"""Synthetic scope guards and an actual projection-equation counterexample."""
from pathlib import Path
import importlib.util
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as p
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_allocation as allocation
from test_g31_foundation_airport_joint_projection import fixture,forecast

path=Path(__file__).with_name('projection_horizon_probe_005.py')
spec=importlib.util.spec_from_file_location('horizon_probe_test',path)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
g,_,_=probe.load_support()

def test_later_source_demand_is_not_visible_to_short_proxy():
    obs=fixture((2,0,0));f=forecast(obs,{0:[0.]*15+[2.]+[0.]*14})
    costs=[]
    for horizon in (600.,1800.):
        projection=p.prepare_inventory_projection(obs,forecast=f,horizon_seconds=horizon)
        offers=dict(public_state_digest=projection.public_state_digest,
            sources={0:dict(source_cap=1)},total_source_cap=1)
        values=allocation.build_marginal_values(projection,offers,{})
        costs.append(values['source_marginals'][0][0])
    assert costs[0]==0 and costs[1]>800
    assert f['bin_edges_seconds']==list(range(0,1801,60))

def test_late_arrival_does_not_create_stock_before_eta():
    obs=fixture((0,0,0));f=forecast(obs,{2:[0.]*15+[1.]+[0.]*14})
    small=p.prepare_inventory_projection(obs,forecast=f,horizon_seconds=600.)
    large=p.prepare_inventory_projection(obs,forecast=f,horizon_seconds=1800.)
    a=p._node_projection(small,2,use_forecast=True,added_event=(632.,1.))
    b=p._node_projection(large,2,use_forecast=True,added_event=(632.,1.))
    base=p._node_projection(large,2,use_forecast=True)
    assert a['ending_inventory']==0 and a['served_mass']==0
    assert b['served_mass']==1 and b['backlog_area']<base['backlog_area']

def decision(claim):
    return dict(selection=dict(flow_plan=dict(receiver_claims_deducted=claim)))

def test_nonzero_claim_excluded_before_any_replay():
    assert probe.replay(decision({'95':1}),None,None,None,None,None,{},g)==dict(excluded='uncredited_claims')

@pytest.mark.parametrize('claim',[None,{'95':-1},{'95':True},{'95':float('nan')}])
def test_unknown_or_invalid_claim_not_assumed_zero(claim):
    with pytest.raises(ValueError,match='claim'):
        probe.replay(decision(claim),None,None,None,None,None,{},g)

def test_wrapper_accepts_only_single_diagnostic_task():
    path=ROOT/'outputs/terminal_flow_horizon_probe_offline005.py'
    spec=importlib.util.spec_from_file_location('horizon_probe_wrapper_test',path)
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    wrapper.validate_task_roster([dict(id='horizon_probe',kind='horizon_probe')])
    for tasks in ([],[dict(id='bins600',kind='bins600')],
            [dict(id='horizon_probe',kind='horizon_probe')]*2):
        with pytest.raises(ValueError):wrapper.validate_task_roster(tasks)
