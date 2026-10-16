"""Pure policy guards; synthetic fixtures do not claim native delivery."""
from copy import deepcopy
import hashlib
import gzip
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import cooperative_bridge_policy as p
from test_g31_circulation_current_possession_permit import fixture as actual_fixture


def fixture():
    owners = {0:'A',1:'A',2:'B',3:'B',4:'B',5:'A',6:'B'}
    roles = {0:0,1:1,2:1,3:0,4:7,5:0,6:0}
    nodes = [dict(node=n,resource_owner=o,zone=o,capacity=3,allow_receive=True,
                  allow_export=True,export_min_stock=0,actual_available=int(n==0),occupancy=int(n==0))
             for n,o in owners.items()]
    edges = [(0,2),(2,4),(0,3),(3,1),(1,4),(4,5),(0,6),(6,1)]
    tray = dict(tray_id='T',node=0,mode='empty',business_bag_id='',edge_to=-1,
                edge_from=-1,reception_node=-1,available_at=8.,generation=2,traversal_id=4)
    def job(identity,origin,arrival=0.,destination=5):
        return dict(business_bag_id=identity,origin=origin,arrival=arrival,destination=destination,
                    storage_node=4,status='waiting_for_tray',deadline=100.)
    own_job=job('own',1)
    head={k:own_job[k] for k in ('business_bag_id','origin','arrival','deadline','status')}
    head.update(fifo_index=0,global_fifo_index=0,demand_observed_at=10.)
    view = dict(owner_id='A',now=10.,trays=[tray],jobs=[],node_contracts=nodes,
                node_records=[[n,roles[n],.1] for n in owners],
                edge_records=[[a,b,1.,1.] for a,b in edges],
                edge_contracts=[{'from':a,'to':b,'capacity':1} for a,b in edges],
                control_projection={'schema':'g31.analytic_control_projection.v1',
                    'waiting_selection':'fifo_prefix_cover_upper_plus_finite_tray_bound',
                    'waiting_groups':[{'origin':1,'count':1,'head_limit':2,'covered_upper_bound':1,
                        'demand_observed_at':10.,'jobs':[head]}], 'exact_waiting_count':1,
                    'known_origin_nodes':[1],'candidate_limit':1})
    receipt = dict(receipt_id='completion1',tray_id='T',source_owner='A',event='UNLOAD_COMPLETE',
                   status='completed',source_local_sequence=1,completed_at=7.,destination=0,business_bag_id='done')
    own = {'envelope':{'schema':'g31.planning_snapshot.v2','kind':'planning_snapshot_v2',
            'capture':{'schema':'g31.planning_capture.v2',
            'local_capture':{'schema':'g31.planning_capture.v1','source_owner':'A','captured_at':9.,
                'jobs':[own_job],'coverage':{'complete_for_declared_local_scope':True,'future_arrivals_included':False}},
            'extension':{'terminal_receipts':[receipt]}}}}
    peer = {'capture':{'local_capture':{'source_owner':'B','captured_at':9.,'message_id':'m',
            'nodes':[deepcopy(n) for n in nodes if n['resource_owner']=='B'],'jobs':[job('peer',2)]}}}
    return view,peer,own


def test_direct_peer_fifo_precedes_possible_own_bridge_and_is_read_only():
    args=fixture(); before=deepcopy(args)
    choice=p.choose_action(*args,'T',[])
    assert choice['kind']=='direct_supply' and choice['destination']==2
    assert choice['selected_current_job']['business_bag_id']=='peer'
    assert choice['positive_mandatory_paths']==[[2,4],[4,5]]
    assert choice['bridge_followup_pre_authorized'] is False and args==before


