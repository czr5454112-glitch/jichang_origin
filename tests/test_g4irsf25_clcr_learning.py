from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf25_clcr_learning as clcr


def _features(pressure: float, *, alternative: bool) -> list[float]:
    values = [0.0] * clcr.FEATURE_COUNT
    if alternative:
        values[0] = -1.0
        values[1] = 2.0
        values[2] = 1.0
        values[3] = pressure
        values[4] = pressure * 0.5
        values[5] = pressure * 0.2
        values[6] = pressure * 0.1
        values[8] = -pressure * 0.05
        values[9] = pressure
        values[10] = pressure * 0.3
    values[12] = 20.0 + pressure
    values[13] = 300.0 - pressure
    values[14] = 8.0 + pressure * 0.4
    values[15] = 8.0 + pressure * 0.1
    values[16] = pressure * 0.3
    values[17] = 5.0
    values[18] = 2.0
    values[19] = 0.0
    values[20] = 4.0
    return values


def _group(index: int, *, pressure: float, branch: int = 1, timeout: bool = False) -> dict[str, object]:
    s4_edge = branch + 1
    alternative_edge = branch + 2
    rejoin = branch + 3
    s4_cost = 20.0 + pressure
    alternative_cost = 22.0 - pressure
    return {
        "schema": clcr.PAIR_SCHEMA,
        "checkpoint_id": f"cp-{index}",
        "checkpoint_time_seconds": float(index),
        "load_scale": 1.0 if index % 2 == 0 else 2.0,
        "branch_node": branch,
        "goal_node": 99,
        "leg": "source_to_target" if index % 2 == 0 else "target_to_sink",
        "task_class": "synthetic_contract_test",
        "s4_first_edge": s4_edge,
        "gate_metrics": {
            "target_queue_plus_incoming": pressure,
            "service_weighted_pressure": pressure * 0.8,
            "corridor_trend": pressure * 0.3,
        },
        "arms": [
            {
                "first_edge": s4_edge,
                "rejoin_node": rejoin,
                "corridor_nodes": [branch, s4_edge, rejoin],
                "support": 50,
                "static_duration_seconds": 5.0,
                "features": _features(pressure, alternative=False),
                "local_system_cost_seconds": s4_cost,
                "private_cost_seconds": 10.0,
                "safe": True,
                "timeout": False,
            },
            {
                "first_edge": alternative_edge,
                "rejoin_node": rejoin,
                "corridor_nodes": [branch, alternative_edge, rejoin],
                "support": 50,
                "static_duration_seconds": 7.0,
                "features": _features(pressure, alternative=True),
                "local_system_cost_seconds": 600.0 if timeout else alternative_cost,
                "private_cost_seconds": 600.0 if timeout else 11.0 + pressure * 0.1,
                "safe": True,
                "timeout": timeout,
            },
        ],
    }


def _dataset(count: int = 36) -> list[dict[str, object]]:
    # Repeating pressure phases preserve both actions and both loads in every
    # chronological fold without leaking a checkpoint across folds.
    pressures = (0.0, 1.0, 2.0, 5.0, 7.0, 9.0)
    return [
        _group(index, pressure=pressures[index % len(pressures)], branch=1 if index % 4 < 2 else 10)
        for index in range(count)
    ]


def test_fixed_feature_contract_matches_runtime_header_order() -> None:
    assert clcr.FEATURE_COUNT == 21
    assert clcr.FEATURE_NAMES[:3] == (
        "s4_score_delta",
        "travel_time_delta",
        "static_potential_delta",
    )
    assert clcr.FEATURE_NAMES[-4:] == (
        "recent_corridor_feedback_age_seconds",
        "recent_corridor_feedback_sample_log1p",
        "recent_corridor_timeout_rate",
        "arm_support_log1p",
    )


def test_normalization_retains_timeout_as_finite_high_cost() -> None:
    group = clcr.normalise_paired_rows([_group(0, pressure=9.0, timeout=True)])[0]

    alternative = group["arms"][1]
    assert alternative["timeout"] is True
    assert alternative["local_system_cost_seconds"] == 600.0
    assert alternative["private_cost_seconds"] == 600.0


