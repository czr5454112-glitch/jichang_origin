"""No native sessions: actual delivered fixtures, policy counterexamples and budgets."""
from copy import deepcopy
from functools import lru_cache
import math
from types import SimpleNamespace
import json
import hashlib
import time
import pytest
from scripts.experiments.g31_ics_circulation import research_original_low_wip_repeat as p
from scripts.experiments.g31_ics_circulation import verify_original_low_wip_repeat as v


@lru_cache(maxsize=1)
def saved():
    path = p.OUT/'original_low_wip_third_prepare_001'
    return p.base.gzread(path/'input.json.gz'), p.base.gzread(path/'raw_final.json.gz'), p.base.read(path/'preregistered_protocol.json')


def fixture():
    data, raw, plan = saved()
    source = next(o for o in raw['owners'] if o.get('third_supply'))
    third = source['third_supply']; proof = third['return_proof']; token = plan['parking_plan']['token_tray_id']
    view = {**{k: deepcopy(data[k]) for k in ('node_records','edge_records','node_contracts','edge_contracts')},
        'owner_id': source['owner'], 'now': third['at'], 'trays': [deepcopy(proof['current_token'])]}
    peer = deepcopy(third['choice']['delivered_message']); owner = source['owner']; other = peer['capture']['local_capture']['source_owner']
    outbox = {rid: deepcopy(row) for rid, row in source['outbox']['outbox'].items()
        if row['kind'] == 'transfer' and rid != third['request_id']}
    # Synthetic continuation fixture: preserve actual receipt/ACK facts, but
    # map the previous scripted ID into this NEW policy's declared namespace.
    # This is not relabelled evidence of a native repeating-policy execution.
    old_id = source['second_supply']['request_id']
    prior = source['second_supply']['return_proof']['terminal_receipt']['receipt_id']
    new_id = p.base.owner_request_id(owner, 'repeat:'+prior)
    outbox[new_id] = outbox.pop(old_id)
    outbox[new_id]['payload']['request_id'] = new_id
    own = proof['own_delivered_self_copy']; rid = own['request_id']
    outbox[rid] = deepcopy(source['outbox']['outbox'][rid]); outbox[rid]['client_view']['last_delivered_ack'] = deepcopy(own['ack'])
    return view, outbox, peer, owner, other, token, deepcopy(plan['parking_plan']), source


def test_actual_latest_delivered_permit_and_complete_action_barrier():
    view, box, peer, owner, other, token, plan, _ = fixture()
    permit = p.local_permit(view, box, owner, other, token, [])
    assert permit['receipt']['business_bag_id'] == 'projected:1x:6'
    barrier = p.physical_barrier(box, owner, peer, plan['parking'])
    assert barrier['known_supply_count'] == 2 and len(barrier['received_request_ids']) == 24
    assert p.local_permit(view, box, owner, other, token, [permit['receipt']['receipt_id']]) is None


@pytest.mark.parametrize('change', ['holding','loaded','future_available','edge','reception','not_destination','missing_self_ack','expired_latest'])
def test_actual_permit_missing_required_fact_cannot_reopen(change):
    view, box, peer, owner, other, token, plan, _ = fixture()
    tray = view['trays'][0]
    if change == 'holding': tray['mode'] = 'holding'
    elif change == 'loaded': tray['business_bag_id'] = 'wrong_job'
    elif change == 'future_available': tray['available_at'] = view['now']+1
    elif change == 'edge': tray['edge_to'] = 49
    elif change == 'reception': tray['reception_node'] = 49
    elif change == 'not_destination': tray['node'] = 138
    elif change == 'missing_self_ack':
        for r in box.values():
            if r['kind'] == 'planning_snapshot_v2': r['client_view'] = {}
    else: view['now'] += 200
    assert p.local_permit(view, box, owner, other, token, []) is None


@pytest.mark.parametrize('change', ['missing_park','pending_peer','pending_own','unknown_kind','unknown_identity','duplicate_action'])
def test_peer_action_coverage_never_infers_received_from_absence(change):
    view, box, peer, owner, other, token, plan, _ = fixture()
    actions = peer['capture']['extension']['submitted_physical_actions']
    if change == 'missing_park': actions.pop()
    elif change == 'pending_peer': actions[0]['last_delivered_ack'] = None
    elif change == 'pending_own': next(r for r in box.values() if r['kind']=='transfer')['client_view']['last_delivered_ack'] = None
    elif change == 'unknown_kind': actions[0]['kind'] = 'route'
    elif change == 'unknown_identity': actions[0]['request_id'] = 'foreign_intent'
    else: actions.append(deepcopy(actions[0]))
    if change in ('unknown_kind','unknown_identity','duplicate_action'):
        with pytest.raises(ValueError): p.physical_barrier(box, owner, peer, plan['parking'])
    else: assert p.physical_barrier(box, owner, peer, plan['parking']) is None


