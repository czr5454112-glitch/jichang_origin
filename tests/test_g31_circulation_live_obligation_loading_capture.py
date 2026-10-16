"""Regression on immutable native003 data; no native session or predictor run."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_native_guard as guard
from scripts.experiments.g31_ics_circulation.planning_capture_v2_contract import PHYSICAL_KINDS

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_native_probe_prepare_003/mechanism'
RAW_SHA={12:'7704f483f64fc2748fa97bc59b034ec650d8eb71d7958ab3f0307ccd34091393',
         24:'6eece5a21268d8276015ed6ccef469603d162b15246a4a547b616c7ae4b215bb',
         25:'46104c4b7286f7e0fb7a617ee24555e12a4a55af91176a44c48e129fb639afa0'}

def saved_revalidation(vector):
    data=(DIRECTORY/f'vector_{vector:02}.json.gz').read_bytes()
    assert hashlib.sha256(data).hexdigest()==RAW_SHA[vector]
    raw=json.loads(gzip.decompress(data));decision=raw['decisions']['A'][0]
    info=decision['information'];endpoint=info['raw_endpoints'];observed=info['native_read']
    calls=raw['calls'][:decision['predecision_call_prefix_count']]
    physical={c['request']['request_id']:c['kind'] for c in calls if c['request']['owner_id']=='A' and c['kind'] in PHYSICAL_KINDS}
    own=[c['request'] for c in calls if c['request']['request_id']==observed['own_request_id']]
    assert own and all(p==own[0] for p in own)
    result=guard.validate_collected_endpoints(endpoint['view'],endpoint['command'],endpoint['received'],
        retained=raw['retained_ledgers']['A'],own_actions=sorted(physical.items()),phase=decision['phase'],
        own_request_id=observed['own_request_id'],peer_message_id=observed['selected_peer_message_id'],
        collection_started_at=observed['collection_started_at'],policy_quiet_since=observed['collection_started_at'],own_request=own[0])
    # This is corrected pure data interpretation only. Preserve native003's
    # actual old unknown/fallback and never mint an online authority token.
    assert info['status']=='unknown' and decision['fallback_used'] is True
    return result

@pytest.mark.parametrize('vector',[12,24,25])
def test_actual_native_loading_capture_fields_pass_new_typed_data_gate(vector):
    result=saved_revalidation(vector)
    assert result['status']=='conditional_validated_later_v3_data',result
    bundle=result['bundle'];t=bundle['trays']['E'];floor=min(r['captured_at'] for r in bundle['source_records'])
    assert floor<bundle['now']<t['available_at']==t['service_ready_at']==t['load_complete_at']
    assert t['ready_kind']=='observed_load_completion' and t['service_ready_known'] is True
    assert bundle['online_information_delivered'] is False
    assert bundle['native_protection_certified'] is False

def actual_bundle_arguments():
    bundle=copy.deepcopy(saved_revalidation(25)['bundle']);floor=min(r['captured_at'] for r in bundle['source_records'])
    return dict(contract=guard.supported_contract(later=True),jobs=bundle['jobs'],trays=bundle['trays'],resources=bundle['resources'],
        now=bundle['now'],phase='first_return',source_records=bundle['source_records'],terminal_receipts=bundle['terminal_receipts'],
        owner_pending_tray_requests=[],entry_receipts=[],collection_contract={'schema':'g31.conditional_collection_quiescence.v1',
            'physical_admissions_quiesced_from':floor,'through':bundle['now'],'future_python_actions_certified_by_native':False})

@pytest.mark.parametrize('change',['wrong_kind','mismatch_available','mismatch_load','unknown_bound','future_start','equal_now',
    'future_L','future_P','future_other_E_mode','bool_available','wrong_loading_node','unknown_service','pending_action'])
def test_future_availability_is_not_generally_allowed(change):
    value=actual_bundle_arguments();e=value['trays']['E'];now=value['now']
    if change=='wrong_kind':e['ready_kind']='empty_available_at'
    elif change=='mismatch_available':e['available_at']+=.001
    elif change=='mismatch_load':e['load_complete_at']+=.001
    elif change=='unknown_bound':e['load_complete_at']=-1.
    elif change=='future_start':
        finish=now+value['jobs']['receiver']['load_seconds']+.1
        e.update(available_at=finish,service_ready_at=finish,load_complete_at=finish)
    elif change=='equal_now':e.update(available_at=now,service_ready_at=now,load_complete_at=now)
    elif change=='future_L':value['trays']['L']['available_at']=now+.1
    elif change=='future_P':value['trays']['P']['available_at']=now+.1
    elif change=='future_other_E_mode':e['mode']='empty'
    elif change=='bool_available':e['available_at']=True
    elif change=='wrong_loading_node':e['node']=0
    elif change=='unknown_service':e['service_ready_known']=False
    elif change=='pending_action':value['owner_pending_tray_requests']=['unresolved-current']
    assert guard.later_bundle(**value)['status']=='unknown',change
