"""Pure fixture and saved transcript guards; no NativeSession execution."""
from copy import deepcopy
import json
import gzip
import time
from contextlib import contextmanager
import pytest

from scripts.experiments.g31_ics_circulation import probe_original_route_update as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update as v

OWNER = "owner:system_domestic"


def view(now):
    return {"owner_id": OWNER, "now": now, "client_transfer_ledger": [],
        "node_records": [[112, 4, 1.5, 0, 0, [113]], [113, 4, 0, 0, 0, [53]], [53, 7, 0, 0, 0, []]],
        "edge_records": [[112, 113, 3., 2.], [113, 53, 2., 1.]],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1} for u, v in ((112, 113), (113, 53))],
        "node_contracts": [{"node": n, "resource_owner": OWNER, "capacity": 4, "occupancy": 1 if n == 112 else 0} for n in (112, 113, 53)],
        "trays": [{"tray_id": "T", "business_bag_id": p.JOB, "generation": 2, "traversal_id": 9,
            "node": 112, "edge_from": -1, "edge_to": -1, "mode": "loaded", "committed_prefix": [5, 112]}],
        "jobs": [{"business_bag_id": p.JOB, "arrival": 1., "status": "in_transit", "storage_node": 53,
            "storage_entered_at": -1., "storage_released_at": -1., "loaded_at": 2., "allow_suffix_reroute": True}]}


class Fixture:
    def __init__(self):
        self.physical_time = p.ADMISSION; self.submits = []; self.ack = None
        self.edge = None; self.read_hook = None; self.drain_complete = True
    def observe_protocol(self, owner):
        assert owner == OWNER
        if self.read_hook: self.read_hook()
        result = view(self.physical_time)
        if self.edge: result["trays"][0].update(self.edge)
        return result
    def submit_protocol_command(self, payload):
        self.submits.append(deepcopy(payload)); return {"status": "queued", "request_id": payload["request_id"]}
    def protocol_command(self, owner, identity):
        assert owner == OWNER and identity == self.submits[0]["request_id"]
        return {"request_id": identity, "last_delivered_ack": deepcopy(self.ack or {})}
    def advance_to(self, target, *, max_events):
        assert target == self.physical_time and max_events == 100000
        return {"status": "reached" if self.drain_complete else "budget_exhausted",
            "horizon_complete": self.drain_complete, "physical_time": target, "wall_seconds": .001}
    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        self.physical_time = horizon
        return {"status": "notified", "timestamp_complete": True, "notifications": {OWNER: 1}, "physical_time": horizon}


def start():
    native = Fixture(); ticks = iter(range(1000000000, 1000000100))
    update = p.RouteUpdate(native, OWNER, clock=lambda: next(ticks))
    native.read_hook = lambda: (p.require(p.ROOT_ID in update.bridge.lineage.roots, "observation_before_admission"))
    update.start()
    assert not native.submits and update.started_ns < update.bridge.lineage.roots[p.ROOT_ID]["observation"]["wall_ns"]
    return native, update


def submitted():
    native, update = start(); native.physical_time = 9660.; update.step()
    assert len(native.submits) == 1
    return native, update


def terminal(native, *, status="updated", hop=113, observed=True):
    native.physical_time = 9662.2
    native.ack = {"sequence": 1, "status": status, "executed_at": 9662., "completed_at": 9662.,
        "delivered_at": 9662.2, "result_id": native.submits[0]["request_id"]}
    if hop is not None:
        native.edge = {"edge_from": 112, "edge_to": hop, "traversal_id": 10}
        if observed: native.edge["edge_exit_at"] = 9663.5


def test_caller_admission_precedes_view_and_candidate_and_second_observation():
    native, update = submitted()
    assert native.submits[0]["business_bag_id"] == p.JOB
    assert native.submits[0]["message_delay"] == 2.
    assert update.intent.decision["first_observation"]["at"] == 9600.
    assert update.intent.decision["at"] == 9660.


@pytest.mark.parametrize("hop,observed", [(None, True), (113, False)])
def test_updated_ack_or_reservation_only_cannot_close(hop, observed):
    native, update = submitted(); terminal(native, hop=hop, observed=observed); update.step()
    assert not update.closed
    assert update.bridge.report(p.ROOT_ID)["status"] == "unknown_incomplete_lineage"


def test_actual_edge_without_delivered_ack_cannot_close():
    native, update = submitted(); terminal(native); native.ack = None; update.step()
    assert update.intent.edge is not None and not update.closed


