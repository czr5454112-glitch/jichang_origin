"""Prepare a fixed JSON RPC ABBA experiment; execution requires a later dispatch.

The two arms use the same source image and JSON-decoded inputs. A constructs
the frozen ProtectionRequestContext normally. B retains only compiled code
from startup. The complete caller RPC and startup/close costs remain visible.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import json_prediction_image as codec
from .json_prediction_client import Client

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
INPUT = OUT/'preference_static_context_pair_001/worker/supplied_inputs.json'
INPUT_SHA = '0066994f93a7a25a8aa0a005020bb262909d5c4c5aacbfea5e14bbb2b262b0cb'
CASES = tuple(f'block{b}_load{r}' for b in range(2) for r in range(3))
ORDER = ('reference', 'compiled', 'compiled', 'reference')
SCHEMA = 'g31.json_prediction_RPC_ABBA.v1'
EXPECTED_PURE_TESTS = 80
ENTRY = 'scripts.experiments.g31_ics_circulation.measure_json_prediction_service'
TEST_NAMES = ('tests/test_g31_circulation_json_prediction_worker.py',
              'tests/test_g31_circulation_json_prediction_campaign.py')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value): Path(path).write_bytes(codec.artifact_encode(value))
def read(path): return codec.artifact_decode(Path(path).read_bytes())


def closure():
    files = codec.source_closure(ROOT, (ENTRY, codec.ENTRY, codec.MODEL,
        'scripts.experiments.g31_ics_circulation.run_json_prediction_pure'))
    for name in TEST_NAMES: files[name] = (ROOT/name).read_bytes()
    return dict(sorted(files.items()))


def check_plan(plan):
    if (plan.get('schema') != SCHEMA or plan.get('hard_timeout_seconds') != 120.
            or plan.get('native_calls') != 0 or plan.get('worker_order') != list(ORDER)
            or plan.get('candidate_queries_per_valid_request') != 32 or plan.get('full_baselines') != 24
            or plan.get('requests') != 24 or plan.get('candidate_queries') != 768
            or [r.get('case') for r in plan.get('cases', [])] != list(CASES)
            or plan.get('input', {}).get('sha256') != INPUT_SHA
            or not plan.get('source_sha256') or plan.get('image', {}).get('directory') != 'image'):
        raise ValueError('changed_campaign_scope')
    for row in plan['cases']:
        if row.get('input') != row['case']+'.json': raise ValueError('changed_case_filename')
    for name in plan['source_sha256']: codec.safe_name(name)


def check_pure_gate(pure,receipt):
    path=pure/'tests.xml'
    tests=ET.parse(path).getroot().findall('.//testcase')
    if (receipt.get('status')!='passed' or receipt.get('source_changed')!=[]
            or receipt.get('native_calls')!=0 or receipt.get('tests')!=EXPECTED_PURE_TESTS
            or len(tests)!=EXPECTED_PURE_TESTS or receipt.get('XML_sha256')!=sha(path)
            or any(child.tag in ('failure','error','skipped') for test in tests for child in test)):
        raise ValueError('pure_gate_not_passed')


def prepare(output, pure):
    output.mkdir(parents=True, exist_ok=False)
    pure_receipt = read(pure/'receipt.json')
    check_pure_gate(pure,pure_receipt)
    files = closure()
    for name,digest in pure_receipt['source_sha256'].items():
        if name not in files or codec.sha_bytes(files[name]) != digest:
            raise ValueError('pure_gate_source_changed')
    for name,data in files.items():
        destination=output/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
    if sha(INPUT)!=INPUT_SHA: raise ValueError('changed_fixed_inputs')
    selected=[r for r in json.loads(INPUT.read_bytes()) if r['owner']=='A']
    if [r['case'] for r in selected]!=list(CASES):raise ValueError('changed_six_cases')
    rows=[]
    for row in selected:
        filename=row['case']+'.json';write(output/filename,row['bundle'])
        rows.append({'case':row['case'],'input':filename,'sha256':sha(output/filename)})
    version=codec.build_image(ROOT,output/'image')
    startup={}
    if set(pure_receipt.get('startup_attestations',{}))!={'reference','compiled'}:
        raise ValueError('missing_functional_startup_gate')
    for mode,ref in pure_receipt['startup_attestations'].items():
        if sha(ref['path'])!=ref['sha256']:raise ValueError('changed_startup_gate')
        attestation=read(ref['path'])
        if (attestation.get('schema')!='g31.json_prediction_startup_functional.v1'
                or attestation.get('mode')!=mode or attestation.get('version')!=version
                or attestation.get('source_unchanged') is not True or attestation.get('closed_requests')!=0):
            raise ValueError('startup_gate_different_implementation')
        startup[mode]={'reference':ref,'loaded_sources':attestation['loaded_sources'],'proof':attestation['proof']}
    if startup['reference']['loaded_sources']!=startup['compiled']['loaded_sources']:
        raise ValueError('different_loaded_source_domains')
    plan={'schema':SCHEMA,'source_sha256':{name:codec.sha_bytes(data) for name,data in files.items()},
        'image':{'directory':'image','version':version},'input':{'path':str(INPUT),'sha256':INPUT_SHA},
        'startup_gate':startup,
        'interpreter':{'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable),'version':sys.version},
        'pure_gate':{str(p):sha(p) for p in (pure/'receipt.json',pure/'tests.xml')},'cases':rows,
        'worker_order':list(ORDER),'hard_timeout_seconds':120.,'native_calls':0,'requests':24,
        'candidate_queries_per_valid_request':32,'candidate_queries':768,'full_baselines':24,
        'A':'Frozen ProtectionRequestContext, including its normal per-context code checks/guard compilation.',
        'B':'Same constructor remainder and exact complete/partial outputs; implementation checks and original guards compiled once per fixed-version JSON worker.',
        'scope':'Supplied initial 3tray/5job retrospective model only. Every request builds new snapshot, full dynamic guard, fingerprint, potential, complete baseline and all32 candidate predictions. No prior observations, labels, potentials or prediction results cached.',
        'startup':'Four independently launched isolated -I -S workers. Each verified source image and loaded closure precedes READY; B compiles guards once. New version requires new process. No late project imports, extension, eval or reload RPC.',
        'request_cost':'Caller admission before encoding through synchronous IPC, worker validation/isolation/model/full baseline/all32/encoding, IPC response and strict caller decode. Server compute is nested, never added again. Queue and transport elapsed are not discarded.',
        'cold_cost':'Per worker launch-to-READY and launch-through-first-reply retained; no discarded warmup or averaging. Input preparation/import/source checks, close/rehash/reclamation, raw exports and saved verification stay in whole owned120/outer application wall. No complete cold100ms claim.',
        'failure':'Source/version/schema/replay/EOF/exception/timeout/capacity error is failed/unknown, never a complete result. All24 fixed requests and all768 queries required. Preserve negatives and partial suffix labels exactly.',
        'complete_100ms_certified':False}
    check_plan(plan);write(output/'preregistered_protocol.json',plan)
    write(output/'prepare_receipt.json',{'status':'prepared_unexecuted','plan_sha256':sha(output/'preregistered_protocol.json'),
        'sources':len(files),'image_version':version,'native_calls':0,'performance_campaign_executed':False})


def verify_pins(output,plan):
    check_plan(plan)
    current={name:codec.sha_bytes(data) for name,data in closure().items()}
    if current!=plan['source_sha256']:raise ValueError('changed_live_closure')
    for name,digest in current.items():
        if sha(output/'source'/name)!=digest:raise ValueError('changed_archive')
    image,_=codec.verify_image(output/'image',plan['image']['version'])
    if (any(plan['source_sha256'].get(name)!=digest for name,digest in image['files'].items())
            or image['files']!={name:codec.sha_bytes(data) for name,data in codec.source_closure(ROOT,
                (codec.ENTRY,codec.MODEL,'scripts.experiments.g31_ics_circulation.json_prediction_image')).items()}):
        raise ValueError('image_not_same_pinned_implementation')
    if plan.get('interpreter')!={'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable),'version':sys.version}:
        raise ValueError('interpreter_changed')
    if sha(plan['input']['path'])!=INPUT_SHA:raise ValueError('changed_inputs')
    selected=[r for r in json.loads(Path(plan['input']['path']).read_bytes()) if r['owner']=='A']
    if [r['case'] for r in selected]!=list(CASES):raise ValueError('changed_input_denominator')
    for row,source in zip(plan['cases'],selected,strict=True):
        if sha(output/row['input'])!=row['sha256'] or codec.encode(read(output/row['input']))!=codec.encode(source['bundle']):
            raise ValueError('changed_case_bytes_or_value')
    for path,digest in plan['pure_gate'].items():
        if sha(path)!=digest:raise ValueError('changed_pure_gate')
    if set(plan.get('startup_gate',{}))!={'reference','compiled'}:raise ValueError('missing_startup_gate')
    for mode,gate in plan['startup_gate'].items():
        ref=gate['reference']
        if sha(ref['path'])!=ref['sha256']:raise ValueError('changed_startup_gate')
        attestation=read(ref['path'])
        if (attestation['version']!=plan['image']['version'] or attestation['mode']!=mode
                or attestation['source_unchanged'] is not True or attestation['closed_requests']!=0
                or gate['loaded_sources']!=attestation['loaded_sources'] or gate['proof']!=attestation['proof']):
            raise ValueError('startup_gate_not_bound')


def check_ready(ready,gate,version,mode):
    if (ready.get('kind')!='ready' or ready.get('version')!=version or ready.get('mode')!=mode
            or ready.get('native_authority') is not False or not gate.get('loaded_sources')
            or ready.get('loaded_sources')!=gate['loaded_sources'] or ready.get('proof')!=gate['proof']
            or not positive_int(ready.get('startup_post_import_wall_ns'))):
        raise ValueError('READY_closure_or_proof_mismatch')


def check_payload(value):
    if (type(value) is not dict or set(value)!={'baseline','actions','predictions'}
            or len(value['actions'])!=32 or len(value['predictions'])!=32
            or value['baseline'].get('status')!='conditional_prediction'
            or any(p.get('status') not in ('conditional_prediction','conditional_protection_rejected_prefix') for p in value['predictions'])):
        raise ValueError('incomplete_prediction_domain')


def positive_int(value, *, zero=False):
    return type(value) is int and value >= (0 if zero else 1)


def check_sample(sample,case,request_id,sequence,version):
    if (sample.get('request_id')!=request_id or sample.get('sequence')!=sequence
            or not positive_int(sample.get('caller_admitted_ns')) or not positive_int(sample.get('caller_decoded_ns'))
            or not positive_int(sample.get('caller_body_finished_ns'))
            or sample['caller_body_finished_ns']<sample['caller_decoded_ns']
            or sample.get('caller_bookkeeping_ns')!=sample['caller_body_finished_ns']-sample['caller_decoded_ns']
            or sample.get('caller_elapsed_ns')!=sample['caller_body_finished_ns']-sample['caller_admitted_ns']
            or not positive_int(sample['caller_elapsed_ns'])
            or sample.get('cold_through_reply_ns') is not None and not positive_int(sample['cold_through_reply_ns'])):
        raise ValueError('sample_clock_or_identity')
    request=sample['request'];response=sample['response']
    if (request.get('kind')!='predict' or request.get('version')!=version or request.get('sequence')!=sequence
            or request.get('request_id')!=request_id or codec.encode(request.get('snapshot'))!=codec.encode(case)
            or response.get('kind')!='prediction' or response.get('version')!=version
            or response.get('sequence')!=sequence or response.get('request_id')!=request_id
            or response.get('native_authority') is not False or response.get('complete_100ms_certified') is not False
            or not positive_int(response.get('compute_wall_ns'),zero=True)
            or response['compute_wall_ns']>sample['caller_elapsed_ns']):
        raise ValueError('sample_RPC_binding')
    check_payload(response['payload'])
    if (not positive_int(sample.get('outer_admitted_ns')) or not positive_int(sample.get('outer_returned_ns'))
            or not sample['outer_admitted_ns']<=sample['caller_admitted_ns']<=sample['caller_body_finished_ns']<=sample['outer_returned_ns']
            or sample.get('complete_caller_elapsed_ns')!=sample['outer_returned_ns']-sample['outer_admitted_ns']):
        raise ValueError('missing_outside_call_envelope')


def campaign(output,expected):
    if sha(output/'preregistered_protocol.json')!=expected:raise ValueError('wrong_plan')
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    ledger=[{'worker':i,'mode':mode,'status':'unknown_unexecuted'} for i,mode in enumerate(ORDER)]
    write(output/'ledger.json',ledger)
    for index,mode in enumerate(ORDER):
        row=ledger[index];row['status']='unknown_in_progress';write(output/'ledger.json',ledger)
        rpc=None
        try:
            with (output/f'{index}.stderr.log').open('xb') as errors:
                with Client(output/'image',plan['image']['version'],mode,
                            timeout=max(.001,120.-(time.perf_counter()-BOOT)),stderr=errors) as rpc:
                    for n,case in enumerate(plan['cases'],1):
                        outside = time.perf_counter_ns()
                        rpc.predict(f'worker-{index}:{case["case"]}',read(output/case['input']))
                        returned = time.perf_counter_ns()
                        rpc.ledger[-1].update(outer_admitted_ns=outside,outer_returned_ns=returned,
                            complete_caller_elapsed_ns=returned-outside)
                reclaimed = time.perf_counter_ns()
                record={'worker':index,'mode':mode,'command':rpc.command,'ready':rpc.ready,
                    'client_started_ns':rpc.started_ns,'ready_ns':rpc.ready_ns,
                    'process_reclaimed_ns':reclaimed,'samples':rpc.ledger,'shutdown':rpc.shutdown}
            name=f'{index}.{mode}.json.gz';(output/name).write_bytes(gzip.compress(codec.artifact_encode(record),compresslevel=1,mtime=0))
            row.update(status='completed',raw=name,sha256=sha(output/name))
            write(output/'ledger.json',ledger)
        except BaseException:
            if rpc is not None:
                write(output/f'{index}.failed_prefix.json',{'status':'unknown','samples':rpc.ledger,
                    'closed':rpc.closed,'process_exit_code':rpc.process.returncode})
            row['status']='unknown_failed';write(output/'ledger.json',ledger);raise
    verify_pins(output,plan)
    report=verify_saved(output,require_process=False)
    write(output/'report.json',report)


def verify_saved(output,*,require_process=True):
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    ledger=read(output/'ledger.json')
    if len(ledger)!=4:raise ValueError('worker_denominator')
    references={};times=[];cold=[];closing=[]
    image,_=codec.verify_image(output/'image',plan['image']['version'])
    for index,(row,mode) in enumerate(zip(ledger,ORDER,strict=True)):
        name=f'{index}.{mode}.json.gz'
        if (row.get('worker')!=index or row.get('mode')!=mode or row.get('status')!='completed'
                or row.get('raw')!=name or sha(output/name)!=row.get('sha256')):raise ValueError('worker_identity_or_raw')
        with gzip.open(output/name,'rb') as source:
            record=codec.artifact_decode(source.read(codec.MAX_ARTIFACT_BYTES+1))
        ready=record['ready'];shutdown=record['shutdown']
        check_ready(ready,plan['startup_gate'][mode],plan['image']['version'],mode)
        command=record.get('command',[])
        expected_command=[plan['interpreter']['path'],'-I','-S',str(output/'image/scripts/experiments/g31_ics_circulation/json_prediction_worker.py'),
            '--image',str(output/'image'),'--version',plan['image']['version'],'--mode',mode,'--admission']
        if (len(command)!=len(expected_command)+1 or command[:-1]!=expected_command
                or type(command[-1]) is not str or len(command[-1])!=32
                or any(c not in '0123456789abcdef' for c in command[-1])):
            raise ValueError('worker_command_not_bound')
        if (record['worker']!=index or record['mode']!=mode or len(record['samples'])!=6
                or ready.get('kind')!='ready' or ready.get('version')!=plan['image']['version']
                or ready.get('mode')!=mode or ready.get('native_authority') is not False
                or not ready.get('loaded_sources') or any(image['files'].get(k)!=v for k,v in ready['loaded_sources'].items())
                or ready.get('proof',{}).get('guard_compilations')!=(1 if mode=='compiled' else 0)
                or not positive_int(record.get('client_started_ns')) or not positive_int(record.get('ready_ns'))
                or record['ready_ns']<record['client_started_ns']
                or shutdown.get('process_exit_code')!=0 or shutdown.get('reply',{}).get('source_unchanged') is not True
                or shutdown['reply'].get('version')!=plan['image']['version'] or shutdown['reply'].get('requests')!=6
                or not positive_int(shutdown.get('close_admitted_ns')) or not positive_int(shutdown.get('close_finished_ns'))
                or not positive_int(shutdown.get('protocol_closed_ns'))
                or not shutdown['close_admitted_ns']<=shutdown['protocol_closed_ns']<=shutdown['close_finished_ns']
                or not positive_int(record.get('process_reclaimed_ns'))
                or record['process_reclaimed_ns']<shutdown['close_finished_ns']):raise ValueError('worker_startup_shutdown')
        previous=record['ready_ns']
        for n,(sample,case) in enumerate(zip(record['samples'],plan['cases'],strict=True),1):
            check_sample(sample,read(output/case['input']),f'worker-{index}:{case["case"]}',n,plan['image']['version'])
            if sample['outer_admitted_ns']<previous:raise ValueError('nonserial_RPC')
            previous=sample['outer_returned_ns']
            if n==1:
                if sample['cold_through_reply_ns']!=sample['caller_body_finished_ns']-record['client_started_ns']:raise ValueError('cold_cost_missing')
                cold.append({'worker':index,'mode':mode,'startup_ns':record['ready_ns']-record['client_started_ns'],
                    'launch_through_first_return_ns':sample['outer_returned_ns']-record['client_started_ns']})
            elif sample['cold_through_reply_ns'] is not None:raise ValueError('cold_label_reused')
            payload=codec.encode(sample['response']['payload'])
            if index==0:references[case['case']]=payload
            elif payload!=references[case['case']]:raise ValueError('ordered_output_not_exact')
            times.append({'worker':index,'mode':mode,'case':case['case'],'complete_caller_ns':sample['complete_caller_elapsed_ns'],
                'nested_worker_compute_ns':sample['response']['compute_wall_ns']})
        if shutdown['close_admitted_ns']<previous:raise ValueError('close_before_reply')
        closing.append({'worker':index,'mode':mode,'close_with_reclamation_ns':record['process_reclaimed_ns']-shutdown['close_admitted_ns']})
    if require_process:
        process=read(output/'bounded_execution.json')
        if process.get('status')!='completed' or process.get('process',{}).get('exitcode')!=0:
            raise ValueError('missing_owned_process_success')
    return {'schema':SCHEMA,'status':'saved_24_RPC_ordered_exact','plan_sha256':sha(output/'preregistered_protocol.json'),
        'requests':24,'candidate_queries':768,'full_baselines':24,'source_changed':[],
        'request_costs':times,'cold_startup_costs':cold,'shutdown_costs':closing,
        'median_complete_caller_ns':{mode:statistics.median(r['complete_caller_ns'] for r in times if r['mode']==mode) for mode in ORDER[:2]},
        'native_calls':0,'complete_100ms_certified':False,
        'scope':'Functional supplied-input RPC comparison; first-request cold and shutdown costs separate, never amortized or subtracted. Entire external application wall still required.'}


def launch(output,expected):
    with (output/'execution_claim.json').open('x',encoding='utf8') as handle:json.dump({'plan_sha256':expected},handle)
    if any((output/n).exists() for n in ('ledger.json','report.json','failure.json','bounded_execution.json')):
        raise ValueError('refuse_prior_execution')
    if sha(output/'preregistered_protocol.json')!=expected:raise ValueError('wrong_plan')
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',ENTRY,'--campaign','--output',str(output),'--plan-sha256',expected,'--admission',admission]
    process=None;error=None
    try:
        remaining=120.-(time.perf_counter()-BOOT)
        if remaining<=0:raise TimeoutError('parent_setup_exhausted_120')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,admission=admission,stdout=stdout,stderr=stderr,cwd=ROOT)
    except BaseException as problem:error=repr(problem)
    result={'status':'completed' if process and process['status']=='exited' and process['exitcode']==0 else 'unknown_or_failed',
        'process':process,'error':error,'command':command,'plan_sha256':expected,
        'parent_pre_final_export_wall_seconds':time.perf_counter()-BOOT,'native_calls':0,
        'full_wall':'An external launch-to-exit receipt includes interpreter startup and final receipt export. No claim of full-platform cold start.'}
    write(output/'bounded_execution.json',result)
    return 0 if result['status']=='completed' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pure',type=Path)
    parser.add_argument('--plan-sha256');parser.add_argument('--admission')
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare','launch','campaign','verify-saved'):mode.add_argument('--'+name,action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output,args.pure.resolve());return 0
    if args.launch:return launch(output,args.plan_sha256)
    if args.verify_saved:print(codec.encode(verify_saved(output)).decode());return 0
    if sys.stdin.readline().strip()!=args.admission:raise ValueError('no_owned_job_admission')
    try:campaign(output,args.plan_sha256)
    except BaseException as error:
        write(output/'failure.json',{'status':'unknown_or_failed','error':repr(error),'traceback':traceback.format_exc(),'native_calls':0});raise
    return 0

if __name__=='__main__':raise SystemExit(main())
