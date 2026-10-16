from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_g31_circulation_preference_request_context import bundle,ordered
from scripts.experiments.g31_ics_circulation import public_preference_receiver_bound_context as new
from scripts.experiments.g31_ics_circulation import public_native_preference_search as search

ROWS=[]
ROOT=Path(__file__).resolve().parents[1]
SAVED=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_protection_context_pair_001'


@pytest.mark.parametrize('index',range(6))
def test_fixed192_saved_inputs_every_early_witness_against_independent_full_result(index):
    name=f'block{index//3}_load{index%3}';plan=json.loads((SAVED/'preregistered_protocol.json').read_bytes())
    row=plan['cases'][index];path=SAVED/row['input'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['input_sha256']
    value=json.loads(path.read_bytes());reference=new.combined.ProtectionRequestContext(value);candidate=new.ReceiverBoundRequestContext(value)
    old=json.loads(gzip.decompress((SAVED/(name+'.0.A.json.gz')).read_bytes()))
    ledger=json.loads((SAVED/'ledger.json').read_bytes());assert hashlib.sha256((SAVED/(name+'.0.A.json.gz')).read_bytes()).hexdigest()==ledger[index*4]['raw_sha256']
    assert ordered(candidate.baseline())==ordered(reference.baseline())==ordered(old['baseline'])
    actions=candidate.actions();assert ordered(actions)==ordered(old['actions']);cuts=0
    for action,full in zip(actions,old['predictions'],strict=True):
        before=reference.predict(action);actual=candidate.predict(action)
        if actual['status']=='conditional_protection_rejected_lower_bound':
            w=actual['witness'];assert full['completion']['receiver']>=w['completion_lower_bound']>old['baseline']['completion']['receiver']
            assert actual['completion']=={} and actual['suffix_status']=='unknown_unexecuted' and actual['full_candidate_prediction'] is False
            assert w['positive_capacity_paths']=={'empty':[5,1],'loaded':[1,3,4]};cuts+=1
        else:assert ordered(actual)==ordered(before)
    assert cuts==(16 if index<3 else 0)
    ROWS.append({'case':name,'early_strict_rejections':cuts,'unchanged_other_results':32-cuts,'counts':candidate.describe()['counts']})


@pytest.mark.parametrize('defect',['extra_empty','L_empty','P_empty','P_returns','new_edge','permission','age','pending','receiver_identity','extra_job'])
def test_alternative_carriers_or_unsupported_contract_cannot_cut(defect):
    value=bundle();action=new.combined.ProtectionRequestContext(value).actions()[8]
    if defect=='extra_empty':value['trays']['NEW']={**value['trays']['E'],'tray_id':'NEW','node':1}
    elif defect=='L_empty':value['trays']['L'].update(mode='empty',business_bag_id='')
    elif defect=='P_empty':value['trays']['P'].update(mode='empty',business_bag_id='')
    elif defect=='P_returns':value['jobs']['blocker']['destination']=1
    elif defect=='new_edge':value['contract']['edge_records'].append([9,1,.01,1.])
    elif defect=='permission':value['contract']['node_contracts'][0]['allow_export']=not value['contract']['node_contracts'][0]['allow_export']
    elif defect=='age':value['now']+=.01
    elif defect=='pending':value['owner_pending_tray_requests']=['other_supply']
    elif defect=='receiver_identity':value['jobs']['receiver']['origin']=7
    else:value['jobs']['new_receiver']=deepcopy(value['jobs']['receiver'])
    a=new.combined.ProtectionRequestContext(value);b=new.ReceiverBoundRequestContext(value)
    assert b.describe()['cut_enabled'] is False
    assert ordered(a.predict(action))==ordered(b.predict(action))
    assert b.describe()['counts']['candidate_lower_bound_rejections']==0


@pytest.mark.parametrize('defect',['bool','extra','missing','window','nan'])
def test_each_candidate_still_has_full_typed_action_guard(defect):
    value=bundle();a=new.combined.ProtectionRequestContext(value);b=new.ReceiverBoundRequestContext(value);action=a.actions()[8]
    if defect=='bool':action['empty_departure']=True
    elif defect=='extra':action['new_supply']='P'
    elif defect=='missing':action.pop('initial_action')
    elif defect=='window':action['empty_departure']+=.001
    else:action['return_delay']=float('nan')
    assert ordered(a.predict(action))==ordered(b.predict(action))
    assert b.describe()['counts']['candidate_lower_bound_rejections']==0


def test_unknown_baseline_disables_new_bound(monkeypatch):
    monkeypatch.setattr(new.combined.proof,'_reference_times',lambda value:None)
    value=bundle();ctx=new.ReceiverBoundRequestContext(value);a=new.combined.base.RequestContext(value)
    assert ctx.describe()['cut_enabled'] is False
    assert ordered(ctx.predict(a.actions()[8]))==ordered(a.predict(a.actions()[8]))


def test_equal_bound_is_not_a_rejection(monkeypatch):
    actual=new.receiver_bound
    def equal(p,b):
        w=actual(p,b)
        if w:w['completion_lower_bound']=w['baseline_completed_at']
        return w
    monkeypatch.setattr(new,'receiver_bound',equal)
    a=new.combined.ProtectionRequestContext(bundle());b=new.ReceiverBoundRequestContext(bundle())
    assert ordered(b.predict(a.actions()[8]))==ordered(a.predict(a.actions()[8]))
    assert b.describe()['counts']['candidate_lower_bound_rejections']==0


def test_forward_float_additions_are_not_collapsed_and_ignore_preference():
    p=SimpleNamespace(outgoing={0:[1,3],1:[2],2:[],3:[2]},edges={(0,1):{'capacity':1},(1,2):{'capacity':1},(0,3):{'capacity':1},(3,2):{'capacity':1}},
        travel={(0,1):.1,(1,2):.2,(0,3):1.,(3,2):1.},action={'initial_action':'prefer_2'})
    value,path=new._arrival(p,0,2,.4)
    assert value==(.4+.1)+.2 and value<.4+(.1+.2) and path==[0,1,2]
    p.edges[0,1]['capacity']=0
    assert new._arrival(p,0,2,.4)==((.4+1.)+1.,[0,3,2])


def test_isolation_and_source_pin(monkeypatch):
    value=bundle();ctx=new.ReceiverBoundRequestContext(value);action=ctx.actions()[8];expected=ctx.predict(action)
    value['trays']['E']['node']=1;ctx.baseline()['completion']['receiver']=-1
    result=ctx.predict(action);result['witness']['completion_lower_bound']=-1
    assert ordered(ctx.predict(action))==ordered(expected)
    monkeypatch.setattr(new,'EXPECTED_COMBINED','0'*64)
    with pytest.raises(ValueError,match='unreviewed_combination_source'):new.ReceiverBoundRequestContext(bundle())


@pytest.mark.parametrize('index',range(6))
def test_four_methods_keep_same_query_order_selected_action_and_full_result(index):
    value=bundle(index);actions=new.combined.ProtectionRequestContext(value).actions()
    domain=dict(zip(((i,w,r,l) for i in range(2) for w in range(4) for r in range(2) for l in range(2)),actions));base=(0,0,0,0)
    for method in search.METHODS:
        a=new.combined.ProtectionRequestContext(value);b=new.ReceiverBoundRequestContext(value);ac=[];bc=[]
        def full(action):ac.append(deepcopy(action));return a.baseline() if action==domain[base] else a.predict(action)
        def partial(action):bc.append(deepcopy(action));return b.baseline() if action==domain[base] else b.predict(action)
        old=search.search(domain,base,full,method=method,budget=32);new_result=search.search(domain,base,partial,method=method,budget=32)
        assert ac==bc
        for name in ('selected_action','selected_prediction','evaluations','stop_reason'):assert ordered(old[name])==ordered(new_result[name])
