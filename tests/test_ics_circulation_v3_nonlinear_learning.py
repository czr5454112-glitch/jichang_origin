"""Numerical and protocol checks for the independent width-32 NumPy model."""
from copy import deepcopy
import json

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.nonlinear_learning import (
    FULL_FEATURE_NAMES, HIDDEN_WIDTH, MLPConfig, MLPValueModel,
    _objective_and_gradients,
)


def examples():
    rows = []
    for group in range(6):
        baseline_cost = None
        for index in range(4):
            x = -1.4 + .17 * group + .6 * index
            context = (group - 2.5) / 3
            timed = 2. + .3 * group + index
            features = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
            features.update(remaining_route_ticks=x, source_empty_stock=context,
                            timed_analytic_absolute=timed)
            cost = 12. + 2. * np.tanh(1.3 * x) + .7 * context + .5 * timed
            if baseline_cost is None:
                baseline_cost = cost
            rows.append({"source_group": f"train:{group}", "split": "train",
                         "is_baseline": index == 0, "features": features,
                         "cost_mean": float(cost), "delta_mean": float(cost - baseline_cost),
                         "timed_delta": float(index)})
    return rows


@pytest.mark.parametrize("paired", [False, True])
def test_actual_direct_and_paired_residual_objectives_pass_full_finite_differences(paired):
    rng = np.random.default_rng(31)
    x, x0, y = rng.normal(size=(5, 2)), rng.normal(size=(5, 2)), rng.normal(size=5)
    parameters = {"w1": rng.normal(0, .2, (2, HIDDEN_WIDTH)),
                  "b1": rng.normal(0, .2, HIDDEN_WIDTH),
                  "w2": rng.normal(0, .2, HIDDEN_WIDTH), "b2": np.array([.37])}
    reference = x0 if paired else None
    objective, analytical, data_mse = _objective_and_gradients(parameters, x, y, reference, l2=.013)
    prediction = np.tanh(x @ parameters["w1"] + parameters["b1"]) @ parameters["w2"] + .37
    if paired:
        prediction -= np.tanh(x0 @ parameters["w1"] + parameters["b1"]) @ parameters["w2"] + .37
    assert data_mse == pytest.approx(np.mean((prediction - y) ** 2), abs=1e-13)
    assert objective > data_mse
    for name, value in parameters.items():
        numerical = np.zeros_like(value)
        for index in np.ndindex(value.shape):
            original = value[index]
            value[index] = original + 1e-6
            plus = _objective_and_gradients(parameters, x, y, reference, l2=.013)[0]
            value[index] = original - 1e-6
            minus = _objective_and_gradients(parameters, x, y, reference, l2=.013)[0]
            value[index] = original
            numerical[index] = (plus - minus) / 2e-6
        np.testing.assert_allclose(analytical[name], numerical, atol=2e-8, rtol=2e-6)
    if paired:
        assert analytical["b2"][0] == 0
        # This catches the incorrect f(x) loss / stop-gradient baseline variant.
        incorrect = _objective_and_gradients(parameters, x, y, None, l2=.013)[1]
        assert not np.allclose(analytical["w1"], incorrect["w1"])


@pytest.mark.parametrize("kind", ["direct", "residual"])
def test_convergence_and_recorded_objective_match_actual_predictions(kind):
    rows = examples()
    model = MLPValueModel.fit(rows, kind, MLPConfig(epochs=500, learning_rate=.01, l2=0, seed=17))
    metadata = model.training_metadata
    assert model.hidden_width == 32 and model.parameter_count == 801
    assert metadata["final_data_mse"] < .02
    assert metadata["final_data_mse"] < metadata["initial_data_mse"] * .02
    baseline = {r["source_group"]: r for r in rows if r["is_baseline"]}
    squared_errors = []
    score_errors = []
    for row in rows:
        reference = baseline[row["source_group"]]["features"]
        predicted = model.predict_value(row["features"])
        if kind == "direct":
            target = row["cost_mean"]
        else:
            predicted -= model.predict_value(reference)
            target = row["delta_mean"] - row["timed_delta"]
        squared_errors.append((predicted - target) ** 2)
        score_errors.append((model.score_features(row["features"], reference) - row["delta_mean"]) ** 2)
        assert model.score_features(reference, reference) == 0.
    assert np.mean(squared_errors) == pytest.approx(metadata["final_data_mse"], abs=1e-12)
    assert np.mean(score_errors) < .04
    assert metadata["source_group_count"] == 6 and metadata["row_count"] == 24
    assert metadata["epochs_completed"] == 500 and metadata["validation_or_test_access"] is False


