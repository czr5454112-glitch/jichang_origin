"""Separate actual18 target for real first EDGE_ENTER closure; no auto-run."""
from __future__ import annotations
import ast
import copy
from types import SimpleNamespace
from . import initial_owner_route_gate_campaign_v2 as previous
from . import initial_owner_route_entry_integration as integrated

SCHEMA='g31.initial_owner_route_entry_campaign.v1'
ROOT,OUT,public,image=previous.ROOT,previous.OUT,previous.public,previous.image
LIMIT,ARMS,FAULTS=previous.LIMIT,previous.ARMS,previous.FAULTS
contract=integrated.contract
old=previous.old
gate=previous.gate
for _name in ('require','sha','read','ordered','reference','write','declarations','scene',
    'captured_collection','call_with_recorded_collection','failed_root_evidence','close_predictor',
    'continuation_result','full_outcome','check_loaded_sources'):
    globals()[_name]=getattr(previous,_name)
CapturedRequest,FixedDefaultRequest=integrated.CapturedRequest,integrated.FixedDefaultRequest
run_continuation,publish_root=integrated.run_continuation,integrated.publish_root
request=SimpleNamespace(**vars(previous.request))
request.FixedContinuationOwner=integrated.TracedContinuationOwner
run_branch=integrated.private(previous.branch_function,globals())()


def verify_plan(output,expected):
    plan=integrated.private(old.verify_plan,{'SCHEMA':SCHEMA})(output,expected)
    require(plan['entry_source_proof']==integrated.integration_proof(),'entry_source_proof_changed')
    for name in ('frozen_v3_campaign','frozen_single_evidence_plan','frozen_gate_v1_campaign',
                 'frozen_gate_v2_campaign','entry_pure_reference'):
        ref=plan[name];require(sha(ref['path'])==ref['sha256'],'entry_reference_changed:'+name)
    require(plan['max_native_workers']==1 and plan['native_branch_budget']==18
        and plan['hard_timeout_seconds']==600.,'entry_campaign_budget')
    return plan


def worker_function():
    syntax=gate.tree(old.worker);original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.ImportFrom) and node.level==1 and node.module is None:
            if len(node.names)==1 and node.names[0].name=='verify_initial_owner_route_campaign_v3':
                node.names[0].name='verify_initial_owner_route_entry_campaign';count+=1
    require(count==1,'entry_worker_verifier_import')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.ImportFrom) and node.level==1 and node.module is None:
            if len(node.names)==1 and node.names[0].name=='verify_initial_owner_route_entry_campaign':
                node.names[0].name='verify_initial_owner_route_campaign_v3'
    require(gate.dump(restored)==gate.dump(original),'entry_worker_AST_changed')
    namespace={**old.worker.__globals__,**globals()}
    exec(compile(ast.fix_missing_locations(syntax),'<entry-owned-worker>','exec'),namespace)
    return namespace['worker']


worker=worker_function()
main=integrated.private(old.main,globals())
if __name__=='__main__':raise SystemExit(main())
