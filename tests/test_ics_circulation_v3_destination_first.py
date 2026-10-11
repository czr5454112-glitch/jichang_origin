"""Validated optional unload rule and immutable all-policy experiment gates."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.destination_first import DestinationFirstSelector, LoggedReferenceSelector
from scripts.experiments.ics_circulation_v3.learning import CandidatePolicy
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation
from scripts.experiments.ics_circulation_v3 import run_destination_first as runner


def scene():
    nodes = {n: Node(n, n, "owner", 4) for n in ("A", "B")}
    edges = {e.edge_id: e for e in (Edge("AB", "A", "B", 2), Edge("BA", "B", "A", 2))}
    state = Snapshot(0, Network(nodes, edges), {"t": Tray("t", "A", "loaded", "b")},
        {"b": Bag("b", "B", "A", 0, 20)}, module=FixedLocalModule(unload_ticks=2, hold_by_node={"A": 3}))
    unload = RouteCandidate("zero", "b", "t", (), 2, 5, 0, "zero", True, "A")
    cycle = RouteCandidate("cycle", "b", "t", (Leg("AB", 0, 2), Leg("BA", 2, 4)), 6, 9, 0, "zero", False, "A")
    return state, unload, cycle


class LastChoice:
    def __init__(self):
        self.history = []

    def __call__(self, state, candidates):
        self.history.append({"scores": [1.0] * (len(candidates) - 1) + [-1.0], "chosen_index": len(candidates) - 1})
        return candidates[-1]


def test_override_calls_original_once_logs_scores_and_never_mutates_state():
    state, unload, cycle = scene()
    before = deepcopy(state)
    delegate = LastChoice()
    selector = DestinationFirstSelector(delegate)
    assert selector(state, (unload, cycle)) == unload
    assert state == before and len(delegate.history) == 1
    record = selector.history[0]
    assert record["overridden"] and record["delegate_index"] == 1 and record["chosen_index"] == 0
    assert record["delegate_records"] == delegate.history
    delegate.history[0]["scores"][0] = 99
    assert record["delegate_records"][0]["scores"][0] == 1.


def test_disabled_rule_preserves_original_and_still_exposes_eligibility():
    state, unload, cycle = scene()
    selector = DestinationFirstSelector(LastChoice(), enabled=False)
    assert selector(state, (unload, cycle)) == cycle
    assert selector.history[0]["eligible"] and not selector.history[0]["overridden"]
    assert selector.history[0]["reason"] == "rule_disabled"


def test_legal_module_hold_is_preserved_and_bag_completion_is_not_empty_availability():
    state, unload, cycle = scene()
    chosen = DestinationFirstSelector(LastChoice())(state, (unload, cycle))
    engine = Simulation(state, (), control_mode="external")
    assert engine.intervene(chosen).accepted
    result = engine.advance(2)
    assert result.completed == {"b": 2}
    assert result.final_trays["t"].mode == "holding" and result.final_trays["t"].available_at == 5
    assert engine.advance(5).final_trays["t"].mode == "empty"


def test_unavailable_reception_rejects_unload_and_keeps_legal_cycle():
    state, unload, cycle = scene()
    state.trays["occupied"] = Tray("occupied", "A", "holding", available_at=3)
    validator = ExecutionValidator()
    assert not validator.validate(state, unload).accepted
    assert validator.validate(state, cycle).accepted
    selector = DestinationFirstSelector(LastChoice())
    assert selector(state, (unload, cycle)) == cycle
    assert selector.history[0]["reason"] == "no_legal_zero_edge_complete_candidate"
    assert "capacity:reception:A" in selector.history[0]["unload_validation"][0]["reason"]


@pytest.mark.parametrize("case", ("absent", "stale", "module_mismatch", "prefix", "accepted_plan"))
def test_rule_never_invents_or_repairs_an_unauthorized_unload(case):
    state, unload, cycle = scene()
    if case == "absent":
        options = (cycle,)
    elif case == "stale":
        options = (replace(unload, dependency_version=999), cycle)
    elif case == "module_mismatch":
        options = (replace(unload, usable_at=2), cycle)
    elif case == "prefix":
        options = (replace(unload, prefix_only=True), cycle)
    else:
        state.plans["t"] = cycle
        options = (unload, cycle)
    before = deepcopy(state)
    selector = DestinationFirstSelector(LastChoice())
    assert selector(state, options) == cycle
    assert not selector.history[0]["eligible"] and state == before


def test_non_destination_loaded_boundary_falls_back():
    state, unload, cycle = scene()
    state.bags["b"] = replace(state.bags["b"], destination="B")
    proposal = replace(cycle, legs=(Leg("AB", 0, 2),), unload_complete=4, usable_at=4, destination_node="B")
    selector = DestinationFirstSelector(LastChoice())
    assert selector(state, (proposal,)) == proposal
    assert selector.history[0]["reason"] == "not_loaded_at_destination"


def test_mixed_identity_pool_is_rejected_before_delegate():
    state, unload, cycle = scene()
    selector = DestinationFirstSelector(LastChoice())
    with pytest.raises(ValueError, match="identities"):
        selector(state, (unload, replace(cycle, tray_id="foreign")))
    assert selector.delegate.history == []


def test_out_of_pool_delegate_rejected_and_zero_pool_not_called():
    state, unload, cycle = scene()
    selector = DestinationFirstSelector(lambda state, candidates: replace(cycle, candidate_id="new"))
    with pytest.raises(ValueError, match="outside"):
        selector(state, (unload, cycle))
    empty = DestinationFirstSelector(LastChoice())
    with pytest.raises(ValueError, match="No authorized"):
        empty(state, ())
    assert empty.delegate.history == []


@pytest.mark.parametrize("kind", ("baseline", "timed"))
def test_logged_reference_matches_existing_candidate_policy_exact_selection(kind):
    state, unload, cycle = scene()
    original = CandidatePolicy(20, (), kind)
    logged = LoggedReferenceSelector(kind, ())
    assert logged(state, (unload, cycle)) == original(state, (unload, cycle))
    assert len(logged.history) == 1
    assert (logged.history[0]["scores"] is None) == (kind == "baseline")


def test_stored_physics_comparison_ignores_only_timing_and_detects_real_change():
    expected = {key: {} for key in runner.PHYSICS_FIELDS}
    expected["result"] = {"completed": {"b": 2}, "policy_stats": {"generation_ms": 1., "generation_calls": 2}}
    actual = deepcopy(expected)
    actual["result"]["policy_stats"]["generation_ms"] = 3.
    assert runner.compare_physics(actual, expected)["equal"]
    actual["result"]["completed"]["b"] = 3
    assert runner.compare_physics(actual, expected)["differing_fields"] == ["result"]


def test_topology_warmth_work_difference_is_reported_separately_from_physics():
    original = {key: [] for key in runner.PHYSICS_FIELDS}
    original["slow_history"] = [{"trigger_time": 0, "proposals": [], "diagnostics": {"search_expansions": 22, "search_calls": 1}}]
    replay = deepcopy(original)
    replay["slow_history"][0]["diagnostics"]["search_expansions"] = 16
    report = runner.compare_physics(replay, original)
    assert report["equal"] and report["non_timing_record_differing_fields"] == ["slow_history"]
    assert [row["search_expansions"] for row in report["slow_search_work"]] == [16, 22]
    replay["slow_history"][0]["diagnostics"]["search_calls"] = 2
    assert not runner.compare_physics(replay, original)["equal"]


def test_asdict_tuple_and_saved_json_list_do_not_create_false_mismatch():
    original = {key: [] for key in runner.PHYSICS_FIELDS}
    original["route_history"] = [{"chosen": {"legs": [{"edge_id": "AB"}]}}]
    replay = deepcopy(original)
    replay["route_history"][0]["chosen"]["legs"] = ({"edge_id": "AB"},)
    assert runner.compare_physics(replay, original)["equal"]


def test_declared_full_denominator_and_immutable_unit_names():
    assert runner.PROTOCOL["episodes"] == 26 * 2 * 36 == 1872
    assert runner.PROTOCOL["new_labels"] == runner.PROTOCOL["new_fits"] == 0
    assert len(runner.unit_scenes()) == 36
    assert sum(realization == "nominal" for realization, _ in runner.unit_scenes().values()) == 4


def test_unfrozen_unit_cannot_start_deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "deploy", lambda *args, **kwargs: pytest.fail("unfrozen deployment forbidden"))
    with pytest.raises(FileNotFoundError):
        runner.run_unit(tmp_path, "missing")
    assert not (tmp_path / "units").exists()


@pytest.mark.parametrize("kind", ("baseline", "timed"))
def test_disabled_wrapper_entire_run_equals_existing_controller(kind):
    from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
    scene = replace(sustained_scenes()[0], horizon=12)
    expected = runner.old.deployment(scene, kind=kind)
    actual = runner.deploy(scene, kind, None, None, None, enabled=False)
    assert runner.compare_physics(actual, expected)["equal"]
    assert actual["metrics"]["overrides"] == 0
    assert len(actual["delegate_history"]) == len(actual["destination_first_history"])
