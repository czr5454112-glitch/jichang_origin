"""Prewritten all-case paired analysis; no rerouting, simulation or filtering."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import json,statistics,sys,gzip,math
from time import get_clock_info

ROOT=next(p for p in Path(__file__).resolve().parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
RUN=BASE/'phase4_w3_terminal_screen_performance_20261010'


def main(stage,output):
    cpu,wall=process_time(),perf_counter();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    bindings={}
    def read(path):
        b=path.read_bytes();bindings[str(path.relative_to(ROOT))]=sha256(b).hexdigest();return json.loads(b)
    protocol=read(RUN/'protocol.json');s=read(RUN/stage/'summary.json')
    environment_path=BASE/'phase4_w3_round8_performance_authoring_20261010/environment_receipt.json'
    environment=read(environment_path)if environment_path.exists()else None
    manifest=read(RUN/(stage+'_manifest.json'))
    checks=[]
    for name,h in manifest.items():
        checks.append({'name':'artifact_sha','file':name,'okay':sha256(Path(name).read_bytes()).hexdigest()==h})
    expected=protocol[stage+'_pairs']
    checks.append({'name':'complete_grid','okay':{(p['block'],p['case']['case_id'])for p in expected}=={(p['block'],p['case_id'])for p in s['pairs']}})
    values=[]
    metrics=('algorithm_cpu_seconds','algorithm_wall_seconds','search_cpu_seconds','screen_cpu_seconds',
             'observer_cpu_seconds','whole_simulation_cpu_seconds','whole_simulation_wall_seconds',
             'process_cpu_seconds','launch_to_exit_wall_seconds')
    def arm_metrics(arm):
        r=arm['receipt'];t=r['timings']
        return {key:(t[key]if key in t else r[key]if key in r else arm[key])for key in metrics}
    for pair in s['pairs']:
        checks.append({'name':'pair_exact','case_id':pair['case_id'],'block':pair['block'],'okay':pair['all_exact']})
        a={name:arm_metrics(pair['arms'][name])for name in('off','on')}
        delta={k:a['on'][k]-a['off'][k]for k in metrics}
        values.append({'case_id':pair['case_id'],'block':pair['block'],'arm_order':pair['arm_order'],
            'off':a['off'],'on':a['on'],'on_minus_off':delta,
            'work':{name:{k:pair['arms'][name]['receipt'][k]for k in('search_calls','search_work','screen_work','certified_queries')}for name in('off','on')},
            'cache_after_equal':pair['cache_after_equal'],
            'instant_tick_equal':pair['physical_comparison']['instant_detached_ticks'],
            'old_wrapper_all_exact':all(all(x['physical'].values())and x['queries']['all_exact']for x in pair['old_wrapper_comparison'].values())})
    aggregate={}
    for key in metrics:
        off=sum(v['off'][key]for v in values);on=sum(v['on'][key]for v in values)
        ds=[v['on_minus_off'][key]for v in values]
        aggregate[key]={'off_total':off,'on_total':on,'on_minus_off_total':on-off,
            'off_over_on_ratio':None if not on else off/on,
            'paired_delta_median':statistics.median(ds),'paired_delta_min':min(ds),'paired_delta_max':max(ds),
            'on_lower_pairs':sum(d<0 for d in ds),'equal_pairs':sum(d==0 for d in ds),'on_higher_pairs':sum(d>0 for d in ds)}
        if 'cpu_seconds'in key:
            intervals=[round(abs(d)*1e9)for d in ds if d]
            aggregate[key]['minimum_nonzero_absolute_paired_delta_ns']=min(intervals,default=None)
            aggregate[key]['observed_absolute_paired_delta_gcd_ns']=math.gcd(*intervals)if intervals else None
    cases=[]
    for name in sorted({v['case_id']for v in values}):
        both=[v for v in values if v['case_id']==name]
        checks.append({'name':'two_blocks_each_case','case_id':name,'okay':len(both)==2 and{v['block']for v in both}=={0,1}})
        cases.append({'case_id':name,'block_pair_deltas':[{k:v[k]for k in('block','arm_order','on_minus_off')}for v in both],
            'off_mean':{k:statistics.mean(v['off'][k]for v in both)for k in metrics},
            'on_mean':{k:statistics.mean(v['on'][k]for v in both)for k in metrics},
            'on_minus_off_mean':{k:statistics.mean(v['on_minus_off'][k]for v in both)for k in metrics}})
    work={arm:{k:sum(v['work'][arm][k]for v in values)for k in('search_calls','search_work','screen_work','certified_queries')}for arm in('off','on')}
    launch=[a for p in s['pairs']for a in p['arms'].values()]
    quantization={};cache_inputs={}
    for arm in launch:
        path=RUN/arm['receipt']['file'];b=path.read_bytes()
        bindings[str(path.relative_to(ROOT))]=sha256(b).hexdigest()
        raw=json.loads(gzip.decompress(b))
        cache_inputs.setdefault((arm['case_id'],arm['block']),{})[arm['arm']]=[
            {k:row[k]for k in('bag_id','private_cache_before_sha256','private_cache_before_entry_count',
                'certified','algorithm_cpu_ns','algorithm_wall_ns','search_cpu_ns','observer_cpu_ns')}
            for row in raw['measurement']['rows']]
        for row in raw['measurement']['rows']:
            kind='empty'if row['bag_id']is None else'loaded'
            for clock in('algorithm','search','screen','observer'):
                key=arm['arm']+'/'+kind+'/'+clock
                q=quantization.setdefault(key,{'queries':0,'active_intervals':0,'structurally_inactive':0,
                    'active_zero_cpu_count':0,'active_positive_cpu_count':0,'minimum_positive_cpu_ns':None,
                    'observed_positive_cpu_gcd_ns':0,'active_zero_cpu_wall_ns_sum':0,'active_zero_cpu_wall_ns_max':0})
                q['queries']+=1
                active=(clock not in('screen','search')or
                    clock=='screen'and row['enabled']and row['screen_status']!='invalid_request_delegate'or
                    clock=='search'and not row['certified'])
                if not active:q['structurally_inactive']+=1;continue
                q['active_intervals']+=1;n=row[clock+'_cpu_ns']
                if not n:
                    q['active_zero_cpu_count']+=1;q['active_zero_cpu_wall_ns_sum']+=row[clock+'_wall_ns']
                    q['active_zero_cpu_wall_ns_max']=max(q['active_zero_cpu_wall_ns_max'],row[clock+'_wall_ns'])
                else:
                    q['active_positive_cpu_count']+=1;q['observed_positive_cpu_gcd_ns']=math.gcd(q['observed_positive_cpu_gcd_ns'],n)
                    q['minimum_positive_cpu_ns']=n if q['minimum_positive_cpu_ns']is None else min(q['minimum_positive_cpu_ns'],n)
    for q in quantization.values():q['active_zero_cpu_fraction']=None if not q['active_intervals']else q['active_zero_cpu_count']/q['active_intervals']
    cache_cases=[];cache_groups={}
    for(case,block),arms in sorted(cache_inputs.items()):
        first_cert=next((i for i,r in enumerate(arms['on'])if r['certified']),None)
        mismatch=[];entry_mismatch=[]
        for i,(off,on)in enumerate(zip(arms['off'],arms['on'])):
            same=off['private_cache_before_sha256']==on['private_cache_before_sha256']
            if not same:mismatch.append(i)
            if off['private_cache_before_entry_count']!=on['private_cache_before_entry_count']:entry_mismatch.append(i)
            key=('/'.join(('empty'if on['bag_id']is None else'loaded',
                 'certified'if on['certified']else'delegated','same_cache'if same else'different_cache')))
            group=cache_groups.setdefault(key,{'queries':0,'on_minus_off_algorithm_cpu_ns':0,
                'on_minus_off_algorithm_wall_ns':0,'on_minus_off_search_cpu_ns':0,'on_minus_off_observer_cpu_ns':0})
            group['queries']+=1
            for field in('algorithm_cpu_ns','algorithm_wall_ns','search_cpu_ns','observer_cpu_ns'):
                group['on_minus_off_'+field]+=on[field]-off[field]
        precedes=bool(mismatch and(first_cert is None or mismatch[0]<first_cert))
        checks.append({'name':'cache_divergence_not_before_first_skip','case_id':case,'block':block,'okay':not precedes})
        cache_cases.append({'case_id':case,'block':block,'queries':len(arms['off']),
            'first_certified_ordinal':first_cert,'first_cache_sha_divergence_ordinal':mismatch[0]if mismatch else None,
            'private_cache_sha_mismatch_count':len(mismatch),'private_cache_entry_count_mismatch_count':len(entry_mismatch),
            'cache_sha_mismatch_ordinals':mismatch,'cache_entry_count_mismatch_ordinals':entry_mismatch,
            'cache_divergence_before_first_skip':precedes})
    result={'stage':stage,'paired_repetitions':len(values),'business_cases':len(cases),
        'physical_episodes':len(launch),'aggregate_nested_metrics_do_not_add':aggregate,'cases':cases,'pairs':values,'work':work,
        'all_exact':s['all_exact'],'input_checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),'checks':checks,
        'per_query_cpu_quantization_by_arm_role_timer':quantization,
        'paired_query_cache_history':{'paired_query_count':sum(c['queries']for c in cache_cases),
            'sha_mismatch_count':sum(c['private_cache_sha_mismatch_count']for c in cache_cases),
            'entry_count_mismatch_count':sum(c['private_cache_entry_count_mismatch_count']for c in cache_cases),
            'cases':cache_cases,'groups':cache_groups,
            'scope':'Initial routing cache and contract match. Later cached topology/LRU/lower/local records may differ after skipped searches. Category timing totals are descriptive, not attribution of an individual query CPU delta solely to its current certificate.'},
        'python_process_cpu_clock_metadata':vars(get_clock_info('process_time')),
        'environment_observation':environment,
        'worker_full_process_cpu_seconds':s['worker_final_process_cpu_seconds_sum'],'parent_interval_cpu_seconds':s['parent_cpu_seconds'],
        'coordinator_wall_makespan_seconds':s['wall_makespan_seconds'],
        'maximum_single_child_peak_working_set_bytes':max(a['receipt']['memory'].get('peak_working_set_bytes')or 0 for a in launch),
        'clock_boundaries':[{'case_id':a['case_id'],'block':a['block'],'arm':a['arm'],
            'launch_to_module_entry_wall_seconds':a.get('launch_to_module_entry_wall_seconds'),
            **{k:a['receipt'][k]for k in('module_entry_cumulative_cpu_seconds','imports_cpu_seconds','imports_wall_seconds',
                'child_invocation_cpu_seconds','child_invocation_wall_seconds','child_cumulative_cpu_at_receipt_seconds')}}for a in launch],
        'source_and_input_bindings':bindings,'analysis_cpu_seconds':process_time()-cpu,'analysis_wall_seconds':perf_counter()-wall,
        'resource_scope':'Pure SHA/read/paired arithmetic and raw query timer census; Markdown construction and final output serialization excluded. Nested performance metrics never added to process CPU.',
        'limits':['Two timing repeats do not create new business samples. All cases and both orders retained.',
                  'Algorithm CPU includes validity/dispatch/screen/search; excludes common observer. Whole simulation includes identical instrumentation.',
                  'Observer work varies naturally with private cache contents even under identical observation code. Query process_time intervals are quantized; zero is not absence of work or latency. Episode algorithm CPU is a sum of sampled intervals, not an exact fine-grained CPU attribution. Complete OS process lifetime is a separate stronger total measurement.',
                  'Elapsed times measured with up to three performance children and independent main-line workers; not unloaded production latency or hard realtime.',
                  'Search work and screen record work are different units. Private cache history may change; candidate and physical equality are checked separately.']}
    result['limits'].append('Cold means the explicitly exported private routing cache is empty at algorithm start. OS filesystem/page caches are neither flushed nor claimed cold; process isolation does not imply an unloaded or hardware-cache-isolated machine.')
    lines=['# Round8 terminal-screen paired performance', '',
        f"{stage}: {len(cases)} business cases, 2 blocks, {len(values)} on/off pairs, {len(launch)} independent physical episodes. All exact: {s['all_exact']}. All predeclared cases and timing regressions retained.", '',
        '## Complete paired timing totals', '',
        '| Metric (seconds) | Off | On | On − off | Off/on | Lower / equal / higher pairs |',
        '|---|---:|---:|---:|---:|---:|']
    for key,a in aggregate.items():
        ratio='n/a'if a['off_over_on_ratio']is None else f"{a['off_over_on_ratio']:.4f}"
        lines.append(f"| {key} | {a['off_total']:.6f} | {a['on_total']:.6f} | {a['on_minus_off_total']:.6f} | {ratio} | {a['on_lower_pairs']}/{a['equal_pairs']}/{a['on_higher_pairs']} |")
    lines+=['','These totals are nested measurement axes, not additive resource cost. Launch elapsed totals are descriptive per-invocation sums, never global elapsed time.', '',
        f"Search work {work['off']['search_work']} → {work['on']['search_work']}; extra screen work {work['on']['screen_work']}; queries {work['off']['search_calls']} in each arm. Screen record work is not the same unit as search expansion work.", '',
        '## Every business case (mean of both blocks)', '',
        '| Case | Algorithm off CPU | Algorithm on CPU | CPU delta | Whole-simulation CPU delta | Full-process CPU delta |',
        '|---|---:|---:|---:|---:|---:|']
    for c in cases:
        lines.append(f"| {c['case_id']} | {c['off_mean']['algorithm_cpu_seconds']:.6f} | {c['on_mean']['algorithm_cpu_seconds']:.6f} | {c['on_minus_off_mean']['algorithm_cpu_seconds']:.6f} | {c['on_minus_off_mean']['whole_simulation_cpu_seconds']:.6f} | {c['on_minus_off_mean']['process_cpu_seconds']:.6f} |")
    lines+=['','Each block and its exact arm order and all deltas are in analysis.json. The same JSON records startup/import boundaries and single-worker lifetime peak memory.','',*['- '+x for x in result['limits']], '',
        f"Analysis: {result['input_checks']} checks, {result['failed_checks']} failures; CPU {result['analysis_cpu_seconds']:.6f}s, wall {result['analysis_wall_seconds']:.6f}s through calculation, excluding final output writes."]
    if environment:
        lines+=['',f"Environment observed during formal execution: Python {environment['python_version']}, {environment['platform']}, {environment['cpu_physical']} physical / {environment['cpu_logical']} logical CPU cores, {environment['memory_total_bytes']} bytes RAM. This snapshot is not a pre-run load or frequency guarantee. Performance children capped at three; concurrent main-line workers capped at six."]
    lines+=['','## CPU timer quantization','',
        '| Arm / query role / timer | Active intervals | CPU-zero count | CPU-zero fraction | Minimum positive CPU (ms) | Largest elapsed time with CPU zero (ms) |',
        '|---|---:|---:|---:|---:|---:|']
    for key,q in sorted(quantization.items()):
        fraction='inactive'if q['active_zero_cpu_fraction']is None else f"{q['active_zero_cpu_fraction']:.4%}"
        minimum='n/a'if q['minimum_positive_cpu_ns']is None else f"{q['minimum_positive_cpu_ns']/1e6:.6f}"
        lines.append(f"| {key} | {q['active_intervals']} | {q['active_zero_cpu_count']} | {fraction} | {minimum} | {q['active_zero_cpu_wall_ns_max']/1e6:.6f} |")
    lines+=['','Disabled screen and skipped delegate intervals are counted as structurally inactive, separately from measured active zero CPU. JSON includes observed increment GCD and paired-difference minimum nonzero/GCD. These are observed quantization, not a claimed accuracy bound; elapsed measurements include concurrent load.']
    ch=result['paired_query_cache_history']
    lines+=['','## Routing-cache history', '',
        f"Among {ch['paired_query_count']} corresponding queries, pre-query private-cache SHA differs in {ch['sha_mismatch_count']} and entry count differs in {ch['entry_count_mismatch_count']}. Each episode starts with identical empty routing cache; skipped searches can change later warming and LRU history. This is part of the complete method trajectory, not a reason to force cache contents equal.", '',
        '| Query role / decision / prior cache | Queries | Algorithm CPU delta (s) | Observer CPU delta (s) |',
        '|---|---:|---:|---:|']
    for key,g in sorted(cache_groups.items()):lines.append(f"| {key} | {g['queries']} | {g['on_minus_off_algorithm_cpu_ns']/1e9:.6f} | {g['on_minus_off_observer_cpu_ns']/1e9:.6f} |")
    lines+=['','Every pair records first screen and first cache-divergence ordinals. Per-query deltas mix current screening, accumulated cache history, timer quantization and runtime variation; they are not clean causal net savings for the current certificate. Whole-episode on/off comparisons remain the primary experiment.']
    lines+=['','[Python process CPU and elapsed clock definitions](https://docs.python.org/3.11/library/time.html#time.process_time) distinguish CPU from elapsed time; integer nanoseconds avoid float representation loss. [Microsoft GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) defines cumulative per-process kernel/user CPU in 100 ns units. Neither representation unit establishes the empirical precision of each short sampled interval.']
    (output/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    (output/'PERFORMANCE.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (output/'analyze.py').write_bytes(Path(__file__).read_bytes())
    (output/'manifest.json').write_text(json.dumps({p.name:sha256(p.read_bytes()).hexdigest()for p in output.iterdir()if p.is_file()},indent=2),encoding='utf8')
    print(json.dumps({'checks':result['input_checks'],'failed_checks':result['failed_checks'],'cpu_seconds':result['analysis_cpu_seconds'],'algorithm':aggregate['algorithm_cpu_seconds']}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main(sys.argv[1],sys.argv[2])
