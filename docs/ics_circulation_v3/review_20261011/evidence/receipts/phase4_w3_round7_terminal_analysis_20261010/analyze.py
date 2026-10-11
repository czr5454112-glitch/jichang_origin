"""Pure saved-summary analysis; deep raw independent validation is separate."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import json

ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'outputs/experiments/ics_circulation_v3';HERE=Path(__file__).parent
INPUT=BASE/'phase4_w3_terminal_capacity_screen_20261010'
OLD=BASE/'phase4_w3_same_zone_supply_repaired_20261010'


def main():
    cpu,wall=process_time(),perf_counter();bound={};checks=[]
    def read(p):
        data=p.read_bytes();bound[str(p.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads(data.decode('utf-8-sig'))
    protocol=read(INPUT/'protocol.json');corpus=read(INPUT/'corpus.json')
    old={r['case_id']:r for r in read(OLD/'full/summary.json')['rows']if r['policy']=='same_zone32plus32'}
    stages={};allrows=[]
    for stage,count in [('pilot',3),('formal',27)]:
        s=read(INPUT/stage/'summary.json');read(INPUT/(stage+'_manifest.json'))
        checks.append({'id':stage,'kind':'denominator','okay':len(s['rows'])==count and s['all_exact']})
        data=[]
        for r in s['rows']:
            previous=old[r['case_id']]
            checks.append({'id':stage+':'+r['case_id'],'kind':'exact_snapshot_candidates_physics',
                'okay':r['status']=='controller_quiescent'and all(r['comparison'].values())and r['raw_complete']})
            checks.append({'id':stage+':'+r['case_id'],'kind':'query_count_unchanged',
                'okay':r['search_calls']==previous['search_calls']})
            row={k:r[k]for k in ('case_id','scene','tape_id','search_calls','search_work','screen_work',
                'certified_queries','cache_after_equal','invocation_cpu_seconds','screen_cpu_seconds_nested','observation_cpu_seconds_nested')}
            row['old_search_work']=previous['search_work'];row['search_work_reduction']=previous['search_work']-r['search_work']
            data.append(row);allrows.append({'stage':stage,**row})
        stages[stage]={'cases':len(data),'rows':data,'search_calls':sum(r['search_calls']for r in data),
            'old_search_work':sum(r['old_search_work']for r in data),'search_work':sum(r['search_work']for r in data),
            'search_work_reduction':sum(r['search_work_reduction']for r in data),'screen_work':sum(r['screen_work']for r in data),
            'certified_queries':sum(r['certified_queries']for r in data),'cache_after_equal_cases':sum(r['cache_after_equal']for r in data),
            'worker_cpu_seconds_nested':s['case_invocation_cpu_seconds_recorded'],
            'parent_cpu_seconds_nested':s['parent_cpu_seconds'],'wall_makespan_seconds_metadata':s['wall_makespan_seconds'],
            'screen_cpu_seconds_nested':sum(r['screen_cpu_seconds_nested']for r in data),
            'observation_cpu_seconds_nested':sum(r['observation_cpu_seconds_nested']for r in data)}
    f=stages['formal']
    checks.extend([{'id':'formal','kind':'all2467_replayed','okay':f['search_calls']==corpus['queries']==2467},
        {'id':'formal','kind':'same93_certificates','okay':f['certified_queries']==corpus['certified_count']==93},
        {'id':'formal','kind':'query_work_saved_exact','okay':f['search_work_reduction']==corpus['certified_query_original_search_work']},
        {'id':'formal','kind':'screen_work_same_corpus','okay':f['screen_work']==corpus['screen_work']}])
    for p,h in bound.items():checks.append({'id':p,'kind':'evidence_unchanged','okay':sha256((ROOT/p).read_bytes()).hexdigest()==h})
    result={'schema':'ics_round7_terminal_screen_summary_analysis_v1','stages':stages,
        'checks':len(checks),'failed_checks':[c for c in checks if not c['okay']],
        'new_physical_calls':0,'new_generate_calls':0,'bound_evidence_sha256':bound,
        'fair_cpu_speedup_measured':False,'cpu_comparison_limit':'No instrumentation-matched screen-disabled deployment batch was run. Observational snapshot hashing and serialization scopes differ from old collection, so invocation CPU is not an algorithm speedup ratio.',
        'search_work_reduction_fraction':f['search_work_reduction']/f['old_search_work'],
        'scope':'Saved summary comparison. Independent audit separately checks every raw query/snapshot/candidate/physical record.',
        'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall}
    with(HERE/'analysis.json').open('x',encoding='utf8')as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    lines=['# 第七轮可选终点筛查部署验证','',
        f"3 条 nominal pilot 和 27 条正式输入均独立完成，全部排空。正式 {f['search_calls']} 次查询的实际公开 Snapshot SHA、身份、K 和完整有序候选池保持一致，物理 tick/事件/任务/实际 slow proposals 也保持一致。",'',
        f"正式筛中 {f['certified_queries']} 条。原逻辑 search work {f['old_search_work']} → {f['search_work']}，减少 {f['search_work_reduction']}（{result['search_work_reduction_fraction']:.3%}）；额外 screen record work {f['screen_work']} 单列，不能把两种不同工作单位机械相减。",'',
        f"最终 cache 状态相同 {f['cache_after_equal_cases']}/27；这只是实测结果，包装器并不保证省略查询后仍逐字段相同。",'',
        f"正式 worker 调用 CPU {f['worker_cpu_seconds_nested']:.6f}s，parent {f['parent_cpu_seconds_nested']:.6f}s，wall {f['wall_makespan_seconds_metadata']:.6f}s。其中 screen CPU {f['screen_cpu_seconds_nested']:.6f}s、Snapshot hash 观察 CPU {f['observation_cpu_seconds_nested']:.6f}s 均为嵌套区间。没有公平的端到端 CPU speedup 测量，不能拿不同观测器的旧批作速度倍率分母。",'',
        '筛查仍只是当前固定 Snapshot/H 的完整 witness 必要条件；不是未来任务不可服务，也没有放宽执行 validator 或改默认策略。', '',
        f"纯文件汇总核验 {result['checks']} 项，失败 {len(result['failed_checks'])}；直接 CPU {result['cpu_seconds']:.6f}s。"]
    (HERE/'TERMINAL_SCREEN.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({k:result[k]for k in ('checks','failed_checks','search_work_reduction_fraction','cpu_seconds','wall_seconds')}))

if __name__=='__main__':main()
