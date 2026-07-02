from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "outputs" / "reports" / "g3e_event_semantics_repair_report.md"
REACHABILITY_TABLE = ROOT / "outputs" / "tables" / "g3e_repair_window_reachability_cases.csv"
MATCHED_GATE_TABLE = ROOT / "outputs" / "tables" / "g3e_matched_gate_after_repair.csv"
G3D_VARIANT_SUMMARY = ROOT / "outputs" / "tables" / "g3d_teacher_replay_variant_summary.csv"


@dataclass(frozen=True)
class ReachabilityCase:
    case: str
    current: int
    goal: int
    ready_time: float
    fault_edges: set[tuple[int, int]]
    fault_windows: tuple[tuple[int, int, float, float], ...]
    expected_safe: bool
    expected_absent_reason: str
    expected_present_reason: str
    why: str


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _line_graph() -> Any:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode

    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1,)),
            1: SimNode(location=1, node_type=4, service_time=1.0, x=1, y=0, outgoing=(2,)),
            2: SimNode(location=2, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5),
            (1, 2): SimEdge(start=1, end=2, length=5.0, speed=2.5),
        },
        heuristic_time=((0.0, 2.0, 4.0), (4.0, 0.0, 2.0), (4.0, 2.0, 0.0)),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _task(segment_id: str = "repair", task_id: int = 1, goal: int = 2) -> Any:
    from czr005.sim_py.task_stream import TaskLeg

    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=0.0,
        std=20.0,
        start=0,
        goal=goal,
        original_start=0,
        original_goal=goal,
        original_entry_time=0.0,
        leg="direct",
        early_bag_split=False,
        source_line=1,
    )


def _reachability_cases() -> tuple[ReachabilityCase, ...]:
    return (
        ReachabilityCase(
            case="repairable_downstream_fault",
            current=0,
            goal=2,
            ready_time=0.0,
            fault_edges=set(),
            fault_windows=((1, 2, 0.0, 5.0),),
            expected_safe=True,
            expected_absent_reason="unreachable_goal",
            expected_present_reason="",
            why="upstream move 0->1 should stay available so the bag can wait at node 1 until edge 1->2 repairs",
        ),
        ReachabilityCase(
            case="permanent_downstream_fault",
            current=0,
            goal=2,
            ready_time=0.0,
            fault_edges={(1, 2)},
            fault_windows=(),
            expected_safe=False,
            expected_absent_reason="",
            expected_present_reason="unreachable_goal",
            why="permanent downstream fault should still make candidate 0->1 unreachable",
        ),
        ReachabilityCase(
            case="currently_faulted_candidate_edge",
            current=0,
            goal=2,
            ready_time=4.0,
            fault_edges=set(),
            fault_windows=((0, 1, 0.0, 5.0),),
            expected_safe=False,
            expected_absent_reason="",
            expected_present_reason="fault_edge",
            why="the repair-horizon fix must not make the currently faulted edge itself safe",
        ),
    )


def _run_reachability_cases() -> list[dict[str, Any]]:
    from czr005.envs.action_mask import build_action_candidates
    from czr005.sim_py import EdgeReservationTable, ReservationTable

    graph = _line_graph()
    rows: list[dict[str, Any]] = []
    for case in _reachability_cases():
        candidates = build_action_candidates(
            graph=graph,
            task=_task(case.case, 1, case.goal),
            current=case.current,
            ready_time=case.ready_time,
            reservations=ReservationTable(),
            edge_reservations=EdgeReservationTable(),
            fault_edges=case.fault_edges,
            fault_windows=case.fault_windows,
        )
        candidate = candidates[0]
        reasons = tuple(str(reason) for reason in candidate.blocked_reasons)
        absent_pass = not case.expected_absent_reason or case.expected_absent_reason not in reasons
        present_pass = not case.expected_present_reason or case.expected_present_reason in reasons
        safe_pass = bool(candidate.safe) == case.expected_safe
        rows.append(
            {
                "case": case.case,
                "current": case.current,
                "next_node": candidate.next_node,
                "goal": case.goal,
                "ready_time": case.ready_time,
                "candidate_safe": candidate.safe,
                "blocked_reasons": "+".join(reasons) if reasons else "none",
                "expected_safe": case.expected_safe,
                "expected_absent_reason": case.expected_absent_reason,
                "expected_present_reason": case.expected_present_reason,
                "case_pass": safe_pass and absent_pass and present_pass,
                "why": case.why,
            }
        )
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _matched_gate_rows() -> list[dict[str, Any]]:
    rows = _read_csv(G3D_VARIANT_SUMMARY)
    aggregate = [row for row in rows if row.get("scenario") == "ALL"]
    selected = []
    for row in aggregate:
        variant = row["replay_variant"]
        if variant not in {
            "g3c_baseline_reproduction",
            "jump_to_earliest_safe_time",
            "reroute_from_current_legacy",
            "wait_fixed_hold_5s",
            "hybrid_legacy_wait_sipp_fallback",
            "ablation_disable_edge_capacity",
            "ablation_edge_capacity_2",
        }:
            continue
        planned = int(row["planned_count"])
        branch_coverage = float(row["branch_effective_label_coverage"])
        conflicts = int(row["post_shield_conflicts"])
        real_conflicts = int(row["real_constraint_conflicts"])
        selected.append(
            {
                "replay_variant": variant,
                "planned_count": planned,
                "max_tasks": int(row["max_tasks"]),
                "branch_effective_label_coverage": branch_coverage,
                "post_shield_conflicts": conflicts,
                "real_constraint_conflicts": real_conflicts,
                "g4a_gate_pass": planned >= 115 and branch_coverage >= 0.75 and conflicts == 0 and real_conflicts == 0,
                "diagnostic_only": str(row["diagnostic_ablation"]).lower() == "true" or real_conflicts > 0,
            }
        )
    return selected


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, set):
        return ";".join(str(item) for item in sorted(value))
    return value


