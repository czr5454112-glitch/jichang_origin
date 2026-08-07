#!/usr/bin/env python3
"""Run the compact G19 J2/S1 versus J2/S4 fault campaign.

The campaign reuses G18's protected 8,192-segment fault scenarios and native
executor.  Only the existing one-hop Route scorer changes: frozen S1 is the
baseline and model-free queue-aware S4 is the treatment.  Native opportunity
rows are deliberately discarded after each run; persisted artifacts contain
only paired counters, metrics and deltas.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf18_system_campaign as g18


SCHEMA = "czr005.g4irsf19.route_fault_campaign.v1"
DEFAULT_JSON = Path("outputs/tables/g4irsf19_route_fault_campaign.json")
DEFAULT_CSV = Path("outputs/tables/g4irsf19_route_fault_campaign.csv")
DEFAULT_REPORT = Path("outputs/reports/g4irsf19_route_fault_campaign.md")
DEFAULT_MAINLINE_REPORT = Path(
    "outputs/reports/g4irsf19_fault_parallel_campaign.md"
)

S1_MODE = "S1_frozen_g4e_legal_local_adapter"
S4_MODE = "S4_queue_aware_rule_only"
J2_TIMING_MODE = "jit_fair_aging_deadline"
J2_MERGE_RULE = "M3"

BASELINE_ARM = g18.Arm(
    arm_id="J2_S1_ROUTE_BASELINE",
    timing_mode=J2_TIMING_MODE,
    merge_rule=J2_MERGE_RULE,
    native_controls={"scorer_mode": S1_MODE},
)
TREATMENT_ARM = g18.Arm(
    arm_id="J2_S4_ROUTE_TREATMENT",
    timing_mode=J2_TIMING_MODE,
    merge_rule=J2_MERGE_RULE,
    native_controls={"scorer_mode": S4_MODE},
)
ARMS = (BASELINE_ARM, TREATMENT_ARM)

DELTA_FIELDS = (
    "mean_tth_seconds",
    "source_wait_mean_seconds",
    "merge_grant_wait_mean_seconds",
    "network_time_mean_seconds",
    "event_count",
    "fault_recovery_seconds",
    "notification_update_event_count",
    "notification_drop_count",
    "physical_fault_entry_violation_count",
)


class RouteFaultCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RouteFaultCampaignError(message)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def _output_path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def build_fault_pairs(
    scenarios: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], g18.SystemJob, g18.SystemJob]]:
    """Materialize matched jobs while freezing the protected G18 boundary."""

    _require(bool(scenarios), "fault campaign has no scenarios")
    pairs: list[tuple[Mapping[str, Any], g18.SystemJob, g18.SystemJob]] = []
    seen: set[str] = set()
    for scenario_value in scenarios:
        scenario = dict(scenario_value)
        scenario_id = scenario.get("scenario_id")
        _require(
            isinstance(scenario_id, str) and bool(scenario_id),
            "fault scenario_id is required",
        )
        _require(scenario_id not in seen, "duplicate fault scenario_id")
        seen.add(scenario_id)

        jobs: list[g18.SystemJob] = []
        for arm in ARMS:
            jobs.append(
                g18.SystemJob(
                    job_id=(
                        f"g4irsf19_route_fault__{scenario_id}__"
                        f"{arm.arm_id.lower()}"
                    ),
                    stage="fault",
                    arm_id=arm.arm_id,
                    prefix_segments=g18.DEFAULT_FAULT_PREFIX,
                    fault_scenario=scenario,
                    telemetry_mode="evidence_trace",
                )
            )
        pairs.append((scenario, jobs[0], jobs[1]))
    return pairs


Executor = Callable[[g18.SystemJob, g18.Arm], Mapping[str, Any]]


def make_execute_job_adapter(*, binary: Path, root: Path = ROOT) -> Executor:
    """Adapt the existing G18 executor to the narrow two-argument runner."""

    def execute(job: g18.SystemJob, arm: g18.Arm) -> Mapping[str, Any]:
        return g18.execute_job(job, arm, binary=binary, root=root)

    return execute


def compact_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only fault, safety, business and resource summaries."""

    metrics_value = result.get("metrics")
    counters_value = result.get("counters")
    hard_safety_value = result.get("hard_safety")
    resources_value = result.get("resources")
    _require(isinstance(metrics_value, Mapping), "fault result lacks metrics")
    _require(isinstance(counters_value, Mapping), "fault result lacks counters")
    metrics = metrics_value
    counters = counters_value
    hard_safety = hard_safety_value if isinstance(hard_safety_value, Mapping) else {}
    resources = resources_value if isinstance(resources_value, Mapping) else {}
    return {
        "status": result.get("status"),
        "hard_safety_pass": hard_safety.get("pass"),
        "algorithmic_safety_pass": result.get("algorithmic_safety_pass"),
        "physical_fault_entry_violation_count": _integer(
            counters.get("physical_fault_edge_entry_violation_count")
        ),
        "fault_event_count": _integer(counters.get("fault_event_count")),
        "repair_event_count": _integer(counters.get("repair_event_count")),
        "notification_update_event_count": _integer(
            counters.get("congestion_beacon_update_event_count")
        ),
        "notification_drop_count": _integer(
            counters.get("fault_notification_drop_count")
        ),
        "fault_affected_bag_count": _integer(
            counters.get("fault_affected_bag_count")
        ),
        "fault_affected_completed_count": _integer(
            counters.get("fault_affected_completed_count")
        ),
        "fault_recovery_available": (
            counters.get("fault_recovery_seconds_available") is True
        ),
        "fault_recovery_seconds": _finite(counters.get("fault_recovery_seconds")),
        "mean_tth_seconds": _finite(metrics.get("mean_tth_seconds")),
        "p95_tth_seconds": _finite(metrics.get("p95_tth_seconds")),
        "p99_tth_seconds": _finite(metrics.get("p99_tth_seconds")),
        "source_wait_mean_seconds": _finite(
            metrics.get("source_wait_mean_seconds")
        ),
        "merge_grant_wait_mean_seconds": _finite(
            metrics.get("merge_grant_wait_mean_seconds")
        ),
        "network_time_mean_seconds": _finite(
            metrics.get("network_time_mean_seconds")
        ),
        "event_count": _integer(counters.get("event_count")),
        "completed_count": _integer(counters.get("completed_count")),
        "failed_count": _integer(counters.get("failed_count")),
        "wall_seconds": _finite(resources.get("wall_seconds")),
        "cpu_seconds": _finite(resources.get("cpu_seconds")),
    }


