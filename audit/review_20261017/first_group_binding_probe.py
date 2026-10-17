"""One cold saved-public model group; no live origin or native execution."""
from __future__ import annotations

import __future__
import argparse
import copyreg
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=Path(__file__).resolve().parent/'first_group_binding_004'
TARGET=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/compatible_initial_native_20261017_002/mechanism/incumbent.raw.json.gz'
ADMISSION='g31-saved-public-one-cold-model-group-20261017'
LIMIT=60.
sys.path[:0]=[str(ROOT),str(ROOT/'src')]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')


def expected_pins(plan):
    return {**plan['source_sha256'],**plan['external_sha256'],
        plan['target']['path']:plan['target']['sha256'],plan['public']['path']:plan['public']['sha256']}


def pins(plan):
    return {name:digest(ROOT/name) for name in expected_pins(plan)}


def prepare():
    from scripts.experiments.g31_ics_circulation import initial_owner_route_image as image
    package='scripts.experiments.g31_ics_circulation.'
    sources=image.source_closure(ROOT,tuple(package+name for name in (
        'live_obligation_owned_initial_provider','bounded_windows_job','diagnose_bound_source_proof_bind')))
    sources[Path(__file__).relative_to(ROOT).as_posix()]=Path(__file__).read_bytes()
    raw=json.loads(gzip.decompress(TARGET.read_bytes()))
    collection=raw['initial_owners']['A']['collection']
    OUTPUT.mkdir(exist_ok=False)
    write(OUTPUT/'A.public.json',collection['public'])
    plan={'schema':'g31.review20261017.first_group_binding_probe.v1','status':'preregistered_unexecuted',
        'hard_worker_tree_seconds':LIMIT,'maximum_attempts':1,'model_groups':1,'prefix_index':0,
        'cold_bind_requests':1,'setup_warm_proof_uses':1,'live_origin_construction':False,
        'native_commands_permitted':False,'offline_saved_public_only':True,
        'original_dynamic_model_guards_retained':True,'no_request_rebind_or_reactivation':True,
        'prior_failed_online_group_preserved':True,'not_online_or_speed_evidence':True,
        'prior_attempt':'first_group_binding_001: startup str-to-hash TypeError before any bind or model call; retained',
        'second_attempt':'first_group_binding_002: one saved group exposed Projection namespace drift; retained',
        'third_attempt':'first_group_binding_003: proved exactly three new __slotnames__ empty lists; retained',
        'revision_purpose':'Run production three-class canonical copy metadata preparation before binding, then the same single group.',
        'prior_runner_sha256':digest(Path(__file__).resolve().parent/'first_group_binding_001/first_group_binding_probe.py'),
        'target':{'path':str(TARGET),'sha256':digest(TARGET)},
        'public':{'path':str(OUTPUT/'A.public.json'),'sha256':digest(OUTPUT/'A.public.json'),
            'original_collection_public_sha256':collection['public_sha256']},
        'source_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in sorted(sources.items())},
        'external_sha256':{str(Path(path).resolve()):digest(path) for path in (sys.executable,__future__.__file__,copyreg.__file__)},
        'worker_scope':'process creation/import/pins/cold bind/setup proof/guarded supplied context/one original model group/close/export',
        'execution_command':[sys.executable,str(Path(__file__).resolve()),'execute']}
    write(OUTPUT/'plan.json',plan)
    print(json.dumps({'plan':str(OUTPUT/'plan.json'),'sha256':digest(OUTPUT/'plan.json'),'sources':len(sources)}))


