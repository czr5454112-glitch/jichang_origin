from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
G4D_CLOSED_LOOP = ROOT / "outputs" / "tables" / "g4d_closed_loop_summary.csv"
G4E_CLOSED_LOOP = ROOT / "outputs" / "tables" / "g4e_closed_loop_comparison.csv"
G4E_DEVIATION = ROOT / "outputs" / "tables" / "g4e_learner_deviation_outcomes.csv"
G4D_TEACHER_SUMMARY = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4D_INTERFACE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"

ACCOUNTING_REPORT = ROOT / "outputs" / "reports" / "g4e_runtime_call_accounting_report.md"
NEXT_GATE_REPORT = ROOT / "outputs" / "reports" / "g4e_next_gate_decision_report.md"
ASTAR_TABLE = ROOT / "outputs" / "tables" / "g4e_astar_call_accounting.csv"
NEXT_GATE_TABLE = ROOT / "outputs" / "tables" / "g4e_next_gate.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _teacher_stats() -> dict[str, int]:
    summary = _read_csv(G4D_TEACHER_SUMMARY)
    return {
        "window_tasks": sum(int(row["max_tasks"]) for row in summary),
        "teacher_planned": sum(int(row["planned"]) for row in summary),
        "teacher_unplanned": sum(int(row["unplanned"]) for row in summary),
        "original_astar_calls": sum(int(row["total_retry_attempts"]) for row in summary),
        "interface_decisions": sum(1 for _ in _read_csv(G4D_INTERFACE)),
    }


def _deviation_inference_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _read_csv(G4E_DEVIATION):
        mode = row["mode"]
        counts[mode] = counts.get(mode, 0) + int(row["steps"])
    return counts


def _accounting_rows() -> list[dict[str, Any]]:
    stats = _teacher_stats()
    original = stats["original_astar_calls"]
    interface_decisions = stats["interface_decisions"]
    g4d_rows = {row["policy"]: row for row in _read_csv(G4D_CLOSED_LOOP)}
    g4e_rows = {row["mode"]: row for row in _read_csv(G4E_CLOSED_LOOP)}
    inference_counts = _deviation_inference_counts()
    rows = [
        {
            "policy": "cie_retry_teacher_baseline",
            "role": "original_cost_reference",
            "planned_count": stats["teacher_planned"],
            "teacher_planned_scope": stats["teacher_planned"],
            "node_window_conflicts": 0,
            "model_inference_count": 0,
            "fallback_astar_calls": original,
            "original_cie_retry_astar_calls": original,
            "interface_level_astar_saved_rate": "",
            "task_zero_fallback_count": 0,
            "task_zero_fallback_share": 0.0,
            "astar_call_reduction_rate": 0.0,
            "call_count_interpretation": "original task-level CIE retry baseline",
        },
        {
            "policy": "g4d_route_exact_risk_head",
            "role": "previous_g4d_baseline",
            "planned_count": int(g4d_rows["g4d_enhanced_mlp_risk_head"]["planned_count"]),
            "teacher_planned_scope": int(g4d_rows["g4d_enhanced_mlp_risk_head"]["teacher_planned_count"]),
            "node_window_conflicts": int(g4d_rows["g4d_enhanced_mlp_risk_head"]["node_window_conflicts"]),
            "model_inference_count": int(g4d_rows["g4d_enhanced_mlp_risk_head"]["model_inference_count"]),
            "fallback_astar_calls": int(g4d_rows["g4d_enhanced_mlp_risk_head"]["verified_cie_fallback_calls"]),
            "original_cie_retry_astar_calls": original,
            "interface_level_astar_saved_rate": 1.0 - int(g4d_rows["g4d_enhanced_mlp_risk_head"]["verified_cie_fallback_calls"]) / max(1, interface_decisions),
            "task_zero_fallback_count": 0,
            "task_zero_fallback_share": 0.0,
            "astar_call_reduction_rate": 1.0 - int(g4d_rows["g4d_enhanced_mlp_risk_head"]["verified_cie_fallback_calls"]) / max(1, original),
            "call_count_interpretation": "G4D aggregate A* reduction but zero task-level full replacement",
        },
        _row_from_g4e("g4e_route_exact_risk_reduced", "development_main_route_exact", g4e_rows["route_exact_with_g4e_fallback"], interface_decisions, original, interface_decisions),
        _row_from_g4e("g4e_goal_reaching_model_only", "diagnostic_true_decentralized_no_fallback", g4e_rows["goal_reaching_model_only"], inference_counts.get("goal_reaching_model_only", 0), original, interface_decisions),
        _row_from_g4e("g4e_goal_reaching_with_fallback", "engineering_goal_reaching_policy", g4e_rows["goal_reaching_with_g4e_fallback"], inference_counts.get("goal_reaching_with_g4e_fallback", 0), original, interface_decisions),
    ]
    return rows


