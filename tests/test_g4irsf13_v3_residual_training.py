from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.train.g4irsf13_v3_residual_training import (
    CANDIDATE_BUNDLE_PATH,
    CLOSED_LOOP_TABLE_PATH,
    DECISIONS_PATH,
    FEATURE_NAMES,
    GATE_SCHEMA,
    LABELS_PATH,
    LEVEL_A_FORMULA_ID,
    MODEL_DIR,
    MODEL_IDS,
    MODEL_SCHEMA,
    PRETRAINING_GATE_PATH,
    RESIDUAL_CLIP,
    SOURCE_MANIFEST_PATH,
    SOURCE_SCHEMA,
    SPLIT_PATH,
    TRACE_SCHEMA_PATH,
    Example,
    _canonical_bytes,
    _fit_linear,
    _level_a_projection,
    _load_json,
    _load_jsonl,
    _model_decision,
    _model_filename,
    _raw_residual,
    _risk_features,
    _risk_probability,
    _self_hash,
    _verify_no_feature_leakage,
    load_examples,
    load_graph,
    sha256_file,
    validate_committed,
)


ROOT = Path(__file__).resolve().parents[1]


def test_source_manifest_binds_real_candidate_and_action_rows() -> None:
    source = _load_json(ROOT / SOURCE_MANIFEST_PATH)
    decisions = _load_jsonl(ROOT / DECISIONS_PATH)
    labels = {
        str(row["decision_id"]): row
        for row in _load_jsonl(ROOT / LABELS_PATH)
    }
    graph = load_graph(ROOT)

    assert source["schema"] == SOURCE_SCHEMA
    assert source["status"] == "PASS"
    assert source["manifest_sha256"] == _self_hash(source, "manifest_sha256")
    assert len(decisions) == source["validation"]["decision_count"]
    assert source["validation"]["candidate_completeness"] == 1.0
    assert source["validation"]["selected_action_coverage"] == 1.0
    assert source["validation"]["hard_decision_count"] > 0
    assert source["validation"]["easy_decision_count"] > 0
    assert source["validation"]["level_a_corrective_label_count"] > 0
    assert (
        source["generation"]["f2_decision_trace_count"] == 340_810
    )
    assert len(source["generation"]["f2_archive_canonical_json_sha256"]) == 64

    for row in decisions:
        candidates = tuple(int(value) for value in row["candidate_next_nodes"])
        assert candidates == graph.outgoing[int(row["junction"])]
        assert row["selected_next"] in candidates
        assert [record["next_node"] for record in row["candidate_records"]] == list(
            candidates
        )
        assert labels[str(row["decision_id"])]["preferred_next"] in candidates


def test_group_split_keeps_every_raw_bag_in_one_partition() -> None:
    split = _load_json(ROOT / SPLIT_PATH)
    decisions = _load_jsonl(ROOT / DECISIONS_PATH)
    task_partitions: dict[int, set[str]] = {}
    for row in decisions:
        partition = split["assignments"][str(row["decision_id"])]
        task_partitions.setdefault(int(row["task_id"]), set()).add(partition)

    assert split["status"] == "PASS"
    assert split["manifest_sha256"] == _self_hash(split, "manifest_sha256")
    assert split["task_overlap_count"] == 0
    assert all(len(partitions) == 1 for partitions in task_partitions.values())
    assert set(split["counts"]) == {
        "train",
        "validation",
        "test",
        "audit_test",
    }
    assert split["counts"]["audit_test"] == 384
    assert min(split["counts"].values()) > 0


def test_label_provenance_and_future_dependency_never_enter_features() -> None:
    schema = _load_json(ROOT / TRACE_SCHEMA_PATH)
    decisions = _load_jsonl(ROOT / DECISIONS_PATH)
    labels = _load_jsonl(ROOT / LABELS_PATH)

    _verify_no_feature_leakage(decisions)
    assert schema["runtime_feature_names"] == list(FEATURE_NAMES)
    assert schema["future_route_model_input_allowed"] is False
    assert schema["main_model_absolute_node_id_allowed"] is False
    assert {
        "label_source",
        "confidence",
        "future_coordination_dependency",
    }.issubset(schema["label_metadata_only_fields"])
    for row in decisions:
        for candidate in row["candidate_records"]:
            feature_keys = set(candidate["features"])
            assert feature_keys == set(FEATURE_NAMES)
            assert "label_source" not in feature_keys
            assert "confidence" not in feature_keys
            assert not any("future" in name for name in feature_keys)
    assert all(row["weak_teacher_used_as_rank_target"] is False for row in labels)
    assert all(
        row["level_b_full_counterfactual_status"]
        == "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
        for row in labels
    )