class FakeClient:
    def __init__(self, box): self.state = {'outbox': box}; self.calls = []; self.refreshed = 0
    def refresh(self, **kwargs): self.refreshed += 1
    def submit(self, owner, kind, payload, *, request_id):
        request = {**deepcopy(payload), 'owner_id': owner, 'request_id': request_id}
        self.calls.append({'kind': kind, 'owner': owner, 'request_id': request_id, 'request': request, 'retry': False})
        self.state['outbox'][request_id] = {'kind': kind, 'payload': request, 'terminal': False, 'client_view': {}, 'submission_reply': {'status':'accepted'}}


def owner_fixture(cap=8):
    view, box, peer, owner, other, token, plan, source = fixture()
    session = SimpleNamespace(physical_time=view['now'],
        observe_protocol_control_policy_recent=lambda *a: deepcopy(view),
        protocol_planning_snapshots_v2=lambda *a: [deepcopy(peer)])
    result = p.RepeatOwner(session, owner, {**plan, 'supply_cap': cap})
    result.client = FakeClient(box); result.quiet = True; result.index = len(result.rows); result.supply = deepcopy(source['supply'])
    result.relayed = [[rid, 'received'] for rid,r in box.items() if r['kind']=='transfer' and p.is_supply(rid,owner)]
    result.next_publication = view['now']+10
    return result, view, peer


def test_cap3_and_cap8_same_policy_through_third_supply():
    a, _, _ = owner_fixture(3); b, _, _ = owner_fixture(8)
    a.activate(); b.activate()
    assert a.client.calls == b.client.calls and a.repeated == b.repeated
    assert len(a.repeated) == 1 and a.repeated[0]['choice']['job']['origin'] == 49
    assert a.repeated[0]['choice']['job']['business_bag_id'] == 'projected:1x:8'
    assert len(a.consumed) == 1


def test_same_source_blocked_head_is_not_skipped():
    a, _, _ = owner_fixture(); a.activate()
    body = a.repeated[0]['choice']['delivered_message']['capture']['local_capture']
    heads = {}
    for j in sorted(body['jobs'],key=lambda j:(j['arrival'],j['business_bag_id'])):
        if j['status']=='waiting_for_tray': heads.setdefault(j['origin'],j['business_bag_id'])
    assert heads[26] == 'projected:1x:14' and a.repeated[0]['choice']['job']['origin'] != 26


def test_received_ack_relay_occurs_without_current_local_token():
    a, view, _ = owner_fixture(); a.relayed = []; view['trays'] = []
    a.activate()
    assert a.repeated == [] and len(a.repeat_publications) == 2
    assert {r['reason']['kind'] for r in a.repeat_publications} == {'received_ack_relay'}
    prior = len(a.repeat_publications); a.activate(); assert len(a.repeat_publications) == prior


def test_expired_peer_does_not_deadlock_fresh_invitation():
    a, view, peer = owner_fixture(); a.next_publication = 0
    # Endpoint supplies a legitimate newest tombstone; it cannot authorize work.
    peer['status'] = 'expired'
    a.activate()
    assert a.repeated == [] and a.repeat_publications[-1]['reason']['kind'] == 'current_empty_invitation'


def test_rejection_consumes_receipt_without_replacement():
    a, _, _ = owner_fixture(); a.activate(); rid = a.repeated[0]['request_id']
    a.client.state['outbox'][rid]['submission_reply'] = {'status':'rejected'}
    a.activate(); assert len(a.repeated) == len(a.consumed) == 1
    assert a.failure['reason'] == 'unknown_supply_submission_rejected'


def test_pending_previous_transfer_blocks_new_invitation_and_supply():
    a, _, _ = owner_fixture(); a.next_publication = 0
    row = next(r for rid,r in a.client.state['outbox'].items() if p.is_supply(rid,a.owner))
    row['client_view']['last_delivered_ack'] = None; row['terminal'] = False
    a.activate(); assert not a.repeated and not a.repeat_publications


def test_publication_budget_is_explicit_unknown_not_unlimited():
    a, _, peer = owner_fixture(); a.next_publication = 0; peer['status'] = 'expired'
    a.repeat_publications = [{} for _ in range(p.MAX_PUBLICATIONS)]
    a.activate(); assert a.failure['reason'] == 'unknown_publication_budget' and not a.repeated


