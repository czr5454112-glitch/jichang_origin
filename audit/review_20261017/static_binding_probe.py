"""One bounded real dependency bind; no model execution or production wiring."""
from __future__ import annotations

import __future__
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
PACKAGE='scripts.experiments.g31_ics_circulation'
OUTPUT=Path(__file__).resolve().parent/'static_binding_002'
ADMISSION='g31-static-binding-20261017-one-cold-one-warm'
LIMIT=60.
sys.path[:0]=[str(ROOT),str(ROOT/'src')]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')


def pins(plan):
    result={name:digest(ROOT/name) for name in plan['source_sha256']}
    for name in plan['external_sha256']:result[name]=digest(name)
    result[plan['target']['path']]=digest(plan['target']['path'])
    return result


def expected_pins(plan):
    return {**plan['source_sha256'],**plan['external_sha256'],plan['target']['path']:plan['target']['sha256']}


def prepare():
    from scripts.experiments.g31_ics_circulation import initial_owner_route_image as image
    modules=tuple(PACKAGE+'.'+name for name in ('diagnose_bound_source_proof_bind',
        'live_obligation_bound_future_fork_v3','bounded_windows_job'))
    sources=image.source_closure(ROOT,modules)
    sources[Path(__file__).relative_to(ROOT).as_posix()]=Path(__file__).read_bytes()
    target=ROOT/'outputs/si65d1/proofs/00.json'
    OUTPUT.mkdir(exist_ok=False)
    plan={'schema':'g31.review20261017.static_binding_probe.v1','status':'preregistered_unexecuted',
        'experiment':'one real v3 cold bind followed by exactly one warm proof and close',
        'hard_worker_tree_seconds':LIMIT,'maximum_attempts':1,
        'target':{'path':str(target),'sha256':digest(target),'bytes':target.stat().st_size},
        'source_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(sources.items())},
        'external_sha256':{str(Path(path).resolve()):digest(path) for path in (sys.executable,__future__.__file__)},
        'expected_calls':{'original_source_proof_calls':1,'private_proof_calls':1,
            'original_inventory_calls':1,'blocked_model_calls':[]},
        'cold_bind_requests':1,'warm_proof_uses':1,'production_provider_changed':False,
        'model_or_native_execution_permitted':False,'saved_target_only_for_byte_comparison':True,
        'not_a_speed_measurement':True,'profile_monitor_overhead_included':True,
        'execution_command':[sys.executable,str(Path(__file__).resolve()),'execute'],
        'worker_clock_scope':'process creation through exit; import, source checks, bind, warm, close and exports included',
        'parent_preparation_and_receipt_io_separately_reported':True,
        'historical_failures_preserved':['outputs/bdb1','outputs/bdb2','outputs/bdbv3p1',
            'audit/review_20261017/static_binding_001'],
        'startup_revision':'Pure import guard runs before importing the real future; actual extension guard still runs afterward.',
        'prior_attempt_actual_cold_warm_calls':[0,0],
        'prior_runner_archive':'audit/review_20261017/static_binding_001/static_binding_probe.py',
        'prior_runner_sha256':digest(Path(__file__).resolve().parent/'static_binding_001/static_binding_probe.py')}
    write(OUTPUT/'plan.json',plan)
    print(json.dumps({'status':plan['status'],'plan':str(OUTPUT/'plan.json'),
        'sha256':digest(OUTPUT/'plan.json'),'source_count':len(sources)}))


