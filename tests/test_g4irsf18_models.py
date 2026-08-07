from __future__ import annotations

import numpy as np
import pytest

from czr005.g4irsf18 import (
    LocalFeatureError,
    PairwiseResidualScorer,
    SetCandidateScorer,
    StandaloneMLPScorer,
    TeacherCounterfactualAffineScorer,
    TinyResidualScorer,
)


FEATURE_NAMES = ("candidate_local_wait", "local_pressure", "deadline_slack")


def test_pairwise_linear_residual_reuses_baseline_but_learns_counterfactual_advantage() -> None:
    rng = np.random.default_rng(18)
    candidate_sets = []
    utilities = []
    baselines = []
    for _ in range(120):
        features = rng.normal(size=(3, 3))
        candidate_sets.append(features)
        utilities.append(1.5 * features[:, 0] - 0.4 * features[:, 1])
        baselines.append(0)
    scorer = PairwiseResidualScorer.fit(
        candidate_sets,
        utilities,
        baselines,
        feature_names=FEATURE_NAMES,
        epochs=700,
    )

    candidates = np.asarray(((-1.0, 0.0, 0.0), (1.2, 0.0, 0.0), (0.0, 2.0, 0.0)))
    assert scorer.choose(candidates, np.zeros(3), 0) == 1
    artifact = scorer.to_dict()
    assert artifact["family"] == "J3_pairwise_linear_residual"
    assert artifact["consumes_baseline_scores"] is True
    assert artifact["ranker"]["identity_features_used"] is False


def test_tiny_residual_and_standalone_scorers_are_deterministic_and_distinct() -> None:
    rng = np.random.default_rng(5)
    features = rng.normal(size=(320, 3))
    advantage = 1.7 * features[:, 0] - 0.35 * features[:, 1] + 0.1 * features[:, 2]

    residual = TinyResidualScorer.fit(
        features,
        advantage,
        feature_names=FEATURE_NAMES,
        hidden_dim=10,
        epochs=750,
        seed=9,
    )
    twin = TinyResidualScorer.fit(
        features,
        advantage,
        feature_names=FEATURE_NAMES,
        hidden_dim=10,
        epochs=750,
        seed=9,
    )
    prediction = np.asarray(residual.regressor.predict(features))
    assert np.corrcoef(prediction, advantage)[0, 1] > 0.96
    assert np.array_equal(
        residual.regressor.input_weights,
        twin.regressor.input_weights,
    )
    choices = np.asarray(((-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    assert residual.choose(choices, np.zeros(2)) == 1
    assert residual.to_dict()["family"] == "J4_tiny_mlp_residual"

    standalone = StandaloneMLPScorer.fit(
        features,
        advantage,
        feature_names=FEATURE_NAMES,
        hidden_dim=10,
        epochs=750,
        seed=9,
    )
    assert standalone.choose(choices) == 1
    assert standalone.to_dict()["consumes_baseline_scores"] is False
    assert "baseline" not in standalone.regressor.feature_names
    padded = np.vstack((choices, np.asarray((np.nan, np.nan, np.nan))))
    assert standalone.scores(padded, (True, True, False))[2] == -np.inf
    assert residual.scores(padded, (0.0, 0.0, np.nan), (True, True, False))[2] == -np.inf


def test_set_scorer_handles_variable_candidate_counts_and_masks() -> None:
    rng = np.random.default_rng(41)
    candidate_sets = []
    utility_sets = []
    for index in range(110):
        count = 2 + index % 4
        features = rng.normal(size=(count, 2))
        centered = features[:, 0] - np.mean(features[:, 0])
        utility = 1.4 * features[:, 0] - 0.25 * features[:, 1] + 0.4 * centered
        candidate_sets.append(features)
        utility_sets.append(utility)
    scorer = SetCandidateScorer.fit(
        candidate_sets,
        utility_sets,
        feature_names=("local_urgency", "local_pressure"),
        hidden_dim=12,
        epochs=850,
        learning_rate=0.03,
        seed=13,
    )
    accuracy = np.mean(
        [
            scorer.choose(features) == int(np.argmax(utility))
            for features, utility in zip(candidate_sets, utility_sets, strict=True)
        ]
    )
    assert accuracy > 0.90

    padded = np.asarray(((0.0, 0.0), (2.0, 0.0), (-1.0, 0.0), (np.nan, np.nan)))
    scores = scorer.scores(padded, (True, True, True, False))
    assert scorer.choose(padded, (True, True, True, False)) == 1
    assert scores[3] == -np.inf
    artifact = scorer.to_dict()
    assert artifact["variable_candidate_count"] is True
    assert artifact["set_pooling"] == ["mean", "max"]
    assert artifact["consumes_baseline_scores"] is False


def test_new_scorers_refuse_identity_and_outcome_feature_names() -> None:
    features = np.asarray(((0.0, 1.0), (1.0, 0.0)))
    targets = np.asarray((0.0, 1.0))
    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        StandaloneMLPScorer.fit(
            features,
            targets,
            feature_names=("task_id", "local_pressure"),
        )
    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        TinyResidualScorer.fit(
            features,
            targets,
            feature_names=("local_pressure", "realized_outcome"),
        )


def test_teacher_counterfactual_affine_folds_to_one_native_formula() -> None:
    names = (
        "deadline_slack_seconds",
        "wait_age_seconds",
        "local_pressure",
    )
    features = np.asarray(
        (
            (20.0, 2.0, 0.0),
            (5.0, 8.0, 1.0),
            (12.0, 4.0, 3.0),
            (2.0, 9.0, 2.0),
        )
    )
    advantages = 0.02 * features[:, 1] - 0.04 * features[:, 2]
    base = TeacherCounterfactualAffineScorer.fit_counterfactual_advantage(
        features,
        advantages,
        feature_names=names,
        blend=40.0,
    )
    weights, bias = base.affine_parameters()
    direct = base.scores(features)
    folded = bias + (features - base.mean) / base.scale @ weights
    assert np.allclose(direct, folded, rtol=0.0, atol=1.0e-12)
    assert base.choose(features[:2]) == 1
    artifact = base.to_dict()
    assert artifact["family"] == "teacher_warm_start_counterfactual_advantage_affine"
    assert artifact["score_direction"] == "higher_is_better"
    assert artifact["tie_break_scope"] == "finite_in_contract_equal_score_only"
    assert artifact["ood_fallback"] == "J2"
    assert artifact["identity_features_used"] is False
