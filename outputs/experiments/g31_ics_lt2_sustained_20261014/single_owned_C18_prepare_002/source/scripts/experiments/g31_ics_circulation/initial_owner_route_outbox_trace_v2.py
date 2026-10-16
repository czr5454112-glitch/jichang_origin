"""Lossless ACK representation, independent of original dict equality.

Old v1 and its unexecuted preparation remain frozen. ACK handling/retry semantics
still use the original ``ack and ack != previous`` once. A separate strict
ordered builtin comparison governs body reuse, including tuple/list, numeric
types and signed-zero bits. All comparison/copy costs remain in the caller.
"""
from __future__ import annotations
import copy
import math
from types import FunctionType
from . import initial_owner_route_outbox_trace as old

gate,require,SOURCE,TERMINAL=old.gate,old.require,old.SOURCE,old.TERMINAL
SCHEMA='g31.initial_root.outbox_query_trace.v2'
_clock,_logical=old._clock,old._logical


def strict_same(left,right):
    """Native builtin trees only; order, type and float representation matter.

    A cycle or custom container is unsupported, never a reusable body. Native
    renderers emit acyclic trees; shared aliases remain valid independent trees.
    """
    pending=[(left,right,False)];active_left=set();active_right=set()
    while pending:
        a,b,leave=pending.pop();kind=type(a)
        if leave:
            active_left.remove(id(a));active_right.remove(id(b));continue
        if type(b) is not kind:return False
        if kind in (dict,list,tuple):
            if id(a) in active_left or id(b) in active_right:return False
            active_left.add(id(a));active_right.add(id(b));pending.append((a,b,True))
            if kind is dict:
                if len(a)!=len(b):return False
                for (ak,av),(bk,bv) in zip(a.items(),b.items()):
                    if type(ak) is not str or type(bk) is not str or ak!=bk:return False
                    pending.append((av,bv,False))
            else:
                if len(a)!=len(b):return False
                pending.extend((av,bv,False) for av,bv in zip(a,b))
        elif kind is float:
            if not math.isfinite(a) or not math.isfinite(b) or a.hex()!=b.hex():return False
        elif kind in (str,int,bool,type(None)):
            if a!=b:return False
        else:return False
    return True


class OutboxTrace(old.OutboxTrace):
    def ack_test(self,owner,identity,ack,previous):
        require(self.pending is not None,'ACK_test_without_actual_query')
        row,original_previous=self.pending
        require(row['owner']==owner and row['request_id']==identity and previous is original_previous,
                'query_ACK_binding')
        condition=ack and ack!=previous  # exact original handler predicate
        if ack:
            if not condition:
                require(identity in self.latest and previous is self.objects[identity]
                    and self.latest[identity] is not None,'ACK_not_from_preceding_actual_refresh')
            body_new=bool(condition) or not strict_same(ack,self.bodies[self.latest[identity]])
            if body_new:
                reference=len(self.bodies);self.bodies.append(copy.deepcopy(ack))
            else:reference=self.latest[identity]
        else:
            reference=None;body_new=False
        row.update(ack_ref=reference,ack_changed=bool(condition),body_is_new=body_new,
            handling_root=self.client.context['root_id'] if self.client.context else None)
        self.latest[identity]=reference;self.objects[identity]=ack
        self.reads.append(row);self.pending=None
        return condition

    def audit_copy(self):
        value=super().audit_copy();value['schema']=SCHEMA
        return value


class Replay(old.Replay):
    def __init__(self,trace,calls,creations):
        require(trace['schema']==SCHEMA and trace['invalid'] is None,'unclosed_outbox_trace')
        self.trace,self.calls,self.creations=trace,calls,creations
        self.rows={};self.handling=[];self.query=0;self.call=0;self.body=0;self.latest={}
        self.last_query_finished=0

    def _query(self,read):
        require(read['ordinal']==self.query and 'error' not in read and read['call_prefix']==self.call
            and _logical(read['at']) and _clock(read['started_ns']) and _clock(read['query_finished_ns'])
            and self.last_query_finished<=read['started_ns']<=read['query_finished_ns'],'query_order_or_clock')
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
        body_new=bool(ack) and (changed or not strict_same(ack,row.get('ack')))
        require(type(read.get('body_is_new')) is bool and read['body_is_new']==body_new,
                'strict_ACK_representation_change')
        if body_new:
            require(reference==self.body,'ACK_new_body_sequence');self.body+=1
        elif ack:require(self.latest.get(identity)==reference,'ACK_reused_foreign_body')
        if changed:
            self.handling.append({'at':read['at'],'owner':read['owner'],'request_id':identity,
                'ack':copy.deepcopy(ack),'handling_root':read['handling_root'],
                'continuation_parent_roots':[self.creations[identity]['creating_root']]})
        self.latest[identity]=reference
        row['ack']=ack;row['terminal']=row['terminal'] or ack.get('status') in TERMINAL
        self.last_query_finished=read['query_finished_ns']


# All original actual query calls, original refresh AST and row/retry mutation
# code remain identical; only the exact accepted trace class is versioned.
REFRESH=old.REFRESH
refresh=FunctionType(old.refresh.__code__,{**old.refresh.__globals__,'OutboxTrace':OutboxTrace},
    old.refresh.__name__,old.refresh.__defaults__,old.refresh.__closure__)
refresh.__kwdefaults__=old.refresh.__kwdefaults__
redirect_refresh=FunctionType(old.redirect_refresh.__code__,{**old.redirect_refresh.__globals__,'refresh':refresh},
    old.redirect_refresh.__name__,old.redirect_refresh.__defaults__,old.redirect_refresh.__closure__)
verify_refresh_inventory=FunctionType(old.verify_refresh_inventory.__code__,
    {**old.verify_refresh_inventory.__globals__,'Replay':Replay},old.verify_refresh_inventory.__name__,
    old.verify_refresh_inventory.__defaults__,old.verify_refresh_inventory.__closure__)


def reconstruct(trace,calls,creations,*,query_prefix=None,call_prefix=None):
    replay=Replay(trace,calls,creations)
    replay.advance(len(trace['reads']) if query_prefix is None else query_prefix,
        len(calls) if call_prefix is None else call_prefix)
    return {'rows':replay.rows,'ack_handling':replay.handling}
