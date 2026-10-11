import pytest

from scripts.experiments.ics_circulation_v3.portfolio_feedback import PortfolioFeedbackPlanner
from scripts.experiments.ics_circulation_v3.run_multi_load_feedback import scenes
from scripts.experiments.ics_circulation_v3.joint_feedback import commit_feedback_plan
from scripts.experiments.ics_circulation_v3.runtime import Simulation


def test_response_search_retains_strong_order_even_when_deviations_are_truncated():
    scene = scenes()[0]
    planner = PortfolioFeedbackPlanner(planning_horizon=20, max_rollouts=2)
    plan = planner.plan(scene.initial, scene.forecasts)
    costs = [r['proxy_cost'] for r in plan.diagnostics['scored']]
    assert len(costs) == 2
    assert plan.diagnostics['selected_proxy_cost'] == min(costs)
    assert plan.diagnostics['unscored_deviations'] > 0
    assert plan.diagnostics['rollout_attempts'] == 2
    engine = Simulation(scene.initial)
    plan = planner.plan(engine.observe(), scene.forecasts)
    commit_feedback_plan(engine, plan)
    engine.advance(2)
    with pytest.raises(ValueError, match='at least two'):
        PortfolioFeedbackPlanner(max_rollouts=1).plan(scene.initial, scene.forecasts)


def test_extra_legal_responses_cannot_raise_the_same_boundary_proxy_score():
    scene = scenes()[3]
    planner = PortfolioFeedbackPlanner(planning_horizon=20, max_rollouts=16)
    combined = planner.plan(scene.initial, scene.forecasts)
    orders = planner.plan(scene.initial, scene.forecasts, mode='adaptive_two_orders')
    assert combined.diagnostics['selected_proxy_cost'] <= orders.diagnostics['selected_proxy_cost'] + 1e-9
    assert combined.diagnostics['rollout_attempts'] <= 16
    assert not combined.diagnostics['failures']