@pytest.mark.parametrize("hop,status,disposition", [(113, "updated", "completed"), (53, "updated", "terminal_failure"), (None, "rejected", "terminal_failure")])
def test_actual_delivered_outcomes_close_only_after_drain_codec(hop, status, disposition):
    native, update = submitted(); terminal(native, status=status, hop=hop); update.step()
    raw = update.snapshot()
    assert update.closed and raw["report"]["status"] == "complete_declared_lineage"
    assert raw["report"]["job_scope_verified"]
    returned = json.loads(raw["returned"]); response = json.loads(returned["output"])
    assert response["disposition"] == disposition
    root = raw["lineage"][p.ROOT_ID]
    assert root["mandatory_drain"]["wall_ns"] <= root["output_returned"]["wall_ns"] < raw["returned_ns"]


def test_incomplete_same_timestamp_drain_keeps_root_open_then_can_finish():
    native, update = submitted(); terminal(native); native.drain_complete = False; update.step()
    assert not update.closed
    native.drain_complete = True; update.step()
    assert update.closed


def test_immutable_retry_same_parent_and_payload():
    native, update = submitted(); native.physical_time = 9720.; update.step()
    assert len(native.submits) == 2 and native.submits[0] == native.submits[1]
    identity = native.submits[0]["request_id"]
    assert update.bridge.lineage.protocol[identity]["parent_roots"] == [p.ROOT_ID]
    assert len(update.bridge.lineage.protocol[identity]["attempts"]) == 2


def test_missing_ack_censored_not_dropped_or_counted_complete():
    native, update = submitted(); native.physical_time = 9900.; update.step(); update.censor()
    raw = update.snapshot()
    assert raw["returned_ns"] is None and raw["censored_ns"] is not None
    assert raw["report"]["status"] == "unknown_incomplete_lineage"
    assert len(raw["lineage"]) == 1


def test_submission_rejection_without_delivered_ack_remains_unknown():
    native, update = start()
    native.submit_protocol_command = lambda payload: {"status": "rejected", "reason": "fixture"}
    native.physical_time = 9660.; update.step()
    assert update.intent.status == "submission_rejected" and not update.closed
    native.physical_time = 9900.; update.step(); update.censor()
    assert update.bridge.report(p.ROOT_ID)["status"] == "unknown_incomplete_lineage"


@pytest.mark.parametrize("complete,due,own_notice,pending,expected", [
    (False, True, True, True, False), (True, False, False, True, False),
    (True, False, True, False, False), (True, True, False, False, True),
    (True, False, True, True, True)])
def test_boundary_requires_actual_complete_timestamp_and_declared_trigger(complete, due, own_notice, pending, expected, monkeypatch):
    class Tape:
        physical_time = 9660. if due else 9601.
        def advance_until_owner_notification(self, *args, **kwargs):
            return {"timestamp_complete": complete, "notifications": {OWNER: 1} if own_notice else {}}
    class Update:
        closed = False; censored_ns = None; owner = OWNER; next_probe = 9660.
        intent = type("Intent", (), {"decision": {} if pending else None})()
    invoked = []
    monkeypatch.setattr(p, "invoke_root", lambda *args: invoked.append(True))
    p.Boundary(Tape(), Update(), []).advance_until_owner_notification([OWNER], {}, 9900., max_events=100000)
    assert bool(invoked) == expected


def test_other_business_cannot_be_submitted_even_when_earlier_eligible():
    native, update = start()
    actual = native.observe_protocol
    def multiple(owner):
        row = actual(owner); row["trays"].insert(0, {**row["trays"][0], "tray_id": "OTHER", "business_bag_id": "earlier"})
        row["jobs"].append({**row["jobs"][0], "business_bag_id": "earlier", "arrival": 0.})
        return row
    native.observe_protocol = multiple; native.physical_time = 9660.; update.step()
    assert native.submits[0]["business_bag_id"] == p.JOB and native.submits[0]["tray_id"] == "T"


@pytest.mark.parametrize("epoch", [9599., 9600.0001, float("nan")])
def test_admission_wrong_epoch_rejected(epoch):
    native = Fixture(); native.physical_time = epoch
    with pytest.raises(ValueError, match="admission_epoch"): p.RouteUpdate(native, OWNER).start()


def test_future_or_foreign_observation_rejected():
    native = Fixture(); native.observe_protocol = lambda owner: {**view(9600.), "owner_id": "foreign"}
    with pytest.raises(ValueError, match="foreign_or_stale_view"): p.RouteUpdate(native, OWNER).start()


def test_unclassified_native_api_fails_closed_before_call():
    with pytest.raises(ValueError, match="unclassified_native_endpoint"):
        p.ServiceTape(Fixture()).offline_state_sha256()


def test_case_factors_only_change_drop_ack_field(monkeypatch):
    monkeypatch.setattr(p.old, "verify_input", lambda value: OWNER)
    base = {"owner_protocol": {"drop_ack_packets": 0, "ack_delay": .2}, "jobs": [{"id": 4}], "capacities": [0, 2]}
    for name, count in p.CASES.items():
        result = p.case_input(base, name); result["owner_protocol"]["drop_ack_packets"] = 0
        assert result == base
        assert p.case_input(base, name)["owner_protocol"]["drop_ack_packets"] == count
    assert base["owner_protocol"]["drop_ack_packets"] == 0


