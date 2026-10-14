"""Actual loaded-decision cursors and role-stratified offline labels.

Only the continuation dispatcher is made resumable here. Physics, FIFO,
generation, authorization, costs and the existing controllers remain shared.
A checkpoint taken inside a loaded-route loop includes its pending candidates
and position, so restoring it never retries an earlier failed tray or repeats
the current tick's slow control. The online context contains no external tape
or controller object. All sampled futures below are offline evaluator inputs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from hashlib import sha256
import json
from time import perf_counter, process_time

from .label_stability import sampled_futures
from .learning import TimedAnalyticEvaluator
from .model import SimulationCheckpoint
from .phase4_control import ControlSpec, build_engine
from .role_features import physical_features
from .runtime import Simulation, actual_action_key, _destination


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass
class ControlCursor:
    stage_index: int = 0
    route_tray_ids: tuple | None = None
    route_index: int = 0
    pending_options: tuple | None = None
    pending_tray_id: str | None = None


@dataclass(frozen=True)
class VisibleDecisionContext:
    cursor: ControlCursor
    next_slow_trigger_at: int | None
    cache_contract: str | None = None


@dataclass
class CoverageCheckpoint:
    base: SimulationCheckpoint
    cursor: ControlCursor
    contract: dict = field(default_factory=dict)

    @property
    def state(self):
        return self.base.state

    @property
    def phase(self):
        return self.base.phase

    def clone(self):
        return deepcopy(self)


def _semantic(value):
    """Serialize one audit instance, excluding only fields ending in ``_ms``.

    Other runtime internals, including the generator's wall-clock ``_started``
    value and cache-dependent work counters, remain in this representation.
    It is not a stable semantic identity for independently collected states.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _semantic(v) for k, v in value.items() if not str(k).endswith("_ms")}
    if isinstance(value, (tuple, list)):
        return [_semantic(v) for v in value]
    if isinstance(value, set):
        return sorted((_semantic(v) for v in value), key=lambda x: json.dumps(x, sort_keys=True))
    if hasattr(value, "tolist"):
        return value.tolist()
    if is_dataclass(value):
        return {"class": type(value).__module__ + "." + type(value).__qualname__,
                "fields": _semantic({k: getattr(value, k) for k in value.__dataclass_fields__})}
    if hasattr(value, "__dict__"):
        return {"class": type(value).__module__ + "." + type(value).__qualname__, "fields": _semantic(vars(value))}
    raise TypeError("checkpoint contains unsupported semantic value: " + type(value).__qualname__)


def checkpoint_fingerprint(checkpoint):
    """Per-instance audit identity, not a cross-run semantic cache key.

    Includes the actual remaining tape and runtime internals; engine-only,
    never a policy input. Equal physical states can have different hashes.
    """
    return digest(_semantic(checkpoint))


