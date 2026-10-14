"""Pure-file round-six mechanisms. No imports from the simulation package."""
from collections import Counter
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path
from time import process_time,perf_counter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
RUN=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_same_zone_supply_repaired_20261010'
POLICIES=('old32','old64','same_zone32plus32')

def normalized(proposals):
    return [{k:p.get(k)for k in ('tray_id','bag_id','destination_node','legs','usable_at')}for p in proposals]

def brief(call):
    d=call.get('diagnostics',{})
    return {'time':call['time'],'state_sha256':call['state_sha256'],
        'cursor_at_call':call['cursor_at_call'],
        'next_slow_trigger_at_after_clock_advance':call['next_slow_trigger_at_after_clock_advance'],
        'published_forecasts':call['published_forecasts'],'known_supply':call['known_supply'],
        'trays':call['snapshot_before']['trays'],'existing_empty_targets':call['snapshot_before']['empty_targets'],
        'existing_plans':call['snapshot_before']['plans'],'proposals':normalized(call.get('proposals',[])),
        'proposal_details':d.get('proposal_details',[]),'demand':d.get('demand',[]),
        'same_zone_enhancement_blocked':d.get('same_zone_enhancement_blocked'),
        'same_zone_guards':d.get('same_zone_guards',[]),
        'candidate_comparisons':d.get('candidate_comparisons',[]),
        'candidate_rejections':d.get('candidate_rejections',[]),'donor_rejections':d.get('donor_rejections',[]),
        'candidate_budget_omissions':d.get('candidate_budget_omissions'),
        'search_calls':d.get('search_calls'),'search_expansions':d.get('search_expansions'),
        'guard_work':d.get('guard_work'),'bounded_stop':d.get('bounded_stop')}

def task_changes(a,b):
    old={r['bag_id']:r for r in a['evaluation_ledger']};new={r['bag_id']:r for r in b['evaluation_ledger']}
    rows=[]
    for key in sorted(set(old)|set(new)):
        x,y=old.get(key),new.get(key)
        if x is None or y is None:
            rows.append({'bag_id':key,'identity_mismatch':True,'old':x,'new':y});continue
        delta={k:None if x[k]is None or y[k]is None else y[k]-x[k]for k in ('load_time','completed_at')}
        if any(x[k]!=y[k]for k in ('load_time','completed_at','observed')):
            rows.append({'bag_id':key,'arrival':x['arrival'],'deadline':x['deadline'],'protected':x['protected'],
                         'old':{k:x[k]for k in ('load_time','completed_at','observed')},
                         'new':{k:y[k]for k in ('load_time','completed_at','observed')},'delta':delta})
    return rows

def pair(a,b):
    x,y=a['metrics'],b['metrics'];ac={r['time']:r for r in a['slow_calls']};bc={r['time']:r for r in b['slow_calls']}
    divergences=[]
    for tick in sorted(set(ac)&set(bc)):
        if normalized(ac[tick].get('proposals',[]))!=normalized(bc[tick].get('proposals',[])):
            divergences.append({'time':tick,'same_public_state':ac[tick]['state_sha256']==bc[tick]['state_sha256'],
                'old':brief(ac[tick]),'new':brief(bc[tick])})
    changes=task_changes(a,b)
    task_regressions=[r for r in changes if not r.get('identity_mismatch')and any((r['delta'][k]or 0)>0 for k in ('load_time','completed_at'))]
    outcomes=Counter()
    old_tasks={r['bag_id']:r for r in a['evaluation_ledger']};new_tasks={r['bag_id']:r for r in b['evaluation_ledger']}
    for identity in sorted(set(old_tasks)|set(new_tasks)):
        def outcome(task):
            if task is None:return 'missing_identity'
            if task['completed_at']is None:return 'unfinished'
            return 'on_time'if task['completed_at']<=task['deadline']else 'late'
        outcomes[outcome(old_tasks.get(identity))+'->'+outcome(new_tasks.get(identity))]+=1
    return {'old_case':a['case'],'new_case':b['case'],
        'delta_cost':None if x['total_cost']is None or y['total_cost']is None else y['total_cost']-x['total_cost'],
        'delta_components':None if x['cost_components']is None or y['cost_components']is None else
            {k:y['cost_components'][k]-x['cost_components'][k]for k in x['cost_components']},
        'delta_on_time':y['on_time']-x['on_time'],'delta_completed':y['completed']-x['completed'],
        'statuses':[a['status'],b['status']],'changed_tasks':changes,
        'task_outcome_transition_counts':dict(outcomes),'task_regressions':task_regressions,
        'first_slow_action_divergence':divergences[0]if divergences else None,
        'slow_action_divergence_count':len(divergences),
        'all_slow_action_differences':[{'time':r['time'],'same_public_state':r['same_public_state'],
            'old_proposals':r['old']['proposals'],'new_proposals':r['new']['proposals']}for r in divergences],
        'actual_control_call_times_equal':list(ac)==list(bc),
        'delta_search_calls':y['search_calls']-x['search_calls'],'delta_search_work':y['search_work']-x['search_work']}