def api_row():
    return {"ordinal": 0, "endpoint": "observe_protocol", "role": "request", "args": [OWNER], "kwargs": {},
        "before": 9600., "after": 9600., "start_ns": 1, "end_ns": 2, "result": view(9600.)}


@pytest.mark.parametrize("mutation", ["omitted", "reordered", "unknown_endpoint", "bool_clock", "future_time", "missing_result", "exception"])
def test_saved_api_damage_rejected(mutation):
    rows = [api_row()]
    if mutation == "omitted": rows = []
    elif mutation == "reordered": rows[0]["ordinal"] = 1
    elif mutation == "unknown_endpoint": rows[0]["endpoint"] = "hidden_truth"
    elif mutation == "bool_clock": rows[0]["start_ns"] = True
    elif mutation == "future_time": rows[0]["after"] = 10000.
    elif mutation == "missing_result": del rows[0]["result"]
    elif mutation == "exception": rows[0]["error"] = "error"
    with pytest.raises(ValueError): v.validate_tape(rows)


def test_replay_does_not_accept_changed_arguments():
    row = api_row(); replay = v.Replay([row])
    with pytest.raises(ValueError, match="request_api_difference"): replay.observe_protocol("foreign")


@pytest.mark.parametrize("value", [True, -1., float("nan"), float("inf")])
def test_only_valid_client_wall_diagnostic_excluded(value):
    with pytest.raises(ValueError, match="invalid_submit_diagnostic"):
        v.projected_root({"client_calls": [{"submit_compute_ms": value}]})


def test_parent_budget_is_shared_without_starting_late_child(monkeypatch, tmp_path):
    monkeypatch.setattr(p.time, "perf_counter", lambda: 600.)
    monkeypatch.setattr(p.subprocess, "run", lambda *args, **kw: pytest.fail("late child started"))
    assert p.child(["unused"], tmp_path / "log", 0.)["status"] == "unknown_parent_budget"


def test_source_closure_and_closed_scope():
    paths = p.source_paths()
    assert p.ROOT / "scripts/eval/run_g4irsf28_service_potential.py" in paths
    assert p.ROOT / "scripts/experiments/g31_ics_circulation/verify_original_route_update.py" in paths
    assert p.contract()["horizon"] == 9900. and p.contract()["roots_per_case"] == 1
    assert p.contract()["complete_100ms_certified"] is False


def replay_fixture(tmp_path):
    began = time.perf_counter_ns(); native = Fixture(); tape = p.ServiceTape(native)
    path = tmp_path / "api.gz"; tape.begin(path)
    update = p.RouteUpdate(tape, OWNER); events = []
    p.invoke_root(update, tape, events, initial=True)
    tape.advance_until_owner_notification([OWNER], {OWNER: 0}, 9660., max_events=100000)
    p.invoke_root(update, tape, events)
    terminal(native); native.physical_time = 9660.
    tape.advance_until_owner_notification([OWNER], {OWNER: 1}, 9662.2, max_events=100000)
    p.invoke_root(update, tape, events)
    tape.close()
    with gzip.open(path, "rt", encoding="utf8") as f: rows = [json.loads(line) for line in f]
    raw = {"root": update.snapshot(), "events": events, "worker_started_ns": began,
        "result_capture_before_seal_ns": time.perf_counter_ns()}
    return raw, rows


def test_actual_request_path_saved_replay_and_clock_binding(tmp_path):
    raw, rows = replay_fixture(tmp_path); v.validate_tape(rows)
    assert v.replay_request(raw, rows).closed


@pytest.mark.parametrize("mutation", ["clock_after_view", "missing_event", "changed_payload", "omit_request", "false_drain"])
def test_saved_request_replay_rejects_semantic_or_lifetime_tampering(tmp_path, mutation):
    raw, rows = replay_fixture(tmp_path)
    if mutation == "clock_after_view":
        shift = 10**10
        raw["root"]["clock_trace"] = [value+shift for value in raw["root"]["clock_trace"]]
    elif mutation == "missing_event": raw["events"].pop()
    elif mutation == "changed_payload": next(r for r in rows if r["endpoint"] == "submit_protocol_command")["args"][0]["next"] = 53
    elif mutation == "omit_request": next(r for r in rows if r["endpoint"] == "protocol_command")["role"] = "controller"
    elif mutation == "false_drain": next(r for r in rows if r["endpoint"] == "advance_to")["result"]["horizon_complete"] = False
    with pytest.raises((ValueError, KeyError)): v.replay_request(raw, rows)