def test_only_current_head_per_source_never_skips_unreachable_predecessor():
    view,peer,own=fixture();first=peer['capture']['local_capture']['jobs'][0]
    first['destination']=0
    successor={**deepcopy(first),'business_bag_id':'peer_after','arrival':1.,'destination':5}
    peer['capture']['local_capture']['jobs'].append(successor)
    choice=p.choose_action(view,peer,own,'T',[])
    assert choice['kind']=='bridge_empty' and choice['selected_current_job']['business_bag_id']=='own'
    assert [j['business_bag_id'] for j in p.fifo_heads(peer['capture']['local_capture']['jobs'],'B',
            {n['node']:n for n in view['node_contracts']},9.)]==['peer']


def test_bridge_uses_least_actual_public_nonloader_nonstorage_node():
    view,peer,own=fixture();peer['capture']['local_capture']['jobs']=[]
    value=p.choose_action(view,peer,own,'T',[])
    assert value['kind']=='bridge_empty' and value['destination']==3
    assert value['positive_empty_path']==[0,3] and value['possible_second_empty_path']==[3,1]
    assert value['completion_permit']['receipt_id']=='completion1'
    assert not value['bridge_followup_pre_authorized']


@pytest.mark.parametrize('defect',['same_zone','full','not_receive','not_export','min_stock','loader','storage','zero_edge'])
def test_bridge_endpoint_contract_and_path_are_necessary(defect):
    view,peer,own=fixture();peer['capture']['local_capture']['jobs']=[]
    nodes={n['node']:n for n in view['node_contracts']};facts={n['node']:n for n in peer['capture']['local_capture']['nodes']}
    for node in (3,6):
        if defect=='same_zone':nodes[node]['zone']='A'
        elif defect=='full':facts[node]['occupancy']=nodes[node]['capacity']
        elif defect=='not_receive':nodes[node]['allow_receive']=False
        elif defect=='not_export':nodes[node]['allow_export']=False
        elif defect=='min_stock':nodes[node]['export_min_stock']=1
        elif defect in ('loader','storage'):
            next(r for r in view['node_records'] if r[0]==node)[1]=1 if defect=='loader' else 7
        else:next(e for e in view['edge_contracts'] if (e['from'],e['to'])==(0,node))['capacity']=0
    assert p.choose_action(view,peer,own,'T',[]) is None


@pytest.mark.parametrize('defect',['source_min','source_permission','own_full','own_unreachable','no_own_head'])
def test_no_unsupported_export_or_own_head_promise(defect):
    view,peer,own=fixture();peer['capture']['local_capture']['jobs']=[]
    nodes={n['node']:n for n in view['node_contracts']}
    if defect=='source_min':nodes[0]['export_min_stock']=1
    elif defect=='source_permission':nodes[0]['allow_export']=False
    elif defect=='own_full':nodes[1]['occupancy']=nodes[1]['capacity']
    elif defect=='own_unreachable':own['envelope']['capture']['local_capture']['jobs'][0]['destination']=0
    else:
        own['envelope']['capture']['local_capture']['jobs']=[]
        view['control_projection']['waiting_groups']=[];view['control_projection']['exact_waiting_count']=0
    assert p.choose_action(view,peer,own,'T',[]) is None


def test_empty_bridge_arrival_cannot_make_another_bridge_without_new_completion():
    view,peer,own=fixture();peer['capture']['local_capture']['jobs']=[]
    assert p.choose_action(view,peer,own,'T',['completion1']) is None
    own['envelope']['capture']['extension']['terminal_receipts']=[]
    assert p.choose_action(view,peer,own,'T',[]) is None
    # Direct supply depends on current possession, not an invented receipt.
    peer['capture']['local_capture']['jobs']=[dict(business_bag_id='peer',origin=2,arrival=0.,
        destination=5,storage_node=4,status='waiting_for_tray')]
    assert p.choose_action(view,peer,own,'T',[])['kind']=='direct_supply'