def _row_from_g4e(policy: str, role: str, row: dict[str, str], inference_count: int, original: int, interface_decisions: int) -> dict[str, Any]:
    fallback = int(row["fallback_calls"])
    zero = int(row["zero_fallback_task_count"])
    total = int(row["teacher_planned_scope"])
    return {
        "policy": policy,
        "role": role,
        "planned_count": int(row["planned_count"]),
        "teacher_planned_scope": total,
        "node_window_conflicts": int(row["node_window_conflicts"]),
        "model_inference_count": inference_count,
        "fallback_astar_calls": fallback,
        "original_cie_retry_astar_calls": original,
        "interface_level_astar_saved_rate": 1.0 - fallback / max(1, interface_decisions),
        "task_zero_fallback_count": zero,
        "task_zero_fallback_share": zero / max(1, total),
        "astar_call_reduction_rate": 1.0 - fallback / max(1, original),
        "call_count_interpretation": _interpret(policy, fallback, original, zero, total),
    }


def _interpret(policy: str, fallback: int, original: int, zero: int, total: int) -> str:
    if "model_only" in policy:
        return "diagnostic: no A* after admission, but requires runtime validation before deployment"
    if fallback < original and zero > 0:
        return "reduces A* calls and improves task-level zero-fallback share"
    if fallback < original:
        return "reduces aggregate A* calls but task-level replacement remains weak"
    return "does not reduce A* calls"


