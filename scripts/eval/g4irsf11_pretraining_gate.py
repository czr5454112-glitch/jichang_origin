"""Assemble the fail-closed A--H gate that controls G4IRSF11 v3 training."""

from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


GATE_SCHEMA = "czr005.g4irsf11.pretraining_gate.v1"
PARTIAL = "PARTIAL_WITH_EXPLICIT_BLOCKER"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "pass", "executed"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _evidence(root: Path, paths: Sequence[Path]) -> list[dict[str, str]]:
    return [
        {"path": _relative(root, path), "sha256": sha256_file(path)}
        for path in paths
        if path.is_file()
    ]


def _gate(
    root: Path,
    *,
    passed: bool,
    paths: Sequence[Path],
    blockers: Sequence[str],
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = _evidence(root, paths)
    actual_blockers = list(blockers)
    if not evidence:
        actual_blockers.append("no hashed evidence artifact exists")
    return {
        "status": "PASS" if passed and evidence and not actual_blockers else PARTIAL,
        "evidence": evidence,
        "blockers": sorted(set(actual_blockers)),
        "metrics": dict(metrics or {}),
    }


def evaluate_pretraining_gate(root: Path) -> dict[str, Any]:
    table_dir = root / "outputs" / "tables"
    report_dir = root / "outputs" / "reports"
    artifact_dir = root / "artifacts" / "datasets"
    gate_dir = root / "artifacts" / "gates"

    protocol = gate_dir / "g4irsf11_event_runtime_protocol.json"
    case_table = table_dir / "g4irsf11_event_runtime_case_ledger.csv"
    frontier_table = table_dir / "g4irsf11_capacity_frontier.csv"
    ablation_table = table_dir / "g4irsf11_system_ablation.csv"
    fault_table = table_dir / "g4irsf11_temporal_fault_repair.csv"
    resource_table = table_dir / "g4irsf11_resource_runtime.csv"
    runtime_gate_table = table_dir / "g4irsf11_event_runtime_gate.csv"
    hard_case_table = table_dir / "g4irsf11_stratified_hard_case_index.csv"
    lineage_table = table_dir / "g4irsf11_feature_lineage_audit.csv"
    decision_manifest_path = artifact_dir / "g4irsf11_decision_trace_manifest.json"
    provenance_path = report_dir / "g4irsf11_gate_integrity_audit.json"

    decision = _read_json(decision_manifest_path)
    rows = _read_csv(case_table)
    frontier = _read_csv(frontier_table)
    ablations = _read_csv(ablation_table)
    faults = _read_csv(fault_table)
    resources = _read_csv(resource_table)
    provenance = _read_json(provenance_path)

    a_ok = provenance.get("overall_status") == "PASS" and provenance.get("remote_ci_status") == "PASS"
    a_blockers: list[str] = []
    if provenance.get("overall_status") != "PASS":
        a_blockers.append("local Git/protected-file provenance is missing or not PASS")
    if provenance.get("remote_ci_status") != "PASS":
        a_blockers.append("remote GitHub Actions status is not independently verified PASS")

    validation = decision.get("validation") if isinstance(decision.get("validation"), Mapping) else {}
    completeness = decision.get("trace_completeness") if isinstance(decision.get("trace_completeness"), Mapping) else {}
    b_ok = validation.get("status") == "PASS" and completeness.get("status") == "PASS"
    b_blockers = [] if b_ok else ["decision validation and/or complete trace groups are not PASS"]

    coverage = decision.get("coverage") if isinstance(decision.get("coverage"), Mapping) else {}
    c_ok = (
        coverage.get("status") == "PASS"
        and int(coverage.get("fault_local_active_decision_count_before_dedupe", 0)) > 0
        and decision.get("sampling_minimum_quota_status") == "PASS"
        and hard_case_table.is_file()
        and lineage_table.is_file()
    )
    c_blockers = [] if c_ok else [
        "stratified high-flow/active-fault/tail coverage, quota, hard-case, or lineage evidence is not PASS"
    ]

    paper = next((row for row in rows if row.get("case_id") == "real_map_paper_full"), {})
    d_ok = (
        paper.get("execution_status") == "EXECUTED"
        and _truth(paper.get("completion_pass"))
        and _truth(paper.get("event_runtime_invariant_pass"))
        and str(paper.get("runtime_full_astar_calls")) == "0"
        and str(paper.get("global_reservation_scan_count")) == "0"
    )
    d_blockers = [] if d_ok else [
        "paper-full event runtime did not both complete all 43,603 segments and pass online invariants"
    ]

    e_ok = (
        len(ablations) == 9
        and all(row.get("execution_status") == "EXECUTED" for row in ablations)
        and all(_truth(row.get("event_runtime_invariant_pass")) for row in ablations)
        and all(str(row.get("unresolved_deadlock_count")) == "0" for row in ablations)
        and all(str(row.get("starvation_count")) == "0" for row in ablations)
    )
    e_blockers = [] if e_ok else [
        "all nine local-control A/B cases must execute with invariants, zero unresolved deadlock, and zero starvation"
    ]

    f_ok = (
        len(frontier) == 63
        and all(row.get("execution_status") == "EXECUTED" for row in frontier)
        and all(str(row.get("safe_execution_pass")) in {"True", "False"} for row in frontier)
        and all(str(row.get("queue_stability_pass")) in {"True", "False"} for row in frontier)
        and all(str(row.get("service_level_pass")) in {"True", "False"} for row in frontier)
        and all(str(row.get("capacity_pass")) in {"True", "False"} for row in frontier)
    )
    f_blockers = [] if f_ok else [
        "the exact 7-mode x 9-scale frontier is incomplete or lacks independent gate classifications"
    ]

    g_ok = (
        len(resources) == 84
        and all(row.get("execution_status") == "EXECUTED" for row in resources)
        and all(int(float(row.get("peak_working_set_bytes") or 0)) > 0 for row in resources)
        and all(float(row.get("decision_latency_us_p99") or 0) >= 0.0 for row in resources)
    )
    g_blockers = [] if g_ok else [
        "all 84 formal cases require isolated-process working set and decision-latency evidence"
    ]

    h_ok = (
        len(faults) == 5
        and all(row.get("execution_status") == "EXECUTED" for row in faults)
        and all(_truth(row.get("fault_recovery_pass")) for row in faults)
    )
    h_blockers = [] if h_ok else [
        "all five temporal delay/loss/repeat/fault-policy cases must execute and recover within the frozen gate"
    ]

    gates = {
        "A": _gate(root, passed=a_ok, paths=[provenance_path, protocol], blockers=a_blockers),
        "B": _gate(
            root,
            passed=b_ok,
            paths=[decision_manifest_path, artifact_dir / "g4irsf11_decision_trace_schema.json"],
            blockers=b_blockers,
            metrics={
                "validated_decisions": validation.get("decision_count", 0),
                "complete_trace_seen": completeness.get("global_decision_seen_count", 0),
            },
        ),
        "C": _gate(
            root,
            passed=c_ok,
            paths=[decision_manifest_path, hard_case_table, lineage_table],
            blockers=c_blockers,
            metrics={
                "sample_count": (decision.get("sampling") or {}).get("sample_count", 0),
                "active_fault_decisions": coverage.get("fault_local_active_decision_count_before_dedupe", 0),
            },
        ),
        "D": _gate(
            root,
            passed=d_ok,
            paths=[case_table, runtime_gate_table],
            blockers=d_blockers,
            metrics={
                "requested_segments": paper.get("workload_segment_count", ""),
                "completed_segments": paper.get("completed_segment_count", ""),
            },
        ),
        "E": _gate(root, passed=e_ok, paths=[ablation_table], blockers=e_blockers),
        "F": _gate(
            root,
            passed=f_ok,
            paths=[frontier_table, protocol],
            blockers=f_blockers,
            metrics={"executed_cases": sum(row.get("execution_status") == "EXECUTED" for row in frontier)},
        ),
        "G": _gate(root, passed=g_ok, paths=[resource_table], blockers=g_blockers),
        "H": _gate(root, passed=h_ok, paths=[fault_table], blockers=h_blockers),
    }

    if decision_manifest_path.is_file():
        decision_binding: dict[str, Any] = {
            "path": _relative(root, decision_manifest_path),
            "sha256": sha256_file(decision_manifest_path),
        }
    else:
        decision_binding = {"path": _relative(root, decision_manifest_path), "sha256": ""}
    overall = "PASS" if all(entry["status"] == "PASS" for entry in gates.values()) else PARTIAL
    return {
        "schema": GATE_SCHEMA,
        "generated_date": date.today().isoformat(),
        "overall_status": overall,
        "gates": gates,
        "decision_manifest": decision_binding,
        "claim_boundary": (
            "A-H are independent fail-closed gates. A complete experiment matrix may retain negative "
            "capacity results, but v3 training remains blocked by any missing/partial gate."
        ),
    }


def write_gate_artifacts(root: Path, manifest: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    gate_path = root / "artifacts" / "gates" / "g4irsf11_pretraining_gate_manifest.json"
    table_path = root / "outputs" / "tables" / "g4irsf11_pretraining_gate.csv"
    report_path = root / "outputs" / "reports" / "g4irsf11_pretraining_gate_report.md"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "stage": stage,
            "status": entry["status"],
            "blockers": json.dumps(entry["blockers"], ensure_ascii=False),
            "evidence_count": len(entry["evidence"]),
            "metrics": json.dumps(entry["metrics"], ensure_ascii=False, sort_keys=True),
        }
        for stage, entry in manifest["gates"].items()
    ]
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report_path.write_text(
        "\n".join(
            [
                "# G4IRSF11 A--H Pretraining Gate",
                "",
                f"Status: `{manifest['overall_status']}`.",
                "",
                "| Stage | Status | Blockers |",
                "| --- | --- | --- |",
                *[
                    f"| {stage} | {entry['status']} | {'; '.join(entry['blockers'])} |"
                    for stage, entry in manifest["gates"].items()
                ],
                "",
                str(manifest["claim_boundary"]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return gate_path, table_path, report_path
