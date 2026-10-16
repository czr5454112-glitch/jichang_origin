"""Budget denominator, neutral coordinate reachability and strict protection."""
import copy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import public_resource_repair as repair


def bundle():
    p = Path(__file__).resolve().parents[1] / "outputs/experiments/g31_ics_lt2_sustained_20261014/native_public_joint_001/gate6/incumbent.json.gz"
    return json.load(gzip.open(p, "rt"))["owners"]["A"]["information"]["bundle"]


def toy(monkeypatch):
    def predict(b, a):
        completion = {j: 10. for j in b["jobs"]}
        if a["departure"] == 1.: completion["receiver"] += -1. if a["initial_next"] == 2 else 1.
        return {"status": "conditional_prediction", "completion": completion, "completion_sum": sum(completion.values())}
    monkeypatch.setattr(repair.model, "predict", predict)
    actions = [{"initial_next": r, "departure": t, "later_mode": "adaptive"} for r in (1, 2) for t in (1., 2.)]
    return actions, actions[1]


def test_coordinate_neutral_plateau_is_given_fair_search_opportunity(monkeypatch):
    actions, incumbent = toy(monkeypatch)
    results = {m: repair.repair(bundle(), actions, incumbent, method=m, evaluation_budget=4) for m in repair.METHODS}
    assert results["coordinate_strict"]["selected_action"] == incumbent
    assert results["coordinate_plateau"]["selected_action"] == results["resource_pair_repair"]["selected_action"] == actions[2]
    assert results["coordinate_plateau"]["model_gain"] == 1.
    assert all(r["evaluations"] <= 4 and not r["native_protection_certified"] for r in results.values())


def test_budget_retains_full_action_denominator_unknown_and_input_immutable(monkeypatch):
    actions, incumbent = toy(monkeypatch)
    b = bundle(); old = copy.deepcopy(b)
    r = repair.repair(b, actions, incumbent, method="resource_pair_repair", evaluation_budget=2)
    assert b == old and r["evaluations"] == 2 and len(r["rows"]) == 4
    assert sum(x["evaluation_status"] == "unknown_unexecuted" for x in r["rows"]) == 2
    assert r["stop_reason"] == "evaluation_budget_exhausted"


def test_missing_job_or_positive_delta_never_counts_as_protected():
    base = {"status": "conditional_prediction", "completion": {"a": 1., "b": 2.}}
    p = copy.deepcopy(base); p["completion"]["b"] += 1e-12
    assert repair.protected(p, base, {"a", "b"}) is False
    p["completion"].pop("b")
    assert repair.protected(p, base, {"a", "b"}) is None


def test_resource_neighborhood_has_whole_obligation_closure():
    b = bundle(); actions, incumbent = repair.model.candidates_from_durations(b)
    n = repair.resource_neighborhood(b, actions)
    assert n["shared_nodes"] == [1, 3, 4] and n["destroy_variables"] == ["initial_next", "departure"]
    assert n["obligation_closure"] == sorted(b["jobs"]) and n["exterior_frozen"] == []


def test_unknown_input_and_unsupported_mixed_continuation_fail_closed():
    b = bundle(); actions, incumbent = repair.model.candidates_from_durations(b)
    b["status"] = "unknown"
    assert repair.repair(b, actions, incumbent, method="resource_pair_repair")["evaluations"] == 0
    b["status"] = "conditional_model_input"; actions[-1]["later_mode"] = "native_keep"
    with pytest.raises(ValueError, match="later_continuation"):
        repair.repair(b, actions, incumbent, method="resource_pair_repair")
