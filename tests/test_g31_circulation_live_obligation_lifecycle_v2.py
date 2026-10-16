"""Immutable actual96 supplied-data fixtures; no native or predictor calls."""
from copy import deepcopy
from functools import lru_cache
import gzip,hashlib,json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import domain_guard_v2 as g
from scripts.experiments.g31_ics_circulation import live_obligation_lifecycle_state_v2 as state

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
REVIEW=OUT/'live_obligation_native_domain_saved_review_001.json'
REVIEW_SHA='76c2c3c9a11c8e7f4a31b9d25dd498e5305b8f041292b30402ca0a81959bbdb7'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
@lru_cache(None)
def review():
    assert digest(REVIEW)==REVIEW_SHA
    return json.loads(REVIEW.read_bytes())
@lru_cache(None)
def raw(key):
    ref=review()['rows'][key]['raw_artifact'];assert digest(ref['path'])==ref['sha256']
    return json.loads(gzip.decompress(Path(ref['path']).read_bytes()))
def fixture(key,owner='B'):
    r=raw(key);d=deepcopy(r['decisions'][owner][0]);info=d['information'];ep=info['raw_endpoints'];obs=info['native_read']
    prior=r['calls'][:d['predecision_call_prefix_count']]
    requests=[c['request'] for c in prior if c['request']['request_id']==obs['own_request_id']]
    assert requests and all(x==requests[0] for x in requests)
    actions={c['request']['request_id']:c['kind'] for c in prior if c['request']['owner_id']==owner and c['kind'] in state.PHYSICAL_KINDS}
    return ep,{'retained':deepcopy(r['retained_ledgers'][owner]),'own_actions':sorted(actions.items()),'phase':d['phase'],
        'own_request_id':obs['own_request_id'],'peer_message_id':obs['selected_peer_message_id'],
        'collection_started_at':obs['collection_started_at'],'policy_quiet_since':obs['collection_started_at'],
        'own_request':deepcopy(requests[0])}
def validate(key,owner='B'):
    ep,kw=fixture(key,owner)
    return g.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],**kw)
def bundle_fixture():
    result=validate('no_overlap/vector_02');assert result['status']=='conditional_validated_later_v3_data',result
    b=deepcopy(result['bundle']);ep=result['raw_endpoints'];contract=g.old.model.public_contract(ep['view'])
    contract['native_semantics']=deepcopy(g.old.model.SUPPORTED_NATIVE_SEMANTICS)
    entries=[]
    for e in result['envelopes'].values():entries+=g.old.validate_inflight(e['capture'],contract,now=b['now'],delivered_at=e['delivered_at'])['entries']
    floor=min(r['captured_at'] for r in b['source_records'])
    return contract,b,{'now':b['now'],'phase':b['phase'],'source_records':b['source_records'],
        'terminal_receipts':b['terminal_receipts'],'owner_pending_tray_requests':[],'entry_receipts':entries,
        'collection_contract':{'schema':'g31.conditional_collection_quiescence.v1','physical_admissions_quiesced_from':floor,
            'through':b['now'],'future_python_actions_certified_by_native':False}}

def test_private_endpoint_code_and_old_module_globals_are_unchanged():
    assert g.validate_later_pair.__code__ is g.old.validate_later_pair.__code__
    assert g.validate_collected_endpoints.__code__ is g.old.validate_collected_endpoints.__code__
    assert g.validate_later_pair.__globals__ is g.validate_collected_endpoints.__globals__
    assert g.validate_later_pair.__globals__ is not vars(g.old)
    assert g.old.validate_later_pair.__globals__['later_bundle'] is g.old.later_bundle
    assert g._private['later_bundle'] is state.later_bundle

