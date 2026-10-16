"""Versioned actual18 preparation target: one-build evidence + observation gate.

Only the owned launcher may execute this finite native/RPC campaign. Old v3
first-hop/physical policy/cadence/IDs and all fault rows remain frozen.
"""
from __future__ import annotations
import ast
import copy
from types import FunctionType,SimpleNamespace
from . import initial_owner_route_campaign_v3 as old
from . import initial_owner_route_gated_evidence as integrated
from . import initial_owner_route_gate_adapter as gate

SCHEMA='g31.initial_owner_route_gate_campaign.v1'
ROOT,OUT,public,contract,image=old.ROOT,old.OUT,old.public,old.contract,old.image
LIMIT,ARMS,FAULTS=old.LIMIT,old.ARMS,old.FAULTS
for _name in ('require','sha','read','ordered','reference','write','declarations','scene',
    'captured_collection','call_with_recorded_collection','failed_root_evidence','close_predictor',
    'continuation_result','full_outcome','check_loaded_sources'):
    globals()[_name]=getattr(old,_name)

CapturedRequest,FixedDefaultRequest=integrated.CapturedRequest,integrated.FixedDefaultRequest
run_continuation,publish_root=integrated.run_continuation,integrated.publish_root
request=SimpleNamespace(**vars(old.request))
request.FixedContinuationOwner=integrated.TracedContinuationOwner


def branch_function():
    syntax=gate.tree(old.run_branch);original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='public.LocalTransport':
            node.func=ast.Name(id='_make_client',ctx=ast.Load());count+=1
    require(count==1,'gate_branch_client_constructor')
    returned=syntax.body[0].body[-1]
    require(isinstance(returned,ast.Return) and isinstance(returned.value,ast.Dict),'gate_branch_return_shape')
    returned.value.keys.extend([ast.Constant('observation_gate_audit'),ast.Constant('outbox_query_trace')])
    returned.value.values.extend([
        ast.parse("root._observation_advance_chain.audit_copy() if hasattr(root,'_observation_advance_chain') else None",mode='eval').body,
        ast.parse('client._root_outbox_trace.audit_copy()',mode='eval').body])
    restored=copy.deepcopy(syntax)
    del restored.body[0].body[-1].value.keys[-2:];del restored.body[0].body[-1].value.values[-2:]
    for node in ast.walk(restored):
        if isinstance(node,ast.Call) and ast.unparse(node.func)=='_make_client':
            node.func=ast.parse('public.LocalTransport',mode='eval').body
    require(gate.dump(restored)==gate.dump(original),'gate_branch_AST_changed')
    namespace={**old.run_branch.__globals__,**globals(),'_make_client':integrated.make_client}
    exec(compile(ast.fix_missing_locations(syntax),'<gate-native-branch>','exec'),namespace)
    return namespace['run_branch']


run_branch=branch_function()


def verify_plan(output,expected):
    plan=integrated.private(old.verify_plan,{'SCHEMA':SCHEMA})(output,expected)
    require(plan['gate_source_proof']==integrated.integration_proof(),'gate_source_proof_changed')
    for name in ('frozen_v3_campaign','frozen_single_evidence_plan','gate_pure_reference'):
        ref=plan[name];require(sha(ref['path'])==ref['sha256'],'gate_reference_changed:'+name)
    require(plan['max_native_workers']==1 and plan['native_branch_budget']==18
        and plan['hard_timeout_seconds']==600.,'gate_campaign_budget')
    return plan


def worker_function():
    syntax=gate.tree(old.worker);original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.ImportFrom) and node.level==1 and node.module is None:
            if len(node.names)==1 and node.names[0].name=='verify_initial_owner_route_campaign_v3':
                node.names[0].name='verify_initial_owner_route_gate_campaign';count+=1
    require(count==1,'gate_worker_verifier_import')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.ImportFrom) and node.level==1 and node.module is None:
            if len(node.names)==1 and node.names[0].name=='verify_initial_owner_route_gate_campaign':
                node.names[0].name='verify_initial_owner_route_campaign_v3'
    require(gate.dump(restored)==gate.dump(original),'gate_worker_AST_changed')
    namespace={**old.worker.__globals__,**globals()}
    exec(compile(ast.fix_missing_locations(syntax),'<gate-owned-worker>','exec'),namespace)
    return namespace['worker']


worker=worker_function()
main=integrated.private(old.main,{**globals()})
if __name__=='__main__':raise SystemExit(main())
