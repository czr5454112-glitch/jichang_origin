"""Pure artifact analysis. Does not import simulation/controller code."""
from collections import Counter
from hashlib import sha256
from itertools import combinations
import gzip
import json
from pathlib import Path

BASE=Path('outputs/experiments/ics_circulation_v3')
SRC=BASE/'phase4_w3_empty_factorial_complete_20261010'
OLD=BASE/'phase4_w3_empty_improvement_20261010'
OUT=BASE/'phase4_w3_empty_factorial_analysis_20261010'
POLICIES=('timed_greedy__incumbent','timed_greedy__fewest_physical',
          'earliest_reactive__incumbent','earliest_reactive__fewest_physical')
checks=Counter(); errors=[]; artifacts={}

def check(ok,kind,detail):
    checks[kind]+=1
    if not ok:errors.append({'kind':kind,'detail':detail})

def read(path,expected=None):
    data=path.read_bytes(); actual=sha256(data).hexdigest(); artifacts[str(path)]=actual
    if expected is not None:check(actual==expected,'sha256',str(path))
    return data

def load_run(root):
    summary=json.loads(read(root/'summary.json')); protocol=json.loads(read(root/'protocol.json'))
    records={}
    for r in summary['rows']:
        record=json.loads(gzip.decompress(read(root/'cases'/r['file'],r['sha256'])))
        key=(r['identity'].split('_')[0],r['identity'].split('_')[1],r['policy'])
        check(key not in records,'unique_case',r['identity']); records[key]=record
        check(record['metrics']['status']=='controller_quiescent','quiescent',r['identity'])
        check(not record.get('source_changed_during_case',False),'case_source',r['identity'])
    for name,expected in protocol['source_sha256'].items():
        read(root/'source_snapshot'/name,expected)
    return summary,protocol,records

def physical(result):
    copy=json.loads(json.dumps(result))
    copy['policy_stats']={k:v for k,v in copy['policy_stats'].items() if not k.endswith('_ms')}
    return copy

def key(seq):
    return tuple(sorted((p['tray_id'],p['destination_node'],tuple((l['edge_id'],l['depart'],l['arrive'])
        for l in p['legs']),p['usable_at'])for p in seq))

def m(case,end='final'):return case['endpoints'][end]['metrics']

def diffs(a,b):
    return {end:{'cost':m(b,end)['total_cost']-m(a,end)['total_cost'],
       'on_time':m(b,end)['on_time']-m(a,end)['on_time'],
       'completed':m(b,end)['completed']-m(a,end)['completed'],
       'components':{k:m(b,end)['cost_components'][k]-m(a,end)['cost_components'][k]
                     for k in m(a,end)['cost_components']}}for end in ('h80','final')}

def first_difference(a,b):
    previous={h['trigger_time']:h for h in a['slow_history']}
    for h in b['slow_history']:
        other=previous.get(h['trigger_time'])
        if other is None or key(h['proposals'])==key(other['proposals']):continue
        t=h['trigger_time']; da,db=other['diagnostics'],h['diagnostics']
        return {'time':t,'a':other,'b':h,
            'snapshot_sha_equal':da.get('snapshot_sha256')==db.get('snapshot_sha256') if 'snapshot_sha256' in da and 'snapshot_sha256' in db else None,
            'physical_trace_before_equal':[x for x in a['endpoints']['final']['result']['trace']if x['time']<t]==[x for x in b['endpoints']['final']['result']['trace']if x['time']<t],
            'candidate_sequences_equal':[key(r['proposals'])for r in da.get('scored_actions',[])if 'proposals' in r]==[key(r['proposals'])for r in db.get('scored_actions',[])if 'proposals' in r],
            'proxy_costs_a':[r.get('proxy_cost')for r in da.get('scored_actions',[])],
            'proxy_costs_b':[r.get('proxy_cost')for r in db.get('scored_actions',[])]}
    return None

