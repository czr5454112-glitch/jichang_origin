"""Optional prediction-only use of uncommitted remaining-route releases.

Firm inventory and donor permissions are unchanged. This evaluator deliberately
uses point forecasts as a heuristic, not as executable supply or a guarantee.
It makes retained route hints causally relevant to later routing decisions.
"""
from dataclasses import asdict
from collections import defaultdict

from .evaluation import AnalyticDeltaEvaluator, ForecastDemand
from .learning import TimedAnalyticEvaluator, active_forecasts
from .prebalance import conditional_supply, known_supply
from .runtime import actual_action_key


class ConditionalAnalyticEvaluator(AnalyticDeltaEvaluator):
    def _supply(self, state, candidate):
        supplies = defaultdict(list)
        for event in known_supply(state):
            if event.tray_id != candidate.tray_id:
                supplies[event.node].append(event.at)
        # conditional_supply excludes any tray already represented by firm
        # supply. The intervention itself replaces its own previous forecast.
        for event in conditional_supply(state):
            if event.tray_id != candidate.tray_id:
                supplies[event.node].append(event.at)
        supplies[state.bags[candidate.bag_id].destination].append(candidate.usable_at)
        return supplies


class ConditionalTimedAnalyticEvaluator(TimedAnalyticEvaluator):
    def _base(self, state):
        forecasts = active_forecasts(state, self.routing_forecasts)
        return ConditionalAnalyticEvaluator(self.horizon, tuple(
            ForecastDemand(f.node, f.at, f.count, f.published_at) for f in forecasts))


class ConditionalCandidatePolicy:
    """Same legal action space; forecast-aware scoring is explicitly optional."""
    def __init__(self, horizon, forecasts):
        self.horizon = horizon
        self.forecasts = tuple(forecasts)
        self.history = []

    def __call__(self, state, candidates):
        if not candidates:
            raise ValueError('no_authorized_candidates')
        evaluator = ConditionalTimedAnalyticEvaluator(self.horizon, self.forecasts)
        unique = {}
        for candidate in candidates:
            unique.setdefault(actual_action_key(state, candidate), candidate)
        keys, actions = tuple(unique), tuple(unique.values())
        values = [evaluator.absolute(state, c) for c in actions]
        index = min(range(len(values)), key=lambda i: (values[i], i))
        self.history.append({'time': state.now, 'version': state.version,
                             'conditional_supply': [asdict(s) for s in conditional_supply(state)],
                             'candidate_count': len(candidates), 'distinct_interventions': len(actions),
                             'actual_action_keys': keys, 'scores': values, 'selected_key': keys[index],
                             'distinct_predicted_values': len(set(values)),
                             'predicted_value_spread': max(values) - min(values),
                             'true_continuation_values_measured': False,
                             'supply_use': 'conditional_heuristic_only_not_export_permission'})
        return actions[index]
