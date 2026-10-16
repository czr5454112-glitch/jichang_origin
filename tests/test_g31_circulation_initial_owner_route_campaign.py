"""Pure campaign wiring/negative gates; no native or new predictor evaluation."""
import ast
import copy
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_campaign as v
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_campaign as launch


def test_fixed_six_order_and_eighteen_rows():
    rows = c.declarations()
    assert len(rows) == 18
    assert [(r['case']['case_id'],r['method']) for r in list(rows.values())[:12]] == [
        (case['case_id'],arm) for case in c.public.domain.cases() for arm in c.ARMS]
    assert {r['case']['case_id'] for r in list(rows.values())[12:]} == {'block0_load0'}
    assert list(rows)[-1] == 'postsubmit_B_execution_outage/block0_load0/budget_two'


@pytest.mark.parametrize('fault,owner', [('normal',None),('initial_ack_drop3',None),
    ('postsubmit_source_outage','A'),('postsubmit_B_execution_outage','B')])
def test_real_fault_schema_changes_only_declared_protocol_fields(fault,owner):
    rows=c.declarations()
    row=next(r for r in rows.values() if r['fault']==fault)
    data=c.scene(row)
    original=c.public.native_scene(row['case'])
    for name in data:
        if name!='owner_protocol': assert data[name]==original[name]
    expected=copy.deepcopy(original['owner_protocol'])
    if fault=='initial_ack_drop3':expected['drop_ack_packets']=3
    if owner:expected['owner_outages']=[{'owner':owner,'start':.115,'end':2.}]
    assert data['owner_protocol']==expected


def test_accepted027_has_no_route_only_ack_selector_or_ack_outage():
    contract=c.read(c.OUT/'native027_accepted_contract_001.json')
    path=Path(contract['source_archive'])/'cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp'
    build=c.read(contract['build_receipt'])
    hashes={k.replace('\\','/'):v for k,v in build['source_after'].items()}
    assert c.sha(path)==hashes['cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp']
    text=path.read_text()
    assert 'command.remaining_ack_drops=circulation_.input.owner_protocol.drop_ack_packets' in text
    ack=text.split('if(event.reason=="protocol_command_ack")',1)[1].split('if(event.reason!="protocol_command_wire")',1)[0]
    assert 'remaining_ack_drops' in ack and 'protocol_owner_available' not in ack


def test_undeclared_case_rejected():
    row=copy.deepcopy(next(iter(c.declarations().values())))
    row['case']['receiver_load']=6.
    with pytest.raises(ValueError,match='undeclared_scene'):c.scene(row)


def test_capture_retains_actual_information_and_endpoints_without_global_patch(monkeypatch):
    log=[]
    info={'status':'fake_fixture_only','rows':[1]}
    class Session:
        physical_time=.11
        def observe_protocol(self,o):log.append(('view',o));return {'owner_id':o,'now':.11}
        def protocol_command(self,o,i):log.append(('command',o,i));return {'request_id':i}
        def protocol_planning_snapshots(self,o):log.append(('received',o));return []
    def collector(*a,**k):return info,SimpleNamespace(audit_copy=lambda:{'owner':'A'})
    monkeypatch.setattr(c.request.adapter,'collect_initial_ledger',collector)
    rows=[]
    result,ledger=c.captured_collection(rows,None,Session(),'A','id',accepted='fake_pure_only')
    info['rows'].append(2)
    assert rows[0]['information']['rows']==[1] and result is info
    assert log==[('view','A'),('command','A','id'),('received','A')]


def test_private_recording_uses_original_method_code_and_does_not_change_global(monkeypatch):
    original=c.request.adapter.collect_initial_ledger
    records=[]
    def sample(value):
        return adapter.collect_initial_ledger(value)  # rebound only in function's private globals
    sample.__globals__['adapter']=c.request.adapter
    monkeypatch.setattr(c,'captured_collection',lambda r,*a,**k:(r.append(a),a)[1])
    assert c.call_with_recorded_collection(sample,records,3)==(3,)
    assert records==[(3,)] and c.request.adapter.collect_initial_ledger is original


def test_real_B_and_both_policy_binding_precede_continuation_source():
    text=inspect.getsource(c.run_branch)
    assert text.index('request.fixed_B_first_action')<text.index('request.FixedContinuationOwner')<text.index('run_continuation(')
    assert "for o in ('A', 'B')" in text
    assert 'selections["A"] != selections["B"]' not in text
    assert 'scene(row)' in text and 'supplied_inputs' not in text


