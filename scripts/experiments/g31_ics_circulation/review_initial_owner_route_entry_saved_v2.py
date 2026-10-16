"""Separate saved-only recovery audit; failed151-source producer stays failed.

The repaired verifier runs all original endpoint/physical/RPC/gate/outbox checks
once. A passive visit uses that same decoded branch for summary, not another
raw scan. No producer receipt/import-exit check is invented or overwritten.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import json
import math
from pathlib import Path
import sys
import traceback
from types import FunctionType
from . import bounded_windows_job
from . import verify_initial_owner_route_entry_campaign_v2 as verifier
from . import review_initial_owner_route_gate_saved_v2 as prior

c=verifier.c
PLAN='d37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097'
EXTERNAL='665be69f6ffdf7c673c887568feb9b1f9d7420fce9f5298a2fed6d4bd8179239'
OLD_REPORT='95361ce13acfd4711a3bc3c68fe37fb51aae1a9a841dd56ed3ddaae693bc9849'
PURE=c.OUT/'initial_entry_verifier_v2_pure_001/receipt.json'
PURE_SHA='79fd9c83d4965fd3a3ef987369dcc8aa862841a55497505cd70622e545f64946'
LIMIT=180.
METADATA=('campaign.json','source_preparation.json','root_prelaunch_review_001.json','root_ready_001.json',
    'branch_ledger.json','predictor_lifetime.json','run_acceptance.json','external_launch_receipt.json',
    'external_application_wall.json','stderr.log','stdout.log','execution_claim.json','worker_claim.json')
MISSING=('receipt.json','verification.json')


def producer_state(source):
    """Small metadata/source binding only. No new authority or native read."""
    plan=c.verify_plan(source,PLAN)
    c.require(len(plan['source_sha256'])==151 and len(plan['compiled_source_archive_sha256'])==67,
              'entry_review_source_domain')
    c.require(all(not (source/name).exists() for name in MISSING),'entry_review_producer_missing_files_changed')
    evidence={name:c.reference(source/name) for name in METADATA}
    outer=c.read(source/'external_application_wall.json');launch=c.read(source/'external_launch_receipt.json')
    ready=c.read(source/'root_ready_001.json');ledger=c.read(source/'branch_ledger.json')
    c.require(evidence['external_application_wall.json']['sha256']==EXTERNAL and
        outer['status']=='application_failed_or_unknown' and outer['exit_code']==1 and
        outer['campaign_sha256']==PLAN and outer['evidence_unchanged'] is True and
        type(outer['whole_python_application_seconds']) in (int,float) and
        math.isfinite(outer['whole_python_application_seconds']) and 0<outer['whole_python_application_seconds']<=600,
        'entry_review_failed_external')
    c.require(launch['campaign_sha256']==PLAN and launch['status']=='unknown_campaign_process' and
        launch['process']['status']=='exited' and launch['process']['exitcode']==1 and
        launch['process']['windows_job_kill_on_close'] is True and
        launch['process']['child_released_only_after_job_assignment'] is True,'entry_review_failed_owned_process')
    c.require(ready['campaign_sha256']==PLAN and ready['wrapper_sha256']==outer['wrapper_sha256'] and
        c.sha(ready['root_review']['path'])==ready['root_review']['sha256'] and
        c.sha(plan['environment']['interpreter'])==outer['python_sha256']==plan['environment']['interpreter_sha256'] and
        c.sha(c.ROOT/'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_entry_campaign.py')==
            outer['launcher_sha256'],'entry_review_launch_source')
    c.require(launch['command']==[plan['environment']['interpreter'],'-m',
        'scripts.experiments.g31_ics_circulation.initial_owner_route_entry_campaign','--output',str(source),
        '--campaign-sha256',PLAN,'--admission',PLAN],'entry_review_process_command')
    for name,digest in launch['artifacts'].items():
        c.require(c.sha(source/name)==digest,'entry_review_launch_artifact')
    error=(source/'stderr.log').read_text(encoding='utf8')
    c.require("NameError: name 'Path' is not defined" in error and 'verify_initial_owner_route_campaign_v3.py' in error,
              'entry_review_preserved_failure_trace')
    c.require(list(ledger)==plan['row_order'] and len(ledger)==18 and all(row['status']=='raw_saved'
        for row in ledger.values()),'entry_review_all18_raw_ledger')
    return plan,evidence,outer,ledger


def prepare(source,output):
    output.mkdir(parents=True,exist_ok=False)
    producer,evidence,outer,ledger=producer_state(source)
    c.require(c.sha(PURE)==PURE_SHA,'entry_review_pure_identity')
    pure=c.read(PURE)
    c.require(pure['status']=='passed' and pure['tests']==12 and pure['source_changed']==[] and
        pure['original151_current_and_archive_unchanged'] is True and
        c.sha(PURE.parent/'tests.xml')==pure['XML_sha256'],'entry_review_repair_pure')
    for name,digest in pure['source_sha256'].items():
        c.require(c.sha(c.ROOT/name)==digest and c.sha(PURE.parent/'source'/name)==digest,'entry_review_pure_source')
    files=c.image.source_closure(c.ROOT,(__package__+'.review_initial_owner_route_entry_saved_v2',
        __package__+'.run_initial_owner_route_entry_verifier_v2_pure',
        'tests.test_g31_circulation_initial_owner_route_entry_verifier_v2'))
    sources,archive={},{}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        sources[str(c.ROOT/name)]=c.image.sha_bytes(data);archive[str(c.ROOT/name)]=str(path.relative_to(output))
    oldpath=c.OUT/'initial_owner_route_gate_independent_actual_review_001/report.json'
    c.require(c.sha(oldpath)==OLD_REPORT,'entry_review_previous_summary')
    plan={'schema':'g31.initial_entry.independent_saved_recovery_plan.v1','source_directory':str(source),
        'producer_campaign_sha256':PLAN,'producer_external_sha256':EXTERNAL,'evidence':evidence,
        'producer_raw':{key:row['raw'] for key,row in ledger.items()},
        'missing_producer_files':list(MISSING),'producer_status':'failed_preserved',
        'source_sha256':sources,'source_archive':archive,'repair_source_proof':verifier.source_proof(),
        'repair_pure_receipt':c.reference(PURE),'repair_pure_XML':c.reference(PURE.parent/'tests.xml'),
        'previous_gate_summary':c.reference(oldpath),
        'environment':{'python':sys.executable,'sha256':c.sha(sys.executable)},
        'fixed_owned_seconds':LIMIT,'cost_reference_seconds':53.934451,
        'cost_basis':'Prior full gate002 saved18 review took53.934451s. This source18 gzip totals12,526,972 bytes versus prior12,969,070.180s includes imports/pins/full unchanged checks/same-decoded summary/export. No duration guarantee.',
        'no_native_or_predictor':True,'new_producer_receipt_or_exit_import_proof':False,
        'command_requires_plan_sha256':True,'status':'prepared_unexecuted'}
    c.write(output/'plan.json',plan);expected=c.sha(output/'plan.json')
    verify_prepared(output,expected)
    c.write(output/'source_review.json',{'status':'no_concrete_namespace_repair_blocker',
        'scope':'Read repair and old defining-v3/gate/entry functions. Twelve bounded pure regressions executed; no branch audit yet.',
        'repair_source':c.reference(Path(verifier.__file__)),'proof':verifier.source_proof(),
        'pure':c.reference(PURE),'original151_unchanged':True,'producer_failure_preserved':True})
    c.write(output/'preparation.json',{'status':'prepared_review_pending','plan':c.reference(output/'plan.json'),
        'audit_source_count':len(sources),'producer_source_count':151,'compiled_archive_count':67,
        'execute_command':[sys.executable,'-m',__package__+'.review_initial_owner_route_entry_saved_v2',
            '--execute','--output',str(output),'--plan-sha256',expected],
        'owned_seconds':LIMIT,'native_calls':0,'predictor_calls':0,'full_audit_dispatched':False})


def verify_prepared(output,expected):
    c.require(c.sha(output/'plan.json')==expected,'entry_review_plan_sha')
    plan=c.read(output/'plan.json');source=Path(plan['source_directory']).resolve()
    c.require(plan['fixed_owned_seconds']==LIMIT and plan['producer_campaign_sha256']==PLAN and
        plan['producer_external_sha256']==EXTERNAL and plan['missing_producer_files']==list(MISSING) and
        plan['repair_source_proof']==verifier.source_proof(),'entry_review_plan_contract')
    for path,digest in plan['source_sha256'].items():
        c.require(c.sha(path)==digest and c.sha(output/plan['source_archive'][path])==digest,'entry_review_audit_source')
    for name,ref in plan['evidence'].items():
        c.require(c.reference(source/name)==ref,'entry_review_producer_evidence_drift')
    c.require(all(not (source/name).exists() for name in MISSING),'entry_review_missing_receipts_rewritten')
    for key in ('repair_pure_receipt','repair_pure_XML','previous_gate_summary'):
        ref=plan[key];c.require(c.sha(ref['path'])==ref['sha256'],'entry_review_reference_changed')
    c.require(c.sha(plan['environment']['python'])==plan['environment']['sha256'],'entry_review_python_changed')
    return plan


def actual_loaded(producer,audit):
    overlap=set(producer['source_sha256'])&set(audit['source_sha256'])
    c.require(all(producer['source_sha256'][key]==audit['source_sha256'][key] for key in overlap),
              'entry_review_different_producer_import')
    return c.check_loaded_sources({**producer,'source_sha256':{
        **producer['source_sha256'],**audit['source_sha256']}})


def inspect_saved(output,expected):
    started=time.perf_counter_ns();audit=verify_prepared(output,expected)
    source=Path(audit['source_directory']).resolve()
    plan,evidence,outer,ledger=producer_state(source)
    loaded_entry=actual_loaded(plan,audit)
    c.require(audit['producer_raw']=={key:row['raw'] for key,row in ledger.items()},'entry_review_raw_manifest_changed')
    life=c.read(source/'predictor_lifetime.json');samples={row['request_id']:row for row in life['ledger']};rows={}
    def visit(raw,row,key):
        result=verifier.verify_branch(raw,row,key)
        rows[key]=prior.details(raw,result,samples)
        rows[key]['raw']=ledger[key]['raw']  # Original verify_saved already hashed this file before decoding.
        return result
    readback=FunctionType(verifier.verify_saved.__code__,{**verifier.verify_saved.__globals__,'verify_branch':visit},
        verifier.verify_saved.__name__,verifier.verify_saved.__defaults__,verifier.verify_saved.__closure__)
    readback.__kwdefaults__=verifier.verify_saved.__kwdefaults__
    c.require(readback.__code__ is verifier.verify_saved.__code__,'entry_review_no_guard_rewrite')
    computed=readback(source,PLAN)
    for key,value in computed['rows'].items():
        rows.setdefault(key,{'root':value['root'],'failure':value.get('failure')})
        rows[key]['branch_attempt']=value['branch_attempt']
    c.require(list(rows)==plan['row_order'] and len(rows)==18,'entry_review_denominator')
    old=c.read(audit['previous_gate_summary']['path']);comparisons={}
    for key,row in rows.items():
        before=old['rows'][key];oldhop=before.get('hop');newhop=row.get('hop')
        both=type(oldhop) is dict and type(newhop) is dict
        comparisons[key]={'gate002_warm_ms':before['root'].get('warm_ms'),'entry_warm_ms':row['root'].get('warm_ms'),
            'gate002_choice':before.get('choice'),'entry_choice':row.get('choice'),
            'gate002_hop':oldhop,'entry_hop':newhop,
            'same_hop_endpoints':both and (oldhop.get('from'),oldhop.get('to'))==(newhop.get('from'),newhop.get('to')),
            'observed_physical_clock_difference':newhop['observed_at']-oldhop['observed_at'] if both else None,
            'physical_clock_difference_is_not_compute_saving':True,
            'gate002_partition_ms':before.get('warm_boundary_partition_ms'),
            'entry_partition_ms':row.get('warm_boundary_partition_ms'),
            'gate002_encoded_bytes':before.get('encoded_root_bytes'),'entry_encoded_bytes':row.get('encoded_root_bytes'),
            'same_business_completion_vector':verifier.exact(before.get('business',{}).get('completion'),
                row.get('business',{}).get('completion')),
            'same_recorded_final_seal':before['native_state_sha256']==row.get('native_state_sha256')}
    # New checks prove the saved artifacts now; they cannot manufacture the
    # producer's missing source-import exit check or terminal success receipt.
    producer_state(source);verify_prepared(output,expected);loaded_exit=actual_loaded(plan,audit)
    for ref in audit['producer_raw'].values():c.require(c.sha(ref['path'])==ref['sha256'],'entry_review_raw_exit_drift')
    c.write(output/'recovered_verification.json',computed)
    normal={key:value for key,value in computed['pairs'].items() if key.startswith('normal/')}
    report={'schema':'g31.initial_entry.independent_saved_recovery.v1',
        'status':'passed_complete_saved_endpoint_physical_RPC_gate_outbox_audit',
        'original_producer_failure_preserved':True,'original_producer_exit_code':1,
        'original_producer_receipt':'missing_not_retroactively_created',
        'original_producer_verification':'missing_new_recovered_verification_is_separate',
        'producer_loaded_import_entry_exit_proof':'not_recorded_in_missing_producer_receipt_unknown',
        'audit_entry_exit_proof_is_separate':True,'evidence':evidence,
        'repaired_verification':c.reference(output/'recovered_verification.json'),
        'audit_plan':c.reference(output/'plan.json'),'source_count':151,'compiled_archive_count':67,
        'loaded_review_entry':loaded_entry,'loaded_review_exit':loaded_exit,
        'branches':18,'closed_roots':computed['closed_roots'],'open_or_unknown_roots':computed['open_or_unknown_roots'],
        'roots_at_most_100ms':sum(row['root'].get('observed_within_100ms',False) for row in rows.values()),
        'prediction_counts':computed['prediction_counts'],'RPC_requests':computed['predictor_requests'],
        'predictor_protocol_closed':computed['predictor_protocol_closed'],
        'predictor_startup_ms':computed['predictor_startup_ms'],
        'predictor_close_with_cleanup_ms':computed['predictor_close_with_cleanup_ms'],
        'full_worker_setup_through_predictor_ready_ms':(life['ready_ns']-life['worker_setup_started_ns'])/1e6 if 'ready_ns' in life else None,
        'whole_failed_producer_python_seconds':outer['whole_python_application_seconds'],
        'whole_failed_producer_unamortized_sensitivity_ms_per_root':outer['whole_python_application_seconds']*1000,
        'gate_steps':sum(row.get('gate',{}).get('steps',0) for row in rows.values()),
        'gate_skips':sum(row.get('gate',{}).get('skips',0) for row in rows.values()),
        'root_encoded_bytes':sum(row.get('encoded_root_bytes',0) for row in rows.values()),
        'normal_pairs':{'count':len(normal),'strict_nonregression_count':sum(
            pair['all_five_strict_nonregression'] is True for pair in normal.values()),
            'unknown_count':sum(pair['all_five_strict_nonregression'] is None for pair in normal.values())},
        'rows':rows,'pairs':computed['pairs'],'previous_gate002_descriptive_reference':audit['previous_gate_summary'],
        'previous_gate002_descriptive_comparison':comparisons,
        'limits':['Producer failed after saved raw export; its absence of final receipt/loaded-import exit check remains unknown.',
            'This separate audit reruns unchanged check code with repaired globals, not native/RPC/model execution.',
            'All current audit entry/exit sources and producer artifacts are independently bound; no producer receipt is minted.',
            'Earlier physical entry observation changes root admission IDs and may affect continuation. No raw tape equality or ABBA speedup claim.',
            'Physical observed_at differences are logical clocks, never subtracted from compute wall.',
            'All cold/native/shared/RPC/codec costs remain charged. Additional saved audit cost is separate and never deducted.',
            'Finite initial-A two-choice experiment only; not original business100ms, full32 or two-machine certification.'],
        'new_native_calls':0,'new_predictor_calls':0,'review_seconds_before_report':(time.perf_counter_ns()-started)/1e9}
    c.write(output/'report.json',report)
    print(json.dumps({key:report[key] for key in ('status','original_producer_failure_preserved','closed_roots',
        'open_or_unknown_roots','roots_at_most_100ms','gate_steps','gate_skips','normal_pairs','review_seconds_before_report')}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true')
    p.add_argument('--worker',action='store_true');p.add_argument('--plan-sha256');a=p.parse_args();output=a.output.resolve()
    if a.prepare:prepare(a.source.resolve(),output);return 0
    if a.worker:
        c.require(sys.stdin.readline()==a.plan_sha256+'\n','entry_review_job_admission')
        try:inspect_saved(output,a.plan_sha256)
        except BaseException:
            c.write(output/'audit_failure.json',{'status':'failed_or_unknown_separate_audit',
                'producer_failure_preserved':True,'error':traceback.format_exc()});raise
        return 0
    if not a.execute:raise ValueError('entry_review_explicit_action')
    verify_prepared(output,a.plan_sha256)
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'plan_sha256':a.plan_sha256,'fixed_seconds':LIMIT},stream)
    command=[sys.executable,'-m',__package__+'.review_initial_owner_route_entry_saved_v2','--output',str(output),
        '--worker','--plan-sha256',a.plan_sha256]
    remaining=LIMIT-(time.monotonic()-BOOT)
    if remaining<=0:raise TimeoutError('entry_review_budget_before_worker')
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=remaining,admission=a.plan_sha256,stdout=out,stderr=err,cwd=c.ROOT)
    c.write(output/'bounded_execution.json',{'process':process,'command':command,'source':c.reference(__file__),
        'fixed_seconds':LIMIT,'post_interpreter_before_final_receipt_seconds':time.monotonic()-BOOT,
        'new_native_calls':0,'new_predictor_calls':0,'original_producer_failure_preserved':True,
        'report':c.reference(output/'report.json') if (output/'report.json').is_file() else None,
        'external_launch_through_exit_clock_required':True})
    return 0 if process['status']=='exited' and process['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
