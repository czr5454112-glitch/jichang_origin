"""Read only named small summaries; never scan bags, routes or event ledgers.

Missing/censored metrics stay null. This reports prior audit results, not a new
physical audit, and retains the distinct HCA/native timing and gate layouts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
CAMPAIGN=HERE.parent
SMALL_NAMES={'manifest.json','native_summary.json','tht_audit.json','business_audit.json',
             'headway_audit.json','rolling_replay.json','source_policy_audit.json',
             'final_summary_001.json','tht_metrics.json','source_policy_audit_001.json',
             'physical_headway_audit.json','run_status.json','NANNING_ONLY_PLAN_002.json',
             'controls_fixed1_drain200000.json','controls_fixed2_drain200000.json',
             'controls_fixed1_original98259.json','controls_fixed2_original98259.json','comparison.json','bound_001.json'}
STATS=('count','sum','mean','min','p50','p95','p99','max')
GATES={'headway':'headway_audit.json','rolling':'rolling_replay.json',
       'source_policy':'source_policy_audit.json','tht':'tht_audit.json','business':'business_audit.json'}
TELEMETRY=('planning_attempts','failed_attempts','search_expansions','score_expansions',
           'local_scoring_calendar_queries','search_decision_k_histogram',
           'search_actual_calendar_query_depth_histogram','committed_route_hop_k_histogram',
           'max_observation_depth','scored_neighbor_candidates','local_score_budget_exhausted_decisions',
           'score_budget_exhaustions','search_budget_failures','inroute_decisions',
           'inroute_replacement_attempts','inroute_replacement_successes','inroute_fallbacks',
           'inroute_search_expansions','inroute_scoring_queries','future_source_precommits',
           'future_source_pending_at_horizon','future_calendar_entries_scanned')


class SmallReader:
    def __init__(self):self.evidence={}
    def read(self,path):
        p=Path(path).resolve()
        if p.name not in SMALL_NAMES:raise ValueError('file is outside named small-summary allowlist: '+p.name)
        if not p.exists():return None
        before=p.stat()
        if before.st_size>2*1024*1024:raise ValueError('refusing large summary file: '+str(p))
        raw=p.read_bytes();after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('summary changed during read')
        obj=json.loads(raw.decode('utf-8-sig'),parse_constant=lambda s:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        self.evidence[str(p)]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        return obj


def get(obj,*keys):
    for key in keys:
        if not isinstance(obj,dict):return None
        obj=obj.get(key)
    return obj


def statistics(block,*,full_allowed=True):
    data=block.get('full_population') if isinstance(block,dict) and full_allowed else None
    status='available' if isinstance(data,dict) else ('censored_or_unavailable' if not full_allowed else 'not_computed')
    return dict(status=status,**{k:data.get(k) if isinstance(data,dict) else None for k in STATS})


def deadlines(count,denominator):
    valid=type(count) is int and type(denominator) is int and denominator>0 and 0<=count<=denominator
    return dict(count=count if valid else None,denominator=denominator,rate=count/denominator if valid else None,
                status='available' if valid else 'not_computed_or_invalid')


def gate(obj,filename):
    passed=get(obj,'passed')
    return dict(status='passed' if passed is True else ('failed' if passed is False else 'not_exported'),
                passed=passed if type(passed) is bool else None,source=filename)


def metrics(tht,business):
    denominator=get(tht,'business_denominator');complete=get(tht,'completed_businesses')
    full=get(tht,'user_tht_full_population_available') is True and denominator is not None and complete==denominator
    secondary=get(tht,'secondary') or {}
    cutoff=get(business,'original_window_completed_businesses') if get(business,'original_window_count_available') is True else None
    return dict(business_denominator=denominator,segment_denominator=get(tht,'segment_denominator'),
                completed_businesses=complete,completed_segments=get(tht,'completed_segments'),
                full_population_available=full,user_tht=statistics(get(tht,'user_tht'),full_allowed=full),
                preplanning=statistics(secondary.get('business_sum_canonical_preplanning'),full_allowed=full),
                planning_retry_wait=statistics(secondary.get('business_sum_planning_wait'),full_allowed=full),
                canonical_elapsed=statistics(secondary.get('business_sum_canonical_elapsed'),full_allowed=full),
                network_elapsed=statistics(get(tht,'network_elapsed'),full_allowed=full),
                original_window_end=get(business,'original_window_end'),original_window_completed_businesses=cutoff,
                original_window_unfinished_businesses=(denominator-cutoff if type(denominator) is int and type(cutoff) is int and 0<=cutoff<=denominator else None),
                original_window_source=get(business,'cutoff_count_method'),
                original_window_state_split=None,original_window_state_split_status='not_computed_from_small_summaries',
                STD=deadlines(get(business,'finish_le_std'),denominator),
                STD_minus_2700=deadlines(get(business,'finish_le_std_minus_2700'),denominator))


def native(directory,label,reader,expected=None,expected_scale=2):
    d=Path(directory);manifest=reader.read(d/'manifest.json');issues=[]
    if manifest is None or manifest.get('status')!='complete':
        return dict(label=label,kind='native',path=str(d),status=manifest.get('status') if manifest else 'not_run_or_missing',metrics=None,audit_gates=None,usable_reported_result=False)
    docs={key:reader.read(d/name) for key,name in GATES.items()}
    audits={key:gate(docs[key],GATES[key]) for key in GATES}
    ns=reader.read(d/'native_summary.json') or {};m=metrics(docs['tht'],docs['business'])
    selection=manifest.get('selection',{});controls=selection.get('effective_controls',{})
    if expected_scale not in (1,2):raise ValueError('Nanning 1x/2x only')
    if selection.get('map')!='nanning' or selection.get('scale')!=expected_scale:issues.append('wrong_map_or_scale')
    if m['business_denominator']!=28506*expected_scale or m['segment_denominator']!=43603*expected_scale:issues.append('wrong_population')
    if expected is not None:
        for k,value in expected.items():
            if k not in controls or controls[k]!=value:issues.append('control_mismatch:'+k)
    if get(docs['business'],'completed_businesses')!=m['completed_businesses']:issues.append('business_completion_disagreement')
    if get(docs['business'],'business_denominator')!=m['business_denominator']:issues.append('business_denominator_disagreement')
    if m['full_population_available'] and m['user_tht']['count']!=m['business_denominator']:issues.append('full_population_stats_count_mismatch')
    if controls.get('future_source_reservation_horizon_seconds')==0 and any(ns.get(k,0) for k in ('future_source_precommits','future_source_launches','future_source_pending_at_horizon')):
        issues.append('future_reservations_present_while_disabled')
    passed=manifest.get('audits_passed') is True and all(g['passed'] is True for g in audits.values())
    return dict(label=label,kind='native',path=str(d),status=manifest['status'],metrics=m,
                audit_gates=audits,all_five_passed=passed,identity_issues=issues,
                usable_reported_result=passed and not issues,controls=controls,
                identity={k:selection.get(k) for k in ('binary','native_source','canonical','profile','build_receipt')},
                compute=dict(native_event_loop_cpu_seconds=ns.get('run_cpu_seconds'),native_event_loop_wall_seconds=ns.get('run_wall_seconds'),
                             native_api_process_cpu_seconds=manifest.get('native_process_cpu_seconds'),native_api_wall_seconds=manifest.get('native_wall_seconds'),
                             end_to_end_wall_seconds=None,source_decision_wall_seconds=ns.get('source_decision_wall_seconds'),
                             inroute_decision_wall_seconds=ns.get('inroute_decision_wall_seconds'),
                             scope=ns.get('run_cpu_measurement'),end_to_end_status='not_measured_in_available_small_summary'),
                telemetry={key:ns.get(key) for key in TELEMETRY})


def hca(directory,prefix,reader):
    d=Path(directory);final=reader.read(d/'final_summary_001.json');tht=reader.read(d/'tht_metrics.json')
    if final is None:return dict(label='HCA_repaired',kind='hca',path=str(d),status='not_run_or_missing',metrics=None,usable_reported_result=False)
    src=reader.read(d/'source_policy_audit_001.json');head=reader.read(d/'physical_headway_audit.json')
    rs=reader.read(d/'run_01/run_status.json') or {};pm=reader.read(Path(prefix)/'manifest.json');pt=reader.read(Path(prefix)/'tht_metrics.json')
    pbound=pm is not None and pt is not None and pm.get('passed') is True and pt.get('passed') is True and pm.get('horizon')==98259 and Path(pm.get('source_run','')).resolve()==d.resolve()
    business=dict(finish_le_std=get(final,'STD','count'),finish_le_std_minus_2700=get(final,'STD_minus_2700','count'),original_window_end=98259,
                  original_window_completed_businesses=pt.get('completed_businesses') if pbound else None,original_window_count_available=pbound,
                  cutoff_count_method='Existing independently audited derived HCA prefix; not a separate short Java execution.' if pbound else 'not_computed_or_prefix_unbound')
    m=metrics(tht,business)
    audits=dict(headway=gate(head,'physical_headway_audit.json'),source_policy=gate(src,'source_policy_audit_001.json'),tht=gate(tht,'tht_metrics.json'),
                rolling=dict(status='not_applicable',passed=None,reason='HCA commits an immutable full route; it has no rolling-replacement ledger.'),
                business=dict(status='not_separately_exported',passed=None,reason='Counts read from final_summary_001.json; no separate small business_audit.json exists here. No synthetic fifth PASS is asserted.'))
    scopes=get(final,'planning_profile','scopes') or {}
    def sec(scope,key):
        n=get(scopes,scope,key)
        return n/1e9 if type(n) in (int,float) else None
    usable=(final.get('cell')=='nanning_2x' and m['business_denominator']==57012 and m['segment_denominator']==87206
            and rs.get('status')=='complete' and rs.get('returncode')==0 and final.get('physical_passed') is True
            and final.get('source_policy_passed') is True and final.get('frozen_inputs_and_classes_postrun_exact') is True
            and all(audits[k]['passed'] is True for k in ('headway','source_policy','tht')))
    return dict(label='HCA_repaired',kind='hca',path=str(d),status=rs.get('status'),metrics=m,audit_gates=audits,all_five_passed=None,
                aggregate_physical_passed=final.get('physical_passed'),frozen_identity_postrun_exact=final.get('frozen_inputs_and_classes_postrun_exact'),
                usable_reported_result=usable,original_prefix_bound=pbound,
                compute=dict(astar_thread_cpu_seconds=sec('astar_search','thread_cpu_ns'),astar_wall_seconds=sec('astar_search','elapsed_ns'),
                             java_window_thread_cpu_seconds=sec('window','thread_cpu_ns'),java_window_wall_seconds=sec('window','elapsed_ns'),
                             end_to_end_wall_seconds=final.get('java_end_to_end_wall_seconds'),whole_process_cpu_seconds=final.get('whole_jvm_process_cpu_seconds'),
                             scopes_overlap=True,scope=final.get('cpu_scope_note')),
                telemetry=dict(astar_calls=get(scopes,'astar_search','calls'),search_success=get(final,'planning_profile','search_success'),search_failure=get(final,'planning_profile','search_failure'),
                               per_bag_retry_count=None,requested_k=None,actual_query_depth=None,
                               missing_reason='HCA does not export G31 k/local-score telemetry; aggregate search failures are not inferred per-bag retry counts.'))


def difference(new,reference):
    if type(new) not in (int,float) or type(reference) not in (int,float):return dict(delta=None,percent=None,status='not_computed')
    return dict(delta=new-reference,percent=(100*(new-reference)/reference if reference else None),status='available')


def different_control_keys(left,right):
    return {key for key in set(left)|set(right) if key not in left or key not in right or left[key]!=right[key]}


def contrast(a,b,label):
    fields={'tht_mean':('user_tht','mean'),'tht_p95':('user_tht','p95'),'tht_p99':('user_tht','p99'),'tht_max':('user_tht','max'),
            'preplanning_mean':('preplanning','mean'),'canonical_elapsed_mean':('canonical_elapsed','mean'),
            'cutoff_completed':('original_window_completed_businesses',),'STD_count':('STD','count'),'early_count':('STD_minus_2700','count')}
    valid=a.get('usable_reported_result') is True and b.get('usable_reported_result') is True
    return dict(label=label,new=a['label'],reference=b['label'],inputs_usable=valid,
                metrics={key:difference(get(a.get('metrics'),*path),get(b.get('metrics'),*path)) if valid else difference(None,None) for key,path in fields.items()},
                timing_ratio=None,timing_reason='No cross-scope native-event-loop versus Java-thread/whole-window speed ratio is calculated.')


def run(plan_path,k1=None,k2=None,hca_path=None,hca_prefix=None,future=None):
    reader=SmallReader();plan=reader.read(plan_path)
    if not plan or plan.get('scope',{}).get('maps')!=['nanning']:raise ValueError('requires the superseding Nanning-only plan')
    cells=[x for x in plan['execution_order'] if x['scale']==2]
    if [(x['map'],x['arm']) for x in cells]!=[('nanning','fixed1'),('nanning','fixed2')]:raise ValueError('unexpected registered two-arm order')
    controls=[reader.read(x['controls']['path']) for x in cells]
    if different_control_keys(*controls)!={'min_depth','max_depth'}:raise ValueError('arms differ beyond depth')
    if any(x.get('congestion_weight')!=1 or x.get('future_source_reservation_horizon_seconds')!=0 for x in controls):raise ValueError('incorrect registered ablation')
    for entry,cfg in zip(cells,controls):
        if reader.evidence[str(Path(entry['controls']['path']).resolve())]['sha256']!=entry['controls']['sha256']:raise ValueError('registered controls changed')
    a=native(k1 or cells[0]['output'],'fixed1_w1',reader,controls[0]);b=native(k2 or cells[1]['output'],'fixed2_w1',reader,controls[1])
    for result,entry in zip((a,b),cells):
        if result['status']!='complete':continue
        expected_identity=dict(binary=plan['frozen_implementation']['binary_sha256'],native_source=plan['frozen_implementation']['native_source_sha256'],
                               **{key:entry['input_identity'][key]['sha256'] for key in ('canonical','profile')})
        for key,sha in expected_identity.items():
            if get(result,'identity',key,'sha256')!=sha:result['identity_issues'].append('registered_identity_mismatch:'+key)
        result['usable_reported_result']=result['usable_reported_result'] and not result['identity_issues']
    hp=hca_path or plan['comparisons']['repaired_hca']['2x']
    h=hca(hp,hca_prefix or CAMPAIGN/'hca_profile004_drain_prefix98259_001/nanning_2x',reader)
    f=native(future or plan['comparisons']['w0_future_reference']['2x'],'fixed1_w0_future60',reader)
    return dict(schema='g31.nanning2x.small_summary_comparison.v1',status='read_existing_small_summaries_only',
                runs=[a,b,h,f],comparisons=[contrast(b,a,'controlled k2 versus k1'),contrast(a,h,'k1 versus HCA contextual'),
                contrast(b,h,'k2 versus HCA contextual'),contrast(f,h,'w0 future60 versus HCA contextual'),contrast(b,f,'k2 versus w0 future60 contextual')],
                source_files=reader.evidence,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                boundaries=['No bags/routes/ledger or large analysis JSON was opened; missing metrics stay null.','Only fixed1 versus fixed2 is a controlled k contrast; k changes accumulated congestion penalties as well as spatial information.',
                            'Full-population THT and tails never fall back to completed-only diagnostics.','Fixed-window completion comes from stored actual-completion audits; drain-derived counts do not provide independent short runtime.',
                            'HCA gate layout is explicitly different; no absent rolling/business audit is fabricated as passed.','This summary records prior evidence, not a new physical or source audit; source hashes cover the small files read.'])


def render(result):
    def fmt(x):return '未算' if x is None else (str(x) if type(x) is int else f'{x:.3f}')
    lines=['南宁 2x：读取既有小型汇总；不重新扫描行李/事件。',
           'arm | THT mean/p95/p99/max (s) | preplanning mean (s) | completed<=98259 | STD / STD-2700 | audit result']
    for r in result['runs']:
        m=r.get('metrics') or {};t=m.get('user_tht') or {};pre=m.get('preplanning') or {}
        audit=','.join(k+':'+v['status'] for k,v in (r.get('audit_gates') or {}).items()) or r['status']
        lines.append(f"{r['label']} | "+'/'.join(fmt(t.get(k)) for k in ('mean','p95','p99','max'))+f" | {fmt(pre.get('mean'))} | {fmt(m.get('original_window_completed_businesses'))} | {fmt(get(m,'STD','count'))} / {fmt(get(m,'STD_minus_2700','count'))} | {audit}")
    lines+=['','计算代价（各自原始测量范围）：']
    for r in result['runs']:
        cost=r.get('compute') or {};telemetry=r.get('telemetry') or {}
        if r['kind']=='native':
            lines.append(f"{r['label']}: event-loop CPU/wall={fmt(cost.get('native_event_loop_cpu_seconds'))}/{fmt(cost.get('native_event_loop_wall_seconds'))}s; native-API CPU/wall={fmt(cost.get('native_api_process_cpu_seconds'))}/{fmt(cost.get('native_api_wall_seconds'))}s; score queries={fmt(telemetry.get('local_scoring_calendar_queries'))}; score-budget exhausted={fmt(telemetry.get('score_budget_exhaustions'))}")
        else:
            lines.append(f"{r['label']}: A* thread CPU/wall={fmt(cost.get('astar_thread_cpu_seconds'))}/{fmt(cost.get('astar_wall_seconds'))}s; whole-window thread CPU/wall={fmt(cost.get('java_window_thread_cpu_seconds'))}/{fmt(cost.get('java_window_wall_seconds'))}s; end-to-end wall={fmt(cost.get('end_to_end_wall_seconds'))}s; whole-JVM CPU={fmt(cost.get('whole_process_cpu_seconds'))}")
    lines+=['','计时保持原范围；不输出 C++/Java 跨范围加速比。缺失数据标为未算。']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,default=HERE/'NANNING_ONLY_PLAN_002.json')
    for name in ('k1','k2','hca-path','hca-prefix','future'):p.add_argument('--'+name,type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    text_path=args.output.with_suffix('.txt')
    if args.output.exists() or text_path.exists():raise FileExistsError('use new output paths')
    result=run(args.plan,args.k1,args.k2,args.hca_path,args.hca_prefix,args.future)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    with text_path.open('x',encoding='utf-8') as f:f.write(render(result))
    print(json.dumps(dict(runs={x['label']:x['status'] for x in result['runs']},output=str(args.output)),ensure_ascii=False))


if __name__=='__main__':main()
