"""Pure wiring/source/complete-outbox gate; no native or prediction."""
import copy
import inspect
import time
from types import SimpleNamespace,FunctionType
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_gated_evidence as i
from scripts.experiments.g31_ics_circulation import initial_owner_route_gate_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_gate_campaign as v
from scripts.experiments.g31_ics_circulation import initial_owner_route_outbox_trace as t


class QuerySession:
    physical_time=.11
    def __init__(self):self.ack={}
    def submit_protocol_command(self,p):return {'status':'accepted','request_id':p['request_id']}
    submit_protocol_transfer=submit_protocol_command
    def protocol_command(self,o,k):return {'last_delivered_ack':copy.deepcopy(self.ack.get(k,{}))}
    protocol_request=protocol_command


def actual_client_fixture():
    session=QuerySession();client=i.make_client(session)
    client.activate('A',{'kind':'synthetic_closed_source_shape'})
    identity=client.submit('A','route','x',business_bag_id='loaded',tray_id='L')
    session.ack[identity]={'status':'updated','delivered_at':.11}
    t.refresh(client,'A');t.refresh(client,'A')
    raw={'calls':client.calls,'outbox':client.rows,'request_creations':client.creations,
        'owner_activation_admissions':client.roots,'ack_handling':client.ack_handling,
        'outbox_query_trace':client._root_outbox_trace.audit_copy(),'root_records':[],'failure':None}
    return session,client,identity,raw


def test_complete_actual_transport_replay_without_projection_only_trust():
    _,client,identity,raw=actual_client_fixture()
    result=v.complete_query_replay(raw)
    assert result['status']=='passed_complete_actual_refresh_outbox_replay' and result['queries']==2
    raw['outbox'][identity]['ack']['status']='rejected'
    with pytest.raises(ValueError,match='complete_actual_outbox'):v.complete_query_replay(raw)


@pytest.mark.parametrize('mutation',['creation','context','missing_body','extra_admission_ID','ACK_handling'])
def test_transport_runtime_lineage_tampering_rejected(mutation):
    _,client,identity,raw=actual_client_fixture();raw=copy.deepcopy(raw)
    if mutation=='creation':raw['request_creations'][identity]['creating_root']='activation:99:A'
    if mutation=='context':raw['outbox_query_trace']['reads'][0]['handling_root']='activation:99:A'
    if mutation=='missing_body':raw['outbox_query_trace']['ack_bodies']=[]
    if mutation=='extra_admission_ID':raw['owner_activation_admissions'][0]['protocol_ids'].append('invented')
    if mutation=='ACK_handling':raw['ack_handling'][0]['ack']['status']='rejected'
    with pytest.raises((ValueError,IndexError,KeyError)):v.complete_query_replay(raw)


def test_original_exact_transport_class_is_retained_and_not_patched():
    session=QuerySession();old_type=i.old.public.LocalTransport;old_refresh=old_type.refresh_owner
    client=i.make_client(session)
    assert type(client) is old_type and old_type.refresh_owner is old_refresh
    assert type(client._root_outbox_trace) is t.OutboxTrace
    assert i.CapturedRequest.observe_after_boundary is i.TRACED_OBSERVE
    assert i.CapturedRequest.drain_and_finish_if_closed is i.TRACKED_DRAIN
    assert i.request.InitialOwnerRequest.observe_after_boundary is i.SOURCE_FUNCTIONS[i.TRACED_OBSERVE]


