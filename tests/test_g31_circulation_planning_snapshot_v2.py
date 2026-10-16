"""Native v2 facts are local physical receipts and actually delivered ACKs."""
from copy import deepcopy
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, prepare_input
from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
from scripts.experiments.g31_ics_circulation.planning_capture_v2_contract import validate_extension


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def scene(**protocol):
    data = tiny_cycle(); data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .03, **protocol}
    data["owner_notifications"] = {"enabled": True}
    return data


def request(identity="one", source="A", target="B", **changes):
    return {"request_id": f"live:{len(source.encode())}:{source}:planning-v2:{identity}",
        "owner_id": source, "kind": "planning_snapshot_v2", "target_owner": target,
        "message_delay": .01, "publication_delay": .02, "expiry": 60., **changes}


def snapshot(session, payload):
    ack = session.protocol_command(payload["owner_id"], payload["request_id"])["last_delivered_ack"]
    return ack["planning_snapshot_v2"]


def publish(session, identity="one", source="A", target="B", **changes):
    payload = request(identity, source, target, **changes)
    assert session.submit_protocol_command(payload)["status"] == "pending"
    session.advance_to(session.physical_time + .1)
    return snapshot(session, payload)


def test_destination_completion_retained_after_hold_and_tray_leaves(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(11.)
    before = publish(session, source="B", target="A")
    extension = before["capture"]["extension"]
    assert [r["business_bag_id"] for r in extension["terminal_receipts"]] == ["B1"]
    receipt = extension["terminal_receipts"][0]
    assert receipt["event"] == "UNLOAD_COMPLETE" and receipt["destination"] == 4 and receipt["source_owner"] == "B"
    assert receipt["receipt_id"] == "completion:1:B:1" and receipt["tray_id"] == "T0"
    assert next(j for j in session.result_at(session.physical_time)["jobs"] if j["business_bag_id"] == "B1")["completed_at"] == receipt["completed_at"]
    session.submit_protocol_transfer({"request_id": "live:1:B:return", "owner_id": "B", "tray_id": "T0",
        "source": 4, "destination": 0, "earliest_departure": 11.1, "expiry": 40., "message_delay": .01})
    session.advance_to(15.)
    after = publish(session, "after", source="B", target="A")
    assert after["capture"]["extension"]["terminal_receipts"] == [receipt]
    assert not any(t["tray_id"] == "T0" for t in after["capture"]["local_capture"]["trays"])
    session.advance_to(28.)
    final = publish(session, "two", source="B", target="A")
    rows = final["capture"]["extension"]["terminal_receipts"]
    assert [r["business_bag_id"] for r in rows] == ["B1", "B2"]
    assert [r["source_local_sequence"] for r in rows] == [1, 2]
    assert rows[0] == receipt


def test_incomplete_future_and_foreign_completion_not_inferred(native):
    data = scene(); data["jobs"].append({**data["jobs"][0], "business_bag_id": "future", "arrival": 40.})
    session = native.NativeSession(data); session.advance_to(5.)
    early = publish(session, source="B", target="A")
    assert early["capture"]["extension"]["terminal_receipts"] == []
    session.advance_to(11.)
    foreign = publish(session, "foreign", source="A", target="B")
    assert foreign["capture"]["extension"]["terminal_receipts"] == []
    local = publish(session, "local", source="B", target="A")
    assert local["capture"]["extension"]["completion_coverage"]["completed_business_bag_ids"] == ["B1"]


def test_resource_owner_not_zone_controls_completion_authority(native):
    data = scene(); data["node_contracts"][4]["resource_owner"] = "C"
    session = native.NativeSession(data); session.advance_to(11.)
    assert publish(session, source="B", target="A")["capture"]["extension"]["terminal_receipts"] == []
    rows = publish(session, source="C", target="A")["capture"]["extension"]["terminal_receipts"]
    assert len(rows) == 1 and rows[0]["source_owner"] == "C" and rows[0]["destination"] == 4


def test_unrelated_owner_completion_does_not_shift_local_receipt_identity(native):
    base = scene(); base["node_records"] += [(7, 1, .05, 7, 0, [8]), (8, 1, .05, 8, 0, [])]
    base["edge_records"].append((7, 8, 1., 1.))
    base["node_contracts"] += [{"node": n, "zone": "C", "capacity": 1} for n in (7, 8)]
    base["edge_contracts"].append({"from": 7, "to": 8, "capacity": 1, "entry_headway": .2})
    base["trays"].append({"tray_id": "TC", "node": 7})
    variant = deepcopy(base)
    variant["jobs"].append({"business_bag_id": "C1", "origin": 7, "destination": 8, "arrival": 0.,
        "deadline": 20., "load_seconds": .1, "unload_seconds": .1, "hold_seconds": .1})
    captures = []
    for data in (base, variant):
        session = native.NativeSession(prepare_input(data)); session.advance_to(11.)
        captures.append(publish(session, source="B", target="A"))
    assert captures[0] == captures[1]


def test_pending_grant_is_not_terminal_and_ack_loss_does_not_expose_truth(native):
    for drops in (0, 1):
        data = scene(drop_ack_packets=drops); data["jobs"] = []
        session = native.NativeSession(data); session.advance_to(0.)
        transfer = {"request_id": "live:1:A:delayed", "owner_id": "A", "tray_id": "T0",
            "source": 0, "destination": 4, "earliest_departure": 5., "expiry": 20., "message_delay": .01}
        session.submit_protocol_transfer(transfer); session.advance_to(.1)
        payload = request(); session.submit_protocol_command(payload); session.advance_to(.2)
        envelope = session.protocol_planning_snapshots_v2("B")[0]
        extension = envelope["capture"]["extension"]
        assert extension["action_coverage"]["unresolved_request_ids"] == [transfer["request_id"]]
        row = extension["submitted_physical_actions"][0]
        actual = session.protocol_request("A", transfer["request_id"]).get("last_delivered_ack")
        assert row["last_delivered_ack"] == (None if actual is None else {k: actual[k] for k in ("sequence", "delivered_at", "status")})
        assert "physical_resolution" not in row and "execution_status" not in row


def test_delivered_route_rejection_terminal_operation_only_and_missing_ack_pending(native):
    for drops in (0, 1):
        session = native.NativeSession(scene(drop_ack_packets=drops)); session.advance_to(.05)
        bad = {"request_id": "live:1:A:invalid-route", "owner_id": "A", "kind": "route", "tray_id": "T0",
            "business_bag_id": "B1", "from": 0, "next": 6, "expected_generation": 999,
            "expected_traversal": 999, "message_delay": .01, "expiry": 1.}
        session.submit_protocol_command(bad); session.advance_to(.15)
        payload = request(); session.submit_protocol_command(payload); session.advance_to(.25)
        extension = session.protocol_planning_snapshots_v2("B")[0]["capture"]["extension"]
        assert extension["action_coverage"]["unresolved_request_ids"] == ([bad["request_id"]] if drops else [])
        row = extension["submitted_physical_actions"][0]
        assert row["kind"] == "route"
        if not drops: assert row["last_delivered_ack"]["status"] == "rejected"
        else: assert row["last_delivered_ack"] is None
        assert extension["terminal_receipts"] == []


@pytest.mark.parametrize("owner,capture,delivery", [("A", .4, .42), ("B", .01, .4)])
def test_outage_wire_capture_delivery_and_source_self_copy(native, owner, capture, delivery):
    session = native.NativeSession(scene(owner_outages=[{"owner": owner, "start": 0., "end": .4}]))
    session.advance_to(0.); payload = request(); session.submit_protocol_command(payload); session.advance_to(.3)
    assert session.protocol_planning_snapshots_v2("B") == []
    session.advance_to(.5); envelope = session.protocol_planning_snapshots_v2("B")[0]
    assert envelope["capture"]["local_capture"]["captured_at"] == capture
    assert envelope["delivered_at"] == (capture + .02 if owner == "A" else delivery)
    assert snapshot(session, payload) == envelope and session.protocol_planning_snapshots("B") == []


def test_latest_expiry_tombstone_and_old_pending_ack_immutable(native):
    session = native.NativeSession(scene(ack_delay=.01)); session.advance_to(0.)
    first = request("old", publication_delay=.8); session.submit_protocol_command(first)
    session.advance_to(.02); session.submit_protocol_command(first); session.advance_to(.05)
    pending = session.protocol_command("A", first["request_id"])["last_delivered_ack"]
    assert pending["status"] == "pending_delivery" and "planning_snapshot_v2" not in pending
    newer = request("new", expiry=.2); session.submit_protocol_command(newer); session.advance_to(.15)
    current = session.protocol_planning_snapshots_v2("B")[0]
    session.advance_to(1.); latest = session.protocol_planning_snapshots_v2("B")[0]
    assert latest["capture"] == current["capture"] and latest["status"] == "expired"
    history = session.observe_protocol("A")["delivered_command_acks"]
    assert all("planning_snapshot_v2" not in r for r in history if r["request_id"] == first["request_id"] and r["sequence"] == pending["sequence"])


@pytest.mark.parametrize("at", [0., .015, .04, .1])
def test_checkpoint_fork_retry_digest_and_mutation_isolation(native, at):
    session = native.NativeSession(scene(drop_ack_packets=1)); session.advance_to(0.)
    payload = request(); session.submit_protocol_command(payload); session.advance_to(at)
    checkpoint, branch = session.checkpoint(), session.fork(); session.advance_to(.2); session.restore(checkpoint)
    for current in (session, branch):
        current.advance_to(.2); current.submit_protocol_command(payload); current.advance_to(.4)
    assert session.offline_state_sha256() == branch.offline_state_sha256()
    actual = snapshot(session, payload)
    assert actual == snapshot(branch, payload) == session.protocol_planning_snapshots_v2("B")[0]
    assert capture_digest_v2(actual["capture"]) == actual["payload_sha256"]
    mutated = deepcopy(actual); mutated["capture"]["extension"]["completion_coverage"]["future_events_included"] = True
    assert capture_digest_v2(mutated["capture"]) != actual["payload_sha256"]
    actual["capture"]["extension"]["terminal_receipts"].append({"fake": True})
    assert snapshot(session, payload) == snapshot(branch, payload)


@pytest.mark.parametrize("key,value", [("terminal_receipts", []), ("extension", {}), ("captured_at", 0.),
    ("action_coverage", {}), ("completed_at", 0.)])
def test_caller_cannot_supply_completion_or_action_coverage(native, key, value):
    session = native.NativeSession(scene()); session.advance_to(0.); before = session.offline_state_sha256()
    with pytest.raises(ValueError, match="planning_snapshot_payload_is_native_captured"):
        session.submit_protocol_command({**request(), key: value})
    assert session.offline_state_sha256() == before


def test_native_extension_matches_pure_scope_reference_without_authenticating_dict(native):
    data = scene(); session = native.NativeSession(data); session.advance_to(11.)
    envelope = publish(session, source="B", target="A")
    body, extension = envelope["capture"], envelope["capture"]["extension"]
    owners = {n["node"]: n.get("resource_owner", n["zone"]) for n in data["node_contracts"]}
    result = validate_extension(extension, source_owner="B", captured_at=extension["captured_at"], node_owners=owners,
        retained_job_contracts={j["business_bag_id"]: j for j in data["jobs"]}, local_action_ledger=[])
    assert result["status"] == "conditional_extension_data" and not result["native_delivery_verified"]
    assert capture_digest_v2(body) == envelope["payload_sha256"]
