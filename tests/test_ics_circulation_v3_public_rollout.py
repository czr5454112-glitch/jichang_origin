from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec
from scripts.experiments.ics_circulation_v3.public_rollout import PublicRolloutSelector, build_public_rollout_engine
from scripts.experiments.ics_circulation_v3.role_coverage import (
    CursorSimulation, VisibleDecisionContext, collect_role_decisions)


def first_decision():
    scene = sustained_scenes()[0]
    spec = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    sample = collect_role_decisions(scene, spec).samples[0]
    engine = CursorSimulation.from_checkpoint(sample["checkpoint"])
    return scene, spec, sample, engine.visible_decision_context()


def test_public_score_uses_only_published_forecasts_and_rejects_stale_candidates():
    scene, spec, sample, context = first_decision()
    state, candidates = sample["checkpoint"].state, sample["pool"]
    visible = tuple(f for f in scene.forecasts if f.published_at <= state.now)
    a, b = PublicRolloutSelector(scene.forecasts, spec=spec), PublicRolloutSelector(visible, spec=spec)
    for policy in (a, b):
        policy.set_decision_context(context)
    assert a(state, candidates) == b(state, candidates)
    assert [r["cost"] for r in a.history[0]["rollouts"]] == [r["cost"] for r in b.history[0]["rollouts"]]
    assert all(f["published_at"] <= state.now for f in a.history[0]["published_forecasts"])
    assert len(a.history[0]["rollouts"]) == len(candidates)
    with pytest.raises(ValueError, match="current decision context"):
        a(state, candidates)
    a.set_decision_context(context)
    with pytest.raises(ValueError, match="does not match"):
        a(state, candidates[:1])


def test_actual_unobserved_tape_change_does_not_change_first_decision_scores():
    scene = sustained_scenes()[0]
    altered = replace(scene, future_bags=())
    engines = [build_public_rollout_engine(s) for s in (scene, altered)]
    for engine in engines:
        engine.advance(1)
    histories = [engine.route_selector.selector.history for engine in engines]
    assert len(histories[0]) == len(histories[1]) == 1
    assert histories[0][0]["actual_action_keys"] == histories[1][0]["actual_action_keys"]
    assert [r["cost"] for r in histories[0][0]["rollouts"]] == [r["cost"] for r in histories[1][0]["rollouts"]]


def test_visible_context_contains_no_private_tape_and_slow_phase_is_not_reset():
    scene, spec, sample, context = first_decision()
    assert set(asdict(context)) == {"cursor", "next_slow_trigger_at", "cache_contract"}
    assert context.cache_contract is None
    late = VisibleDecisionContext(context.cursor, 3)
    branch = CursorSimulation.from_visible(sample["checkpoint"].state, late, (), spec, ())
    branch.choose_pending(sample["pool"][0])
    branch.advance(7)
    assert branch.slow_controller.trigger_times == [3, 5]
    with pytest.raises(ValueError, match="unpublished"):
        CursorSimulation.from_visible(sample["checkpoint"].state, context, (), spec, scene.forecasts)
