from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_unified_baseline_comparison.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_unified_baseline_comparison_report.md"

SOURCE_TABLES = {
    "phase2_baseline_smoke": ROOT / "outputs" / "tables" / "phase2_baseline_smoke_metrics.csv",
    "phase5_robustness_sweep": ROOT / "outputs" / "tables" / "phase5_robustness_sweep_metrics.csv",
    "phase8_legacy_event_parity": ROOT / "outputs" / "tables" / "phase8_legacy_event_parity.csv",
    "phase9_matched_baseline_comparison": ROOT / "outputs" / "tables" / "phase9_matched_baseline_comparison.csv",
    "phase9_synthetic_matched_baseline_comparison": (
        ROOT / "outputs" / "tables" / "phase9_synthetic_matched_baseline_comparison.csv"
    ),
    "phase9_dense_pibt_stress_sweep": ROOT / "outputs" / "tables" / "phase9_dense_pibt_stress_sweep.csv",
    "phase9_event_runtime_scaling": ROOT / "outputs" / "tables" / "phase9_event_runtime_scaling.csv",
    "phase9_matched_runtime_scaling": ROOT / "outputs" / "tables" / "phase9_matched_runtime_scaling.csv",
}

PARITY_TABLES = {
    "sipp_planner": ROOT / "outputs" / "tables" / "phase2_cpp_sipp_parity.csv",
    "rolling_horizon_sipp": ROOT / "outputs" / "tables" / "phase2_cpp_rolling_horizon_parity.csv",
    "periodic_replanning_sipp": ROOT / "outputs" / "tables" / "phase2_periodic_replanning_parity.csv",
    "pibt_active_bag_replay": ROOT / "outputs" / "tables" / "phase2_pibt_active_bag_replay_parity.csv",
    "phase8_synthetic_event_scheduler": ROOT / "outputs" / "tables" / "phase8_native_cpp_event_parity.csv",
    "phase8_randomized_synthetic": ROOT / "outputs" / "tables" / "phase8_native_cpp_randomized_parity.csv",
    "phase8_legacy_event_scheduler": ROOT / "outputs" / "tables" / "phase8_legacy_event_parity.csv",
    "phase9_matched_baseline_comparison": ROOT / "outputs" / "tables" / "phase9_matched_baseline_comparison.csv",
    "phase9_runtime_scaling": ROOT / "outputs" / "tables" / "phase9_event_runtime_scaling.csv",
    "phase9_matched_runtime_scaling": ROOT / "outputs" / "tables" / "phase9_matched_runtime_scaling.csv",
    "phase9_dense_pibt_stress_sweep": ROOT / "outputs" / "tables" / "phase9_dense_pibt_stress_sweep.csv",
}