def test_all192_actual_collections_preserve_true_current_changes_and_older_known_inputs():
    current=0;old_known=0;new_known=0
    for key,row in review()['rows'].items():
        for before in row['stages']:
            result=validate(key,before['owner']);known=result['status']=='conditional_validated_later_v3_data'
            if 'owned_tray_changed_after_v3_capture' in before['reasons']:
                current+=1;assert result['reasons']==['owned_tray_changed_after_v3_capture']
            if before['verified']:
                old_known+=1;assert known,(key,before['owner'],result)
            if known:
                new_known+=1
                assert result['native_delivery_verified'] is False and result['native_protection_certified'] is False
                assert result['bundle']['current_state_certified'] is False
    assert current==30 and old_known==126
    assert new_known>=old_known  # Extra supplied-data acceptance never edits saved statuses.

@pytest.mark.parametrize('key',['no_overlap/vector_02','no_overlap/vector_22','insufficient_advance/vector_25'])
def test_real_extra_completed_receipt_shapes_can_be_conditionally_represented(key):
    result=validate(key)
    assert result['status']=='conditional_validated_later_v3_data',result
    assert 'loaded' in result['bundle']['completed_prefix']
    assert len(result['bundle']['completed_prefix'])>1
    assert raw(key)['summary']['status']=='unknown_missing_input_or_unexecuted_counterfactual'

@pytest.mark.parametrize('mutation',['missing_terminal','changed_terminal_owner','future_terminal','duplicate_terminal','changed_receipt_id',
    'missing_loaded','wrong_completed_job','pending','bad_occupancy','missing_resource','bad_coverage','cross_union_ack',
    'extra_known_fault','future_job_epoch','missing_entry','entry_traversal','entry_after_floor','expired_exit'])
def test_pure_bundle_rejects_adversarial_completed_state_and_authority(mutation):
    contract,b,kw=bundle_fixture();term=kw['terminal_receipts'];floor=kw['collection_contract']['physical_admissions_quiesced_from']
    if mutation=='missing_terminal':term.pop()
    elif mutation=='changed_terminal_owner':term[0]['source_owner']='foreign'
    elif mutation=='future_terminal':term[0]['completed_at']=b['now']+1.
    elif mutation=='duplicate_terminal':term.append(deepcopy(term[0]))
    elif mutation=='changed_receipt_id':term[0]['identity']=''
    elif mutation=='missing_loaded':term[:]=[r for r in term if r['business_bag_id']!='loaded']
    elif mutation=='wrong_completed_job':b['jobs']['reuse2']['status']='completed'
    elif mutation=='pending':kw['owner_pending_tray_requests']=['unresolved']
    elif mutation=='bad_occupancy':b['resources'][10]['occupancy']+=1
    elif mutation=='missing_resource':b['resources'].pop(10)
    elif mutation=='bad_coverage':kw['source_records'][0]['node_ids'].pop()
    elif mutation=='cross_union_ack':kw['source_records'][0]['submitted_physical_actions'][0]['last_delivered_ack']['delivered_at']=floor
    elif mutation=='extra_known_fault':kw['source_records'][0]['known_faults']=[{}]
    elif mutation=='future_job_epoch':b['jobs']['receiver']['loaded_at']=b['now']+1.
    elif mutation=='missing_entry':kw['entry_receipts'].clear()
    elif mutation=='entry_traversal':kw['entry_receipts'][0]['traversal_id']+=1
    elif mutation=='entry_after_floor':kw['entry_receipts'][0]['entered_at']=b['now']
    else:kw['entry_receipts'][0]['derived_edge_exit_at']=b['now']
    result=state.later_bundle(contract,b['jobs'],b['trays'],b['resources'],**kw)
    assert result['status']=='unknown',mutation

def stationary_fixture(key,name,owner='B'):
    r=review()['rows'][key];d=next(d for d in r['stages'] if d['owner']==owner)
    t=deepcopy(next(t for c in d['source_captures'] for t in c['trays'] if t['tray_id']==name))
    native=raw(key);jobs={j['business_bag_id']:deepcopy(j) for j in native['input']['jobs']}
    for c in d['source_captures']:
        for j in c['jobs']:jobs[j['business_bag_id']].update(j)
    completed={r['business_bag_id']:r['completed_at'] for r in d['delivered_terminal_receipts']}
    for j in completed:jobs[j]['status']='completed'
    service={n[0]:max(.001,n[2]) for n in native['input']['node_records']}
    return t,jobs,completed,{'floor':d['capture_union_floor'],'now':d['at'],'phase':d['phase'],'service':service}