class CursorSimulation(Simulation):
    """Exact routing program counter without changing the frozen base runtime."""
    @classmethod
    def from_base_checkpoint(cls, base, *, cursor=None, contract=None):
        engine = super().from_checkpoint(base)
        engine._cursor = deepcopy(cursor) if cursor is not None else ControlCursor()
        engine.control_contract = deepcopy(contract or {})
        engine._decision_callback = None
        engine._forced_choice = None
        return engine

    @classmethod
    def from_checkpoint(cls, checkpoint):
        if not isinstance(checkpoint, CoverageCheckpoint):
            raise TypeError("CursorSimulation requires a CoverageCheckpoint")
        return cls.from_base_checkpoint(checkpoint.base, cursor=checkpoint.cursor,
                                        contract=checkpoint.contract)

    @classmethod
    def from_visible(cls, snapshot, context, forecast_tape, spec, published_forecasts):
        """Public projection only: all forecast publications must be visible now.

        Caller supplies a synthetic forecast tape, not a hidden engine tape.
        The fixed built-in controller is reconstructed deliberately as an online
        model, while the exact current decision cursor and slow clock are kept.
        This is not represented as a replay of the true engine checkpoint.
        """
        published = tuple(published_forecasts)
        if any(f.published_at > snapshot.now for f in published):
            raise ValueError("online projection cannot receive unpublished forecasts")
        if spec.routing == "external":
            raise ValueError("public projection requires a fixed built-in continuation")
        baseline = build_engine(snapshot, published, tuple(forecast_tape), spec)
        if getattr(context, "cache_contract", None) is not None:
            from .routing_cache_contract import CACHE_CONTRACT, enable_replay_cache
            if context.cache_contract != CACHE_CONTRACT:
                raise ValueError("Unknown public projection cache contract")
            enable_replay_cache(baseline)
        if baseline.slow_controller is not None:
            if context.next_slow_trigger_at is None:
                raise ValueError("missing visible slow clock phase")
            baseline.slow_controller.next_trigger_at = context.next_slow_trigger_at
        elif context.next_slow_trigger_at is not None:
            raise ValueError("slow-controller contract mismatch")
        checkpoint = baseline.checkpoint()
        checkpoint.phase = "routes"
        return cls.from_base_checkpoint(checkpoint, cursor=context.cursor,
                                        contract=baseline.control_contract)

    def checkpoint(self):
        if self._forced_choice is not None:
            raise ValueError("consume the pending forced choice before checkpointing")
        return CoverageCheckpoint(super().checkpoint(), deepcopy(self._cursor), deepcopy(self.control_contract))

    def visible_decision_context(self):
        if self._cursor.pending_options is None:
            raise ValueError("context is available only at an actual loaded decision")
        slow = self.slow_controller
        if slow is not None and not hasattr(slow, "next_trigger_at"):
            raise ValueError("slow controller must expose its deterministic trigger phase")
        generator = self._generator
        seen = set()
        while id(generator) not in seen and not hasattr(generator, "cache_contract"):
            seen.add(id(generator))
            generator = getattr(generator, "generator", getattr(generator, "inner", None))
            if generator is None:
                break
        return VisibleDecisionContext(deepcopy(self._cursor), None if slow is None else slow.next_trigger_at,
                                      getattr(generator, "cache_contract", None))

    def choose_pending(self, candidate):
        if self._cursor.pending_options is None or candidate not in self._cursor.pending_options:
            raise ValueError("choice must belong to this exact pending decision")
        if self._forced_choice is not None:
            raise ValueError("pending choice is already set")
        self._forced_choice = candidate

    def _stages(self):
        return (("protected", "soft", "empty", "slow", "reactive")
                if self.coordination_order == "route_then_prebalance" else
                ("protected", "slow", "empty", "soft", "reactive"))

    def _attach_context(self):
        selector, seen = self.route_selector, set()
        while selector is not None and id(selector) not in seen:
            seen.add(id(selector))
            if hasattr(selector, "set_decision_context"):
                selector.set_decision_context(self.visible_decision_context())
                return
            selector = getattr(selector, "selector", None)

    def _resume_loaded(self, protected):
        cursor = self._cursor
        if cursor.route_tray_ids is None:
            cursor.route_tray_ids = tuple(sorted(self.state.trays))
            cursor.route_index = 0
        while cursor.route_index < len(cursor.route_tray_ids):
            tray = self.state.trays[cursor.route_tray_ids[cursor.route_index]]
            if cursor.pending_options is None:
                if (tray.mode != "loaded" or tray.tray_id in self.state.plans
                        or self.state.bags[tray.bag_id].protected != protected):
                    cursor.route_index += 1
                    continue
                cursor.pending_options = self._generate(tray)
                cursor.pending_tray_id = tray.tray_id
                # Every actual generation attempt is in the denominator,
                # including zero options for which the selector is not invoked.
                if self._decision_callback is not None:
                    self._decision_callback(self, tray, cursor.pending_options)
            options = cursor.pending_options
            if options:
                self._attach_context()
                if self._forced_choice is None:
                    chosen = self._select(options)
                else:
                    chosen, self._forced_choice = self._forced_choice, None
                    # This action replaces exactly the current selector call.
                    # Subsequent calls use the checkpointed continuation.
                verdict = self._commit(chosen, "route_commit")
                assert verdict.accepted, verdict.reason
            elif protected:
                self.policy_stats["protected_unadmitted_decisions"] += 1
            cursor.pending_options, cursor.pending_tray_id = None, None
            cursor.route_index += 1
        cursor.route_tray_ids, cursor.route_index = None, 0

    def _resume_empty(self):
        for tray_id, destination in sorted(tuple(self.state.empty_targets.items())):
            tray = self.state.trays[tray_id]
            if tray_id in self.state.plans or tray.mode != "empty":
                continue
            if tray.node == destination:
                del self.state.empty_targets[tray_id]
                continue
            options = self._generate(tray, destination)
            if options:
                verdict = self._commit(options[0], "empty_continue")
                assert verdict.accepted, verdict.reason

    def _resume_reactive(self):
        if not self.reactive_empty_dispatch:
            return
        reserved = defaultdict(int)
        for plan in self.state.plans.values():
            if plan.bag_id is None:
                reserved[plan.continuation_destination or _destination(self.state, plan)] += 1
        for tray_id, destination in self.state.empty_targets.items():
            if tray_id not in self.state.plans:
                reserved[destination] += 1
        for bag in self._waiting():
            if reserved[bag.origin]:
                reserved[bag.origin] -= 1
                continue
            choices = []
            for tray in sorted(self.state.trays.values(), key=lambda t: t.tray_id):
                if (tray.mode != "empty" or tray.node == bag.origin or tray.tray_id in self.state.plans
                        or tray.tray_id in self.state.empty_targets):
                    continue
                options = self._generate(tray, bag.origin)
                if options:
                    choices.append(options[0])
            if choices:
                chosen = min(choices, key=lambda p: (p.usable_at, p.tray_id))
                verdict = self._commit(chosen, "empty_dispatch", visible_bag_id=bag.bag_id)
                assert verdict.accepted, verdict.reason

    def _continue_causally(self):
        self._prepare_routes()
        if self.control_mode == "external":
            return
        stages = self._stages()
        while self._cursor.stage_index < len(stages):
            stage = stages[self._cursor.stage_index]
            if stage in {"protected", "soft"}:
                self._resume_loaded(stage == "protected")
            elif stage == "empty":
                self._resume_empty()
            elif stage == "slow":
                self._run_slow_controller()
            else:
                self._resume_reactive()
            self._cursor.stage_index += 1
        self._cursor = ControlCursor()