def _next_gate_rows(accounting: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy = {row["policy"]: row for row in accounting}
    main = by_policy["g4e_route_exact_risk_reduced"]
    goal = by_policy["g4e_goal_reaching_with_fallback"]
    model_only = by_policy["g4e_goal_reaching_model_only"]
    g4d = by_policy["g4d_route_exact_risk_head"]
    rows = [
        ("planned_count_ge_g4d", int(main["planned_count"]) >= int(g4d["planned_count"]), f"{main['planned_count']}>={g4d['planned_count']}", "development_pass"),
        ("node_window_conflicts_zero", int(main["node_window_conflicts"]) == 0 and int(goal["node_window_conflicts"]) == 0, "0", "development_pass"),
        ("fallback_calls_le_g4d", int(main["fallback_astar_calls"]) <= int(g4d["fallback_astar_calls"]), f"{main['fallback_astar_calls']}<={g4d['fallback_astar_calls']}", "development_pass"),
        ("has_zero_fallback_tasks", int(main["task_zero_fallback_count"]) > int(g4d["task_zero_fallback_count"]), f"{main['task_zero_fallback_count']}>{g4d['task_zero_fallback_count']}", "development_pass"),
        ("goal_reaching_safe_ge_route_exact", int(model_only["planned_count"]) >= int(main["planned_count"]), f"{model_only['planned_count']}>={main['planned_count']}", "development_pass"),
        ("promotion_astar_reduction_ge_70pct", float(main["astar_call_reduction_rate"]) >= 0.70, main["astar_call_reduction_rate"], "block_promotion"),
        ("promotion_fallback_rate_le_12pct", (1.0 - float(main["interface_level_astar_saved_rate"])) <= 0.12, 1.0 - float(main["interface_level_astar_saved_rate"]), "block_promotion"),
        ("recommend_g4f_runtime", False, "G4E development pass only", "block_promotion"),
    ]
    return [
        {
            "gate": gate,
            "pass": passed,
            "value": value,
            "decision": decision if passed else "block_promotion" if "promotion" in gate or gate == "recommend_g4f_runtime" else "block_development",
        }
        for gate, passed, value, decision in rows
    ]


def _write_accounting_report(rows: list[dict[str, Any]]) -> None:
    ACCOUNTING_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4E Runtime Call Accounting Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This report separates interface-level savings, task-level zero-fallback share, and original CIE retry A* attempt reduction. Timing is a call-count proxy, not a real runtime speedup claim.",
        "",
        "## A* Accounting",
        "",
        _markdown_table(
            ["Policy", "Planned", "Fallback A*", "A* Reduction", "0-fallback tasks", "Interpretation"],
            [
                [
                    row["policy"],
                    f"{row['planned_count']}/{row['teacher_planned_scope']}",
                    row["fallback_astar_calls"],
                    row["astar_call_reduction_rate"],
                    f"{row['task_zero_fallback_count']}/{row['teacher_planned_scope']}",
                    row["call_count_interpretation"],
                ]
                for row in rows
            ],
        ),
        "",
        "## Decision",
        "",
        "G4E reduces route-exact fallback calls relative to G4D and introduces a nonzero zero-fallback task share. It does not reach the 70% A* reduction / 12% fallback-rate promotion target, so it remains a development pass rather than a G4F promotion candidate.",
        "",
        "## Artifact",
        "",
        f"- A* accounting: `{_relative(ASTAR_TABLE)}`",
    ]
    ACCOUNTING_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_gate_report(rows: list[dict[str, Any]]) -> None:
    passed_dev = all(row["pass"] == "True" or row["pass"] is True for row in rows if row["decision"] == "development_pass")
    promotion = all(row["pass"] == "True" or row["pass"] is True for row in rows)
    NEXT_GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4E Next Gate Decision Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Gate Summary",
        "",
        _markdown_table(["Gate", "Pass", "Value", "Decision"], [[row["gate"], row["pass"], row["value"], row["decision"]] for row in rows]),
        "",
        "## Decision",
        "",
        (
            "G4E is a promotion candidate for G4F."
            if promotion
            else "G4E is a development pass, not a G4F promotion candidate. Continue fallback-reduction and runtime validation before C++ promotion."
        ),
        "",
        f"- Development pass: `{passed_dev}`",
        f"- Promotion candidate: `{promotion}`",
        "",
        "## Artifact",
        "",
        f"- Next gate table: `{_relative(NEXT_GATE_TABLE)}`",
    ]
    NEXT_GATE_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    accounting = _accounting_rows()
    gates = _next_gate_rows(accounting)
    _write_csv(
        ASTAR_TABLE,
        accounting,
        [
            "policy",
            "role",
            "planned_count",
            "teacher_planned_scope",
            "node_window_conflicts",
            "model_inference_count",
            "fallback_astar_calls",
            "original_cie_retry_astar_calls",
            "interface_level_astar_saved_rate",
            "task_zero_fallback_count",
            "task_zero_fallback_share",
            "astar_call_reduction_rate",
            "call_count_interpretation",
        ],
    )
    _write_csv(NEXT_GATE_TABLE, gates, ["gate", "pass", "value", "decision"])
    _write_accounting_report(accounting)
    _write_gate_report(gates)

    main_row = next(row for row in accounting if row["policy"] == "g4e_route_exact_risk_reduced")
    g4d_row = next(row for row in accounting if row["policy"] == "g4d_route_exact_risk_head")
    if int(main_row["fallback_astar_calls"]) > int(g4d_row["fallback_astar_calls"]):
        raise AssertionError("G4E fallback calls must not exceed G4D")
    if int(main_row["planned_count"]) < int(g4d_row["planned_count"]):
        raise AssertionError("G4E planned count must not drop below G4D")
    missing = [path for path in (ASTAR_TABLE, NEXT_GATE_TABLE, ACCOUNTING_REPORT, NEXT_GATE_REPORT) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4E runtime accounting artifacts: {missing}")
    print(
        "g4e runtime accounting complete: "
        f"fallback={main_row['fallback_astar_calls']} "
        f"astar_reduction={float(main_row['astar_call_reduction_rate']):.6f} "
        f"zero_fallback_tasks={main_row['task_zero_fallback_count']}"
    )


if __name__ == "__main__":
    main()
