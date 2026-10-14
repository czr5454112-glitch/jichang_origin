"""Real owner commands: source processing, peer delivery and immutable ACKs."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.analytic_control import transfer_candidates


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = str(next((Path(__file__).absolute().parents[1] / "build_lt_session_010/python").glob("czr005_circulation*.pyd")))
    return load_native(binary)


def data(**protocol):
    value = tiny_cycle(); value["transfers"] = []
    value["jobs"][0]["allow_suffix_reroute"] = True
    value["owner_protocol"] = dict(enabled=True, timeout=.5, ack_delay=.2)
    value["owner_protocol"].update(protocol)
    return value


def command(kind, owner="A", suffix="one", **payload):
    return dict(request_id=f"live:{len(owner.encode('utf-8'))}:{owner}:{kind}:{suffix}",
                owner_id=owner, kind=kind, **payload)


def route(session, **extra):
    tray = session.observe_protocol("A")["trays"][0]
    payload = dict(business_bag_id=tray["business_bag_id"], tray_id=tray["tray_id"],
                   expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
                   expiry=5., message_delay=.01, next=1)
    payload["from"] = tray["node"]; payload.update(extra)
    return command("route", **payload)


def ack(session, request):
    return session.protocol_command(request["owner_id"], request["request_id"]).get("last_delivered_ack")


def transfer(**extra):
    out = dict(request_id="live:1:B:return", owner_id="B", tray_id="T0", source=4, destination=0,
               earliest_departure=10., expiry=60., message_delay=0.)
    out.update(extra); return out


@pytest.mark.parametrize("delay,allowed,reason", [(.01, True, "allowed"), (.2, True, "stale_executed_prefix"),
                                                (.01, False, "service_obligation_disallows_reroute")])
def test_route_ack_follows_real_revalidation_and_never_exposes_raw_request(native, delay, allowed, reason):
    value = data(); value["jobs"][0]["allow_suffix_reroute"] = allowed
    s = native.NativeSession(value); s.advance_to(.11); request = route(s, message_delay=delay)
    assert s.submit_protocol_command(request)["status"] == "pending"
    assert ack(s, request) is None
    s.advance_to(.11 + delay)
    assert ack(s, request) is None  # native validation happened, ACK has not arrived
    assert "route_requests" not in s.observe_protocol("A")
    s.advance_to(.31 + delay + 1e-8)
    result = ack(s, request)
    assert result["reason"] == reason
    assert result["status"] == ("updated" if reason == "allowed" else "rejected")
    assert result["executed_at"] == pytest.approx(.11 + delay)
    assert result["completed_at"] == pytest.approx(.11 + delay)
    assert s.result_at(30)["jobs"][0]["status"] == "completed"


def test_lost_route_ack_retries_cached_validation_without_second_route(native):
    s = native.NativeSession(data(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=2.))
    s.advance_to(.11); request = route(s)
    s.submit_protocol_command(request); s.advance_to(1.)
    assert s.protocol_command("A", request["request_id"])["status"] == "timeout_unknown"
    assert s.submit_protocol_command(request) == dict(status="pending", reason="retry_enqueued")
    s.advance_to(1.3)
    assert ack(s, request)["status"] == "updated"  # actual tray has long since moved
    saved = deepcopy(ack(s, request)); s.advance_to(3.)
    assert ack(s, request) == saved  # old duplicate cannot roll back sequence
    assert sum(r["event"].startswith("ROUTE_INTENT_") for r in s.result_at(3.)["receipts"]) == 1


def test_source_outage_defers_route_execution_and_can_cause_real_staleness(native):
    s = native.NativeSession(data(owner_outages=[dict(owner="A", start=.115, end=.5)]))
    s.advance_to(.11); request = route(s)
    s.submit_protocol_command(request); s.advance_to(.49)
    assert ack(s, request) is None
    s.advance_to(.71)
    assert ack(s, request)["reason"] == "stale_executed_prefix"
    assert ack(s, request)["executed_at"] == .5


def test_demand_captures_at_real_source_execution_and_delivers_after_recipient_recovery(native):
    value = data(owner_outages=[dict(owner="A", start=.01, end=.5), dict(owner="B", start=.4, end=2.)])
    value["jobs"][1]["arrival"] = .2
    s = native.NativeSession(value); s.advance_to(.05)
    request = command("demand", target_owner="B", publication_delay=.1)
    s.submit_protocol_command(request); s.advance_to(1.)
    assert ack(s, request) is None
    assert s.observe_protocol("B")["delivered_messages"] == []
    # A real retry gives an honest pending result, without recapturing a queue.
    s.submit_protocol_command(request); s.advance_to(1.3)
    assert ack(s, request)["status"] == "pending_delivery"
    s.advance_to(2.21)
    final = ack(s, request)
    assert final["status"] == "delivered" and final["executed_at"] == .5 and final["completed_at"] == 2.
    message, = s.observe_protocol("B")["delivered_messages"]
    assert message["observed_at"] == .5 and message["delivered_at"] == 2.
    assert [j["business_bag_id"] for j in message["jobs"]] == ["B2"]
    assert message["message_id"] == final["result_id"]
    s.advance_to(5.); assert s.observe_protocol("B")["delivered_messages"] == [message]


def test_captured_message_can_receive_peer_ack_while_source_is_down(native):
    s = native.NativeSession(data(owner_outages=[dict(owner="A", start=.2, end=2.)]))
    s.advance_to(.05); request = command("demand", target_owner="B", publication_delay=.5)
    s.submit_protocol_command(request); s.advance_to(.8)
    assert ack(s, request)["status"] == "delivered"
    assert ack(s, request)["executed_at"] == .05
    assert ack(s, request)["completed_at"] == .55


def forecast_scene(**config):
    value = data(**config); value["node_contracts"][1]["resource_owner"] = "B"
    return value


def test_forecast_then_exact_withdraw_without_original_ack_and_out_of_order_delivery(native):
    s = native.NativeSession(forecast_scene(drop_ack_packets=1))
    s.advance_to(.05)
    forecast = command("service_forecast", target_owner="B", tray_id="T0", next=1, publication_delay=2.)
    s.submit_protocol_command(forecast); s.advance_to(.06)
    assert ack(s, forecast) is None
    withdraw = command("withdraw_service_forecast", forecast_request_id=forecast["request_id"], publication_delay=.1)
    s.submit_protocol_command(withdraw); s.advance_to(.7)
    tombstone, = s.observe_protocol("B")["delivered_messages"]
    assert tombstone["status"] == "withdrawn" and tombstone["observed_at"] == .06
    assert tombstone["entry_estimate"] == pytest.approx(.15)
    assert s.submit_protocol_command(withdraw)["status"] == "pending"
    s.advance_to(1.)
    assert ack(s, withdraw)["status"] == "delivered"
    assert ack(s, withdraw)["result_id"] == tombstone["message_id"]
    s.advance_to(2.5)
    messages = s.observe_protocol("B")["delivered_messages"]
    assert len(messages) == 2 and messages[0]["message_id"] == tombstone["supersedes"]
    assert sum(m["status"] == "withdrawn" for m in messages) == 1
    assert messages[0]["observed_at"] == .05 and messages[0]["delivered_at"] == 2.05
    assert s.result_at(30.)["jobs"][0]["status"] == "completed"


def test_forecast_deferred_source_checks_current_local_service_not_old_payload(native):
    value = forecast_scene(owner_outages=[dict(owner="A", start=.01, end=1.)])
    s = native.NativeSession(value); s.advance_to(.05)
    request = command("service_forecast", target_owner="B", tray_id="T0", next=1)
    s.submit_protocol_command(request); s.advance_to(1.3)
    assert ack(s, request)["status"] == "rejected"
    assert not s.observe_protocol("B")["delivered_messages"]


@pytest.mark.parametrize("earliest,expected", [(50., "cancelled"), (10., "rejected")])
def test_cancel_real_pending_only_and_cannot_undo_committed_lease(native, earliest, expected):
    value = data(drop_ack_packets=1)
    s = native.NativeSession(value); s.advance_to(10.)
    t = transfer(earliest_departure=earliest); s.submit_protocol_transfer(t); s.advance_to(10.1)
    c = command("cancel_transfer", owner="B", transfer_request_id=t["request_id"])
    s.submit_protocol_command(c); s.advance_to(11.)
    assert ack(s, c) is None
    s.submit_protocol_command(c); s.advance_to(11.3)
    assert ack(s, c)["status"] == expected
    ledger, = s.observe_protocol_control("B")["client_transfer_ledger"]
    assert ledger["status"] == ("cancelled" if expected == "cancelled" else "pending")
    result = s.result_at(70.)
    assert result["transfers"][0]["status"] == ("cancelled" if expected == "cancelled" else "received")
    assert sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]) == (0 if earliest == 50 else 1)


def test_command_identity_domain_conflicts_and_other_owner_reference_do_not_mutate(native):
    s = native.NativeSession(data()); s.advance_to(10.)
    t = transfer(earliest_departure=50.); s.submit_protocol_transfer(t)
    request = command("demand", owner="B", target_owner="A"); s.submit_protocol_command(request)
    before = s.offline_state_sha256()
    assert s.submit_protocol_command(dict(request, publication_delay=1.))["reason"] == "request_identity_conflict"
    assert s.submit_protocol_command(dict(request, kind="cancel_transfer", transfer_request_id=t["request_id"]))["reason"] == "request_identity_conflict"
    assert s.submit_protocol_command(dict(request, request_id=t["request_id"]))["reason"] == "request_identity_conflict"
    assert s.submit_protocol_transfer(dict(t, request_id=request["request_id"]))["reason"] == "request_identity_conflict"
    foreign = command("cancel_transfer", transfer_request_id=t["request_id"])
    assert s.submit_protocol_command(foreign)["reason"] == "reference_not_owned"
    assert s.protocol_command("A", request["request_id"])["status"] == "unknown_request"
    assert s.offline_state_sha256() == before


@pytest.mark.parametrize("boundary", [.05, .3, .6, 2.1, 3.])
def test_commands_checkpoint_preserves_wire_peer_recovery_drop_duplicate_and_retry(native, boundary):
    value = data(owner_outages=[dict(owner="A", start=.01, end=.5), dict(owner="B", start=.4, end=2.)],
                 drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=1.)
    s = native.NativeSession(value); s.advance_to(.05)
    request = command("demand", target_owner="B", publication_delay=.1)
    s.submit_protocol_command(request); s.advance_to(boundary)
    fork = s.fork(); restored = native.NativeSession(value); restored.restore(s.checkpoint())
    for branch in (s, fork, restored):
        branch.advance_to(4.); branch.submit_protocol_command(request); branch.advance_to(5.)
    assert s.offline_state_sha256() == fork.offline_state_sha256() == restored.offline_state_sha256()
    assert s.observe_protocol("A") == fork.observe_protocol("A") == restored.observe_protocol("A")
    assert s.observe_protocol_control("B") == fork.observe_protocol_control("B") == restored.observe_protocol_control("B")
    assert ack(s, request)["status"] == "delivered"


def test_protocol_compact_incoming_uses_only_delivered_ack_and_hidden_outage_cannot_leak(native):
    first = data(ack_delay=100.)
    second = deepcopy(first); second["owner_protocol"]["owner_outages"] = [dict(owner="A", start=9., end=20.)]
    a, b = native.NativeSession(first), native.NativeSession(second)
    for s in (a, b):
        s.advance_to(8.)
        s.submit_protocol_command(command("demand", target_owner="B")); s.advance_to(10.)
        s.submit_protocol_transfer(transfer(earliest_departure=50.)); s.advance_to(11.)
    assert a.offline_state_sha256() != b.offline_state_sha256()
    assert a.observe_protocol_control("B") == b.observe_protocol_control("B")
    assert a.observe_protocol("B") == b.observe_protocol("B")
    for s in (a, b):
        full, compact = s.observe_protocol("B"), s.observe_protocol_control("B")
        for view in (full, compact): view["transfers"] = view["client_transfer_ledger"]
        assert transfer_candidates(full, predictive=True)["intents"] == transfer_candidates(compact, predictive=True)["intents"]


def test_transfer_received_timestamp_is_physical_and_not_late_ack_time(native):
    s = native.NativeSession(data(drop_ack_packets=1)); s.advance_to(10.)
    t = transfer(); s.submit_protocol_transfer(t); s.advance_to(30.)
    s.submit_protocol_transfer(t); s.advance_to(30.3)
    received = s.protocol_request("B", t["request_id"])["last_delivered_ack"]
    actual = s.result_at(30.3)["transfers"][0]
    assert received["status"] == "received" and received["received_at"] == actual["received_at"]
    assert received["received_at"] < received["observed_at"] == 30.


def test_protocol_signature_remains_exact_after_restore_and_hides_unreleased_jobs(native):
    first = data(); second = deepcopy(first)
    first["jobs"][1]["arrival"] = 40.; second["jobs"][1]["arrival"] = 50.
    a, b = native.NativeSession(first), native.NativeSession(second)
    a.advance_to(.1); b.advance_to(.1)
    assert a.protocol_demand_signature("A") == b.protocol_demand_signature("A")
    b.restore(a.checkpoint())
    a.advance_to(45.); b.advance_to(45.)
    assert a.protocol_demand_signature("A") == b.protocol_demand_signature("A")
    assert a.protocol_demand_signature("A")["waiting_count"] == 1
