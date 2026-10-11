"""A strong small-action comparator: forecast-rollout choice of both orders.

This is a per-boundary controller, not scene-level hindsight selection. Each
order uses the same physical permissions and the same declared continuation.
Its two prospective responses form a smaller, explicit comparison domain.
"""
from dataclasses import asdict, replace
from time import perf_counter

from .feedback_scenarios import feedback_scene
from .joint_feedback import (FeedbackPlan, ForecastResponsePlanner, fingerprint,
                             published_proxy, route_signature)


class AdaptiveOrderPlanner(ForecastResponsePlanner):
    def plan(self, snapshot, forecasts=(), *, mode='adaptive_two_orders'):
        if mode != 'adaptive_two_orders':
            return super().plan(snapshot, forecasts, mode=mode)
        start = perf_counter()
        visible = tuple(f for f in forecasts if f.published_at <= snapshot.now)
        proxy = published_proxy(snapshot, visible, snapshot.now + self.spec.planning_horizon)
        constructions = [self._construct(snapshot, visible, order)
                         for order in ('route_then_prebalance', 'prebalance_then_route')]
        signatures = [tuple(sorted((route_signature(p) for p in item[1]), key=repr)) for item in constructions]
        distinct = signatures[0] != signatures[1]
        selected, best, records, failures = 0, None, [], []
        if distinct and self.max_rollouts >= 2:
            for index, (state, actions, _, response) in enumerate(constructions):
                try:
                    result = self._score(state, visible, proxy)
                    records.append({'index': index, 'order': ('route_then_prebalance', 'prebalance_then_route')[index],
                                    'proposals': [asdict(p) for p in actions], 'proxy_cost': result.total_cost,
                                    'cost_components': result.cost_components,
                                    'proxy_uncompleted': list(result.uncompleted_bag_ids),
                                    'response_changed': index == 1, 'response_diagnostics': response})
                    if best is None or result.total_cost < best - 1e-9:
                        selected, best = index, result.total_cost
                except (ValueError, AssertionError) as exc:
                    failures.append({'index': index, 'type': type(exc).__name__, 'reason': str(exc)})
        actions = constructions[selected][1]
        return FeedbackPlan(fingerprint(asdict(snapshot)), actions,
            {'method': mode, 'time': snapshot.now, 'source_version': snapshot.version,
             'information': 'current_snapshot_and_already_published_forecasts_only',
             'execution_mode': 'whole_route', 'proxy_future': [asdict(b) for b in proxy],
             'proxy_sha256': fingerprint([asdict(b) for b in proxy]), 'control_spec': asdict(self.spec),
             'same_continuation_for_all_scored_actions': True,
             'single_deviation_count': int(distinct), 'rollout_limit': self.max_rollouts,
             'unscored_deviations': int(distinct and self.max_rollouts < 2),
             'rollout_attempts': 2 if distinct and self.max_rollouts >= 2 else 0,
             'scored': records, 'failures': failures, 'selected_index': selected, 'selected_proxy_cost': best,
             'actual_route_changed': tuple(route_signature(p) for p in actions if p.bag_id is not None)
                                     != tuple(route_signature(p) for p in constructions[0][1] if p.bag_id is not None),
             'status': 'best_of_two_prospective_orders' if best is not None else 'conventional_fallback_or_identical_orders',
             'claim': 'bounded_two_order_forecast_response_comparator_not_joint_optimum',
             'elapsed_ms': (perf_counter() - start) * 1000})


def urgency_matrix():
    """Predeclared follow-up changes observed deadlines, never past results.

    First factorial had slack=30 and feedback equalled prebalance-first in all
    54 cells. This 18-cell follow-up asks whether a fixed order remains adequate
    when loaded tardiness trades against future tray waiting. It is development,
    not an independent confirmation or selected best subset of the old table.
    """
    scenes = []
    for length in (2, 4, 6):
        for extra in (1, 3):
            for slack in (0, 1, 3):
                scene = feedback_scene(shared_travel=length, detour_extra=extra)
                initial = scene.initial.clone()
                initial.bags['initial'] = replace(initial.bags['initial'], deadline=length + 3 + slack)
                scenes.append(replace(scene, name=f'urgent_{scene.name}_slack{slack}', initial=initial,
                                      factors={**scene.factors, 'loaded_deadline_slack': slack,
                                               'role': 'new_development_factorial_following_fixed_order_tie_diagnosis'}))
    return tuple(scenes)
