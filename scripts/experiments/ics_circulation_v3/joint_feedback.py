"""One routing -> prebalancing response -> route-selection feedback round.

All proposed routes are uncommitted decisions at the current boundary. Each
alternative rebuilds the same protected routing/empty controller from that
boundary. Thus a balancing response can change the selected loaded route;
there is no fictitious cancellation of an already accepted empty obligation.
This is a bounded single-deviation method, not joint optimal control.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from time import perf_counter

from .learning import CandidatePolicy, active_forecasts
from .model import Bag, RouteCandidate
from .phase4_control import ControlSpec, GeneratorFactory, PublishedRoutingSelector, build_engine
from .prebalance import PredictivePrebalancer
from .runtime import ExecutionValidator, Simulation, actual_action_key


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def route_signature(candidate):
    return (candidate.tray_id, candidate.bag_id, candidate.destination_node,
            tuple((leg.edge_id, leg.depart, leg.arrive) for leg in candidate.legs),
            candidate.unload_complete, candidate.usable_at)


def published_proxy(snapshot, forecasts, horizon):
    """Only declared, visible pending forecast units; never engine arrivals."""
    visible = tuple(f for f in forecasts if f.published_at <= snapshot.now)
    active = active_forecasts(snapshot, visible)
    return tuple(sorted((Bag(identity, f.node, f.destination, f.at, f.deadline)
                         for f in active if f.at <= horizon for identity in f.unit_ids),
                        key=lambda bag: (bag.arrival, bag.bag_id)))


class _ObservedSelector:
    def __init__(self, horizon, forecasts, override=None):
        self.horizon, self.forecasts, self.override = horizon, tuple(forecasts), override
        self.history, self.override_used = [], False

    def __call__(self, snapshot, candidates):
        chosen = CandidatePolicy(self.horizon, self.forecasts, kind='timed')(snapshot, candidates)
        if self.override is not None and candidates[0].tray_id == self.override[0]:
            matching = [c for c in candidates if route_signature(c) == self.override]
            if not matching:
                raise ValueError('single_deviation_not_in_current_legal_candidate_set')
            chosen, self.override_used = matching[0], True
        self.history.append({'time': snapshot.now, 'tray_id': chosen.tray_id,
                             'protected': snapshot.bags[chosen.bag_id].protected,
                             'candidates': tuple(candidates), 'chosen': chosen,
                             'actual_action_keys': tuple(actual_action_key(snapshot, c, route_mode='whole_route') for c in candidates)})
        return chosen


@dataclass(frozen=True)
class FeedbackPlan:
    source_fingerprint: str
    proposals: tuple[RouteCandidate, ...]
    diagnostics: dict


class ForecastResponsePlanner:
    def __init__(self, *, planning_horizon=24, candidate_count=4, max_rollouts=16,
                 expansion_limit=2000, slow_period=2):
        if any(type(v) is not int or v < 1 for v in (planning_horizon, candidate_count, max_rollouts, expansion_limit, slow_period)):
            raise ValueError('positive integer planning budgets required')
        self.spec = ControlSpec(routing='timed', predictive=True, planning_horizon=planning_horizon,
                                candidate_count=candidate_count, expansion_limit=expansion_limit,
                                slow_period=slow_period, route_mode='whole_route')
        self.max_rollouts = max_rollouts
        self.factory = GeneratorFactory(self.spec)

    def _construct(self, snapshot, visible, order, override=None):
        selector = _ObservedSelector(snapshot.now + self.spec.planning_horizon, visible, override)
        slow = PredictivePrebalancer(visible, planning_horizon=self.spec.planning_horizon,
                                    planning_budget_ms=None, generator_factory=self.factory)
        scratch = Simulation(snapshot, route_mode='whole_route', generator_factory=self.factory,
                             route_selector=selector, slow_controller=slow,
                             search_horizon=self.spec.planning_horizon, candidate_count=self.spec.candidate_count,
                             coordination_order=order)
        # Reuse exactly the kernel's protected admission, FIFO, greedy response,
        # continued empty obligations and reactive fallback. This scratch
        # engine contains no exogenous tape and never advances physical time.
        scratch._continue_causally()
        if override is not None and not scratch.route_selector.override_used:
            raise ValueError('requested_deviation_was_not_a_loaded_decision')
        proposals = tuple(sorted((plan for tray_id, plan in scratch.state.plans.items()
                                  if tray_id not in snapshot.plans), key=lambda p: p.dependency_version))
        return scratch.state.clone(), proposals, scratch.route_selector.history, scratch.slow_controller.last_diagnostics

    def _score(self, planned, visible, proxy):
        engine = build_engine(planned, visible, proxy, self.spec)
        # The response at this tick has already been planned. The continuation
        # has the same independent slow period, without running it twice now.
        engine.slow_controller.next_trigger_at = planned.now + self.spec.slow_period
        return engine.advance(planned.now + self.spec.planning_horizon)

    def plan(self, snapshot, forecasts=(), *, mode='one_round_feedback'):
        if mode not in {'route_then_prebalance', 'prebalance_then_route', 'one_round_feedback'}:
            raise ValueError('unknown feedback comparison mode')
        start = perf_counter()
        visible = tuple(f for f in forecasts if f.published_at <= snapshot.now)
        proxy = published_proxy(snapshot, visible, snapshot.now + self.spec.planning_horizon)
        order = 'prebalance_then_route' if mode == 'prebalance_then_route' else 'route_then_prebalance'
        baseline, base_actions, choices, base_response = self._construct(snapshot, visible, order)
        alternatives = []
        if mode == 'one_round_feedback':
            for row in choices:
                if row['protected']:
                    continue
                alternatives.extend(route_signature(c) for c in row['candidates']
                                    if route_signature(c) != route_signature(row['chosen']))
        # Whole-route physical signatures discard candidate names/versions.
        alternatives = list(dict.fromkeys(alternatives))
        records, failures, selected = [], [], 0
        best_actions = base_actions
        best_cost = None
        # Conventional controls do not pay for unused forecast rollouts. A
        # feedback boundary with no distinct route choice also skips scoring.
        to_score = [None] + alternatives[:self.max_rollouts - 1] if alternatives else []
        for index, override in enumerate(to_score):
            try:
                if override is None:
                    planned, actions, response = baseline, base_actions, base_response
                else:
                    planned, actions, _, response = self._construct(snapshot, visible, order, override)
                evaluated = self._score(planned, visible, proxy)
                response_signatures = [route_signature(p) for p in actions if p.bag_id is None]
                records.append({'index': index, 'override': override, 'proposals': [asdict(p) for p in actions],
                                'empty_response': response_signatures,
                                'response_changed': response_signatures != [route_signature(p) for p in base_actions if p.bag_id is None],
                                'proxy_cost': evaluated.total_cost, 'cost_components': evaluated.cost_components,
                                'proxy_uncompleted': list(evaluated.uncompleted_bag_ids),
                                'response_diagnostics': response})
                if best_cost is None or evaluated.total_cost < best_cost - 1e-9:
                    best_actions, best_cost, selected = actions, evaluated.total_cost, index
            except (ValueError, AssertionError) as exc:
                failures.append({'index': index, 'override': override, 'type': type(exc).__name__, 'reason': str(exc)})
        # If every proxy continuation fails, preserve the legal conventional
        # construction; never represent an unscored incumbent as optimized.
        diagnostics = {'method': mode, 'time': snapshot.now, 'source_version': snapshot.version,
                       'information': 'current_snapshot_and_already_published_forecasts_only',
                       'execution_mode': 'whole_route', 'proxy_future': [asdict(b) for b in proxy],
                       'proxy_sha256': fingerprint([asdict(b) for b in proxy]),
                       'control_spec': asdict(self.spec), 'same_continuation_for_all_scored_actions': True,
                       'candidate_decisions': [{**row, 'chosen': asdict(row['chosen']),
                                                'candidates': [asdict(c) for c in row['candidates']]} for row in choices],
                       'single_deviation_count': len(alternatives), 'rollout_limit': self.max_rollouts,
                       'unscored_deviations': max(0, len(alternatives) - (self.max_rollouts - 1)),
                       'rollout_attempts': len(to_score),
                       'scored': records, 'failures': failures, 'selected_index': selected,
                       'selected_proxy_cost': best_cost,
                       'actual_route_changed': tuple(route_signature(p) for p in best_actions if p.bag_id is not None)
                                               != tuple(route_signature(p) for p in base_actions if p.bag_id is not None),
                       'status': ('conventional_construct_only' if mode != 'one_round_feedback'
                                  else 'no_distinct_route_deviation' if not alternatives
                                  else 'fallback_all_proxy_rollouts_failed' if best_cost is None
                                  else 'best_scored_single_deviation'),
                       'claim': 'one_response_round_with_bounded_single_route_deviations_not_joint_optimum',
                       'elapsed_ms': (perf_counter() - start) * 1000}
        return FeedbackPlan(fingerprint(asdict(snapshot)), best_actions, diagnostics)


def commit_feedback_plan(engine, plan):
    """Prevalidate the entire sequential response before publishing any action.

    The single-process driver owns this boundary. This is not a distributed
    transaction; the separate message/participant protocol owns that problem.
    """
    observation = engine.observe()
    if engine.route_mode != 'whole_route' or fingerprint(asdict(observation)) != plan.source_fingerprint:
        raise ValueError('stale_or_wrong_mode_feedback_plan')
    staged = observation.clone()
    for action in plan.proposals:
        verdict = ExecutionValidator().commit(staged, action, route_mode='whole_route')
        if not verdict.accepted:
            raise ValueError(f'feedback_joint_prevalidation_failed:{verdict.reason}')
    for action in plan.proposals:
        verdict = engine.intervene(action)
        assert verdict.accepted, verdict.reason


def run_feedback_episode(initial, forecasts, future_bags, horizon, *, mode='one_round_feedback', planner=None):
    """Driver owns real future; the planner receives observation/publications."""
    planner = planner or ForecastResponsePlanner()
    engine = Simulation(initial, future_bags, route_mode='whole_route', generator_factory=planner.factory,
                        route_selector=PublishedRoutingSelector(planner.spec, forecasts),
                        search_horizon=planner.spec.planning_horizon, candidate_count=planner.spec.candidate_count)
    next_slow = initial.now
    history = []
    while engine.state.now < horizon:
        observation = engine.observe()
        if observation.now >= next_slow:
            plan = planner.plan(observation, forecasts, mode=mode)
            commit_feedback_plan(engine, plan)
            history.append(plan.diagnostics)
            next_slow += planner.spec.slow_period
        engine.advance(observation.now + 1)
    return engine.result(), history
