from copy import deepcopy
import gzip
import inspect
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import probe_original_route_update_pending_ack as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update_pending_ack as v
from scripts.experiments.g31_ics_circulation import route_pending_ack_evidence as evidence
from scripts.experiments.g31_ics_circulation import replay_route_pending_ack as replay
from scripts.experiments.g31_ics_circulation import launch_original_route_update_pending_ack as launch


def row(index, endpoint="protocol_command", role="request"):
    return {"ordinal": index, "endpoint": endpoint, "role": role, "args": ["A", "r"], "kwargs": {},
        "before": 10., "after": 10., "start_ns": 10 + index, "end_ns": 11 + index, "result": {"status": "pending"}}


def tape(path, rows):
    with gzip.open(path, "wt", encoding="utf8") as stream:
        for item in rows: stream.write(json.dumps(item) + "\n")


def test_worker_bytecode_and_original_globals_are_unchanged():
    original = dict(p.policy.worker.__globals__)
    inherited = p.inherited_worker()
    assert inherited.__code__ is p.policy.worker.__code__
    assert inherited.__closure__ is p.policy.worker.__closure__
    changed = {key for key in original if inherited.__globals__[key] is not original[key]}
    assert changed == {"SCHEMA", "verify_pins", "RouteUpdate"}
    assert original == p.policy.worker.__globals__


def test_new_verifier_does_not_mutate_frozen_globals():
    before = dict(v.original.verify_case.__globals__)
    candidate = v.case_function()
    assert candidate is not v.original.verify_case
    assert v.original.verify_case.__globals__ == before
    assert candidate.__globals__["p"] is p
    assert candidate.__globals__["verify_scheduled_reference"] is v.verify_reference


def test_original_assessor_call_shape_change_is_rejected(monkeypatch):
    source = inspect.getsource(v.original.verify_case)
    real = v.inspect.getsource
    monkeypatch.setattr(v.inspect, "getsource", lambda value: source.replace('p.old.assess(root["intent"], root["client_calls"])',
        'p.old.assess(root["intent"], [])') if value is v.original.verify_case else real(value))
    with pytest.raises(ValueError, match="assessor_call_changed"): v.case_function()


def test_stream_comparison_omits_only_one_declared_request_view(tmp_path):
    reference = [row(0), row(1, "observe_protocol"), row(2)]
    current = [deepcopy(reference[0]), deepcopy(reference[2])]
    current[1]["ordinal"] = 1
    path = tmp_path / "tape.gz"; tape(path, reference)
    result = v.compare_api_stream(path, current, [(0, 2)])
    assert result == {"remaining_api_rows": 2, "omitted_full_view_ordinals_in_reference": [1]}


@pytest.mark.parametrize("change", ["query_removed", "result_changed", "args_changed", "role_changed", "reordered", "extra_row"])
def test_other_api_changes_fail(tmp_path, change):
    reference = [row(0), row(1, "observe_protocol"), row(2)]
    current = [deepcopy(reference[0]), deepcopy(reference[2])]
    if change == "query_removed": current.pop()
    elif change == "result_changed": current[0]["result"]["status"] = "acknowledged"
    elif change == "args_changed": current[0]["args"][0] = "B"
    elif change == "role_changed": current[0]["role"] = "controller"
    elif change == "reordered": current[0]["before"] = 9.; current.reverse()
    elif change == "extra_row": current.append(row(3))
    path = tmp_path / "tape.gz"; tape(path, reference)
    with pytest.raises(ValueError): v.compare_api_stream(path, current, [(0, 2)])


@pytest.mark.parametrize("reference,intervals", [
    ([row(0)], [(0, 1)]),
    ([row(0, "observe_protocol"), row(1, "observe_protocol")], [(0, 2)]),
    ([row(0, "observe_protocol", "controller")], [(0, 1)]),
])
def test_nonexact_observation_omission_rejected(tmp_path, reference, intervals):
    path = tmp_path / "tape.gz"; tape(path, reference)
    with pytest.raises(ValueError): v.compare_api_stream(path, [], intervals)


