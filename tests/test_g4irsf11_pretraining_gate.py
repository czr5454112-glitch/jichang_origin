from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval.g4irsf11_pretraining_gate import (
    PARTIAL,
    evaluate_pretraining_gate,
    write_gate_artifacts,
)


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _complete_fixture(root: Path) -> None:
    tables = root / "outputs" / "tables"
    reports = root / "outputs" / "reports"
    datasets = root / "artifacts" / "datasets"
    gates = root / "artifacts" / "gates"
    _json(gates / "g4irsf11_event_runtime_protocol.json", {"case_count": 84})
    _json(
        reports / "g4irsf11_gate_integrity_audit.json",
        {
            "schema": "czr005.g4irsf11.provenance_ci_audit.v1",
            "overall_status": "PASS",
            "remote_ci_status": "PASS",
            "local_state_clean": True,
            "protected_inputs_clean": True,
            "audited_head_sha": "a" * 40,
            "audited_upstream_head_sha": "a" * 40,
            "remote_ci": {
                "head_sha": "a" * 40,
                "workflow": "g4irsf11-gate-integrity",
                "branch": "codex/czr005-rewrite",
                "event": "push",
                "conclusion": "success",
                "run_url": "https://github.com/example/actions/runs/1",
            },
        },
    )
    _json(
        datasets / "g4irsf11_decision_trace_manifest.json",
        {
            "validation": {"status": "PASS", "decision_count": 100},
            "trace_completeness": {"status": "PASS", "global_decision_seen_count": 100},
            "coverage": {"status": "PASS", "fault_local_active_decision_count_before_dedupe": 2},
            "sampling_minimum_quota_status": "PASS",
            "sampling": {"sample_count": 80},
        },
    )
    _json(datasets / "g4irsf11_decision_trace_schema.json", {"schema": "trace"})
    _csv(
        tables / "g4irsf11_event_runtime_case_ledger.csv",
        [
            {
                "case_id": "real_map_paper_full",
                "execution_status": "EXECUTED",
                "completion_pass": True,
                "event_runtime_invariant_pass": True,
                "runtime_full_astar_calls": 0,
                "global_reservation_scan_count": 0,
                "workload_segment_count": 43603,
                "completed_segment_count": 43603,
            }
        ],
    )
    _csv(tables / "g4irsf11_event_runtime_gate.csv", [{"status": "PASS"}])
    _csv(tables / "g4irsf11_stratified_hard_case_index.csv", [{"decision_id": "d"}])
    _csv(tables / "g4irsf11_feature_lineage_audit.csv", [{"feature": "queue", "lineage": "runtime"}])
    _csv(
        tables / "g4irsf11_system_ablation.csv",
        [
            {
                "case_id": f"a{i}",
                "execution_status": "EXECUTED",
                "event_runtime_invariant_pass": True,
                "unresolved_deadlock_count": 0,
                "starvation_count": 0,
            }
            for i in range(9)
        ],
    )
    _csv(
        tables / "g4irsf11_capacity_frontier.csv",
        [
            {
                "case_id": f"f{i}",
                "execution_status": "EXECUTED",
                "safe_execution_pass": i % 2 == 0,
                "queue_stability_pass": False,
                "service_level_pass": False,
                "capacity_pass": False,
            }
            for i in range(63)
        ],
    )
    _csv(
        tables / "g4irsf11_resource_runtime.csv",
        [
            {
                "case_id": f"r{i}",
                "execution_status": "EXECUTED",
                "peak_working_set_bytes": 1024,
                "decision_latency_us_p99": 1.0,
            }
            for i in range(84)
        ],
    )
    _csv(
        tables / "g4irsf11_temporal_fault_repair.csv",
        [
            {
                "case_id": f"fault{i}",
                "execution_status": "EXECUTED",
                "fault_recovery_pass": True,
            }
            for i in range(5)
        ],
    )


def test_gate_passes_only_with_all_exact_a_through_h_evidence(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    manifest = evaluate_pretraining_gate(tmp_path)
    assert manifest["overall_status"] == "PASS"
    assert set(manifest["gates"]) == set("ABCDEFGH")
    assert all(entry["evidence"] for entry in manifest["gates"].values())


def test_gate_fails_closed_for_missing_ci_and_incomplete_paper_full(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    provenance = tmp_path / "outputs" / "reports" / "g4irsf11_gate_integrity_audit.json"
    _json(
        provenance,
        {
            "schema": "czr005.g4irsf11.provenance_ci_audit.v1",
            "overall_status": "PASS",
            "remote_ci_status": "UNVERIFIED",
            "audited_head_sha": "a" * 40,
            "audited_upstream_head_sha": "a" * 40,
            "remote_ci": {"head_sha": "a" * 40},
        },
    )
    ledger = tmp_path / "outputs" / "tables" / "g4irsf11_event_runtime_case_ledger.csv"
    _csv(
        ledger,
        [
            {
                "case_id": "real_map_paper_full",
                "execution_status": "EXECUTED",
                "completion_pass": False,
                "event_runtime_invariant_pass": True,
                "runtime_full_astar_calls": 0,
                "global_reservation_scan_count": 0,
                "workload_segment_count": 43603,
                "completed_segment_count": 12119,
            }
        ],
    )
    manifest = evaluate_pretraining_gate(tmp_path)
    assert manifest["overall_status"] == PARTIAL
    assert manifest["gates"]["A"]["status"] == PARTIAL
    assert manifest["gates"]["D"]["status"] == PARTIAL


def test_gate_requires_exact_matrix_counts_and_writes_hashed_manifest(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    frontier = tmp_path / "outputs" / "tables" / "g4irsf11_capacity_frontier.csv"
    rows = list(csv.DictReader(frontier.open(encoding="utf-8")))
    _csv(frontier, rows[:-1])
    manifest = evaluate_pretraining_gate(tmp_path)
    assert manifest["gates"]["F"]["status"] == PARTIAL
    paths = write_gate_artifacts(tmp_path, manifest)
    assert all(path.is_file() for path in paths)
    saved = json.loads(paths[0].read_text(encoding="utf-8"))
    assert saved["overall_status"] == PARTIAL
    assert saved["gates"]["F"]["evidence"][0]["sha256"]
