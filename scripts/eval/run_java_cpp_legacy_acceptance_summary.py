from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "outputs" / "reports" / "java_cpp_legacy_acceptance_summary_report.md"
TABLE_PATH = ROOT / "outputs" / "tables" / "java_cpp_legacy_acceptance_summary.csv"


@dataclass(frozen=True)
class PerformanceGate:
    gate: str
    performance_table: Path
    java_runtime: str
    cpp_runtime: str
    throughput_field: str
    parity_table: Path
    parity_fields: tuple[str, ...]
    summary_fields: tuple[str, ...]
    scope: str


GATES = (
    PerformanceGate(
        gate="astar_core",
        performance_table=ROOT / "outputs" / "tables" / "java_python_cpp_astar_performance.csv",
        java_runtime="legacy_java_astar",
        cpp_runtime="cpp_pybind_astar",
        throughput_field="plans_per_second",
        parity_table=ROOT / "outputs" / "tables" / "java_python_cpp_astar_path_parity.csv",
        parity_fields=("java_cpp_parity", "java_python_parity", "python_cpp_parity"),
        summary_fields=("checksum",),
        scope="legacy Java Astar.research vs Python reference and C++ pybind A* on 8000 map2/inputdata cases",
    ),
    PerformanceGate(
        gate="legacy_no_fault_window",
        performance_table=ROOT / "outputs" / "tables" / "java_cpp_legacy_window_performance.csv",
        java_runtime="legacy_java_ics_no_fault_window",
        cpp_runtime="cpp_pybind_legacy_no_fault_window",
        throughput_field="plans_per_second",
        parity_table=ROOT / "outputs" / "tables" / "java_cpp_legacy_window_route_parity.csv",
        parity_fields=("match",),
        summary_fields=(
            "epochs_run",
            "generated_count",
            "planned_count",
            "completed_count",
            "active_route_count",
            "unfinished_count",
            "route_size_checksum",
            "route_location_checksum",
            "last_epoch",
        ),
        scope="read-only Java ICS_PathFinding no-fault headless scheduler window vs native C++",
    ),
    PerformanceGate(
        gate="legacy_scheduled_fault_window",
        performance_table=ROOT / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_performance.csv",
        java_runtime="legacy_java_ics_scheduled_fault_window",
        cpp_runtime="cpp_pybind_legacy_scheduled_fault_window",
        throughput_field="plans_per_second",
        parity_table=ROOT / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_route_parity.csv",
        parity_fields=("match",),
        summary_fields=(
            "epochs_run",
            "generated_count",
            "planned_count",
            "completed_count",
            "active_route_count",
            "unfinished_count",
            "fault_event_count",
            "repair_event_count",
            "active_fault_count",
            "route_size_checksum",
            "route_location_checksum",
            "last_epoch",
        ),
        scope="deterministic scheduled fault/repair, including first-edge active-route fault removal",
    ),
    PerformanceGate(
        gate="legacy_probability_extreme_window",
        performance_table=ROOT
        / "outputs"
        / "tables"
        / "java_cpp_legacy_probability_extreme_window_performance.csv",
        java_runtime="legacy_java_ics_probability_extreme_window",
        cpp_runtime="cpp_pybind_legacy_probability_extreme_window",
        throughput_field="plans_per_second",
        parity_table=ROOT
        / "outputs"
        / "tables"
        / "java_cpp_legacy_probability_extreme_window_route_parity.csv",
        parity_fields=("match",),
        summary_fields=(
            "epochs_run",
            "generated_count",
            "planned_count",
            "completed_count",
            "active_route_count",
            "unfinished_count",
            "generated_fault_edge_count",
            "generated_repair_edge_count",
            "active_fault_count",
            "route_size_checksum",
            "route_location_checksum",
            "last_epoch",
        ),
        scope="deterministic probability-extreme Tasks.generate_tasks branches, fault_probability=1.0 repair_probability=0.0",
    ),
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing acceptance input table: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _row_by_runtime(rows: Iterable[dict[str, str]], runtime: str) -> dict[str, str]:
    for row in rows:
        if row.get("runtime") == runtime:
            return row
    raise KeyError(f"missing runtime row: {runtime}")


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _summary_match(java: dict[str, str], cpp: dict[str, str], fields: tuple[str, ...]) -> tuple[bool, str]:
    for field in fields:
        if str(java[field]) != str(cpp[field]):
            return False, f"{field}: java={java[field]} cpp={cpp[field]}"
    return True, "match"


def _parity_pass(path: Path, fields: tuple[str, ...]) -> tuple[bool, int, str]:
    rows = _read_rows(path)
    for index, row in enumerate(rows, start=1):
        for field in fields:
            if not _as_bool(row[field]):
                return False, len(rows), f"row {index} field {field}"
    return True, len(rows), "match"


def _gate_row(gate: PerformanceGate) -> dict[str, Any]:
    rows = _read_rows(gate.performance_table)
    java = _row_by_runtime(rows, gate.java_runtime)
    cpp = _row_by_runtime(rows, gate.cpp_runtime)
    java_rate = float(java[gate.throughput_field])
    cpp_rate = float(cpp[gate.throughput_field])
    speedup = cpp_rate / java_rate if java_rate > 0.0 else 0.0
    performance_pass = speedup >= 1.0
    summary_pass, summary_detail = _summary_match(java, cpp, gate.summary_fields)
    parity_pass, parity_rows, parity_detail = _parity_pass(gate.parity_table, gate.parity_fields)
    gate_pass = performance_pass and summary_pass and parity_pass
    return {
        "gate": gate.gate,
        "scope": gate.scope,
        "java_runtime": gate.java_runtime,
        "cpp_runtime": gate.cpp_runtime,
        "java_rate": java_rate,
        "cpp_rate": cpp_rate,
        "cpp_java_speedup": speedup,
        "performance_pass": performance_pass,
        "summary_pass": summary_pass,
        "summary_detail": summary_detail,
        "parity_pass": parity_pass,
        "parity_rows": parity_rows,
        "parity_detail": parity_detail,
        "gate_pass": gate_pass,
        "performance_table": gate.performance_table.relative_to(ROOT).as_posix(),
        "parity_table": gate.parity_table.relative_to(ROOT).as_posix(),
    }


def _write_table(rows: list[dict[str, Any]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "gate",
            "java_runtime",
            "cpp_runtime",
            "java_rate",
            "cpp_rate",
            "cpp_java_speedup",
            "performance_pass",
            "summary_pass",
            "parity_pass",
            "parity_rows",
            "gate_pass",
            "performance_table",
            "parity_table",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{field: row[field] for field in fieldnames},
                    "java_rate": f"{float(row['java_rate']):.6f}",
                    "cpp_rate": f"{float(row['cpp_rate']):.6f}",
                    "cpp_java_speedup": f"{float(row['cpp_java_speedup']):.6f}",
                }
            )


def _write_report(rows: list[dict[str, Any]]) -> None:
    all_pass = all(bool(row["gate_pass"]) for row in rows)
    min_speedup = min(float(row["cpp_java_speedup"]) for row in rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Java / C++ Legacy Acceptance Summary",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This summary is a read-only audit over the generated Java/C++ benchmark tables. "
            "It verifies that every recorded legacy-performance gate has Java/C++ functional parity "
            "and that Release C++ throughput is not below the read-only legacy Java baseline."
        ),
        "",
        "The legacy Java project remains reference-only; these gates use external harnesses and native C++ ports.",
        "",
        "## Gates",
        "",
        "| Gate | Scope | C++/Java speedup | Summary | Route/path parity | Performance |",
        "|---|---|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {gate} | {scope} | {cpp_java_speedup:.3f}x | {summary} | {parity} | {performance} |".format(
                gate=row["gate"],
                scope=row["scope"],
                cpp_java_speedup=float(row["cpp_java_speedup"]),
                summary="PASS" if row["summary_pass"] else f"FAIL ({row['summary_detail']})",
                parity="PASS" if row["parity_pass"] else f"FAIL ({row['parity_detail']})",
                performance="PASS" if row["performance_pass"] else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Acceptance Status",
            "",
            "- all recorded Java/C++ legacy gates pass: PASS"
            if all_pass
            else "- all recorded Java/C++ legacy gates pass: FAIL",
            f"- minimum C++/Java speedup across recorded gates: `{min_speedup:.3f}x`",
            "- legacy Java source modification: not required by these gates",
            "",
            "## Boundary",
            "",
            (
                "The acceptance evidence covers the computational core and headless legacy scheduler "
                "paths used by the project: A*, no-fault scheduling, deterministic fault/repair including "
                "active-route first-edge removal, and deterministic probability-extreme task-generation branches. "
                "Intermediate random probabilities are not used as a parity gate because the read-only Java project "
                "does not expose an injectable random seed. Swing repaint/sleep timing is GUI behavior rather than "
                "the Python/C++ compute runtime target."
            ),
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = [_gate_row(gate) for gate in GATES]
    _write_table(rows)
    _write_report(rows)
    if not all(bool(row["gate_pass"]) for row in rows):
        failed = ", ".join(row["gate"] for row in rows if not row["gate_pass"])
        raise AssertionError(f"legacy acceptance summary failed gates: {failed}")
    min_speedup = min(float(row["cpp_java_speedup"]) for row in rows)
    print(f"java_cpp_legacy_acceptance gates={len(rows)} min_speedup={min_speedup:.3f} all_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
