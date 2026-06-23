from __future__ import annotations

import csv
from datetime import date
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_event_scheduler.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_event_scheduler_report.md"
MAX_DECISIONS_PER_TASK = 128


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    safety_pass = all(bool(row["safety_pass"]) for row in rows)
    accounted_pass = all(bool(row["accounted_pass"]) for row in rows)
    edge_rows = [row for row in rows if row["policy"] == "edge_score_event"]
    fallback_rows = [row for row in rows if row["policy"] == "fallback_event"]
    lines = [
        "# Phase8 Native C++ Event Scheduler Smoke",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This smoke runs the first native C++ event-queue replay path. Tasks enter the event queue by `pass_time`; each bag schedules decision events at its local ready time after start-node service, hold, edge traversal, or node service. The scheduler reuses the C++ EdgeScore runtime model, `JunctionShield`, node/edge reservations, and repair-window fault handling.",
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        "This is a high-throughput scheduler integration smoke, not a final Python parity claim. The compact replay routes one task to completion before the next task, while this event scheduler interleaves active bags chronologically, so aggregate planned counts can differ on dense cases.",
        "",
        "## Metrics",
        "",
        "| Case | Policy | Tasks | Planned | Unplanned | Decisions | Conflicts | Mean travel | Decisions/s | Compact planned | Compact decisions | Accounted | Safety |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {task_count} | {planned_count} | {unplanned_count} | "
            "{decision_count} | {post_shield_conflicts} | {mean_travel_time:.12f} | "
            "{decisions_per_second:.2f} | {compact_planned_count} | {compact_decision_count} | "
            "{accounted_pass} | {safety_pass} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- event scheduler accounted all configured tasks: PASS" if accounted_pass else "- event scheduler accounted all configured tasks: FAIL",
            "- event scheduler post-shield safety: PASS" if safety_pass else "- event scheduler post-shield safety: FAIL",
            f"- EdgeScore event rows: `{len(edge_rows)}`",
            f"- fallback event rows: `{len(fallback_rows)}`",
            "- compact-vs-event strict metric parity: not expected",
            "- Python/C++ event trace parity: covered by `phase8_native_cpp_event_parity_report.md`",
            "- final paper-grade scheduler throughput: not covered",
            "",
            "## Remaining Work",
            "",
            "- add larger manifest sweeps and runtime scaling measurements",
            "- carry this scheduler path into Phase9 baseline and policy comparisons",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        MANIFEST_PATH,
        cpp_replay_kwargs,
        load_manifest_cases,
    )

    cases = load_manifest_cases(MANIFEST_PATH)
    rows: list[dict[str, float | int | str | bool]] = []
    for case in cases:
        node_records = list(case.node_records)
        edge_records = list(case.edge_records)
        heuristic_time = [list(row) for row in case.heuristic_time]
        task_records = list(case.task_records)
        common = cpp_replay_kwargs(case.spec, MAX_DECISIONS_PER_TASK)
        compact = czr005_cpp.edge_score_native_replay_summary_from_records(
            node_records,
            edge_records,
            heuristic_time,
            task_records,
            str(MODEL_PATH),
            **common,
        )
        event_rows = (
            (
                "edge_score_event",
                czr005_cpp.edge_score_native_event_replay_summary_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    str(MODEL_PATH),
                    **common,
                ),
            ),
            (
                "fallback_event",
                czr005_cpp.edge_score_native_event_fallback_replay_summary_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    **common,
                ),
            ),
        )
        for policy_name, summary in event_rows:
            accounted = int(summary["planned_count"]) + int(summary["unplanned_count"])
            rows.append(
                {
                    "case": case.spec.name,
                    "policy": policy_name,
                    "task_count": case.spec.task_count,
                    "planned_count": int(summary["planned_count"]),
                    "unplanned_count": int(summary["unplanned_count"]),
                    "decision_count": int(summary["decision_count"]),
                    "post_shield_conflicts": int(summary["post_shield_conflicts"]),
                    "mean_travel_time": float(summary["mean_travel_time"]),
                    "decisions_per_second": float(summary["decisions_per_second"]),
                    "compact_planned_count": int(compact["planned_count"]),
                    "compact_decision_count": int(compact["decision_count"]),
                    "accounted_pass": accounted == case.spec.task_count,
                    "safety_pass": int(summary["post_shield_conflicts"]) == 0,
                }
            )

    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["accounted_pass"]) for row in rows):
        raise AssertionError("event scheduler failed to account for all configured tasks")
    if not all(bool(row["safety_pass"]) for row in rows):
        raise AssertionError("event scheduler produced post-shield conflicts")
    print(f"phase8_native_cpp_event_scheduler rows={len(rows)} safety_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
