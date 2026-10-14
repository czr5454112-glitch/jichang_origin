"""Pure-file full-denominator SAA mechanism extraction; no simulator imports."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter

BASE=Path('outputs/experiments/ics_circulation_v3')
SRC=BASE/'phase4_w3_empty_scenarios_20261010'
OLD=BASE/'phase4_w3_empty_improvement_20261010'
FACTOR=BASE/'phase4_w3_empty_factorial_complete_20261010'
OUT=Path(__file__).resolve().parent
SEEDS=('scenario8_s17','scenario8_s29','scenario8_s43')


def key(seq):
    return tuple(sorted((p['tray_id'],p['destination_node'],tuple((l['edge_id'],l['depart'],l['arrive'])for l in p['legs']),p['usable_at'])for p in seq))


def physical(result):
    result=json.loads(json.dumps(result))
    result['policy_stats']={k:v for k,v in result['policy_stats'].items()if not k.endswith('_ms')}
    return result


def run():
    cpu,wall=process_time(),perf_counter();bound={};checks=Counter();errors=[]
    if (OUT/'analysis.json').exists():raise FileExistsError('No replacing frozen mechanism analysis')
    if not (SRC/'summary.json').exists():raise FileNotFoundError('Formal144 summary not yet complete')

    def read(path,expected=None):
        data=path.read_bytes();actual=sha256(data).hexdigest();bound[str(path)]=actual
        if expected is not None:check(actual==expected,'sha256',str(path))
        return data

    def check(ok,kind,detail):
        checks[kind]+=1
        if not ok:errors.append({'kind':kind,'detail':detail})

    def index(root):
        s=json.loads(read(root/'summary.json'))
        return s,{r['identity']:r for r in s['rows']}

    summary,idx=index(SRC);_,oldidx=index(OLD);_,factidx=index(FACTOR)
    selection=json.loads(read(OUT/'selection_protocol.json'))
    check(summary['planned_episodes']==144 and len(idx)==144,'full144',len(idx))
    check(summary['statuses']=={'controller_quiescent':144},'complete_statuses',summary['statuses'])
    points={};scenarios={};legacy={};reproduction=[]

    def load(root,record):return json.loads(gzip.decompress(read(root/'cases'/record['file'],record['sha256'])))

    for si in range(4):
        for ti in range(9):
            unit=f's{si}_t{ti}'
            p=points[unit]=load(SRC,idx[unit+'_point'])
            legacy[unit]=load(OLD,oldidx[unit+'_legacy_empty12'])
            f=load(FACTOR,factidx[unit+'_timed_greedy__fewest_physical'])
            equal={end:physical(p['endpoints'][end]['result'])==physical(f['endpoints'][end]['result'])for end in ('h80','final')}
            equal['route_history']=p['route_history']==f['route_history']
            equal['slow_actions']=[(h['trigger_time'],h['proposals'])for h in p['slow_history']]==[(h['trigger_time'],h['proposals'])for h in f['slow_history']]
            check(all(equal.values()),'point_factorial_reproduction',unit);reproduction.append({'unit':unit,**equal})
            for seed in SEEDS:scenarios[(unit,seed)]=load(SRC,idx[unit+'_'+seed])

    def metrics(c,end):return c['endpoints'][end]['metrics']

    def first_difference(a,b):
        ah={h['trigger_time']:h for h in a['slow_history']}
        for h in b['slow_history']:
            old=ah.get(h['trigger_time'])
            if old is None or key(h['proposals'])==key(old['proposals']):continue
            da,db=old['diagnostics'],h['diagnostics']
            return {'time':h['trigger_time'],'a_selected':da['selected_action_index'],'b_selected':db['selected_action_index'],
                'same_snapshot_sha':da.get('snapshot_sha256')==db.get('snapshot_sha256')if 'snapshot_sha256'in da and 'snapshot_sha256'in db else None,
                'snapshot_sha_a':da.get('snapshot_sha256'),'snapshot_sha_b':db.get('snapshot_sha256'),
                'same_candidate_sequences':[key(r['proposals'])for r in da['scored_actions']if 'proposals'in r]==[key(r['proposals'])for r in db['scored_actions']if 'proposals'in r],
                'a_proposals':old['proposals'],'b_proposals':h['proposals']}
        return None

    pairs=[]
    for reference,table in [('point',points),('legacy',legacy)]:
        for unit in sorted(points):
            for seed in SEEDS:
                a,b=table[unit],scenarios[(unit,seed)]
                pairs.append({'reference':reference,'unit':unit,'seed':seed,'scene':b['scene'],'tape':b['tape'],
                    'a_identity':a['identity'],'b_identity':b['identity'],'first_slow_difference':first_difference(a,b),
                    'endpoints':{end:{'delta_cost':metrics(b,end)['total_cost']-metrics(a,end)['total_cost'],
                        'delta_on_time':metrics(b,end)['on_time']-metrics(a,end)['on_time'],
                        'delta_completed':metrics(b,end)['completed']-metrics(a,end)['completed'],
                        'component_deltas':{k:metrics(b,end)['cost_components'][k]-metrics(a,end)['cost_components'][k]for k in metrics(a,end)['cost_components']}}
                        for end in ('h80','final')}})
    aggregate=[]
    for ref in ('point','legacy'):
        for seed in SEEDS:
            ps=[p for p in pairs if p['reference']==ref and p['seed']==seed]
            aggregate.append({'reference':ref,'seed':seed,'n':len(ps),'endpoints':{end:{
                'delta_cost':sum(p['endpoints'][end]['delta_cost']for p in ps),
                'delta_on_time':sum(p['endpoints'][end]['delta_on_time']for p in ps),
                'better':sum(p['endpoints'][end]['delta_cost'] < -1e-9 for p in ps),
                'equal':sum(abs(p['endpoints'][end]['delta_cost'])<=1e-9 for p in ps),
                'worse':sum(p['endpoints'][end]['delta_cost'] > 1e-9 for p in ps)}for end in ('h80','final')}})
    selections=[]
    for seed in SEEDS:
        candidates=[p for p in pairs if p['reference']=='point' and p['seed']==seed]
        for role,sign in [('minimum_delta',1),('maximum_delta',-1)]:
            selected=min(candidates,key=lambda p:(sign*p['endpoints']['final']['delta_cost'],p['unit']))
            selections.append({'role':role,'unit':selected['unit'],'seed':seed,'delta_cost':selected['endpoints']['final']['delta_cost']})
    spread=[]
    for unit in sorted(points):
        costs={seed:metrics(scenarios[(unit,seed)],'final')['total_cost']for seed in SEEDS}
        spread.append({'unit':unit,'costs':costs,'range':max(costs.values())-min(costs.values())})
    maxspread=min(spread,key=lambda r:(-r['range'],r['unit']))
    selections += [{'role':'maximum_seed_spread','unit':maxspread['unit'],'seed':seed,
        'delta_cost':metrics(scenarios[(maxspread['unit'],seed)],'final')['total_cost']-metrics(points[maxspread['unit']],'final')['total_cost']}for seed in SEEDS]

    def composition(diag,score):
        proxy={b['bag_id']:b for b in diag.get('proxy_bags',[])}
        data=[]
        for request in score.get('scenarios',[]):
            physical_row=score['physical_scenarios'][request['physical_index']]
            tape=physical_row['public_scenario_tape'];sample={b['bag_id']:b for b in tape}
            data.append({'physical_index':request['physical_index'],'cache_hit':request['cache_hit'],
                'cost':request['proxy_cost'],'future_sha256':request['future_sha256'],'tape':tape,
                'cancelled_ids':sorted(proxy.keys()-sample.keys()),
                'changed_units':[{'bag_id':bid,'point':original,'scenario':sample[bid]}
                    for bid,original in proxy.items()if bid in sample and original!=sample[bid]]})
        if data:check(len(data)==8 and abs(sum(r['cost']for r in data)/8-score['proxy_cost'])<1e-8,'mean_eight',score['ordinal'])
        return data

    examples={}
    for choice in selections:
        identity=choice['unit']+'_'+choice['seed']
        if identity in examples:examples[identity]['roles'].append(choice['role']);continue
        p,s=points[choice['unit']],scenarios[(choice['unit'],choice['seed'])]
        first=first_difference(p,s);detail=None
        if first:
            hp=next(h for h in p['slow_history']if h['trigger_time']==first['time'])
            hs=next(h for h in s['slow_history']if h['trigger_time']==first['time'])
            ds=hs['diagnostics']
            detail={'point_decision':hp,'scenario_decision':hs,'eight_requested_samples':composition(ds,ds['scored_actions'][ds['selected_action_index']]),
                    'all_action_expectations':[{'ordinal':r['ordinal'],'kind':r['kind'],'proposals':r['proposals'],'expected_cost':r['proxy_cost'],
                       'scenario_costs':[x['proxy_cost']for x in r['scenarios']]}for r in ds['scored_actions']]}
        examples[identity]={'roles':[choice['role']],'unit':choice['unit'],'seed':choice['seed'],'delta_cost':choice['delta_cost'],
            'first_difference':first,'decision_evidence':detail,
            'actual_point_trace':p['endpoints']['final']['result']['trace'],'actual_scenario_trace':s['endpoints']['final']['result']['trace'],
            'metrics':{pol:{end:metrics(c,end)for end in ('h80','final')}for pol,c in [('point',p),('scenario',s)]}}

    changed=[n for n,h in bound.items()if sha256(Path(n).read_bytes()).hexdigest()!=h]
    result={'schema':'scenario_mechanism_analysis_v1','selection_protocol':selection,'all216_reference_pairs':pairs,
        'aggregate':aggregate,'all36_point_reproduction':reproduction,'all36_seed_spread':spread,
        'selected_examples':selections,'examples':examples,'bound_sha256':bound,'changed':changed,
        'checks':dict(checks),'errors':errors,'analysis_cpu_seconds':process_time()-cpu,'analysis_wall_seconds':perf_counter()-wall,
        'scope':'Pure file analysis, no new simulations, repeated deployment outcomes, no tuning or causal guarantee from posthoc traces'}
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 公共情景方法完整配对与机制例证','',
        '固定全36条流×三个种子，同时对point和legacy配对，共216项。例证选择规则已在完整summary出现前落盘；这是事后解释，不是重新训练、调先验或独立确认。',
        '', '| reference | seed | n | delta J | delta on time | better/equal/worse |','|---|---|---:|---:|---:|---:|']
    for r in aggregate:
        e=r['endpoints']['final'];lines.append(f"| {r['reference']} | {r['seed']} | {r['n']} | {e['delta_cost']:+.1f} | {e['delta_on_time']:+d} | {e['better']}/{e['equal']}/{e['worse']} |")
    lines+=['',f"最大三种子成本跨度：{maxspread['unit']}，{maxspread['range']:.1f} J。全部36条跨度均保留。每个种子的极值即使为零或同号也保留，不强行命名正/负例。",'',
        '| role | unit | seed | delta versus point |','|---|---|---|---:|']
    for r in selections:lines.append(f"| {r['role']} | {r['unit']} | {r['seed']} | {r['delta_cost']:+.1f} |")
    lines+=['',f"绑定{len(bound)}份原件，SHA变化{len(changed)}，检查{sum(checks.values())}项/错误{len(errors)}。point与原factorial timed/fewest的36次两端点完整物理、route/slow记录逐项验证。",'',
        'analysis.json保存每个首动作分歧的公开snapshot SHA、point预测、完整候选顺序、每候选八样本成本、八情景取消/扰动组成、重复权重与实际物理trace。样本均值是未校准prior下的估计，不能称真实未来条件期望或概率保证。',
        '', '逐例物理链另存PHYSICAL_CHAINS.md；所有正负分母保留，不能将选择出的极值当总体表现。']
    (OUT/'SCENARIO_MECHANISMS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'aggregate':aggregate,'selections':selections,'maxspread':maxspread,'errors':errors,'changed':changed,'cpu':result['analysis_cpu_seconds']},ensure_ascii=False))
    raise SystemExit(bool(errors or changed))


if __name__=='__main__':run()