@pytest.mark.parametrize('key,name',[
    ('mechanism/vector_02','P'),('no_overlap/vector_00','E'),
    ('insufficient_advance/vector_16','E'),('no_overlap/vector_22','P'),('no_overlap/vector_02','P')])
def test_exact_native_stationary_service_unload_hold_and_empty_fields(key,name):
    t,jobs,completed,kw=stationary_fixture(key,name)
    bound=state.stable_stationary(name,t,jobs,completed,**kw)
    assert bound is None or bound>kw['now']

@pytest.mark.parametrize('mutation',['known_false','bool_ready','equal_now','past_ready','start_after_floor','wrong_kind',
    'wrong_node','wrong_prefix','wrong_job','bad_available','bad_load_complete','missing_known'])
def test_stationary_service_adversarial_calendar_and_identity(mutation):
    t,jobs,completed,kw=stationary_fixture('mechanism/vector_02','P')
    if mutation=='known_false':t['service_ready_known']=False
    elif mutation=='bool_ready':t['service_ready_at']=True
    elif mutation=='equal_now':t['service_ready_at']=kw['now']
    elif mutation=='past_ready':t['service_ready_at']=kw['now']-.01
    elif mutation=='start_after_floor':t['service_ready_at']=kw['floor']+kw['service'][t['node']]+.01
    elif mutation=='wrong_kind':t['ready_kind']='observed_load_completion'
    elif mutation=='wrong_node':t['node']=1
    elif mutation=='wrong_prefix':t['committed_prefix']=[3]
    elif mutation=='wrong_job':t['business_bag_id']='receiver'
    elif mutation=='bad_available':t['available_at']=kw['now']+1
    elif mutation=='bad_load_complete':t['load_complete_at']=0.
    else:del t['service_ready_known']
    with pytest.raises((ValueError,KeyError)):state.stable_stationary('P',t,jobs,completed,**kw)

@pytest.mark.parametrize('mutation',['wrong_kind','mismatch_available','future_start','equal_now','missing_completion','changed_hold'])
def test_actual_unload_and_hold_require_exact_future_native_bounds(mutation):
    key,name=('no_overlap/vector_22','P') if mutation in ('missing_completion','changed_hold') else ('insufficient_advance/vector_16','E')
    t,jobs,completed,kw=stationary_fixture(key,name)
    if mutation=='wrong_kind':t['ready_kind']='observed_load_completion'
    elif mutation=='mismatch_available':t['available_at']+=.01
    elif mutation=='future_start':t['available_at']=t['service_ready_at']=kw['floor']+jobs['receiver']['unload_seconds']+.01
    elif mutation=='equal_now':t['available_at']=t['service_ready_at']=kw['now']
    elif mutation=='missing_completion':completed.pop('blocker')
    else:jobs['blocker']['hold_seconds']+=.01
    with pytest.raises((ValueError,KeyError)):state.stable_stationary(name,t,jobs,completed,**kw)

@pytest.mark.parametrize('mutation',['bad_digest','future_ack','wrong_owner','pending_current','missing_coverage'])
def test_endpoint_checks_are_not_bypassed(mutation):
    ep,kw=fixture('no_overlap/vector_02')
    if mutation=='bad_digest':ep['received'][0]['payload_sha256']='0'*64
    elif mutation=='future_ack':ep['command']['last_delivered_ack']['delivered_at']=ep['view']['now']+1.
    elif mutation=='wrong_owner':ep['view']['owner_id']='A'
    elif mutation=='pending_current':kw['own_actions'].append(('unseen','transfer'))
    else:ep['received'][0]['capture']['capture_v2']['local_capture']['coverage']['complete_for_declared_local_scope']=False
    result=g.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],**kw)
    assert result['status']=='unknown'
