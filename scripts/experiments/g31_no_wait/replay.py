"""Independent commit-order replay for the isolated no-wait continuation prototype.

This verifies the declared reservation protocol, not conveyor geometry. All timing
and route physics checks remain in run.audit. No native summary is trusted here.
"""
from __future__ import annotations

from bisect import bisect_right, insort
from collections import Counter, defaultdict
import heapq
import math

from scripts.experiments.g31_no_wait.headway_audit import input_ticks, reported_ticks, ticks_per_second


def replay_calendar(rows, bags, *, endpoint_policy="hca_query_exempt",
                    cleanup_phase="before_commit_le",
                    require_commit_equals_admission=True, max_examples=20,
                    interval_mode="closed", time_grid_seconds=None,
                    cleanup_field="completion_epoch", edge_entry_headway_seconds=0.0):
    """Replay published complete certificates in commit_order.

    Policies: hca_query_exempt skips a *current* bag's source/goal query but
    inserts all its route intervals; internal_only compares only two internal
    visits; all_nodes enforces occupancy at endpoints too. Closed intervals are
    used exactly, without epsilon. Completion at an integer epoch is removed
    before a commit at that epoch, matching the independently checked Java order.
    ``before_commit_lt`` is an explicit diagnostic counterfactual, not default.
    Failed/unplanned rows retain denominator membership but insert nothing.
    """
    if endpoint_policy not in {"hca_query_exempt", "internal_only", "all_nodes"}:
        raise ValueError("unsupported endpoint_policy")
    if cleanup_phase not in {"before_commit_le", "before_commit_lt"}:
        raise ValueError("unsupported cleanup_phase")
    if interval_mode not in {"closed", "half_open"}:
        raise ValueError("unsupported interval_mode")
    if cleanup_field not in {"completion_epoch", "resource_cleanup_epoch", "resource_cleanup_time"}:
        raise ValueError("unsupported cleanup_field")
    frequency = ticks_per_second(time_grid_seconds) if time_grid_seconds is not None else None
    if interval_mode == "half_open" and frequency is None:
        raise ValueError("half-open physical replay requires an explicit integer time grid")
    if not math.isfinite(edge_entry_headway_seconds) or edge_entry_headway_seconds < 0:
        raise ValueError("invalid edge headway")
    def decode(value):
        return reported_ticks(value, frequency) if frequency else float(value)
    def ceil_epoch(value):
        return ((value + frequency - 1) // frequency) * frequency if frequency else math.ceil(value)
    edge_headway = input_ticks(edge_entry_headway_seconds, frequency) if frequency else edge_entry_headway_seconds
    if max_examples < 0:
        raise ValueError("max_examples must be nonnegative")
    canonical = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(canonical) != len(rows) or len(actual) != len(bags) or canonical.keys() != actual.keys():
        raise ValueError("full canonical segment identity changed")
    counts = Counter()
    examples = []

    def violation(reason, sid, **details):
        counts[reason] += 1
        if len(examples) < max_examples:
            examples.append({"reason": reason, "segment_id": sid, **details})

    def finite_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    commits = []
    seen_orders = set()
    for sid, bag in actual.items():
        if not bag.get("route"):
            continue
        meta = {key: bag.get(key) for key in
                ("admission", "finish", "commit_time", "commit_order", "completion_epoch", cleanup_field)}
        if not all(finite_number(v) for v in meta.values()):
            violation("invalid_or_missing_commit_metadata", sid, fields=meta)
            continue
        order = meta["commit_order"]
        if order < 0 or int(order) != order or order in seen_orders:
            violation("invalid_or_duplicate_commit_order", sid, commit_order=order)
            continue
        seen_orders.add(order)
        route = []
        malformed = False
        for p in bag["route"]:
            if (not isinstance(p, (list, tuple)) or len(p) != 3
                    or not all(finite_number(x) for x in p)
                    or int(p[0]) != p[0] or p[2] < p[1]):
                malformed = True
                break
            try:
                route.append((int(p[0]), decode(p[1]), decode(p[2])))
            except ValueError:
                malformed = True
                break
        if malformed:
            violation("malformed_route_interval", sid)
            continue
        release = (input_ticks(canonical[sid]["pass_time"], frequency) if frequency
                   else float(canonical[sid]["pass_time"]))
        try:
            admission, finish, now, epoch = (decode(meta[k]) for k in
                                           ("admission", "finish", "commit_time", cleanup_field))
            business_epoch = decode(meta["completion_epoch"])
        except ValueError:
            violation("offgrid_commit_metadata", sid)
            continue
        if not math.isfinite(release):
            violation("nonfinite_business_release", sid)
            continue
        if now < release:
            violation("committed_before_business_release", sid, commit_time=now, release=release)
        if admission < release:
            violation("admitted_before_business_release", sid, admission=admission, release=release)
        if now > admission:
            violation("committed_after_physical_admission", sid, commit_time=now, admission=admission)
        if require_commit_equals_admission and now != admission:
            violation("commit_admission_contract_mismatch", sid, commit_time=now, admission=admission)
        if route[0][1] != admission or route[-1][1] != finish:
            violation("route_metadata_time_mismatch", sid)
        if business_epoch != ceil_epoch(finish):
            violation("completion_epoch_mismatch", sid, supplied=business_epoch, expected=ceil_epoch(finish))
        if cleanup_field != "completion_epoch":
            expected_cleanup = ceil_epoch(max([business_epoch, route[-1][2]] +
                                             [p[2] + edge_headway for p in route[:-1]]))
            if epoch != expected_cleanup:
                violation("resource_cleanup_epoch_mismatch", sid, supplied=epoch, expected=expected_cleanup)
        if epoch < now or any(a < now for _, a, _ in route):
            violation("certificate_contains_past_state", sid)
        if (route[0][0] != int(canonical[sid]["start"])
                or route[-1][0] != int(canonical[sid]["goal"])):
            violation("route_endpoint_mismatch", sid)
        commits.append((int(order), sid, now, epoch, route))

    # Each entry is (arrival, departure, owner, role). Owner deletion removes its
    # entire saved route, even service intervals nominally extending beyond goal.
    calendars = defaultdict(list)
    live = set()
    cleanup = []
    previous_time = -math.inf
    previous_order = None
    stats = Counter()
    endpoint_examples = []
    for order, sid, now, epoch, route in sorted(commits):
        if now < previous_time:
            violation("commit_order_time_reversal", sid, commit_order=order,
                      commit_time=now, previous_order=previous_order, previous_time=previous_time)
        previous_time = max(previous_time, now)
        previous_order = order
        while cleanup and (cleanup[0][0] <= now if cleanup_phase == "before_commit_le"
                           else cleanup[0][0] < now):
            _, old_order, owner = heapq.heappop(cleanup)
            if owner in live:
                live.remove(owner)
                stats["completed_owners_removed"] += 1
        start = int(canonical[sid]["start"])
        goal = int(canonical[sid]["goal"])
        staged = []
        for i, (node, a, d) in enumerate(route):
            role = "internal"
            if i == 0:
                role = "source"
            if i == len(route) - 1:
                role = "source_goal" if i == 0 else "goal"
            # Safe memory pruning: an interval ending strictly before now cannot
            # clash with a valid future exact-arrival query. Closed endpoints stay.
            calendar = calendars[node]
            if calendar:
                calendar = [p for p in calendar if p[2] in live and
                            (p[1] >= now if interval_mode == "closed" else p[1] > now)]
                calendars[node] = calendar
            if interval_mode == "half_open" and d == a:
                stats["empty_intervals_ignored"] += 1
                continue
            # Do not invert rounded endpoints to infer a lower start bound.
            # Equal starts can have different durations; direct endpoint tests
            # also avoid cancellation at widely different floating scales.
            upper = bisect_right(calendar, (d, math.inf, "\uffff", "\uffff"))
            current_exempt = node == start or node == goal
            stats["interval_queries"] += 1
            for old_a, old_d, owner, old_role in calendar[:upper]:
                stats["candidate_interval_comparisons"] += 1
                if (a > old_d or d < old_a) if interval_mode == "closed" else (a >= old_d or d <= old_a):
                    continue
                is_violation = (endpoint_policy == "all_nodes"
                                or endpoint_policy == "hca_query_exempt" and not current_exempt
                                or endpoint_policy == "internal_only" and role == old_role == "internal")
                details = {"node": node, "prior_segment_id": owner,
                           "prior_interval": [old_a, old_d], "new_interval": [a, d],
                           "prior_role": old_role, "new_role": role, "commit_time": now,
                           "commit_order": order}
                if is_violation:
                    violation("reservation_query_conflict", sid, **details)
                    if old_role != "internal" and role == "internal":
                        stats["internal_query_conflicts_with_prior_endpoint"] += 1
                else:
                    stats["exempt_overlapping_queries"] += 1
                    if len(endpoint_examples) < max_examples:
                        endpoint_examples.append({"segment_id": sid, **details})
            staged.append((node, a, d, role))
        # Publication occurs only after all queries; an invalid observed commit is
        # still replayed so the ledger reflects what the payload claims happened.
        live.add(sid)
        for node, a, d, role in staged:
            insort(calendars[node], (a, d, sid, role))
            stats["published_intervals"] += 1
        heapq.heappush(cleanup, (epoch, order, sid))
        stats["published_certificates"] += 1

    return {
        "schema": "g31.nowait.commit_calendar_replay.v1",
        "passed": not counts,
        "segment_denominator": len(rows),
        "planned_routes": sum(bool(b.get("route")) for b in bags),
        "replayed_certificates": len(commits),
        "endpoint_policy": endpoint_policy,
        "cleanup_phase": cleanup_phase,
        "cleanup_field": cleanup_field,
        "interval_mode": interval_mode,
        "time_grid_seconds": time_grid_seconds,
        "reported_violation_time_units": "ticks" if frequency else "seconds",
        "require_commit_equals_admission": require_commit_equals_admission,
        "violation_count": sum(counts.values()), "violation_counts": dict(counts),
        "violation_examples": examples, "stats": dict(stats),
        "exempt_overlap_examples": endpoint_examples,
        "boundary": ("Complete published certificates, exact selected-interval node calendars; source/goal current-query "
                     "exemption is directional, not a blanket endpoint exemption. No proof of edge geometry, "
                     "failed-attempt side effects, hidden read sets, real concurrent transactions, or transport "
                     "execution beyond the reported routes. Use run.audit for service/travel/causal physics."),
    }