@dataclass(frozen=True)
class RoleQuota:
    bands: tuple = (0, 20, 40)
    nodes: tuple = ("S", "B", "C", "G")
    roles: tuple = ("origin", "continuation", "arrival_at_destination")
    per_cell: int = 1
    max_samples: int | None = None
    selection_rule: str = "chronological"

    def __post_init__(self):
        if (not self.bands or tuple(sorted(set(self.bands))) != self.bands
                or any(type(b) is not int or b < 0 for b in self.bands)):
            raise ValueError("bands must be sorted unique nonnegative integer starts")
        if type(self.per_cell) is not int or self.per_cell < 1:
            raise ValueError("per_cell must be positive integer")
        if self.max_samples is not None and (type(self.max_samples) is not int or self.max_samples < 1):
            raise ValueError("max_samples must be None or positive integer")
        if self.selection_rule not in {"chronological", "node_role_round_robin"}:
            raise ValueError("unknown quota selection rule")


@dataclass
class CoverageCollection:
    samples: list
    opportunities: list
    episode_result: object
    contract: dict
    metadata: dict


def collect_role_decisions(scene, spec, *, quota=RoleQuota(), route_selector=None,
                           selector_manifest=None, source_group=None, cache_contract=None):
    """First attempts per declared node/role/band; no labels or outcomes used.

    Zero-option attempts can consume a quota cell. They are kept as unlabelable
    samples, never silently replaced by a later successful opportunity.
    """
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec,
                        route_selector=route_selector, selector_manifest=selector_manifest)
    if cache_contract is not None:
        from .routing_cache_contract import CACHE_CONTRACT, enable_replay_cache
        if cache_contract != CACHE_CONTRACT:
            raise ValueError("Unknown collection cache contract")
        enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    sampled, history, counts = [], [], Counter()
    policy_sha = digest(base.control_contract["continuation"]["selector"])
    def record(current, tray, options):
        state, bag = current.state, current.state.bags[tray.bag_id]
        node = tray.node
        role = ("arrival_at_destination" if node == bag.destination else "origin" if node == bag.origin else "continuation")
        # Counts physical arrivals at this node since the current bag was loaded,
        # rather than repeated attempts while sitting on an unavailable route.
        load_index = max((i for i, e in enumerate(current._trace) if e.get("event") == "load"
                          and e.get("bag_id") == bag.bag_id and e.get("tray_id") == tray.tray_id), default=-1)
        arrivals = sum(e.get("event") == "prefix_arrive" and e.get("tray_id") == tray.tray_id
                       and e.get("node") == node for e in current._trace[load_index + 1:])
        revisited = arrivals >= (1 if node == bag.origin else 2)
        band = max((b for b in quota.bands if b <= state.now), default=None)
        unique, keys, seen = [], [], set()
        for candidate in options:
            key = actual_action_key(state, candidate, route_mode=spec.route_mode)
            if key not in seen:
                unique.append(candidate)
                keys.append(key)
                seen.add(key)
        identity = f"{scene.name}:{source_group or spec.routing}:d{len(history)}:t{state.now}:{bag.bag_id}:{node}"
        cell = (node, role, band)
        accepted = (node in quota.nodes and role in quota.roles and band is not None and not bag.protected
                    and counts[cell] < quota.per_cell and (quota.selection_rule == "node_role_round_robin"
                         or quota.max_samples is None or len(sampled) < quota.max_samples))
        row = {"identity": identity, "time": state.now, "version": state.version, "source_node": node,
               "role": role, "revisit": revisited, "band": band, "bag_id": bag.bag_id, "tray_id": tray.tray_id,
               "protected": bag.protected, "raw_candidate_count": len(options), "candidate_count": len(unique),
               "candidate_stratum": "zero" if not unique else "single" if len(unique) == 1 else "multiple",
               "selector_called": bool(options), "state_sha256": digest(asdict(state)), "sampled": accepted,
               "search_status": getattr(current._generator, "last_search_status", None),
               "search_work": getattr(current._generator, "last_expansions", None),
               "cursor": asdict(current._cursor), "next_slow_trigger_at": current.visible_decision_context().next_slow_trigger_at}
        if accepted:
            checkpoint = current.checkpoint()
            published = tuple(f for f in scene.forecasts if f.published_at <= state.now)
            evaluator = TimedAnalyticEvaluator(state.now + spec.planning_horizon, published)
            sampled.append({**row, "checkpoint": checkpoint, "checkpoint_sha256": checkpoint_fingerprint(checkpoint),
                            "pool": tuple(unique), "normal_keys": tuple(keys),
                            "features": tuple(evaluator.features(state, p) for p in unique),
                            "features_physical": tuple(physical_features(state, p, state.now + spec.planning_horizon,
                                                                          published, route_mode=spec.route_mode) for p in unique),
                            "policy_sha": policy_sha, "continuation_contract": deepcopy(current.control_contract)})
            if cache_contract is not None:
                from .routing_cache_contract import routing_cache_state
                cache_state = routing_cache_state(current)
                sampled[-1]["routing_cache_checkpoint"] = {
                    "schema": cache_state["schema"], "fast_cache_sha256": cache_state["fast_cache_sha256"],
                    "fast_generator_config": cache_state["fast_generator_config"],
                    "checkpoint_owner": cache_state["checkpoint_owner"]}
            counts[cell] += 1
        history.append(row)
    engine._decision_callback = record
    started, cpu = perf_counter(), process_time()
    result = engine.advance(scene.horizon)
    eligible_sample_count = len(sampled)
    if quota.selection_rule == "node_role_round_robin" and quota.max_samples is not None:
        buckets = {(node, role): sorted((s for s in sampled if s["source_node"] == node and s["role"] == role),
                                        key=lambda s: (s["band"], s["time"], s["identity"]))
                   for node in quota.nodes for role in quota.roles}
        chosen = []
        while len(chosen) < quota.max_samples and any(buckets.values()):
            for bucket in buckets.values():
                if bucket and len(chosen) < quota.max_samples:
                    chosen.append(bucket.pop(0))
        selected_ids = {s["identity"] for s in chosen}
        for row in history:
            row["sampled"] = row["identity"] in selected_ids
        sampled = chosen
    selected_counts = Counter((s["source_node"], s["role"], s["band"]) for s in sampled)
    metadata = {"quota": asdict(quota), "policy_sha": policy_sha, "source_group": source_group,
                "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu,
                "sampling_inputs": "actual observed role/node/time, authorization count and prior quota usage only",
                "opportunities": len(history), "samples": len(sampled),
                "eligible_quota_cells_before_total_cap": eligible_sample_count,
                "candidate_denominator": dict(Counter(r["candidate_stratum"] for r in history)),
                "observed_nodes": dict(Counter(r["source_node"] for r in history)),
                "sampled_cells": [{"node": k[0], "role": k[1], "band": k[2], "count": v} for k, v in sorted(selected_counts.items())],
                "empty_nodes": [node for node in quota.nodes if not any(r["source_node"] == node for r in history)],
                "empty_declared_cells": [{"node": node, "role": role, "band": band}
                    for node in quota.nodes for role in quota.roles for band in quota.bands
                    if not any(r["source_node"] == node and r["role"] == role and r["band"] == band for r in history)],
                "route_history": deepcopy(getattr(engine.route_selector, "history", [])),
                "selector_history": deepcopy(getattr(getattr(engine.route_selector, "selector", None), "history", [])),
                "slow_history": deepcopy(getattr(engine.slow_controller, "history", [])),
                "slow_trigger_times": deepcopy(getattr(engine.slow_controller, "trigger_times", [])),
                "slow_next_trigger_at": getattr(engine.slow_controller, "next_trigger_at", None)}
    if cache_contract is not None:
        metadata["routing_cache_contract"] = cache_contract
    return CoverageCollection(sampled, history, result, deepcopy(engine.control_contract), metadata)


