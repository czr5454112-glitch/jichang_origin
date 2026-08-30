#!/usr/bin/env python3
"""Run the frozen V3R15 commit-triggered Candidate-A core screen.

The V3R13 Stage-2 registration remains the population, case, fault, cohort,
metric, and threshold authority.  This runner changes only the third arm's
append-only extension spelling and reuses the V3R14 three-arm gate evaluator.
Import and injected execution do not load the native extension or write
evidence.
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
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r14_candidate_b_screen as shared,
)


SCHEMA = "czr005.g4irsf32.v3r15.candidate_a_commit_recheck_screen.v1"
PROTOCOL_ID = "G4IRSF32_V3R15_CANDIDATE_A_COMMIT_RECHECK_20260829"
MEASUREMENT_REQUIRED = (
    "MEASUREMENT_REQUIRED_V3R15_CANDIDATE_A_COMMIT_RECHECK"
)
NO_GO = "NO_GO_V3R15_CANDIDATE_A_COMMIT_RECHECK"
PASS = MEASUREMENT_REQUIRED

PREREGISTRATION_PATH = (
    ROOT / "docs/G4IRSF32_v3r15_candidate_a_commit_recheck_preregistration.md"
)
CASE_REGISTRATION_PATH = stage2.PREREGISTRATION_PATH
OUTPUT_JSON = (
    ROOT
    / "outputs/tables/g4irsf32_v3r15_candidate_a_commit_recheck_screen.json"
)
OUTPUT_MD = (
    ROOT
    / "outputs/reports/g4irsf32_v3r15_candidate_a_commit_recheck_screen.md"
)

ARMS = ("off", "candidate_a", "candidate_a_recheck")
OLD_SCORER = shared.OLD_SCORER
HISTORICAL_MODE = "closed_loop"
RECHECK_MODE = "closed_loop_commit_recheck"
EVENT_TRACE_LIMIT = stage2.EVENT_TRACE_LIMIT
RESOURCE_RATIO_LIMIT = stage2.RESOURCE_RATIO_LIMIT
NANNING_TARGET_P95_REDUCTION = stage2.NANNING_TARGET_P95_REDUCTION
NANNING_MEAN_REGRESSION_LIMIT = stage2.NANNING_MEAN_REGRESSION_LIMIT
NANNING_TAIL_REGRESSION_LIMIT = stage2.NANNING_TAIL_REGRESSION_LIMIT
MAP2_REGRESSION_LIMIT = stage2.MAP2_REGRESSION_LIMIT

Executor = Callable[..., Mapping[str, Any]]
WorkloadSlice = stage2.WorkloadSlice
CandidateARecheckScreenError = stage2.Stage2CampaignError

_read_preregistration = stage2._read_preregistration
_load_workload_slices = stage2._load_workload_slices
_rows = stage2._rows
_mapping = stage2._mapping


def _resolve_binary(binary: Path) -> Path:
    """Bind formal execution to an explicit V3R15 build without loading it."""

    resolved = binary.resolve(strict=True)
    if not resolved.is_file():
        raise CandidateARecheckScreenError("V3R15 binary must be a file")
    if "build_g32_v3r15" not in {part.lower() for part in resolved.parts}:
        raise CandidateARecheckScreenError(
            "Candidate-A recheck binary must come from build_g32_v3r15"
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
    """Prepare once and derive the exact off/A/A+recheck arms."""

    paired, runtime_rows, rejected = stage2._build_pair_requests(
        case, workload, binary=binary
    )
    off = paired["off"]
    candidate_a = paired[HISTORICAL_MODE]
    mode_key = stage2.stage01.NS + "mode"

    if off.get("scorer_mode") != OLD_SCORER:
        raise CandidateARecheckScreenError("V3R13 off-arm scorer changed")
    if candidate_a.get("scorer_mode") != OLD_SCORER:
        raise CandidateARecheckScreenError("V3R13 Candidate-A scorer changed")
    if candidate_a.get(mode_key) != HISTORICAL_MODE:
        raise CandidateARecheckScreenError("historical Candidate-A mode changed")

    candidate_a_recheck = copy.deepcopy(candidate_a)
    candidate_a_recheck[mode_key] = RECHECK_MODE
    if candidate_a_recheck.get("event_trace_limit") != EVENT_TRACE_LIMIT:
        raise CandidateARecheckScreenError("generic event trace suppression changed")

    expected = copy.deepcopy(candidate_a)
    expected[mode_key] = RECHECK_MODE
    if candidate_a_recheck != expected:
        raise CandidateARecheckScreenError(
            "Candidate-A recheck request has an unregistered delta"
        )
    return (
        {
            "off": off,
            "candidate_a": candidate_a,
            "candidate_a_recheck": candidate_a_recheck,
        },
        runtime_rows,
        rejected,
    )


_build_three_arm_requests = _build_arm_requests


def _execute_arm(
    executor: Executor,
    request: Mapping[str, Any],
    *,
    workload: WorkloadSlice,
    arm: str,
    eligible_raw_task_ids: frozenset[int],
    eligible_target_segment_ids: frozenset[str],
) -> dict[str, Any]:
    expected_mode = {
        "off": "off",
        "candidate_a": HISTORICAL_MODE,
        "candidate_a_recheck": RECHECK_MODE,
    }[arm]
    expected_scorer = OLD_SCORER
    observed_identity: dict[str, str] = {}

    def identity_checked_executor(**native_request: Any) -> Mapping[str, Any]:
        payload = executor(**native_request)
        if not isinstance(payload, Mapping):
            raise CandidateARecheckScreenError("executor must return a mapping")
        summary = _mapping(payload.get("summary"), "payload.summary")
        scorer_mode_echo = summary.get("scorer_mode_echo")
        scorer_id = summary.get("scorer_id")
        if scorer_mode_echo != expected_scorer or scorer_id != expected_scorer:
            raise CandidateARecheckScreenError(
                f"{arm}: native scorer identity does not match {expected_scorer}"
            )
        if arm == "off":
            if stage2.stage01.NS + "mode" in summary:
                raise CandidateARecheckScreenError(
                    "off: native extension mode must be absent"
                )
        elif summary.get(stage2.stage01.NS + "mode") != expected_mode:
            raise CandidateARecheckScreenError(
                f"{arm}: native extension mode echo does not match {expected_mode}"
            )
        observed_identity.update(
            scorer_mode_echo=str(scorer_mode_echo),
            scorer_id=str(scorer_id),
        )
        if arm != "off":
            observed_identity["extension_mode_echo"] = expected_mode
        return payload

    metrics = stage2._execute_arm(
        identity_checked_executor,
        request,
        workload=workload,
        mode=expected_mode,
        expected_extension_mode=(None if arm == "off" else expected_mode),
        eligible_raw_task_ids=eligible_raw_task_ids,
        eligible_target_segment_ids=eligible_target_segment_ids,
    )
    metrics["arm"] = arm
    metrics["scorer_mode"] = expected_scorer
    metrics.update(observed_identity)
    return metrics


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
        primary_arm="candidate_a_recheck",
        attribution_arm="candidate_a",
    )


def run_screen(*, executor: Executor, binary: Path) -> dict[str, Any]:
    """Execute the ten registered cases and thirty fixed injected/native arms."""

    resolved_binary = _resolve_binary(binary)
    registration = _read_preregistration()
    slices = _load_workload_slices(registration)
    registered_cases = _rows(registration.get("cases"), "cases")
    cases = []
    for case in registered_cases:
        key = (str(case.get("map_id")), int(case.get("scale", -1)))
        workload = slices.get(key)
        if workload is None:
            raise CandidateARecheckScreenError(
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
        "primary_comparison": "candidate_a_recheck/off",
        "attribution_only_comparison": "candidate_a_recheck/candidate_a",
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


run_campaign = run_screen


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF32 V3R15 Candidate A commit-recheck core screen",
        "",
        f"Status: `{result.get('status')}`.",
        "",
        "Primary comparison: `candidate_a_recheck / off`. Historical "
        "Candidate A attribution is diagnostic only.",
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
                "Core screen passed. Isolated RSS and exact mixed-origin "
                "measurement support is required before any Stage 3 decision."
                if result.get("core_screen_pass")
                else "Candidate A commit recheck is NO-GO; Stage 3 remains blocked."
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
    """Publish only the two registered append-only V3R15 outputs."""

    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("V3R15 commit-recheck outputs are append-only")
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
            f"CANDIDATE_A_RECHECK_SCREEN_RUNNER_ERROR: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    write_evidence(result)
    print(result["status"])
    return 0 if result.get("core_screen_pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
