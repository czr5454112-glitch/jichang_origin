"""Original validator, with only its digest global privately substituted.

The actual C try and its classification are inside B's measured validator.
Only NotImplemented invokes the original writer once; resource failures escape.
Every ordinary original rejection and the original expiry order are retained.
"""
from __future__ import annotations
import hashlib
import struct
import time
from types import FunctionType
from . import delivered_peer_cost_probe as original
from . import planning_capture_v2_c_encoder as encoder

require=original.require


class UnsafeExceptionEvidence(RuntimeError):
    """Failure to represent rejection evidence is unknown, never a rejection."""


def exception_args(values):
    """Hook-free exact representation. Unrepresentable/aliased graphs fail.

    Integer hex and float bits preserve types and values without JSON number
    coercion. This is diagnostic exception data, not capture normalization.
    """
    seen=set();count=0
    def visit(value,depth):
        nonlocal count
        count+=1
        if depth>64 or count>10000:raise UnsafeExceptionEvidence('exception_args_limit')
        kind=type(value)
        if kind is str:return {'type':'str','value':value}
        if kind is bytes:return {'type':'bytes','hex':value.hex()}
        if kind is bool:return {'type':'bool','value':value}
        if kind is int:return {'type':'int','hex':hex(value)}
        if kind is float:return {'type':'float64','hex':struct.pack('>d',value).hex()}
        if value is None:return {'type':'none'}
        if not (kind is tuple or kind is list or kind is dict):raise UnsafeExceptionEvidence('exception_args_custom')
        if id(value) in seen:raise UnsafeExceptionEvidence('exception_args_alias_or_cycle')
        seen.add(id(value))
        if kind is dict:return {'type':'dict','items':[[visit(k,depth+1),visit(v,depth+1)] for k,v in value.items()]}
        return {'type':'tuple' if kind is tuple else 'list','items':[visit(v,depth+1) for v in value]}
    if type(values) is not tuple:raise UnsafeExceptionEvidence('exception_args_not_tuple')
    return visit(values,0)


_EXACT_ERRORS=(ValueError,KeyError,TypeError,MemoryError,RecursionError,RuntimeError,
               OverflowError,OSError,FileNotFoundError,TimeoutError,KeyboardInterrupt,SystemExit)


def error_evidence(exc):
    kind=type(exc)
    if not any(kind is c for c in _EXACT_ERRORS):
        return {'exception_type':'non_exact_builtin_exception','exception_text':'unknown: exception representation not inspected',
                'exception_args_verified':False}
    try:args=exception_args(exc.args)
    except (UnsafeExceptionEvidence,MemoryError,RecursionError):
        return {'exception_type':kind.__name__,'exception_text':'unknown: exception arguments not safely representable',
                'exception_args_verified':False}
    try:message=str(exc)
    except (ValueError,MemoryError,RecursionError):
        return {'exception_type':kind.__name__,'exception_text':'unknown: builtin exception rendering failed',
                'exception_args_verified':False}
    return {'exception_type':kind.__name__,'exception_text':message,'exception_args':args,'exception_args_verified':True}


def invoke(function,args):
    try:value=function(*args)
    except (ValueError,KeyError,TypeError) as exc:
        evidence=error_evidence(exc)
        if evidence['exception_args_verified'] is not True:
            raise UnsafeExceptionEvidence('ordinary_rejection_args_unknown') from exc
        return {'status':'rejected',**evidence}
    if value is None:return {'status':'absent'}
    require(len(args[0])==1 and value is args[0][0],'unexpected_original_return_identity')
    return {'status':'accepted','envelope':value}


def private_validator(digest):
    old=original._VALIDATOR
    namespace={**old.__globals__,'capture_digest_v2':digest}
    result=FunctionType(old.__code__,namespace,old.__name__,old.__defaults__,old.__closure__)
    result.__kwdefaults__=old.__kwdefaults__
    require(set(namespace)==set(old.__globals__) and all(namespace[k] is v
        for k,v in old.__globals__.items() if k!='capture_digest_v2'),'private_digest_only')
    return result


class DigestRecord:
    """No tree copies or preflight. Each C result is classified at that call."""
    def __init__(self,try_bytes,verify):
        self.try_bytes,self.verify=try_bytes,verify
        self.events=[]

    def __call__(self,body):
        row={'ordinal':len(self.events),'classification':'entered','returned':False}
        self.events.append(row)
        try:
            self.verify()
            def attempt(value):
                require(value is body,'same_body')
                data=self.try_bytes(value)
                row['classification']='original_fallback' if data is NotImplemented else 'direct_C_bytes'
                return data
            # This is the original reviewed dispatcher, not an imitation of
            # its fallback rules. In particular, exceptions never cause retry.
            result=encoder._digest(attempt,body)
            row['returned']=True;row['sha256']=result
            return result
        except BaseException as exc:
            row['error']=error_evidence(exc)
            raise


def bound(candidate):
    require(type(candidate) is encoder.Candidate,'verified_Candidate_required')
    record=DigestRecord(candidate._try,candidate._verify)
    return private_validator(record),record


def source_proof():
    original.source_proof();encoder.source_proof()
    sentinel=object();function=private_validator(sentinel)
    return {'original_validator_code':function.__code__ is original._VALIDATOR.__code__,
        'original_defaults_closure_preserved':function.__defaults__ is original._VALIDATOR.__defaults__
            and function.__closure__ is original._VALIDATOR.__closure__,
        'only_changed_global':'capture_digest_v2','expiry_order_unchanged':True,
        'original_dispatcher_code_used':True,'fallback_only_NotImplemented':True,
        'ordinary_rejections_include_typed_args':True,'unrepresentable_exception_args_unknown':True,
        'B_classification_overhead_in_validator':True,'resource_exception_equivalence':False,
        'not_live_capture_authority_or_full_day_acceptance':True}


def measure(args,arm,candidate,clock=time.perf_counter_ns,attempt=None):
    require(arm in ('A','B'),'arm')
    function,record=(bound(candidate) if arm=='B' else (original._VALIDATOR,None))
    # Binding/setup is outside this isolated span but inside batch and whole.
    start=clock()
    if attempt is not None:attempt.update(validator_started_ns=start,
        digest_events=record.events if record is not None else None)
    outcome=invoke(function,args);end=clock()
    require(type(start) is int and type(end) is int and 0<=start<=end,'typed_clock')
    events=record.events if record is not None else None
    if events is not None:require(len(events)<=1,'original_digest_call_bound')
    return outcome,{'started_ns':start,'finished_ns':end,'validator_ns':end-start,'digest_events':events}


def byte_oracle(body,candidate):
    """Before measurement, retain both complete byte strings, not just hashes."""
    require(type(candidate) is encoder.Candidate,'verified_Candidate_required')
    candidate._verify()
    expected=encoder.reference_bytes_v2(body);direct=candidate.module.try_typed_bytes(body)
    classification='original_fallback' if direct is NotImplemented else 'direct_C_bytes'
    actual=encoder._bytes(lambda _:NotImplemented,body) if direct is NotImplemented else direct
    require(type(actual) is bytes and actual==expected,'premeasurement_full_bytes')
    return {'classification':classification,'expected_hex':expected.hex(),'actual_hex':actual.hex(),
        'sha256':hashlib.sha256(actual).hexdigest(),
        'C_attempts':1,'original_byte_writer_calls':2 if direct is NotImplemented else 1,
        'scope':'Premeasurement complete-byte oracle; not a validator measurement or successful capture proof.'}
