"""Protocol leakage and incomplete-evidence boundaries for W3 development."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3 import run_paired_development as run
from scripts.experiments.ics_circulation_v3.model import Bag, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.nonlinear_learning import FULL_FEATURE_NAMES, MLPConfig


def training_rows():
    rows = []
    for stream in ("A", "B", "C", "D"):
        for band in (0, 20, 40):
            for candidate in (0, 1):
                feature = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
                feature.update(remaining_route_ticks=float(candidate), timed_analytic_absolute=float(candidate))
                rows.append({"stream": stream, "source_group": f"{stream}:{band}", "band": band,
                    "features": feature, "is_baseline": candidate == 0, "normal_ordinal": candidate,
                    "actual_action_key": str(candidate), "cost_mean": 10. - candidate,
                    "delta_mean": -float(candidate), "timed_delta": float(candidate)})
    return rows


def label_sample():
    values = np.asarray([[[10. + r + f * .01 + effect for f in range(32)]
                           for effect in (0., -2., -9.)] for r in range(4)])
    features = []
    for i in range(3):
        f = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
        f["timed_analytic_absolute"] = float(i)
        features.append(f)
    raw = []
    for r in range(4):
        for c in range(3):
            for f in range(32):
                costs = dict.fromkeys(run.COST_WEIGHTS, 0.)
                costs["tray_wait"] = values[r, c, f]
                raw.append({"replicate": r, "candidate": c, "future_index": f, "cost_components": costs})
    return {"actual_action_keys": ["baseline", "normal", "expanded_only"],
            "normal_action_keys": ["baseline", "normal"], "features_observable_only": features,
            "proposals": [{}, {}, {}], "paired_costs": values.tolist(), "raw_branches": raw,
            "summary": {"identity": "A:timed:t0:bag", "band": 0, "time": 0}}


def test_entire_held_out_stream_labels_and_features_cannot_change_its_model_or_normalization():
    rows = training_rows()
    changed = deepcopy(rows)
    for row in changed:
        if row["stream"] == "D":
            row["delta_mean"] = 1e6 if not row["is_baseline"] else 0.
            row["cost_mean"] = -1e9
            row["features"]["remaining_route_ticks"] = 1e12
    config = MLPConfig(epochs=5, learning_rate=.01, l2=.001, seed=17)
    for kind in ("paired_direct", "residual"):
        left, left_bounds, fold = run.fit_fold(rows, "D", kind, 17, config=config)
        right, right_bounds, _ = run.fit_fold(changed, "D", kind, 17, config=config)
        assert left.to_dict() == right.to_dict() and left_bounds == right_bounds
        assert len(fold["training_checkpoints"]) == 9 and len(fold["evaluation_checkpoints"]) == 3
        assert all(group.startswith(("A:", "B:", "C:")) for group in left.training_metadata["source_groups"])
        assert left_bounds["remaining_route_ticks"]["maximum"] == 1.


def test_expanded_best_action_cannot_enter_training_or_normal_pool_assessment():
    rows = run.normal_rows(label_sample(), "A")
    assert len(rows) == 2 and {row["candidate_index"] for row in rows} == {0, 1}
    assert len(rows[1]["paired_deltas"]) == 128
    assert rows[0]["delta_mean"] == rows[0]["timed_delta"] == 0
    assert rows[1]["delta_mean"] == pytest.approx(-2.)
    stats = run.assess(rows, kind="baseline")
    assert stats["mean_regret"] == pytest.approx(2.)  # Not expanded-only regret 9.


def test_missing_branch_cost_mismatch_and_hidden_feature_are_rejected():
    sample = label_sample()
    sample["raw_branches"].pop()
    with pytest.raises(ValueError, match="Missing or duplicate"):
        run.normal_rows(sample, "A")
    sample = label_sample()
    sample["raw_branches"][0]["cost_components"]["tray_wait"] += 1
    with pytest.raises(ValueError, match="original physical components"):
        run.normal_rows(sample, "A")
    sample = label_sample()
    sample["features_observable_only"][0]["future_truth"] = 12.
    with pytest.raises(ValueError, match="same 23"):
        run.normal_rows(sample, "A")


def test_incomplete_or_failed_labels_and_existing_output_refuse_before_fit(tmp_path, monkeypatch):
    labels = tmp_path / "labels"
    labels.mkdir()
    monkeypatch.setattr(run.MLPValueModel, "fit", lambda *a, **kw: pytest.fail("Must not fit"))
    with pytest.raises(ValueError, match="incomplete"):
        run.run(tmp_path / "new", labels)
    assert not (tmp_path / "new").exists()
    (labels / "summary.json").write_text(json.dumps({"source_changed_during_run": False, "failures": ["bad"]}))
    with pytest.raises(ValueError, match="zero failures"):
        run.run(tmp_path / "new", labels)
    output = tmp_path / "old"
    output.mkdir()
    (output / "sentinel").write_text("keep")
    with pytest.raises(ValueError, match="overwritten"):
        run.run(output, labels, protocol_only=True)
    assert (output / "sentinel").read_text() == "keep"


def test_deployment_preserves_unfinished_task_denominator():
    initial = Snapshot(0, Network({n: Node(n, n, n) for n in "AB"}, {}),
                       {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "B", 0, 1)})
    scene = SimpleNamespace(initial=initial, forecasts=(), future_bags=(), horizon=2)
    result = run.deployment(scene)
    assert result["metrics"]["scheduled_bags"] == 1
    assert result["metrics"]["completed"] == result["metrics"]["on_time"] == 0
    assert result["metrics"]["uncompleted"] == ["b"]
    assert result["metrics"]["total_cost"] == 11


def test_selector_cannot_see_later_publications_even_when_they_disagree():
    from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
    from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
    from scripts.experiments.ics_circulation_v3.phase4_control import GeneratorFactory
    state = feedback_scene().initial
    candidates = GeneratorFactory(run.ControlSpec(**run.PROTOCOL["deployed_spec"]))().generate(state, "initial", "loaded", k=4)
    class FrozenModel:
        def score_features(self, feature, reference):
            return feature["timed_analytic_absolute"] - reference["timed_analytic_absolute"]
    bounds = {n: {"minimum": -1e9, "maximum": 1e9} for n in FULL_FEATURE_NAMES}
    unpublished = RoutingDemandForecast("later", "B", "C", 12, 30, published_at=10)
    first = run.LearnedSelector(FrozenModel(), bounds, (unpublished,))
    second = run.LearnedSelector(FrozenModel(), bounds, (replace(unpublished, node="S", count=50),))
    assert first(state, candidates) == second(state, candidates)
    assert first.history == second.history
    assert first.history[0]["published_forecasts"] == []


def test_all_fixed_models_freeze_before_assessment_and_no_seed_is_selected(tmp_path, monkeypatch):
    rows = training_rows()
    scenes = [SimpleNamespace(name=n, initial=Snapshot(0, Network({"x": Node("x", "x", "x")}, {}), {}, {}),
                              forecasts=(), future_bags=(), horizon=2) for n in "ABCD"]
    labels = tmp_path / "labels"
    labels.mkdir()
    for scene in scenes:
        (labels / (scene.name + "_episode.json")).write_text(json.dumps({"metrics": {"timed_cost": 1., "baseline_cost": 1.}}))
    monkeypatch.setattr(run, "load_labels", lambda p: (rows, {"files_sha256": {}}))
    monkeypatch.setattr(run, "sustained_scenes", lambda: scenes)
    calls = []
    class Probe:
        def __init__(self, kind, config, groups):
            self.kind, self.config = kind, config
            self.training_metadata = {"source_groups": groups, "history": []}
        def score_features(self, f, reference):
            # Fixed seeds intentionally disagree; none may be selected away.
            return (1 if self.config.seed == 17 else -1) * (f["remaining_route_ticks"] - reference["remaining_route_ticks"])
        def to_dict(self):
            return {"kind": self.kind, "config": self.config.to_dict(), "training_metadata": self.training_metadata}
    def fit(cls, train, kind, config, feature_names):
        assert not (tmp_path / "output" / "frozen_models.json").exists()
        assert all(r["split"] == "train" for r in train)
        streams = {r["stream"] for r in train}
        assert len(streams) == 3 and len({r["source_group"] for r in train}) == 9
        calls.append((frozenset(streams), kind, config.seed, config.epochs, config.learning_rate, config.l2))
        return Probe(kind, config, sorted({r["source_group"] for r in train}))
    monkeypatch.setattr(run.MLPValueModel, "fit", classmethod(fit))
    original_assess = run.assess
    def assess(*args, **kwargs):
        assert len(calls) == 24
        assert len(json.loads((tmp_path / "output" / "frozen_models.json").read_text())) == 24
        return original_assess(*args, **kwargs)
    monkeypatch.setattr(run, "assess", assess)
    def deploy(scene, **kwargs):
        assert len(calls) == 24
        return {"metrics": {"status": "completed_run", "total_cost": 1., "scheduled_bags": 1, "completed": 1},
                "boundaries": [{"time": i, "state_sha256": str(i)} for i in range(2)]}
    monkeypatch.setattr(run, "deployment", deploy)
    summary = run.run(tmp_path / "output", labels)
    assert summary["fits"] == 24 and summary["deployment_runs"] == 32
    assert not summary["frozen_models_changed"]
    assert {c[2:] for c in calls} == {(seed, 400, .01, .001) for seed in (17, 29, 43)}
    assert {row["policy"] for row in summary["deployment_metrics"]} == {
        "baseline", "timed", *(f"{kind}_seed{seed}" for kind in ("paired_direct", "residual") for seed in (17, 29, 43))}
