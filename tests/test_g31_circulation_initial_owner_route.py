"""Pure initial-A gates. No NativeSession, native binary or performance run."""
from __future__ import annotations
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_contract as c
from scripts.experiments.g31_ics_circulation import initial_owner_route_worker as w
from scripts.experiments.g31_ics_circulation import initial_owner_route_request as r
from scripts.experiments.g31_ics_circulation import initial_owner_route_image as image
from scripts.experiments.g31_ics_circulation import initial_owner_route_client as client
from scripts.experiments.g31_ics_circulation import json_prediction_image as old_image
from scripts.experiments.g31_ics_circulation import json_prediction_worker as old_worker
from scripts.experiments.g31_ics_circulation import json_prediction_client as old_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
OLD_RAW = OUT/'json_prediction_RPC_prepare_002/1.compiled.json.gz'
OLD_RAW_SHA = 'eb4f8eceeedb20eb1901c18ddd4a6f2fde765b16bcc3452d1b256da9a0b1a2ce'


@pytest.fixture(scope='module')
def samples():
    raw = OLD_RAW.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == OLD_RAW_SHA
    saved = json.loads(gzip.decompress(raw))['samples']
    assert len(saved) == 6
    return saved


def packet(snapshot):
    return {'schema':c.SCHEMA,'bundle':copy.deepcopy(snapshot),'root_started_ns':0,
        'decision_cutoff_ns':c.BUDGET_NS-c.FINALIZATION_RESERVE_NS,
        'root_deadline_ns':c.BUDGET_NS,'participation_contract_sha256':c.contract_sha256()}


@pytest.fixture(scope='module')
def engine():
    return w.Engine(w.MODE, old_image)


@pytest.mark.parametrize('index',range(6))
def test_actual_saved_six_baselines_and_prefer2_exact(index,samples,engine,monkeypatch):
    # Frozen deterministic clock is solely a functional guard test. No timing
    # or speed measurement is made; both atomic calls are allowed to finish.
    monkeypatch.setattr(w,'time',SimpleNamespace(perf_counter_ns=lambda:1))
    sample=samples[index]; expected=sample['response']['payload']
    got=engine.predict(packet(sample['request']['snapshot']))
    assert old_image.encode(got['baseline']) == old_image.encode(expected['baseline'])
    assert old_image.encode(got['predictions'][0]) == old_image.encode(expected['baseline'])
    assert got['actions']==[expected['actions'][0],expected['actions'][16]]
    assert old_image.encode(got['predictions'][1])==old_image.encode(expected['predictions'][16])
    assert got['counts']=={'logical_choices':2,'baseline_evaluation_calls':1,
        'complete_baselines':1,'additional_candidate_calls':1}
    assert got['full_32_search_performed'] is False


def test_no_cross_request_or_output_alias(samples,engine,monkeypatch):
    monkeypatch.setattr(w,'time',SimpleNamespace(perf_counter_ns=lambda:1))
    request=packet(samples[0]['request']['snapshot']); original=copy.deepcopy(request)
    result=engine.predict(request)
    reference=copy.deepcopy(result)
    result['baseline']['completion']['loaded']=-1
    assert result['predictions'][0]==reference['predictions'][0]
    result['predictions'][1].clear()
    request['bundle']['trays']['L']['node']=999
    assert engine.predict(original)==reference
    changed=engine.predict(request)
    assert changed['selection']['choice'] is None
    assert changed['counts']['complete_baselines']==0
    assert changed['counts']['additional_candidate_calls']==0
    assert set(engine.__dict__)=={'context','proof','contract','codec'}


def fake_engine(clock,monkeypatch):
    calls=[]
    base={'status':'conditional_prediction','completion':dict.fromkeys(sorted(c.JOBS),10.),
          'native_protection_certified':False}
    actions=[dict(initial_action=a,empty_departure=t,return_delay=d,later_action=l)
             for a in ('native_default','prefer_2') for t in (.11,1.,2.,3.)
             for d in (0.,.5) for l in ('native_default','prefer_8')]
    class Context:
        def __init__(self,bundle): calls.append('baseline')
        def baseline(self): return copy.deepcopy(base)
        def actions(self): return copy.deepcopy(actions)
        def predict(self,action):
            calls.append('candidate')
            value=copy.deepcopy(base);value['completion']['loaded']=9.
            return value
    engine=w.Engine.__new__(w.Engine);engine.context=Context;engine.contract=c;engine.codec=old_image
    ticks=iter(clock)
    monkeypatch.setattr(w,'time',SimpleNamespace(perf_counter_ns=lambda:next(ticks)))
    return engine,calls


@pytest.mark.parametrize('ticks,expected_calls,choice,status',[
    ([60_000_000,60_000_001],[],None,'unknown_no_baseline_budget'),
    ([1,60_000_000,60_000_001,60_000_002],['baseline'],'native_default','budget_exhausted_default_incumbent'),
    ([1,2,61_000_000,61_000_001],['baseline','candidate'],'native_default','budget_exhausted_default_incumbent'),
    ([1,2,3,4],['baseline','candidate'],'prefer_2','conditional_two_choice_selection'),
])
def test_atomic_budget_gates_keep_unknown_and_full_cost(ticks,expected_calls,choice,status,monkeypatch):
    engine,calls=fake_engine(ticks,monkeypatch)
    got=engine.predict(packet({}))
    assert calls==expected_calls
    assert got['selection']['choice']==choice and got['selection']['status']==status
    assert got['complete_100ms_certified'] is False


