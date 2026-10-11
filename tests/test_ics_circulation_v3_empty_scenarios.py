from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.empty_factorial import FactorialEmptyPrebalancer
from scripts.experiments.ics_circulation_v3.empty_scenarios import (
    PublicScenarioSettings, ScenarioEmptyPrebalancer, build_scenario_empty_engine, public_scenarios)
from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.joint_feedback import published_proxy
from scripts.experiments.ics_circulation_v3.empty_improvement import EmptyImprovementSettings


def fixture():
    scene = feedback_scene()
    proxy = published_proxy(scene.initial, scene.forecasts, scene.initial.now + 40)
    assert proxy
    return scene, proxy


def test_draws_are_common_and_deterministic_from_public_fields_only():
    scene, proxy = fixture()
    settings = PublicScenarioSettings(count=32, seed=17)
    first = public_scenarios(scene.initial, proxy, settings)
    assert first == public_scenarios(scene.initial.clone(), tuple(reversed(proxy)), settings)
    assert len(first) == 32
    assert all(b.arrival > scene.initial.now and b.bag_id not in scene.initial.bags for row in first for b in row)
    assert all({b.bag_id for b in row} <= {b.bag_id for b in proxy} for row in first)


def test_observed_tasks_cannot_be_cancelled_or_resampled():
    scene, proxy = fixture()
    with pytest.raises(ValueError, match="unobserved"):
        public_scenarios(scene.initial, (*proxy, next(iter(scene.initial.bags.values()))), PublicScenarioSettings())
    with pytest.raises(ValueError, match="duplicate"):
        public_scenarios(scene.initial, (proxy[0], proxy[0]), PublicScenarioSettings())


def test_protected_proxy_keeps_identity_and_od_across_all_draws():
    scene, proxy = fixture()
    protected = replace(proxy[0], protected=True)
    rows = public_scenarios(scene.initial, (protected,), PublicScenarioSettings(64, 29))
    assert all(len(row) == 1 and row[0].protected and row[0].bag_id == protected.bag_id
               and row[0].origin == protected.origin and row[0].destination == protected.destination for row in rows)


def test_unreachable_reversal_is_rejected_not_silently_dropped():
    scene, proxy = fixture()
    state = scene.initial.clone()
    # Leave the forecast origin with no positive-capacity incoming edge.
    state.network = replace(state.network, edges={k: e for k, e in state.network.edges.items()
        if e.target != proxy[0].origin})
    with pytest.raises(ValueError, match="return path"):
        public_scenarios(state, proxy, PublicScenarioSettings())


def test_duplicate_scenarios_preserve_weight_and_count_physics_once(monkeypatch):
    scene, proxy = fixture()
    import scripts.experiments.ics_circulation_v3.empty_scenarios as module
    monkeypatch.setattr(module, 'public_scenarios', lambda *args: ((), (), proxy))
    calls = []
    def fake(self, state, seq, forecasts, future, next_slow):
        calls.append(future)
        value = float(len(future) * 9)
        return {'status': 'complete', 'proxy_cost': value, 'cost_components': {'tray_wait': value},
                'completed': len(future), 'search_calls': 2, 'search_work': 7, 'ticks': 40,
                'wall_seconds': .1, 'cpu_seconds': .1}
    monkeypatch.setattr(FactorialEmptyPrebalancer, '_score', fake)
    row = ScenarioEmptyPrebalancer()._score(scene.initial, (), scene.forecasts, proxy, 2)
    assert row['proxy_cost'] == len(proxy) * 3
    assert row['cost_components']['tray_wait'] == row['proxy_cost']
    assert row['requested_scenarios'] == 3 and row['physical_proxy_calls'] == len(calls) == 2
    assert row['exact_duplicate_reuses'] == 1 and row['search_calls'] == 4 and row['search_work'] == 14


def test_any_partial_scenario_excludes_entire_action_mean(monkeypatch):
    scene, proxy = fixture()
    import scripts.experiments.ics_circulation_v3.empty_scenarios as module
    monkeypatch.setattr(module, 'public_scenarios', lambda *args: ((), proxy))
    def fake(self, state, seq, forecasts, future, next_slow):
        return {'status': 'budget_exhausted' if future else 'complete', 'proxy_cost': None if future else 0.,
                'search_calls': 2, 'search_work': 7, 'ticks': 3, 'wall_seconds': .1, 'cpu_seconds': .1}
    monkeypatch.setattr(FactorialEmptyPrebalancer, '_score', fake)
    row = ScenarioEmptyPrebalancer()._score(scene.initial, (), scene.forecasts, proxy, 2)
    assert row['status'] == 'scenario_projection_incomplete' and row['proxy_cost'] is None
    assert row['physical_proxy_calls'] == 2


def test_hidden_actual_tape_does_not_change_scenarios_first_action_or_value():
    scene, _ = fixture()
    records = []
    for source in (scene, replace(scene, future_bags=())):
        engine = build_scenario_empty_engine(source, scenarios=PublicScenarioSettings(8, 43),
            settings=EmptyImprovementSettings(score_horizon=20, max_rollouts=2))
        engine.advance(scene.initial.now + 1)
        records.append(engine.slow_controller.history[0])
    left, right = records
    assert left['proposals'] == right['proposals']
    def semantic(record):
        return [(r['proxy_cost'], r['scenarios'], r['search_calls'], r['search_work'])
                for r in record['diagnostics']['scored_actions']]
    assert semantic(left) == semantic(right)
