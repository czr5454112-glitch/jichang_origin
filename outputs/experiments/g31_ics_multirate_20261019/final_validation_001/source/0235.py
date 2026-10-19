"""Private exact collector clone with passive, ordered failure-prefix evidence.

The actual native session is never proxied. Only the three existing getter calls
are wrapped. Their return objects and exceptions are returned/re-raised exactly;
recording faults make evidence unknown rather than replacing a native result.
This module grants no authority to its exported JSON journal.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import json
import textwrap
import time
from types import FunctionType,SimpleNamespace
from . import live_obligation_initial_decision_adapter as original

SCHEMA='g31.live_initial_recorded_collector.v1'
ORDER=('view','command','received')


def require(ok,reason):
    if not ok:raise ValueError('initial_recorded:'+reason)


def _clone(function,namespace,code=None):
    result=FunctionType(code or function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__;return result


def _dump(tree):return ast.dump(tree,include_attributes=False)


def collector_code():
    function=original.native_gate.collect_initial_ledger
    tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
    expressions=('session.observe_protocol(owner)','session.protocol_command(owner,initial_request_id)',
                 'session.protocol_planning_snapshots(owner)')
    old=[ast.parse(s,mode='eval').body for s in expressions]
    new=[ast.parse('_record_initial_endpoint('+repr(label)+',lambda:'+text+')',mode='eval').body
         for label,text in zip(ORDER,expressions,strict=True)]
    class Replace(ast.NodeTransformer):
        def __init__(self,left,right):self.left=left;self.right=right;self.counts=[0,0,0]
        def visit_Call(self,node):
            for i,before in enumerate(self.left):
                if _dump(node)==_dump(before):
                    self.counts[i]+=1;return ast.copy_location(copy.deepcopy(self.right[i]),node)
            return self.generic_visit(node)
    transform=Replace(old,new);changed=transform.visit(copy.deepcopy(tree))
    require(transform.counts==[1,1,1],'exact_three_getter_expressions')
    inverse=Replace(new,old);restored=inverse.visit(copy.deepcopy(changed))
    require(inverse.counts==[1,1,1] and _dump(restored)==_dump(tree),'inverse_collector_AST')
    namespace={};exec(compile(ast.fix_missing_locations(changed),__file__,'exec'),namespace)
    return namespace[function.__name__].__code__,hashlib.sha256(_dump(tree).encode()).hexdigest()


_CODE,_AST=collector_code()


def endpoint_data(label,value):
    if label=='view':return original.representation.normalized_view(value)
    # Command/received use their actual builtin JSON tree. A wrapper permits
    # received's top-level list, without converting any scalar/keys/tuples.
    encoded=original.history.payload_encoding({'endpoint':value})
    return json.loads(encoded)['endpoint']


class EndpointJournal:
    """Own getter observations only; no capability, authority or native calls."""
    def __init__(self):self.records=[];self._active=None;self.monitor_failed=False;self.monitor_errors=[]

    def _fault(self,stage,error):
        # Monitoring must never replace the original native exception. This
        # flag is also checked before a successful result can leave _invoke.
        self.monitor_failed=True
        try:self.monitor_errors.append({'stage':stage,'error_type':type(error).__name__})
        except BaseException:pass

    def _clock(self,row,key):
        try:row[key]=time.perf_counter_ns()
        except BaseException as error:self._fault(key,error)

    def _error(self,row,status,error):
        try:
            row.update(status=status,error_type=type(error).__name__)
            row['error']=str(error)
        except BaseException as recording_error:self._fault('exception_record',recording_error)

    def begin(self,label,owner,request_id):
        require(self._active is None and label in ('initial','fresh_current') and owner in ('A','B')
            and type(request_id) is str and request_id,'journal_scope')
        entry={'collection':label,'owner':owner,'request_id':request_id,'endpoints':[],'status':'in_progress'}
        self.records.append(entry);self._active=entry;self._clock(entry,'started_ns');return entry

    def call(self,label,function):
        entry=self._active;require(entry is not None,'active_collection')
        rows=entry['endpoints'];require(len(rows)<3 and label==ORDER[len(rows)],'exact_endpoint_order')
        row={'endpoint':label,'status':'in_progress'};rows.append(row);self._clock(row,'started_ns')
        try:
            value=function()
        except BaseException as error:
            self._error(row,'raised',error)
            raise
        else:
            try:
                row['status']='returned';row['value']=endpoint_data(label,value)
            except BaseException as error:
                self._fault('returned_data_export',error)
                try:row.update(evidence_status='unknown_export_error',export_error=type(error).__name__)
                except BaseException as recording_error:self._fault('export_error_record',recording_error)
            return value
        finally:self._clock(row,'finished_ns')

    def finish(self,entry,result=None,error=None):
        require(self._active is entry,'journal_completion_identity')
        self._clock(entry,'finished_ns')
        try:
            if error is not None:self._error(entry,'raised',error)
            else:
                entry.update(status='returned',returned_decision_type=type(result).__name__)
                if type(result) is dict:entry['returned_status']=result.get('status')
        except BaseException as recording_error:self._fault('collection_finish_record',recording_error)
        finally:self._active=None

    def audit_copy(self):
        # Export only this explicitly builtin tree. No native handle can be
        # attached to rows by collector success, and no authority is restored.
        return json.loads(original.history.payload_encoding({'schema':SCHEMA,'records':self.records,
            'monitor_failed':self.monitor_failed,'monitor_errors':self.monitor_errors,
            'saved_copy_has_authority':False}))


def make_functions(journal):
    require(type(journal) is EndpointJournal,'exact_journal_type')
    collector=original.native_gate.collect_initial_ledger
    require('_record_initial_endpoint' not in collector.__globals__,'record_global_collision')
    captured=_clone(collector,{**collector.__globals__,'_record_initial_endpoint':journal.call},_CODE)
    gate=SimpleNamespace(**vars(original.native_gate));gate.collect_initial_ledger=captured
    collect=_clone(original.collect_initial_decision,{**original.collect_initial_decision.__globals__,'native_gate':gate})
    refresh=_clone(original.revalidate_first_component,{**original.revalidate_first_component.__globals__,'collect_initial_decision':collect})
    return collect,refresh,captured


def _invoke(journal,label,owner,request_id,function,*args,**kwargs):
    entry=journal.begin(label,owner,request_id)
    try:result=function(*args,**kwargs)
    except BaseException as error:
        try:journal.finish(entry,error=error)
        except BaseException as recording_error:journal._fault('finish_during_original_exception',recording_error)
        raise
    try:journal.finish(entry,result=result)
    except BaseException as recording_error:journal._fault('finish_after_return',recording_error)
    if journal.monitor_failed:return original.unknown('endpoint_recording_failed',evidence_prefix_complete=False)
    return result


def collect_initial_decision(native,session,owner,publication_id,client,accepted,*,journal):
    collect,_,_=make_functions(journal)
    return _invoke(journal,'initial',owner,publication_id,collect,native,session,owner,publication_id,client,accepted)


def revalidate_first_component(decision,action,*,journal):
    original.require_current(decision)
    _,refresh,_=make_functions(journal)
    return _invoke(journal,'fresh_current',decision._owner,decision._request_id,refresh,decision,action)


def source_proof():
    code,source=collector_code();require(source==_AST and code.co_code==_CODE.co_code,'collector_source_changed')
    journal=EndpointJournal();collect,refresh,captured=make_functions(journal)
    function=original.native_gate.collect_initial_ledger
    require(set(captured.__globals__)==set(function.__globals__)|{'_record_initial_endpoint'}
        and all(captured.__globals__[k] is v for k,v in function.__globals__.items()),'collector_defining_globals')
    require(collect.__code__ is original.collect_initial_decision.__code__
        and all(collect.__globals__[k] is v for k,v in original.collect_initial_decision.__globals__.items() if k!='native_gate'),
        'original_adapter_code_globals')
    require(refresh.__code__ is original.revalidate_first_component.__code__
        and all(refresh.__globals__[k] is v for k,v in original.revalidate_first_component.__globals__.items() if k!='collect_initial_decision'),
        'original_refresh_code_globals')
    return {'schema':SCHEMA,'collector_original_AST_sha256':source,'inverse_AST_exact_three_passive_getter_wrappers':True,
        'original_adapter_and_refresh_code_unchanged':True,'actual_session_never_proxied':True,
        'original_return_object_and_exception_preserved':True,'endpoint_order':list(ORDER),
        'getter_count_unchanged':True,'raw_export_can_fail_unknown':True,'journal_has_native_authority':False,
        'monitor_failure_sticky_unknown_and_original_exception_not_replaced':True,
        'exception_timing_or_allocation_equivalent':False,'full_request_or_100ms_certified':False}
