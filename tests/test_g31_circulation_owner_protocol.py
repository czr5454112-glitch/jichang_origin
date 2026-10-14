"""Native ACK loss/duplication and owner outage transfer subprotocol."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = str(next((Path(__file__).absolute().parents[1]/"build_lt_session_009/python").glob("czr005_circulation*.pyd")))
    return load_native(binary)


def data(**protocol):
    value = tiny_cycle(); value["transfers"] = []
    value["owner_protocol"] = dict(enabled=True, timeout=.5, ack_delay=.2, **protocol)
    return value


def request():
    return dict(request_id="live:1:B:return-1", owner_id="B", tray_id="T0", source=4, destination=0,
                earliest_departure=10., expiry=60., message_delay=0.)


def start(native, value):
    session = native.NativeSession(value);session.advance_to(10.)
    assert session.submit_protocol_transfer(request())["status"] == "pending"
    return session


def audited(value, session, horizon=70.):
    result = session.result_at(horizon)
    replay = deepcopy(value); replay["transfers"] = [dict(request(), issued_at=10.)]
    assert audit_result(replay, result)["status"] == "passed"
    assert len(result["transfers"]) == 1
    assert sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]) <= 1
    return result


def test_lost_ack_keeps_real_physics_and_retry_does_not_mint_or_release(native):
    value = data(drop_ack_packets=1)
    session = start(native, value);session.advance_to(11.)
    unknown = session.protocol_request("B", request()["request_id"])
    assert unknown["status"] == "timeout_unknown" and "last_delivered_ack" not in unknown
    assert not session.observe_protocol("B")["delivered_transfer_acks"]
    assert "transfers" not in session.observe_protocol("B")
    before = session.offline_state_sha256()
    assert session.protocol_request("B", request()["request_id"]) == unknown
    assert session.offline_state_sha256() == before
    assert session.submit_protocol_transfer(request()) == {"status": "pending", "reason": "retry_enqueued"}
    session.advance_to(11.3)
    assert session.protocol_request("B", request()["request_id"])["status"] == "acknowledged"
    result = audited(value, session)
    assert [j["status"] for j in result["jobs"]] == ["completed", "completed"]
    assert result["transfers"][0]["status"] == "received"


def test_late_retry_after_departure_and_expiry_returns_only_delivered_snapshot(native):
    value = data(drop_ack_packets=1)
    session = start(native, value);session.advance_to(65.)
    assert session.protocol_request("B", request()["request_id"])["status"] == "timeout_unknown"
    assert session.submit_protocol_transfer(request())["status"] == "pending"
    assert "last_delivered_ack" not in session.protocol_request("B", request()["request_id"])
    session.advance_to(65.3)
    answer = session.protocol_request("B", request()["request_id"])
    assert answer["last_delivered_ack"]["status"] == "received"
    assert answer["last_delivered_ack"]["observed_at"] == 65.
    audited(value, session)


def test_duplicate_ack_and_old_copy_cannot_replace_newer_delivered_sequence(native):
    value = data(duplicate_acks=True, duplicate_ack_delay=5.)
    session = start(native, value);session.advance_to(11.)
    first = session.protocol_request("B", request()["request_id"])["last_delivered_ack"]
    assert session.submit_protocol_transfer(request())["status"] == "pending"
    session.advance_to(12.)
    second = session.protocol_request("B", request()["request_id"])["last_delivered_ack"]
    assert second["sequence"] > first["sequence"]
    session.advance_to(15.3)
    assert session.protocol_request("B", request()["request_id"])["last_delivered_ack"] == second
    delivered = session.observe_protocol("B")["delivered_transfer_acks"]
    assert next(a for a in delivered if a["sequence"] == first["sequence"])["delivered_copies"] == 2
    audited(value, session)


@pytest.mark.parametrize("owner", ["A", "B"])
def test_owner_unavailable_defers_real_request_until_recovery(native, owner):
    value = data(owner_outages=[dict(owner=owner, start=9., end=20.)])
    session = start(native, value);session.advance_to(19.)
    assert session.protocol_request("B", request()["request_id"])["status"] == "timeout_unknown"
    prefix = session.result_at(19.)
    assert prefix["jobs"][0]["status"] == "completed"  # local service is not stopped
    assert not any(r["event"] in ("MODULE_REQUEST_DELIVERED", "EXPORT_GRANTED") for r in prefix["receipts"])
    session.advance_to(20.3)
    answer = session.protocol_request("B", request()["request_id"])
    assert answer["status"] == "acknowledged" and answer["last_delivered_ack"]["observed_at"] == 20.
    result = audited(value, session)
    assert all(r["time"] >= 20 for r in result["receipts"] if r["event"] == "EXPORT_GRANTED")
    assert result["jobs"][1]["status"] == "completed"


def test_already_committed_empty_transfer_and_reception_survive_owner_outage(native):
    value = data(owner_outages=[dict(owner="A", start=10.2, end=40.), dict(owner="B", start=10.2, end=40.)])
    session = start(native, value)
    result = audited(value, session)
    assert result["transfers"][0]["received_at"] < 40.
    assert result["jobs"][1]["completed_at"] < 40.
    assert sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]) == 1


def test_pending_future_release_cannot_grant_from_unrelated_events_during_outage(native):
    value = data(owner_outages=[dict(owner="A", start=8.1, end=20.)])
    session = native.NativeSession(value);session.advance_to(8.)
    early = dict(request(), earliest_departure=8.)
    assert session.submit_protocol_transfer(early)["status"] == "pending"
    session.advance_to(19.)
    result = session.result_at(19.)
    assert result["transfers"][0]["status"] == "pending"
    assert not any(r["event"] == "EXPORT_GRANTED" for r in result["receipts"])
    session.advance_to(20.)
    assert any(r["event"] == "EXPORT_GRANTED" and r["time"] == 20. for r in session.result_at(20.)["receipts"])


def test_payload_conflict_and_other_owner_namespace_never_mutate_physics(native):
    session = start(native, data())
    before = session.offline_state_sha256()
    assert session.submit_protocol_transfer(dict(request(), expiry=61.))["reason"] == "request_identity_conflict"
    assert session.submit_protocol_transfer(dict(request(), owner_id="A"))["reason"] == "owner_request_namespace_required"
    assert session.protocol_request("A", request()["request_id"])["status"] == "unknown_request"
    assert session.offline_state_sha256() == before


def test_refusal_is_unknown_until_actual_delayed_ack(native):
    value = data(); value["owner_protocol"]["ack_delay"] = 2.
    next(n for n in value["node_contracts"] if n["node"] == 0)["allow_receive"] = False
    session = start(native, value);session.advance_to(11.)
    assert session.protocol_request("B", request()["request_id"])["status"] == "timeout_unknown"
    assert not session.observe_protocol("B")["delivered_transfer_acks"]
    session.advance_to(12.)
    ack = session.protocol_request("B", request()["request_id"])["last_delivered_ack"]
    assert ack["status"] == "rejected" and ack["reason"] == "destination_module_refused"
    audited(value, session)


@pytest.mark.parametrize("boundary", [10., 10.1, 10.3, 11., 20.1])
def test_protocol_checkpoint_seals_pending_ack_drops_outage_and_client_timeout(native, boundary):
    value = data(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=2.,
                 owner_outages=[dict(owner="A", start=9., end=20.)])
    parent = start(native, value);parent.advance_to(boundary)
    before = parent.offline_state_sha256()
    a, b = parent.fork(), native.NativeSession(value)
    b.restore(parent.checkpoint())
    assert a.offline_state_sha256() == b.offline_state_sha256() == before
    ar, br = a.result_at(70.), b.result_at(70.)
    for key in ("receipts", "jobs", "trays", "transfers", "leg_identities"):
        assert ar[key] == br[key]
    assert a.observe_protocol("B") == b.observe_protocol("B")
    assert a.offline_state_sha256() == b.offline_state_sha256()
    assert parent.offline_state_sha256() == before


def test_protocol_projection_ignores_hidden_future_and_blocks_legacy_online_bypass(native):
    one = data(drop_ack_packets=1); two = deepcopy(one)
    one["jobs"][1]["arrival"] = 50.; two["jobs"][1]["arrival"] = 60.
    a, b = start(native, one), start(native, two)
    for time in (10., 10.3, 11.):
        a.advance_to(time);b.advance_to(time)
        assert a.observe_protocol("B") == b.observe_protocol("B")
    for call in (lambda: a.observe("B"), lambda: a.observe_control("B"), lambda: a.demand_signature("B"),
                 lambda: a.submit_transfer_intent(request()), lambda: a.cancel_transfer_intent(request()["request_id"], "B"),
                 lambda: a.publish_demand("A", "B", 0)):
        with pytest.raises(ValueError, match="owner_protocol_endpoint_required"):
            call()
    # Offline diagnostics, checkpoints and actual results intentionally remain
    # available to the experiment harness, not an untrusted controller API.
    assert a.result_at(11.)["mode"] == "circulation"
    assert a.offline_diagnostics()["schema"].endswith("v1")


def test_static_owner_cache_is_rebuilt_after_cross_config_restore(native):
    first = tiny_cycle();first["transfers"] = []
    second = deepcopy(first)
    for node in second["node_contracts"]:
        node["resource_owner"] = "other-"+node["zone"]
    a, b = native.NativeSession(first), native.NativeSession(second)
    a.advance_to(.5);b.restore(a.checkpoint())
    for owner in ("A", "B"):
        assert a.observe(owner) == b.observe(owner)
        assert a.observe_control(owner) == b.observe_control(owner)
        assert a.demand_signature(owner) == b.demand_signature(owner)


def test_unreceived_ack_and_hidden_destination_uptime_do_not_change_projection(native):
    up = data();up["owner_protocol"]["ack_delay"] = 100.
    down = deepcopy(up)
    down["owner_protocol"]["owner_outages"] = [dict(owner="A", start=9., end=20.)]
    sessions = [native.NativeSession(value) for value in (up, down)]
    req = dict(request(), earliest_departure=50.)
    for session in sessions:
        session.advance_to(10.)
        assert session.submit_protocol_transfer(req)["status"] == "pending"
        session.advance_to(11.)
    a, b = [s.observe_protocol("B") for s in sessions]
    assert "version" not in a and "transfers" not in a
    assert a == b
    assert a["client_requests"][0]["status"] == "timeout_unknown"
    assert not a["delivered_transfer_acks"]


def test_adjacent_outages_do_not_create_a_same_timestamp_grant_gap(native):
    value = data(owner_outages=[dict(owner="A", start=9., end=20.), dict(owner="A", start=20., end=30.)])
    session = start(native, value);session.advance_to(25.)
    assert not any(r["event"] == "EXPORT_GRANTED" for r in session.result_at(25.)["receipts"])
    session.advance_to(30.)
    grants = [r for r in session.result_at(30.)["receipts"] if r["event"] == "EXPORT_GRANTED"]
    assert len(grants) == 1 and grants[0]["time"] == 30.
    audited(value, session)


def test_lifecycle_release_at_outage_start_cannot_grant_before_outage_phase(native):
    # Tiny contract actual HOLD_COMPLETE is 9.9; it calls circulation_progress
    # at the same timestamp as this new destination outage.
    value = data(owner_outages=[dict(owner="A", start=9.9, end=20.)])
    session = native.NativeSession(value);session.advance_to(8.)
    assert session.submit_protocol_transfer(dict(request(), earliest_departure=8.))["status"] == "pending"
    session.advance_to(15.)
    result = session.result_at(15.)
    assert any(r["event"] == "HOLD_COMPLETE" and r["time"] == 9.9 for r in result["receipts"])
    assert not any(r["event"] == "EXPORT_GRANTED" for r in result["receipts"])
    session.advance_to(20.)
    assert sum(r["event"] == "EXPORT_GRANTED" and r["time"] == 20. for r in session.result_at(20.)["receipts"]) == 1


def test_same_timestamp_recovery_and_multiple_retries_ack_latest_attempt_once_physically(native):
    value = data(owner_outages=[dict(owner="A", start=9., end=20.)])
    session = native.NativeSession(value);session.advance_to(10.)
    req = dict(request(), message_delay=.2)
    assert session.submit_protocol_transfer(req)["status"] == "pending"
    session.advance_to(19.8)
    assert session.submit_protocol_transfer(req)["status"] == "pending"
    assert session.submit_protocol_transfer(req)["status"] == "pending"
    session.advance_to(20.5)
    answer = session.protocol_request("B", req["request_id"])
    assert answer["attempt"] == 3 and answer["status"] == "acknowledged"
    acks = session.observe_protocol("B")["delivered_transfer_acks"]
    assert any(a["attempt"] == 3 for a in acks)
    result = session.result_at(70.)
    assert len(result["transfers"]) == 1
    assert sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]) == 1
    assert result["transfers"][0]["status"] == "received"


def test_protocol_rejects_nonfinite_derived_ack_before_session_creation(native):
    value = data();value["options"]["max_simulation_time"] = 1.e308
    value["owner_protocol"]["ack_delay"] = 1.e308
    with pytest.raises(ValueError, match="nonfinite_derived_time"):
        native.NativeSession(value)