@pytest.mark.parametrize("kind", ["direct", "residual"])
def test_deterministic_seed_exact_roundtrip_and_training_only_normalization(kind):
    rows = examples()
    before = deepcopy(rows)
    config = MLPConfig(epochs=20, seed=29)
    model = MLPValueModel.fit(rows, kind, config)
    repeated = MLPValueModel.fit(rows, kind, config)
    assert model.to_dict() == repeated.to_dict()
    assert rows == before
    matrix = np.array([[row["features"][key] for key in model.feature_names] for row in rows])
    np.testing.assert_array_equal(model.center, matrix.mean(axis=0))
    expected_scale = matrix.std(axis=0)
    expected_scale[expected_scale < 1e-9] = 1.
    np.testing.assert_array_equal(model.scale, expected_scale)
    value = json.loads(json.dumps(model.to_dict(), allow_nan=False))
    restored = MLPValueModel.from_dict(value)
    assert restored.to_dict() == model.to_dict()
    for row in rows:
        assert restored.predict_value(row["features"]) == model.predict_value(row["features"])
    value["parameters"]["w1"][0][0] += 1
    value["training_metadata"]["row_count"] = -1
    assert restored.to_dict() == model.to_dict()
    held_out = {**rows[0]["features"], "remaining_route_ticks": 999.}
    model.predict_value(held_out)
    np.testing.assert_array_equal(model.center, matrix.mean(axis=0))
    different_seed = MLPValueModel.fit(rows, kind, MLPConfig(epochs=20, seed=43))
    assert not np.array_equal(model.parameters["w1"], different_seed.parameters["w1"])


def test_direct_and_residual_have_same_feature_schema_and_capacity():
    rows = examples()
    direct = MLPValueModel.fit(rows, "direct", MLPConfig(epochs=1))
    residual = MLPValueModel.fit(rows, "residual", MLPConfig(epochs=1))
    assert direct.feature_names == residual.feature_names == FULL_FEATURE_NAMES
    assert direct.parameter_count == residual.parameter_count == 801
    assert {k: v.shape for k, v in direct.parameters.items()} == {k: v.shape for k, v in residual.parameters.items()}


def test_explicit_ablations_never_read_removed_features_and_direct_can_remove_analytic():
    rows = examples()
    selected = ("remaining_route_ticks", "source_empty_stock")
    config = MLPConfig(epochs=10)
    reduced = [{**r, "features": {k: r["features"][k] for k in selected}} for r in rows]
    # A removed value need not even be numeric: touching it is a test failure.
    poisoned = deepcopy(rows)
    for row in poisoned:
        for key in set(FULL_FEATURE_NAMES) - set(selected):
            row["features"][key] = object()
    reduced_model = MLPValueModel.fit(reduced, "direct", config, feature_names=selected)
    full_model = MLPValueModel.fit(poisoned, "direct", config, feature_names=selected)
    assert full_model.to_dict() == reduced_model.to_dict()
    assert full_model.score_features(poisoned[1]["features"], poisoned[0]["features"]) == reduced_model.score_features(
        reduced[1]["features"], reduced[0]["features"])
    assert "timed_analytic_absolute" in full_model.training_metadata["removed_feature_names"]
    with pytest.raises(ValueError, match="require timed_analytic_absolute"):
        MLPValueModel.fit(rows, "residual", config, feature_names=selected)
    with pytest.raises(ValueError, match="schema"):
        MLPValueModel.fit(reduced, "direct", config)


