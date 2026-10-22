"""Contract-only tests; no prepare, launch, or ledger writes."""
import copy
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
loader=importlib.util.spec_from_file_location('bins600_driver',ROOT/'outputs/terminal_flow_bins600_005.py')
d=importlib.util.module_from_spec(loader);loader.loader.exec_module(d)
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_forecast import bin_edges

@pytest.fixture
def pair():
    import json
    reference=json.loads((d.CYCLE/'runs/TF_bridge_all_005_TF-B1-60_P2201/plan.json').read_text(encoding='utf8'))
    candidate=copy.deepcopy(reference)
    candidate.update(method='TF-B1-600',forecast_bin_edges_seconds=bin_edges('600'),batch='initial')
    return reference,candidate

def test_same_source_same_information_pair_changes_only_bins(pair):
    changes=d.validate_pair(*pair,flow)
    assert set(changes)=={'forecast_bin_edges_seconds'}

@pytest.mark.parametrize('field,value', [('projection_horizon_seconds',1800.),('recompute_period_seconds',300.),
    ('supply_mode','conditional'),('horizon',18000.),('batch','formal'),('method','TF-predictor')])
def test_unregistered_axes_cannot_hide_as_bin_extension(pair,field,value):
    pair[1][field]=value
    with pytest.raises(ValueError): d.validate_pair(*pair,flow)

def test_source_change_cannot_hide_as_bin_effect(pair):
    pair[1]['source_bundle']['sha256']='another-source'
    with pytest.raises(ValueError,match='only_bin_edges'): d.validate_pair(*pair,flow)

def test_test_parent_cannot_enter_dev_extension(pair):
    pair[1]['parent']['split']='test'
    with pytest.raises(ValueError,match='same_DEV_parent'): d.validate_pair(*pair,flow)

def test_unchanged_bins_do_not_claim_a600_intervention(pair):
    pair[1]['forecast_bin_edges_seconds']=bin_edges('60')
    with pytest.raises(ValueError,match='600_method_contract'): d.validate_pair(*pair,flow)
