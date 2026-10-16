"""Actual opt-in native v3 facts; requires an explicitly selected new binary.

Drafting/collecting these tests does not execute or accept a native version.
Offline result receipts below are verification evidence, never policy inputs.
"""
from copy import deepcopy
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input
from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
from scripts.experiments.g31_ics_circulation.planning_capture_v3_contract import (
    capture_digest_v3, reconcile_capture_occupancy, validate_inflight,
)


@pytest.fixture(scope="module")
def native():
    global _verified_native_for_gate
    module = load_native(os.environ["G31_CIRCULATION_BINARY"])
    assert hasattr(module.NativeSession, "protocol_planning_snapshots_v3")
    _verified_native_for_gate = module
    return module


def scene(**protocol):
    return prepare_input({
        "schema": "g31.circulation.input.v1",
        "model_scope": "synthetic long edge; observed entry separated from reservation",
        "node_records": [(0, 1, 1., 0, 0, [1]), (1, 1, .05, 1, 0, [])],
        "edge_records": [(0, 1, 10., 1.)],
        "node_contracts": [{"node": n, "zone": owner, "resource_owner": owner, "capacity": 1}
                           for n, owner in ((0, "A"), (1, "B"))],
        "edge_contracts": [{"from": 0, "to": 1, "capacity": 1, "entry_headway": .2}],
        "trays": [{"tray_id": "T0", "node": 0}],
        "jobs": [{"business_bag_id": "B1", "origin": 0, "destination": 1, "arrival": 0.,
                  "deadline": 40., "load_seconds": .1, "unload_seconds": .5, "hold_seconds": .2}],
        "transfers": [], "faults": [], "options": {"max_simulation_time": 80.},
        "owner_protocol": {"enabled": True, "timeout": .2, "ack_delay": .01, **protocol},
        "owner_notifications": {"enabled": True},
    })


def contract(data):
    return {key: deepcopy(data[key]) for key in ("node_contracts", "edge_contracts", "edge_records")} | {
        "native_semantics": {"minimum_service_seconds": .001}}


def request(identity="one", source="A", target="B", **changes):
    return {"request_id": f"live:{len(source.encode())}:{source}:planning-v3:{identity}",
        "owner_id": source, "kind": "planning_snapshot_v3", "target_owner": target,
        "message_delay": 0., "publication_delay": .01, "expiry": 60., **changes}


def self_copy(session, payload):
    return session.protocol_command(payload["owner_id"], payload["request_id"])["last_delivered_ack"]["planning_snapshot_v3"]


def publish(session, identity="one", source="A", target="B", **changes):
    payload = request(identity, source, target, **changes)
    assert session.submit_protocol_command(payload)["status"] == "pending"
    session.advance_to(session.physical_time + .03)
    return self_copy(session, payload)


