"""Source-bound outbox replay sidecar; no NativeSession or transport proxy.

The exact original client instance is retained. A private refresh function logs
its actual query and the ORIGINAL ACK-change test once. Complete changed ACK
bodies are copied once, repeated reads reference those bodies. Neither native
reads, immutable retry times, row updates nor admission identities are skipped.
Future integration must close every refresh call site before this is authority.
"""
from __future__ import annotations
import ast
import copy
import inspect
import math
import time
from . import initial_owner_route_gate_adapter as gate

require=gate.require
SOURCE=gate.original.public.LocalTransport.refresh_owner
TERMINAL=SOURCE.__globals__['v1'].TERMINAL


class OutboxTrace:
    def __init__(self,client):
        require(not hasattr(client,'_root_outbox_trace') and not client.rows and not client.calls,
                'trace_requires_fresh_original_client')
        self.client=client;self.reads=[];self.bodies=[];self.latest={};self.objects={}
        self.pending=None;self.refreshes=[];self.active=None;self.invalid=None
        client._root_outbox_trace=self

    def query(self,method,owner,identity):
        require(self.pending is None and self.active is not None,'unscoped_or_overlapping_query')
        client=self.client
        row={'ordinal':len(self.reads),'refresh':self.active,'method':method,'owner':owner,
             'request_id':identity,'at':client.session.physical_time,'call_prefix':len(client.calls),
             'started_ns':time.perf_counter_ns()}
        self.pending=(row,client.rows[identity].get('ack'))
        try:
            value=getattr(client.session,method)(owner,identity)
            row['query_finished_ns']=time.perf_counter_ns()
            return value
        except BaseException as exc:
            row.update(error=repr(exc),query_finished_ns=time.perf_counter_ns())
            self.reads.append(row);self.pending=None;self.invalid=repr(exc)
            raise

    def ack_test(self,owner,identity,ack,previous):
        require(self.pending is not None,'ACK_test_without_actual_query')
        row,original_previous=self.pending
        require(row['owner']==owner and row['request_id']==identity and previous is original_previous,
                'query_ACK_binding')
        # This is the original expression, including short-circuit behavior.
        condition=ack and ack!=previous
        if condition:
            reference=len(self.bodies);self.bodies.append(copy.deepcopy(ack))
        elif ack:
            require(identity in self.latest and previous is self.objects[identity],
                    'ACK_not_from_preceding_actual_refresh')
            reference=self.latest[identity]
            require(reference is not None,'missing_previous_ACK_body')
        else:reference=None
        row.update(ack_ref=reference,ack_changed=bool(condition),
                   handling_root=self.client.context['root_id'] if self.client.context else None)
        self.latest[identity]=reference;self.objects[identity]=ack
        self.reads.append(row);self.pending=None
        return condition

    def snapshot(self):
        require(self.pending is None and self.active is None,'outbox_checkpoint_inside_refresh')
        return {'query_prefix':len(self.reads),'call_prefix':len(self.client.calls),
                'ack_handling_prefix':len(self.client.ack_handling),'invalid':self.invalid}

    def audit_copy(self):
        return {'schema':'g31.initial_root.outbox_query_trace.v1','reads':copy.deepcopy(self.reads),
            'ack_bodies':copy.deepcopy(self.bodies),'refreshes':copy.deepcopy(self.refreshes),
            'invalid':self.invalid,'complete_query_endpoint_not_claimed':True,
            'scope':'Exact actual query arguments and ACK data consumed by original refresh, plus original calls ledger.'}


def _query(client,method,owner,identity):
    return client._root_outbox_trace.query(method,owner,identity)


def _ack_test(client,owner,identity,ack,previous):
    return client._root_outbox_trace.ack_test(owner,identity,ack,previous)


