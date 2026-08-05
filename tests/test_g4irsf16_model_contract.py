from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from czr005.g4irsf16.model import (
    DEPLOYMENT_FEATURES,
    FORBIDDEN_RUNTIME_FEATURE_TOKENS,
    MODEL_SCHEMA,
    SelectiveEnsembleModel,
    activation_metrics,
    expected_calibration_error,
    ordered_feature_vector,
    with_self_sha256,
)
from czr005.g4irsf16.training import (
    build_model_artifact,
    choose_selective_thresholds,
    fit_linear_ensemble,
    score_linear_heads,
)


def _artifact() -> dict[str, object]:
    width = len(DEPLOYMENT_FEATURES)
    return with_self_sha256(
        {
            "schema": MODEL_SCHEMA,
            "kind": "I4",
            "action": "HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY",
            "feature_names": list(DEPLOYMENT_FEATURES),
            "normalization": {
                "mean": [0.0] * width,
                "scale": [1.0] * width,
            },
            "training_bounds": {
                "min": [-1.0] * width,
                "max": [1.0] * width,
            },
            "heads": {
                "benefit_logit": [[5.0] + [0.0] * width],
                "harmful_logit": [[-5.0] + [0.0] * width],
                "risk_adjusted_utility_seconds": [[2.0] + [0.0] * width],
            },
            "thresholds": {
                "benefit_probability_lcb": 0.90,
                "harmful_probability_ucb": 0.10,
                "utility_lcb_margin_seconds": 0.0,
            },
        }
    )


def _features(value: float = 0.0) -> OrderedDict[str, float]:
    return OrderedDict((name, value) for name in DEPLOYMENT_FEATURES)


def test_exact_feature_schema_and_deterministic_inference() -> None:
    model = SelectiveEnsembleModel.from_artifact(_artifact())
    features = _features()
    first = model.score(features)
    assert first.activation is True
    assert first.abstention_reason == "ACTIVATE"
    assert [model.score(features) for _ in range(50)] == [first] * 50


def test_schema_mismatch_and_ood_fail_closed() -> None:
    model = SelectiveEnsembleModel.from_artifact(_artifact())
    missing = _features()
    missing.pop(next(iter(missing)))
    assert model.score(missing).abstention_reason == "FEATURE_SCHEMA_FAIL_CLOSED"

    extra = _features()
    extra["task_id"] = 7.0
    assert model.score(extra).abstention_reason == "FEATURE_SCHEMA_FAIL_CLOSED"

    reversed_features = OrderedDict(reversed(tuple(_features().items())))
    assert model.score(reversed_features).abstention_reason == "FEATURE_SCHEMA_FAIL_CLOSED"

    ood = _features()
    ood[DEPLOYMENT_FEATURES[0]] = 2.0
    assert model.score(ood).abstention_reason == "OOD_ABSTAIN"
    assert model.score(ood).activation is False


def test_model_hash_and_dimensions_are_enforced() -> None:
    artifact = _artifact()
    artifact["kind"] = "I3"
    with pytest.raises(ValueError, match="MODEL_SELF_SHA256_MISMATCH"):
        SelectiveEnsembleModel.from_artifact(artifact)

    bad = _artifact()
    bad["feature_names"] = list(reversed(DEPLOYMENT_FEATURES))
    bad = with_self_sha256(bad)
    with pytest.raises(ValueError, match="MODEL_FEATURE_SCHEMA_MISMATCH"):
        SelectiveEnsembleModel.from_artifact(bad)


def test_deployment_allowlist_contains_no_forbidden_identity_or_outcome() -> None:
    lowered = "|".join(DEPLOYMENT_FEATURES).lower()
    for token in FORBIDDEN_RUNTIME_FEATURE_TOKENS:
        assert token not in lowered


def test_calibration_and_activation_metrics() -> None:
    assert expected_calibration_error([0.1, 0.9], [0, 1], bin_count=2) == pytest.approx(0.1)
    metrics = activation_metrics(
        ["BENEFICIAL", "HARMFUL", "NEUTRAL_WITHIN_TOLERANCE"],
        [True, False, False],
        [2.0, -3.0, 0.0],
    )
    assert metrics["beneficial_precision"] == 1.0
    assert metrics["harmful_activation_rate"] == 0.0
    assert metrics["activation_coverage"] == pytest.approx(1.0 / 3.0)
    assert metrics["target_panel_abstention_rate"] == pytest.approx(2.0 / 3.0)

    harmful_metrics = activation_metrics(
        ["HARMFUL", "HARMFUL", "BENEFICIAL", "NEUTRAL_WITHIN_TOLERANCE"],
        [True, False, False, False],
        [-1.0, -1.0, 1.0, 0.0],
    )
    assert harmful_metrics["harmful_activation_rate"] == 0.25
    assert harmful_metrics["high_confidence_harmful_precision"] == 1.0


def test_ordered_vector_rejects_boolean_as_numeric() -> None:
    features = _features()
    features[DEPLOYMENT_FEATURES[0]] = True  # type: ignore[assignment]
    with pytest.raises(ValueError, match="FEATURE_NOT_NUMERIC"):
        ordered_feature_vector(features)


def test_cluster_bootstrap_training_exports_runtime_only_json() -> None:
    rng = np.random.default_rng(16)
    width = len(DEPLOYMENT_FEATURES)
    x_train = rng.normal(size=(40, width))
    benefit = (x_train[:, 0] > 0.8).astype(int)
    harmful = (x_train[:, 0] < -0.2).astype(int)
    utility = x_train[:, 0] * 2.0
    x_calibration = rng.normal(size=(20, width))
    benefit_calibration = (x_calibration[:, 0] > 0.8).astype(int)
    harmful_calibration = (x_calibration[:, 0] < -0.2).astype(int)
    prepared, heads = fit_linear_ensemble(
        x_train,
        benefit,
        harmful,
        utility,
        [f"group-{index // 2}" for index in range(len(x_train))],
        x_calibration_raw=x_calibration,
        beneficial_calibration=benefit_calibration,
        harmful_calibration=harmful_calibration,
        ensemble_size=4,
    )
    diagnostics = score_linear_heads(prepared, heads, x_calibration)
    labels = [
        "BENEFICIAL" if good else "HARMFUL" if bad else "NEUTRAL_WITHIN_TOLERANCE"
        for good, bad in zip(benefit_calibration, harmful_calibration, strict=True)
    ]
    thresholds, _ = choose_selective_thresholds(
        diagnostics,
        labels,
        x_calibration[:, 0] * 2.0,
        minimum_coverage=0.0025,
        maximum_coverage=0.05,
        maximum_harmful_activation_rate=0.005,
    )
    artifact = build_model_artifact(
        kind="I4",
        action="HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY",
        prepared=prepared,
        heads=heads,
        thresholds=thresholds,
        training_metadata={"fixture": "deterministic"},
    )
    model = SelectiveEnsembleModel.from_artifact(artifact)
    assert len(model.benefit_weights) == 4
