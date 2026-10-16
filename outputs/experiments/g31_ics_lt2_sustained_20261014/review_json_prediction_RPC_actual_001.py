"""Saved-byte readback only: no predictor, profiler or NativeSession calls."""
from __future__ import annotations
import collections
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.experiments.g31_ics_circulation import measure_json_prediction_service as measure

START=time.perf_counter()
P=Path(__file__).resolve().parent/'json_prediction_RPC_prepare_002'
WRAPPER=P.parent/'user_resume_20261015_001/invoke_json_prediction_RPC_002_measured.ps1'
EXPECTED_EXTERNAL='83124d5bdb8ad337d78f4eb6d4070b4891e6b51f0ee54d0372a485ce8511504c'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ordered(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
def ms(ns):return ns/1e6
def stats(values):return {'min':min(values),'median':statistics.median(values),'max':max(values),'sum':sum(values)}


def main():
    # Re-execute all saved-data guards, not any model simulation.
    checked=measure.verify_saved(P,require_process=True)
    reported=read(P/'report.json')
    assert ordered(checked)==ordered(reported)
    plan=read(P/'preregistered_protocol.json');ready=read(P/'ready.json')
    process=read(P/'bounded_execution.json');external=read(P/'external_application_wall.json')
    ledger=read(P/'ledger.json');claim=read(P/'execution_claim.json')
    assert sha(P/'external_application_wall.json')==EXPECTED_EXTERNAL
    assert sha(P/'preregistered_protocol.json')==ready['preregistered_plan_sha256']==claim['plan_sha256']==external['plan_sha256']==process['plan_sha256']
    assert external['wrapper_sha256']==sha(WRAPPER)
    assert external['module_sha256']==plan['source_sha256']['scripts/experiments/g31_ics_circulation/measure_json_prediction_service.py']
    assert external['python_sha256']==plan['interpreter']['sha256']
    assert external['status']=='application_exited_zero' and external['exit_code']==0 and external['evidence_unchanged'] is True and external['error'] is None
    assert process['status']=='completed' and process['process']['status']=='exited' and process['process']['exitcode']==0 and process['error'] is None
    assert process['process']['windows_job_kill_on_close'] is True and process['process']['child_released_only_after_job_assignment'] is True
    assert 0<process['process']['wall_seconds']<=process['process']['hard_timeout_seconds']<=120
    assert process['process']['wall_seconds']<=process['parent_pre_final_export_wall_seconds']<=external['whole_python_application_seconds']<120
    expected_command=[plan['interpreter']['path'],'-m',measure.ENTRY,'--campaign','--output',str(P),
        '--plan-sha256',sha(P/'preregistered_protocol.json'),'--admission']
    assert process['command'][:-1]==expected_command and len(process['command'][-1])==32
    expected_raw={f'{i}.{mode}.json.gz' for i,mode in enumerate(measure.ORDER)}
    assert {path.name for path in P.glob('*.json.gz')}==expected_raw
    assert {path.name for path in P.glob('[0-9]*.stderr.log')}=={f'{n}.stderr.log' for n in range(4)}
    assert not list(P.glob('*failed_prefix*')) and not (P/'failure.json').exists()
    assert all((P/f'{n}.stderr.log').stat().st_size==0 for n in range(4))
    assert (P/'stdout.log').stat().st_size==(P/'stderr.log').stat().st_size==0
    reference={};labels=collections.Counter();warm={'reference':[],'compiled':[]};nested={'reference':[],'compiled':[]}
    cold={'reference':[],'compiled':[]};startup={'reference':[],'compiled':[]};closing={'reference':[],'compiled':[]}
    per_case={case:{'reference':[],'compiled':[]} for case in measure.CASES}
    clocks=[];worker_windows=[];full_baselines=0;prediction_count=0
    for worker,(row,mode) in enumerate(zip(ledger,measure.ORDER,strict=True)):
        raw=P/row['raw'];assert sha(raw)==row['sha256']
        value=json.loads(gzip.decompress(raw.read_bytes()))
        assert value['worker']==worker and value['mode']==mode and len(value['samples'])==6
        whole=value['process_reclaimed_ns']-value['client_started_ns']
        phase_intervals=[]
        previous=value['client_started_ns']
        phase_intervals.append(('startup',value['ready_ns']-previous));previous=value['ready_ns']
        startup[mode].append(ms(value['ready_ns']-value['client_started_ns']))
        for n,(sample,case) in enumerate(zip(value['samples'],measure.CASES,strict=True),1):
            assert sample['request']['request_id']==sample['response']['request_id']==f'worker-{worker}:{case}'
            payload=sample['response']['payload']
            assert list(payload)==['baseline','actions','predictions'] and len(payload['actions'])==len(payload['predictions'])==32
            assert payload['baseline']['status']=='conditional_prediction'
            full_baselines+=1;prediction_count+=len(payload['predictions'])
            if worker==0:reference[case]=ordered(payload)
            else:assert ordered(payload)==reference[case]
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
            outer_start=sample['outer_admitted_ns'];outer_end=sample['outer_returned_ns']
            assert previous<=outer_start<=sample['caller_admitted_ns']<=sample['caller_decoded_ns']<=sample['caller_body_finished_ns']<=outer_end
            parts={'input_read_decode_and_call_dispatch':sample['caller_admitted_ns']-outer_start,
                'live_RPC_through_decoded_reply':sample['caller_decoded_ns']-sample['caller_admitted_ns'],
                'caller_ledger_build_append':sample['caller_body_finished_ns']-sample['caller_decoded_ns'],
                'caller_final_clock_fields_and_return_tail':outer_end-sample['caller_body_finished_ns']}
            assert sum(parts.values())==sample['complete_caller_elapsed_ns']==outer_end-outer_start
            assert 0<=sample['response']['compute_wall_ns']<=parts['live_RPC_through_decoded_reply']
            phase_intervals.extend([('between_requests_or_setup',outer_start-previous),('complete_request',outer_end-outer_start)])
            previous=outer_end
            warm[mode].append(ms(outer_end-outer_start));nested[mode].append(ms(sample['response']['compute_wall_ns']))
            per_case[case][mode].append(ms(outer_end-outer_start))
            clocks.append({'worker':worker,'case':case,'mode':mode,'full_caller_ms':ms(outer_end-outer_start),
                'parts_ms':{k:ms(v) for k,v in parts.items()},'nested_compute_ms':ms(sample['response']['compute_wall_ns'])})
            if n==1:cold[mode].append(ms(outer_end-value['client_started_ns']))
        close=value['shutdown'];assert previous<=close['close_admitted_ns']<=close['protocol_closed_ns']<=close['close_finished_ns']<=value['process_reclaimed_ns']
        phase_intervals.extend([('before_close',close['close_admitted_ns']-previous),('close_rehash_and_reclamation',value['process_reclaimed_ns']-close['close_admitted_ns'])])
        assert sum(duration for _,duration in phase_intervals)==whole
        closing[mode].append(ms(value['process_reclaimed_ns']-close['close_admitted_ns']))
        worker_windows.append({'worker':worker,'mode':mode,'full_window_ms':ms(whole),
            'between_request_or_close_residual_ms':ms(sum(d for name,d in phase_intervals if name in ('between_requests_or_setup','before_close')))})
    assert full_baselines==24 and prediction_count==768
    worker_total=sum(row['full_window_ms'] for row in worker_windows)/1000
    assert worker_total<process['process']['wall_seconds']<external['whole_python_application_seconds']
    evidence=[P/name for name in ('ready.json','preregistered_protocol.json','report.json','ledger.json','bounded_execution.json',
        'external_application_wall.json','execution_claim.json','root_prelaunch_review_001.json','independent_source_review_001.json')]
    evidence.extend(P/name for name in sorted(expected_raw));evidence.append(WRAPPER)
    result={'schema':'g31.json_prediction_RPC.independent_saved_review.v1','status':'passed_saved_outputs_and_cost_envelopes',
        'evidence_sha256':{str(path):sha(path) for path in evidence},'reviewer_source_sha256':sha(__file__),
        'source_closure_count':len(plan['source_sha256']),'current_and_archived_source_exact':True,
        'full_saved_verifier_reexecuted':True,'independent_raw_ordered_comparison':True,
        'requests':24,'full_baselines':24,'candidate_queries':768,'prediction_status_counts':dict(labels),
        'raw_worker_denominator':4,'worker_order':list(measure.ORDER),'extra_worker_raw_or_failure_prefix_found':False,
        'warm_complete_caller_ms':{mode:stats(values) for mode,values in warm.items()},
        'warm_median_change_fraction':statistics.median(warm['compiled'])/statistics.median(warm['reference'])-1,
        'warm_total_change_fraction':sum(warm['compiled'])/sum(warm['reference'])-1,
        'per_case_median_ms':{case:{mode:statistics.median(values) for mode,values in arms.items()} for case,arms in per_case.items()},
        'nested_compute_ms_not_additive':{mode:stats(values) for mode,values in nested.items()},
        'startup_launch_to_READY_ms':{mode:stats(values) for mode,values in startup.items()},
        'cold_launch_through_first_return_ms':{mode:stats(values) for mode,values in cold.items()},
        'close_with_reclamation_ms':{mode:stats(values) for mode,values in closing.items()},
        'compiled_warm_requests_at_or_below_100ms':sum(value<=100 for value in warm['compiled']),
        'compiled_warm_requests_total':len(warm['compiled']),'complete_100ms_certified':False,
        'whole_python_application_seconds':external['whole_python_application_seconds'],
        'owned_campaign_seconds':process['process']['wall_seconds'],'worker_process_windows_seconds':worker_total,
        'remaining_owned_campaign_setup_checks_exports_seconds':process['process']['wall_seconds']-worker_total,
        'all_remaining_cost_retained':True,'request_clock_parts':clocks,'worker_windows':worker_windows,
        'cost_scope':'Four component caller intervals exactly partition each outside-call envelope. Worker compute is nested inside live RPC and is never added twice. Startup, all inter-request bookkeeping, close/rehash/reclamation, shared source validation, exports and saved verification remain in worker/campaign/application totals. No cost amortization or subtraction from requests.',
        'limits':['Saved outputs, source bytes and process evidence reviewed; no new model/profile/native execution.',
            'One fixed serial ABBA experiment over six retrospective supplied inputs; no stability, online or original-workload inference.',
            'Worker count is source-bound command/artifact denominator, not an independent live OS census.',
            'External application interval excludes the declared PowerShell/tool startup and pre/postlaunch evidence hashing; not platform cold start.',
            'Cold first-request figures are launch-through-first-return of each prediction worker; whole parent setup remains additional in full application cost.'],
        'new_predictor_calls':0,'new_profile_calls':0,'new_native_calls':0,'review_wall_seconds':time.perf_counter()-START}
    path=P.parent/'json_prediction_RPC_independent_actual_review_001.json'
    if path.exists():raise ValueError('preserve_prior_review')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':result['status'],'sha256':sha(path),'warm_ms':result['warm_complete_caller_ms'],
        'cold_ms':result['cold_launch_through_first_return_ms'],'labels':dict(labels)},indent=2))

if __name__=='__main__':main()
