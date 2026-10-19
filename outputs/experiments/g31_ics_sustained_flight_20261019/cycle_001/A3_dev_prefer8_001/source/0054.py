"""Finite policy: identical choices/reply budget, richer lawful history.

Only the per-owner collector namespace changes. An initially supported pair can
avoid the old recollection, so fresh native outcomes are required. No old result
table is read. Pure gates do not certify future native outcomes.
"""
from types import FunctionType
from . import live_obligation_recollection_policy_v2 as old
from . import live_obligation_historical_adapter as adapter

bound=old.bound
PHYSICAL_KINDS,TERMINAL_BY_KIND=old.PHYSICAL_KINDS,old.TERMINAL_BY_KIND
PhaseReplyBudget,local_target=old.PhaseReplyBudget,old.local_target
retry_admission,attempt_evidence=old.retry_admission,old.attempt_evidence


def clone(function,namespace):
    out=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    out.__kwdefaults__=function.__kwdefaults__
    return out


class OwnerPolicy(old.OwnerPolicy):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        owner_adapter=adapter.OwnerCollectionAdapter(self.client,self.session,self.owner)
        namespace=dict(old.OwnerPolicy.decide_pending.__globals__)
        namespace['adapter']=owner_adapter
        namespace['fixed_choice']=clone(old.old.fixed_choice,{**old.old.fixed_choice.__globals__,'adapter':owner_adapter})
        decision=clone(old.OwnerPolicy.decide_pending,namespace)
        self.decide_pending=decision.__get__(self,type(self))
