"""Boundary tests for the phase-3 protocol; no physical or performance runs.

Optimization and simulation are replaced with tiny deterministic probes, while
the real selection, split/freeze orchestration and deployment accounting run.
The held-out labels intentionally prefer the opposite hyperparameter choice.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3 import run_phase3_learning as runner
from scripts.experiments.ics_circulation_v3.learning import RidgeValueModel
from scripts.experiments.ics_circulation_v3.model import Bag, Network, Node, Snapshot
from scripts.experiments.ics_circulation_v3.nonlinear_learning import FULL_FEATURE_NAMES


def candidate_rows(group, split, sign):
    rows = []
    for index in range(4):
        features = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
        features.update(remaining_route_ticks=float(index), timed_analytic_absolute=float(index))
        rows.append({"source_group": group, "split": split, "is_baseline": index == 0,
                     "candidate_index": index, "features": features,
                     "cost_mean": 10. + sign * index, "delta_mean": float(sign * index),
                     "timed_delta": float(index), "analytic_delta": float(index),
                     "forecast_delta": float(index)})
    return rows


class ProbeModel:
    """Two lr choices prefer opposite routes; ties use the declared L2 order."""
    def __init__(self, kind, config, feature_names):
        self.kind, self.config, self.feature_names = kind, config, feature_names

    def score_features(self, features, reference):
        sign = -1. if self.config.learning_rate == .01 else 1.
        return sign * (features["remaining_route_ticks"] - reference["remaining_route_ticks"])

    def to_dict(self):
        return {"kind": self.kind, "config": self.config.to_dict(), "features": list(self.feature_names)}


def install_artifacts(tmp_path, monkeypatch):
    base = tmp_path / "evidence"
    training = base / "confirmed"
    training.mkdir(parents=True)
    old = base / "phase2_learning_20261009"
    old.mkdir()
    groups = {split: [f"old:{split}:{i}" for i in range(count)]
              for split, count in (("train", 80), ("validation", 20), ("test", 40), ("deployment", 40))}
    for directory in (training, old):
        (directory / "split_manifest.json").write_text(json.dumps({"groups": groups}), encoding="utf-8")
    rows = [row for split in ("train", "validation", "test") for group in groups[split]
            for row in candidate_rows(group, split, -1 if split != "test" else 1)]
    (training / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    for kind in ("direct", "residual"):
        model = RidgeValueModel(kind, FULL_FEATURE_NAMES, np.zeros(23), np.ones(23), np.zeros(23), 0., 1.)
        (training / f"{kind}_model.json").write_text(json.dumps(model.to_dict()), encoding="utf-8")
    monkeypatch.setattr(runner, "BASE", base)
    monkeypatch.setattr(runner, "TRAINING", training)
    return groups


def test_all_48_fits_freeze_before_fresh_labels_and_test_cannot_select_hyperparameters(tmp_path, monkeypatch):
    old_groups = install_artifacts(tmp_path, monkeypatch)
    output = tmp_path / "run"
    calls = []
    labels_started = False
    saw_freeze = []

    def fit(cls, rows, kind, config, feature_names):
        assert not labels_started, "Any test/deployment-triggered fitting violates the freeze boundary"
        assert all(r["split"] == "train" and r["source_group"] in old_groups["train"] for r in rows)
        calls.append({"kind": kind, "seed": config.seed, "lr": config.learning_rate, "l2": config.l2,
                      "epochs": config.epochs, "groups": len({r["source_group"] for r in rows}),
                      "features": tuple(feature_names)})
        return ProbeModel(kind, config, feature_names)

    monkeypatch.setattr(runner.MLPValueModel, "fit", classmethod(fit))

    def label(scenes, destination):
        nonlocal labels_started
        labels_started = True
        assert len(calls) == 48
        assert len(scenes) == 40
        frozen = json.loads((destination / "frozen_models.json").read_text())
        manifest = json.loads((destination / "split_manifest.json").read_text())
        assert len(frozen) == 14  # 10 deployment models plus four low-sample models
        assert manifest["frozen_models_sha256_before_test"] == runner.sha(destination / "frozen_models.json")
        saw_freeze.append(runner.sha(destination / "frozen_models.json"))
        assert all("test_phase3confirm" in scene.source_group for scene in scenes)
        # Validation favors lr .01; fresh labels favor lr .003. This must not
        # trigger a refit or replace a frozen winner after labels become visible.
        rows = [row for scene in scenes for row in candidate_rows(scene.source_group, "test", 1)]
        branches = [{"invariant_checks": 1} for _ in range(len(rows) * 2)]
        return rows, branches

    monkeypatch.setattr(runner, "label_fresh_test", label)

    def deploy(scenes, models, destination):
        assert labels_started and len(calls) == 48 and len(scenes) == 40
        assert all("deployment_phase3confirm" in scene.source_group for scene in scenes)
        assert runner.sha(destination / "frozen_models.json") == saw_freeze[0]
        for model in models.values():
            if isinstance(model, ProbeModel):
                assert model.config.learning_rate == .01 and model.config.l2 == 0.
        policies = ["baseline", "analytic", "timed", "forecast_rollout", *models]
        assert len(policies) == 14
        return [{"source_group": s.source_group, "policy": p, "total_cost": 1.,
                 "completed": 1, "bag_denominator": 1, "on_time": 1, "uncompleted": [],
                 "cost_components": {"tray_wait": 0.}, "wall_ms": 0., "nested_forecast_rollouts": 0,
                 "invariant_checks": 1} for s in scenes for p in policies]

    monkeypatch.setattr(runner, "execute_deployment", deploy)
    summary = runner.run(output)
    assert summary["training_fit_count"] == 48
    assert summary["deployment_runs"] == 560
    assert summary["new_candidate_rows"] == 160 and summary["new_paired_branch_rollouts"] == 320
    assert summary["source_groups"] == {"train": 80, "validation": 20, "test": 40, "deployment": 40}
    assert summary["test_metrics"]["mlp_direct_seed17"]["mean_regret"] == 3.
    assert {c["epochs"] for c in calls} == {400}
    assert {(c["lr"], c["l2"]) for c in calls} == {(.003, 0.), (.003, .001), (.01, 0.), (.01, .001)}
    for seed in (17, 29, 43):
        full = [c for c in calls if c["seed"] == seed and c["groups"] == 80 and len(c["features"]) == 23]
        assert len(full) == 8 and {c["kind"] for c in full} == {"direct", "residual"}
    attempts = json.loads((output / "validation_selection.json").read_text())
    assert all(d["source_group"] in old_groups["validation"] for a in attempts for d in a["decisions"])
    assert all(len(a["decisions"]) == 20 for a in attempts)
    assert len(json.loads((output / "sample_size_curve.json").read_text())) == 6


def test_training_loader_rejects_mislabeled_held_out_rows(tmp_path, monkeypatch):
    install_artifacts(tmp_path, monkeypatch)
    path = runner.TRAINING / "candidates.jsonl"
    rows = runner.read_rows(path)
    next(r for r in rows if r["split"] == "train")["split"] = "test"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(AssertionError):
        runner.training_rows()


def test_deployment_keeps_uncompleted_bags_in_denominator_and_identical_policy_inputs(tmp_path, monkeypatch):
    initial_bag = Bag("initial", "A", "A", 0, 8)
    late = Bag("late", "A", "A", 2, 4)
    uncompleted = Bag("uncompleted", "A", "A", 3, 7)
    initial = Snapshot(0, Network({"A": Node("A", "zone", "control")}, {}), {}, {"initial": initial_bag})
    scene = SimpleNamespace(source_group="fresh:deployment", initial=initial, forecasts=(), horizon=12,
                            future=lambda seed: (late, uncompleted))
    observed_inputs = []

    class FakeSimulation:
        def __init__(self, state, future, **kwargs):
            observed_inputs.append((state, future, kwargs["route_mode"], kwargs["candidate_count"], kwargs["generator_factory"]))
            self.route_selector = kwargs["route_selector"]

        def advance(self, horizon):
            assert horizon == 12
            return SimpleNamespace(total_cost=4., cost_components={"tray_wait": 1.},
                                   completed={"initial": 5, "late": 6}, uncompleted_bag_ids=("uncompleted",),
                                   invariant_checks=1, policy_stats={})

    monkeypatch.setattr(runner, "Simulation", FakeSimulation)
    records = runner.execute_deployment([scene], {}, tmp_path)
    assert len(records) == 4
    assert {r["policy"] for r in records} == {"baseline", "analytic", "timed", "forecast_rollout"}
    assert all(r["bag_denominator"] == 3 and r["completed"] == 2 and r["on_time"] == 1 for r in records)
    assert all(r["uncompleted"] == ["uncompleted"] for r in records)
    assert all(entry == observed_inputs[0] for entry in observed_inputs)
    summary = runner.summarize_deployment(records)
    assert all(s["bag_denominator"] == 3 and s["uncompleted_total"] == 1 and s["on_time"] == 1 for s in summary.values())
    assert summary["baseline"]["mean_delta_from_timed"] == 0.


def test_run_does_not_overwrite_prior_evidence(tmp_path):
    (tmp_path / "sentinel.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        runner.run(tmp_path)
    assert (tmp_path / "sentinel.json").read_text() == "{}"
