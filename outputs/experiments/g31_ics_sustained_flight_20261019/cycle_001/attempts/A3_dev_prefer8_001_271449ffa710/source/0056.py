"""Source/pure-tested adapter for retained own-publication history.

Uses the actual finite-fixture LocalTransport, not a supplied JSON outbox. The
three original owner endpoints and original session/time/content capability seal
remain in force. No peer view, result, checkpoint, model or native fork is read.
Actual native acceptance of this new integration remains unexecuted.
"""
from __future__ import annotations
import copy
import json
import math
from types import FunctionType
from . import live_obligation_domain_adapter as endpoint
from . import live_obligation_recollection_adapter as sealed
from . import domain_guard_historical_service as guard
from . import research_native_preexisting_v3_bound as fixture

bind_native027=sealed.bind_native027
collect_initial_ledger=sealed.collect_initial_ledger
json_data=sealed.json_data
is_native_attempt=sealed.is_native_attempt
is_native_collected=sealed.is_native_collected


def require(value,reason):
    if not value:raise ValueError('historical_adapter:'+reason)


def payload_encoding(request):
    require(type(request) is dict,'immutable_request_object')
    active=set()
    def check(value):
        kind=type(value)
        if value is None or kind in (str,bool,int):return
        if kind is float:
            require(math.isfinite(value),'nonfinite_public_payload');return
        require(kind in (dict,list),'unsupported_public_payload_type')
        require(id(value) not in active,'cyclic_public_payload');active.add(id(value))
        if kind is dict:
            require(all(type(k) is str for k in value),'public_payload_key')
            for item in value.values():check(item)
        else:
            for item in value:check(item)
        active.remove(id(value))
    check(request)
    # JSON scalar spelling retains bool/int/float distinctions and signed zero;
    # these public command payloads contain no authority-bearing attributes.
    return json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False)


def submission_history(calls,owner,now):
    """Lossless data validation only; cannot mint an origin capability."""
    require(type(calls) is list and owner in ('A','B'),'submission_scope')
    history={};first=set();previous=-1.
    for call in calls:
        require(type(call) is dict and type(call.get('request')) is dict,'actual_call_shape')
        request=call['request']
        if request['owner_id']!=owner:continue
        at=call['at'];key=request['request_id']
        require(type(at) in (int,float) and math.isfinite(at) and 0<=at<=now and previous<=at,
                'actual_own_call_chronology')
        previous=at
        require(type(key) is str and key and type(call['retry']) is bool
                and type(call['kind']) is str,'actual_call_identity')
        encoded=payload_encoding(request)
        require(key not in history or history[key]==(call['kind'],encoded),'immutable_retry_payload_changed')
        if not call['retry']:
            require(key not in first,'duplicate_first_submission');first.add(key)
        else:require(key in first,'retry_without_actual_first_submission')
        history[key]=(call['kind'],encoded)
    require(set(history)==first,'complete_first_submission_history')
    return history


def client_owned_snapshot(client,session,owner,provided_rows):
    """Extract only the current admitting owner's actual immutable client rows.

This function alone grants no native authority. `collect_native` first checks
the active accepted native handle; the native wrapper seals only actual reads.
The closed client type excludes an overriding owned()/send() implementation.
"""
    require(type(client) is fixture.LocalTransport and client.session is session,
            'actual_same_session_local_transport_required')
    now=session.physical_time
    require(type(now) in (int,float) and math.isfinite(now) and now>=0,'actual_collection_clock')
    require(type(client.context) is dict and client.context.get('owner')==owner
            and type(client.context.get('root_id')) is str and client.context['root_id']
            and type(client.roots) is list and client.roots and client.roots[-1] is client.context
            and type(client.context.get('accepted_at')) in (int,float)
            and client.context['accepted_at']==now,
            'current_owned_admission_required')
    require(type(client.rows) is dict and type(client.calls) is list,'actual_client_storage_shape')
    actual=fixture.LocalTransport.owned(client,owner)
    require(type(provided_rows) is dict and set(provided_rows)==set(actual)
            and all(provided_rows[k] is actual[k] for k in actual),'actual_owned_row_alias_required')
    history=submission_history(client.calls,owner,now)
    require(list(history)==list(actual),'complete_actual_owned_submission_ledger')
    for key,row in actual.items():
        require(type(row) is dict and row['request']['owner_id']==owner
                and row['request']['request_id']==key
                and history[key]==(row['kind'],payload_encoding(row['request'])),'owned_payload_differs_from_actual_submission')
    publications={key:copy.deepcopy(row['request']) for key,row in actual.items()
                  if row['kind']=='planning_snapshot_v3'}
    return actual,publications,{'schema':'g31.actual_owner_publication_ledger.v1',
        'owner':owner,'at':now,'source':'same_session_LocalTransport_actual_owned_rows_and_submission_calls',
        'admission_root':client.context['root_id'],'submission_call_count':len(client.calls),
        'own_submitted_request_ids':list(actual),'publication_request_ids':list(publications),
        'publication_requests':copy.deepcopy(publications)}