def test_default_control_has_no_prediction_and_is_explicit():
    root=c.FixedDefaultRequest.__new__(c.FixedDefaultRequest)
    root.state='collected';events=[];root._record=lambda *x:events.append(x)
    root.choose()
    assert root.choice=='native_default' and root.state=='selected'
    assert events[0][1]['baseline_simulated'] is False


def test_unknown_fixed_control_cannot_select():
    root=c.FixedDefaultRequest.__new__(c.FixedDefaultRequest);root.state='unknown_collection'
    with pytest.raises(ValueError):root.choose()


def calls_fixture():
    p={'request_id':'live:1:A:x','owner_id':'A','kind':'route','from':0,'next':2}
    row={'at':.11,'kind':'route','retry':False,'request':p,'reply':{'status':'pending'}}
    box={p['request_id']:{'kind':'route','request':copy.deepcopy(p)}}
    return [row,{**copy.deepcopy(row),'at':.61,'retry':True}],box


def test_all_immutable_calls_and_denominator():
    calls,box=calls_fixture()
    assert v.immutable_calls(calls,box)==(1,2)


@pytest.mark.parametrize('mutation',[
    lambda rows,box:rows[1]['request'].update(next=1),
    lambda rows,box:rows[0].update(retry=True),
    lambda rows,box:rows[1].update(retry=False),
    lambda rows,box:rows[1].update(at=.01),
    lambda rows,box:rows[1].update(at=True),
    lambda rows,box:box.clear(),
    lambda rows,box:box.update(extra={'kind':'route','request':{}}),
    lambda rows,box:rows[1]['request'].update(owner_id='B'),
])
def test_retry_and_outbox_tamper_rejected(mutation):
    calls,box=calls_fixture();mutation(calls,box)
    with pytest.raises((ValueError,KeyError)):v.immutable_calls(calls,box)


def test_pair_requires_both_full_assessed_and_strict_zero():
    row={'business':{'status':'assessed','completion':dict.fromkeys(c.contract.JOBS,10.)}}
    assert v.pair_comparison(row,row)['all_five_strict_nonregression'] is True
    trial=copy.deepcopy(row);trial['business']['completion']['loaded']+=1e-12
    assert v.pair_comparison(row,trial)['all_five_strict_nonregression'] is False
    trial['business']['status']='unknown'
    assert v.pair_comparison(row,trial)['all_five_strict_nonregression'] is None


def root_fixture(state='unknown_prediction'):
    root=SimpleNamespace(request_id='normal:block0_load0:budget_two',started_ns=10,
        deadline_ns=100000010,cutoff_ns=60000010,state=state,choice=None,hop=None,command_id=None,
        events=[],session=SimpleNamespace(physical_time=40.))
    root.evidence=lambda:c.request.InitialOwnerRequest.evidence(root)
    return root


def test_root_codec_and_outside_return_are_charged(monkeypatch):
    root=root_fixture()
    # Both modules use the same real monotonic clock. This checks ordering only,
    # not a fake-clock performance or100ms outcome claim.
    root.started_ns=c.time.perf_counter_ns();root.deadline_ns=root.started_ns+100000000
    root.cutoff_ns=root.started_ns+60000000
    holders=[];record=c.publish_root(root,holders)
    assert holders[0] is record and record['outside_return_ns']>=record['value']['body_finished_ns']
    raw={'root_records':holders,'key':'normal/block0_load0/budget_two','failure':None,'root_constructed':True,
         'specification':{'method':'budget_two'},'outbox':{}}
    got=v.root_replay(raw)
    assert got['closed'] is False and got['status']=='unknown_prediction'


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(outside_return_ns=0),
    lambda r:r.update(warm_caller_elapsed_ns=0),
    lambda r:r['value']['evidence'].update(root_id='wrong'),
    lambda r:r['ledger'].update(evidence_sha256='0'*64),
    lambda r:r.update(return_codec='{}'),
    lambda r:r.update(closed=True),
])
def test_root_clock_codec_and_falseclosure_rejected(mutation):
    root=root_fixture();root.started_ns=c.time.perf_counter_ns();root.deadline_ns=root.started_ns+100000000;root.cutoff_ns=root.started_ns+60000000
    rows=[];c.publish_root(root,rows);mutation(rows[0])
    raw={'root_records':rows,'key':'normal/block0_load0/budget_two','failure':None,'root_constructed':True,
         'specification':{'method':'budget_two'},'outbox':{}}
    with pytest.raises(ValueError):v.root_replay(raw)


def test_missing_root_not_silently_omitted():
    with pytest.raises(ValueError):v.root_replay({'root_records':[],'failure':None,'root_constructed':False})
    assert v.root_replay({'root_records':[],'failure':'constructor failed','root_constructed':False})['closed'] is False


