"""Validate future-source telemetry without promoting plans to observations."""
from __future__ import annotations

from collections import Counter

from .headway_audit import reported_ticks, ticks_per_second, input_ticks


def audit_future_metadata(rows, bags, *, horizon=None, time_grid_seconds=1e-6):
    frequency = ticks_per_second(time_grid_seconds)
    cutoff = None if horizon is None else input_ticks(horizon, frequency)
    expected = {str(r["segment_id"]): r for r in rows}
    counts, stats = Counter(), Counter()
    examples = []

    def fail(sid, reason, **detail):
        counts[reason] += 1
        if len(examples) < 30:
            examples.append(dict(segment_id=sid, reason=reason, **detail))

    for bag in bags:
        sid = str(bag["segment_id"])
        if sid not in expected:
            fail(sid, "future_unknown_segment")
            continue
        present = "future_reserved" in bag
        if not present:
            # Baseline comparison retains the original auditable schema.
            if any(k in bag for k in ("future_pending", "reserved_route", "reservation_time")):
                fail(sid, "future_metadata_without_flag")
            continue
        reserved, pending = bag.get("future_reserved"), bag.get("future_pending")
        if not isinstance(reserved, bool) or not isinstance(pending, bool):
            fail(sid, "future_flags_not_boolean")
            continue
        clocks = ("reservation_time", "planned_admission", "planned_finish", "planned_resource_cleanup_epoch")
        arrays = ("reserved_route", "reserved_node_reservation_ids", "reserved_edge_reservation_ids")
        if not reserved:
            if pending or any(bag.get(k) is not None for k in clocks + ("reservation_order",)) or any(bag.get(k, []) != [] for k in arrays):
                fail(sid, "unreserved_has_future_metadata")
            continue
        stats["future_reserved_segments"] += 1
        stats["future_pending_segments" if pending else "future_launched_segments"] += 1
        try:
            ticks = {k: reported_ticks(bag[k], frequency) for k in clocks}
            order = bag["reservation_order"]
            if isinstance(order, bool) or not isinstance(order, int) or order <= 0:
                raise ValueError("reservation_order must be a positive ledger order")
            route = bag["reserved_route"]
            if not isinstance(route, list) or not route:
                raise ValueError("reserved route must be complete and nonempty")
            decoded = []
            for p in route:
                if (not isinstance(p, (list, tuple)) or len(p) != 3 or isinstance(p[0], bool)
                        or not isinstance(p[0], int)):
                    raise ValueError("malformed reserved route point")
                decoded.append((p[0], reported_ticks(p[1], frequency), reported_ticks(p[2], frequency)))
            node_ids, edge_ids = bag["reserved_node_reservation_ids"], bag["reserved_edge_reservation_ids"]
            if len(node_ids) != len(route) or len(edge_ids) != len(route) - 1:
                raise ValueError("reserved ids do not match complete route")
            row = expected[sid]
            if decoded[0][0] != int(row["start"]) or decoded[-1][0] != int(row["goal"]):
                fail(sid, "future_route_endpoint_mismatch")
            if decoded[0][1] != ticks["planned_admission"] or decoded[-1][1] != ticks["planned_finish"]:
                fail(sid, "future_plan_clock_route_mismatch")
            attempt = reported_ticks(bag["first_planning_attempt_time"], frequency)
            if not (input_ticks(row["pass_time"], frequency) <= attempt <= ticks["reservation_time"] < ticks["planned_admission"] <= ticks["planned_finish"] <= ticks["planned_resource_cleanup_epoch"]):
                fail(sid, "future_clock_order_invalid")
            if cutoff is not None and ticks["reservation_time"] > cutoff:
                fail(sid, "future_reservation_after_horizon")
            admitted = bag.get("admission") is not None
            if pending == admitted:
                fail(sid, "future_pending_admission_mismatch")
            if pending:
                for key in ("admission", "finish", "actual_finish", "completion_epoch", "commit_time", "planning_time", "commit_order", "resource_cleanup_epoch", "resource_cleanup_time"):
                    if bag.get(key) is not None:
                        fail(sid, "future_pending_leaks_actual_clock", field=key)
                for key in ("route", "node_reservation_ids", "edge_reservation_ids"):
                    if bag.get(key) != []:
                        fail(sid, "future_pending_leaks_actual_route", field=key)
                if bag.get("completed") is not False or bag.get("actual_arrived_index") != -1:
                    fail(sid, "future_pending_claims_physical_progress")
                if cutoff is not None and ticks["planned_admission"] <= cutoff:
                    fail(sid, "future_pending_missed_due_launch")
            else:
                if reported_ticks(bag["admission"], frequency) != ticks["planned_admission"]:
                    fail(sid, "future_actual_admission_differs_from_plan")
                if reported_ticks(bag["commit_time"], frequency) != ticks["planned_admission"]:
                    fail(sid, "future_commit_time_not_actual_launch")
                if cutoff is not None and ticks["planned_admission"] > cutoff:
                    fail(sid, "future_launch_after_horizon")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            fail(sid, "malformed_future_metadata", detail=str(exc))
    return dict(schema="g31.nowait.future_metadata_audit.v1", passed=not counts,
                violation_count=sum(counts.values()), violation_counts=dict(counts),
                violation_examples=examples, stats=dict(stats),
                boundary="Initial reserved certificate is persistent provenance. Pending plans are not actual admissions, routes, finishes or completed observations.")


def merge_future_result(result, future):
    """Attach a hard metadata gate while retaining each original audit's schema."""
    result["future_reservation_audit"] = future
    result["passed"] = bool(result["passed"] and future["passed"])
    return result
