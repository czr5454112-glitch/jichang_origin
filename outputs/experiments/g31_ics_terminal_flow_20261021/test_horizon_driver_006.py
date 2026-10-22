"""Finite repair-block admission and sole-axis checks; no native launches."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[3]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
d=load('horizon_driver006',ROOT/'outputs/terminal_flow_horizon006.py')
f=load('scripts.experiments.g31_ics_circulation.horizon_driver_staged_flow',
    Path(__file__).with_name('horizon_repair_preparation_006')/'foundation_airport_transport_campaign.py')

@pytest.fixture
def pair():
    a=json.loads((d.CYCLE/'runs/TF_bridge_all_005_TF-B1-60_P2201/plan.json').read_text())
    a['batch']='initial';b=copy.deepcopy(a);b.update(method=d.METHODS[1],projection_horizon_seconds=1800.)
    return a,b

def test_exact_projection_axis(pair):
    assert set(d.validate_pair(*pair,f))=={'projection_horizon'}

@pytest.mark.parametrize('field,value',[
    ('supply_mode','conditional'),('horizon',18000.),('batch','formal'),
    ('recompute_period_seconds',300.),('forecast_horizon_seconds',900.),
    ('forecast_bin_edges_seconds',[0,300,600,1800]),('projection_horizon_seconds',900.),
    ('demand_model',{'sha256':'new'})])
def test_no_hidden_extra_axis(pair,field,value):
    pair[1][field]=value
    with pytest.raises(ValueError):d.validate_pair(*pair,f)

def test_source_cannot_change_within_pair(pair):
    pair[1]['source_bundle']['sha256']='changed'
    with pytest.raises(ValueError,match='only_projection_axis'):d.validate_pair(*pair,f)

def test_test_parent_cannot_be_relabelled(pair):
    for p in pair:p['parent']['split']='test'
    with pytest.raises(ValueError,match='same_fixed_DEV_parent'):d.validate_pair(*pair,f)

def test_preflight_reserves_full_eight_and_audit(monkeypatch,tmp_path):
    (tmp_path/'ledger.jsonl').write_text('')
    monkeypatch.setattr(d,'CYCLE',tmp_path)
    limits=dict(native_start_limit=160,allocations=dict(initial=24))
    captured={}
    def check(*args,**kwargs):captured.update(kwargs);return {'admitted':True}
    w=SimpleNamespace(read=lambda path:limits if path.name=='campaign_budget.json' else {'cutoff_utc':'cutoff'},
        snapshot=lambda **k:{},instant=lambda v:v,preflight=check,historical_seconds=lambda h:10,
        evidence_bytes=lambda roots:12)
    assert d.preflight(w)=={'admitted':True}
    assert captured['offline_seconds']==24300 and captured['remaining_seconds']==6000
    assert captured['reserved_bytes']==8*536870912+256*1024**2

def test_original_initial_quota_not_reset(monkeypatch,tmp_path):
    events=[dict(event='native_start',batch='initial')]*17
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    monkeypatch.setattr(d,'CYCLE',tmp_path)
    limits=dict(native_start_limit=160,allocations=dict(initial=24))
    w=SimpleNamespace(read=lambda path:limits if path.name=='campaign_budget.json' else {'cutoff_utc':'cutoff'},
        snapshot=lambda **k:{},instant=lambda v:v,preflight=lambda *a,**k:{},historical_seconds=lambda h:10,
        evidence_bytes=lambda roots:12)
    with pytest.raises(ValueError,match='unspent_initial_quota'):d.preflight(w)
