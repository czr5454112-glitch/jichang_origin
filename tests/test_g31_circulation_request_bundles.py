"""Whole-call bundle coverage, causal retries and no-action roots."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import request_bundle_measurement as measurement
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        self.value += 1000
        return self.value


class Session:
    def __init__(self):
        self.physical_time = 0.
        self.calls = []
    def advance_until_owner_notification(self, owners, after, deadline, **kwargs):
        self.physical_time = deadline
        self.calls.append(("advance", deadline))
        return {"status": "notified", "timestamp_complete": True, "notifications": {}}
    def observe_protocol_control(self, owner):
        self.calls.append(("view", owner))
        return {"now": self.physical_time, "client_transfer_ledger": [], "delivered_messages": []}
    def submit_protocol_transfer(self, payload):
        self.calls.append(("submit", copy.deepcopy(payload)))
        return {"status": "pending"}
    def protocol_request(self, owner, request_id):
        self.calls.append(("query", owner, request_id))
        ack = {"status": "received", "delivered_at": 1.} if self.physical_time >= 1 else {}
        return {"last_delivered_ack": ack}
    def result_at(self, horizon):
        self.calls.append(("result", horizon))
        return {"done": True}


def owner(client, owner_id, current, causes, **kwargs):
    refreshed = client.refresh(owner_id=owner_id)
    client.view(owner_id)
    attempts = []
    if current["round"] == 0 and owner_id == "A":
        mid, reply = client.submit(owner_id, "transfer", {"tray_id": "T", "source": 0, "destination": 1,
            "earliest_departure": 0., "expiry": 10., "message_delay": .1})
        attempts.append({"request_id": mid, "reply": reply})
    return {"refreshed": refreshed, "attempts": attempts, "publications": [], "service_actions": []}


def controller(session, owners, *, state=None, **kwargs):
    round_ = 0 if state is None else state["round"]
    session.advance_until_owner_notification(owners, {}, round_/2)
    client = ProtocolClient(session, retry_period=.5, state=None if state is None else state["client"])
    current = {"round": round_, "owner_epochs": {o: round_ for o in owners},
               "next_tick": round_+1, "config": {"owners": owners}}
    measurement.event._due_timers(current, session.physical_time)
    records = []
    for o in owners:
        records.append(measurement.event._activate_owner(client, o, current, {"periodic_tick": round_}))
        session.advance_until_owner_notification(owners, {}, round_/2)
    result = session.result_at(round_/2)
    return {"status": "reached" if round_ == 2 else "control_budget_exhausted", "result": result,
        "controller_state": {"client": copy.deepcopy(client.state), "round": round_+1},
        "control_records": records, "client_calls": client.calls}


def capture(monkeypatch):
    monkeypatch.setattr(measurement.event, "_activate_owner", owner)
    monkeypatch.setattr(measurement.event, "run_event_protocol_control", controller)
    session = Session()
    recorder = measurement.BundleRecorder(session, clock=Clock())
    parts, state = [], None
    for _ in range(3):
        part = recorder.run(["A", "B"], state=state)
        state = part["controller_state"]
        parts.append(part)
    return recorder, parts


def test_wrappers_preserve_calls_and_states_and_cover_across_segments(monkeypatch):
    recorder, parts = capture(monkeypatch)
    plain = Session(); state = None
    for expected in parts:
        actual = controller(plain, ["A", "B"], state=state)
        assert actual["controller_state"] == expected["controller_state"]
        state = actual["controller_state"]
    assert recorder.session.calls == plain.calls
    report = measurement.analyze_bundles(recorder.ledger())
    assert report["status"] == "complete_conservative_bundle_accounting", report
    assert report["request_count"] == 6
    assert report["protocol_request_count"] == 1
    assert report["open_root_count"] == 0
    assert sum(r["status"] == "no_action" for r in report["requests"]) == 5
    assert next(iter(recorder.messages.values()))["attempts"] == 2
    first = report["requests"][0]
    assert first["logical_end_to_end_seconds"] == 1
    assert first["complete_compute_upper_ns"] > 0
    assert report["complete_100ms_requirement_certified"] is False


def test_lost_ack_prefix_remains_open_after_output_checkpoint(monkeypatch):
    monkeypatch.setattr(measurement.event, "_activate_owner", owner)
    monkeypatch.setattr(measurement.event, "run_event_protocol_control", controller)
    recorder = measurement.BundleRecorder(Session(), clock=Clock())
    recorder.run(["A", "B"])
    report = measurement.analyze_bundles(recorder.ledger())
    assert report["status"] == "complete_conservative_bundle_accounting"
    assert report["open_root_count"] == 1
    assert report["requests"][0]["complete_compute_upper_ns"] is None
    assert report["all_captured_roots_complete_upper_within_100ms"] is None


@pytest.mark.parametrize("defect", ["gap", "overlap", "lost_dependency", "bad_terminal", "unknown_method_class", "runtime_error"])
def test_incomplete_or_inconsistent_bundles_cannot_pass(monkeypatch, defect):
    recorder, _ = capture(monkeypatch)
    raw = recorder.ledger()
    if defect == "gap":
        raw["bundles"].pop()
    elif defect == "overlap":
        raw["bundles"].append({**raw["bundles"][0], "bundle_id": 10000})
    elif defect == "lost_dependency":
        mid = raw["messages"][0]["request_id"]
        bundle = next(b for b in raw["bundles"] if b["kind"] == "native_advance_full" and mid in b["protocol_request_ids"])
        bundle["protocol_request_ids"].remove(mid)
    elif defect == "bad_terminal":
        raw["messages"][0]["closed_ns"] += 1
    elif defect == "unknown_method_class":
        raw["bundles"][0]["kind"] = "unmeasured_native_work"
    else:
        raw["runtime_error"] = "interrupted"
    report = measurement.analyze_bundles(raw)
    assert report["status"] == "unknown_invalid_bundle_capture"
    assert report["all_captured_roots_complete_upper_within_100ms"] is None


def test_shared_bundle_cost_is_identical_full_charge_not_average(monkeypatch):
    recorder, _ = capture(monkeypatch)
    raw = recorder.ledger()
    report = measurement.analyze_bundles(raw)
    for root in report["requests"]:
        expected = sum(b["end_ns"]-b["start_ns"] for b in raw["bundles"] if root["request_id"] in b["root_request_ids"])
        assert root["complete_compute_upper_ns"] == expected


def test_unexpected_native_execution_fails_closed_and_restores_hook(monkeypatch):
    monkeypatch.setattr(measurement.event, "_activate_owner", owner)
    def bad_controller(session, *args, **kwargs):
        session.surprise()
    monkeypatch.setattr(measurement.event, "run_event_protocol_control", bad_controller)
    session = Session(); session.surprise = lambda: None
    recorder = measurement.BundleRecorder(session, clock=Clock())
    with pytest.raises(ValueError, match="unclassified_native_method"):
        recorder.run(["A"])
    assert measurement.event._activate_owner is owner
    assert measurement.analyze_bundles(recorder.ledger())["status"] == "unknown_invalid_bundle_capture"


def test_budget_cut_after_no_action_requires_complete_native_drain(monkeypatch):
    monkeypatch.setattr(measurement.event, "_activate_owner", owner)
    def cut(session, owners, *, state=None, **kwargs):
        client = ProtocolClient(session)
        if state is None:
            measurement.event._activate_owner(client, "B", {"round": 1, "owner_epochs": {}}, {})
        else:
            session.advance_until_owner_notification(owners, {}, 0.)
        return {"status": "control_budget_exhausted", "controller_state": {}, "control_records": []}
    monkeypatch.setattr(measurement.event, "run_event_protocol_control", cut)
    recorder = measurement.BundleRecorder(Session(), clock=Clock())
    recorder.run(["B"])
    assert measurement.analyze_bundles(recorder.ledger())["open_root_count"] == 1
    saved_advance = recorder.session.advance_until_owner_notification
    recorder.session.advance_until_owner_notification = lambda *a, **kw: {"status": "budget_exhausted", "timestamp_complete": False}
    recorder.run(["B"], state={})
    assert measurement.analyze_bundles(recorder.ledger())["open_root_count"] == 1
    recorder.session.advance_until_owner_notification = saved_advance
    recorder.run(["B"], state={})
    assert measurement.analyze_bundles(recorder.ledger())["open_root_count"] == 0


@pytest.mark.parametrize("defect", ["no_drain", "partial_drain", "bad_accepted", "nan_logical"])
def test_root_lifecycle_tampering_fails_closed(monkeypatch, defect):
    recorder, _ = capture(monkeypatch)
    raw = recorder.ledger()
    root = raw["requests"][-1]
    if defect == "no_drain":
        root["drain_complete_bundle_id"] = None
    elif defect == "partial_drain":
        next(b for b in raw["bundles"] if b["bundle_id"] == root["drain_complete_bundle_id"])["timestamp_complete"] = False
    elif defect == "bad_accepted":
        root["accepted_ns"] = True
    else:
        root["logical_opened_at"] = float("nan")
    assert measurement.analyze_bundles(raw)["status"] == "unknown_invalid_bundle_capture"


def test_policy_observation_capability_survives_proxy_without_changing_legacy_type():
    class PolicySession(Session):
        def observe_protocol_control_policy(self, owner):
            return {"owner_id": owner, "now": 0., "delivered_messages": []}
    assert not hasattr(measurement._SessionProxy, "observe_protocol_control_policy")
    recorder = measurement.BundleRecorder(PolicySession(), clock=Clock())
    recorder.current_root = "diagnostic_only"
    view = measurement._PolicySessionProxy(recorder).observe_protocol_control_policy("A")
    assert view["owner_id"] == "A"
    assert recorder.native_methods == {"observe_protocol_control_policy": 1}


def test_timer_origin_and_shared_checkpoint_work_follow_waiting_owner_across_shards(monkeypatch):
    monkeypatch.setattr(measurement.event, "_activate_owner", owner)
    def split(session, owners, *, state=None, **kwargs):
        current = {"round": 1, "owner_epochs": {}, "next_tick": 1, "config": {"owners": owners}}
        client = ProtocolClient(session)
        if state is None:
            session.advance_until_owner_notification(owners, {}, 0.)
            measurement.event._due_timers(current, 0.)
            who = "A"
        else:
            who = "B"
        record = measurement.event._activate_owner(client, who, current, {"periodic_tick": 0})
        session.advance_until_owner_notification(owners, {}, 0.)
        return {"status": "control_budget_exhausted", "controller_state": {}, "control_records": [record]}
    monkeypatch.setattr(measurement.event, "run_event_protocol_control", split)
    recorder = measurement.BundleRecorder(Session(), clock=Clock())
    recorder.run(["A", "B"])
    original_native = recorder.bundles[0]["bundle_id"]
    assert recorder.last_native != original_native
    recorder.run(["A", "B"], state={})
    raw = recorder.ledger()
    b = raw["requests"][-1]
    assert b["trigger_bundle_ids"] == [original_native]
    assert measurement.analyze_bundles(raw)["status"] == "complete_conservative_bundle_accounting"
    first_output = next(bundle for bundle in raw["bundles"] if bundle["kind"] == "scheduler_output_full")
    assert b["request_id"] in first_output["root_request_ids"]
    first_output["root_request_ids"].remove(b["request_id"])
    assert measurement.analyze_bundles(raw)["status"] == "unknown_invalid_bundle_capture"


def test_unmeasured_initial_restore_cannot_create_new_lifetimes(monkeypatch):
    recorder = measurement.BundleRecorder(Session(), clock=Clock())
    with pytest.raises(ValueError, match="initial_unmeasured_controller_restore"):
        recorder.run(["A"], state={})
