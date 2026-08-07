from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from czr005 import cpp_backend
from czr005.g4irsf17 import (
    CANONICAL_OBSERVATION_FEATURES,
    CANDIDATE_FEATURES,
    CONTEXT_FEATURES,
    PAIRWISE_FEATURES,
    PhaseDTrainingConfig,
    deterministic_group_split,
    train_phase_d,
    write_phase_d_artifacts,
)
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


ROOT = Path(__file__).resolve().parents[1]


def _observation(*, alternative: bool, beneficial: bool, index: int) -> dict[str, float]:
    values = {name: 0.0 for name in CANONICAL_OBSERVATION_FEATURES}
    values.update(
        {
            "candidate_local_rank": float(alternative),
            "candidate_deadline_slack_seconds": (
                -20.0 if alternative and beneficial else 220.0 if alternative else 100.0
            ),
            "candidate_wait_age_seconds": 45.0 if alternative and beneficial else 5.0,
            "candidate_leg_priority": float(index % 2) if alternative else 0.0,
            "candidate_repair_priority": float(alternative and beneficial),
            "deadline_slack_delta_to_baseline_seconds": (
                -120.0 if alternative and beneficial else 120.0 if alternative else 0.0
            ),
            "wait_age_delta_to_baseline_seconds": (
                40.0 if alternative and beneficial else 0.0
            ),
            "leg_priority_delta_to_baseline": (
                float(index % 2) if alternative else 0.0
            ),
            "urgency_delta_to_granted_seconds": (
                -120.0 if alternative and beneficial else 120.0 if alternative else 0.0
            ),
            "wait_delta_to_granted_seconds": (
                40.0 if alternative and beneficial else 0.0
            ),
            "source_queue_length": float(3 + index % 3),
            "source_queue_capacity": 10.0,
            "source_queue_utilization": float(3 + index % 3) / 10.0,
            "source_queue_generation_delta": float(index % 5),
            "release_count_10s": float(index % 4),
            "release_count_30s": float(index % 7),
            "release_count_60s": float(index % 9),
            "admission_count_10s": float(index % 3),
            "admission_count_30s": float(index % 6),
            "admission_count_60s": float(index % 8),
            "queue_slope_10s": float((index % 3) - 1),
            "queue_slope_30s": float((index % 5) - 2),
            "queue_slope_60s": float((index % 7) - 3),
            "first_edge_credit_slack_seconds": float(10 + index % 5),
            "target_queue_length": float(2 + index % 4),
            "target_queue_capacity": 10.0,
            "target_queue_utilization": float(2 + index % 4) / 10.0,
            "target_scheduled_incoming": float(index % 4),
            "estimated_service_rate_60s": float(4 + index % 3),
            "drain_slope_60s": float((index % 3) - 1),
            "service_weighted_pressure": float(5 + index % 5),
            "one_hop_ttl_pressure": float(4 + index % 5),
            "two_hop_ttl_pressure": float(3 + index % 5),
            "merge_pending_count": float(index % 4),
            "merge_oldest_request_age_seconds": float(index % 20),
            "merge_token_generation_delta": float(index % 5),
            "time_to_next_service_opportunity_seconds": float(5 + index % 10),
            "recent_incoming_grants_60s": float(index % 8),
            "incoming_grant_imbalance_60s": float((index % 5) - 2),
        }
    )
    return values


def _rows(count: int = 48) -> list[dict[str, object]]:
    groups = [f"task-{index:03d}" for index in range(count)]
    assignments = deterministic_group_split(groups, seed=17)
    within_split: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    for index, (group, split) in enumerate(zip(groups, assignments, strict=True)):
        position = within_split.get(split, 0)
        within_split[split] = position + 1
        beneficial = position % 2 == 0
        baseline = _observation(alternative=False, beneficial=beneficial, index=index)
        alternative = _observation(alternative=True, beneficial=beneficial, index=index)
        # Context is a source-front value and must be identical for both candidates.
        for name in CONTEXT_FEATURES:
            baseline[name] = alternative[name]
        rows.append(
            {
                "task_group": group,
                "source_group": f"source-{index % 6}",
                "event_time": float(index * 3_600),
                "time_bucket": f"release-{index % 4}",
                "leg": f"leg-{index % 2}",
                # Exact native telemetry shape: K candidate-only vectors plus
                # one shared context vector and explicit pair indices.
                "candidate_features": [
                    [baseline[name] for name in CANDIDATE_FEATURES],
                    [alternative[name] for name in CANDIDATE_FEATURES],
                ],
                "context_features": [alternative[name] for name in CONTEXT_FEATURES],
                "baseline_candidate_index": 0,
                "proposed_candidate_index": 1,
                "system_utility": 8.0 if beneficial else -8.0,
                "supervisor_authorized": True,
            }
        )
    return rows


