"""Source/call-chain tests only; synthetic sessions cannot grant native authority."""
import copy
import json
from types import SimpleNamespace, FunctionType
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_gate_adapter as a
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_gate_adapter as v


class Session:
    def __init__(self):self.physical_time=.11;self.fail=False;self.notices={}
    def advance_until_owner_notification(self,owners,cursors,horizon,**kwargs):
        if self.fail:raise RuntimeError('injected advance failure')
        self.physical_time=horizon
        return {'physical_time':horizon,'timestamp_complete':True,'horizon_complete':True,
            'status':'notified' if self.notices else 'horizon_reached','notifications':copy.deepcopy(self.notices)}
    def advance_to(self,horizon,**kwargs):
        self.physical_time=horizon
        return {'physical_time':horizon,'status':'reached','horizon_complete':True,
                'result':{'wall_seconds':.0001}}


class Client:
    def __init__(self,session):
        self.session=session;self.calls=[];self.roots=[]
        self.rows={'x':{'kind':'route','request':{'request_id':'x','owner_id':'A'},
                        'terminal':False,'next_retry':1.}}
    def activate(self,owner,trigger):
        self.roots.append({'root_id':f'activation:{len(self.roots)}:{owner}',
            'owner':owner,'accepted_at':self.session.physical_time,'scope':'owner_activation_proxy',
            'trigger':copy.deepcopy(trigger),'protocol_ids':[]})


class Root:
    def __init__(self,session,client):
        self.session=session;self.client=client;self.events=[];self.request_id='test'
        self.state='pending_first_hop_and_ack';self.last_boundary=None
    def _record(self,stage,value):
        self.events.append({'stage':stage,'at':self.session.physical_time,'value':copy.deepcopy(value)})


def fixture():
    session=Session();client=Client(session);root=Root(session,client)
    return session,client,root,a._RecordedChain(session,client,root),[]


def step(f,at,*,cursor=None,wrong_trigger=False,postview_time=None,drain=True):
    session,client,root,chain,batches=f
    response=chain.notification_advance(['A','B'],cursor or {'A':0,'B':0},at,max_events=100000)
    batches.append({'deadline':at,'response':copy.deepcopy(response)})
    before=len(client.roots);skip=chain.decide(response)
    root.last_boundary=copy.deepcopy(response)
    client.activate('A',{'kind':'wrong' if wrong_trigger else 'initial_A_continuation','root_id':root.request_id})
    if not skip:
        root._record('continuation',{'view':{'now':at}})
        if drain:
            result=chain.root_drain(at,max_events=100000);root._record('mandatory_drain',result)
            root._record('post_drain_observation',{'view':{'now':at if postview_time is None else postview_time}})
    chain.after_step(skip,before)
    return skip


def saved(f):
    _,client,root,chain,batches=f
    # Exercise actual saved JSON tuple/list representation, not Python equality.
    return json.loads(json.dumps([root.events,batches,chain.audit_copy(),client.roots,client.calls,root.request_id]))


def test_real_call_core_full_then_skip_and_saved_independent_recompute():
    f=fixture();assert not step(f,.11);assert step(f,.16)
    report=v.verify(*saved(f))
    assert report['steps']==2 and report['skips']==1 and report['native_calls']==3
    assert report['policy_outbox_replay_still_required'] and not report['native_authenticity_certified']
    assert len(f[1].roots)==2 and f[2].last_boundary['physical_time']==.16


def test_parameter_and_result_snapshots_do_not_alias_native_or_caller():
    f=fixture();session,client,root,chain,batches=f
    cursors={'A':0,'B':0};response=chain.notification_advance(['A','B'],cursors,.11,max_events=100000)
    cursors['A']=999;response['physical_time']=100
    assert chain.calls[0]['args'][1]['A']==0 and chain.calls[0]['response']['physical_time']==.11
    assert not chain.decide(response)
    assert root.events[-1]['value']['decision']['reason']=='unobserved_native_advance_or_mutation'


@pytest.mark.parametrize('kind',['unwrapped_advance','extra_tracked_drain','missing_full_drain','wrong_postview','wrong_admission'])
def test_unknown_or_incomplete_chain_never_silently_skips(kind):
    f=fixture();session,client,root,chain,batches=f
    assert not step(f,.11,drain=kind!='missing_full_drain',
        postview_time=.1 if kind=='wrong_postview' else None,wrong_trigger=kind=='wrong_admission')
    if kind=='unwrapped_advance':session.physical_time=.12
    if kind=='extra_tracked_drain':chain.root_drain(.11,max_events=100000)
    assert not step(f,.16)


