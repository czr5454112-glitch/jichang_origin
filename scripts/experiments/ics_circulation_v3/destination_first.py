"""Opt-in validated destination-first rule, not a dominance theorem or owner."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from .learning import TimedAnalyticEvaluator
from .runtime import ExecutionValidator, actual_action_key


class LoggedReferenceSelector:
    """Exact baseline/timed selection arithmetic with one-pass score logging.

    CandidatePolicy's baseline/single-candidate paths do not compute scores;
    those records deliberately retain scores=None instead of invented scores.
    """
    def __init__(self, kind, forecasts, horizon=20):
        if kind not in {"baseline", "timed"}:
            raise ValueError("reference must be baseline or timed")
        self.kind, self.forecasts, self.horizon = kind, tuple(forecasts), horizon
        self.history = []

    def __call__(self, state, candidates):
        if not candidates:
            raise ValueError("No authorized candidates")
        published = tuple(f for f in self.forecasts if f.published_at <= state.now)
        scores = None
        if self.kind == "baseline" or len(candidates) == 1:
            index = 0
            rule = "first_candidate" if self.kind == "baseline" else "single_candidate"
        else:
            evaluator = TimedAnalyticEvaluator(state.now + self.horizon, published)
            scores = [evaluator.absolute(state, c) for c in candidates]
            index = min(range(len(candidates)), key=lambda i: (scores[i], i))
            rule = "timed_absolute_then_ordinal"
        self.history.append({"time": state.now, "scores": scores, "chosen_index": index,
            "selection_rule": rule, "published_forecasts": [asdict(f) for f in published]})
        return candidates[index]


class DestinationFirstSelector:
    """Call the original delegate exactly once, then optionally choose unload.

    No candidate is generated or removed. Only a complete zero-edge candidate
    already in the normal pool, matching the same active loaded bag/tray and
    accepted by ExecutionValidator, can override the delegate. Runtime still
    revalidates/commits under its normal owner lock. No committed plan is undone.
    """
    def __init__(self, delegate, *, enabled=True, route_mode="next_edge", validator=None):
        if type(enabled) is not bool or route_mode not in {"next_edge", "whole_route"}:
            raise ValueError("invalid destination-first configuration")
        self.delegate, self.enabled, self.route_mode = delegate, enabled, route_mode
        self.validator = validator or ExecutionValidator()
        self.history = []

    def __call__(self, state, candidates):
        candidates = tuple(candidates)
        if not candidates:
            raise ValueError("No authorized candidates")
        bag_id, tray_id = candidates[0].bag_id, candidates[0].tray_id
        if any(c.bag_id != bag_id or c.tray_id != tray_id for c in candidates):
            raise ValueError("candidate pool mixes bag/tray request identities")
        before = len(getattr(self.delegate, "history", ()))
        original = self.delegate(state, candidates)
        if original not in candidates:
            raise ValueError("delegate returned outside the normal candidate pool")
        delegate_history = getattr(self.delegate, "history", ())
        delegate_records = deepcopy(delegate_history[before:])
        tray, bag = state.trays.get(tray_id), state.bags.get(bag_id)
        at_destination = bool(bag is not None and tray is not None and tray.mode == "loaded"
            and tray.bag_id == bag_id and tray.node == bag.destination
            and bag_id not in state.completed and tray.available_at <= state.now)
        unload, checks = [], []
        if at_destination:
            for index, candidate in enumerate(candidates):
                if candidate.legs or candidate.prefix_only:
                    continue
                validation = self.validator.validate(state, candidate, route_mode=self.route_mode)
                checks.append({"index": index, "accepted": validation.accepted, "reason": validation.reason})
                if validation.accepted:
                    unload.append((index, candidate))
        selected = unload[0][1] if self.enabled and unload else original
        eligible = bool(unload)
        reason = ("not_loaded_at_destination" if not at_destination else
                  "no_legal_zero_edge_complete_candidate" if not eligible else
                  "rule_disabled" if not self.enabled else
                  "delegate_already_unloads" if selected == original else "destination_first_override")
        self.history.append({"time": state.now, "version": state.version,
            "bag_id": bag_id, "tray_id": tray_id, "source_node": tray.node if tray else None,
            "candidate_count": len(candidates), "enabled": self.enabled, "at_destination": at_destination,
            "eligible": eligible, "overridden": selected != original, "reason": reason,
            "unload_validation": checks, "delegate_records": delegate_records,
            "delegate_index": candidates.index(original), "chosen_index": candidates.index(selected),
            "delegate_choice": asdict(original), "chosen": asdict(selected),
            "delegate_action_key": actual_action_key(state, original, route_mode=self.route_mode),
            "chosen_action_key": actual_action_key(state, selected, route_mode=self.route_mode)})
        return selected


class OpportunityRecorder:
    """Transparent generator instrumentation; empty and zero pools remain visible."""
    def __init__(self, generator):
        self.generator, self.history = generator, []

    def generate(self, state, bag_id, tray_id, k=4):
        result = self.generator.generate(state, bag_id, tray_id, k=k)
        tray, bag = state.trays[tray_id], state.bags[bag_id]
        self.history.append({"time": state.now, "version": state.version, "bag_id": bag_id,
            "tray_id": tray_id, "source_node": tray.node, "at_destination": tray.node == bag.destination,
            "raw_candidate_count": len(result), "search_status": self.generator.last_search_status})
        return result

    def generate_empty(self, state, tray_id, destination, k=1):
        return self.generator.generate_empty(state, tray_id, destination, k=k)