def test_normalization_rejects_wrong_feature_dimension() -> None:
    group = _group(0, pressure=3.0)
    group["arms"][1]["features"] = [0.0] * 20  # type: ignore[index]

    with pytest.raises(clcr.CLCRLearningError, match="exactly 21"):
        clcr.normalise_paired_rows([group])


def test_grouped_chronological_split_keeps_equal_times_and_ids_together() -> None:
    rows = clcr.normalise_paired_rows(_dataset(12))
    rows[1]["checkpoint_time_seconds"] = rows[0]["checkpoint_time_seconds"]
    split = clcr.checkpoint_group_chronological_split(rows, train_fraction=0.5, validation_fraction=0.25)

    owners = {
        row["checkpoint_id"]: name
        for name, partition in split.items()
        for row in partition
    }
    assert len(owners) == len(rows)
    assert owners[rows[0]["checkpoint_id"]] == owners[rows[1]["checkpoint_id"]]
    assert max(row["checkpoint_time_seconds"] for row in split["train"]) < min(
        row["checkpoint_time_seconds"] for row in split["validation"]
    )
    assert max(row["checkpoint_time_seconds"] for row in split["validation"]) < min(
        row["checkpoint_time_seconds"] for row in split["test"]
    )


def test_same_dataset_produces_oracle_local_ceiling_and_opportunity_mass() -> None:
    rows = clcr.normalise_paired_rows(_dataset())

    ceilings = clcr.compute_action_ceilings(rows)

    full = ceilings["full_state"]
    assert full["branch_decisions"] == len(rows)
    assert full["useful_opportunities"] > 0
    assert full["opportunity_mass"] > 0.0
    assert full["stable_action_reversal_branches"] == [1, 10]
    assert set(full["by_load"]) == {"1.0", "2.0"}
    local = ceilings["local_observation"]
    assert 0.0 <= local["pairwise_ranking_ceiling"] <= 1.0
    assert 0.0 <= local["singleton_checkpoint_fraction"] <= 1.0


def test_t0_and_l1_use_small_validation_selection_and_export_runtime_schema() -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)

    t0, t0_selection = clcr.select_t0_threshold(
        split["train"], split["validation"], min_support=1, margin_seconds=0.1
    )
    l1, l1_selection = clcr.select_l1_ridge(
        split["train"], split["validation"], min_support=1, margin_seconds=0.1
    )

    assert 2 <= t0_selection["candidate_count"] <= 8
    assert t0_selection["candidate_count"] == 2 * t0_selection["threshold_candidate_count"]
    assert t0_selection["fairness_cap_candidates_seconds"] == [30.0, 60.0]
    assert t0_selection["selection_folds"] == ["train", "validation"]
    assert t0_selection["held_out_test_used_for_selection"] is False
    assert t0_selection["residual_refit_from_pairs"] is False
    assert l1_selection["candidate_count"] == 3
    assert t0["schema"] == clcr.ARTIFACT_SCHEMA
    assert t0["mode"] == "t0"
    assert t0["t0_exit_pressure"] == t0["t0_enter_pressure"]
    assert t0["private_cap_seconds"] in (30.0, 60.0)
    assert len(t0["arms"]) == 8
    assert l1["feature_names"] == list(clcr.FEATURE_NAMES)
    assert set(l1["normalization"]) == {"mean", "scale", "min", "max"}
    assert len(l1["normalization"]["mean"]) == clcr.FEATURE_COUNT
    assert len(l1["model"]["system_weights"]) == clcr.FEATURE_COUNT
    assert set(l1["model"]) == {"system_weights", "private_weights"}
    assert all(arm["support"] == 50 for arm in l1["arms"])
    assert all(arm["training_support"] > 0 for arm in l1["arms"])
    assert l1["normalization"]["min"][16] == -600.0
    assert l1["normalization"]["max"][19] == 1.0
    assert "model" not in t0
    encoded = json.dumps(l1)
    for forbidden in ("checkpoint_id", "checkpoint_time", "runtime_bag_id", "task_id", "segment_id", "decision_id"):
        assert forbidden not in encoded

    metrics = clcr.evaluate_artifact(split["test"], l1)
    assert metrics["pairwise_ranking_accuracy"] >= 0.8
    assert metrics["system_mae"] < 2.0
    assert metrics["safety_failure_count"] == 0
    assert set(metrics["calibration_by_branch"]) == {"1", "10"}