def sample_artifact(sample):
    """Serializable evidence; the live exact checkpoint is intentionally private."""
    checkpoint = sample["checkpoint"]
    fields = {key: value for key, value in sample.items() if key not in {"checkpoint", "pool"}}
    fields.update(state=asdict(checkpoint.state), proposals=[asdict(p) for p in sample["pool"]],
                  checkpoint_metadata={"phase": checkpoint.phase, "cursor": asdict(checkpoint.cursor),
                     "accrued_cost": checkpoint.base.cost_components,
                     "next_slow_trigger_at": getattr(checkpoint.base.slow_controller, "next_trigger_at", None),
                     "slow_trigger_times": getattr(checkpoint.base.slow_controller, "trigger_times", []),
                     "exact_checkpoint_scope": "base physical ledger, private tape, actual controllers, loaded-route cursor; never supplied to policy"})
    return fields


def branch_role_decision(checkpoint, candidate, future, horizon, *, continuation_selector=None,
                         selector_manifest=None):
    """Offline intervention at the exact pending selector position."""
    if not isinstance(checkpoint, CoverageCheckpoint) or checkpoint.cursor.pending_options is None:
        raise ValueError("need an exact pending-decision checkpoint")
    if horizon <= checkpoint.state.now:
        raise ValueError("label horizon must follow the decision tick")
    identifiers = [b.bag_id for b in future]
    if len(set(identifiers)) != len(identifiers) or any(
            b.arrival <= checkpoint.state.now or b.bag_id in checkpoint.state.bags for b in future):
        raise ValueError("future must contain unique unobserved later tasks")
    restored = checkpoint.clone()
    restored.base.pending_arrivals = defaultdict(list)
    for bag in future:
        restored.base.pending_arrivals[bag.arrival].append(bag)
    if (continuation_selector is None) != (selector_manifest is None):
        raise ValueError("selector replacement requires an explicit manifest")
    if continuation_selector is not None:
        restored.base.route_selector = deepcopy(continuation_selector)
    engine = CursorSimulation.from_checkpoint(restored)
    engine.choose_pending(candidate)
    return engine.advance(horizon)