@pytest.mark.parametrize('change',['submission','due_retry','A_notice','stale_notice','cursor_gap'])
def test_actual_changed_inputs_fall_back(change):
    f=fixture();assert not step(f,.11)
    if change=='submission':f[1].calls.append({'request_id':'new'})
    if change=='due_retry':f[1].rows['x']['next_retry']=.16
    if change=='A_notice':f[0].notices={'A':{'sequence':1,'observed_at':.16,'change_mask':16}}
    if change=='stale_notice':f[0].notices={'B':{'sequence':1,'observed_at':.15,'change_mask':2}}
    assert not step(f,.16,cursor={'A':1,'B':0} if change=='cursor_gap' else None)


def test_error_is_retained_and_original_exception_propagates():
    f=fixture();f[0].fail=True
    with pytest.raises(RuntimeError,match='injected'):f[3].notification_advance(['A','B'],{'A':0,'B':0},.16,max_events=100000)
    assert len(f[3].calls)==1 and 'injected' in f[3].calls[0]['error']
    assert f[3].calls[0]['before']==f[3].calls[0]['after']==.11


@pytest.mark.parametrize('field',['decision','boolean','batch','notification','clock','drain','admission','counts','missing_completion','reorder'])
def test_saved_tampering_cannot_supply_a_runtime_or_replay_permission(field):
    f=fixture();step(f,.11);step(f,.16)
    events,batches,audit,roots,calls,identity=saved(f)
    proofs=[e for e in events if e['stage']=='root_observation_gate']
    completions=[e for e in events if e['stage']=='root_observation_gate_completion']
    if field=='decision':proofs[1]['value']['decision']['skip']=False
    if field=='boolean':
        # A fabricated caller Boolean plus a cursor gap must fail recomputation.
        proofs[1]['value']['inputs']['all_native_advances_observed']=True
        proofs[1]['value']['inputs']['cursor_before']['A']=55
    if field=='batch':batches[1]['response']['horizon_complete']=False
    if field=='notification':proofs[1]['value']['notification_call']['response']['notifications']['C']={}
    if field=='clock':audit['calls'][1]['before']=.1
    if field=='drain':completions[0]['value']['actual_drain_call']['ordinal']=2
    if field=='admission':roots[1]['trigger']['kind']='changed'
    if field=='counts':completions[1]['value']['protocol_call_count_after']=1
    if field=='missing_completion':events.remove(completions[-1])
    if field=='reorder':audit['calls'][0],audit['calls'][1]=audit['calls'][1],audit['calls'][0]
    with pytest.raises((ValueError,KeyError,IndexError)):
        v.verify(events,batches,audit,roots,calls,identity)


def test_final_scheduler_drain_also_in_complete_trace_and_batches():
    f=fixture();step(f,.11);response=f[3].final_drain(.2,max_events=100000)
    f[4].append({'deadline':.2,'response':response,'kind':'final_drain'})
    assert v.verify(*saved(f))['native_calls']==3


def test_source_only_private_compilation_restores_entire_scheduler_and_globals():
    original=a.original.run_continuation;before=dict(original.__globals__)
    fn=a.continuation(original)
    assert fn._source_proof['exact_full_ast_restoration']
    assert fn._source_proof['scheduler_advance_sites']==['session.advance_until_owner_notification','session.advance_to']
    assert original.__globals__==before and fn.__globals__ is not original.__globals__
    assert fn._source_proof['runtime_dispatch_ready'] is False
    assert 'root.last_boundary' in fn._source_proof['actual_boundary_assignment_ast'] or 'last_boundary' in fn._source_proof['actual_boundary_assignment_ast']


def test_original_v3_private_function_accepted_without_module_mutation():
    from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign_v3 as v3
    fn=a.continuation(v3.run_continuation)
    assert fn.__globals__['publish_root'] is v3.publish_root
    assert v3.run_continuation.__code__ is a.original.run_continuation.__code__


def test_unknown_scheduler_or_policy_cannot_enter_closed_adapter():
    with pytest.raises(ValueError,match='unknown_scheduler'):a.continuation(step)
    class Bad:
        def activate(self):self.session.advance_to(1.)
    with pytest.raises(ValueError,match='hidden_policy'):a.no_hidden_policy_advances({'A':Bad()},SimpleNamespace())
    f=fixture();f[2].native=object();f[2].accepted={}
    with pytest.raises(ValueError,match='accepted_session'):a.ActualAdvanceChain(f[0],f[1],f[2],{})


def test_collector_and_fixed_policy_source_inventory_no_hidden_advance():
    proof=a.collection_inventory();assert len(proof['collectors'])==5
    assert proof['pre_chain_resets_continuity']
    transport=object.__new__(a.original.public.LocalTransport)
    policy=object.__new__(a.request.FixedContinuationOwner)
    inventory=a.no_hidden_policy_advances({'A':policy,'B':policy},transport)
    assert len(inventory)>30 and all(row['source_sha256'] for row in inventory.values())


def test_project_outbox_retains_every_identity_and_isolates_only_required_fields():
    f=fixture();rows=f[1].rows;rows['bad']=None
    projection=a.project_outbox(rows)
    assert list(projection)==['x','bad'] and projection['bad'] is None
    projection['x']['request']['owner_id']='B';assert rows['x']['request']['owner_id']=='A'


