from __future__ import annotations

import numpy as np
import pytest

from czr005.g4irsf17 import (
    ConservativeSelectiveOverride,
    FeatureEnvelope,
    LocalPriorityCandidate,
    LocalizedThesisPriority,
    OverrideEvidence,
    PairwiseLinearRanker,
    PlattCalibrator,
    TinyMLPListwiseRanker,
    current_priority_baseline,
    evaluate_policy_families,
    expected_calibration_error,
    fifo_baseline,
    ranking_metrics,
    selective_override_metrics,
    system_utility,
)


def test_fifo_current_and_localized_thesis_families_are_distinct() -> None:
    assert fifo_baseline([1, 0, 2]).chosen_index == 1
    assert current_priority_baseline([0.1, 0.2, -1.0]).chosen_index == 1
    rule = LocalizedThesisPriority(starvation_age_seconds=60.0, aging_cap_seconds=120.0)
    candidates = [
        LocalPriorityCandidate(0, 10.0, 1.0),
        LocalPriorityCandidate(1, 100.0, 80.0),
        LocalPriorityCandidate(2, 1_000.0, 0.0, repair_priority=True),
    ]
    assert rule.choose(candidates).chosen_index == 2
    definition = rule.ablation_definition()
    assert "pass_time" in definition["legacy_anchor"]
    assert definition["identity_features_used"] is False


def test_pairwise_logistic_ranker_learns_direction_and_is_deterministic() -> None:
    values = np.linspace(-3.0, 3.0, 121)
    features = np.column_stack([values, np.sin(values)])
    labels = (values > 0.0).astype(float)
    first = PairwiseLinearRanker.fit(
        features,
        labels,
        feature_names=("delta_wait", "local_pressure"),
        epochs=700,
    )
    second = PairwiseLinearRanker.fit(
        features,
        labels,
        feature_names=("delta_wait", "local_pressure"),
        epochs=700,
    )
    prediction = first.predict_proba([[-2.0, 0.0], [2.0, 0.0]])
    assert prediction[0] < 0.25
    assert prediction[1] > 0.75
    assert np.array_equal(first.weights, second.weights)
    assert first.bias == second.bias
    with pytest.raises(ValueError, match="NONLOCAL_OR_ID_FEATURE"):
        PairwiseLinearRanker.fit(
            features,
            labels,
            feature_names=("task_id", "local_pressure"),
        )


def test_tiny_listwise_mlp_learns_masked_top4_ranking() -> None:
    rng = np.random.default_rng(11)
    features = rng.normal(size=(128, 4, 3))
    utility = features[:, :, 0] - 0.25 * features[:, :, 1]
    masks = np.ones((128, 4), dtype=bool)
    masks[::3, 3] = False
    features[::3, 3, :] = np.nan
    masked_utility = np.where(masks, utility, -np.inf)
    targets = np.argmax(masked_utility, axis=1)
    model = TinyMLPListwiseRanker.fit(
        features,
        targets,
        feature_names=("local_wait", "local_slack", "local_pressure"),
        legal_masks=masks,
        hidden_dim=8,
        epochs=700,
        learning_rate=0.04,
        seed=5,
    )
    choices = [model.choose(features[index], masks[index]) for index in range(128)]
    assert np.mean(np.asarray(choices) == targets) > 0.90
    assert all(choice != 3 for index, choice in enumerate(choices) if index % 3 == 0)
    twin = TinyMLPListwiseRanker.fit(
        features,
        targets,
        feature_names=("local_wait", "local_slack", "local_pressure"),
        legal_masks=masks,
        hidden_dim=8,
        epochs=700,
        learning_rate=0.04,
        seed=5,
    )
    assert np.array_equal(model.input_weights, twin.input_weights)


def _good_evidence(**updates) -> OverrideEvidence:
    values = {
        "proposed_index": 1,
        "calibrated_benefit_probabilities": (0.80, 0.82, 0.84, 0.86),
        "calibrated_harm_probabilities": (0.01, 0.02, 0.02, 0.03),
        "utility_samples_seconds": (0.4, 0.5, 0.6, 0.7),
        "calibration_ece": 0.03,
        "ood": False,
        "supervisor_authorized": True,
    }
    values.update(updates)
    return OverrideEvidence(**values)


def test_selective_override_requires_calibration_ood_harm_and_supervisor_gates() -> None:
    selector = ConservativeSelectiveOverride()
    accepted = selector.decide(0, _good_evidence())
    assert accepted.activated is True
    assert accepted.chosen_index == 1

    cases = (
        (_good_evidence(calibration_ece=0.2), "CALIBRATION_GATE"),
        (_good_evidence(ood=True), "OOD_GATE"),
        (_good_evidence(supervisor_authorized=False), "SUPERVISOR_GATE"),
        (
            _good_evidence(calibrated_harm_probabilities=(0.06, 0.07, 0.08)),
            "HARM_BUDGET_GATE",
        ),
        (_good_evidence(utility_samples_seconds=(-0.2, -0.1, 0.1)), "UTILITY_LCB_GATE"),
    )
    for evidence, reason in cases:
        decision = selector.decide(0, evidence)
        assert decision.activated is False
        assert decision.chosen_index == 0
        assert decision.reason == reason


def test_calibration_ood_and_policy_metrics_are_reportable() -> None:
    scores = np.linspace(-3.0, 3.0, 100)
    labels = (scores > 0.0).astype(int)
    calibrator = PlattCalibrator.fit(scores, labels)
    probabilities = np.asarray(calibrator.predict(scores))
    assert probabilities[0] < probabilities[-1]
    assert expected_calibration_error(probabilities, labels) < 0.15

    envelope = FeatureEnvelope.fit(
        np.column_stack([scores, np.sin(scores)]),
        feature_names=("local_wait", "local_pressure"),
    )
    assert envelope.is_ood([0.0, 0.0]) is False
    assert envelope.is_ood([100.0, 0.0]) is True

    utilities = [[0.0, 2.0], [1.0, -1.0], [0.0, 0.5]]
    baseline = [0, 0, 0]
    choices = [1, 0, 1]
    metrics = ranking_metrics(utilities, choices, baseline_indices=baseline)
    assert metrics["top1_accuracy"] == 1.0
    assert metrics["harmful_override_rate"] == 0.0
    selective = selective_override_metrics([2.0, -2.0, 0.5], [True, False, True])
    assert selective["beneficial_precision"] == 1.0
    assert selective["harmful_recall"] == 1.0
    report = evaluate_policy_families(
        utilities,
        {"FIFO": baseline, "LOCAL_RULE": choices},
        baseline_indices=baseline,
    )
    assert set(report["families"]) == {"FIFO", "LOCAL_RULE"}
    assert system_utility(
        2.0,
        [1.0, -0.5, 100.0],
        tail_harm_penalty_seconds=0.25,
        deadline_risk_seconds=0.25,
        max_external_bags=2,
    ) == 2.0