def test_no_later_capability_deepcopy_in_campaign():
    source=inspect.getsource(c.run_branch)
    assert "'decisions': {o: p.decisions" in source
    assert 'copy.deepcopy(p.decisions)' not in source


def test_launcher_one_shared_owned600_not_perbranch():
    source=inspect.getsource(launch)
    assert launch.LIMIT==600.
    assert source.count('bounded_windows_job.run(')==1
    assert 'timeout=remaining' in source and 'execution_claim.json' in source
    assert 'external_application_startup_clock_required' in source


def test_core_sources_old_plan_unchanged():
    previous=c.read(c.OUT/'initial_owner_route_source_prepare_002/plan.json')
    for name in ('initial_owner_route_request.py','initial_owner_route_contract.py','initial_owner_route_worker.py'):
        relative='scripts/experiments/g31_ics_circulation/'+name
        assert c.sha(c.ROOT/relative)==previous['source_sha256'][relative]


def test_capture_function_does_not_read_peer_or_result():
    source=inspect.getsource(c.captured_collection)
    assert 'observe_protocol(owner)' in source and 'protocol_planning_snapshots(owner)' in source
    assert 'result_at' not in source and 'checkpoint' not in source


def test_campaign_returns_only_post_horizon_result_to_assessment():
    source=inspect.getsource(c.run_branch)
    assert source.index('run_continuation(')<source.index('result = session.result_at(')<source.index('outcome = full_outcome(')
    assert 'result_at' not in inspect.getsource(c.run_continuation)


def test_endpoint_wrong_owner_rejected_before_revalidation():
    with pytest.raises(ValueError,match='initial_endpoint_owner_or_epoch'):
        v.endpoint_replay({'endpoints':{'owner':'A','at':.11,'view':{'owner_id':'B','now':.11}},'information':{}})


def test_exact_image_actual_startup_and_close_without_prediction(tmp_path):
    old=c.read(c.OUT/'initial_owner_route_source_prepare_002/plan.json')
    with (tmp_path/'stderr.log').open('x',encoding='utf8') as stderr:
        client=c.InitialOwnerClient(old['image']['path'],old['image']['version'],'initial_A_two',timeout=30.,stderr=stderr)
        try:
            ready=copy.deepcopy(client.ready)
            assert ready['proof']['participation_contract_sha256']==c.contract.contract_sha256()
            assert ready['proof']['logical_choices']==2 and ready['mode']=='initial_A_two'
            assert ready['loaded_sources'] and client.sequence==0
            closed=client.close()
            assert closed['reply']['requests']==0 and closed['process_exit_code']==0
        finally:
            if not client.closed:client.abort()
    saved={'status':'passed_functional_startup_zero_predictions','image':old['image'],
        'ready':ready,'close':closed,'predictor_evaluations':0,'native_calls':0,
        'not_a_performance_sample':True}
    directory=Path(os.environ.get('G31_INITIAL_CAMPAIGN_PURE_OUTPUT',str(tmp_path)))
    c.write(directory/'image_startup.json',saved)


def rpc_fixture():
    root={'root_id':'normal:block0_load0:budget_two','root_started_ns':10,'root_deadline_ns':100000010,
        'decision_cutoff_ns':60000010,'choice':None,'events':[]}
    packet={'schema':c.contract.SCHEMA,'bundle':{'fixture_only':1},'root_started_ns':10,
        'root_deadline_ns':100000010,'decision_cutoff_ns':60000010,
        'participation_contract_sha256':c.contract.contract_sha256()}
    payload={'schema':c.contract.SCHEMA,'snapshot_sha256':c.image.sha_bytes(c.image.encode(packet['bundle'])),
        'native_authority':False,'full_32_search_performed':False,
        'participation_contract_sha256':c.contract.contract_sha256(),
        'budget':{**{k:packet[k] for k in ('root_started_ns','root_deadline_ns','decision_cutoff_ns')},
                  'worker_started_ns':60000011},
        'counts':{'logical_choices':2,'baseline_evaluation_calls':0,'complete_baselines':0,'additional_candidate_calls':0},
        'baseline':None,'selection':{'choice':None,'status':'unknown_no_baseline_budget'}}
    reply={'request_id':root['root_id'],'sequence':1,'payload':payload}
    sample={'request_id':root['root_id'],'sequence':1,'request':{'request_id':root['root_id'],'sequence':1,'snapshot':packet},
        'response':reply,'caller_admitted_ns':20,'caller_decoded_ns':60000100,'caller_body_finished_ns':60000200}
    root['events']=[{'stage':'two_choice_reply','value':copy.deepcopy(reply)}]
    raw={'root_records':[{'value':{'evidence':root},'outside_return_ns':100000000}],
        'initial_endpoint_records':{'A':[{'information':{'bundle':copy.deepcopy(packet['bundle'])}}]}}
    return sample,raw


