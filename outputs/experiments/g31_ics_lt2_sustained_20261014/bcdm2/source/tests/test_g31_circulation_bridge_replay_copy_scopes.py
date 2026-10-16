"""Synthetic functional gate, never native delivery or replay-performance evidence."""
import ast
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_replay_copy_scopes as c


def exact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def mutable_ids(value):
    if type(value) is dict:
        return {id(value)}.union(*(mutable_ids(v) for v in value.values()))
    if type(value) in (list, tuple):
        return ({id(value)} if type(value) is list else set()).union(*(mutable_ids(v) for v in value))
    return set()


def public_fixture():
    """Fresh complete typed bodies, fabricated for pure guards and labeled so."""
    owners = {0:'A',1:'A',2:'B',3:'B',4:'B',5:'A',6:'B'}
    roles = {0:0,1:1,2:1,3:0,4:7,5:0,6:0}
    nodes = [dict(node=n, resource_owner=o, zone=o, capacity=3, allow_receive=True,
        allow_export=True, export_min_stock=0, actual_available=int(n==0),
        occupancy=int(n==0), unrepresented_occupancy=0) for n,o in owners.items()]
    tray = dict(tray_id='T',node=0,mode='empty',business_bag_id='',edge_to=-1,
        edge_from=-1,reception_node=-1,available_at=8.,generation=2,traversal_id=4,
        ready_kind='stationary',service_ready_at=8.,load_complete_at=-1.,
        service_ready_known=True,committed_prefix=[0])
    def job(identity, origin):
        return dict(business_bag_id=identity,origin=origin,destination=5,arrival=0.,deadline=100.,
            storage_node=4,storage_release_at=0.,storage_min_dwell=0.,load_seconds=1.,unload_seconds=1.,
            hold_seconds=1.,protected_service=True,allow_suffix_reroute=False,status='waiting_for_tray',
            loaded_at=-1.,storage_entered_at=-1.,storage_released_at=-1.)
    parking = [dict(request_id='pa',owner='A',tray_id='T',source=1,destination=3),
               dict(request_id='pb',owner='B',tray_id='P',source=2,destination=5)]
    plan = dict(owners=['A','B'],parking=parking,token_tray_id='T',token_owner='A')
    def action(rid, owner):
        return dict(request_id=rid,kind='transfer',source_owner=owner,
            last_delivered_ack=dict(sequence=1,delivered_at=6.,status='received'))
    completion = dict(receipt_id='completion1',source_local_sequence=1,source_owner='A',
        event='UNLOAD_COMPLETE',status='completed',business_bag_id='done',destination=0,tray_id='T',completed_at=7.)
    def envelope(owner):
        peer = 'B' if owner=='A' else 'A'
        local_nodes = [deepcopy(n) for n in nodes if n['resource_owner']==owner]
        trays = [deepcopy(tray)] if owner=='A' else []
        jobs = [job('own',1)] if owner=='A' else [job('peer',2)]
        local = dict(schema='g31.planning_capture.v1',message_id='m'+owner,source_owner=owner,
            target_owner=peer,publication_sequence=1,captured_at=9.,valid_until=100.,static_contract_sha256='0'*64,
            semantics={**{k:'synthetic' for k in ('queue_discipline','resource_semantics','event_semantics',
                'scorer_mode','merge_grant_rule','merge_grant_timing_mode')},'minimum_service_seconds':.001},
            jobs=jobs,trays=trays,nodes=local_nodes,known_faults=[],coverage=dict(scope='synthetic_complete_local',
                complete_for_declared_local_scope=True,local_node_ids=[n['node'] for n in local_nodes],
                tray_ids=[t['tray_id'] for t in trays],business_bag_ids=[j['business_bag_id'] for j in jobs],
                unrepresented_occupancy=0,future_arrivals_included=False))
        actions = [action('pa','A'),action('a1','A')] if owner=='A' else [action('pb','B')]
        receipts = [deepcopy(completion)] if owner=='A' else []
        ext = dict(schema='g31.planning_capture_extension.v2',source_owner=owner,captured_at=9.,
            terminal_receipts=receipts,completion_coverage=dict(
                scope='all_source_owned_destination_unload_completions_through_capture',complete_for_declared_scope=True,
                through=9.,source_owned_destination_nodes=local['coverage']['local_node_ids'][:],future_events_included=False,
                completed_business_bag_ids=[r['business_bag_id'] for r in receipts]),submitted_physical_actions=actions,
            action_coverage=dict(scope='all_source_submitted_physical_operations_last_delivered_ack',
                through=9.,complete_for_declared_scope=True,includes_unsubmitted_python_plans=False,
                uses_hidden_execution_truth=False,submitted_request_ids=[a['request_id'] for a in actions],unresolved_request_ids=[]))
        body = dict(schema='g31.planning_capture.v2',local_capture=local,extension=ext)
        return dict(schema='g31.planning_snapshot.v2',kind='planning_snapshot_v2',capture=body,
            digest_format='g31.planning_capture_digest.v2',payload_sha256=c.base.capture_digest_v2(body),
            delivered_at=9.2,status='conditional')
    own,peer = envelope('A'),envelope('B')
    ack = dict(status='delivered',sequence=1,executed_at=9.,completed_at=9.2,delivered_at=9.5,
        result_id='mA',planning_snapshot_v2=own)
    box = {p['request_id']:dict(kind='transfer',payload={k:v for k,v in p.items() if k!='owner'},
        terminal=True,submission_reply={'status':'accepted'},client_view={'last_delivered_ack':action(p['request_id'],'A')['last_delivered_ack']})
        for p in parking if p['owner']=='A'}
    box['pa']['payload']['owner_id']='A'
    box['a1']=dict(kind='transfer',payload=dict(request_id='a1',owner_id='A',tray_id='T',source=1,destination=0),
        terminal=True,submission_reply={'status':'accepted'},client_view={'last_delivered_ack':action('a1','A')['last_delivered_ack']})
    box['snap']=dict(kind='planning_snapshot_v2',payload=dict(request_id='snap',owner_id='A',target_owner='B'),
        terminal=True,submission_reply={'status':'accepted'},client_view={'last_delivered_ack':ack})
    edges=[(0,2),(2,4),(0,3),(3,1),(1,4),(4,5),(0,6),(6,1)]
    head={k:own['capture']['local_capture']['jobs'][0][k] for k in ('business_bag_id','origin','arrival','deadline','status')}
    head.update(fifo_index=0,global_fifo_index=0,demand_observed_at=10.)
    view=dict(owner_id='A',now=10.,trays=[deepcopy(tray)],jobs=[],node_contracts=nodes,
        node_records=[[n,roles[n],.1] for n in owners],edge_records=[[a,b,1.,1.] for a,b in edges],
        edge_contracts=[dict(**{'from':a,'to':b},capacity=1) for a,b in edges],
        control_projection=dict(schema='g31.analytic_control_projection.v1',waiting_selection='fifo_prefix_cover_upper_plus_finite_tray_bound',
            waiting_groups=[dict(origin=1,count=1,head_limit=2,covered_upper_bound=1,demand_observed_at=10.,jobs=[head])],
            exact_waiting_count=1,known_origin_nodes=[1],candidate_limit=1))
    return view,box,peer,plan


