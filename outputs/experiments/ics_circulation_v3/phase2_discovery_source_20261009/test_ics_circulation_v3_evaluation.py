from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.evaluation import (
    AnalyticDeltaEvaluator, CirculationFootprint, ForecastDemand,
    PairedRolloutLabeler, ReleaseChange, ResidualCandidateScorer, indexed_int,
)
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, candidate_reservations, simulate
from scripts.experiments.ics_circulation_v3.scenarios import pilot_scenes
from scripts.experiments.ics_circulation_v3.counterexamples import run_counterexamples


def fixture_scene():
    scene = pilot_scenes()[12]
    candidates = CandidateGenerator(horizon=scene.horizon).generate(
        scene.state, scene.target_bag_id, scene.target_tray_id, k=3)
    assert len(candidates) == 3
    return scene, candidates


def test_delayed_release_changes_every_demand_prefix_not_just_total_inventory():
    change = ReleaseChange("B", 9, 13)
    assert [change.cumulative_delta(t) for t in (8, 9, 12, 13, 40)] == [0, -1, -1, 0, 0]


def test_occupancy_footprint_matches_execution_node_edge_and_reception():
    scene, candidates = fixture_scene()
    baseline, candidate = candidates[0], candidates[1]
    footprint = CirculationFootprint.between(scene.state, candidate, baseline)
    baseline_slots = candidate_reservations(scene.state, baseline)
    candidate_slots = candidate_reservations(scene.state, candidate)
    resources = {slot.resource for slot in (*baseline_slots, *candidate_slots)}
    for resource in resources:
        for at in range(32):
            actual = sum(slot.start <= at < slot.end for slot in candidate_slots if slot.resource == resource)
            actual -= sum(slot.start <= at < slot.end for slot in baseline_slots if slot.resource == resource)
            predicted = sum(slot.delta for slot in footprint.occupancy
                            if slot.resource == resource and slot.start <= at < slot.end)
            assert predicted == actual
    assert CirculationFootprint.between(scene.state, baseline, baseline).occupancy == ()


def test_old_arrival_time_matters_with_identical_current_stock():
    scene, candidates = fixture_scene()
    early, late = scene.state.clone(), scene.state.clone()
    flight = early.old_in_transit[0]
    early.old_in_transit = (replace(flight, depart=-24, arrive=6),)
    late.old_in_transit = (replace(flight, depart=-12, arrive=18),)
    evaluator = AnalyticDeltaEvaluator(48, (ForecastDemand("B", 10, 2),))
    assert early.trays == late.trays
    assert evaluator.absolute(early, candidates[0]) < evaluator.absolute(late, candidates[0])


def test_disabled_residual_and_enabled_model_have_exact_zero_baseline():
    scene, candidates = fixture_scene()
    evaluator = AnalyticDeltaEvaluator(scene.horizon, scene.forecasts)
    off = ResidualCandidateScorer(evaluator)
    on = ResidualCandidateScorer(evaluator, {"usable_ticks": .3, "edge_count": 4.})
    assert off.score(scene.state, candidates[0], candidates[0]) == 0
    assert on.score(scene.state, candidates[0], candidates[0]) == 0
    for candidate in candidates:
        assert off.score(scene.state, candidate, candidates[0]) == evaluator.delta(scene.state, candidate, candidates[0])
    with pytest.raises(ValueError, match="forbidden"):
        ResidualCandidateScorer(evaluator, {"actual_future": 1.}).score(scene.state, candidates[1], candidates[0])


def test_future_forecasts_are_rejected_and_noise_is_order_independent():
    scene, candidates = fixture_scene()
    with pytest.raises(ValueError, match="after decision"):
        AnalyticDeltaEvaluator(48, (ForecastDemand("B", 10, published_at=1),)).absolute(scene.state, candidates[0])
    object_ids = ["bag:3", "bag:1", "bag:2"]
    forward = {key: indexed_int(7, "scene", key, "arrival", -3, 3) for key in object_ids}
    backward = {key: indexed_int(7, "scene", key, "arrival", -3, 3) for key in reversed(object_ids)}
    assert forward == backward


def test_noop_replay_matches_full_ledger_trace_and_cost_without_mutating_source():
    scene, candidates = fixture_scene()
    before = scene.state.clone()
    first = simulate(scene.state, candidates[0], scene.future(0), scene.horizon)
    second = simulate(scene.state.clone(), candidates[0], scene.future(0), scene.horizon)
    assert first == second
    assert scene.state == before
    assert set(first.final_trays) == set(before.trays)


def test_labeling_is_paired_and_reordering_alternatives_does_not_change_labels():
    scene, candidates = fixture_scene()
    futures = [scene.future(0), scene.future(1)]
    labels, branches = PairedRolloutLabeler(scene.horizon).label(scene.state, candidates, futures)
    reordered, _ = PairedRolloutLabeler(scene.horizon).label(
        scene.state, (candidates[0], candidates[2], candidates[1]), futures)
    assert {x["candidate_id"]: x["paired_deltas"] for x in labels} == {
        x["candidate_id"]: x["paired_deltas"] for x in reordered}
    assert labels[0]["paired_deltas"] == [0., 0.]
    assert len(branches) == 6
    assert all(row["invariant_checks"] > 0 for row in branches)
    assert len({row["future_index"] for row in branches}) == 2


def test_invalid_reference_cannot_silently_produce_labels():
    scene, candidates = fixture_scene()
    with pytest.raises(ValueError, match="explicit valid baseline"):
        PairedRolloutLabeler(48).label(scene.state, tuple(reversed(candidates)), [scene.future(0)])
    mixed = (candidates[0], replace(candidates[1], baseline_id="another_scene"))
    with pytest.raises(ValueError, match="share the current reference"):
        PairedRolloutLabeler(48).label(scene.state, mixed, [scene.future(0)])


def test_pilot_source_groups_are_distinct_and_future_truth_not_a_feature():
    scenes = pilot_scenes()
    assert len(scenes) == len({scene.scene_id for scene in scenes}) == 24
    scene, candidates = fixture_scene()
    evaluator = AnalyticDeltaEvaluator(scene.horizon, scene.forecasts)
    before = evaluator.features(scene.state, candidates[0])
    for seed in range(4):
        scene.future(seed)
    assert evaluator.features(scene.state, candidates[0]) == before
    assert not any("actual" in key or "future" in key or "seed" in key for key in before)


def test_executable_counterexamples_cover_release_transit_and_shared_commit():
    results = run_counterexamples()
    assert len(results) == 3
    assert all(row["passed"] for row in results)
