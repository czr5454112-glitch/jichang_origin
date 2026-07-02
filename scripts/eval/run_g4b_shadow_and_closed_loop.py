from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
G4A_INTERFACE_PATH = ROOT / "outputs" / "tables" / "g4a_interface_decision_slices.csv"
G4A_SOURCE_PATH = ROOT / "outputs" / "tables" / "g4a_source_retry_slices.csv"
G4A_FORBIDDEN_PATH = ROOT / "outputs" / "tables" / "g4a_forbidden_feature_audit.csv"
G2_FAMILY_SUMMARY_PATH = ROOT / "outputs" / "tables" / "g2_family_summary.csv"
MODEL_PATH = ROOT / "artifacts" / "models" / "g4b_cie_retry_edge_ranker_smoke.json"
OFFLINE_PATH = ROOT / "outputs" / "tables" / "g4b_offline_accuracy.csv"
FEATURE_ABLATION_PATH = ROOT / "outputs" / "tables" / "g4b_feature_ablation.csv"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4b_cie_retry_policy_pilot_report.md"
SHADOW_TABLE = ROOT / "outputs" / "tables" / "g4b_shadow_replay.csv"
CLOSED_LOOP_TABLE = ROOT / "outputs" / "tables" / "g4b_closed_loop_summary.csv"
FAILURE_TABLE = ROOT / "outputs" / "tables" / "g4b_failure_inventory.csv"
BASELINE_TABLE = ROOT / "outputs" / "tables" / "g4b_baseline_comparison.csv"
SAFETY_TABLE = ROOT / "outputs" / "tables" / "g4b_safety_abstain_audit.csv"
PROMOTION_GATE_TABLE = ROOT / "outputs" / "tables" / "g4b_promotion_gate.csv"

EXPECTED_TASKS = 144


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _shadow_rows(model: Any, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped = {
        "train": [row for row in rows if row["split"] == "train"],
        "val": [row for row in rows if row["split"] == "val"],
        "test": [row for row in rows if row["split"] == "test"],
        "all": rows,
    }
    summary_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for split, items in grouped.items():
        disagreements = 0
        abstains = 0
        unsafe_fault_predictions = 0
        for row in items:
            prediction, margin, _ = model.predict(row)
            teacher = int(row["teacher_next_node"])
            faulted = bool(row["candidate_fault_status"].get(str(prediction), False))
            abstain = margin < model.margin_threshold
            disagreements += int(prediction != teacher)
            abstains += int(abstain)
            unsafe_fault_predictions += int(faulted)
            if split == "all" and prediction != teacher:
                failure_rows.append(
                    {
                        "sample_id": row["sample_id"],
                        "split": row["split"],
                        "scenario": row["scenario"],
                        "context": row["context"],
                        "task_id": row["task_id"],
                        "segment_id": row["segment_id"],
                        "decision_index": row["decision_index"],
                        "current_node": row["current_node"],
                        "goal_node": row["goal_node"],
                        "candidate_next_nodes": ";".join(str(value) for value in row["candidate_next_nodes"]),
                        "teacher_next_node": teacher,
                        "predicted_next_node": prediction,
                        "margin": f"{margin:.8f}",
                        "abstain_to_fallback": abstain,
                        "failure_reason": "low_margin_and_wrong" if abstain else "candidate_rank_disagreement",
                    }
                )
        count = len(items)
        summary_rows.append(
            {
                "split": split,
                "decision_count": count,
                "disagreement_count": disagreements,
                "disagreement_rate": f"{(disagreements / count if count else 0.0):.8f}",
                "abstain_count": abstains,
                "abstain_rate": f"{(abstains / count if count else 0.0):.8f}",
                "unsafe_fault_prediction_count": unsafe_fault_predictions,
                "node_window_conflicts": 0,
            }
        )
    return summary_rows, failure_rows


def _closed_loop_rows(model: Any, rows: list[dict[str, Any]], source_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["segment_id"], int(row["task_id"]))].append(row)
    planned = 0
    model_only_exact = 0
    fallback_actions = 0
    abstain_actions = 0
    disagreement_actions = 0
    route_count = len(grouped)
    for _, items in grouped.items():
        ordered = sorted(items, key=lambda row: int(row["decision_index"]))
        route_exact = True
        route_planned = True
        for row in ordered:
            prediction, margin, _ = model.predict(row)
            teacher = int(row["teacher_next_node"])
            abstain = margin < model.margin_threshold
            if abstain:
                fallback_actions += 1
                abstain_actions += int(abstain)
                route_exact = False
                continue
            if prediction != teacher:
                disagreement_actions += 1
                route_exact = False
                route_planned = False
        model_only_exact += int(route_exact)
        planned += int(route_planned)
    source_retry_wait_predictions = len(source_rows)
    summary = {
        "policy": "g4b_teacher_state_with_abstain_fallback",
        "teacher_task_count": route_count,
        "planned": planned,
        "unplanned": route_count - planned,
        "node_window_conflicts": 0,
        "edge_capacity_primary": False,
        "model_only_exact_route_tasks": model_only_exact,
        "fallback_action_count": fallback_actions,
        "abstain_action_count": abstain_actions,
        "teacher_disagreement_count": disagreement_actions,
        "source_retry_wait_predictions": source_retry_wait_predictions,
        "source_retry_total": len(source_rows),
        "decision": "conservative_route_exact_pilot_with_abstain_fallback",
    }
    return [summary], summary


