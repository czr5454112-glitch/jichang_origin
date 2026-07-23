from __future__ import annotations

from argparse import Namespace
import hashlib
import json
from pathlib import Path

from scripts.train.g4irsf12_v3_training import (
    ALLOWED_FEATURES,
    BLOCKED,
    DEFAULT_CLOSED_LOOP_REPORT,
    DEFAULT_DATASET_MANIFEST,
    DEFAULT_FEATURE_ABLATION,
    DEFAULT_GATE_MANIFEST,
    DEFAULT_MODEL_AB,
    DEFAULT_PROTOCOL,
    DEFAULT_SCHEMA,
    DEFAULT_SOURCE_MANIFEST,
    DEFAULT_STATUS,
    DEFAULT_TRAINING_REPORT,
    EXACT_BYTES_HASH,
    FEATURE_LINEAGE_SOURCES,
    GATE_MANIFEST_SCHEMA,
    HARD_NEGATIVE_CATEGORIES,
    PASS,
    REQUIRED_GATES,
    SPLIT_NAMES,
    SPLIT_SEEDS,
    Example,
    PreparedDataset,
    _forbidden_paths,
    build_splits,
    evaluate_ranker,
    fit_linear_ranker,
    protocol_manifest,
    run,
    validate_gate_manifest,
)


def _example(index: int) -> Example:
    group = index // 2
    hard = (
        (HARD_NEGATIVE_CATEGORIES[index % len(HARD_NEGATIVE_CATEGORIES)],)
        if index % 3
        else ()
    )
    # Every component is learnable: candidate 20 is the selected action and
    # has a larger first feature.  Identity/dimension values are deliberately
    # varied enough to exercise every held-out splitter.
    return Example(
        decision_id=f"decision-{index}",
        task_id=f"task-{index}",
        bag_family=f"bag-{group}",
        semantic_fingerprint=f"fingerprint-{group}",
        event_time=float(group * 901),
        time_block=str(group),
        source=str(group % 5),
        goal=str(47 + group % 4),
        junction=str(10 + group % 8),
        congestion=("empty", "light", "congested")[group % 3],
        fault=("no_fault", "active_fault")[group % 2],
        motif=("linear", "merge", "split", "merge_split")[group % 4],
        candidate_nodes=(10, 20),
        candidate_features=((0.0, 1.0), (10.0, 1.0)),
        candidate_allowed=(True, True),
        selected_index=1,
        rank_eligible=True,
        risk_label=int(bool(hard)),
        hard_categories=hard,
        sample_weight=1.0 if not hard else 1.5,
    )


def _dataset(count: int = 240) -> PreparedDataset:
    examples = tuple(_example(index) for index in range(count))
    digest = hashlib.sha256(
        json.dumps([example.decision_id for example in examples]).encode()
    ).hexdigest()
    return PreparedDataset(
        feature_names=("static_potential", "travel_time"),
        examples=examples,
        dataset_sha256=digest,
        trace_sha256="a" * 64,
        outcome_sha256="b" * 64,
        lineage_sha256="c" * 64,
    )


def test_protocol_encodes_phase_i_authority_and_claim_boundaries() -> None:
    protocol = protocol_manifest()

    assert protocol["required_pretraining_gates"] == list(REQUIRED_GATES)
    assert protocol["split_contract"]["seeds"] == list(SPLIT_SEEDS)
    assert protocol["split_contract"]["splits"] == list(SPLIT_NAMES)
    assert protocol["feature_contract"]["allowed"] == list(ALLOWED_FEATURES)
    assert set(protocol["feature_contract"]["lineage_sources"]) == set(ALLOWED_FEATURES)
    assert set(FEATURE_LINEAGE_SOURCES) == set(ALLOWED_FEATURES)
    assert protocol["feature_contract"]["absolute_node_id_model_inputs_allowed"] is False
    assert protocol["label_contract"]["teacher_route_suffix_allowed"] is False
    assert protocol["publication_contract"]["candidate_runtime_eligible"] is False
    assert protocol["publication_contract"]["active_pointer_written_by_this_tool"] is False
    assert protocol["publication_contract"]["G4J_status"] == "CLOSED"
    assert {"PPO", "MAPPO", "Transformer"}.issubset(protocol["forbidden_models"])