class Session:
    def __init__(self, responses=None, view=None, peer=None):
        self.physical_time=10.;self.responses=responses or {};self.calls=[];self.view=view;self.peer=peer
    def protocol_request(self, owner, rid):
        self.calls.append(('protocol_request',owner,rid));value=self.responses[rid]
        if isinstance(value,BaseException): raise value
        return value
    def protocol_command(self, owner, rid):
        self.calls.append(('protocol_command',owner,rid));value=self.responses[rid]
        if isinstance(value,BaseException): raise value
        return value
    def submit_protocol_transfer(self, payload):
        self.calls.append(('submit_protocol_transfer',deepcopy(payload)));return {'status':'accepted'}
    def submit_protocol_command(self, payload):
        self.calls.append(('submit_protocol_command',deepcopy(payload)));return {'status':'accepted'}
    def observe_protocol_control_policy_recent(self, owner, validity):
        self.calls.append(('view',owner,validity));return deepcopy(self.view)
    def protocol_planning_snapshots_v2(self, owner):
        self.calls.append(('received',owner));return [deepcopy(self.peer)]


def client(session, box):
    return c.protocol.ProtocolClient(session,state=dict(schema='g31.protocol_client_state.v1',retry_period=60.,
        rejection_cooldown=1.,forecast_validity=120.,sequences={},outbox=box),retry_period=60.,rejection_cooldown=1.)


def call_values(calls):
    return [{k:v for k,v in row.items() if k!='submit_compute_ms'} for row in calls]


def test_source_inverse_ast_mro_original_global_functions_unchanged():
    proof=c.source_proof()
    assert len(proof['expression_proofs'])==4 and all(p['inverse_AST_exact'] for p in proof['expression_proofs'])
    assert proof['retained_client_view_deepcopy'] and proof['possession_gate_original_copies_retained']
    assert c.run_policy.__code__ is c.policy.run_policy.__code__
    assert c._BORROWED_OWN is not c.possession.PossessionGate.consume.__globals__['reuse'].latest_own_capture


