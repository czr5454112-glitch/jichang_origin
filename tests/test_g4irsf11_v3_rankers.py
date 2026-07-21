from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from czr005.models.g4irsf11_v3 import (
    FEATURE_NAMES,
    MODEL_NAMES,
    PRETRAINING_GATE_SCHEMA,
    REQUIRED_DECISION_VALIDATIONS,
    REQUIRED_STAGE_GATES,
    SPLIT_NAMES,
    DecisionExample,
    V3TrainingError,
    connected_group_ids,
    load_training_examples,
    preflight_training,
    prepare_dataset,
    score_v3_candidates,
    split_audit_rows,
    train_all_models,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor(root: Path, path: Path, *, rows: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha(path),
    }
    if rows is not None:
        result["row_count"] = rows
    return result


def _write_preflight_fixture(root: Path) -> tuple[Path, Path, dict[str, object]]:
    root.mkdir(parents=True, exist_ok=True)
    artifacts = root / "artifacts"
    artifacts.mkdir()
    hard = artifacts / "hard.csv"
    hard.write_text("decision_id\nd-1\n", encoding="utf-8")
    outcomes = artifacts / "outcomes.jsonl"
    outcomes.write_text('{"decision_id":"d-1","reached_goal":true}\n', encoding="utf-8")
    lineage = artifacts / "lineage.csv"
    lineage.write_text("field_path\ntravel_time\n", encoding="utf-8")
    source = artifacts / "source.csv"
    source.write_text("decision_id\nd-1\n", encoding="utf-8")
    decision = {
        "schema_id": "czr005.g4irsf11.decision_trace.v1",
        "validation": {
            "status": "PASS",
            **{name: "PASS" for name in REQUIRED_DECISION_VALIDATIONS},
        },
        "coverage": {"status": "PASS"},
        "sampling": {"sample_count": 1},
        "sampling_minimum_quota_status": "PASS",
        "artifacts": {
            "hard_case_index": _descriptor(root, hard, rows=1),
            "outcome_sample": _descriptor(root, outcomes, rows=1),
            "feature_lineage_table": _descriptor(root, lineage, rows=1),
            "source_release_mapping": _descriptor(root, source, rows=1),
        },
    }
    decision_path = root / "decision.json"
    decision_path.write_text(json.dumps(decision, sort_keys=True), encoding="utf-8")

    gates: dict[str, object] = {}
    for stage in REQUIRED_STAGE_GATES:
        evidence = artifacts / f"gate_{stage}.json"
        evidence.write_text(json.dumps({"stage": stage, "status": "PASS"}), encoding="utf-8")
        gates[stage] = {"status": "PASS", "evidence": [_descriptor(root, evidence)]}
    gate = {
        "schema": PRETRAINING_GATE_SCHEMA,
        "gates": gates,
        "decision_manifest": _descriptor(root, decision_path),
    }
    gate_path = root / "gate.json"
    gate_path.write_text(json.dumps(gate, sort_keys=True), encoding="utf-8")
    return gate_path, decision_path, gate


def test_preflight_requires_hashed_a_through_h_and_exact_decision_binding(tmp_path: Path) -> None:
    gate_path, decision_path, _ = _write_preflight_fixture(tmp_path)
    approval = preflight_training(tmp_path, gate_path, decision_path)
    assert approval.allowed
    assert approval.blockers == ()
    assert approval.gate_statuses == {stage: "PASS" for stage in REQUIRED_STAGE_GATES}
    assert set(approval.artifacts) == {
        "hard_case_index",
        "outcome_sample",
        "feature_lineage_table",
        "source_release_mapping",
    }


def test_preflight_fails_closed_for_partial_stage_or_stale_evidence(tmp_path: Path) -> None:
    gate_path, decision_path, gate = _write_preflight_fixture(tmp_path)
    gates = gate["gates"]
    assert isinstance(gates, dict)
    stage_h = gates["H"]
    assert isinstance(stage_h, dict)
    stage_h["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
    gate_path.write_text(json.dumps(gate, sort_keys=True), encoding="utf-8")
    approval = preflight_training(tmp_path, gate_path, decision_path)
    assert not approval.allowed
    assert any("gate H: status" in blocker for blocker in approval.blockers)

    stage_h["status"] = "PASS"
    gate_path.write_text(json.dumps(gate, sort_keys=True), encoding="utf-8")
    evidence_path = tmp_path / str(stage_h["evidence"][0]["path"])
    evidence_path.write_text("tampered", encoding="utf-8")
    approval = preflight_training(tmp_path, gate_path, decision_path)
    assert not approval.allowed
    assert any("gate H evidence[0]: sha256 mismatch" in blocker for blocker in approval.blockers)


def test_preflight_rejects_partial_decision_coverage_even_when_a_h_say_pass(tmp_path: Path) -> None:
    gate_path, decision_path, gate = _write_preflight_fixture(tmp_path)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["coverage"] = {
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "blockers": ["missing_fault_decisions"],
    }
    decision_path.write_text(json.dumps(decision, sort_keys=True), encoding="utf-8")
    gate["decision_manifest"] = _descriptor(tmp_path, decision_path)
    gate_path.write_text(json.dumps(gate, sort_keys=True), encoding="utf-8")
    approval = preflight_training(tmp_path, gate_path, decision_path)
    assert not approval.allowed
    assert "decision manifest: high-flow/fault/tail coverage is not PASS" in approval.blockers


def _example(
    index: int,
    *,
    task_family: str | None = None,
    fingerprint: str | None = None,
    risk: int = 0,
) -> DecisionExample:
    features = np.zeros((3, len(FEATURE_NAMES)), dtype=np.float64)
    potential = FEATURE_NAMES.index("static_potential")
    queue = FEATURE_NAMES.index("target_queue_length")
    fault = FEATURE_NAMES.index("advertised_fault")
    features[:, potential] = [2.0, 0.1, 1.0]
    features[:, queue] = [float(index % 3), 0.0, 2.0]
    features[:, fault] = [0.0, float(risk), 0.0]
    day = index % 3
    source = str(100 + (index % 4))
    goal = str(200 + (index % 5))
    fault_name = "fault_local_active" if index % 3 == 0 else "no_fault"
    digest = fingerprint or hashlib.sha256(f"semantic-{index}".encode()).hexdigest()
    return DecisionExample(
        decision_id=f"decision-{index}",
        task_family=task_family or f"scenario|task-{index}",
        semantic_fingerprint=digest,
        source=source,
        goal=goal,
        fault=fault_name,
        day=day,
        event_time=day * 100_000.0 + index * 100.0,
        candidate_nodes=(10, 11, 12),
        candidate_features=features,
        target_index=1,
        risk_label=risk,
    )


def test_connected_groups_join_task_repeats_and_semantic_duplicates() -> None:
    duplicate = hashlib.sha256(b"same-semantic-decision").hexdigest()
    examples = (
        _example(0, task_family="bank|task-7"),
        _example(1, task_family="bank|task-7"),
        _example(2, task_family="bank|task-8", fingerprint=duplicate),
        _example(3, task_family="bank|task-9", fingerprint=duplicate),
    )
    groups = connected_group_ids(examples)
    assert groups[0] == groups[1]
    assert groups[2] == groups[3]
    assert groups[0] != groups[2]


def test_all_required_splits_have_zero_task_and_duplicate_overlap() -> None:
    dataset = prepare_dataset(tuple(_example(index, risk=index % 4 == 0) for index in range(30)))
    assert set(dataset.splits) == set(SPLIT_NAMES)
    rows = split_audit_rows(dataset)
    assert len(rows) == len(SPLIT_NAMES)
    assert all(row["status"] == "PASS" for row in rows)
    assert all(row["task_repeat_overlap"] == 0 for row in rows)
    assert all(row["semantic_duplicate_overlap"] == 0 for row in rows)


def test_split_builder_refuses_missing_fault_dimension() -> None:
    examples = []
    for index in range(12):
        value = _example(index)
        examples.append(
            DecisionExample(
                **{**value.__dict__, "fault": "no_fault"},
            )
        )
    with pytest.raises(V3TrainingError, match="fault_heldout"):
        prepare_dataset(examples)


def test_four_models_are_small_node_id_free_and_reproducible() -> None:
    dataset = prepare_dataset(tuple(_example(index, risk=index % 7 == 0) for index in range(30)))
    models_a, metrics_a = train_all_models(dataset, epochs=5, learning_rate=0.02, seed=23)
    models_b, metrics_b = train_all_models(dataset, epochs=5, learning_rate=0.02, seed=23)
    assert tuple(models_a) == MODEL_NAMES
    assert json.dumps(models_a, sort_keys=True) == json.dumps(models_b, sort_keys=True)
    assert json.dumps(metrics_a, sort_keys=True) == json.dumps(metrics_b, sort_keys=True)
    for name, model in models_a.items():
        assert model["absolute_node_id_features"] is False
        assert "current_node" not in model["feature_names"]
        assert "goal_node" not in model["feature_names"]
        assert set(metrics_a[name]) == set(SPLIT_NAMES)
        assert model["risk_head"] is not None if name == "v3_risk_head_plus_ranker" else model["risk_head"] is None
        source = dataset.examples[0]
        records = [
            {
                "next_node": node,
                "features": {
                    feature_name: float(source.candidate_features[candidate_index, feature_index])
                    for feature_index, feature_name in enumerate(FEATURE_NAMES)
                },
            }
            for candidate_index, node in enumerate(source.candidate_nodes)
        ]
        prediction = score_v3_candidates(model, records)
        assert prediction["selected_next"] in source.candidate_nodes
        assert len(prediction["scores"]) == len(source.candidate_nodes)
        assert ("risk_probability" in prediction) == (name == "v3_risk_head_plus_ranker")


def test_loader_uses_failed_rows_only_for_risk_and_rejects_unapproved_feature(tmp_path: Path) -> None:
    hard = tmp_path / "hard.csv"
    outcomes = tmp_path / "outcomes.jsonl"
    fieldnames = [
        "decision_id",
        "task_id",
        "scenario",
        "scenario_observed",
        "source_node",
        "goal_node",
        "fault_bucket",
        "original_arrival_time",
        "event_time",
        "candidate_records",
        "selected_next",
        "semantic_fingerprint",
    ]
    candidates = [
        {"next_node": 2, "features": {"travel_time": 2.0}},
        {"next_node": 3, "features": {"travel_time": 1.0}},
    ]
    rows = []
    for index in range(2):
        rows.append(
            {
                "decision_id": f"d-{index}",
                "task_id": f"t-{index}",
                "scenario": "paper",
                "scenario_observed": "paper",
                "source_node": 1,
                "goal_node": 9,
                "fault_bucket": "no_fault",
                "original_arrival_time": index * 86_400,
                "event_time": index * 86_400 + 10,
                "candidate_records": json.dumps(candidates),
                "selected_next": 3,
                "semantic_fingerprint": hashlib.sha256(f"d-{index}".encode()).hexdigest(),
            }
        )
    with hard.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    outcomes.write_text(
        '\n'.join(
            (
                json.dumps({"decision_id": "d-0", "reached_goal": True}),
                json.dumps({"decision_id": "d-1", "reached_goal": False}),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_training_examples(hard, outcomes)
    assert loaded[0].target_index == 1
    assert loaded[0].risk_label == 0
    assert loaded[1].target_index is None
    assert loaded[1].risk_label == 1

    rows[0]["candidate_records"] = json.dumps(
        [
            {"next_node": 2, "features": {"future_route_cost": 1.0}},
            {"next_node": 3, "features": {"travel_time": 1.0}},
        ]
    )
    with hard.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(V3TrainingError, match="unapproved candidate features"):
        load_training_examples(hard, outcomes)
