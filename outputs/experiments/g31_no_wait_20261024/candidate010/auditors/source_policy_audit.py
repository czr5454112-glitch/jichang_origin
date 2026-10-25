"""Independent nominal-source FIFO and first-planning-clock audit.

The ordering reference is exclusively canonical raw release and stable row order.
Future/unattempted tasks remain in their source queue; no prompt-start optimality
is asserted. Endpoint/edge reservations are checked by separate physical audits.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _d(value):
    return Decimal(str(value))


def audit_source_policy(rows, bags, source_generation_interval=1,
                        release_quantum=1, source_fifo_order="canonical", *, horizon=None):
    """Verify no overtaking/early first attempt against canonical source order.

    ``source_fifo_order`` records the declared implementation policy. Even when
    it is 'activation', the audit reference remains canonical and is never
    replaced with algorithm-generated ordering. Missing attempt telemetry is
    unavailable evidence, while an explicit None means not yet attempted.
    """
    rows, bags = list(rows), list(bags)
    from .future_metadata import audit_future_metadata, merge_future_result
    future = audit_future_metadata(rows, bags, horizon=horizon)
    if not _finite(source_generation_interval) or source_generation_interval < 0:
        raise ValueError("source_generation_interval must be finite and nonnegative")
    if not _finite(release_quantum) or release_quantum <= 0:
        raise ValueError("release_quantum must be finite and positive")
    if source_fifo_order not in ("canonical", "activation"):
        raise ValueError("unknown declared source_fifo_order")
    expected = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(expected) != len(rows) or len(actual) != len(bags):
        raise ValueError("duplicate segment identity")
    counts = Counter()
    examples = []

    def fail(sid, reason, *detail):
        counts[reason] += 1
        if len(examples) < 30:
            examples.append([sid, reason, *detail])

    def ceil_release(value):
        quantum = _d(release_quantum)
        return (_d(value) / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum

    for sid in actual.keys() - expected.keys():
        fail(sid, "unknown_actual_segment")
    queues = defaultdict(list)
    business = defaultdict(dict)
    checked = {}
    missing = missing_attempt = attempted = admitted = unattempted = 0
    for ordinal, row in enumerate(rows):
        sid = str(row["segment_id"])
        if not _finite(row["pass_time"]):
            raise ValueError("canonical release must be finite")
        queues[row["start"]].append((row["pass_time"], ordinal, sid))
        task = str(row["task_id"])
        leg = row["leg"]
        if leg in business[task]:
            raise ValueError("duplicate business leg")
        business[task][leg] = sid
        bag = actual.get(sid)
        if bag is None:
            missing += 1
            fail(sid, "missing_actual_segment")
            bag = {}
        for key in ("task_id", "leg", "start", "goal"):
            if key in bag and key in row and bag[key] != row[key]:
                fail(sid, "identity_mismatch", key)
        if "first_planning_attempt_time" not in bag:
            missing_attempt += 1
            fail(sid, "missing_first_planning_attempt_telemetry")
        attempt = bag.get("first_planning_attempt_time")
        admission = bag.get("admission")
        activation = bag.get("activation_time")
        finish = bag.get("finish")
        valid = True
        for field, value in (("first_planning_attempt_time", attempt), ("admission", admission),
                             ("activation_time", activation), ("finish", finish)):
            if value is not None and not _finite(value):
                fail(sid, "nonfinite_clock", field)
                valid = False
        if not valid:
            checked[sid] = dict(attempt=None, admission=None)
            continue
        if attempt is None:
            unattempted += 1
        else:
            attempted += 1
            if _d(attempt) < ceil_release(row["pass_time"]):
                fail(sid, "first_attempt_before_ceil_canonical_release")
        if admission is not None:
            admitted += 1
            if attempt is None:
                fail(sid, "admitted_without_first_attempt")
            elif admission < attempt:
                fail(sid, "admission_before_first_attempt")
            if _d(admission) < ceil_release(row["pass_time"]):
                fail(sid, "admission_before_ceil_canonical_release")
        if bag.get("future_reserved") is True:
            reserved_at, planned = bag.get("reservation_time"), bag.get("planned_admission")
            if _finite(reserved_at) and _d(reserved_at) < ceil_release(row["pass_time"]):
                fail(sid, "future_reservation_before_ceil_release")
            if _finite(planned) and _d(planned) != ceil_release(planned):
                fail(sid, "future_admission_not_on_source_quantum")
        if "activation_time" in bag:
            if attempt is not None and activation is None:
                fail(sid, "attempt_without_recorded_activation")
            if activation is not None and (activation < row["pass_time"] or
                                           (attempt is not None and activation > attempt)):
                fail(sid, "activation_outside_release_attempt_window")
        if finish is not None and admission is not None and finish < admission:
            fail(sid, "finish_before_admission")
        if bag.get("completed") is True and (finish is None or admission is None):
            fail(sid, "completed_without_admission_and_finish")
        checked[sid] = dict(attempt=attempt, admission=admission)

    ordering_hash = hashlib.sha256()
    pair_checks = 0
    for source, queue in queues.items():
        queue.sort(key=lambda entry: (entry[0], entry[1]))
        ordering_hash.update(json.dumps([source, [entry[2] for entry in queue]], separators=(",", ":")).encode())
        blocked_by = None
        previous = None
        for _, _, sid in queue:
            clocks = checked[sid]
            attempt, admission = clocks["attempt"], clocks["admission"]
            if blocked_by is not None and (attempt is not None or admission is not None):
                fail(sid, "bypassed_unadmitted_canonical_predecessor", blocked_by)
            if previous is not None and attempt is not None:
                pair_checks += 1
                prior_admission = checked[previous]["admission"]
                if prior_admission is not None and _d(attempt) < _d(prior_admission) + _d(source_generation_interval):
                    fail(sid, "first_attempt_before_previous_success_plus_source_interval", previous)
            if admission is None and blocked_by is None:
                blocked_by = sid
            previous = sid

    gate_checks = 0
    for legs in business.values():
        if "storage_out" not in legs:
            continue
        sid = legs["storage_out"]
        clocks = checked[sid]
        if clocks["attempt"] is None and clocks["admission"] is None:
            continue
        gate_checks += 1
        prior_sid = legs.get("storage_in")
        prior = actual.get(prior_sid, {})
        finish = prior.get("finish")
        if prior.get("completed") is not True or not _finite(finish):
            fail(sid, "outbound_attempt_before_verified_inbound_completion", prior_sid)
            continue
        ready = ceil_release(finish)
        for report_field in ("reported_finish_epoch", "observed_finish"):
            report = prior.get(report_field)
            if report is not None:
                if not _finite(report) or report < finish:
                    fail(prior_sid, "invalid_actual_completion_report", report_field)
                else:
                    ready = max(ready, _d(report))
        if clocks["attempt"] is not None and _d(clocks["attempt"]) < ready:
            fail(sid, "outbound_first_attempt_before_inbound_report", prior_sid, float(ready))
        if clocks["admission"] is not None and _d(clocks["admission"]) < ready:
            fail(sid, "outbound_admission_before_inbound_report", prior_sid, float(ready))

    return merge_future_result(dict(schema="g31.nowait.source_policy_audit.v1", passed=not counts,
                declared_source_fifo_order=source_fifo_order,
                reference="stable canonical raw pass_time, original row order for equal releases; never generated or activation order",
                source_generation_interval=source_generation_interval, release_quantum=release_quantum,
                segment_denominator=len(rows), business_denominator=len(business), source_count=len(queues),
                attempted_segments=attempted, admitted_segments=admitted, unattempted_segments=unattempted,
                missing_segments=missing, missing_first_attempt_telemetry=missing_attempt,
                predecessor_pacing_checks=pair_checks, ebs_gate_checks=gate_checks,
                canonical_source_order_sha256=ordering_hash.hexdigest(),
                violation_count=sum(counts.values()), violation_counts=dict(counts), violation_examples=examples,
                boundaries=["Checks no early attempt/admission and no canonical overtaking; does not assert a head must start immediately.",
                            "Explicit unattempted future or blocked tasks remain in the full denominator and are legal unless bypassed.",
                            "EBS gate uses verified completed inbound continuous finish rounded to the source quantum and any supplied later actual report.",
                            "Resource safety and exact physical arrival are independent audits; this check is not an optimality or performance proof.",
                            "Future reservation retains the source head: pacing and predecessor release use actual admission, never reservation_time or planned_admission."]), future)