@pytest.mark.parametrize('status',['pending','granted','received','updated','rejected','failed','expired'])
@pytest.mark.parametrize('indexed',[False,True])
def test_discard_refresh_exact_state_request_order_retry_and_index(status,indexed):
    box={}
    for rid,kind,owner in [('a','transfer','A'),('b','route','A'),('foreign','route','B')]:
        box[rid]=dict(kind=kind,payload=dict(request_id=rid,owner_id=owner,nested=[1,{'x':-0.0}]),terminal=False,next_retry=10.)
    response=dict(last_delivered_ack=dict(status=status,delivered_at=9.),nested=[1,{'x':-0.0}])
    a,b=Session({rid:deepcopy(response) for rid in box}),Session({rid:deepcopy(response) for rid in box})
    old,new=client(a,box),client(b,box)
    old._use_active_request_index=new._use_active_request_index=indexed
    returned=old.refresh(owner_id='A');assert c._refresh_discarded(new,owner_id='A') is None
    assert exact(old.state)==exact(new.state) and a.calls==b.calls and call_values(old.calls)==call_values(new.calls)
    assert old._active_requests==new._active_requests and old._owner_active_requests==new._owner_active_requests
    assert len(returned)==2 and 'client_view' not in new.state['outbox']['foreign']
    assert not mutable_ids(new.state)&mutable_ids(b.responses)
    assert not mutable_ids(returned)&mutable_ids(old.state)


def test_refresh_exception_retains_identical_completed_prefix():
    box={rid:dict(kind='transfer',payload=dict(request_id=rid,owner_id='A'),terminal=False,next_retry=20.) for rid in ('a','b')}
    sessions=[Session({'a':{'last_delivered_ack':{'status':'received'}},'b':ValueError('queryfailed')}) for _ in range(2)]
    values=[client(s,box) for s in sessions]
    for fn,v in zip((lambda v:v.refresh(owner_id='A'),lambda v:c._refresh_discarded(v,owner_id='A')),values):
        with pytest.raises(ValueError,match='queryfailed'):fn(v)
    assert exact(values[0].state)==exact(values[1].state) and sessions[0].calls==sessions[1].calls


def test_nonexact_client_rejected_without_query():
    with pytest.raises(ValueError,match='nonexact_client'):c._refresh_discarded(SimpleNamespace(),owner_id='A')


def test_cooldown_retirement_equivalent():
    box={'a':dict(kind='route',payload=dict(request_id='a',owner_id='A'),terminal=True,cooldown_until=10.)}
    a,b=client(Session(),box),client(Session(),box)
    a.refresh(owner_id='A');c._refresh_discarded(b,owner_id='A')
    assert exact(a.state)==exact(b.state) and not b._active_requests and b.state['outbox']['a']['cooldown_consumed']


@pytest.mark.parametrize('defect',['none','owner','digest','sequence_bool','duplicate_sequence','expired','future_ack','coverage'])
def test_borrow_guards_exactly_match_original_and_run_on_every_call(defect):
    view,box,peer,plan=public_fixture();nodes={n['node']:n for n in view['node_contracts']}
    row=box['snap'];ack=row['client_view']['last_delivered_ack'];env=ack['planning_snapshot_v2'];local=env['capture']['local_capture']
    if defect=='owner':row['payload']['owner_id']='B'
    elif defect=='digest':env['payload_sha256']='0'*64
    elif defect=='sequence_bool':local['publication_sequence']=True
    elif defect=='duplicate_sequence':
        box['snap2']=deepcopy(row);box['snap2']['payload']['request_id']='snap2'
    elif defect=='expired':local['valid_until']=10.;env['payload_sha256']=c.base.capture_digest_v2(env['capture'])
    elif defect=='future_ack':ack['delivered_at']=11.
    elif defect=='coverage':
        local['coverage']['local_node_ids'].pop();env['payload_sha256']=c.base.capture_digest_v2(env['capture'])
    before=exact((view,box,peer,plan));results=[]
    for fn in (c.reuse.latest_own_capture,c._BORROWED_OWN):
        try:results.append(('return',exact(fn(box,'A','B',10.,nodes))))
        except Exception as error:results.append(('error',type(error).__name__,str(error)))
    assert results[0]==results[1] and before==exact((view,box,peer,plan))
    if defect=='none':
        borrowed=c._BORROWED_OWN(box,'A','B',10.,nodes)
        assert borrowed['ack'] is ack and borrowed['envelope'] is env
        env['payload_sha256']='broken'
        with pytest.raises(ValueError,match='message_digest'):c._BORROWED_OWN(box,'A','B',10.,nodes)


