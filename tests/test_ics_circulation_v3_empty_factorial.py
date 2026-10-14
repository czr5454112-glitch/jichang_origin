from dataclasses import asdict
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.empty_factorial import (
    EmptyFactorial, FACTORS, FactorialEmptyPrebalancer, build_empty_factorial_engine,
)
from scripts.experiments.ics_circulation_v3.empty_improvement import (
    EmptyImprovementSettings, build_empty_improvement_engine,
)
from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_full_cycle import physical_result
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory


def fixture(factors, cls=FactorialEmptyPrebalancer):
    spec = ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    factory = ReplayRegionalFactory(20, 2000, 12, True, 3)
    controller = cls(spec=spec, settings=EmptyImprovementSettings(score_horizon=16, max_rollouts=12),
        generator_factory=factory, factors=factors)
    nodes = {n: Node(n, n, n, capacity=6) for n in ("A", "B", "C")}
    edges = tuple(Edge(a+b, a, b, 1) for a in nodes for b in nodes if a != b)
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
        {"a": Tray("a", "A"), "b": Tray("b", "C")}, {})
    forecasts = (RoutingDemandForecast("need", "B", "A", 4, 12),)
    return controller, state, forecasts


@pytest.mark.parametrize("kwargs", ({"continuation":"unknown"}, {"tie":"unknown"}, {"continuation":True}, {"tie":None}))
def test_invalid_factor_strings_fail_explicitly(kwargs):
    with pytest.raises(ValueError):
        EmptyFactorial(**kwargs)


def test_four_cells_keep_same_candidate_order_and_declared_budgets_at_same_state():
    alternatives=[]
    for factors in FACTORS:
        ctrl, state, forecasts = fixture(factors)
        ctrl.set_slow_context(0,2)
        result=ctrl.plan(state,forecasts)
        rows=result.diagnostics['scored_actions']
        alternatives.append([r['proposals'] for r in rows])
        assert len(rows)<=12 and all(r['status']=='complete' for r in rows)
        assert result.diagnostics['proxy_route_search_horizon']==20
        assert result.diagnostics['proxy_fast_candidate_count']==4
        assert result.diagnostics['factorial']==asdict(factors)
        assert [r['kind'] for r in rows[:2]]==['greedy_incumbent','no_transfer']
        assert all(r['ticks']==16 for r in rows)
        if factors.continuation=='earliest_reactive':
            assert all(r['slow_trigger_times']==[] for r in rows)
        else:
            assert all(r['slow_trigger_times']==list(range(2,16,2)) for r in rows)
    assert all(a==alternatives[0] for a in alternatives)


def test_tie_only_changes_equal_values_and_prefers_fewer_transfers():
    class EqualScore(FactorialEmptyPrebalancer):
        def _score(self,snapshot,sequence,forecasts,proxy,next_slow):
            return {'status':'complete','proxy_cost':1.,'proposals':[asdict(p)for p in sequence]}
    selections=[]
    for tie in ('incumbent','fewest_physical'):
        ctrl,state,forecasts=fixture(EmptyFactorial(tie=tie),EqualScore)
        ctrl.set_slow_context(0,2)
        result=ctrl.plan(state,forecasts)
        selections.append(result.diagnostics['selected_action_index'])
        original=tuple(ctrl.generator_factory().generate_empty(state,'a','B',k=1))
        assert not ctrl._prefer_complete(1.+2e-9,(),1,1.,original,0)
        assert ctrl._prefer_complete(1.-2e-9,original,2,1.,(),1)
    assert selections==[0,1]


@pytest.mark.parametrize("order", ('route_then_prebalance','prebalance_then_route'))
def test_default_factorial_cell_exactly_preserves_original_physics(order):
    scene=feedback_scene()
    spec=ControlSpec(routing='timed',planning_horizon=20,slow_period=2,coordination_order=order)
    settings=EmptyImprovementSettings(score_horizon=20,max_rollouts=12)
    old=build_empty_improvement_engine(scene,spec,settings=settings)
    new=build_empty_factorial_engine(scene,EmptyFactorial(),spec=spec,settings=settings)
    assert physical_result(old.advance(32))==physical_result(new.advance(32))
    assert old.route_selector.history==new.route_selector.history


def test_earliest_projection_rejects_unpublished_and_keeps_original_next_edge_permission():
    from dataclasses import replace
    ctrl,state,forecasts=fixture(EmptyFactorial('earliest_reactive','fewest_physical'))
    with pytest.raises(ValueError,match='unpublished'):
        ctrl._project(state,(replace(forecasts[0],published_at=1),),(),2)
    projected=ctrl._project(state,forecasts,(),2)
    assert projected.route_mode=='next_edge' and projected.search_horizon==20
    assert projected.candidate_count==4 and projected.slow_controller is None
    assert projected._cursor.stage_index==4


def test_historical_json_comparison_preserves_nested_action_fields():
    from scripts.experiments.ics_circulation_v3.run_empty_factorial import json_equal
    left={'legs':({'edge_id':'AB','depart':1,'arrive':2},),'time':0}
    right={'legs':[{'edge_id':'AB','depart':1,'arrive':2}],'time':0}
    assert json_equal(left,right)
    right['legs'][0]['depart']=2
    assert not json_equal(left,right)