def worker(expected):
    if sys.stdin.readline()!=ADMISSION+'\n':raise ValueError('missing_job_admission')
    started=time.perf_counter_ns();monitor=None;prior=sys.getprofile();plan=None
    report={'status':'unknown_worker_failure','cold_warm_completed':False}
    try:
        if digest(OUTPUT/'plan.json')!=expected:raise ValueError('plan_changed')
        plan=json.loads((OUTPUT/'plan.json').read_bytes())
        report['entry_pins']=pins(plan)
        if report['entry_pins']!=expected_pins(plan):raise ValueError('entry_source_or_target_changed')
        from scripts.experiments.g31_ics_circulation import diagnose_bound_source_proof_bind as original
        original.archive.no_execution_extensions(pure=True)
        from scripts.experiments.g31_ics_circulation import live_obligation_bound_future_fork_v3 as candidate
        from scripts.experiments.g31_ics_circulation import live_obligation_future_later_fork as future
        original.archive.no_execution_extensions(pure=False)
        if prior is not None or not gc.isenabled():raise ValueError('default_profile_and_gc_required')
        report['loaded_entry']=original.archive.loaded_sources(plan['source_sha256'])
        monitor=original.CallMonitor(future)
        write(OUTPUT/'probe_started.json',{'status':'entering_one_cold_bind','plan_sha256':expected,
            'elapsed_worker_ns':time.perf_counter_ns()-started})
        sys.setprofile(monitor)
        try:
            report['probe']=original.probe(candidate.bind_request,OUTPUT,Path(plan['target']['path']).read_bytes())
            report['monitor_active']=sys.getprofile() is monitor
        finally:
            sys.setprofile(prior)
        report['calls']=monitor.summary()
        if report['probe']['status']!='exact_one_bind_one_warm':raise ValueError('binding_not_complete')
        if report['calls']!=plan['expected_calls'] or not report['monitor_active']:
            raise ValueError('exact_structural_call_counts_required')
        report['cold_warm_completed']=True
        report['status']='exact_one_bind_one_warm'
    except BaseException:
        report['error']=traceback.format_exc()
        report['status']='unknown_failed_actual_dependency_binding'
    finally:
        sys.setprofile(prior)
        if monitor is not None:report['calls']=monitor.summary()
        if plan is not None:
            try:
                report['exit_pins']=pins(plan)
                if report['exit_pins']!=expected_pins(plan):raise ValueError('exit_source_or_target_changed')
            except BaseException:
                report['exit_error']=traceback.format_exc();report['status']='unknown_source_drift'
        report['worker_through_checks_ns']=time.perf_counter_ns()-started
        report['native_authority']=False;report['complete_request_100ms_certified']=False
        write(OUTPUT/'report.json',report)
    return 0 if report['status']=='exact_one_bind_one_warm' else 1


def execute():
    from scripts.experiments.g31_ics_circulation import bounded_windows_job as bounded
    started=time.perf_counter_ns();plan=json.loads((OUTPUT/'plan.json').read_bytes())
    expected=digest(OUTPUT/'plan.json')
    write(OUTPUT/'attempt_started.json',{'plan_sha256':expected,'maximum_attempts':1,
        'hard_worker_tree_seconds':LIMIT,'started_parent_ns':started})
    result={'status':'unknown_parent_failure','plan_sha256':expected}
    try:
        if plan['hard_worker_tree_seconds']!=LIMIT or plan['maximum_attempts']!=1:
            raise ValueError('preregistered_budget_changed')
        if pins(plan)!=expected_pins(plan):raise ValueError('parent_entry_source_changed')
        command=[sys.executable,str(Path(__file__).resolve()),'worker','--expected',expected]
        with (OUTPUT/'worker.stdout.log').open('x',encoding='utf8') as stdout, \
             (OUTPUT/'worker.stderr.log').open('x',encoding='utf8') as stderr:
            result['process']=bounded.run(command,timeout=LIMIT,stdout=stdout,stderr=stderr,
                admission=ADMISSION,cwd=ROOT)
        result['command']=command
        result['status']=result['process']['status']
        if (OUTPUT/'report.json').is_file():
            result['report_sha256']=digest(OUTPUT/'report.json')
            result['worker_status']=json.loads((OUTPUT/'report.json').read_bytes())['status']
        result['exit_pins']=pins(plan)
        if result['exit_pins']!=expected_pins(plan):raise ValueError('parent_exit_source_changed')
    except BaseException:
        result['error']=traceback.format_exc();result['status']='unknown_parent_failure'
    finally:
        result['parent_through_checks_ns']=time.perf_counter_ns()-started
        write(OUTPUT/'bounded_receipt.json',result)
    print(json.dumps({key:result.get(key) for key in ('status','worker_status','process','report_sha256')}))
    return 0 if result.get('worker_status')=='exact_one_bind_one_warm' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('prepare','execute','worker'))
    parser.add_argument('--expected')
    args=parser.parse_args()
    if args.mode=='prepare':prepare();return 0
    if args.mode=='worker':return worker(args.expected)
    return execute()


if __name__=='__main__':raise SystemExit(main())
