from scripts.experiments.ics_circulation_v3.adaptive_order_feedback import AdaptiveOrderPlanner, urgency_matrix
from scripts.experiments.ics_circulation_v3.joint_feedback import run_feedback_episode


def test_order_choice_uses_observed_urgency_and_can_keep_route_first():
    scenes = urgency_matrix()
    scene = next(s for s in scenes if s.factors['shared_travel'] == 2
                 and s.factors['detour_extra'] == 3 and s.factors['loaded_deadline_slack'] == 0)
    planner = AdaptiveOrderPlanner(planning_horizon=20)
    plan = planner.plan(scene.initial, scene.forecasts)
    assert plan.diagnostics['selected_index'] == 0
    assert plan.diagnostics['rollout_attempts'] == 2
    chosen = plan.diagnostics['scored'][0]['proxy_cost']
    assert chosen < plan.diagnostics['scored'][1]['proxy_cost']
    result, _ = run_feedback_episode(scene.initial, scene.forecasts, scene.future_bags,
                                     scene.horizon, mode='adaptive_two_orders', planner=planner)
    assert result.total_cost == chosen


def test_full_urgency_grid_is_preserved_and_budget_is_explicit():
    scenes = urgency_matrix()
    assert len(scenes) == 18 and len({s.name for s in scenes}) == 18
    scene = scenes[0]
    plan = AdaptiveOrderPlanner(planning_horizon=20, max_rollouts=1).plan(scene.initial, scene.forecasts)
    assert plan.diagnostics['rollout_attempts'] == 0
    assert plan.diagnostics['unscored_deviations'] == 1
