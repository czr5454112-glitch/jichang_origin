"""Independent saved-data check only; no model/native imports or execution."""
from pathlib import Path
import gzip,hashlib,json,math,pickle,statistics,time
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
CASE=OUT/'preference_receiver_bound_pair_001'
OLD=OUT/'preference_protection_context_pair_001'
OLD_PLAN='3f29244efa0524732a21c8872ce884ccf039ace6ab0a82c0810a313ba0827441'
OLD_LEDGER='b7d35dcf3dbc32dba454c66226e5ac418f8c1412ed4e75d4e38462a1c31401a6'
EXPECTED='745c9e64171e11f803537e3a577e6ee3c5e1af8c23aaf4bd433cb361912ad5e7'
JOBS={'loaded','receiver','reuse1','reuse2','blocker'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def ordered(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def number(v):return type(v) in (int,float) and math.isfinite(v) and v>=0
def check(ok,reason):
    if not ok:raise ValueError(reason)
def bound(bundle,action,baseline):
    import heapq
    c=bundle['contract'];edges={(u,v):max(.001,length/speed) for u,v,length,speed in c['edge_records']}
    capacity={(e['from'],e['to']):e['capacity'] for e in c['edge_contracts']};outgoing={n[0]:n[5] for n in c['node_records']}
    def earliest(source,goal,at):
        q=[(at,source,(source,))];best={source:at}
        while q:
            at,n,path=heapq.heappop(q)
            if at!=best[n]:continue
            if n==goal:return at,list(path)
            for target in outgoing[n]:
                if capacity[n,target]<=0:continue
                t=at+edges[n,target]
                check(number(t),'finite lower clock')
                if t<best.get(target,math.inf):best[target]=t;heapq.heappush(q,(t,target,path+(target,)))
        raise ValueError('no lower path')
    wire=bundle['now']+c['protocol']['message_delay'];grant=max(wire,action['empty_departure'])
    arrival,p1=earliest(5,1,grant);load=arrival+bundle['jobs']['receiver']['load_seconds'];destination,p2=earliest(1,4,load)
    return {'job':'receiver','completion_lower_bound':destination+bundle['jobs']['receiver']['unload_seconds'],'baseline_completed_at':baseline['receiver'],
        'wire_delivery_lower_bound':wire,'grant_lower_bound':grant,'empty_arrival_lower_bound':arrival,'load_completion_lower_bound':load,
        'destination_arrival_lower_bound':destination,'positive_capacity_paths':{'empty':p1,'loaded':p2},'comparison':'strict >; no tolerance',
        'float_rule':'Forward t + travel labels; same per-edge floats/addition order, no collapsed distance sum.',
        'relaxed_nonnegative_terms':['all node service','berth/edge capacity waiting','headway/calendar/queue waiting','rejections/retries and further control delay'],
        'authority_scope':'Pinned .11 initial 3tray/5job continuation: E sole possible receiver carrier; not an arbitrary future-policy or native availability proof.'}

def main():
    start=time.perf_counter();bindings={};checks=0
    def pin(p,digest=None):
        nonlocal checks
        actual=sha(p);check(digest is None or actual==digest,'hash:'+str(p));bindings[str(p)]=actual;checks+=1
    plan_path=CASE/'preregistered_protocol.json';pin(plan_path,EXPECTED);plan=read(plan_path)
    check(len(plan['source_sha256'])==45,'source count')
    for name,digest in plan['source_sha256'].items():pin(ROOT/name,digest);pin(CASE/'source'/name,digest)
    pin(plan['input']['path'],plan['input']['sha256']);source=[r for r in read(plan['input']['path']) if r['owner']=='A']
    for p,digest in plan['pure_gate'].items():pin(p,digest)
    receipt=read(CASE/'receipt.json');ledger=read(CASE/'ledger.json');process=read(CASE/'external_process.json');external=read(CASE/'external_application_wall.json')
    for name in ('receipt.json','ledger.json','external_process.json','external_application_wall.json','root_prelaunch_review.json'):
        if (CASE/name).exists():pin(CASE/name)
    check(receipt['status']=='completed_pure_ABBA_with_validated_partial_suffixes' and receipt['source_changed']==receipt['input_changed']==[],'receipt')
    check(process['status']=='worker_exited_zero' and process['process']['status']=='exited' and process['process']['exitcode']==0,'process')
    check(process['process']['windows_job_kill_on_close'] is True and process['process']['child_released_only_after_job_assignment'] is True,'job')
    check(0<process['process']['hard_timeout_seconds']<=120,'job bound')
    check(external['status']=='application_exited_zero' and external['evidence_unchanged'] is True and external['exit_code']==0 and external['error'] is None,'external')
    check(process['plan_sha256']==receipt['plan_sha256']==external['plan_sha256']==EXPECTED,'plan binding')
    module=ROOT/'scripts/experiments/g31_ics_circulation/measure_preference_receiver_bound_context.py'
    pin(module,external['module_sha256']);pin(OUT/'user_resume_20261015_001/invoke_receiver_bound_pair_001_measured.ps1',external['wrapper_sha256'])
    pin(process['command'][0],external['python_sha256'])
    check(process['command'][1:3]==['-m','scripts.experiments.g31_ics_circulation.measure_preference_receiver_bound_context']
        and process['command'][3:8]==['--worker','--output',str(CASE),'--plan-sha256',EXPECTED]
        and process['command'][8]=='--admission' and len(process['command'])==10,'worker command')
    for name,digest in process['evidence_sha256'].items():pin(CASE/name,digest)
    check(len(ledger)==24 and ordered(ledger)==ordered(receipt['timing_samples']),'24 ledger')
    check(len(plan['cases'])==len(source)==6,'six cases')
    pin(OLD/'preregistered_protocol.json',OLD_PLAN);pin(OLD/'ledger.json',OLD_LEDGER);oldledger=read(OLD/'ledger.json')
    check(plan['independent_full_oracle']['path']==str(OLD),'oracle path')
    for name,digest in plan['independent_full_oracle']['sha256'].items():pin(OLD/name,digest)
    counts={'A_full':0,'A_prefix':0,'B_full':0,'B_prefix':0,'B_early':0};pairs=[]
    for ci,(case,origin) in enumerate(zip(plan['cases'],source,strict=True)):
        check(case['case']==origin['case'] and case['order']==['A','B','B','A'],'ABBA/case')
        path=CASE/case['input'];pin(path,case['input_sha256']);bundle=read(path);check(ordered(bundle)==ordered(origin['bundle']),'exact public input')
        fingerprint=hashlib.sha256(pickle.dumps(bundle,protocol=5)).hexdigest();firstA=None;firstB=None;percuts=[]
        prior=[]
        for oldn,oldarm in ((0,'A'),(1,'B')):
            oldname=f"{case['case']}.{oldn}.{oldarm}.json.gz";pin(OLD/oldname,oldledger[4*ci+oldn]['raw_sha256'])
            prior.append(json.loads(gzip.decompress((OLD/oldname).read_bytes())))
        full,oldcombined=prior
        for n,arm in enumerate(case['order']):
            row=ledger[4*ci+n];name=f"{case['case']}.{n}.{arm}.json.gz";pin(CASE/name,row['raw_sha256'])
            check((row['case'],row['sample'],row['arm'],row['raw'],row['status'])==(case['case'],n,arm,name,'completed'),'row identity')
            check(type(row['wall_ns']) is int and row['wall_ns']>0 and type(row['cpu_ns']) is int and row['cpu_ns']>=0,'clocks')
            value=json.loads(gzip.decompress((CASE/name).read_bytes()))
            check(set(value)=={'baseline','actions','predictions'} and len(value['actions'])==len(value['predictions'])==32,'payload denominator')
            check(ordered(value['baseline'])==ordered(full['baseline']) and ordered(value['actions'])==ordered(full['actions']),'same baseline/actions')
            baseline=full['baseline']['completion'];check(full['baseline']['status']=='conditional_prediction' and set(baseline)==JOBS and all(number(v) for v in baseline.values()),'baseline complete')
            if arm=='A':
                check(ordered(value)==ordered(oldcombined),'A exact frozen combined')
                if firstA is None:firstA=value
                else:check(ordered(value)==ordered(firstA),'A repeat')
            elif firstB is None:firstB=value
            else:check(ordered(value)==ordered(firstB),'B repeat')
            prefixcuts=earlycuts=0
            for i,(a,b) in enumerate(zip(full['predictions'],value['predictions'],strict=True)):
                check(a['status']=='conditional_prediction' and set(a['completion'])==JOBS and all(number(v) for v in a['completion'].values()),'saved full model')
                status=b['status']
                if status=='conditional_prediction':
                    check(ordered(a)==ordered(b),'full ordered output');counts[arm+'_full']+=1;continue
                check(status in ('conditional_protection_rejected_prefix','conditional_protection_rejected_lower_bound'),'partial status')
                check(set(b)=={'status','completion','completion_sum','witness','supplied_snapshot_sha256','baseline_action','baseline_completion','full_candidate_prediction','suffix_status','native_protection_certified','native_execution_certified','online_information_delivered','complete_100ms_certified'},'partial fields')
                check(b['completion']=={} and b['completion_sum'] is None and b['full_candidate_prediction'] is False and b['suffix_status']=='unknown_unexecuted','partial not full')
                check(all(b[k] is False for k in ('native_protection_certified','native_execution_certified','online_information_delivered','complete_100ms_certified')),'no authority')
                check(b['supplied_snapshot_sha256']==fingerprint and ordered(b['baseline_completion'])==ordered(baseline) and ordered(b['baseline_action'])==ordered(full['actions'][0]),'same input baseline')
                w=b['witness'];j=w['job']
                if status=='conditional_protection_rejected_prefix':
                    check(ordered(b)==ordered(oldcombined['predictions'][i]),'prefix exact frozen combined')
                    prefix=w['completed_prefix']
                    check(set(w)=={'job','candidate_completed_at','baseline_completed_at','cut_at','completed_prefix','comparison','observed_point'},'witness fields')
                    check(j in JOBS and w['comparison']=='strict >; no tolerance' and w['observed_point']=='original unload assignment before its post-unload notification','witness scope')
                    check(all(number(w[k]) for k in ('cut_at','candidate_completed_at','baseline_completed_at')) and w['candidate_completed_at']==w['cut_at']==a['completion'][j] and w['baseline_completed_at']==baseline[j] and a['completion'][j]>baseline[j],'strict irreparable completion')
                    check(type(prefix) is dict and j in prefix and all(k in JOBS and number(v) and v==a['completion'][k] and v<=w['cut_at'] for k,v in prefix.items()),'actual prefix')
                    prefixcuts+=1;counts[arm+'_prefix']+=1
                else:
                    check(arm=='B' and j=='receiver','early receiver only')
                    expected=bound(bundle,full['actions'][i],baseline)
                    check(ordered(w)==ordered(expected),'independent lower calculation')
                    check(a['completion'][j]>=w['completion_lower_bound']>baseline[j],'strict optimistic completion')
                    earlycuts+=1;counts['B_early']+=1
            check(row['checks']=={'full_exact':32-prefixcuts-earlycuts,'strict_prefix_rejections':prefixcuts,'unknown':0,'strict_lower_bound_rejections':earlycuts},'reported counts')
            if arm=='B':percuts.append({'early':earlycuts,'prefix':prefixcuts})
        rows=ledger[4*ci:4*ci+4];a=statistics.median(r['wall_ns'] for r in rows if r['arm']=='A');b=statistics.median(r['wall_ns'] for r in rows if r['arm']=='B')
        pairs.append({'case':case['case'],'median_A_ns':a,'median_B_ns':b,'B_faster':b<a,'counterexamples_each_B':percuts})
        check(receipt['case_pairs'][ci]=={'case':case['case'],'median_A_ns':a,'median_B_ns':b},'paired medians')
    totals={arm:sum(r['wall_ns'] for r in ledger if r['arm']==arm) for arm in ('A','B')}
    medians={arm:statistics.median(r['wall_ns'] for r in ledger if r['arm']==arm) for arm in ('A','B')}
    check(all(receipt['median_'+arm+'_ns']==medians[arm] for arm in ('A','B')),'summary medians')
    clocks={'worker_before_saved_recheck_s':receipt['worker_wall_seconds'],'owned_process_s':process['process']['wall_seconds'],
        'parent_post_interpreter_s':process['parent_post_interpreter_wall_seconds'],'external_python_s':external['whole_python_application_seconds']}
    check(all(number(v) for v in clocks.values()) and sum(totals.values())/1e9<=clocks['worker_before_saved_recheck_s']<=clocks['owned_process_s']<=clocks['parent_post_interpreter_s']<=clocks['external_python_s'],'clock conservation hierarchy')
    check(receipt['candidate_queries']==768 and receipt['full_baselines']==24 and receipt['complete_100ms_certified'] is False,'totals')
    pin(__file__)
    report={'status':'independent_saved_24_batch_check_passed','plan_sha256':EXPECTED,'hash_checks':checks,'evidence_sha256':bindings,
        'source_count':45,'contexts':6,'batches':24,'queries':768,'fully_charged_baselines':24,'counts':counts,'case_pairs':pairs,
        'total_ns':totals,'median_ns':medians,'total_reduction_percent':100*(totals['A']-totals['B'])/totals['A'],
        'candidate_min_ns':min(r['wall_ns'] for r in ledger if r['arm']=='B'),'candidate_max_ns':max(r['wall_ns'] for r in ledger if r['arm']=='B'),
        'candidate_samples_at_or_below_100ms':sum(r['wall_ns']<=100000000 for r in ledger if r['arm']=='B'),'clocks':clocks,
        'new_projection_calls':0,'new_native_calls':0,'complete_100ms_certified':False,'wall_seconds':time.perf_counter()-start,
        'limits':['Two B samples for each of six retrospective supplied inputs; every slower case is retained.','Independent raw/hash/finite-duration checks do not independently recreate wall-clock hardware observations.','Partial candidates retain unknown suffixes; no native or complete business-request certification.','Full JSON encoding is inside each batch; diagnostic gzip/readback/import/setup remain in complete external wall.']}
    target=OUT/'preference_receiver_bound_pair_001_independent_review.json'
    with target.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'status':report['status'],'report_sha256':sha(target),'counts':counts,'total_ns':totals,'median_ns':medians,'wall_seconds':report['wall_seconds']}))
if __name__=='__main__':main()
