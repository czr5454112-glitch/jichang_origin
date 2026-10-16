"""Saved JSON/hash/clock checks only; never import a predictor or native API."""
from pathlib import Path
import gzip, hashlib, json, math, runpy, statistics, time
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
CASE=OUT/'preference_receiver_vector_pair_001'
PREVIOUS=OUT/'preference_receiver_bound_pair_001'
FULL=OUT/'preference_protection_context_pair_001'
PLAN='80f713be813bf769a6f190518b1a9dc1c5ae7c55750b1ff979f92fac9e2629da'
JOBS={'loaded','receiver','reuse1','reuse2','blocker'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    p=Path(p);b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def encode(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def require(ok,why):
    if not ok:raise ValueError(why)
def number(v):return type(v) in (int,float) and math.isfinite(v) and v>=0

def main():
    start=time.perf_counter();pins={}
    def pin(p,expected=None):
        got=sha(p);require(expected is None or got==expected,'hash:'+str(p));pins[str(p)]=got
    old_review=OUT/'preference_receiver_bound_pair_001_independent_review.json'
    pin(old_review,'01cc43eaf1ebf4c7ed7ad6c4c0df63a079111050efcbd02b2eda85046d0f62e6')
    review=read(old_review)
    # This already pinned helper contains only stdlib data checks and an
    # independent optimistic path calculation; run_path does not call main.
    helper=OUT/'review_receiver_bound_pair_001.py'
    pin(helper,review['evidence_sha256'][str(helper)])
    bound=runpy.run_path(str(helper))['bound']
    pin(CASE/'preregistered_protocol.json',PLAN);plan=read(CASE/'preregistered_protocol.json')
    require(len(plan['source_sha256'])==45 and plan['hard_timeout_seconds']==120.,'fixed domain')
    for name,digest in plan['source_sha256'].items():pin(ROOT/name,digest);pin(CASE/'source'/name,digest)
    pin(plan['input']['path'],plan['input']['sha256'])
    for p,digest in plan['pure_gate'].items():pin(p,digest)
    prior=plan['independent_accepted_oracle']
    require(Path(prior['path'])==PREVIOUS,'prior path')
    for name,digest in prior['sha256'].items():pin(PREVIOUS/name,digest)
    receipt,ledger,process,external=(read(CASE/n) for n in ('receipt.json','ledger.json','external_process.json','external_application_wall.json'))
    for name in ('receipt.json','ledger.json','external_process.json','external_application_wall.json','root_prelaunch_review_001.json'):pin(CASE/name)
    require(receipt['status']=='completed_pure_ABBA_with_validated_partial_suffixes' and receipt['source_changed']==receipt['input_changed']==[],'receipt')
    require(process['status']=='worker_exited_zero' and process['process']['status']=='exited' and process['process']['exitcode']==0
        and process['process']['windows_job_kill_on_close'] is True and process['process']['child_released_only_after_job_assignment'] is True
        and 0<process['process']['hard_timeout_seconds']<=120,'owned process')
    require(external['status']=='application_exited_zero' and external['evidence_unchanged'] is True and external['exit_code']==0 and external['error'] is None,'external')
    require(process['plan_sha256']==receipt['plan_sha256']==external['plan_sha256']==PLAN,'plan identities')
    module=ROOT/'scripts/experiments/g31_ics_circulation/measure_preference_receiver_vector_context.py'
    pin(module,external['module_sha256']);pin(OUT/'user_resume_20261015_001/invoke_receiver_vector_pair_001_measured.ps1',external['wrapper_sha256'])
    pin(process['command'][0],external['python_sha256'])
    require(process['command'][1:]==['-m','scripts.experiments.g31_ics_circulation.measure_preference_receiver_vector_context',
        '--worker','--output',str(CASE),'--plan-sha256',PLAN,'--admission',process['command'][-1]] and len(process['command'])==10,'command')
    for name,digest in process['evidence_sha256'].items():pin(CASE/name,digest)
    require(len(ledger)==24 and encode(ledger)==encode(receipt['timing_samples']),'ledger denominator')
    source=[r for r in read(plan['input']['path']) if r['owner']=='A']
    require(len(source)==len(plan['cases'])==6,'input cases')
    fullledger=read(FULL/'ledger.json');pin(FULL/'ledger.json',review['evidence_sha256'][str(FULL/'ledger.json')])
    counts={arm:{'full':0,'prefix':0,'early':0} for arm in ('A','B')};pairs=[]
    for ci,(case,supplied) in enumerate(zip(plan['cases'],source,strict=True)):
        require(case['case']==supplied['case'] and case['order']==['A','B','B','A'],'case order')
        pin(CASE/case['input'],case['input_sha256']);bundle=read(CASE/case['input'])
        require(encode(bundle)==encode(supplied['bundle']),'input exact')
        priorpath=PREVIOUS/f"{case['case']}.1.B.json.gz";old=read(priorpath)
        name=f"{case['case']}.0.A.json.gz";pin(FULL/name,fullledger[ci*4]['raw_sha256']);full=read(FULL/name)
        require(old['baseline']==full['baseline'] and old['actions']==full['actions'] and len(old['actions'])==32,'full baseline/actions')
        baseline=full['baseline']['completion'];require(set(baseline)==JOBS and all(number(v) for v in baseline.values()),'five baseline completions')
        per={'full':0,'prefix':0,'early':0}
        for i,prediction in enumerate(old['predictions']):
            actual=full['predictions'][i];require(actual['status']=='conditional_prediction' and set(actual['completion'])==JOBS,'old complete domain')
            status=prediction['status']
            if status=='conditional_prediction':require(encode(prediction)==encode(actual),'full exact');per['full']+=1;continue
            require(prediction['completion']=={} and prediction['completion_sum'] is None and prediction['full_candidate_prediction'] is False
                and prediction['suffix_status']=='unknown_unexecuted' and prediction['baseline_completion']==baseline,'partial honest')
            require(all(prediction[k] is False for k in ('native_protection_certified','native_execution_certified','online_information_delivered','complete_100ms_certified')),'no authority')
            witness=prediction['witness'];job=witness['job']
            if status=='conditional_protection_rejected_lower_bound':
                require(encode(witness)==encode(bound(bundle,old['actions'][i],baseline)),'lower independently recomputed')
                require(actual['completion'][job]>=witness['completion_lower_bound']>baseline[job],'strict optimistic bound');per['early']+=1
            else:
                require(status=='conditional_protection_rejected_prefix' and witness['candidate_completed_at']==actual['completion'][job]
                    and witness['baseline_completed_at']==baseline[job] and witness['candidate_completed_at']>baseline[job]
                    and witness['cut_at']==witness['candidate_completed_at'],'strict prefix')
                require(all(k in JOBS and v==actual['completion'][k] and v<=witness['cut_at'] for k,v in witness['completed_prefix'].items()),'prefix exact');per['prefix']+=1
        for n,arm in enumerate(case['order']):
            row=ledger[ci*4+n];name=f"{case['case']}.{n}.{arm}.json.gz";pin(CASE/name,row['raw_sha256'])
            require((row['case'],row['sample'],row['arm'],row['raw'],row['status'])==(case['case'],n,arm,name,'completed'),'sample identity')
            require(type(row['wall_ns']) is int and row['wall_ns']>0 and type(row['cpu_ns']) is int and row['cpu_ns']>=0,'finite clocks')
            require(encode(read(CASE/name))==encode(old),'both arms exact accepted ordered output')
            require(row['checks']=={'full_exact':per['full'],'strict_prefix_rejections':per['prefix'],'unknown':0,'strict_lower_bound_rejections':per['early']},'checks exact')
            for key in per:counts[arm][key]+=per[key]
        rows=ledger[ci*4:ci*4+4];a=statistics.median(r['wall_ns'] for r in rows if r['arm']=='A');b=statistics.median(r['wall_ns'] for r in rows if r['arm']=='B')
        require(receipt['case_pairs'][ci]=={'case':case['case'],'median_A_ns':a,'median_B_ns':b},'case medians')
        pairs.append({'case':case['case'],'median_A_ns':a,'median_B_ns':b,'B_faster':b<a,'distinct_candidate_counts':per})
    totals={arm:sum(r['wall_ns'] for r in ledger if r['arm']==arm) for arm in ('A','B')}
    medians={arm:statistics.median(r['wall_ns'] for r in ledger if r['arm']==arm) for arm in ('A','B')}
    require(all(receipt['median_'+a+'_ns']==medians[a] for a in ('A','B')),'overall medians')
    clocks={'worker_before_readback_s':receipt['worker_wall_seconds'],'owned_process_s':process['process']['wall_seconds'],
        'parent_post_interpreter_s':process['parent_post_interpreter_wall_seconds'],'external_python_s':external['whole_python_application_seconds']}
    require(all(number(v) for v in clocks.values()) and sum(totals.values())/1e9<=clocks['worker_before_readback_s']<=clocks['owned_process_s']<=clocks['parent_post_interpreter_s']<=clocks['external_python_s'],'clock hierarchy')
    require(receipt['candidate_queries']==768 and receipt['full_baselines']==24 and receipt['complete_100ms_certified'] is False,'full denominator')
    pin(__file__)
    report={'status':'independent_saved_vector_pair_passed','plan_sha256':PLAN,'evidence_sha256':pins,'source_count':45,'batches':24,'queries':768,'baselines':24,
        'counts':counts,'case_pairs':pairs,'total_ns':totals,'median_ns':medians,'total_reduction_percent':100*(totals['A']-totals['B'])/totals['A'],
        'candidate_min_ns':min(r['wall_ns'] for r in ledger if r['arm']=='B'),'candidate_max_ns':max(r['wall_ns'] for r in ledger if r['arm']=='B'),
        'candidate_samples_at_or_below_100ms':sum(r['wall_ns']<=100000000 for r in ledger if r['arm']=='B'),'clocks':clocks,
        'new_projection_calls':0,'new_native_calls':0,'complete_100ms_certified':False,'wall_seconds':time.perf_counter()-start,
        'review_precheck_correction':'First independent invocation stopped before raw/clock checking because its helper used a nonexistent accepted_receiver_bound key. Corrected to the actual pinned independent_accepted_oracle schema; no experiment artifact changed.',
        'limits':['Fixed six retrospective supplied contexts, two B samples each; three slower block1 cases retained.',
                  'Total batch cost improved while overall median worsened; all B samples remain above 100ms.',
                  'Strict partial counterexamples have unknown suffixes. No native, online, business-request or hard-real-time certification.',
                  'No new prediction, profile, tuning or proposed next receiver micro-optimization.']}
    target=OUT/'preference_receiver_vector_pair_001_independent_review.json'
    with target.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'status':report['status'],'sha256':sha(target),'total_ns':totals,'median_ns':medians,'counts':counts,'wall_seconds':report['wall_seconds']}))
if __name__=='__main__':main()
