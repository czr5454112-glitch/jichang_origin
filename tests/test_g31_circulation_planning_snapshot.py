"""Native snapshots are source-captured messages, never caller future facts."""
from copy import deepcopy
import hashlib
import os
import struct

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    module = load_native(os.environ["G31_CIRCULATION_BINARY"])
    assert hasattr(module.NativeSession, "protocol_planning_snapshots")
    return module


def scene(**protocol):
    data = tiny_cycle()
    data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .03, **protocol}
    data["owner_notifications"] = {"enabled": True}
    return data


def request(identity="one", **changes):
    return {"request_id": "live:1:A:planning:" + identity, "owner_id": "A", "kind": "planning_snapshot",
        "target_owner": "B", "message_delay": .01, "publication_delay": .02, "expiry": 5., **changes}


def final_snapshot(session, payload):
    return session.protocol_command(payload["owner_id"], payload["request_id"])["last_delivered_ack"]["planning_snapshot"]


def capture_digest(body):
    """Independent encoding of the documented native typed capture digest."""
    data = bytearray()
    def text(value):
        encoded = value.encode("utf-8")
        data.extend(struct.pack(">Q", len(encoded)))
        data.extend(encoded)
    def integer(value):
        data.extend(struct.pack(">Q", value & ((1 << 64) - 1)))
    def floating(value):
        data.extend(struct.pack(">d", value))
    def boolean(value):
        data.append(1 if value else 0)
    text("czr005.g4irsf14.runtime-state-component.v2")
    text("g31.planning_capture_digest.v1")
    text(body["schema"])
    for key in ("message_id", "source_owner", "target_owner"):
        text(body[key])
    integer(body["publication_sequence"])
    floating(body["captured_at"])
    floating(body["valid_until"])
    text(body["static_contract_sha256"])
    for key in ("queue_discipline", "resource_semantics", "event_semantics", "scorer_mode", "merge_grant_rule", "merge_grant_timing_mode"):
        text(body["semantics"][key])
    floating(body["semantics"]["minimum_service_seconds"])
    integer(len(body["jobs"]))
    for job in body["jobs"]:
        text(job["business_bag_id"])
        integer(job["origin"])
        integer(job["destination"])
        floating(job["arrival"])
        floating(job["deadline"])
        integer(job["storage_node"])
        for key in ("storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds"):
            floating(job[key])
        boolean(job["protected_service"])
        boolean(job["allow_suffix_reroute"])
        text(job["status"])
        for key in ("loaded_at", "storage_entered_at", "storage_released_at"):
            floating(job[key])
    integer(len(body["trays"]))
    for tray in body["trays"]:
        for key in ("tray_id", "business_bag_id", "mode", "ready_kind"):
            text(tray[key])
        for key in ("node", "edge_from", "edge_to", "reception_node", "generation", "traversal_id"):
            integer(tray[key])
        for key in ("available_at", "service_ready_at", "load_complete_at"):
            floating(tray[key])
        boolean(tray["service_ready_known"])
        integer(len(tray["committed_prefix"]))
        for node in tray["committed_prefix"]:
            integer(node)
    integer(len(body["nodes"]))
    for node in body["nodes"]:
        for key in ("node", "occupancy", "actual_available", "unrepresented_occupancy"):
            integer(node[key])
    integer(len(body["known_faults"]))
    for fault in body["known_faults"]:
        integer(fault["from"])
        integer(fault["to"])
        boolean(fault["active"])
        floating(fault["received_at"])
    coverage = body["coverage"]
    text(coverage["scope"])
    boolean(coverage["complete_for_declared_local_scope"])
    integer(len(coverage["local_node_ids"]))
    for node in coverage["local_node_ids"]:
        integer(node)
    for field in ("tray_ids", "business_bag_ids"):
        integer(len(coverage[field]))
        for identity in coverage[field]:
            text(identity)
    integer(coverage["unrepresented_occupancy"])
    boolean(coverage["future_arrivals_included"])
    return hashlib.sha256(data).hexdigest()