def test_closed_source_factory_preserves_cadence_admissions_and_firsthop():
    proof=i.integration_proof()
    assert proof['scheduler']['exact_full_ast_restoration'] and proof['scheduler']['refresh_AST_restored']
    assert proof['refresh_sites']=={'initial_collection':1,'root_observe':1,'owner_activate':1,'scheduler_fallback_and_final':2}
    assert proof['global_monkeypatch'] is False and proof['scheduler']['firsthop_detector_changed'] is False
    assert i.run_continuation.__globals__['ActualAdvanceChain'] is i.ActualAdvanceChain
    assert i.run_continuation.__globals__['_traced_refresh'] is t.refresh
    assert c.run_branch.__globals__['request'].FixedContinuationOwner is i.TracedContinuationOwner
    assert c.run_branch.__globals__['CapturedRequest'] is i.CapturedRequest
    assert c.run_branch.__globals__['run_continuation'] is i.run_continuation
    assert c.worker.__globals__['run_branch'] is c.run_branch
    assert 'verify_initial_owner_route_gate_campaign' in c.worker.__code__.co_names
    assert i.request.FixedContinuationOwner is not i.TracedContinuationOwner


def test_private_policy_inventory_maps_only_exact_registered_method():
    client=object.__new__(i.old.public.LocalTransport)
    policy=object.__new__(i.TracedContinuationOwner)
    inventory=i.inventory({'A':policy,'B':policy},client)
    assert len(inventory)>30
    assert any(value['function'] is i.TRACED_ACTIVATE for value in inventory.values())


def test_fake_session_cannot_enter_actual_chain():
    session=QuerySession();client=i.make_client(session)
    root=SimpleNamespace(session=session,client=client,native=object(),accepted={})
    with pytest.raises(ValueError,match='accepted_session'):i.ActualAdvanceChain(session,client,root,{})


def test_root_proof_normalization_isolates_complete_live_state():
    session,client,identity,raw=actual_client_fixture()
    root=SimpleNamespace(client=client)
    proof=i.old.normalization.normalize(i.root_runtime_proof(root))
    client.rows[identity]['ack']['status']='changed_by_caller'
    assert proof['outbox'][identity]['ack']['status']=='updated'
    assert proof['trace']['ack_bodies'][0]['status']=='updated'
    assert proof['calls'][0]['request'] is not client.calls[0]['request']


def test_onebuild_finish_checks_new_evidence_identity_and_keeps_old_body():
    assert i.finish_root.__code__ is i.single.finish_root.__code__
    assert i.publish_root.__code__ is i.single.publish_root.__code__
    assert i.finish_root.__globals__['evidence'] is i.EVIDENCE
    assert i.single.finish_root.__globals__['evidence'] is i.single.evidence
    assert i.old.CapturedRequest.evidence is not i.EVIDENCE


def test_all18_declared_inputs_and_request_budget_remain_old():
    assert c.declarations()==i.old.declarations() and len(c.declarations())==18
    assert c.LIMIT==600. and c.contract.BUDGET_NS==100_000_000
    assert c.contract.FINALIZATION_RESERVE_NS==40_000_000
    assert c.contract.observed_first_hop is i.old.contract.observed_first_hop
    assert c.scene is i.old.scene


def test_private_verifier_retains_original_endpoint_physical_RPC_codes():
    assert v._original_verify_branch.__code__ is v.old.verify_branch.__code__
    assert v.rpc_replay.__code__ is v.old.rpc_replay.__code__
    assert v.verify_saved.__code__ is v.old.verify_saved.__code__
    assert v.verify_saved.__globals__['verify_branch'] is v.verify_branch
    assert v._original_verify_branch.__globals__['c'] is c


def test_owned_launcher_retains_entire_old600_job_and_new_entrypoint():
    from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_gate_campaign as launch
    assert launch.main.__code__ is launch.old.main.__code__
    assert launch.main.__globals__['LIMIT']==600.
    assert launch.main.__globals__['MODULE'].endswith('.initial_owner_route_gate_campaign')
    assert launch.old.MODULE.endswith('.initial_owner_route_campaign_v3')


def test_prepare_rejects_missing_or_changed_frozen_archive(tmp_path):
    from scripts.experiments.g31_ics_circulation import prepare_initial_owner_route_gate_campaign as prepare
    source=tmp_path/'source.py';source.write_text('original',encoding='utf8')
    archive=tmp_path/'archive.py';archive.write_text('original',encoding='utf8')
    plan={'source_sha256':{str(source):c.sha(source)},'source_archive':{str(source):'archive.py'}}
    prepare.verify_frozen(tmp_path,plan)
    archive.write_text('changed',encoding='utf8')
    with pytest.raises(ValueError,match='frozen_source'):prepare.verify_frozen(tmp_path,plan)
    plan['source_archive']={}
    with pytest.raises(ValueError,match='source_domain'):prepare.verify_frozen(tmp_path,plan)


