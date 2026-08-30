#!/usr/bin/env python3
"""Run the frozen V3R14 Candidate-B outcome-blind real-map screen.

The V3R13 Stage-2 preregistration remains the case, population, canonical
closure, and fault authority.  This module is deliberately a thin adapter
over that committed runner: it prepares each case once, fans the request out
to the three registered arms, and evaluates only the core gates measurable by
the current payload.  Importing or calling :func:`run_screen` with an injected
executor neither loads the native extension nor writes evidence.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r13_stage2_campaign as stage2,
)


SCHEMA = "czr005.g4irsf32.v3r14.candidate_b_screen.v1"
PROTOCOL_ID = "G4IRSF32_V3R14_CANDIDATE_B_UNCOVERED_WORK_20260829"
MEASUREMENT_REQUIRED = "MEASUREMENT_REQUIRED_V3R14_CANDIDATE_B"
NO_GO = "NO_GO_V3R14_CANDIDATE_B"
# A core pass is intentionally not a Stage-3 GO.  Keep PASS as a convenient
# compatibility spelling for injected tests and downstream report code.
PASS = MEASUREMENT_REQUIRED

PREREGISTRATION_PATH = stage2.PREREGISTRATION_PATH
OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r14_candidate_b_screen.json"
OUTPUT_MD = ROOT / "outputs/reports/g4irsf32_v3r14_candidate_b_screen.md"

ARMS = ("off", "candidate_a", "candidate_a_b")
OLD_SCORER = "S4_queue_aware_rule_only"
CANDIDATE_B_SCORER = "S4_uncovered_local_work_seconds_rule_only"
EVENT_TRACE_LIMIT = stage2.EVENT_TRACE_LIMIT
RESOURCE_RATIO_LIMIT = stage2.RESOURCE_RATIO_LIMIT
NANNING_TARGET_P95_REDUCTION = stage2.NANNING_TARGET_P95_REDUCTION
NANNING_MEAN_REGRESSION_LIMIT = stage2.NANNING_MEAN_REGRESSION_LIMIT
NANNING_TAIL_REGRESSION_LIMIT = stage2.NANNING_TAIL_REGRESSION_LIMIT
MAP2_REGRESSION_LIMIT = stage2.MAP2_REGRESSION_LIMIT
EPSILON = stage2.EPSILON

CORE_RESOURCE_NAMES = (
    "events_per_completed_segment",
    "wall_seconds",
    "max_source_queue_length",
    "max_junction_queue_length",
    "merge_grant_peak_pending_requests",
)

Executor = Callable[..., Mapping[str, Any]]
WorkloadSlice = stage2.WorkloadSlice
CandidateBScreenError = stage2.Stage2CampaignError

# Re-export the exact committed authorities/helpers used by this screen.  The
# aliases make that dependency explicit and avoid a second implementation of
# preregistration, canonical selection, fault handling, or metric semantics.
_read_preregistration = stage2._read_preregistration
_load_workload_slices = stage2._load_workload_slices
_arm_metrics = stage2._arm_metrics
_mapping = stage2._mapping
_rows = stage2._rows
_integer = stage2._integer
_ratio = stage2._ratio
_at_most = stage2._at_most
_reduction = stage2._reduction


def _resolve_binary(binary: Path) -> Path:
    """Bind the screen to an explicit V3R14 build without loading it."""

    resolved = binary.resolve(strict=True)
    if not resolved.is_file():
        raise CandidateBScreenError("V3R14 binary must be a file")
    if "build_g32_v3r14" not in {part.lower() for part in resolved.parts}:
        raise CandidateBScreenError(
            "Candidate-B binary must be passed explicitly from build_g32_v3r14"
        )
    return resolved


def _build_arm_requests(
    case: Mapping[str, Any],
    workload: WorkloadSlice,
    *,
    binary: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    """Prepare once and derive exactly the three frozen ablation arms."""

    paired, runtime_rows, rejected = stage2._build_pair_requests(
        case, workload, binary=binary
    )
    off = paired["off"]
    candidate_a = paired["closed_loop"]
    if off.get("scorer_mode") != OLD_SCORER:
        raise CandidateBScreenError("V3R13 off-arm scorer spelling changed")
    if candidate_a.get("scorer_mode") != OLD_SCORER:
        raise CandidateBScreenError("V3R13 Candidate-A scorer spelling changed")

    candidate_a_b = copy.deepcopy(candidate_a)
    candidate_a_b["scorer_mode"] = CANDIDATE_B_SCORER
    if candidate_a_b.get(stage2.stage01.NS + "mode") != "closed_loop":
        raise CandidateBScreenError("Candidate A+B must retain closed_loop mode")
    if candidate_a_b.get("event_trace_limit") != EVENT_TRACE_LIMIT:
        raise CandidateBScreenError("generic event trace suppression changed")

    # Prove that scorer_mode is the sole Candidate-B request delta.
    expected = copy.deepcopy(candidate_a)
    expected["scorer_mode"] = CANDIDATE_B_SCORER
    if candidate_a_b != expected:
        raise CandidateBScreenError("Candidate A+B request has an unregistered delta")
    return (
        {
            "off": off,
            "candidate_a": candidate_a,
            "candidate_a_b": candidate_a_b,
        },
        runtime_rows,
        rejected,
    )


# Keep a descriptive public-ish alias while allowing tests to make the shared
# prepared-request property explicit.
_build_three_arm_requests = _build_arm_requests


def _eligible_cohorts(
    workload: WorkloadSlice,
    runtime_rows: Sequence[Mapping[str, Any]],
) -> tuple[frozenset[int], frozenset[str]]:
    runtime_segment_ids = {str(row["segment_id"]) for row in runtime_rows}
    segments_by_task: dict[int, set[str]] = {}
    for row in workload.rows:
        segments_by_task.setdefault(int(row["task_id"]), set()).add(
            str(row["segment_id"])
        )
    eligible_raw_task_ids = frozenset(
        task_id
        for task_id, segment_ids in segments_by_task.items()
        if segment_ids.issubset(runtime_segment_ids)
    )
    eligible_target_segment_ids = frozenset(
        workload.target_segment_ids & runtime_segment_ids
    )
    return eligible_raw_task_ids, eligible_target_segment_ids


def _execute_arm(
    executor: Executor,
    request: Mapping[str, Any],
    *,
    workload: WorkloadSlice,
    arm: str,
    eligible_raw_task_ids: frozenset[int],
    eligible_target_segment_ids: frozenset[str],
) -> dict[str, Any]:
    semantic_mode = "off" if arm == "off" else "closed_loop"
    expected_scorer = str(request["scorer_mode"])
    observed_identity: dict[str, str] = {}

    def identity_checked_executor(**native_request: Any) -> Mapping[str, Any]:
        payload = executor(**native_request)
        if not isinstance(payload, Mapping):
            raise CandidateBScreenError("executor must return a mapping")
        summary = _mapping(payload.get("summary"), "payload.summary")
        scorer_mode_echo = summary.get("scorer_mode_echo")
        scorer_id = summary.get("scorer_id")
        if scorer_mode_echo != expected_scorer or scorer_id != expected_scorer:
            raise CandidateBScreenError(
                f"{arm}: native scorer identity does not match {expected_scorer}"
            )
        observed_identity.update(
            scorer_mode_echo=str(scorer_mode_echo), scorer_id=str(scorer_id)
        )
        return payload

    metrics = stage2._execute_arm(
        identity_checked_executor,
        request,
        workload=workload,
        mode=semantic_mode,
        eligible_raw_task_ids=eligible_raw_task_ids,
        eligible_target_segment_ids=eligible_target_segment_ids,
    )
    metrics["arm"] = arm
    metrics["scorer_mode"] = expected_scorer
    metrics.update(observed_identity)
    return metrics


def _resource_ratios(
    candidate: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, float | None]:
    candidate_resources = _mapping(candidate["resources"], "candidate resources")
    control_resources = _mapping(control["resources"], "control resources")
    return {
        name: _ratio(candidate_resources[name], control_resources[name])
        for name in CORE_RESOURCE_NAMES
    }


def _nanning_comparison(
    candidate: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    control_target = _mapping(control["target"], "control target")
    candidate_target = _mapping(candidate["target"], "candidate target")
    control_latency = _mapping(control_target["latency"], "control target latency")
    candidate_latency = _mapping(
        candidate_target["latency"], "candidate target latency"
    )
    control_whole = _mapping(
        control["whole_system_java_release_latency"], "control whole latency"
    )
    candidate_whole = _mapping(
        candidate["whole_system_java_release_latency"], "candidate whole latency"
    )
    source_reduced = float(candidate_target["target_source_wait_seconds"]) < (
        float(control_target["target_source_wait_seconds"]) - EPSILON
    )
    total_not_lower = float(candidate_target["target_total_latency_seconds"]) >= (
        float(control_target["target_total_latency_seconds"]) - EPSILON
    )
    return {
        "ratios": {
            "local_start49_source_wait_area_proxy": _ratio(
                candidate_target[
                    "local_start49_source_wait_area_proxy_bag_seconds"
                ],
                control_target[
                    "local_start49_source_wait_area_proxy_bag_seconds"
                ],
            ),
            "target_p95": _ratio(
                candidate_latency["p95_seconds"], control_latency["p95_seconds"]
            ),
            "whole_mean": _ratio(
                candidate_whole["mean_seconds"], control_whole["mean_seconds"]
            ),
            "whole_p95": _ratio(
                candidate_whole["p95_seconds"], control_whole["p95_seconds"]
            ),
            "whole_p99": _ratio(
                candidate_whole["p99_seconds"], control_whole["p99_seconds"]
            ),
        },
        "source_wait_reduced": source_reduced,
        "total_latency_not_lower": total_not_lower,
        "no_source_to_network_unchanged_total_transfer": not (
            source_reduced and total_not_lower
        ),
    }


def _map2_comparison(
    candidate: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    control_whole = _mapping(
        control["whole_system_java_release_latency"], "control whole latency"
    )
    candidate_whole = _mapping(
        candidate["whole_system_java_release_latency"], "candidate whole latency"
    )
    return {
        "ratios": {
            name: _ratio(
                candidate_whole[f"{name}_seconds"],
                control_whole[f"{name}_seconds"],
            )
            for name in ("mean", "p95", "p99")
        }
    }


def _safety_diagnostics(arm: Mapping[str, Any]) -> Mapping[str, Any]:
    safety = _mapping(arm["safety"], "arm safety")
    return _mapping(safety["diagnostic_counters"], "safety diagnostics")


def _evaluate_three_arm_case(
    case: Mapping[str, Any],
    workload: WorkloadSlice,
    *,
    arms: dict[str, dict[str, Any]],
    runtime_rows: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]],
    eligible_raw_task_ids: frozenset[int],
    eligible_target_segment_ids: frozenset[str],
    primary_arm: str,
    attribution_arm: str,
) -> dict[str, Any]:
    """Apply the frozen three-arm core gates to already measured arms.

    V3R14 and later append-only screens share these thresholds and metric
    semantics.  Keeping the evaluator here avoids copying the gate body while
    leaving each runner responsible for its own exact request deltas and native
    identity checks.
    """

    off = arms["off"]
    primary_candidate = arms[primary_arm]
    attribution_control = arms[attribution_arm]

    primary_resource_ratios = _resource_ratios(primary_candidate, off)
    attribution_resource_ratios = _resource_ratios(
        primary_candidate, attribution_control
    )
    primary_timing_cohort_matched = all(
        arm["_complete_raw_task_ids"] == eligible_raw_task_ids
        and arm["_completed_target_segment_ids"] == eligible_target_segment_ids
        for arm in (off, primary_candidate)
    )
    off_safety_diagnostics = _safety_diagnostics(off)
    candidate_safety_diagnostics = _safety_diagnostics(primary_candidate)
    no_new_starvation = _integer(
        candidate_safety_diagnostics["starvation_count"],
        f"{primary_arm} starvation count",
    ) <= _integer(off_safety_diagnostics["starvation_count"], "off starvation count")

    gates: dict[str, bool] = {
        "completed_not_lower": (
            primary_candidate["completed_segment_count"]
            >= off["completed_segment_count"]
            and primary_candidate["completed_raw_bag_count"]
            >= off["completed_raw_bag_count"]
        ),
        "static_fault_reachable_timing_cohort_complete_and_matched": (
            primary_timing_cohort_matched
        ),
        "hard_safety": all(
            arm["safety"]["pass"] is True for arm in (off, primary_candidate)
        ),
        "no_new_starvation_threshold_crossings": no_new_starvation,
        "core_resources_within_1p10": all(
            ratio is not None and ratio <= RESOURCE_RATIO_LIMIT + EPSILON
            for ratio in primary_resource_ratios.values()
        ),
    }

    if workload.map_id == stage2.nanning_native.MAP_ID:
        primary = _nanning_comparison(primary_candidate, off)
        attribution = _nanning_comparison(
            primary_candidate, attribution_control
        )
        ratios = _mapping(primary["ratios"], "primary Nanning ratios")
        gates.update(
            nanning_target_p95_improves_2pct=(
                ratios["target_p95"] is not None
                and float(ratios["target_p95"])
                <= 1.0 - NANNING_TARGET_P95_REDUCTION + EPSILON
            ),
            nanning_whole_mean_regression_at_most_0p5pct=(
                ratios["whole_mean"] is not None
                and float(ratios["whole_mean"])
                <= 1.0 + NANNING_MEAN_REGRESSION_LIMIT + EPSILON
            ),
            nanning_whole_p95_regression_at_most_1pct=(
                ratios["whole_p95"] is not None
                and float(ratios["whole_p95"])
                <= 1.0 + NANNING_TAIL_REGRESSION_LIMIT + EPSILON
            ),
            nanning_whole_p99_regression_at_most_1pct=(
                ratios["whole_p99"] is not None
                and float(ratios["whole_p99"])
                <= 1.0 + NANNING_TAIL_REGRESSION_LIMIT + EPSILON
            ),
            nanning_no_source_to_network_unchanged_total_transfer=bool(
                primary["no_source_to_network_unchanged_total_transfer"]
            ),
        )
    else:
        primary = _map2_comparison(primary_candidate, off)
        attribution = _map2_comparison(
            primary_candidate, attribution_control
        )
        ratios = _mapping(primary["ratios"], "primary map2 ratios")
        gates.update(
            map2_mean_regression_at_most_0p5pct=(
                ratios["mean"] is not None
                and float(ratios["mean"])
                <= 1.0 + MAP2_REGRESSION_LIMIT + EPSILON
            ),
            map2_p95_regression_at_most_0p5pct=(
                ratios["p95"] is not None
                and float(ratios["p95"])
                <= 1.0 + MAP2_REGRESSION_LIMIT + EPSILON
            ),
            map2_p99_regression_at_most_0p5pct=(
                ratios["p99"] is not None
                and float(ratios["p99"])
                <= 1.0 + MAP2_REGRESSION_LIMIT + EPSILON
            ),
        )

    safety_counter_deltas = {
        name: _integer(candidate_safety_diagnostics[name], f"candidate {name}")
        - _integer(off_safety_diagnostics[name], f"off {name}")
        for name in off_safety_diagnostics
    }
    attribution_timing_cohort_matched = (
        attribution_control["_complete_raw_task_ids"] == eligible_raw_task_ids
        and attribution_control["_completed_target_segment_ids"]
        == eligible_target_segment_ids
    )
    for arm in arms.values():
        arm.pop("_complete_raw_task_ids")
        arm.pop("_completed_target_segment_ids")

    return {
        "case_id": str(case["case_id"]),
        "map_id": workload.map_id,
        "scale": workload.scale,
        "role": case["role"],
        "fault_scenario": case.get("fault_scenario"),
        "fault_edges": case.get("fault_edges", []),
        "population": {
            "raw_task_count": workload.raw_task_count,
            "segment_count": len(workload.rows),
            "runtime_reachable_segment_count": len(runtime_rows),
            "source_rejected_segment_count": len(rejected),
            "fault_reachable_raw_task_count": len(eligible_raw_task_ids),
            "fault_reachable_target_segment_count": len(
                eligible_target_segment_ids
            ),
            "ordered_segment_ids_exact": [
                str(row["segment_id"]) for row in workload.rows
            ]
            == list(workload.ordered_segment_ids),
        },
        "arms": arms,
        "primary_comparison": {
            "candidate": primary_arm,
            "control": "off",
            "performance": primary,
            "resource_ratios": primary_resource_ratios,
        },
        "attribution_only_comparison": {
            "candidate": primary_arm,
            "control": attribution_arm,
            "performance": attribution,
            "resource_ratios": attribution_resource_ratios,
            "gate_bearing": False,
        },
        "performance_ratios": primary["ratios"],
        "resource_ratios": primary_resource_ratios,
        "diagnostics": {
            "safety_counter_deltas": safety_counter_deltas,
            "candidate_a_attribution_safety_pass": (
                attribution_control["safety"]["pass"] is True
            ),
            "candidate_a_attribution_timing_cohort_matched": (
                attribution_timing_cohort_matched
            ),
            "rss_status": "NOT_REQUIRED_BY_CORE_SCREEN_MEASUREMENT_PENDING",
            "mixed_origin_wait_area_status": (
                "NOT_REQUIRED_BY_CORE_SCREEN_MEASUREMENT_PENDING"
            ),
            "start49_source_wait_proxy_is_formal_mixed_integral": False,
        },
        "gates": gates,
        "pass": all(gates.values()),
    }


def _run_case(
    case: Mapping[str, Any],
    workload: WorkloadSlice,
    *,
    executor: Executor,
    binary: Path,
) -> dict[str, Any]:
    requests, runtime_rows, rejected = _build_arm_requests(
        case, workload, binary=binary
    )
    eligible_raw_task_ids, eligible_target_segment_ids = _eligible_cohorts(
        workload, runtime_rows
    )
    arms = {
        arm: _execute_arm(
            executor,
            requests[arm],
            workload=workload,
            arm=arm,
            eligible_raw_task_ids=eligible_raw_task_ids,
            eligible_target_segment_ids=eligible_target_segment_ids,
        )
        for arm in ARMS
    }
    return _evaluate_three_arm_case(
        case,
        workload,
        arms=arms,
        runtime_rows=runtime_rows,
        rejected=rejected,
        eligible_raw_task_ids=eligible_raw_task_ids,
        eligible_target_segment_ids=eligible_target_segment_ids,
        primary_arm="candidate_a_b",
        attribution_arm="candidate_a",
    )

def run_screen(*, executor: Executor, binary: Path) -> dict[str, Any]:
    """Execute the same ten registered cases and thirty fixed arm runs."""

    resolved_binary = _resolve_binary(binary)
    registration = _read_preregistration()
    slices = _load_workload_slices(registration)
    registered_cases = _rows(registration.get("cases"), "cases")
    cases = []
    for case in registered_cases:
        key = (str(case.get("map_id")), int(case.get("scale", -1)))
        workload = slices.get(key)
        if workload is None:
            raise CandidateBScreenError(
                f"unsupported preregistered case slice: {key}"
            )
        cases.append(
            _run_case(case, workload, executor=executor, binary=resolved_binary)
        )
    gates = {
        "exact_ten_preregistered_semantic_cases": (
            len(cases) == 10
            and [case["case_id"] for case in cases]
            == [str(case["case_id"]) for case in registered_cases]
        ),
        "exact_thirty_fixed_arm_executions": len(cases) * len(ARMS) == 30,
        "all_nanning_core_gates": all(
            case["pass"]
            for case in cases
            if case["map_id"] == stage2.nanning_native.MAP_ID
        ),
        "all_map2_core_gates": all(
            case["pass"]
            for case in cases
            if case["map_id"] == stage2.map2_native.MAP_ID
        ),
    }
    core_pass = all(gates.values())
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "preregistration": PREREGISTRATION_PATH.relative_to(ROOT).as_posix(),
        "binary": str(resolved_binary),
        "status": MEASUREMENT_REQUIRED if core_pass else NO_GO,
        "pass": core_pass,
        "core_screen_pass": core_pass,
        "measurement_only_support_required": core_pass,
        "formal_measurement_pass": None,
        "stage3_authorized": False,
        "semantic_case_count": len(cases),
        "execution_count": len(cases) * len(ARMS),
        "arms": list(ARMS),
        "primary_comparison": "candidate_a_b/off",
        "attribution_only_comparison": "candidate_a_b/candidate_a",
        "thresholds": {
            "resource_ratio_max": RESOURCE_RATIO_LIMIT,
            "nanning_target_p95_reduction_min": NANNING_TARGET_P95_REDUCTION,
            "nanning_whole_mean_regression_max": NANNING_MEAN_REGRESSION_LIMIT,
            "nanning_whole_p95_p99_regression_max": (
                NANNING_TAIL_REGRESSION_LIMIT
            ),
            "map2_mean_p95_p99_regression_max": MAP2_REGRESSION_LIMIT,
            "peak_rss_core_gate": False,
            "full_mixed_origin_integral_core_gate": False,
        },
        "gates": gates,
        "cases": cases,
    }


# Campaign is a useful synonym for callers patterned after the V3R13 runner.
run_campaign = run_screen


def _format_ratio(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF32 V3R14 Candidate B real-map core screen",
        "",
        f"Status: `{result.get('status')}`.",
        "",
        "Primary comparison: `candidate_a_b / off`. Candidate A attribution is "
        "diagnostic only.",
        "",
        "| case | target/map2 P95 ratio | whole mean ratio | max core resource ratio | pass |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in result.get("cases", []):
        performance = case["performance_ratios"]
        if case["map_id"] == stage2.nanning_native.MAP_ID:
            p95 = performance.get("target_p95")
            mean = performance.get("whole_mean")
        else:
            p95 = performance.get("p95")
            mean = performance.get("mean")
        resources = [
            value
            for value in case["resource_ratios"].values()
            if value is not None
        ]
        lines.append(
            "| {case_id} | {p95} | {mean} | {resource} | {passed} |".format(
                case_id=case["case_id"],
                p95=_format_ratio(p95),
                mean=_format_ratio(mean),
                resource=_format_ratio(max(resources) if resources else None),
                passed="PASS" if case["pass"] else "FAIL",
            )
        )
    case_failures = [
        (
            str(case["case_id"]),
            [name for name, passed in case.get("gates", {}).items() if not passed],
        )
        for case in result.get("cases", [])
        if not case.get("pass")
    ]
    campaign_failures = [
        name for name, passed in result.get("gates", {}).items() if not passed
    ]
    lines.extend(
        [
            "",
            "## Failed core gates",
            "",
            *(
                [f"- `{case_id}`: " + ", ".join(names) for case_id, names in case_failures]
                if case_failures
                else ["None."]
            ),
            "",
            "## Decision",
            "",
            (
                "Core screen passed. Isolated RSS and exact mixed-origin "
                "measurement support is required before any Stage 3 decision."
                if result.get("core_screen_pass")
                else "Candidate B is NO-GO; Stage 3 remains blocked."
            ),
            "",
            "Stage 3 authorized: `false`.",
            "",
            "Failed campaign gates: "
            + (", ".join(campaign_failures) if campaign_failures else "none"),
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(
    result: Mapping[str, Any],
    *,
    json_path: Path = OUTPUT_JSON,
    markdown_path: Path = OUTPUT_MD,
) -> None:
    """Publish only the two registered append-only screen outputs."""

    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("V3R14 Candidate-B screen outputs are append-only")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        with json_path.open("x", encoding="utf-8", newline="\n") as handle:
            created.append(json_path)
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        with markdown_path.open("x", encoding="utf-8", newline="\n") as handle:
            created.append(markdown_path)
            handle.write(render_report(result))
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def cpp_executor(**request: Any) -> Mapping[str, Any]:
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    return g4irsf11_event_runtime_from_records(**request)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = run_screen(executor=cpp_executor, binary=arguments.binary)
    except Exception as error:
        print(
            f"CANDIDATE_B_SCREEN_RUNNER_ERROR: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    write_evidence(result)
    print(result["status"])
    return 0 if result.get("core_screen_pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
