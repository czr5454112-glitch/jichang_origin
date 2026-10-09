"""Local routing-request owner and deterministic transport-accounting harness.

The only physical mutation is ExecutionValidator.commit. Synthetic message and
queue delays are accounting inputs, never measured network latency, and do not
advance the physical simulation tick. This is not distributed integration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from math import isfinite
from threading import RLock
from time import perf_counter

from .model import RouteCandidate, Snapshot, ValidationResult
from .routing import RegionalCandidateGenerator
from .runtime import INFINITY, ExecutionValidator, assert_invariants, capacity_conflict, effective_reservations, actual_action_key


OUTCOMES = ("new_route_success", "still_valid_old_route", "search_exhausted",
            "proven_infeasible", "communication_failure", "commit_failure", "local_processing_failure",
            "updated_route_success", "suffix_update_failed_old_route_kept")
REQUEST_INTENTS = frozenset({"ensure_route", "new_route", "keep_valid", "update_suffix"})


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class DependencySummary:
    version: int
    observed_tick: int
    topology_sha256: str
    resources_sha256: str
    control_partitions: tuple[str, ...]


def summarize(snapshot: Snapshot) -> DependencySummary:
    return DependencySummary(
        snapshot.version, snapshot.now, digest(asdict(snapshot.network)),
        digest({"trays": {key: asdict(value) for key, value in snapshot.trays.items()},
                "reservations": [asdict(slot) for slot in effective_reservations(snapshot)],
                "plans": {key: asdict(value) for key, value in snapshot.plans.items()},
                "module": asdict(snapshot.module), "bags": {key: asdict(value) for key, value in snapshot.bags.items()},
                "old_in_transit": [asdict(value) for value in snapshot.old_in_transit],
                "empty_targets": snapshot.empty_targets, "completed": snapshot.completed,
                "load_times": snapshot.load_times,
                "conditional_forecasts": {key: asdict(value) for key, value in snapshot.conditional_forecasts.items()},
                "replaceable_trays": sorted(snapshot.replaceable_trays)}),
        tuple(sorted({node.control_partition for node in snapshot.network.nodes.values()})),
    )


@dataclass(frozen=True)
class RouteRequest:
    request_id: str
    bag_id: str
    tray_id: str
    route_mode: str = "next_edge"
    max_attempts: int = 2
    candidate_count: int = 3
    # ensure_route preserves the legacy fallback behavior; an explicit update
    # is different from accepting a still-valid old itinerary as the answer.
    intent: str = "ensure_route"
    trigger_reason: str = "on_demand"

    def fingerprint(self) -> str:
        # Retransmission settings may vary without changing the requested action.
        return digest((self.bag_id, self.tray_id, self.route_mode, self.intent, self.trigger_reason))


@dataclass(frozen=True)
class AttemptFault:
    queue_ms: float = 0.0
    snapshot_message_ms: float = 0.0
    commit_message_ms: float = 0.0
    acknowledgement_ms: float = 0.0
    fail_snapshot: bool = False
    fail_commit_message: bool = False
    lose_acknowledgement: bool = False
    invalid_summary: bool = False
    stale_summary_before_delivery: bool = False
    invalidate_before_commit: bool = False

    def __post_init__(self):
        for name in ("queue_ms", "snapshot_message_ms", "commit_message_ms", "acknowledgement_ms"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError("Synthetic transport durations must be finite nonnegative values")


@dataclass(frozen=True)
class TransportScript:
    attempts: tuple[AttemptFault, ...] = ()
    repeat_last: bool = False

    def at(self, number: int) -> AttemptFault:
        if number < len(self.attempts):
            return self.attempts[number]
        return self.attempts[-1] if self.repeat_last and self.attempts else AttemptFault()


@dataclass(frozen=True)
class CommitReceipt:
    """Receipt for the validated witness; Snapshot.plans records the actual
    committed safe prefix or protected/full itinerary selected by route_mode.
    """
    request_id: str
    request_fingerprint: str
    candidate: RouteCandidate
    committed_version: int


@dataclass(frozen=True)
class RequestResult:
    request_id: str
    status: str
    reason: str
    attempts: int
    candidate_id: str | None
    owner_committed: bool  # A new-route receipt exists for THIS request_id.
    acknowledged: bool
    receipt_replayed: bool
    attempts_trace: tuple[dict, ...]
    timings: dict[str, float | None]
    proof: dict | None = None


def _covered(slots, resource, tray_id, start, end):
    if end <= start:
        return True
    cursor = start
    for slot in sorted((slot for slot in slots if slot.resource == resource and slot.tray_id == tray_id),
                       key=lambda slot: (slot.start, slot.end)):
        if slot.end <= cursor:
            continue
        if slot.start > cursor:
            return False
        cursor = max(cursor, slot.end)
        if cursor >= end:
            return True
    return end <= start


def validate_committed_full_route(snapshot: Snapshot, request: RouteRequest) -> ValidationResult:
    """Read-only fallback check of a real owner's remaining full commitment.

    A candidate from a cache, an entered prefix and an expired/completed route
    are not full-route fallbacks. Version drift alone does not invalidate an
    irrevocable route; its remaining physical and reservation evidence does.
    """
    plan = snapshot.plans.get(request.tray_id)
    if plan is None or plan.prefix_only or plan.bag_id != request.bag_id:
        return ValidationResult(False, "no_committed_full_old_route")
    tray, bag = snapshot.trays.get(request.tray_id), snapshot.bags.get(request.bag_id)
    if tray is None or bag is None or request.bag_id in snapshot.completed or tray.bag_id != request.bag_id:
        return ValidationResult(False, "old_route_identity_or_completion")
    try:
        assert_invariants(snapshot)
        node = snapshot.network.edges[plan.legs[0].edge_id].source if plan.legs else tray.node
        previous = None
        for leg in plan.legs:
            edge = snapshot.network.edges[leg.edge_id]
            if edge.source != node or leg.arrive != leg.depart + edge.travel_time or (previous is not None and leg.depart < previous):
                return ValidationResult(False, "old_route_path_or_timing")
            if previous is not None and leg.depart > previous and not snapshot.network.nodes[node].can_wait:
                return ValidationResult(False, "old_route_waiting_forbidden")
            node, previous = edge.target, leg.arrive
        arrival = plan.legs[-1].arrive if plan.legs else plan.unload_complete - snapshot.module.unload_ticks
        if (node != bag.destination or plan.unload_complete != arrival + snapshot.module.unload_ticks
                or plan.usable_at != plan.unload_complete + snapshot.module.hold_ticks(node)
                or (bag.protected and plan.unload_complete > bag.deadline)):
            return ValidationResult(False, "old_route_terminal_or_protection")
        remaining = [leg for leg in plan.legs if leg.arrive > snapshot.now]
        if remaining:
            first = remaining[0]
            source = snapshot.network.edges[first.edge_id].source
            if tray.node is None:
                if tray.mode != "in_transit" or not first.depart <= snapshot.now < first.arrive:
                    return ValidationResult(False, "old_route_entered_edge_mismatch")
            elif tray.node != source or first.depart < snapshot.now:
                return ValidationResult(False, "old_route_current_node_mismatch")
        elif tray.node != node or snapshot.now >= plan.unload_complete:
            return ValidationResult(False, "old_route_not_active")
        required = []
        for index, leg in enumerate(plan.legs):
            required.append((f"edge:{leg.edge_id}", max(snapshot.now, leg.depart), leg.arrive))
            if index:
                previous_leg = plan.legs[index - 1]
                wait_node = snapshot.network.edges[previous_leg.edge_id].target
                required.append((f"node:{wait_node}", max(snapshot.now, previous_leg.arrive), leg.depart))
        if remaining and tray.node is not None:
            required.append((f"node:{tray.node}", snapshot.now, remaining[0].depart))
        required.extend(((f"node:{node}", max(snapshot.now, arrival), INFINITY),
                         (f"reception:{node}", max(snapshot.now, arrival), plan.usable_at)))
        if not all(_covered(snapshot.reservations, resource, request.tray_id, start, end)
                   for resource, start, end in required):
            return ValidationResult(False, "old_route_missing_owned_reservation")
        conflict = capacity_conflict(snapshot, effective_reservations(snapshot))
        return ValidationResult(False, conflict) if conflict else ValidationResult(True, "committed_full_route_still_valid")
    except (AssertionError, KeyError, ValueError) as error:
        return ValidationResult(False, f"old_route_invalid:{type(error).__name__}")


class ResourceOwner:
    """One local owner, serialized observations and idempotent accepted receipts.

    External code must use this object to mutate its snapshot during a request.
    The existing validator remains the only route-commit implementation.
    """

    def __init__(self, snapshot: Snapshot):
        self._state = snapshot.clone()
        self._lock = RLock()
        self._validator = ExecutionValidator()
        self._receipts: dict[str, CommitReceipt] = {}
        self._request_fingerprints: dict[str, str] = {}

    def observe(self):
        with self._lock:
            visible = self._state.clone()
            return visible, summarize(visible)

    def snapshot(self):
        with self._lock:
            return self._state.clone()

    def observe_partition(self, partition):
        """Restricted API for future local planners; observe() is centralized."""
        from .partition_observation import observe_partition
        with self._lock:
            return observe_partition(self._state, partition)

    def register(self, request):
        with self._lock:
            known = self._request_fingerprints.setdefault(request.request_id, request.fingerprint())
            return known == request.fingerprint()

    def receipt(self, request):
        with self._lock:
            receipt = self._receipts.get(request.request_id)
            return receipt if receipt and receipt.request_fingerprint == request.fingerprint() else None

    def invalidate_version(self):
        """Synthetic dependency invalidation, not a cancellation or capacity edit."""
        with self._lock:
            self._state.version += 1

    def old_route(self, request):
        with self._lock:
            return validate_committed_full_route(self._state, request)

    def prepare_update(self, request, summary):
        with self._lock:
            if request.intent != "update_suffix":
                raise ValueError("replacement_requires_explicit_update_intent")
            if summarize(self._state) != summary:
                raise ValueError("stale_dependency_summary")
            context = self._validator.prepare_replacement(self._state, request.tray_id)
            if context.bag_id != request.bag_id:
                raise ValueError("request_action_identity_mismatch")
            return context

    def revalidate(self, candidate, request, summary, context=None):
        with self._lock:
            if request.intent not in REQUEST_INTENTS:
                return ValidationResult(False, "invalid_request_intent")
            if candidate.bag_id != request.bag_id or candidate.tray_id != request.tray_id:
                return ValidationResult(False, "request_action_identity_mismatch")
            current = summarize(self._state)
            if current != summary:
                return ValidationResult(False, "stale_dependency_summary")
            if request.intent == "update_suffix":
                if context is None:
                    return ValidationResult(False, "missing_replacement_context")
                return self._validator.validate_replacement(self._state, context, candidate,
                                                            route_mode=request.route_mode)
            if context is not None or request.intent == "keep_valid":
                return ValidationResult(False, "request_intent_disallows_commit")
            return self._validator.validate(self._state, candidate, route_mode=request.route_mode)

    def verify_static_proof(self, proof, summary):
        with self._lock:
            if summarize(self._state) != summary:
                return False
            return static_no_path(self._state, proof["source"], proof["destination"]) == proof

    def commit(self, candidate, request, context=None):
        with self._lock:
            if request.intent not in REQUEST_INTENTS:
                return ValidationResult(False, "invalid_request_intent"), None, False
            if candidate.bag_id != request.bag_id or candidate.tray_id != request.tray_id:
                return ValidationResult(False, "request_action_identity_mismatch"), None, False
            receipt = self.receipt(request)
            if receipt is not None:
                return ValidationResult(True, "accepted_receipt_replay"), receipt, True
            if not self.register(request):
                return ValidationResult(False, "request_id_collision"), None, False
            if request.intent == "update_suffix":
                if context is None:
                    return ValidationResult(False, "missing_replacement_context"), None, False
                result = self._validator.replace_suffix(self._state, context, candidate, route_mode=request.route_mode)
            elif context is not None or request.intent == "keep_valid":
                return ValidationResult(False, "request_intent_disallows_commit"), None, False
            else:
                result = self._validator.commit(self._state, candidate, route_mode=request.route_mode)
            if not result.accepted:
                return result, None, False
            receipt = CommitReceipt(request.request_id, request.fingerprint(), candidate, self._state.version)
            self._receipts[request.request_id] = receipt
            return result, receipt, False


def static_no_path(snapshot: Snapshot, source: str, destination: str):
    """Sound certificate only on the complete current directed physical graph."""
    if source not in snapshot.network.nodes or destination not in snapshot.network.nodes:
        return None
    reached, queue = {source}, [source]
    while queue:
        node = queue.pop()
        for edge in snapshot.network.edges.values():
            if edge.capacity > 0 and edge.source == node and edge.target not in reached:
                reached.add(edge.target)
                queue.append(edge.target)
    if destination in reached:
        return None
    return {"kind": "complete_directed_static_no_path", "source": source, "destination": destination,
            "reachable_cut": sorted(reached), "topology_sha256": digest(asdict(snapshot.network)),
            "dependency_version": snapshot.version}


def candidate_features(snapshot, candidate):
    return {"travel_ticks": sum(snapshot.network.edges[leg.edge_id].travel_time for leg in candidate.legs),
            "unload_complete": candidate.unload_complete, "usable_at": candidate.usable_at,
            "remaining_deadline": snapshot.bags[candidate.bag_id].deadline - candidate.unload_complete}


class RoutingRequestService:
    def __init__(self, owner: ResourceOwner, *, generator_factory=None, feature_builder=candidate_features, selector=None):
        self.owner = owner
        self.generator_factory = generator_factory or (lambda: RegionalCandidateGenerator(deadline_ms=None, dynamic_local=True))
        self.feature_builder = feature_builder
        self.selector = selector or (lambda snapshot, candidates, features: candidates[0])

    def handle(self, request: RouteRequest, transport: TransportScript = TransportScript()) -> RequestResult:
        started = perf_counter()
        progress = {}
        try:
            return self._handle(request, transport, progress)
        except Exception as error:
            # A broken local extension remains in the request denominator. It
            # is neither a network failure nor a proof of physical infeasibility.
            timing = progress.get("timing", {})
            trace = progress.get("trace", [])
            if trace:
                trace[-1]["events"].append(f"local_exception:{type(error).__name__}:{error}")
            receipt = self.owner.receipt(request)
            local_wall = (perf_counter() - started) * 1000
            core = sum(timing.get(key, 0.0) for key in ("snapshot_compute_ms", "generation_ms", "feature_ms", "score_ms",
                                                       "revalidation_ms", "commit_compute_ms", "proof_ms"))
            timing.update({"local_wall_ms": local_wall, "local_other_ms": max(0.0, local_wall - core),
                           "accounted_end_to_end_ms": local_wall + timing.get("simulated_queue_ms", 0.0)
                           + timing.get("simulated_communication_ms", 0.0), "actual_network_ms": None})
            return RequestResult(request.request_id, "local_processing_failure", f"{type(error).__name__}:{error}",
                                 len(trace), receipt.candidate.candidate_id if receipt else None,
                                 receipt is not None, False, False, tuple(trace), timing)

    def _handle(self, request, transport, progress) -> RequestResult:
        started = perf_counter()
        timing = {key: 0.0 for key in ("snapshot_compute_ms", "generation_ms", "feature_ms", "score_ms",
                                      "revalidation_ms", "commit_compute_ms", "proof_ms", "simulated_queue_ms",
                                      "simulated_communication_ms")}
        trace = []
        progress.update(timing=timing, trace=trace)
        selected = None
        final_status, final_reason = "commit_failure", "no_attempt"
        acked, replayed = False, False

        def measured(key, function, *args, **kwargs):
            begin = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                timing[key] += (perf_counter() - begin) * 1000

        def finish(status, reason, proof=None):
            receipt = self.owner.receipt(request)
            # Failed optimization may keep an old *currently valid* route, but
            # must never count as an update success or erase a lost-ack outcome.
            if (request.intent == "update_suffix" and receipt is None
                    and status in {"search_exhausted", "commit_failure", "proven_infeasible"}
                    and self.owner.old_route(request).accepted):
                status, reason = "suffix_update_failed_old_route_kept", reason
            local_wall = (perf_counter() - started) * 1000
            core = sum(timing[key] for key in ("snapshot_compute_ms", "generation_ms", "feature_ms", "score_ms",
                                              "revalidation_ms", "commit_compute_ms", "proof_ms"))
            timing.update({"local_wall_ms": local_wall, "local_other_ms": max(0.0, local_wall - core),
                           "accounted_end_to_end_ms": local_wall + timing["simulated_queue_ms"] + timing["simulated_communication_ms"],
                           "actual_network_ms": None})
            return RequestResult(request.request_id, status, reason, len(trace),
                                 receipt.candidate.candidate_id if receipt else selected.candidate_id if selected else None,
                                 receipt is not None, acked, replayed, tuple(trace), timing, proof)

        if (not request.request_id or request.route_mode not in {"whole_route", "next_edge"}
                or request.intent not in REQUEST_INTENTS
                or not isinstance(request.trigger_reason, str) or not request.trigger_reason
                or type(request.max_attempts) is not int or not 1 <= request.max_attempts <= 10
                or type(request.candidate_count) is not int or not 1 <= request.candidate_count <= 20):
            return finish("commit_failure", "invalid_request_parameters")
        if not self.owner.register(request):
            return finish("commit_failure", "request_id_collision")
        for attempt_index in range(request.max_attempts):
            fault = transport.at(attempt_index)
            row = {"attempt": attempt_index + 1, "events": [], "fault": asdict(fault),
                   "intent": request.intent, "trigger_reason": request.trigger_reason}
            trace.append(row)
            timing["simulated_queue_ms"] += fault.queue_ms
            timing["simulated_communication_ms"] += fault.snapshot_message_ms
            if fault.fail_snapshot:
                final_status, final_reason = "communication_failure", "snapshot_message_failed"
                row["events"].append(final_reason)
                continue
            observation, summary = measured("snapshot_compute_ms", self.owner.observe)
            if fault.invalid_summary:
                summary = replace(summary, control_partitions=summary.control_partitions + ("missing-owner-partition",))
            row["received_summary"] = asdict(summary)
            if summarize(observation) != summary:
                final_status, final_reason = "communication_failure", "invalid_dependency_summary"
                row["events"].append(final_reason)
                continue
            if fault.stale_summary_before_delivery:
                self.owner.invalidate_version()
                row["events"].append("synthetic_version_invalidated_after_snapshot")
            receipt = self.owner.receipt(request)
            if receipt is not None:
                replayed, acked = True, True
                row["events"].append("accepted_receipt_recovered")
                return finish("updated_route_success" if request.intent == "update_suffix" else "new_route_success",
                              "accepted_receipt_recovered")
            fallback = measured("revalidation_ms", self.owner.old_route, request)
            if fallback.accepted and request.intent in {"ensure_route", "keep_valid"}:
                selected = self.owner.snapshot().plans[request.tray_id]
                acked = True
                row["events"].append("committed_full_old_route_revalidated")
                return finish("still_valid_old_route", fallback.reason)
            if request.intent == "keep_valid":
                return finish("commit_failure", fallback.reason)
            context = None
            planning = observation
            if request.intent == "update_suffix":
                try:
                    context = measured("revalidation_ms", self.owner.prepare_update, request, summary)
                except ValueError as error:
                    final_status, final_reason = "commit_failure", str(error)
                    row["events"].append(final_reason)
                    if final_reason == "stale_dependency_summary":
                        continue
                    return finish(final_status, final_reason)
                planning = context.planning_snapshot
                row["replacement"] = {"anchor_node": context.anchor_node, "anchor_time": context.anchor_time,
                                      "frozen_legs": [asdict(leg) for leg in context.frozen_legs],
                                      "source_version": context.source_version,
                                      "old_plan": asdict(observation.plans[request.tray_id])}
            tray, bag = planning.trays.get(request.tray_id), planning.bags.get(request.bag_id)
            if (tray is None or bag is None or tray.bag_id != request.bag_id or tray.mode != "loaded"
                    or tray.node is None or request.tray_id in planning.plans):
                row["events"].append(fallback.reason)
                return finish("commit_failure", "request_not_updatable_without_revoking_commitment")
            proof = measured("proof_ms", static_no_path, planning, tray.node, bag.destination)
            if proof is not None:
                if measured("revalidation_ms", self.owner.verify_static_proof, proof, summary):
                    row["events"].append("static_no_path_proof_revalidated")
                    return finish("proven_infeasible", "complete_directed_static_no_path", proof)
                final_status, final_reason = "commit_failure", "stale_static_proof"
                row["events"].append(final_reason)
                continue
            row["processing_stage"] = "generation"
            generator = self.generator_factory()
            candidates = measured("generation_ms", generator.generate, planning.clone(), request.bag_id,
                                  request.tray_id, k=request.candidate_count)
            row["search_status"] = getattr(generator, "last_search_status", "unreported")
            row["expansions"] = getattr(generator, "last_expansions", None)
            validator = ExecutionValidator()
            valid = measured("revalidation_ms", lambda: tuple(candidate for candidate in candidates
                             if candidate.bag_id == request.bag_id and candidate.tray_id == request.tray_id
                             and validator.validate(planning, candidate, route_mode=request.route_mode).accepted))
            row["generated_count"], row["authorized_local_count"] = len(candidates), len(valid)
            # The conditionally retained remaining witness is part of the
            # intervention; discarded diagnostic candidate IDs are not.
            unique = {}
            for candidate in valid:
                unique.setdefault(actual_action_key(planning, candidate, route_mode=request.route_mode), candidate)
            row["actual_action_keys"] = list(unique)
            row["distinct_actual_actions"] = len(unique)
            valid = tuple(unique.values())
            if not valid:
                row["events"].append("bounded_search_returned_no_authorized_candidate")
                return finish("search_exhausted", "bounded_search_no_authorized_candidate_not_infeasibility")
            row["processing_stage"] = "features"
            # A future safe anchor is a reservation planning view, not a new
            # observation time. Prediction/scoring must not see publications
            # that arrive between the actual observation and that anchor.
            features = measured("feature_ms", lambda: tuple(self.feature_builder(observation.clone(), candidate) for candidate in valid))
            row["processing_stage"] = "scoring"
            chosen = measured("score_ms", self.selector, observation.clone(), valid, deepcopy(features))
            if chosen not in valid:
                row["events"].append("selector_outside_authorized_candidate_set")
                return finish("commit_failure", "selector_outside_authorized_candidate_set")
            selected = valid[valid.index(chosen)]
            row["processing_stage"] = "owner_revalidation"
            row["selected_candidate"] = asdict(selected)
            result = measured("revalidation_ms", self.owner.revalidate, selected, request, summary, context)
            row["events"].append(f"owner_revalidation:{result.reason}")
            if not result.accepted:
                final_status, final_reason = "commit_failure", result.reason
                continue
            timing["simulated_communication_ms"] += fault.commit_message_ms
            if fault.fail_commit_message:
                final_status, final_reason = "communication_failure", "commit_message_failed"
                row["events"].append(final_reason)
                continue
            if fault.invalidate_before_commit:
                self.owner.invalidate_version()
                row["events"].append("synthetic_version_invalidated_before_commit")
            row["processing_stage"] = "owner_commit"
            result, receipt, was_replayed = measured("commit_compute_ms", self.owner.commit, selected, request, context)
            row["events"].append(f"owner_commit:{result.reason}")
            if not result.accepted:
                final_status, final_reason = "commit_failure", result.reason
                continue
            timing["simulated_communication_ms"] += fault.acknowledgement_ms
            if fault.lose_acknowledgement:
                final_status, final_reason = "communication_failure", "commit_acknowledgement_lost_owner_committed"
                row["events"].append(final_reason)
                continue
            acked, replayed = True, was_replayed
            return finish("updated_route_success" if request.intent == "update_suffix" else "new_route_success", result.reason)
        return finish(final_status, final_reason)