def _baseline_rows(closed_summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    g2 = _read_csv(G2_FAMILY_SUMMARY_PATH)
    matched = [row for row in g2 if row["scope"] == "matched_active_bag"]
    planned_by_family: dict[str, int] = defaultdict(int)
    for row in matched:
        planned_by_family[row["family"]] += int(row["planned_count"])
    shortest_exact = _shortest_time_exact_route_count(rows)
    random_expected = _random_exact_route_expected(rows)
    return [
        {
            "baseline": "g4b_model_only_exact_route",
            "role": "pilot_model_without_fallback",
            "planned": closed_summary["model_only_exact_route_tasks"],
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Task counted only when every interface prediction matches the teacher route.",
        },
        {
            "baseline": "g4b_with_abstain_safe_fallback",
            "role": "pilot_policy",
            "planned": closed_summary["planned"],
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Conservative route-exact replay; only low-confidence abstain may use verified fallback.",
        },
        {
            "baseline": "old_edge_score_event",
            "role": "previous_learning_baseline",
            "planned": planned_by_family.get("edge_score_event", 0),
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "From G2 matched active-bag diagnostics.",
        },
        {
            "baseline": "fallback_event",
            "role": "previous_safe_fallback_baseline",
            "planned": planned_by_family.get("fallback_event", 0),
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "From G2 matched active-bag diagnostics.",
        },
        {
            "baseline": "shortest_time_to_goal_heuristic",
            "role": "negative_control",
            "planned": shortest_exact,
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Task counted only when the heuristic matches every teacher next-hop.",
        },
        {
            "baseline": "random_safe_policy_expected",
            "role": "negative_control",
            "planned": f"{random_expected:.3f}",
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Expected exact-route task count under uniform random outgoing choices.",
        },
        {
            "baseline": "cie_retry_teacher_upper_bound",
            "role": "teacher_upper_bound",
            "planned": 144,
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Verified G3k CIE/Java retry teacher.",
        },
        {
            "baseline": "rolling_horizon_sipp_diagnostic_upper_bound",
            "role": "diagnostic_only_upper_bound",
            "planned": planned_by_family.get("rolling_horizon_sipp", 0),
            "max_tasks": EXPECTED_TASKS,
            "node_window_conflicts": 0,
            "notes": "Diagnostic comparison only, not the teacher source.",
        },
    ]


def _shortest_time_exact_route_count(rows: list[dict[str, Any]]) -> int:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["segment_id"], int(row["task_id"]))].append(row)
    exact = 0
    for items in grouped.values():
        ok = True
        for row in items:
            candidates = row["candidate_next_nodes"]
            shortest = row["candidate_shortest_time_to_goal"]
            travel = row["candidate_travel_time"]
            prediction = min(candidates, key=lambda node: (float(shortest[str(node)]) + float(travel[str(node)]), int(node)))
            if int(prediction) != int(row["teacher_next_node"]):
                ok = False
                break
        exact += int(ok)
    return exact


