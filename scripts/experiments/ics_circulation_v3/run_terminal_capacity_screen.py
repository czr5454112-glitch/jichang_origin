"""Frozen corpus screen audit and independent opt-in 3-pilot/27 deployment."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict
from pathlib import Path
from time import process_time,perf_counter
import argparse,gzip,json,pickle,traceback

from .run_same_zone_query_coverage import (ROOT,SOURCE,BASE,OLD,read,write,manifest,verify_manifest,
    validate_old_artifacts,verify_collection_reuse,without_ms,exact_json_value,write_gzip)
from .run_same_zone_supply import exact_original_scene
from .same_zone_experiment import CASE_BUDGET,TAIL_CAP,install_supply_policy
from .same_zone_labels import run_cycle
from .phase4_control import build_engine
from .network_role_labels import SPEC,bind_accounting
from .network_full_cycle import compare_old_result
from .model import Bag
from .role_coverage import CursorSimulation
from .routing_cache_contract import enable_replay_cache
from .phase4_network_workloads import file_sha
from .experiment_resources import memory_snapshot
from .terminal_capacity_screen import install_terminal_screen,terminal_capacity_certificate

COLLECTION=BASE/'phase4_w3_same_zone_query_coverage_20261010'
SHADOW=BASE/'phase4_w3_same_zone_query_shadow_20261010'
DEFAULT=BASE/'phase4_w3_terminal_capacity_screen_20261010'


def verify(output):
    output=Path(output);verify_manifest(output/'preparation_manifest.json');p=read(output/'protocol.json')
    for n,h in p['source_sha256'].items():
        if file_sha(SOURCE/n)!=h:raise ValueError('frozen source drift '+n)
    for n,h in p['test_sha256'].items():
        if file_sha(ROOT/'tests'/n)!=h:raise ValueError('frozen test drift '+n)
    for n,h in p['input_sha256'].items():
        if file_sha(n)!=h:raise ValueError('frozen input drift '+n)
    return p


def prepare(output):
    cpu,wall=process_time(),perf_counter();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    requests=validate_old_artifacts();verify_collection_reuse(SHADOW)
    names=set(read(SHADOW/'protocol.json')['source_sha256'])|{'terminal_capacity_screen.py','run_terminal_capacity_screen.py'}
    sources={n:file_sha(SOURCE/n)for n in sorted(names)}
    tests={p.name:file_sha(p)for p in sorted((ROOT/'tests').glob('test_ics_circulation_v3_*.py'))}
    inputs=dict(read(SHADOW/'protocol.json')['input_sha256'])
    inputs.update({str(p.resolve()):file_sha(p)for p in (OLD/'protocol.json',OLD/'saved_tapes.json',OLD/'full/manifest.json',
        OLD/'full/summary.json',COLLECTION/'protocol.json',COLLECTION/'collections/summary.json',SHADOW/'collection_reuse.json',SHADOW/'preparation_manifest.json')}
    )
    inputs[str((SHADOW/'protocol.json').resolve())]=file_sha(SHADOW/'protocol.json')
    cpp=ROOT/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
    if file_sha(cpp)!='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951':
        raise ValueError('original C++ binding differs')
    inputs[str(cpp.resolve())]=file_sha(cpp)
    for name,h in inputs.items():
        if file_sha(name)!=h:raise ValueError('ancestral input chain changed '+name)
    for kind,values in [('source',sources),('test',tests)]:
        (output/(kind+'_snapshot')).mkdir()
        for n in values:(output/(kind+'_snapshot')/n).write_bytes(((SOURCE if kind=='source'else ROOT/'tests')/n).read_bytes())
    p={'schema':'ics_round7_terminal_screen_protocol_v1','source_sha256':sources,'test_sha256':tests,'input_sha256':inputs,
        'requests':requests,'pilot':[r for r in requests if r['tape_id']=='nominal'],'workers':3,
        'screen_max_records':200000,'case_budget':asdict(CASE_BUDGET),'tail_cap':TAIL_CAP,
        'screen_scope':'Original Snapshot/H whole-witness node terminal necessary condition; optional wrapper, no default change.',
        'deployment_scope':'3 nominal pilot then all27 independent physical cases; full repeats pilot, no reuse.',
        'equivalence':'Original query identity and complete raw ordered candidate sequence; physical trajectories, protected outcomes, task ledger, actual actions and drain all exact. Search status/work and private cache may differ and are separately recorded.',
        'cost_axes':'Call count stays one per query; search work plus separately recorded screen record work and CPU. Record-work excludes sorting comparisons; total CPU includes them.',
        'prepare_cpu_seconds':process_time()-cpu,'prepare_wall_seconds':perf_counter()-wall}
    write(output/'protocol.json',p);manifest(output,'preparation_manifest.json',[x for x in output.rglob('*')if x.is_file()])


def read_query(row):
    p=COLLECTION/row['file']
    if file_sha(p)!=row['sha256']:raise ValueError('saved query SHA differs')
    with gzip.open(p,'rb')as f:return pickle.load(f)


def indices(case_id):
    old=next(r for r in read(COLLECTION/'collections/summary.json')['rows']if r['case_id']==case_id)
    p=COLLECTION/old['query_index_file']
    if file_sha(p)!=old['query_index_sha256']:raise ValueError('query index changed')
    return read(p)


def corpus(output):
    cpu,wall=process_time(),perf_counter();output=Path(output);p=verify(output);verify_collection_reuse(SHADOW)
    rows=[]
    for case in p['requests']:
        for index in indices(case['case_id']):
            q=read_query(index);c=terminal_capacity_certificate(q['snapshot'],q['tray_id'],q['destination'],
                q['generator_settings']['horizon'],max_records=p['screen_max_records'])
            rows.append({'query_id':index['query_id'],'case_id':case['case_id'],
                'original_status':q['last_search_status'],'original_work':q['last_expansions'],
                'original_raw_count':len(q['options']),'certificate':c,
                'observed_false_positive':c['certified']and bool(q['options'])})
    verify(output);verify_collection_reuse(SHADOW)
    result={'rows':rows,'queries':len(rows),'certified_count':sum(r['certificate']['certified']for r in rows),
        'false_positives_against_saved_raw':sum(r['observed_false_positive']for r in rows),
        'original_search_work':sum(r['original_work']for r in rows),
        'certified_query_original_search_work':sum(r['original_work']for r in rows if r['certificate']['certified']),
        'screen_work':sum(r['certificate']['screen_work']for r in rows),'new_generate_calls':0,'new_physical_calls':0,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Read/SHA/decode and certificate function across all2467 saved queries; final serialization excluded.',
        'completeness_limit':'Observed no false positive alone is not proof; the interval-containment argument and validator tests establish the sufficient condition.'}
    write(output/'corpus.json',result);manifest(output,'corpus_manifest.json',[output/'corpus.json'])
    if len(rows)!=2467 or result['false_positives_against_saved_raw']:raise ValueError('corpus denominator or soundness failed')


def compare_physical(old,new):
    checks={'final_result':compare_old_result(old['result'],new['result'])['equal'],
        'original_endpoint_result':compare_old_result(old['original_endpoint']['result'],new['original_endpoint']['result'])['equal']}
    # Observational diagnostics/search counters and cache are explicitly outside
    # physical equality; unchanged candidate sequences are checked separately.
    for field in ('status','stopped_at','initial_state','initial_cursor','opportunities',
        'actual_slow_trigger_times','physical_tick_trace','event_trace_suffix','milestones','last_cycle_state','evaluation_ledger'):
        checks[field]=exact_json_value(without_ms(old[field]),without_ms(new[field]))
    checks['selector_history_suffix']=exact_json_value(without_ms(old['selector_history_suffix']),without_ms(new['selector_history_suffix']))
    # The slow history includes explicit search-status diagnostics. Screening
    # intentionally changes those; compare every proposal/trigger separately.
    checks['slow_triggers_and_proposals']=exact_json_value(
        [{k:v for k,v in r.items()if k!='diagnostics'}for r in old['slow_history_suffix']],
        [{k:v for k,v in r.items()if k!='diagnostics'}for r in new['slow_history_suffix']])
    return checks


def deploy_case(output,stage,request):
    cpu,wall=process_time(),perf_counter();output=Path(output);name=request['case_id'];target=output/stage/(name+'.json.gz')
    outcome=None;physical=False;accounting=None;failure=None;checks={};query_checks=[];payload={};recovery=None;raw_complete=False
    try:
        p=verify(output);scene=exact_original_scene(request['scene']);saved=read(OLD/'saved_tapes.json')[request['scene']][request['tape_id']]
        future=tuple(Bag(**b)for b in saved['future_engine_only'])
        base=build_engine(scene.initial,scene.forecasts,future,SPEC);enable_replay_cache(base)
        engine=CursorSimulation.from_base_checkpoint(base.checkpoint(),contract=base.control_contract)
        install_supply_policy(engine,'same_zone32plus32');accounting=install_terminal_screen(engine,max_records=p['screen_max_records'])
        owner=bind_accounting(engine,CASE_BUDGET);physical=True
        outcome=run_cycle(engine,{**engine.state.bags,**{b.bag_id:b for b in future}},minimum_observation_at=scene.horizon,
            budget=CASE_BUDGET,tail_cap=TAIL_CAP,owner=owner,retain_physical_ticks=True)
        if file_sha(OLD/request['file'])!=request['sha256']:raise ValueError('original round6 raw changed')
        old=read(OLD/request['file']);checks=compare_physical(old,outcome);original_indices=indices(name)
        checks['same_query_count']=len(accounting.rows)==len(original_indices)==len(outcome['searches'])
        for actual,index in zip(accounting.rows,original_indices):
            q=read_query(index)
            exact=all(actual[k]==q[k]for k in ('time','version','bag_id','tray_id','destination','requested_k','public_snapshot_sha256'))and actual['options']==q['options']
            query_checks.append({'query_id':index['query_id'],'exact_input_identity_and_raw_pool':exact,
                'certified':actual['certificate']['certified'],'old_work':q['last_expansions'],
                'old_status':q['last_search_status'],'new_work':actual['search_work'],'new_status':actual['search_status']})
        checks['all_ordered_query_raw_pools_exact']=all(r['exact_input_identity_and_raw_pool']for r in query_checks)
        payload={'case':request,'outcome':outcome,'screen_accounting':asdict(accounting),
            'comparison':checks,'query_checks':query_checks,'cache_after_equal':exact_json_value(old['cache_after'],outcome['cache_after']),
            'cache_scope':'Skipping provably empty searches may omit cache warming/LRU events. Logical cold-equivalent budgets and actual candidate sequence, not cache bytes, define equivalence.'}
        write_gzip(target,payload);raw_complete=True;verify(output)
    except Exception as error:
        failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
        recovery=target.with_suffix('.recovery.json')
        try:write(recovery,{'case':request,'outcome':outcome,'screen_accounting':None if accounting is None else asdict(accounting),
            'comparison':checks,'query_checks':query_checks,'failure':failure})
        except Exception as recovery_error:failure['recovery_error']=str(recovery_error)
    status='invocation_failure'if failure else outcome['status']if all(checks.values())else'equivalence_mismatch'
    row={'case_id':name,'scene':request['scene'],'tape_id':request['tape_id'],'status':status,'failure':failure,
        'actual_physical_call':physical,'physical_result_status':None if outcome is None else outcome['status'],
        'file':str(target.relative_to(output))if target.exists()else None,'sha256':file_sha(target)if target.exists()else None,
        'raw_complete':raw_complete,'recovery_file':str(recovery.relative_to(output))if recovery is not None and recovery.exists()else None,
        'recovery_sha256':file_sha(recovery)if recovery is not None and recovery.exists()else None,
        'comparison':checks,'cache_after_equal':payload.get('cache_after_equal'),
        'search_calls':0 if outcome is None else outcome['search_calls'],'search_work':0 if outcome is None else outcome['search_work'],
        'screen_work':None if accounting is None else accounting.screen_work,
        'screen_cpu_seconds_nested':None if accounting is None else accounting.screen_cpu_seconds,
        'observation_cpu_seconds_nested':None if accounting is None else accounting.observation_cpu_seconds,
        'certified_queries':0 if accounting is None else sum(r['certificate']['certified']for r in accounting.rows),
        'invocation_cpu_seconds':process_time()-cpu,'invocation_wall_seconds':perf_counter()-wall,'memory':memory_snapshot()}
    try:write(output/stage/(name+'.result.json'),row)
    except Exception as error:row['status']='result_persistence_failure';row['persistence_error']=str(error)
    return row


def deploy(output,stage):
    cpu,wall=process_time(),perf_counter();output=Path(output);p=verify(output);verify_collection_reuse(SHADOW)
    verify_manifest(output/'corpus_manifest.json');c=read(output/'corpus.json')
    if c['queries']!=2467 or c['false_positives_against_saved_raw']:raise ValueError('certified corpus check required')
    if stage=='formal':
        pilot=read(output/'pilot/summary.json')
        verify_manifest(output/'pilot_manifest.json')
        if not pilot['all_exact']or not pilot['source_inputs_tests_unchanged']:raise ValueError('pilot equivalence required')
    requests=p['pilot']if stage=='pilot'else p['requests'];(output/stage).mkdir(exist_ok=False);rows=[]
    with ProcessPoolExecutor(max_workers=3)as pool:
        jobs={pool.submit(deploy_case,str(output),stage,r):r for r in requests}
        for f in as_completed(jobs):
            try:row=f.result()
            except Exception as error:row={'case_id':jobs[f]['case_id'],'status':'worker_failure','failure':str(error),
                'invocation_cpu_seconds':None,'actual_physical_call':None}
            rows.append(row);print(json.dumps({'completed':len(rows),'case':row['case_id'],'status':row['status']}),flush=True)
    unchanged=True;immutable_error=None
    try:verify(output);verify_collection_reuse(SHADOW)
    except Exception as error:unchanged=False;immutable_error=str(error)
    summary={'rows':sorted(rows,key=lambda r:r['case_id']),'planned_requests':len(requests),
        'case_invocation_cpu_seconds_recorded':sum(r.get('invocation_cpu_seconds')or 0 for r in rows),
        'unknown_resource_cases':sum(r.get('invocation_cpu_seconds')is None for r in rows),
        'actual_physical_calls_recorded':sum(r.get('actual_physical_call')is True for r in rows),
        'parent_cpu_seconds':process_time()-cpu,'wall_makespan_seconds':perf_counter()-wall,
        'all_exact':all(r['status']=='controller_quiescent'and all(r['comparison'].values())for r in rows),
        'pilot_reused_by_formal':False,'source_inputs_tests_unchanged':unchanged,'immutable_error':immutable_error}
    write(output/stage/'summary.json',summary);manifest(output,stage+'_manifest.json',[f for f in(output/stage).rglob('*')if f.is_file()])
    if not summary['all_exact']or not unchanged:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT)
    parser.add_argument('--stage',choices=('prepare','corpus','pilot','formal'),required=True);a=parser.parse_args()
    if a.stage=='prepare':prepare(a.output)
    elif a.stage=='corpus':corpus(a.output)
    else:deploy(a.output,a.stage)
