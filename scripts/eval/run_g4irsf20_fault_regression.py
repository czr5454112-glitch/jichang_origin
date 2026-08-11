#!/usr/bin/env python3
"""Check G20 event pruning on two protected 8,192-segment-prefix fault cases.

The matched arms both use the G19 A0 + S4 + J2 controller.  The only changed
runtime control is the G20 event-hotpath policy (E0 versus E2 by default).
Per-bag bounded action and complete timing projections are compared in memory
and discarded;
only compact gates and counters are written.
"""

from __future__ import annotations

import argparse
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

from scripts.eval import run_g4irsf18_jit_campaign as jit
from scripts.eval import run_g4irsf18_system_campaign as g18
from scripts.eval import run_g4irsf19_route_fault_campaign as g19_fault
from scripts.eval import run_g4irsf20_event_hotpath as hotpath


SCHEMA = "czr005.g4irsf20.fault_regression.v1"
DEFAULT_JSON = Path("outputs/tables/g4irsf20_fault_regression.json")
DEFAULT_REPORT = Path("outputs/reports/g4irsf20_fault_regression.md")
S4_MODE = "S4_queue_aware_rule_only"
J2_TIMING_MODE = "jit_fair_aging_deadline"
J2_MERGE_RULE = "M3"
POLICIES = ("E1", "E2")


class FaultRegressionError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FaultRegressionError(message)


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def build_fault_jobs(
    scenarios: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], g18.SystemJob]]:
    """Freeze the same protected input and fault windows used by G19."""

    _require(bool(scenarios), "fault regression has no scenarios")
    jobs: list[tuple[Mapping[str, Any], g18.SystemJob]] = []
    seen: set[str] = set()
    for value in scenarios:
        scenario = dict(value)
        scenario_id = scenario.get("scenario_id")
        _require(isinstance(scenario_id, str) and bool(scenario_id), "scenario_id is required")
        _require(scenario_id not in seen, "duplicate scenario_id")
        seen.add(scenario_id)
        jobs.append(
            (
                scenario,
                g18.SystemJob(
                    job_id=f"g4irsf20_fault__{scenario_id}",
                    stage="fault",
                    arm_id="A0_S4_J2",
                    prefix_segments=g18.DEFAULT_FAULT_PREFIX,
                    fault_scenario=scenario,
                    telemetry_mode="evidence_trace",
                ),
            )
        )
    return jobs


