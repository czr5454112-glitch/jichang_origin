"""One bounded saved-only readback; no native session, RPC or prediction."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from types import FunctionType
from . import bounded_windows_job
from . import verify_initial_owner_route_gate_campaign_v2 as verifier

c=verifier.c
PLAN='659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4'
EXTERNAL='f62581487c60d949c627cbeb9fded699bb8e0606d6fa9e8990acb8aacced1b6d'
OLD_REPORT='6619c11ca5aca23cb7bb083a7198d5fd6b56e9b7697a5c700b12a93628e641a5'
LIMIT=180.


def actual_loaded(plan,review_digest):
    extra={str(Path(__file__).resolve()):review_digest}
    return c.check_loaded_sources({**plan,'source_sha256':{**plan['source_sha256'],**extra}})


def details(raw,result,samples):
    record=raw['root_records'][0] if raw['root_records'] else None
    row={'specification':raw['specification'],'root':result['root'],'failure':raw['failure'],
        'gate':result['observation_gate'],'query_replay':result['query_replay'],
        'business':{k:v for k,v in result['business'].items() if k in
            ('status','completion','completion_sum','business_complete','common_horizon_complete',
             'initial_actual_next','same_L_two_returns_and_two_reloads','audit')},
        'native_state_sha256':raw['native_state_sha256']}
    if record is None:return row
    root=record['value']['evidence'];events=root['events'];start=root['root_started_ns']
    collection=next(e for e in events if e['stage']=='actual_A_collection')
    checks=[e for e in events if e['stage']=='final_local_and_receiver_check']
    boundaries=[start,collection['wall_ns'],checks[0]['wall_ns'] if checks else collection['wall_ns'],
        events[-1]['wall_ns'],record['finalization_started_ns'],record['value']['body_finished_ns'],record['outside_return_ns']]
    c.require(all(type(x) is int and x>=0 for x in boundaries) and boundaries==sorted(boundaries),'review_boundary_order')
    names=('admission_through_A_collection','collection_through_final_local_check',
        'postcheck_through_last_observation','last_observation_to_finalization',
        'evidence_body_construction_normalization_encoding','outside_return_ledger_codec_tail')
    partition={name:b-a for name,a,b in zip(names,boundaries,boundaries[1:])}
    c.require(sum(partition.values())==record['warm_caller_elapsed_ns']==boundaries[-1]-start,'review_full_root_partition')
    trace=raw['outbox_query_trace'];proof=root['runtime_query_proof']
    row.update(choice=root['choice'],command_id=root['command_id'],hop=root['hop'],
        warm_boundary_partition_ms={k:v/1e6 for k,v in partition.items()},
        event_counts=dict(Counter(e['stage'] for e in events)),root_event_count=len(events),
        encoded_root_bytes=record['ledger']['bytes'],
        query_trace={'queries':len(trace['reads']),'ACK_bodies':len(trace['ack_bodies']),
            'new_representation_without_handler_change':sum(q['body_is_new'] and not q['ack_changed'] for q in trace['reads']),
            'root_queries':proof['checkpoint']['query_prefix'],'root_ACK_bodies':len(proof['trace']['ack_bodies'])},
        native_setup_before_root_ms=(start-raw['clocks']['branch_setup_started_ns'])/1e6,
        initial_collection_status=collection['value']['status'],
        baseline_or_submission_overrides=[e['stage'] for e in events if 'overrun' in e['stage']],RPC=None)
    sample=samples.get(root['root_id'])
    if sample:
        payload=sample['response']['payload'];budget=payload['budget']
        row['RPC']={'sequence':sample['sequence'],'counts':payload['counts'],'selection':payload['selection'],
            'worker_compute_wall_ms':(budget['worker_finished_ns']-budget['worker_started_ns'])/1e6,
            'caller_body_ms':sample['caller_elapsed_ns']/1e6,'atomic_overrun':budget['atomic_overrun'],
            'baseline_status':payload['baseline']['status'] if payload['baseline'] else None,
            'candidate_status':payload['predictions'][1]['status'] if payload['predictions'] else None}
    return row


def inspect_saved(source,output):
    started=time.perf_counter_ns();own=c.sha(__file__)
    plan=c.verify_plan(source,PLAN);loaded_entry=actual_loaded(plan,own)
    c.require(len(plan['source_sha256'])==141 and len(plan['compiled_source_archive_sha256'])==67,'review_source_domain')
    names=('campaign.json','source_preparation.json','root_prelaunch_review_001.json','root_ready_001.json',
        'branch_ledger.json','receipt.json','verification.json','predictor_lifetime.json','run_acceptance.json',
        'external_launch_receipt.json','external_application_wall.json')
    evidence={name:c.reference(source/name) for name in names}
    receipt=c.read(source/'receipt.json');outer=c.read(source/'external_application_wall.json')
    launch=c.read(source/'external_launch_receipt.json');ledger=c.read(source/'branch_ledger.json')
    ready=c.read(source/'root_ready_001.json')
    c.require(evidence['external_application_wall.json']['sha256']==EXTERNAL and
        outer['status']=='application_exited_zero' and outer['exit_code']==0 and outer['evidence_unchanged'] is True
        and outer['campaign_sha256']==PLAN and 0<outer['whole_python_application_seconds']<=600,'review_external')
    c.require(launch['campaign_sha256']==PLAN and launch['status']=='campaign_process_exited'
        and launch['process']['status']=='exited' and launch['process']['exitcode']==0
        and launch['process']['windows_job_kill_on_close'] is True
        and launch['process']['child_released_only_after_job_assignment'] is True,'review_owned_process')
    c.require(ready['campaign_sha256']==PLAN and ready['wrapper_sha256']==outer['wrapper_sha256']
        and c.sha(ready['root_review']['path'])==ready['root_review']['sha256']
        and c.sha(plan['environment']['interpreter'])==outer['python_sha256']==plan['environment']['interpreter_sha256']
        and c.sha(c.ROOT/'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_gate_campaign_v2.py')
            ==outer['launcher_sha256'],'review_launch_source_binding')
    c.require(launch['command']==[plan['environment']['interpreter'],'-m',
        'scripts.experiments.g31_ics_circulation.initial_owner_route_gate_campaign_v2',
        '--output',str(source),'--campaign-sha256',PLAN,'--admission',PLAN],'review_exact_process_command')
    for name,digest in launch['artifacts'].items():c.require(c.sha(source/name)==digest,'review_launch_artifact')
    c.require(receipt['status']=='completed_finite_request_cohort' and receipt['source_changed']==[]
        and receipt['branches']==18 and receipt['campaign_sha256']==PLAN
        and receipt['verification']==evidence['verification.json'],'review_receipt')
    for field in ('loaded_project_sources_entry','loaded_project_sources_exit'):
        c.require(len(receipt[field])==len(set(receipt[field])) and set(receipt[field])<=set(plan['source_sha256']),
            'review_producer_loaded_closure')
    life=c.read(source/'predictor_lifetime.json');samples={s['request_id']:s for s in life['ledger']};rows={}
    def visit(raw,row,key):
        result=verifier.verify_branch(raw,row,key)  # all original checks, unchanged
        rows[key]=details(raw,result,samples)
        rows[key]['raw']=c.reference(source/'raw'/(key+'.json.gz'))
        return result
    readback=FunctionType(verifier.verify_saved.__code__,{**verifier.verify_saved.__globals__,'verify_branch':visit},
        verifier.verify_saved.__name__,verifier.verify_saved.__defaults__,verifier.verify_saved.__closure__)
    c.require(readback.__code__ is verifier.verify_saved.__code__,'review_no_guard_rewrite')
    computed=readback(source,PLAN)
    c.require(c.ordered(computed)==c.ordered(c.read(source/'verification.json')),'review_all_saved_checks_changed')
    for key,value in computed['rows'].items():
        rows.setdefault(key,{'root':value['root'],'failure':value.get('failure')})
        rows[key]['branch_attempt']=value['branch_attempt']
    c.require(list(rows)==plan['row_order'] and len(rows)==18,'review_full_denominator')
    oldpath=c.OUT/'initial_owner_route_v3_independent_actual_review_001/report.json'
    c.require(c.sha(oldpath)==OLD_REPORT,'review_old_descriptive_report')
    old=c.read(oldpath);comparisons={}
    for key,row in rows.items():
        prior=old['rows'][key]
        comparisons[key]={'old_warm_ms':prior['root']['warm_ms'],'new_warm_ms':row['root']['warm_ms'],
            'old_choice':prior['choice'],'new_choice':row.get('choice'),
            'old_encoded_root_bytes':prior['encoded_root_bytes'],'new_encoded_root_bytes':row.get('encoded_root_bytes'),
            'old_partition_ms':prior['warm_boundary_partition_ms'],'new_partition_ms':row.get('warm_boundary_partition_ms'),
            'same_recorded_final_seal':prior['native_state_sha256']==row.get('native_state_sha256')}
    c.verify_plan(source,PLAN);loaded_exit=actual_loaded(plan,own)
    c.require(c.sha(__file__)==own and all(c.reference(source/name)==ref for name,ref in evidence.items()),'review_exit_drift')
    summary={'schema':'g31.initial_owner_route_gate_v2.independent_saved_review.v1',
        'status':'passed_complete_saved_endpoint_physical_RPC_gate_outbox_audit',
        'evidence':evidence,'source_count':141,'compiled_archive_count':67,'review_source':c.reference(__file__),
        'loaded_review_entry':loaded_entry,'loaded_review_exit':loaded_exit,
        'branches':18,'closed_roots':computed['closed_roots'],'open_or_unknown_roots':computed['open_or_unknown_roots'],
        'roots_at_most_100ms':sum(r['root'].get('observed_within_100ms',False) for r in rows.values()),
        'prediction_counts':computed['prediction_counts'],'RPC_requests':computed['predictor_requests'],
        'predictor_protocol_closed':computed['predictor_protocol_closed'],
        'predictor_startup_ms':computed['predictor_startup_ms'],
        'predictor_close_with_cleanup_ms':computed['predictor_close_with_cleanup_ms'],
        'full_worker_setup_through_predictor_ready_ms':(life['ready_ns']-life['worker_setup_started_ns'])/1e6,
        'whole_python_application_seconds':outer['whole_python_application_seconds'],
        'whole_campaign_unamortized_sensitivity_ms_per_root':outer['whole_python_application_seconds']*1000,
        'gate_steps':sum(r.get('gate',{}).get('steps',0) for r in rows.values()),
        'gate_skips':sum(r.get('gate',{}).get('skips',0) for r in rows.values()),
        'root_encoded_bytes':sum(r.get('encoded_root_bytes',0) for r in rows.values()),
        'rows':rows,'pairs':computed['pairs'],'old_v3_descriptive_reference':c.reference(oldpath),
        'old_v3_descriptive_comparison':comparisons,
        'limits':['Six disjoint recorded-boundary intervals sum to each root wall; not isolated function profiles.',
            'Different measurement rounds, deadline-dependent choices and new mandatory proof payloads: no ABBA or causal speedup claim.',
            'RPC and native/physical/shared work remain charged; no division, subtraction or inferred CPU lower bound.',
            'One finite initial-A two-choice firsthop experiment, not full32, original business100ms or all-day success.',
            'Full existing endpoint/physical/RPC plus gate and complete outbox checks rerun; no native reexecution or predictor calls.'],
        'new_native_calls':0,'new_predictor_calls':0,'review_seconds_before_report':(time.perf_counter_ns()-started)/1e9}
    c.write(output/'report.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','closed_roots','open_or_unknown_roots','roots_at_most_100ms',
        'gate_steps','gate_skips','review_seconds_before_report')}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');a=p.parse_args();source=a.source.resolve();output=a.output.resolve()
    if a.worker:
        c.require(sys.stdin.readline()==PLAN+'\n','review_job_admission')
        inspect_saved(source,output);return 0
    output.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m',__package__+'.review_initial_owner_route_gate_saved_v2','--source',str(source),'--output',str(output),'--worker']
    c.write(output/'plan.json',{'source':c.reference(__file__),'campaign':c.reference(source/'campaign.json'),
        'external_sha256':EXTERNAL,'fixed_owned_seconds':LIMIT,'observed_previous_post_cleanup_seconds':60.0311031,
        'estimated_scope':'Single existing complete saved verifier plus same-decoded-object summary; entry/exit pins/export included.',
        'command':command,'native_calls':0,'predictor_calls':0})
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,LIMIT-(time.monotonic()-BOOT)),
            admission=PLAN,stdout=out,stderr=err,cwd=c.ROOT)
    c.write(output/'bounded_execution.json',{'process':process,'command':command,'source':c.reference(__file__),
        'fixed_seconds':LIMIT,'post_interpreter_before_final_receipt_seconds':time.monotonic()-BOOT,
        'new_native_calls':0,'new_predictor_calls':0,'report':c.reference(output/'report.json') if (output/'report.json').is_file() else None})
    return 0 if process['status']=='exited' and process['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
