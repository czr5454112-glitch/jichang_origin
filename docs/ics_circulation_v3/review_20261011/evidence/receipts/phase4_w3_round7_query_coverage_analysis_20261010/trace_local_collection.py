"""Transparent paths-yield instrumentation for fixed six cells and controls.

No simulation; no generator settings or ordering altered. Formal results stay
untouched. Original baseline status/work/raw is checked for each traced query.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import gzip,json,pickle,sys,time

ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from scripts.experiments.ics_circulation_v3.routing_reference import EventTimeSearch
from scripts.experiments.ics_circulation_v3.same_zone_query_coverage import coverage_cell,shadow_variant,VARIANTS
BASE=ROOT/'outputs/experiments/ics_circulation_v3';HERE=Path(__file__).parent
COLLECTION=BASE/'phase4_w3_same_zone_query_coverage_20261010'
SHADOW=BASE/'phase4_w3_same_zone_query_shadow_20261010'


def main():
    cpu,wall=time.process_time(),time.perf_counter();bound={}
    def raw(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest();return data
    selected=json.loads(raw(SHADOW/'selection.json'));chosen={}
    for row in sorted(selected['formal'],key=lambda r:(r['case_id'],r['time'],r['query_ordinal'])):
        if row['selection']=='all_truncated':chosen.setdefault(coverage_cell(row),row)
    requests=list(chosen.values())+[r for r in selected['formal']if r['selection']=='earliest_successful_control']
    rows=[];original=EventTimeSearch.paths
    for request in requests:
        data=raw(COLLECTION/request['file'])
        if sha256(data).hexdigest()!=request['sha256']:raise ValueError('query artifact drift')
        query=pickle.loads(gzip.decompress(data));calls=[]
        def observed(search,source,start_tick,targets,**kwargs):
            row={'source':source,'start_tick':start_tick,'targets':sorted(targets),
                'stage':kwargs.get('stage','full_graph_time_labels'),'per_target':kwargs.get('per_target'),
                'labels_per_state':kwargs.get('labels_per_state',1),'yielded':[],
                'completed_iteration':False,'exception':None}
            calls.append(row)
            try:
                for node,tick,legs in original(search,source,start_tick,targets,**kwargs):
                    row['yielded'].append({'node':node,'tick':tick,'legs':[asdict(l)for l in legs]})
                    yield node,tick,legs
                row['completed_iteration']=True
            except Exception as error:
                row['exception']={'type':type(error).__name__,'message':str(error)};raise
        try:
            EventTimeSearch.paths=observed
            result=shadow_variant(query,VARIANTS[0])
        finally:EventTimeSearch.paths=original
        lost=[c for c in calls if c['stage']=='dynamic_local_time_labels'and c['exception']and c['yielded']]
        rows.append({'request':request,'baseline_reproduced':result['original_query_reproduced'],
            'result':result,'path_calls':calls,'aborted_partial_local_pool_count':len(lost),
            'yielded_labels_in_aborted_local_pools':sum(len(c['yielded'])for c in lost),
            'yielded_destination_labels_in_aborted_local_pools':sum(x['node']==query['destination']for c in lost for x in c['yielded']),
            'interpretation':'A yielded portal label discarded by tuple materialization is an observed batching loss, but does not prove a missing feasible terminal route or improved objective.'})
    changed=[p for p,h in bound.items()if sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    result={'requests':len(requests),'rows':rows,'all_baselines_exact':all(r['baseline_reproduced']for r in rows),
        'changed_inputs':changed,'new_physical_simulations':0,'new_search_invocations':len(requests),
        'selection_rule':'Earliest identity per six truncated public query cells, plus all six previously selected matched successful controls; no outcome or cost selected the representative.',
        'bound_input_sha256':bound,'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.perf_counter()-wall,
        'resource_scope':'Read/hash and transparent baseline search instrumentation; nested per-query clocks excluded from addition, final serialization excluded.'}
    with(HERE/'local_yield_trace.json').open('x',encoding='utf8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k]for k in ('requests','all_baselines_exact','changed_inputs','cpu_seconds','wall_seconds')}))

if __name__=='__main__':main()