def test_t0_copies_every_g24_arm_residual_without_refitting_from_pairs() -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    source = clcr.read_g24_corridor_residuals()

    first = clcr.build_t0_artifact(
        rows[:12],
        metric="target_queue_plus_incoming",
        enter_pressure=5.0,
        exit_pressure=5.0,
        min_support=1,
        private_cap_seconds=30.0,
    )
    changed_labels = clcr.normalise_paired_rows(
        [_group(index, pressure=100.0 + index, timeout=True) for index in range(12)]
    )
    second = clcr.build_t0_artifact(
        changed_labels,
        metric="target_queue_plus_incoming",
        enter_pressure=5.0,
        exit_pressure=5.0,
        min_support=1,
        private_cap_seconds=60.0,
    )

    expected = {
        (row["branch_node"], row["first_edge"]): row["residual_seconds"]
        for row in source
    }
    expected_private = {
        (row["branch_node"], row["first_edge"]): row["dynamic_duration_seconds"]
        for row in source
    }
    first_residuals = {
        (arm["branch_node"], arm["first_edge"]): arm["t0_system_delta_seconds"]
        for arm in first["arms"]
    }
    second_residuals = {
        (arm["branch_node"], arm["first_edge"]): arm["t0_system_delta_seconds"]
        for arm in second["arms"]
    }
    assert len(expected) == 8
    assert first_residuals == pytest.approx(expected)
    assert second_residuals == pytest.approx(expected)
    first_private = {
        (arm["branch_node"], arm["first_edge"]): arm["t0_private_delta_seconds"]
        for arm in first["arms"]
    }
    second_private = {
        (arm["branch_node"], arm["first_edge"]): arm["t0_private_delta_seconds"]
        for arm in second["arms"]
    }
    assert first_private == pytest.approx(expected_private)
    assert second_private == pytest.approx(expected_private)
    assert first["training_metadata"]["residual_source"] == clcr.G24_CORRIDOR_SOURCE
    assert first["training_metadata"]["residual_contract"] == "FROZEN_G24_NO_PAIRED_REFIT"


def test_custom_g24_source_provenance_follows_selected_artifact(
    tmp_path: Path,
) -> None:
    document = json.loads(
        clcr.G24_DECISION_SUMMARY_PATH.read_text(encoding="utf-8")
    )
    document["reconvergent_corridor"]["corridors"][0]["residual_seconds"] += 1.25
    custom_source = tmp_path / "g24-custom.json"
    custom_source.write_text(json.dumps(document), encoding="utf-8")
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)

    artifact, selection = clcr.select_t0_threshold(
        split["train"],
        split["validation"],
        min_support=1,
        margin_seconds=0.1,
        g24_decision_summary_path=custom_source,
    )

    expected_source = (
        f"{clcr._portable_evidence_path(custom_source)}"
        "#reconvergent_corridor.corridors"
    )
    assert artifact["training_metadata"]["residual_source"] == expected_source
    assert selection["residual_source"] == expected_source
    expected_residual = document["reconvergent_corridor"]["corridors"][0][
        "residual_seconds"
    ]
    assert artifact["arms"][0]["t0_system_delta_seconds"] == pytest.approx(
        expected_residual
    )


def test_t0_selection_uses_validation_only_and_test_is_held_out(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)
    validation_ids = {row["checkpoint_id"] for row in split["validation"]}
    test_ids = {row["checkpoint_id"] for row in split["test"]}
    evaluated_ids: list[set[str]] = []
    original_evaluate = clcr.evaluate_artifact

    def recording_evaluate(groups: object, artifact: object) -> dict[str, object]:
        partition = list(groups)  # type: ignore[arg-type]
        evaluated_ids.append({str(row["checkpoint_id"]) for row in partition})
        return original_evaluate(partition, artifact)  # type: ignore[arg-type]

    monkeypatch.setattr(clcr, "evaluate_artifact", recording_evaluate)
    artifact, selection = clcr.select_t0_threshold(
        split["train"], split["validation"], min_support=1, margin_seconds=0.1
    )

    assert evaluated_ids
    assert all(ids == validation_ids for ids in evaluated_ids)
    assert all(not (ids & test_ids) for ids in evaluated_ids)
    assert selection["held_out_test_used_for_selection"] is False
    held_out_metrics = original_evaluate(split["test"], artifact)
    assert held_out_metrics["checkpoint_count"] == len(split["test"])