def build_native_request(
    job: g18.SystemJob,
    *,
    policy: str,
    binary: Path,
    root: Path = ROOT,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Build the G18/G19 protected fault request with only policy variable."""

    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS

    _require(policy in ("E0", *POLICIES), f"unsupported hotpath policy: {policy}")
    rows, descriptor = g18._load_input(job, root)
    fault_windows, fault_descriptor = g18._fault_windows(job.fault_scenario, rows)
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=jit._binding_rows(rows),
        fault_windows=fault_windows,
        scenario=f"g4irsf20_fault_{job.job_id}_{policy.lower()}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        search_path=binary.resolve(strict=True).parent,
        g4irsf16_supervisor_mode="off",
        scorer_mode=S4_MODE,
        merge_grant_rule=J2_MERGE_RULE,
        merge_grant_timing_mode=J2_TIMING_MODE,
        g4irsf20_event_hotpath_policy=policy,
    )
    return request, rows, {**descriptor, "fault": fault_descriptor}


def _compact_payload(
    payload: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    policy: str,
    wall_seconds: float,
    cpu_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = payload.get("summary")
    bags = payload.get("bags")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(isinstance(bags, list), "native payload lacks bag rows")
    bag_rows = [row for row in bags if isinstance(row, Mapping)]
    _require(len(bag_rows) == len(bags), "native bag rows contain a non-object")
    _require(summary.get("scorer_mode") == S4_MODE, "S4 scorer echo drift")
    _require(summary.get("merge_grant_timing_mode") == J2_TIMING_MODE, "J2 echo drift")
    echo = summary.get("g4irsf20_event_hotpath_policy")
    _require(echo in (None, "E0") if policy == "E0" else echo == policy, "policy echo drift")

    raw = jit._raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    all_complete = len(completed) == len(raw)
    safety = jit._hard_safety(summary, len(rows))
    tth = [float(row["tth_seconds"]) for row in completed]
    affected = _integer(summary.get("fault_affected_bag_count")) or 0
    affected_complete = _integer(summary.get("fault_affected_completed_count")) or 0
    compact = {
        "policy": policy,
        "status": "COMPLETE" if all_complete and safety["pass"] else "FAULT_GATE_FAILED",
        "requested_segment_count": len(rows),
        "raw_bag_count": len(raw),
        "completed_bag_count": len(completed),
        "failed_count": _integer(summary.get("failed_count")) or 0,
        "hard_safety_pass": safety["pass"],
        "physical_fault_entry_violation_count": (
            _integer(summary.get("physical_fault_edge_entry_violation_count")) or 0
        ),
        "fault_event_count": _integer(summary.get("fault_event_count")) or 0,
        "repair_event_count": _integer(summary.get("repair_event_count")) or 0,
        "fault_affected_bag_count": affected,
        "fault_affected_completed_count": affected_complete,
        "all_affected_tasks_completed": affected > 0 and affected_complete == affected,
        "notification_update_event_count": (
            _integer(summary.get("congestion_beacon_update_event_count")) or 0
        ),
        "notification_drop_count": _integer(summary.get("fault_notification_drop_count")) or 0,
        "mean_tth_seconds": statistics.fmean(tth) if all_complete and tth else None,
        "event_count": _integer(summary.get("event_count")) or 0,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
    }
    semantic = {
        "actions": hotpath._action_projection(bag_rows),
        "tth": hotpath._tth_projection(raw),
        "hard_safety": dict(safety["gates"]),
    }
    return compact, semantic


Executor = Callable[[g18.SystemJob, str], tuple[Mapping[str, Any], Mapping[str, Any]]]


def make_executor(*, binary: Path, root: Path = ROOT) -> Executor:
    def execute(job: g18.SystemJob, policy: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        from czr005 import cpp_backend

        request, rows, descriptor = build_native_request(
            job, policy=policy, binary=binary, root=root
        )
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
        cpu_seconds = time.process_time() - cpu_start
        wall_seconds = time.perf_counter() - wall_start
        _require(isinstance(payload, Mapping), "native result is not an object")
        return _compact_payload(
            payload,
            rows=rows,
            descriptor=descriptor,
            policy=policy,
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
        )

    return execute


def execute_campaign(
    *,
    binary: Path,
    policy: str = "E2",
    root: Path = ROOT,
    scenarios: Sequence[Mapping[str, Any]] | None = None,
    executor: Executor | None = None,
) -> dict[str, Any]:
    _require(policy in POLICIES, f"treatment policy must be one of {POLICIES}")
    scenario_values = tuple(scenarios or g18._fault_scenarios(root))
    run = executor or make_executor(binary=binary, root=root)
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for scenario, job in build_fault_jobs(scenario_values):
        baseline, baseline_semantic = run(job, "E0")
        treatment, treatment_semantic = run(job, policy)
        scenario_id = str(scenario["scenario_id"])
        gates = {
            "both_complete": baseline.get("status") == treatment.get("status") == "COMPLETE",
            "both_zero_physical_fault_entry_violations": (
                baseline.get("physical_fault_entry_violation_count") == 0
                and treatment.get("physical_fault_entry_violation_count") == 0
            ),
            "both_affected_task_sets_complete": (
                baseline.get("all_affected_tasks_completed") is True
                and treatment.get("all_affected_tasks_completed") is True
            ),
            "action_semantics_equal_to_e0": (
                baseline_semantic.get("actions") == treatment_semantic.get("actions")
            ),
            "per_task_tth_equal_to_e0": hotpath._close(
                baseline_semantic.get("tth"), treatment_semantic.get("tth")
            ),
            "hard_safety_semantics_equal_to_e0": (
                baseline_semantic.get("hard_safety")
                == treatment_semantic.get("hard_safety")
            ),
        }
        for name, passed in gates.items():
            if passed is not True:
                failures.append(f"{scenario_id}:{name}")
        rows.append(
            {
                "scenario_id": scenario_id,
                "fault": {
                    "edges": scenario.get("edges"),
                    "onset_time": scenario.get("onset_time"),
                    "onset_fraction": scenario.get("onset_fraction"),
                    "duration_seconds": scenario.get("duration_seconds"),
                },
                "baseline": dict(baseline),
                "treatment": dict(treatment),
                "paired_gates": gates,
                "treatment_minus_baseline": {
                    "mean_tth_seconds": (
                        (_finite(treatment.get("mean_tth_seconds")) or 0.0)
                        - (_finite(baseline.get("mean_tth_seconds")) or 0.0)
                    ),
                    "event_count": (
                        (_integer(treatment.get("event_count")) or 0)
                        - (_integer(baseline.get("event_count")) or 0)
                    ),
                },
            }
        )
    return {
        "schema": SCHEMA,
        "status": "COMPLETE" if not failures else "FAILED_REQUIRED_GATE",
        "failed_requirements": failures,
        "design": {
            "input": "protected_first_8192_file_order",
            "controller": "A0 + S4 + J2 (M3 destination-grant rule)",
            "baseline_policy": "E0",
            "treatment_policy": policy,
            "only_changed_control": "g4irsf20_event_hotpath_policy",
            "raw_bag_and_semantic_rows_persisted": 0,
        },
        "claim_boundary": {
            "immediate_fault_notifications": "EVALUATED",
            "delayed_or_dropped_fault_notifications": "NOT_EVALUATED_IN_G4IRSF20",
        },
        "scenario_count": len(rows),
        "scenarios": rows,
    }


def render_report(campaign: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF20 event-hotpath fault regression",
        "",
        f"Campaign status: **`{campaign.get('status', 'UNKNOWN')}`**.",
        "",
        (
            "This matched regression keeps A0 + S4 + J2 (M3 destination-grant "
            "rule) and two protected 8,192-segment-prefix fault cases fixed. "
            "Only the event-hotpath policy changes."
        ),
        "",
        "| Scenario | Policy | Complete E0/new | Physical entries E0/new | Affected complete E0/new | Bounded action projection equal | Per-task TTH equal | Event delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in campaign.get("scenarios", []):
        baseline = row["baseline"]
        treatment = row["treatment"]
        gates = row["paired_gates"]
        lines.append(
            f"| {row['scenario_id']} | {treatment['policy']} | "
            f"{baseline['status']}/{treatment['status']} | "
            f"{baseline['physical_fault_entry_violation_count']}/"
            f"{treatment['physical_fault_entry_violation_count']} | "
            f"{baseline['fault_affected_completed_count']}/{baseline['fault_affected_bag_count']} ; "
            f"{treatment['fault_affected_completed_count']}/{treatment['fault_affected_bag_count']} | "
            f"{gates['action_semantics_equal_to_e0']} | "
            f"{gates['per_task_tth_equal_to_e0']} | "
            f"{row['treatment_minus_baseline']['event_count']} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            (
                "The comparison covers immediate fault notifications only. Delayed and "
                "dropped notification behavior remains explicitly unevaluated in G4IRSF20; "
                "notification counters are descriptive and are not used as proof for that case."
            ),
            "",
            "Per-bag final/count/last-eight action projections and complete timing projections were compared in memory and were not persisted; this is not a full action-trace claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    campaign: Mapping[str, Any],
    *,
    root: Path = ROOT,
    json_path: Path = DEFAULT_JSON,
    report_path: Path = DEFAULT_REPORT,
) -> tuple[Path, Path]:
    resolved_json = _rooted(root, json_path)
    resolved_report = _rooted(root, report_path)
    g19_fault._atomic_json(resolved_json, campaign)
    g19_fault._atomic_text(resolved_report, render_report(campaign))
    return resolved_json, resolved_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", choices=POLICIES, default="E2")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign = execute_campaign(binary=args.binary, policy=args.policy, root=args.root)
    paths = write_outputs(
        campaign,
        root=args.root,
        json_path=args.json_output,
        report_path=args.report_output,
    )
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "status": campaign["status"],
                "scenario_count": campaign["scenario_count"],
                "outputs": [str(path) for path in paths],
            },
            ensure_ascii=False,
        )
    )
    return 0 if campaign["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
