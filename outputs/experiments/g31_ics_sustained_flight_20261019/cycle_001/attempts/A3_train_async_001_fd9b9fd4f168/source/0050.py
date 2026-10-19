"""Revalidated supplied owner data for a future conditional communication model.

No native object is accepted here and no dictionary is a delivery capability.
The existing endpoint/digest/identity/current-state guards are rerun. Saved
outcomes, branch IDs and the other owner's view are not arguments. An actual
online adapter must separately establish the origin of these exact arguments.
"""
from __future__ import annotations
import copy
import hashlib
import json
from . import live_obligation_domain_guard as initial
from . import domain_guard_historical_service as later
from . import live_obligation_historical_adapter as history
from . import live_obligation_native_view_v2 as representation
from .planning_capture_v2_contract import PHYSICAL_KINDS

VERSION = 'g31.live_obligation.delivered_data_context.v1'


def require(ok, why):
    if not ok: raise ValueError('delivered_context:' + why)


def encoded(value):
    # This validates an exact builtin JSON tree, finite values, cycles, keys
    # and scalar spellings before canonical serialization; no custom hooks.
    return history.payload_encoding(value)


def unknown(reason):
    return {'status':'unknown', 'reasons':[str(reason)],
            'native_delivery_verified':False, 'online_executable':False,
            'native_protection_certified':False}


class SuppliedContext:
    """Integrity envelope, explicitly NOT native session/admission authority."""
    __slots__ = ('_payload', '_digest')
    def __init__(self, payload):
        payload=copy.deepcopy(payload)
        # Only the guard's derived resources map has integer JSON keys. Raw
        # endpoint/call data above has already passed the strict string-key
        # encoder. Preserve each node identity and reject mixed/colliding keys.
        resources=payload['validated']['bundle']['resources']
        require(type(resources) is dict and all(type(k) is int and k>=0 for k in resources),
                'derived_resource_keys')
        payload['validated']['bundle']['resources']={str(k):v for k,v in resources.items()}
        self._payload = encoded(payload)
        self._digest = hashlib.sha256(self._payload.encode()).hexdigest()

    def audit_copy(self):
        return {'schema':VERSION, 'payload':json.loads(self._payload),
                'sha256':self._digest, 'native_delivery_verified':False,
                'online_executable':False, 'authority':'none_supplied_data_only'}


def initial_context(*, view, command, received, own_request):
    """One deciding owner's exact three endpoint values and immutable request."""
    try:
        safe = representation.normalized_view(view)
        encoded({'command':command, 'received':received, 'own_request':own_request})
        owner = safe['owner_id']; peer = {'A':'B','B':'A'}[owner]
        require(own_request['owner_id']==owner and own_request['target_owner']==peer
                and own_request['kind']=='planning_snapshot'
                and command['kind']=='planning_snapshot'
                and command['request_id']==own_request['request_id'], 'initial_request_endpoint')
        validated = initial.validate_pair(safe, command.get('last_delivered_ack',{}), received)
        require(validated['status']=='conditional_validated_data',
                'initial_guard:' + str(validated.get('reasons')))
        require(safe['now']==.11, 'initial_epoch')
        # Retain actual capture epochs. The projected .11 state is clearly
        # distinct from those source events; no synthetic capture is minted.
        payload = {'phase':'initial', 'owner':owner, 'at':safe['now'],
            'evidence':{'view':safe,'command':copy.deepcopy(command),
                        'received':copy.deepcopy(received),'own_request':copy.deepcopy(own_request)},
            'validated':validated}
        return SuppliedContext(payload)
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        return unknown(exc)


def later_context(*, view, command, received, retained, own_calls, phase,
                  own_request_id, peer_message_id, collection_started_at,
                  policy_quiet_since):
    """Historical/unloading data gate; no completion is inferred from a timer.

`own_calls` must contain only this owner's actual immutable submission prefix.
The actual adapter must bind it to its exact LocalTransport/session/admission.
This function merely verifies supplied records and never grants that binding.
"""
    try:
        safe = representation.normalized_view(view); owner = safe['owner_id']
        encoded({'command':command,'received':received,'retained':retained,'own_calls':own_calls})
        require(type(own_calls) is list and all(c['request']['owner_id']==owner for c in own_calls),
                'foreign_submission_prefix')
        submitted = history.submission_history(own_calls, owner, safe['now'])
        requests = {key:(kind,json.loads(payload)) for key,(kind,payload) in submitted.items()}
        require(own_request_id in requests and requests[own_request_id][0]=='planning_snapshot_v3',
                'own_publication_not_submitted')
        publications = {key:payload for key,(kind,payload) in requests.items() if kind=='planning_snapshot_v3'}
        actions = sorted((key,kind) for key,(kind,_) in requests.items() if kind in PHYSICAL_KINDS)
        args = dict(retained=copy.deepcopy(retained), own_actions=actions, phase=phase,
            own_request_id=own_request_id,peer_message_id=peer_message_id,
            collection_started_at=collection_started_at,policy_quiet_since=policy_quiet_since,
            own_request=requests[own_request_id][1],own_publication_requests=publications)
        validated = later.validate_collected_endpoints(safe, command, received, **args)
        require(validated['status']=='conditional_validated_later_v3_data',
                'later_guard:' + str(validated.get('reasons')) + ':' + str(validated.get('bundle',{}).get('reasons')))
        return SuppliedContext({'phase':phase,'owner':owner,'at':safe['now'],
            'evidence':{'view':safe,'command':copy.deepcopy(command),'received':copy.deepcopy(received),
                'retained':copy.deepcopy(retained),'own_calls':copy.deepcopy(own_calls),
                'phase':phase,'own_request_id':own_request_id,'peer_message_id':peer_message_id,
                'collection_started_at':collection_started_at,'policy_quiet_since':policy_quiet_since},
            'validated':validated})
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        return unknown(exc)


def revalidate(context):
    """Reject forged/mutated labels and re-execute every supplied-data guard."""
    if type(context) is not SuppliedContext: return unknown('context_type')
    try:
        require(hashlib.sha256(context._payload.encode()).hexdigest()==context._digest,'context_bytes_changed')
        payload = json.loads(context._payload)
        rebuilt = (initial_context(**payload['evidence']) if payload['phase']=='initial'
                   else later_context(**payload['evidence']))
        require(type(rebuilt) is SuppliedContext and rebuilt._payload==context._payload,
                'context_revalidation_changed')
        return copy.deepcopy(payload['validated'])
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        return unknown(exc)


def initial_projection_bundle(context):
    result = revalidate(context)
    if result.get('status')!='conditional_validated_data': return unknown('initial_context_required')
    bundle = copy.deepcopy(result['bundle'])
    bundle['resources']={int(k):v for k,v in bundle['resources'].items()}
    bundle.update(model_version=VERSION, protocol=copy.deepcopy(initial.construction.PROTOCOL),
        owner_pending_tray_requests=[], online_information_delivered=False,
        assumptions=['Supplied actual initial endpoint data passed all guards; native origin not certified here.',
          'Future physics and message delivery are conditional projections, not observed facts.'])
    # A loading tray's actual capture carries the known completion epoch.
    bundle['trays']['P']['load_end']=bundle['trays']['P']['load_complete_at']
    return bundle