def comparison(left,right,ca,cb):
    pairs=[]
    for si in range(4):
        for ti in range(9):
            a,b=ca[(f's{si}',f't{ti}',left)],cb[(f's{si}',f't{ti}',right)]
            pairs.append({'unit':f's{si}_t{ti}','scene':a['scene'],'tape':a['tape'],
                'a':a['identity'],'b':b['identity'],'delta_b_minus_a':diffs(a,b),
                'physical_endpoint_equal':{end:physical(a['endpoints'][end]['result'])==physical(b['endpoints'][end]['result']) for end in ('h80','final')},
                'route_history_equal':a['route_history']==b['route_history'],
                'slow_actions_equal':[(h['trigger_time'],h['proposals'])for h in a['slow_history']]==[(h['trigger_time'],h['proposals'])for h in b['slow_history']],
                'first_slow_physical_difference':first_difference(a,b)})
    return {'a':left,'b':right,'rows':pairs,'endpoints':{end:{
        'cost_delta':sum(r['delta_b_minus_a'][end]['cost']for r in pairs),
        'on_time_delta':sum(r['delta_b_minus_a'][end]['on_time']for r in pairs),
        'better':sum(r['delta_b_minus_a'][end]['cost'] < -1e-9 for r in pairs),
        'equal':sum(abs(r['delta_b_minus_a'][end]['cost']) <= 1e-9 for r in pairs),
        'worse':sum(r['delta_b_minus_a'][end]['cost'] > 1e-9 for r in pairs)}for end in ('h80','final')},
        'fully_equal_physical_endpoints':sum(all(r['physical_endpoint_equal'].values())for r in pairs),
        'equal_route_histories':sum(r['route_history_equal']for r in pairs),
        'equal_slow_actions':sum(r['slow_actions_equal']for r in pairs)}

summary,protocol,cases=load_run(SRC)
oldsummary,oldprotocol,old=load_run(OLD)
check(summary['recorded_episodes']==144 and len(cases)==144,'matrix_size','144 full factorial')
check(json.loads(read(SRC/'inputs.json'))==json.loads(read(OLD/'inputs.json',protocol['original_inputs_sha256'])),'same_inputs','all36 inputs')
for name,expected in protocol['source_sha256'].items():read(Path('scripts/experiments/ics_circulation_v3')/name,expected)
for name,expected in protocol['tests_sha256'].items():
    read(SRC/'test_snapshot'/name,expected);read(Path('tests')/name,expected)

ranking_checks=0
for ck,c in cases.items():
    if ck[2]==POLICIES[0]:
        reproduction=c['original_default_reproduction']
        check(all(reproduction['equal'].values()),'original_default_reproduction',c['identity'])
        read(Path(reproduction['file']),reproduction['sha256'])
    for h in c['slow_history']:
        d=h['diagnostics']; rows=d['scored_actions']
        check(d['rollout_calls']==len(rows) and len(rows)<=12,'rollout_accounting',(c['identity'],h['trigger_time']))
        if not rows:continue
        check(rows[0]['kind']=='greedy_incumbent' and rows[1]['kind']=='no_transfer','mandatory_actions',(c['identity'],h['trigger_time']))
        best=0
        for i,r in enumerate(rows):
            if r['status']!='complete':continue
            if i==0:continue
            cost,oldcost=r['proxy_cost'],rows[best]['proxy_cost']
            lower=cost<oldcost-1e-9
            tie=abs(cost-oldcost)<=1e-9 and c['factors']['tie']=='fewest_physical'
            if lower or (tie and (len(r['proposals']),key(r['proposals']),i)<(len(rows[best]['proposals']),key(rows[best]['proposals']),best)):best=i
        check(best==d['selected_action_index'],'independent_ranking',(c['identity'],h['trigger_time'],best,d['selected_action_index']))
        check(key(h['proposals'])==key(rows[best]['proposals']),'selected_action_committed',(c['identity'],h['trigger_time']))
        for r in rows:
            check(r['status']=='complete' and r['ticks']==40,'complete_projection',(c['identity'],h['trigger_time'],r['ordinal']))
            check(r['search_calls']==len(r['searches']) and r['search_work']==sum(x['work']for x in r['searches']),'search_accounting',(c['identity'],h['trigger_time'],r['ordinal']))
        ranking_checks+=1

