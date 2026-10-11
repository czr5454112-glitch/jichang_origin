"""Paired target invariance, whole-stream isolation and complete run accounting."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.paired_linear import PairedLinearModel
from scripts.experiments.ics_circulation_v3 import run_role_linear as runner


def source_rows(*, analytic_zero=False):
    rows = []
    for i, stream in enumerate(runner.PROTOCOL["streams"]):
        for node in ("S", "B"):
            for action in range(3):
                base = dict.fromkeys(runner.shared.FULL_FEATURE_NAMES, 0.)
                base.update(remaining_route_ticks=float(action + i),
                            timed_analytic_absolute=0. if analytic_zero else float(2 * action))
                physical = {**dict.fromkeys(runner.shared.PHYSICAL_FEATURE_NAMES, 0.), **base}
                physical["prefix_completes_delivery"] = float(action == 0)
                rows.append({"stream": stream, "owner": None, "source_group": f"{stream}:{node}",
                    "features23": base, "features31": physical, "is_baseline": action == 0,
                    "normal_ordinal": action, "actual_action_key": str(action), "source_node": node,
                    "role": "origin", "cost_mean": 10. + i - action, "delta_mean": -float(action),
                    "timed_delta": 0. if analytic_zero else float(2 * action)})
    return rows


@pytest.mark.parametrize("schema", ["paired23", "physical31"])
def test_zero_analytic_pair_direct_and_residual_are_exactly_equal(schema):
    rows = source_rows(analytic_zero=True)
    held = runner.PROTOCOL["streams"][-1]
    direct, bounds, _ = runner.fit_fold(rows, held, schema, "paired_direct")
    residual, other_bounds, _ = runner.fit_fold(rows, held, schema, "residual")
    assert np.array_equal(direct.weights, residual.weights)
    assert np.array_equal(direct.scale, residual.scale)
    assert bounds == other_bounds
    projected = runner.shared.project_rows(rows, schema)
    for candidate in projected:
        reference = next(r for r in projected if r["source_group"] == candidate["source_group"] and r["is_baseline"])
        assert direct.score_features(candidate["features"], reference["features"]) == residual.score_features(
            candidate["features"], reference["features"])
        assert direct.score_features(reference["features"], reference["features"]) == 0.


@pytest.mark.parametrize("kind", ["paired_direct", "residual"])
def test_group_absolute_cost_shift_does_not_change_paired_fit(kind):
    original = source_rows()
    changed = deepcopy(original)
    for row in changed:
        row["cost_mean"] += 1e9 if row["source_node"] == "S" else -5000.
    left, _, _ = runner.fit_fold(original, runner.PROTOCOL["streams"][-1], "physical31", kind)
    right, _, _ = runner.fit_fold(changed, runner.PROTOCOL["streams"][-1], "physical31", kind)
    assert left.to_dict() == right.to_dict()


def test_held_out_extreme_features_and_labels_do_not_change_fit_or_normalization():
    rows, held = source_rows(), runner.PROTOCOL["streams"][-1]
    changed = deepcopy(rows)
    for row in changed:
        if row["stream"] == held:
            row["features23"]["remaining_route_ticks"] = 1e30
            row["features31"]["prefix_completes_delivery"] = -1e20
            row["delta_mean"] = 9e20
    for schema in runner.shared.SCHEMAS:
        for kind in runner.shared.KINDS:
            a, bounds, fold = runner.fit_fold(rows, held, schema, kind)
            b, changed_bounds, other_fold = runner.fit_fold(changed, held, schema, kind)
            assert a.to_dict() == b.to_dict() and bounds == changed_bounds and fold == other_fold
            assert held not in fold["training_streams"]
    bad = deepcopy(rows)
    bad[0]["source_group"] = next(r["source_group"] for r in rows if r["stream"] == held)
    with pytest.raises(ValueError, match="crosses"):
        runner.fit_fold(bad, held, "paired23", "residual")


def test_closed_form_ridge_matches_declared_mean_loss_and_serialization():
    rows = runner.shared.project_rows(source_rows(), "paired23")
    model = PairedLinearModel.fit(rows, "residual", feature_names=runner.shared.FULL_FEATURE_NAMES)
    baseline = {r["source_group"]: r for r in rows if r["is_baseline"]}
    difference = np.asarray([[(r["features"][n] - baseline[r["source_group"]]["features"][n]) / model.scale[j]
                              for j, n in enumerate(model.feature_names)] for r in rows])
    target = np.asarray([r["delta_mean"] - r["timed_delta"] for r in rows])
    gradient = 2 * difference.T @ (difference @ model.weights - target) / len(rows) + 2 * model.weights
    assert np.max(np.abs(gradient)) < 1e-10
    restored = PairedLinearModel.from_dict(model.to_dict())
    assert restored.to_dict() == model.to_dict()
    assert restored.config.seed is None and restored.config.alpha == 1.
    for changed in (dict(model.to_dict(), architecture="absolute_cost"),
                    dict(model.to_dict(), weights=[float("nan")] * len(model.feature_names))):
        with pytest.raises(ValueError):
            PairedLinearModel.from_dict(changed)
    rows[0]["split"] = "test"
    with pytest.raises(ValueError, match="only training"):
        PairedLinearModel.fit(rows, "paired_direct")


def test_existing_output_is_refused_before_label_access(tmp_path, monkeypatch):
    (tmp_path / "sentinel").write_text("keep")
    monkeypatch.setattr(runner.shared, "load_r0_labels", lambda _: pytest.fail("must not read labels"))
    with pytest.raises(ValueError, match="overwritten"):
        runner.run(tmp_path, tmp_path / "missing")


def test_full_216_episode_denominator_freeze_and_failure_preservation(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.shared, "load_r0_labels", lambda _: (source_rows(), [None] * 24, {}))
    monkeypatch.setattr(runner, "_check_inputs", lambda _: True)
    calls = []
    def deployment(scene, **kwargs):
        assert (tmp_path / "fit_freeze.json").is_file()
        assert len(runner.shared.read(tmp_path / "frozen_models.json")) == 16
        calls.append(kwargs["kind"])
        if len(calls) == 100:
            raise ValueError("intentional complete denominator test")
        return {"metrics": {"status": "completed_run", "total_cost": 1.,
                            "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                            "completed": 0, "uncompleted": ["retained"]}}
    monkeypatch.setattr(runner.shared, "deployment", deployment)
    result = runner.run(tmp_path, "unused")
    assert result["fits"] == 16 and len(calls) == result["deployment_runs"] == 216
    assert result["linear_deployments"] == 144 and result["baseline_timed_deployments"] == 72
    assert len(result["failures"]) == 1 and result["failures"][0]["completed"] is None
    assert result["completed_bags"] == 0
    for stream in runner.PROTOCOL["streams"]:
        for realization in ["nominal", *(f"stress_{i}" for i in range(8))]:
            group = [r for r in result["deployment_metrics"] if r["stream"] == stream and r["realization"] == realization]
            assert len(group) == 6
            assert len({r["actual_tape_sha256"] for r in group}) == len({r["scene_input_sha256"] for r in group}) == 1
