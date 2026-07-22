from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from czr005.models.g4irsf11_v3 import build_split_readiness_audit
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_HASH_SEMANTICS,
    CANONICAL_MAP_RELATIVE_PATH,
    CANONICAL_MAP_SHA256,
    canonical_map_identity,
    canonical_map_protocol_identity,
)

from scripts.eval.g4irsf11_pretraining_gate import (
    PARTIAL,
    evaluate_pretraining_gate,
    fixed_event_runtime_protocol_manifest,
    write_gate_artifacts,
)
from czr005.datasets.decision_trace import SCHEMA_ID, decision_trace_schema
from scripts.eval.g4irsf11_experiment_protocol import formal_cases
from scripts.eval.g4irsf11_result_validation import canonical_manifest_sha256
from scripts.eval.g4irsf11_publication import (
    artifact_bindings as publication_artifact_bindings,
    begin_completion,
    complete_publication,
)
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
    FORMAL_COMPLETION_PATH,
    FORMAL_PUBLICATION_ARTIFACTS,
    _formal_completion_metadata,
    _formal_producer,
)
from czr005.models.g4irsf11_v3 import (
    REQUIRED_DECISION_VALIDATIONS,
    SEMANTIC_TEXT_HASH,
    preflight_training,
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


def _semantic_sha(path: Path) -> str:
    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def _artifact_descriptor(root: Path, path: Path, row_count: int) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _semantic_sha(path),
        "hash_semantics": SEMANTIC_TEXT_HASH,
        "row_count": row_count,
    }


