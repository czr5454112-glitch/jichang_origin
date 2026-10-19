"""Actual-owner initial collection seam; no selector, submit or native factory.

The capability authenticates one actual collection, not model predictions or
future protection. Saved JSON can never reconstruct it. Private Python fields
are not a security boundary against arbitrary in-process code modification.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from . import live_obligation_domain_adapter as native_gate
from . import live_obligation_historical_adapter as history
from . import live_obligation_delivered_context as supplied
from . import live_obligation_native_view_v2 as representation
from . import live_obligation_full32_suffix_partition as domain
from .planning_capture_v2_contract import PHYSICAL_KINDS

_TOKEN=object()
VERSION='g31.live_obligation.actual_initial_decision.v1'


def require(ok,reason):
    if not ok:raise ValueError('initial_decision:'+reason)


def unknown(reason,**extra):
    return {'status':'unknown','reason':reason,'native_delivery_verified':False,
        'native_protection_certified':False,'dispatch_authorized':False,**extra}


def _client_snapshot(client,session,owner):
    require(type(client) is history.fixture.LocalTransport and client.session is session,'exact_same_session_client')
    rows=history.fixture.LocalTransport.owned(client,owner)
    actual,_,diagnostic=history.client_owned_snapshot(client,session,owner,rows)
    require(not any(row['kind'] in PHYSICAL_KINDS for row in actual.values()),'initial_physical_action_already_submitted')
    # Full ordered own rows and current admission, not just publication IDs.
    data={'rows':actual,'diagnostic':diagnostic,'admission':client.context}
    encoded=history.payload_encoding(data)
    return actual,encoded


class InitialDecision:
    __slots__=('_token','_native','_session','_client','_accepted','_owner','_request_id','_at',
        '_admission','_client_bytes','_public_bytes','_ledger','_digest')

    def __init__(self,token,*,native,session,client,accepted,owner,request_id,public,ledger,client_bytes):
        require(token is _TOKEN,'actual_reads_required')
        self._token,self._native,self._session,self._client,self._accepted=token,native,session,client,accepted
        self._owner,self._request_id,self._at=owner,request_id,session.physical_time
        self._admission=client.context;self._client_bytes=client_bytes
        self._public_bytes=history.payload_encoding(public);self._digest=hashlib.sha256(self._public_bytes.encode()).hexdigest()
        self._ledger=ledger

    def audit_copy(self):
        return {'schema':VERSION,'owner':self._owner,'at':self._at,'own_publication_id':self._request_id,
            'public':json.loads(self._public_bytes),'public_sha256':self._digest,
            'native_origin':'actual_same_owner_three_endpoints_and_immutable_client_publication',
            'native_protection_certified':False,'dispatch_authorized':False,
            'saved_copy_has_authority':False}


def require_current(decision):
    require(type(decision) is InitialDecision and decision._token is _TOKEN,'initial_decision_type')
    require(native_gate._valid_handle(decision._native,decision._session,decision._accepted),'current_native_admission')
    require(decision._session.physical_time==decision._at and decision._client.context is decision._admission,
        'session_time_or_owner_admission_changed')
    _,current=_client_snapshot(decision._client,decision._session,decision._owner)
    require(current==decision._client_bytes,'own_ledger_changed')
    require(hashlib.sha256(decision._public_bytes.encode()).hexdigest()==decision._digest,'public_data_changed')
    ledger=decision._ledger
    require(type(ledger) is native_gate.previous.NativeJobLedger
        and ledger._token is native_gate.previous._LEDGER_TOKEN
        and ledger._session is decision._session and ledger._owner==decision._owner,'real_same_owner_contract_ledger')
    return decision


def collect_initial_decision(native,session,owner,publication_id,client,accepted):
    """Exactly the existing three own endpoints; no view of the other owner."""
    try:
        require(owner in ('A','B') and type(publication_id) is str and publication_id,'owner_publication_identity')
        require(native_gate._valid_handle(native,session,accepted),'active_native027_session')
        rows,before=_client_snapshot(client,session,owner)
        require(publication_id in rows and rows[publication_id]['kind']=='planning_snapshot','own_initial_publication')
        request=copy.deepcopy(rows[publication_id]['request'])
        require(request['owner_id']==owner and request['request_id']==publication_id
            and request['target_owner']==({'A':'B','B':'A'}[owner]),'immutable_request_channel')
        information,ledger=native_gate.collect_initial_ledger(native,session,owner,publication_id,accepted=accepted)
        ep=information.get('raw_endpoints',{})
        require(information.get('status')=='conditional_native_delivered_model_input'
            and information.get('native_delivery_verified') is True and set(ep)=={'view','command','received'},'actual_complete_initial_reads')
        public={'view':representation.normalized_view(ep['view']),
            'command':copy.deepcopy(ep['command']),'received':copy.deepcopy(ep['received']),'own_request':request}
        require(ep['command'].get('request_id')==publication_id and ep['command'].get('kind')=='planning_snapshot',
            'returned_command_identity')
        context=supplied.initial_context(**public)
        require(type(context) is supplied.SuppliedContext,'initial_supplied_guard')
        _,after=_client_snapshot(client,session,owner)
        require(after==before and information['native_read']['owner']==owner
            and information['native_read']['own_request_id']==publication_id
            and information['native_read']['at']==session.physical_time==public['view']['now'],
            'collection_or_admission_changed')
        result=InitialDecision(_TOKEN,native=native,session=session,client=client,accepted=accepted,owner=owner,
            request_id=publication_id,public=public,ledger=ledger,client_bytes=after)
        return require_current(result)
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as error:
        return unknown(str(error))


def supplied_snapshot(decision):
    """Fresh data validation, no native capability crosses the pure seam."""
    require_current(decision)
    result=supplied.initial_context(**json.loads(decision._public_bytes))
    require(type(result) is supplied.SuppliedContext,'initial_revalidation')
    return result


def revalidate_first_component(decision,action):
    """Recollect actual current facts, return a proposal; never submits it.