@pytest.mark.parametrize('change',[
    lambda p:p.update(root_started_ns=True),
    lambda p:p.update(root_deadline_ns=c.BUDGET_NS+1),
    lambda p:p.update(decision_cutoff_ns=1),
    lambda p:p.update(participation_contract_sha256='0'*64),
    lambda p:p.update(exec='anything'),
    lambda p:p.update(bundle=[]),
])
def test_strict_packet_rejects_before_prediction(change,monkeypatch):
    engine,calls=fake_engine([1],monkeypatch);value=packet({});change(value)
    with pytest.raises(ValueError): engine.predict(value)
    assert calls==[]


def test_strict_protection_tiny_positive_and_partial_never_win():
    base={'status':'conditional_prediction','completion':dict.fromkeys(sorted(c.JOBS),10.),'native_protection_certified':False}
    bad=copy.deepcopy(base);bad['completion']['loaded']=10.+1e-12;bad['completion']['blocker']=0.
    assert c.select(base,bad,decision_budget_expired=False)['choice']=='native_default'
    partial={'status':'conditional_protection_rejected_prefix','completion':{}}
    assert c.select(base,partial,decision_budget_expired=False)['candidate_eligible'] is False
    assert c.select(base,base,decision_budget_expired=False)['choice']=='native_default'


def source():
    return {'tray_id':'L','business_bag_id':'loaded','node':0,'mode':'loaded','edge_from':-1,
            'edge_to':-1,'reception_node':-1,'generation':1,'traversal_id':0,'committed_prefix':[0]}


def ownview():
    return {'owner_id':'A','now':.11,'trays':[source()],
            'jobs':[{'business_bag_id':'loaded','allow_suffix_reroute':True}],
            'node_contracts':[{'node':2,'resource_owner':'A','capacity':1,'occupancy':0}],
            'known_faults':[]}


@pytest.mark.parametrize('field,value',[('capacity',True),('capacity',1.),('capacity',0),
    ('occupancy',True),('occupancy',1),('resource_owner','B')])
def test_same_owner_receiver_strict_checks(field,value):
    view=ownview();view['node_contracts'][0][field]=value
    assert c.validate_final_local(view,{'trays':{'L':source()}},'prefer_2')['status'].startswith('unknown')


def test_source_epoch_identity_and_default_are_not_forced1():
    view=ownview()
    assert c.validate_final_local(view,{'trays':{'L':source()}},'native_default')['status']=='fresh_local_precondition_checked'
    view['trays'][0]['generation']=2
    assert c.validate_final_local(view,{'trays':{'L':source()}},'native_default')['status'].startswith('unknown')
    view=ownview();view['now']=.12
    assert c.validate_final_local(view,{'trays':{'L':source()}},'prefer_2')['status'].startswith('unknown')


def moving(target=2):
    view=ownview();view['now']=1.2
    view['trays'][0].update(edge_from=0,edge_to=target,committed_prefix=[0,target],traversal_id=1)
    return view


@pytest.mark.parametrize('exit_at',[None,-1.,1.2,float('nan'),float('inf'),True])
def test_pending_reservation_never_actual_entry(exit_at):
    view=moving()
    if exit_at is not None:view['trays'][0]['edge_exit_at']=exit_at
    assert c.observed_first_hop(view,source()) is None


def test_observed_entry_and_post_exit_prove_first_hop():
    view=moving();view['trays'][0]['edge_exit_at']=1.3
    assert c.observed_first_hop(view,source())['to']==2
    view['trays'][0].update(node=2,edge_from=-1,edge_to=-1);view['now']=1.3
    assert c.observed_first_hop(view,source())['evidence']=='post_exit_prefix'


def command(status='updated',delivered_at=1.):
    return {'request_id':'r','status':'acknowledged','attempt':1,'kind':'route',
            'last_delivered_ack':{'status':status,'delivered_at':delivered_at}}


@pytest.mark.parametrize('ack,hop,complete',[(command(),None,True),
    ({}, {'to':2,'observed_at':1.2},True),
    (command(delivered_at=2.),{'to':2,'observed_at':1.2},True),
    (command(),{'to':2,'observed_at':1.2},False)])
def test_updated_ack_without_hop_or_actual_ack_or_drain_stays_open(ack,hop,complete):
    assert not c.closure('prefer_2',hop,ack,queried_owner='A',request_id='r',now=1.2,timestamp_complete=complete)['closed']