def test_l2_trigger_ceiling_excludes_chronological_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)
    captured: dict[str, object] = {}

    def capture_trigger(
        ceilings: object, _l1_metrics: object = None
    ) -> dict[str, object]:
        captured["ceilings"] = ceilings
        return {"triggered": False, "reasons": []}

    monkeypatch.setattr(clcr, "decide_l2_trigger", capture_trigger)
    result = clcr.train_evidence_ladder(rows, min_support=1, margin_seconds=0.1)

    trigger_ceilings = captured["ceilings"]
    assert trigger_ceilings == result["l2_trigger_ceilings"]
    assert trigger_ceilings["full_state"]["branch_decisions"] == (  # type: ignore[index]
        len(split["train"]) + len(split["validation"])
    )
    assert result["ceilings"]["full_state"]["branch_decisions"] == len(rows)
    assert result["l2_trigger"]["evidence_scope"] == "TRAIN_AND_VALIDATION_ONLY"
    assert result["l2_trigger"]["checkpoint_count"] == (
        len(split["train"]) + len(split["validation"])
    )


def test_main_uses_mandatory_t0_and_l1_filenames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "policies"
    metrics_csv = tmp_path / "tables" / "model_metrics.csv"
    threshold_report = tmp_path / "reports" / "threshold.md"
    contextual_report = tmp_path / "reports" / "contextual.md"
    custom_g24 = tmp_path / "custom-g24.json"
    custom_g24.write_text(
        clcr.G24_DECISION_SUMMARY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    output_dir.mkdir(parents=True)
    (output_dir / "g4irsf25_clcr_l2.json").write_text("stale-l2", encoding="utf-8")
    (output_dir / "g4irsf25_clcr_l3.json").write_text("stale-l3", encoding="utf-8")
    monkeypatch.setattr(clcr, "read_compact_pairs", lambda _path: [{"checkpoint_id": "fixture"}])
    metric = {
        "checkpoint_count": 3,
        "arm_sample_count": 6,
        "system_mae": 1.25,
        "private_mae": 0.75,
        "pairwise_ranking_accuracy": 0.8,
        "beneficial_precision": 0.9,
        "harmful_recall": 1.0,
        "expected_regret": 0.2,
        "mutation_count": 2,
        "mutation_decision_coverage": 2.0 / 3.0,
        "useful_opportunity_count": 2,
        "useful_opportunity_coverage": 0.5,
        "harmful_mutation_count": 0,
        "harmful_mutation_rate": 0.0,
        "safety_failure_count": 0,
    }
    monkeypatch.setattr(
        clcr,
        "train_evidence_ladder",
        lambda _groups, **_kwargs: {
            "artifacts": {
                "t0": {
                    "mode": "t0",
                    "t0_metric": "target_queue_plus_incoming",
                    "t0_enter_pressure": 5.0,
                    "t0_exit_pressure": 5.0,
                    "private_cap_seconds": 30.0,
                    "training_metadata": {
                        "residual_contract": "FROZEN_G24_NO_PAIRED_REFIT",
                        "residual_source": clcr.G24_CORRIDOR_SOURCE,
                    },
                },
                "l1": {"mode": "l1"},
            },
            "metrics": {
                "t0_validation": dict(metric),
                "t0_test": dict(metric),
                "l1_validation": dict(metric),
                "l1_test": dict(metric),
            },
            "ceilings": {
                "full_state": {
                    "useful_opportunities": 2,
                    "branch_decisions": 3,
                    "mean_possible_improvement_fraction": 0.1,
                    "stable_action_reversal_branches": [1, 10],
                },
                "local_observation": {
                    "pairwise_ranking_ceiling": 0.9,
                    "s4_action_accuracy": 0.5,
                    "mean_local_regret_ceiling": 0.1,
                },
                "opportunity_mass": 4.0,
            },
            "t0_selection": {
                "fairness_cap_candidates_seconds": [30.0, 60.0],
                "threshold_candidate_count": 4,
                "selection_folds": ["train", "validation"],
                "held_out_test_used_for_selection": False,
            },
            "l2_trigger": {"triggered": False, "reasons": []},
            "l3_trigger": {
                "triggered": False,
                "reasons": [],
                "residual_feedback_correlation": 0.0,
            },
        },
    )

    assert clcr.main(
        [
            "--input",
            str(tmp_path / "pairs.json"),
            "--output-dir",
            str(output_dir),
            "--model-metrics-csv",
            str(metrics_csv),
            "--threshold-report",
            str(threshold_report),
            "--contextual-report",
            str(contextual_report),
            "--g24-decision-summary",
            str(custom_g24),
        ]
    ) == 0
    assert (output_dir / "g4irsf25_t0_threshold.json").is_file()
    assert (output_dir / "g4irsf25_clcr_l1.json").is_file()
    assert not (output_dir / "g4irsf25_clcr_t0.json").exists()
    assert not (output_dir / "g4irsf25_clcr_l2.json").exists()
    assert not (output_dir / "g4irsf25_clcr_l3.json").exists()
    evidence = json.loads(
        (output_dir / "g4irsf25_clcr_learning_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    expected_input = clcr._portable_evidence_path(tmp_path / "pairs.json")
    assert evidence["provenance"]["paired_input_dataset"] == expected_input
    assert evidence["provenance"]["g24_corridor_source"] == (
        f"{clcr._portable_evidence_path(custom_g24)}"
        "#reconvergent_corridor.corridors"
    )
    assert metrics_csv.read_text(encoding="utf-8").count("\n") == 5
    assert "model,split,checkpoint_count" in metrics_csv.read_text(encoding="utf-8")
    assert "FROZEN_G24_NO_PAIRED_REFIT" in threshold_report.read_text(encoding="utf-8")
    assert "Single threshold: `5.000000`" in threshold_report.read_text(encoding="utf-8")
    contextual = contextual_report.read_text(encoding="utf-8")
    assert contextual.count("NOT_TRIGGERED") == 2
    assert "native policy selection is intentionally outside this report" in contextual
    assert expected_input in contextual
    assert expected_input in threshold_report.read_text(encoding="utf-8")


def test_failed_staging_preserves_every_published_learning_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "policies"
    metrics_csv = tmp_path / "tables" / "metrics.csv"
    threshold_report = tmp_path / "reports" / "threshold.md"
    contextual_report = tmp_path / "reports" / "contextual.md"
    targets = [
        output_dir / "g4irsf25_t0_threshold.json",
        output_dir / "g4irsf25_clcr_l1.json",
        output_dir / "g4irsf25_clcr_l2.json",
        output_dir / "g4irsf25_clcr_l3.json",
        output_dir / "g4irsf25_clcr_learning_evidence.json",
        metrics_csv,
        threshold_report,
        contextual_report,
    ]
    for index, target in enumerate(targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"old-{index}", encoding="utf-8")
    old_contents = {
        target: target.read_text(encoding="utf-8") for target in targets
    }

    monkeypatch.setattr(clcr, "read_compact_pairs", lambda _path: [{"checkpoint_id": "fixture"}])
    monkeypatch.setattr(
        clcr,
        "train_evidence_ladder",
        lambda _groups, **_kwargs: {
            "artifacts": {
                "t0": {"mode": "t0", "training_metadata": {}},
                "l1": {"mode": "l1"},
            },
            "metrics": {},
            "ceilings": {},
            "t0_selection": {},
            "l2_trigger": {"triggered": False, "reasons": []},
            "l3_trigger": {"triggered": False, "reasons": []},
        },
    )

    def fail_metrics(_path: Path, _metrics: object) -> None:
        raise OSError("injected staging failure")

    monkeypatch.setattr(clcr, "write_model_metrics_csv", fail_metrics)
    assert clcr.main(
        [
            "--input",
            str(tmp_path / "pairs.json"),
            "--output-dir",
            str(output_dir),
            "--model-metrics-csv",
            str(metrics_csv),
            "--threshold-report",
            str(threshold_report),
            "--contextual-report",
            str(contextual_report),
        ]
    ) == 2

    assert {
        target: target.read_text(encoding="utf-8") for target in targets
    } == old_contents
    assert not list(tmp_path.rglob("*.tmp"))


def test_failed_promotion_rolls_back_prior_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.csv"
    stale_optional = tmp_path / "stale-l2.json"
    first.write_text("old-first", encoding="utf-8")
    second.write_text("old-second", encoding="utf-8")
    stale_optional.write_text("old-optional", encoding="utf-8")
    real_replace = clcr.os.replace
    call_count = 0

    def fail_second_replace(source: object, target: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("injected promotion failure")
        real_replace(source, target)

    monkeypatch.setattr(clcr.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="injected promotion failure"):
        clcr._stage_and_publish_outputs(
            [
                (first, lambda path: path.write_text("new-first", encoding="utf-8")),
                (second, lambda path: path.write_text("new-second", encoding="utf-8")),
            ],
            remove_after_success=[stale_optional],
        )

    assert first.read_text(encoding="utf-8") == "old-first"
    assert second.read_text(encoding="utf-8") == "old-second"
    assert stale_optional.read_text(encoding="utf-8") == "old-optional"
    assert not list(tmp_path.glob("*.tmp"))


def test_delivery_paths_default_to_exact_repository_locations() -> None:
    args = clcr.parse_args(["--input", "pairs.json", "--output-dir", "policies"])

    assert args.model_metrics_csv == clcr.REPOSITORY_ROOT / "outputs/tables/g4irsf25_model_metrics.csv"
    assert args.threshold_report == clcr.REPOSITORY_ROOT / "outputs/reports/g4irsf25_threshold_gate.md"
    assert args.contextual_report == clcr.REPOSITORY_ROOT / "outputs/reports/g4irsf25_contextual_learning.md"


def test_oracle_trigger_gates_single_tiny_mlp_and_exports_cpp_shape() -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)
    ceilings = clcr.compute_action_ceilings(rows)

    trigger = clcr.decide_l2_trigger(ceilings)

    assert trigger["triggered"] is True
    assert "stable_reversals_on_at_least_two_branches" in trigger["reasons"]
    artifact = clcr.fit_l2_tiny_mlp(split["train"], hidden_units=4, min_support=1, margin_seconds=0.1)
    assert artifact["mode"] == "l2"
    assert set(artifact["model"]) == {
        "hidden_weights",
        "hidden_bias",
        "hidden_system_weights",
        "hidden_private_weights",
        "hidden_system_bias",
        "hidden_private_bias",
    }
    assert len(artifact["model"]["hidden_weights"]) == 4
    assert all(len(row) == clcr.FEATURE_COUNT for row in artifact["model"]["hidden_weights"])
    assert len(artifact["model"]["hidden_system_weights"]) == 4
    assert clcr.evaluate_artifact(split["test"], artifact)["safety_failure_count"] == 0


def test_l3_requires_evidence_and_reuses_linear_model_with_online_bias_only() -> None:
    rows = clcr.normalise_paired_rows(_dataset())
    split = clcr.checkpoint_group_chronological_split(rows)
    l1 = clcr.fit_l1_ridge(split["train"], min_support=1)
    trigger = clcr.decide_l3_trigger(
        {"pairwise_ranking_accuracy": 0.80, "system_mae": 1.0},
        {"pairwise_ranking_accuracy": 0.60, "system_mae": 2.0},
        residual_feedback_correlation=0.30,
    )

    assert trigger["triggered"] is True
    l3 = clcr.build_l3_bias_artifact(l1, short_alpha=0.2, long_alpha=0.02, bias_cap_seconds=30.0, trigger=trigger)
    assert l3["mode"] == "l3"
    assert l3["model"] == l1["model"]
    assert l3["l3_bias_cap_seconds"] == 30.0
    assert l3["training_metadata"]["l3_trigger"]["triggered"] is True
