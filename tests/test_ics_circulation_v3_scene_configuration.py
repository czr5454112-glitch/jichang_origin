from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3 import run_scene_configuration as runner
from scripts.experiments.ics_circulation_v3.model import Tray
from scripts.experiments.ics_circulation_v3.phase2_scenarios import make_scene, phase2_scenes
from scripts.experiments.ics_circulation_v3.scene_configuration import (
    CONFIGURATION_IDS, FEATURE_NAMES, SceneSelector, evaluate_stored, fit_selectors,
    initial_features, select_on_validation,
)


def examples(split="train", *, inverted=False):
    rows = []
    for index in range(16):
        left = index < 8
        if inverted:
            left = not left
        features = dict.fromkeys(FEATURE_NAMES, 0.)
        features["target_static_travel_ticks"] = float(index)
        rows.append({"source_group": f"{split}:{index:02d}", "split": split, "features": features,
                     "costs": dict(zip(CONFIGURATION_IDS, (0. if left else 10., 10. if left else 0., 20., 30.)))})
    return rows


def test_initial_features_need_only_visible_view_and_published_forecasts():
    scene = make_scene(2, "feature_audit")
    # This object has no future() or truth_shift field. Accessing either would
    # break feature extraction rather than accidentally expose hidden labels.
    visible_only = SimpleNamespace(initial=scene.initial, forecasts=scene.forecasts,
                                   horizon=scene.horizon, target_bag=scene.target_bag)
    values = runner._observable(visible_only)
    assert set(values) == set(FEATURE_NAMES)
    assert not any(part in name for name in values for part in ("truth", "seed", "source_group", "future"))
    altered_truth = replace(scene, truth_shift=10_000)
    assert runner._observable(altered_truth) == values
    changed = scene.initial.clone()
    changed.trays["new_visible_empty"] = Tray("new_visible_empty", "B")
    more_stock = initial_features(changed, scene.forecasts, target_bag_id=scene.target_bag, horizon=scene.horizon)
    assert more_stock["destination_empty_stock"] == values["destination_empty_stock"] + 1
    with pytest.raises(ValueError, match="Unpublished"):
        initial_features(scene.initial, (replace(scene.forecasts[0], published_at=1),),
                         target_bag_id=scene.target_bag, horizon=scene.horizon)


def test_all_configuration_source_groups_are_fresh_and_disjoint():
    groups = runner.configuration_scenes()
    assert {key: len(value) for key, value in groups.items()} == {"train": 80, "validation": 20, "test": 40}
    identifiers = [scene.source_group for scenes in groups.values() for scene in scenes]
    assert len(set(identifiers)) == 140
    for namespace in ("", "confirm1", "phase3confirm", "phase3smoke"):
        assert not set(identifiers) & {scene.source_group for scene in phase2_scenes(evaluation_namespace=namespace)}
    smoke = {scene.source_group for scenes in runner.configuration_scenes(smoke=True).values() for scene in scenes}
    assert not set(identifiers) & smoke


def test_stump_uses_training_thresholds_and_leaf_actions_and_is_order_deterministic():
    rows = examples()
    before = deepcopy(rows)
    fixed, stump = fit_selectors(rows, min_leaf_groups=8)
    assert rows == before
    assert fixed.left_configuration == CONFIGURATION_IDS[0]
    assert stump.split_feature == "target_static_travel_ticks" and stump.threshold == 7.5
    assert stump.left_configuration == CONFIGURATION_IDS[0] and stump.right_configuration == CONFIGURATION_IDS[1]
    assert stump.training_metadata["leaf_group_counts"] == [8, 8]
    assert stump.training_metadata["training_mean_cost"] == 0.
    reversed_fixed, reversed_stump = fit_selectors(list(reversed(rows)), min_leaf_groups=8)
    assert reversed_fixed.to_dict() == fixed.to_dict() and reversed_stump.to_dict() == stump.to_dict()
    restored = SceneSelector.from_dict(json.loads(json.dumps(stump.to_dict())))
    assert [restored.select(row["features"]) for row in rows] == [stump.select(row["features"]) for row in rows]


def test_validation_gates_without_refitting_and_opposite_test_costs_cannot_change_choice():
    fixed, stump = fit_selectors(examples())
    frozen = fixed.to_dict(), stump.to_dict()
    winner, decision = select_on_validation(fixed, stump, examples("validation", inverted=True))
    assert decision["selected"] == "best_fixed" and winner is fixed
    assert (fixed.to_dict(), stump.to_dict()) == frozen
    # Here the held-out table strongly favors the rejected stump. Evaluating it
    # must neither revisit the gate nor alter the trained split/actions.
    test = examples("test")
    assert evaluate_stored(test, stump)["mean_cost"] == 0.
    assert evaluate_stored(test, winner)["mean_cost"] == 5.
    assert decision["selected"] == "best_fixed" and (fixed.to_dict(), stump.to_dict()) == frozen
    tie_validation = examples("validation")
    for row in tie_validation:
        row["costs"] = dict.fromkeys(CONFIGURATION_IDS, 2.)
    assert select_on_validation(fixed, stump, tie_validation)[0] is fixed


