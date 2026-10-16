"""Fixed6 ABBA24 complete initial-context plus prediction component.

Draft preparation requires its own focused pure receipt. No dispatch occurs
without --execute and an exact prepared hash. Initial guards are inside BOTH
sample callbacks; initial evidence loading remains separately in whole120.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import sys
import textwrap
import traceback
from types import FunctionType, SimpleNamespace
from . import measure_scoped_public_inputs_v2_six as prior
from . import public_live_obligation_initial_scoped_inputs as component
from . import prepare_initial_scoped_public_inputs as source

ROOT, OUT, ORDER = prior.ROOT, prior.OUT, prior.ORDER
MODULE = 'scripts.experiments.g31_ics_circulation.measure_initial_scoped_public_inputs_six'
TEST = 'tests/test_g31_circulation_initial_scoped_inputs_cost.py'
PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_initial_scoped_inputs_cost_pure'
PURE = OUT/'initial_scoped_inputs_cost_pure_001'
PURE_COUNT = 30
SOURCE = OUT/'initial_scoped_public_inputs_source_prepare_001'
SOURCE_PLAN = '08c46b3b638cc19eb50d4e5b85ebd5449a5736d9a2153e5e7aa23d53356ac91b'
FULL = source.PREVIOUS
PREVIOUS = prior.OUT/'scoped_public_inputs_v2_six_cost_prepare_001'
PREVIOUS_PLAN = 'b1e5a14e4362c84f79b16ca22607086b29db3213b0ff588248ec9461816292c0'
PREVIOUS_REPORT = '05a338830db5d8b0b8e5ab54c2542a9ad4a4d9201d19538019dda672148d0063'
SCHEMA = 'g31.initial_context_and_predict.ABBA6.v1'
LIMIT = 120.
sha, read, write, ref, require = prior.sha, prior.read, prior.write, prior.ref, prior.require
frozen = prior.frozen


def _reference(public, action):
    require(action is public['action'], 'same_action_object')
    return component.reference(public)


def _candidate(public, action):
    require(action is public['action'], 'same_action_object')
    return component.predict(public)


def _dump(node): return ast.dump(node, include_attributes=False)


def _worker_code():
    original = ast.parse(textwrap.dedent(inspect.getsource(frozen.worker)))
    old = ast.parse('context=base.build_initial(public,prior)').body[0]
    new = ast.parse('context=public').body[0]
    class Replace(ast.NodeTransformer):
        def __init__(self, inverse=False): self.inverse=inverse; self.assignment=0; self.label=0
        def visit_Assign(self, node):
            before,after = (new,old) if self.inverse else (old,new)
            if _dump(node) == _dump(before): self.assignment+=1; return copy.deepcopy(after)
            return self.generic_visit(node)
        def visit_Constant(self, node):
            before,after = ('public_input_loaded_only','initial_context_prepared') if self.inverse else ('initial_context_prepared','public_input_loaded_only')
            if node.value == before: self.label+=1; return ast.copy_location(ast.Constant(after), node)
            return node
    transform = Replace(); syntax = transform.visit(copy.deepcopy(original))
    require((transform.assignment,transform.label) == (1,1), 'one_outside_initial_construction')
    tail = ast.parse("write(output/'report.json',report)").body[0]; body=syntax.body[0].body
    positions = [i for i,node in enumerate(body) if _dump(node)==_dump(tail)]
    require(len(positions)==1,'report_insertion')
    additions=ast.parse("report=_extend_report(output,plan,ledger,report)\nrequire(pins_now(output,plan)==exit_pins,'post_extra_audit_pins')").body
    body[positions[0]:positions[0]]=additions
    # The inherited receipt used the pre-extension counter. Preserve that
    # original on inverse proof, but emit the fully checked report denominator.
    receipt=body[-1]
    require(isinstance(receipt,ast.Expr) and isinstance(receipt.value,ast.Call),'receipt_shape')
    mapping=receipt.value.args[1]; require(isinstance(mapping,ast.Dict),'receipt_mapping')
    fields={key.value:index for index,key in enumerate(mapping.keys) if isinstance(key,ast.Constant)}
    require(_dump(mapping.values[fields['exact']])==_dump(ast.parse('exact_count',mode='eval').body)
        and _dump(mapping.values[fields['unknown']])==_dump(ast.parse('24-exact_count',mode='eval').body),'receipt_original_counts')
    mapping.values[fields['exact']]=ast.parse("report['exact']",mode='eval').body
    mapping.values[fields['unknown']]=ast.parse("report['unknown']",mode='eval').body
    inverse=copy.deepcopy(syntax); del inverse.body[0].body[positions[0]:positions[0]+len(additions)]
    inverse_mapping=inverse.body[0].body[-1].value.args[1]
    inverse_mapping.values[fields['exact']]=ast.parse('exact_count',mode='eval').body
    inverse_mapping.values[fields['unknown']]=ast.parse('24-exact_count',mode='eval').body
    restore=Replace(True); inverse=restore.visit(inverse)
    require((restore.assignment,restore.label)==(1,1) and _dump(inverse)==_dump(original),'inverse_worker_AST')
    namespace={};exec(compile(ast.fix_missing_locations(syntax),str(Path(__file__)),'exec'),namespace)
    return namespace['worker'].__code__,hashlib.sha256(_dump(original).encode()).hexdigest()


_CODE,_ORIGINAL_AST=_worker_code()


def worker_function():
    namespace={**frozen.worker.__globals__,'lazy':SimpleNamespace(predict=_reference),
        'candidate':SimpleNamespace(predict=_candidate),'pins_now':pins_now,'_extend_report':_extend_report}
    result=FunctionType(_CODE,namespace,frozen.worker.__name__,frozen.worker.__defaults__,frozen.worker.__closure__)
    result.__kwdefaults__=frozen.worker.__kwdefaults__;return result


def source_proof():
    function=worker_function();old=frozen.worker.__globals__;allowed={'lazy','candidate','pins_now','_extend_report'}
    require(set(function.__globals__)==set(old)|{'_extend_report'}
        and all(function.__globals__[k] is v for k,v in old.items() if k not in allowed),'full_worker_globals')
    require(function.__globals__['lazy'].predict is _reference and function.__globals__['candidate'].predict is _candidate
        and function.__globals__['pins_now'] is pins_now and function.__globals__['_extend_report'] is _extend_report,
        'complete_component_bindings')
    return {'schema':SCHEMA,'original_worker_AST_sha256':_ORIGINAL_AST,
        'inverse_AST_only_outside_context_to_public_status_label_final_audit_and_receipt_counts':True,
        'complete_component':component.source_proof(),
        'initial_context_calls_per_sample':2,'sample_start_precedes_all_initial_context_and_scope_work':True,
        'initial_evidence_load_and_all_checks_in_whole':True,
        'first_saved_before_lazy_target_read':True,'comparison_to_v2_only_after_all_predictions':True,
        'per_sample_cycle_cleanup_certified':False,'complete_request100ms_certified':False}


def _extend_report(output,plan,ledger,report):
    # Reuse the already checked complete saved comparator. Its legacy parameter
    # name refers to an audit-only target, never a predictor input. Relabel every
    # version-specific output so it cannot be mistaken for v1 versus v2 timing.
    audit_plan={'rows':{key:{'comparison_only_v1_prediction':row['comparison_only_v2_prediction']}
        for key,row in plan['rows'].items()}}
    result=prior._extend_report(output,audit_plan,ledger,report)
    checks=result.pop('v1_full_output_checks')
    for row in checks:
        if 'comparison_only_v1_prediction' in row:row['comparison_only_v2_prediction']=row.pop('comparison_only_v1_prediction')
        if row['status']=='exact_v1_full_output':row['status']='exact_v2_full_output'
        if row['status']=='unknown_saved_v1_error':row['status']='unknown_saved_v2_error'
    result.update(schema=SCHEMA,source_proof=source_proof(),v2_full_output_checks=checks,
        A_version='original_initial_then_scoped_v2',B_version='same_scope_initial_and_predict',
        initial_context_caller_separate_unchanged_inside_whole=False,
        both_initial_context_constructions_and_fact_comparisons_inside_each_sample=True,
        worker_seconds_scope='Original core before the added complete saved-output check; whole owned/external wall includes all work.',
        comparison_with_previous_predict_only_ABBA_valid=False)
    return result


def pins_now(output,plan):
    require(plan['schema']==SCHEMA and plan['order']==list(ORDER)
        and plan['source_proof']==source_proof(),'initial_component_scope')
    return frozen.pins_now(output,plan)


def prepare(output):
    frozen.base.no_execution_extensions();prior._pure_receipt(PURE,PURE_COUNT)
    require(sha(SOURCE/'plan.json')==SOURCE_PLAN,'initial_source_plan')
    saved=read(SOURCE/'plan.json');files=frozen.image.source_closure(ROOT,(MODULE,PURE_MODULE,TEST[:-3].replace('/','.')))
    for path,digest in saved['source_sha256'].items():
        require(sha(path)==digest==sha(SOURCE/saved['source_archive'][path]),'initial_source_archive')
        files[str(Path(path).relative_to(ROOT))]=Path(path).read_bytes()
    for path,digest in saved['evidence_sha256'].items():require(sha(path)==digest,'frozen_initial_evidence')
    old=read(PREVIOUS/'plan.json');full=read(FULL/'final_receipt.json');fullrows=read(FULL/'rows.json')
    require(sha(PREVIOUS/'plan.json')==PREVIOUS_PLAN and sha(PREVIOUS/'report.json')==PREVIOUS_REPORT
        and sha(FULL/'plan.json')==source.PREVIOUS_PLAN,'fixed_source_plans')
    require(full['status']=='exact_all96_original_checks_and_full_outputs' and full['full_output_exact']==96
        and full['unknown_or_difference']==0 and full['actual_collection_data_checks']==226
        and full['actual_known_collection_data']==192 and full['source_changed']==[],'full96_closed')
    output.mkdir(exist_ok=False);pins,archives=prior._archive(output,files)
    evidence={**old['evidence_sha256'],**saved['evidence_sha256']};rows=copy.deepcopy(old['rows'])
    for key in ORDER:
        comparator=fullrows[key]['prediction'];require(comparator==ref(comparator['path']),'fixed_v2_comparator')
        rows[key].pop('comparison_only_v1_prediction',None)
        rows[key]['comparison_only_v2_prediction']=comparator;evidence[comparator['path']]=comparator['sha256']
    for folder,names in ((SOURCE,('plan.json','source_preparation.json')),
        (FULL,('plan.json','final_receipt.json','rows.json','external_application_wall.json')),
        (PREVIOUS,('plan.json','report.json','receipt.json','external_application_wall.json')),
        (PURE,('receipt.json','tests.xml','external_application_wall.json'))):
        for name in names:evidence[str(folder/name)]=sha(folder/name)
    plan={**old,'schema':SCHEMA,'source_sha256':pins,'source_archive':archives,'evidence_sha256':evidence,
        'rows':rows,'source_proof':source_proof(),'preparation_model_calls':0,'preparation_raw_decodes':0,
        'scope':'A original two-owner build_initial and scoped-v2 prediction; B fresh scoped-v2 construction, same original two-owner guards/comparison, same-scope prediction.',
        'timing':'Every sample includes both owner context constructions and fact equality plus model. Input decode/action precheck remains outside sample but inside whole120, with all hashes, exports, lazy/v2 readback and process cleanup. Default GC; no per-sample cycle reclamation certificate.',
        'comparison_order':'Each complete returned prediction is saved before the lazy target is read. Additional scoped-v2 target comparisons occur after all24 callbacks. This order is source-bound, not independent timing authority; neither target enters a callback.',
        'not_comparable_to_previous_predict_only_samples':True,
        'failure':'All24 rows remain including per-call initial-context exceptions. No new retry/action search or budget extension.'}
    write(output/'plan.json',plan)
    write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'source_count':len(pins),'focused_pure_tests':PURE_COUNT,'component_pure_tests':22,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--expected-plan');args=parser.parse_args()
    output=args.output.resolve();frozen.base.no_execution_extensions()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(sys.stdin.readline()==args.expected_plan+'\n','owned_admission')
        try:
            worker_function()(output,args.expected_plan)
            require(read(output/'report.json')['status']=='passed_fixed_six_ABBA24_complete_prediction','complete24_gate')
        except BaseException:write(output/'failure.json',{'status':'unknown_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute and sha(output/'plan.json')==args.expected_plan,'reviewed_execute')
    with (output/'execution_claim').open('x'):pass
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',args.expected_plan]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        process=frozen.bounded_windows_job.run(command,timeout=frozen.base.remaining(time.monotonic()-BOOT),
            stdout=out,stderr=err,admission=args.expected_plan,cwd=ROOT)
    wall=time.monotonic()-BOOT;passed=process['status']=='exited' and process['exitcode']==0 and wall<=LIMIT
    write(output/'bounded_execution.json',{'status':'completed' if passed else 'unknown_failed_or_timeout',
        'process':process,'command':command,'whole_python_before_receipt_seconds':wall,'shared_limit_seconds':LIMIT})
    return 0 if passed and time.monotonic()-BOOT<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