def test_capture_occurs_at_source_execution_not_submission_or_delivery(native):
    session = native.NativeSession(scene(ack_delay=.1))
    session.advance_to(0.)
    payload = request(message_delay=.25, publication_delay=.2)
    assert session.submit_protocol_command(payload)["status"] == "pending"
    session.advance_to(.3)
    assert session.protocol_planning_snapshots("B") == []
    assert "last_delivered_ack" not in session.protocol_command("A", payload["request_id"])
    session.advance_to(.46)
    snapshot = session.protocol_planning_snapshots("B")[0]
    assert snapshot["capture"]["captured_at"] == .25
    assert snapshot["delivered_at"] == .25 + .2
    assert [j["business_bag_id"] for j in snapshot["capture"]["jobs"]] == ["B1", "B2"]
    assert session.protocol_planning_snapshots("A") == []
    session.advance_to(.56)
    assert final_snapshot(session, payload) == snapshot
    session.advance_to(1.5)
    assert session.protocol_planning_snapshots("B")[0] == snapshot
    assert final_snapshot(session, payload) == snapshot


def test_snapshot_source_contracts_local_ready_and_resource_owner_coverage(native):
    data = scene()
    data["node_contracts"][3]["zone"] = "A"
    data["node_contracts"][3]["resource_owner"] = "B"
    session = native.NativeSession(data)
    session.advance_to(.05)
    payload = request(message_delay=.01)
    session.submit_protocol_command(payload)
    session.advance_to(.15)
    snapshot = final_snapshot(session, payload)
    body = snapshot["capture"]
    assert body["captured_at"] == .05 + .01
    assert body["coverage"]["business_bag_ids"] == ["B1"]
    assert body["coverage"]["tray_ids"] == ["T0"]
    assert 3 not in body["coverage"]["local_node_ids"]
    job, tray = body["jobs"][0], body["trays"][0]
    assert job["storage_node"] == 2 and job["storage_release_at"] == 6.
    assert job["unload_seconds"] == .5 and job["hold_seconds"] == 1.25
    assert tray["mode"] == "loading" and tray["service_ready_known"] is True
    assert tray["service_ready_at"] == tray["load_complete_at"] == .1
    assert tray["ready_kind"] == "observed_load_completion"
    assert "internal_traversal_id" not in tray and "runtime_id" not in tray
    assert body["semantics"]["queue_discipline"] == "fifo"
    assert body["semantics"]["resource_semantics"] == "R3_java_node_window_compatible"
    assert body["semantics"]["event_semantics"] == "E4_batch_plus_destination_merge_request"
    assert len(body["static_contract_sha256"]) == len(snapshot["payload_sha256"]) == 64
    assert capture_digest(body) == snapshot["payload_sha256"]
    modified = deepcopy(body)
    modified["jobs"][0]["storage_release_at"] += 1.
    assert capture_digest(modified) != snapshot["payload_sha256"]
    modified = deepcopy(body)
    modified["coverage"]["business_bag_ids"].append("fabricated")
    assert capture_digest(modified) != snapshot["payload_sha256"]


def test_pending_ack_does_not_acquire_later_capture_self_copy(native):
    session = native.NativeSession(scene(ack_delay=.01))
    session.advance_to(0.)
    payload = request(message_delay=.01, publication_delay=.3)
    session.submit_protocol_command(payload)
    session.advance_to(.02)
    session.submit_protocol_command(payload)
    session.advance_to(.05)
    old = session.protocol_command("A", payload["request_id"])["last_delivered_ack"]
    assert old["status"] == "pending_delivery" and "planning_snapshot" not in old
    session.advance_to(.4)
    history = session.observe_protocol("A")["delivered_command_acks"]
    assert "planning_snapshot" not in next(a for a in history if a["sequence"] == old["sequence"])
    assert final_snapshot(session, payload)["capture"]["captured_at"] == .01


@pytest.mark.parametrize("protocol", [{"drop_ack_packets": 1},
    {"duplicate_acks": True, "duplicate_ack_delay": .01}])
