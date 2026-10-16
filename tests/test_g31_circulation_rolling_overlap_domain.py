import copy
import pytest
from scripts.experiments.g31_ics_circulation import research_rolling_overlap_domain as model


def prediction(values=(10., 10., 10., 10.)):
    return {"status": "conditional_prediction", "completion": dict(zip(sorted(model.JOBS), values)), "completion_sum": sum(values)}


def test_preregistered_complete_finite_denominator_and_no_native_permission():
    plan = model.protocol()
    assert len(plan["cases"]) == 6 and len(plan["actions"]) == 16
    assert plan["maximum_projection_cells"] == 96 and plan["native_branch_budget"] == 0
    assert plan["derivation"]["receiver_loads"] == [3., 5., 7.]
    assert plan["derivation"]["initial_storage_path_bounds"] == pytest.approx([4.4, 5.4])
    assert plan["derivation"]["masking_gate"] == pytest.approx(5.4)
    assert len({model.key(action) for action in plan["actions"]}) == 16


def test_new_contract_changes_only_public_load_and_storage_gate():
    cases = model.public_domain()["cases"]
    first, last = model.make_bundle(cases[0]), model.make_bundle(cases[-1])
    for field in ("node_records", "edge_records", "node_contracts", "edge_contracts", "trays", "owner_protocol"):
        assert first["contract"][field] == last["contract"][field]
    assert set(first["jobs"]) == set(last["jobs"]) == model.JOBS
    assert first["online_information_delivered"] is last["online_information_delivered"] is False
    for key in first["jobs"]:
        a, b = copy.deepcopy(first["jobs"][key]), copy.deepcopy(last["jobs"][key])
        if key == "loaded": a.pop("storage_release_at"); b.pop("storage_release_at")
        if key == "receiver": a.pop("load_seconds"); b.pop("load_seconds")
        assert a == b


def test_strict_protection_keeps_tiny_regression_and_missing_completion_unknown():
    assert model.protected(prediction((10., 10., 10., 10. + 1e-12)), prediction()) is False
    partial = prediction(); partial["completion"].pop("receiver")
    assert model.protected(partial, prediction()) is None
    assert model.protected({"status": "unknown_unfinished_projection", "completion": {}}, prediction()) is None


@pytest.mark.parametrize("bad", (float("nan"), float("inf"), -1., True))
def test_invalid_completion_is_unknown_not_model_protected(bad):
    value = prediction(); value["completion"]["receiver"] = bad
    assert model.protected(value, value) is None


def test_undeclared_case_and_action_fail_closed():
    with pytest.raises(ValueError, match="undeclared_overlap_case"):
        model.make_bundle({"case_id": "injected", "storage_gate": 5.4, "receiver_load": 9.})
    bad = {**model.public_domain()["incumbent"], "reuse_next": 9}
    assert model.predict(model.public_domain()["cases"][0], bad)["status"] == "unknown_undeclared_action"


def plateau_evaluator(case, action):
    target = action["initial_next"] == 2 and action["departure"] == .11 and action["reuse_next"] == 8
    return prediction((10., 10., 9. if target else 10., 10.))


def test_strong_plateau_and_pair_baselines_can_cross_neutral_states():
    case = model.public_domain()["cases"][0]
    results = {method: model.solve(case, method, evaluator=plateau_evaluator) for method in model.METHODS}
    assert results["coordinate_strict"]["model_gain"] == 0
    for method in model.METHODS[1:]:
        assert results[method]["model_gain"] == 1
    for row in results.values():
        assert row["evaluations"] <= row["budget"] == 16
        assert len(row["rows"]) == row["candidate_denominator"] == 16


def test_budget_does_not_hide_unexecuted_candidates():
    row = model.solve(model.public_domain()["cases"][0], "resource_pair_repair", evaluator=plateau_evaluator, budget=2)
    assert row["evaluations"] == 2 and row["stop"] == "budget_exhausted"
    assert sum(r["evaluation_status"] == "unknown_unexecuted" for r in row["rows"]) == 14


@pytest.mark.parametrize("defect", ("missing", "duplicate"))
def test_causal_cube_requires_full_unique_action_denominator(defect):
    case = model.public_domain()["cases"][0]
    cells = [{"action": a, "prediction": prediction()} for a in model.public_domain()["actions"]]
    if defect == "missing": cells.pop()
    else: cells[-1] = copy.deepcopy(cells[0])
    assert model.assess_case(case, cells)["status"] == "unknown_incomplete_or_duplicate_factorial"


def test_censored_cube_is_unknown_not_zero_interaction():
    case = model.public_domain()["cases"][0]
    cells = [{"action": a, "prediction": prediction()} for a in model.public_domain()["actions"]]
    cells[0]["prediction"] = {"status": "unknown_event_budget", "completion": {}}
    result = model.assess_case(case, cells)
    assert any(cube["status"] == "unknown_incomplete_cube" and cube["third_difference_by_job"] is None for cube in result["cubes"])


def test_model_intent_records_first_wait_and_second_immediate_without_stock_creation():
    case = model.public_domain()["cases"][0]
    action = {**model.public_domain()["incumbent"], "first_return_delay": .5, "reuse_next": 8}
    projection = model.Projection(model.make_bundle(case), action)
    projection.time = 6.
    projection.trays["L"].update(node=6, mode="empty", job=None)
    projection.tick()
    assert projection.requests[0]["earliest"] == 6.5 and projection.returns == 1
    projection.return_pending = False; projection.returns = 1; projection.time = 12.
    projection.tick()
    assert projection.requests[-1]["earliest"] == 12. and projection.returns == 2
    assert set(projection.trays) == {"L", "E"}