def test_new_resource_owner_is_required_for_permit():
    view, box, peer, owner, other, token, plan, _ = fixture()
    for row in view['node_contracts']:
        if row['node'] == view['trays'][0]['node']: row['resource_owner'] = other
    with pytest.raises(ValueError, match='nonlocal'): p.local_permit(view, box, owner, other, token, [])


def test_latest_receipt_never_uses_older_identity():
    view, box, peer, owner, other, token, plan, _ = fixture()
    own = next(r for r in box.values() if r['kind']=='planning_snapshot_v2')['client_view']['last_delivered_ack']['planning_snapshot_v2']
    body=own['capture']; nodes={r['node']:r for r in view['node_contracts']}
    receipt=p.receipt_for_token(body['local_capture'],body['extension'],token,owner,nodes)
    assert receipt['business_bag_id']=='projected:1x:6'
    duplicate=deepcopy(body);duplicate['extension']['terminal_receipts'].append(deepcopy(receipt))
    with pytest.raises(ValueError,match='duplicate'):p.receipt_for_token(duplicate['local_capture'],duplicate['extension'],token,owner,nodes)


@pytest.mark.parametrize('clock', [True,-1,float('nan'),float('inf')])
def test_prefix_cannot_erase_invalid_clock(clock):
    with pytest.raises(ValueError):v.semantic({'endpoint':'advance_to','result':{'wall_seconds':clock}})


def test_prefix_only_removes_exact_outer_wall_field():
    a={'endpoint':'advance_to','result':{'wall_seconds':1.,'physical_time':10.,'nested':{'wall_seconds':9.}}}
    b=deepcopy(a);b['result']['wall_seconds']=2.
    assert v.semantic(a)==v.semantic(b) and a['result']['wall_seconds']==1.
    b['result']['nested']['wall_seconds']=10.
    assert v.semantic(a)!=v.semantic(b)


def test_frozen_runtime_restored_on_exception():
    original=(p.base.Owner,p.base.run_policy,p.base.HORIZON)
    with pytest.raises(RuntimeError):
        with p.installed(): raise RuntimeError('test')
    assert (p.base.Owner,p.base.run_policy,p.base.HORIZON)==original
    assert p.base.sha(p.base.__file__)==p.BASE_SHA and p.base.sha(p.reuse.__file__)==p.REUSE_SHA


def test_closed_source_domain_includes_launcher_job_and_verifier():
    paths=p.source_paths();names={x.name for x in paths}
    assert {'bounded_windows_job.py','launch_original_low_wip_repeat.py','verify_original_low_wip_repeat.py',
        'run_g4irsf28_service_potential.py','test_g31_circulation_low_wip_repeat.py'} <= names
    assert p.CAPS=={'cap3':3,'cap8':8} and p.HORIZON==86400. and p.PARENT_SECONDS==2400.


@pytest.mark.parametrize('suffix', ['repeat:fake','repeat:completion:21:owner:system_domestic:0',
    'repeat:completion:21:owner:system_domestic:01','repeat:completion:21:owner:system_domestic:-1'])
def test_supply_identifier_cannot_smuggle_an_unclassified_remote_action(suffix):
    owner='owner:system_domestic'
    assert not p.is_supply(p.base.owner_request_id(owner,suffix),owner)


def test_new_owner_permit_uses_its_own_receipt_and_current_authority(monkeypatch):
    view, box, peer, owner, other, token, plan, _=fixture()
    view['owner_id']=other;view['trays'][0]['node']=46;view['trays'][0]['available_at']=21759.803;view['now']=21780.
    receipt={'receipt_id':f'completion:{len(other.encode())}:{other}:1','source_local_sequence':1,'source_owner':other,
        'event':'UNLOAD_COMPLETE','status':'completed','business_bag_id':'projected:1x:8','tray_id':token,'destination':46,'completed_at':21758.803}
    # Unit injection at an already-authenticated helper boundary, NOT native evidence.
    authenticated={'envelope':{'capture':{'local_capture':{'captured_at':21772.},'extension':{'terminal_receipts':[receipt]}}}}
    monkeypatch.setattr(p.reuse,'latest_own_capture',lambda *a:authenticated)
    permit=p.local_permit(view,{},other,owner,token,[])
    assert permit['receipt']['source_owner']==other and permit['current_token']['node']==46
    assert p.local_permit(view,{},other,owner,token,[receipt['receipt_id']]) is None
    with pytest.raises(ValueError,match='permit_owner'):p.local_permit(view,{},owner,other,token,[])


