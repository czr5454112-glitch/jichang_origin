"""Saved-only readback: no NativeSession, projection run, RPC or new prediction."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from . import bounded_windows_job
from . import verify_initial_owner_route_campaign_v3 as verifier

c=verifier.c
PLAN='e5459ab579d76e65c76ee41b0a4bc5f06224f3be0796ace6636ec4d0a2f7b46d'
EXTERNAL='2452e435633edf431209dc161fb5677d74a4ccecf5a2dfcfb16a69672756a18b'


def inspect_saved(source,output):
    started=time.perf_counter_ns()
    plan=c.verify_plan(source,PLAN)
    computed=verifier.verify_saved(source,PLAN)
    saved=c.read(source/'verification.json')
    c.require(c.ordered(computed)==c.ordered(saved),'independent_saved_replay_changed')
    receipt=c.read(source/'receipt.json');outer=c.read(source/'external_application_wall.json')
    launch=c.read(source/'external_launch_receipt.json')
    c.require(receipt['source_changed']==[] and receipt['branches']==18 and
        receipt['verification']==c.reference(source/'verification.json') and
        receipt['campaign_sha256']==PLAN,'saved_receipt_binding')
    c.require(c.sha(source/'external_application_wall.json')==EXTERNAL and
        outer['status']=='application_exited_zero' and outer['exit_code']==0 and
        outer['evidence_unchanged'] is True and outer['campaign_sha256']==PLAN and
        outer['whole_python_application_seconds']<=600 and launch['status']=='campaign_process_exited',
        'external_execution_not_closed')
    for field in ('loaded_project_sources_entry','loaded_project_sources_exit'):
        c.require(len(receipt[field])==len(set(receipt[field])) and
            set(receipt[field])<=set(plan['source_sha256']),'actual_loaded_source_outside_closure')
    life=c.read(source/'predictor_lifetime.json')
    samples={row['request_id']:row for row in life['ledger']}
    ledger=c.read(source/'branch_ledger.json')
    rows={}
    for key in plan['row_order']:
        path=source/'raw'/(key+'.json.gz')
        c.require(ledger[key]['status']=='raw_saved' and ledger[key]['raw']==c.reference(path),'raw_binding')
        with gzip.open(path,'rt',encoding='utf8') as stream:raw=json.load(stream)
        record=raw['root_records'][0];root=record['value']['evidence'];events=root['events']
        start=root['root_started_ns'];end=record['outside_return_ns'];warm=end-start
        collection=next(e for e in events if e['stage']=='actual_A_collection')
        checks=[e for e in events if e['stage']=='final_local_and_receiver_check']
        collection_end=collection['wall_ns']
        check_end=checks[0]['wall_ns'] if checks else collection_end
        last_event=events[-1]['wall_ns'];finalize=record['finalization_started_ns']
        body=record['value']['body_finished_ns']
        boundaries=[start,collection_end,check_end,last_event,finalize,body,end]
        c.require(all(type(x) is int for x in boundaries) and boundaries==sorted(boundaries), 'boundary_order')
        names=('admission_through_A_collection','collection_through_final_local_check',
            'postcheck_through_last_observation','last_observation_to_finalization',
            'evidence_body_construction_normalization_encoding','outside_return_ledger_codec_tail')
        partition={name:b-a for name,a,b in zip(names,boundaries,boundaries[1:])}
        c.require(sum(partition.values())==warm==record['warm_caller_elapsed_ns'],'whole_root_partition')
        row={'specification':raw['specification'],'root':computed['rows'][key]['root'],
            'choice':root['choice'],'command_id':root['command_id'],'hop':root['hop'],
            'warm_boundary_partition_ms':{k:v/1e6 for k,v in partition.items()},
            'event_counts':{s:sum(e['stage']==s for e in events) for s in dict.fromkeys(e['stage'] for e in events)},
            'root_event_count':len(events),'encoded_root_bytes':json.loads(record['return_codec'])['bytes'],
            'initial_collection_status':collection['value']['status'],
            'initial_collection_reasons':collection['value'].get('reasons'),
            'baseline_or_submission_overrides':[{'stage':e['stage'],'at':e['at'],
                'elapsed_ms':(e['wall_ns']-start)/1e6} for e in events if 'overrun' in e['stage']],
            'native_setup_before_root_ms':(start-raw['clocks']['branch_setup_started_ns'])/1e6,
            'branch_attempt':computed['rows'][key]['branch_attempt'],
            'business':{k:v for k,v in computed['rows'][key]['business'].items() if k in
                ('status','completion','completion_sum','business_complete','common_horizon_complete',
                 'initial_actual_next','same_L_two_returns_and_two_reloads','audit')},
            'native_state_sha256':raw['native_state_sha256'],'raw':c.reference(path),
            'failure':raw['failure']}
        sample=samples.get(root['root_id'])
        if sample:
            payload=sample['response']['payload'];budget=payload['budget']
            row['RPC']={'sequence':sample['sequence'],'counts':payload['counts'],'selection':payload['selection'],
                'worker_compute_wall_ms':(budget['worker_finished_ns']-budget['worker_started_ns'])/1e6,
                'worker_through_full_baseline_ms':(budget['baseline_finished_ns']-budget['worker_started_ns'])/1e6,
                'after_baseline_through_candidate_ms':(budget['candidate_finished_ns']-budget['baseline_finished_ns'])/1e6,
                'caller_body_ms':sample['caller_elapsed_ns']/1e6,
                'baseline_status':payload['baseline']['status'],
                'candidate_status':payload['predictions'][1]['status'],
                'atomic_overrun':budget['atomic_overrun'],
                'full32':False}
        else:row['RPC']=None
        rows[key]=row
    c.verify_plan(source,PLAN)
    evidence={name:c.reference(source/name) for name in ('campaign.json','source_preparation.json',
        'root_prelaunch_review_001.json','root_ready_001.json','branch_ledger.json','receipt.json',
        'verification.json','predictor_lifetime.json','run_acceptance.json','external_launch_receipt.json',
        'external_application_wall.json')}
    report={'schema':'g31.initial_owner_route_v3.independent_saved_review.v1',
        'status':'passed_saved_endpoint_RPC_and_physical_readback','evidence':evidence,
        'review_source':c.reference(__file__),'source_count':len(plan['source_sha256']),
        'compiled_archive_count':len(plan['compiled_source_archive_sha256']),
        'branches':18,'closed_roots':computed['closed_roots'],
        'open_or_unknown_roots':computed['open_or_unknown_roots'],
        'roots_at_most_100ms':sum(r['root']['observed_within_100ms'] for r in rows.values()),
        'prediction_counts':computed['prediction_counts'],'RPC_requests':computed['predictor_requests'],
        'predictor_protocol_closed':computed['predictor_protocol_closed'],
        'predictor_startup_ms':computed['predictor_startup_ms'],
        'predictor_close_with_cleanup_ms':computed['predictor_close_with_cleanup_ms'],
        'worker_before_final_receipt_seconds':(receipt['before_final_receipt_export_ns']-
            receipt['worker_started_after_import_ns'])/1e9,
        'after_predictor_cleanup_through_verification_and_exit_checks_seconds':(
            receipt['before_final_receipt_export_ns']-life['cleanup_finished_ns'])/1e9,
        'whole_python_application_seconds':outer['whole_python_application_seconds'],
        'full_shared_cold_sensitivity_ms_per_root':outer['whole_python_application_seconds']*1000,
        'rows':rows,'pairs':computed['pairs'],
        'timing_interpretation':'Six disjoint recorded-boundary intervals sum exactly to each root wall. They are NOT isolated function profiles: collection includes native/codec; continuation includes native advances, fixed participant work and observation; final body includes normalization/encoding; return tail includes evidence ledger copies/codec/hash. RPC worker wall is nested, not extra CPU or exclusive cost. No shared or physical subtraction. Full campaign cold sensitivity charges entire campaign to each root and is not divided.',
        'limits':['Finite initial A two-choice first-hop; not joint/full32 or all-original-workload optimization.',
            'Eight pairs have complete five-job outcomes and strict delta<=0; drop3 pair remains unknown.',
            'No new predictor, native replay, full native query tape or performance/profile was run for this review.',
            'Root wall includes diagnostic evidence; no measured interval is retrospectively removed.'],
        'review_saved_only_seconds':(time.perf_counter_ns()-started)/1e9,
        'new_predictor_calls':0,'new_native_calls':0,'new_profile_calls':0}
    c.write(output/'report.json',report)
    print(json.dumps({k:report[k] for k in ('status','branches','closed_roots','open_or_unknown_roots',
        'roots_at_most_100ms','prediction_counts','review_saved_only_seconds')}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true')
    a=p.parse_args();source=a.source.resolve();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=PLAN+'\n':raise ValueError('review_job_admission')
        inspect_saved(source,output);return 0
    output.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m',__package__+'.review_initial_owner_route_v3_saved',
        '--source',str(source),'--output',str(output),'--worker']
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120-(time.monotonic()-BOOT)),
            admission=PLAN,stdout=out,stderr=err,cwd=c.ROOT)
    c.write(output/'bounded_execution.json',{'status':process['status'],'process':process,
        'command':command,'source':c.reference(__file__),'native_calls':0,'new_predictions':0,
        'post_import_before_final_receipt_seconds':time.monotonic()-BOOT,
        'report':c.reference(output/'report.json') if (output/'report.json').is_file() else None})
    return 0 if process['status']=='exited' and process['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