@pytest.mark.parametrize('defect',['future_head','duplicate_job','missing_projection','missing_stock','bool_occupancy','bad_receipt'])
def test_missing_malformed_authority_is_not_empty_queue(defect):
    view,peer,own=fixture()
    if defect=='future_head':peer['capture']['local_capture']['jobs'][0]['arrival']=11.
    elif defect=='duplicate_job':peer['capture']['local_capture']['jobs']*=2
    elif defect=='missing_projection':
        peer['capture']['local_capture']['jobs']=[];del view['control_projection']
    elif defect=='missing_stock':del view['node_contracts'][0]['actual_available']
    elif defect=='bool_occupancy':peer['capture']['local_capture']['nodes'][0]['occupancy']=True
    else:
        peer['capture']['local_capture']['jobs']=[]
        own['envelope']['capture']['extension']['terminal_receipts'][0]['source_owner']='B'
    with pytest.raises((ValueError,KeyError)):
        p.choose_action(view,peer,own,'T',[])


class Client:
    def __init__(self,box):
        self.state={'outbox':deepcopy(box)};self.calls=[];self.refreshes=0
    def refresh(self,**kwargs):self.refreshes+=1
    def submit(self,owner,kind,payload,*,request_id):
        assert request_id not in self.state['outbox']
        self.calls.append(dict(owner=owner,kind=kind,payload=deepcopy(payload),request_id=request_id,retry=False))
        self.state['outbox'][request_id]={'kind':kind,'terminal':False,
            'payload':{**deepcopy(payload),'owner_id':owner,'kind':kind,'request_id':request_id},
            'client_view':{},'submission_reply':{'status':'accepted'}}


def actual_owner():
    """Actual saved compact endpoint, source self-copy and delivered peer.

    Calling the new candidate on these saved facts is a pure counterfactual,
    never a new runtime/delivery or physical-execution claim.
    """
    gate,proof_view,box,peer=actual_fixture()
    path=p.base.OUT/'original_low_wip_third_prepare_001/api/013737.json.gz'
    encoded=path.read_bytes()
    assert hashlib.sha256(encoded).hexdigest()=='d647ab64fef84b381cb3ea6241e49747924293970514de9fd126456c40d313b8'
    record=json.loads(gzip.decompress(encoded));assert record['endpoint']=='observe_protocol_control_policy_recent'
    view=record['result'];assert view['jobs']==[] and view['owner_id']==gate.owner and view['now']==proof_view['now']
    value=p.BridgeOwner.__new__(p.BridgeOwner)
    value.owner=gate.owner;value.peer=gate.peer;value.plan=deepcopy(gate.plan);value.possession=gate
    value.quiet=True;value.failure=None;value.index=0;value.rows=[];value.completed=[];value.pending=None
    value.supply=None;value.operations=[];value.decisions=[];value.consumed_completions=[]
    value.client=Client(box);value.publications=1;value.next_publication=view['now']+10
    value.relayed=[rid for rid,row in box.items() if row['kind']=='transfer' and rid not in gate.parking]
    value.replied=[];value.bridge_publications=[];value.last_barrier=None;value.cap_observed=False
    value.cap_relay=None;value.halt_new_actions=False;value.reads=[]
    def observe(owner,validity):
        assert owner==value.owner and validity==p.base.VALIDITY
        value.reads.append(('own_view',owner));return deepcopy(view)
    def received(owner):
        assert owner==value.owner
        value.reads.append(('own_received',owner));return [deepcopy(peer)]
    value.session=SimpleNamespace(physical_time=view['now'],observe_protocol_control_policy_recent=observe,
        protocol_planning_snapshots_v2=received)
    return value,view,peer