def test_compiled_scheduler_executes_identical_background_admission_and_ID_positions():
    """Private synthetic functional A/B; no fake session is admitted by ActualAdvanceChain."""
    class TraceSession(Session):
        def advance_until_owner_notification(self,owners,cursors,horizon,**kwargs):
            self.notices=({'A':{'sequence':1,'observed_at':horizon,'change_mask':2}}
                          if horizon==.11+2*.05 else {})
            return super().advance_until_owner_notification(owners,cursors,horizon,**kwargs)
    class Policy:
        pending=None;peer_quiet_until=0.
        def __init__(self,client,owner):self.client=client;self.owner=owner;self.trace=[]
        def activate(self,trigger):
            self.client.activate(self.owner,trigger)
            self.trace.append({'owner':self.owner,'at':self.client.session.physical_time,
                'next_demand_ID_if_needed':f'demand-{len(self.client.roots)}','trigger':copy.deepcopy(trigger)})
    class TestRoot(Root):
        def observe_after_boundary(self,response):
            self.last_boundary=copy.deepcopy(response)
            self.client.activate('A',{'kind':'initial_A_continuation','root_id':self.request_id})
            self._record('continuation',{'view':{'now':self.session.physical_time}})
        def drain_and_finish_if_closed(self):
            advance=self.chain.root_drain if hasattr(self,'chain') else self.session.advance_to
            result=advance(self.session.physical_time,max_events=100000)
            self._record('mandatory_drain',result)
            closed=self.session.physical_time>=.11+2*.05
            self._record('post_drain_observation',{'view':{'now':self.session.physical_time}})
            if closed:self.state='closed_native_default_first_hop'
            return {'closed':closed}
    class PureChain(a._RecordedChain):
        def __init__(self,session,client,root,policies):
            super().__init__(session,client,root);root.chain=self
    def run(candidate):
        session=TraceSession();client=Client(session);root=TestRoot(session,client)
        policies={owner:Policy(client,owner) for owner in ('A','B')}
        function=a.continuation(a.original.run_continuation) if candidate else a.original.run_continuation
        public=SimpleNamespace(v1=SimpleNamespace(START=.11,PERIOD=.05),MAX_ACTIVATIONS=100)
        function=FunctionType(function.__code__,{**function.__globals__,
            'contract':SimpleNamespace(HORIZON=.31),'public':public,'ActualAdvanceChain':PureChain,
            'publish_root':lambda root,holder:holder.append({'state':root.state,'at':session.physical_time})})
        client.refresh_owner=lambda *args,**kwargs:None
        records=[];batches=[];returned=function(session,client,policies,root,records,batches)
        return session,client,root,policies,records,batches,returned
    old,new=run(False),run(True)
    assert old[1].roots==new[1].roots
    assert old[4:]==new[4:]
    assert [p.trace for p in old[3].values()]==[p.trace for p in new[3].values()]
    assert old[2].last_boundary==new[2].last_boundary
    assert sum(e['stage']=='continuation' for e in old[2].events)==3
    assert sum(e['stage']=='continuation' for e in new[2].events)==2
    report=v.verify(new[2].events,new[5],new[2].chain.audit_copy(),new[1].roots,new[1].calls,new[2].request_id)
    assert report['skips']==1


def test_actual_saved_boundary_and_drain_shapes_are_supported_without_native_authority():
    import gzip
    import hashlib
    path=a.original.OUT/'initial_owner_route_campaign_v3_prepare_001/raw/normal/block0_load0/fixed_default.json.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='84633d9fa8c503c6b92a2e88f814e914b083bac72850c4ef91a86ccb5da247dd'
    with gzip.open(path,'rt',encoding='utf8') as stream:raw=json.load(stream)
    evidence=raw['root_records'][0]['value']['evidence']
    actual_drains=[e for e in evidence['events'] if e['stage']=='mandatory_drain']
    batches=raw['native_batches']
    assert len(actual_drains)==122 and len(batches)>122
    f=fixture();session,client,root,chain,_=f
    first=batches[0]
    class SavedSession(Session):
        def advance_until_owner_notification(self,*args,**kwargs):
            self.physical_time=first['response']['physical_time'];return copy.deepcopy(first['response'])
        def advance_to(self,*args,**kwargs):
            self.physical_time=actual_drains[0]['at'];return copy.deepcopy(actual_drains[0]['value'])
    session=SavedSession();client=Client(session);root=Root(session,client)
    chain=a._RecordedChain(session,client,root)
    response=chain.notification_advance(['A','B'],{'A':0,'B':0},first['deadline'],max_events=100000)
    assert not chain.decide(response)  # The old collection jump is never retroactively continuous.
    assert chain.root_drain(session.physical_time,max_events=100000)==actual_drains[0]['value']
    assert not root.events[-1]['value']['decision']['actual_native_authority']