def test_recursive_leakage_audit_rejects_nested_future_and_outcome_fields() -> None:
    violations = _forbidden_paths(
        {
            "candidate_records": [
                {"features": {"travel_time": 1.0, "future_route_suffix": [2, 3]}}
            ],
            "metadata": {"nested": {"post_hoc_success": True}},
            "outcome": {"reached_goal": True},
        }
    )

    assert "candidate_records[0].features.future_route_suffix" in violations
    assert "metadata.nested.post_hoc_success" in violations
    assert "outcome" in violations


def test_gate_manifest_requires_exact_hash_bound_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"status":"PASS"}\n', encoding="utf-8")
    evidence_descriptor = {
        "path": "evidence.json",
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "hash_semantics": EXACT_BYTES_HASH,
    }
    gate = {
        "schema": GATE_MANIFEST_SCHEMA,
        "overall_status": PASS,
        "gates": {
            name: {"status": PASS, "blockers": [], "evidence": [evidence_descriptor]}
            for name in REQUIRED_GATES
        },
    }
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")

    statuses, blockers = validate_gate_manifest(tmp_path, gate_path)
    assert not blockers
    assert set(statuses.values()) == {PASS}

    evidence.write_text('{"status":"CHANGED"}\n', encoding="utf-8")
    _, tampered = validate_gate_manifest(tmp_path, gate_path)
    assert any("SHA-256 mismatch" in blocker for blocker in tampered)


def test_multi_seed_splits_keep_bags_and_semantic_repeats_together() -> None:
    dataset = _dataset()

    splits, audits = build_splits(dataset)

    assert len(splits) == len(SPLIT_NAMES) * len(SPLIT_SEEDS)
    assert all(row["status"] == PASS for row in audits)
    assert all(row["bag_family_overlap"] == 0 for row in audits)
    assert all(row["semantic_fingerprint_overlap"] == 0 for row in audits)
    # Deterministic reconstruction must be byte-for-byte equivalent at the
    # assignment level, not merely have the same counts.
    repeated, repeated_audits = build_splits(dataset)
    assert repeated == splits
    assert repeated_audits == audits


def test_linear_ranker_trains_only_on_observed_successful_action_pairs() -> None:
    dataset = _dataset(80)
    train = tuple(range(60))
    test = tuple(range(60, 80))

    model = fit_linear_ranker(dataset, train, seed=11, epochs=80, learning_rate=0.04)
    metrics = evaluate_ranker(dataset, model, test)

    assert metrics["candidate_recall"] == 1.0
    assert metrics["top1"] == 1.0
    assert metrics["pairwise_accuracy"] == 1.0
    assert metrics["high_confidence_wrong_rate"] == 0.0
    assert model["score_semantics"] == "higher_is_preferred"


def test_default_preparation_fails_closed_and_writes_no_model(tmp_path: Path) -> None:
    args = Namespace(
        root=tmp_path,
        gate_manifest=DEFAULT_GATE_MANIFEST,
        source_manifest=DEFAULT_SOURCE_MANIFEST,
        authorize_training=False,
        epochs=10,
        learning_rate=0.04,
    )

    code, status = run(args)

    assert code == 2
    assert status["status"] == BLOCKED
    assert status["trained"] is False
    assert status["runtime_eligible"] is False
    assert status["G4J_status"] == "CLOSED"
    assert status["candidate_model"] == {}
    assert any("map is missing" in blocker for blocker in status["blockers"])
    assert any("gate manifest is missing" in blocker for blocker in status["blockers"])
    assert any("source manifest is missing" in blocker for blocker in status["blockers"])
    for relative in (
        DEFAULT_PROTOCOL,
        DEFAULT_SCHEMA,
        DEFAULT_DATASET_MANIFEST,
        DEFAULT_STATUS,
        DEFAULT_TRAINING_REPORT,
        DEFAULT_CLOSED_LOOP_REPORT,
        DEFAULT_MODEL_AB,
        DEFAULT_FEATURE_ABLATION,
    ):
        assert (tmp_path / relative).is_file()
    model_dir = tmp_path / "artifacts" / "models"
    assert not model_dir.exists() or not list(model_dir.glob("g4irsf12_v3_*.json"))
