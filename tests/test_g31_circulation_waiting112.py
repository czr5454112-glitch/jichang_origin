"""Pure decision/evidence tests. No NativeSession or physical simulation."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import research_original_waiting112 as gate


OWNER = "owner:system_domestic"


def view(now=10.):
    return {"owner_id": OWNER, "now": now,
        "node_records": [[112, 4, 1.5, 0, 0, [113, 53]], [113, 4, 1.5, 0, 0, [8]], [8, 4, 0, 0, 0, [53]], [53, 7, 0, 0, 0, []]],
        "edge_records": [[112, 113, 3., 2.], [113, 8, 1., 1.], [8, 53, 2., 1.]],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1} for u, v in ((112, 113), (113, 8), (8, 53))],
        "node_contracts": [{"node": n, "resource_owner": OWNER, "capacity": 4, "occupancy": 1 if n == 112 else 0} for n in (112, 113, 8, 53)],
        "trays": [{"tray_id": "T", "business_bag_id": "J", "generation": 2, "traversal_id": 9, "node": 112,
            "edge_from": -1, "edge_to": -1, "mode": "loaded", "committed_prefix": [5, 112]}],
        "jobs": [{"business_bag_id": "J", "arrival": 1., "status": "in_transit", "storage_node": 53,
            "storage_entered_at": -1., "storage_released_at": -1., "loaded_at": 2., "allow_suffix_reroute": True}]}


class Client:
    def __init__(self): self.state, self.calls = {"outbox": {}}, []
    def submit(self, owner, kind, payload, *, request_id):
        request = {**copy.deepcopy(payload), "request_id": request_id, "owner_id": owner, "kind": kind}
        self.state["outbox"][request_id] = {"payload": request}
        self.calls.append({"at": payload["expiry"]-120., "retry": False, "kind": kind, "request": request,
                           "reply": {"status": "queued"}})
        return request_id, {"status": "queued"}


def submitted():
    intent, client = gate.WaitingIntent(), Client()
    intent.observe(view(10.), client); intent.observe(view(13.5), client)
    return intent, client


def ack(intent, client, status="updated", at=15.7):
    client.state["outbox"][intent.decision["request_id"]]["client_view"] = {
        "last_delivered_ack": {"status": status, "completed_at": 15.5, "delivered_at": at}}


def test_requires_two_current_observations_and_exact_duration():
    intent, client = gate.WaitingIntent(), Client()
    intent.observe(view(10), client)
    intent.observe(view(13.499999999), client)
    assert client.calls == []
    intent.observe(view(13.5), client)
    assert len(client.calls) == 1 and client.calls[0]["request"]["message_delay"] == 2.


@pytest.mark.parametrize("field,value", [("generation", 3), ("traversal_id", 10), ("business_bag_id", "K"), ("committed_prefix", [7, 112])])
def test_wait_resets_on_identity_or_prefix_change(field, value):
    intent, client = gate.WaitingIntent(), Client(); intent.observe(view(10), client)
    later = view(20); later["trays"][0][field] = value
    if field == "business_bag_id": later["jobs"][0]["business_bag_id"] = value
    intent.observe(later, client)
    assert client.calls == []


def test_intervening_inflight_observation_invalidates_wait():
    intent, client = gate.WaitingIntent(), Client(); intent.observe(view(10), client)
    moving = view(12); moving["trays"][0]["edge_to"] = 53
    intent.observe(moving, client); intent.observe(view(20), client)
    assert not client.calls


@pytest.mark.parametrize("field,value", [("status", "storage"), ("storage_entered_at", 1.), ("storage_released_at", 1.),
    ("storage_node", 54), ("allow_suffix_reroute", False), ("arrival", 999.), ("loaded_at", -1.)])
def test_noneligible_job_not_admitted(field, value):
    intent, client = gate.WaitingIntent(), Client()
    for now in (10., 20.):
        current = view(now); current["jobs"][0][field] = value; intent.observe(current, client)
    assert not client.calls


def test_receiver_occupancy_is_local_and_current():
    intent, client = gate.WaitingIntent(), Client(); intent.observe(view(10), client)
    full = view(20); full["node_contracts"][1]["occupancy"] = 4; intent.observe(full, client)
    assert not client.calls
    intent.observe(view(21), client)
    assert len(client.calls) == 1 and intent.decision["receiver_local_contract"]["occupancy"] == 0


@pytest.mark.parametrize("change", ["foreign_source", "foreign_receiver", "missing_occupancy", "future_clock", "duplicate_job"])
def test_malformed_or_nonlocal_inputs_fail_closed(change):
    current = view()
    if change == "foreign_source": current["owner_id"] = "foreign"
    if change == "foreign_receiver": current["node_contracts"][1]["resource_owner"] = "foreign"
    if change == "missing_occupancy": current["node_contracts"][1].pop("occupancy")
    if change == "future_clock": current["now"] = float("nan")
    if change == "duplicate_job": current["jobs"] *= 2
    with pytest.raises(ValueError): gate.WaitingIntent().observe(current, Client())


def test_first_qualifying_snapshot_uses_fifo_identity_order():
    intent, client = gate.WaitingIntent(), Client()
    for now in (10., 20.):
        current = view(now)
        current["trays"].insert(0, {**copy.deepcopy(current["trays"][0]), "tray_id": "T2", "business_bag_id": "A"})
        current["jobs"].append({**current["jobs"][0], "business_bag_id": "A", "arrival": 2.})
        intent.observe(current, client)
    assert intent.decision["local_job"]["business_bag_id"] == "J"


def test_static_suffix_excludes_zero_capacity_and_return112():
    current = view()
    assert gate.positive_suffix(current) == [113, 8, 53]
    current["edge_contracts"][1]["capacity"] = 0
    current["edge_records"] += [[113, 112, 1., 1.], [112, 53, 1., 1.]]
    current["edge_contracts"] += [{"from": 113, "to": 112, "capacity": 1}, {"from": 112, "to": 53, "capacity": 1}]
    assert gate.positive_suffix(current) is None


def test_ack_alone_is_not_execution_and_only_one_request():
    intent, client = submitted(); ack(intent, client)
    intent.observe(view(16.), client); intent.observe(view(80.), client)
    assert intent.status == "awaiting_delivered_ack_and_edge" and len(client.calls) == 1
    assert gate.assess(intent.snapshot(), client.calls)["executable"] is None


@pytest.mark.parametrize("inflight", [True, False])
def test_actual_source_local_edge_and_delivered_ack_both_required(inflight):
    intent, client = submitted(); ack(intent, client)
    current = view(16.); tray = current["trays"][0]; tray["traversal_id"] = 10
    if inflight: tray.update(edge_from=112, edge_to=113, edge_exit_at=17.)
    else: tray.update(node=113, committed_prefix=[5, 112, 113])
    intent.observe(current, client)
    assert gate.assess(intent.snapshot(), client.calls)["status"] == "passed_executability_only"


def test_physical_other_edge_is_explicit_negative():
    intent, client = submitted(); ack(intent, client)
    current = view(16.); current["trays"][0].update(edge_from=112, edge_to=53, traversal_id=10, edge_exit_at=17.)
    intent.observe(current, client)
    assert intent.status == "updated_but_other_edge"
    assert gate.assess(intent.snapshot(), client.calls)["executable"] is None


def test_delivered_rejection_and_pending_ack_retained():
    intent, client = submitted(); ack(intent, client, "pending_execution")
    client.state["outbox"][intent.decision["request_id"]]["client_view"]["last_delivered_ack"]["completed_at"] = -1.
    intent.observe(view(16), client)
    assert gate.assess(intent.snapshot(), client.calls)["executable"] is None
    ack(intent, client, "rejected"); intent.observe(view(17), client)
    assert intent.status == "delivered_rejection"


def test_future_ack_and_shortened_wire_fail_closed():
    intent, client = submitted(); ack(intent, client, at=30.)
    with pytest.raises(ValueError, match="future_ack"): intent.observe(view(16), client)
    snapshot = intent.snapshot(); snapshot["decision"]["request"]["message_delay"] = 1.5
    with pytest.raises(ValueError, match="request_scope_changed"): gate.assess(snapshot, client.calls)


def test_no_input_or_view_mutation():
    current = view(10); before = copy.deepcopy(current)
    gate.WaitingIntent().observe(current, Client())
    assert current == before


def test_import_closure_includes_absolute_native_host_dependency():
    paths = gate.source_paths()
    assert gate.ROOT / "scripts/eval/run_g4irsf28_service_potential.py" in paths
    assert len(paths) == len(set(paths))


class TapeFixtureNative:
    def __init__(self): self.physical_time = 10.; self.current = view(10); self.reply = {}
    def observe_protocol_control_policy_recent(self, owner, validity): return copy.deepcopy(self.current)
    def submit_protocol_command(self, payload): return {"status": "queued"}
    def protocol_command(self, owner, identity): return copy.deepcopy(self.reply)


def tape_fixture(tmp_path):
    native = TapeFixtureNative(); tape = gate.GateTape(native, tmp_path / "api")
    client, intent = gate.ProtocolClient(tape, retry_period=60.), gate.WaitingIntent()
    for now in (10., 13.5, 16.):
        native.physical_time = now; native.current = view(now)
        if now == 16.:
            native.reply = {"last_delivered_ack": {"status": "updated", "completed_at": 15.5, "delivered_at": 15.7}}
            native.current["trays"][0].update(edge_from=112, edge_to=113, traversal_id=10, edge_exit_at=17.)
            client.refresh(owner_id=OWNER)
        intent.observe(tape.observe_protocol_control_policy_recent(OWNER, 120.), client)
    rows = [gate.gzread(tmp_path / "api" / row["path"]) for row in tape.rows]
    return rows, intent.snapshot(), client.calls


def test_exact_pure_tape_replay_with_real_client_clock(tmp_path):
    rows, intent, calls = tape_fixture(tmp_path)
    assert gate.replay_gate_rows(rows, intent, calls)["executable"] is True


def test_actual_client_retry_reuses_same_id_and_payload_through_pure_replay(tmp_path):
    native = TapeFixtureNative(); tape = gate.GateTape(native, tmp_path / "retry_api")
    client, intent = gate.ProtocolClient(tape, retry_period=60.), gate.WaitingIntent()
    for now in (10., 13.5, 74., 76.):
        native.physical_time = now; native.current = view(now)
        if now == 74.:
            native.reply = {"last_delivered_ack": {"status": "pending_execution", "completed_at": -1., "delivered_at": 15.7}}
            client.refresh(owner_id=OWNER)
        elif now == 76.:
            native.reply = {"last_delivered_ack": {"status": "updated", "completed_at": 15.5, "delivered_at": 75.7}}
            native.current["trays"][0].update(node=113, committed_prefix=[5, 112, 113], traversal_id=10)
            client.refresh(owner_id=OWNER)
        intent.observe(tape.observe_protocol_control_policy_recent(OWNER, 120.), client)
    assert [call["retry"] for call in client.calls] == [False, True]
    assert client.calls[0]["request"] == client.calls[1]["request"]
    rows = [gate.gzread(tmp_path / "retry_api" / row["path"]) for row in tape.rows]
    assert gate.replay_gate_rows(rows, intent.snapshot(), client.calls)["executable"] is True


def test_assessor_rejects_second_identity_or_changed_retry_payload():
    intent, client = submitted()
    retry = copy.deepcopy(client.calls[0]); retry["retry"] = True
    retry["request"]["expected_traversal"] += 1
    with pytest.raises(ValueError, match="one_immutable_request"):
        gate.assess(intent.snapshot(), client.calls + [retry])
    retry = copy.deepcopy(client.calls[0]); retry["request"]["request_id"] += "-new"
    with pytest.raises(ValueError, match="one_immutable_request"):
        gate.assess(intent.snapshot(), client.calls + [retry])


@pytest.mark.parametrize("change", ["remove_observation", "rewrite_submit", "remove_ack", "rewrite_edge", "reorder"])
def test_raw_api_tape_tampering_fails(tmp_path, change):
    rows, intent, calls = tape_fixture(tmp_path)
    if change == "remove_observation": rows.pop(0)
    if change == "rewrite_submit": rows[2]["args"][0]["message_delay"] = 1.5
    if change == "remove_ack": rows[3]["result"] = {}
    if change == "rewrite_edge": rows[-1]["result"]["trays"][0]["edge_to"] = 53
    if change == "reorder": rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises((ValueError, IndexError)): gate.replay_gate_rows(rows, intent, calls)


def test_boundary_does_not_probe_incomplete_native_timestamp():
    class Native:
        physical_time = 20.
        def advance_until_owner_notification(self, *args, **kwargs): return {"timestamp_complete": False, "notifications": {OWNER: {}}}
    class Tape:
        def observe_protocol_control_policy_recent(self, *args): raise AssertionError("must not read incomplete time")
    boundary = gate.Boundary(Native(), OWNER, Tape())
    boundary.advance_until_owner_notification([OWNER], {}, 30., max_events=1)
    assert boundary.intent.observation_count == 0


def test_original_saved_input_identity_and_positive_suffix():
    path = gate.OUTPUTS / "original_tie_streamed_native_002/input.json.gz"
    assert gate.sha(path) == gate.INPUT_SHA
    data = gate.gzread(path)
    assert gate.verify_input(data) == OWNER
    suffix = gate.positive_suffix(data)
    assert suffix[0] == 113 and suffix[-1] == 53 and 112 not in suffix


def test_atomic_evidence_writer_retries_only_bounded_permission_error(tmp_path, monkeypatch):
    original = Path.replace; attempts, sleeps = [], []
    def transient(path, target):
        attempts.append(str(path))
        if len(attempts) == 1: raise PermissionError("temporary sharing violation")
        return original(path, target)
    monkeypatch.setattr(Path, "replace", transient)
    monkeypatch.setattr(gate.time, "sleep", sleeps.append)
    gate.write(tmp_path / "manifest.json", {"complete": True})
    assert gate.read(tmp_path / "manifest.json") == {"complete": True}
    assert len(attempts) == 2 and sleeps == [.01]


def test_atomic_evidence_writer_preserves_temp_on_permanent_error(tmp_path, monkeypatch):
    attempts = []
    def denied(path, target):
        attempts.append(str(path)); raise PermissionError("permanent")
    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(gate.time, "sleep", lambda seconds: None)
    with pytest.raises(PermissionError): gate.write(tmp_path / "manifest.json", {"complete": True})
    assert len(attempts) == 6
    assert gate.read(tmp_path / "manifest.json.tmp") == {"complete": True}


@pytest.mark.parametrize("exit_at", [None, -1., 15., 16., float("nan"), True])
def test_reserved_future_edge_plus_updated_ack_does_not_prove_entry(exit_at):
    intent, client = submitted(); ack(intent, client)
    current = view(16.); current["trays"][0].update(edge_from=112, edge_to=113, traversal_id=10)
    if exit_at is not None: current["trays"][0]["edge_exit_at"] = exit_at
    intent.observe(current, client)
    assert intent.reservation is not None and intent.edge is None
    assert gate.assess(intent.snapshot(), client.calls)["executable"] is None


def test_pending_reservation_can_later_be_proved_by_completed_edge_prefix():
    intent, client = submitted(); ack(intent, client)
    reserved = view(16.); reserved["trays"][0].update(edge_from=112, edge_to=113, traversal_id=10)
    intent.observe(reserved, client)
    complete = view(20.); complete["trays"][0].update(node=113, committed_prefix=[5, 112, 113], traversal_id=10)
    intent.observe(complete, client)
    assert intent.edge["evidence"] == "completed_committed_prefix"
    assert gate.assess(intent.snapshot(), client.calls)["executable"] is True