def _fast_config() -> PhaseDTrainingConfig:
    return PhaseDTrainingConfig(
        ensemble_size=3,
        pairwise_epochs=60,
        mlp_epochs=60,
        calibrator_epochs=100,
        minimum_beneficial_train=1,
        minimum_beneficial_calibration=1,
        minimum_beneficial_validation=1,
        minimum_harmful_train=1,
        minimum_harmful_calibration=1,
        minimum_harmful_validation=1,
        minimum_beneficial_sources=1,
        minimum_beneficial_time_buckets=1,
        minimum_beneficial_legs=1,
        minimum_validation_activations=0,
        minimum_beneficial_precision=0.0,
        minimum_harmful_recall=0.0,
        maximum_harmful_activation_rate=1.0,
        maximum_calibration_ece=1.0,
        benefit_probability_lcb_min=0.0,
        harm_probability_ucb_max=1.0,
    )


def _h_bag_rows() -> list[dict[str, object]]:
    rows = _rows()
    for row in rows:
        utility = float(row["system_utility"])
        row.update(
            {
                "horizon": "H_bag",
                "utility_scope": "DIRECT_ONLY_H_BAG",
                "eligible_causal_effect": True,
                "hard_gate_pass": True,
                "action_changed": True,
                "direct_bag_count": 2,
                "direct_bag_tth_sum_delta_seconds": -utility,
                "deadline_miss_delta": 0,
            }
        )
    return rows


def _h_system_rows() -> list[dict[str, object]]:
    rows = _rows()
    for row in rows:
        row.update(
            {
                "horizon": "H_system",
                "utility_scope": "SYSTEM_REALIZED_AFFECTED",
                "eligible_causal_effect": True,
                "hard_gate_pass": True,
                "action_changed": True,
                "other_bag_count": 3,
                "other_bag_sum_delta_seconds": 0.0,
                "other_bag_cvar95_harm_seconds": 0.0,
            }
        )
    return rows


def test_missing_feature_rows_is_an_explicit_no_go(tmp_path: Path) -> None:
    result = train_phase_d(
        [
            {
                "descriptor_id": "task-a",
                "source": "source-a",
                "event_ordinal": 0,
                "system_utility": 5.0,
                "utility_scope": "SYSTEM_REALIZED_AFFECTED",
                "eligible_causal_effect": True,
                "hard_gate_pass": True,
                "action_changed": True,
            }
        ]
    )

    assert result.status == "NO_GO_FEATURE_EFFECT_ROWS_ABSENT"
    assert result.authorized is False
    assert result.model_artifacts == {}
    assert result.input_summary["rejection_reasons"] == {
        "FEATURE_ROWS_MISSING_MATCHED_CANDIDATE_PAIR": 1
    }
    assert result.gate_artifact["final_audit"]["consumed"] is False

    paths = write_phase_d_artifacts(result, tmp_path)
    assert paths["gate"].is_file()
    assert paths["policy"].is_file()
    assert paths["report"].is_file()
    assert "pairwise_model" not in paths
    assert json.loads(paths["gate"].read_text(encoding="utf-8"))["authorized"] is False


def test_h_bag_direct_swap_cohort_trains_but_cannot_supply_system_authorization() -> None:
    result = train_phase_d(_h_bag_rows(), config=_fast_config())

    assert set(result.model_artifacts) == {"pairwise_linear", "tiny_mlp"}
    development_rows = sum(
        result.split_summary["by_selection_split"][split]["row_count"]
        for split in ("train", "calibration", "validation")
    )
    assert result.support["observed"]["h_bag_training_rows"] == development_rows
    assert result.support["observed"]["h_system_externality_rows"] == 0
    assert result.support["pass"] is True
    assert result.authorized is False
    assert result.gate_artifact["promotion_checks"]["h_system_externality_evidence"] is False
    assert "PROMOTION_H_SYSTEM_EXTERNALITY_EVIDENCE_FAILED" in result.reasons
    contract = result.gate_artifact["training_label_contract"]
    assert contract["BOUNDED_DIRECT_SWAP_COHORT"][
        "provides_full_system_externality_evidence"
    ] is False
    assert result.gate_artifact["runtime_closed_loop_authorized"] is False


