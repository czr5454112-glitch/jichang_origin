"""Independent full-cycle analysis comparison against audited raw result files."""
from collections import defaultdict
import json
from pathlib import Path
from time import perf_counter,process_time
from audit_round5_full_cycle import Audit,ROOT,read,file_hash


def metrics(result,expected,initial_completed):
    bags=result['final_snapshot']['bags']; completed=result['completed']; trays=result['final_trays']
    protected={k for k,b in bags.items() if b['protected']}
    observed=set(bags);done=set(completed)
    return {'total_cost':result['total_cost'],'cost_components':result['cost_components'],
        'expected_full_ledger_tasks':len(expected),'observed_tasks':len(observed),'unobserved_tasks':len(expected-observed),
        'completed_tasks':len(done),'newly_completed_since_checkpoint':len(done-initial_completed),
        'observed_uncompleted_tasks':len(observed-done),'full_ledger_uncompleted_tasks':len(expected-done),
        'on_time':sum(t<=bags[k]['deadline'] for k,t in completed.items()),
        'protected_observed':len(protected),'protected_completed':len(protected&done),
        'protected_on_time':sum(completed[k]<=bags[k]['deadline'] for k in protected&done),
        'protected_uncompleted':len(protected-done),'protected_completed_late':sum(completed[k]>bags[k]['deadline'] for k in protected&done),
        'completion_times':completed,'final_tray_positions':{k:t['node'] for k,t in trays.items()},
        'empty_in_transit':sum(t['mode']=='in_transit' and t['bag_id'] is None for t in trays.values()),
        'loaded_in_transit':sum(t['mode']=='in_transit' and t['bag_id'] is not None for t in trays.values()),
        'holding_or_unloading_trays':sum(t['mode'] in ('holding','unloading') for t in trays.values())}


def equal(a,b):
    if isinstance(a,float) or isinstance(b,float):return abs(a-b)<=1e-9
    if isinstance(a,dict):return set(a)==set(b) and all(equal(v,b[k]) for k,v in a.items())
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b


def main():
    wall,cpu=perf_counter(),process_time();audit=Audit()
    base=ROOT/'outputs/experiments/ics_circulation_v3'
    evidence=base/'phase4_w3_round5_independent_review_20261010'
    folder=base/'phase4_w3_network_full_cycle_analysis_20261010'
    formal=base/'phase4_w3_network_full_cycle_20261010'
    audit.manifest(folder)
    for path in (evidence/'full_cycle_final_audit.json',formal/'summary.json'):audit.bind(path)
    own=read(evidence/'full_cycle_final_audit.json')
    other=read(folder/'summary.json')
    other_values={x['identity']:x for x in read(folder/'samples.json')}
    for identity,value in own['independently_recomputed_sample_values'].items():
        reported=other_values[identity]
        for end in ('old80','full'):
            for k,v in value[end].items():audit.check(equal(v,reported[end][k]),identity,'independent full32 cost vector/value differs:'+end+':'+k)
        for k in ('baseline_ordinal','old80_choice_full_regret','exact_optset_equal','full_same_future_completion_times_differ','full_same_future_final_tray_positions_differ'):
            audit.check(equal(value[k],reported[k]),identity,'independent sample diagnostic differs:'+k)
    for k,v in own['independently_recomputed_summary'].items():audit.check(equal(v,other[k]),folder,'independent aggregate differs:'+k)
    original=base/'phase4_w3_network_role_labels_parallel_20261009'
    samples={}
    for scene in ('cross_cycle','counterflow','near_full'):
        for entry in read(original/scene/'summary.json')['samples']:
            path=original/scene/entry['file'];audit.bind(path)
            samples[entry['identity']]=read(path)
    reported={r['request_key']:r for r in read(folder/'requests.json')}
    rows=read(formal/'summary.json')['rows']
    cached={}; sums={end:defaultdict(float) for end in ('old80','full')}; costs={end:defaultdict(float) for end in sums}
    for row in rows:
        path=Path(row['file'])
        if str(path) not in cached:
            audit.bind(path,row['artifact_sha256'])
            raw=read(path)
            expected=set(raw['expected_task_ids']);initial=set(samples[row['sample']]['state']['completed'])
            cached[str(path)]={end:metrics(result,expected,initial) for end,result in (
                ('old80',raw['endpoints'][str(raw['old80_at'])]['result']),('full',raw['result']))} | {
                'search_calls':raw['search_calls'],'search_work':raw['search_work'],
                'cpu_seconds':raw['cpu_seconds'],'wall_seconds':raw['wall_seconds']}
        exact=cached[str(path)]
        for end in ('old80','full'):
            audit.check(equal(exact[end],reported[row['request_key']][end]),row['request_key'],'analysis request metrics not equal raw physical endpoint:'+end)
            for k,v in exact[end].items():
                if isinstance(v,(int,float)) and k!='total_cost':sums[end][k]+=v
            for k,v in exact[end]['cost_components'].items():costs[end][k]+=v
    for end,totals in sums.items():
        for k,v in totals.items():audit.check(equal(v,other['request_weighted'][end][k]),end,'request-weighted ledger aggregate differs:'+k)
        audit.check(equal(dict(costs[end]),other['request_weighted'][end]['cost_components_sum']),end,'request-weighted physical cost components differ')
    for source,target in (('search_calls','unique_physical_search_calls'),('search_work','unique_physical_search_work'),('cpu_seconds','unique_branch_cpu_seconds'),('wall_seconds','unique_branch_wall_seconds_sum_not_makespan')):
        audit.check(abs(sum(r[source] for r in cached.values())-other[target])<=1e-6,target,'unique physical resource sum differs')
    changed=[p for p,h in audit.files.items() if file_hash(p)!=h]
    audit.check(not changed,folder,'analysis or raw evidence changed during independent comparison')
    result={'schema':'ics_v3_full_cycle_analysis_independent_comparison_v1','checks':audit.count,
        'failed_checks':len(audit.errors),'errors':audit.errors,'requests':len(rows),'physical_files':len(cached),
        'independent_request_weighted':{end:dict(v) for end,v in sums.items()},
        'bound_files':len(audit.files),'all_bound_files_unchanged':not changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,'script_sha256':file_hash(__file__),
        'scope':'Compares independently audited 17x4x32 vectors and independently recomputed per-request endpoint task/protection/in-transit and cost ledgers against analysis. Uses actual raw outcomes, no new simulation. Request-weighted bag instances are correlated, not unique operational tasks.'}
    with (evidence/'full_cycle_analysis_comparison.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ('checks','failed_checks','requests','physical_files','wall_seconds')}))
    return bool(audit.errors)

if __name__=='__main__':raise SystemExit(main())