def test_cap_reached_does_not_create_fourth_request():
    a, view, peer=owner_fixture(3)
    rid=p.base.owner_request_id(a.owner,f'repeat:completion:{len(a.owner.encode())}:{a.owner}:99')
    a.client.state['outbox'][rid]={'kind':'transfer','terminal':True,'client_view':{'last_delivered_ack':{'status':'received','delivered_at':20000.}}}
    a.relayed.append([rid,'received']);a.activate()
    assert a.cap_observed and not a.repeated and not a.client.calls
    peer['status']='expired';a.next_publication=0
    before=a.client.refreshed;a.activate()
    assert a.cap_observed and not a.repeat_publications and not a.client.calls
    assert a.client.refreshed==before+1


def test_incomplete_native_boundary_does_not_advance_or_claim_horizon(monkeypatch):
    class EmptyOwner:
        def __init__(self,*args):self.client=SimpleNamespace(calls=[]);self.failure=None
        def activate(self):pass
    monkeypatch.setattr(p,'RepeatOwner',EmptyOwner)
    native=SimpleNamespace(physical_time=0.,advance_to=lambda *a,**k:{'status':'event_budget','horizon_complete':False})
    owners,status,tick=p.run_policy(native,{'parking_plan':{'owners':['A','B']},'supply_cap':8})
    assert status=='unknown_native_budget' and tick==0 and native.physical_time==0


def test_failure_halts_new_actions_but_pending_other_owner_retries_to_horizon(monkeypatch):
    created=[]
    class PendingOwner:
        def __init__(self,session,owner,plan):
            self.owner=owner;self.client=SimpleNamespace(calls=[]);self.failure=None;self.halt_new_actions=False
            self.refreshes=0;created.append(self)
        def activate(self):
            self.refreshes+=1
            if self.owner=='A' and not self.halt_new_actions:self.failure={'reason':'unknown_publication_budget'}
            if self.owner=='B':
                assert self.halt_new_actions
                self.client.calls.append({'kind':'transfer','retry':True,'request_id':'same_pending_immutable_id'})
    monkeypatch.setattr(p,'RepeatOwner',PendingOwner);monkeypatch.setattr(p,'HORIZON',20.);monkeypatch.setattr(p,'MAX_TICKS',4)
    session=SimpleNamespace(physical_time=0.)
    def advance(target,**kwargs):
        session.physical_time=target;return {'status':'reached','horizon_complete':True}
    session.advance_to=advance
    _,status,tick=p.run_policy(session,{'parking_plan':{'owners':['A','B']},'supply_cap':8})
    assert session.physical_time==20. and status=='horizon_complete_with_policy_failure' and tick==2
    assert all(o.refreshes==3 for o in created)
    assert {r['request_id'] for r in created[1].client.calls}=={'same_pending_immutable_id'}
    assert all(r['retry'] for r in created[1].client.calls)


@pytest.mark.parametrize('cap',[3,8])
def test_actual_saved005_startup_prefix_is_unchanged(cap):
    report=v.bootstrap_replay(cap)
    assert report['status']=='passed_actual_saved_bootstrap_prefix' and report['through']==8900.
    assert report['api_rows']>8000 and report['native_executions']==0


@pytest.mark.parametrize('mode',['timeout','error','empty_success'])
def test_whole_job_failure_retains_both_unknown_branches(tmp_path,monkeypatch,mode):
    from scripts.experiments.g31_ics_circulation import launch_original_low_wip_repeat as launch
    data=b'{}';(tmp_path/'campaign.json').write_bytes(data)
    ledger={name:{'status':'unknown_unexecuted'} for name in p.CAPS}
    (tmp_path/'branch_ledger.json').write_text(json.dumps(ledger))
    digest=hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(launch,'BOOT',time.monotonic())
    monkeypatch.setattr(launch.sys,'argv',['launch','--output',str(tmp_path),'--campaign-sha256',digest])
    calls=[]
    def fake(command,**kwargs):
        calls.append((command,kwargs));assert kwargs['timeout']<=2400. and kwargs['admission']==digest
        if mode=='error':raise PermissionError('injected assignment failure')
        return {'status':'hard_timeout' if mode=='timeout' else 'exited','exitcode':1 if mode=='timeout' else 0}
    monkeypatch.setattr(launch.bounded_windows_job,'run',fake)
    if mode=='timeout':assert launch.main()==1
    else:
        with pytest.raises((PermissionError,FileNotFoundError)):launch.main()
    receipt=json.loads((tmp_path/'external_launch_receipt.json').read_bytes())
    assert receipt['status'].startswith('unknown') and calls
    assert json.loads((tmp_path/'branch_ledger.json').read_bytes())==ledger
    with pytest.raises(ValueError,match='already_attempted'):launch.main()
