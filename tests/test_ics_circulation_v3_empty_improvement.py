from dataclasses import asdict, replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.empty_improvement import (
    EmptyImprovementSettings, OneStepEmptyPrebalancer,
    build_empty_improvement_engine, slow_after_context,
)
from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.prebalance import PredictivePrebalancer
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory, enable_replay_cache
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation


def controller(settings=None, spec=None):
    spec = spec or ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    factory = ReplayRegionalFactory(spec.planning_horizon, spec.expansion_limit,
        spec.static_path_limit, spec.dynamic_local, spec.local_label_limit)
    return OneStepEmptyPrebalancer(spec=spec, settings=settings or EmptyImprovementSettings(),
                                  generator_factory=factory)


def small_state():
    nodes = {n: Node(n, n, n, capacity=6) for n in ("A", "B", "C")}
    edges = tuple(Edge(a+b, a, b, 1) for a in nodes for b in nodes if a != b)
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
        {"a": Tray("a", "A"), "b": Tray("b", "C")}, {})


def forecasts():
    return (RoutingDemandForecast("need", "B", "A", 4, 12, count=2),)


def plan(ctrl, state, fcasts):
    ctrl.set_slow_context(state.now, state.now + ctrl.spec.slow_period)
    return ctrl.plan(state, fcasts)


def test_requires_actual_slow_context_and_published_forecasts():
    ctrl, state = controller(), small_state()
    with pytest.raises(ValueError, match="actual slow trigger"):
        ctrl.plan(state, forecasts())
    with pytest.raises(ValueError, match="unpublished"):
        plan(ctrl, state, (replace(forecasts()[0], published_at=1),))
    with pytest.raises(TypeError):
        ctrl.plan(state, forecasts(), future_bags=())
    with pytest.raises(ValueError, match="future trigger"):
        ctrl.set_slow_context(1, 1)


@pytest.mark.parametrize("bad", (1, 0, True, 2.5))
def test_rollout_budget_reserves_two_mandatory_branches(bad):
    with pytest.raises(ValueError):
        EmptyImprovementSettings(max_rollouts=bad)


@pytest.mark.parametrize("order,index", (("route_then_prebalance", 4), ("prebalance_then_route", 2)))
def test_public_projection_cursor_is_immediately_after_slow(order, index):
    spec = ControlSpec(coordination_order=order)
    ctx = slow_after_context(spec, 8)
    assert ctx.cursor.stage_index == index
    assert ctx.next_slow_trigger_at == 8
    assert ctx.cursor.pending_options is None


def test_greedy_entire_sequence_is_mandatory_even_beyond_alternative_depth():
    state = small_state()
    ctrl = controller(EmptyImprovementSettings(max_rollouts=2, max_transfer_depth=1, score_horizon=14))
    before = state.clone()
    expected = PredictivePrebalancer(planning_horizon=20, planning_budget_ms=None,
        generator_factory=ctrl.generator_factory).plan(state, forecasts())
    result = plan(ctrl, state, forecasts())
    rows = result.diagnostics["scored_actions"]
    assert len(expected.proposals) == 2
    assert rows[0]["kind"] == "greedy_incumbent"
    assert rows[0]["proposals"] == [asdict(p) for p in expected.proposals]
    assert rows[1]["kind"] == "no_transfer" and rows[1]["proposals"] == []
    assert all(row["status"] == "complete" for row in rows)
    assert state == before
    assert result.diagnostics["rollout_calls"] == 2


def test_equal_proxy_cost_preserves_original_greedy_ordinal_zero():
    class EqualScore(OneStepEmptyPrebalancer):
        def _score(self, snapshot, sequence, forecasts, proxy, next_slow):
            return {"status": "complete", "proxy_cost": 1.0, "proposals": [asdict(p) for p in sequence]}
    base = controller(EmptyImprovementSettings(max_rollouts=12))
    ctrl = EqualScore(spec=base.spec, settings=base.settings, generator_factory=base.generator_factory)
    result = plan(ctrl, small_state(), forecasts())
    assert result.diagnostics["selected_action_index"] == 0
    assert not result.diagnostics["actual_sequence_changed"]


