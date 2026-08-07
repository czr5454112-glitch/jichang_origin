#!/usr/bin/env python3
"""Run the minimal G19 Route scorer ablation on the real native runtime.

The campaign changes one existing one-hop Route scorer at a time while holding
the G18 J2 timing/merge boundary and every other frozen runtime control fixed.
S1 is the paired baseline; S2, S3 and S4 are treatments.  Small evidence cases
retain decision rows only long enough to match same-state choices and then
discard them.  Capacity cases disable decision/event traces entirely.

This is fixed-workload research evidence.  It neither trains a new model nor
adds a second routing framework around the native event loop.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import csv
from dataclasses import asdict, dataclass
import io
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


SCHEMA_CASE_RESULT = "czr005.g4irsf19.route_case_result.v1"
SCHEMA_CAMPAIGN = "czr005.g4irsf19.route_campaign.v1"

DEFAULT_PREFIXES = (144, 512, 2_048, 8_192)
DEFAULT_EVIDENCE_PREFIXES = (144, 512)
ALLOWED_PREFIXES = DEFAULT_PREFIXES
ALLOWED_SCALES = (1, 2)
DEFAULT_DECISION_TRACE_LIMIT = 500_000

DEFAULT_RESULTS = ROOT / "outputs/runtime/g4irsf19_route_campaign"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf19_route_campaign.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf19_route_campaign.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf19_route_campaign.md"

J2_TIMING_MODE = "jit_fair_aging_deadline"
J2_MERGE_RULE = "M3"

METRIC_FIELDS = (
    "mean_tth_seconds",
    "median_tth_seconds",
    "p95_tth_seconds",
    "p99_tth_seconds",
    "max_tth_seconds",
    "source_wait_mean_seconds",
    "route_wait_mean_seconds",
    "merge_grant_wait_mean_seconds",
    "network_time_mean_seconds",
    "event_count",
    "loop_count",
    "fairness_jain",
)


class RouteCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RouteCampaignError(message)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_bytes(path, payload)


def _atomic_text(path: Path, value: str) -> None:
    _atomic_bytes(path, value.encode("utf-8"))


@dataclass(frozen=True)
class RouteArm:
    arm_id: str
    scorer_mode: str
    uses_model: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ROUTE_ARMS = (
    RouteArm("S1", "S1_frozen_g4e_legal_local_adapter", True),
    RouteArm("S2", "S2_frozen_g4e_without_absolute_node_ids", True),
    RouteArm("S3", "S3_shortest_potential_only", False),
    RouteArm("S4", "S4_queue_aware_rule_only", False),
)
ARM_BY_ID = {arm.arm_id: arm for arm in ROUTE_ARMS}


@dataclass(frozen=True)
class RouteCase:
    case_id: str
    kind: str
    telemetry_mode: str
    prefix_segments: int | None = None
    scale: int = 1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_cases(
    *,
    prefixes: Sequence[int] = DEFAULT_PREFIXES,
    evidence_prefixes: Sequence[int] = DEFAULT_EVIDENCE_PREFIXES,
    scales: Sequence[int] = (),
) -> list[RouteCase]:
    prefix_values = tuple(dict.fromkeys(int(value) for value in prefixes))
    evidence_values = frozenset(int(value) for value in evidence_prefixes)
    scale_values = tuple(dict.fromkeys(int(value) for value in scales))
    _require(bool(prefix_values) or bool(scale_values), "campaign has no cases")
    _require(
        all(value in ALLOWED_PREFIXES for value in prefix_values),
        "prefixes must be selected from the G18 fixed ladder",
    )
    _require(
        evidence_values.issubset(prefix_values),
        "evidence prefixes must be included in prefixes",
    )
    _require(
        all(value in ALLOWED_SCALES for value in scale_values),
        "optional capacity scales are limited to 1x and 2x",
    )
    cases = [
        RouteCase(
            case_id=f"prefix_{prefix}",
            kind="prefix",
            telemetry_mode=(
                "evidence_trace" if prefix in evidence_values else "capacity"
            ),
            prefix_segments=prefix,
            scale=1,
        )
        for prefix in prefix_values
    ]
    cases.extend(
        RouteCase(
            case_id=f"scale_{scale}x",
            kind="scale",
            telemetry_mode="capacity",
            prefix_segments=None,
            scale=scale,
        )
        for scale in scale_values
    )
    _require(len({case.case_id for case in cases}) == len(cases), "duplicate case ID")
    return cases


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("metadata")
    return value if isinstance(value, Mapping) else {}


def _selected_next(row: Mapping[str, Any]) -> int | None:
    for name in ("selected_next", "selected_next_node"):
        value = _integer(row.get(name))
        if value is not None:
            return value
    return None


def _candidate_nodes(row: Mapping[str, Any]) -> tuple[int, ...] | None:
    value = row.get("candidate_next_nodes")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        records = row.get("candidate_records")
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            return None
        value = [
            record.get("next_node")
            for record in records
            if isinstance(record, Mapping)
        ]
    nodes: list[int] = []
    for item in value:
        parsed = _integer(item)
        if parsed is None:
            return None
        nodes.append(parsed)
    return tuple(sorted(set(nodes))) if nodes else None


def _state_key(row: Mapping[str, Any]) -> tuple[Any, ...] | None:
    segment = row.get("segment_id")
    task = _integer(row.get("task_id"))
    current = _integer(row.get("current_node"))
    goal = _integer(row.get("goal_node"))
    candidates = _candidate_nodes(row)
    if (
        not isinstance(segment, str)
        or not segment
        or task is None
        or current is None
        or goal is None
        or candidates is None
        or _selected_next(row) is None
    ):
        return None
    # Repeated visits to the same local state are paired in trace order.  The
    # immutable segment/task identity prevents cross-bag matches.
    return segment, task, current, goal, candidates


def _risk_fallback(row: Mapping[str, Any]) -> bool:
    metadata = _metadata(row)
    return any(
        value is True
        for value in (
            row.get("risk_gate_triggered"),
            row.get("scorer_risk_abstain"),
            metadata.get("scorer_risk_abstain"),
        )
    )


def _shield_fallback(row: Mapping[str, Any]) -> bool:
    metadata = _metadata(row)
    explicit = (
        "shield_fallback_triggered",
        "safety_shield_triggered",
        "physical_fault_shield_triggered",
        "physical_fault_interlock_rejected",
    )
    if any(row.get(name) is True or metadata.get(name) is True for name in explicit):
        return True
    source = str(row.get("decision_source", "")).lower()
    reason = str(row.get("rule_reason", "")).lower()
    return "shield" in source or "shield" in reason or "physical_interlock" in reason


def _scorer_prediction(row: Mapping[str, Any]) -> int | None:
    metadata = _metadata(row)
    for value in (
        metadata.get("scorer_raw_prediction"),
        row.get("scorer_raw_prediction"),
        row.get("model_prediction"),
    ):
        parsed = _integer(value)
        if parsed is not None:
            return parsed
    return None


def _trace_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    valid = [row for row in rows if _state_key(row) is not None]
    return {
        "stored_rows": len(rows),
        "state_observable_rows": len(valid),
        "state_unobservable_rows": len(rows) - len(valid),
        "branch_opportunity_rows": sum(
            1 for row in valid if len(_candidate_nodes(row) or ()) >= 2
        ),
        "risk_fallback_rows": sum(1 for row in valid if _risk_fallback(row)),
        "shield_fallback_rows": sum(1 for row in valid if _shield_fallback(row)),
        "configured_scorer_ownership_rows": sum(
            1
            for row in valid
            if not _risk_fallback(row)
            and not _shield_fallback(row)
            and _scorer_prediction(row) is not None
            and _selected_next(row) == _scorer_prediction(row)
        ),
    }


def compact_route_mutations(
    baseline_rows: Sequence[Mapping[str, Any]],
    treatment_rows: Sequence[Mapping[str, Any]],
    *,
    baseline_truncated: bool = False,
    treatment_truncated: bool = False,
    telemetry_enabled: bool = True,
) -> dict[str, Any]:
    """Match same local states and return counters, never raw decisions.

    The match key is exactly the observable local identity available in the
    existing trace: segment, task, current node, goal and the sorted candidate
    next-node set.  Repeated equal keys are paired FIFO.  Consequently the
    mutation count is an observed lower bound when trajectories diverge or a
    trace is truncated; it is not presented as a full counterfactual replay.
    """

    if not telemetry_enabled:
        return {
            "status": "NOT_COLLECTED_CAPACITY_MODE",
            "claim_boundary": (
                "Capacity mode disables decision and event traces; business and "
                "native summary metrics remain available, Route mutations do not."
            ),
            "baseline": _trace_counts(()),
            "treatment": _trace_counts(()),
            "matched_state_rows": 0,
            "matched_branch_opportunity_rows": 0,
            "distinct_selected_next_mutation_count": None,
            "distinct_selected_next_mutation_rate": None,
            "captured_trace_mutation_upper_bound": None,
            "complete_trace_mutation_upper_bound": None,
        }

    baseline_counts = _trace_counts(baseline_rows)
    treatment_counts = _trace_counts(treatment_rows)
    treatment_by_state: dict[tuple[Any, ...], deque[Mapping[str, Any]]] = defaultdict(deque)
    for row in treatment_rows:
        key = _state_key(row)
        if key is not None:
            treatment_by_state[key].append(row)

    matched = 0
    matched_branch = 0
    mutations = 0
    matched_risk = 0
    matched_shield = 0
    for baseline in baseline_rows:
        key = _state_key(baseline)
        if key is None or not treatment_by_state[key]:
            continue
        treatment = treatment_by_state[key].popleft()
        matched += 1
        branch = len(key[-1]) >= 2
        if branch:
            matched_branch += 1
            if _selected_next(baseline) != _selected_next(treatment):
                mutations += 1
        if _risk_fallback(baseline) or _risk_fallback(treatment):
            matched_risk += 1
        if _shield_fallback(baseline) or _shield_fallback(treatment):
            matched_shield += 1

    unmatched_baseline_branch = max(
        0, baseline_counts["branch_opportunity_rows"] - matched_branch
    )
    unmatched_treatment_branch = max(
        0, treatment_counts["branch_opportunity_rows"] - matched_branch
    )
    captured_upper = mutations + min(
        unmatched_baseline_branch, unmatched_treatment_branch
    )
    complete_observation = (
        not baseline_truncated
        and not treatment_truncated
        and baseline_counts["state_unobservable_rows"] == 0
        and treatment_counts["state_unobservable_rows"] == 0
    )
    if baseline_truncated or treatment_truncated:
        status = "OBSERVED_LOWER_BOUND_TRACE_TRUNCATED"
    elif not complete_observation:
        status = "OBSERVED_LOWER_BOUND_FIELDS_MISSING"
    else:
        status = "COMPLETE_CAPTURE_SAME_STATE_MATCH"
    return {
        "status": status,
        "claim_boundary": (
            "Same-state trace matching is an observed mutation lower bound, not "
            "a cloned-state counterfactual. Unmatched divergent trajectories are "
            "reported instead of inferred."
        ),
        "match_key": [
            "segment_id",
            "task_id",
            "current_node",
            "goal_node",
            "sorted_unique_candidate_next_nodes",
            "FIFO_occurrence_within_equal_key",
        ],
        "baseline": baseline_counts,
        "treatment": treatment_counts,
        "matched_state_rows": matched,
        "matched_branch_opportunity_rows": matched_branch,
        "unmatched_baseline_branch_rows": unmatched_baseline_branch,
        "unmatched_treatment_branch_rows": unmatched_treatment_branch,
        "distinct_selected_next_mutation_count": mutations,
        "distinct_selected_next_mutation_rate": (
            mutations / matched_branch if matched_branch else None
        ),
        "matched_rows_with_risk_fallback": matched_risk,
        "matched_rows_with_shield_fallback": matched_shield,
        "captured_trace_mutation_upper_bound": captured_upper,
        "complete_trace_mutation_upper_bound": (
            captured_upper if complete_observation else None
        ),
    }


def load_case_input(
    case: RouteCase, *, root: Path = ROOT
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from scripts.eval import run_g4irsf18_system_campaign as g18

    job = g18.SystemJob(
        job_id=f"g19_route_{case.case_id}",
        stage="ladder" if case.kind == "prefix" else "scale",
        arm_id="J2",
        prefix_segments=case.prefix_segments,
        scale=case.scale,
        max_segments=-1,
        telemetry_mode=case.telemetry_mode,
    )
    return g18._load_input(job, root)


def load_fixed_graph() -> tuple[Any, Any, Any]:
    from scripts.eval.g4irsf11_fixed_map import (
        assert_canonical_map,
        canonical_graph_records,
    )

    return canonical_graph_records(assert_canonical_map())


def build_runtime_request(
    case: RouteCase,
    arm: RouteArm,
    *,
    rows: Sequence[Mapping[str, Any]],
    graph: tuple[Any, Any, Any],
    binary: Path,
    model_path: Path,
    decision_trace_limit: int = DEFAULT_DECISION_TRACE_LIMIT,
) -> dict[str, Any]:
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS
    from scripts.eval import run_g4irsf18_jit_campaign as jit

    _require(decision_trace_limit > 0, "decision trace limit must be positive")
    nodes, edges, heuristic = graph
    evidence = case.telemetry_mode == "evidence_trace"
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=jit._binding_rows(rows),
        fault_windows=(),
        scenario=f"g4irsf19_route_{case.case_id}_{arm.arm_id}",
        summary_only=False,
        trace_limit=decision_trace_limit if evidence else 0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        expected_binary_path=binary,
        search_path=binary.parent,
        g4irsf16_supervisor_mode="off",
        merge_grant_rule=J2_MERGE_RULE,
        merge_grant_timing_mode=J2_TIMING_MODE,
        scorer_mode=arm.scorer_mode,
    )
    if arm.uses_model:
        request["scorer_model_path"] = model_path
    else:
        # The wrapper intentionally rejects a model path for pure rules S3/S4.
        request.pop("scorer_model_path", None)
    return request


def _task_sum(
    segment_rows: Sequence[Mapping[str, Any]], field: str
) -> dict[int, float]:
    result: dict[int, float] = defaultdict(float)
    for row in segment_rows:
        task = _integer(row.get("task_id"))
        value = _finite(row.get(field))
        if task is not None and value is not None:
            result[task] += value
    return dict(result)


def summarize_payload(
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    arm: RouteArm,
    wall_seconds: float,
    cpu_seconds: float,
) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
    from scripts.eval import run_g4irsf18_jit_campaign as jit

    summary = payload.get("summary")
    bags = payload.get("bags")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(isinstance(bags, list), "native payload lacks bag rows")
    _require(
        summary.get("merge_grant_timing_mode") == J2_TIMING_MODE,
        "native J2 timing echo drift",
    )
    _require(summary.get("scorer_mode") == arm.scorer_mode, "scorer echo drift")

    raw = jit._raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    all_complete = len(completed) == len(raw)
    tth = [float(row["tth_seconds"]) for row in completed]
    source = [float(row["source_wait_seconds"]) for row in completed]
    merge = [float(row["merge_grant_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    complete_tasks = {int(row["task_id"]) for row in completed}
    route_by_task = _task_sum(bags, "junction_queue_wait_seconds")
    route = [route_by_task.get(task, 0.0) for task in complete_tasks]
    safety = jit._hard_safety(summary, len(rows))
    event_count = _integer(summary.get("event_count"))
    loop_count = _integer(summary.get("loop_count"))
    fairness = _finite(summary.get("fairness_jain"))
    status = (
        "COMPLETE"
        if safety["pass"] and all_complete
        else (
            "CAPACITY_CENSORED_EVENT_LIMIT"
            if summary.get("event_limit_reached") is True
            else (
                "CAPACITY_CENSORED_SIMULATION_TIME"
                if summary.get("time_limit_reached") is True
                else "HARD_GATE_FAILED"
            )
        )
    )
    decisions = payload.get("decision_trace", payload.get("decisions", []))
    _require(isinstance(decisions, list), "native decision trace is not a list")
    decision_rows = [row for row in decisions if isinstance(row, Mapping)]
    _require(
        len(decision_rows) == len(decisions),
        "native decision trace contains a non-object row",
    )
    result = {
        "arm": arm.as_dict(),
        "status": status,
        "hard_safety": safety,
        "resources": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
        },
        "metrics": {
            "requested_segments": len(rows),
            "raw_bag_count": len(raw),
            "complete_raw_bag_count": len(completed),
            "mean_tth_seconds": statistics.fmean(tth) if all_complete and tth else None,
            "median_tth_seconds": _quantile(tth, 0.50) if all_complete else None,
            "p95_tth_seconds": _quantile(tth, 0.95) if all_complete else None,
            "p99_tth_seconds": _quantile(tth, 0.99) if all_complete else None,
            "max_tth_seconds": max(tth) if all_complete and tth else None,
            "source_wait_mean_seconds": (
                statistics.fmean(source) if all_complete and source else None
            ),
            # This is the sum of native junction queue waits per raw task.
            # Merge-grant wait is a diagnostic subset, not an additive term.
            "route_wait_mean_seconds": (
                statistics.fmean(route) if all_complete and route else None
            ),
            "merge_grant_wait_mean_seconds": (
                statistics.fmean(merge) if all_complete and merge else None
            ),
            "network_time_mean_seconds": (
                statistics.fmean(network) if all_complete and network else None
            ),
            "event_count": event_count,
            "events_per_requested_segment": (
                event_count / len(rows) if event_count is not None and rows else None
            ),
            "loop_count": loop_count,
            "loops_per_raw_bag": (
                loop_count / len(raw) if loop_count is not None and raw else None
            ),
            "fairness_jain": fairness,
        },
        "telemetry": {
            "mode": (
                "evidence_trace"
                if _integer(summary.get("trace_limit")) not in (None, 0)
                else "capacity"
            ),
            "decision_trace_seen_count": summary.get("decision_trace_seen_count"),
            "decision_trace_stored_count": summary.get("decision_trace_stored_count"),
            "decision_trace_truncated": summary.get("decision_trace_truncated"),
            "raw_rows_persisted": False,
        },
        "counters": {
            name: summary.get(name)
            for name in (
                "event_count",
                "decision_count",
                "loop_count",
                "fairness_jain",
                "scorer_decision_evaluation_count",
                "scorer_candidate_evaluation_count",
                "scorer_risk_abstain_count",
                "shield_rejection_count",
                "physical_fault_interlock_rejection_count",
                "reservation_conflicts",
                "unresolved_deadlock_count",
            )
        },
    }
    return result, decision_rows


Executor = Callable[[Mapping[str, Any]], Mapping[str, Any]]
InputLoader = Callable[[RouteCase], tuple[list[dict[str, Any]], dict[str, Any]]]


def execute_case(
    case: RouteCase,
    *,
    binary: Path,
    root: Path = ROOT,
    decision_trace_limit: int = DEFAULT_DECISION_TRACE_LIMIT,
    executor: Executor | None = None,
    input_loader: InputLoader | None = None,
    graph: tuple[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    from scripts.eval.g4irsf14_opportunity_census import MODEL_PATH

    resolved_binary = binary if executor is not None else binary.resolve(strict=True)
    loader = input_loader or (lambda value: load_case_input(value, root=root))
    rows, descriptor = loader(case)
    _require(bool(rows), "case input is empty")
    _require(descriptor.get("topology_changed") is False, "case changed topology")
    fixed_graph = graph if graph is not None else load_fixed_graph()
    model_path = (root / MODEL_PATH).resolve(strict=True)

    if executor is None:
        from czr005 import cpp_backend

        native_executor: Executor = lambda request: (
            cpp_backend.g4irsf11_event_runtime_from_records(**request)
        )
    else:
        native_executor = executor

    compact_arms: dict[str, dict[str, Any]] = {}
    transient_rows: dict[str, list[Mapping[str, Any]]] = {}
    for arm in ROUTE_ARMS:
        request = build_runtime_request(
            case,
            arm,
            rows=rows,
            graph=fixed_graph,
            binary=resolved_binary,
            model_path=model_path,
            decision_trace_limit=decision_trace_limit,
        )
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        payload = native_executor(request)
        cpu_seconds = time.process_time() - cpu_start
        wall_seconds = time.perf_counter() - wall_start
        _require(isinstance(payload, Mapping), "native executor returned a non-object")
        compact, decisions = summarize_payload(
            rows,
            descriptor,
            payload,
            arm=arm,
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
        )
        compact_arms[arm.arm_id] = compact
        transient_rows[arm.arm_id] = decisions

    comparisons: list[dict[str, Any]] = []
    baseline = compact_arms["S1"]
    baseline_metrics = baseline["metrics"]
    evidence = case.telemetry_mode == "evidence_trace"
    for treatment_id in ("S2", "S3", "S4"):
        treatment = compact_arms[treatment_id]
        treatment_metrics = treatment["metrics"]
        deltas = {
            field: (
                float(treatment_metrics[field]) - float(baseline_metrics[field])
                if _finite(treatment_metrics.get(field)) is not None
                and _finite(baseline_metrics.get(field)) is not None
                else None
            )
            for field in METRIC_FIELDS
        }
        mutation = compact_route_mutations(
            transient_rows["S1"],
            transient_rows[treatment_id],
            baseline_truncated=(
                baseline["telemetry"].get("decision_trace_truncated") is True
            ),
            treatment_truncated=(
                treatment["telemetry"].get("decision_trace_truncated") is True
            ),
            telemetry_enabled=evidence,
        )
        comparisons.append(
            {
                "baseline_arm": "S1",
                "treatment_arm": treatment_id,
                "baseline_status": baseline["status"],
                "treatment_status": treatment["status"],
                "baseline_hard_safety_pass": baseline["hard_safety"]["pass"],
                "treatment_hard_safety_pass": treatment["hard_safety"]["pass"],
                "baseline_metrics": dict(baseline_metrics),
                "treatment_metrics": dict(treatment_metrics),
                "treatment_minus_baseline": deltas,
                "route_mutation": mutation,
            }
        )

    # Raw decision rows intentionally leave scope here and are never returned
    # or serialized.  Only the compact same-state counts above survive.
    return {
        "schema": SCHEMA_CASE_RESULT,
        "case": case.as_dict(),
        "input": dict(descriptor),
        "runtime_contract": {
            "timing_mode": J2_TIMING_MODE,
            "merge_rule": J2_MERGE_RULE,
            "decision_trace_limit": decision_trace_limit,
            "scorer_only_ablation": True,
            "capacity_trace_disabled": case.telemetry_mode == "capacity",
            "route_wait_semantics": (
                "mean per raw task of summed native junction_queue_wait_seconds; "
                "merge_grant_wait_seconds is a diagnostic subset"
            ),
            "raw_decision_rows_persisted": False,
        },
        "arms": compact_arms,
        "comparisons": comparisons,
        "status": (
            "COMPLETE"
            if all(value["status"] == "COMPLETE" for value in compact_arms.values())
            else "INCOMPLETE"
        ),
    }


def _binary_descriptor(binary: Path) -> dict[str, Any]:
    resolved = binary.resolve(strict=True)
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _case_path(results_dir: Path, case: RouteCase) -> Path:
    return results_dir / f"g4irsf19_route_{case.case_id}.json"


def _read_case(
    path: Path,
    case: RouteCase,
    binary: Mapping[str, Any],
    decision_trace_limit: int,
) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(value, dict)
        and value.get("schema") == SCHEMA_CASE_RESULT
        and value.get("case") == case.as_dict()
        and value.get("binary") == binary
        and isinstance(value.get("runtime_contract"), Mapping)
        and value["runtime_contract"].get("decision_trace_limit")
        == decision_trace_limit
    ):
        return value
    return None


def _flatten_results(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in cases:
        case = result["case"]
        for comparison in result["comparisons"]:
            mutation = comparison["route_mutation"]
            baseline_metrics = comparison["baseline_metrics"]
            treatment_metrics = comparison["treatment_metrics"]
            deltas = comparison["treatment_minus_baseline"]
            row: dict[str, Any] = {
                "case_id": case["case_id"],
                "kind": case["kind"],
                "prefix_segments": case["prefix_segments"],
                "scale": case["scale"],
                "telemetry_mode": case["telemetry_mode"],
                "baseline_arm": comparison["baseline_arm"],
                "treatment_arm": comparison["treatment_arm"],
                "baseline_status": comparison["baseline_status"],
                "treatment_status": comparison["treatment_status"],
                "baseline_hard_safety_pass": comparison[
                    "baseline_hard_safety_pass"
                ],
                "treatment_hard_safety_pass": comparison[
                    "treatment_hard_safety_pass"
                ],
                "mutation_observability": mutation["status"],
                "baseline_branch_opportunity_rows": mutation["baseline"][
                    "branch_opportunity_rows"
                ],
                "treatment_branch_opportunity_rows": mutation["treatment"][
                    "branch_opportunity_rows"
                ],
                "matched_state_rows": mutation["matched_state_rows"],
                "matched_branch_opportunity_rows": mutation[
                    "matched_branch_opportunity_rows"
                ],
                "distinct_selected_next_mutation_count": mutation[
                    "distinct_selected_next_mutation_count"
                ],
                "distinct_selected_next_mutation_rate": mutation[
                    "distinct_selected_next_mutation_rate"
                ],
                "baseline_risk_fallback_rows": mutation["baseline"][
                    "risk_fallback_rows"
                ],
                "treatment_risk_fallback_rows": mutation["treatment"][
                    "risk_fallback_rows"
                ],
                "baseline_shield_fallback_rows": mutation["baseline"][
                    "shield_fallback_rows"
                ],
                "treatment_shield_fallback_rows": mutation["treatment"][
                    "shield_fallback_rows"
                ],
            }
            for field in METRIC_FIELDS:
                row[f"baseline_{field}"] = baseline_metrics.get(field)
                row[f"treatment_{field}"] = treatment_metrics.get(field)
                row[f"delta_{field}"] = deltas.get(field)
            rows.append(row)
    return rows


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _show(value: Any, digits: int = 4) -> str:
    parsed = _finite(value)
    return "-" if parsed is None else f"{parsed:.{digits}f}"


def _markdown(campaign: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF19 Route scorer paired campaign",
        "",
        "This campaign holds the existing G18 J2 timing/merge boundary fixed and "
        "changes only the native one-hop Route scorer (S1/S2/S3/S4). No new model "
        "is trained and no second routing framework is introduced.",
        "",
        "| Case | Pair | Trace | Safety B/T | Matched branch | Mutations | Mean TTH delta (s) | P95 delta (s) | Route-wait delta (s) | Events delta |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in campaign["rows"]:
        lines.append(
            "| "
            f"{row['case_id']} | S1/{row['treatment_arm']} | "
            f"{row['mutation_observability']} | "
            f"{row['baseline_hard_safety_pass']}/{row['treatment_hard_safety_pass']} | "
            f"{row['matched_branch_opportunity_rows']} | "
            f"{row['distinct_selected_next_mutation_count'] if row['distinct_selected_next_mutation_count'] is not None else '-'} | "
            f"{_show(row['delta_mean_tth_seconds'])} | "
            f"{_show(row['delta_p95_tth_seconds'])} | "
            f"{_show(row['delta_route_wait_mean_seconds'])} | "
            f"{_show(row['delta_event_count'], 0)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Evidence traces are matched by immutable segment/task identity, current "
            "node, goal and the candidate next-node set. A selected-next difference is "
            "a directly observed mutation. Unmatched divergent trajectories and any "
            "truncation remain explicit, so the mutation count is a lower bound rather "
            "than a cloned-state counterfactual claim.",
            "",
            "Capacity cases deliberately retain no decision or event rows. They report "
            "only paired business, safety and native summary metrics. Route wait is the "
            "per-raw-task sum of native junction queue wait; merge-grant wait is a "
            "diagnostic subset and must not be added to it.",
            "",
            "This fixed-map result is research evidence, not production promotion "
            "authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def run_campaign(
    cases: Sequence[RouteCase],
    *,
    binary: Path,
    root: Path = ROOT,
    results_dir: Path = DEFAULT_RESULTS,
    json_path: Path = DEFAULT_JSON,
    csv_path: Path = DEFAULT_CSV,
    report_path: Path = DEFAULT_REPORT,
    decision_trace_limit: int = DEFAULT_DECISION_TRACE_LIMIT,
    force: bool = False,
    only_case: str | None = None,
) -> dict[str, Any]:
    descriptor = _binary_descriptor(binary)
    selected = [case for case in cases if only_case in (None, case.case_id)]
    _require(bool(selected), f"unknown or empty --only-case: {only_case}")
    results: list[dict[str, Any]] = []
    for case in selected:
        path = _case_path(results_dir, case)
        cached = (
            None
            if force
            else _read_case(path, case, descriptor, decision_trace_limit)
        )
        if cached is not None:
            result = cached
        else:
            result = execute_case(
                case,
                binary=binary,
                root=root,
                decision_trace_limit=decision_trace_limit,
            )
            result["binary"] = descriptor
            _atomic_json(path, result)
        results.append(result)

    flat = _flatten_results(results)
    campaign = {
        "schema": SCHEMA_CAMPAIGN,
        "status": (
            "COMPLETE"
            if len(results) == len(selected)
            and all(result.get("status") == "COMPLETE" for result in results)
            else "INCOMPLETE"
        ),
        "claim_boundary": (
            "Fixed-map research-only native Route scorer ablation; no production "
            "promotion and no independent generalization claim."
        ),
        "binary": descriptor,
        "cases": results,
        "rows": flat,
    }
    _atomic_json(json_path, campaign)
    _atomic_text(csv_path, _csv_text(flat))
    _atomic_text(report_path, _markdown(campaign))
    return campaign


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--prefixes", nargs="+", type=int, default=list(DEFAULT_PREFIXES))
    parser.add_argument(
        "--evidence-prefixes",
        nargs="*",
        type=int,
        default=list(DEFAULT_EVIDENCE_PREFIXES),
    )
    parser.add_argument("--scales", nargs="*", type=int, default=[])
    parser.add_argument("--decision-trace-limit", type=int, default=DEFAULT_DECISION_TRACE_LIMIT)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--only-case")
    parser.add_argument("--force", action="store_true")
    return parser


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        cases = build_cases(
            prefixes=args.prefixes,
            evidence_prefixes=args.evidence_prefixes,
            scales=args.scales,
        )
        campaign = run_campaign(
            cases,
            binary=_resolve(root, args.binary),
            root=root,
            results_dir=_resolve(root, args.results_dir),
            json_path=_resolve(root, args.json),
            csv_path=_resolve(root, args.csv),
            report_path=_resolve(root, args.report),
            decision_trace_limit=args.decision_trace_limit,
            force=args.force,
            only_case=args.only_case,
        )
        print(
            json.dumps(
                {
                    "status": campaign["status"],
                    "case_count": len(campaign["cases"]),
                    "comparison_count": len(campaign["rows"]),
                },
                sort_keys=True,
            )
        )
        return 0 if campaign["status"] == "COMPLETE" else 2
    except (RouteCampaignError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G19 Route campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
