"""Restricted receiver-only optimistic bound, before the event simulation.

This composes the frozen ProtectionRequestContext without editing it. Existing
input/action guards and per-action constructor still run. The complete baseline
runs normally, then a candidate can be rejected only by a strict lower bound.
It is a supplied-data model statement, not a native or online certificate.

The unique-carrier premise depends on the ENTIRE pinned original input guard
and continuation, not just receiver_bound's redundant local checks. At .11 L
is already loaded: any visit to node1 precedes its destination unloading, so
it cannot load receiver there. Its only post-completion supply is 6->7, and
all subsequent reuse paths remain in {7,3,8,4,6}, which cannot reach node1.
P is already loading blocker at1 and ends at sink9; the frozen continuation
never publishes a P return. E is therefore the sole possible receiver tray,
and receiver is the sole waiting job at1. Changed graph, services, permission,
carrier/job identity, snapshot age, pending action or continuation is outside
the pinned guard domain and cannot acquire this proof by passing the small
redundant checks alone. No claim is made for arbitrary future owner policies.
"""
from __future__ import annotations
import copy
import hashlib
import heapq
import math
from pathlib import Path
from types import FunctionType, SimpleNamespace
from . import public_preference_protection_request_context as combined

EXPECTED_COMBINED='d517656ee8a043ada499c13c9ac16c46d3c1f0d1f2f6741ee937e834b16c03e0'
VERSION='public_preference_receiver_optimistic_bound_v1'


class _LowerBoundRejected(Exception):
    def __init__(self,witness):self.witness=witness


def _number(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def _arrival(projection,source,goal,at):
    """Earliest floating label, not start plus a pre-summed distance.

Every forward addition is exactly t + the same per-edge float used by run.
Round-to-nearest addition is monotone on this finite nonnegative domain.
Deleting nonnegative waits/services cannot make this label later than the
corresponding actual path. Minimum over all positive-capacity paths preserves
that direction. No preference is treated as a forced edge.
"""
    queue=[(at,source,(source,))];best={source:at}
    while queue:
        value,node,path=heapq.heappop(queue)
        if value!=best[node]:continue
        if node==goal:return value,list(path)
        for target in projection.outgoing[node]:
            edge=(node,target)
            if projection.edges[edge]['capacity']<=0:continue
            travel=projection.travel[edge]
            if not _number(travel) or travel<=0:return None
            arrival=value+travel
            if not _number(arrival):return None
            if arrival<best.get(target,math.inf):
                best[target]=arrival;heapq.heappush(queue,(arrival,target,path+(target,)))
    return None


def receiver_bound(projection,baseline):
    """Only called after the pinned complete initial/action guards succeed."""
    if (type(baseline) is not dict or set(baseline)!=combined.proof.original.contract.JOBS
            or not all(_number(v) for v in baseline.values())):return None
    job=projection.jobs['receiver'];now=projection.b['now']
    # These checks deliberately duplicate only the small authority facts used
    # by the proof; they never replace the full original initial guard.
    if (now!=.11 or projection.time!=now or set(projection.trays)!={'L','E','P'}
            or projection.trays['E']['node']!=5 or projection.trays['E']['mode']!='empty'
            or projection.trays['L']['node']!=0 or projection.trays['L']['mode']!='loaded'
            or projection.trays['L']['job']!='loaded' or projection.trays['P']['node']!=1
            or projection.trays['P']['mode']!='loading' or projection.trays['P']['job']!='blocker'
            or job['origin']!=1 or job['destination']!=4 or job['status']!='waiting_for_tray'
            or projection.jobs['blocker']['destination']!=9 or projection.outgoing[9]
            or projection.b.get('owner_pending_tray_requests',[])!=[]):return None
    wire=projection.b['contract']['protocol']['message_delay']
    if wire!=.01:return None
    earliest=projection.action['empty_departure']
    if not all(_number(v) for v in (earliest,job['load_seconds'],job['unload_seconds'])):return None
    wire_at=now+wire;grant_at=max(wire_at,earliest)
    incoming=_arrival(projection,5,job['origin'],grant_at)
    if incoming is None:return None
    load_end=incoming[0]+job['load_seconds']
    outgoing=_arrival(projection,job['origin'],job['destination'],load_end)
    if outgoing is None:return None
    lower=outgoing[0]+job['unload_seconds']
    if not _number(lower):return None
    return {'job':'receiver','completion_lower_bound':lower,'baseline_completed_at':baseline['receiver'],
        'wire_delivery_lower_bound':wire_at,'grant_lower_bound':grant_at,
        'empty_arrival_lower_bound':incoming[0],'load_completion_lower_bound':load_end,
        'destination_arrival_lower_bound':outgoing[0],'positive_capacity_paths':{'empty':incoming[1],'loaded':outgoing[1]},
        'comparison':'strict >; no tolerance',
        'float_rule':'Forward t + travel labels; same per-edge floats/addition order, no collapsed distance sum.',
        'relaxed_nonnegative_terms':['all node service','berth/edge capacity waiting','headway/calendar/queue waiting','rejections/retries and further control delay'],
        'authority_scope':'Pinned .11 initial 3tray/5job continuation: E sole possible receiver carrier; not an arbitrary future-policy or native availability proof.'}


class ReceiverBoundRequestContext(combined.ProtectionRequestContext):
    __slots__=('__early_count','__baseline_action','__fingerprint')
    def __init__(self,bundle):
        if hashlib.sha256(Path(combined.__file__).read_bytes()).hexdigest()!=EXPECTED_COMBINED:
            raise ValueError('receiver_bound:unreviewed_combination_source')
        def run(projection):
            ledger=projection.completed
            # The baseline's plain completed dict bypasses the bound. A ledger
            # exists only after the frozen context has its own full baseline.
            if type(ledger) is combined.proof._CompletionLedger:
                witness=receiver_bound(projection,ledger._baseline)
                if witness is not None and witness['completion_lower_bound']>witness['baseline_completed_at']:
                    raise _LowerBoundRejected(witness)
            return combined.proof._RUN(projection)
        facade=SimpleNamespace(**{**vars(combined.proof),'_RUN':run})
        constructor=combined.ProtectionRequestContext.__init__
        initialize=FunctionType(constructor.__code__,{**constructor.__globals__,'proof':facade},
            constructor.__name__,constructor.__defaults__,constructor.__closure__)
        initialize.__kwdefaults__=copy.deepcopy(constructor.__kwdefaults__)
        initialize(self,bundle)
        self.__early_count=0
        actions=self.actions();self.__baseline_action=actions[0] if actions else {}
        self.__fingerprint=combined.base.RequestContext.describe(self)['supplied_snapshot_sha256']

    def predict(self,action):
        try:return super().predict(action)
        except _LowerBoundRejected as rejected:
            self.__early_count+=1
            return {'status':'conditional_protection_rejected_lower_bound','completion':{},'completion_sum':None,
                'witness':copy.deepcopy(rejected.witness),'supplied_snapshot_sha256':self.__fingerprint,
                'baseline_action':copy.deepcopy(self.__baseline_action),'baseline_completion':self.baseline()['completion'],
                'full_candidate_prediction':False,'suffix_status':'unknown_unexecuted',
                'native_protection_certified':False,'native_execution_certified':False,
                'online_information_delivered':False,'complete_100ms_certified':False}

    def describe(self):
        value=super().describe();value['version']=VERSION
        value['counts']['candidate_lower_bound_rejections']=self.__early_count
        value['early_bound']='Receiver only after original full input/action guards and original dynamic constructor; same-input baseline computed normally.'
        return value