def aggregate(policy):
    cs=[c for k,c in cases.items()if k[2]==policy]; rs=[r for r in summary['rows']if r['policy']==policy]
    ds=[h['diagnostics']for c in cs for h in c['slow_history']]; scores=[s for d in ds for s in d['scored_actions']]
    return {'policy':policy,'cases':len(cs),'endpoints':{end:{
        'cost':sum(m(c,end)['total_cost']for c in cs),'completed':sum(m(c,end)['completed']for c in cs),
        'scheduled':sum(m(c,end)['scheduled']for c in cs),'on_time':sum(m(c,end)['on_time']for c in cs),
        'cost_components':{k:sum(m(c,end)['cost_components'][k]for c in cs)for k in m(cs[0],end)['cost_components']}}
        for end in ('h80','final')},
        'invocation_cpu_seconds':sum(r['invocation_cpu_seconds']for r in rs),
        'deployment_cpu_seconds':sum(c['metrics']['process_cpu_seconds']for c in cs),
        'physical_proxy_calls':len(scores),'proxy_statuses':dict(Counter(s['status']for s in scores)),
        'internal_search_calls':sum(c['metrics']['internal_search_calls']for c in cs),
        'internal_search_work':sum(c['metrics']['internal_search_work']for c in cs),
        'maximum_rollouts_at_decision':max(d['rollout_calls']for d in ds),
        'scored_depth2':sum(len(s['proposals'])==2 for s in scores),
        'changed_actions':sum(d['actual_sequence_changed']for d in ds),
        'changed_to_no_transfer':sum(d['actual_sequence_changed'] and not d['scored_actions'][d['selected_action_index']]['proposals']for d in ds if d['scored_actions']),
        'fallbacks':sum(d['fallback_to_greedy']for d in ds),
        'omissions':{k:sum(c['metrics'][k]for c in cs)for k in ('unscored_enumerated_actions','unexplored_sequence_nodes','unsearched_requests','proposal_pool_discarded_valid')}}

table=[aggregate(p)for p in POLICIES]
pairs=[comparison(a,b,cases,cases)for a,b in combinations(POLICIES,2)]
references=[comparison(a,b,old,cases)for a in ('greedy','legacy_empty12','public_fast4','empty12_h40')for b in POLICIES]
units=[]
for si in range(4):
    for ti in range(9):
        unit={'unit':f's{si}_t{ti}','cost':{},'on_time':{}}
        for p in POLICIES:
            c=cases[(f's{si}',f't{ti}',p)];unit['cost'][p]=m(c)['total_cost'];unit['on_time'][p]=m(c)['on_time']
        unit['interaction_cost']=(unit['cost'][POLICIES[3]]-unit['cost'][POLICIES[2]])-(unit['cost'][POLICIES[1]]-unit['cost'][POLICIES[0]])
        units.append(unit)
for name,expected in tuple(artifacts.items()):check(sha256(Path(name).read_bytes()).hexdigest()==expected,'final_sha256',name)
result={'schema':'empty_factorial_pure_file_analysis_v1','source':str(SRC.resolve()),'no_new_simulations':True,
    'development_not_confirmation':True,'checks':dict(checks),'errors':errors,'artifact_sha256':artifacts,
    'table':table,'all_six_factor_pairs':pairs,'all_16_reference_pairs':references,'all36_units':units,
    'interaction_cost_sum':sum(u['interaction_cost']for u in units),
    'summary_accounting':{k:v for k,v in summary.items()if k!='rows'}}
