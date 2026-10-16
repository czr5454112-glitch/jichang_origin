"""Actual saved endpoint shapes; no native or prediction is invoked."""
import copy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import domain_guard_historical_service as gate
from scripts.experiments.g31_ics_circulation import verify_live_obligation_recollection as replay
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as digest

OUT=Path(__file__).resolve().parents[1]/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN=OUT/'live_obligation_recollection_native_v2_prepare_001'
DIAG=OUT/'live_obligation_recollection_v2_residual_001.json'
ROWS=json.loads(DIAG.read_text())['rows']

def arguments(key,owner='B',index=-1):
    raw=json.loads(gzip.decompress((RUN/(key+'.json.gz')).read_bytes()))
    entry=raw['collection_attempts'][owner][index]
    ep=copy.deepcopy(entry['information']['raw_endpoints']);pending=entry['collection']
    requests=replay.prefix_requests(raw,owner,entry)
    # Native binding shape: only public static row sequences are tuples.
    for field in ('node_records','edge_records'):ep['view'][field]=[tuple(r) for r in ep['view'][field]]
    kwargs={'retained':raw['retained_ledgers'][owner],
        'own_actions':sorted((k,kind) for k,(kind,_) in requests.items() if kind in replay.policy.PHYSICAL_KINDS),
        'phase':entry['phase'],'own_request_id':pending['request_id'],'peer_message_id':pending['peer_message'],
        'collection_started_at':pending['at'],'policy_quiet_since':pending['policy_quiet_since'],
        'own_request':requests[pending['request_id']][1],
        'own_publication_requests':{k:r for k,(kind,r) in requests.items() if kind=='planning_snapshot_v3'}}
    return raw,entry,ep,kwargs

def invoke(ep,kw):return gate.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],**kw)
def historical(ep):
    return next(c for c in ep['view']['client_commands'] if 'preflight' in c['request_id'])
def rehash(command):
    e=command['last_delivered_ack']['planning_snapshot_v3'];e['payload_sha256']=digest.capture_digest_v3(e['capture'])

@pytest.mark.parametrize('key',[k for k,r in ROWS.items() if r['cause'].startswith('goal_service')])
def test_all_fourteen_real_known_historical_entries_preserve_raw(key):
    raw,entry,ep,kw=arguments(key);before=copy.deepcopy(ep);out=invoke(ep,kw)
    assert out['status']=='conditional_validated_later_v3_data'
    assert ep==before and out['bundle']['raw_service_ready_fields_preserved'] is True
    assert out['native_delivery_verified'] is False and out['online_information_delivered'] is False
    facts=out['bundle']['derived_goal_service_bounds'];assert len(facts)==1
    name,h=next(iter(facts.items()));assert h['deciding_owner']=='B'
    assert out['bundle']['trays'][name]['service_ready_at']==h['raw_service_ready_at']<h['derived_service_end']
    assert any(e['tray_id']==name and e['event']=='UNLOAD_START' and e['time']==h['derived_service_end'] for e in raw['result']['receipts'])
    assert entry['at']+.01<out['bundle']['trays']['L']['service_ready_at']

@pytest.mark.parametrize('key',['insufficient_advance/vector_16','insufficient_advance/vector_17'])
def test_real_unload_crossing_keeps_original_unknown(key):
    _,_,ep,kw=arguments(key);out=invoke(ep,kw)
    assert out['status']=='unknown' and out['bundle']['reasons']==['stable_observed_unloading']
    assert 'derived_goal_service_bounds' not in out.get('bundle',{})

@pytest.mark.parametrize('mutation',[
    'missing_self_history','missing_immutable_request','wrong_owner','wrong_target','wrong_request_id',
    'changed_wire','wrong_result','future_ack','equal_floor_ack','expired_history','digest',
    'generation','traversal','job','edge','prefix','source_owner','unknown_entry','future_arrival',
    'static_digest','bool_sequence','nonfinite_epoch','source_fault','duplicate_command'])