def worker(expected):
    if sys.stdin.readline()!=ADMISSION+'\n':raise ValueError('missing_job_admission')
    started=time.perf_counter_ns();plan=None;request=None
    report={'status':'unknown_worker_failure','offline_saved_public_only':True,'native_authority':False,
        'live_origin_constructed':False,'native_commands_sent':0,'model_group_attempts':0}
    try:
        if digest(OUTPUT/'plan.json')!=expected:raise ValueError('plan_changed')
        plan=json.loads((OUTPUT/'plan.json').read_bytes())
        report['entry_pins']=pins(plan)
        if report['entry_pins']!=expected_pins(plan):raise ValueError('entry_source_or_input_changed')
        from scripts.experiments.g31_ics_circulation import live_obligation_owned_initial_provider as provider
        from scripts.experiments.g31_ics_circulation import diagnose_bound_source_proof_bind as diagnostic
        diagnostic.archive.no_execution_extensions(pure=False)
        report['loaded_entry']=diagnostic.archive.loaded_sources(plan['source_sha256'])
        public=json.loads((OUTPUT/'A.public.json').read_bytes())
        if hashlib.sha256(provider.origin.history.payload_encoding(public).encode()).hexdigest()!=plan['public']['original_collection_public_sha256']:
            raise ValueError('original_public_digest_mismatch')
        write(OUTPUT/'bind_started.json',{'elapsed_worker_ns':time.perf_counter_ns()-started})
        report['copy_metadata_preparation']=provider._prepare_copy_metadata()
        request=provider.binding.bind_request()
        report['source_proof']=provider.source_proof(request)
        context=provider.origin.supplied.initial_context(**public)
        if type(context) is not provider.origin.supplied.SuppliedContext:raise ValueError('fresh_supplied_context_required')
        group=provider.domain.partition(provider.future.core.lazy.original.physics.previous.actions())['groups'][0]
        write(OUTPUT/'group_started.json',{'elapsed_worker_ns':time.perf_counter_ns()-started})
        report['model_group_attempts']=1
        report['group']=provider.execution.execute_bound_group(request,group,context)
        report['status']='saved_group_returned_with_binding_failure' if report['group'].get('binding_error') else 'saved_group_returned'
    except BaseException:
        report['error']=traceback.format_exc()
    finally:
        if request is not None:
            try:
                changes=[]
                for row in request._proof._dependencies._records:
                    if row[0]!='namespace':continue
                    _,namespace,keys,values,label=row
                    if tuple(namespace)==keys and all(namespace[key] is value for key,value in zip(keys,values,strict=True)):continue
                    added=[key for key in namespace if key not in keys]
                    changes.append({'label':label,'before_keys':keys,'after_keys':list(namespace),
                        'added':added,'removed':[key for key in keys if key not in namespace],
                        'rebound':[key for key,value in zip(keys,values,strict=True) if key in namespace and namespace[key] is not value],
                        'slotnames':namespace.get('__slotnames__') if type(namespace.get('__slotnames__')) is list else None,
                        'slotnames_type':type(namespace.get('__slotnames__')).__name__})
                report['diagnostic_namespace_changes']=changes
                report['diagnostic_private_binding_state']=request._proof.description()
                report['private_state_is_not_authority']=True
            except BaseException:report['private_state_error']=traceback.format_exc()
            try:
                request.close();report['close_completed']=True
            except BaseException:
                report['close_completed']=False;report['close_error']=traceback.format_exc()
        if plan is not None:
            try:
                report['exit_pins']=pins(plan)
                if report['exit_pins']!=expected_pins(plan):raise ValueError('exit_source_or_input_changed')
            except BaseException:
                report['exit_error']=traceback.format_exc();report['status']='unknown_source_drift'
        report['worker_through_checks_ns']=time.perf_counter_ns()-started
        write(OUTPUT/'report.json',report)
    return 0 if report['status'].startswith('saved_group_returned') else 1


def execute():
    from scripts.experiments.g31_ics_circulation import bounded_windows_job as bounded
    started=time.perf_counter_ns();plan=json.loads((OUTPUT/'plan.json').read_bytes());expected=digest(OUTPUT/'plan.json')
    write(OUTPUT/'attempt_started.json',{'plan_sha256':expected,'hard_worker_tree_seconds':LIMIT,'maximum_attempts':1})
    result={'status':'unknown_parent_failure','plan_sha256':expected}
    try:
        if plan['hard_worker_tree_seconds']!=LIMIT or plan['maximum_attempts']!=1:raise ValueError('budget_changed')
        if pins(plan)!=expected_pins(plan):raise ValueError('parent_source_or_input_changed')
        command=[sys.executable,str(Path(__file__).resolve()),'worker','--expected',expected]
        with (OUTPUT/'worker.stdout.log').open('x',encoding='utf8') as stdout, \
             (OUTPUT/'worker.stderr.log').open('x',encoding='utf8') as stderr:
            result['process']=bounded.run(command,timeout=LIMIT,stdout=stdout,stderr=stderr,admission=ADMISSION,cwd=ROOT)
        result['status']=result['process']['status'];result['command']=command
        if (OUTPUT/'report.json').is_file():
            result['report_sha256']=digest(OUTPUT/'report.json')
            result['worker_status']=json.loads((OUTPUT/'report.json').read_bytes())['status']
        result['exit_pins']=pins(plan)
        if result['exit_pins']!=expected_pins(plan):raise ValueError('parent_exit_source_or_input_changed')
    except BaseException:
        result['error']=traceback.format_exc();result['status']='unknown_parent_failure'
    finally:
        result['parent_through_checks_ns']=time.perf_counter_ns()-started
        write(OUTPUT/'bounded_receipt.json',result)
    print(json.dumps({key:result.get(key) for key in ('status','worker_status','process','report_sha256')}))
    return 0 if str(result.get('worker_status','')).startswith('saved_group_returned') else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','execute','worker'));parser.add_argument('--expected')
    args=parser.parse_args()
    if args.mode=='prepare':prepare();return 0
    if args.mode=='worker':return worker(args.expected)
    return execute()


if __name__=='__main__':raise SystemExit(main())