def test_actual_compact_empty_jobs_still_has_joinable_current_own_heads():
    value,view,peer=actual_owner();nodes={n['node']:n for n in view['node_contracts']}
    own=p.reuse.latest_own_capture(value.client.state['outbox'],value.owner,value.peer,view['now'],nodes)
    heads=p.current_own_fifo_heads(view,own,nodes)
    assert view['jobs']==[] and len(heads)==7
    assert heads[0]['business_bag_id']=='projected:1x:3'
    # Hypothetical negative peer queue after real same-owner compact facts:
    # this checks bridge construction, not actual peer emptiness/delivery.
    peer['capture']['local_capture']['jobs']=[]
    selected=p.choose_action(view,peer,own,value.plan['token_tray_id'],[])
    assert selected['kind']=='bridge_empty'
    assert selected['selected_current_job'] in heads and not selected['bridge_followup_pre_authorized']


@pytest.mark.parametrize('defect',['schema','capture_source','capture_future','missing_head','changed_head',
    'changed_deadline','stale_current','omitted_contract','omitted_group','duplicate_group','missing_projection'])
def test_actual_compact_join_rejects_missing_or_changed_current_authority(defect):
    value,view,_=actual_owner();nodes={n['node']:n for n in view['node_contracts']}
    own=p.reuse.latest_own_capture(value.client.state['outbox'],value.owner,value.peer,view['now'],nodes)
    projection=view['control_projection'];group=projection['waiting_groups'][0];local=own['envelope']['capture']['local_capture']
    if defect=='schema':projection['schema']='unknown'
    elif defect=='capture_source':local['source_owner']=value.peer
    elif defect=='capture_future':local['captured_at']=view['now']+1.
    elif defect=='missing_head':group['jobs']=[]
    elif defect=='changed_head':group['jobs'][0]['business_bag_id']='different-current-id'
    elif defect=='changed_deadline':group['jobs'][0]['deadline']+=1.
    elif defect=='stale_current':group['demand_observed_at']-=1.
    elif defect=='omitted_contract':local['jobs']=[j for j in local['jobs'] if j['business_bag_id']!=group['jobs'][0]['business_bag_id']]
    elif defect=='omitted_group':projection['waiting_groups'].pop(0)
    elif defect=='duplicate_group':projection['waiting_groups'].append(deepcopy(group))
    else:del view['control_projection']
    with pytest.raises((ValueError,KeyError)):
        p.current_own_fifo_heads(view,own,nodes)


def test_actual_shaped_facts_produce_exact_token_request_after_watermark_consumed():
    value,view,peer=actual_owner();old=value.possession.consumed;original=value.client.submit
    def checked(owner,kind,payload,*,request_id):
        if kind=='transfer':
            assert old < value.possession.consumed
            assert value.consumed_completions
        return original(owner,kind,payload,request_id=request_id)
    value.client.submit=checked;value.activate()
    transfers=[c for c in value.client.calls if c['kind']=='transfer']
    assert len(transfers)==1 and len(value.operations)==1
    call=transfers[0];assert call['payload']['tray_id']==value.plan['token_tray_id']
    assert call['payload']['source']==view['trays'][0]['node']
    assert set(call['payload'])=={'tray_id','source','destination','message_delay','earliest_departure','expiry'}
    assert value.operations[0]['choice']['selected_current_job']['business_bag_id']=='projected:1x:8'
    # Same facts after submission cannot authorize another immutable identity.
    value.activate();assert len([c for c in value.client.calls if c['kind']=='transfer'])==1


def test_checkpoint_retains_both_monotone_consumptions_without_restore_claim():
    value,_,_=actual_owner();value.activate();saved=value.controller_checkpoint()
    assert saved['possession']['consumed_action_ids'] and saved['consumed_completions']
    assert saved['restore_supported'] is False
    saved['possession']['consumed_action_ids'].clear();saved['consumed_completions'].clear()
    saved['client_state']['outbox'].clear()
    assert value.possession.consumed and value.consumed_completions and value.client.state['outbox']
    with pytest.raises(ValueError,match='fresh_trial_only'):
        p.BridgeOwner(SimpleNamespace(physical_time=1.),value.owner,value.plan)


