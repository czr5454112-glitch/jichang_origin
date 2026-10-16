"""New public-model policy boundary; immutable old native collectors reused.

No saved native result, case-index outcome table or native fork is read here.
Initial facts come directly from the actual accepted owner's native collector.
Later choice requires that collector's live session-bound sealed object.
"""
from __future__ import annotations
from . import native_preexisting_v3_bound_adapter as adapter
from . import public_native_preference_search as search
from .public_owned_action_state import bind_supplied_bundle

METHODS=('incumbent',*(f'fixed_window_{i}' for i in range(4)),*search.METHODS,'pair_repair_later_default')


def method_parameters(method, *, later=False):
    if method not in METHODS:raise ValueError('online_preference:unsupported_method')
    if method.startswith('fixed_window_'):
        return {'method':'resource_pair_repair'} if later else {'method':'fixed_initial_window','fixed_window':int(method[-1])}
    if method=='pair_repair_later_default':
        return {'method':'resource_pair_repair','later_default_only':True}
    return {'method':method}


def initial(native,session,owner,planning_id,accepted,method):
    # This actual native call creates the session/owner-bound retained ledger;
    # no caller-supplied dictionary can stand in for this read operation.
    information,ledger=adapter.collect_initial_ledger(native,session,owner,planning_id,accepted=accepted)
    if (ledger is None or not information.get('native_delivery_verified')
            or ledger._session is not session or ledger._owner!=owner):
        return information,ledger,{'status':'unknown_unverified_initial_input','selected_action':None}
    proposal=search.initial_proposal(information['bundle'],**method_parameters(method))
    return information,ledger,proposal


def later(information,method):
    if (not adapter.is_native_collected(information)
            or information.get('status')!='conditional_native_delivered_later_v3_model_input'
            or information.get('native_delivery_verified') is not True):
        return {'status':'unknown_unverified_or_unsupported_input','selected_action':None}
    try:
        bundle=bind_supplied_bundle(information['bundle'],information['raw_endpoints']['view'])
        result=search.later_proposal(bundle,**method_parameters(method,later=True))
        result['current_owned_action_facts']=bundle['owner_current_action_facts']
        return result
    except (ValueError,KeyError,TypeError,AttributeError):
        return {'status':'unknown_current_owned_action_scope','selected_action':None}
