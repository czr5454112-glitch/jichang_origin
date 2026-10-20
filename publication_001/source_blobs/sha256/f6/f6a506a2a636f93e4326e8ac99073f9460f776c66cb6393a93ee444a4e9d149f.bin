"""Fail-closed accounting for a proposed serial request event ledger.

This module does not instrument the native/controller implementation. A ledger
must cover its service windows with nested monotonic-clock spans. Known control
work is charged in full to every dependent root, without averaging. Root IDs
precede observation/solve, so no-action decisions remain in the denominator.
"""
from __future__ import annotations

from collections import Counter
import math


SCHEMA = "g31.request_event_ledger.v1"
BUDGET_NS = 100_000_000
ROOT_PHASES = ("observe", "preprocess", "predict", "candidate", "solve", "fallback", "submit", "serialize")
MESSAGE_PHASES = ("serialize", "submit", "source_validate", "receiver_validate", "commit", "ack", "retry")
CLASSES = {"control", "physics", "wait", "diagnostic", "unclassified"}
TERMINAL_ROOT = {"completed", "no_action", "fallback", "rejected", "failed", "expired"}
TERMINAL_MESSAGE = {"received", "delivered", "updated", "withdrawn", "cancelled", "rejected", "failed", "expired"}


def _ns(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _union(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def analyze_ledger(ledger: dict) -> dict:
    """Validate, partition nested spans, and account the declared request domain.

    Work classes are instrumentation assertions, not inferred from function
    names. A complete measurement is not a hard-real-time or business-per-job
    certificate. V1 intentionally accepts only one execution lane/clock.
    """
    roots = ledger.get("requests", [])
    result = {"schema": "g31.request_event_accounting.v1", "status": "unknown",
        "request_count": len(roots) if isinstance(roots, list) else None,
        "budget_ns": BUDGET_NS, "requests": [], "errors": [],
        "all_observed_requests_within_100ms": None,
        "complete_business_requirement_certified": False,
        "hard_realtime_guarantee": False,
        "attribution_rule": "Full dependent shared work per root, exclusive nesting, no averaging; elapsed wall clock rather than CPU-only time.",
        "scope": "Measured serial requests in the declared domain; owner activations are not automatically per-job business update requests."}
    errors = result["errors"]
    try:
        if ledger["schema"] != SCHEMA or ledger["clock"] != "monotonic_ns" or ledger["execution_lanes"] != 1:
            raise ValueError("unsupported_schema_clock_or_parallel_execution")
        scope = ledger["request_scope"]
        if scope not in {"owner_activation_updates", "explicit_business_updates"}:
            raise ValueError("undeclared_request_scope")
        result["request_scope"] = scope
        if ledger.get("coverage_complete") is not True:
            errors.append("instrumentation_coverage_not_complete")
        windows = ledger["service_windows"]
        if not windows:
            raise ValueError("missing_service_windows")
        for window in windows:
            if not all(_ns(window[k]) for k in ("start_ns", "end_ns")) or window["end_ns"] < window["start_ns"]:
                raise ValueError("invalid_service_window")
        window_intervals = sorted((w["start_ns"], w["end_ns"]) for w in windows)
        if any(b[0] < a[1] for a, b in zip(window_intervals, window_intervals[1:])):
            raise ValueError("overlapping_service_windows")
        by_root = {}
        for root in roots:
            rid = root["request_id"]
            if not isinstance(rid, str) or not rid or rid in by_root:
                raise ValueError("duplicate_or_invalid_root_identity")
            if not _ns(root["opened_ns"]):
                raise ValueError("invalid_root_open_time")
            closed = root.get("closed_ns")
            if closed is not None and (not _ns(closed) or closed < root["opened_ns"]):
                raise ValueError("invalid_root_close_time")
            if root["status"] in TERMINAL_ROOT and closed is None:
                raise ValueError("terminal_root_without_close")
            if root["status"] not in TERMINAL_ROOT | {"open", "unknown"}:
                raise ValueError("invalid_root_status")
            if root["status"] not in TERMINAL_ROOT and closed is not None:
                raise ValueError("nonterminal_root_with_close")
            if not isinstance(root.get("business_job_ids"), list):
                raise ValueError("missing_explicit_business_job_association")
            by_root[rid] = root
        messages = {}
        for message in ledger["messages"]:
            mid = message["request_id"]
            if not isinstance(mid, str) or not mid or mid in messages:
                raise ValueError("duplicate_or_invalid_message_identity")
            deps = message["root_request_ids"]
            if not deps or len(set(deps)) != len(deps) or not set(deps) <= set(by_root):
                raise ValueError("invalid_message_root_dependencies")
            messages[mid] = message
        spans = {}
        children = {}
        top = []
        for span in ledger["spans"]:
            sid = span["span_id"]
            if not isinstance(sid, str) or not sid or sid in spans:
                raise ValueError("duplicate_or_invalid_span_identity")
            if not all(_ns(span[k]) for k in ("start_ns", "end_ns")) or span["end_ns"] < span["start_ns"]:
                raise ValueError("invalid_span_interval")
            if span["work_class"] not in CLASSES or not isinstance(span["phase"], str):
                raise ValueError("invalid_span_class_or_phase")
            deps = span["root_request_ids"]
            if len(set(deps)) != len(deps) or not set(deps) <= set(by_root):
                raise ValueError("invalid_span_root_dependencies")
            mid = span.get("protocol_request_id")
            if mid is not None and mid not in messages:
                raise ValueError("unknown_protocol_request_identity")
            spans[sid] = span
            parent = span.get("parent_span_id")
            children.setdefault(parent, []).append(sid)
            if parent is None:
                top.append(sid)
        for sid, span in spans.items():
            parent = span.get("parent_span_id")
            if parent is not None:
                if parent not in spans:
                    raise ValueError("missing_parent_span")
                p = spans[parent]
                if not p["start_ns"] <= span["start_ns"] <= span["end_ns"] <= p["end_ns"]:
                    raise ValueError("child_outside_parent")
        for siblings in children.values():
            ordered = sorted((spans[s]["start_ns"], spans[s]["end_ns"]) for s in siblings)
            if any(b[0] < a[1] for a, b in zip(ordered, ordered[1:])):
                raise ValueError("overlapping_serial_sibling_spans")
        if _union([(spans[s]["start_ns"], spans[s]["end_ns"]) for s in top]) != _union(window_intervals):
            errors.append("service_window_gap_or_extra_span")
        pieces = []
        observed_phases = {rid: set() for rid in by_root}
        message_phases = {mid: set() for mid in messages}
        visited = set()

        def visit(sid, inherited):
            if sid in visited:
                raise ValueError("span_cycle_or_multiple_visit")
            visited.add(sid)
            s = spans[sid]
            deps = set(s["root_request_ids"]) | inherited
            mid = s.get("protocol_request_id")
            if mid is not None:
                if not set(messages[mid]["root_request_ids"]) <= deps:
                    raise ValueError("message_span_omits_dependent_root")
                if s["work_class"] == "control":
                    message_phases[mid].add(s["phase"])
            for rid in deps:
                root = by_root[rid]
                if s["start_ns"] < root["opened_ns"] or (root.get("closed_ns") is not None and s["end_ns"] > root["closed_ns"]):
                    raise ValueError("charged_span_outside_request_lifetime")
                if s["work_class"] == "control":
                    observed_phases[rid].add(s["phase"])
            cursor = s["start_ns"]
            for child in sorted(children.get(sid, []), key=lambda k: (spans[k]["start_ns"], spans[k]["end_ns"])):
                c = spans[child]
                if c["start_ns"] > cursor:
                    pieces.append((cursor, c["start_ns"], s, deps))
                visit(child, deps)
                cursor = c["end_ns"]
            if s["end_ns"] > cursor:
                pieces.append((cursor, s["end_ns"], s, deps))
        for sid in sorted(top, key=lambda k: spans[k]["start_ns"]):
            visit(sid, set())
        if visited != set(spans):
            raise ValueError("unreachable_or_cyclic_spans")
        if not roots:
            errors.append("empty_request_denominator")
        counts = Counter()
        by_request = {rid: [] for rid in by_root}
        for start, end, s, deps in pieces:
            counts[s["work_class"]] += end - start
            if s["work_class"] == "control" and not deps:
                errors.append("unattributed_control_work:" + s["span_id"])
            if s["work_class"] == "unclassified":
                errors.append("unclassified_work:" + s["span_id"])
            if s["work_class"] in {"physics", "wait", "diagnostic"} and not s.get("exclusion_reason"):
                errors.append("missing_exclusion_reason:" + s["span_id"])
            for rid in deps:
                by_request[rid].append((start, end, s))

        def phase_check(label, declarations, required, measured):
            if set(declarations) != set(required):
                errors.append("incomplete_phase_declaration:" + label)
            for phase in required:
                disposition = declarations.get(phase)
                if disposition == "measured":
                    if phase not in measured:
                        errors.append("declared_phase_not_measured:" + label + ":" + phase)
                elif isinstance(disposition, dict) and isinstance(disposition.get("not_applicable"), str) and disposition["not_applicable"].strip():
                    if phase in measured:
                        errors.append("measured_phase_marked_not_applicable:" + label + ":" + phase)
                else:
                    errors.append("unknown_phase_coverage:" + label + ":" + phase)
        for rid, root in by_root.items():
            phase_check(rid, root["phase_coverage"], ROOT_PHASES, observed_phases[rid])
            if not observed_phases[rid]:
                errors.append("root_without_control_measurement:" + rid)
        for mid, message in messages.items():
            phase_check(mid, message["phase_coverage"], MESSAGE_PHASES, message_phases[mid])
            # Even a rejected message was serialized and submitted. A terminal
            # transport outcome also needs its ACK processing; an immediate
            # submission rejection is the explicit exception to that last step.
            mandatory = {"serialize", "submit"}
            if not (message["status"] == "rejected" and message.get("immediate_submission_rejection") is True):
                mandatory.add("ack")
            for phase in mandatory - message_phases[mid]:
                errors.append("mandatory_message_phase_unmeasured:" + mid + ":" + phase)
            if message["status"] not in TERMINAL_MESSAGE:
                errors.append("open_or_unknown_protocol_request:" + mid)
        for rid, root in by_root.items():
            intervals = [(a, b) for a, b, s in by_request[rid] if s["work_class"] == "control"]
            merged = _union(intervals)
            compute = sum(b - a for a, b in merged)
            # Single-lane disjoint exclusive pieces must equal their union.
            if compute != sum(b - a for a, b in intervals):
                raise ValueError("duplicate_exclusive_charge")
            logical = None
            if "logical_opened_at" in root and "logical_closed_at" in root:
                a, b = root["logical_opened_at"], root["logical_closed_at"]
                if not _finite(a) or not _finite(b) or b < a:
                    raise ValueError("invalid_logical_lifetime")
                logical = b - a
            closed = root.get("closed_ns")
            result["requests"].append({"request_id": rid, "status": root["status"],
                "business_job_ids": root["business_job_ids"], "known_control_compute_ns": compute,
                "max_continuous_compute_ns": max((b-a for a, b in merged), default=0),
                "observed_compute_exceeds_100ms": compute > BUDGET_NS,
                "root_wall_elapsed_ns": None if closed is None else closed-root["opened_ns"],
                "logical_end_to_end_seconds": logical,
                "logical_queue_transport_split": "unmeasured",
                "protocol_request_ids": [mid for mid, m in messages.items() if rid in m["root_request_ids"]]})
            if root["status"] not in TERMINAL_ROOT:
                errors.append("open_or_unknown_root:" + rid)
        result["exclusive_work_ns_by_class"] = dict(counts)
        result["status_counts"] = dict(Counter(r["status"] for r in roots))
        result["protocol_request_count"] = len(messages)
        result["known_over_budget_count"] = sum(r["observed_compute_exceeds_100ms"] for r in result["requests"])
        result["errors"] = list(dict.fromkeys(errors))
        complete = not errors
        for row in result["requests"]:
            row["complete_request_compute_ns"] = row["known_control_compute_ns"] if complete else None
        result["status"] = "complete_measured_accounting" if complete else "unknown_incomplete_measurement"
        result["all_observed_requests_within_100ms"] = result["known_over_budget_count"] == 0 if complete else None
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        result["status"] = "unknown_invalid_ledger"
        result["errors"].append(str(exc))
        result["all_observed_requests_within_100ms"] = None
        for row in result["requests"]:
            row["complete_request_compute_ns"] = None
    return result
