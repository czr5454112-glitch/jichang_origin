"""Full27 frozen new-policy query collection and fixed shadow coverage probes."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from copy import deepcopy
from dataclasses import asdict
import argparse,gzip,json,pickle,traceback
from pathlib import Path
from time import process_time,perf_counter

from .model import Bag
from .network_full_cycle import compare_old_result
from .network_role_labels import SPEC,bind_accounting
from .phase4_control import build_engine
from .phase4_network_workloads import file_sha
from .role_coverage import CursorSimulation
from .routing_cache_contract import enable_replay_cache
from .run_same_zone_supply import exact_original_scene,exact_json_value,read,write_gzip
from .same_zone_experiment import CASE_BUDGET,TAIL_CAP,install_supply_policy
from .same_zone_labels import run_cycle
from .same_zone_query_probe import install_query_probe
from .same_zone_query_coverage import VARIANTS,probe_query,query_summary,select_requests
from .experiment_resources import memory_snapshot

ROOT=Path(__file__).resolve().parents[3];SOURCE=Path(__file__).parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
OLD=BASE/'phase4_w3_same_zone_supply_repaired_20261010'
DEFAULT=BASE/'phase4_w3_same_zone_query_coverage_20261010'


def write(path,value):
    with Path(path).open('x',encoding='utf8')as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def manifest(output,name,paths):
    output=Path(output)
    write(output/name,{str(Path(p).resolve()):file_sha(p)for p in paths})


def verify_manifest(path):
    for name,h in read(path).items():
        if file_sha(name)!=h:raise ValueError('artifact manifest drift: '+name)


def collection_root(output):
    return Path(read(Path(output)/'protocol.json').get('reused_collection_root',output))


def without_ms(value):
    if isinstance(value,dict):return{k:without_ms(v)for k,v in value.items()if not k.endswith('_ms')}
    if isinstance(value,(list,tuple)):return[without_ms(v)for v in value]
    return value


def compare_collection(old,new):
    checks={'final_result':compare_old_result(old['result'],new['result'])['equal']}
    for field in ('status','stopped_at','initial_state','initial_cursor','opportunities','searches',
                  'cache_before','cache_after','slow_history_suffix','actual_slow_trigger_times',
                  'selector_history_suffix','physical_tick_trace','event_trace_suffix','milestones',
                  'last_cycle_state','evaluation_ledger'):
        checks[field]=exact_json_value(without_ms(old[field]),without_ms(new[field]))
    checks['original_endpoint_result']=compare_old_result(old['original_endpoint']['result'],new['original_endpoint']['result'])['equal']
    checks['original_endpoint_state_and_search']=exact_json_value(
        {k:v for k,v in old['original_endpoint'].items()if k!='result'},
        {k:v for k,v in new['original_endpoint'].items()if k!='result'})
    return checks


def persist_collection(folder,output,request,sink,outcome):
    """Keep independent query artifacts and recover outcome on write failure."""
    indices=[];failures=[]
    for query in sink:
        p=folder/f"q{query['query_ordinal']:05d}.pkl.gz"
        try:
            with gzip.open(p,'xb')as stream:pickle.dump(query,stream,protocol=pickle.HIGHEST_PROTOCOL)
            summary=query_summary(query)if query['phase']=='returned'else {k:query.get(k)for k in ('query_ordinal','phase','time','last_search_status','error')}
            indices.append({**summary,'query_id':request['case_id']+f":q{query['query_ordinal']:05d}",
                'case_id':request['case_id'],'scene':request['scene'],'tape_id':request['tape_id'],
                'file':str(p.relative_to(output)),'sha256':file_sha(p)})
        except Exception as error:
            failures.append({'scope':'query','query_ordinal':query['query_ordinal'],
                'type':type(error).__name__,'message':str(error),'partial_file':str(p.relative_to(output))if p.exists()else None})
    if outcome is not None:
        try:write_gzip(folder/'outcome.json.gz',outcome)
        except Exception as error:
            failures.append({'scope':'outcome','type':type(error).__name__,'message':str(error)})
            try:write(folder/'outcome.recovery.json',outcome)
            except Exception as recovery:
                failures.append({'scope':'outcome_recovery','type':type(recovery).__name__,'message':str(recovery)})
    try:write(folder/'queries.json',indices)
    except Exception as error:
        failures.append({'scope':'query_index','type':type(error).__name__,'message':str(error)})
    return indices,failures


def verify(output):
    output=Path(output);protocol=read(output/'protocol.json')
    if(output/'preparation_manifest.json').exists():verify_manifest(output/'preparation_manifest.json')
    for name,h in protocol['source_sha256'].items():
        if file_sha(SOURCE/name)!=h:raise ValueError('frozen source drift: '+name)
    for name,h in protocol['test_sha256'].items():
        if file_sha(ROOT/'tests'/name)!=h:raise ValueError('frozen test drift: '+name)
    for path,h in protocol['input_sha256'].items():
        if file_sha(path)!=h:raise ValueError('input drift: '+path)
    return protocol


def validate_old_artifacts():
    summary=read(OLD/'full/summary.json');old_manifest=read(OLD/'full/manifest.json')
    for name,h in old_manifest.items():
        if file_sha(OLD/'full'/name)!=h:raise ValueError('round6 manifest drift: '+name)
    requests=[r for r in summary['rows']if r['policy']=='same_zone32plus32']
    for r in requests:
        if file_sha(OLD/r['file'])!=r['sha256']or old_manifest[Path(r['file']).name]!=r['sha256']:
            raise ValueError('round6 summary/raw manifest binding differs')
    return requests


def import_collection(origin):
    """Bind immutable prior collection; no physical call or old-log rewrite."""
    origin=Path(origin).resolve();p=read(origin/'protocol.json');s=read(origin/'collections/summary.json')
    if len(s['rows'])!=27 or s['truncated_queries']!=93:raise ValueError('complete27/all93 prior collection required')
    for kind in ('source','test'):
        for name,h in p[kind+'_sha256'].items():
            if file_sha(origin/(kind+'_snapshot')/name)!=h:raise ValueError('prior frozen snapshot drift')
    for row in s['rows']:
        if row['status']!='controller_quiescent'or not row['source_inputs_tests_unchanged']or not all(row['comparison'].values()):
            raise ValueError('prior collection did not reproduce exactly')
        idx=origin/row['query_index_file']
        if file_sha(idx)!=row['query_index_sha256']:raise ValueError('prior query index drift')
        for q in read(idx):
            if file_sha(origin/q['file'])!=q['sha256']:raise ValueError('prior query artifact drift')
    return {'schema':'round7_collection_reuse_v1','origin':str(origin),
        'new_physical_calls':0,'original_physical_calls':27,'truncated_queries':93,
        'measurement_revision':'Shadow recovery/manifest repair only. Prior collector remains under its own source snapshot; policy/probe unchanged.',
        'files_sha256':{str(f.resolve()):file_sha(f)for f in sorted(origin.rglob('*'))if f.is_file()}}


def verify_collection_reuse(output):
    p=Path(output)/'collection_reuse.json'
    if p.exists():
        for name,h in read(p)['files_sha256'].items():
            if file_sha(name)!=h:raise ValueError('reused collection drift: '+name)


def prepare(output,reuse_collection=None):
    cpu,wall=process_time(),perf_counter();output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    old_protocol=read(OLD/'protocol.json');requests=validate_old_artifacts()
    if len(requests)!=27:raise ValueError('all27 new cases required')
    names=set(old_protocol['source_sha256'])|{'same_zone_query_probe.py','same_zone_query_coverage.py',
        'run_same_zone_query_coverage.py','same_zone_labels.py'}
    source={name:file_sha(SOURCE/name)for name in sorted(names)}
    for name,h in old_protocol['source_sha256'].items():
        if source[name]!=h:raise ValueError('round6 source changed: '+name)
    tests={p.name:file_sha(p)for p in sorted((ROOT/'tests').glob('test_ics_circulation_v3_*.py'))}
    paths=[OLD/'protocol.json',OLD/'saved_tapes.json',OLD/'full/summary.json',OLD/'full/manifest.json']
    paths += [OLD/r['file']for r in requests]
    paths += [Path(p)for p in old_protocol['input_sha256']]
    inputs={str(p.resolve()):file_sha(p)for p in paths}
    for name in ('source_snapshot','test_snapshot'):(output/name).mkdir()
    for name in source:(output/'source_snapshot'/name).write_bytes((SOURCE/name).read_bytes())
    for name in tests:(output/'test_snapshot'/name).write_bytes((ROOT/'tests'/name).read_bytes())
    reuse=import_collection(reuse_collection)if reuse_collection is not None else None
    if reuse is not None:write(output/'collection_reuse.json',reuse)
    protocol={'schema':'ics_round7_query_coverage_protocol_v1','source_sha256':source,'test_sha256':tests,
        'input_sha256':inputs,'requests':requests,'expected_truncated_queries':93,
        'collection_workers':3,'probe_workers':3,'case_budget':asdict(CASE_BUDGET),'tail_cap':TAIL_CAP,
        'parallel_resource_revision':'Before coverage collection: root approved labels6 + coverage3, total9, based on 16 physical/22 logical cores and measured label pilot memory; not shadow outcome selection.',
        'variants':VARIANTS,'selection':'all truncated plus first successful control per(scene,callsite,source,destination,K,protected), order case_id/time/query_ordinal',
        'pilot':'first truncated query per scene plus matched control; not performance selection; formal repeats all',
        'action_scope':'shadow only, fixed original K; no candidate execution or deployment changes',
        'cache_scope':'regional fresh private cold-equivalent; fullgraph dedicated-worker cold legacy cache restored afterward',
        'reused_collection_root':None if reuse is None else reuse['origin'],
        'prepare_cpu_seconds':process_time()-cpu,'prepare_wall_seconds':perf_counter()-wall}
    if reuse is None:protocol.pop('reused_collection_root')
    write(output/'protocol.json',protocol)
    manifest(output,'preparation_manifest.json',[f for f in output.rglob('*')if f.is_file()])
    return protocol


def collect_case(output,request):
    cpu,wall=process_time(),perf_counter();output=Path(output);name=request['case_id']
    folder=output/'collections'/name;folder.mkdir(parents=True,exist_ok=False)
    sink=[];outcome=None;physical=False;failure=None;indices=[];checks={}
    try:
        verify(output)
        scene=exact_original_scene(request['scene'])
        tape=read(OLD/'saved_tapes.json')[request['scene']][request['tape_id']]
        future=tuple(Bag(**x)for x in tape['future_engine_only'])
        base=build_engine(scene.initial,scene.forecasts,future,SPEC);enable_replay_cache(base)
        engine=CursorSimulation.from_base_checkpoint(base.checkpoint(),contract=base.control_contract)
        install_supply_policy(engine,'same_zone32plus32')
        owner=bind_accounting(engine,CASE_BUDGET);install_query_probe(engine,sink)
        physical=True
        outcome=run_cycle(engine,{**engine.state.bags,**{b.bag_id:b for b in future}},
            minimum_observation_at=scene.horizon,budget=CASE_BUDGET,tail_cap=TAIL_CAP,
            owner=owner,retain_physical_ticks=True)
        checks=compare_collection(read(OLD/request['file']),outcome)
        checks['query_count_matches_searches']=len(sink)==len(outcome['searches'])
        checks['query_identity_order_matches']=all(
            q['time']==r['time']and q['bag_id']==r['bag_id']and q['tray_id']==r['tray_id']
            and q.get('raw_candidate_count')==r['candidate_count']
            and q['last_expansions']==r['work']and q['last_search_status']==r['status']
            for q,r in zip(sink,outcome['searches']))
        # Raw pool can be filtered by original next_edge validation. The loaded
        # callback state/identity must bind and its options must be a subset.
        loaded=[q for q in sink if q['method']=='generate']
        checks['loaded_opportunity_count']=len(loaded)==len(outcome['opportunities'])
        checks['loaded_input_and_authorized_subset']=all(
            q['time']==o['time']and q['version']==o['version']and q['bag_id']==o['bag_id']
            and q['tray_id']==o['tray_id']and q['snapshot'].trays[q['tray_id']].node==o['node']
            and all(any(exact_json_value(p,asdict(c))for c in q['options'])for p in o['candidates'])
            for q,o in zip(loaded,outcome['opportunities']))
    except Exception as error:
        failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    # Retain every completed/partial query, also if comparison or physics failed.
    indices,persistence_failures=persist_collection(folder,output,request,sink,outcome)
    unchanged=True;immutability_error=None
    try:verify(output)
    except Exception as error:unchanged=False;immutability_error=str(error)
    row={'case_id':name,'scene':request['scene'],'tape_id':request['tape_id'],
        'status':'execution_failure'if failure else 'persistence_failure'if persistence_failures else
            'immutability_failure'if not unchanged else outcome['status']if all(checks.values())else'replication_mismatch',
        'failure':failure,'comparison':checks,'physical_call_started':physical,
        'physical_result_status':None if outcome is None else outcome['status'],
        'persistence_failures':persistence_failures,'observed_query_count':len(sink),
        'query_count':len(indices),'truncated_count':sum(q.get('last_search_status')=='expansion_budget_exhausted'for q in indices),
        'query_index_file':str((folder/'queries.json').relative_to(output)),
        'query_index_sha256':file_sha(folder/'queries.json')if(folder/'queries.json').exists()else None,
        'cycle_cpu_seconds_nested':None if outcome is None else outcome['cpu_seconds'],
        'invocation_cpu_seconds':process_time()-cpu,'invocation_wall_seconds':perf_counter()-wall,
        'memory':memory_snapshot(),'source_inputs_tests_unchanged':unchanged,'immutability_error':immutability_error,
        'resource_scope':'Entire worker through persistence and final verification; final small result serialization excluded, cycle CPU nested.'}
    try:write(folder/'result.json',row)
    except Exception as error:
        row['status']='result_persistence_failure';row['result_persistence_error']=str(error)
        # Return the measured row to parent summary even if the result file failed.
    return row


def collect(output,workers):
    cpu,wall=process_time(),perf_counter();protocol=verify(output);output=Path(output)
    if protocol.get('reused_collection_root'):raise ValueError('reused collection has zero new physical invocations')
    (output/'collections').mkdir(exist_ok=False);rows=[]
    with ProcessPoolExecutor(max_workers=workers)as pool:
        jobs={pool.submit(collect_case,str(output),r):r for r in protocol['requests']}
        for job in as_completed(jobs):
            request=jobs[job]
            try:row=job.result()
            except Exception as error:row={'case_id':request['case_id'],'status':'worker_failure',
                'failure':{'type':type(error).__name__,'message':str(error)},'invocation_cpu_seconds':None,
                'physical_call_started':None}
            rows.append(row);print(json.dumps({'collected':len(rows),'case':row['case_id'],'status':row['status']},ensure_ascii=False),flush=True)
    summary={'rows':sorted(rows,key=lambda r:r['case_id']),'planned_cases':27,
        'worker_cpu_seconds_recorded':sum(r.get('invocation_cpu_seconds')or 0 for r in rows),
        'unknown_worker_resources':sum(r.get('invocation_cpu_seconds')is None for r in rows),
        'parent_cpu_seconds':process_time()-cpu,'wall_makespan_seconds':perf_counter()-wall,
        'physical_calls_recorded':sum(r.get('physical_call_started')is True for r in rows),
        'truncated_queries':sum(r.get('truncated_count',0)for r in rows),
        'no_physical_reuse_from_round6_or_nominal_label_collection':True}
    write(output/'collections/summary.json',summary);verify(output)
    manifest(output,'collection_manifest.json',[p for p in(output/'collections').rglob('*')if p.is_file()])
    if any(r['status']!='controller_quiescent'for r in rows):raise SystemExit(1)
    if summary['truncated_queries']!=protocol['expected_truncated_queries']:raise ValueError('all93 truncated denominator differs')


def select(output):
    cpu,wall=process_time(),perf_counter();verify(output);verify_collection_reuse(output);output=Path(output)
    origin=collection_root(output);summary=read(origin/'collections/summary.json');queries=[]
    if len(summary['rows'])!=27 or any(r['status']!='controller_quiescent'or not r['source_inputs_tests_unchanged']for r in summary['rows']):
        raise ValueError('complete exact27 collection required')
    for row in summary['rows']:
        path=origin/row['query_index_file']
        if file_sha(path)!=row['query_index_sha256']:raise ValueError('query index drift')
        queries.extend(read(path))
    selected=select_requests(queries)
    if selected['truncated_count']!=93:raise ValueError('all93 truncated required')
    selected.update(cpu_seconds=process_time()-cpu,wall_seconds=perf_counter()-wall,
        selection_before_shadow_outcomes=True)
    write(output/'selection.json',selected)
    manifest(output,'selection_manifest.json',[output/'selection.json',output/'protocol.json'])
    return selected


def probe_worker(output,stage,request):
    cpu,wall=process_time(),perf_counter();output=Path(output)
    failure=None;result=None
    try:
        verify(output);verify_manifest(output/'selection_manifest.json')
        query_path=collection_root(output)/request['file']
        if file_sha(query_path)!=request['sha256']:raise ValueError('captured query changed')
        # Only own newly generated query artifacts, checked against frozen index.
        with gzip.open(query_path,'rb')as stream:query=pickle.load(stream)
        result=probe_query(query)
    except Exception as error:failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    name=request['case_id']+'__q'+str(request['query_ordinal']).zfill(5)+'.json'
    target=output/stage/name
    payload={'request':request,'status':'probe_failure'if failure else result['status'],
        'failure':failure,'result':result,'invocation_cpu_seconds':process_time()-cpu,
        'invocation_wall_seconds':perf_counter()-wall,'memory':memory_snapshot(),
        'resource_scope':'Worker verification/read/shadow interval; per-variant CPU is nested; final output serialization excluded.'}
    try:write(target,payload)
    except Exception as error:
        payload['status']='probe_persistence_failure'
        payload['persistence_failure']={'type':type(error).__name__,'message':str(error)}
        recovery=target.with_suffix('.recovery.json')
        try:
            # Plain direct fallback does not share the failed writer entrance.
            with recovery.open('x',encoding='utf8')as stream:json.dump(payload,stream,ensure_ascii=False,indent=2,allow_nan=False)
            target=recovery
        except Exception as recovery_error:
            payload['recovery_failure']={'type':type(recovery_error).__name__,'message':str(recovery_error)}
            return {'query_id':request['query_id'],'status':'probe_persistence_failure',
                'partial_evidence':payload,'invocation_cpu_seconds':process_time()-cpu,
                'invocation_wall_seconds':perf_counter()-wall,'file':None,'sha256':None}
    return {'query_id':request['query_id'],'status':payload['status'],'file':str(target.relative_to(output)),
        'sha256':file_sha(target),'invocation_cpu_seconds':payload['invocation_cpu_seconds'],
        'invocation_wall_seconds':payload['invocation_wall_seconds']}


def probe(output,stage,workers):
    cpu,wall=process_time(),perf_counter();verify(output);verify_collection_reuse(output);output=Path(output)
    verify_manifest(output/'selection_manifest.json')
    selection=read(output/'selection.json');requests=selection[stage]
    (output/stage).mkdir(exist_ok=False);rows=[]
    with ProcessPoolExecutor(max_workers=workers)as pool:
        jobs={pool.submit(probe_worker,str(output),stage,r):r for r in requests}
        for job in as_completed(jobs):
            request=jobs[job]
            try:row=job.result()
            except Exception as error:row={'query_id':request['query_id'],'status':'worker_failure',
                'failure':{'type':type(error).__name__,'message':str(error)},'invocation_cpu_seconds':None}
            rows.append(row)
    summary={'planned_requests':len(requests),'rows':rows,
        'worker_cpu_seconds_recorded':sum(r.get('invocation_cpu_seconds')or 0 for r in rows),
        'unknown_worker_resources':sum(r.get('invocation_cpu_seconds')is None for r in rows),
        'parent_cpu_seconds':process_time()-cpu,'wall_makespan_seconds':perf_counter()-wall,
        'new_simulation_branches':0,'memo_reuse':0,'pilot_reused_by_formal':False}
    write(output/stage/'summary.json',summary);verify(output);verify_collection_reuse(output)
    manifest(output,stage+'_manifest.json',[p for p in(output/stage).rglob('*')if p.is_file()]+[output/'selection.json'])
    if any(r['status']!='completed_shadow_probe'for r in rows):raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT)
    parser.add_argument('--reuse-collection',type=Path)
    parser.add_argument('--stage',choices=('prepare','collect','select','pilot','formal'),required=True)
    parser.add_argument('--workers',type=int,default=3);args=parser.parse_args()
    if not 1<=args.workers<=3:raise ValueError('one to three dedicated workers only')
    if args.stage=='prepare':prepare(args.output,args.reuse_collection)
    elif args.stage=='collect':collect(args.output,args.workers)
    elif args.stage=='select':select(args.output)
    else:probe(args.output,args.stage,args.workers)