def test_residual_ablations_only_use_selected_features_plus_required_analytic():
    rows = examples()
    names = ("remaining_route_ticks", "timed_analytic_absolute")
    model = MLPValueModel.fit(rows, "residual", MLPConfig(epochs=10), feature_names=names)
    full = deepcopy(rows[1]["features"])
    reference = deepcopy(rows[0]["features"])
    expected = model.score_features(full, reference)
    for name in set(FULL_FEATURE_NAMES) - set(names):
        full[name] = float("nan")
        reference[name] = None
    assert model.score_features(full, reference) == expected
    assert model.score_features(reference, reference) == 0
    del full["remaining_route_ticks"]
    with pytest.raises(ValueError, match="schema"):
        model.score_features(full, reference)


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r[0].update(split="test"), "training"),
    (lambda r: r[0].update(split="validation"), "training"),
    (lambda r: r[0].update(is_baseline=False), "baseline"),
    (lambda r: r[1].update(is_baseline=True), "baseline"),
    (lambda r: r[0]["features"].update(remaining_route_ticks=np.inf), "finite"),
    (lambda r: r[0]["features"].update(remaining_route_ticks=True), "finite"),
    (lambda r: r[0]["features"].update(unpublished_truth=1), "schema"),
    (lambda r: r[0].update(cost_mean=np.nan), "finite"),
])
def test_fit_rejects_leakage_invalid_schema_and_nonfinite_data(mutation, match):
    rows = examples()
    mutation(rows)
    with pytest.raises(ValueError, match=match):
        MLPValueModel.fit(rows, "direct", MLPConfig(epochs=1))


def test_residual_rejects_nonfinite_misaligned_and_nonzero_baseline_labels():
    for field, value, match in (("delta_mean", np.nan, "finite"), ("timed_delta", 3., "match"),
                                ("delta_mean", 1., "Baseline")):
        rows = examples()
        rows[0][field] = value
        with pytest.raises(ValueError, match=match):
            MLPValueModel.fit(rows, "residual", MLPConfig(epochs=1))
    rows = examples()
    for row in rows:
        row["cost_mean"] = object()  # residual objective must not read full-cost labels
    MLPValueModel.fit(rows, "residual", MLPConfig(epochs=1))


@pytest.mark.parametrize("arguments", [
    {"epochs": 0}, {"epochs": True}, {"seed": -1}, {"seed": 1.5}, {"l2": -1},
    {"learning_rate": 0}, {"learning_rate": np.inf}, {"beta1": 1}, {"beta2": -1}, {"epsilon": 0},
])
def test_optimizer_configuration_rejects_invalid_values(arguments):
    with pytest.raises(ValueError):
        MLPConfig(**arguments)


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(schema="other"),
    lambda v: v["architecture"].update(hidden_width=16),
    lambda v: v["parameters"]["w1"].pop(),
    lambda v: v["parameters"]["w2"].__setitem__(0, np.inf),
    lambda v: v["parameters"].update(extra=[0]),
    lambda v: v["scale"].__setitem__(0, 0),
    lambda v: v["center"].__setitem__(0, np.nan),
    lambda v: v["feature_names"].reverse(),
    lambda v: v["training_metadata"].update(loss=np.nan),
    lambda v: v["config"].update(seed=-1),
])
def test_deserialization_rejects_corrupt_schema_shapes_and_nonfinite_state(mutation):
    payload = MLPValueModel.fit(examples(), "direct", MLPConfig(epochs=1)).to_dict()
    mutation(payload)
    with pytest.raises(ValueError):
        MLPValueModel.from_dict(payload)


def test_runtime_checks_nonfinite_selected_features_unknown_keys_and_bad_kind():
    model = MLPValueModel.fit(examples(), "direct", MLPConfig(epochs=1))
    features = examples()[0]["features"]
    with pytest.raises(ValueError, match="finite"):
        model.predict_value({**features, "remaining_route_ticks": float("nan")})
    with pytest.raises(ValueError, match="schema"):
        model.predict_value({**features, "future_seed": 1})
    with pytest.raises(ValueError, match="kind"):
        MLPValueModel.fit(examples(), "oracle", MLPConfig(epochs=1))
    with pytest.raises(ValueError, match="unknown"):
        MLPValueModel.fit(examples(), "direct", MLPConfig(epochs=1), feature_names=("hidden_truth",))
