"""Pure-file round7 invocation ledger; nested work and parallel walls never add."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import argparse,json

ROOT=next(p for p in Path(__file__).resolve().parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
HERE=BASE/'phase4_w3_round7_resource_ledger_20261010'
LABEL=BASE/'phase4_w3_same_zone_labels_20261010'
COVER=BASE/'phase4_w3_same_zone_query_coverage_20261010'
SHADOW=BASE/'phase4_w3_same_zone_query_shadow_20261010'
TERMINAL=BASE/'phase4_w3_terminal_capacity_screen_20261010'
REVIEW=BASE/'phase4_w3_round7_independent_review_20261010'


def main(output,required):
    cpu,wall=process_time(),perf_counter();bound={};rows=[];checks=[];used=set()
    if output.exists():raise FileExistsError(output)
    for item in required:
        if not(BASE/item).is_file():raise FileNotFoundError(item)
    def read(path):
        data=path.read_bytes();key=str(path.relative_to(ROOT));bound[key]=sha256(data).hexdigest()
        return json.loads(data.decode('utf-8-sig'))
    def component(scope,value,field):
        return {'scope':scope,'cpu_seconds':value,'source_field':field,
                'quality':'unknown'if value is None else'measured_interval_lower_bound'}
    def add(identity,path,parts,wall_value=None,status='complete',counts=None,notes=None):
        if identity in {r['id']for r in rows}:raise ValueError('Duplicate invocation '+identity)
        rows.append({'id':identity,'source':None if path is None else str(path.relative_to(ROOT)),
            'status':status,'cpu_components':parts,'wall_seconds_individual_scope':wall_value,
            'counts':counts or {},'notes':notes or []})
        if path is not None:used.add(path)
    def direct(identity,path,ck='cpu_seconds',wk='wall_seconds'):
        s=read(path);failed=any(bool(s.get(k))for k in ('exit_code','failed_checks','errors','failures'))
        add(identity,path,[component('direct measured interval',s[ck],ck)],s.get(wk),
            status='failed'if failed else'complete',
            counts={k:s[k]for k in ('checks','failed_checks','new_physical_simulations','new_physical_calls',
                'actual_physical_calls','physical_simulations','new_generate_calls','new_search_invocations','queries','exit_code')if k in s and not isinstance(s[k],list)},
            notes=[s.get('resource_scope',s.get('scope','Timing excludes unasserted bootstrap/final serialization.')),
                'Embedded prior/worker/cycle CPU is metadata, not another invocation. Zero measured CPU is timer resolution, not proof of no work.'])
        if failed:
            rows[-1]['failure_evidence']={k:s[k]for k in ('exit_code','failed_checks','errors','failures','cause','failure','error')if s.get(k)}
    direct('label_prepare',LABEL/'protocol.json','preparation_cpu_seconds','preparation_wall_seconds')
    direct('label_historical_prepare',LABEL/'historical_preparation.json')
    direct('coverage_prepare',COVER/'protocol.json','prepare_cpu_seconds','prepare_wall_seconds')
    direct('shadow_repaired_prepare',SHADOW/'protocol.json','prepare_cpu_seconds','prepare_wall_seconds')
    direct('shadow_selection',SHADOW/'selection.json')
    direct('terminal_screen_prepare',TERMINAL/'protocol.json','prepare_cpu_seconds','prepare_wall_seconds')
    if(TERMINAL/'corpus.json').exists():direct('terminal_screen_all2467_corpus',TERMINAL/'corpus.json')
    for identity,path,count in [('label_collection3',LABEL/'collection_run/summary.json',3),
        ('label_normal5',LABEL/'normal_resume/summary.json',5),('label_pilot16',LABEL/'pilot/summary.json',16),
        ('label_historical48',LABEL/'old12/summary.json',48),('label_formal692',LABEL/'full/summary.json',692),
        ('coverage_collection27',COVER/'collections/summary.json',27),
        ('coverage_pilot',SHADOW/'pilot/summary.json',4),('coverage_formal',SHADOW/'formal/summary.json',99),
        ('terminal_screen_pilot3',TERMINAL/'pilot/summary.json',3),('terminal_screen_formal27',TERMINAL/'formal/summary.json',27)]:
        if not path.exists():
            add(identity,path,[component('worker and parent',None,'pending')],status='pending',counts={'planned_requests':count});continue
        s=read(path);ck=next(k for k in ('case_invocation_cpu_seconds_recorded','worker_cpu_seconds_recorded')if k in s)
        planned=s.get('planned_requests',s.get('planned_cases'))
        recorded=sum(r.get('invocation_cpu_seconds')or 0 for r in s['rows'])
        checks.append({'id':identity,'kind':'cpu_sum','okay':abs(recorded-s[ck])<1e-8})
        checks.append({'id':identity,'kind':'denominator','okay':len(s['rows'])==planned and(count is None or planned==count)})
        add(identity,path,[component('worker invocation intervals',s[ck],ck),
            component('coordinator interval',s['parent_cpu_seconds'],'parent_cpu_seconds')],s['wall_makespan_seconds'],
            counts={k:s[k]for k in ('planned_requests','planned_cases','actual_physical_calls_recorded',
                'physical_calls_recorded','unknown_physical_call_statuses','unknown_worker_resources','unknown_resource_cases',
                'status_counts','new_simulation_branches','memo_reuse','truncated_queries')if k in s},
            notes=['Cycle/query/variant timings are nested and not added. Pilot and formal repeated identities are independent calls, no discount.',
                'Nominal label collection and coverage collection overlap case identities but are separately executed.',
                'Process-pool makespans overlap other runners and must not be added into global wall.'])
        unknown=sum(r.get('invocation_cpu_seconds')is None for r in s['rows'])
        if unknown:rows[-1]['cpu_components'].append(component('unrecorded workers',None,str(unknown)+' failed/unmeasured workers'))
        rows[-1]['worker_lifetime_peak_memory_not_additive']={k:max((r.get('memory',{}).get(k,0)or 0 for r in s['rows']),default=0)
            for k in ('peak_working_set_bytes','peak_commit_bytes')}
    # Every explicit author invocation is distinct; parent summaries copied into
    # repaired records are not counted a second time.
    author=BASE/'phase4_w3_round7_labels_authoring_20261010/validation_attempts.json';s=read(author)
    for n,a in enumerate(s['attempts']):
        add('label_author_'+str(n+1),author,[component('pytest child',a['child_cpu_seconds'],'attempts.child_cpu_seconds')],
            a['tool_wall_seconds'],'failed_tests'if a.get('failed')else'complete',
            counts={k:a[k]for k in ('tests','passed','failed')},notes=['Tool wall only; child CPU unknown.'])
    for n,a in enumerate(s['auxiliary_diagnostics']):
        add('label_auxiliary_'+str(n+1),author,[component('diagnostic child',a['cpu_seconds'],'auxiliary_diagnostics.cpu_seconds')],a['tool_wall_seconds'])
    qa=BASE/'phase4_w3_round7_query_coverage_authoring_20261010'
    for name in ('validation.json','validation_repaired.json','validation_recovery_freeze.json'):direct('coverage_author_'+name,qa/name)
    s=read(qa/'validation.json')
    for n,a in enumerate(s['prior_unmetered_attempts']):
        add('coverage_author_unmetered_'+str(n+1),qa/'validation.json',[component('pytest child',None,'prior_unmetered_attempts.cpu_seconds')],
            a['tool_wall_seconds'],counts={'tests':a['tests'],'passed':a['passed']})
    s=read(qa/'recovery_revision.json');a=s['author_validation_attempt']
    add('coverage_recovery_author_failed_test',qa/'recovery_revision.json',
        [component('pytest child',None,'author_validation_attempt.child_cpu_seconds')],a['tool_wall_seconds'],
        'failed_test',counts={k:a[k]for k in ('tests','passed','failed')},notes=[a['cause']])
    direct('query_probe_author',BASE/'phase4_w3_round7_query_probe_authoring_20261010/initial.json')
    ta=BASE/'phase4_w3_round7_terminal_authoring_20261010'
    for name in ('validation.json','validation_snapshot_bound.json'):direct('terminal_author_'+name,ta/name)
    s=read(ta/'validation.json')
    for n,a in enumerate(s['prior_unmetered_attempts']):
        add('terminal_author_unmetered_'+str(n+1),ta/'validation.json',
            [component('pytest child',None,'prior_unmetered_attempts.cpu_seconds')],a['tool_wall_seconds'],counts={'passed':a['passed']})
    census=BASE/'phase4_w3_round7_search_census_20261010'
    direct('search_census_initial_failed',census/'census.json')
    direct('search_census_repaired',census/'census_repaired.json')
    observer=BASE/'phase4_w3_round7_physical_observation_20261010'
    p=observer/'supplement/summary.json';s=read(p)
    add('immutable_observation_supplement3',p,[component('3 independent worker intervals',s['case_cpu_seconds'],'case_cpu_seconds'),
        component('parent interval',s['parent_cpu_seconds'],'parent_cpu_seconds')],s['wall_makespan_seconds'],
        counts={'new_physical_calls':len(s['rows']),'all_passed':s['all_passed']},
        notes=['New3 nominal physical invocations; separate from prior label3 and coverage27, no identity reuse discount.'])
    direct('immutable_observation_author',observer/'validation.json')
    p=observer/'initial_test_failure.json';s=read(p)
    add('immutable_observation_author_initial_failure',p,[component('pytest child',None,'unrecorded CPU')],
        s.get('tool_wall_seconds',s.get('wall_seconds')),status='failed_tests',notes=[str(s)])
    p=BASE/'phase4_w3_round7_value_analysis_20261010/results/analysis.json'
    if p.exists():
        s=read(p);r=s['resources']
        add('root_matched_value_analysis',p,[component('pure artifact analysis',r['analysis_cpu_seconds'],'resources.analysis_cpu_seconds')],
            r['analysis_wall_seconds'],notes=[r['scope'],'Explicit direct analysis clock; label outcome metrics are nested metadata.'])
    paths=set(REVIEW.glob('*.json'))
    paths.update(REVIEW.glob('full_validation*/result.json'))
    for directory in BASE.glob('phase4_w3_round7_*_20261010'):
        if directory in (HERE,REVIEW,census,qa):continue
        primary=directory/'analysis.json'
        if primary.exists():paths.add(primary)
        elif(directory/'manifest.json').exists():paths.add(directory/'manifest.json')
        if 'visual' in directory.name and(directory/'metadata.json').exists():paths.add(directory/'metadata.json')
    paths.add(BASE/'phase4_w3_round7_value_analysis_20261010/historical_mechanisms/mechanisms.json')
    paths.add(BASE/'phase4_w3_round7_value_analysis_20261010/results/analysis.json')
    paths.add(BASE/'phase4_w3_round7_value_analysis_20261010/visuals/manifest.json')
    paths.add(BASE/'phase4_w3_round7_query_coverage_analysis_20261010/local_yield_trace.json')
    paths.update([LABEL/'independent_choice_check/result.json',LABEL/'independent_choice_check/service_ties_result.json',
        LABEL/'summary_authoring_receipt.json'])
    paths.update(BASE/n for n in required)
    for path in sorted(paths-used):
        s=read(path);ck=next((k for k in ('cpu_seconds','analysis_cpu_seconds','cpu_seconds_measured_after_plot_imports')
            if isinstance(s.get(k),(int,float))),None)
        if ck:
            wk=next((k for k in ('wall_seconds','analysis_wall_seconds','wall_seconds_measured_after_plot_imports')if k in s),'wall_seconds')
            direct('analysis:'+str(path.relative_to(BASE)),path,ck,wk)
    add('unmetered_auxiliary',None,[component('edits, shell/tool bootstrap, inspections, polling, docs and unmeasured support',None,'author disclosure')],
        notes=['No original-network physical run inferred from inspections; unmeasured CPU is not zero. Source snapshots/manifests are artifacts, not duplicate invocations.'])
    for path,h in bound.items():checks.append({'id':path,'kind':'evidence_unchanged','okay':sha256((ROOT/path).read_bytes()).hexdigest()==h})
    payload={'schema':'ics_round7_resource_ledger_v1','rows':rows,'checks':checks,
        'failed_checks':sum(not c['okay']for c in checks),'bound_evidence_sha256':bound,
        'pending':[r['id']for r in rows if r['status']=='pending'],
        'known_nonoverlapping_cpu_seconds_lower_bound':sum(c['cpu_seconds']for r in rows for c in r['cpu_components']if c['cpu_seconds']is not None),
        'unknown_cpu_components':sum(c['cpu_seconds']is None for r in rows for c in r['cpu_components']),
        'whole_round_cpu_completely_measured':False,'global_wall_makespan_seconds':None,
        'reason':'Measured disjoint CPU intervals add; concurrent wall, worker lifetime memory, branch/query nested work and caps do not.',
        'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'ledger_cpu_seconds':process_time()-cpu,'ledger_wall_seconds':perf_counter()-wall,
        'ledger_scope':'Own read/hash/aggregation interval excluded from totals; final serialization excluded; no new searches or simulation.'}
    output.mkdir(parents=True)
    (output/'ledger.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'summarize.py').write_bytes(Path(__file__).read_bytes())
    lines=['# 第七轮资源与失败账','',f"已记录互不重叠 CPU 区间合计 **{payload['known_nonoverlapping_cpu_seconds_lower_bound']:.6f}s**，属于本轮总耗时下界。未知分量 {payload['unknown_cpu_components']}；pending {len(payload['pending'])}。",'',
        '| 独立调用 | 状态 | 已记录 CPU(s) | 未知分量 | 本调用 wall(s) |','|---|---|---:|---:|---:|']
    for r in rows:
        known=sum(c['cpu_seconds']for c in r['cpu_components']if c['cpu_seconds']is not None)
        known_text=f'{known:.6f}'if any(c['cpu_seconds']is not None for c in r['cpu_components'])else'未知'
        lines.append(f"| {r['id']} | {r['status']} | {known_text} | {sum(c['cpu_seconds']is None for c in r['cpu_components'])} | {r['wall_seconds_individual_scope']} |")
    lines += ['', '并发 wall 不相加；worker lifetime 内存峰值不相加为同时峰值；旧文件复用、label memo 与嵌套 cycle/query 时钟不冒充额外物理工作。',
        '',f"证据核验 {len(checks)} 项，失败 {payload['failed_checks']}；账本自身 CPU {payload['ledger_cpu_seconds']:.6f}s 另列且未加入上表。"]
    (output/'RESOURCE_LEDGER.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({k:payload[k]for k in ('known_nonoverlapping_cpu_seconds_lower_bound','unknown_cpu_components','pending','failed_checks','ledger_cpu_seconds')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-file',action='append',default=[]);args=parser.parse_args();main(args.output,args.require_file)
