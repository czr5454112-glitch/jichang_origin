#!/usr/bin/env python3
"""Run the compact G20 E0/E1/E2 event-hotpath paired ladder.

The runner keeps the G19 A0 + S4 + J2 controller and fixed airport input.
Only redundant congestion-beacon publication changes.  The 1x/2x jobs run to
natural completion; 4x uses G19's native wall-bounded progress return.  Raw
bag rows and in-memory semantic projections are discarded after pairing.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf19_bounded_capacity as g19_capacity
from scripts.eval import run_g4irsf18_jit_campaign as g18_jit


SCHEMA = "czr005.g4irsf20.event_hotpath_campaign.v1"
BEST_POLICY_SCHEMA = "czr005.g4irsf20.event_hotpath_policy.v1"
POLICIES = ("E0", "E1", "E2")
FULL_SCALES = (1, 2)
BOUNDED_SCALE = 4
ALL_SCALES = (*FULL_SCALES, BOUNDED_SCALE)

DEFAULT_JSON = ROOT / "outputs/tables/g4irsf20_event_hotpath_ab.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf20_event_hotpath_ab.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf20_event_hotpath.md"
DEFAULT_BEST_POLICY = ROOT / "artifacts/policies/g4irsf20_event_policy.json"

TTH_ABS_TOLERANCE_SECONDS = 1.0e-9
MECHANISM_THRESHOLDS = {
    "beacon_reduction_fraction": 0.30,
    "events_per_completed_bag_reduction_fraction": 0.20,
    "bounded_events_per_second_improvement_fraction": 0.25,
    "bounded_completion_improvement_fraction": 0.20,
}

Executor = Callable[..., Mapping[str, Any]]
InputLoader = Callable[[int, Path], tuple[list[dict[str, Any]], dict[str, Any]]]
RssReader = Callable[[], tuple[float | None, str]]


class EventHotpathError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EventHotpathError(message)


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _reduction(baseline: float | int | None, treatment: float | int | None) -> float | None:
    left = _finite(baseline)
    right = _finite(treatment)
    if left is None or right is None or left <= 0.0:
        return 0.0 if left == right == 0.0 else None
    return (left - right) / left


def _improvement(baseline: float | int | None, treatment: float | int | None) -> float | None:
    left = _finite(baseline)
    right = _finite(treatment)
    if left is None or right is None or left <= 0.0:
        return 0.0 if left == right == 0.0 else None
    return (right - left) / left


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if not isinstance(right, (int, float)) or isinstance(right, bool):
            return False
        return math.isclose(
            float(left),
            float(right),
            rel_tol=0.0,
            abs_tol=TTH_ABS_TOLERANCE_SECONDS,
        )
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(
            _close(a, b) for a, b in zip(left, right)
        )
    return left == right


def build_native_request(
    rows: Sequence[Mapping[str, Any]],
    *,
    scale: int,
    policy: str,
    binary: Path,
    root: Path,
    bounded_wall_seconds: float,
    check_events: int,
) -> dict[str, Any]:
    """Reuse G19's fixed S4/J2 request and change only the G20 policy."""

    _require(scale in ALL_SCALES, f"scale must be one of {ALL_SCALES}")
    _require(policy in POLICIES, f"policy must be one of {POLICIES}")
    _require(bounded_wall_seconds > 0.0, "bounded wall seconds must be positive")
    _require(check_events > 0, "check events must be positive")
    request = g19_capacity.build_native_request(
        rows,
        scale=scale,
        scorer="S4",
        binary=binary,
        root=root,
        max_wall_seconds=bounded_wall_seconds,
        check_events=check_events,
    )
    request.update(
        scenario=f"g4irsf20_event_hotpath_{scale}x_{policy.lower()}",
        g4irsf20_event_hotpath_policy=policy,
    )
    if scale in FULL_SCALES:
        # E1/E2 make the wrapper materialize the complete append-only tail;
        # E0 retains the historical unbounded G19 call shape.
        request.pop("bounded_wall_seconds", None)
        request.pop("bounded_check_every_events", None)
        request["summary_only"] = False
    else:
        request["summary_only"] = True
    return request