FIELDNAMES = [
    "evidence_group",
    "source_table",
    "source_scope",
    "case",
    "policy_or_baseline",
    "engine",
    "max_tasks",
    "fault_edges",
    "fault_windows",
    "node_capacities",
    "merge_groups",
    "merge_capacity",
    "merge_headway_seconds",
    "planned_count",
    "unplanned_count",
    "post_shield_conflicts",
    "mean_travel_time",
    "p95_travel_time",
    "decision_count",
    "elapsed_seconds",
    "elapsed_ci95_seconds",
    "repeat_count",
    "hardware",
    "decisions_per_second",
    "cpp_decision_speedup",
    "python_planned",
    "cpp_planned",
    "python_decisions",
    "cpp_decisions",
    "python_conflicts",
    "cpp_conflicts",
    "summary_parity_pass",
    "trace_parity_pass",
    "strict_parity_pass",
    "parity_rows",
    "pass_rows",
    "safety_pass",
    "notes",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _int_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(int(float(str(value))))


def _float_text(value: Any, places: int = 6) -> str:
    if value in (None, ""):
        return ""
    return f"{float(str(value)):.{places}f}"


def _blank_row(**values: Any) -> dict[str, str]:
    row = {field: "" for field in FIELDNAMES}
    for key, value in values.items():
        row[key] = str(value)
    return row


def _source_name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _outcome_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    phase2_path = SOURCE_TABLES["phase2_baseline_smoke"]
    for source in _read_csv(phase2_path):
        rows.append(
            _blank_row(
                evidence_group="baseline_or_policy_outcome",
                source_table=_source_name(phase2_path),
                source_scope="same-map Python baseline smoke on map2/inputdata",
                case="phase2_baseline_smoke",
                policy_or_baseline=source["baseline"],
                engine="python",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges="none",
                fault_windows="none",
                node_capacities="none",
                merge_groups="none",
                merge_capacity="1",
                merge_headway_seconds="0.0",
                planned_count=_int_text(source["planned_count"]),
                unplanned_count=_int_text(source["unplanned_count"]),
                post_shield_conflicts=_int_text(source["post_shield_conflicts"]),
                mean_travel_time=_float_text(source["mean_travel_time"]),
                p95_travel_time=_float_text(source["p95_travel_time"]),
                elapsed_seconds=_float_text(source["elapsed_seconds"]),
                safety_pass=str(int(float(source["post_shield_conflicts"])) == 0),
                notes="Phase2 broad smoke; not a matched Phase9 policy bakeoff.",
            )
        )

    phase5_path = SOURCE_TABLES["phase5_robustness_sweep"]
    for source in _read_csv(phase5_path):
        rows.append(
            _blank_row(
                evidence_group="baseline_or_policy_outcome",
                source_table=_source_name(phase5_path),
                source_scope="same-map learned-policy robustness sweep on map2 task windows",
                case=source["case"],
                policy_or_baseline=source["policy"],
                engine="python",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows="none",
                node_capacities="none",
                merge_groups="none",
                merge_capacity="1",
                merge_headway_seconds="0.0",
                planned_count=_int_text(source["planned_count"]),
                unplanned_count=_int_text(source["unplanned_count"]),
                post_shield_conflicts=_int_text(source["post_shield_conflicts"]),
                mean_travel_time=_float_text(source["mean_travel_time"]),
                p95_travel_time=_float_text(source["p95_travel_time"]),
                elapsed_seconds=_float_text(source["elapsed_seconds"]),
                safety_pass=str(int(float(source["post_shield_conflicts"])) == 0),
                notes="Compares A*-guided, DAgger BC, and rolling-horizon SIPP in the existing Phase5 sweep.",
            )
        )
    return rows


def _legacy_event_parity_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase8_legacy_event_parity"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        rows.append(
            _blank_row(
                evidence_group="native_event_parity",
                source_table=_source_name(path),
                source_scope="real legacy map2/inputdata event-scheduler parity",
                case=source["case"],
                policy_or_baseline=source["policy"],
                engine="python_cpp_event",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                decision_count=_int_text(source["cpp_decisions"]),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_decisions"]),
                cpp_decisions=_int_text(source["cpp_decisions"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["summary_match"],
                trace_parity_pass=source["trace_match"],
                strict_parity_pass=source["strict_parity_pass"],
                safety_pass=str(int(float(source["python_conflicts"])) == 0 and int(float(source["cpp_conflicts"])) == 0),
                notes="Trace-level Python/C++ event replay parity on real legacy task windows.",
            )
        )
    return rows


def _matched_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase9_matched_baseline_comparison"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        rows.append(
            _blank_row(
                evidence_group="matched_baseline_comparison",
                source_table=_source_name(path),
                source_scope="common real legacy map2/inputdata scenario rows across included baseline families",
                case=source["scenario"],
                policy_or_baseline=source["family"],
                engine="python_cpp",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                mean_travel_time=_float_text(source["cpp_mean_travel_time"]),
                decision_count=_int_text(source["cpp_decisions"]),
                elapsed_seconds=_float_text(source["cpp_elapsed_seconds"]),
                cpp_decision_speedup=_float_text(source["cpp_speedup"], places=6),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_decisions"]),
                cpp_decisions=_int_text(source["cpp_decisions"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["parity_pass"],
                strict_parity_pass=source["parity_pass"],
                safety_pass=str(int(float(source["python_conflicts"])) == 0 and int(float(source["cpp_conflicts"])) == 0),
                notes="Matched Phase9 scenario row generated by rerunning Python and C++ implementations.",
            )
        )
    return rows


def _synthetic_matched_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase9_synthetic_matched_baseline_comparison"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        python_conflicts = int(float(source["python_conflicts"]))
        cpp_conflicts = int(float(source["cpp_conflicts"]))
        rows.append(
            _blank_row(
                evidence_group="synthetic_matched_baseline_comparison",
                source_table=_source_name(path),
                source_scope="fixed-seed synthetic ICS-like Phase8 manifest rows; heldout-like but not a real airport map",
                case=source["scenario"],
                policy_or_baseline=source["family"],
                engine="python_cpp",
                max_tasks=_int_text(source["task_count"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                mean_travel_time=_float_text(source["cpp_mean_travel_time"]),
                decision_count=_int_text(source["cpp_active_steps"]),
                elapsed_seconds=_float_text(source["cpp_elapsed_seconds"]),
                cpp_decision_speedup=_float_text(source["cpp_speedup"], places=6),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_active_steps"]),
                cpp_decisions=_int_text(source["cpp_active_steps"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["parity_pass"],
                strict_parity_pass=source["parity_pass"],
                safety_pass=str(python_conflicts == 0 and cpp_conflicts == 0),
                notes=source.get("notes", "Synthetic matched Phase9 scenario row."),
            )
        )
    return rows


def _dense_pibt_stress_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase9_dense_pibt_stress_sweep"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        python_conflicts = int(float(source["python_conflicts"]))
        cpp_conflicts = int(float(source["cpp_conflicts"]))
        rows.append(
            _blank_row(
                evidence_group="dense_pibt_stress_sweep",
                source_table=_source_name(path),
                source_scope="fixed random dense synthetic active-bag PIBT stress seeds",
                case=source["scenario"],
                policy_or_baseline="pibt_active_bag_replay",
                engine="python_cpp",
                max_tasks=_int_text(source["task_count"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                mean_travel_time=_float_text(source["cpp_mean_travel_time"]),
                decision_count=_int_text(source["cpp_decisions"]),
                elapsed_seconds=_float_text(source["cpp_elapsed_seconds"]),
                cpp_decision_speedup=_float_text(source["cpp_speedup"], places=6),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_decisions"]),
                cpp_decisions=_int_text(source["cpp_decisions"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["parity_pass"],
                strict_parity_pass=source["parity_pass"],
                safety_pass=str(python_conflicts == 0 and cpp_conflicts == 0),
                notes="Additional dense PIBT active-bag stress row; synthetic, not a separate real heldout map.",
            )
        )
    return rows


def _runtime_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase9_event_runtime_scaling"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        rows.append(
            _blank_row(
                evidence_group="native_event_runtime",
                source_table=_source_name(path),
                source_scope="repeated local timing on real legacy map2/inputdata windows",
                case=source["case"],
                policy_or_baseline=source["policy"],
                engine="python_cpp_event",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                decision_count=_int_text(source["cpp_decisions"]),
                elapsed_seconds=_float_text(source["cpp_elapsed_mean_seconds"]),
                decisions_per_second=_float_text(source["cpp_decisions_per_second"], places=2),
                cpp_decision_speedup=_float_text(source["cpp_decision_speedup"], places=6),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_decisions"]),
                cpp_decisions=_int_text(source["cpp_decisions"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["summary_parity_pass"],
                strict_parity_pass=source["summary_parity_pass"],
                safety_pass=str(int(float(source["python_conflicts"])) == 0 and int(float(source["cpp_conflicts"])) == 0),
                notes=f"Repeated {source['repeat_count']}x timing row with local environment metadata.",
            )
        )
    return rows


def _matched_runtime_rows() -> list[dict[str, str]]:
    path = SOURCE_TABLES["phase9_matched_runtime_scaling"]
    rows: list[dict[str, str]] = []
    for source in _read_csv(path):
        hardware = (
            f"{source.get('platform', '')}; machine={source.get('machine', '')}; "
            f"cpu_count={source.get('cpu_count', '')}; processor={source.get('processor', '')}"
        )
        rows.append(
            _blank_row(
                evidence_group="matched_baseline_runtime",
                source_table=_source_name(path),
                source_scope="repeated local timing for every Phase9 matched baseline family row",
                case=source["scenario"],
                policy_or_baseline=source["family"],
                engine="python_cpp",
                max_tasks=_int_text(source["max_tasks"]),
                fault_edges=source.get("fault_edges", "none"),
                fault_windows=source.get("fault_windows", "none"),
                node_capacities=source.get("node_capacities", "none"),
                merge_groups=source.get("merge_groups", "none"),
                merge_capacity=source.get("merge_capacity", "1"),
                merge_headway_seconds=source.get("merge_headway_seconds", "0.0"),
                planned_count=_int_text(source["cpp_planned"]),
                unplanned_count=_int_text(source["cpp_unplanned"]),
                post_shield_conflicts=_int_text(source["cpp_conflicts"]),
                mean_travel_time=_float_text(source["cpp_mean_travel_time"]),
                decision_count=_int_text(source["cpp_active_steps"]),
                elapsed_seconds=_float_text(source["cpp_elapsed_mean_seconds"]),
                elapsed_ci95_seconds=_float_text(source["cpp_elapsed_ci95_seconds"]),
                repeat_count=_int_text(source["repeat_count"]),
                hardware=hardware,
                decisions_per_second=_float_text(source["cpp_active_steps_per_second"], places=2),
                cpp_decision_speedup=_float_text(source["cpp_elapsed_speedup"], places=6),
                python_planned=_int_text(source["python_planned"]),
                cpp_planned=_int_text(source["cpp_planned"]),
                python_decisions=_int_text(source["python_active_steps"]),
                cpp_decisions=_int_text(source["cpp_active_steps"]),
                python_conflicts=_int_text(source["python_conflicts"]),
                cpp_conflicts=_int_text(source["cpp_conflicts"]),
                summary_parity_pass=source["parity_pass"],
                strict_parity_pass=source["parity_pass"],
                safety_pass=str(int(float(source["python_conflicts"])) == 0 and int(float(source["cpp_conflicts"])) == 0),
                notes=f"Repeated {source['repeat_count']}x matched timing row with local hardware metadata and 95% CI.",
            )
        )
    return rows


def _pass_column(rows: list[dict[str, str]]) -> str:
    candidates = ("strict_parity_pass", "parity_pass", "summary_parity_pass")
    for candidate in candidates:
        if rows and candidate in rows[0]:
            return candidate
    raise KeyError("no parity pass column found")


def _conflict_pass(rows: list[dict[str, str]]) -> bool:
    conflict_columns = [
        ("python_conflicts", "cpp_conflicts"),
        ("post_shield_conflicts",),
    ]
    for columns in conflict_columns:
        if rows and all(column in rows[0] for column in columns):
            return all(all(int(float(row[column])) == 0 for column in columns) for row in rows)
    return True


def _parity_summary_rows() -> list[dict[str, str]]:
    summary_rows: list[dict[str, str]] = []
    for family, path in PARITY_TABLES.items():
        source_rows = _read_csv(path)
        pass_column = _pass_column(source_rows)
        pass_count = sum(1 for row in source_rows if _bool(row[pass_column]))
        safety_pass = _conflict_pass(source_rows)
        summary_rows.append(
            _blank_row(
                evidence_group="baseline_family_parity_summary",
                source_table=_source_name(path),
                source_scope="aggregated Python/C++ parity gate",
                case="ALL",
                policy_or_baseline=family,
                engine="python_cpp",
                strict_parity_pass=str(pass_count == len(source_rows)),
                parity_rows=str(len(source_rows)),
                pass_rows=str(pass_count),
                safety_pass=str(safety_pass),
                notes=f"Uses `{pass_column}` across all rows in the source table.",
            )
        )
    return summary_rows


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    rows.extend(_outcome_rows())
    rows.extend(_matched_rows())
    rows.extend(_synthetic_matched_rows())
    rows.extend(_dense_pibt_stress_rows())
    rows.extend(_legacy_event_parity_rows())
    rows.extend(_runtime_rows())
    rows.extend(_matched_runtime_rows())
    rows.extend(_parity_summary_rows())
    return rows


def write_table(rows: list[dict[str, str]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    outcome_rows = [row for row in rows if row["evidence_group"] == "baseline_or_policy_outcome"]
    matched_rows = [row for row in rows if row["evidence_group"] == "matched_baseline_comparison"]
    synthetic_rows = [
        row for row in rows if row["evidence_group"] == "synthetic_matched_baseline_comparison"
    ]
    dense_pibt_rows = [row for row in rows if row["evidence_group"] == "dense_pibt_stress_sweep"]
    matched_runtime_rows = [row for row in rows if row["evidence_group"] == "matched_baseline_runtime"]
    event_rows = [row for row in rows if row["evidence_group"] in {"native_event_parity", "native_event_runtime"}]
    parity_rows = [row for row in rows if row["evidence_group"] == "baseline_family_parity_summary"]
    safety_gate_pass = all(row["safety_pass"] == "True" for row in rows if row["safety_pass"])
    all_reported_safety_pass = all(row["safety_pass"] == "True" for row in rows if row["safety_pass"])
    event_parity_pass = all(row["strict_parity_pass"] == "True" for row in event_rows if row["strict_parity_pass"])
    family_parity_pass = all(row["strict_parity_pass"] == "True" for row in parity_rows)
    policies = sorted(
        {
            row["policy_or_baseline"]
            for row in [*outcome_rows, *event_rows]
            + matched_rows
            + synthetic_rows
            + dense_pibt_rows
            if row["policy_or_baseline"]
        }
    )
    families = sorted({row["policy_or_baseline"] for row in parity_rows if row["policy_or_baseline"]})
    speedups = [
        float(row["cpp_decision_speedup"])
        for row in rows
        if row["evidence_group"] in {"native_event_runtime", "matched_baseline_runtime"} and row["cpp_decision_speedup"]
    ]
    return {
        "outcome_row_count": len(outcome_rows),
        "matched_row_count": len(matched_rows),
        "synthetic_row_count": len(synthetic_rows),
        "dense_pibt_stress_row_count": len(dense_pibt_rows),
        "dense_pibt_stress_safety_pass": all(row["safety_pass"] == "True" for row in dense_pibt_rows),
        "dense_pibt_stress_parity_pass": all(row["strict_parity_pass"] == "True" for row in dense_pibt_rows),
        "matched_runtime_row_count": len(matched_runtime_rows),
        "event_row_count": len(event_rows),
        "family_row_count": len(parity_rows),
        "safety_gate_pass": safety_gate_pass,
        "all_reported_safety_pass": all_reported_safety_pass,
        "event_parity_pass": event_parity_pass,
        "family_parity_pass": family_parity_pass,
        "policies": policies,
        "families": families,
        "median_speedup": _median(speedups),
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _fault_label(row: dict[str, str]) -> str:
    if row["fault_edges"] != "none":
        return row["fault_edges"]
    return row["fault_windows"]


def _config_label(row: dict[str, str]) -> str:
    parts = []
    if row["node_capacities"] and row["node_capacities"] != "none":
        parts.append(f"nodes={row['node_capacities']}")
    if row["merge_groups"] and row["merge_groups"] != "none":
        parts.append(
            f"merge={row['merge_groups']},cap={row['merge_capacity']},headway={row['merge_headway_seconds']}"
        )
    return "; ".join(parts) if parts else "none"


def write_report(rows: list[dict[str, str]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = _summarize(rows)
    outcome_rows = [row for row in rows if row["evidence_group"] == "baseline_or_policy_outcome"]
    matched_rows = [row for row in rows if row["evidence_group"] == "matched_baseline_comparison"]
    synthetic_rows = [
        row for row in rows if row["evidence_group"] == "synthetic_matched_baseline_comparison"
    ]
    dense_pibt_rows = [row for row in rows if row["evidence_group"] == "dense_pibt_stress_sweep"]
    legacy_event_rows = [row for row in rows if row["evidence_group"] == "native_event_parity"]
    runtime_rows = [row for row in rows if row["evidence_group"] == "native_event_runtime"]
    matched_runtime_rows = [row for row in rows if row["evidence_group"] == "matched_baseline_runtime"]
    parity_rows = [row for row in rows if row["evidence_group"] == "baseline_family_parity_summary"]
    lines = [
        "# Phase9 Unified Baseline Comparison Diagnostic",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic builds a single Phase9 evidence table from the existing generated CSV outputs. "
            "It combines same-map policy/baseline outcome rows, real legacy event-scheduler Python/C++ parity, "
            "heldout-like synthetic matched rows, dense active-bag PIBT stress rows, repeated native event runtime rows, "
            "repeated matched-baseline runtime rows, and aggregate parity coverage for the Phase2/Phase8 baseline families."
        ),
        "",
        (
            "The table is intentionally an evidence index, not a final paper benchmark. Rows come from different "
            "scopes, and the first matched Phase9 rows are still limited to small no-fault/buffer-capacity/static-fault/repair-window/merge-group windows, "
            "so cross-policy ranking should wait for expanded matched maps, task windows, fault schedules, and "
            "multi-machine hardware-normalized timing."
        ),
        "",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Outcome Evidence",
        "",
        "| Case | Policy/Baseline | Tasks | Faults | Planned | Unplanned | Conflicts | Mean travel | Seconds |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in outcome_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {fault_edges} | {planned_count} | "
            "{unplanned_count} | {post_shield_conflicts} | {mean_travel_time} | {elapsed_seconds} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Matched Baseline Evidence",
            "",
            "| Scenario | Family | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity |",
            "|---|---|---:|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in matched_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {fault_label} | {config_label} | {planned_count} | "
            "{decision_count} | {post_shield_conflicts} | {cpp_decision_speedup} | {strict_parity_pass} |".format(
                **{**row, "fault_label": _fault_label(row), "config_label": _config_label(row)}
            )
        )

    lines.extend(
        [
            "",
            "## Synthetic Matched Evidence",
            "",
            "| Scenario | Family | Tasks | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity | Notes |",
            "|---|---|---:|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in synthetic_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {config_label} | {planned_count} | "
            "{decision_count} | {post_shield_conflicts} | {cpp_decision_speedup} | "
            "{strict_parity_pass} | {notes} |".format(
                **{**row, "config_label": _config_label(row)}
            )
        )

    lines.extend(
        [
            "",
            "## Dense PIBT Stress Evidence",
            "",
            "| Scenario | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity |",
            "|---|---:|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in dense_pibt_rows:
        lines.append(
            "| {case} | {max_tasks} | {fault_label} | {config_label} | {planned_count} | {decision_count} | "
            "{post_shield_conflicts} | {cpp_decision_speedup} | {strict_parity_pass} |".format(
                **{**row, "fault_label": _fault_label(row), "config_label": _config_label(row)}
            )
        )

    lines.extend(
        [
            "",
            "## Legacy Event Parity Evidence",
            "",
            "| Case | Policy | Tasks | Py planned | C++ planned | C++ decisions | Conflicts | Strict parity |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in legacy_event_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {python_planned} | {cpp_planned} | "
            "{cpp_decisions} | {cpp_conflicts} | {strict_parity_pass} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Runtime Evidence",
            "",
            "| Case | Policy | Tasks | C++ planned | C++ decisions | C++ seconds | C++ decisions/s | Speedup | Parity |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in runtime_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {planned_count} | {decision_count} | "
            "{elapsed_seconds} | {decisions_per_second} | {cpp_decision_speedup} | {strict_parity_pass} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Matched Runtime Evidence",
            "",
            (
                "| Scenario | Family | Tasks | Config | Repeats | C++ seconds mean+/-95% CI | "
                "C++ active steps/s | Speedup | Parity |"
            ),
            "|---|---|---:|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in matched_runtime_rows:
        lines.append(
            "| {case} | {policy_or_baseline} | {max_tasks} | {config_label} | {repeat_count} | "
            "{elapsed_seconds}+/-{elapsed_ci95_seconds} | {decisions_per_second} | "
            "{cpp_decision_speedup} | {strict_parity_pass} |".format(
                **{**row, "config_label": _config_label(row)}
            )
        )

    lines.extend(
        [
            "",
            "## Parity Coverage",
            "",
            "| Family | Source rows | Passing rows | Safety | Source |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in parity_rows:
        lines.append(
            "| {policy_or_baseline} | {parity_rows} | {pass_rows} | {safety_pass} | `{source_table}` |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- unified outcome rows: `{summary['outcome_row_count']}`",
            f"- matched baseline rows: `{summary['matched_row_count']}`",
            f"- synthetic matched baseline rows: `{summary['synthetic_row_count']}`",
            f"- dense PIBT stress rows: `{summary['dense_pibt_stress_row_count']}`",
            f"- matched baseline runtime rows: `{summary['matched_runtime_row_count']}`",
            f"- native event parity/runtime rows: `{summary['event_row_count']}`",
            f"- baseline-family parity summaries: `{summary['family_row_count']}`",
            f"- policies/baselines surfaced: `{', '.join(summary['policies'])}`",
            f"- parity families surfaced: `{', '.join(summary['families'])}`",
            "- gate-scoped post-shield conflicts are zero: PASS"
            if summary["safety_gate_pass"]
            else "- gate-scoped post-shield conflicts are zero: FAIL",
            "- all reported post-shield conflicts are zero: PASS"
            if summary["all_reported_safety_pass"]
            else "- all reported post-shield conflicts are zero: FAIL",
            "- dense PIBT stress Python/C++ parity rows pass: PASS"
            if summary["dense_pibt_stress_parity_pass"]
            else "- dense PIBT stress Python/C++ parity rows pass: FAIL",
            "- dense PIBT stress rows are safety-clean: PASS"
            if summary["dense_pibt_stress_safety_pass"]
            else "- dense PIBT stress rows are safety-clean: FAIL",
            "- native event Python/C++ parity rows pass: PASS"
            if summary["event_parity_pass"]
            else "- native event Python/C++ parity rows pass: FAIL",
            "- baseline-family parity summaries pass: PASS"
            if summary["family_parity_pass"]
            else "- baseline-family parity summaries pass: FAIL",
            f"- median C++ decision-throughput speedup in runtime rows: `{summary['median_speedup']:.3f}x`",
            "- matched paper-grade Phase9 comparison: not covered",
            "- matched merge-group scenario: covered",
            "- repeated matched-baseline runtime timing with 95% CI: covered",
            "- heldout-like synthetic matched comparison: covered",
            "- dense active-bag PIBT stress sweep: covered",
            "",
            "## Remaining Work",
            "",
            "- add a separate real heldout airport map when fixture data is available",
            "- expand randomized graph topologies and task-source distributions before paper-grade stress claims",
            "- expand timing to multi-machine hardware-normalized runs and confidence intervals before paper-grade speed claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_table(rows)
    write_report(rows)
    summary = _summarize(rows)
    if not summary["safety_gate_pass"]:
        raise AssertionError("Phase9 unified comparison found post-shield conflicts")
    if not summary["event_parity_pass"]:
        raise AssertionError("Phase9 unified comparison found event parity failures")
    if not summary["family_parity_pass"]:
        raise AssertionError("Phase9 unified comparison found baseline-family parity failures")
    print(
        "phase9_unified_baseline_comparison "
        f"rows={len(rows)} outcome_rows={summary['outcome_row_count']} "
        f"event_rows={summary['event_row_count']} parity_families={summary['family_row_count']}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