def compile_refresh():
    syntax=gate.tree(SOURCE);original=copy.deepcopy(syntax);queries=tests=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Call) and ast.unparse(node.func) in (
                'self.session.protocol_request','self.session.protocol_command'):
            method=node.func.attr
            node.func=ast.Name(id='_query',ctx=ast.Load())
            node.args=[ast.Name(id='self',ctx=ast.Load()),ast.Constant(value=method),*node.args]
            queries+=1
        if isinstance(node,ast.If) and ast.unparse(node.test)=="ack and ack != row.get('ack')":
            node.test=ast.parse("_ack_test(self, owner, identity, ack, row.get('ack'))",mode='eval').body
            tests+=1
    require(queries==2 and tests==1,'refresh_source_shape')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='_query':
            method=node.args[1].value;node.func=ast.parse('self.session.'+method,mode='eval').body
            node.args=node.args[2:]
        if isinstance(node,ast.If) and isinstance(node.test,ast.Call) and ast.unparse(node.test.func)=='_ack_test':
            node.test=ast.parse("ack and ack != row.get('ack')",mode='eval').body
    require(gate.dump(restored)==gate.dump(original),'refresh_AST_changed')
    namespace={**SOURCE.__globals__,'_query':_query,'_ack_test':_ack_test}
    exec(compile(ast.fix_missing_locations(syntax),'<source-bound-outbox-refresh>','exec'),namespace)
    return namespace[SOURCE.__name__]


REFRESH=compile_refresh()


def refresh(client,owner,*,retry=True):
    trace=client._root_outbox_trace
    require(type(trace) is OutboxTrace and trace.client is client and trace.active is None,
            'outbox_trace_instance')
    entry={'ordinal':len(trace.refreshes),'owner':owner,'retry':retry,
        'at':client.session.physical_time,'first_query':len(trace.reads),'first_call':len(client.calls),
        'started_ns':time.perf_counter_ns()}
    trace.active=entry['ordinal'];trace.refreshes.append(entry)
    try:return REFRESH(client,owner,retry=retry)
    except BaseException as exc:
        trace.invalid=repr(exc);entry['error']=repr(exc);raise
    finally:
        entry.update(after_query=len(trace.reads),after_call=len(client.calls),finished_ns=time.perf_counter_ns())
        trace.active=None


def redirect_refresh(function):
    """Private exact function AST, replacing only its explicit refresh calls."""
    syntax=gate.tree(function);original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Call) and ast.unparse(node.func) in ('self.client.refresh_owner','client.refresh_owner'):
            client=node.func.value;node.func=ast.Name(id='_traced_refresh',ctx=ast.Load())
            node.args.insert(0,client);count+=1
    require(count>0,'missing_declared_refresh_site')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='_traced_refresh':
            client=node.args.pop(0);node.func=ast.Attribute(value=client,attr='refresh_owner',ctx=ast.Load())
    require(gate.dump(restored)==gate.dump(original),'refresh_callsite_AST_changed')
    namespace={**function.__globals__,'_traced_refresh':refresh}
    exec(compile(ast.fix_missing_locations(syntax),'<private-refresh-callsite>','exec'),namespace)
    result=namespace[function.__name__];result._refresh_sites=count
    return result