def test_real_h_system_rows_satisfy_only_the_externality_evidence_gate() -> None:
    result = train_phase_d(_h_system_rows(), config=_fast_config())

    assert result.support["observed"]["h_system_externality_rows"] > 0
    assert result.gate_artifact["promotion_checks"]["h_system_externality_evidence"] is True
    assert result.gate_artifact["runtime_closed_loop_authorized"] is False


def test_training_uses_task_group_hard_split_and_keeps_final_audit_sealed() -> None:
    rows = _rows()
    assignments = deterministic_group_split(
        [row["task_group"] for row in rows], seed=17
    )
    # A deliberately nonnumeric sentinel proves Phase D never opens a sealed
    # final-audit outcome.  The later audit command owns that read.
    for row, assignment in zip(rows, assignments, strict=True):
        if assignment == "final_audit":
            row["system_utility"] = "SEALED_DO_NOT_PARSE"
    result = train_phase_d(rows, config=_fast_config())

    assert set(result.model_artifacts) == {"pairwise_linear", "tiny_mlp"}
    assert result.split_summary["task_group_overlap_count"] == 0
    assert result.split_summary["final_audit"]["row_count"] > 0
    assert result.split_summary["final_audit"]["consumed"] is False
    assert result.input_summary["final_audit_outcomes_parsed"] is False
    pairwise = result.model_artifacts["pairwise_linear"]
    assert pairwise["artifact_set_id"] == result.gate_artifact[
        "artifact_set_id"
    ]
    assert pairwise["artifact_set_id"].startswith(
        "g4irsf17-i1-seed17-rows"
    )
    counts = result.split_summary["by_selection_split"]
    assert counts["final_audit"]["beneficial_count"] is None
    assert counts["final_audit"]["harmful_count"] is None
    assert pairwise["training_row_count"] == counts["train"]["row_count"]
    assert pairwise["calibration_row_count"] == counts["calibration"]["row_count"]
    assert pairwise["validation_row_count"] == counts["validation"]["row_count"]
    assert pairwise["final_audit_consumed"] is False
    assert result.validation_evaluation["partition"] == "task_group.validation"
    assert set(result.validation_evaluation["families"]) == {
        "FIFO",
        "CURRENT_AGING_Q0",
        "LOCALIZED_THESIS_RULE",
        "PAIRWISE_LINEAR",
        "TINY_MLP",
        "SELECTIVE_GATE",
    }


def test_uncalibrated_export_keeps_one_artifact_set_identity(tmp_path: Path) -> None:
    rows = _rows()
    assignments = deterministic_group_split(
        [str(row["task_group"]) for row in rows], seed=17
    )
    for row, assignment in zip(rows, assignments, strict=True):
        if assignment == "calibration":
            # Force a one-class calibration partition while retaining valid
            # train/validation partitions and real trained model exports.
            row["system_utility"] = 8.0

    result = train_phase_d(rows, config=_fast_config())

    assert result.status == "NO_GO_CALIBRATION_CLASS_SUPPORT"
    pairwise = result.model_artifacts["pairwise_linear"]
    mlp = result.model_artifacts["tiny_mlp"]
    artifact_set_ids = {
        pairwise["artifact_set_id"],
        mlp["artifact_set_id"],
        result.policy_artifact["artifact_set_id"],
        result.gate_artifact["artifact_set_id"],
    }
    assert len(artifact_set_ids) == 1
    assert next(iter(artifact_set_ids)).startswith(
        "g4irsf17-i1-seed17-rows"
    )

    paths = write_phase_d_artifacts(result, tmp_path)
    persisted_ids = {
        json.loads(paths[name].read_text(encoding="utf-8"))["artifact_set_id"]
        for name in ("pairwise_model", "mlp_model", "policy", "gate")
    }
    assert persisted_ids == artifact_set_ids