def _hotpath_counts(
    source: Mapping[str, Any],
    summary: Mapping[str, Any],
    policy: str,
) -> dict[str, Any]:
    def count(name: str) -> int:
        value = _integer(source.get(name))
        if value is None:
            value = _integer(summary.get(name))
        return value or 0

    echo = source.get(
        "g4irsf20_event_hotpath_policy",
        summary.get("g4irsf20_event_hotpath_policy"),
    )
    if policy == "E0":
        _require(echo in (None, "E0"), "E0 hotpath echo drift")
    else:
        _require(echo == policy, f"{policy} hotpath echo drift")
    redundant = count("g4irsf20_redundant_beacon_suppressed_count")
    same_state = count("g4irsf20_same_state_beacon_suppressed_count")
    _require(redundant >= 0 and same_state >= 0, "negative hotpath counter")
    return {
        "policy": policy,
        "redundant_beacon_suppressed_count": redundant,
        "same_state_beacon_suppressed_count": same_state,
        "total_beacon_suppressed_count": redundant + same_state,
    }


def _action_projection(bags: Sequence[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    rows = []
    for bag in bags:
        history = bag.get("short_history", [])
        _require(isinstance(history, list), "native short_history is not a list")
        rows.append(
            (
                str(bag.get("segment_id", "")),
                _integer(bag.get("task_id")),
                _integer(bag.get("start")),
                _integer(bag.get("goal")),
                _integer(bag.get("final_node")),
                bag.get("completed"),
                str(bag.get("failure_reason", "")),
                _integer(bag.get("decision_count")),
                _integer(bag.get("retry_count")),
                _integer(bag.get("loop_count")),
                tuple(_integer(value) for value in history),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row[1] or -1, row[0])))


def _tth_projection(raw_bags: Sequence[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                _integer(row.get("task_id")),
                row.get("complete"),
                _finite(row.get("tth_seconds")),
                _finite(row.get("source_wait_seconds")),
                _finite(row.get("network_time_seconds")),
                _finite(row.get("merge_grant_wait_seconds")),
            )
            for row in raw_bags
        )
    )


def _route_wait_by_task(bags: Sequence[Mapping[str, Any]]) -> dict[int, float]:
    result: dict[int, float] = {}
    for bag in bags:
        task = _integer(bag.get("task_id"))
        wait = _finite(bag.get("junction_queue_wait_seconds"))
        if task is not None and wait is not None:
            result[task] = result.get(task, 0.0) + wait
    return result


