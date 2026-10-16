"""Validate native diagnostic spans without discounting the coarse native bound.

This is a phase-partition audit, not per-request certification. No unlabeled
native interval is inferred to be physics. One serial session/epoch per audit.
"""
from __future__ import annotations

from collections import Counter
import math


PHASES = ("native_call", "event_dispatch", "admission", "source_execution", "transfer_progress",
    "source_validate", "receiver_validate", "permission_validate", "reservation_commit",
    "physical_dispatch", "publication_delivery", "outcome_update", "ack_create", "ack_delivery",
    "timeout", "retry", "cancellation", "withdrawal", "recovery", "shared_scan", "observation",
    "serialization", "unclassified", "leg_creation")
METHODS = ("none", "submit_transfer", "submit_command", "query_transfer", "query_command",
    "observe_protocol", "observe_control", "observe_policy", "observe_policy_recent",
    "demand_signature", "planning_snapshots", "advance_notification", "advance_to", "result_at")
IDENTITIES = ("none", "transfer", "command", "leg", "job", "binding_submission",
    "route", "demand", "service_forecast", "planning_snapshot")
DIRECT_CONTROL_METHODS = set(METHODS[1:11])


def _uint(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _enum(value, names):
    if not _uint(value) or value >= len(names):
        raise ValueError("unknown_native_enum")
    return names[value]


def analyze_native_timing(batches, call_envelopes):
    """Conserve exclusive intervals, validate identities, and retain all remainder.

    Envelopes are measured by the Python native-call wrapper, before argument
    conversion through return. Submission/query envelope IDs are taken from its
    actual arguments. This function never supplies timing data to the policy.
    """
    report = {"schema": "g31.native_request_timing_audit.v1", "status": "unknown",
        "errors": [], "complete_request_100ms_certified": False,
        "physics_subtracted_ns": 0, "refined_per_request_totals_available": False}
    try:
        if not batches or not call_envelopes:
            raise ValueError("empty_native_capture")
        session = batches[0]["session_identity"]
        epoch = batches[0]["trace_epoch"]
        if not _uint(session) or session == 0 or not _uint(epoch) or epoch == 0:
            raise ValueError("invalid_session_epoch")
        rows, identities, seen_calls, previous_count, previous_span_count = {}, {}, set(), 0, 0
        for batch in batches:
            if (batch["schema"] != "g31.native_request_timing.v1" or
                batch["clock"] != "steady_clock_relative_nanoseconds" or
                batch["coverage"] != "known_control_phases_and_unclassified_remainder" or
                batch["physics_subtraction_authorized"] is not False or
                batch["session_identity"] != session or batch["trace_epoch"] != epoch or
                batch["errors"] != 0):
                raise ValueError("invalid_incomplete_or_mixed_epoch_capture")
            count = batch["completed_outer_calls"]
            emitted = batch["emitted_span_count"]
            if not _uint(count) or count < previous_count:
                raise ValueError("native_call_counter_reversed")
            if (not _uint(emitted) or emitted < previous_span_count or
                [row["span_id"] for row in batch["rows"]] != list(range(previous_span_count, emitted))):
                raise ValueError("missing_reordered_or_repeated_span_record")
            previous_span_count = emitted
            local_outer = set()
            for row in batch["rows"]:
                sid, parent = row["span_id"], row["parent_span_id"]
                if not _uint(sid) or sid in rows or not isinstance(parent, int) or isinstance(parent, bool) or parent < -1:
                    raise ValueError("duplicate_or_invalid_span_id")
                if row["trace_epoch"] != epoch or row["ended"] is not True or row["exception_exit"] is not False:
                    raise ValueError("incomplete_or_failed_native_span")
                if not all(_uint(row[k]) for k in ("start_ns", "end_ns", "call_ordinal", "event_sequence", "attempt")):
                    raise ValueError("invalid_native_time_or_counter")
                if row["end_ns"] < row["start_ns"] or row["call_ordinal"] == 0:
                    raise ValueError("reversed_native_interval")
                logical = row["logical_time"]
                if isinstance(logical, bool) or not isinstance(logical, (int, float)) or not math.isfinite(logical) or logical < 0:
                    raise ValueError("invalid_logical_time")
                _enum(row["phase"], PHASES); _enum(row["method"], METHODS)
                for kind_key, index_key in (("identity_kind", "identity_index"),
                                            ("related_identity_kind", "related_identity_index")):
                    kind, index = _enum(row[kind_key], IDENTITIES), row[index_key]
                    if not isinstance(index, int) or isinstance(index, bool) or (
                        index != -1 if kind in {"none", "binding_submission"} else index < 0):
                        raise ValueError("invalid_association_index")
                if parent == -1:
                    if row["phase"] != 0 or row["method"] == 0 or row["call_ordinal"] in local_outer:
                        raise ValueError("invalid_outer_native_call")
                    local_outer.add(row["call_ordinal"])
                rows[sid] = row
            if local_outer != set(range(previous_count+1, count+1)):
                raise ValueError("missing_or_repeated_outer_call")
            seen_calls.update(local_outer); previous_count = count
            for kind, key in (("transfer", "transfer_identities"), ("command", "command_identities"),
                              ("leg", "leg_identities"), ("job", "job_identities")):
                local_indices = set()
                for identity in batch[key]:
                    index = identity["index"]
                    if not _uint(index) or index in local_indices:
                        raise ValueError("duplicate_or_invalid_identity_table")
                    local_indices.add(index)
                    key_id = (kind, index)
                    # native_index can become known after initial admission;
                    # immutable IDs and all other identity fields cannot change.
                    old = identities.get(key_id)
                    if old is not None:
                        for k in set(old) | set(identity):
                            if k != "native_index" and old.get(k) != identity.get(k):
                                raise ValueError("mutated_native_identity")
                        if kind == "command" and old.get("native_index", -1) >= 0 and old["native_index"] != identity.get("native_index"):
                            raise ValueError("mutated_native_index")
                    identities[key_id] = identity
        envelopes = {}
        for envelope in call_envelopes:
            ordinal = envelope["call_ordinal"]
            if not _uint(ordinal) or ordinal in envelopes or envelope["session_identity"] != session or envelope["trace_epoch"] != epoch:
                raise ValueError("invalid_python_call_identity")
            if not _uint(envelope["start_ns"]) or not _uint(envelope["end_ns"]) or envelope["end_ns"] < envelope["start_ns"]:
                raise ValueError("invalid_python_envelope")
            method = _enum(envelope["method"], METHODS)
            if method in {"submit_transfer", "submit_command", "query_transfer", "query_command"}:
                if not isinstance(envelope.get("protocol_request_id"), str) or not envelope["protocol_request_id"]:
                    raise ValueError("missing_actual_argument_request_id")
            envelopes[ordinal] = envelope
        if set(envelopes) != seen_calls:
            raise ValueError("python_native_call_coverage_mismatch")
        ordered_envelopes = sorted(envelopes.values(), key=lambda e: e["call_ordinal"])
        if any(b["start_ns"] < a["end_ns"] for a, b in zip(ordered_envelopes, ordered_envelopes[1:])):
            raise ValueError("overlapping_python_native_calls")
        children, outer = {}, {}
        for sid, row in rows.items():
            parent = row["parent_span_id"]
            if parent == -1:
                outer[row["call_ordinal"]] = row
                if row["method"] != envelopes[row["call_ordinal"]]["method"]:
                    raise ValueError("native_method_mismatch")
            else:
                p = rows.get(parent)
                if p is None or p["call_ordinal"] != row["call_ordinal"] or not p["start_ns"] <= row["start_ns"] <= row["end_ns"] <= p["end_ns"]:
                    raise ValueError("missing_parent_or_child_outside_call")
                if parent >= sid:
                    raise ValueError("cyclic_or_noncausal_span_parent")
            children.setdefault(parent, []).append(row)
        for parent, group in children.items():
            ordered = sorted(group, key=lambda r: (r["start_ns"], r["end_ns"]))
            if any(b["start_ns"] < a["end_ns"] for a, b in zip(ordered, ordered[1:])):
                raise ValueError("overlapping_native_siblings")
        # Association validity is independent of elapsed time. Publication rows
        # resolve through command native_index; leg relations come from immutable
        # creation spans or a correctly guarded active-leg observation.
        leg_relations = {}
        publications = {}
        for (kind, _), identity in identities.items():
            if kind == "command" and identity.get("native_index", -1) >= 0:
                publication_kind = "service_forecast" if identity["kind"] == "withdraw_service_forecast" else identity["kind"]
                publications.setdefault((publication_kind, identity["native_index"]), []).append(identity["request_id"])
        for row in rows.values():
            if row["identity_kind"] == 3 and row["related_identity_kind"] in (1, 4):
                key = row["identity_index"]
                relation = (IDENTITIES[row["related_identity_kind"]], row["related_identity_index"])
                if key in leg_relations and leg_relations[key] != relation:
                    raise ValueError("conflicting_immutable_leg_relation")
                leg_relations[key] = relation
        def resolve(kind, index, call):
            if kind == "none": return []
            if kind == "binding_submission":
                value = envelopes[call].get("protocol_request_id")
                if not value: raise ValueError("unbound_rejected_submission")
                return [value]
            if kind in {"transfer", "command", "job", "leg"}:
                identity = identities.get((kind, index))
                if identity is None: raise ValueError("missing_native_identity")
                if kind == "job": return [identity["business_bag_id"]]
                if kind == "leg":
                    relation = leg_relations.get(index)
                    if relation is None and identity.get("job_index", -1) >= 0:
                        relation = ("job", identity["job_index"])
                    if relation is None: raise ValueError("missing_immutable_leg_relation")
                    return resolve(*relation, call)
                return [identity["request_id"]]
            matches = publications.get((kind, index), [])
            if not matches: raise ValueError("unresolved_publication_or_route_identity")
            return matches
        phase_ns = Counter(); identified = 0; native_remainder = 0; native_total = 0; python_remainder = 0
        association_count = 0
        for row in rows.values():
            for kind_key, index_key in (("identity_kind", "identity_index"), ("related_identity_kind", "related_identity_index")):
                resolved = resolve(IDENTITIES[row[kind_key]], row[index_key], row["call_ordinal"])
                if any(not isinstance(value, str) or not value for value in resolved):
                    raise ValueError("invalid_resolved_identity")
                association_count += bool(resolved)
            exclusive = row["end_ns"]-row["start_ns"] - sum(c["end_ns"]-c["start_ns"] for c in children.get(row["span_id"], []))
            phase = PHASES[row["phase"]]
            phase_ns[phase] += exclusive
            known = phase not in {"native_call", "event_dispatch", "unclassified"}
            if phase == "native_call" and METHODS[row["method"]] in DIRECT_CONTROL_METHODS:
                known = True
            if known: identified += exclusive
            else: native_remainder += exclusive
        for ordinal, row in outer.items():
            native = row["end_ns"]-row["start_ns"]
            python = envelopes[ordinal]["end_ns"]-envelopes[ordinal]["start_ns"]
            if native > python: raise ValueError("native_duration_exceeds_python_envelope")
            native_total += native; python_remainder += python-native
        if identified + native_remainder != native_total:
            raise ValueError("exclusive_partition_does_not_conserve")
        report.update(status="validated_partial_native_phase_partition", session_identity=session, trace_epoch=epoch,
            native_call_count=len(outer), span_count=len(rows), resolved_association_count=association_count,
            exclusive_ns_by_phase=dict(phase_ns), identified_control_bundle_ns=identified,
            unclassified_native_remainder_ns=native_remainder, python_binding_remainder_ns=python_remainder,
            unchanged_whole_native_envelope_ns=native_total+python_remainder,
            scope="Only a conserved phase decomposition. All native work and Python remainder remain charged; no physical work is subtracted and no per-business-request total is asserted.")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        report["errors"].append(str(exc))
    return report