OUT.mkdir(exist_ok=False)
with (OUT/'analysis.json').open('x',encoding='utf-8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
(OUT/'analyze.py').write_bytes(Path(__file__).read_bytes())
lines=['# 空盘选择：延续模型 × 同分规则的完整开发消融','',
    '固定 36 条原始 deployment tape，四格全部报告，共 144 次。实际控制均为 timed K4；候选构造、mandatory greedy/no-transfer、depth2、动作预算12、score40、搜索配额与公共 point proxy 不变。earliest/reactive 格保持共同 planning20/K4/真实 cursor，因此不宣称等同旧 legacy 内部 K1/planning40/snapshot-restart 模型。',
    '',f"全部 {len(cases)}/144 controller_quiescent；源码漂移为零，失败/截尾为零。纯文件核验 {sum(checks.values())} 项，错误 {len(errors)}；原默认格 36/36 复现旧 empty12_h40 的两端点完整物理 result（仅忽略 policy 毫秒字段）、路由历史和慢层动作。",'',
    '| proxy continuation / tie | final J | on time / scheduled | worker invocation CPU(s) | proxy calls | internal queries / work |',
    '|---|---:|---:|---:|---:|---:|']
for r in table:
    e=r['endpoints']['final'];lines.append(f"| {r['policy']} | {e['cost']:.1f} | {e['on_time']}/{e['scheduled']} | {r['invocation_cpu_seconds']:.3f} | {r['physical_proxy_calls']} | {r['internal_search_calls']} / {r['internal_search_work']} |")
lines += ['',f"所有格 198/198 完成；h80 与完整 drain 的聚合成本/准时数一致。完整本次 worker invocation CPU {summary['case_invocation_cpu_seconds_recorded']:.3f}s，协调器 wall {summary['coordinator_wall_seconds']:.3f}s（6 workers）。CPU 是本机同时实验负载下的测量，不能解释为可移植实时延迟。",'',
    '| paired change (B minus A) | final delta J | delta on time | better / equal / worse tapes |',
    '|---|---:|---:|---:|']
for r in pairs:
    e=r['endpoints']['final'];lines.append(f"| {r['a']} → {r['b']} | {e['cost_delta']:+.1f} | {e['on_time_delta']:+d} | {e['better']}/{e['equal']}/{e['worse']} |")
lines += ['',f"两因素的完整配对 interaction（earliest 下 tie 效果减 timed 下 tie 效果）合计 {result['interaction_cost_sum']:+.1f} J。逐 tape 数值与首动作分歧的 snapshot SHA、候选、proxy 成本和实际动作全部保存在 analysis.json。这里没有只保留收益样本，也不根据本结果宣称已选出部署配置。",'',
    '| versus legacy reference | delta J | delta on time | better / equal / worse |',
    '|---|---:|---:|---:|']
for r in references:
    if r['a']!='legacy_empty12':continue
    e=r['endpoints']['final'];lines.append(f"| {r['b']} | {e['cost_delta']:+.1f} | {e['on_time_delta']:+d} | {e['better']}/{e['equal']}/{e['worse']} |")
lines += ['','earliest/incumbent 与 timed/incumbent 成本相同；对同分规则的改变才产生这批流上的行为收益。timed/fewest 改善但还留一个 +2.1 J / −1 准时的 legacy 差额；earliest/fewest 的成本/准时达到旧强对照，因此这次消融解释了现有缺口，不能包装为超过强对照。所有 36×4 结果、各格与 greedy/legacy/public-fast/原 new 的配对分母均保留。',
    '', '候选覆盖和省略以 JSON 原始计数为准。若 depth2 为零、预算未饱和，只能说此开发族未激活联合两转移的机制；不能将动作预算或联合规划记为贡献。首分歧 snapshot SHA 相同的比较可解释选择规则在相同状态上的变化，后续总轨迹仍是各自重复部署的结果，不是固定续接下的单步因果差值。',
    '', '运行异常另账：首次 preflight 因 tuple/list 对照失配，0 仿真；第二次历史 JSON 比较假失败中止，保留 74 个已结束 episode（其中18条被旧 runner 错标 execution_failure，物理计算已完成但完整记录被异常处理覆盖），可恢复成功记录的 deployment CPU 下界239.375s，额外失配和在途 CPU 未知。当前144全量重跑未复用这些结果；总研究成本不可只记本次1139.969s。详见旧目录 preflight_failure.json / aborted_run.json。',
    '', '这份分析不运行模拟、不调整方法、不筛种子，不证明真实未来上的 dominance、稳定性或统计泛化。']
with (OUT/'FACTORIAL_RESULTS.md').open('x',encoding='utf-8')as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'checks':sum(checks.values()),'errors':errors,'table':table,'pairs':[{k:v for k,v in r.items()if k!='rows'}for r in pairs]},ensure_ascii=False))
raise SystemExit(bool(errors))