def test_historical_authority_identity_time_and_coverage_negatives(mutation):
    _,_,ep,kw=arguments('mechanism/vector_02');command=historical(ep);rid=command['request_id']
    ack=command['last_delivered_ack'];env=ack['planning_snapshot_v3'];body=env['capture'];b=body['capture_v2']['local_capture']
    f=body['extension']['source_observed_inflight'][0]
    if mutation=='missing_self_history':ep['view']['client_commands'].remove(command)
    elif mutation=='missing_immutable_request':kw['own_publication_requests'].pop(rid)
    elif mutation=='wrong_owner':kw['own_publication_requests'][rid]['owner_id']='A'
    elif mutation=='wrong_target':kw['own_publication_requests'][rid]['target_owner']='B'
    elif mutation=='wrong_request_id':kw['own_publication_requests'][rid]['request_id']='different'
    elif mutation=='changed_wire':kw['own_publication_requests'][rid]['message_delay']=.001
    elif mutation=='wrong_result':ack['result_id']='wrong'
    elif mutation=='future_ack':ack['delivered_at']=ep['view']['now']+.1
    elif mutation=='equal_floor_ack':ack['delivered_at']=ep['command']['last_delivered_ack']['executed_at']
    elif mutation=='expired_history':b['valid_until']=ep['view']['now'];kw['own_publication_requests'][rid]['expiry']=b['valid_until'];rehash(command)
    elif mutation=='digest':env['payload_sha256']='0'*64
    elif mutation=='generation':f['generation']+=1;rehash(command)
    elif mutation=='traversal':f['traversal_id']+=1;rehash(command)
    elif mutation=='job':f['business_bag_id']='loaded';rehash(command)
    elif mutation=='edge':f['edge_from']=1;rehash(command)
    elif mutation=='prefix':next(t for t in b['trays'] if t['tray_id']=='E')['committed_prefix']=[3];rehash(command)
    elif mutation=='source_owner':b['source_owner']='A';rehash(command)
    elif mutation=='unknown_entry':body['extension']['source_observed_inflight']=[];body['extension']['coverage']['unmatched_tray_ids']=['E'];rehash(command)
    elif mutation=='future_arrival':f['entered_at']+=1.;f['derived_edge_exit_at']+=1.;rehash(command)
    elif mutation=='static_digest':b['static_contract_sha256']='0'*64;rehash(command)
    elif mutation=='bool_sequence':ack['sequence']=True
    elif mutation=='nonfinite_epoch':ack['delivered_at']=float('inf')
    elif mutation=='source_fault':b['known_faults']=[{'from':3,'to':4,'active':True}]
    elif mutation=='duplicate_command':ep['view']['client_commands'].append(copy.deepcopy(command))
    out=invoke(ep,kw)
    assert out['status']=='unknown',mutation
    assert out['native_delivery_verified'] is False

@pytest.mark.parametrize('mutation',['current_owner','current_L','current_occupancy','current_pending',
                                    'current_bound','changed_public_service'])
def test_no_bypass_of_current_endpoint_and_own_action_guards(mutation):
    _,_,ep,kw=arguments('mechanism/vector_02')
    if mutation=='current_owner':ep['view']['owner_id']='A'
    elif mutation=='current_L':next(t for t in ep['view']['trays'] if t['tray_id']=='L')['generation']+=1
    elif mutation=='current_occupancy':next(n for n in ep['view']['node_contracts'] if n['node']==7)['occupancy']+=1
    elif mutation=='current_pending':
        c=next(c for c in ep['view']['client_requests'] if c['request_id'] in dict(kw['own_actions']))
        c['last_delivered_ack']={}
    elif mutation=='current_bound':
        e=ep['command']['last_delivered_ack']['planning_snapshot_v3']
        next(t for t in e['capture']['capture_v2']['local_capture']['trays'] if t['tray_id']=='L')['service_ready_at']=ep['view']['now']+.005
        e['payload_sha256']=digest.capture_digest_v3(e['capture'])
    elif mutation=='changed_public_service':
        rows=ep['view']['node_records'];i=next(i for i,r in enumerate(rows) if r[0]==4);r=list(rows[i]);r[2]=.2;rows[i]=tuple(r)
    assert invoke(ep,kw)['status']=='unknown'

def test_peer_or_saved_remote_history_cannot_replace_deciding_owner_self_ack():
    _,_,ep,kw=arguments('mechanism/vector_02');command=historical(ep)
    remote=copy.deepcopy(command['last_delivered_ack']['planning_snapshot_v3'])
    ep['view']['client_commands'].remove(command)
    ep['received'].append(remote)
    assert invoke(ep,kw)['status']=='unknown'

def test_prior_module_globals_are_unchanged():
    before=(gate.old.validate_collected_endpoints,gate.old.lifecycle.stable_stationary,gate.old.lifecycle.VERSION)
    _,_,ep,kw=arguments('mechanism/vector_02');invoke(ep,kw)
    assert before==(gate.old.validate_collected_endpoints,gate.old.lifecycle.stable_stationary,gate.old.lifecycle.VERSION)
