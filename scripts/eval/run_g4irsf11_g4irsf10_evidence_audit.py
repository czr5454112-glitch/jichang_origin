"""Re-audit G4IRSF10 artifacts before G4IRSF11 changes the runtime.

This runner is intentionally limited to the historical hand-off.  Runtime,
capacity, fault and policy experiments live in separate runners so generating
one report can never masquerade as completing the whole stage.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf11_g4irsf10_audit import (
    audit_hard_case_rows,
    audit_high_flow_rows,
    audit_jsonl_span,
    read_csv_rows,
    write_csv,
)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(value) for value in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _scenario_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row.get("scenario", "")): row for row in rows}


def _resolve_recorded_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path
    # Artifacts can contain an absolute path from the machine that generated
    # them.  Only the repo-relative suffix is accepted as a relocation fallback.
    lowered = [part.lower() for part in path.parts]
    for anchor in (".pytest_cache", "artifacts", "outputs", "data"):
        if anchor in lowered:
            return root.joinpath(*path.parts[lowered.index(anchor) :])
    return path


def _smoke_span_rows(root: Path, high_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_name = _scenario_rows(high_rows)
    result: list[dict[str, Any]] = []
    for scenario, intended_scope in (
        ("high_flow_no_fault_32x_smoke", "32x full scale"),
        ("rolling_7_day_1x_smoke", "7 complete days"),
        ("rolling_2_day_1x", "2 complete days"),
    ):
        row = by_name.get(scenario)
        if not row or str(row.get("task_path", "")) in {"", "NOT_RUN"}:
            result.append(
                {
                    "scenario": scenario,
                    "status": "NOT_EXECUTED_OR_MISSING",
                    "intended_scope": intended_scope,
                }
            )
            continue
        path = _resolve_recorded_path(root, str(row["task_path"]))
        if not path.exists():
            result.append(
                {
                    "scenario": scenario,
                    "status": "ARTIFACT_MISSING",
                    "intended_scope": intended_scope,
                    "task_path": str(path),
                }
            )
            continue
        executed_limit = int(float(row.get("task_count") or 0))
        span = audit_jsonl_span(path, executed_limit)
        result.append(
            {
                "scenario": scenario,
                "status": "PREFIX_MEASURED",
                "intended_scope": intended_scope,
                "task_path": str(path),
                "executed_rows": span.rows_used,
                "generated_rows": span.full_row_count,
                "coverage_fraction": span.coverage_fraction,
                "min_pass_time": span.min_pass_time,
                "max_pass_time": span.max_pass_time,
                "executed_time_span_seconds": span.elapsed_seconds,
                "executed_copy_indices": json.dumps(span.copy_indices),
                "executed_copy_count": len(span.copy_indices),
                "full_scope_proven": span.rows_used == span.full_row_count,
            }
        )
    return result


def _generation_evidence(root: Path) -> list[dict[str, Any]]:
    manifest_dir = root / ".pytest_cache" / "g4irsf10" / "tasks"
    result: list[dict[str, Any]] = []
    for scenario in ("high_flow_no_fault_2x", "high_flow_no_fault_4x", "rolling_7_day_1x_smoke"):
        path = manifest_dir / f"{scenario}_tasks_manifest.json"
        if not path.exists():
            result.append({"scenario": scenario, "status": "MANIFEST_MISSING"})
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        result.append(
            {
                "scenario": scenario,
                "status": "RECORDED",
                "generation_level": manifest.get("generation_level"),
                "scale": manifest.get("scale"),
                "rolling_days": manifest.get("rolling_days"),
                "time_compression": manifest.get("time_compression"),
                "row_count": manifest.get("row_count"),
                "source_input": manifest.get("source_input"),
                "independent_rule_replay": False,
                "generator_classification": "deterministic synchronized replicas with micro offsets",
            }
        )
    return result


def run(root: Path) -> dict[str, Path]:
    high_path = root / "outputs" / "tables" / "g4irsf10_v2_safe_high_flow_matrix.csv"
    hard_path = root / "outputs" / "tables" / "g4irsf10_hard_case_index.csv"
    if not high_path.exists() or not hard_path.exists():
        raise FileNotFoundError("G4IRSF10 hand-off artifacts are incomplete")

    high_source = read_csv_rows(high_path)
    high_audit = audit_high_flow_rows(high_source)
    hard_source = read_csv_rows(hard_path)
    hard_summary, distributions = audit_hard_case_rows(hard_source)
    smoke_rows = _smoke_span_rows(root, high_source)
    generation_rows = _generation_evidence(root)

    table_dir = root / "outputs" / "tables"
    report_dir = root / "outputs" / "reports"
    high_out = table_dir / "g4irsf11_g4irsf10_high_flow_reaudit.csv"
    smoke_out = table_dir / "g4irsf11_g4irsf10_smoke_span_audit.csv"
    hard_out = table_dir / "g4irsf11_g4irsf10_hardcase_distribution.csv"
    summary_out = table_dir / "g4irsf11_g4irsf10_hardcase_summary.csv"
    generation_out = table_dir / "g4irsf11_g4irsf10_generation_audit.csv"
    report_out = report_dir / "g4irsf11_g4irsf10_evidence_audit.md"
    write_csv(high_out, high_audit)
    write_csv(smoke_out, smoke_rows)
    write_csv(hard_out, distributions)
    write_csv(summary_out, [hard_summary])
    write_csv(generation_out, generation_rows)

    high_table = [
        [
            row["scale"],
            f"{row['mean_tth']:.6f}",
            f"{row['p95_tth']:.6f}",
            f"{row['p99_tth']:.6f}",
            row["source_queue_backlog"],
            f"{row['max_source_queue_delay']:.3f}",
            row["loop_count"],
            f"{row['fallback_per_planned_segment']:.6f}",
            f"{row['segment_throughput_per_second']:.3f}",
            "PASS" if row["safe_execution_pass"] else "FAIL",
            row["capacity_status"],
        ]
        for row in high_audit
        if row["evidence_status"] == "RECORDED"
    ]
    smoke_table = [
        [
            row["scenario"],
            row["status"],
            row.get("executed_rows", ""),
            row.get("generated_rows", ""),
            f"{float(row.get('coverage_fraction', 0.0)):.6f}",
            f"{float(row.get('executed_time_span_seconds', 0.0)):.3f}",
            row.get("executed_copy_indices", ""),
            row.get("full_scope_proven", False),
        ]
        for row in smoke_rows
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    report_out.write_text(
        "\n".join(
            [
                "# G4IRSF11 G4IRSF10 evidence re-audit",
                "",
                "This is a direct artifact/code audit, not a restatement of the previous promotion report.",
                "",
                "## Scale evidence",
                "",
                _markdown_table(
                    [
                        "Scale",
                        "Mean THT",
                        "p95",
                        "p99",
                        "Backlog count",
                        "Max queue delay s",
                        "Loops",
                        "Fallback/planned segment",
                        "Planned segment/s",
                        "Safe execution",
                        "Capacity",
                    ],
                    high_table,
                ),
                "",
                "All five rows pass the narrow safe-execution predicate only when completion is exact and conflicts/full A* are zero. Queue stability remains `UNVERIFIED_NO_TIME_SERIES`; service level remains `UNVERIFIED_NO_SLO`. Therefore none is relabelled as capacity PASS. In particular, 16x is retained as operational-capacity negative evidence. G4IRSF10 did not retain the total decision count, so fallback/decision and decision/s are explicitly unavailable; the table reports only fallback/planned-segment and planned-segment/s diagnostics.",
                "",
                "## Smoke and rolling scope",
                "",
                _markdown_table(
                    ["Scenario", "Status", "Executed", "Generated", "Coverage", "Time span s", "Copy indices", "Full scope"],
                    smoke_table,
                ),
                "",
                "The measured scope uses the prefix actually passed to the runtime. The unconsumed tail of a generated JSONL is not continuity evidence.",
                "",
                "## Generator classification",
                "",
                "The audited generator copies every processed base row for each replica/day and adds deterministic replica micro-offsets. It preserves selected empirical distributions, but it is not independent-day generation and is not an original Java rule replay.",
                "",
                "## Legacy hard-case index",
                "",
                _markdown_table(
                    ["Rows", "Unique content", "Duplicates", "Duplicate rate", "Scenarios", "High-flow", "Fault", "Tail", "Required coverage gate"],
                    [[
                        hard_summary["row_count"],
                        hard_summary["unique_content_count"],
                        hard_summary["duplicate_content_count"],
                        f"{hard_summary['duplicate_rate']:.6f}",
                        hard_summary["scenario_count"],
                        hard_summary["covers_high_flow"],
                        hard_summary["covers_fault"],
                        hard_summary["covers_tail"],
                        hard_summary["required_family_gate"],
                    ]],
                ),
                "",
                "The index is task/path-derived and sequentially capped. This audit measures the rows actually written; the manifest's pre-cap `seen` counter is not used as coverage proof. The index remains diagnostic-only and is not eligible for v3 training.",
                "",
                "## Claim boundary",
                "",
                "G4IRSF10 demonstrated a complete zero-conflict, zero-full-A* execution closure. It did not demonstrate 16x operational capacity, queue stability, a seven-day executed continuity window, temporal repair, real peak RSS, or a decision-level training dataset.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "high_flow": high_out,
        "smoke": smoke_out,
        "hard_distribution": hard_out,
        "hard_summary": summary_out,
        "generation": generation_out,
        "report": report_out,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    outputs = run(args.repo_root.resolve())
    print(json.dumps({name: str(path) for name, path in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
