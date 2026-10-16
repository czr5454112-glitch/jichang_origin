"""One fresh complete root evidence tree and encoding; no live installation.

All events/endpoints and the original strict artifact roundtrip remain charged.
Only this call owns its fresh value/ledger, so returning them needs no second
deepcopy. No observation, scheduler, predictor or native authority changes.
"""
from __future__ import annotations
import hashlib
import math
import time
from types import FunctionType
from . import initial_owner_route_campaign_v3 as old

image,normalization,contract=old.image,old.normalization,old.contract
SCHEMA='g31.single_root_evidence.v1'


def exact_tree(a,b):
    """Ordered builtin equality, including integer/float and signed-zero types."""
    pending=[(a,b)]
    while pending:
        left,right=pending.pop()
        kind=type(left)
        if type(right) is not kind:return False
        if kind is dict:
            if any(type(k) is not str for k in left) or list(left)!=list(right):return False
            pending.extend((value,right[key]) for key,value in left.items())
        elif kind is list:
            if len(left)!=len(right):return False
            pending.extend(zip(left,right))
        elif kind is float:
            if not math.isfinite(left) or left.hex()!=right.hex():return False
        elif kind in (str,int,bool,type(None)):
            if left!=right:return False
        else:return False
    return True


def evidence(self):
    raw={'schema':contract.SCHEMA,'root_id':self.request_id,'state':self.state,
        'owner':'A','root_started_ns':self.started_ns,'root_deadline_ns':self.deadline_ns,
        'decision_cutoff_ns':self.cutoff_ns,'choice':self.choice,'command_id':self.command_id,
        'hop':self.hop,'events':self.events,
        'participation_contract_sha256':contract.contract_sha256(),
        'complete_100ms_certified':False,'full_business_protection_certified':False,
        'scope':('Actual finite initial-A first-hop evidence; future fixed continuation '
            'and full-H outcome are separate. No full32, protection or universal100ms certificate.'),
        'initial_endpoint_records':{'A':self.initial_endpoint_records,'B':self.B_endpoint_records}}
    result=normalization.normalize(raw)
    encoded=image.artifact_encode(result)
    finished=time.perf_counter_ns()
    return {'evidence':result,'encoded':encoded,'body_finished_ns':finished,
            'body_elapsed_ns':finished-self.started_ns,'outside_return_tail_required':True}


class SingleEvidenceRequest(old.CapturedRequest):
    evidence=evidence


def finish_root(root):
    start=time.perf_counter_ns()
    old.require(root.evidence.__func__.__code__ is evidence.__code__,'single_evidence_method_not_owned')
    value=root.evidence()
    encoded=value.pop('encoded')
    decoded=image.artifact_decode(encoded)
    old.require(exact_tree(decoded,value['evidence']),'root_codec_roundtrip_order_or_type')
    ledger={'root_id':root.request_id,'evidence_sha256':hashlib.sha256(encoded).hexdigest(),
            'bytes':len(encoded),'state':root.state,'choice':root.choice}
    return {'value':value,'ledger':ledger,
            'return_codec':image.artifact_encode(ledger).decode('utf8'),
            'finalization_started_ns':start}


# Identical original publication/append/outside-return and closed-status logic.
# A private namespace is used; no imported module globals are changed.
publish_root=FunctionType(old.base.publish_root.__code__,globals(),
    old.base.publish_root.__name__,old.base.publish_root.__defaults__,old.base.publish_root.__closure__)