def test_level_a_formula_is_same_state_deterministic_and_hash_stable() -> None:
    decisions = _load_jsonl(ROOT / DECISIONS_PATH)
    labels = {
        str(row["decision_id"]): row
        for row in _load_jsonl(ROOT / LABELS_PATH)
    }
    corrective = next(
        row
        for row in decisions
        if labels[str(row["decision_id"])]["corrective_label_authorised"]
    )
    first = _level_a_projection(corrective)
    second = _level_a_projection(json.loads(json.dumps(corrective)))

    assert first["formula_id"] == LEVEL_A_FORMULA_ID
    assert first["rank_target_authorised"] is True
    assert first["full_state_clone_used"] is False
    assert first["future_route_used"] is False
    assert _canonical_bytes(first) == _canonical_bytes(second)
    assert _canonical_bytes(first) == _canonical_bytes(
        labels[str(corrective["decision_id"])]["level_a_projection"]
    )
    assert first["preferred_next"] in corrective["candidate_next_nodes"]
    assert first["best_margin_seconds"] > 0.0


def test_pretraining_gate_fails_closed_beyond_level_a() -> None:
    gate = _load_json(ROOT / PRETRAINING_GATE_PATH)

    assert gate["schema"] == GATE_SCHEMA
    assert gate["overall_status"] == "PASS"
    assert gate["manifest_sha256"] == _self_hash(gate, "manifest_sha256")
    assert {row["status"] for row in gate["gates"].values()} == {"PASS"}
    assert gate["label_authority"]["level_a_local_one_step_projection"] == "PASS"
    assert gate["label_authority"]["level_a_corrective_support"] > 0
    assert (
        gate["label_authority"]["level_b_matched_full_state_counterfactual"]
        == "FAIL"
    )
    assert (
        gate["label_authority"]["level_c_v2_weak_teacher_as_causal_target"]
        == "FAIL"
    )
    assert gate["runtime_activation_allowed"] is False


def test_v0_through_v5_are_clipped_hash_bound_and_offline_only() -> None:
    for model_id in MODEL_IDS:
        path = ROOT / MODEL_DIR / _model_filename(model_id)
        payload = _load_json(path)
        assert payload["schema"] == MODEL_SCHEMA
        assert payload["model_id"] == model_id
        assert payload["model_sha256"] == _self_hash(payload, "model_sha256")
        assert payload["residual_clip"] == [-RESIDUAL_CLIP, RESIDUAL_CLIP]
        assert payload["runtime_eligible"] is False
        assert payload["closed_loop_status"] == "NOT_RUN"
        assert not any(
            "node_id" in name for name in payload["parameters"]["feature_names"]
        )