def reconstruct(trace,calls,creations,*,query_prefix=None,call_prefix=None):
    """No native calls. Replay full original row mutations in actual read/send order."""
    require(trace['schema']=='g31.initial_root.outbox_query_trace.v1' and trace['invalid'] is None,
            'unclosed_outbox_trace')
    reads=trace['reads'];bodies=trace['ack_bodies'];n=len(reads) if query_prefix is None else query_prefix
    limit=len(calls) if call_prefix is None else call_prefix
    require(type(n) is int and 0<=n<=len(reads) and type(limit) is int and 0<=limit<=len(calls),'outbox_prefix')
    rows={};handling=[];cursor=0;used_bodies=[];latest={}
    def send(call):
        identity=call['request']['request_id'];kind=call['kind'];payload=call['request']
        if call['retry']:
            require(identity in rows and gate.ordered(rows[identity]['request'])==gate.ordered(payload)
                and rows[identity]['kind']==kind,'immutable_retry')
        else:
            require(identity not in rows,'duplicate_new_intent')
            rows[identity]={'kind':kind,'request':copy.deepcopy(payload),'terminal':False}
        row=rows[identity];row['next_retry']=call['at']+.5
        row['reply']=copy.deepcopy(call['reply']);row['terminal']=call['reply'].get('status')=='rejected'
    for index,read in enumerate(reads[:n]):
        require(read['ordinal']==index and 'error' not in read and type(read['call_prefix']) is int
            and cursor<=read['call_prefix']<=limit,'query_order')
        while cursor<read['call_prefix']:send(calls[cursor]);cursor+=1
        identity=read['request_id'];require(identity in rows,'query_before_intent')
        row=rows[identity]
        require(read['owner']==row['request']['owner_id'] and read['method']==(
            'protocol_request' if row['kind']=='transfer' else 'protocol_command'),'query_owner_kind')
        reference=read['ack_ref']
        require(reference is None or type(reference) is int and 0<=reference<len(bodies),'ACK_reference')
        ack={} if reference is None else bodies[reference]
        changed=bool(ack and ack!=row.get('ack'))
        require(changed is read['ack_changed'],'original_ACK_change_test')
        if changed:
            require(reference==len(used_bodies),'ACK_new_body_sequence');used_bodies.append(reference)
            require(identity in creations,'ACK_missing_creation')
            handling.append({'at':read['at'],'owner':read['owner'],'request_id':identity,
                'ack':copy.deepcopy(ack),'handling_root':read['handling_root'],
                'continuation_parent_roots':[creations[identity]['creating_root']]})
        elif ack:require(latest.get(identity)==reference,'ACK_reused_foreign_body')
        latest[identity]=reference
        # ACK bodies are verifier-owned read-only data. Replacing a row's
        # reference never mutates its body; duplicate queries need no tree copy.
        row['ack']=ack;row['terminal']=row['terminal'] or ack.get('status') in TERMINAL
    while cursor<limit:send(calls[cursor]);cursor+=1
    if n==len(reads):require(used_bodies==list(range(len(bodies))),'unreferenced_ACK_body')
    return {'rows':rows,'ack_handling':handling}


def verify_refresh_inventory(trace,calls,creations):
    """One forward replay; never reconstruct the complete history per query."""
    replay=Replay(trace,calls,creations)
    previous_query=previous_call=0;previous_finish=0
    for ordinal,entry in enumerate(trace['refreshes']):
        require(entry['ordinal']==ordinal and 'error' not in entry
            and entry['first_query']==previous_query and entry['first_call']>=previous_call
            and entry['after_query']>=entry['first_query'] and entry['after_call']>=entry['first_call']
            and type(entry['retry']) is bool and _clock(entry['started_ns']) and _clock(entry['finished_ns'])
            and previous_finish<=entry['started_ns']<=entry['finished_ns'] and _logical(entry['at']),
            'refresh_inventory')
        replay.advance(entry['first_query'],entry['first_call'])
        expected=[identity for identity,row in replay.rows.items() if row['request']['owner_id']==entry['owner']]
        actual=trace['reads'][entry['first_query']:entry['after_query']]
        require([row['request_id'] for row in actual]==expected
            and all(row['refresh']==ordinal and row['owner']==entry['owner'] and row['at']==entry['at']
                    for row in actual),'complete_owner_query_inventory')
        for index,row in enumerate(actual):
            next_count=actual[index+1]['call_prefix'] if index+1<len(actual) else entry['after_call']
            require(entry['started_ns']<=row['started_ns']<=row['query_finished_ns']<=entry['finished_ns'],
                    'query_outside_refresh_clock')
            replay.advance(row['ordinal']+1,row['call_prefix'])
            after=replay.rows[row['request_id']]
            due=entry['retry'] and not after['terminal'] and entry['at']>=after['next_retry']
            require(next_count-row['call_prefix']==int(due),'original_retry_count')
            if due:
                call=calls[row['call_prefix']]
                require(call['retry'] is True and call['request']['request_id']==row['request_id']
                        and call['at']==entry['at'],'original_retry_identity_time')
        previous_query,previous_call=entry['after_query'],entry['after_call']
        previous_finish=entry['finished_ns']
    require(previous_query==len(trace['reads']),'unscoped_query_tail')
    replay.advance(len(trace['reads']),len(calls));replay.finish()
    return {'status':'passed_complete_outbox_query_and_retry_replay',
            'refreshes':len(trace['refreshes']),'queries':len(trace['reads']),
            'native_authenticity_certified_by_data_alone':False}


