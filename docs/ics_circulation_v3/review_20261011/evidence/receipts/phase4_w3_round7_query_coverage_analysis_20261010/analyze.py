"""Pure saved-file comparison, including public terminal resource certificates."""
from collections import Counter,defaultdict
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import gzip,json,pickle,sys,time

ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from scripts.experiments.ics_circulation_v3.routing import _ResourceView
from scripts.experiments.ics_circulation_v3.runtime import INFINITY
from scripts.experiments.ics_circulation_v3.same_zone_query_coverage import public_sha

BASE=ROOT/'outputs/experiments/ics_circulation_v3'
INPUT=BASE/'phase4_w3_same_zone_query_shadow_20261010'
COLLECTION=BASE/'phase4_w3_same_zone_query_coverage_20261010'
HERE=Path(__file__).parent


def main():
    cpu,wall=time.process_time(),time.perf_counter();bound={};checks=[]
    def raw(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest();return data
    def read(path):return json.loads(raw(path).decode('utf-8-sig'))
    def check(kind,okay,identity):checks.append({'kind':kind,'okay':bool(okay),'identity':identity})
    collection=read(COLLECTION/'collections/summary.json');selection=read(INPUT/'selection.json')
    formal=read(INPUT/'formal/summary.json');protocol=read(INPUT/'protocol.json')
    check('full27',len(collection['rows'])==27 and all(r['status']=='controller_quiescent'for r in collection['rows']),'collection')
    check('all93',selection['truncated_count']==93,'selection')
    check('all_formal_requests',len(formal['rows'])==len(selection['formal']), 'formal')
    expected={r['query_id']:r for r in selection['formal']};rows=[]
    for record in formal['rows']:
        payload=read(INPUT/record['file']);identity=record['query_id'];request=expected[identity]
        check('formal_file_sha',bound[str((INPUT/record['file']).relative_to(ROOT))]==record['sha256'],identity)
        check('completed_shadow',payload['status']=='completed_shadow_probe',identity)
        if payload.get('result')is None:continue
        data=raw(COLLECTION/request['file']);check('query_sha',sha256(data).hexdigest()==request['sha256'],identity)
        query=pickle.loads(gzip.decompress(data));state=query['snapshot']
        check('snapshot_sha',public_sha(state)==query['public_snapshot_sha256'],identity)
        view=_ResourceView(state,query['tray_id']);dest=query['destination'];horizon_end=state.now+query['generator_settings']['horizon']
        terminal_block=not view.available('node:'+dest,horizon_end,INFINITY)
        slots={r:[asdict(s)for s in view.slots[r]]for r in ('node:'+dest,'reception:'+dest,'node:'+state.trays[query['tray_id']].node)}
        variants=payload['result'].get('variants',[])
        check('fixed_four',[(v['variant'],v['settings']['expansion_limit'])for v in variants]==[(v[0],v[2])for v in protocol['variants']],identity)
        check('baseline_exact',bool(variants and variants[0].get('original_query_reproduced')),identity)
        evidence=[]
        for v in variants:
            diag=v['diagnostics'];stage=diag.get('work_units_by_stage',{})
            options=v['authorized_options']
            check('terminal_certificate_not_refuted',not terminal_block or not options,identity+':'+v['variant'])
            evidence.append({**{k:v[k]for k in ('variant','status','work','raw_candidate_count','authorized_candidate_count',
                'minimum_usable_at','new_authorized_action_keys','resolves_original_zero','earlier_usable_than_original','actual_action_keys')},
                'diagnostics':diag,'dominant_work_stage':max(stage,key=stage.get)if stage else None,
                'failure':v['failure'],'cpu_seconds_nested':v['cpu_seconds'],
                'authorized_route_details':[{'candidate_id':o['candidate_id'],'legs':o['legs'],
                    'unload_complete':o['unload_complete'],'usable_at':o['usable_at']}for o in options]})
        row={'query':request,'snapshot_now':state.now,'generator_settings':query['generator_settings'],
             'original_call_stack':query['call_stack'],'original_diagnostics':query['last_diagnostics'],
             'public_target':asdict(state.network.nodes[dest]),'destination_hold_ticks':state.module.hold_ticks(dest),
             'terminal_node_blocked_at_horizon_through_infinity':terminal_block,'target_and_source_reservations':slots,
             'certificate_scope':'If [now+H, infinity) has no room for one more tray, then every earlier terminal interval also fails under this fixed public reservation model. This does not forecast later removal or prove real-future task infeasibility.',
             'variants':evidence,'worker_cpu_seconds_nested':payload['invocation_cpu_seconds']}
        rows.append(row)
    groups=[]
    for selection_type in ('all_truncated','earliest_successful_control'):
        subset=[r for r in rows if r['query']['selection']==selection_type]
        for scene in sorted({r['query']['scene']for r in subset}):
            scene_rows=[r for r in subset if r['query']['scene']==scene]
            for variant in protocol['variants']:
                values=[next(v for v in r['variants']if v['variant']==variant[0])for r in scene_rows]
                groups.append({'selection':selection_type,'scene':scene,'variant':variant[0],
                    'queries':len(values),'nonempty_authorized':sum(v['authorized_candidate_count']>0 for v in values),
                    'status_counts':dict(Counter(v['status']for v in values)),
                    'new_authorized_prefixes':sum(bool(v['new_authorized_action_keys'])for v in values),
                    'earlier_usable':sum(v['earlier_usable_than_original']for v in values),
                    'work':sum(v['work']for v in values),'cpu_seconds_nested':sum(v['cpu_seconds_nested']for v in values)})
    # Fixed representative rule: earliest identity per public query cell and
    # observed work/result category, never a downstream cost or best gain.
    representatives={}
    for r in sorted(rows,key=lambda r:(r['query']['case_id'],r['query']['time'],r['query']['query_ordinal'])):
        if r['query']['selection']!='all_truncated':continue
        q=r['query'];key=(q['scene'],q['callsite'],q['source'],q['destination'],
            r['terminal_node_blocked_at_horizon_through_infinity'],tuple((v['dominant_work_stage'],v['status'],v['authorized_candidate_count']>0)for v in r['variants']))
        representatives.setdefault(repr(key),q['query_id'])
    for path,h in bound.items():check('input_unchanged',sha256((ROOT/path).read_bytes()).hexdigest()==h,path)
    result={'schema':'round7_fixed_query_coverage_analysis_v1','new_physical_simulations':0,'new_searches':0,
        'rows':rows,'groups':groups,'representative_rule':'earliest case/time/ordinal per query cell plus observed work/result category; no physical cost used',
        'representatives':representatives,'checks':len(checks),'failed_checks':[c for c in checks if not c['okay']],
        'certificate_count_among_truncations':sum(r['terminal_node_blocked_at_horizon_through_infinity']and r['query']['selection']=='all_truncated'for r in rows),
        'bound_input_sha256':bound,'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.perf_counter()-wall,
        'resource_scope':'Saved-file read/hash/comparison interval; final serialization excluded. Embedded worker/search CPU is nested and not added.'}
    with (HERE/'analysis.json').open('x',encoding='utf8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# 第七轮固定影子查询覆盖诊断','',
        '输入来自 27 条已声明的新策略轨迹。保留全部 93 次截断及匹配成功 controls；四档固定搜索只生成，不执行新增候选。','',
        '| 查询域 | 场景 | 搜索 | 查询数 | 授权非空 | 新授权前缀 | 更早 usable | work |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for g in groups:lines.append('| '+ ' | '.join(str(g[k])for k in ('selection','scene','variant','queries','nonempty_authorized','new_authorized_prefixes','earlier_usable','work'))+' |')
    lines += ['',f"公开终点长期占用证书覆盖 {result['certificate_count_among_truncations']} / 93 条截断。证书仅针对当前公开预留模型下的终点无限期驻留要求，不能推导真实未来任务不可服务。",
        '',f"纯文件检查 {len(checks)} 项，失败 {len(result['failed_checks'])}；直接分析 CPU {result['cpu_seconds']:.6f}s。",
        '', '局部标签或搜索预算的遗漏只能由找到的合法反例证明；同样未找到不等于完整覆盖。全图 event 参考也有时刻表示、K 与预算边界，不能套用 SIPP 最早标签支配定理。']
    (HERE/'COVERAGE.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({k:result[k]for k in ('checks','failed_checks','certificate_count_among_truncations','cpu_seconds','wall_seconds')},ensure_ascii=False))

if __name__=='__main__':main()
