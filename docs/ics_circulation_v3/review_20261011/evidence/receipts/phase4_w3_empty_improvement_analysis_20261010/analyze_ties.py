import gzip
from hashlib import sha256
import json
from pathlib import Path
from collections import Counter

SRC=Path('outputs/experiments/ics_circulation_v3/phase4_w3_empty_improvement_20261010')
OUT=Path('outputs/experiments/ics_circulation_v3/phase4_w3_empty_improvement_analysis_20261010')
summary=json.loads((SRC/'summary.json').read_text())
cases={}
hashes={}
for row in summary['rows']:
    path=SRC/'cases'/row['file']
    data=path.read_bytes()
    hashes[row['file']]=sha256(data).hexdigest()
    assert hashes[row['file']]==row['sha256']
    cases[(row['scene'],row['tape'],row['policy'])]=json.loads(gzip.decompress(data))

def physical(record):
    r=json.loads(json.dumps(record))
    r['policy_stats']={k:v for k,v in r['policy_stats'].items() if not k.endswith('_ms')}
    return r

def signature(seq):
    return sorted((p['tray_id'],p['destination_node'],tuple((l['edge_id'],l['depart'],l['arrive'])for l in p['legs']))for p in seq)

coverage={}
for policy in ('empty2_h40','empty12_h40','empty24_h40','empty24_h80'):
    ds=[h['diagnostics']for k,c in cases.items()if k[2]==policy for h in c['slow_history']]
    coverage[policy]={'slow_triggers':len(ds),'rollout_call_histogram':dict(Counter(d['rollout_calls']for d in ds)),
        'maximum_actual_rollouts':max(d['rollout_calls']for d in ds),
        'unscored_enumerated_actions':sum(d['unscored_enumerated_actions']for d in ds),
        'unexplored_sequence_nodes':sum(d['unexplored_sequence_nodes']for d in ds),
        'unsearched_requests':sum(d['proposal_unsearched_requests']for d in ds),
        'discarded_valid_candidates':sum(d['proposal_pool_discarded_valid']for d in ds),
        'scored_depth_two_sequences':sum(len(r['proposals'])==2 for d in ds for r in d['scored_actions']),
        'selected_no_transfer_over_nonempty_incumbent':sum(d['actual_sequence_changed']and not h['proposals']for k,c in cases.items()if k[2]==policy for h in c['slow_history']for d in (h['diagnostics'],))}
equivalence=[]
for left,right in (('greedy','empty2_h40'),('empty12_h40','empty24_h40'),('empty24_h40','empty24_h80')):
    rows=[]
    for scene,tape,policy in cases:
        if policy!=left:continue
        a,b=cases[(scene,tape,left)],cases[(scene,tape,right)]
        rows.append({'scene':scene,'tape':tape,'physical_results':{end:physical(a['endpoints'][end]['result'])==physical(b['endpoints'][end]['result'])for end in ('h80','final')},
            'route_history_equal':a['route_history']==b['route_history'],
            'slow_actions_equal':[(h['trigger_time'],h['proposals'])for h in a['slow_history']]==[(h['trigger_time'],h['proposals'])for h in b['slow_history']]})
    equivalence.append({'left':left,'right':right,'rows':rows,'all_equal':all(all(r['physical_results'].values())and r['route_history_equal']and r['slow_actions_equal']for r in rows)})
comparisons=[]
for scene,tape,policy in cases:
    if policy!='empty12_h40':continue
    a,b=cases[(scene,tape,policy)],cases[(scene,tape,'legacy_empty12')]
    am,bm=a['endpoints']['final']['metrics'],b['endpoints']['final']['metrics']
    old={h['trigger_time']:h for h in b['slow_history']}
    first=None
    for h in a['slow_history']:
        t=h['trigger_time'];other=old.get(t)
        if other is not None and signature(h['proposals'])!=signature(other['proposals']):
            first={'time':t,'new':h,'legacy':other,
                'past_trace_equal':[r for r in a['endpoints']['final']['result']['trace']if r['time']<t]==[r for r in b['endpoints']['final']['result']['trace']if r['time']<t],
                'loaded_history_through_tick_equal':[r for r in a['route_history']if r['time']<=t]==[r for r in b['route_history']if r['time']<=t],
                'source_version_equal':h['diagnostics']['snapshot_version']==other['diagnostics']['snapshot_version'],
                'state_evidence_limit':'legacy lacks full snapshot hash; this verifies common initial input and matching recorded physical/control prefix, not a direct full-snapshot comparison'}
            break
    row={'scene':scene,'tape':tape,'new_case':a['identity'],'legacy_case':b['identity'],
        'final_delta':am['total_cost']-bm['total_cost'],'on_time_delta':am['on_time']-bm['on_time'],
        'components_delta':{k:am['cost_components'][k]-bm['cost_components'][k]for k in am['cost_components']},
        'first_slow_proposal_difference':first}
    if abs(row['final_delta'])>1e-8 or row['on_time_delta']:
        row.update(new_trace=a['endpoints']['final']['result']['trace'],legacy_trace=b['endpoints']['final']['result']['trace'],
            new_final_snapshot=a['endpoints']['final']['result']['final_snapshot'],legacy_final_snapshot=b['endpoints']['final']['result']['final_snapshot'])
    comparisons.append(row)