def test_validation_can_choose_stump_and_never_moves_threshold_for_new_feature_values():
    fixed, stump = fit_selectors(examples())
    validation = examples("validation")
    for row in validation:
        row["features"]["target_static_travel_ticks"] += 100
    before = stump.to_dict()
    select_on_validation(fixed, stump, validation)
    assert stump.to_dict() == before and stump.threshold == 7.5
    assert select_on_validation(fixed, stump, examples("validation"))[0] is stump


@pytest.mark.parametrize("bad_split", ["validation", "test"])
def test_fit_rejects_held_out_labels(bad_split):
    with pytest.raises(ValueError, match="Only train"):
        fit_selectors(examples(bad_split))


def test_incomplete_full_information_and_duplicate_groups_are_not_silently_dropped():
    rows = examples()
    rows[0]["costs"][CONFIGURATION_IDS[2]] = None
    with pytest.raises(ValueError, match="cannot be dropped"):
        fit_selectors(rows)
    rows[0]["costs"].pop(CONFIGURATION_IDS[2])
    with pytest.raises(ValueError, match="all four"):
        fit_selectors(rows)
    with pytest.raises(ValueError, match="unique"):
        fit_selectors(examples() + [examples()[0]])
    fixed, stump = fit_selectors(examples())
    validation = examples("validation")
    validation[0]["source_group"] = examples()[0]["source_group"]
    with pytest.raises(ValueError, match="overlap"):
        select_on_validation(fixed, stump, validation)


def test_stored_episode_lookup_counts_failures_and_retains_bag_denominators(monkeypatch):
    fixed, _ = fit_selectors(examples())
    rows = examples("test")
    for row in rows:
        row["outcomes"] = {name: {"all_bag_denominator": 3, "completed": 2, "uncompleted": 1, "on_time": 1}
                           for name in CONFIGURATION_IDS}
    rows[0]["costs"][fixed.left_configuration] = None
    monkeypatch.setattr(runner, "build_engine", lambda *_: pytest.fail("Stored selector evaluation must not simulate"))
    metrics = runner._evaluate(rows, fixed)
    assert metrics["source_groups"] == 16 and metrics["cost_available_count"] == 15
    assert metrics["failed_selected_episodes"] == 1 and metrics["additional_simulation_calls"] == 0
    assert metrics["all_bag_denominator"] == 48 and metrics["uncompleted"] == 16
    assert metrics["completed"] == 32 and metrics["on_time"] == 16


def test_small_training_set_falls_back_without_relaxing_minimum_leaf_size():
    fixed, stump = fit_selectors(examples()[:8], min_leaf_groups=8)
    assert stump.kind == "stump_fallback_fixed" and stump.split_feature is None
    assert stump.left_configuration == fixed.left_configuration


def test_runner_freezes_choices_before_fresh_test_costs_and_counts_each_return_once(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BASE", tmp_path / "empty_history")
    calls = []

    def collect(scenes, output, split):
        if split == "test":
            assert (output / "frozen_selectors.json").exists()
            assert (output / "test_choices_before_episode_labels.jsonl").exists()
        rows, episodes = [], []
        for scene in scenes:
            features = runner._observable(scene)
            outcomes = {name: {"all_bag_denominator": 3, "completed": 2, "uncompleted": 1, "on_time": 1}
                        for name in CONFIGURATION_IDS}
            rows.append({"source_group": scene.source_group, "split": split, "features": features,
                         "costs": dict(zip(CONFIGURATION_IDS, (2., 1., 3., 4.))), "outcomes": outcomes})
            for name in CONFIGURATION_IDS:
                calls.append((scene.source_group, name))
                episodes.append({"status": "complete", "invariant_checks": 1, "episode_wall_ms": 0.})
        return rows, episodes

    monkeypatch.setattr(runner, "collect_episodes", collect)
    summary = runner.run(tmp_path / "run", smoke=True)
    assert summary["episode_calls"] == summary["expected_episode_calls"] == 64
    assert len(calls) == len(set(calls)) == 64
    assert summary["additional_evaluation_simulations"] == 0
    assert summary["source_groups"] == {"train": 8, "validation": 4, "test": 4}
    assert summary["validation_gate"]["selected"] == "best_fixed"
    assert summary["test_metrics"]["validation_selected"]["all_bag_denominator"] == 12


def test_existing_output_and_unknown_or_nonfinite_features_are_rejected(tmp_path):
    (tmp_path / "prior.json").write_text("{}")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        runner.run(tmp_path)
    fixed, _ = fit_selectors(examples())
    features = examples()[0]["features"]
    with pytest.raises(ValueError, match="schema"):
        fixed.select({**features, "truth_shift": 8.})
    with pytest.raises(ValueError, match="finite"):
        fixed.select({**features, "target_static_travel_ticks": float("nan")})
