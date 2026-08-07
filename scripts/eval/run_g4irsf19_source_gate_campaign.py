#!/usr/bin/env python3
"""Run the narrow G19 Source ADMIT/HOLD pressure-gate campaign.

The campaign changes only existing source-admission controls.  It keeps the
E4/J2/M3 event boundary, Route S4, R3, P2 and Q0 fixed, trains no model, and
adds no native runtime mechanism.  Small 144/512 evidence cases use the
existing G17 source-wait telemetry only long enough to count distinct observed
HOLD states; raw interval rows are never persisted.  Optional 1x/2x capacity
cases retain summary counters only.
"""

from __future__ import annotations

import argparse
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


SCHEMA_CASE_RESULT = "czr005.g4irsf19.source_gate_case_result.v1"
SCHEMA_CAMPAIGN = "czr005.g4irsf19.source_gate_campaign.v1"

DEFAULT_PREFIXES = (144, 512)
ALLOWED_PREFIXES = DEFAULT_PREFIXES
ALLOWED_SCALES = (1, 2)
DEFAULT_TELEMETRY_LIMIT = 500_000

DEFAULT_RESULTS = ROOT / "outputs/runtime/g4irsf19_source_gate_campaign"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf19_source_gate_campaign.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf19_source_gate_campaign.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf19_source_admission.md"
DEFAULT_CLOSED_LOOP_REPORT = (
    ROOT / "outputs/reports/g4irsf19_source_closed_loop.md"
)

J2_TIMING_MODE = "jit_fair_aging_deadline"
J2_MERGE_RULE = "M3"
S4_SCORER_MODE = "S4_queue_aware_rule_only"

COMPARISON_METRICS = (
    "mean_tth_seconds",
    "p95_tth_seconds",
    "source_wait_mean_seconds",
    "event_count",
)


class SourceGateCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceGateCampaignError(message)


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


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
class SourceGateArm:
    arm_id: str
    enable_source_admission: bool
    enable_backpressure: bool
    admission_mode: str
    pressure_mode: str
    expected_admission_mode: str
    expected_pressure_mode: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


SOURCE_ARMS = (
    SourceGateArm(
        "A0",
        False,
        False,
        "off",
        "off",
        "off",
        "C0_off",
    ),
    SourceGateArm(
        "A1",
        True,
        True,
        "legacy_unbound",
        "absolute_downstream_queue_penalty",
        "legacy_unbound",
        "C1_absolute_downstream_queue_penalty",
    ),
    SourceGateArm(
        "A2",
        True,
        True,
        "legacy_unbound",
        "goal_conditioned_differential",
        "legacy_unbound",
        "C2_goal_conditioned_differential",
    ),
)
ARM_BY_ID = {arm.arm_id: arm for arm in SOURCE_ARMS}