def test_actual_saved_all_outbox_ACK_shapes_replay_without_backfilling_history():
    """Saved final ACK shapes at H40 only; not authority for earlier skips."""
    import gzip,hashlib,json
    path=c.OUT/'initial_owner_route_campaign_v3_prepare_001/raw/normal/block0_load0/fixed_default.json.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='84633d9fa8c503c6b92a2e88f814e914b083bac72850c4ef91a86ccb5da247dd'
    with gzip.open(path,'rt',encoding='utf8') as stream:saved=json.load(stream)
    class SavedShapeSession(QuerySession):
        def submit_protocol_command(self,payload):
            return copy.deepcopy(next(row['reply'] for row in saved['calls']
                if not row['retry'] and row['request']['request_id']==payload['request_id']))
        submit_protocol_transfer=submit_protocol_command
    session=SavedShapeSession();client=i.make_client(session)
    for call in saved['calls']:
        if call['retry']:continue
        payload=copy.deepcopy(call['request']);identity=payload.pop('request_id')
        owner=payload.pop('owner_id');payload.pop('kind',None);session.physical_time=call['at']
        client.activate(owner,{'kind':'saved_final_shape_pure_fixture'})
        label=identity[len('live:1:'+owner+':'):]
        assert client.submit(owner,call['kind'],label,**payload)==identity
    session.physical_time=40.
    session.ack={key:copy.deepcopy(row.get('ack',{})) for key,row in saved['outbox'].items()}
    for _ in range(2):
        for owner in ('A','B'):
            client.activate(owner,{'kind':'saved_H40_final_shape_pure_fixture'})
            t.refresh(client,owner,retry=False)
    assert set(row['kind'] for row in client.rows.values())>={'demand','planning_snapshot','planning_snapshot_v3','transfer','route'}
    data=client._root_outbox_trace.audit_copy()
    assert t.verify_refresh_inventory(data,client.calls,client.creations)['queries']==2*len(client.rows)
    replay=t.Replay(data,client.calls,client.creations).advance(len(data['reads']),len(client.calls)).finish()
    assert v.exact(replay['rows'],client.rows) and v.exact(replay['ack_handling'],client.ack_handling)
    normalized=i.old.normalization.normalize({'trace':data,'outbox':client.rows})
    assert normalized['outbox']==client.rows


