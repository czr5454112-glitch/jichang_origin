"""All actual nominal decision coverage, without reading any branch outcome."""
from collections import Counter,defaultdict
import json
from pathlib import Path
from time import process_time,perf_counter
from audit_round5_full_cycle import Audit,ROOT,read,file_hash

def main():
    folder=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_network_nominal_opportunities_repaired_20261010'
    output=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_network_nominal_analysis_20261010'
    wall,cpu=perf_counter(),process_time()
    audit=Audit()
    start=read(folder/'full_input_manifest_start.json')
    states=[]
    for scene in ('cross_cycle','counterflow','near_full'):
        path=folder/'collections'/scene/'collection.json.gz'
        audit.bind(path,start[str(path.relative_to(folder))])
        body=read(path)
        for meta in body['attempts']:
            path=folder/'collections'/scene/f"d{meta['decision_index']:04d}.json"
            audit.bind(path,start[str(path.relative_to(folder))])
            row=read(path)
            node=str(row['source_node'])
            network=row['state']['network']
            families=('zero' if row['candidate_count']==0 else 'spatial_prefix' if row['prefix_geometry_distinct']>1 else
                'timed_prefix_only' if row['timed_prefix_distinct']>1 else 'conditional_witness_only' if row['actual_action_distinct']>1 else 'identical_actual_action')
            states.append({k:row[k] for k in ('identity','scene','decision_index','role','source_node','time','protected',
                'original_role_sample','candidate_count','prefix_geometry_distinct','timed_prefix_distinct','actual_action_distinct')} | {
                'candidate_family':families,'node':network['nodes'][node],
                'positive_capacity_in_degree':sum(str(e['target'])==node and e['capacity']>0 for e in network['edges'].values()),
                'positive_capacity_out_degree':sum(str(e['source'])==node and e['capacity']>0 for e in network['edges'].values())})
    audit.check(len(states)==180 and sum(s['candidate_count']>0 for s in states)==174,folder,'actual-state denominator mismatch')
    def summarize(group):
        positive=[s for s in group if s['candidate_count']]
        return {'attempts':len(group),'nonempty':len(positive),'zero':len(group)-len(positive),
            'old_sample_attempts':sum(s['original_role_sample'] for s in group),
            'old_sample_nonempty':sum(s['original_role_sample'] for s in positive),
            'time_min':min(s['time'] for s in group),'time_max':max(s['time'] for s in group),
            'protected_attempts':sum(s['protected'] for s in group),
            'candidate_count_histogram':dict(Counter(str(s['candidate_count']) for s in group)),
            'candidate_families':dict(Counter(s['candidate_family'] for s in group)),
            'spatial_prefix_distinct_histogram':dict(Counter(str(s['prefix_geometry_distinct']) for s in group)),
            'timed_prefix_distinct_histogram':dict(Counter(str(s['timed_prefix_distinct']) for s in group)),
            'nonempty_old_sample_coverage_fraction':sum(s['original_role_sample'] for s in positive)/len(positive) if positive else None}
    strata={}
    for axes in (('role',),('source_node',),('role','source_node'),('scene','role','source_node')):
        groups=defaultdict(list)
        for state in states:groups['|'.join(str(state[k]) for k in axes)].append(state)
        strata['|'.join(axes)]={key:summarize(group) for key,group in sorted(groups.items())}
    all_summary=summarize(states)
    unseen=sorted({str(s['source_node']) for s in states if s['candidate_count']} - {str(s['source_node']) for s in states if s['candidate_count'] and s['original_role_sample']})
    changed=[p for p,h in audit.files.items() if file_hash(p)!=h]
    audit.check(not changed,folder,'collection artifacts changed during feature-only analysis')
    result={'schema':'ics_v3_nominal_actual_feature_only_coverage_v1','branch_outcomes_read':False,
        'counts':all_summary,'strata':strata,'states':states,'nonempty_nodes_absent_from_old_nonempty_sample':unseen,
        'checks':audit.count,'failed_checks':len(audit.errors),'errors':audit.errors,'bound_files':len(audit.files),
        'all_bound_files_unchanged':not changed,'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'script_sha256':file_hash(__file__),'scope':'Only actual decision snapshot/candidate geometry and previous sampling flags. Reads no counterfactual cost, outcome, regret or future label to select coverage or examples.'}
    output.mkdir(parents=True,exist_ok=True)
    with (output/'feature_coverage.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('counts','nonempty_nodes_absent_from_old_nonempty_sample','checks','failed_checks','wall_seconds')}))
    return bool(audit.errors)

if __name__=='__main__':raise SystemExit(main())
