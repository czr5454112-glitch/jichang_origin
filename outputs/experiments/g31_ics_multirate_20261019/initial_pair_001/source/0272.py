"""Fixed6 ABBA24 whole initial+predict draft; root dispatch only after review."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import copy
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace
from . import measure_initial_scoped_public_inputs_six as prior
from . import public_live_obligation_owned_bundle as component
from . import prepare_live_obligation_owned_bundle as source

ROOT, OUT, ORDER, LIMIT = prior.ROOT, prior.OUT, prior.ORDER, prior.LIMIT
frozen = prior.frozen
MODULE = 'scripts.experiments.g31_ics_circulation.measure_owned_initial_bundle_six'
TEST = 'tests/test_g31_circulation_owned_initial_bundle_cost.py'
PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_owned_initial_bundle_cost_pure'
PURE = OUT/'owned_initial_bundle_cost_pure_002'
PURE_COUNT = 25
SOURCE = OUT/'owned_initial_bundle_source_prepare_001'
SOURCE_PLAN = '27b3fa03e16428512b440e3bba2fafc403b95b053342aedf03e77d73bc406cb5'
PREVIOUS = OUT/'initial_scoped_inputs_six_cost_prepare_001'
PREVIOUS_PLAN = '20522f420b69367c2cd09ebc1d9a6774b5b4853970cdde363ac637b3cfe3bf31'
PREVIOUS_REPORT = 'b1b043f9df91ae0dbc1fa16c7d9bd6490c82316bc51707850747dbb0fed92898'
FULL = source.PREVIOUS
SCHEMA = 'g31.initial_scoped_vs_owned_bundle.ABBA6.v1'
sha, read, write, ref, require = prior.sha, prior.read, prior.write, prior.ref, prior.require


def _reference(public, action):
    require(action is public['action'], 'same_action_object')
    return component.reference(public)


def _candidate(public, action):
    require(action is public['action'], 'same_action_object')
    return component.predict(public)


def worker_function():
    old=prior.worker_function()
    namespace={**old.__globals__,'lazy':SimpleNamespace(predict=_reference),
        'candidate':SimpleNamespace(predict=_candidate),'pins_now':pins_now,
        '_extend_report':_extend_report}
    function=FunctionType(old.__code__,namespace,old.__name__,old.__defaults__,old.__closure__)
    function.__kwdefaults__=old.__kwdefaults__
    return function


def source_proof():
    old=prior.worker_function(); new=worker_function(); allowed={'lazy','candidate','pins_now','_extend_report'}
    require(new.__code__ is old.__code__ and new.__defaults__ is old.__defaults__
        and new.__closure__ is old.__closure__ and new.__kwdefaults__ is old.__kwdefaults__
        and set(new.__globals__)==set(old.__globals__)
        and all(new.__globals__[k] is v for k,v in old.__globals__.items() if k not in allowed),'whole_worker_code_and_globals')
    require(new.__globals__['lazy'].predict is _reference and new.__globals__['candidate'].predict is _candidate
        and new.__globals__['pins_now'] is pins_now and new.__globals__['_extend_report'] is _extend_report,
        'four_private_bindings')
    return {'schema':SCHEMA,'historical_worker_proof':prior.source_proof(),
        'original_complete_component_worker_code_unchanged':True,
        'changed_private_globals_only':sorted(allowed),'component':component.source_proof(),
        'A':'current initial_scope.predict, original bundle deepcopy',
        'B':'fresh owned-bundle scope, retained full revalidation deepcopy and protocol copy',
        'both_samples_start_before_scope_initial_guards_fact_comparisons_and_model':True,
        'input_decode_action_precheck_all_exports_all_target_checks_cleanup_in_whole':True,
        'save_before_lazy_target_read_retained':True,'additional_initial_scope_target_after_all24_callbacks':True,
        'target_read_order_proof':'Source order only, not an independent read-time authority',
        'per_sample_cycle_cleanup_certified':False,'complete_request100ms_certified':False}


def _extend_report(output,plan,ledger,report):
    audit_plan={'rows':{key:{'comparison_only_v2_prediction':row['comparison_only_initial_scope_prediction']}
        for key,row in plan['rows'].items()}}
    result=prior._extend_report(output,audit_plan,ledger,report)
    checks=result.pop('v2_full_output_checks')
    for row in checks:
        if 'comparison_only_v2_prediction' in row:
            row['comparison_only_initial_scope_prediction']=row.pop('comparison_only_v2_prediction')
        if row['status']=='exact_v2_full_output': row['status']='exact_initial_scope_full_output'
        if row['status']=='unknown_saved_v2_error': row['status']='unknown_saved_initial_scope_error'
    result.update(schema=SCHEMA,source_proof=source_proof(),initial_scope_full_output_checks=checks,
        A_version='initial_scope_original_bundle_copy',B_version='initial_scope_private_owned_bundle',
        allocation_failure_timing_equivalent=False,
        previous_initial_scope_ABBA_is_historical_not_current_arm_measurement=True)
    return result


def pins_now(output,plan):
    require(plan['schema']==SCHEMA and plan['order']==list(ORDER) and plan['source_proof']==source_proof(),'owned_bundle_scope')
    return frozen.pins_now(output,plan)


def prepare(output):
    frozen.base.no_execution_extensions(); prior.prior._pure_receipt(PURE,PURE_COUNT); source.pure_receipt()
    require(sha(SOURCE/'plan.json')==SOURCE_PLAN,'owned_source_plan')
    saved=read(SOURCE/'plan.json')
    files=frozen.image.source_closure(ROOT,(MODULE,PURE_MODULE,TEST[:-3].replace('/','.')))
    for path,digest in saved['source_sha256'].items():
        require(sha(path)==digest==sha(SOURCE/saved['source_archive'][path]),'owned_source_archive')
        files[str(Path(path).relative_to(ROOT))]=Path(path).read_bytes()
    for path,digest in saved['evidence_sha256'].items(): require(sha(path)==digest,'owned_source_evidence')
    require(sha(PREVIOUS/'plan.json')==PREVIOUS_PLAN and sha(PREVIOUS/'report.json')==PREVIOUS_REPORT
        and sha(FULL/'plan.json')==source.PREVIOUS_PLAN and sha(FULL/'final_receipt.json')==source.PREVIOUS_FINAL,
        'historical_plan_result_identities')
    old=read(PREVIOUS/'plan.json'); actual=read(PREVIOUS/'report.json'); final=read(FULL/'final_receipt.json')
    require(actual['exact']==24 and actual['unknown']==0 and actual['source_changed']==[]
        and final['full_output_exact']==96 and final['unknown_or_difference']==0
        and final['actual_collection_data_checks']==226 and final['actual_known_collection_data']==192
        and final['early_ordinal_mapping_certified'] and final['early_unbound_invocations']==0
        and final['source_changed']==[],'historical_complete_outputs')
    rows=copy.deepcopy(old['rows']); fullrows=read(FULL/'rows.json')
    evidence={**old['evidence_sha256'],**saved['evidence_sha256']}
    for key in ORDER:
        target=fullrows[key]['prediction']; require(target==ref(target['path']),'full96_comparator')
        rows[key].pop('comparison_only_v2_prediction',None)
        rows[key]['comparison_only_initial_scope_prediction']=target; evidence[target['path']]=target['sha256']
    for folder,names in ((SOURCE,('plan.json','source_preparation.json')),
        (FULL,('plan.json','final_receipt.json','rows.json','external_application_wall.json')),
        (PREVIOUS,('plan.json','report.json','receipt.json','external_application_wall.json')),
        (PURE,('receipt.json','tests.xml','external_application_wall.json'))):
        for name in names: evidence[str(folder/name)]=sha(folder/name)
    output.mkdir(exist_ok=False); pins,archives=prior.prior._archive(output,files)
    plan={**old,'schema':SCHEMA,'status':'prepared_unexecuted','source_sha256':pins,'source_archive':archives,
        'evidence_sha256':evidence,'rows':rows,'source_proof':source_proof(),
        'scope':'A current full initial-scope component; B same scope plus only one private bundle copy removal per projection helper call. No validation/observation cache.',
        'timing':'Both samples include fresh scope, all A/B initial guards and fact comparisons, model call, and caller return. Source proof/hashes, input decode/action precheck, all24 exports and lazy/initial-scope exact readbacks, source exit, default-GC process cleanup share120. No per-sample destruction claim.',
        'comparison_order':'Complete returned prediction saved before lazy target read; additional initial-scope targets checked after all24 model callbacks. Targets are never predictor arguments.',
        'failure':'All24 rows retained. Exceptions, unknowns, export errors and mismatch prevent speed summary and success; no retries, extension or row replacement.',
        'allocation_failure_timing_equivalent':False,'preparation_model_calls':0,'preparation_raw_decodes':0}
    write(output/'plan.json',plan)
    write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'source_count':len(pins),'focused_pure_tests':PURE_COUNT,'component_pure_tests':26,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def main():
    # Keep the reviewed owned launcher, admission, failure/receipt and full24
    # status gate bytecode. No new cleanup or timing behavior is invented here.
    function=FunctionType(prior.main.__code__,{**prior.main.__globals__,'BOOT':BOOT,'MODULE':MODULE,
        'prepare':prepare,'worker_function':worker_function},prior.main.__name__,prior.main.__defaults__,prior.main.__closure__)
    function.__kwdefaults__=prior.main.__kwdefaults__
    return function()


if __name__=='__main__': raise SystemExit(main())
