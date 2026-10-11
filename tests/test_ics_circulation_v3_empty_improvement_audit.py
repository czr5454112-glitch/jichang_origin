"""Independent information and exact post-slow continuation checks."""
from collections import defaultdict
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.empty_improvement import (
    EmptyImprovementSettings, OneStepEmptyPrebalancer, build_empty_improvement_engine)
from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.joint_feedback import published_proxy
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.prebalance import PredictivePrebalancer
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    CACHE_CONTRACT, enable_replay_cache)
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator


@pytest.mark.parametrize("order", ["route_then_prebalance", "prebalance_then_route"])
def test_post_slow_projection_matches_actual_private_checkpoint_action_values(order):
    scene = feedback_scene()
    spec = ControlSpec(planning_horizon=20, coordination_order=order)
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    captured = []

    class PauseAtActualSlow(Exception):
        pass

    def pause():
        captured.append(engine.checkpoint())
        raise PauseAtActualSlow

    engine._run_slow_controller = pause
    with pytest.raises(PauseAtActualSlow):
        engine.advance(1)
    checkpoint = captured[0]
    state = checkpoint.state
    visible = tuple(f for f in scene.forecasts if f.published_at <= state.now)
    horizon = 40
    proxy = published_proxy(state, visible, horizon)
    ctrl = OneStepEmptyPrebalancer(spec=spec,
        settings=EmptyImprovementSettings(score_horizon=horizon, max_rollouts=2),
        generator_factory=base.generator_factory)
    greedy = PredictivePrebalancer(planning_horizon=20, planning_budget_ms=None,
        generator_factory=base.generator_factory).plan(state, visible)
    assert greedy.proposals and any(p.legs[0].depart == state.now for p in greedy.proposals)
    projected_costs, exact_costs = [], []
    for sequence in ((), greedy.proposals):
        private = checkpoint.clone()
        # Test-only oracle: resume the genuine past program counter and costs,
        # substituting the same PUBLIC synthetic tape as the online model.
        private.base.pending_arrivals = defaultdict(list)
        for bag in proxy:
            private.base.pending_arrivals[bag.arrival].append(bag)
        private.base.slow_controller.next_trigger_at = 2
        private.base.slow_controller.forecast_publications = visible
        private.cursor.stage_index += 1
        exact = CursorSimulation.from_checkpoint(private)
        for proposal in sequence:
            assert ExecutionValidator().commit(exact.state, proposal).accepted
        expected = exact.advance(horizon)
        score = ctrl._score(state, sequence, visible, proxy, 2)
        assert score["status"] == "complete"
        assert score["cost_components"] == expected.cost_components
        assert score["slow_trigger_times"] == exact.slow_controller.trigger_times
        assert 0 not in score["slow_trigger_times"]
        assert score["slow_trigger_times"][0] == 2
        projected_costs.append(score["proxy_cost"])
        exact_costs.append(expected.total_cost)
    assert projected_costs[1] - projected_costs[0] == pytest.approx(exact_costs[1] - exact_costs[0])


def test_hidden_actual_tape_change_preserves_same_first_slow_action_and_scores():
    scene = feedback_scene()
    false_truth = replace(scene, future_bags=())
    settings = EmptyImprovementSettings(score_horizon=20, max_rollouts=12)
    histories = []
    for source in (scene, false_truth):
        engine = build_empty_improvement_engine(source, settings=settings)
        engine.advance(1)
        histories.append(engine.slow_controller.history[0])
    left, right = histories
    assert left["proposals"] == right["proposals"]
    fields = ("snapshot_sha256", "published_forecasts", "proxy_bags", "proxy_sha256",
              "next_slow_trigger_at", "cursor", "selected_action_index", "selected_proxy_cost")
    assert {k: left["diagnostics"][k] for k in fields} == {k: right["diagnostics"][k] for k in fields}
    results = lambda item: [(r["proposals"], r["status"], r["proxy_cost"],
                             r["search_calls"], r["search_work"])
                            for r in item["diagnostics"]["scored_actions"]]
    assert results(left) == results(right)


def test_public_fast_baseline_propagates_isolated_cache_into_proxy_entrances(monkeypatch):
    from scripts.experiments.ics_circulation_v3.run_empty_improvement import build_case
    from scripts.experiments.ics_circulation_v3.routing_cache_contract import routing_cache_state

    original = CursorSimulation.from_visible.__func__
    contracts = []

    def record(cls, snapshot, context, forecast_tape, spec, published_forecasts):
        result = original(cls, snapshot, context, forecast_tape, spec, published_forecasts)
        contracts.append((context.cache_contract, routing_cache_state(result)["schema"]))
        return result

    monkeypatch.setattr(CursorSimulation, "from_visible", classmethod(record))
    engine = build_case(feedback_scene(), "public_fast4")
    engine.advance(1)
    assert contracts and all(pair == (CACHE_CONTRACT, CACHE_CONTRACT) for pair in contracts)