Even a successful guard is momentary. An eventual dispatcher must consume it
without an intervening activation/submission/advance and still needs actual
native ACK and edge evidence. Remote receiving permission is never granted here.
"""
    try:
        require_current(decision)
        from . import public_live_obligation_projection as construction
        actions=construction.actions();domain.partition(actions)
        require(type(action) is dict and tuple(action)==domain.FIELDS and
            any(all(domain.token(action[k])==domain.token(a[k]) for k in domain.FIELDS) for a in actions),'declared32_action')
        fresh=collect_initial_decision(decision._native,decision._session,decision._owner,decision._request_id,
            decision._client,decision._accepted)
        require(type(fresh) is InitialDecision,'fresh_owner_endpoint_guard')
        require(fresh._public_bytes==decision._public_bytes,'initial_information_changed_during_solve')
        view=json.loads(fresh._public_bytes)['view'];now=view['now'];owner=fresh._owner
        key='L' if owner=='A' else 'E';matches=[t for t in view['trays'] if t['tray_id']==key]
        require(len(matches)==1,'unique_actual_local_tray');tray=matches[0]
        require(tray['edge_to']<0 and tray['edge_from']<0,'already_committed')
        if owner=='A':
            require(tray['node']==0 and tray['mode']=='loaded' and tray['business_bag_id']=='loaded','current_loaded_source')
            if action['initial_action']=='native_default':component={'kind':'no_command_native_default','actual_next_unknown':True}
            else:
                require(tray['service_ready_known'] is True and type(tray['service_ready_at']) is float
                    and math.isfinite(tray['service_ready_at']) and now+.01<tray['service_ready_at'],'strict_actual_route_wire_window')
                target=[n for n in view['node_contracts'] if n['node']==2 and n['resource_owner']==owner]
                require(len(target)==1 and target[0]['occupancy']<target[0]['capacity'],'current_owned_receiver_capacity')
                component={'kind':'route','tray_id':'L','business_bag_id':'loaded','from':0,'next':2,
                    'expected_generation':tray['generation'],'expected_traversal':tray['traversal_id'],'expiry':5.,'message_delay':.01}
        else:
            require(tray['node']==5 and tray['mode']=='empty' and not tray['business_bag_id']
                and tray['available_at']<=now,'current_empty_source')
            component={'kind':'transfer','tray_id':'E','source':5,'destination':1,
                'earliest_departure':action['empty_departure'],'expiry':39.,'message_delay':.01}
        require_current(fresh)
        return {'status':'fresh_local_component_proposal','owner':owner,'at':now,'public_sha256':fresh._digest,
            'component':component,'native_request_submitted':False,'dispatch_authorized':False,
            'native_protection_certified':False,'requires_immediate_actual_dispatch_recheck':True,
            'future_components_nonbinding':True}
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as error:return unknown(str(error))
