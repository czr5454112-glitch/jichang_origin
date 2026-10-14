"""Read-only fifth-round resource ledger; never imports simulation code.

Run with --output <fresh directory>. Pending runs remain pending. Resource
boundaries are explicit; nested branch/collection totals are not added twice.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import process_time, perf_counter

BASE=Path('outputs/experiments/ics_circulation_v3')


def collect(output):
    started_cpu,started_wall=process_time(),perf_counter()
    if Path(output).exists():
        raise FileExistsError('Resource ledger output must be a fresh directory')
    bound={}; rows=[]; checks=[]

    def read(path):
        path=Path(path);data=path.read_bytes();bound[str(path)]=sha256(data).hexdigest()
        return json.loads(data.decode('utf-8-sig'))

    def component(scope,value,quality,field,note=''):
        return {'scope':scope,'cpu_seconds':value,'quality':quality,'source_field':field,'note':note}

    def row(identity,label,source,*,status='complete',components=(),wall=None,counts=None,notes=()):
        obj={'id':identity,'label':label,'source':str(source)if source else None,'status':status,
             'cpu_components':list(components),'wall_seconds_individual_invocation':wall,
             'work_counts':counts or {},'notes':list(notes)}
        rows.append(obj);return obj

    def run_summary(identity,folder,label,kind='empty',planned=None):
        directory=BASE/folder;path=directory/'summary.json'
        if not path.exists():
            row(identity,label,path,status='pending',counts={'planned_requests_or_episodes':planned},
                components=[component('worker',None,'pending','summary not yet written'),component('parent',None,'pending','summary not yet written')],
                notes=['No resource number inferred from budgets or partially written case files.'])
            return
        s=read(path)
        if kind=='empty':
            worker,parent,wall=s['case_invocation_cpu_seconds_recorded'],s['parent_cpu_seconds'],s['coordinator_wall_seconds']
            unknown=s['cases_with_unavailable_invocation_accounting'];wf='case_invocation_cpu_seconds_recorded'
            counts={'planned':s['planned_episodes'],'recorded':s['recorded_episodes'],'statuses':s['statuses'],'unknown_worker_resources':unknown}
            checks.append({'id':identity,'worker_cpu_matches_rows':abs(worker-sum(r.get('invocation_cpu_seconds')or 0 for r in s['rows']))<1e-8})
        elif kind=='scenario':
            worker,parent,wall=s['case_cpu_seconds_recorded'],s['parent_cpu_seconds'],s['wall_seconds']
            unknown=s['cases_unknown_resources'];wf='case_cpu_seconds_recorded'
            counts={'planned':s['planned_episodes'],'recorded':len(s['rows']),'statuses':s['statuses'],'unknown_worker_resources':unknown,
                'action_evaluations':sum(r.get('action_evaluations',0)for r in s['rows']),
                'requested_scenarios':sum(r.get('requested_scenarios',0)for r in s['rows']),
                'physical_proxy_calls':sum(r.get('physical_proxy_calls',0)for r in s['rows']),
                'duplicate_reuses':sum(r.get('duplicate_reuses',0)for r in s['rows'])}
            checks.append({'id':identity,'worker_cpu_matches_rows':abs(worker-sum(r.get('invocation_cpu_seconds')or 0 for r in s['rows']))<1e-8})
            checks.append({'id':identity,'scenario_requests_equal_physical_plus_reuse':counts['requested_scenarios']==counts['physical_proxy_calls']+counts['duplicate_reuses']})
        elif kind=='network':
            worker,parent,wall=s['worker_cpu_seconds_sum'],s['parent_cpu_seconds'],s['wall_makespan_seconds']
            unknown=0 if s['complete_resource_accounting'] else 1;wf='worker_cpu_seconds_sum'
            counts={k:s[k]for k in ('request_count','actual_branches','cache_reused','status_counts','worker_failures')}
            if s['complete_resource_accounting'] and not s['worker_failures']:
                checks.append({'id':identity,'requests_equal_physical_plus_reuse':s['request_count']==s['actual_branches']+s['cache_reused']})
        elif kind=='nominal':
            worker,parent,wall=s['case_cpu_seconds_recorded'],s['parent_cpu_seconds'],s['wall_makespan_seconds']
            unknown=s['unknown_resource_cases'];wf='case_cpu_seconds_recorded'
            counts={k:s[k]for k in ('planned_requests','unique_requested','actual_physical_calls_recorded','unknown_physical_call_statuses','cache_hits','status_counts')}
            if not s['unknown_physical_call_statuses']:
                checks.append({'id':identity,'requests_equal_physical_plus_reuse':s['planned_requests']==s['actual_physical_calls_recorded']+s['cache_hits']})
        row(identity,label,path,components=[component('worker invocations',worker,'complete_recorded_scope'if not unknown else 'lower_bound',wf,
            'Includes nested deployment/branch/collection work within this invocation; do not add those subtotals.'),
            component('coordinator parent',parent,'complete_recorded_scope','parent_cpu_seconds')],wall=wall,counts=counts,
            notes=['Measured instrumented scopes exclude unrecorded interpreter/bootstrap work; not a claim of complete machine-wide CPU.'])

    run_summary('empty_pilot28','phase4_w3_empty_improvement_pilot_20261010','empty pilot 28',planned=28)
    run_summary('empty_formal252','phase4_w3_empty_improvement_20261010','empty full 252',planned=252)
    path=BASE/'phase4_w3_empty_factorial_20261010/preflight_failure.json';s=read(path)
    row('factorial_preflight','factorial first preflight failure',path,status='failed_preflight',
        components=[component('preflight process',None,'unknown','not recorded')],counts={'physical_episodes':s['physical_episodes']},notes=[s['reason']])
    path=BASE/'phase4_w3_empty_factorial_repaired_20261010/aborted_run.json';s=read(path)
    row('factorial_aborted','factorial aborted artifact-comparison run',path,status='aborted',
        components=[component('successful deployment records only',s['successful_deployment_cpu_seconds_lower_bound'],'lower_bound','successful_deployment_cpu_seconds_lower_bound'),
                    component('failed verification, in-flight, coordinator and serialization',None,'unknown','lost/incomplete accounting')],
        counts={'preserved_case_files':s['preserved_case_files'],'physical_episodes_at_least':s['physical_episodes_at_least'],'case_statuses':s['case_statuses']},notes=[s['lost_record_explanation']])
    path=Path('.tmp/factorial_default_replay_debug.json');s=read(path)
    row('factorial_debug','factorial separate default replay diagnostic',path,
        components=[component('one deployment',s['metrics']['process_cpu_seconds'],'complete_recorded_scope','metrics.process_cpu_seconds'),
                    component('imports, caller and file serialization',None,'unknown','not recorded')],
        wall=s['metrics']['wall_seconds'],counts={'new_physical_episodes':1},notes=['Separate run, not a copy of an old episode.'])
    run_summary('factorial_full144','phase4_w3_empty_factorial_complete_20261010','factorial full rerun 144',planned=144)
    run_summary('scenario_pilot16','phase4_w3_empty_scenarios_pilot_20261010','public scenario pilot 16','scenario',16)
    run_summary('scenario_full144','phase4_w3_empty_scenarios_20261010','public scenario full 144','scenario',144)
    path=BASE/'phase4_w3_network_full_cycle_pilot_20261010/interruption.json';s=read(path)
    row('network_bad_pilot','network initial interrupted pilot',path,status='aborted',
        components=[component('three completed collections',s['recorded_collection_cpu_seconds'],'complete_recorded_scope','recorded_collection_cpu_seconds'),
                    component('completed saved physical branches',s['recorded_branch_cpu_seconds_lower_bound'],'lower_bound','recorded_branch_cpu_seconds_lower_bound'),
                    component('interrupted in-flight, setup, serialization and parent',None,'unknown','invocation_cpu_not_recoverable')],
        counts={'recorded_branch_calls_lower_bound':s['recorded_branch_calls_lower_bound'],'collection_invocations':3},notes=[s['reason']])
    run_summary('network_pilot_v2','phase4_w3_network_full_cycle_pilot_v2_20261010','network corrected pilot 12','network',12)
    rows[-1]['notes']+=['Fresh three collections and all 12 branches; no reuse from interrupted pilot.']
    run_summary('network_full2176','phase4_w3_network_full_cycle_20261010','network full 2176 requests','network',2176)
    rows[-1]['notes']+=['Six global memo shards each newly collect three scenes (18 collection invocations, not 18 independent samples). Expected memo aliases are not new physical branches. Nested scene/branch CPU is already within worker invocation sum. CPU caps are not resource observations.']
    path=BASE/'phase4_w3_network_opportunity_census_20261010/summary.json';s=read(path)
    row('network_census','network opportunity census',path,
        components=[component('three worker collections',s['worker_cpu_seconds'],'complete_recorded_scope','worker_cpu_seconds'),
                    component('parent',s['parent_cpu_seconds'],'complete_recorded_scope','parent_cpu_seconds')],wall=s['wall_seconds'],
        counts={'physical_collection_invocations':len(s['scenes'])},notes=['These are separate census simulations; no new counterfactual labels.'])
    path=BASE/'phase4_w3_network_nominal_opportunities_20261010/initialization_failure.json';s=read(path)
    row('nominal_preflight','nominal first collection and denominator preflight',path,status='failed_preflight_after_collection',
        components=[component('three completed collections',s['complete_collection_cpu_seconds'],'complete_recorded_scope','complete_collection_cpu_seconds'),
                    component('initial parent/setup',None,'unknown','parent_cpu_seconds=null')],
        counts={k:s[k]for k in ('attempts','nonempty','actual_requests','counterfactual_physical_calls')},notes=[s['qualification']])
    path=BASE/'phase4_w3_network_nominal_opportunities_repaired_20261010/collection_summary.json';s=read(path)
    row('nominal_collection_reuse','nominal repaired collection reuse',path,status='reused_artifact',
        components=[component('new collection physical work',0,'certified_zero','new_physical_collection_calls=0'),
                    component('copy/repair setup process',None,'unknown','not recorded')],
        counts={'new_physical_collection_calls':s['new_physical_collection_calls']},notes=[f"Original collection CPU {s['reused_original_collection_cpu_seconds']} s already counted in nominal_preflight; byte copy is not a new collection."])
    run_summary('nominal_pilot12','phase4_w3_network_nominal_opportunities_repaired_20261010/pilot','nominal pilot 12','nominal',12)
    run_summary('nominal_full693','phase4_w3_network_nominal_opportunities_repaired_20261010/full','nominal full 693','nominal',693)
    rows[-1]['notes']+=['Full run actually reruns the 12 pilot identities; no cross-run memo reuse. 693 = 172*4 + 1*2 + 1*3, with six K0 attempts retained separately.']

    for identity,folder in [('tests700','phase4_w3_round5_validation_20261010'),('tests717','phase4_w3_round5_final_validation_20261010')]:
        path=BASE/folder/'validation_manifest.json';s=read(path)
        row(identity,f"regression suite {s['counts']['testcases']}",path,
            components=[component('pytest host process',s['process_cpu_seconds'],'complete_recorded_scope','process_cpu_seconds',s['cpu_scope']),
                        component('any child subprocess CPU',None,'unknown','excluded by cpu_scope; existence/amount unquantified')],
            wall=s['wall_seconds'],counts=s['counts'],notes=['700 and 717 are separate invocations; neither substitutes for the other.'])
    path=BASE/'phase4_w3_empty_factorial_analysis_20261010/failure_audit_validation.json';s=read(path)
    row('tests2_post717','two post-717 injected failure tests',path,
        components=[component('pytest invocation',None,'unknown','CPU and pytest wall not recorded')],counts={'passed':s['passed'],'failed':s['failed']},
        notes=['Separate timing boundary: report 717 + 2, not a 719-test invocation. Mocked deployments; no new physical episodes.'])
    path=Path('.tmp/round5_empty_authoring_validation_20261010.json');s=read(path)
    row('authoring_smoke','empty authoring integration smoke',path,
        components=[component('one smoke deployment',s['pilot']['cpu_seconds'],'complete_recorded_scope','pilot.cpu_seconds'),
                    component('smoke imports/caller',None,'unknown','not recorded')],counts={'physical_smoke_episodes':1},notes=[s['pilot']['interpretation']])
    row('authoring_tests','early authoring and focused tests',path,
        components=[component('all early focused test invocations',None,'unknown','not metered')],
        counts={'recorded_checks':s['checks']},notes=['Includes initial fixture failure and Temp ACL setup error. Later factorial 10, combined 30, SAA 7 and independent small suites were real invocations but not comprehensively CPU-metered; do not infer CPU from test counts.'])

    # Only direct analysis/audit clocks are included. Embedded source-run
    # resources under analysis.resources are already counted above.
    analysis_files=[]
    for directory in sorted(BASE.glob('*20261010')):
        if not directory.is_dir():continue
        if '_analysis' in directory.name and (directory/'analysis.json').exists():analysis_files.append(directory/'analysis.json')
        if directory.name=='phase4_w3_round5_independent_review_20261010':
            analysis_files += [p for p in sorted(directory.glob('*.json')) if p.name not in ('manifest.json',)]
    for name in ('audit_and_values.json','feature_coverage.json','mechanisms.json'):
        nominal_audit=BASE/'phase4_w3_network_nominal_analysis_20261010'/name
        if nominal_audit.exists():analysis_files.append(nominal_audit)
    for name in ('analysis.json','shared_tick_evidence.json'):
        scenario_mechanisms=BASE/'phase4_w3_empty_scenario_mechanisms_20261010'/name
        if scenario_mechanisms.exists():analysis_files.append(scenario_mechanisms)
    for relative in ('phase4_w3_network_full_cycle_analysis_20261010/summary.json',
                     'phase4_w3_round5_visuals_20261010/all_configurations/manifest.json'):
        extra_analysis=BASE/relative
        if extra_analysis.exists():analysis_files.append(extra_analysis)
    if len(analysis_files)!=len(set(analysis_files)):
        raise ValueError('An analysis invocation was listed twice')
    for path in analysis_files:
        s=read(path)
        ckey=next((k for k in ('analysis_cpu_seconds','cpu_seconds','process_cpu_seconds')if isinstance(s.get(k),(int,float))),None)
        wkey=next((k for k in ('analysis_wall_seconds','wall_seconds')if isinstance(s.get(k),(int,float))),None)
        # Binding-only manifests have no runtime; retain audit evidence but do
        # not manufacture separate work unless this file describes an audit.
        if not ckey and not any(k in s for k in ('schema','checks','counts')):continue
        audit_row=row('analysis:'+str(path.relative_to(BASE)),path.parent.name+'/'+path.name,path,
            components=[component('analysis/audit process',s[ckey]if ckey else None,'complete_recorded_scope'if ckey else 'unknown',ckey or 'not recorded')],
            wall=s[wkey]if wkey else None,counts={k:s[k]for k in ('checks','failed_checks','errors')if k in s},
            notes=['Pure-file/read-only audit time only; embedded original experiment resources are not added again. Each independently repeated audit invocation is separately counted.'])
        if path==BASE/'phase4_w3_network_full_cycle_analysis_20261010/summary.json':
            audit_row['nonadditive_physical_work_details']={key:s[key]for key in (
                'unique_physical_search_calls','unique_physical_search_work','unique_branch_cpu_seconds',
                'resources_detail','resource_note')}
            audit_row['notes'].append('These physical work details are metadata for the already-counted formal run, not work performed by this analyzer. Single-worker peak memory must not be summed into a simultaneous process-family peak.')
    row('analysis_unmetered','other unmetered development and analysis',None,
        components=[component('pure-file tools, initial failed analysis, plots, py_compile and inspection',None,'unknown','no saved process CPU measurement')],
        notes=['Includes empty tie/coverage analysis, factorial mechanism extraction, first SAA pilot analyzer KeyError(proxy_bags), and three plot generations. Initial SAA analyzer parent reports tool wall 3.2600039s, which is not process CPU and is not added to a makespan. Ad hoc shell/tool probes were not comprehensively timed.'])
    for path in sorted(Path(__file__).resolve().parent.glob('*/ledger.json')):
        s=read(path)
        row('prior_ledger:'+path.parent.name,'previous resource ledger generation '+path.parent.name,path,
            components=[component('pure-file ledger generation',s['ledger_generation_cpu_seconds'],'complete_recorded_scope','ledger_generation_cpu_seconds',s['ledger_generation_scope'])],
            wall=s['ledger_generation_wall_seconds'],notes=['Only the prior summarizer itself is added; its embedded experiment totals are never re-added.'])

    # Verify completed evidence did not change during this read-only pass.
    changed=[name for name,expected in bound.items()if sha256(Path(name).read_bytes()).hexdigest()!=expected]
    numeric=[c for r in rows for c in r['cpu_components']if c['cpu_seconds']is not None]
    complete_sum=sum(c['cpu_seconds']for c in numeric if c['quality']in ('complete_recorded_scope','certified_zero'))
    lower_sum=sum(c['cpu_seconds']for c in numeric if c['quality']=='lower_bound')
    cpu,wall=process_time()-started_cpu,perf_counter()-started_wall
    payload={'schema':'ics_round5_resource_ledger_v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_only':True,'new_physical_simulations':0,'rows':rows,'checks':checks,'bound_evidence_sha256':bound,
        'bound_evidence_changed':changed,'pending_runs':[r['id']for r in rows if r['status']=='pending'],
        'totals':{'sum_complete_recorded_scope_cpu_seconds':complete_sum,
            'additional_lower_bound_cpu_seconds':lower_sum,'known_nonoverlapping_cpu_seconds_floor':complete_sum+lower_sum,
            'unknown_cpu_component_count':sum(c['quality']=='unknown'for r in rows for c in r['cpu_components']),
            'pending_cpu_component_count':sum(c['quality']=='pending'for r in rows for c in r['cpu_components']),
            'complete_fifth_round_cpu_known':False,'global_wall_makespan_seconds':None,
            'reason':'Known disjoint measured CPU scopes can add; unknown and pending work prevents full total. Concurrent run walls cannot be summed without a timeline.'},
        'ledger_generation_cpu_seconds':cpu,'ledger_generation_wall_seconds':wall,
        'ledger_generation_scope':'This pure-file generation through evidence verification; final serialization and shell overhead excluded; not included in above subtotals.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'ledger.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 第五轮实际资源与失败账','',
        '只读已落盘记录；实际耗时与预算分开。完整值只对明确的计量区间成立，整个第五轮CPU仍不完全可知。已知CPU可按互不重叠的区间相加；并发壁钟不得相加。',
        '', '| invocation | state | recorded complete CPU(s) | extra lower bound(s) | unknown components | individual wall(s) |',
        '|---|---|---:|---:|---:|---:|']
    for r in rows:
        cs=r['cpu_components'];a=sum(c['cpu_seconds']or 0 for c in cs if c['quality']in ('complete_recorded_scope','certified_zero'))
        b=sum(c['cpu_seconds']or 0 for c in cs if c['quality']=='lower_bound');u=sum(c['quality']in ('unknown','pending')for c in cs)
        wt='unknown'if r['wall_seconds_individual_invocation']is None else f"{r['wall_seconds_individual_invocation']:.3f}"
        av=f'{a:.6f}' if any(c['quality']in ('complete_recorded_scope','certified_zero')for c in cs)else 'unknown'
        lines.append(f"| {r['label']} | {r['status']} | {av} | {b:.6f} | {u} | {wt} |")
    lines+=['',f"已完整计量区间的CPU小计：{complete_sum:.6f}s；另外可恢复的CPU下界：{lower_sum:.6f}s；两者合计的已知工作下界：{complete_sum+lower_sum:.6f}s。此数不含尚未完成/未知区间，也不含本汇总器自身{cpu:.6f}s的已记录计算。禁止称为第五轮完整总CPU。",'',
        f"待完成：{', '.join(payload['pending_runs']) or '无主批次待完成'}。本次绑定{len(bound)}份证据，变化{len(changed)}份。",
        '', '父进程与worker分别保留；已含在worker内的branch/collection CPU不再次加入。nominal首采集复制到repaired目录仅记一次；12pilot与full693实际独立运行，身份相同不代表复用。full-cycle memo alias和SAA重复情景请求保留请求权重，但不算新增物理分支。',
        '', '700与717是两次独立全套验证；新增2例在717完成后单独运行，保留717+2边界。验证计量为pytest宿主CPU，子进程CPU未包括；旧失败试验的失配记录与中断工作不会零填。',
        '', '所有路径、字段、计量范围、失败原因、重复计数排除规则与SHA见ledger.json。各行wall只属于其运行，不提供跨并发相加的总wall。']
    (output/'RESOURCE_LEDGER.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (output/'summarize.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'output':str(output),'pending':payload['pending_runs'],'totals':payload['totals'],'checks':checks,'changed':changed},ensure_ascii=False))
    if changed or any(v is False for c in checks for k,v in c.items()if k!='id'):raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
