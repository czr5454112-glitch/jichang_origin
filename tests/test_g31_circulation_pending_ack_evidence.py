from copy import deepcopy
import ast
import inspect
import textwrap

import pytest

from scripts.experiments.g31_ics_circulation import route_pending_ack_evidence as evidence


def sample():
    ack = {"status": "updated", "delivered_at": 12., "completed_at": 11., "sequence": 1}
    root = {"owner": "A", "intent": {"decision": {"owner": "A", "request_id": "r", "at": 9.},
        "ack": ack, "last_now": 11.}, "started_ns": 10, "returned_ns": 40, "censored_ns": None,
        "steps": [{"at": 12., "initial": False}]}
    rows = [{"ordinal": 0, "endpoint": "protocol_command", "role": "request", "args": ["A", "r"],
        "kwargs": {}, "before": 12., "after": 12., "start_ns": 20, "end_ns": 30,
        "result": {"request_id": "r", "kind": "route", "status": "acknowledged", "last_delivered_ack": deepcopy(ack)}}]
    events = [{"at": 12., "initial": False, "first_api": 0, "after_api": 1}]
    return root, rows, events


def test_later_query_does_not_freshen_last_physical_observation():
    args = sample(); before = deepcopy(args)
    proof = evidence.actual_ack_query(*args)
    assert proof["queried_at"] == 12. > args[0]["intent"]["last_now"]
    assert args == before


@pytest.mark.parametrize("mutation", [
    lambda r,t,e: t[0]["result"].pop("last_delivered_ack"),
    lambda r,t,e: t[0].update(endpoint="observe_protocol"),
    lambda r,t,e: t[0].update(args=["B", "r"]),
    lambda r,t,e: t[0]["result"].update(request_id="other"),
    lambda r,t,e: t[0]["result"].update(kind="planning_snapshot_v3"),
    lambda r,t,e: t[0]["result"].update(status="pending"),
    lambda r,t,e: t[0].update(before=11.),
    lambda r,t,e: t[0].update(after=13.),
    lambda r,t,e: t[0].update(error="query failed"),
    lambda r,t,e: t[0].update(ordinal=True),
    lambda r,t,e: t[0].update(end_ns=41),
    lambda r,t,e: e[0].update(at=13.),
    lambda r,t,e: r["steps"][0].update(at=13.),
    lambda r,t,e: r["steps"].clear(),
    lambda r,t,e: e[0].update(after_api=0),
    lambda r,t,e: t[0].update(role="controller"),
])
def test_missing_or_unbound_query_is_rejected(mutation):
    args = sample(); mutation(*args)
    with pytest.raises(ValueError): evidence.actual_ack_query(*args)


def test_future_ack_in_a_real_query_is_still_rejected():
    root, rows, events = sample()
    root["intent"]["ack"]["delivered_at"] = 13.
    rows[0]["result"]["last_delivered_ack"]["delivered_at"] = 13.
    with pytest.raises(ValueError, match="future_or_predecision_ack"):
        evidence.actual_ack_query(root, rows, events)


def test_different_sequence_is_not_same_ack():
    args = sample(); args[1][0]["result"]["last_delivered_ack"]["sequence"] = 2
    with pytest.raises(ValueError, match="without_actual_query"): evidence.actual_ack_query(*args)


def test_open_root_without_ack_stays_without_query_proof():
    root, rows, events = sample(); root["intent"]["ack"] = None
    assert evidence.actual_ack_query(root, rows, events) is None


def test_original_assessor_globals_and_source_are_unchanged():
    source = inspect.getsource(evidence.original.assess)
    globals_before = dict(evidence.original.assess.__globals__)
    compiled = evidence.assessor_with_query_bound()
    assert compiled is not evidence.original.assess
    assert compiled.__globals__ is not evidence.original.assess.__globals__
    assert inspect.getsource(evidence.original.assess) == source
    assert evidence.original.assess.__globals__ == globals_before
    assert compiled({"decision": None}, [], ack_query_at=None) == evidence.original.assess({"decision": None}, [])


def test_changed_reference_bound_fails_closed(monkeypatch):
    source = inspect.getsource(evidence.original.assess)
    real = evidence.inspect.getsource
    monkeypatch.setattr(evidence.inspect, "getsource", lambda value: source.replace('intent["last_now"]', 'intent["other"]')
        if value is evidence.original.assess else real(value))
    with pytest.raises(ValueError, match="guard_denominator"): evidence.assessor_with_query_bound()
