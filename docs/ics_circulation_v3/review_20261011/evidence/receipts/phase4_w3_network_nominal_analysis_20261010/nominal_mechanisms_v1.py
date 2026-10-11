"""Pure-file complete nonflat census and post-hoc physical mechanism evidence."""
from collections import Counter,defaultdict
import json
from pathlib import Path
from time import perf_counter,process_time
from audit_round5_full_cycle import Audit,ROOT,read,file_hash


def movement_ledger(result,initial,allbags,network):
    carried={k:t['bag_id'] for k,t in initial['trays'].items()}
    loads,empty,loaded=[],[],[]
    for event in result['trace']:
        if event['event']=='load':
            carried[event['tray_id']]=event['bag_id']
            loads.append({'time':event['time'],'tray_id':event['tray_id'],'bag_id':event['bag_id'],
                'arrival':allbags[event['bag_id']]['arrival'],'wait':event['time']-allbags[event['bag_id']]['arrival']})
        elif event['event']=='unload_complete':
            carried[event['tray_id']]=None
        elif event['event']=='depart':
            edge=network['edges'][event['edge_id']]
            item={'depart':event['time'],'arrive':event['time']+edge['travel_time'],'tray_id':event['tray_id'],
                'bag_id':carried[event['tray_id']],'edge_id':event['edge_id'],'travel':edge['travel_time'],'capacity':edge['capacity']}
            (empty if item['bag_id'] is None else loaded).append(item)
    return {'loads':loads,'empty_legs':empty,'loaded_legs':loaded,
        'recomputed_queue_wait':sum(x['wait'] for x in loads),'recomputed_empty_distance':sum(x['travel'] for x in empty)}