def label_role_decision(sample, nominal_future, *, groups=4, futures_per_group=8, horizon_ticks=None,
                        regime="stress", continuation_selector=None, selector_manifest=None):
    """K4 paired common-future labels, separate nominal and stress regimes."""
    if any(type(v) is not int or v < 1 for v in (groups, futures_per_group)):
        raise ValueError("positive integer group/future counts required")
    if regime not in {"nominal", "stress"}:
        raise ValueError("regime must be nominal or stress")
    checkpoint, pool = sample["checkpoint"], sample["pool"]
    horizon_ticks = sample["continuation_contract"]["spec"]["planning_horizon"] if horizon_ticks is None else horizon_ticks
    if horizon_ticks != sample["continuation_contract"]["spec"]["planning_horizon"]:
        raise ValueError("label horizon must equal the declared planning horizon")
    groups, futures_per_group = (1, 1) if regime == "nominal" else (groups, futures_per_group)
    future_groups, costs, branches, failures = [], [], [], []
    state = checkpoint.state
    started, cpu = perf_counter(), process_time()
    for group in range(groups):
        seed = int(digest([sample["identity"], "role_coverage_future", group])[:16], 16)
        futures = ((tuple(b for b in nominal_future if b.bag_id not in state.bags and b.arrival > state.now),)
                   if regime == "nominal" else sampled_futures(nominal_future, state, count=futures_per_group, seed=seed))
        future_groups.append({"seed": seed, "tapes": [[asdict(b) for b in tape] for tape in futures]})
        candidate_costs = []
        for c, candidate in enumerate(pool):
            values = []
            for f, future in enumerate(futures):
                branch = {"group": group, "candidate": c, "future_index": f, "future_sha256": digest([asdict(b) for b in future])}
                try:
                    outcome = branch_role_decision(checkpoint, candidate, future, state.now + horizon_ticks,
                        continuation_selector=continuation_selector, selector_manifest=selector_manifest)
                    values.append(outcome.total_cost)
                    branch.update(total_cost=outcome.total_cost, cost_components=outcome.cost_components,
                                  completed=outcome.completed, uncompleted=outcome.uncompleted_bag_ids,
                                  invariant_checks=outcome.invariant_checks, failed=False)
                except (ValueError, AssertionError) as exc:
                    values.append(None)
                    branch.update(failed=True, error=type(exc).__name__, reason=str(exc))
                    failures.append(branch)
                branches.append(branch)
            candidate_costs.append(values)
        costs.append(candidate_costs)
    return {"identity": sample["identity"], "regime": regime, "horizon_ticks": horizon_ticks,
            "groups": groups, "futures_per_group": futures_per_group, "candidate_count": len(pool),
            "checkpoint_sha256": sample["checkpoint_sha256"], "state": asdict(state),
            "source_node": sample["source_node"], "role": sample["role"], "band": sample["band"],
            "actual_action_keys": list(sample["normal_keys"]), "proposals": [asdict(p) for p in pool],
            "features_observable_only": sample["features"], "future_groups_offline_only": future_groups,
            "features_physical": sample["features_physical"],
            "paired_costs": costs, "raw_branches": branches, "failures": failures,
            "sampled_policy_sha": sample["policy_sha"], "continuation_override": selector_manifest,
            "source_continuation_contract": sample["continuation_contract"],
            "zero_candidate_preserved": not pool, "wall_seconds": perf_counter() - started,
            "cpu_seconds": process_time() - cpu}