def analyze(stage, label=None):
    cpu0,wall0=process_time(),perf_counter();dest=OUT/(label or stage)
    if dest.exists():raise FileExistsError(dest)
    bound={};checks=[]
    def read(path):
        data=path.read_bytes();key=str(path.relative_to(ROOT));actual=sha256(data).hexdigest()
        if key in bound and bound[key]!=actual:raise ValueError('Input changed between reads: '+key)
        bound[key]=actual
        if path.suffix=='.gz':data=gzip.decompress(data)
        return json.loads(data.decode('utf-8-sig'))
    protocol=read(OUT/'selection_protocol.json');exp=read(RUN/'protocol.json')
    summary=read(RUN/stage/'summary.json');manifest=read(RUN/stage/'manifest.json')
    expected={r['case_id']for r in exp['stage_planned_cases'][stage]}
    checks.append({'kind':'complete_requested_denominator','okay':expected=={r['case_id']for r in summary['rows']}})
    cases={};compact=[]
    for row in summary['rows']:
        if not row.get('file'):
            compact.append({'case_id':row['case_id'],'status':row['status'],'failure_row':row});continue
        path=RUN/row['file'];s=read(path);cases[row['case_id']]=path
        checks.append({'kind':'raw_sha','case_id':row['case_id'],'okay':sha256(path.read_bytes()).hexdigest()==row['sha256']==manifest[path.name]})
        calls=s['slow_calls'];reasons=Counter(r['reason']for c in calls for r in c.get('diagnostics',{}).get('candidate_rejections',[]))
        same=[(c,d)for c in calls for d in c.get('diagnostics',{}).get('proposal_details',[])if d.get('domain')=='same_zone']
        compact.append({'case':s['case'],'summary_status':row['status'],
            'old32_replication':s.get('old32_replication'),'metrics':s['metrics'],'slow_calls':len(calls),
            'invocation_cpu_seconds':row.get('invocation_cpu_seconds'),
            'invocation_wall_seconds':row.get('invocation_wall_seconds'),
            'cycle_cpu_is_nested':True,
            'active_budget_parameters':s['active_policy_contract']['effective_controller_scalar_parameters'],
            'case_budget':s['budget'],'case_budget_stop':s['budget_stop'],
            'search_status_counts':dict(Counter(q.get('status')for q in s['searches'])),
            'slow_bounded_stop_counts':dict(Counter(c.get('diagnostics',{}).get('bounded_stop')for c in calls if c.get('diagnostics',{}).get('bounded_stop'))),
            'max_guard_work_single_slow_call':max((c.get('diagnostics',{}).get('guard_work',0)for c in calls),default=0),
            'guard_work_limit_reached_calls':sum(c.get('diagnostics',{}).get('guard_work',0)>=s['active_policy_contract']['effective_controller_scalar_parameters'].get('max_guard_work',float('inf'))for c in calls),
            'guard_work_separate_from_case_search_work':True,
            'candidate_budget_omissions':{d:sum(c.get('diagnostics',{}).get('candidate_budget_omissions',{}).get(d,0)for c in calls)for d in ('cross_zone','same_zone')},
            'demand_units_truncated_calls':sum(bool(c.get('diagnostics',{}).get('demand_units_truncated'))for c in calls),
            'same_zone_enhancement_block_counts':dict(Counter(str(c.get('diagnostics',{}).get('same_zone_enhancement_blocked'))for c in calls if c.get('diagnostics',{}).get('same_zone_enhancement_blocked'))),
            'same_zone_commit_count':len(same),'same_zone_commits':[{'time':c['time'],**d}for c,d in same],
            'candidate_rejection_reasons':dict(reasons),
            'guard_work':sum(c.get('diagnostics',{}).get('guard_work',0)for c in calls),
            'domain_query_totals':{d:sum(c.get('diagnostics',{}).get('search_calls_by_domain',{}).get(d,0)for c in calls)for d in ('cross_zone','same_zone')},
            'first_same_zone_commit':brief(same[0][0])if same else None,
            'specified_slow_ticks':{str(c['time']):brief(c)for c in calls if stage=='mechanism'and c['time']in (127,139)},
            'state_final_trays':s['result']['final_trays']if s.get('result')else None})
        for c in calls:
            checks.append({'kind':'only_published','case_id':row['case_id'],'time':c['time'],
                'okay':all(f['published_at']<=c['time']for f in c['published_forecasts'])})
        del s,calls
    pairs=[];interactions=[]
    def load(name):
        return read(cases[name])if name in cases else None
    if stage=='mechanism':
        for policy in POLICIES:
            a=load(f'counterflow_d0040_c0__{policy}');b=load(f'counterflow_d0040_c1__{policy}')
            if a and b:interactions.append(pair(a,b))
        for c in (0,1):
            a=load(f'counterflow_d0040_c{c}__old32')
            for policy in POLICIES[1:]:
                b=load(f'counterflow_d0040_c{c}__{policy}')
                if a and b:pairs.append(pair(a,b))
    else:
        units=sorted({(r['scene'],r['tape_id'])for r in summary['rows']})
        for scene,tape in units:
            a=load(f'{scene}__{tape}__old32')
            for policy in POLICIES[1:]:
                b=load(f'{scene}__{tape}__{policy}')
                if a and b:pairs.append(pair(a,b))
    a=b=None
    for p in pairs+interactions:
        if p['delta_components']is not None and all(r.get('delta',{}).get('load_time')is not None for r in p['changed_tasks']):
            checks.append({'kind':'wait_delta_from_task_ledger','old':p['old_case']['case_id'],'new':p['new_case']['case_id'],
                'okay':abs(sum(r['delta']['load_time']for r in p['changed_tasks'])-p['delta_components']['tray_wait'])<1e-8})
    selected=[]
    if stage=='full':
        for scene in sorted({r['scene']for r in summary['rows']}):
            relevant=[p for p in pairs if p['new_case']['scene']==scene and p['new_case']['policy']=='same_zone32plus32'and p['delta_cost']is not None]
            if relevant:
                for role,chosen in [('minimum',min(relevant,key=lambda p:(p['delta_cost'],p['new_case']['tape_id']))),
                                    ('maximum',min(relevant,key=lambda p:(-p['delta_cost'],p['new_case']['tape_id'])))]:
                    selected.append({'role':role,'scene':scene,'old_case':chosen['old_case']['case_id'],
                        'new_case':chosen['new_case']['case_id'],'delta_cost':chosen['delta_cost']})
    # Preserve raw trace chains for every mechanism cell and selected full cases.
    selected_ids=set(cases)if stage in ('mechanism','nominal_pilot')else {r[k]for r in selected for k in ('old_case','new_case')}
    if stage=='full':
        for p in pairs:
            if p['new_case']['policy']=='same_zone32plus32'and p['delta_cost']is not None and p['delta_cost']>1e-9:
                selected_ids.update((p['old_case']['case_id'],p['new_case']['case_id']))
    chains={}
    for name in sorted(selected_ids):
        s=load(name)
        if s.get('result'):
            chains[name]={'evaluation_ledger':s['evaluation_ledger'],
                'events':[r for r in s['result']['trace']if r.get('event')not in ('tick','initial')],
                'slow_call_actions':[{'time':c['time'],'state_sha256':c['state_sha256'],
                    'proposals':normalized(c.get('proposals',[]))}for c in s['slow_calls']]}
        del s
    changed=[p for p,h in bound.items()if sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    result={'schema':'ics_round6_same_zone_mechanisms_v1','stage':stage,'run_directory':str(RUN),'new_physical_simulations':0,
        'summary_resource_metadata':{k:summary[k]for k in ('case_invocation_cpu_seconds_recorded','parent_cpu_seconds','wall_makespan_seconds')},
        'resource_metadata_is_not_analyzer_work':True,'cases':compact,'pairs':pairs,'c1_minus_c0':interactions,
        'full_selected_extrema':selected,'all_harmed_new_pairs':[p for p in pairs if p['new_case']['policy']=='same_zone32plus32'and p['delta_cost']is not None and p['delta_cost']>1e-9],
        'chains':chains,'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),
        'failed_check_details':[c for c in checks if not c['okay']],'bound_file_sha256':bound,'changed_inputs':changed,
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'cpu_seconds':process_time()-cpu0,'wall_seconds':perf_counter()-wall0,
        'resource_scope':'Pure-file read/hash/analysis through verification, excluding final serialization and markdown rendering; no simulator imported.'}
    dest.mkdir()
    (dest/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[f'# 第六轮供盘机制：{stage}','',f"全部请求 {len(expected)}，保存物理原件 {len(cases)}；只读检查 {result['checks']}，失败 {result['failed_checks']}，输入变化 {len(changed)}。无新增仿真。",'',
        '| case | status | J | wait | empty distance | on time | same-zone commits | guard work |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for c in compact:
        if 'metrics'not in c:lines.append(f"| {c['case_id']} | {c['status']} | unknown | | | | | |");continue
        m=c['metrics'];co=m['cost_components']or {}
        lines.append(f"| {c['case']['case_id']} | {c['summary_status']} (physical:{m['status']}) | {m['total_cost']} | {co.get('tray_wait')} | {co.get('empty_distance')} | {m['on_time']}/{m['task_ledger_count']} | {c['same_zone_commit_count']} | {c['guard_work']} |")
    lines+=['','| old → new | ΔJ | Δwait | Δempty distance | Δon-time | first different slow action |',
            '|---|---:|---:|---:|---:|---:|']
    for p in pairs+interactions:
        co=p['delta_components']or {};first=p['first_slow_action_divergence']
        lines.append(f"| {p['old_case']['case_id']} → {p['new_case']['case_id']} | {p['delta_cost']} | {co.get('tray_wait')} | {co.get('empty_distance')} | {p['delta_on_time']} | {first['time']if first else 'none'} |")
    lines+=['','完整逐袋变化、首次动作分歧的公共snapshot/forecast、所有动作差异、t127/139候选与拒绝、物理事件链和原件SHA见analysis.json。此自动表保留全分母，不把同轨迹局部regret相加。',
        '',f"本分析CPU {result['cpu_seconds']:.6f}s、wall {result['wall_seconds']:.6f}s；实验worker资源仅作metadata，不计入分析耗时。"]
    (dest/'MECHANISMS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (dest/'analyze.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'stage':stage,'cases':len(cases),'pairs':len(pairs),'checks':result['checks'],
        'failed_checks':result['failed_checks'],'changed':changed,'cpu_seconds':result['cpu_seconds']},ensure_ascii=False))
    if result['failed_checks']or changed:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('mechanism','nominal_pilot','full'),required=True)
    parser.add_argument('--label')
    args=parser.parse_args();analyze(args.stage,args.label)