def _delta(treatment: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in DELTA_FIELDS:
        treatment_value = _finite(treatment.get(field))
        baseline_value = _finite(baseline.get(field))
        result[field] = (
            treatment_value - baseline_value
            if treatment_value is not None and baseline_value is not None
            else None
        )
    return result


def aggregate_status(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    """Require every native completion and every declared paired gate."""

    failures: list[str] = []
    if not rows:
        failures.append("campaign:no_scenarios")
    for row in rows:
        scenario_id = str(row.get("scenario_id", "unknown"))
        for arm_name in ("baseline", "treatment"):
            arm = row.get(arm_name)
            status = arm.get("status") if isinstance(arm, Mapping) else None
            if status != "COMPLETE":
                failures.append(
                    f"{scenario_id}:{arm_name}:native_status={status}"
                )
        gates = row.get("paired_gates")
        if not isinstance(gates, Mapping) or not gates:
            failures.append(f"{scenario_id}:paired_gates:missing")
            continue
        for gate_name, passed in gates.items():
            if passed is not True:
                failures.append(f"{scenario_id}:paired_gate:{gate_name}")
    return ("COMPLETE" if not failures else "FAILED_REQUIRED_GATE"), failures


def execute_campaign(
    *,
    binary: Path,
    root: Path = ROOT,
    scenarios: Sequence[Mapping[str, Any]] | None = None,
    executor: Executor | None = None,
) -> dict[str, Any]:
    scenario_values = tuple(scenarios or g18._fault_scenarios(root))
    run = executor or make_execute_job_adapter(binary=binary, root=root)
    rows: list[dict[str, Any]] = []
    for scenario, baseline_job, treatment_job in build_fault_pairs(scenario_values):
        baseline_raw = run(baseline_job, BASELINE_ARM)
        treatment_raw = run(treatment_job, TREATMENT_ARM)
        _require(isinstance(baseline_raw, Mapping), "baseline executor result is not an object")
        _require(isinstance(treatment_raw, Mapping), "treatment executor result is not an object")
        baseline = compact_result(baseline_raw)
        treatment = compact_result(treatment_raw)
        baseline_violation = baseline["physical_fault_entry_violation_count"]
        treatment_violation = treatment["physical_fault_entry_violation_count"]
        rows.append(
            {
                "scenario_id": scenario["scenario_id"],
                "fault": {
                    "edges": scenario.get("edges"),
                    "onset_time": scenario.get("onset_time"),
                    "onset_fraction": scenario.get("onset_fraction"),
                    "duration_seconds": scenario.get("duration_seconds"),
                    "message_delay_seconds": scenario.get(
                        "message_delay_seconds"
                    ),
                    "notification_dropped": scenario.get(
                        "notification_dropped"
                    ),
                },
                "baseline": baseline,
                "treatment": treatment,
                "treatment_minus_baseline": _delta(treatment, baseline),
                "paired_gates": {
                    "both_hard_safety_pass": (
                        baseline["hard_safety_pass"] is True
                        and treatment["hard_safety_pass"] is True
                    ),
                    "both_zero_physical_fault_entry_violations": (
                        baseline_violation == 0 and treatment_violation == 0
                    ),
                    "both_fault_and_repair_events_observed": (
                        (baseline["fault_event_count"] or 0) > 0
                        and (baseline["repair_event_count"] or 0) > 0
                        and (treatment["fault_event_count"] or 0) > 0
                        and (treatment["repair_event_count"] or 0) > 0
                    ),
                    "both_recovery_metrics_available": (
                        baseline["fault_recovery_available"] is True
                        and treatment["fault_recovery_available"] is True
                    ),
                },
            }
        )

    status, failed_requirements = aggregate_status(rows)
    return {
        "schema": SCHEMA,
        "status": status,
        "failed_requirements": failed_requirements,
        "design": {
            "input": "protected_first_8192_file_order",
            "merge_and_timing": "G18 J2 / M3",
            "baseline": BASELINE_ARM.as_dict(),
            "treatment": TREATMENT_ARM.as_dict(),
            "only_changed_control": "scorer_mode",
            "raw_opportunity_rows_persisted": 0,
        },
        "scenario_count": len(rows),
        "scenarios": rows,
    }


CSV_FIELDS = (
    "scenario_id",
    "baseline_status",
    "treatment_status",
    "baseline_hard_safety_pass",
    "treatment_hard_safety_pass",
    "baseline_physical_fault_entry_violation_count",
    "treatment_physical_fault_entry_violation_count",
    "baseline_notification_update_event_count",
    "treatment_notification_update_event_count",
    "baseline_notification_drop_count",
    "treatment_notification_drop_count",
    "baseline_fault_recovery_available",
    "treatment_fault_recovery_available",
    "baseline_fault_recovery_seconds",
    "treatment_fault_recovery_seconds",
    "mean_tth_delta_seconds",
    "source_wait_delta_seconds",
    "merge_grant_wait_delta_seconds",
    "event_count_delta",
    "both_hard_safety_pass",
    "both_zero_physical_fault_entry_violations",
)


def csv_rows(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row_value in campaign.get("scenarios", []):
        _require(isinstance(row_value, Mapping), "campaign scenario is not an object")
        baseline = row_value["baseline"]
        treatment = row_value["treatment"]
        delta = row_value["treatment_minus_baseline"]
        gates = row_value["paired_gates"]
        output.append(
            {
                "scenario_id": row_value["scenario_id"],
                "baseline_status": baseline["status"],
                "treatment_status": treatment["status"],
                "baseline_hard_safety_pass": baseline["hard_safety_pass"],
                "treatment_hard_safety_pass": treatment["hard_safety_pass"],
                "baseline_physical_fault_entry_violation_count": baseline[
                    "physical_fault_entry_violation_count"
                ],
                "treatment_physical_fault_entry_violation_count": treatment[
                    "physical_fault_entry_violation_count"
                ],
                "baseline_notification_update_event_count": baseline[
                    "notification_update_event_count"
                ],
                "treatment_notification_update_event_count": treatment[
                    "notification_update_event_count"
                ],
                "baseline_notification_drop_count": baseline[
                    "notification_drop_count"
                ],
                "treatment_notification_drop_count": treatment[
                    "notification_drop_count"
                ],
                "baseline_fault_recovery_available": baseline[
                    "fault_recovery_available"
                ],
                "treatment_fault_recovery_available": treatment[
                    "fault_recovery_available"
                ],
                "baseline_fault_recovery_seconds": baseline[
                    "fault_recovery_seconds"
                ],
                "treatment_fault_recovery_seconds": treatment[
                    "fault_recovery_seconds"
                ],
                "mean_tth_delta_seconds": delta["mean_tth_seconds"],
                "source_wait_delta_seconds": delta[
                    "source_wait_mean_seconds"
                ],
                "merge_grant_wait_delta_seconds": delta[
                    "merge_grant_wait_mean_seconds"
                ],
                "event_count_delta": delta["event_count"],
                "both_hard_safety_pass": gates["both_hard_safety_pass"],
                "both_zero_physical_fault_entry_violations": gates[
                    "both_zero_physical_fault_entry_violations"
                ],
            }
        )
    return output


def _fmt(value: Any, digits: int = 3) -> str:
    number = _finite(value)
    return "—" if number is None else f"{number:.{digits}f}"


def render_report(campaign: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF19 J2/S4 fault evidence",
        "",
        f"Campaign status: **`{campaign.get('status', 'UNKNOWN')}`**.",
        "",
        (
            "This is a paired 8,192-segment regression over the protected G18 "
            "fault catalogue. S1 and S4 share J2/M3 and every other runtime "
            "control; only the one-hop Route scorer changes."
        ),
        "",
        "Raw opportunity rows persisted: **0**.",
        "",
        (
            "| Scenario | Hard safety S1/S4 | Physical entry violations S1/S4 | "
            "Notification updates S1/S4 | Drops S1/S4 | Recovery s S1/S4 | "
            "ΔTTH s | Δsource wait s | Δmerge wait s | Δevents |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in campaign.get("scenarios", []):
        baseline = row["baseline"]
        treatment = row["treatment"]
        delta = row["treatment_minus_baseline"]
        lines.append(
            f"| {row['scenario_id']} | "
            f"{baseline['hard_safety_pass']}/{treatment['hard_safety_pass']} | "
            f"{baseline['physical_fault_entry_violation_count']}/"
            f"{treatment['physical_fault_entry_violation_count']} | "
            f"{baseline['notification_update_event_count']}/"
            f"{treatment['notification_update_event_count']} | "
            f"{baseline['notification_drop_count']}/"
            f"{treatment['notification_drop_count']} | "
            f"{_fmt(baseline['fault_recovery_seconds'])}/"
            f"{_fmt(treatment['fault_recovery_seconds'])} | "
            f"{_fmt(delta['mean_tth_seconds'])} | "
            f"{_fmt(delta['source_wait_mean_seconds'])} | "
            f"{_fmt(delta['merge_grant_wait_mean_seconds'])} | "
            f"{_fmt(delta['event_count'], 0)} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            (
                "A negative delta means S4 used less time or fewer events than "
                "S1 on the same protected input and fault window. Missing "
                "recovery values remain missing; they are not imputed. This "
                "campaign is fault evidence for the existing decentralized "
                "one-hop scorer, not a production promotion decision."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    campaign: Mapping[str, Any],
    *,
    root: Path = ROOT,
    json_path: Path = DEFAULT_JSON,
    csv_path: Path = DEFAULT_CSV,
    report_path: Path = DEFAULT_REPORT,
    mainline_report_path: Path = DEFAULT_MAINLINE_REPORT,
) -> tuple[Path, Path, Path, Path]:
    resolved_json = _output_path(root, json_path)
    resolved_csv = _output_path(root, csv_path)
    resolved_report = _output_path(root, report_path)
    resolved_mainline_report = _output_path(root, mainline_report_path)
    _atomic_json(resolved_json, campaign)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv_rows(campaign))
    _atomic_text(resolved_csv, stream.getvalue())
    report = render_report(campaign)
    _atomic_text(resolved_report, report)
    _atomic_text(resolved_mainline_report, report)
    return resolved_json, resolved_csv, resolved_report, resolved_mainline_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--mainline-report-output", type=Path, default=DEFAULT_MAINLINE_REPORT
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign = execute_campaign(binary=args.binary, root=args.root)
    paths = write_outputs(
        campaign,
        root=args.root,
        json_path=args.json_output,
        csv_path=args.csv_output,
        report_path=args.report_output,
        mainline_report_path=args.mainline_report_output,
    )
    print(
        json.dumps(
            {
                "schema": campaign["schema"],
                "status": campaign.get("status"),
                "scenario_count": campaign["scenario_count"],
                "outputs": [str(path) for path in paths],
            },
            ensure_ascii=False,
        )
    )
    return 0 if campaign.get("status") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
