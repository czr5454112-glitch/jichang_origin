from dataclasses import asdict
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_full_cycle import branch_full_cycle, compare_old_result
from scripts.experiments.ics_circulation_v3.network_role_labels import SearchBudget, collect_network_decisions
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation, checkpoint_fingerprint
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache, routing_cache_state
from scripts.experiments.ics_circulation_v3.run_same_zone_supply import exact_json_value, planned_rows
from scripts.experiments.ics_circulation_v3.same_zone_experiment import (
    POLICIES, install_supply_policy, run_observed_cycle, saved_error_tapes)


def scene_fixture(forecasts=(), future=()):
    net = Network({n: Node(n, "zone", "owner", 2) for n in ("L", "J", "U")},
        {"LJ": Edge("LJ", "L", "J", 2), "JU": Edge("JU", "J", "U", 2),
         "UL": Edge("UL", "U", "L", 2)})
    state = Snapshot(0, net, {"tray": Tray("tray", "L", "loaded", "seen")},
                     {"seen": Bag("seen", "L", "U", 0, 30)})
    return SimpleNamespace(name="cross_cycle", initial=state, forecasts=forecasts,
                           future_bags=future, horizon=12)


def actual_sample():
    scene = scene_fixture()
    result = collect_network_decisions(scene, spec=ControlSpec(planning_horizon=20, predictive=True),
                                       budget=SearchBudget(40, 10000, 10), bands=(0,))
    return result["samples"][0]


def initial_engine(scene):
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags,
                        ControlSpec(planning_horizon=20, predictive=True))
    enable_replay_cache(base)
    return CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)


def test_fixed_case_denominators_include_budget_control_and_repeat_nominal():
    assert len(planned_rows("mechanism")) == 6
    assert len(planned_rows("nominal_pilot")) == 9
    assert len(planned_rows("full")) == 81
    for stage in ("mechanism", "nominal_pilot", "full"):
        rows = planned_rows(stage)
        assert len({r["case_id"] for r in rows}) == len(rows)
        assert set(r["policy"] for r in rows) == set(POLICIES)
    assert {r["case_id"] for r in planned_rows("nominal_pilot")} <= {r["case_id"] for r in planned_rows("full")}
    with pytest.raises(ValueError):
        planned_rows("pick_successes")


def test_fixed_error_tapes_keep_protected_bags_and_slack_and_are_reproducible():
    future = tuple(Bag(f"b{i}", "L", "U", 20 + i, 80 + i, protected=i % 2 == 0) for i in range(20))
    scene = scene_fixture(future=future)
    tapes = saved_error_tapes(scene)
    assert tapes == saved_error_tapes(scene)
    assert len(tapes) == 8
    originals = {b.bag_id: b for b in future}
    protected = {b.bag_id: b for b in future if b.protected}
    for tape in tapes:
        assert {b.bag_id: b for b in tape if b.protected} == protected
        for bag in tape:
            old = originals[bag.bag_id]
            assert (bag.origin, bag.destination) == (old.origin, old.destination)
            assert bag.deadline - bag.arrival == old.deadline - old.arrival
            assert bag.arrival - old.arrival in (-2, 0, 2)
    assert any(len(tape) < len(future) for tape in tapes)


def test_budget_control_preserves_real_cursor_clock_state_and_cache():
    sample = actual_sample()
    original = checkpoint_fingerprint(sample["checkpoint"])
    engine = CursorSimulation.from_checkpoint(sample["checkpoint"])
    state, cursor = asdict(engine.state), asdict(engine._cursor)
    clock, cache = engine.slow_controller.next_trigger_at, routing_cache_state(engine)
    wrapper = engine.slow_controller
    inner = wrapper.controller
    install_supply_policy(engine, "old64")
    assert engine.slow_controller is wrapper and wrapper.controller is inner
    assert inner.max_candidates == 64
    assert engine.slow_controller.next_trigger_at == clock
    assert asdict(engine._cursor) == cursor and asdict(engine.state) == state
    assert routing_cache_state(engine) == cache
    assert checkpoint_fingerprint(sample["checkpoint"]) == original


def test_logging_preserves_original_checkpoint_physics_search_and_private_cache():
    sample = actual_sample()
    checkpoint, candidate = sample["checkpoint"], sample["pool"][0]
    before = checkpoint_fingerprint(checkpoint)
    old = branch_full_cycle(checkpoint, candidate, ())
    engine = CursorSimulation.from_checkpoint(checkpoint)
    install_supply_policy(engine, "old32")
    new = run_observed_cycle(engine, checkpoint.state.bags,
                             minimum_observation_at=checkpoint.state.now + 80,
                             forced_candidate=candidate)
    assert new["status"] == old["status"] == "controller_quiescent"
    assert new["stopped_at"] == old["stopped_at"]
    assert compare_old_result(old["result"], new["result"])["equal"]
    assert new["searches"] == old["searches"]
    assert new["cache_before"] == old["cache_before"]
    assert checkpoint_fingerprint(checkpoint) == before
    assert all(c["time"] == c["snapshot_before"]["now"] for c in new["slow_calls"])
    assert new["milestones"]["controller_quiescent"]["time"] < new["stopped_at"]


def test_ghost_forecast_is_visible_only_on_actual_published_slow_call():
    forecasts = (RoutingDemandForecast("ghost", "L", "U", 30, 100, published_at=20),)
    scene = scene_fixture(forecasts=forecasts)
    outcome = run_observed_cycle(initial_engine(scene), {"seen"}, minimum_observation_at=12)
    assert outcome["status"] == "controller_quiescent"
    assert outcome["milestones"]["controller_quiescent"]["time"] >= 83
    assert not any(c["published_forecasts"] for c in outcome["slow_calls"] if c["time"] < 20)
    assert any(c["published_forecasts"] for c in outcome["slow_calls"] if c["time"] >= 20)
    assert set(outcome["result"]["final_snapshot"]["bags"]) == {"seen"}
    assert outcome["milestones"]["task_complete"]["time"] < 20


def test_saved_future_and_query_censor_remain_in_expected_denominator():
    scene = scene_fixture(future=(Bag("later", "L", "U", 30, 60),))
    outcome = run_observed_cycle(initial_engine(scene), {"seen", "later"},
        minimum_observation_at=12, budget=SearchBudget(1, 10000, 10))
    assert outcome["status"] == "budget_censored"
    assert outcome["last_cycle_state"]["expected_task_count"] == 2
    assert "later" in outcome["last_cycle_state"]["unobserved_task_ids"]
    assert not outcome["last_cycle_state"]["task_complete"]
    assert outcome["search_calls"] == 1


def test_persisted_private_cache_compares_exactly_after_json_sequence_encoding():
    sample = actual_sample()
    cache = routing_cache_state(CursorSimulation.from_checkpoint(sample["checkpoint"]))
    persisted = json.loads(json.dumps(cache))
    assert persisted != cache  # Real topology signatures contain Python tuples.
    assert exact_json_value(persisted, cache)


def test_json_cache_comparison_rejects_any_changed_cache_entry():
    sample = actual_sample()
    cache = routing_cache_state(CursorSimulation.from_checkpoint(sample["checkpoint"]))
    changed = deepcopy(json.loads(json.dumps(cache)))
    changed["fast_cache"]["entries_lru_oldest_first"][0]["network_signature"][0][0][2] = "changed permission"
    assert not exact_json_value(changed, cache)
    changed = deepcopy(json.loads(json.dumps(cache)))
    changed["fast_cache_sha256"] = "changed cache digest"
    assert not exact_json_value(changed, cache)