def collect_native(native,session,owner,own_request_id,*,client,accepted,ledger,
                   owned_client_rows,phase,peer_message_id,collection_started_at,policy_quiet_since):
    if not endpoint._valid_handle(native,session,accepted):
        return endpoint.unknown('missing_session_bound_native027_acceptance')
    try:
        rows,publications,ledger_read=client_owned_snapshot(client,session,owner,owned_client_rows)
    except (KeyError,TypeError,ValueError,AttributeError) as error:
        return endpoint.unknown('invalid_actual_owner_publication_client',error=str(error))
    def validate(view,command,returned,**kwargs):
        return guard.validate_collected_endpoints(view,command,returned,
            own_publication_requests=publications,**kwargs)
    namespace=dict(vars(endpoint));namespace['validate_collected_endpoints']=validate
    collect=FunctionType(endpoint.collect_native.__code__,namespace,endpoint.collect_native.__name__,
                         endpoint.collect_native.__defaults__,endpoint.collect_native.__closure__)
    collect.__kwdefaults__=endpoint.collect_native.__kwdefaults__
    result=collect(native,session,owner,own_request_id,accepted=accepted,ledger=ledger,
        owned_client_rows=rows,phase=phase,peer_message_id=peer_message_id,
        collection_started_at=collection_started_at,policy_quiet_since=policy_quiet_since)
    # No physics/admission occurs in collection. Recheck the actual client and
    # original native origin before attaching audit data and sealing the result.
    try:
        _,after,after_read=client_owned_snapshot(client,session,owner,owned_client_rows)
        require(payload_encoding(publications)==payload_encoding(after)
            and payload_encoding(ledger_read)==payload_encoding(after_read),'client_changed_during_collection')
        read=result.get('native_read',{})
        require(endpoint._valid_handle(native,session,accepted)
            and read.get('owner')==owner and read.get('own_request_id')==own_request_id
            and read.get('at')==session.physical_time==ledger_read['at']
            and read.get('actual_endpoints')==['observe_protocol','protocol_command','protocol_planning_snapshots_v3']
            and set(result.get('raw_endpoints',{}))=={'view','command','received'},
            'actual_same_owner_endpoint_origin_required')
    except (KeyError,TypeError,ValueError,AttributeError) as error:
        return endpoint.unknown('actual_owner_collection_changed_or_incomplete',error=str(error),
            partial_information=sealed.json_data(result),actual_publication_ledger=ledger_read)
    data=sealed.json_data(result)
    data['actual_publication_ledger']=ledger_read
    return sealed.NativeCollectionAttempt(sealed._ATTEMPT_TOKEN,data,accepted)


class OwnerCollectionAdapter:
    """Per-policy private namespace adapter; never installed in old globals."""
    json_data=staticmethod(json_data)
    is_native_attempt=staticmethod(is_native_attempt)
    is_native_collected=staticmethod(is_native_collected)

    def __init__(self,client,session,owner):
        self._client,self._session,self._owner=client,session,owner

    def collect_native(self,native,session,owner,own_request_id,**kwargs):
        if session is not self._session or owner!=self._owner:
            return endpoint.unknown('wrong_bound_owner_collection_adapter')
        return collect_native(native,session,owner,own_request_id,client=self._client,**kwargs)
