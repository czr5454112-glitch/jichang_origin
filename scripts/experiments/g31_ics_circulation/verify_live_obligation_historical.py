"""Saved replay of the actual-client historical collector; no native authority."""
from __future__ import annotations
import copy
from types import FunctionType
from . import verify_live_obligation_recollection as base
from . import live_obligation_historical_policy as policy
from . import domain_guard_historical_service as historical
from . import live_obligation_historical_adapter as adapter

require,json_value=base.require,base.json_value

def expected_information(raw,owner,entry):
    """Reconstruct only explicitly recorded owner-local reads/call prefix."""
    info=entry['information'];ep=info['raw_endpoints'];pending=entry['collection']
    requests=base.prefix_requests(raw,owner,entry);own_id=pending['request_id']
    history=adapter.submission_history(raw['calls'][:entry['predecision_call_prefix_count']],owner,entry['at'])
    require(list(requests)==list(history),'actual_ordered_own_submission_prefix')
    require(own_id in requests and requests[own_id][0]=='planning_snapshot_v3','attempt_own_publication')
    require(entry['phase']==pending['phase'] and entry['actual_local_view']==ep['view']
            and ep['view']['owner_id']==owner and ep['view']['now']==entry['at'],'attempt_current_view')
    actual_read={'owner':owner,'own_request_id':own_id,'at':entry['at'],
        'native_binary':raw['retained_ledgers'][owner]['native_binary'],'acceptance':raw['native027_acceptance'],
        'selected_peer_message_id':pending['peer_message'],'collection_started_at':pending['at'],
        'actual_endpoints':['observe_protocol','protocol_command','protocol_planning_snapshots_v3']}
    require(info['native_read']==actual_read,'attempt_actual_read_binding')
    roots=[r for r in raw['owner_activation_admissions'] if r['owner']==owner and r['accepted_at']==entry['at']]
    require(len(roots)==1,'unique_current_owned_admission')
    publications={k:copy.deepcopy(request) for k,(kind,request) in requests.items() if kind=='planning_snapshot_v3'}
    actual_ledger={'schema':'g31.actual_owner_publication_ledger.v1','owner':owner,'at':entry['at'],
        'source':'same_session_LocalTransport_actual_owned_rows_and_submission_calls',
        'admission_root':roots[0]['root_id'],'submission_call_count':entry['predecision_call_prefix_count'],
        'own_submitted_request_ids':list(requests),'publication_request_ids':list(publications),
        'publication_requests':publications}
    actions=sorted((k,kind) for k,(kind,_) in requests.items() if kind in policy.PHYSICAL_KINDS)
    replay=historical.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],
        retained=raw['retained_ledgers'][owner],own_actions=actions,phase=entry['phase'],
        own_request_id=own_id,peer_message_id=pending['peer_message'],collection_started_at=pending['at'],
        policy_quiet_since=pending['policy_quiet_since'],own_request=requests[own_id][1],
        own_publication_requests=publications)
    known=replay['status']=='conditional_validated_later_v3_data'
    expected=json_value(replay);expected['native_read']=actual_read
    if known:expected.update(status='conditional_native_delivered_later_v3_model_input',
        native_delivery_verified=True,online_information_delivered=True,conditional_stability_only=True,
        current_state_certified=False,native_protection_certified=False)
    expected['actual_publication_ledger']=actual_ledger
    return known,requests,expected

def replay_information(raw,owner,entry):
    known,requests,expected=expected_information(raw,owner,entry)
    require(adapter.payload_encoding(entry['information'])==adapter.payload_encoding(expected),
            'complete_actual_client_history_endpoint_replay')
    return known,requests,base.owned_at_view(requests,entry['information']['raw_endpoints']['view'])

def verify_call_history(raw):
    result=base.verify_call_history(raw)
    for owner in ('A','B'):adapter.submission_history(raw['calls'],owner,40.)
    return result

_namespace={**vars(base),'policy':policy,'replay_information':replay_information,
            'verify_call_history':verify_call_history}
for _name in ('verify_terminal_receipts','prefix_requests','owned_at_view',
              'verify_attempts','verify_saved','verify_replies','verify_partial'):
    _source=getattr(base,_name)
    _function=FunctionType(_source.__code__,_namespace,_source.__name__,_source.__defaults__,_source.__closure__)
    _function.__kwdefaults__=_source.__kwdefaults__
    _namespace[_name]=globals()[_name]=_function
