from dataclasses import asdict

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.label_stability import (
    branch_with_future, candidate_pool, collect_decisions, digest, sampled_futures,
    stability_summary, sustained_scenes)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine


def test_checkpoint_label_keeps_continuation_phase_and_matches_actual_branch():
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20, slow_period=3)
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    state = engine.observe()
    candidate = candidate_pool(state, state.trays['loaded'], spec)[0][0]
    checkpoint = engine.checkpoint()
    before = digest(asdict(checkpoint.state))
    expected = engine.branch(candidate).advance(24)
    actual = branch_with_future(checkpoint, candidate, scene.future_bags, 24)
    assert actual == expected
    assert checkpoint.slow_controller.next_trigger_at == 0
    assert digest(asdict(checkpoint.state)) == before
    with pytest.raises(ValueError, match='unobserved later'):
        branch_with_future(checkpoint, candidate, tuple(state.bags.values()), 24)


def test_future_sampling_is_nested_reproducible_and_preserves_observed_identity():
    scene = sustained_scenes()[0]
    state = scene.initial
    before = digest(asdict(state))
    two = sampled_futures(scene.future_bags, state, count=2, seed=19)
    many = sampled_futures(scene.future_bags, state, count=32, seed=19)
    assert two == many[:2]
    assert any(f != scene.future_bags for f in many)
    assert all(b.arrival > state.now and b.bag_id not in state.bags for f in many for b in f)
    assert digest(asdict(state)) == before


def test_pairing_removes_shared_future_noise_and_selection_reference_is_held_out():
    # Two actions share large exogenous noise but always differ by exactly 2.
    common = np.array([0., 100.] * 16)
    costs = np.array([[common + 2, common], [common + 3, common + 1]])
    result = stability_summary(costs, [0, 1], [0, 5])
    assert result['value_range'] == 2
    assert result['timed_selection_loss_within_normal_pool'] == 2
    assert all(r['paired_delta_standard_errors'] == [0, 0] for r in result['rows'])
    assert all(r['other_replicates_regret'] == 0 for r in result['rows'])
    assert result['best_index'] == 1


def test_samples_are_reachable_later_rounds_and_keep_single_action_denominator():
    scene = sustained_scenes()[0]
    samples, history, result = collect_decisions(scene, ControlSpec(planning_horizon=20, candidate_count=1), expanded_count=1)
    assert [s['band'] for s in samples] == [0, 20, 40]
    assert all(s['checkpoint'].phase == 'routes' for s in samples)
    assert any(s['checkpoint'].state.completed for s in samples[1:])
    assert len(history) == scene.horizon
    assert any(r.get('normal_interventions') == 1 for r in history)
    assert len(result.completed) == 6