def test_compiled_integrated_scheduler_keeps_IDs_and_replays_every_actual_refresh():
    """Explicit synthetic endpoint fixture; never admitted by the native factory."""
    class Session(QuerySession):
        def advance_until_owner_notification(self,owners,cursors,horizon,**kwargs):
            self.physical_time=horizon
            notices=({'A':{'sequence':1 if horizon==.11 else 2,'observed_at':horizon,'change_mask':2}}
                     if horizon in (.11,.11+2*.05) else {})
            return {'status':'notified' if notices else 'horizon_reached','physical_time':horizon,
                'timestamp_complete':True,'horizon_complete':True,'notifications':notices}
        def advance_to(self,horizon,**kwargs):
            self.physical_time=horizon
            return {'status':'reached','physical_time':horizon,'horizon_complete':True}
        def observe_protocol(self,owner):return {'owner_id':owner,'now':self.physical_time}
    class Policy:
        pending=None;peer_quiet_until=0.
        def __init__(self,client,owner,traced):self.client,self.owner,self.traced=client,owner,traced
        def activate(self,trigger):
            self.client.activate(self.owner,trigger)
            if self.traced:t.refresh(self.client,self.owner)
            else:self.client.refresh_owner(self.owner)
    class PureChain(i.ActualAdvanceChain):
        def __init__(self,session,client,root,policies):
            i.gate._RecordedChain.__init__(self,session,client,root)
            root._observation_advance_chain=self
    fake_contract=SimpleNamespace(observed_first_hop=lambda view,source:None,
        closure=lambda choice,hop,command,**kw:{'closed':kw['timestamp_complete'] and kw['now']>=.11+2*.05,
            'status':'closed_native_default_first_hop'})
    def run(candidate):
        session=Session();client=i.make_client(session) if candidate else i.old.public.LocalTransport(session)
        client.activate('A',{'kind':'synthetic_initial'});client.submit('A','route','pending',tray_id='L')
        class Root:
            _record=i.request.InitialOwnerRequest._record
        root=Root();root.client=client;root.session=session;root.request_id='synthetic-root'
        root.events=[];root.state='pending_first_hop_and_ack';root.source={};root.hop=None
        root.command_id=None;root.choice='native_default';root.last_boundary=None
        observer=i.TRACED_OBSERVE if candidate else i.request.InitialOwnerRequest.observe_after_boundary
        Root.observe_after_boundary=i.private(observer,{'contract':fake_contract})
        if candidate:
            helper=i.private(i.gate._actual_root_drain,{'ActualAdvanceChain':PureChain})
            Root.drain_and_finish_if_closed=i.private(i.TRACKED_DRAIN,{'contract':fake_contract,'_actual_root_drain':helper})
        else:Root.drain_and_finish_if_closed=i.private(i.request.InitialOwnerRequest.drain_and_finish_if_closed,{'contract':fake_contract})
        def publish(root,holder):
            holder.append({'value':{'evidence':{'events':copy.deepcopy(root.events),
                **({'runtime_query_proof':i.old.normalization.normalize(i.root_runtime_proof(root))} if candidate else {})},
                'body_finished_ns':time.perf_counter_ns()}})
        function=i.run_continuation if candidate else i.old.run_continuation
        function=i.private(function,{'ActualAdvanceChain':PureChain,'contract':SimpleNamespace(HORIZON=.31),
            'public':SimpleNamespace(v1=SimpleNamespace(START=.11,PERIOD=.05),MAX_ACTIVATIONS=100),
            'publish_root':publish})
        policies={o:Policy(client,o,candidate) for o in ('A','B')};records=[];batches=[]
        returned=function(session,client,policies,root,records,batches)
        return client,root,records,batches,returned
    original,candidate=run(False),run(True)
    project=lambda roots:[{k:v for k,v in r.items() if k!='accepted_wall_ns'} for r in roots]
    assert project(original[0].roots)==project(candidate[0].roots)
    assert original[0].calls==candidate[0].calls and original[0].rows==candidate[0].rows
    assert original[3:]==candidate[3:]
    assert sum(e['stage']=='continuation' for e in original[1].events)==3
    assert sum(e['stage']=='continuation' for e in candidate[1].events)==2
    client,root,records,batches,_=candidate
    raw={'calls':client.calls,'outbox':client.rows,'request_creations':client.creations,
        'owner_activation_admissions':client.roots,'ack_handling':client.ack_handling,
        'outbox_query_trace':client._root_outbox_trace.audit_copy(),'root_records':records,'failure':None,
        'observation_gate_audit':root._observation_advance_chain.audit_copy()}
    checked=v.complete_query_replay(raw)
    assert checked['gate_checkpoints']==6
    report=v.chain_verifier.verify(records[0]['value']['evidence']['events'],batches,
        raw['observation_gate_audit'],client.roots,client.calls,root.request_id)
    assert report['skips']==1
    bad=copy.deepcopy(raw)
    event=next(e for e in bad['root_records'][0]['value']['evidence']['events']
        if e['stage']=='root_observation_gate' and e['value']['decision']['skip'])
    identity=next(iter(event['value']['inputs']['outbox']))
    event['value']['inputs']['outbox'][identity]['terminal']=True
    with pytest.raises(ValueError,match='full_outbox_reconstruction'):v.complete_query_replay(bad)
