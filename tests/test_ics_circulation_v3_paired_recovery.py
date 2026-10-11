"""Real leakage, precision, cache and incomplete-evidence recovery boundaries."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3 import run_paired_recovery as run
from scripts.experiments.ics_circulation_v3.model import Bag, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.nonlinear_learning import MLPConfig
from scripts.experiments.ics_circulation_v3.role_coverage import RoleQuota, collect_role_decisions


def rows():
    result = []
    for stream in run.PROTOCOL["streams"]:
        for node in ("S", "B"):
            for action in (0, 1):
                base = dict.fromkeys(run.FULL_FEATURE_NAMES, 0.)
                base.update(remaining_route_ticks=float(action), timed_analytic_absolute=float(action))
                physical = {**dict.fromkeys(run.PHYSICAL_FEATURE_NAMES, 0.), **base}
                physical["prefix_completes_delivery"] = float(action)
                result.append({"stream": stream, "owner": None, "source_group": f"{stream}:{node}",
                    "features23": base, "features31": physical, "is_baseline": action == 0,
                    "normal_ordinal": action, "actual_action_key": str(action), "source_node": node,
                    "role": "origin", "cost_mean": 3. - action, "delta_mean": -float(action), "timed_delta": float(action)})
    return result


def label(costs=None, *, node="B"):
    if costs is None:
        costs = np.asarray([[[10. + g + f / 10 for f in range(8)],
                             [8. + g + f / 10 for f in range(8)]] for g in range(4)])
    count = costs.shape[1]
    features = []
    for i in range(count):
        base = dict.fromkeys(run.FULL_FEATURE_NAMES, 0.)
        base["timed_analytic_absolute"] = float(i)
        features.append(base)
    branches = []
    for g in range(4):
        for c in range(count):
            for f in range(8):
                components = dict.fromkeys(run.COST_WEIGHTS, 0.)
                components["tray_wait"] = float(costs[g, c, f])
                branches.append({"group": g, "candidate": c, "future_index": f, "failed": False,
                    "cost_components": components, "total_cost": float(costs[g, c, f]), "future_sha256": run.digest([])})
    return {"identity": "one", "candidate_count": count, "actual_action_keys": [str(i) for i in range(count)],
        "proposals": [{} for _ in range(count)], "groups": 4, "futures_per_group": 8, "horizon_ticks": 20,
        "regime": "stress", "failures": [], "features_observable_only": features,
        "features_physical": [{**dict.fromkeys(run.PHYSICAL_FEATURE_NAMES, 0.), **f} for f in features],
        "paired_costs": costs.tolist(), "raw_branches": branches,
        "future_groups_offline_only": [{"tapes": [[] for _ in range(8)]} for _ in range(4)],
        "source_node": node, "role": "origin", "band": 0, "state": {"now": 0}, "checkpoint_sha256": "fixed"}


def test_held_out_role_features_and_opposite_labels_do_not_change_fits_or_normalization():
    original = rows()
    held = run.PROTOCOL["streams"][-1]
    changed = deepcopy(original)
    for row in changed:
        if row["stream"] == held:
            row["delta_mean"] = 0. if row["is_baseline"] else 1e9
            row["cost_mean"] = -1e12
            row["features23"]["remaining_route_ticks"] = 1e15
            row["features31"]["prefix_completes_delivery"] = 1e13
    for schema in run.SCHEMAS:
        for kind in run.KINDS:
            cfg = MLPConfig(epochs=3, seed=17, learning_rate=.01, l2=.001)
            left, bounds, _ = run.fit_model(original, held, schema, kind, 17, config=cfg)
            right, changed_bounds, _ = run.fit_model(changed, held, schema, kind, 17, config=cfg)
            assert left.to_dict() == right.to_dict()
            assert bounds == changed_bounds
            assert bounds["remaining_route_ticks"]["maximum"] == 1.


def test_recovery_rows_reject_held_out_or_another_model_even_with_identical_features():
    source = rows()
    held = run.PROTOCOL["streams"][-1]
    owner = run.model_name(held, "physical31", "paired_direct", 17)
    recovered = [dict(r, source_group="r1:" + r["source_group"], owner=owner) for r in source if r["stream"] != held]
    cfg = MLPConfig(epochs=1, seed=17)
    model, _, fold = run.fit_model(source, held, "physical31", "paired_direct", 17,
                                  r1_rows=recovered, owner=owner, config=cfg)
    assert fold["r1_training_rows"] == 12
    assert all(not group.startswith(held) for group in model.training_metadata["source_groups"])
    for bad in (dict(recovered[0], stream=held), dict(recovered[0], owner="another_model")):
        with pytest.raises(ValueError, match="three training streams only"):
            run.fit_model(source, held, "physical31", "paired_direct", 17,
                          r1_rows=[*recovered[1:], bad], owner=owner, config=cfg)


def test_raw_components_common_future_pairing_hidden_features_and_missing_branch_are_checked():
    result = run.label_rows(label(), run.PROTOCOL["streams"][0])
    assert result[0]["delta_mean"] == result[0]["timed_delta"] == 0
    assert result[1]["delta_mean"] == pytest.approx(-2.)
    for change, message in ((lambda l: l["raw_branches"].pop(), "Missing or duplicated"),
        (lambda l: l["raw_branches"][0]["cost_components"].update(tray_wait=99), "physical components"),
        (lambda l: l["raw_branches"][0].update(future_sha256="other_tape"), "same indexed future"),
        (lambda l: l["features_physical"][0].update(truth_shift=1), "hidden fields forbidden")):
        item = label()
        change(item)
        with pytest.raises(ValueError, match=message):
            run.label_rows(item, run.PROTOCOL["streams"][0])


def test_precision_gate_is_strict_on_ties_and_singletons_cannot_dilute_failure():
    # First two draws tie, all eight prefer candidate 1; choosing candidate 1
    # would be membership-correct but the estimated optimum sets differ.
    costs = np.full((4, 2, 8), 10.)
    costs[:, 1, 2:] = 9.
    bad = label(costs)
    singles = [label(np.zeros((4, 1, 8))) for _ in range(100)]
    result = run.noise_gate([bad, *singles])
    assert result["r1_groups"] == 4
    assert result["subsets"]["source_B"]["agreement_denominator"] == 4
    assert result["subsets"]["source_B"]["agreement_rate"] == 0
    assert result["zero_single_candidate_states"] == 100


def test_precision_gate_checks_two_group_budget_and_reports_no_new_role_guarantee():
    costs = np.full((4, 2, 8), 10.)
    costs[:2, 1, :] = 9.
    costs[2:, 1, :] = 12.
    result = run.noise_gate([label(costs)])
    assert result["subsets"]["all"]["agreement_rate"] == 1.
    assert result["subsets"]["all"]["two_group_agreement_rate"] == 0.
    assert result["subsets"]["all"]["last_two_groups_mean_regret"] == 2.
    assert result["r1_groups"] == 4
    assert run.noise_gate([label(node="S")])["r1_groups"] == 4  # B support absent.


def test_held_out_labels_cannot_change_fold_precision_or_role_sampling_budget():
    held = run.PROTOCOL["streams"][-1]
    original = []
    for stream in run.PROTOCOL["streams"]:
        for node in ("S", "B"):
            item = label(node=node)
            item["identity"] = stream + ":" + node
            original.append(item)
    changed = deepcopy(original)
    for item in changed:
        if item["identity"].startswith(held + ":"):
            item["paired_costs"] = np.random.default_rng(19).normal(size=(4, 2, 8)).tolist()
            item["source_node"], item["role"] = "C", "arrival_at_destination"
    before, after = run.fold_precision(original, held), run.fold_precision(changed, held)
    assert before == after and before["r1_groups"] == 2
    assert run.sample_groups({"source_node": "B", "role": "origin"}, 2, before["observed_node_role_support"]) == 2
    assert run.sample_groups({"source_node": "C", "role": "arrival_at_destination"}, 2, before["observed_node_role_support"]) == 4


def test_sample_local_exact_cache_preserves_physical_costs_and_all_requested_denominators():
    initial = Snapshot(0, Network({"A": Node("A", "A", "A")}, {}),
                       {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "A", 0, 1)})
    scene = SimpleNamespace(name="cache", initial=initial, forecasts=(), future_bags=(), horizon=2)
    collection = collect_role_decisions(scene, run.SPEC,
        quota=RoleQuota(nodes=("A",), max_samples=1), source_group="cache_test")
    sample = collection.samples[0]
    timed = run.PublishedRoutingSelector(run.SPEC, ())
    manifest = {"implementation": "PublishedRoutingSelector", "kind": "timed"}
    cached = run.cached_label(sample, (), groups=4, continuation_selector=timed, selector_manifest=manifest)
    uncached = run.cached_label(sample, (), groups=4, continuation_selector=timed, selector_manifest=manifest, cache=False)
    assert cached["paired_costs"] == uncached["paired_costs"]
    assert cached["future_groups_offline_only"] == uncached["future_groups_offline_only"]
    assert cached["requested_branches"] == uncached["requested_branches"] == len(sample["pool"]) * 32
    assert cached["actual_unique_branch_calls"] == len(sample["pool"])
    assert cached["cache_reused_branches"] == len(sample["pool"]) * 31
    assert uncached["actual_unique_branch_calls"] == cached["requested_branches"]
    assert run.label_rows(cached, "test") == run.label_rows(uncached, "test")


def test_incomplete_labels_existing_outputs_and_missing_recovery_stage_refuse_before_training(tmp_path, monkeypatch):
    monkeypatch.setattr(run.MLPValueModel, "fit", lambda *a, **k: pytest.fail("no fit authorized"))
    with pytest.raises(ValueError, match="Complete frozen R0"):
        run.run_r0(tmp_path / "new", tmp_path / "missing")
    assert not (tmp_path / "new").exists()
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / "sentinel").write_text("preserve")
    with pytest.raises(ValueError, match="overwritten"):
        run.run_r0(folder, tmp_path / "missing")
    assert (folder / "sentinel").read_text() == "preserve"
    monkeypatch.setattr(run, "validate_source", lambda p: None)
    with pytest.raises(ValueError, match="Stage incomplete"):
        run.run_evaluation(tmp_path / "new")


def test_unfinished_task_remains_in_full_episode_denominator():
    initial = Snapshot(0, Network({n: Node(n, n, n) for n in "AB"}, {}),
                       {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "B", 0, 1)})
    result = run.deployment(SimpleNamespace(initial=initial, forecasts=(), future_bags=(), horizon=2))
    assert result["metrics"]["scheduled_bags"] == 1
    assert result["metrics"]["completed"] == result["metrics"]["on_time"] == 0
    assert result["metrics"]["uncompleted"] == ["b"]


def test_runtime_schemas_use_only_published_forecasts_and_retain_reference_zero():
    from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
    from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
    from scripts.experiments.ics_circulation_v3.phase4_control import GeneratorFactory
    state = feedback_scene().initial
    candidates = GeneratorFactory(run.SPEC)().generate(state, "initial", "loaded", k=4)
    later = RoutingDemandForecast("later", "B", "C", 12, 30, published_at=10)
    for schema, names in run.SCHEMAS.items():
        class Frozen:
            feature_names = names
            def score_features(self, f, reference):
                return f["timed_analytic_absolute"] - reference["timed_analytic_absolute"]
        bounds = {n: {"minimum": -1e9, "maximum": 1e9} for n in names}
        a = run.RecoverySelector(Frozen(), bounds, (later,), schema=schema)
        b = run.RecoverySelector(Frozen(), bounds, (replace(later, node="S", count=50),), schema=schema)
        assert a(state, candidates) == b(state, candidates)
        assert a.history == b.history and a.history[0]["reference_zero"]
        assert a.history[0]["published_forecasts"] == []
