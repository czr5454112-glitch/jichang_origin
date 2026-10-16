"""Native022 coverage/parity tests; require an explicitly selected binary."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.native_request_timing import analyze_native_timing, PHASES
from scripts.experiments.g31_ics_circulation.profile_request_bundles import semantics


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        pytest.skip("explicit Native022 binary required")
    result = load_native(binary)
    assert hasattr(result.NativeSession, "offline_request_timing_start")
    return result


def scene(**protocol):
    result = tiny_cycle(); result["transfers"] = []
    result["owner_protocol"] = {"enabled": True, "timeout": .5, "ack_delay": .2, **protocol}
    result["owner_notifications"] = {"enabled": True}
    return result


def transfer(**changes):
    return {"request_id": "live:1:B:return-1", "owner_id": "B", "tray_id": "T0", "source": 4,
        "destination": 0, "earliest_departure": 10., "expiry": 60., "message_delay": 0., **changes}


def stable(value):
    if isinstance(value, dict):
        return {key: stable(child) for key, child in value.items() if key != "wall_seconds"}
    if isinstance(value, list): return [stable(child) for child in value]
    return value


def ordered_semantics(value):
    # Mapping equality ignores insertion order. Preserve it in this exact
    # rendering so diagnostic on/off cannot silently reorder a public view.
    return json.dumps(stable(semantics(value)), ensure_ascii=False, separators=(",", ":"))


def exercise(native, data, *, timed, earliest=10.):
    raw = native.NativeSession(data)
    session = capture_session(raw, capacity=100_000, session_identity=1) if timed else raw
    outputs = []
    outputs.append(session.advance_to(10.))
    payload = transfer(earliest_departure=earliest)
    outputs.append(session.submit_protocol_transfer(payload))
    outputs.append(session.advance_to(11.))
    outputs.append(session.protocol_request("B", payload["request_id"]))
    outputs.append(session.observe_protocol("B"))
    outputs.append(session.observe_protocol_control("B"))
    outputs.append(session.observe_protocol_control_policy("B"))
    outputs.append(session.observe_protocol_control_policy_recent("B", 120.))
    outputs.append(session.protocol_demand_signature("B"))
    outputs.append(session.protocol_planning_snapshots("B"))
    outputs.append(session.submit_protocol_transfer(payload))
    outputs.append(session.advance_to(70.))
    outputs.append(session.submit_protocol_transfer(payload))
    outputs.append(session.advance_to(70.3))
    outputs.append(session.protocol_request("B", payload["request_id"]))
    outputs.append(session.result_at(70.3))
    if timed:
        session.take_completed()
        report = analyze_native_timing(session.batches, session.envelopes)
        assert report["status"] == "validated_partial_native_phase_partition", report
    return raw, outputs, session


@pytest.mark.parametrize("case", ["normal", "future_departure", "source_refused", "receiver_refused", "lost_duplicate_ack", "owner_recovery"])
def test_capture_on_off_preserves_every_result_and_physical_hash(native, case):
    data = scene()
    earliest = 12. if case == "future_departure" else 10.
    if case == "source_refused":
        next(n for n in data["node_contracts"] if n["node"] == 4)["allow_export"] = False
    if case == "receiver_refused":
        next(n for n in data["node_contracts"] if n["node"] == 0)["allow_receive"] = False
    if case == "lost_duplicate_ack":
        data["owner_protocol"].update(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=2.)
    if case == "owner_recovery":
        data["owner_protocol"]["owner_outages"] = [{"owner": "A", "start": 9., "end": 20.}]
    plain, expected, _ = exercise(native, deepcopy(data), timed=False, earliest=earliest)
    recorded, actual, capture = exercise(native, deepcopy(data), timed=True, earliest=earliest)
    assert ordered_semantics(actual) == ordered_semantics(expected)
    assert recorded.offline_state_sha256() == plain.offline_state_sha256()
    rows = capture.batches[-1]["rows"]
    phases = {PHASES[r["phase"]] for r in rows if r["identity_kind"] == 1}
    assert {"source_validate", "ack_create", "ack_delivery"} <= phases
    if case not in {"source_refused"}:
        assert "receiver_validate" in phases
    if case not in {"source_refused", "receiver_refused"}:
        assert "reservation_commit" in phases
        relations = [r for r in rows if PHASES[r["phase"]] == "leg_creation" and r["related_identity_kind"] == 1]
        assert relations and relations[0]["related_identity_index"] == 0


def test_synchronous_rejection_still_has_full_call_identity(native):
    raw = native.NativeSession(scene()); capture = capture_session(raw, session_identity=1)
    reply = capture.submit_protocol_transfer(transfer(request_id="invalid-namespace"))
    assert reply["status"] == "rejected"
    batch = capture.take_completed()
    assert not batch["transfer_identities"]
    assert analyze_native_timing(capture.batches, capture.envelopes)["status"] == "validated_partial_native_phase_partition"


def test_command_publication_and_ack_are_actual_nested_control_work(native):
    raw = native.NativeSession(scene()); capture = capture_session(raw, session_identity=1)
    payload = {"request_id": "live:1:A:demand:0", "owner_id": "A", "kind": "demand",
               "target_owner": "B", "message_delay": .01, "publication_delay": .02}
    assert capture.submit_protocol_command(payload)["status"] == "pending"
    capture.advance_to(.5)
    assert capture.protocol_command("A", payload["request_id"])["last_delivered_ack"]["status"] == "delivered"
    capture.take_completed()
    report = analyze_native_timing(capture.batches, capture.envelopes)
    assert report["status"] == "validated_partial_native_phase_partition", report
    assert {"source_execution", "publication_delivery", "ack_create", "ack_delivery"} <= set(report["exclusive_ns_by_phase"])


def test_overflow_and_restore_unread_capture_cannot_validate(native):
    raw = native.NativeSession(scene()); capture = capture_session(raw, capacity=2, session_identity=1)
    capture.advance_to(10.); capture.take_completed()
    assert analyze_native_timing(capture.batches, capture.envelopes)["status"] == "unknown"
    raw2 = native.NativeSession(scene()); checkpoint = raw2.checkpoint()
    capture2 = capture_session(raw2, session_identity=2); capture2.advance_to(1.)
    raw2.restore(checkpoint)
    batch = raw2.offline_request_timing_take()
    assert not batch["enabled"] and batch["rows"] and batch["errors"]


def test_fork_starts_disabled_without_resetting_parent_trace(native):
    raw = native.NativeSession(scene()); capture = capture_session(raw, session_identity=1)
    capture.advance_to(1.)
    child = raw.fork()
    assert not child.offline_request_timing_take()["enabled"]
    capture.advance_to(2.)
    batch = capture.take_completed()
    assert batch["enabled"] and batch["errors"] == 0 and batch["completed_outer_calls"] == 2
    assert analyze_native_timing(capture.batches, capture.envelopes)["status"] == "validated_partial_native_phase_partition"


@pytest.mark.parametrize("case", ["route_allowed", "route_stale", "forecast_withdraw",
                                  "cancel_pending", "cancel_committed", "planning_snapshot"])
def test_command_phases_preserve_ordered_transcript_and_checkpoint(native, case):
    def run(timed):
        data = scene()
        data["jobs"][0]["allow_suffix_reroute"] = True
        if case == "forecast_withdraw":
            data["node_contracts"][1]["resource_owner"] = "B"
        raw = native.NativeSession(data)
        session = capture_session(raw, session_identity=1) if timed else raw
        outputs = []
        def call(name, *args):
            result = getattr(session, name)(*args); outputs.append(result); return result
        def command(kind, owner="A", **payload):
            return {"request_id": f"live:1:{owner}:{kind}:one", "owner_id": owner, "kind": kind, **payload}
        if case.startswith("route"):
            call("advance_to", .11)
            tray = call("observe_protocol", "A")["trays"][0]
            payload = command("route", business_bag_id=tray["business_bag_id"], tray_id=tray["tray_id"],
                expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
                expiry=5., message_delay=.01 if case == "route_allowed" else .2, next=1)
            payload["from"] = tray["node"]
            call("submit_protocol_command", payload); call("advance_to", .6)
            reply = call("protocol_command", "A", payload["request_id"])["last_delivered_ack"]
            assert reply["reason"] == ("allowed" if case == "route_allowed" else "stale_executed_prefix")
            required = {"permission_validate", "source_execution"}
        elif case == "forecast_withdraw":
            call("advance_to", .05)
            forecast = command("service_forecast", target_owner="B", tray_id="T0", next=1, publication_delay=2.)
            call("submit_protocol_command", forecast); call("advance_to", .06)
            payload = command("withdraw_service_forecast", forecast_request_id=forecast["request_id"], publication_delay=.1)
            call("submit_protocol_command", payload); call("advance_to", 2.5)
            assert call("protocol_command", "A", payload["request_id"])["last_delivered_ack"]["status"] == "delivered"
            required = {"withdrawal", "publication_delivery"}
        elif case.startswith("cancel"):
            call("advance_to", 10.)
            pending = case == "cancel_pending"
            request = transfer(earliest_departure=50. if pending else 10.)
            call("submit_protocol_transfer", request); call("advance_to", 10.1)
            payload = command("cancel_transfer", owner="B", transfer_request_id=request["request_id"])
            call("submit_protocol_command", payload); call("advance_to", 11.)
            assert call("protocol_command", "B", payload["request_id"])["last_delivered_ack"]["status"] == ("cancelled" if pending else "rejected")
            required = {"cancellation", "source_execution"}
        else:
            payload = command("planning_snapshot", target_owner="B", message_delay=.01, publication_delay=.02, expiry=5.)
            call("submit_protocol_command", payload); call("advance_to", .5)
            assert call("protocol_command", "A", payload["request_id"])["last_delivered_ack"]["status"] == "delivered"
            assert call("protocol_planning_snapshots", "B")
            required = {"publication_delivery", "source_execution"}
        call("result_at", 70.)
        if timed:
            session.take_completed()
            report = analyze_native_timing(session.batches, session.envelopes)
            assert report["status"] == "validated_partial_native_phase_partition", report
            assert required <= set(report["exclusive_ns_by_phase"])
        return ordered_semantics(outputs), raw.offline_state_sha256(), raw.checkpoint().offline_state_sha256
    expected = run(False); actual = run(True)
    assert actual == expected