def _complete_fixture(root: Path) -> None:
    tables = root / "outputs" / "tables"
    reports = root / "outputs" / "reports"
    datasets = root / "artifacts" / "datasets"
    gates = root / "artifacts" / "gates"
    protocol = fixed_event_runtime_protocol_manifest()
    protocol_digest = canonical_manifest_sha256(protocol)
    implementation_digest = "f" * 64
    runner_args = SimpleNamespace(
        measurement_cohort="pretraining-fixture",
        concurrent_worker_target=8,
    )
    producer = _formal_producer(
        runner_args, implementation_digest=implementation_digest
    )
    row_binding = {
        "protocol_manifest_sha256": protocol_digest,
        "map_sha256": CANONICAL_MAP_SHA256,
        "implementation_sha256": implementation_digest,
        "measurement_cohort": "pretraining-fixture",
        "declared_concurrent_worker_target": 8,
    }
    cases = formal_cases()
    _json(gates / "g4irsf11_event_runtime_protocol.json", protocol)
    _json(
        reports / "g4irsf11_gate_integrity_audit.json",
        {
            "schema": "czr005.g4irsf11.provenance_ci_audit.v1",
            "overall_status": "PASS",
            "remote_ci_status": "PASS",
            "local_state_clean": True,
            "protected_inputs_clean": True,
            "fixed_real_map_clean": True,
            "fixed_real_map": {
                **canonical_map_protocol_identity(),
            },
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
    hard_case = tables / "g4irsf11_stratified_hard_case_index.csv"
    outcome_sample = datasets / "g4irsf11_decision_outcome_sample.jsonl"
    hard_rows: list[dict[str, object]] = []
    outcome_rows: list[str] = []
    for index in range(12):
        day_offset = 86_400 if index >= 6 else 0
        source = 1 + index % 2
        goal = 9 + index % 2
        decision_id = f"d-{index}"
        hard_rows.append(
            {
                "decision_id": decision_id,
                "task_id": f"task-{index}",
                "scenario": "fault" if index >= 10 else "highflow",
                "scenario_observed": "fault" if index >= 10 else "highflow",
                "scale": "4.0x" if index % 2 else "2.5x",
                "flight_bank": f"release_15m_{index % 4}",
                "load_level": "4.0x" if index % 2 else "2.5x",
                "fault_scenario": "single_delayed_30s" if index >= 10 else "no_fault",
                "fixed_real_map_only": True,
                "canonical_map_sha256": CANONICAL_MAP_SHA256,
                "source_node": source,
                "goal_node": goal,
                "fault_bucket": "fault_local_active" if index >= 10 else "no_fault",
                "original_arrival_time": day_offset + index * 100,
                "event_time": day_offset + index * 100 + 10,
                "candidate_records": json.dumps(
                    [
                        {"next_node": 2, "features": {"travel_time": 2.0}},
                        {"next_node": 3, "features": {"travel_time": 1.0}},
                    ]
                ),
                "selected_next": 3,
                "semantic_fingerprint": hashlib.sha256(decision_id.encode()).hexdigest(),
            }
        )
        outcome_rows.append(json.dumps({"decision_id": decision_id, "reached_goal": True}))
    _csv(hard_case, hard_rows)
    outcome_sample.parent.mkdir(parents=True, exist_ok=True)
    outcome_sample.write_text("\n".join(outcome_rows) + "\n", encoding="utf-8")
    lineage_path = tables / "g4irsf11_feature_lineage_audit.csv"
    _csv(lineage_path, [{"feature": "queue", "lineage": "runtime"}])
    source_mapping = datasets / "g4irsf11_source_release_mapping.csv"
    _csv(
        source_mapping,
        [
            {"decision_id": row["decision_id"], "task_id": row["task_id"]}
            for row in hard_rows
        ],
    )
    decision_manifest = datasets / "g4irsf11_decision_trace_manifest.json"
    _json(
        decision_manifest,
        {
            "schema_id": SCHEMA_ID,
            "fixed_real_map_only": True,
            "canonical_map_sha256": CANONICAL_MAP_SHA256,
            "graph": {
                "path": CANONICAL_MAP_RELATIVE_PATH.as_posix(),
                "sha256": CANONICAL_MAP_SHA256,
                "sha256_semantics": CANONICAL_MAP_HASH_SEMANTICS,
                "fixed_real_map_only": True,
                "topology_mutation_allowed": False,
                "raw_bytes_sha256": canonical_map_identity()["raw_bytes_sha256"],
            },
            "artifact_hash_semantics": (
                "sha256 of UTF-8 text after CRLF/CR newline normalization to LF"
            ),
            "validation": {
                "status": "PASS",
                "decision_count": 100,
                "fixed_real_map_identity": "PASS",
                **{name: "PASS" for name in REQUIRED_DECISION_VALIDATIONS},
            },
            "trace_completeness": {"status": "PASS", "global_decision_seen_count": 100},
            "coverage": {"status": "PASS", "fault_local_active_decision_count_before_dedupe": 2},
            "sampling_minimum_quota_status": "PASS",
            "sampling": {"sample_count": 80},
            "producer": producer,
            "artifacts": {
                "hard_case_index": {
                    **_artifact_descriptor(root, hard_case, len(hard_rows)),
                },
                "outcome_sample": {
                    **_artifact_descriptor(root, outcome_sample, len(outcome_rows)),
                },
                "feature_lineage_table": _artifact_descriptor(root, lineage_path, 1),
                "source_release_mapping": _artifact_descriptor(
                    root, source_mapping, len(hard_rows)
                ),
            },
        },
    )
    _json(datasets / "g4irsf11_decision_trace_schema.json", decision_trace_schema())
    _csv(
        tables / "g4irsf11_event_runtime_case_ledger.csv",
        [
            {
                "case_id": case.case_id,
                "execution_status": "EXECUTED",
                "completion_pass": True,
                "event_runtime_invariant_pass": True,
                "runtime_full_astar_calls": 0,
                "global_reservation_scan_count": 0,
                "workload_segment_count": 43603 if case.case_id == "real_map_paper_full" else 1,
                "completed_segment_count": 43603 if case.case_id == "real_map_paper_full" else 1,
                **row_binding,
            }
            for case in cases
        ],
    )
    _csv(tables / "g4irsf11_event_runtime_gate.csv", [{"status": "PASS"}])
    readiness, dataset = build_split_readiness_audit(
        hard_case,
        outcome_sample,
        decision_manifest_sha256=_semantic_sha(decision_manifest),
    )
    assert dataset is not None and readiness["status"] == "PASS"
    _json(reports / "g4irsf11_v3_split_readiness.json", readiness)
    _csv(
        tables / "g4irsf11_system_ablation.csv",
        [
            {
                "case_id": case.case_id,
                "execution_status": "EXECUTED",
                "event_runtime_invariant_pass": True,
                "unresolved_deadlock_count": 0,
                "starvation_count": 0,
                **row_binding,
            }
            for case in cases
            if case.category == "system_ablation"
        ],
    )
    _csv(
        tables / "g4irsf11_capacity_frontier.csv",
        [
            {
                "case_id": case.case_id,
                "execution_status": "EXECUTED",
                "safe_execution_pass": True,
                "queue_stability_pass": False,
                "service_level_pass": False,
                "capacity_pass": False,
                **row_binding,
            }
            for case in cases
            if case.category == "capacity_frontier"
        ],
    )
    _csv(
        tables / "g4irsf11_resource_runtime.csv",
        [
            {
                "case_id": case.case_id,
                "execution_status": "EXECUTED",
                "peak_working_set_bytes": 1024,
                "decision_latency_us_p99": 1.0,
                **row_binding,
            }
            for case in cases
        ],
    )
    _csv(
        tables / "g4irsf11_temporal_fault_repair.csv",
        [
            {
                "case_id": case.case_id,
                "execution_status": "EXECUTED",
                "fault_recovery_pass": True,
                **row_binding,
            }
            for case in cases
            if case.category == "temporal_fault"
        ],
    )
    for relative in FORMAL_PUBLICATION_ARTIFACTS:
        path = root / relative
        if path.is_file():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            _json(path, {})
        elif path.suffix == ".jsonl":
            path.write_text("", encoding="utf-8")
        elif path.suffix == ".csv":
            path.write_text("fixture\n", encoding="utf-8")
        else:
            path.write_text("fixture\n", encoding="utf-8")
    completion_metadata = _formal_completion_metadata(
        runner_args,
        implementation_digest=implementation_digest,
        executed_case_count=len(cases),
        decision_artifacts_ready=True,
        no_smoke_substitution_pass=True,
    )
    completion_path = root / FORMAL_COMPLETION_PATH.relative_to(
        Path(__file__).resolve().parents[1]
    )
    completion_bindings = publication_artifact_bindings(
        root, FORMAL_PUBLICATION_ARTIFACTS
    )
    transaction = begin_completion(
        completion_path,
        completion_metadata,
        expected_bindings=completion_bindings,
    )
    complete_publication(
        completion_path,
        completion_metadata,
        root=root,
        artifact_paths=FORMAL_PUBLICATION_ARTIFACTS,
        expected_bindings=completion_bindings,
        publication_id=str(transaction["publication_id"]),
    )


def test_gate_passes_only_with_all_exact_a_through_h_evidence(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    manifest = evaluate_pretraining_gate(tmp_path)
    assert manifest["overall_status"] == "PASS"
    assert set(manifest["gates"]) == set("ABCDEFGH")
    assert all(entry["evidence"] for entry in manifest["gates"].values())
    assert manifest["fixed_real_map_only"] is True
    assert manifest["canonical_map_sha256"] == CANONICAL_MAP_SHA256


def test_persisted_gate_allows_training_only_when_exact_recomputation_matches(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    manifest = evaluate_pretraining_gate(tmp_path)
    gate_path = write_gate_artifacts(tmp_path, manifest)[0]
    decision_path = (
        tmp_path / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    )

    approval = preflight_training(tmp_path, gate_path, decision_path)

    assert approval.allowed, approval.blockers
    assert approval.fixed_real_map_only is True
    assert approval.canonical_map_sha256 == CANONICAL_MAP_SHA256


def test_gate_rejects_unbound_protocol_and_decision_identity(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    protocol = tmp_path / "artifacts" / "gates" / "g4irsf11_event_runtime_protocol.json"
    _json(protocol, {"case_count": 84})
    decision_path = (
        tmp_path / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["graph"].pop("sha256")
    _json(decision_path, decision)

    manifest = evaluate_pretraining_gate(tmp_path)

    assert manifest["gates"]["A"]["status"] == PARTIAL
    assert manifest["gates"]["B"]["status"] == PARTIAL
    assert manifest["gates"]["C"]["status"] == PARTIAL


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


def test_gate_c_rejects_partial_split_readiness(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    readiness = tmp_path / "outputs" / "reports" / "g4irsf11_v3_split_readiness.json"
    payload = json.loads(readiness.read_text(encoding="utf-8"))
    payload["status"] = PARTIAL
    payload["blockers"] = ["day_heldout: at least two actual day buckets are required"]
    _json(readiness, payload)
    manifest = evaluate_pretraining_gate(tmp_path)
    assert manifest["gates"]["C"]["status"] == PARTIAL
    assert any("day_heldout" in value for value in manifest["gates"]["C"]["blockers"])


def test_gate_b_requires_the_exact_executable_decision_schema(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    schema_path = (
        tmp_path / "artifacts" / "datasets" / "g4irsf11_decision_trace_schema.json"
    )
    _json(schema_path, {"schema": "stale"})

    manifest = evaluate_pretraining_gate(tmp_path)

    assert manifest["gates"]["B"]["status"] == PARTIAL