@pytest.mark.parametrize("clock", [True, -1., float("inf"), float("nan")])
def test_wall_clock_exclusion_has_strict_domain(clock):
    item = row(0, "advance_to"); item["result"]["wall_seconds"] = clock
    with pytest.raises(ValueError): v.api_semantics(item)


def proof_fixture():
    events = [{"first_api": 0, "after_api": 1, "at": 10., "initial": True},
        {"first_api": 1, "after_api": 2, "at": 11., "initial": False}]
    root = {"steps": [{}, {}], "pending_ack_path": {"sticky_observed_hop": {
        "actual_view_count": 1, "observed_at": 10., "source": "same_instance_unchanged_public_observe_path"},
        "full_view_reads": 1, "ack_only_steps": 1}}
    return {"root": root, "events": events}, [row(0, "observe_protocol"), row(1)], {"events": deepcopy(events)}


def test_omission_requires_earlier_observed_proof():
    args = proof_fixture()
    assert v.omitted_reference_indices(*args) == [(1, 2)]
    args[0]["root"]["pending_ack_path"]["sticky_observed_hop"] = None
    with pytest.raises(ValueError, match="before_actual_proof"): v.omitted_reference_indices(*args)


def test_reservation_or_forged_proof_origin_rejected():
    args = proof_fixture()
    args[0]["root"]["pending_ack_path"]["sticky_observed_hop"]["source"] = "reservation"
    with pytest.raises(ValueError, match="proof_origin"): v.omitted_reference_indices(*args)


def test_actual_counter_mismatch_rejected():
    args = proof_fixture(); args[0]["root"]["pending_ack_path"]["ack_only_steps"] = 2
    with pytest.raises(ValueError, match="read_denominator"): v.omitted_reference_indices(*args)


def test_fixed_case_contract_and_job_bound():
    assert len(p.CASES) == 3 and p.HORIZON == 9900. and p.ADMISSION == 9600.
    assert launch.LIMIT == p.PARENT_SECONDS == 600.
    assert launch.CASES == set(p.CASES)
    assert "No buffered writer change" in p.contract()["change"]
    assert p.old.BINARY_SHA == p.policy.old.BINARY_SHA


def test_actual_saved_baseline_as_pure_replay_fixture():
    """No native: delete only the recorded final view then replay new policy."""
    directory = p.REFERENCE / "baseline"
    oldraw = p.old.gzread(directory / "raw.json.gz")
    rows = replay._read_api(directory / "service_tape.jsonl.gz")
    saved = replay.replay_case(directory)
    removed = set()
    for event, mode in zip(oldraw["events"], saved["modes"], strict=True):
        if mode["ack_only"]:
            removed.update(i for i in range(event["first_api"], event["after_api"]) if rows[i]["endpoint"] == "observe_protocol")
    current = [deepcopy(item) for i, item in enumerate(rows) if i not in removed]
    for index, item in enumerate(current): item["ordinal"] = index
    raw = deepcopy(oldraw); raw["root"] = saved["candidate_snapshot"]
    for event in raw["events"]:
        event["first_api"] -= sum(i < event["first_api"] for i in removed)
        event["after_api"] -= sum(i < event["after_api"] for i in removed)
    namespace = v.case_function().__globals__
    update = namespace["replay_request"](raw, current)
    assert update.closed and len(removed) == 1
    result = evidence.assess(raw["root"], current, raw["events"])
    assert result["assessment"]["executable"] is True
    assert result["actual_ack_query"]["queried_at"] == 9605.7
    assert result["physical_observation_last_now"] == 9605.5
    assert not result["observation_time_rewritten"]
    assert v.omitted_reference_indices(raw, current, oldraw)


def test_complete_source_closure_includes_new_evidence_and_launcher():
    paths = set(p.source_paths())
    assert {Path(m.__file__).resolve() for m in (p, v, evidence, launch, replay)} <= paths
    assert p.ROOT / "scripts/eval/run_g4irsf28_service_potential.py" in paths
    assert p.source_paths() == p.source_paths()
