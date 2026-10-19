"""Versioned same-six study correcting only the initial route-bound schema.

The original actual3known/3unknown evidence and all173 sources stay immutable.
No physical/model/selection call is added. Preparation never runs native code.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import textwrap
from types import FunctionType
from . import research_live_initial_six_seam as previous
from . import live_obligation_initial_recorded_adapter_v2 as recorded
from . import verify_live_initial_six_seam_v2 as verifier

ROOT,OUT=previous.ROOT,previous.OUT
MODULE=__package__+'.research_live_initial_six_seam_v2'
SCHEMA='g31.live_initial_six_seam.v2'
PURE=OUT/'live_initial_six_seam_v2_pure_001'
PRIOR=OUT/'live_initial_six_seam_prepare_001'
DIAGNOSIS=OUT/'live_initial_six_service_field_diagnosis_001.json'
TESTS=('tests/test_g31_circulation_live_initial_recorded_adapter.py',
       'tests/test_g31_circulation_live_initial_service_window_v2.py')
EXPECTED_TESTS=81  # 36 frozen +44 actual-schema/typed-bound +1 complete prepare-flow case.
origin=recorded.original
LIMIT=previous.LIMIT
CASES,KEYS,DOMAIN=previous.CASES,previous.KEYS,previous.DOMAIN
sha,read,write,reference,require=(getattr(previous,k) for k in ('sha','read','write','reference','require'))
seam,fixture,image=previous.seam,previous.fixture,previous.image


def _clone(function,namespace,code=None):
    result=FunctionType(code or function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__;return result


def source_gate():
    old=previous.source_gate()
    require(sha(PRIOR/'plan.json')=='29452ac24d205fbd516700a7af051a19805d239dd75f96e091b7f57304e83085','frozen173plan')
    plan=read(PRIOR/'plan.json')
    for name,digest in plan['source_sha256'].items():
        require(sha(name)==sha(PRIOR/plan['source_archive'][name])==digest,'frozen173source')
    require(sha(PRIOR/'receipt.json')=='524b29515d0f6e3bc963c5e38b1161528646eb090c27d9793551199332ecef46','old_actual_receipt')
    require(sha(DIAGNOSIS)=='9d638594cca23ea8360c82c280f6a05e9daa2315526fb1ac06da67f446c48fb0','saved_schema_diagnosis')
    for row in read(DIAGNOSIS)['rows']:
        require(sha(row['raw']['path'])==row['raw']['sha256'],'actual_schema_fixture')
    return old


def source_files():
    files=previous.source_files()
    for name,blob in image.source_closure(ROOT,[MODULE,__package__+'.launch_live_initial_six_seam_v2',
        __package__+'.run_live_initial_six_seam_v2_pure',TESTS[1][:-3].replace('/','.')]).items():
        require(name not in files or files[name]==blob,'source_conflict_v2');files[name]=blob
    return dict(sorted(files.items()))


def _complete_plan(plan):
    require('integration_source_proof' not in plan,'plan_extended_once')
    plan['integration_source_proof']=source_proof()
    plan['references'].update(frozen173=reference(PRIOR/'plan.json'),prior_actual_receipt=reference(PRIOR/'receipt.json'),
        source_bound_schema_diagnosis=reference(DIAGNOSIS))
    for row in read(DIAGNOSIS)['rows']:plan['references']['actual_schema_'+row['case']]=row['raw']


def prepare_code():
    tree=ast.parse(textwrap.dedent(inspect.getsource(previous.prepare)));count=0;hooks=0
    old='.launch_live_initial_six_seam';new=old+'_v2'
    hook=ast.parse('_complete_plan(plan)').body[0]
    write=ast.parse("write(output/'plan.json',plan)").body[0]
    class Replace(ast.NodeTransformer):
        def visit_Constant(self,node):
            nonlocal count
            if node.value==old:count+=1;return ast.copy_location(ast.Constant(new),node)
            return node
        def visit_Expr(self,node):
            nonlocal hooks
            if ast.dump(node,include_attributes=False)==ast.dump(write,include_attributes=False):
                hooks+=1;return [ast.copy_location(copy.deepcopy(hook),node),node]
            return self.generic_visit(node)
    changed=Replace().visit(copy.deepcopy(tree));require(count==hooks==1,'exact_launcher_and_plan_hook')
    inverse_count=0;inverse_hooks=0
    class Restore(ast.NodeTransformer):
        def visit_Constant(self,node):
            nonlocal inverse_count
            if node.value==new:inverse_count+=1;return ast.copy_location(ast.Constant(old),node)
            return node
        def visit_Expr(self,node):
            nonlocal inverse_hooks
            if ast.dump(node,include_attributes=False)==ast.dump(hook,include_attributes=False):inverse_hooks+=1;return None
            return self.generic_visit(node)
    restored=Restore().visit(copy.deepcopy(changed))
    require(inverse_count==inverse_hooks==1 and ast.dump(restored,include_attributes=False)==ast.dump(tree,include_attributes=False),
        'inverse_prepare_AST')
    namespace={};exec(compile(ast.fix_missing_locations(changed),__file__,'exec'),namespace)
    return namespace['prepare'].__code__


_NS={**vars(previous),'recorded':recorded,'origin':origin,'MODULE':MODULE,'SCHEMA':SCHEMA,
    'PURE':PURE,'TESTS':TESTS,'EXPECTED_TESTS':EXPECTED_TESTS,'source_gate':source_gate,'source_files':source_files,
    '_complete_plan':_complete_plan}
_EXACT=('encoded','data','declaration','owner_row','run_case','verify_journal','verify_saved',
        'loaded_source_pins','evidence_pins','worker','main')
for _name in _EXACT:
    globals()[_name]=_clone(getattr(previous,_name),_NS);_NS[_name]=globals()[_name]
verify_owner=verifier.make_verify_owner(_NS);_NS['verify_owner']=verify_owner
_prepare=_clone(previous.prepare,_NS,prepare_code())
_verify_plan=_clone(previous.verify_plan,_NS)


def source_proof():
    require(all(globals()[k].__code__ is getattr(previous,k).__code__ for k in _EXACT),'unchanged_campaign_code')
    replaced={'recorded','origin','MODULE','SCHEMA','PURE','TESTS','EXPECTED_TESTS','source_gate','source_files',
        'prepare','verify_plan','verify_owner',*_EXACT}
    require(set(_NS)==set(vars(previous))|{'_complete_plan'} and _NS['_complete_plan'] is _complete_plan
        and all(_NS[k] is v for k,v in vars(previous).items() if k not in replaced),
        'complete_defining_globals')
    require(prepare_code().co_code==_prepare.__code__.co_code,'prepare_source_binding')
    return {'schema':SCHEMA+'.source','recorded':recorded.source_proof(),'saved':verifier.source_proof(),
        'exact_old_function_codes':list(_EXACT),'same_three_inputs_six_owners':True,
        'same_one_shared120_acceptance_and_no_physical_submit':True,'old173_preserved':True,
        'prepare_inverse_AST_launcher_and_prewrite_extension_only':True,
        'final_plan_completed_before_first_write_verify_and_ready':True}


def verify_plan(output,plan):
    _verify_plan(output,plan)
    require(plan['integration_source_proof']==source_proof(),'integration_source_proof')


_NS['verify_plan']=verify_plan


def prepare(output):
    _prepare(output)


_NS['prepare']=prepare

if __name__=='__main__':raise SystemExit(main())
