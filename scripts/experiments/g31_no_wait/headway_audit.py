"""Independent integer-grid physics and headway audit for no-wait candidate 002.

The declared time grid is a model contract, not an overlap tolerance. Inputs are
normalized once; reported route times must round-trip from their integer tick.
No geometry, opposite-direction shared lane or variable-speed claim is made.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
import math


def ticks_per_second(time_grid_seconds=1e-6):
    grid = Decimal(str(time_grid_seconds))
    if not grid.is_finite() or grid <= 0:
        raise ValueError("time grid must be positive and finite")
    frequency = Decimal(1) / grid
    if frequency != frequency.to_integral_value():
        raise ValueError("time grid must divide one second exactly")
    return int(frequency)


def input_ticks(value, frequency):
    """Declared input normalization, nearest tick with half away from zero."""
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("nonfinite time")
    return int((number * frequency).to_integral_value(rounding=ROUND_HALF_UP))


def reported_ticks(value, frequency):
    """Decode a double serialized from ticks, rejecting actual off-grid times."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("nonfinite or nonnumeric reported time")
    ticks = input_ticks(value, frequency)
    # Exact double equality verifies serialization, not a safety epsilon.
    if value != ticks / frequency:
        raise ValueError("reported time does not round-trip from the declared integer grid")
    return ticks