def _clock(value):return type(value) is int and value>=0
def _logical(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


class Replay:
    """Incremental exact row state for ordered gate checkpoints and final audit.

    Returned state is verifier-owned. It is not a native session or permission.
    Query/send processing is linear; checkpoint projections may be compared by
    the caller without copying the complete ACK tree at every query.
    """
    def __init__(self,trace,calls,creations):
        require(trace['schema']=='g31.initial_root.outbox_query_trace.v1' and trace['invalid'] is None,
                'unclosed_outbox_trace')
        self.trace,self.calls,self.creations=trace,calls,creations
        self.rows={};self.handling=[];self.query=0;self.call=0;self.body=0;self.latest={}
        self.last_query_finished=0

    def _send(self,call):
        identity=call['request']['request_id'];kind=call['kind'];payload=call['request']
        require(_logical(call['at']) and type(call['retry']) is bool,'send_clock_or_retry_type')
        if call['retry']:
            require(identity in self.rows and gate.ordered(self.rows[identity]['request'])==gate.ordered(payload)
                and self.rows[identity]['kind']==kind,'immutable_retry')
        else:
            require(identity not in self.rows and identity in self.creations,'duplicate_or_uncreated_intent')
            self.rows[identity]={'kind':kind,'request':copy.deepcopy(payload),'terminal':False}
        row=self.rows[identity];row['next_retry']=call['at']+.5
        row['reply']=copy.deepcopy(call['reply']);row['terminal']=call['reply'].get('status')=='rejected'

    def _query(self,read):
        require(read['ordinal']==self.query and 'error' not in read and read['call_prefix']==self.call
            and _logical(read['at']) and _clock(read['started_ns']) and _clock(read['query_finished_ns'])
            and self.last_query_finished<=read['started_ns']<=read['query_finished_ns'], 'query_order_or_clock')
        identity=read['request_id'];require(identity in self.rows,'query_before_intent')
        row=self.rows[identity];bodies=self.trace['ack_bodies']
        require(read['owner']==row['request']['owner_id'] and read['method']==(
            'protocol_request' if row['kind']=='transfer' else 'protocol_command'),'query_owner_kind')
        reference=read['ack_ref']
        require(reference is None or type(reference) is int and 0<=reference<len(bodies),'ACK_reference')
        ack={} if reference is None else bodies[reference]
        require(type(ack) is dict,'ACK_body_type')
        changed=bool(ack and ack!=row.get('ack'))
        require(changed is read['ack_changed'],'original_ACK_change_test')
        if changed:
            require(reference==self.body,'ACK_new_body_sequence');self.body+=1
            self.handling.append({'at':read['at'],'owner':read['owner'],'request_id':identity,
                'ack':copy.deepcopy(ack),'handling_root':read['handling_root'],
                'continuation_parent_roots':[self.creations[identity]['creating_root']]})
        elif ack:require(self.latest.get(identity)==reference,'ACK_reused_foreign_body')
        self.latest[identity]=reference
        # The saved body is only read by this verifier. Repeated reads replace
        # the pointer exactly as native refresh does, without a full tree copy.
        row['ack']=ack;row['terminal']=row['terminal'] or ack.get('status') in TERMINAL
        self.last_query_finished=read['query_finished_ns']

    def advance(self,query_prefix,call_prefix):
        reads=self.trace['reads']
        require(type(query_prefix) is int and self.query<=query_prefix<=len(reads)
            and type(call_prefix) is int and self.call<=call_prefix<=len(self.calls),'nonmonotone_outbox_checkpoint')
        while self.query<query_prefix:
            read=reads[self.query];count=read['call_prefix']
            require(type(count) is int and self.call<=count<=call_prefix,'query_order')
            while self.call<count:self._send(self.calls[self.call]);self.call+=1
            self._query(read);self.query+=1
        while self.call<call_prefix:self._send(self.calls[self.call]);self.call+=1
        return self

    def finish(self):
        require(self.query==len(self.trace['reads']) and self.call==len(self.calls)
            and self.body==len(self.trace['ack_bodies']),'unconsumed_outbox_trace')
        return {'rows':self.rows,'ack_handling':self.handling}
