"""Run exact rolling-continuity and 8x/16x G4IRSF11 stress extensions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.eval.g4irsf11_evaluation_reporting import case_row, sha256_file, write_csv  # noqa: E402
from scripts.eval.g4irsf11_experiment_protocol import (  # noqa: E402
    EXTENSION_PROTOCOL_VERSION,
    system_extension_cases,
    system_extension_manifest,
)
from scripts.eval.g4irsf11_workloads import load_jsonl  # noqa: E402
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (  # noqa: E402
    MAP_PATH,
    SOURCE_TASK_PATH,
    _case_paths,
    _descriptor_matches,
    _read_json,
    _write_json,
    execute_case,
    implementation_sha256,
)


PROTOCOL_PATH = ROOT / "artifacts" / "gates" / "g4irsf11_system_extension_protocol.json"
TABLE_PATH = ROOT / "outputs" / "tables" / "g4irsf11_system_extension_matrix.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "g4irsf11_system_extension_report.md"


def _continuity_audit(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    expected = {
        "extension_rolling_2day_full": 87_206,
        "extension_rolling_7day_full": 305_221,
        "extension_synchronized_8x_full": 348_824,
        "extension_synchronized_16x_full": 697_648,
        "extension_fault_delayed_16x_full": 697_648,
    }.get(str(row.get("case_id")))
    actual = int(float(row.get("workload_segment_count") or 0))
    item["expected_exact_segment_count"] = expected if expected is not None else ""
    item["exact_segment_count_pass"] = expected is not None and actual == expected
    span = float(row.get("arrival_span_seconds") or 0.0)
    required_boundaries = 6 if row.get("case_id") == "extension_rolling_7day_full" else (
        1 if row.get("case_id") == "extension_rolling_2day_full" else 0
    )
    item["required_day_boundaries"] = required_boundaries
    item["observed_full_day_boundaries"] = int(span // 86_400.0)
    item["day_boundary_pass"] = (
        int(span // 86_400.0) >= required_boundaries if required_boundaries else True
    )
    item["no_smoke_substitution_pass"] = (
        row.get("execution_status") == "EXECUTED"
        and bool(item["exact_segment_count_pass"])
        and bool(item["day_boundary_pass"])
    )
    return item


def _load_rows(
    *, source_sha256: str, map_sha256: str, implementation_digest: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in system_extension_cases():
        paths = _case_paths(case)
        execution: dict[str, Any] = {
            "status": "NOT_RUN",
            "blocker": "exact system extension case not executed",
        }
        result = None
        if paths["execution"].is_file():
            candidate = _read_json(paths["execution"])
            if _descriptor_matches(
                candidate,
                case,
                source_sha256=source_sha256,
                map_sha256=map_sha256,
                implementation_digest=implementation_digest,
                protocol_version=EXTENSION_PROTOCOL_VERSION,
            ):
                execution = candidate
                if paths["result"].is_file():
                    result = _read_json(paths["result"])
        rows.append(_continuity_audit(case_row(case, result, execution)))
    return rows


def _write_report(rows: Sequence[Mapping[str, Any]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4IRSF11 Exact Continuity and Extreme-Stress Extensions",
        "",
        "These cases supplement the frozen 84-case matrix. They do not replace it and use no first-N segment limit.",
        "",
        "| Case | Execution | Exact input | Day boundary | Completed / requested | Capacity | Blocker |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        completed = f"{row.get('completed_segment_count', 0)} / {row.get('workload_segment_count', 0)}"
        lines.append(
            "| {case_id} | {execution_status} | {exact_segment_count_pass} | "
            "{day_boundary_pass} | {completed} | {capacity_pass} | {blocker} |".format(
                completed=completed,
                **row,
            )
        )
    lines.extend(
        [
            "",
            "Safe execution and capacity are independent. An 8x/16x run is never promoted merely because it avoids conflicts.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Exact extension case ID; repeatable")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--keep-workloads", action="store_true")
    parser.add_argument("--execute-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=14_400.0)
    parser.add_argument("--max-events", type=int, default=50_000_000)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--search-path", type=Path, default=ROOT / "build_vs" / "python" / "Release")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = system_extension_cases()
    by_id = {case.case_id: case for case in cases}
    if args.case:
        unknown = sorted(set(args.case) - set(by_id))
        if unknown:
            raise SystemExit(f"unknown --case values: {unknown}")
        selected = [by_id[name] for name in args.case]
    else:
        selected = list(cases)

    _write_json(PROTOCOL_PATH, system_extension_manifest())
    base_rows = load_jsonl(SOURCE_TASK_PATH)
    if len(base_rows) != 43_603:
        raise SystemExit(f"formal source task count must be 43603, got {len(base_rows)}")
    source_sha256 = sha256_file(SOURCE_TASK_PATH)
    map_sha256 = sha256_file(MAP_PATH)
    implementation_digest = implementation_sha256(args.search_path)
    failures = 0
    for index, case in enumerate(selected, start=1):
        print(f"[g4irsf11-extension] {index}/{len(selected)} START {case.case_id}", flush=True)
        _, execution = execute_case(
            case,
            base_rows,
            args,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            protocol_version=EXTENSION_PROTOCOL_VERSION,
        )
        failures += execution.get("status") != "EXECUTED"
        print(
            f"[g4irsf11-extension] {index}/{len(selected)} {execution.get('status')} {case.case_id}",
            flush=True,
        )
    if args.execute_only:
        return 2 if failures else 0
    rows = _load_rows(
        source_sha256=source_sha256,
        map_sha256=map_sha256,
        implementation_digest=implementation_digest,
    )
    write_csv(TABLE_PATH, rows)
    _write_report(rows)
    print(
        json.dumps(
            {
                "executed": sum(row["execution_status"] == "EXECUTED" for row in rows),
                "case_count": len(rows),
                "exact_inputs": sum(bool(row["no_smoke_substitution_pass"]) for row in rows),
                "failures": failures,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