@dataclass(frozen=True)
class SourceGateCase:
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
    scales: Sequence[int] = (),
) -> list[SourceGateCase]:
    prefix_values = tuple(dict.fromkeys(int(value) for value in prefixes))
    scale_values = tuple(dict.fromkeys(int(value) for value in scales))
    _require(bool(prefix_values) or bool(scale_values), "campaign has no cases")
    _require(
        all(value in ALLOWED_PREFIXES for value in prefix_values),
        "evidence prefixes must be 144 and/or 512",
    )
    _require(
        all(value in ALLOWED_SCALES for value in scale_values),
        "capacity scales are limited to 1x and 2x",
    )
    cases = [
        SourceGateCase(
            case_id=f"prefix_{prefix}",
            kind="prefix",
            telemetry_mode="evidence_trace",
            prefix_segments=prefix,
            scale=1,
        )
        for prefix in prefix_values
    ]
    cases.extend(
        SourceGateCase(
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


def load_case_input(
    case: SourceGateCase, *, root: Path = ROOT
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from scripts.eval import run_g4irsf18_system_campaign as g18

    job = g18.SystemJob(
        job_id=f"g19_source_gate_{case.case_id}",
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
    case: SourceGateCase,
    arm: SourceGateArm,
    *,
    rows: Sequence[Mapping[str, Any]],
    graph: tuple[Any, Any, Any],
    binary: Path,
    telemetry_limit: int = DEFAULT_TELEMETRY_LIMIT,
) -> dict[str, Any]:
    from scripts.eval import run_g4irsf18_jit_campaign as jit
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS

    _require(telemetry_limit > 0, "telemetry limit must be positive")
    nodes, edges, heuristic = graph
    evidence = case.telemetry_mode == "evidence_trace"
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=jit._binding_rows(rows),
        fault_windows=(),
        scenario=f"g4irsf19_source_gate_{case.case_id}_{arm.arm_id}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        expected_binary_path=binary,
        search_path=binary.parent,
        g4irsf16_supervisor_mode="off",
        g4irsf17_source_policy_mode="off",
        enable_g4irsf17_source_wait_telemetry=evidence,
        g4irsf17_source_wait_trace_limit=(telemetry_limit if evidence else 0),
        merge_grant_rule=J2_MERGE_RULE,
        merge_grant_timing_mode=J2_TIMING_MODE,
        scorer_mode=S4_SCORER_MODE,
        enable_source_admission=arm.enable_source_admission,
        enable_backpressure=arm.enable_backpressure,
        admission_mode=arm.admission_mode,
        pressure_mode=arm.pressure_mode,
    )
    # S4 is a native rule.  The wrapper deliberately rejects model paths for
    # S3/S4; model paths remain exclusive to S1/S2 campaigns.
    request.pop("scorer_model_path", None)
    return request


def _hold_state_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("source_node"),
        row.get("source_generation"),
        row.get("selected_runtime_bag_id"),
        row.get("reason"),
        row.get("blocker_node"),
        row.get("blocker_resource"),
        row.get("blocker_resource_from_node"),
        row.get("blocker_resource_to_node"),
        row.get("blocker_generation"),
    )


def compact_hold_opportunities(
    rows: Sequence[Mapping[str, Any]],
    *,
    telemetry_enabled: bool = True,
    trace_truncated: bool = False,
) -> dict[str, Any]:
    """Collapse wait intervals without retaining trace identities.

    A distinct opportunity is an observed unique wait-state key.  This is not
    a counterfactual action or a route mutation: one bag can produce many
    retries, and HOLD merely defers source admission.
    """

    claim = (
        "A distinct HOLD opportunity is one unique observed source-generation, "
        "selected-bag and blocker-state key. Retry counters may revisit the "
        "same key; HOLD defers admission and is not a bag route/action mutation."
    )
    if not telemetry_enabled:
        return {
            "status": "NOT_COLLECTED_CAPACITY_MODE",
            "claim_boundary": claim,
            "observed_wait_interval_count": None,
            "observed_hold_interval_count": None,
            "distinct_hold_opportunity_count": None,
            "distinct_selected_bag_count": None,
            "distinct_selected_segment_count": None,
            "raw_interval_rows_persisted": False,
        }

    valid_rows = [row for row in rows if isinstance(row, Mapping)]
    _require(len(valid_rows) == len(rows), "source-wait trace contains a non-object row")
    # The telemetry also closes ordinary service-wait intervals after a
    # successful admission with selected_runtime_bag_id=-1.  Those rows are
    # useful for wait attribution but are not HOLD actions.  A real held
    # attempt always carries the selected bag identity supplied by the failed
    # try_admit_source call.
    hold_rows = [
        row
        for row in valid_rows
        if _integer(row.get("selected_runtime_bag_id")) is not None
        and int(row["selected_runtime_bag_id"]) >= 0
    ]
    keys = {_hold_state_key(row) for row in hold_rows}
    bags = {
        int(row["selected_runtime_bag_id"])
        for row in hold_rows
        if _integer(row.get("selected_runtime_bag_id")) is not None
        and int(row["selected_runtime_bag_id"]) >= 0
    }
    segments = {
        str(row["selected_segment_id"])
        for row in hold_rows
        if isinstance(row.get("selected_segment_id"), str)
        and str(row["selected_segment_id"])
    }
    return {
        "status": (
            "OBSERVED_LOWER_BOUND_TRACE_TRUNCATED"
            if trace_truncated
            else "COMPLETE_OBSERVED_WAIT_STATE_CAPTURE"
        ),
        "claim_boundary": claim,
        "observed_wait_interval_count": len(valid_rows),
        "observed_hold_interval_count": len(hold_rows),
        "distinct_hold_opportunity_count": len(keys),
        "distinct_selected_bag_count": len(bags),
        "distinct_selected_segment_count": len(segments),
        "raw_interval_rows_persisted": False,
    }


def _source_counters(summary: Mapping[str, Any]) -> dict[str, int]:
    names = (
        "source_admission_attempt_count",
        "source_admission_admitted_count",
        "source_admission_local_resource_hold_count",
        "source_admission_downstream_pressure_hold_count",
        "source_admission_beacon_read_count",
        "source_admission_max_observed_downstream_pressure",
    )
    result: dict[str, int] = {}
    for name in names:
        value = _integer(summary.get(name))
        _require(value is not None and value >= 0, f"missing source counter: {name}")
        result[name] = value
    result["source_admission_hold_retry_count"] = (
        result["source_admission_local_resource_hold_count"]
        + result["source_admission_downstream_pressure_hold_count"]
    )
    _require(
        result["source_admission_attempt_count"]
        == result["source_admission_admitted_count"]
        + result["source_admission_hold_retry_count"],
        "source admission attempt outcomes do not conserve",
    )
    return result


def summarize_payload(
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    arm: SourceGateArm,
    telemetry_enabled: bool,
    wall_seconds: float,
    cpu_seconds: float,
) -> dict[str, Any]:
    from scripts.eval import run_g4irsf18_jit_campaign as jit

    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(
        summary.get("merge_grant_timing_mode") == J2_TIMING_MODE,
        "native J2 timing echo drift",
    )
    _require(summary.get("scorer_mode") == S4_SCORER_MODE, "native S4 echo drift")
    _require(
        summary.get("admission_mode") == arm.expected_admission_mode,
        f"{arm.arm_id}: admission-mode echo drift",
    )
    _require(
        summary.get("pressure_mode") == arm.expected_pressure_mode,
        f"{arm.arm_id}: pressure-mode echo drift",
    )
    _require(
        summary.get("source_admission_enabled") is arm.enable_source_admission,
        f"{arm.arm_id}: source-admission enable echo drift",
    )

    counters = _source_counters(summary)
    raw = jit._raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    all_complete = len(completed) == len(raw)
    tth = [float(row["tth_seconds"]) for row in completed]
    source_wait = [float(row["source_wait_seconds"]) for row in completed]
    safety = jit._hard_safety(summary, len(rows))
    event_count = _integer(summary.get("event_count"))

    if telemetry_enabled:
        _require(
            summary.get("g4irsf17_source_wait_telemetry_enabled") is True,
            "source-wait telemetry was not enabled",
        )
        interval_rows = payload.get("g4irsf17_source_wait_blockers")
        _require(isinstance(interval_rows, list), "source-wait interval rows missing")
        total = _integer(summary.get("g4irsf17_source_wait_interval_total_count"))
        stored = _integer(summary.get("g4irsf17_source_wait_interval_stored_count"))
        dropped = _integer(summary.get("g4irsf17_source_wait_interval_dropped_count"))
        _require(None not in (total, stored, dropped), "source-wait interval counters missing")
        _require(stored == len(interval_rows), "source-wait stored-count mismatch")
        _require(total == stored + dropped, "source-wait interval conservation failed")
        _require(
            _integer(
                summary.get("g4irsf17_source_wait_runtime_global_scan_count")
            )
            == 0,
            "source-wait telemetry performed a global scan",
        )
        compact_holds = compact_hold_opportunities(
            interval_rows,
            telemetry_enabled=True,
            trace_truncated=bool(dropped),
        )
        observed_holds = _integer(
            compact_holds.get("observed_hold_interval_count")
        )
        distinct_holds = _integer(
            compact_holds.get("distinct_hold_opportunity_count")
        )
        _require(
            observed_holds is not None
            and observed_holds
            <= counters["source_admission_hold_retry_count"],
            "observed HOLD intervals exceed native HOLD retry outcomes",
        )
        _require(
            distinct_holds is not None and distinct_holds <= observed_holds,
            "distinct HOLD states exceed observed HOLD intervals",
        )
        if counters["source_admission_hold_retry_count"] == 0:
            _require(
                observed_holds == 0 and distinct_holds == 0,
                "zero native HOLD outcomes produced a distinct HOLD opportunity",
            )
    else:
        _require(
            "g4irsf17_source_wait_blockers" not in payload
            or payload.get("g4irsf17_source_wait_blockers") == [],
            "capacity mode unexpectedly retained source-wait rows",
        )
        compact_holds = compact_hold_opportunities([], telemetry_enabled=False)

    if safety["pass"] and all_complete:
        status = "COMPLETE"
    elif summary.get("event_limit_reached") is True:
        status = "CAPACITY_CENSORED_EVENT_LIMIT"
    elif summary.get("time_limit_reached") is True:
        status = "CAPACITY_CENSORED_SIMULATION_TIME"
    else:
        status = "HARD_GATE_FAILED"

    return {
        "arm": arm.as_dict(),
        "status": status,
        "hard_safety": safety,
        "resources": {"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds},
        "metrics": {
            "requested_segments": len(rows),
            "raw_bag_count": len(raw),
            "complete_raw_bag_count": len(completed),
            "mean_tth_seconds": (
                statistics.fmean(tth) if all_complete and tth else None
            ),
            "p95_tth_seconds": _quantile(tth, 0.95) if all_complete else None,
            "source_wait_mean_seconds": (
                statistics.fmean(source_wait)
                if all_complete and source_wait
                else None
            ),
            "event_count": event_count,
            "events_per_raw_bag": (
                event_count / len(raw) if event_count is not None and raw else None
            ),
        },
        "source_counters": counters,
        "hold_observation": compact_holds,
    }


Executor = Callable[[Mapping[str, Any]], Mapping[str, Any]]
InputLoader = Callable[[SourceGateCase], tuple[list[dict[str, Any]], dict[str, Any]]]


def execute_case(
    case: SourceGateCase,
    *,
    binary: Path,
    root: Path = ROOT,
    telemetry_limit: int = DEFAULT_TELEMETRY_LIMIT,
    executor: Executor | None = None,
    input_loader: InputLoader | None = None,
    graph: tuple[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    resolved_binary = binary if executor is not None else binary.resolve(strict=True)
    loader = input_loader or (lambda value: load_case_input(value, root=root))
    rows, descriptor = loader(case)
    _require(bool(rows), "case input is empty")
    _require(descriptor.get("topology_changed") is False, "case changed topology")
    fixed_graph = graph if graph is not None else load_fixed_graph()
    telemetry_enabled = case.telemetry_mode == "evidence_trace"

    if executor is None:
        from czr005 import cpp_backend

        native_executor: Executor = lambda request: (
            cpp_backend.g4irsf11_event_runtime_from_records(**request)
        )
    else:
        native_executor = executor

    arms: dict[str, dict[str, Any]] = {}
    for arm in SOURCE_ARMS:
        request = build_runtime_request(
            case,
            arm,
            rows=rows,
            graph=fixed_graph,
            binary=resolved_binary,
            telemetry_limit=telemetry_limit,
        )
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        payload = native_executor(request)
        cpu_seconds = time.process_time() - cpu_start
        wall_seconds = time.perf_counter() - wall_start
        _require(isinstance(payload, Mapping), "native executor returned a non-object")
        arms[arm.arm_id] = summarize_payload(
            rows,
            descriptor,
            payload,
            arm=arm,
            telemetry_enabled=telemetry_enabled,
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
        )

    comparisons: list[dict[str, Any]] = []
    baseline = arms["A0"]
    for treatment_id in ("A1", "A2"):
        treatment = arms[treatment_id]
        metric_deltas = {
            name: (
                float(treatment["metrics"][name]) - float(baseline["metrics"][name])
                if _finite(treatment["metrics"].get(name)) is not None
                and _finite(baseline["metrics"].get(name)) is not None
                else None
            )
            for name in COMPARISON_METRICS
        }
        comparisons.append(
            {
                "baseline_arm": "A0",
                "treatment_arm": treatment_id,
                "baseline_status": baseline["status"],
                "treatment_status": treatment["status"],
                "baseline_hard_safety_pass": baseline["hard_safety"]["pass"],
                "treatment_hard_safety_pass": treatment["hard_safety"]["pass"],
                "treatment_minus_baseline": metric_deltas,
            }
        )

    return {
        "schema": SCHEMA_CASE_RESULT,
        "case": case.as_dict(),
        "input": dict(descriptor),
        "runtime_contract": {
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "merge_timing": J2_TIMING_MODE,
            "merge_rule": J2_MERGE_RULE,
            "route_scorer": S4_SCORER_MODE,
            "resource_semantics": "R3_java_node_window_compatible",
            "pibt_mode": "P2",
            "priority_mode": "Q0",
            "new_model_trained": False,
            "native_runtime_changed": False,
            "capacity_trace_disabled": not telemetry_enabled,
            "raw_source_wait_rows_persisted": False,
        },
        "arms": arms,
        "comparisons": comparisons,
        "status": (
            "COMPLETE"
            if all(value["status"] == "COMPLETE" for value in arms.values())
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


def _case_path(results_dir: Path, case: SourceGateCase) -> Path:
    return results_dir / f"g4irsf19_source_gate_{case.case_id}.json"


def _read_case(
    path: Path,
    case: SourceGateCase,
    binary: Mapping[str, Any],
    telemetry_limit: int,
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
        and value.get("telemetry_limit") == telemetry_limit
    ):
        return value
    return None


def _flatten_results(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in cases:
        case = result["case"]
        comparison_by_arm = {
            row["treatment_arm"]: row for row in result["comparisons"]
        }
        for arm_id, arm_result in result["arms"].items():
            arm = arm_result["arm"]
            metrics = arm_result["metrics"]
            counters = arm_result["source_counters"]
            hold = arm_result["hold_observation"]
            comparison = comparison_by_arm.get(arm_id)
            deltas = comparison["treatment_minus_baseline"] if comparison else {}
            rows.append(
                {
                    "case_id": case["case_id"],
                    "kind": case["kind"],
                    "prefix_segments": case["prefix_segments"],
                    "scale": case["scale"],
                    "telemetry_mode": case["telemetry_mode"],
                    "arm_id": arm_id,
                    "enable_source_admission": arm["enable_source_admission"],
                    "enable_backpressure": arm["enable_backpressure"],
                    "admission_mode": arm["admission_mode"],
                    "pressure_mode": arm["pressure_mode"],
                    "status": arm_result["status"],
                    "hard_safety_pass": arm_result["hard_safety"]["pass"],
                    "source_admission_attempt_count": counters[
                        "source_admission_attempt_count"
                    ],
                    "source_admission_admitted_count": counters[
                        "source_admission_admitted_count"
                    ],
                    "source_admission_local_resource_hold_count": counters[
                        "source_admission_local_resource_hold_count"
                    ],
                    "source_admission_downstream_pressure_hold_count": counters[
                        "source_admission_downstream_pressure_hold_count"
                    ],
                    "source_admission_hold_retry_count": counters[
                        "source_admission_hold_retry_count"
                    ],
                    "hold_observation_status": hold["status"],
                    "observed_wait_interval_count": hold[
                        "observed_wait_interval_count"
                    ],
                    "observed_hold_interval_count": hold[
                        "observed_hold_interval_count"
                    ],
                    "distinct_hold_opportunity_count": hold[
                        "distinct_hold_opportunity_count"
                    ],
                    "distinct_selected_bag_count": hold[
                        "distinct_selected_bag_count"
                    ],
                    "mean_tth_seconds": metrics["mean_tth_seconds"],
                    "p95_tth_seconds": metrics["p95_tth_seconds"],
                    "source_wait_mean_seconds": metrics[
                        "source_wait_mean_seconds"
                    ],
                    "event_count": metrics["event_count"],
                    "delta_mean_tth_vs_a0_seconds": deltas.get(
                        "mean_tth_seconds"
                    ),
                    "delta_source_wait_vs_a0_seconds": deltas.get(
                        "source_wait_mean_seconds"
                    ),
                    "delta_events_vs_a0": deltas.get("event_count"),
                }
            )
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
        "# G4IRSF19 Source ADMIT/HOLD pressure campaign",
        "",
        "The campaign keeps E4/J2/M3, Route S4, R3, P2 and Q0 fixed. A0 "
        "disables source admission/backpressure, A1 uses the existing absolute "
        "downstream queue penalty, and A2 uses the existing goal-conditioned "
        "differential. No model is trained and no native mechanism is added.",
        "",
        "| Case | Arm | Safety | Attempts | Admitted | Local HOLD retries | Downstream HOLD retries | Distinct observed HOLD states | Held bags | Mean TTH (s) | Source wait (s) | Events | Delta TTH vs A0 (s) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in campaign["rows"]:
        lines.append(
            "| "
            f"{row['case_id']} | {row['arm_id']} | {row['hard_safety_pass']} | "
            f"{row['source_admission_attempt_count']} | "
            f"{row['source_admission_admitted_count']} | "
            f"{row['source_admission_local_resource_hold_count']} | "
            f"{row['source_admission_downstream_pressure_hold_count']} | "
            f"{row['distinct_hold_opportunity_count'] if row['distinct_hold_opportunity_count'] is not None else '-'} | "
            f"{row['distinct_selected_bag_count'] if row['distinct_selected_bag_count'] is not None else '-'} | "
            f"{_show(row['mean_tth_seconds'])} | "
            f"{_show(row['source_wait_mean_seconds'])} | "
            f"{_show(row['event_count'], 0)} | "
            f"{_show(row['delta_mean_tth_vs_a0_seconds'])} |"
        )
    measured_treatments = [
        row
        for row in campaign["rows"]
        if row["arm_id"] in {"A1", "A2"}
        and _finite(row.get("delta_mean_tth_vs_a0_seconds")) is not None
        and _finite(row.get("delta_source_wait_vs_a0_seconds")) is not None
    ]
    all_treatments_worse = bool(measured_treatments) and all(
        float(row["delta_mean_tth_vs_a0_seconds"]) > 0.0
        and float(row["delta_source_wait_vs_a0_seconds"]) > 0.0
        for row in measured_treatments
    )
    prefix_by_arm = {
        (row["case_id"], row["arm_id"]): row
        for row in campaign["rows"]
        if row["case_id"] in {"prefix_144", "prefix_512"}
    }
    small_modes_identical = bool(prefix_by_arm) and all(
        prefix_by_arm.get((case_id, "A1")) is not None
        and prefix_by_arm.get((case_id, "A2")) is not None
        and all(
            prefix_by_arm[(case_id, "A1")].get(field)
            == prefix_by_arm[(case_id, "A2")].get(field)
            for field in (
                "source_admission_attempt_count",
                "source_admission_local_resource_hold_count",
                "source_admission_downstream_pressure_hold_count",
                "distinct_hold_opportunity_count",
                "mean_tth_seconds",
                "source_wait_mean_seconds",
                "event_count",
            )
        )
        for case_id in ("prefix_144", "prefix_512")
    )
    lines.extend(
        [
            "",
            "## Observed decision",
            "",
            (
                "No deterministic pressure arm is promoted: every measured A1/A2 "
                "case increases both mean TTH and source wait relative to A0."
                if all_treatments_worse
                else "The measured arms do not support one uniform business decision; "
                "inspect the paired rows before promotion."
            ),
            (
                "At 144 and 512 segments A1 and A2 collapse to exactly the same "
                "source counters, distinct HOLD states and business metrics."
                if small_modes_identical
                else "A1 and A2 do not collapse to the same observed small-case behavior."
            ),
            "",
            "## Interpretation boundary",
            "",
            "The local/downstream HOLD counters count admission attempts, including "
            "retries. A distinct observed HOLD state deduplicates evidence intervals "
            "by source generation, selected bag and blocker state. Neither quantity "
            "is a bag routing mutation: HOLD only defers admission. Raw source-wait "
            "intervals are discarded after compact counting.",
            "",
            "The optional 1x/2x capacity cases disable interval telemetry and retain "
            "only counters, business metrics and safety gates. Positive TTH, source-"
            "wait and event deltas mean the treatment is worse than A0.",
            "",
            "This is fixed-map research evidence, not production promotion authority.",
            "",
        ]
    )
    return "\n".join(lines)


def _closed_loop_markdown(campaign: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF19 Source closed-loop boundary",
        "",
        "Status: `NOT_A_LEARNED_CLOSED_LOOP_CAMPAIGN`.",
        "",
        "A0/A1/A2 are deterministic configurations of the existing native "
        "ADMIT/HOLD pressure gate. They test whether the seam is active and "
        "whether its business effect is promising; they do not evaluate a "
        "learned Source policy and therefore cannot establish learned Source "
        "ownership or action mutations.",
        "",
        "| Case | Arm | Safety | Downstream HOLD retries | Distinct observed HOLD states | Delta TTH vs A0 (s) | Delta source wait vs A0 (s) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in campaign["rows"]:
        if row["arm_id"] == "A0":
            continue
        lines.append(
            "| "
            f"{row['case_id']} | {row['arm_id']} | {row['hard_safety_pass']} | "
            f"{row['source_admission_downstream_pressure_hold_count']} | "
            f"{row['distinct_hold_opportunity_count'] if row['distinct_hold_opportunity_count'] is not None else '-'} | "
            f"{_show(row['delta_mean_tth_vs_a0_seconds'])} | "
            f"{_show(row['delta_source_wait_vs_a0_seconds'])} |"
        )
    lines.extend(
        [
            "",
            "HOLD retries are repeated admission evaluations, not distinct bag "
            "mutations. The distinct-state column is still only observed seam "
            "activity, not a cloned counterfactual action count.",
            "",
            "Promotion remains blocked until a bounded learned ADMIT/HOLD policy "
            "changes actions on matched states and passes the paired safety and "
            "business gates. This report intentionally records that boundary "
            "instead of relabeling deterministic pressure gating as learning.",
            "",
        ]
    )
    return "\n".join(lines)


def write_campaign_artifacts(
    campaign: Mapping[str, Any],
    *,
    json_path: Path,
    csv_path: Path,
    report_path: Path,
    closed_loop_report_path: Path | None = None,
) -> None:
    _atomic_json(json_path, campaign)
    _atomic_text(csv_path, _csv_text(campaign["rows"]))
    _atomic_text(report_path, _markdown(campaign))
    if closed_loop_report_path is not None:
        _atomic_text(closed_loop_report_path, _closed_loop_markdown(campaign))


def run_campaign(
    cases: Sequence[SourceGateCase],
    *,
    binary: Path,
    root: Path = ROOT,
    results_dir: Path = DEFAULT_RESULTS,
    json_path: Path = DEFAULT_JSON,
    csv_path: Path = DEFAULT_CSV,
    report_path: Path = DEFAULT_REPORT,
    closed_loop_report_path: Path = DEFAULT_CLOSED_LOOP_REPORT,
    telemetry_limit: int = DEFAULT_TELEMETRY_LIMIT,
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
            else _read_case(path, case, descriptor, telemetry_limit)
        )
        if cached is not None:
            result = cached
        else:
            result = execute_case(
                case,
                binary=binary,
                root=root,
                telemetry_limit=telemetry_limit,
            )
            result["binary"] = descriptor
            result["telemetry_limit"] = telemetry_limit
            _atomic_json(path, result)
        results.append(result)

    campaign: dict[str, Any] = {
        "schema": SCHEMA_CAMPAIGN,
        "status": (
            "COMPLETE"
            if all(result["status"] == "COMPLETE" for result in results)
            else "INCOMPLETE"
        ),
        "binary": descriptor,
        "arms": [arm.as_dict() for arm in SOURCE_ARMS],
        "cases": results,
    }
    campaign["rows"] = _flatten_results(results)
    write_campaign_artifacts(
        campaign,
        json_path=json_path,
        csv_path=csv_path,
        report_path=report_path,
        closed_loop_report_path=closed_loop_report_path,
    )
    return campaign


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--prefixes",
        type=int,
        nargs="*",
        choices=ALLOWED_PREFIXES,
        default=list(DEFAULT_PREFIXES),
    )
    parser.add_argument(
        "--scales", type=int, nargs="*", choices=ALLOWED_SCALES, default=[]
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--closed-loop-report", type=Path, default=DEFAULT_CLOSED_LOOP_REPORT
    )
    parser.add_argument(
        "--telemetry-limit", type=int, default=DEFAULT_TELEMETRY_LIMIT
    )
    parser.add_argument("--only-case")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign = run_campaign(
        build_cases(prefixes=args.prefixes, scales=args.scales),
        binary=args.binary,
        results_dir=args.results_dir,
        json_path=args.json,
        csv_path=args.csv,
        report_path=args.report,
        closed_loop_report_path=args.closed_loop_report,
        telemetry_limit=args.telemetry_limit,
        force=args.force,
        only_case=args.only_case,
    )
    print(
        json.dumps(
            {
                "schema": campaign["schema"],
                "status": campaign["status"],
                "case_count": len(campaign["cases"]),
                "row_count": len(campaign["rows"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if campaign["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
