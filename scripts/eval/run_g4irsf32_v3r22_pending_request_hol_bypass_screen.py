#!/usr/bin/env python3
"""Run the frozen V3R22 pending-request HOL-bypass core screen.

V3R13 remains the authority for cases, cohorts, metrics, and thresholds.  The
third arm changes only the local queue discipline; injected execution neither
loads the native extension nor writes evidence.
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
    run_g4irsf32_v3r18_source_release_tie_screen as previous,
)


stage2 = previous.stage2
shared = previous.shared

SCHEMA = "czr005.g4irsf32.v3r22.pending_request_hol_bypass_screen.v1"
PROTOCOL_ID = "G4IRSF32_V3R22_PENDING_REQUEST_HOL_BYPASS_20260830"
MEASUREMENT_REQUIRED = "MEASUREMENT_REQUIRED_V3R22_PENDING_REQUEST_HOL_BYPASS"
NO_GO = "NO_GO_V3R22_PENDING_REQUEST_HOL_BYPASS"
PASS = MEASUREMENT_REQUIRED

PREREGISTRATION_PATH = (
    ROOT / "docs/G4IRSF32_v3r22_pending_request_hol_bypass_preregistration.md"
)
CASE_REGISTRATION_PATH = stage2.PREREGISTRATION_PATH
OUTPUT_JSON = (
    ROOT / "outputs/tables/g4irsf32_v3r22_pending_request_hol_bypass_screen.json"
)
OUTPUT_MD = (
    ROOT / "outputs/reports/g4irsf32_v3r22_pending_request_hol_bypass_screen.md"
)

ARMS = ("off", "candidate_a", "candidate_a_hol_bypass")
OLD_SCORER = previous.OLD_SCORER
HISTORICAL_QUEUE_DISCIPLINE = "fifo"
CANDIDATE_QUEUE_DISCIPLINE = "fifo_junction_skip_pending_merge_owner"
HISTORICAL_MODE = previous.HISTORICAL_MODE
EVENT_TRACE_LIMIT = previous.EVENT_TRACE_LIMIT
RESOURCE_RATIO_LIMIT = previous.RESOURCE_RATIO_LIMIT
NANNING_TARGET_P95_REDUCTION = previous.NANNING_TARGET_P95_REDUCTION
NANNING_MEAN_REGRESSION_LIMIT = previous.NANNING_MEAN_REGRESSION_LIMIT
NANNING_TAIL_REGRESSION_LIMIT = previous.NANNING_TAIL_REGRESSION_LIMIT
MAP2_REGRESSION_LIMIT = previous.MAP2_REGRESSION_LIMIT

Executor = Callable[..., Mapping[str, Any]]
WorkloadSlice = previous.WorkloadSlice
PendingRequestHolBypassScreenError = previous.SourceReleaseTieScreenError

_read_preregistration = previous._read_preregistration
_load_workload_slices = previous._load_workload_slices
_rows = previous._rows
_execute_arm = previous._execute_arm


def _resolve_binary(binary: Path) -> Path:
    resolved = binary.resolve(strict=True)
    if not resolved.is_file():
        raise PendingRequestHolBypassScreenError("V3R22 binary must be a file")
    if "build_g32_v3r22" not in {part.lower() for part in resolved.parts}:
        raise PendingRequestHolBypassScreenError(
            "pending-request-HOL-bypass binary must come from build_g32_v3r22"
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
    """Prepare once and derive only the frozen off/A/A+HOL arms."""

    paired, runtime_rows, rejected = stage2._build_pair_requests(
        case, workload, binary=binary
    )
    off = paired["off"]
    candidate_a = paired[HISTORICAL_MODE]
    mode_key = stage2.stage01.NS + "mode"
    if (
        off.get("scorer_mode") != OLD_SCORER
        or candidate_a.get("scorer_mode") != OLD_SCORER
        or off.get("queue_discipline") != HISTORICAL_QUEUE_DISCIPLINE
        or candidate_a.get("queue_discipline") != HISTORICAL_QUEUE_DISCIPLINE
        or candidate_a.get(mode_key) != HISTORICAL_MODE
    ):
        raise PendingRequestHolBypassScreenError(
            "V3R13 off/Candidate-A request identity changed"
        )

    candidate = copy.deepcopy(candidate_a)
    candidate["queue_discipline"] = CANDIDATE_QUEUE_DISCIPLINE
    expected = copy.deepcopy(candidate_a)
    expected["queue_discipline"] = CANDIDATE_QUEUE_DISCIPLINE
    if candidate != expected:
        raise PendingRequestHolBypassScreenError(
            "Candidate A HOL-bypass request has an unregistered delta"
        )
    if candidate.get("event_trace_limit") != EVENT_TRACE_LIMIT:
        raise PendingRequestHolBypassScreenError(
            "generic event trace suppression changed"
        )
    return (
        {
            "off": off,
            "candidate_a": candidate_a,
            "candidate_a_hol_bypass": candidate,
        },
        runtime_rows,
        rejected,
    )


_build_three_arm_requests = _build_arm_requests


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
    eligible_raw_task_ids, eligible_target_segment_ids = shared._eligible_cohorts(
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
    return shared._evaluate_three_arm_case(
        case,
        workload,
        arms=arms,
        runtime_rows=runtime_rows,
        rejected=rejected,
        eligible_raw_task_ids=eligible_raw_task_ids,
        eligible_target_segment_ids=eligible_target_segment_ids,
        primary_arm="candidate_a_hol_bypass",
        attribution_arm="candidate_a",
    )


def run_screen(*, executor: Executor, binary: Path) -> dict[str, Any]:
    """Execute the registered ten cases and thirty fixed arms."""

    resolved_binary = _resolve_binary(binary)
    registration = _read_preregistration()
    slices = _load_workload_slices(registration)
    registered_cases = _rows(registration.get("cases"), "cases")
    cases = []
    for case in registered_cases:
        key = (str(case.get("map_id")), int(case.get("scale", -1)))
        workload = slices.get(key)
        if workload is None:
            raise PendingRequestHolBypassScreenError(
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
        "case_registration": CASE_REGISTRATION_PATH.relative_to(ROOT).as_posix(),
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
        "primary_comparison": "candidate_a_hol_bypass/off",
        "attribution_only_comparison": "candidate_a_hol_bypass/candidate_a",
        "thresholds": {
            "resource_ratio_max": RESOURCE_RATIO_LIMIT,
            "nanning_target_p95_reduction_min": NANNING_TARGET_P95_REDUCTION,
            "nanning_whole_mean_regression_max": NANNING_MEAN_REGRESSION_LIMIT,
            "nanning_whole_p95_p99_regression_max": NANNING_TAIL_REGRESSION_LIMIT,
            "map2_mean_p95_p99_regression_max": MAP2_REGRESSION_LIMIT,
            "peak_rss_core_gate": False,
            "full_mixed_origin_integral_core_gate": False,
        },
        "gates": gates,
        "cases": cases,
    }


run_campaign = run_screen


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF32 V3R22 pending-request HOL-bypass core screen",
        "",
        f"Status: `{result.get('status')}`.",
        "",
        "Primary comparison: `candidate_a_hol_bypass / off`. Candidate A is attribution-only.",
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
            value for value in case["resource_ratios"].values() if value is not None
        ]
        lines.append(
            "| {case_id} | {p95} | {mean} | {resource} | {passed} |".format(
                case_id=case["case_id"],
                p95=shared._format_ratio(p95),
                mean=shared._format_ratio(mean),
                resource=shared._format_ratio(max(resources) if resources else None),
                passed="PASS" if case["pass"] else "FAIL",
            )
        )
    failures = [
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
                [f"- `{case_id}`: " + ", ".join(names) for case_id, names in failures]
                if failures
                else ["None."]
            ),
            "",
            "## Decision",
            "",
            (
                "Core passed; isolated RSS and exact mixed-origin measurement are now required."
                if result.get("core_screen_pass")
                else "Pending-request HOL bypass is NO-GO; Stage 3 remains blocked."
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
    """Publish only the two registered append-only V3R22 outputs."""

    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("V3R22 pending-request-HOL outputs are append-only")
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
            "PENDING_REQUEST_HOL_BYPASS_SCREEN_RUNNER_ERROR: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    write_evidence(result)
    print(result["status"])
    return 0 if result.get("core_screen_pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