def test_fresh_current_barrier_cap_sticks_even_without_token_and_relays_once(monkeypatch):
    value,view,peer=actual_owner();view['trays']=[]
    monkeypatch.setattr(p,'MAX_EMPTY_OPERATIONS',2)
    value.activate()
    assert value.cap_observed and value.cap_relay['request_id']
    assert len(value.client.calls)==1 and value.client.calls[0]['kind']=='planning_snapshot_v2'
    assert len(value.reads)==2
    value.session.physical_time+=1000.;value.activate()
    assert value.client.refreshes==2 and len(value.client.calls)==1 and len(value.reads)==2


@pytest.mark.parametrize('defect',['pending','rejected','old_peer','missing_parking','new_unpublished'])
def test_received_barrier_fails_closed(defect):
    value,view,peer=actual_owner();box=value.client.state['outbox'];nodes={n['node']:n for n in view['node_contracts']}
    own=p.reuse.latest_own_capture(box,value.owner,value.peer,view['now'],nodes)
    row=next(r for rid,r in box.items() if r['kind']=='transfer' and rid not in value.possession.parking)
    if defect=='pending':row['terminal']=False
    elif defect=='rejected':row['submission_reply']['status']='rejected'
    elif defect=='old_peer':peer['capture']['local_capture']['captured_at']=own['envelope']['capture']['local_capture']['captured_at']-1
    elif defect=='missing_parking':
        actions=peer['capture']['extension']['submitted_physical_actions'];actions.pop(0)
    else:
        box['opaque-new']=deepcopy(row);box['opaque-new']['payload']['request_id']='opaque-new'
    assert p.received_barrier(box,value.owner,own,peer,value.plan['parking'],value.plan['token_tray_id'],view['now']) is None


def test_received_duplicate_ACK_after_selfcapture_not_false_pending():
    value,view,peer=actual_owner();box=value.client.state['outbox'];nodes={n['node']:n for n in view['node_contracts']}
    own=p.reuse.latest_own_capture(box,value.owner,value.peer,view['now'],nodes)
    row=next(r for rid,r in box.items() if r['kind']=='transfer' and rid not in value.possession.parking)
    row['client_view']['last_delivered_ack']['delivered_at']=view['now']
    assert p.received_barrier(box,value.owner,own,peer,value.plan['parking'],value.plan['token_tray_id'],view['now']) is not None


def test_halted_owner_refreshes_without_any_observation_or_new_action():
    value,_,_=actual_owner();value.halt_new_actions=True;value.activate()
    assert value.client.refreshes==1 and not value.reads and not value.client.calls


def test_transition_to_quiet_executes_only_original_startup_activation(monkeypatch):
    value,_,_=actual_owner();value.quiet=False;calls=[]
    def original(self):
        calls.append('frozen_startup');self.quiet=True
    monkeypatch.setattr(p.base.Owner,'activate',original)
    value.activate()
    assert calls==['frozen_startup'] and not value.reads and not value.client.calls
    assert not value.operations and not value.bridge_publications


def historical_guard_fixture(monkeypatch):
    """Actual typed ACK/body; the lowered cap and prior cap-proof are hypothetical."""
    value,view,peer=actual_owner();box=value.client.state['outbox'];nodes={n['node']:n for n in view['node_contracts']}
    own=p.reuse.latest_own_capture(box,value.owner,value.peer,view['now'],nodes)
    proof=p.received_barrier(box,value.owner,own,peer,value.plan['parking'],value.plan['token_tray_id'],view['now'])
    captured=own['envelope']['capture']['local_capture']['captured_at']
    proof.update(own_captured_at=captured-4,peer_captured_at=captured-3,observed_at=captured-2)
    value.cap_observed=True;value.cap_relay={'request_id':own['request_id'],'at':captured-2,'proof':proof,
        'source_owner':value.owner,'target_owner':value.peer,'publication_enqueued':True}
    monkeypatch.setattr(p,'MAX_EMPTY_OPERATIONS',2)
    return value.summary(),value.plan,view