def test_actual_RPC_binding_preserves_no_baseline_unknown():
    sample,raw=rpc_fixture()
    assert v.rpc_replay(sample,raw)['baseline_evaluation_calls']==0


@pytest.mark.parametrize('mutate',[
    lambda s,r:s.update(request_id='other'),
    lambda s,r:s['request'].update(sequence=2),
    lambda s,r:s['request']['snapshot']['bundle'].update(fixture_only=2),
    lambda s,r:s['response']['payload'].update(snapshot_sha256='0'*64),
    lambda s,r:s['response']['payload']['counts'].update(baseline_evaluation_calls=True),
    lambda s,r:s['response']['payload']['selection'].update(choice='native_default'),
    lambda s,r:s['response']['payload']['budget'].update(worker_started_ns=1),
    lambda s,r:r['root_records'][0]['value']['evidence']['events'].clear(),
    lambda s,r:s.update(caller_body_finished_ns=100000001),
])
def test_RPC_clock_payload_owner_action_and_count_tamper(mutate):
    sample,raw=rpc_fixture();mutate(sample,raw)
    with pytest.raises(ValueError):v.rpc_replay(sample,raw)


def test_CapturedRequest_new_endpoint_codec_inside_root():
    root=c.CapturedRequest.__new__(c.CapturedRequest)
    root.__dict__.update(root_fixture().__dict__)
    root.__dict__.pop('evidence')
    root.started_ns=c.time.perf_counter_ns();root.deadline_ns=root.started_ns+100000000;root.cutoff_ns=root.started_ns+60000000
    root.initial_endpoint_records=[{'large_actual_endpoint_fixture':[1,2,3]}]
    root.B_endpoint_records=[{'peer_owner_query_fixture':True}]
    result=root.evidence()
    decoded=c.image.artifact_decode(result['encoded'])
    assert decoded['initial_endpoint_records']=={'A':root.initial_endpoint_records,'B':root.B_endpoint_records}
    root.initial_endpoint_records[0]['large_actual_endpoint_fixture'].append(4)
    assert decoded['initial_endpoint_records']['A'][0]['large_actual_endpoint_fixture']==[1,2,3]


def test_run_branch_actual_wiring_order_with_explicit_pure_fakes(monkeypatch):
    log=[]
    row=next(r for r in c.declarations().values() if r['method']=='budget_two')
    class Session:
        physical_time=0.
        def __init__(self,data):log.append('session')
        def advance_to(self,now,**kwargs):
            self.physical_time=now;log.append(('advance',now))
            return {'physical_time':now,'status':'reached','horizon_complete':True}
        def result_at(self,now):log.append('result_after_continuation');return {}
        def offline_state_sha256(self):return '0'*64
    class Root:
        def __init__(self,native,session,accepted,predictor,client,request_id):
            self.session=session;self.started_ns=c.time.perf_counter_ns();self.initial_endpoint_records=[]
            self.planning={'A':'a','B':'b'};self.channels={'A':'ca','B':'cb'};self.ledger=object()
            self.choice=None;self.state='admitted';log.append('root_admission')
        def collect(self):self.session.physical_time=.11;self.state='collected';log.append('collect_A')
        def choose(self):self.state='selected';self.choice='native_default';log.append('choose_A')
        def final_revalidate_and_submit(self):self.state='pending_first_hop_and_ack';log.append('final_A')
    def fixed_b(session,client,planning,**kwargs):
        assert session.physical_time==.11;log.append('fixed_B_at_.11')
        return {'request_id':'b'},object()
    def policy(native,session,client,owner,*args):
        log.append('fixed_actor_'+owner)
        return SimpleNamespace(decisions=[],exchanges=[],quiet_periods=[],choices=[],returns=[],supplies=[],recovery=[])
    def continuation(session,client,policies,root,roots,batches):
        assert set(policies)=={'A','B'} and log[-2:]==['fixed_actor_A','fixed_actor_B']
        log.append('continuation_advance');session.physical_time=40.;return batches,0,'finished'
    monkeypatch.setattr(c,'CapturedRequest',Root)
    monkeypatch.setattr(c.request,'fixed_B_first_action',fixed_b)
    monkeypatch.setattr(c.request,'FixedContinuationOwner',policy)
    monkeypatch.setattr(c.request.adapter,'bind_native027',lambda *a,**k:({},SimpleNamespace(audit_copy=lambda:{})))
    monkeypatch.setattr(c,'run_continuation',continuation)
    monkeypatch.setattr(c,'full_outcome',lambda *a:{'status':'pure_fake_only'})
    accepted=SimpleNamespace(active_for=lambda k:True,branch_specification=lambda k:row)
    raw=c.run_branch(SimpleNamespace(NativeSession=Session),accepted,'fixture',row,{'native_contract_reference':{}},None)
    assert raw['failure'] is None
    assert log.index('root_admission')<log.index('collect_A')<log.index('fixed_B_at_.11')<log.index('continuation_advance')
    assert log[-1]=='result_after_continuation'