def _write_report(reachability_rows: list[dict[str, Any]], matched_rows: list[dict[str, Any]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_reachability_pass = all(str(row["case_pass"]) == "True" or row["case_pass"] is True for row in reachability_rows)
    best_primary = max(
        (row for row in matched_rows if not row["diagnostic_only"] and row["replay_variant"] != "hybrid_legacy_wait_sipp_fallback"),
        key=lambda row: (int(row["planned_count"]), float(row["branch_effective_label_coverage"])),
    )
    edge_ablation = next(row for row in matched_rows if row["replay_variant"] == "ablation_disable_edge_capacity")
    decision = (
        "Continue event-capacity repair before G4A. The repair-window reachability fix is validated, "
        f"but best primary replay is still {best_primary['planned_count']}/144, below the 115/144 gate. "
        f"Edge-capacity ablation reaches {edge_ablation['planned_count']}/144 but has "
        f"{edge_ablation['real_constraint_conflicts']} real-constraint conflicts, so the remaining blocker is not safe to bypass."
    )
    lines = [
        "# G3e Event-Semantics Repair",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This pass fixes and validates one concrete event-horizon semantic bug: downstream repair-window faults should not make upstream waiting nodes look permanently unreachable. It is not training, not G4A scaling, and not a relaxation of hard edge-capacity safety.",
        "",
        "## Repair-Window Reachability Cases",
        "",
        _markdown_table(
            ["Case", "Safe", "Reasons", "Pass"],
            [[row["case"], row["candidate_safe"], row["blocked_reasons"], row["case_pass"]] for row in reachability_rows],
        ),
        "",
        f"Reachability semantic tests: `{'PASS' if all_reachability_pass else 'FAIL'}`.",
        "",
        "## Matched-Window Gate After Repair",
        "",
        _markdown_table(
            ["Variant", "Planned", "Branch Coverage", "Conflicts", "Real Conflicts", "Gate"],
            [
                [
                    row["replay_variant"],
                    f"{row['planned_count']}/{row['max_tasks']}",
                    f"{float(row['branch_effective_label_coverage']):.3f}",
                    row["post_shield_conflicts"],
                    row["real_constraint_conflicts"],
                    row["g4a_gate_pass"],
                ]
                for row in matched_rows
            ],
        ),
        "",
        "## Decision",
        "",
        decision,
        "",
        "## Artifacts",
        "",
        f"- Reachability cases: `{_relative(REACHABILITY_TABLE)}`",
        f"- Matched gate table: `{_relative(MATCHED_GATE_TABLE)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def main() -> None:
    _prepare_imports()
    reachability_rows = _run_reachability_cases()
    matched_rows = _matched_gate_rows()
    if not matched_rows:
        raise AssertionError("G3e requires regenerated G3d variant summary rows")
    _write_csv(
        REACHABILITY_TABLE,
        reachability_rows,
        [
            "case",
            "current",
            "next_node",
            "goal",
            "ready_time",
            "candidate_safe",
            "blocked_reasons",
            "expected_safe",
            "expected_absent_reason",
            "expected_present_reason",
            "case_pass",
            "why",
        ],
    )
    _write_csv(
        MATCHED_GATE_TABLE,
        matched_rows,
        [
            "replay_variant",
            "planned_count",
            "max_tasks",
            "branch_effective_label_coverage",
            "post_shield_conflicts",
            "real_constraint_conflicts",
            "g4a_gate_pass",
            "diagnostic_only",
        ],
    )
    _write_report(reachability_rows, matched_rows)
    if not all(bool(row["case_pass"]) for row in reachability_rows):
        raise AssertionError("repair-window reachability case failed")
    print(f"g3e complete: reachability_cases={len(reachability_rows)} matched_rows={len(matched_rows)}")


if __name__ == "__main__":
    main()