def test_export_is_transparent_and_contains_no_identity_feature_or_raw_split_key(
    tmp_path: Path,
) -> None:
    rows = _rows()
    result = train_phase_d(
        rows,
        config=replace(_fast_config(), minimum_beneficial_train=10_000),
    )
    paths = write_phase_d_artifacts(result, tmp_path)

    pairwise = json.loads(paths["pairwise_model"].read_text(encoding="utf-8"))
    mlp = json.loads(paths["mlp_model"].read_text(encoding="utf-8"))
    assert pairwise["benefit_members"][0]["feature_names"] == list(PAIRWISE_FEATURES)
    assert mlp["model"]["feature_names"] == list(CANONICAL_OBSERVATION_FEATURES)
    assert pairwise["identity_features_used"] is False
    assert mlp["identity_features_used"] is False
    serialized_models = json.dumps({"pairwise": pairwise, "mlp": mlp})
    for row in rows:
        assert str(row["task_group"]) not in serialized_models
        assert str(row["source_group"]) not in serialized_models
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    assert gate["authorized"] is False
    assert gate["promotion_checks"]["support"] is False
    assert "PROMOTION_SUPPORT_FAILED" in gate["reason_codes"]
    assert gate["runtime_closed_loop_authorized"] is False
    assert gate["final_audit"]["consumed"] is False
    assert paths["policy_table"].read_text(encoding="utf-8").count("\n") >= 7
    assert paths["bucket_table"].read_text(encoding="utf-8").count("\n") > 1


def test_real_phase_d_exports_adapt_to_native_without_authorization_upgrade() -> None:
    result = train_phase_d(_rows(), config=_fast_config())
    pairwise = result.model_artifacts["pairwise_linear"]
    bundle = cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
        pairwise,
        result.gate_artifact,
        supervisor_authorized=True,
    )
    assert bundle["kind"] == "pairwise_ensemble_selective"
    assert bundle["artifact_set_id"] == pairwise["artifact_set_id"]
    assert bundle["pairwise_artifact"] == pairwise
    assert bundle["gate_artifact"] == result.gate_artifact
    assert bundle["authorized"] is result.gate_artifact["authorized"]
    assert bundle["runtime_closed_loop_authorized"] is False
    if not cpp_backend.is_available():
        return
    nodes, edges, heuristic = canonical_graph_records()
    native = cpp_backend.load_cpp_module()
    payload = native.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=[
            ("g17-export-a:direct", 1, 0.0, 1000.0, 3, 47, "typed-direct"),
            ("g17-export-b:storage_out", 2, 0.0, 10.0, 3, 47, "typed-storage"),
        ],
        fault_windows=[],
        queue_discipline="fifo",
        event_semantics="E1",
        minimum_service_seconds=0.25,
        local_queue_capacity=8,
        admission_mode="off",
        enable_source_admission=False,
        scenario="pytest_g4irsf17_real_training_export",
        g4irsf17_source_policy_mode="shadow",
        g4irsf17_source_policy_artifact=bundle,
        g4irsf17_source_policy_trace_limit=100,
    )
    assert payload["summary"]["g4irsf17_source_policy_kind"] == (
        "pairwise_ensemble_selective"
    )
    assert payload["summary"]["g4irsf17_source_policy_activation_count"] == 0
    assert payload["g4irsf17_source_policy_decisions"]


def test_cli_writes_a_scientific_no_go_instead_of_inventing_features(tmp_path: Path) -> None:
    input_path = tmp_path / "effects.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "task_group": "task-a",
                "source_group": "source-a",
                "event_time": 0,
                "system_utility": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/eval/train_g4irsf17_i1.py"),
            "--effects",
            str(input_path),
            "--output-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    printed = json.loads(completed.stdout)
    assert printed["status"] == "NO_GO_FEATURE_EFFECT_ROWS_ABSENT"
    gate_path = tmp_path / "artifacts/gates/g4irsf17_i1_selective_gate.json"
    assert json.loads(gate_path.read_text(encoding="utf-8"))["authorized"] is False
    report = (tmp_path / "outputs/reports/g4irsf17_i1_model_decision.md").read_text(
        encoding="utf-8"
    )
    assert "Final audit consumed: `false`" in report