for name,expected in hashes.items():assert sha256((SRC/'cases'/name).read_bytes()).hexdigest()==expected
payload={'source':str(SRC.resolve()),'case_hashes':hashes,'coverage':coverage,'trajectory_equivalence':equivalence,'all_legacy_direct_pairs':comparisons,
    'new_minus_legacy':sum(r['final_delta']for r in comparisons),'on_time_delta':sum(r['on_time_delta']for r in comparisons),
    'interpretation':'read-only mechanism evidence; no new physical calls, no policy tuning, no independent causal ablation'}
with (OUT/'tie_and_coverage.json').open('x',encoding='utf-8')as f:json.dump(payload,f,ensure_ascii=False,indent=2)
(OUT/'analyze_ties.py').write_bytes(Path(__file__).read_bytes())
text='''# 平局、实际候选覆盖与旧强对照

全部252原件重读；本追加分析无新仿真。`tie_and_coverage.json`保留36个new-vs-legacy直接配对，包括32成本相等项，及全部三组预算/窗口轨迹核对。

**预算没有饱和。** new12h40、new24h40、new24h80每次最多只评7条序列；未评分已枚举动作、未搜索请求、丢弃合法候选、剩余搜索节点均0。三版没有一个depth2序列得到评分，本开发族实际供需域尚未形成两项联合空调。12→24以及40→80各36对的h80/final完整物理result（仅去policy毫秒字段）、route history与slow实际动作均一致。greedy→new2也36/36全部一致，等待对照没有改善。不得包装为更大搜索预算、长窗或联合depth2的实验成功。

**旧强对照优于新方法的差额集中在4/36，合计16.2成本、4个准时任务。** 两个L2_D3压力例各+6；L2_D1 stress4、L4_D1 stress7各+2.1。其余32对成本相等。四例首slow分歧前的物理trace、当前tick前loaded决策、snapshot version均一致；旧legacy没有完整snapshot hash，故不将该前缀核对伪称直接完整state哈希证明。

1. L2_D3 stress0/stress4在t24/t26：new保留greedy的B盘loaded→C，而legacy的no-transfer与此调拨proxy同分，按动作数优先选空序列。同tickreactive从G选donor→C（两盘ETA同为2，reactive按盘名排序），当前逆向C→B任务完成时刻不变，却交换后续供盘身份。到t34下一轮预测公布，legacy两盘都在B，可把donor预调S于37可用，S任务40装载45完成；new的B盘须守B需求，G盘与S同zone被慢层跨zone候选规则排除，40才reactive返回S，43装载48完成。每例wait+3、tardy+3=+6。这不是把no-transfer误当成实际静止。
2. L2_D1 stress4与L4_D1 stress7在t34：new的delayed/early/no-transfer在其timed+未来greedy proxy下同分，保留delayed incumbent；legacy没有未来慢层，no-transfer更贵，early与delayed同分时按physical key选early。delayed在CS40/SX41形成不可撤销预约，真实逆向G→S任务到达后S盘被迫选SY/YG去G47才可装载；legacy此前已走完SX，S盘走SX/XG于G46装载。该袋51→50完成，deadline50，从逾期变准时；每例wait1+tardy1+加权empty0.1=+2.1。

候选在new池中已存在，增加到24或80未打破这些平局。简单移植legacy tie也不等于legacy：在new proxy中no-transfer往往因后续greedy补调而同分，旧legacy却给它较高成本。接下来的完整36条流2×2开发消融因此固定同一候选构造、K、预算、公开proxy、真实执行，只交叉proxy continuation（timed+未来greedy / earliest+reactive无未来slow）与tie（原incumbent / 少转移后physical key）。所有四配置保留，不能只报最优一格或称独立确认。
'''
with (OUT/'TIE_AND_COVERAGE.md').open('x',encoding='utf-8')as f:f.write(text)
print(json.dumps({'trajectory_equivalence':[{'left':r['left'],'right':r['right'],'all_equal':r['all_equal']}for r in equivalence],'new_minus_legacy':payload['new_minus_legacy'],'on_time_delta':payload['on_time_delta']},ensure_ascii=False))
