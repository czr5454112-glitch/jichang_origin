"""Run Gate A against production evidence and preserve explicit blockers.

This runner intentionally exits non-zero while historical G4IRSF10 artifacts
lack executable command/status evidence or a legal decision-level hard-case
population.  Unit-test success is reported independently and can never promote
the production evidence gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf11_fixed_map import canonical_map_identity  # noqa: E402
from scripts.eval.g4irsf11_gate_integrity import (  # noqa: E402
    CommandRecord,
    run_recorded_command,
)


CONFIG = ROOT / "artifacts" / "gates" / "g4irsf11_gate_a_production_config.json"
AUDIT_JSON = ROOT / ".pytest_cache" / "g4irsf11" / "gate_a_production.json"
AUDIT_CSV = ROOT / "outputs" / "tables" / "g4irsf11_gate_integrity_audit.csv"
AUDIT_MD = ROOT / "outputs" / "reports" / "g4irsf11_gate_integrity_audit.md"
CI_REPORT = ROOT / "outputs" / "reports" / "g4irsf11_ci_or_blocker_report.md"

TARGET_TESTS = (
    "tests/test_g4irsf11_gate_integrity.py",
    "tests/test_g4irsf11_provenance_audit.py",
    "tests/test_g4irsf11_g4irsf10_audit.py",
)
PY_COMPILE_TARGETS = (
    "scripts/eval/g4irsf11_fixed_map.py",
    "scripts/eval/g4irsf11_gate_integrity.py",
    "scripts/eval/g4irsf11_provenance_audit.py",
    "scripts/eval/g4irsf11_g4irsf10_audit.py",
    "scripts/eval/run_g4irsf11_gate_a_production_audit.py",
)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "gate",
        "status",
        "violation_count",
        "row_count",
        "key_metrics_json",
        "detail_sample",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(value) for value in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _command_suite(root: Path, config: Path, audit_json: Path) -> list[CommandRecord]:
    python = sys.executable
    pytest_basetemp = (
        root / ".pytest_cache" / "g4irsf11" / f"{audit_json.stem}_tests"
    )
    commands = [
        (python, "-m", "py_compile", *PY_COMPILE_TARGETS),
        (
            python,
            "-m",
            "pytest",
            "-q",
            *TARGET_TESTS,
            "--basetemp",
            str(pytest_basetemp),
        ),
        (python, "scripts/eval/validate_g4irsf11_committed_artifacts.py"),
        (
            python,
            "scripts/eval/g4irsf11_gate_integrity.py",
            "--repo",
            str(root),
            "--config",
            str(config),
            "--output",
            str(audit_json),
        ),
    ]
    return [run_recorded_command(command, cwd=root, timeout_seconds=180.0) for command in commands]


def _check_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        details = check.get("details") if isinstance(check.get("details"), list) else []
        metrics = check.get("metrics") if isinstance(check.get("metrics"), Mapping) else {}
        violation_count = int(metrics.get("violation_count", len(details)))
        row_count = metrics.get("row_count", metrics.get("actual_count", ""))
        keys = (
            "expected_count",
            "actual_count",
            "high_flow_count",
            "fault_count",
            "tail_count",
            "invalid_candidate_count",
            "invalid_decision_semantics_count",
            "invalid_source_goal_count",
            "invalid_sampling_evidence_count",
            "duplicate_fraction",
            "max_scenario_family_fraction",
            "runtime_feature_count",
            "runtime_state_field_count",
            "lineage_field_count",
        )
        key_metrics = {key: metrics[key] for key in keys if key in metrics}
        rows.append(
            {
                "gate": str(check.get("name") or ""),
                "status": str(check.get("status") or ""),
                "violation_count": violation_count,
                "row_count": row_count,
                "key_metrics_json": json.dumps(key_metrics, sort_keys=True),
                "detail_sample": " | ".join(str(value) for value in details[:3]),
            }
        )
    return rows


def _write_reports(
    payload: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    commands: Sequence[CommandRecord],
) -> None:
    _write_csv(AUDIT_CSV, rows)
    by_name = {str(row["gate"]): row for row in rows}
    evidence_names = (
        "fixed_real_map_identity_and_topology",
        "paper_scenario_exact_set_hash_status",
        "optional_executed_or_explicit_blocker",
        "hard_case_stratified_coverage_and_validity",
        "runtime_feature_field_lineage_no_leakage",
    )
    evidence_rows = [by_name[name] for name in evidence_names if name in by_name]
    evidence_status = (
        "PASS"
        if len(evidence_rows) == len(evidence_names)
        and all(row["status"] == "PASS" for row in evidence_rows)
        else "FAIL"
    )
    identity = canonical_map_identity()
    table = [
        [row["gate"], row["status"], row["violation_count"], row["row_count"]]
        for row in evidence_rows
    ]
    paper = by_name.get("paper_scenario_exact_set_hash_status", {})
    optional = by_name.get("optional_executed_or_explicit_blocker", {})
    hard = by_name.get("hard_case_stratified_coverage_and_validity", {})
    lineage = by_name.get("runtime_feature_field_lineage_no_leakage", {})
    AUDIT_MD.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_MD.write_text(
        "\n".join(
            [
                "# G4IRSF11 Gate A production evidence audit",
                "",
                f"Overall production-evidence status: `{evidence_status}`.",
                "",
                "This report evaluates the checked-in G4IRSF10 artifacts. Passing function tests are not production evidence and cannot change a failing evidence gate.",
                "",
                "## Fixed real map identity",
                "",
                f"- Path: `{identity['repo_relative_path']}`",
                f"- Normalized-text SHA-256: `{identity['sha256']}`",
                f"- Raw-byte SHA-256: `{identity['raw_bytes_sha256']}`",
                "- Topology mutation allowed: `false`",
                "",
                "## Gate results",
                "",
                _markdown_table(
                    ["Gate", "Status", "Violations", "Evidence rows"], table
                ),
                "",
                "## Explicit historical blockers",
                "",
                f"- Paper matrix: `{paper.get('status', 'MISSING')}` with `{paper.get('violation_count', 'unknown')}` violations. The frozen 37 rows lack recorded execution status, executable command, and return code (37 x 3 = 111).",
                f"- Optional boundary matrix: `{optional.get('status', 'MISSING')}` with `{optional.get('violation_count', 'unknown')}` violations. Each of the four boundaries lacks an executed-or-explicit-blocker status.",
                f"- Legacy hard-case index: `{hard.get('status', 'MISSING')}` with `{hard.get('violation_count', 'unknown')}` violations. It is path/task-derived, lacks legal decision records and sampling provenance, and is not training evidence.",
                f"- Runtime field lineage: `{lineage.get('status', 'MISSING')}`. The actual committed lineage remains a distinct transitive no-leakage gate.",
                "",
                "## Claim boundary",
                "",
                "Gate A is fail-closed. Historical execution summaries remain useful diagnostics, but they are not promoted to reproducible experiment, optional-boundary, hard-case-training, or CI provenance PASS.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    validation_commands = commands[:3]
    validation_status = (
        "PASS" if all(command.return_code == 0 for command in validation_commands) else "BLOCKED"
    )
    command_table = [
        [command.executable_command, command.return_code]
        for command in commands
    ]
    blockers = [
        str(row["gate"])
        for row in evidence_rows
        if str(row["status"]) != "PASS"
    ]
    CI_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF11 CI or blocker report",
                "",
                f"Local validation-command status: `{validation_status}`.",
                f"Production Gate-A status: `{evidence_status}`.",
                "",
                "## Exact target test list",
                "",
                *[f"- `{test}`" for test in TARGET_TESTS],
                "",
                "## Executed commands and return codes",
                "",
                _markdown_table(["Executable command", "Return code"], command_table),
                "",
                "The production gate command is expected to return `2` while evidence blockers remain; that non-zero code is recorded rather than relabelled as a test failure or PASS.",
                "",
                "## Promotion blockers",
                "",
                *([f"- `{name}`" for name in blockers] or ["- None"]),
                "",
                f"Raw local gate JSON: `{AUDIT_JSON.relative_to(ROOT).as_posix()}` (ignored runtime evidence).",
                f"Committed config: `{CONFIG.relative_to(ROOT).as_posix()}`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _validate_gate_command_payload(
    payload: Mapping[str, Any], gate_return_code: int
) -> int:
    if payload.get("schema") != "czr005.g4irsf11.gate_integrity.v1":
        raise RuntimeError("production gate wrote an unexpected audit schema")
    status = payload.get("overall_status")
    if status not in {"PASS", "FAIL"}:
        raise RuntimeError(f"production gate wrote an invalid overall_status: {status!r}")
    expected_return_code = 0 if status == "PASS" else 2
    if gate_return_code != expected_return_code:
        raise RuntimeError(
            "production gate return code contradicts its payload: "
            f"status={status}, expected={expected_return_code}, actual={gate_return_code}"
        )
    return expected_return_code


def run(root: Path, config: Path) -> int:
    pending_audit = AUDIT_JSON.with_name(
        f"{AUDIT_JSON.stem}.pending-{uuid.uuid4().hex}{AUDIT_JSON.suffix}"
    )
    if pending_audit.exists():
        raise RuntimeError(f"refusing to reuse a pre-existing pending audit: {pending_audit}")
    commands = _command_suite(root, config, pending_audit)
    gate_command = commands[-1]
    if not pending_audit.is_file():
        raise RuntimeError(
            "production gate did not write its JSON report: "
            f"return_code={gate_command.return_code}, stderr={gate_command.stderr}"
        )
    payload = json.loads(pending_audit.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("production gate JSON must be an object")
    status = _validate_gate_command_payload(payload, gate_command.return_code)
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    pending_audit.replace(AUDIT_JSON)
    rows = _check_rows(payload)
    _write_reports(payload, rows, commands)
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=CONFIG)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = run(args.repo_root.resolve(), args.config.resolve())
    print(
        json.dumps(
            {
                "status": "PASS" if status == 0 else "FAIL",
                "audit_csv": str(AUDIT_CSV),
                "audit_md": str(AUDIT_MD),
                "ci_report": str(CI_REPORT),
            },
            sort_keys=True,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
