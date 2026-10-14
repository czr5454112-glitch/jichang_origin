"""Bounded response search retaining both conventional order incumbents.

This is a stronger development comparator, not a joint optimum. A prior
route-first-only single deviation could discard the stronger other ordering.
The first two distinct responses now have priority within the same rollout
budget; route deviations are considered afterwards. Monotonicity is only with
respect to the common prospective score at this boundary, not actual future
episode cost under forecast error or a truncated horizon.
"""
from dataclasses import asdict
from time import perf_counter

from .adaptive_order_feedback import AdaptiveOrderPlanner
from .joint_feedback import FeedbackPlan, fingerprint, published_proxy, route_signature


class PortfolioFeedbackPlanner(AdaptiveOrderPlanner):
    def plan(self, snapshot, forecasts=(), *, mode='feedback_with_order_incumbents'):
        if mode != 'feedback_with_order_incumbents':
            return super().plan(snapshot, forecasts, mode=mode)
        if self.max_rollouts < 2:
            raise ValueError('two incumbent responses require rollout budget at least two')
        started = perf_counter()
        visible = tuple(f for f in forecasts if f.published_at <= snapshot.now)
        proxy = published_proxy(snapshot, visible, snapshot.now + self.spec.planning_horizon)
        route_first = self._construct(snapshot, visible, 'route_then_prebalance')
        empty_first = self._construct(snapshot, visible, 'prebalance_then_route')
        alternatives = list(dict.fromkeys(route_signature(c) for row in route_first[2] if not row['protected']
                                         for c in row['candidates'] if route_signature(c) != route_signature(row['chosen'])))
        constructions = [('route_then_prebalance', None, route_first), ('prebalance_then_route', None, empty_first)]
        # No accepted physical route is replaced. Each option is a fresh full
        # response built from the same uncommitted observation boundary.
        for override in alternatives:
            constructions.append(('route_first_single_deviation', override, None))
        seen, records, failures, evaluated = set(), [], [], 0
        best, selected, best_actions = None, 0, route_first[1]
        unscored = 0
        for index, (kind, override, constructed) in enumerate(constructions):
            if evaluated >= self.max_rollouts:
                unscored += 1
                continue
            try:
                planned, actions, _, response = constructed or self._construct(
                    snapshot, visible, 'route_then_prebalance', override)
                signature = tuple(sorted((route_signature(p) for p in actions), key=repr))
                if signature in seen:
                    continue
                seen.add(signature)
                # Identical empty boundaries need no rollout at all. Both
                # conventional controls produce the same absence of action.
                if not route_first[1] and not empty_first[1] and not alternatives:
                    continue
                evaluated += 1
                result = self._score(planned, visible, proxy)
                records.append({'index': index, 'kind': kind, 'override': override,
                                'proposals': [asdict(p) for p in actions], 'proxy_cost': result.total_cost,
                                'cost_components': result.cost_components, 'response_diagnostics': response,
                                'proxy_uncompleted': list(result.uncompleted_bag_ids)})
                if best is None or result.total_cost < best - 1e-9:
                    best, selected, best_actions = result.total_cost, index, actions
            except (ValueError, AssertionError) as exc:
                failures.append({'index': index, 'kind': kind, 'reason': str(exc), 'type': type(exc).__name__})
        return FeedbackPlan(fingerprint(asdict(snapshot)), best_actions,
            {'method': mode, 'time': snapshot.now, 'source_version': snapshot.version,
             'information': 'current_snapshot_and_already_published_forecasts_only',
             'execution_mode': 'whole_route', 'proxy_future': [asdict(b) for b in proxy],
             'proxy_sha256': fingerprint([asdict(b) for b in proxy]), 'control_spec': asdict(self.spec),
             'same_continuation_for_all_scored_actions': True, 'single_deviation_count': len(alternatives),
             'rollout_limit': self.max_rollouts, 'rollout_attempts': evaluated,
             'unscored_deviations': unscored, 'scored': records, 'failures': failures,
             'selected_index': selected, 'selected_proxy_cost': best,
             'actual_route_changed': tuple(route_signature(p) for p in best_actions if p.bag_id is not None)
                                     != tuple(route_signature(p) for p in route_first[1] if p.bag_id is not None),
             'status': 'bounded_incumbent_retaining_response_search',
             'claim': 'at successful common scoring boundaries retains both order costs; no true future or global optimality guarantee',
             'elapsed_ms': (perf_counter() - started) * 1000})