def test_v5_inference_vectors_reproduce_residual_risk_and_fallback() -> None:
    payload = _load_json(
        ROOT / MODEL_DIR / _model_filename(MODEL_IDS[-1])
    )
    model = dict(payload["parameters"])
    model["risk_head"] = payload["risk_head"]
    vectors = payload["inference_test_vectors"]

    assert len(vectors) >= 3
    base_id = payload["parameters"]["base_model_id"]
    base = _load_json(ROOT / MODEL_DIR / _model_filename(base_id))
    assert payload["parameters"]["base_parameters_sha256"] == hashlib.sha256(
        _canonical_bytes(base["parameters"])
    ).hexdigest()
    stripped = {
        key: value
        for key, value in payload["parameters"].items()
        if key not in {"base_model_id", "base_parameters_sha256", "risk_head"}
    }
    assert _canonical_bytes(stripped) == _canonical_bytes(base["parameters"])
    assert payload["deterministic_inference_contract"]["residual_clip"] == [
        -RESIDUAL_CLIP,
        RESIDUAL_CLIP,
    ]
    for vector in vectors:
        inputs = vector["input"]
        expected = vector["expected"]
        example = Example(
            decision={"candidate_records": []},
            label={},
            features=np.asarray(inputs["candidate_feature_vectors"], dtype=np.float64),
            frozen_costs=np.asarray(inputs["frozen_g4e_costs"], dtype=np.float64),
            selected_index=0,
            f2_selected_index=0,
        )
        residual = _raw_residual(model, example)
        risk = _risk_features(example, residual)
        probability = _risk_probability(payload["risk_head"], risk)

        assert np.all(np.abs(residual) <= RESIDUAL_CLIP + 1e-12)
        assert np.allclose(
            residual, expected["clipped_raw_residuals"], rtol=0.0, atol=1e-12
        )
        assert np.allclose(
            risk, expected["risk_feature_vector"], rtol=0.0, atol=1e-12
        )
        assert abs(probability - expected["risk_probability"]) <= 1e-12

    # Force a high-uncertainty decision and verify that fallback returns the
    # exact frozen argmin, independent of the learned residual.
    first = vectors[0]["input"]
    example = Example(
        decision={"candidate_records": []},
        label={},
        features=np.asarray(first["candidate_feature_vectors"], dtype=np.float64),
        frozen_costs=np.asarray(first["frozen_g4e_costs"], dtype=np.float64),
        selected_index=0,
        f2_selected_index=0,
    )
    forced = dict(model)
    forced_head = dict(payload["risk_head"])
    forced_head["fallback_threshold"] = 0.0
    forced["risk_head"] = forced_head
    choice, costs, _, fallback, _ = _model_decision(forced, example)
    assert fallback is True
    assert np.array_equal(costs, example.frozen_costs)
    assert choice == int(np.argmin(example.frozen_costs))


def test_small_real_subset_training_regenerates_bit_for_bit() -> None:
    examples, assignments = load_examples(ROOT)
    train = [
        index
        for index, example in enumerate(examples)
        if assignments[str(example.decision["decision_id"])] == "train"
        and len(example.frozen_costs) > 1
    ][:64]
    assert len(train) == 64
    first = _fit_linear(
        examples,
        train,
        feature_indices=tuple(range(len(FEATURE_NAMES))),
        objective="pairwise",
        epochs=6,
        learning_rate=0.05,
    )
    second = _fit_linear(
        examples,
        train,
        feature_indices=tuple(range(len(FEATURE_NAMES))),
        objective="pairwise",
        epochs=6,
        learning_rate=0.05,
    )
    assert _canonical_bytes(first) == _canonical_bytes(second)


def test_candidate_bundle_and_closed_loop_claim_boundary() -> None:
    bundle = _load_json(ROOT / CANDIDATE_BUNDLE_PATH)
    assert bundle["bundle_sha256"] == _self_hash(bundle, "bundle_sha256")
    assert set(bundle["model_artifacts"]) == set(MODEL_IDS)
    for descriptor in bundle["model_artifacts"].values():
        assert sha256_file(ROOT / descriptor["path"]) == descriptor["sha256"]
    assert bundle["runtime_eligible"] is False
    assert bundle["closed_loop_status"] == "NOT_RUN"
    assert bundle["strict_win_vs_f2"] == "NOT_RUN"
    assert bundle["strict_win_vs_v2_safe"] == "NOT_RUN"
    v5 = _load_json(ROOT / MODEL_DIR / _model_filename(MODEL_IDS[-1]))
    assert (
        v5["parameters"]["base_model_id"]
        == bundle["selected_offline_candidate"]
    )
    assert bundle["hyperparameter_selection"]["path"].endswith(
        "g4irsf13_v3_hyperparameter_selection.csv"
    )
    runtime = bundle["runtime_integration_contract"]
    assert runtime["default_s1_unchanged"] is True
    assert runtime["required_experiment_flag"].endswith("=true")
    assert runtime["test_vector_absolute_tolerance"] == 1e-12

    with (ROOT / CLOSED_LOOP_TABLE_PATH).open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 25
    assert {row["execution_status"] for row in rows} == {"NOT_RUN"}
    assert not any(row["original_entry_mean_minutes"] for row in rows)


def test_committed_stage_f_artifacts_validate_together() -> None:
    result = validate_committed(ROOT)

    assert result["status"] == "PASS"
    assert result["decision_count"] > 3_000
    assert result["candidate_count"] > result["decision_count"]
    assert result["hard_count"] > 0
    assert result["easy_count"] > 0
    assert result["runtime_eligible"] is False
    assert result["closed_loop_status"] == "NOT_RUN"
