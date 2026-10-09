from dataclasses import replace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.learning import RidgeValueModel, TimedAnalyticEvaluator, active_forecasts
from scripts.experiments.ics_circulation_v3.phase2_scenarios import phase2_scenes
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.model import Bag


def test_source_groups_disjoint_and_uncertain_events_only_after_checkpoint():
    scenes = phase2_scenes()
    groups = [s.source_group for s in scenes]
    assert len(groups) == len(set(groups)) == 180
    assert [sum(s.split == split for s in scenes) for split in ("train", "validation", "test", "deployment")] == [80, 20, 40, 40]
    assert all(b.arrival > scene.intervention_at for scene in scenes for seed in (0, 1) for b in scene.future(seed))


def test_timed_features_use_published_forecasts_and_no_truth_metadata():
    scene = phase2_scenes(1, 0, 0, 0)[0]
    state = scene.initial
    candidates = RegionalCandidateGenerator(horizon=72).generate(state, scene.target_bag, scene.target_tray, 3)
    evaluator = TimedAnalyticEvaluator(72, scene.forecasts)
    features = evaluator.features(state, candidates[0])
    assert all(np.isfinite(list(features.values())))
    assert not any("truth" in key or "seed" in key or "split" in key or "group" in key for key in features)
    assert evaluator.delta(state, candidates[0], candidates[0]) == 0
    with pytest.raises(ValueError, match="Unpublished"):
        active_forecasts(state, (replace(scene.forecasts[0], published_at=1),))
    later = state.clone()
    later.now = 100
    assert active_forecasts(later, scene.forecasts) == ()


def examples():
    rows = []
    for group in range(5):
        for index in range(3):
            analytic = float(index)
            value = float(group * 2 + index * 4)
            rows.append({"source_group": str(group), "is_baseline": index == 0,
                         "features": {"timed_analytic_absolute": analytic, "route_length": float(index), "stock": float(group)},
                         "cost_mean": value, "delta_mean": float(index * 4), "timed_delta": analytic})
    return rows


@pytest.mark.parametrize("kind", ["direct", "residual"])
def test_frozen_small_models_zero_baseline_roundtrip_and_same_schema(kind):
    rows = examples()
    model = RidgeValueModel.fit(rows, kind, .001)
    restored = RidgeValueModel.from_dict(model.to_dict())
    baseline = rows[0]["features"]
    assert model.score_features(baseline, baseline) == 0
    for row in rows:
        assert restored.predict_value(row["features"]) == model.predict_value(row["features"])
    assert model.score_features(rows[2]["features"], baseline) == pytest.approx(8., abs=.01)
    with pytest.raises(ValueError, match="schema"):
        model.predict_value({**baseline, "future_truth": 1})


def test_fitting_requires_group_baselines_and_does_not_mutate_rows():
    rows = examples()
    before = repr(rows)
    RidgeValueModel.fit(rows, "residual")
    assert repr(rows) == before
    with pytest.raises(ValueError, match="baseline"):
        RidgeValueModel.fit([row for row in rows if not row["is_baseline"]], "residual")


def test_early_arrivals_consume_identified_forecast_without_future_access():
    scene = phase2_scenes(1, 0, 0, 0)[0]
    state = scene.initial.clone()
    forecast = replace(scene.forecasts[0], at=12, count=3)
    state.now = 10
    state.bags[f"{forecast.forecast_id}:1"] = Bag(f"{forecast.forecast_id}:1", forecast.node,
                                                 forecast.destination, 10, forecast.deadline)
    pending = active_forecasts(state, (forecast,))[0]
    assert pending.count == 2
    assert pending.unit_ids == (f"{forecast.forecast_id}:0", f"{forecast.forecast_id}:2")


def test_late_identified_forecast_persists_until_observation_cancel_or_ttl():
    scene = phase2_scenes(1, 0, 0, 0)[0]
    state = scene.initial.clone()
    state.now = 14
    forecast = replace(scene.forecasts[0], at=12, count=1)
    pending = active_forecasts(state, (forecast,))[0]
    assert pending.at == 15 and pending.count == 1
    cancellation = replace(forecast, count=0, published_at=13)
    assert active_forecasts(state, (forecast, cancellation)) == ()
    state.bags[f"{forecast.forecast_id}:0"] = Bag(f"{forecast.forecast_id}:0", forecast.node,
                                                forecast.destination, 14, forecast.deadline)
    assert active_forecasts(state, (forecast,)) == ()


def test_confirmatory_namespace_has_fresh_test_and_deployment_but_same_training():
    discovery = phase2_scenes(2, 1, 1, 1)
    confirmatory = phase2_scenes(2, 1, 1, 1, "confirm1")
    assert [s.source_group for s in discovery[:3]] == [s.source_group for s in confirmatory[:3]]
    assert not {s.source_group for s in discovery[3:]} & {s.source_group for s in confirmatory[3:]}
