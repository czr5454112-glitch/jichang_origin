"""Closed private integration of actual notification gates and one-build evidence.

No NativeSession/LocalTransport proxy and no mutation of imported classes or
globals. Every refresh uses the original client object and original row-update
code, with an actual query sidecar. First-hop and participant policies stay old.
This module alone neither dispatches native nor grants authority to saved data.
"""
from __future__ import annotations
import ast
import builtins
import copy
import hashlib
import inspect
from types import FunctionType
from . import initial_owner_route_gate_adapter as gate
from . import initial_owner_route_outbox_trace_v2 as trace
from . import single_root_evidence as single

old=single.old
request=gate.request
require=gate.require


def private(function,changes):
    result=FunctionType(function.__code__,{**function.__globals__,**changes},function.__name__,
                        function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


TRACED_COLLECT=trace.redirect_refresh(request.InitialOwnerRequest.collect)
TRACED_OBSERVE=trace.redirect_refresh(request.InitialOwnerRequest.observe_after_boundary)
TRACED_ACTIVATE=trace.redirect_refresh(request.FixedContinuationOwner.activate)
SOURCE_FUNCTIONS={TRACED_COLLECT:request.InitialOwnerRequest.collect,
    TRACED_OBSERVE:request.InitialOwnerRequest.observe_after_boundary,
    TRACED_ACTIVATE:request.FixedContinuationOwner.activate}


class TracedContinuationOwner(request.FixedContinuationOwner):
    activate=TRACED_ACTIVATE


def inventory(policies,client):
    result={}
    for label,instance in [*policies.items(),('transport',client)]:
        for cls in type(instance).__mro__:
            for name,function in vars(cls).items():
                if not inspect.isfunction(function):continue
                original=SOURCE_FUNCTIONS.get(function,function)
                require(not gate.native_advance_sites(original),'hidden_policy_advance')
                # All selected refresh callsites must be one of the three
                # source-proven replacements, or the uncalled parent method.
                key=f'{label}:{cls.__module__}.{cls.__qualname__}.{name}'
                result[key]={'function':function,'code':function.__code__,
                    'source_sha256':hashlib.sha256(inspect.getsource(original).encode()).hexdigest()}
    require(type(client).refresh_owner is trace.SOURCE,'transport_refresh_source_changed')
    return result


class ActualAdvanceChain(gate._RecordedChain):
    """Exact closed integration identities; no caller-provided allowlist."""
    def __init__(self,session,client,root,policies):
        require(session is root.session and client is root.client,'foreign_session_or_client')
        require(request.adapter._valid_handle(root.native,session,root.accepted),'missing_actual_accepted_session')
        require(root.drain_and_finish_if_closed.__func__ is TRACKED_DRAIN,'untracked_root_drain')
        require(root.observe_after_boundary.__func__ is TRACED_OBSERVE,'unknown_root_observer')
        require(root.collect.__func__ is CapturedRequest.collect,'unknown_collection')
        require(root._record.__func__ is request.InitialOwnerRequest._record,'unknown_recorder')
        require(not hasattr(root,'_observation_advance_chain'),'single_use_chain')
        require(type(client) is old.public.LocalTransport and
            type(getattr(client,'_root_outbox_trace',None)) is trace.OutboxTrace and
            client._root_outbox_trace.client is client,'unknown_exact_transport')
        require(not policies or set(policies)=={'A','B'} and all(type(p) is TracedContinuationOwner
            and p.session is session and p.client is client and p.owner==owner
            and p.activate.__func__ is TRACED_ACTIVATE for owner,p in policies.items()),'unknown_policy_instances')
        self.method_inventory=inventory(policies,client)
        self.collection_source_inventory=gate.collection_inventory()
        super().__init__(session,client,root)
        root._observation_advance_chain=self

    def decide(self,response):
        decision=super().decide(response)
        # Same-thread read of the exact trace after original background work,
        # before the retained root activation. No supplied Boolean authority.
        self.root.events[-1]['value']['outbox_checkpoint']=self.client._root_outbox_trace.snapshot()
        return decision

    def after_step(self,skipped,admission_before):
        super().after_step(skipped,admission_before)
        self.root.events[-1]['value']['outbox_checkpoint']=self.client._root_outbox_trace.snapshot()


# Identical previously proved root drain code, with this exact chain class only.
_actual_root_drain=private(gate._actual_root_drain,{'ActualAdvanceChain':ActualAdvanceChain})
TRACKED_DRAIN=private(gate.TRACKED_ROOT_DRAIN,{'_actual_root_drain':_actual_root_drain})


def root_runtime_proof(root):
    t=root.client._root_outbox_trace
    checkpoint=t.snapshot()
    chain=getattr(root,'_observation_advance_chain',None)
    # These are live references consumed immediately by the one fresh normalize
    # below. They are never returned to callers or used after later mutation.
    return {'schema':'g31.initial_root.complete_runtime_query_proof.v1',
        'checkpoint':checkpoint,'trace':{'schema':'g31.initial_root.outbox_query_trace.v2',
            'reads':t.reads,'ack_bodies':t.bodies,'refreshes':t.refreshes,'invalid':t.invalid,
            'complete_query_endpoint_not_claimed':True,
            'scope':'Actual arguments and ACK data consumed by original refresh; not every public query.'},
        'calls':root.client.calls,'creations':root.client.creations,'outbox':root.client.rows,
        'ack_handling_count':len(root.client.ack_handling),
        'admission_count':len(root.client.roots),
        'advance_calls':chain.calls if chain is not None else [],
        'saved_data_grants_native_authority':False}


def _evidence_function():
    source=gate.tree(single.evidence);original=copy.deepcopy(source)
    fn=source.body[0]
    # Only add required proof BEFORE the original single normalize/encode.
    marker=next(i for i,node in enumerate(fn.body) if isinstance(node,ast.Assign)
        and ast.unparse(node.targets[0])=='result')
    fn.body.insert(marker,ast.parse("raw['runtime_query_proof'] = root_runtime_proof(self)").body[0])
    restored=copy.deepcopy(source);del restored.body[0].body[marker]
    require(gate.dump(restored)==gate.dump(original),'onebuild_evidence_AST_changed')
    namespace={**single.evidence.__globals__,'root_runtime_proof':root_runtime_proof}
    exec(compile(ast.fix_missing_locations(source),'<gated-single-evidence>','exec'),namespace)
    return namespace['evidence']


EVIDENCE=_evidence_function()


class CapturedRequest(single.SingleEvidenceRequest):
    evidence=EVIDENCE
    observe_after_boundary=TRACED_OBSERVE
    drain_and_finish_if_closed=TRACKED_DRAIN

    def collect(self):
        return old.call_with_recorded_collection(TRACED_COLLECT,self.initial_endpoint_records,self)


class FixedDefaultRequest(CapturedRequest):
    choose=old.FixedDefaultRequest.choose


# The exact onebuild finisher still checks its own immutable evidence function.
finish_root=private(single.finish_root,{'evidence':EVIDENCE})
publish_root=private(single.publish_root,{'finish_root':finish_root})


def _scheduler_compiler(syntax,filename,mode):
    """Called once by a private clone of the proven scheduler factory."""
    require(filename=='<gated-original-continuation>' and mode=='exec','unexpected_scheduler_compile')
    original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='client.refresh_owner':
            node.func=ast.Name(id='_traced_refresh',ctx=ast.Load())
            node.args.insert(0,ast.Name(id='client',ctx=ast.Load()));count+=1
    require(count==2,'scheduler_refresh_inventory')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='_traced_refresh':
            node.func=ast.parse('client.refresh_owner',mode='eval').body;node.args.pop(0)
    require(gate.dump(restored)==gate.dump(original),'scheduler_refresh_AST_changed')
    return builtins.compile(ast.fix_missing_locations(syntax),filename,mode)


def scheduler():
    # The original factory first restores/proves the complete scheduler AST;
    # its sole compile call then adds exactly the two traced refresh callsites.
    # There is no builtins/global patch: compile lives only in this function's
    # private globals, and is never passed to a native or policy object.
    factory=private(gate.continuation,{'compile':_scheduler_compiler,'ActualAdvanceChain':ActualAdvanceChain})
    source=private(old.run_continuation,{'publish_root':publish_root,'_traced_refresh':trace.refresh})
    function=factory(source)
    function._source_proof.update(original_refresh_sites=2,refresh_AST_restored=True,
        complete_outbox_trace=True,firsthop_detector_changed=False)
    return function


run_continuation=scheduler()


def make_client(session):
    client=old.public.LocalTransport(session)
    trace.OutboxTrace(client)
    return client


def integration_proof():
    return {'schema':'g31.initial_root.gated_evidence_source.v2',
        'scheduler':copy.deepcopy(run_continuation._source_proof),
        'refresh_sites':{'initial_collection':TRACED_COLLECT._refresh_sites,
            'root_observe':TRACED_OBSERVE._refresh_sites,'owner_activate':TRACED_ACTIVATE._refresh_sites,
            'scheduler_fallback_and_final':2},
        'actual_client_and_session_type_preserved':True,'global_monkeypatch':False,
        'firsthop_detector':{'module':request.contract.observed_first_hop.__module__,
            'source_sha256':hashlib.sha256(inspect.getsource(request.contract.observed_first_hop).encode()).hexdigest()},
        'onebuild_proof_added_before_encoding':True,'runtime_dispatched':False}