def test_retry_loss_duplicate_acks_keep_one_exact_snapshot(native, protocol):
    session = native.NativeSession(scene(**protocol))
    session.advance_to(0.)
    payload = request()
    session.submit_protocol_command(payload)
    session.advance_to(.1)
    snapshot = session.protocol_planning_snapshots("B")[0]
    if protocol.get("drop_ack_packets"):
        assert "last_delivered_ack" not in session.protocol_command("A", payload["request_id"])
    session.submit_protocol_command(payload)
    session.advance_to(.3)
    assert session.protocol_planning_snapshots("B") == [snapshot]
    assert final_snapshot(session, payload) == snapshot
    assert session.protocol_command("A", payload["request_id"])["attempt"] == 2


@pytest.mark.parametrize("owner,captured,delivered", [("A", .4, .42), ("B", .01, .4)])
def test_source_and_target_outages_preserve_actual_capture_and_delivery(native, owner, captured, delivered):
    session = native.NativeSession(scene(owner_outages=[{"owner": owner, "start": 0., "end": .4}]))
    session.advance_to(0.)
    payload = request()
    session.submit_protocol_command(payload)
    session.advance_to(.3)
    assert session.protocol_planning_snapshots("B") == []
    session.advance_to(.5)
    snapshot = session.protocol_planning_snapshots("B")[0]
    assert snapshot["capture"]["captured_at"] == captured
    # Match native addition order exactly, without epsilon as a causal rule.
    assert snapshot["delivered_at"] == (captured + .02 if owner == "A" else delivered)
    assert final_snapshot(session, payload) == snapshot


def test_latest_expired_revision_suppresses_older_delayed_snapshot(native):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    first = request("old", message_delay=0., publication_delay=1., expiry=5.)
    session.submit_protocol_command(first)
    session.advance_to(.1)
    second = request("new", message_delay=0., publication_delay=.1, expiry=.3)
    session.submit_protocol_command(second)
    session.advance_to(.25)
    latest = session.protocol_planning_snapshots("B")[0]
    assert latest["capture"]["captured_at"] == .1 and latest["status"] == "conditional"
    session.advance_to(.3)
    assert session.protocol_planning_snapshots("B")[0]["status"] == "expired"
    session.advance_to(1.1)
    chosen = session.protocol_planning_snapshots("B")[0]
    assert chosen["capture"] == latest["capture"] and chosen["status"] == "expired"
    assert final_snapshot(session, first)["capture"]["captured_at"] == 0.


def test_expiry_before_capture_and_expiry_during_target_outage_are_distinct(native):
    session = native.NativeSession(scene(owner_outages=[{"owner": "B", "start": 0., "end": .5}]))
    session.advance_to(0.)
    uncaptured = request("uncaptured", message_delay=.2, expiry=.1)
    captured = request("captured", expiry=.1)
    session.submit_protocol_command(uncaptured)
    session.submit_protocol_command(captured)
    session.advance_to(.6)
    a = session.protocol_command("A", uncaptured["request_id"])["last_delivered_ack"]
    b = session.protocol_command("A", captured["request_id"])["last_delivered_ack"]
    assert a["status"] == "expired" and "planning_snapshot" not in a
    assert b["status"] == "expired" and b["planning_snapshot"]["status"] == "expired"
    assert session.protocol_planning_snapshots("B") == [b["planning_snapshot"]]


@pytest.mark.parametrize("field,value", [("jobs", []), ("trays", []), ("captured_at", 0.),
    ("service_ready_at", 0.), ("static_contract_sha256", "fake"), ("unknown", 1)])
def test_caller_cannot_fabricate_native_payload_or_unrecognized_fields(native, field, value):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    before = session.offline_state_sha256()
    with pytest.raises(ValueError, match="planning_snapshot_payload_is_native_captured"):
        session.submit_protocol_command({**request(), field: value})
    assert session.offline_state_sha256() == before


