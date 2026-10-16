import copy
import pytest
from scripts.experiments.g31_ics_circulation import research_preexisting_occupancy_domain as model


def prediction():
    return {"status": "conditional_prediction", "completion": {j: 10. for j in model.JOBS}, "completion_sum": 50.}


def test_complete_new_domain_preregistered_before_outcomes():
    plan = model.protocol()
    assert plan["maximum_projection_cells"] == 192 and plan["native_branch_budget"] == 0
    assert len(plan["cases"]) == 6
    for row in plan["cases"]:
        assert len(row["configuration_sha256"]) == 64
        assert len(row["domain"]["actions"]) == 32
        assert len({model.prior.key(a) for a in row["domain"]["actions"]}) == 32
        assert len([a for a in row["domain"]["actions"] if a["initial_next"] == 1]) == 16
    assert len(plan["falsifiable_criteria"]) == 5


def test_timing_windows_include_public_blocker_and_loaded_clearance():
    case = next(c for c in model.cases() if c["blocker_load"] == 3.)
    d = model.domain(case)
    assert d["public_derivation"]["blocker_node1_clear_bound"] == pytest.approx(3.1)
    assert d["public_derivation"]["loaded_node1_clear_bound_if_E_does_not_preempt"] == pytest.approx(4.2)
    assert d["public_derivation"]["supply_windows"] == pytest.approx([.11, 2.21, 3.101, 4.201])


def test_real_blocker_job_tray_and_park_do_not_change_existing_capacities():
    case = model.cases()[-1]; bundle = model.make_bundle(case); old = model.prior.fixture.scene(0.)
    assert set(bundle["trays"]) == {"L", "E", "P"}
    assert set(bundle["jobs"]) == model.JOBS
    assert len(bundle["contract"]["jobs"]) == 5 and len(bundle["contract"]["trays"]) == 3
    assert bundle["jobs"]["blocker"]["destination"] == 9
    assert bundle["trays"]["P"]["node"] == 1 and bundle["trays"]["P"]["mode"] == "loading"
    assert bundle["jobs"]["loaded"]["storage_release_at"] == 0
    for node in old["node_contracts"]:
        new = next(n for n in bundle["contract"]["node_contracts"] if n["node"] == node["node"])
        assert new == node
    assert bundle["contract"]["edge_contracts"][:-1] == old["edge_contracts"]
    assert bundle["online_information_delivered"] is False


def test_blocker_is_in_strict_protection_denominator():
    value = prediction(); value["completion"]["blocker"] += 1e-12
    assert model.protected(value, prediction()) is False
    value["completion"].pop("blocker")
    assert model.protected(value, prediction()) is None


@pytest.mark.parametrize("bad", (float("inf"), float("nan"), True, -1.))
def test_bad_blocker_completion_remains_unknown(bad):
    value = prediction(); value["completion"]["blocker"] = bad
    assert model.protected(value, value) is None


def test_missing_and_duplicate_action_rows_cannot_certify_factorial():
    case = model.cases()[0]
    cells = [{"action": a, "prediction": prediction()} for a in model.domain(case)["actions"]]
    assert model.assess(case, cells[:-1])["status"] == "unknown_incomplete_or_duplicate_factorial"
    cells[-1] = copy.deepcopy(cells[0])
    assert model.assess(case, cells)["status"] == "unknown_incomplete_or_duplicate_factorial"


def test_plateau_pair_and_enumeration_have_identical_information_budget():
    case = model.cases()[0]; actions = model.domain(case)["actions"]
    lookup = {}
    for action in actions:
        p = prediction()
        if action["initial_next"] == 2 and action["departure"] == .11 and action["reuse_next"] == 8:
            p["completion"]["reuse1"] -= 1.; p["completion_sum"] -= 1.
        lookup[model.prior.key(action)] = p
    results = {m: model.solve(case, m, lookup) for m in model.METHODS}
    assert results["coordinate_strict"]["model_gain"] == 0
    for method in model.METHODS[1:]: assert results[method]["model_gain"] == 1
    for row in results.values():
        assert row["evaluations"] <= row["budget"] == 32
        assert len(row["rows"]) == 32
    assert lookup[model.prior.key(model.domain(case)["incumbent"])]["completion"] == prediction()["completion"]


def test_unknown_prediction_remains_unknown_in_fixed_reference_and_cube():
    case = model.cases()[0]; cells = [{"action": a, "prediction": prediction()} for a in model.domain(case)["actions"]]
    cells[0]["prediction"] = {"status": "unknown_event_budget", "completion": {}}
    result = model.assess(case, cells)
    assert result["coverage"][0]["model_protected"] is None
    assert any(cube["status"] == "unknown_incomplete_cube" for cube in result["cubes"])


def test_park_path_is_explicit_and_does_not_override_other_trays():
    case = model.cases()[0]
    projection = model.Projection(model.make_bundle(case), model.domain(case)["incumbent"])
    assert projection.choose_next("P") == 9
    projection.trays["E"].update(node=1)
    assert projection.choose_next("E") == 3
    assert projection.choose_next("L") == 1


def test_park_edge_is_shared_legal_and_only_simple_blocker_destination_path():
    bundle = model.make_bundle(model.cases()[0]); c = bundle["contract"]
    graph = {row[0]: list(row[5]) for row in c["node_records"]}
    paths, stack = [], [(1,)]
    while stack:
        path = stack.pop()
        if path[-1] == 9: paths.append(path); continue
        stack.extend(path + (n,) for n in graph[path[-1]] if n not in path)
    assert paths == [(1, 9)] and graph[9] == []
    assert next(e for e in c["edge_contracts"] if (e["from"], e["to"]) == (1, 9))["capacity"] == 1
    assert {n["resource_owner"] for n in c["node_contracts"] if n["node"] in (1, 9)} == {"A"}