def test_newest_expired_does_not_resurrect_older_capture():
    view,box,peer,plan=public_fixture();nodes={n['node']:n for n in view['node_contracts']}
    box['new']=deepcopy(box['snap']);box['new']['payload']['request_id']='new'
    ack=box['new']['client_view']['last_delivered_ack'];env=ack['planning_snapshot_v2'];local=env['capture']['local_capture']
    local.update(publication_sequence=2,message_id='new',valid_until=10.);ack['result_id']='new'
    env['payload_sha256']=c.base.capture_digest_v2(env['capture'])
    for fn in (c.reuse.latest_own_capture,c._BORROWED_OWN):assert fn(box,'A','B',10.,nodes) is None


@pytest.mark.parametrize('peer_jobs',[True,False])
def test_readonly_consumers_and_durable_possession_do_not_borrow(peer_jobs):
    view,box,peer,plan=public_fixture();nodes={n['node']:n for n in view['node_contracts']}
    if not peer_jobs:
        peer['capture']['local_capture']['jobs']=[];peer['capture']['local_capture']['coverage']['business_bag_ids']=[]
        peer['payload_sha256']=c.base.capture_digest_v2(peer['capture'])
    before=exact((view,box,peer,plan));own=c._BORROWED_OWN(box,'A','B',10.,nodes)
    barrier=c.policy.received_barrier(box,'A',own,peer,plan['parking'],'T',10.)
    choice=c.policy.choose_action(view,peer,own,'T',[])
    gate=c.possession.PossessionGate('A',plan,['pa','pb']);permit=gate.consume(view,box,[peer])
    assert barrier and choice and permit
    assert choice['kind']==('direct_supply' if peer_jobs else 'bridge_empty')
    assert before==exact((view,box,peer,plan))
    assert not mutable_ids((barrier,choice,permit))&mutable_ids((view,box,peer,plan))
    saved=exact(permit);box['snap']['client_view']['last_delivered_ack']['planning_snapshot_v2']['capture']['local_capture']['jobs'].clear()
    assert exact(permit)==saved


def owner(cls,view,box,peer,plan,*,halt=False):
    session=Session(view=view,peer=peer);value=cls.__new__(cls)
    value.session=session;value.owner='A';value.peer='B';value.plan=deepcopy(plan);value.client=client(session,box)
    value.possession=c.possession.PossessionGate('A',plan,['pa','pb'])
    value.quiet=True;value.failure=None;value.index=0;value.rows=[];value.completed=[];value.pending=None;value.supply=None
    value.operations=[];value.decisions=[];value.consumed_completions=[];value.publications=1;value.next_publication=20.
    value.relayed=['a1'];value.replied=[];value.bridge_publications=[];value.last_barrier=None;value.cap_observed=False
    value.cap_relay=None;value.halt_new_actions=halt
    return value


@pytest.mark.parametrize('mode',['direct','bridge','notempty','halt','cap'])
def test_actual_bridge_private_mro_and_full_activation_state_equivalence(mode):
    view,box,peer,plan=public_fixture()
    if mode=='bridge':
        peer['capture']['local_capture']['jobs']=[];peer['capture']['local_capture']['coverage']['business_bag_ids']=[]
        peer['payload_sha256']=c.base.capture_digest_v2(peer['capture'])
    if mode=='notempty':view['trays'][0]['mode']='loaded'
    old,new=[owner(cls,*deepcopy((view,box,peer,plan)),halt=mode=='halt') for cls in (c.policy.BridgeOwner,c.CopyScopedBridgeOwner)]
    if mode=='cap':old.cap_observed=new.cap_observed=True
    old.activate();new.activate()
    assert exact(old.controller_checkpoint())==exact(new.controller_checkpoint())
    assert call_values(old.client.calls)==call_values(new.client.calls) and old.session.calls==new.session.calls
    assert exact(old.last_barrier)==exact(new.last_barrier) and exact(old.decisions)==exact(new.decisions)
    assert not mutable_ids((new.decisions,new.operations,new.last_barrier))&mutable_ids(new.client.state)


def test_inverse_transform_rejects_unmatched_or_repeated_expression():
    with pytest.raises(ValueError,match='expression_count'):
        c.expression_variant(c._REFRESH,'unknown()','None',c._REFRESH.__globals__)


def test_source_proof_rejects_private_binding_drift(monkeypatch):
    monkeypatch.setattr(c._PRIVATE_REUSE,'latest_own_capture',c._OWN)
    with pytest.raises(ValueError,match='escaping_possession'):c.source_proof()


def test_original_generic_refresh_still_returns_full_independent_views():
    response={'last_delivered_ack':{'status':'received'},'nested':[1,{'x':2}]}
    value=client(Session({'a':response}),{'a':dict(kind='transfer',payload=dict(request_id='a',owner_id='A'),terminal=False,next_retry=20.)})
    result=value.refresh(owner_id='A');result[0]['view']['nested'][1]['x']=99
    assert response['nested'][1]['x']==2 and value.state['outbox']['a']['client_view']['nested'][1]['x']==2