def test_other_hop_is_failure_only_after_real_ack_and_drain():
    hop={'to':1,'observed_at':1.2}
    assert not c.closure('prefer_2',hop,None,queried_owner='A',request_id='r',now=1.2,timestamp_complete=True)['closed']
    result=c.closure('prefer_2',hop,command(),queried_owner='A',request_id='r',now=1.2,timestamp_complete=True)
    assert result['status']=='closed_updated_but_other_first_hop' and result['requested_hop_executed'] is False
    assert c.closure('native_default',hop,None,queried_owner='A',request_id=None,now=1.2,timestamp_complete=True)['ack_status']=='not_applicable_no_command'


def test_real_command_shape_binds_query_argument_not_invented_response_owner():
    raw_path=OUT/'native027_fixture_diagnostic_002/raw.json'
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest()=='540d665b2a172f8d66ae03048c4461c064a7f0ffad9324fcb1b61b4a64ffc93f'
    raw=json.loads(raw_path.read_text())['capture']['command']
    assert set(raw)=={'request_id','status','attempt','kind','last_delivered_ack'}
    assert 'owner_id' not in raw
    query=command();hop={'to':2,'observed_at':1.2}
    assert set(query)==set(raw)
    assert c.closure('prefer_2',hop,query,queried_owner='A',request_id='r',now=1.2,timestamp_complete=True)['closed']
    assert not c.closure('prefer_2',hop,query,queried_owner='B',request_id='r',now=1.2,timestamp_complete=True)['closed']
    assert not c.closure('prefer_2',hop,query,queried_owner='A',request_id='wrong',now=1.2,timestamp_complete=True)['closed']


@pytest.mark.parametrize('status',['rejected','expired','failed','cancelled'])
def test_delivered_failure_closes_but_submit_response_does_not(status):
    assert c.closure('prefer_2',None,command(status),queried_owner='A',request_id='r',now=1.2,timestamp_complete=True)['closed']
    assert not c.closure('prefer_2',None,{'status':status},queried_owner='A',request_id='r',now=1.2,timestamp_complete=True)['closed']


def test_fixed_continuation_keeps_original_code_and_no_shared_global_patch():
    old=r.public.OwnerPolicy.decide_pending
    new=r.FixedContinuationOwner.decide_pending
    assert new.__code__ is old.__code__ and new.__closure__ is old.__closure__
    assert new.__globals__ is not old.__globals__
    assert old.__globals__['policy'] is r.public.policy
    assert new.__globals__['policy'].later is r.fixed_later
    assert r.fixed_later({'native_delivery_verified':True},'anything')['selected_action'] is None


def test_original_rpc_methods_and_image_only_entry_schema_changes():
    for name in ('predict','close','abort','_reader','_next'):
        assert getattr(client.InitialOwnerClient,name) is getattr(old_client.Client,name)
    original=Path(old_image.__file__).read_text()
    expected=original.replace("SCHEMA = 'g31.json_prediction_image.v1'", "SCHEMA = 'g31.initial_owner_route_image.v1'")
    expected=expected.replace("ENTRY = 'scripts.experiments.g31_ics_circulation.json_prediction_worker'", "ENTRY = 'scripts.experiments.g31_ics_circulation.initial_owner_route_worker'")
    expected=expected.replace("'scripts.experiments.g31_ics_circulation.json_prediction_image'", "'scripts.experiments.g31_ics_circulation.initial_owner_route_image'")
    assert Path(image.__file__).read_text()==expected


def test_replay_identity_closed_protocol_and_eof():
    class E:
        def predict(self,s):return {'native_authority':False}
    p=old_worker.Protocol('v',E(),old_image)
    req={'kind':'predict','version':'v','sequence':1,'request_id':'x','snapshot':{}}
    p.accept(req)
    with pytest.raises(ValueError):p.accept({**req,'sequence':2})
    p.accept({'kind':'close','version':'v','sequence':2})
    with pytest.raises(ValueError):p.accept({**req,'sequence':2,'request_id':'y'})


def test_root_admitted_before_authority_checks_and_no_fake_native(monkeypatch):
    root=r.InitialOwnerRequest.__new__(r.InitialOwnerRequest);seen=[]
    def reject(*args): seen.append(root.started_ns);return False
    monkeypatch.setattr(r.adapter,'_valid_handle',reject)
    with pytest.raises(ValueError):
        r.InitialOwnerRequest.__init__(root,None,None,None,None,None,request_id='root')
    assert seen==[root.started_ns] and root.deadline_ns-root.started_ns==c.BUDGET_NS


def test_boundary_complete_is_real_response_not_success_label():
    assert r.native_boundary_complete({'physical_time':.11,'status':'reached','horizon_complete':True},.11)
    assert not r.native_boundary_complete({'physical_time':.11,'status':'budget_exhausted','horizon_complete':False},.11)
    assert not r.native_boundary_complete({'physical_time':.11,'status':'horizon_reached','timestamp_complete':False},.11)
    assert not r.native_boundary_complete({'physical_time':.12,'status':'reached','horizon_complete':True},.11)


def test_pure_source_closure_explicitly_pins_its_own_gate():
    from scripts.experiments.g31_ics_circulation import run_initial_owner_route_pure as gate
    name='scripts/experiments/g31_ics_circulation/run_initial_owner_route_pure.py'
    assert gate.sources()[name]==Path(gate.__file__).read_bytes()