def _full_result(
    payload: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    scale: int,
    policy: str,
    wall_seconds: float,
    cpu_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = payload.get("summary")
    bags = payload.get("bags")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(isinstance(bags, list), "full native payload lacks bag rows")
    bag_rows = [row for row in bags if isinstance(row, Mapping)]
    _require(len(bag_rows) == len(bags), "native bag rows contain a non-object")
    _require(
        summary.get("scorer_mode") == g19_capacity.SCORER_MODES["S4"],
        "S4 scorer echo drift",
    )
    _require(
        summary.get("merge_grant_timing_mode") == "jit_fair_aging_deadline",
        "J2 timing echo drift",
    )
    raw = g18_jit._raw_bags(
        rows,
        payload,
        str(descriptor["tth_denominator"]),
    )
    completed = [row for row in raw if row["complete"]]
    all_complete = len(completed) == len(raw)
    tth = [float(row["tth_seconds"]) for row in completed]
    source_wait = [float(row["source_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    merge_wait = [float(row["merge_grant_wait_seconds"]) for row in completed]
    route_by_task = _route_wait_by_task(bag_rows)
    route_wait = [route_by_task.get(int(row["task_id"]), 0.0) for row in completed]
    safety = g18_jit._hard_safety(summary, len(rows))
    events = _integer(summary.get("event_count")) or 0
    beacons = _integer(summary.get("congestion_beacon_update_event_count")) or 0
    hotpath = _hotpath_counts(summary, summary, policy)
    result = {
        "scale": scale,
        "execution_mode": "full",
        "policy": policy,
        "status": "COMPLETE" if all_complete and safety["pass"] else "FULL_GATE_FAILED",
        "input": dict(descriptor),
        "progress": {
            "requested_bags": len(rows),
            "released_bags": _integer(summary.get("bag_release_event_count")) or len(rows),
            "completed_bags": len(completed),
            "failed_bags": _integer(summary.get("failed_count")) or 0,
            "current_backlog": max(len(rows) - len(completed), 0),
        },
        "metrics": {
            "mean_tth_seconds": statistics.fmean(tth) if all_complete and tth else None,
            "p95_tth_seconds": g18_jit._quantile(tth, 0.95) if all_complete else None,
            "p99_tth_seconds": g18_jit._quantile(tth, 0.99) if all_complete else None,
            "source_wait_mean_seconds": (
                statistics.fmean(source_wait) if all_complete and source_wait else None
            ),
            "route_wait_mean_seconds": (
                statistics.fmean(route_wait) if all_complete and route_wait else None
            ),
            "merge_grant_wait_mean_seconds": (
                statistics.fmean(merge_wait) if all_complete and merge_wait else None
            ),
            "network_time_mean_seconds": (
                statistics.fmean(network) if all_complete and network else None
            ),
            "event_count": events,
            "congestion_beacon_event_count": beacons,
            "events_per_completed_bag": events / len(completed) if completed else None,
            "events_per_wall_second": events / wall_seconds if wall_seconds > 0.0 else None,
        },
        "hotpath": hotpath,
        "hard_safety": safety,
        "resources": {
            "native_wall_seconds": wall_seconds,
            "native_process_cpu_seconds": cpu_seconds,
            "native_cpu_to_wall_ratio": cpu_seconds / wall_seconds if wall_seconds > 0.0 else None,
        },
    }
    semantic = {
        "actions": _action_projection(bag_rows),
        "tth": _tth_projection(raw),
        "route_wait_by_task": tuple(sorted(route_by_task.items())),
        "hard_safety": dict(safety["gates"]),
    }
    return result, semantic


def _bounded_safety(summary: Mapping[str, Any]) -> dict[str, Any]:
    zero_fields = (
        "failed_count",
        "reservation_conflicts",
        "physical_fault_edge_entry_violation_count",
        "unresolved_deadlock_count",
        "runtime_full_astar_calls",
        "runtime_full_cie_astar_calls",
        "global_reservation_scan_count",
        "priority_global_scan_count",
        "scorer_runtime_global_scan_count",
        "microphase_runtime_global_scan_count",
        "first_edge_credit_global_scan_count",
        "priority_future_route_input_count",
        "scorer_future_route_input_count",
        "first_edge_credit_future_route_count",
        "scorer_future_schedule_input_count",
        "full_future_routes_stored",
    )
    gates = {f"{name}_zero": _integer(summary.get(name, 0)) == 0 for name in zero_fields}
    gates["future_path_field_absent"] = summary.get("bag_future_path_field_present", False) is False
    return {"pass": all(gates.values()), "gates": gates}


def _bounded_result(
    payload: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    policy: str,
    wall_seconds: float,
    cpu_seconds: float,
    bounded_wall_seconds: float,
    check_events: int,
) -> tuple[dict[str, Any], None]:
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    history, history_source = g19_capacity.progress_history_from_payload(
        payload,
        requested=len(rows),
        wall_seconds=wall_seconds,
    )
    frontier = history[-1]
    slopes = g19_capacity.progress_slopes(history)
    event_types = frontier.get("event_type_counts", {})
    _require(isinstance(event_types, Mapping), "bounded event_type_counts is not an object")
    events = _integer(frontier.get("event_total")) or 0
    completed = _integer(frontier.get("completed_bags")) or 0
    hotpath = _hotpath_counts(frontier, summary, policy)
    safety = _bounded_safety(summary)
    result = {
        "scale": BOUNDED_SCALE,
        "execution_mode": "bounded",
        "policy": policy,
        "status": str(payload.get("execution_status", "BOUNDED_PROGRESS")),
        "input": dict(descriptor),
        "progress": {
            "requested_bags": len(rows),
            "released_bags": _integer(frontier.get("released_bags")) or 0,
            "completed_bags": completed,
            "failed_bags": _integer(frontier.get("failed_bags")) or 0,
            "current_backlog": _integer(frontier.get("current_backlog")) or 0,
            "completion_fraction": completed / len(rows) if rows else None,
            "simulated_time": _finite(frontier.get("simulated_time")),
            "history_source": history_source,
        },
        "metrics": {
            "mean_tth_seconds": None,
            "p95_tth_seconds": None,
            "p99_tth_seconds": None,
            "source_wait_mean_seconds": None,
            "route_wait_mean_seconds": None,
            "merge_grant_wait_mean_seconds": None,
            "network_time_mean_seconds": None,
            "event_count": events,
            "congestion_beacon_event_count": (
                _integer(event_types.get("congestion_beacon_update")) or 0
            ),
            "events_per_completed_bag": events / completed if completed else None,
            "events_per_wall_second": slopes.get("events_per_wall_second"),
            "completions_per_wall_second": slopes.get("completions_per_wall_second"),
        },
        "hotpath": hotpath,
        "hard_safety": safety,
        "resources": {
            "bounded_wall_seconds": bounded_wall_seconds,
            "bounded_check_every_events": check_events,
            "native_wall_seconds": wall_seconds,
            "native_process_cpu_seconds": cpu_seconds,
            "native_cpu_to_wall_ratio": cpu_seconds / wall_seconds if wall_seconds > 0.0 else None,
        },
    }
    return result, None


def execute_job(
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    *,
    scale: int,
    policy: str,
    binary: Path,
    root: Path,
    bounded_wall_seconds: float,
    check_events: int,
    executor: Executor,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    request = build_native_request(
        rows,
        scale=scale,
        policy=policy,
        binary=binary,
        root=root,
        bounded_wall_seconds=bounded_wall_seconds,
        check_events=check_events,
    )
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = executor(**request)
    cpu_seconds = time.process_time() - cpu_started
    wall_seconds = time.perf_counter() - wall_started
    _require(isinstance(payload, Mapping), "native payload is not an object")
    if scale in FULL_SCALES:
        return _full_result(
            payload,
            rows=rows,
            descriptor=descriptor,
            scale=scale,
            policy=policy,
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
        )
    return _bounded_result(
        payload,
        rows=rows,
        descriptor=descriptor,
        policy=policy,
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        bounded_wall_seconds=bounded_wall_seconds,
        check_events=check_events,
    )


def build_comparisons(
    rows: Sequence[Mapping[str, Any]],
    semantics: Mapping[tuple[int, str], Mapping[str, Any] | None],
) -> list[dict[str, Any]]:
    by_key = {(int(row["scale"]), str(row["policy"])): row for row in rows}
    comparisons: list[dict[str, Any]] = []
    for scale in ALL_SCALES:
        baseline = by_key[(scale, "E0")]
        for policy in POLICIES:
            treatment = by_key[(scale, policy)]
            base_metrics = baseline["metrics"]
            metrics = treatment["metrics"]
            if scale in FULL_SCALES:
                base_semantic = semantics[(scale, "E0")]
                semantic = semantics[(scale, policy)]
                _require(base_semantic is not None and semantic is not None, "missing full semantic projection")
                action_equal = semantic["actions"] == base_semantic["actions"]
                tth_equal = _close(semantic["tth"], base_semantic["tth"])
                route_wait_equal = _close(
                    semantic["route_wait_by_task"],
                    base_semantic["route_wait_by_task"],
                )
                safety_equal = semantic["hard_safety"] == base_semantic["hard_safety"]
                nonregression = all(
                    _finite(metrics.get(name)) is not None
                    and _finite(base_metrics.get(name)) is not None
                    and float(metrics[name])
                    <= float(base_metrics[name]) + TTH_ABS_TOLERANCE_SECONDS
                    for name in ("mean_tth_seconds", "p95_tth_seconds", "p99_tth_seconds")
                )
                semantic_gate = bool(
                    action_equal
                    and tth_equal
                    and route_wait_equal
                    and safety_equal
                    and nonregression
                    and treatment["hard_safety"]["pass"]
                )
            else:
                action_equal = tth_equal = route_wait_equal = safety_equal = nonregression = semantic_gate = None
            comparisons.append(
                {
                    "scale": scale,
                    "policy": policy,
                    "baseline_policy": "E0",
                    "action_semantics_equal_to_e0": action_equal,
                    "tth_semantics_equal_to_e0": tth_equal,
                    "route_wait_semantics_equal_to_e0": route_wait_equal,
                    "hard_safety_equal_to_e0": safety_equal,
                    "tth_nonregression_vs_e0": nonregression,
                    "full_semantic_gate_pass": semantic_gate,
                    "event_count_delta_vs_e0": (
                        (_integer(metrics.get("event_count")) or 0)
                        - (_integer(base_metrics.get("event_count")) or 0)
                    ),
                    "beacon_reduction_fraction": _reduction(
                        base_metrics.get("congestion_beacon_event_count"),
                        metrics.get("congestion_beacon_event_count"),
                    ),
                    "events_per_completed_bag_reduction_fraction": _reduction(
                        base_metrics.get("events_per_completed_bag"),
                        metrics.get("events_per_completed_bag"),
                    ),
                    "events_per_second_improvement_fraction": _improvement(
                        base_metrics.get("events_per_wall_second"),
                        metrics.get("events_per_wall_second"),
                    ),
                    "completion_improvement_fraction": _improvement(
                        baseline["progress"].get("completed_bags"),
                        treatment["progress"].get("completed_bags"),
                    ),
                }
            )
    return comparisons


def select_best_policy(comparisons: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_policy = {policy: [row for row in comparisons if row["policy"] == policy] for policy in POLICIES}
    candidates: list[dict[str, Any]] = []
    for policy in ("E1", "E2"):
        rows = by_policy[policy]
        full = [row for row in rows if row["scale"] in FULL_SCALES]
        bounded = next(row for row in rows if row["scale"] == BOUNDED_SCALE)

        def maximum(name: str) -> float | None:
            values = [_finite(row.get(name)) for row in rows]
            present = [value for value in values if value is not None]
            return max(present) if present else None

        evidence = {
            "beacon_reduction_fraction": maximum("beacon_reduction_fraction"),
            "events_per_completed_bag_reduction_fraction": maximum(
                "events_per_completed_bag_reduction_fraction"
            ),
            "bounded_events_per_second_improvement_fraction": _finite(
                bounded.get("events_per_second_improvement_fraction")
            ),
            "bounded_completion_improvement_fraction": _finite(
                bounded.get("completion_improvement_fraction")
            ),
        }
        mechanism_checks = {
            name: value is not None and value + 1.0e-12 >= MECHANISM_THRESHOLDS[name]
            for name, value in evidence.items()
        }
        full_gate = len(full) == len(FULL_SCALES) and all(
            row.get("full_semantic_gate_pass") is True for row in full
        )
        # An event-policy optimization is useful only if the 4x live frontier
        # does not regress.  Events/s alone is not comparable after deleting
        # cheap no-op events, so use completed work and events per completion.
        bounded_completion = _finite(
            bounded.get("completion_improvement_fraction")
        )
        bounded_efficiency = _finite(
            bounded.get("events_per_completed_bag_reduction_fraction")
        )
        bounded_nonregression = bool(
            bounded_completion is not None
            and bounded_efficiency is not None
            and bounded_completion >= -1.0e-12
            and bounded_efficiency >= -1.0e-12
        )
        candidates.append(
            {
                "policy": policy,
                "full_semantic_gate_pass": full_gate,
                "mechanism_checks": mechanism_checks,
                "mechanism_gate_pass": any(mechanism_checks.values()),
                "bounded_work_nonregression_pass": bounded_nonregression,
                "eligible": full_gate and bounded_nonregression and any(mechanism_checks.values()),
                "evidence": evidence,
            }
        )
    eligible = [row for row in candidates if row["eligible"]]
    if eligible:
        def score(row: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
            evidence = row["evidence"]
            return (
                _finite(evidence["bounded_completion_improvement_fraction"]) or -math.inf,
                _finite(evidence["bounded_events_per_second_improvement_fraction"]) or -math.inf,
                _finite(evidence["beacon_reduction_fraction"]) or -math.inf,
                _finite(evidence["events_per_completed_bag_reduction_fraction"]) or -math.inf,
                -POLICIES.index(str(row["policy"])),
            )

        winner = max(eligible, key=score)
        selected = str(winner["policy"])
        status = "SELECTED_EVENT_PUBLICATION_RESEARCH_POLICY"
        reason = "SEMANTICS_AND_EVENT_MECHANISM_GATES_PASSED"
    else:
        selected = "E0"
        status = "E0_RETAINED"
        reason = "NO_EVENT_PUBLICATION_POLICY_PASSED_BOTH_GATES"
    return {
        "schema": BEST_POLICY_SCHEMA,
        "status": status,
        "selected_policy": selected,
        "runtime_controls": {"g4irsf20_event_hotpath_policy": selected},
        "selection_reason": reason,
        "thresholds": dict(MECHANISM_THRESHOLDS),
        "candidates": candidates,
        "claim_boundary": (
            "Fixed-map G19 S4/J2 event-publication policy only; no route, "
            "future-path, global-reservation, or production claim."
        ),
    }


CSV_FIELDS = (
    "scale",
    "execution_mode",
    "policy",
    "status",
    "requested_bags",
    "released_bags",
    "completed_bags",
    "failed_bags",
    "current_backlog",
    "event_count",
    "congestion_beacon_event_count",
    "redundant_beacon_suppressed_count",
    "same_state_beacon_suppressed_count",
    "events_per_completed_bag",
    "events_per_wall_second",
    "mean_tth_seconds",
    "p95_tth_seconds",
    "p99_tth_seconds",
    "hard_safety_pass",
    "action_semantics_equal_to_e0",
    "tth_semantics_equal_to_e0",
    "route_wait_semantics_equal_to_e0",
    "hard_safety_equal_to_e0",
    "full_semantic_gate_pass",
    "beacon_reduction_fraction",
    "events_per_completed_bag_reduction_fraction",
    "events_per_second_improvement_fraction",
    "completion_improvement_fraction",
)


def render_csv(rows: Sequence[Mapping[str, Any]], comparisons: Sequence[Mapping[str, Any]]) -> str:
    comparison = {(row["scale"], row["policy"]): row for row in comparisons}
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        metrics = row["metrics"]
        progress = row["progress"]
        hotpath = row["hotpath"]
        pair = comparison[(row["scale"], row["policy"])]
        writer.writerow(
            {
                "scale": row["scale"],
                "execution_mode": row["execution_mode"],
                "policy": row["policy"],
                "status": row["status"],
                **{name: progress.get(name) for name in (
                    "requested_bags", "released_bags", "completed_bags", "failed_bags", "current_backlog"
                )},
                **{name: metrics.get(name) for name in (
                    "event_count", "congestion_beacon_event_count", "events_per_completed_bag",
                    "events_per_wall_second", "mean_tth_seconds", "p95_tth_seconds", "p99_tth_seconds"
                )},
                "redundant_beacon_suppressed_count": hotpath["redundant_beacon_suppressed_count"],
                "same_state_beacon_suppressed_count": hotpath["same_state_beacon_suppressed_count"],
                "hard_safety_pass": row["hard_safety"]["pass"],
                **{name: pair.get(name) for name in CSV_FIELDS if name in pair},
            }
        )
    return stream.getvalue()


def _fmt(value: Any) -> str:
    number = _finite(value)
    if number is None:
        return "-" if value is None else str(value)
    return f"{number:.6f}"


def render_report(campaign: Mapping[str, Any]) -> str:
    comparisons = {(row["scale"], row["policy"]): row for row in campaign["comparisons"]}
    lines = [
        "# G4IRSF20 event hotpath paired ladder",
        "",
        "E0/E1/E2 use the same fixed-map input and frozen A0 + S4 + J2 controls. "
        "Event counts may change; 1x/2x action, per-task TTH, and hard-safety semantics may not.",
        "For full rows, completed work is reported as raw tasks over input segments; "
        "`COMPLETE` means every raw task finished. Bounded 4x rows report completed segments.",
        "Action parity uses each bag's final/count/last-eight projection, not a full trace; "
        "per-task TTH and route-wait projections cover every completed raw task.",
        "",
        "| scale | mode | policy | status | completed work / input | events | beacon events | suppressed | events/complete | events/s | mean TTH s | full semantics |",
        "|---:|:---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in campaign["rows"]:
        pair = comparisons[(row["scale"], row["policy"])]
        progress = row["progress"]
        metrics = row["metrics"]
        completed_work = (
            f"{progress['completed_bags']} raw tasks / {progress['requested_bags']} segments"
            if row["execution_mode"] == "full"
            else f"{progress['completed_bags']} / {progress['requested_bags']} segments"
        )
        lines.append(
            f"| {row['scale']}x | {row['execution_mode']} | {row['policy']} | {row['status']} | "
            f"{completed_work} | {metrics['event_count']} | "
            f"{metrics['congestion_beacon_event_count']} | {row['hotpath']['total_beacon_suppressed_count']} | "
            f"{_fmt(metrics['events_per_completed_bag'])} | {_fmt(metrics['events_per_wall_second'])} | "
            f"{_fmt(metrics['mean_tth_seconds'])} | {_fmt(pair['full_semantic_gate_pass'])} |"
        )
    selection = campaign["selection"]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Status: **{selection['status']}**",
            f"- Selected policy: **{selection['selected_policy']}**",
            f"- Reason: `{selection['selection_reason']}`",
            "",
            "The 4x row is a bounded live-frontier observation, not a completed-capacity claim. "
            "A reduction in events without TTH or 4x progress movement is reported as software-overhead reduction, not physical-capacity improvement.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_campaign(
    *,
    binary: Path,
    root: Path = ROOT,
    policies: Sequence[str] = POLICIES,
    bounded_wall_seconds: float = 60.0,
    check_events: int = 65_536,
    json_path: Path = DEFAULT_JSON,
    csv_path: Path = DEFAULT_CSV,
    report_path: Path = DEFAULT_REPORT,
    best_policy_path: Path = DEFAULT_BEST_POLICY,
    executor: Executor | None = None,
    input_loader: InputLoader = g19_capacity.load_g18_scale_input,
) -> dict[str, Any]:
    normalized = tuple(str(policy) for policy in policies)
    _require(normalized == POLICIES, "paired ladder must run E0, E1, E2 in order")
    _require(bounded_wall_seconds > 0.0, "bounded wall seconds must be positive")
    _require(type(check_events) is int and check_events > 0, "check events must be positive")
    if executor is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        executor = g4irsf11_event_runtime_from_records
    results: list[dict[str, Any]] = []
    semantics: dict[tuple[int, str], Mapping[str, Any] | None] = {}
    for scale in ALL_SCALES:
        input_started = time.perf_counter()
        input_rows, descriptor = input_loader(scale, root)
        input_seconds = time.perf_counter() - input_started
        _require(bool(input_rows), "input loader returned no rows")
        _require(descriptor.get("topology_changed") is False, "scale input changed topology")
        _require(_integer(descriptor.get("segments")) == len(input_rows), "input segment count drift")
        for policy in normalized:
            result, semantic = execute_job(
                input_rows,
                descriptor,
                scale=scale,
                policy=policy,
                binary=binary,
                root=root,
                bounded_wall_seconds=bounded_wall_seconds,
                check_events=check_events,
                executor=executor,
            )
            result["resources"]["input_preparation_wall_seconds"] = input_seconds
            results.append(result)
            semantics[(scale, policy)] = semantic
    comparisons = build_comparisons(results, semantics)
    selection = select_best_policy(comparisons)
    campaign = {
        "schema": SCHEMA,
        "status": (
            "COMPLETE"
            if all(row["status"] in {"COMPLETE", "BOUNDED_PROGRESS"} for row in results)
            else "GATE_FAILED"
        ),
        "design": {
            "fixed_topology": True,
            "frozen_controller": "Source A0 + Route S4 + Merge J2",
            "policies": list(POLICIES),
            "full_scales": list(FULL_SCALES),
            "bounded_scale": BOUNDED_SCALE,
            "bounded_wall_seconds": bounded_wall_seconds,
            "raw_rows_persisted": False,
            "event_count_may_change_under_semantic_parity": True,
            "action_semantics_projection": (
                "per-segment final node, completion/failure, decision/retry/loop "
                "counts, and bounded recent executed-node history"
            ),
            "tth_semantics_projection": "exact per-task completed timing tuple",
            "route_wait_semantics_projection": "exact per-task aggregate junction wait",
        },
        "rows": results,
        "comparisons": comparisons,
        "selection": selection,
    }
    g19_capacity._atomic_json(json_path, campaign)
    g19_capacity._atomic_text(csv_path, render_csv(results, comparisons))
    g19_capacity._atomic_text(report_path, render_report(campaign))
    g19_capacity._atomic_json(best_policy_path, selection)
    return campaign


def _positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    parser.add_argument("--bounded-wall-s", type=_positive_float, default=60.0)
    parser.add_argument("--check-events", type=_positive_int, default=65_536)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--best-policy", type=Path, default=DEFAULT_BEST_POLICY)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        campaign = run_campaign(
            binary=_rooted(root, args.binary),
            root=root,
            policies=args.policies,
            bounded_wall_seconds=args.bounded_wall_s,
            check_events=args.check_events,
            json_path=_rooted(root, args.json),
            csv_path=_rooted(root, args.csv),
            report_path=_rooted(root, args.report),
            best_policy_path=_rooted(root, args.best_policy),
        )
        print(
            json.dumps(
                {
                    "status": campaign["status"],
                    "row_count": len(campaign["rows"]),
                    "selected_policy": campaign["selection"]["selected_policy"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if campaign["status"] == "COMPLETE" else 2
    except (EventHotpathError, OSError, ValueError, TypeError) as exc:
        print(f"G20 event hotpath campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