def audit_headway(rows, bags, profile, *, time_grid_seconds=1e-6,
                  strict_endpoint_resources=True, edge_entry_headway_seconds=2.0,
                  max_examples=20):
    """Rebuild exact routes, then check physical half-open nodes and edge entry.

    ``profile`` uses the same nodes/edges structure as run.audit. Edge travel is
    length / 2 m/s. This campaign's positive devices must all be 2 seconds;
    original-zero connectors occupy an empty node interval. Goal business
    completion remains its arrival, while its physical resource lasts 2 seconds.
    Full-population business/STD/EBS accounting remains the runner's responsibility.
    """
    frequency = ticks_per_second(time_grid_seconds)
    headway = input_ticks(edge_entry_headway_seconds, frequency)
    if headway < 0 or max_examples < 0:
        raise ValueError("negative headway or max_examples")
    canonical = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(canonical) != len(rows) or len(actual) != len(bags) or canonical.keys() != actual.keys():
        raise ValueError("full canonical segment identity changed")
    service = {int(n["location"]): input_ticks(n["service_time"], frequency)
               for n in profile["nodes"]}
    if any(s not in (0, 2 * frequency) for s in service.values()):
        raise ValueError("positive device service is not exactly 2 seconds")
    travel = {(int(e["start"]), int(e["end"])):
              input_ticks(Decimal(str(e["length"])) / 2, frequency)
              for e in profile["edges"]}
    if any(t < 0 for t in travel.values()):
        raise ValueError("negative edge travel")
    counts, stats = Counter(), Counter()
    examples = []
    resources, entries = defaultdict(list), defaultdict(list)

    def violation(reason, sid, **details):
        counts[reason] += 1
        if len(examples) < max_examples:
            examples.append(dict(reason=reason, segment_id=sid, **details))

    for sid, bag in actual.items():
        raw = bag.get("route", [])
        if not raw:
            continue
        stats["planned_routes"] += 1
        route = []
        try:
            for point in raw:
                if (not isinstance(point, (tuple, list)) or len(point) != 3
                        or isinstance(point[0], bool) or int(point[0]) != point[0]):
                    raise ValueError("malformed route point")
                node = int(point[0])
                if node not in service:
                    raise ValueError("unknown route node")
                route.append((node, reported_ticks(point[1], frequency),
                              reported_ticks(point[2], frequency)))
        except (TypeError, ValueError, OverflowError) as exc:
            violation("malformed_or_offgrid_route", sid, detail=str(exc))
            continue
        row = canonical[sid]
        if route[0][0] != int(row["start"]) or route[-1][0] != int(row["goal"]):
            violation("route_endpoint_mismatch", sid)
        if len({p[0] for p in route}) != len(route):
            violation("repeated_route_node", sid)
        if route[0][1] < input_ticks(row["pass_time"], frequency):
            violation("early_admission", sid)
        expected_arrival = route[0][1]
        for i, (node, arrival, departure) in enumerate(route):
            if arrival != expected_arrival:
                violation("no_wait_route_time_mismatch", sid, node=node,
                          reported_arrival_ticks=arrival, expected_arrival_ticks=expected_arrival)
            expected_departure = expected_arrival + service[node]
            is_endpoint = i == 0 or i == len(route) - 1
            # Legacy endpoint diagnostics may have a zero terminal reservation.
            legal_departures = {expected_departure}
            if not strict_endpoint_resources and i == len(route) - 1:
                legal_departures.add(expected_arrival)
            if departure not in legal_departures:
                violation("device_through_time_mismatch", sid, node=node,
                          reported_departure_ticks=departure, expected_departure_ticks=expected_departure)
            if service[node] > 0 and (strict_endpoint_resources or not is_endpoint):
                role = "source" if i == 0 else "goal" if i == len(route) - 1 else "internal"
                resources[node].append((expected_arrival, expected_departure, sid, role))
                stats["positive_node_visits_checked"] += 1
            elif service[node] == 0:
                stats["empty_zero_service_node_visits"] += 1
            if i + 1 < len(route):
                edge = (node, route[i + 1][0])
                if edge not in travel:
                    violation("missing_edge", sid, edge=edge)
                    break
                entries[edge].append((expected_departure, sid))
                expected_arrival = expected_departure + travel[edge]
        try:
            if reported_ticks(bag["admission"], frequency) != route[0][1]:
                violation("admission_metadata_mismatch", sid)
            if reported_ticks(bag["finish"], frequency) != route[-1][1]:
                violation("finish_metadata_mismatch", sid)
        except (KeyError, ValueError, TypeError) as exc:
            violation("invalid_time_metadata", sid, detail=str(exc))

    for node, intervals in resources.items():
        # All positive devices have equal duration, so consecutive sorted starts
        # are a necessary and sufficient half-open non-overlap check.
        intervals.sort()
        for prior, current in zip(intervals, intervals[1:]):
            stats["node_adjacent_pairs_checked"] += 1
            if current[0] < prior[1]:
                violation("physical_node_overlap", current[2], node=node,
                          prior_segment_id=prior[2], prior_role=prior[3], current_role=current[3],
                          prior_ticks=list(prior[:2]), current_ticks=list(current[:2]))
    edge_report = []
    minimum = None
    for edge, arrivals in sorted(entries.items()):
        arrivals.sort()
        local_minimum = None
        local_violations = 0
        for prior, current in zip(arrivals, arrivals[1:]):
            gap = current[0] - prior[0]
            minimum = gap if minimum is None else min(minimum, gap)
            local_minimum = gap if local_minimum is None else min(local_minimum, gap)
            stats["edge_adjacent_pairs_checked"] += 1
            if gap < headway:
                local_violations += 1
                violation("directed_edge_headway", current[1], edge=list(edge),
                          prior_segment_id=prior[1], entry_ticks=current[0],
                          prior_entry_ticks=prior[0], headway_ticks=gap, required_ticks=headway)
        edge_report.append(dict(edge=list(edge), entries=len(arrivals),
                                minimum_headway_ticks=local_minimum,
                                violations=local_violations))
    return dict(schema="g31.nowait.physical_headway_audit.v1", passed=not counts,
                segment_denominator=len(rows), planned_routes=stats["planned_routes"],
                time_grid_seconds=time_grid_seconds, ticks_per_second=frequency,
                strict_endpoint_resources=strict_endpoint_resources,
                required_edge_headway_ticks=headway, minimum_edge_headway_ticks=minimum,
                violation_count=sum(counts.values()), violation_counts=dict(counts),
                violation_examples=examples, stats=dict(stats), edges=edge_report,
                boundary="Exact integer-grid fixed-speed directed-edge headway and positive-node half-open occupancy. No unknown physical bag length, shared cross-edge geometry, reverse-lane or variable-speed guarantee. Complete certificates; runner separately checks horizon, business, release and EBS accounting.")
