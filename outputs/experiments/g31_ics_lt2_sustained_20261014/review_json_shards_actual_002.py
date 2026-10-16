"""Saved data only: exact readback and additive clock envelopes, no prediction."""
from __future__ import annotations
import collections
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.experiments.g31_ics_circulation import measure_json_prediction_shards as measure

START=time.perf_counter()
OUT=Path(__file__).resolve().parent
P=OUT/'json_prediction_shards_RPC_prepare_002'
OLD=OUT/'json_prediction_RPC_prepare_002'
WRAPPER=OUT/'user_resume_20261015_001/invoke_json_prediction_shards_RPC_002_measured.ps1'
EXPECTED_EXTERNAL='3b23889227989741ff9c6010b128fb5eb62f6d15386e412aaae87ab22fac8ba7'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ordered(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
def ms(ns):return ns/1e6
def stats(values):return {'min':min(values),'median':statistics.median(values),'max':max(values),'sum':sum(values)}
def reference(path):return {'path':str(path),'sha256':sha(path)}

def main():
    checked=measure.verify_saved(P,require_process=True)
    assert ordered(checked)==ordered(read(P/'report.json'))
    plan=read(P/'preregistered_protocol.json');ledger=read(P/'ledger.json')
    process=read(P/'bounded_execution.json');external=read(P/'external_application_wall.json')
    prelaunch=read(P/'root_prelaunch_review_001.json');claim=read(P/'execution_claim.json')
    assert sha(P/'external_application_wall.json')==EXPECTED_EXTERNAL
    assert prelaunch['status']=='passed_root_narrow_campaign_wiring_fix_review'
    assert prelaunch['plan']['sha256']==claim['plan_sha256']==process['plan_sha256']==external['plan_sha256']==sha(P/'preregistered_protocol.json')
    assert datetime.datetime.fromisoformat(prelaunch['recorded_utc'])<datetime.datetime.fromisoformat(external['started_utc'])
    assert external['wrapper_sha256']==sha(WRAPPER)==prelaunch['wrapper']['sha256']
    assert external['module_sha256']==plan['source_sha256']['scripts/experiments/g31_ics_circulation/measure_json_prediction_shards.py']
    assert external['python_sha256']==plan['interpreter']['sha256']
    assert external['status']=='application_exited_zero' and external['exit_code']==0 and external['evidence_unchanged'] is True and external['error'] is None
    assert process['status']=='completed' and process['process']['status']=='exited' and process['process']['exitcode']==0 and process['error'] is None
    assert process['process']['windows_job_kill_on_close'] is True and process['process']['child_released_only_after_job_assignment'] is True
    assert 0<process['process']['wall_seconds']<=process['process']['hard_timeout_seconds']<=120
    assert process['process']['wall_seconds']<=process['parent_pre_final_export_wall_seconds']<=external['whole_python_application_seconds']<120
    command=[plan['interpreter']['path'],'-m',measure.ENTRY,'--campaign','--output',str(P),
             '--plan-sha256',sha(P/'preregistered_protocol.json'),'--admission']
    assert process['command'][:-1]==command and len(process['command'][-1])==32
    assert not (P/'ready.json').exists()
    expected_logs={f'{i}.{mode}.stderr.log' for i,arm in enumerate(measure.ORDER) for mode in measure.MODES[arm]}
    assert {path.name for path in P.glob('[0-9]*.stderr.log')}==expected_logs
    assert all((P/name).stat().st_size==0 for name in expected_logs|{'stdout.log','stderr.log'})
    assert not (P/'failure.json').exists() and not list(P.glob('*failed_prefix*'))

    # Bind prior accepted raw bytes before using their six full/partial payloads.
    oldreviewpath=OUT/'json_prediction_RPC_independent_actual_review_001.json'
    assert sha(oldreviewpath)=='e8fae8dd5772fab81a3906733c2532fc6607a46de533b242d64d9289f01d8c5e'
    oldreview=read(oldreviewpath);oldplan=read(OLD/'preregistered_protocol.json')
    oldraw=OLD/'1.compiled.json.gz'
    for path in (OLD/'preregistered_protocol.json',OLD/'ledger.json',oldraw):
        assert sha(path)==oldreview['evidence_sha256'][str(path)]
    assert all(sha(ROOT/name)==sha(OLD/'source'/name)==digest for name,digest in oldplan['source_sha256'].items())
    rawold=json.loads(gzip.decompress(oldraw.read_bytes()))
    assert rawold['mode']=='compiled' and len(rawold['samples'])==6
    oldpayloads={case:sample['response']['payload'] for case,sample in zip(measure.CASES,rawold['samples'],strict=True)}
    labels=collections.Counter();warm={a:[] for a in ('single','split')}
    maximum={a:[] for a in warm};summed={a:[] for a in warm}
    cold={a:[] for a in warm};startup={a:[] for a in warm};closing={a:[] for a in warm}
    percase={case:{a:[] for a in warm} for case in measure.CASES}
    clockparts=[];windows=[];physical_baselines=0;queries=0;worker_count=0;RPC=0
    for index,(entry,arm) in enumerate(zip(ledger,measure.ORDER,strict=True)):
        raw=P/entry['raw'];assert sha(raw)==entry['sha256']
        value=json.loads(gzip.decompress(raw.read_bytes()))
        assert value['round']==index and value['arm']==arm and len(value['samples'])==6
        worker_count+=len(value['workers'])
        assert len(value['workers'])==(1 if arm=='single' else 2)
        for w in value['workers']:
            assert w['shutdown']['process_exit_code']==0 and w['shutdown']['reply']['requests']==6
        previous=value['ready_ns'];whole=value['process_reclaimed_ns']-value['client_started_ns']
        intervals=[('startup',previous-value['client_started_ns'])]
        startup[arm].append(ms(intervals[0][1]))
        for n,(row,case) in enumerate(zip(value['samples'],measure.CASES,strict=True),1):
            payload=row['merged_payload']
            assert ordered(payload)==ordered(oldpayloads[case])
            assert list(payload)==['baseline','actions','predictions'] and len(payload['actions'])==len(payload['predictions'])==32
            assert payload['baseline']['status']=='conditional_prediction'
            count=len(row['worker_samples']);physical_baselines+=count;queries+=32;RPC+=count
            if arm=='split':
                assert ordered(row['worker_samples'][0]['response']['payload']['baseline'])==ordered(row['worker_samples'][1]['response']['payload']['baseline'])
            for prediction in payload['predictions']:
                labels[prediction['status']]+=1
                if prediction['status']=='conditional_protection_rejected_prefix':
                    assert prediction['full_candidate_prediction'] is False and prediction['suffix_status']=='unknown_unexecuted'
                    assert prediction['completion']=={} and prediction['completion_sum'] is None
                    assert prediction['native_protection_certified'] is False and prediction['native_execution_certified'] is False
                    witness=prediction['witness'];job=witness['job']
                    assert witness['comparison']=='strict >; no tolerance'
                    assert witness['candidate_completed_at']>witness['baseline_completed_at']==payload['baseline']['completion'][job]
                    assert prediction['baseline_completion']==payload['baseline']['completion']
            begin,end=row['outer_admitted_ns'],row['outer_returned_ns']
            assert previous<=begin<=row['caller_admitted_ns']<=row['all_replies_ns']<=row['caller_body_finished_ns']<=end
            parts={'input_read_decode_and_dispatch':row['caller_admitted_ns']-begin,
                   'isolation_scheduling_RPC_through_replies':row['all_replies_ns']-row['caller_admitted_ns'],
                   'merge_whole_output_codec_and_ledger':row['caller_body_finished_ns']-row['all_replies_ns'],
                   'return_fields_and_thread_join_tail':end-row['caller_body_finished_ns']}
            assert sum(parts.values())==row['complete_caller_elapsed_ns']==end-begin
            for sample in row['worker_samples']:
                assert row['caller_admitted_ns']<=sample['caller_admitted_ns']<=sample['caller_decoded_ns']<=sample['caller_body_finished_ns']<=row['all_replies_ns']
                assert 0<=sample['response']['compute_wall_ns']<=sample['caller_elapsed_ns']
            intervals.extend([('between_requests',begin-previous),('request',end-begin)]);previous=end
            times=[sample['response']['compute_wall_ns'] for sample in row['worker_samples']]
            warm[arm].append(ms(end-begin));maximum[arm].append(ms(max(times)));summed[arm].append(ms(sum(times)))
            percase[case][arm].append(ms(end-begin))
            clockparts.append({'round':index,'arm':arm,'case':case,'complete_caller_ms':ms(end-begin),
                               'parts_ms':{k:ms(v) for k,v in parts.items()},'nested_max_worker_compute_ms':ms(max(times)),
                               'nested_sum_worker_compute_ms_not_CPU':ms(sum(times))})
            if n==1:cold[arm].append(ms(end-value['client_started_ns']))
        finish=value['shutdown'];assert previous<=finish['close_admitted_ns']<=finish['closed_and_reclaimed_ns']<=value['process_reclaimed_ns']
        intervals.extend([('before_close',finish['close_admitted_ns']-previous),
                          ('close_and_reclamation',value['process_reclaimed_ns']-finish['close_admitted_ns'])])
        assert sum(duration for _,duration in intervals)==whole
        closing[arm].append(ms(intervals[-1][1]))
        windows.append({'round':index,'arm':arm,'lifetime_ms':ms(whole),
                        'unamortized_residual_ms':ms(sum(d for name,d in intervals if name in ('between_requests','before_close')))})
    assert (worker_count,RPC,physical_baselines,queries)==(6,36,36,768)
    assert sum(labels.values())==768 and len(clockparts)==24
    windows_seconds=sum(v['lifetime_ms'] for v in windows)/1000
    assert windows_seconds<process['process']['wall_seconds']<external['whole_python_application_seconds']
    names=('preregistered_protocol.json','report.json','ledger.json','execution_claim.json','bounded_execution.json',
           'external_application_wall.json','root_prelaunch_review_001.json','wiring_fix_proof_001.json')
    evidence=[P/name for name in names]+[P/row['raw'] for row in ledger]+[WRAPPER,oldreviewpath,oldraw]
    report={'schema':'g31.json_shards.independent_saved_review.v1','status':'passed_full_saved_readback',
        'evidence':{str(path):sha(path) for path in evidence},'reviewer_source_sha256':sha(__file__),
        'source_count':len(plan['source_sha256']),'current_archive_and_images_exact':True,'old85_source_unchanged':True,
        'all_saved_verifier_guards_reexecuted':True,'old_exact_six_payloads':reference(oldraw),
        'logical_requests':24,'physical_worker_processes':worker_count,'physical_RPC_requests':RPC,
        'physical_full_baselines':physical_baselines,'candidate_queries':queries,'candidate_status_counts':dict(labels),
        'all_worker_close_exitcodes':0,'extra_worker_raw_or_failure_prefix':False,
        'warm_fullcaller_ms':{arm:stats(v) for arm,v in warm.items()},
        'warm_median_change_fraction':statistics.median(warm['split'])/statistics.median(warm['single'])-1,
        'warm_total_change_fraction':sum(warm['split'])/sum(warm['single'])-1,
        'per_case_median_ms':{case:{arm:statistics.median(v) for arm,v in arms.items()} for case,arms in percase.items()},
        'at_or_below_100ms':{arm:{'count':sum(v<=100 for v in values),'total':len(values)} for arm,values in warm.items()},
        'nested_max_worker_compute_ms':{arm:stats(v) for arm,v in maximum.items()},
        'nested_sum_worker_compute_wall_ms_not_CPU':{arm:stats(v) for arm,v in summed.items()},
        'nested_sum_worker_compute_change_fraction':sum(summed['split'])/sum(summed['single'])-1,
        'startup_all_workers_ready_ms':{arm:stats(v) for arm,v in startup.items()},
        'cold_all_workers_launch_through_first_return_ms':{arm:stats(v) for arm,v in cold.items()},
        'close_and_owned_reclamation_ms':{arm:stats(v) for arm,v in closing.items()},
        'complete_caller_clock_parts':clockparts,
        'partition_statistics_ms':{arm:{name:stats([row['parts_ms'][name] for row in clockparts if row['arm']==arm])
                                      for name in clockparts[0]['parts_ms']} for arm in warm},
        'round_lifetimes':windows,'total_round_lifetime_seconds':windows_seconds,
        'owned_campaign_wall_seconds':process['process']['wall_seconds'],
        'remaining_owned_campaign_setup_verification_exports_seconds':process['process']['wall_seconds']-windows_seconds,
        'whole_python_application_seconds':external['whole_python_application_seconds'],
        'ready_finalizer':'The metadata-only finalizer ran after actual dispatch and correctly rejected execution_claim. No prepared_unexecuted ready was written; actual authority is the prior root prelaunch receipt plus pinned plan/wrapper.',
        'interference':'The short metadata finalizer and listing may overlap actual execution. This is retained as one non-isolation-certified ABBA observation; no rerun/filtering is justified by it.',
        'cost_scope':'Four nonoverlapping caller intervals exactly close each outside-call envelope. Worker compute WALL durations are nested, duplicated baseline work is counted36, and sums are not CPU or latency. Startup/close/shared verification/export costs are not amortized or subtracted. Application cost excludes only declared outer PowerShell/tool startup and receipt hashing/export.',
        'limits':['New common caller adds complete-result codec and deep-copy evidence to both arms. NewA381ms cannot be directly compared with old207ms.',
                  'One fixed six-input retrospective ABBA observation, no stability/native/online/business authority.',
                  'All per-arm12 warm requests exceed100ms; some split worker kernels alone exceed100ms. No complete100ms certificate.',
                  'Worker denominator is actual source-bound process lifecycle/artifacts, not an independent live OS census.'],
        'new_predictor_calls':0,'new_profile_calls':0,'new_native_calls':0,'review_wall_seconds':time.perf_counter()-START}
    target=OUT/'json_prediction_shards_independent_actual_review_002.json'
    with target.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'path':str(target),'sha256':sha(target),'warm':report['warm_fullcaller_ms'],
        'cold':report['cold_all_workers_launch_through_first_return_ms'],'partition':report['partition_statistics_ms'],
        'compute_sum_change':report['nested_sum_worker_compute_change_fraction'],'labels':dict(labels)},indent=2))

if __name__=='__main__':main()