def test_json_transport_equivalence_keeps_order_and_numeric_types():
    value={'nodes':[(0,2,1.)],'other':[1,2]}
    decoded=json.loads(c.ordered(value))
    assert decoded!=value and c.ordered(decoded)==c.ordered(value)
    assert c.ordered({'x':1})!=c.ordered({'x':1.})
    assert c.ordered({'a':1,'b':2})!=c.ordered({'b':2,'a':1})


def test_partial_boundary_has_no_diagnostic_advance_or_refresh(monkeypatch):
    log=[]
    class Session:
        physical_time=.11
        def advance_until_owner_notification(self,*a,**k):
            log.append('original_partial_boundary')
            return {'status':'budget_exhausted','physical_time':.11,'timestamp_complete':False}
        def advance_to(self,*a,**k):raise AssertionError('must preserve partial cut')
    client=SimpleNamespace(activate=lambda *a,**k:log.append('activate'),
                           refresh_owner=lambda *a,**k:log.append('refresh'))
    root=SimpleNamespace(state='pending_first_hop_and_ack')
    monkeypatch.setattr(c,'publish_root',lambda root,rows:rows.append({'unknown_partial':True}))
    rows=[];batches=[]
    _,_,status=c.run_continuation(Session(),client,{},root,rows,batches)
    assert status=='unknown_native_boundary' and log==['original_partial_boundary'] and len(rows)==1


def test_exception_branch_diagnostic_source_never_unconditionally_advances():
    source=inspect.getsource(c.run_branch)
    tree=ast.parse(source)
    parent={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
           and node.func.attr=='result_at']
    assert len(calls)==1
    node=parent[calls[0]]
    while not isinstance(node,ast.If):node=parent[node]
    condition=ast.unparse(node.test)
    assert "failure is None" in condition and "status == 'finished'" in condition and 'contract.HORIZON' in condition


def test_final_validation_replays_pre_submit_choice_before_overrun(monkeypatch):
    root=root_fixture('unknown_final_fixture_only')
    root.started_ns=c.time.perf_counter_ns()-200000000
    root.deadline_ns=root.started_ns+100000000;root.cutoff_ns=root.started_ns+60000000
    root.choice='native_default'
    seen=[]
    verdict={'status':'fresh_local_precondition_checked','source':{'tray_id':'L'},'checked_choice':'prefer_2'}
    def validate(view,bundle,choice):
        seen.append(choice)
        return {**verdict,'checked_choice':choice}
    monkeypatch.setattr(c.contract,'validate_final_local',validate)
    root.events=[
        {'stage':'two_choice_reply','wall_ns':root.started_ns+1,'at':.11,
         'value':{'payload':{'selection':{'choice':'prefer_2'}}}},
        {'stage':'final_local_and_receiver_check','wall_ns':root.started_ns+2,'at':.11,
         'value':{'view':{},'verdict':verdict}},
        {'stage':'pre_submit_root_overrun_default_incumbent','wall_ns':root.deadline_ns+1,'at':.11,'value':{}}]
    rows=[];c.publish_root(root,rows)
    endpoints={'A':[{'information':{'bundle':{}}}]}
    # Add the captured endpoint image then rebuild its exact returned encoding.
    evidence=rows[0]['value']['evidence'];evidence['initial_endpoint_records']=endpoints
    encoded=c.image.artifact_encode(evidence)
    rows[0]['ledger'].update(evidence_sha256=c.image.sha_bytes(encoded),bytes=len(encoded))
    rows[0]['return_codec']=c.image.artifact_encode(rows[0]['ledger']).decode()
    raw={'root_records':rows,'key':'normal/block0_load0/budget_two','failure':None,'root_constructed':True,
         'specification':{'method':'budget_two'},'outbox':{},'initial_endpoint_records':endpoints}
    assert v.root_replay(raw)['closed'] is False
    assert seen==['prefer_2']
