"""Fixed synthetic shape only; no actual history or native authority.

The seed public_fixture is an exact source copy from the frozen37 pure gate.
"""
from copy import deepcopy
from . import bridge_replay_copy_scopes as c


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


JOBS, REVISIONS = 64, 16
FAMILIES = ('discard_refresh', 'temporary_own_capture')


def fixed_fixture():
    """Reconstruct all64 jobs/all16 revisions each time, never reuse history."""
    view,box,peer,plan=public_fixture()
    seed=box.pop('snap')
    own=seed['client_view']['last_delivered_ack']['planning_snapshot_v2']
    for env,prefix in ((own,'own'),(peer,'peer')):
        local=env['capture']['local_capture'];template=local['jobs'][0]
        local['jobs']=[{**deepcopy(template),'business_bag_id':prefix+':'+format(i,'03d')} for i in range(JOBS)]
        local['coverage']['business_bag_ids']=[j['business_bag_id'] for j in local['jobs']]
        env['payload_sha256']=c.base.capture_digest_v2(env['capture'])
    group=view['control_projection']['waiting_groups'][0]
    head=group['jobs'][0]
    group['jobs']=[{**deepcopy(head),'business_bag_id':'own:'+format(i,'03d'),
        'fifo_index':i,'global_fifo_index':i} for i in range(2)]
    group['count']=JOBS;view['control_projection']['exact_waiting_count']=JOBS
    for index in range(REVISIONS):
        rid='snapshot:'+format(index,'02d');row=deepcopy(seed);row['payload']['request_id']=rid
        ack=row['client_view']['last_delivered_ack'];env=ack['planning_snapshot_v2'];local=env['capture']['local_capture']
        local['publication_sequence']=index+1;local['message_id']='mA:'+format(index,'02d')
        ack['result_id']=local['message_id'];ack['sequence']=index+1
        env['payload_sha256']=c.base.capture_digest_v2(env['capture']);box[rid]=row
    return view,box,peer,plan


class QuerySession:
    """Synthetic return-by-value endpoint, no native/projection construction."""
    def __init__(self, responses):
        self.physical_time=10.;self.responses=responses;self.calls=[]

    def protocol_command(self, owner, rid):
        self.calls.append(['protocol_command',owner,rid])
        return deepcopy(self.responses[rid])

    def protocol_request(self, owner, rid):
        self.calls.append(['protocol_request',owner,rid])
        return deepcopy(self.responses[rid])

    def submit_protocol_command(self, payload):
        self.calls.append(['submit_protocol_command',deepcopy(payload)])
        return {'status':'accepted'}

    def submit_protocol_transfer(self, payload):
        self.calls.append(['submit_protocol_transfer',deepcopy(payload)])
        return {'status':'accepted'}


def make_case(family):
    if family not in FAMILIES:raise ValueError('copy_fixture:family')
    view,box,peer,plan=fixed_fixture()
    case={'family':family,'view':view,'box':box,'peer':peer,'plan':plan,
          'nodes':{n['node']:n for n in view['node_contracts']}}
    if family=='discard_refresh':
        responses={rid:deepcopy(row['client_view']) for rid,row in box.items() if row['kind']=='planning_snapshot_v2'}
        for rid in responses:
            box[rid]['terminal']=False;box[rid]['next_retry']=20.;box[rid].pop('client_view')
        session=QuerySession(responses)
        client=c.protocol.ProtocolClient(session,retry_period=60.,state={
            'schema':'g31.protocol_client_state.v1','retry_period':60.,'rejection_cooldown':.2,
            'forecast_validity':120.,'sequences':{},'outbox':box})
        case.update(session=session,client=client)
    return case


def invoke(case, arm):
    if arm not in ('A','B'):raise ValueError('copy_fixture:arm')
    if case['family']=='discard_refresh':
        if arm=='A':case['client'].refresh(owner_id='A')
        else:c._refresh_discarded(case['client'],owner_id='A')
        return None
    own=(c.reuse.latest_own_capture if arm=='A' else c._BORROWED_OWN)(case['box'],'A','B',10.,case['nodes'])
    barrier=c.policy.received_barrier(case['box'],'A',own,case['peer'],case['plan']['parking'],'T',10.)
    choice=c.policy.choose_action(case['view'],case['peer'],own,'T',[])
    # Diagnostic verifier inspects the temporary own reference before disposing
    # of this invocation. The measured policy's durable outputs are only these
    # original fresh barrier/choice values, never this diagnostic tuple.
    return own,barrier,choice
