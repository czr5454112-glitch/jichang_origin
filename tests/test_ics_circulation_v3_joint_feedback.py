from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.joint_feedback import ForecastResponsePlanner, commit_feedback_plan, published_proxy
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.joint_feedback import run_feedback_episode


def scene():
    nodes = {n: Node(n, n, n, capacity=3) for n in ('S', 'U', 'V', 'G')}
    edges = [Edge('SU', 'S', 'U', 1), Edge('UG', 'U', 'G', 1),
             Edge('SV', 'S', 'V', 2), Edge('VG', 'V', 'G', 2), Edge('GS', 'G', 'S', 2)]
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {'t': Tray('t', 'S', 'loaded', 'b'), 'spare': Tray('spare', 'G')},
                    {'b': Bag('b', 'S', 'G', 0, 10)})


def test_feedback_plans_are_detached_and_all_actions_pass_physical_owner():
    state = scene()
    before = state.clone()
    planner = ForecastResponsePlanner(planning_horizon=8, max_rollouts=4)
    plan = planner.plan(state)
    assert state == before
    assert plan.diagnostics['single_deviation_count'] > 0
    assert plan.diagnostics['same_continuation_for_all_scored_actions']
    engine = Simulation(state)
    observation = engine.observe()
    plan = planner.plan(observation)
    commit_feedback_plan(engine, plan)
    assert engine.advance(9).completed['b'] <= 9


def test_future_publication_and_cancelled_units_cannot_enter_proxy():
    state = scene()
    f = RoutingDemandForecast('f', 'G', 'S', 4, 10)
    future = replace(f, forecast_id='later', published_at=2)
    cancelled = replace(f, count=0)
    assert len(published_proxy(state, (f, future), 8)) == 1
    assert published_proxy(state, (cancelled, future), 8) == ()
    with pytest.raises(ValueError, match='Conflicting forecast'):
        published_proxy(state, (f, cancelled), 8)


def test_stale_feedback_plan_fails_before_committing_any_route():
    engine = Simulation(scene())
    plan = ForecastResponsePlanner(planning_horizon=8).plan(engine.observe())
    engine.state.version += 1
    before = engine.state.clone()
    with pytest.raises(ValueError, match='stale_or_wrong_mode'):
        commit_feedback_plan(engine, plan)
    assert engine.state == before


def test_budget_truncation_is_not_reported_as_joint_optimality():
    plan = ForecastResponsePlanner(planning_horizon=8, max_rollouts=1).plan(scene())
    assert plan.diagnostics['single_deviation_count'] > 0
    assert plan.diagnostics['unscored_deviations'] > 0
    assert plan.diagnostics['rollout_attempts'] == 1
    assert 'not_joint_optimum' in plan.diagnostics['claim']


def test_feedback_changes_loaded_route_and_actual_empty_response_then_service():
    fixture = feedback_scene()
    planner = ForecastResponsePlanner(planning_horizon=20, max_rollouts=8)
    baseline, base_history = run_feedback_episode(fixture.initial, fixture.forecasts, fixture.future_bags,
                                                  fixture.horizon, mode='route_then_prebalance', planner=planner)
    feedback, history = run_feedback_episode(fixture.initial, fixture.forecasts, fixture.future_bags,
                                             fixture.horizon, planner=planner)
    assert baseline.total_cost == pytest.approx(3.6)
    assert feedback.total_cost == pytest.approx(0.6)
    assert history[0]['actual_route_changed']
    chosen = next(row for row in history[0]['scored'] if row['index'] == history[0]['selected_index'])
    assert chosen['response_changed']
    assert feedback.completed['need:0'] < baseline.completed['need:0']
    assert all(row['rollout_attempts'] == 0 for row in base_history)


def test_unused_lookahead_is_skipped_and_published_truth_is_not_swapped_into_planning():
    matched = feedback_scene()
    reversed_scene = feedback_scene(condition='reversal')
    planner = ForecastResponsePlanner(planning_horizon=20)
    # Same observation/public forecast -> exactly same plan before truth arrives.
    one = planner.plan(matched.initial, matched.forecasts)
    two = planner.plan(reversed_scene.initial, reversed_scene.forecasts)
    assert one.proposals == two.proposals
    assert one.diagnostics['proxy_sha256'] == two.diagnostics['proxy_sha256']
    empty = scene()
    empty.bags.clear()
    empty.trays['t'] = replace(empty.trays['t'], mode='empty', bag_id=None)
    plan = planner.plan(empty)
    assert plan.diagnostics['rollout_attempts'] == 0