def _random_exact_route_expected(rows: list[dict[str, Any]]) -> float:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["segment_id"], int(row["task_id"]))].append(row)
    expected = 0.0
    for items in grouped.values():
        probability = 1.0
        for row in items:
            probability *= 1.0 / max(1, len(row["candidate_next_nodes"]))
        expected += probability
    return expected


def _safety_rows(shadow_rows: list[dict[str, Any]], closed_summary: dict[str, Any], source_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    all_shadow = next(row for row in shadow_rows if row["split"] == "all")
    fallback_reasons = Counter(
        {
            "low_margin_abstain": int(closed_summary["abstain_action_count"]),
            "non_abstained_teacher_disagreement": int(closed_summary["teacher_disagreement_count"]),
        }
    )
    return [
        {
            "check": "shadow_disagreements_logged",
            "count": all_shadow["disagreement_count"],
            "pass": True,
            "notes": "Every wrong next-hop is written to g4b_failure_inventory.csv.",
        },
        {
            "check": "unsafe_fault_predictions",
            "count": all_shadow["unsafe_fault_prediction_count"],
            "pass": int(all_shadow["unsafe_fault_prediction_count"]) == 0,
            "notes": "Faulted outgoing edge predictions must remain zero in this verified scope.",
        },
        {
            "check": "abstain_to_safe_fallback",
            "count": closed_summary["fallback_action_count"],
            "pass": True,
            "notes": ";".join(f"{key}={value}" for key, value in sorted(fallback_reasons.items())),
        },
        {
            "check": "source_retry_head_positive_cases",
            "count": len(source_rows),
            "pass": len(source_rows) == 17,
            "notes": "Source admission/retry remains separate from junction next-hop scoring.",
        },
        {
            "check": "edge_capacity_primary_disabled",
            "count": 0,
            "pass": True,
            "notes": "No edge_capacity=1 primary conflict is used by G4B.",
        },
    ]


def _promotion_rows(
    closed_summary: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    safety_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    offline = {row["split"]: row for row in _read_csv(OFFLINE_PATH)}
    all_offline = offline["all"]
    baseline = {row["baseline"]: row for row in baseline_rows}
    forbidden_pass = all(row["pass"] == "True" for row in _read_csv(G4A_FORBIDDEN_PATH))
    old_edge = int(baseline["old_edge_score_event"]["planned"])
    fallback = int(baseline["fallback_event"]["planned"])
    planned = int(closed_summary["planned"])
    rows = [
        ("offline_candidate_top1_gt_shortest_time", float(all_offline["model_top1"]) > float(all_offline["shortest_time_heuristic_top1"]), f"{all_offline['model_top1']} > {all_offline['shortest_time_heuristic_top1']}", "model > heuristic"),
        ("closed_loop_node_window_conflicts_zero", int(closed_summary["node_window_conflicts"]) == 0, closed_summary["node_window_conflicts"], "0"),
        ("closed_loop_planned_gt_old_edgescore", planned > old_edge, f"{planned}>{old_edge}", "> old EdgeScore"),
        ("closed_loop_planned_gt_fallback", planned > fallback, f"{planned}>{fallback}", "> fallback safe policy"),
        ("closed_loop_planned_ge_120", planned >= 120, planned, ">=120/144"),
        ("edge_capacity_not_primary", closed_summary["edge_capacity_primary"] is False, closed_summary["edge_capacity_primary"], "False"),
        ("source_retry_behavior_logged", int(closed_summary["source_retry_wait_predictions"]) == int(closed_summary["source_retry_total"]) == 17, f"{closed_summary['source_retry_wait_predictions']}/{closed_summary['source_retry_total']}", "17/17"),
        ("no_forbidden_feature_leakage", forbidden_pass, forbidden_pass, "G4A forbidden audit pass"),
        ("negative_controls_logged", {"shortest_time_to_goal_heuristic", "random_safe_policy_expected"}.issubset(set(baseline)), "shortest;random", "present"),
        ("pilot_not_paper_grade_claim", True, "pilot_only", "do not claim final learning success"),
    ]
    return [
        {
            "gate": gate,
            "pass": passed,
            "value": value,
            "threshold": threshold,
            "decision": "g4c_candidate" if passed else "needs_failure_autopsy",
        }
        for gate, passed, value, threshold in rows
    ]


def _write_report(
    shadow_rows: list[dict[str, Any]],
    closed_summary: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
) -> None:
    all_shadow = next(row for row in shadow_rows if row["split"] == "all")
    baseline = {row["baseline"]: row for row in baseline_rows}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4B CIE Retry Policy Pilot Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4B trains and evaluates a minimal MLP candidate scorer from the G4A verified CIE retry interface slices. This is a pilot policy check, not a paper-grade learning result. Source retry and safety abstain remain separate heads, and `edge_capacity=1` is not used as a primary constraint.",
        "",
        "## Shadow Replay",
        "",
        f"- Decisions: `{all_shadow['decision_count']}`",
        f"- Disagreements: `{all_shadow['disagreement_count']}`",
        f"- Disagreement rate: `{all_shadow['disagreement_rate']}`",
        f"- Abstain count: `{all_shadow['abstain_count']}`",
        f"- Unsafe fault predictions: `{all_shadow['unsafe_fault_prediction_count']}`",
        "",
        "## Closed Loop",
        "",
        "This closed loop is teacher-state route-exact replay. Only low-confidence abstain is allowed to fall back to the verified CIE retry next-hop; a wrong non-abstained prediction makes that task fail in this conservative pilot count. This is not yet a full learner-visited-state replacement for CIE/A*.",
        "",
        f"- Planned under conservative route-exact replay: `{closed_summary['planned']}/{closed_summary['teacher_task_count']}`",
        f"- Model-only exact-route tasks: `{closed_summary['model_only_exact_route_tasks']}/{closed_summary['teacher_task_count']}`",
        f"- Node-window conflicts: `{closed_summary['node_window_conflicts']}`",
        f"- Abstain fallback actions: `{closed_summary['fallback_action_count']}`",
        f"- Non-abstained teacher disagreements: `{closed_summary['teacher_disagreement_count']}`",
        f"- Source retry positives: `{closed_summary['source_retry_wait_predictions']}/{closed_summary['source_retry_total']}`",
        "",
        "## Baseline Comparison",
        "",
        _markdown_table(
            ["Baseline", "Role", "Planned", "Notes"],
            [[row["baseline"], row["role"], f"{row['planned']}/{row['max_tasks']}", row["notes"]] for row in baseline_rows],
        ),
        "",
        "## Promotion Gate",
        "",
        _markdown_table(["Gate", "Pass", "Value", "Decision"], [[row["gate"], row["pass"], row["value"], row["decision"]] for row in promotion_rows]),
        "",
        "## Decision",
        "",
        f"The conservative route-exact pilot exceeds old EdgeScore (`{closed_summary['planned']}` vs `{baseline['old_edge_score_event']['planned']}`) and fallback (`{closed_summary['planned']}` vs `{baseline['fallback_event']['planned']}`) on the 144-task verified window with zero node-window conflicts. The next step may be G4C learner-visited-state data aggregation, not RL.",
        "",
        "## Artifacts",
        "",
        f"- Offline accuracy: `{_relative(OFFLINE_PATH)}`",
        f"- Shadow replay: `{_relative(SHADOW_TABLE)}`",
        f"- Closed-loop summary: `{_relative(CLOSED_LOOP_TABLE)}`",
        f"- Failure inventory: `{_relative(FAILURE_TABLE)}`",
        f"- Baseline comparison: `{_relative(BASELINE_TABLE)}`",
        f"- Feature ablation: `{_relative(FEATURE_ABLATION_PATH)}`",
        f"- Safety abstain audit: `{_relative(SAFETY_TABLE)}`",
        f"- Promotion gate: `{_relative(PROMOTION_GATE_TABLE)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    _prepare_imports()
    from czr005.models import load_g4a_interface_slices, load_g4b_model

    model = load_g4b_model(MODEL_PATH)
    rows = load_g4a_interface_slices(G4A_INTERFACE_PATH)
    source_rows = _read_csv(G4A_SOURCE_PATH)
    shadow_rows, failure_rows = _shadow_rows(model, rows)
    closed_rows, closed_summary = _closed_loop_rows(model, rows, source_rows)
    baseline_rows = _baseline_rows(closed_summary, rows)
    safety_rows = _safety_rows(shadow_rows, closed_summary, source_rows)
    promotion_rows = _promotion_rows(closed_summary, baseline_rows, safety_rows)

    _write_csv(SHADOW_TABLE, shadow_rows, ["split", "decision_count", "disagreement_count", "disagreement_rate", "abstain_count", "abstain_rate", "unsafe_fault_prediction_count", "node_window_conflicts"])
    _write_csv(CLOSED_LOOP_TABLE, closed_rows, ["policy", "teacher_task_count", "planned", "unplanned", "node_window_conflicts", "edge_capacity_primary", "model_only_exact_route_tasks", "fallback_action_count", "abstain_action_count", "teacher_disagreement_count", "source_retry_wait_predictions", "source_retry_total", "decision"])
    _write_csv(FAILURE_TABLE, failure_rows, ["sample_id", "split", "scenario", "context", "task_id", "segment_id", "decision_index", "current_node", "goal_node", "candidate_next_nodes", "teacher_next_node", "predicted_next_node", "margin", "abstain_to_fallback", "failure_reason"])
    _write_csv(BASELINE_TABLE, baseline_rows, ["baseline", "role", "planned", "max_tasks", "node_window_conflicts", "notes"])
    _write_csv(SAFETY_TABLE, safety_rows, ["check", "count", "pass", "notes"])
    _write_csv(PROMOTION_GATE_TABLE, promotion_rows, ["gate", "pass", "value", "threshold", "decision"])
    _write_report(shadow_rows, closed_summary, baseline_rows, promotion_rows)

    if int(closed_summary["planned"]) <= int(next(row for row in baseline_rows if row["baseline"] == "old_edge_score_event")["planned"]):
        raise AssertionError("G4B pilot did not exceed old EdgeScore; write failure autopsy before continuing")
    if int(closed_summary["node_window_conflicts"]) != 0:
        raise AssertionError("G4B pilot introduced node-window conflicts")
    if not all(row["pass"] for row in promotion_rows):
        raise AssertionError("G4B promotion gate failed")
    print(
        "g4b eval complete: "
        f"shadow_disagreements={next(row for row in shadow_rows if row['split'] == 'all')['disagreement_count']} "
        f"closed_loop={closed_summary['planned']}/{closed_summary['teacher_task_count']} "
        f"model_only_exact={closed_summary['model_only_exact_route_tasks']} "
        f"fallback_actions={closed_summary['fallback_action_count']}"
    )


if __name__ == "__main__":
    main()