def test_historical_cap_delivery_is_not_full_replay_or_new_action_permission(monkeypatch):
    summary,plan,public=historical_guard_fixture(monkeypatch)
    result=p.cap_relay_evidence(summary,plan,public)
    assert result['status']=='historical_delivered_cap_relay'
    assert not result['new_actions_authorized'] and not result['full_policy_replay_verified']


@pytest.mark.parametrize('defect',['unsubmitted','missing_ack','undelivered','expired_delivery','digest','wrong_owner','no_cap','failure','duplicate_ids','duplicate_jobs'])
def test_cap_proof_alone_never_certifies_undelivered_relay(monkeypatch,defect):
    summary,plan,public=historical_guard_fixture(monkeypatch);relay=summary['cap_relay']
    row=summary['outbox']['outbox'][relay['request_id']];ack=row['client_view']['last_delivered_ack']
    if defect=='unsubmitted':relay['publication_enqueued']=False
    elif defect=='missing_ack':row['client_view']={}
    elif defect=='undelivered':ack['status']='pending'
    elif defect=='expired_delivery':ack['planning_snapshot_v2']['capture']['local_capture']['valid_until']=ack['completed_at']
    elif defect=='digest':ack['planning_snapshot_v2']['payload_sha256']='0'*64
    elif defect=='wrong_owner':row['payload']['owner_id']='other'
    elif defect=='no_cap':summary['cap_observed']=False
    elif defect=='failure':summary['failure']={'reason':'prior_rejection'}
    elif defect=='duplicate_ids':relay['proof']['received_action_ids'].append(relay['proof']['received_action_ids'][0])
    else:relay['proof']['token_completed_job_ids']*=2
    assert p.cap_relay_evidence(summary,plan,public)['status']=='unknown_cap_relay'


@pytest.mark.parametrize('failure',['terminal','guard'])
def test_policy_failure_preserves_other_owner_retry_and_full_native_horizon(monkeypatch,failure):
    instances=[]
    class Owner:
        def __init__(self,session,owner,plan):
            self.session=session;self.owner=owner;self.failure=None;self.halt_new_actions=False
            self.client=SimpleNamespace(calls=[]);self.activations=[];instances.append(self)
        def activate(self):
            self.activations.append((self.session.physical_time,self.halt_new_actions))
            if self.owner=='A' and not self.halt_new_actions:
                if failure=='guard':raise ValueError('malformed_observation')
                self.failure={'reason':'terminal_rejected'}
            if self.owner=='B':
                self.client.calls.append({'kind':'transfer','retry':True,'request_id':'same-pending-id'})
    class Session:
        physical_time=0.
        def advance_to(self,target,**kwargs):
            self.physical_time=target;return {'status':'reached','horizon_complete':True}
    monkeypatch.setattr(p,'BridgeOwner',Owner);monkeypatch.setattr(p,'HORIZON',20.)
    owners,status,tick=p.run_policy(Session(),{'parking_plan':{'owners':['A','B']}})
    assert status=='horizon_complete_with_policy_failure' and tick==2
    assert owners[1].activations==[(0.,True),(10.,True),(20.,True)]
    assert len(owners[1].client.calls)==3 and {r['request_id'] for r in owners[1].client.calls}=={'same-pending-id'}


def test_fixed_domain_and_original005_source_are_not_changed():
    assert hashlib.sha256(open(p.base.__file__,'rb').read()).hexdigest()==p.reuse.BASE_SHA
    scope=p.scope();assert (scope['offered'],scope['total_tray_identities'],scope['noncirculating_parked_trays'])==(28506,22,21)
    assert (p.MAX_TOKEN_COMPLETIONS,p.MAX_EMPTY_OPERATIONS,p.MAX_PHYSICAL)==(39,78,100)
    assert p.HORIZON==86400. and scope['native_calls']==0 and not scope['complete_100ms_certified']
