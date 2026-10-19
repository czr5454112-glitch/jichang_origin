"""One-pair policy with only the observed owner-view representation repaired.

The original decide_pending bytecode still requires a real NativeCollectionAttempt
before the pure screen. No capability, timestamp or physical action is replaced.
"""
from types import FunctionType
from . import live_obligation_recollection_policy as old
from . import live_obligation_native_view_v2 as representation

adapter, bound = old.adapter, old.bound
PHYSICAL_KINDS, TERMINAL_BY_KIND = old.PHYSICAL_KINDS, old.TERMINAL_BY_KIND
PhaseReplyBudget, local_target = old.PhaseReplyBudget, old.local_target
attempt_evidence = old.attempt_evidence


def retry_admission(information, pending, view, owned_rows):
    """Supplied-data screen; live authority is still checked by the caller."""
    try:
        safe, equal = representation.equivalent_views(view, information['raw_endpoints']['view'])
        if not equal: raise ValueError('not_the_collected_current_view')
    except (KeyError, TypeError, ValueError) as error:
        return {'status':'not_admitted','reason':str(error),'native_success_certified':False}
    return old.retry_admission(information, pending, safe, owned_rows)


_namespace = dict(old.OwnerPolicy.decide_pending.__globals__)
_namespace['retry_admission'] = retry_admission
_decide = FunctionType(old.OwnerPolicy.decide_pending.__code__, _namespace,
    old.OwnerPolicy.decide_pending.__name__, old.OwnerPolicy.decide_pending.__defaults__,
    old.OwnerPolicy.decide_pending.__closure__)
_decide.__kwdefaults__ = old.OwnerPolicy.decide_pending.__kwdefaults__


class OwnerPolicy(old.OwnerPolicy):
    decide_pending = _decide