@pytest.mark.parametrize("time", [0., .015, .04, .1])
def test_checkpoint_before_capture_delivery_ack_and_later_read_is_exact(native, time):
    session = native.NativeSession(scene(drop_ack_packets=1))
    session.advance_to(0.)
    payload = request()
    session.submit_protocol_command(payload)
    session.advance_to(time)
    checkpoint = session.checkpoint()
    branch = session.fork()
    session.advance_to(.2)
    session.restore(checkpoint)
    for current in (session, branch):
        current.advance_to(.2)
        current.submit_protocol_command(payload)
        current.advance_to(.4)
    assert session.offline_state_sha256() == branch.offline_state_sha256()
    assert session.protocol_planning_snapshots("B") == branch.protocol_planning_snapshots("B")
    assert final_snapshot(session, payload) == final_snapshot(branch, payload)
    frozen = deepcopy(final_snapshot(session, payload))
    altered = session.protocol_planning_snapshots("B")[0]
    altered["capture"]["jobs"][0]["storage_release_at"] = -99
    altered["capture"]["trays"].clear()
    assert final_snapshot(session, payload) == frozen
    assert session.protocol_planning_snapshots("B")[0] == frozen
    assert capture_digest(frozen["capture"]) == frozen["payload_sha256"]


def test_private_future_and_unrelated_owner_activity_do_not_enter_capture_or_digest(native):
    first = scene()
    first["node_contracts"][5]["resource_owner"] = "C"
    second = deepcopy(first)
    second["jobs"].append({**second["jobs"][0], "business_bag_id": "future", "arrival": 40.})
    second["faults"] = [{"from": 1, "to": 2, "start": 35., "end": 45.}]
    a, b = native.NativeSession(first), native.NativeSession(second)
    a.advance_to(0.)
    b.advance_to(0.)
    b.submit_protocol_command({"request_id": "live:1:C:other", "owner_id": "C", "kind": "demand",
                               "target_owner": "C", "message_delay": 0., "publication_delay": 0.})
    b.advance_to(0.)
    payload = request()
    for current in (a, b):
        current.submit_protocol_command(payload)
        current.advance_to(.1)
    assert a.protocol_planning_snapshots("B") == b.protocol_planning_snapshots("B")
    assert final_snapshot(a, payload) == final_snapshot(b, payload)
    assert a.offline_state_sha256() != b.offline_state_sha256()


def test_known_local_contract_change_is_captured_but_not_a_static_digest_change(native):
    a_data, b_data = scene(), scene()
    b_data["jobs"][0]["storage_release_at"] = 12.
    snapshots = []
    for data in (a_data, b_data):
        session = native.NativeSession(data)
        session.advance_to(0.)
        session.submit_protocol_command(request())
        session.advance_to(.1)
        snapshots.append(session.protocol_planning_snapshots("B")[0])
    a, b = snapshots
    assert a["capture"]["static_contract_sha256"] == b["capture"]["static_contract_sha256"]
    assert a["payload_sha256"] != b["payload_sha256"]
    assert [s["capture"]["jobs"][0]["storage_release_at"] for s in snapshots] == [6., 12.]


def test_remote_incoming_berth_is_counted_without_disclosing_remote_carrier(native):
    data = scene()
    data["node_contracts"][1]["resource_owner"] = "B"
    session = native.NativeSession(data)
    session.advance_to(.2)
    payload = request("B", owner_id="B", request_id="live:1:B:planning:one", target_owner="A", message_delay=0.)
    session.submit_protocol_command(payload)
    session.advance_to(.3)
    body = session.protocol_planning_snapshots("A")[0]["capture"]
    node = next(n for n in body["nodes"] if n["node"] == 1)
    assert node["occupancy"] == node["unrepresented_occupancy"] == 1
    assert body["trays"] == [] and body["jobs"] == []
    assert body["coverage"]["unrepresented_occupancy"] >= 1


def test_wrong_owner_access_and_request_namespaces_do_not_expose_source_payload(native):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    bad = request(owner_id="B")
    assert session.submit_protocol_command(bad)["status"] == "rejected"
    payload = request()
    session.submit_protocol_command(payload)
    session.advance_to(.1)
    assert session.protocol_command("B", payload["request_id"])["status"] == "unknown_request"
    assert session.protocol_planning_snapshots("A") == []
    with pytest.raises(ValueError, match="unknown_observation_owner"):
        session.protocol_planning_snapshots("unknown")