def test_all_proxy_budget_failures_keep_legal_greedy_and_never_rank_partial_cost():
    ctrl = controller(EmptyImprovementSettings(max_rollouts=2, branch_search_calls=1, score_horizon=16))
    result = plan(ctrl, small_state(), forecasts())
    assert result.diagnostics["fallback_to_greedy"]
    assert result.diagnostics["selected_proxy_cost"] is None
    rows = result.diagnostics["scored_actions"]
    assert all(row["status"] == "budget_exhausted" and row["proxy_cost"] is None for row in rows)
    assert all(row["search_calls"] == 1 for row in rows)
    state = small_state()
    for candidate in result.proposals:
        assert ExecutionValidator().commit(state, candidate).accepted


def test_empty_visible_demand_has_proven_identical_action_omission():
    result = plan(controller(), small_state(), ())
    diag = result.diagnostics
    assert result.proposals == ()
    assert diag["status"] == "identical_no_demand_action"
    assert diag["rollout_calls"] == 0 and diag["mandatory_identical_actions_not_simulated"] == 2
    assert "truth" not in diag["omitted_projection_reason"]


def test_unadmitted_protected_load_blocks_extra_domain_without_erasing_incumbent():
    state = small_state()
    state.bags["hard"] = Bag("hard", "A", "B", 0, 0, protected=True)
    state.trays["hard_tray"] = Tray("hard_tray", "A", "loaded", "hard")
    result = plan(controller(EmptyImprovementSettings(max_rollouts=24, score_horizon=8)), state, forecasts())
    assert result.diagnostics["unadmitted_protected_bags"] == ["hard"]
    assert result.diagnostics["proposal_search_calls"] == 0
    assert [r["kind"] for r in result.diagnostics["scored_actions"]] == ["greedy_incumbent", "no_transfer"]


def test_pool_interleaves_donors_before_departure_variants():
    ctrl = controller(EmptyImprovementSettings(max_rollouts=6, max_pool_per_state=2))
    result = plan(ctrl, small_state(), (replace(forecasts()[0], count=1),))
    rows = result.diagnostics["scored_actions"]
    single = [r["proposals"][0] for r in rows[2:] if len(r["proposals"]) == 1]
    assert {p["tray_id"] for p in single} == {"a", "b"}
    assert result.diagnostics["proposal_pool_discarded_valid"] > 0
    assert result.diagnostics["proposal_search_calls"] <= ctrl.settings.max_search_calls


def test_greedy_single_action_can_still_be_extended_to_depth_two():
    state = small_state()
    ctrl = controller(EmptyImprovementSettings(max_rollouts=24, score_horizon=20))
    ctrl.max_proposals = 1  # A deliberately bounded incumbent is still expandable.
    result = plan(ctrl, state, forecasts())
    assert len(result.diagnostics["scored_actions"][0]["proposals"]) == 1
    assert any(len(row["proposals"]) == 2 for row in result.diagnostics["scored_actions"])


@pytest.mark.parametrize("order", ("route_then_prebalance", "prebalance_then_route"))
def test_builder_is_causal_and_checkpoint_restores_complete_policy(order):
    scene = feedback_scene()
    spec = ControlSpec(routing="timed", planning_horizon=20, slow_period=2, coordination_order=order)
    engine = build_empty_improvement_engine(scene, spec, settings=EmptyImprovementSettings(max_rollouts=2, score_horizon=20))
    engine.advance(5)
    resumed = Simulation.from_checkpoint(engine.checkpoint())
    left, right = engine.advance(32), resumed.advance(32)
    assert left.total_cost == right.total_cost
    assert left.cost_components == right.cost_components
    assert left.trace == right.trace
    assert len(left.completed) == 2
    for row in engine.slow_controller.history:
        diag = row["diagnostics"]
        assert diag["next_slow_trigger_at"] == row["trigger_time"] + 2
        assert all(f["published_at"] <= row["trigger_time"] for f in diag["published_forecasts"])


def test_disabled_builder_exactly_keeps_old_greedy_physics():
    scene = feedback_scene()
    spec = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    old = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    enable_replay_cache(old)
    wrapped = build_empty_improvement_engine(scene, spec, enabled=False)
    left, right = old.advance(32), wrapped.advance(32)
    assert left.total_cost == right.total_cost and left.trace == right.trace
    assert left.cost_components == right.cost_components