def test_reservation_before_actual_entry_retains_unmatched_denominator(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(1.)
    # The complete .2 timestamp has no edge reservation. Stop at the actual
    # 1.1 dispatch publication, before its same-time EDGE_ENTER microevent.
    # This deliberately incomplete timestamp is a negative capture fixture,
    # never a production controller admission boundary.
    for _ in range(5):
        progress = session.advance_to(1.1, max_events=1)
        assert progress["status"] == "budget_exhausted" and not progress["horizon_complete"]
    tray = session.observe_protocol("A")["trays"][0]
    assert tray["edge_to"] == 1 and "edge_exit_at" not in tray
    envelope = publish(session)
    body = envelope["capture"]; extension = body["extension"]
    assert extension["captured_at"] == 1.1
    assert extension["source_observed_inflight"] == []
    assert extension["coverage"]["source_owned_inflight_tray_ids"] == ["T0"]
    assert extension["coverage"]["unmatched_tray_ids"] == ["T0"]
    assert extension["coverage"]["complete_for_declared_source_inflight"] is False
    checked = validate_inflight(body, contract(data), now=session.physical_time, delivered_at=envelope["delivered_at"])
    assert checked["status"] == "unknown" and checked["reason"] == "unobserved_or_unmatched_committed_entry"
    assert capture_digest_v3(body) == envelope["payload_sha256"]


def test_actual_entry_public_identity_and_exact_source_observable_exit(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(1.3)
    current = session.observe_protocol("A")["trays"][0]
    envelope = publish(session); body = envelope["capture"]
    assert envelope["schema"] == "g31.planning_snapshot.v3" and envelope["kind"] == "planning_snapshot_v3"
    assert envelope["digest_format"] == "g31.planning_capture_digest.v3"
    assert set(body) == {"schema", "capture_v2", "extension"}
    assert body["capture_v2"]["schema"] == "g31.planning_capture.v2"
    assert len(capture_digest_v2(body["capture_v2"])) == 64
    row, = body["extension"]["source_observed_inflight"]
    assert row["receipt_event"] == "EDGE_ENTER" and row["source_owner"] == "A"
    for key in ("tray_id", "business_bag_id", "generation", "traversal_id", "edge_from", "edge_to"):
        assert row[key] == current[key]
    assert row["static_edge_travel_seconds"] == 10.
    assert row["derived_edge_exit_at"] == row["entered_at"] + 10. == current["edge_exit_at"]
    assert not {"internal_traversal_id", "transport_leg_id", "event_seq", "runtime_id"} & set(row)
    receipts = session.result_at(session.physical_time)["receipts"]
    actual = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["tray_id"] == "T0"]
    assert len(actual) == 1 and row["entered_at"] == actual[0]["time"]
    assert body["extension"]["coverage"]["complete_for_declared_source_inflight"] is True
    assert body["extension"]["coverage"]["unmatched_tray_ids"] == []
    checked = validate_inflight(body, contract(data), now=session.physical_time, delivered_at=envelope["delivered_at"])
    assert checked["status"] == "conditional_inflight_extension_data"
    assert not checked["native_delivery_verified"] and not checked["native_protection_certified"]
    assert capture_digest_v3(body) == envelope["payload_sha256"]


def test_remote_incoming_identified_occupancy_and_no_atomic_cut_claim(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(1.3)
    payloads = [request(source=owner, target=peer) for owner, peer in (("A", "B"), ("B", "A"))]
    for payload in payloads: session.submit_protocol_command(payload)
    session.advance_to(1.33)
    envelopes = [self_copy(session, payload) for payload in payloads]
    target = envelopes[1]["capture"]["capture_v2"]["local_capture"]
    assert target["trays"] == []
    assert target["nodes"][0]["occupancy"] == target["nodes"][0]["unrepresented_occupancy"] == 1
    checked = reconcile_capture_occupancy([e["capture"] for e in envelopes], contract(data),
        now=session.physical_time, delivered_at_by_source={p["owner_id"]: e["delivered_at"] for p, e in zip(payloads, envelopes)})
    assert checked["status"] == "conditional_same_timestamp_occupancy_consistency"
    assert len(checked["reservations_by_node"][1]) == 1
    assert not any(checked[key] for key in ("atomic_capture_cut_verified", "simultaneous_state_certified", "current_state_certified"))
    for envelope in envelopes:
        assert envelope["capture"]["capture_v2"]["extension"]["submitted_physical_actions"] == []


def test_source_changes_after_exit_and_old_capture_cannot_prove_arrival(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(1.3)
    old = publish(session); entry = old["capture"]["extension"]["source_observed_inflight"][0]
    at = entry["derived_edge_exit_at"]
    checked = validate_inflight(old["capture"], contract(data), now=at, delivered_at=old["delivered_at"], maximum_age=20.)
    assert checked["status"] == "unknown"
    session.advance_to(12.)
    a = publish(session, "after", source="A", target="B")
    b = publish(session, "after", source="B", target="A")
    for envelope in (a, b):
        assert envelope["capture"]["extension"]["source_observed_inflight"] == []
        assert envelope["capture"]["extension"]["coverage"]["source_owned_inflight_tray_ids"] == []
    assert a["capture"]["capture_v2"]["local_capture"]["trays"] == []
    assert [r["business_bag_id"] for r in b["capture"]["capture_v2"]["extension"]["terminal_receipts"]] == ["B1"]


@pytest.mark.parametrize("at", [1.3, 1.305, 1.315, 1.33])
def test_checkpoint_retry_peer_selfcopy_and_typed_digest_are_exact(native, at):
    session = native.NativeSession(scene(drop_ack_packets=1)); session.advance_to(1.3)
    payload = request(); session.submit_protocol_command(payload); session.advance_to(at)
    checkpoint, branch = session.checkpoint(), session.fork()
    session.advance_to(2.); session.restore(checkpoint)
    for current in (session, branch):
        current.advance_to(1.35); current.submit_protocol_command(payload); current.advance_to(1.4)
    assert session.offline_state_sha256() == branch.offline_state_sha256()
    envelope = self_copy(session, payload)
    assert envelope == self_copy(branch, payload) == session.protocol_planning_snapshots_v3("B")[0]
    assert capture_digest_v3(envelope["capture"]) == envelope["payload_sha256"]
    original = deepcopy(envelope)
    envelope["capture"]["extension"]["source_observed_inflight"][0]["entered_at"] += .1
    assert capture_digest_v3(envelope["capture"]) != original["payload_sha256"]
    assert self_copy(session, payload) == original
    assert session.protocol_planning_snapshots("B") == session.protocol_planning_snapshots_v2("B") == []


def test_lost_self_ack_does_not_hide_peer_or_recapture_on_retry(native):
    session = native.NativeSession(scene(drop_ack_packets=1)); session.advance_to(1.3)
    payload = request(); session.submit_protocol_command(payload); session.advance_to(1.35)
    peer = session.protocol_planning_snapshots_v3("B")[0]
    assert "last_delivered_ack" not in session.protocol_command("A", payload["request_id"])
    session.submit_protocol_command(payload); session.advance_to(1.4)
    assert self_copy(session, payload) == peer
    assert session.protocol_command("A", payload["request_id"])["attempt"] == 2


@pytest.mark.parametrize("owner,capture,delivery", [("A", 1.4, 1.41), ("B", 1.3, 1.4)])
def test_outage_capture_and_delivery_preserve_causal_source_facts(native, owner, capture, delivery):
    session = native.NativeSession(scene(owner_outages=[{"owner": owner, "start": 1.2, "end": 1.4}]))
    session.advance_to(1.3); payload = request(); session.submit_protocol_command(payload); session.advance_to(1.35)
    assert session.protocol_planning_snapshots_v3("B") == []
    session.advance_to(1.45); envelope = session.protocol_planning_snapshots_v3("B")[0]
    assert envelope["capture"]["extension"]["captured_at"] == capture
    assert envelope["delivered_at"] == (capture + .01 if owner == "A" else delivery)
    assert self_copy(session, payload) == envelope


def test_latest_expiry_is_tombstone_and_old_pending_ack_has_no_future_body(native):
    session = native.NativeSession(scene()); session.advance_to(1.3)
    old = request("old", publication_delay=.5); session.submit_protocol_command(old)
    session.advance_to(1.305); session.submit_protocol_command(old); session.advance_to(1.32)
    pending = session.protocol_command("A", old["request_id"])["last_delivered_ack"]
    assert pending["status"] == "pending_delivery" and "planning_snapshot_v3" not in pending
    new = request("new", expiry=1.4); session.submit_protocol_command(new); session.advance_to(1.37)
    latest = session.protocol_planning_snapshots_v3("B")[0]
    session.advance_to(1.9); stale = session.protocol_planning_snapshots_v3("B")[0]
    assert stale["status"] == "expired" and stale["capture"] == latest["capture"]
    history = session.observe_protocol("A")["delivered_command_acks"]
    assert all("planning_snapshot_v3" not in r for r in history
               if r["request_id"] == old["request_id"] and r["sequence"] == pending["sequence"])


@pytest.mark.parametrize("key,value", [("capture_v2", {}), ("extension", {}), ("entered_at", 0.),
    ("source_observed_inflight", []), ("unmatched_tray_ids", []), ("internal_traversal_id", 1)])
def test_caller_cannot_supply_entry_facts_or_internal_identity(native, key, value):
    session = native.NativeSession(scene()); session.advance_to(1.3); before = session.offline_state_sha256()
    with pytest.raises(ValueError, match="planning_snapshot_payload_is_native_captured"):
        session.submit_protocol_command({**request(), key: value})
    assert session.offline_state_sha256() == before


def test_wrong_owner_and_unknown_observer_cannot_read_capture(native):
    session = native.NativeSession(scene()); session.advance_to(1.3)
    payload = request(); session.submit_protocol_command(payload); session.advance_to(1.35)
    assert session.protocol_command("B", payload["request_id"])["status"] == "unknown_request"
    assert session.protocol_planning_snapshots_v3("A") == []
    with pytest.raises(ValueError, match="unknown_observation_owner"):
        session.protocol_planning_snapshots_v3("unknown")


def test_unrelated_private_traversals_and_future_events_do_not_change_source_body(native):
    base = scene()
    base["node_records"] += [(2, 1, .01, 2, 0, [3]), (3, 1, .01, 3, 0, [])]
    base["edge_records"].append((2, 3, 10., 1.))
    base["node_contracts"] += [{"node": n, "zone": "C", "resource_owner": "C", "capacity": 1} for n in (2, 3)]
    base["edge_contracts"].append({"from": 2, "to": 3, "capacity": 1, "entry_headway": .2})
    base["trays"].append({"tray_id": "TC", "node": 2})
    variant = deepcopy(base)
    variant["jobs"] += [{"business_bag_id": "C1", "origin": 2, "destination": 3, "arrival": 0.,
        "deadline": 40., "load_seconds": .01, "unload_seconds": .1, "hold_seconds": .1},
        {**base["jobs"][0], "business_bag_id": "unobserved_future", "arrival": 40., "deadline": 70.}]
    variant["faults"] = [{"from": 2, "to": 3, "start": 35., "end": 45.}]
    envelopes, private_traversals = [], []
    for data in (base, variant):
        session = native.NativeSession(prepare_input(data)); session.advance_to(1.3)
        envelopes.append(publish(session))
        entered = [r for r in session.result_at(session.physical_time)["receipts"]
                   if r["event"] == "EDGE_ENTER" and r["tray_id"] == "T0"]
        assert len(entered) == 1
        private_traversals.append(entered[0]["traversal_id"])
    assert private_traversals[0] != private_traversals[1]
    assert envelopes[0] == envelopes[1]


def test_reused_tray_and_empty_return_bind_current_source_job_and_traversal(native):
    data = scene(); data["node_records"][1] = (1, 1, .05, 1, 0, [0])
    data["edge_records"].append((1, 0, 1., 1.))
    data["edge_contracts"].append({"from": 1, "to": 0, "capacity": 1, "entry_headway": .2})
    data["jobs"].append({**data["jobs"][0], "business_bag_id": "B2", "arrival": .05})
    session = native.NativeSession(prepare_input(data)); session.advance_to(1.3)
    first = publish(session)["capture"]["extension"]["source_observed_inflight"][0]
    session.advance_to(12.)
    transfer = {"request_id": "live:1:B:return", "owner_id": "B", "tray_id": "T0", "source": 1,
        "destination": 0, "earliest_departure": 12., "expiry": 30., "message_delay": .01}
    assert session.submit_protocol_transfer(transfer)["status"] == "pending"
    session.advance_to(12.2)
    returning = publish(session, "empty", source="B", target="A")["capture"]["extension"]["source_observed_inflight"][0]
    assert returning["source_owner"] == "B" and returning["business_bag_id"] == ""
    assert (returning["edge_from"], returning["edge_to"]) == (1, 0)
    assert returning["traversal_id"] > first["traversal_id"] and returning["entered_at"] > first["entered_at"]
    # Return reception finishes at14.06, load at14.16 and source service at
    # 15.16. At15 the second leg has not entered;16 observes its actual entry.
    session.advance_to(16.)
    assert session.observe_protocol("A")["trays"][0]["business_bag_id"] == "B2"
    reused = publish(session, "reused")["capture"]["extension"]["source_observed_inflight"][0]
    current = session.observe_protocol("A")["trays"][0]
    assert reused["business_bag_id"] == "B2" and reused["source_owner"] == "A"
    assert reused["generation"] == current["generation"] > first["generation"]
    assert reused["traversal_id"] == current["traversal_id"] > returning["traversal_id"]
    assert reused["entered_at"] > returning["entered_at"]
    assert reused["derived_edge_exit_at"] == current["edge_exit_at"]
