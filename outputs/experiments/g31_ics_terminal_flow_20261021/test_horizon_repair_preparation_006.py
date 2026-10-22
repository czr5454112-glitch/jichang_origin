"""Method-axis checks for staged code; this does not certify native performance."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as old

def staged(name):
    path=Path(__file__).with_name('horizon_repair_preparation_006')/(name+'.py')
    spec=importlib.util.spec_from_file_location('scripts.experiments.g31_ics_circulation.staged_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

new=staged('foundation_airport_transport_campaign')
campaign=staged('foundation_airport_joint_campaign')
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
plans=sorted((CYCLE/'runs').glob('TF_*_005_*/plan.json'))

@pytest.mark.parametrize('path',plans,ids=lambda p:p.parent.name)
def test_existing_registered_contracts_unchanged(path):
    plan=json.loads(path.read_text())
    assert old.method_contract_errors(plan)==new.method_contract_errors(plan)==[]
    assert old.comparison_contract(plan)==new.comparison_contract(plan)

def baseline():
    return json.loads((CYCLE/'runs/TF_bridge_all_005_TF-B1-60_P2201/plan.json').read_text())

def candidate():
    plan=baseline();plan.update(method='TF-B1-60-H1800',projection_horizon_seconds=1800.);return plan

def test_only_projection_axis_and_method_enabled():
    a,b=baseline(),candidate()
    assert 'TF-B1-60-H1800' in campaign.TRANSPORT_METHODS
    assert new.method_contract_errors(b)==[]
    ac,bc=new.comparison_contract(a),new.comparison_contract(b)
    assert {k for k in ac if ac[k]!=bc[k]}=={'projection_horizon'}
    assert new.ALLOWED_COMPARISON_DIFFERENCES[b['method']]==('projection_horizon',)
    assert new.REFERENCES[b['method']]=='TF-B1-60'

@pytest.mark.parametrize('field,value',[
    ('projection_horizon_seconds',600.),('projection_horizon_seconds',900.),
    ('forecast_horizon_seconds',600.),('recompute_period_seconds',300.),
    ('supply_mode','conditional'),('forecast_bin_edges_seconds',[0.,300.,600.,1800.]),
    ('model',{'unexpected':'action-Q'}),('demand_model',{'unexpected':'predictor'})])
def test_mixed_axis_or_model_change_rejected(field,value):
    plan=candidate();plan[field]=value
    assert new.method_contract_errors(plan)

def test_baseline_does_not_silently_gain_longer_horizon():
    plan=baseline();plan['projection_horizon_seconds']=1800.
    assert 'projection_horizon_seconds' in new.method_contract_errors(plan)

def test_bad_command_or_dispatch_timing_rejected():
    for key in ('command_delay_seconds','dispatch_slot_seconds'):
        plan=candidate();plan['transport_config'][key]+=1
        assert 'dispatch_timing' in new.method_contract_errors(plan)