def main():
    wall,cpu=perf_counter(),process_time()
    folder=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_network_nominal_opportunities_repaired_20261010'
    output=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_network_nominal_analysis_20261010'
    audit=Audit()
    audit.bind(output/'audit_and_values.json')
    analysis=read(output/'audit_and_values.json')
    summary=read(folder/'full/summary.json')
    audit.bind(folder/'full/summary.json')
    branches={(r['sample'],r['candidate']):r for r in summary['rows']}
    sources={}
    for scene in ('cross_cycle','counterflow','near_full'):
        path=ROOT/f'outputs/experiments/ics_circulation_v3/phase4_w3_network_role_labels_parallel_20261009/{scene}/{scene}_input.json'
        audit.bind(path)
        sources[scene]=read(path)
    nonflat=[]
    suboptimal=[]
    for state in analysis['states']:
        value=state['values']['final']
        if not value['complete_pool'] or value['spread']<=1e-8:
            continue
        meta=branches[state['identity'],0]
        path=folder/'collections'/state['scene']/f"d{meta['decision_index']:04d}.json"
        audit.bind(path)
        snapshot=read(path)
        row={k:snapshot[k] for k in ('identity','scene','decision_index','time','source_node','role','bag_id','tray_id','actual_chosen_index','original_role_sample','prefix_geometries')}
        row.update(costs=value['costs'],optset=value['optset'],local_regret=value['actual_choice_regret'],
            deadline=snapshot['state']['bags'][snapshot['bag_id']]['deadline'],candidate_family=state['candidate_family'],
            best_prefixes={str(i):snapshot['prefix_geometries'][i] for i in value['optset']},
            candidate_baseline_flags=[p['is_baseline'] for p in snapshot['candidates']])
        nonflat.append(row)
        if value['actual_choice_regret']<=1e-8:
            continue
        chosen,best=snapshot['actual_chosen_index'],min(value['optset'])
        source=sources[state['scene']]
        bags=dict(source['initial']['bags'])
        bags.update((b['bag_id'],b) for b in source['future_engine_only'])
        results=[]
        evidence=[]
        for index in (chosen,best):
            reference=branches[state['identity'],index]
            path=folder/reference['file']
            audit.bind(path,reference['sha256'])
            result=read(path)['result']
            results.append(result)
            moves=movement_ledger(result,source['initial'],bags,snapshot['state']['network'])
            audit.check(moves['recomputed_queue_wait']==result['cost_components']['tray_wait'],row['identity'],'origin-queue wait differs from actual load/arrival trace')
            audit.check(moves['recomputed_empty_distance']==result['cost_components']['empty_distance'],row['identity'],'empty distance differs from physical empty departures')
            evidence.append({'candidate':index,'raw_file':str(path),'raw_sha256':reference['sha256'],
                'total_cost':result['total_cost'],'cost_components':result['cost_components'],
                'completed':result['completed'],'final_trays':result['final_trays'],**moves,
                'controller_events_after_decision':[e for e in result['trace'] if e['time']>=snapshot['time'] and e['event'] in ('slow_commit','empty_dispatch','empty_continue','load','unload_complete')]})
        baseline,alternative=results
        row.update(best_representative=best,best_representative_rule='least candidate ordinal among all equal full-cycle minima; post-hoc explanation only',
            cost_component_delta={k:alternative['cost_components'][k]-v for k,v in baseline['cost_components'].items()},
            current_bag_completed_baseline=baseline['completed'][snapshot['bag_id']],
            current_bag_completed_best=alternative['completed'][snapshot['bag_id']],
            current_bag_completion_delay=alternative['completed'][snapshot['bag_id']]-baseline['completed'][snapshot['bag_id']],
            completion_changes={k:{'baseline':v,'best':alternative['completed'][k],'delta':alternative['completed'][k]-v} for k,v in baseline['completed'].items() if alternative['completed'][k]!=v},
            final_tray_changes={k:{'baseline':v,'best':alternative['final_trays'][k]} for k,v in baseline['final_trays'].items() if alternative['final_trays'][k]!=v},
            movement_and_resource_evidence=evidence)
        suboptimal.append(row)
    flats=[{k:s[k] for k in ('identity','scene','role','source_node','candidate_family')} | {
        'completion_vectors':s['values']['final']['distinct_completion_vectors'],
        'tray_position_vectors':s['values']['final']['distinct_tray_position_vectors']}
        for s in analysis['states'] if s['values']['final']['complete_pool'] and s['values']['final']['spread']<=1e-8
        and (s['values']['final']['distinct_completion_vectors']>1 or s['values']['final']['distinct_tray_position_vectors']>1)]
    audit.check((len(nonflat),len(suboptimal),len(flats))==(25,12,51),output,'classification denominator differs from complete audit')
    strongest=min(suboptimal,key=lambda r:(-r['local_regret'],r['scene'],r['time'],r['identity']))
    ordinary=min(suboptimal,key=lambda r:(r['local_regret'],r['scene'],r['time'],r['identity']))
    for name in ('prebalance.py','runtime.py'):
        audit.bind(ROOT/'scripts/experiments/ics_circulation_v3'/name)
    changed=[p for p,h in audit.files.items() if file_hash(p)!=h]
    audit.check(not changed,output,'bound raw files changed during mechanism analysis')
    result={'schema':'ics_v3_nominal_complete_posthoc_mechanism_audit_v1','new_physical_simulations':0,
        'checks':audit.count,'failed_checks':len(audit.errors),'errors':audit.errors,
        'all_25_nonflat':nonflat,'all_12_suboptimal':suboptimal,'all_51_costflat_physical_differences':flats,
        'nonflat_classification':dict(Counter(r['role']+'|'+r['candidate_family'] for r in nonflat)),
        'flat_different_classification':dict(Counter(r['role']+'|'+r['candidate_family'] for r in flats)),
        'posthoc_examples':{'strongest':strongest['identity'],'ordinary_lowest_positive_regret':ordinary['identity']},
        'bound_file_sha256':audit.files,'all_bound_files_unchanged':not changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,'script_sha256':file_hash(__file__),
        'interpretation':'All 25 nonflat and all 12 suboptimal actual states retained. Examples are declared post-hoc, not training selection. One reused nominal future and fixed timed/greedy continuation; local interventions along one episode cannot be summed into achievable savings.'}
    with (output/'mechanisms.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# 原图全部实际决策：供盘时序机制','',
        '完整693分支均已排空，覆盖174非空状态和另6个无候选尝试。25池的完整周期成本非平坦，12池中实际Timed选择并非事后最优；旧18抽样没有覆盖这12池。全部12均在counterflow，实际选择index0且该候选标is_baseline，但它不是知道未来的oracle。',
        '', '这些是固定后续控制和单条已复用nominal任务流下的一次当前动作偏离。沿同一路径的状态互相关联；不能把12个局部regret相加称作可部署episode节省，更不能据此按收益挑训练样本。',
        '', '|d|scene / node / t|bag|role|完整成本向量 c0,c1,c2,c3|全部最优index|最优实际前缀|当前袋完成 延迟|Δqueue wait / Δempty distance|终态改变盘|',
        '|---:|---|---|---|---|---|---|---|---|---|']
    for r in suboptimal:
        lines.append(f"|{r['decision_index']}|{r['scene']} / {r['source_node']} / {r['time']}|{r['bag_id']}|{r['role']}|{', '.join(f'{c:.1f}' for c in r['costs'])}|{','.join(map(str,r['optset']))}|{' ; '.join(r['best_prefixes'][str(r['best_representative'])])}|{r['current_bag_completed_baseline']}→{r['current_bag_completed_best']} ({r['current_bag_completion_delay']:+})|{r['cost_component_delta']['tray_wait']:+.0f} / {r['cost_component_delta']['empty_distance']:+.0f}|{', '.join(r['final_tray_changes'])}|")
    lines += ['',
        '最强反例按完整局部regret降序、时间升序确定为d40（并列45.7中最早）。t126的round1:flow1原走26→27→28，后续到114，139完成；最优当前合法前缀改为26→27→2，后续原控制继续绕行，157完成，比原来晚18但仍早于deadline211。原执行在139立即将114的initial:49:0承诺空返26，路程70，209才装载t156到达的round2:flow1，222完成。替代分支在t156由reactive empty_dispatch调用原先停在46的warm_tray，经46→39→40→52→26，169装载，182完成。当前袋变慢18，后续袋提前40；全期queue wait下降40，empty distance下降57，J下降45.7。',
        '',
        '此共享资源链是实体空盘可用性与承诺，不是已证实的某条边容量瓶颈。26和46同属international，114属domestic。原PredictivePrebalancer跳过同zone供盘，reactive dispatch可响应同zone可见任务；原分支的既有承诺阻止重复供盘。因而路径偏离通过改变卸载时刻间接改变后续供盘。成本没有独立的loaded travel项；本例当前袋虽变慢仍准时，所以解释必须附带成本权重和固定slow continuation。',
        '',
        '普通反例取全部正regret中最小值并按时间确定d19（22.7）。t46在112，当前前缀由112→113改112→53；当前round0:flow1完成49→86，晚37但仍早于deadline151。原initial:26:0于49提前承诺空返，替代分支改由round0:flow2的initial:49:0在51空返；round1:flow1在96到达后由46的initial:134:0响应，109装载/122完成，原126装载/139完成。此后也有代价：round2:flow0完成157→172（晚15），同时round2:flow2完成216→205，round2:flow1完成222→217。所有到达、实际装载和完成时间均保留，不能仅展示提前的袋。全期queue wait净下降17、empty distance下降57，J下降22.7。',
        '',
        f"25非平坦分类：{result['nonflat_classification']}。另51个cost-flat但完成时间向量或终态盘位置不同的池分类：{result['flat_different_classification']}。成本平坦不等于物理轨迹相同。mechanisms.json保留全部25/12/51身份，以及12对分支完整装载账、空载/载袋逐边移动、控制事件、完成变化、盘终态和原始文件SHA。",'',
        f"独立逐事件复算12对分支：queue wait等于各load time−arrival之和，empty distance等于空载depart所用边travel_time之和；{audit.count} checks，{len(audit.errors)} errors，无新仿真。"]
    with (output/'NOMINAL_MECHANISMS.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({k:result[k] for k in ('checks','failed_checks','nonflat_classification','flat_different_classification','posthoc_examples','wall_seconds')}))
    return bool(audit.errors)

if __name__=='__main__':raise SystemExit(main())
