"""Prepare-only by default: one compiled32 versus two compiled16 processes.

Four logical ABBA rounds, six fixed inputs each. Physical baseline denominator
is36, not24. All timing/codec/merge/cleanup costs and failures remain visible.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path
import statistics
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import json_prediction_image as codec
from . import json_prediction_shard_image as shard_image
from . import measure_json_prediction_service as old
from .json_prediction_shard_client import LogicalClient, merge

ROOT, OUT, INPUT, INPUT_SHA, CASES = old.ROOT, old.OUT, old.INPUT, old.INPUT_SHA, old.CASES
ORDER = ('single','split','split','single')
MODES = {'single':('compiled',),'split':('shard0','shard1')}
SCHEMA = 'g31.json_prediction_exact_two_shards_ABBA.v1'
ENTRY = 'scripts.experiments.g31_ics_circulation.measure_json_prediction_shards'
TEST_NAMES = ('tests/test_g31_circulation_json_prediction_shards.py',)
EXPECTED_PURE_TESTS = 61
sha, read, write = old.sha, old.read, old.write


def closure():
    files = codec.source_closure(ROOT,(ENTRY,shard_image.ENTRY,
        'scripts.experiments.g31_ics_circulation.run_json_shards_pure'))
    for name in TEST_NAMES:
        files[name] = (ROOT/name).read_bytes()
    return dict(sorted(files.items()))


def check_plan(plan):
    expected = {'schema':SCHEMA,'round_order':list(ORDER),'logical_requests':24,
        'physical_worker_processes':6,'physical_RPC_requests':36,'physical_full_baselines':36,
        'candidate_queries':768,'candidate_queries_per_logical_request':32,
        'shards':{'shard0':list(range(16)),'shard1':list(range(16,32))},
        'hard_timeout_seconds':120.,'native_calls':0}
    if any(plan.get(k)!=v for k,v in expected.items()):
        raise ValueError('changed_fixed_shard_campaign')
    if ([r.get('case') for r in plan.get('cases',[])] != list(CASES)
            or plan.get('input',{}).get('sha256') != INPUT_SHA
            or set(plan.get('images',{})) != {'single','split'} or not plan.get('source_sha256')):
        raise ValueError('input_or_source_denominator')
    for name in plan['source_sha256']:
        codec.safe_name(name)
    for row in plan['cases']:
        if row['input'] != row['case']+'.json':
            raise ValueError('case_filename')
    for key in ('single','split'):
        if plan['images'][key]['directory'] != 'image_'+key:
            raise ValueError('image_directory')


def check_pure(pure,receipt):
    cases = ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
    if (receipt.get('status')!='passed' or receipt.get('source_changed')!=[]
            or receipt.get('native_calls')!=0 or receipt.get('tests')!=EXPECTED_PURE_TESTS
            or len(cases)!=EXPECTED_PURE_TESTS or receipt.get('XML_sha256')!=sha(pure/'tests.xml')
            or any(c.tag in ('failure','error','skipped') for row in cases for c in row)):
        raise ValueError('functional_gate_not_passed')


def prepare(output,pure):
    output.mkdir(parents=True,exist_ok=False)
    receipt=read(pure/'receipt.json');check_pure(pure,receipt)
    files=closure()
    if receipt['source_sha256']!={k:codec.sha_bytes(v) for k,v in files.items()}:
        raise ValueError('functional_source_changed')
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    if sha(INPUT)!=INPUT_SHA:raise ValueError('fixed_input_changed')
    selected=[r for r in json.loads(INPUT.read_bytes()) if r['owner']=='A']
    if [r['case'] for r in selected]!=list(CASES):raise ValueError('six_cases_changed')
    rows=[]
    for row in selected:
        path=output/(row['case']+'.json');write(path,row['bundle'])
        rows.append({'case':row['case'],'input':path.name,'sha256':sha(path)})
    images={key:{'directory':'image_'+key,'version':module.build_image(ROOT,output/('image_'+key))}
        for key,module in (('single',codec),('split',shard_image))}
    startup={}
    if set(receipt.get('startup_attestations',{}))!={'compiled','shard0','shard1'}:
        raise ValueError('startup_functional_denominator')
    for mode,ref in receipt['startup_attestations'].items():
        if sha(ref['path'])!=ref['sha256']:raise ValueError('startup_attestation_changed')
        value=read(ref['path']);key='single' if mode=='compiled' else 'split'
        if (value.get('mode')!=mode or value.get('version')!=images[key]['version']
                or value.get('source_unchanged') is not True or value.get('closed_requests')!=0):
            raise ValueError('startup_wrong_image_or_requests')
        startup[mode]={'reference':ref,'loaded_sources':value['loaded_sources'],'proof':value['proof']}
    if startup['shard0']['loaded_sources']!=startup['shard1']['loaded_sources']:
        raise ValueError('split_loaded_closure_differs')
    plan={'schema':SCHEMA,'round_order':list(ORDER),'logical_requests':24,'physical_worker_processes':6,
        'physical_RPC_requests':36,'physical_full_baselines':36,'candidate_queries':768,
        'candidate_queries_per_logical_request':32,'shards':{'shard0':list(range(16)),'shard1':list(range(16,32))},
        'hard_timeout_seconds':120.,'native_calls':0,'input':{'path':str(INPUT),'sha256':INPUT_SHA},
        'cases':rows,'images':images,'startup_gate':startup,
        'source_sha256':{k:codec.sha_bytes(v) for k,v in files.items()},
        'interpreter':{'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable),'version':sys.version},
        'pure_gate':{str(p):sha(p) for p in (pure/'receipt.json',pure/'tests.xml')},
        'A':'Frozen compiled single-worker Engine and original Client; all32 queries.',
        'B':'Two new same-version processes, fixed0..15/16..31; every process repeats full fresh guard/potential/baseline. No shared request state or cross-request cache.',
        'common_caller':'Admission precedes actual input file read/decode. Caller isolation, both frames, scheduling/wait/merge, whole-result codec, ledger and outside return tail included. Worker compute nested; sumworker wall is duplicated-work diagnostic, not CPU time or request wall.',
        'cold':'All6 process startups, first-request launch envelope, shutdown/rehash/reclamation and complete shared120 campaign retained without amortization. External full Python launch-to-exit still required.',
        'failure':'Any shard/schema/baseline/domain/source/timeout failure makes complete logical request unknown and closes owned workers. Never fill missing rows with earlier outputs or declare partial32 complete.',
        'scope':'Supplied initial3tray/5job model, fixed six retrospective inputs. One ABBA pipeline comparison; no native, no algorithm or complete100ms claim.'}
    check_plan(plan);write(output/'preregistered_protocol.json',plan)
    write(output/'prepare_receipt.json',{'status':'prepared_unexecuted','plan_sha256':sha(output/'preregistered_protocol.json'),
        'sources':len(files),'images':images,'native_calls':0,'performance_campaign_executed':False})


def verify_pins(output,plan):
    check_plan(plan)
    files=closure();current={k:codec.sha_bytes(v) for k,v in files.items()}
    if current!=plan['source_sha256']:raise ValueError('live_closure_changed')
    for name,digest in current.items():
        if sha(output/'source'/name)!=digest:raise ValueError('archive_changed')
    for key,module in (('single',codec),('split',shard_image)):
        manifest,_=module.verify_image(output/plan['images'][key]['directory'],plan['images'][key]['version'])
        helper='scripts.experiments.g31_ics_circulation.'+('json_prediction_image' if key=='single' else 'json_prediction_shard_image')
        expected={name:codec.sha_bytes(data) for name,data in codec.source_closure(ROOT,(module.ENTRY,module.MODEL,helper)).items()}
        if manifest['files']!=expected or any(current.get(k)!=v for k,v in expected.items()):
            raise ValueError('image_not_exact_source_closure')
    if plan['interpreter']!={'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable),'version':sys.version}:
        raise ValueError('interpreter_changed')
    if sha(plan['input']['path'])!=INPUT_SHA:raise ValueError('input_changed')
    selected=[r for r in json.loads(Path(plan['input']['path']).read_bytes()) if r['owner']=='A']
    if [r['case'] for r in selected]!=list(CASES):raise ValueError('source_input_order_changed')
    for row,supplied in zip(plan['cases'],selected,strict=True):
        if sha(output/row['input'])!=row['sha256'] or codec.encode(read(output/row['input']))!=codec.encode(supplied['bundle']):
            raise ValueError('case_changed')
    for path,digest in plan['pure_gate'].items():
        if sha(path)!=digest:raise ValueError('pure_gate_changed')
    if set(plan['startup_gate'])!={'compiled','shard0','shard1'}:raise ValueError('startup_gate_denominator')
    for mode,gate in plan['startup_gate'].items():
        ref=gate['reference'];value=read(ref['path']);key='single' if mode=='compiled' else 'split'
        if (sha(ref['path'])!=ref['sha256'] or value['mode']!=mode
                or value['version']!=plan['images'][key]['version'] or value['source_unchanged'] is not True
                or value['closed_requests']!=0 or value['loaded_sources']!=gate['loaded_sources'] or value['proof']!=gate['proof']):
            raise ValueError('startup_gate_changed')


def check_sample(row,snapshot,identity,sequence,arm,versions):
    count=1 if arm=='single' else 2
    clocks=('outer_admitted_ns','caller_admitted_ns','all_replies_ns','caller_body_finished_ns','outer_returned_ns')
    if (any(not old.positive_int(row.get(k)) for k in clocks)
            or [row[k] for k in clocks]!=sorted(row[k] for k in clocks)
            or row.get('request_id')!=identity or row.get('arm')!=arm
            or codec.encode(row.get('snapshot'))!=codec.encode(snapshot)
            or row.get('caller_elapsed_ns')!=row['caller_body_finished_ns']-row['caller_admitted_ns']
            or row.get('complete_caller_elapsed_ns')!=row['outer_returned_ns']-row['outer_admitted_ns']
            or row.get('physical_baselines')!=count or row.get('candidate_queries')!=32
            or type(row.get('physical_baselines')) is not int or type(row.get('candidate_queries')) is not int
            or len(row.get('worker_samples',[]))!=count):
        raise ValueError('logical_sample_identity_or_cost')
    parts=[];compute=0
    for i,sample in enumerate(row['worker_samples']):
        request,response=sample['request'],sample['response']
        expected_id=identity+':'+str(i)
        clock=('caller_admitted_ns','caller_decoded_ns','caller_body_finished_ns')
        if (any(not old.positive_int(sample.get(k)) for k in clock)
                or not row['caller_admitted_ns']<=sample[clock[0]]<=sample[clock[1]]<=sample[clock[2]]<=row['all_replies_ns']
                or sample.get('request_id')!=expected_id or sample.get('sequence')!=sequence
                or type(sample.get('sequence')) is not int
                or sample.get('caller_elapsed_ns')!=sample[clock[2]]-sample[clock[0]]
                or sample.get('caller_bookkeeping_ns')!=sample[clock[2]]-sample[clock[1]]
                or set(request)!={'kind','version','sequence','request_id','snapshot'}
                or request['kind']!='predict' or request['version']!=versions[arm]
                or request['sequence']!=sequence or request['request_id']!=expected_id
                or type(request['sequence']) is not int
                or codec.encode(request['snapshot'])!=codec.encode(snapshot)
                or response.get('kind')!='prediction' or response.get('version')!=versions[arm]
                or response.get('sequence')!=sequence or response.get('request_id')!=expected_id
                or type(response.get('sequence')) is not int
                or response.get('native_authority') is not False or response.get('complete_100ms_certified') is not False
                or not old.positive_int(response.get('compute_wall_ns'),zero=True)
                or response['compute_wall_ns']>sample['caller_elapsed_ns']):
            raise ValueError('worker_RPC_identity_or_cost')
        compute+=response['compute_wall_ns'];parts.append(response['payload'])
    payload=parts[0] if arm=='single' else merge(parts,snapshot)
    old.check_payload(payload)
    if codec.encode(payload)!=codec.encode(row['merged_payload']) or row.get('sum_worker_compute_ns')!=compute:
        raise ValueError('merge_or_nested_compute_changed')
    return payload


def worker_record(client):
    return {'mode':client.mode,'command':client.command,'ready':client.ready,
        'client_started_ns':client.started_ns,'ready_ns':client.ready_ns,
        'shutdown':client.shutdown,'ledger_count':len(client.ledger)}


def campaign(output,expected):
    if sha(output/'preregistered_protocol.json')!=expected:raise ValueError('wrong_plan')
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    ledger=[{'round':i,'arm':arm,'status':'unknown_unexecuted'} for i,arm in enumerate(ORDER)]
    write(output/'ledger.json',ledger)
    images={key:{'path':output/value['directory'],'version':value['version']} for key,value in plan['images'].items()}
    for index,arm in enumerate(ORDER):
        state=ledger[index];state['status']='unknown_in_progress';write(output/'ledger.json',ledger)
        client=None;attempts=[]
        try:
            with ExitStack() as stack:
                stderrs=[stack.enter_context((output/f'{index}.{mode}.stderr.log').open('x',encoding='utf8')) for mode in MODES[arm]]
                client=LogicalClient(arm,images,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
                    stderrs=stderrs,startup_attempts=attempts)
                for case in plan['cases']:
                    admitted=time.perf_counter_ns()
                    snapshot=read(output/case['input'])
                    client.predict(f'round-{index}:{case["case"]}',snapshot)
                    returned=time.perf_counter_ns()
                    client.ledger[-1].update(outer_admitted_ns=admitted,outer_returned_ns=returned,
                        complete_caller_elapsed_ns=returned-admitted)
                shutdown=client.close()
                record={'round':index,'arm':arm,'client_started_ns':client.started_ns,'ready_ns':client.ready_ns,
                    'startup_attempts':attempts,'workers':[worker_record(c) for c in client.clients],
                    'samples':client.ledger,'shutdown':shutdown,'process_reclaimed_ns':time.perf_counter_ns(),
                    'cleanup_errors':client.cleanup_errors}
            name=f'{index}.{arm}.json.gz'
            with (output/name).open('xb') as handle:
                handle.write(gzip.compress(codec.artifact_encode(record),compresslevel=1,mtime=0))
            state.update(status='completed',raw=name,sha256=sha(output/name));write(output/'ledger.json',ledger)
        except BaseException as error:
            if client is not None:client.abort()
            write(output/f'{index}.failed_prefix.json',{'status':'unknown','error':repr(error),'startup_attempts':attempts,
                'samples':client.ledger if client else [],'cleanup_errors':client.cleanup_errors if client else [],
                'partial_worker_samples':[{'mode':getattr(c,'mode',None),'command':getattr(c,'command',None),
                    'samples':getattr(c,'ledger',[]),'process_exit_code':getattr(getattr(c,'process',None),'returncode',None)}
                    for c in client.clients] if client else []})
            state['status']='unknown_failed';write(output/'ledger.json',ledger);raise
    verify_pins(output,plan)
    write(output/'report.json',verify_saved(output,require_process=False))


def verify_saved(output,*,require_process=True):
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    ledger=read(output/'ledger.json')
    if len(ledger)!=4:raise ValueError('round_denominator')
    expected_raw={f'{i}.{arm}.json.gz' for i,arm in enumerate(ORDER)}
    if {p.name for p in output.glob('*.json.gz')}!=expected_raw or list(output.glob('*.failed_prefix.json')):
        raise ValueError('extra_or_missing_worker_raw')
    versions={k:v['version'] for k,v in plan['images'].items()}
    reference={};costs=[];cold=[];shutdowns=[];process_count=0;RPC_count=0
    for index,(state,arm) in enumerate(zip(ledger,ORDER,strict=True)):
        name=f'{index}.{arm}.json.gz'
        if (state.get('round')!=index or state.get('arm')!=arm or state.get('status')!='completed'
                or state.get('raw')!=name or state.get('sha256')!=sha(output/name)):
            raise ValueError('round_identity_or_hash')
        with gzip.open(output/name,'rb') as stream:record=codec.artifact_decode(stream.read(codec.MAX_ARTIFACT_BYTES+1))
        if (record.get('round')!=index or record.get('arm')!=arm or record.get('cleanup_errors')!=[]
                or len(record.get('workers',[]))!=len(MODES[arm]) or len(record.get('startup_attempts',[]))!=len(MODES[arm])
                or len(record.get('samples',[]))!=6):raise ValueError('actual_denominator')
        for wi,(worker,mode) in enumerate(zip(record['workers'],MODES[arm],strict=True)):
            key='single' if mode=='compiled' else 'split';version=versions[key]
            old.check_ready(worker['ready'],plan['startup_gate'][mode],version,mode)
            entry='json_prediction_worker.py' if key=='single' else 'json_prediction_shard_worker.py'
            expected=[plan['interpreter']['path'],'-I','-S',str(output/plan['images'][key]['directory']/'scripts/experiments/g31_ics_circulation'/entry),
                '--image',str(output/plan['images'][key]['directory']),'--version',version,'--mode',mode,'--admission']
            command=worker.get('command',[]);attempt=record['startup_attempts'][wi];closed=worker['shutdown']
            if (len(command)!=len(expected)+1 or command[:-1]!=expected or len(command[-1])!=32
                    or any(c not in '0123456789abcdef' for c in command[-1])
                    or attempt.get('mode')!=mode or attempt.get('status')!='ready' or attempt.get('command')!=command
                    or not old.positive_int(attempt.get('pid')) or worker.get('mode')!=mode or worker.get('ledger_count')!=6
                    or closed.get('process_exit_code')!=0 or closed.get('reply',{}).get('source_unchanged') is not True
                    or closed['reply'].get('requests')!=6 or closed['reply'].get('version')!=version):
                raise ValueError('actual_worker_lifecycle')
            required=('client_started_ns','ready_ns')
            if any(not old.positive_int(worker.get(k)) for k in required):raise ValueError('worker_startup_clock')
            cfields=('close_admitted_ns','protocol_closed_ns','close_finished_ns')
            if (any(not old.positive_int(closed.get(k)) for k in cfields)
                    or [closed[k] for k in cfields]!=sorted(closed[k] for k in cfields)):
                raise ValueError('worker_close_clock')
            process_count+=1
        if (any(not old.positive_int(record.get(k)) for k in ('client_started_ns','ready_ns','process_reclaimed_ns'))
                or not record['client_started_ns']<=min(w['client_started_ns'] for w in record['workers'])
                or any(w['ready_ns']<w['client_started_ns'] or w['ready_ns']>record['ready_ns'] for w in record['workers'])):
            raise ValueError('logical_startup_clock')
        previous=record['ready_ns']
        for sequence,(sample,case) in enumerate(zip(record['samples'],plan['cases'],strict=True),1):
            payload=check_sample(sample,read(output/case['input']),f'round-{index}:{case["case"]}',sequence,arm,versions)
            if sample['outer_admitted_ns']<previous:raise ValueError('nonserial_logical_requests')
            previous=sample['outer_returned_ns'];RPC_count+=len(sample['worker_samples'])
            for worker,part in zip(record['workers'],sample['worker_samples'],strict=True):
                if part['caller_admitted_ns']<worker['ready_ns']:raise ValueError('request_before_READY')
                expected_cold=part['caller_body_finished_ns']-worker['client_started_ns'] if sequence==1 else None
                if part.get('cold_through_reply_ns')!=expected_cold:raise ValueError('worker_cold_cost')
            encoded=codec.encode(payload)
            if index==0:reference[case['case']]=encoded
            elif encoded!=reference[case['case']]:raise ValueError('ordered32_output_changed')
            costs.append({'round':index,'arm':arm,'case':case['case'],
                'complete_caller_ns':sample['complete_caller_elapsed_ns'],'sum_worker_compute_ns':sample['sum_worker_compute_ns'],
                'max_worker_compute_ns':max(s['response']['compute_wall_ns'] for s in sample['worker_samples']),
                'physical_baselines':sample['physical_baselines'],'candidate_queries':32})
            if sequence==1:cold.append({'round':index,'arm':arm,'startup_ns':record['ready_ns']-record['client_started_ns'],
                'launch_through_first_return_ns':sample['outer_returned_ns']-record['client_started_ns']})
        finish=record['shutdown']
        if (not old.positive_int(finish.get('close_admitted_ns')) or not old.positive_int(finish.get('closed_and_reclaimed_ns'))
                or not previous<=finish['close_admitted_ns']<=finish['closed_and_reclaimed_ns']<=record['process_reclaimed_ns']
                or finish['workers']!=[w['shutdown'] for w in record['workers']]
                or any(w['shutdown']['close_admitted_ns']<finish['close_admitted_ns'] or w['shutdown']['close_finished_ns']>finish['closed_and_reclaimed_ns'] for w in record['workers'])):
            raise ValueError('complete_cleanup_envelope')
        shutdowns.append({'round':index,'arm':arm,'close_with_reclamation_ns':record['process_reclaimed_ns']-finish['close_admitted_ns']})
    if (process_count,RPC_count,sum(r['physical_baselines'] for r in costs),sum(r['candidate_queries'] for r in costs))!=(6,36,36,768):
        raise ValueError('physical_work_denominator')
    if require_process:
        receipt=read(output/'bounded_execution.json')
        if receipt.get('status')!='completed' or receipt.get('process',{}).get('exitcode')!=0:
            raise ValueError('owned_campaign_not_completed')
    return {'schema':SCHEMA,'status':'saved_exact24_logical36_baseline768_candidates',
        'plan_sha256':sha(output/'preregistered_protocol.json'),'source_changed':[],
        'logical_requests':24,'physical_workers':6,'physical_RPC_requests':36,'physical_full_baselines':36,'candidate_queries':768,
        'costs':costs,'cold_costs':cold,'shutdown_costs':shutdowns,
        'median_complete_caller_ns':{arm:statistics.median(r['complete_caller_ns'] for r in costs if r['arm']==arm) for arm in ('single','split')},
        'native_calls':0,'complete_100ms_certified':False,
        'scope':'Exact supplied32 outputs only. Sum worker compute WALL durations are duplicated nested work, not measured CPU or critical-path caller wall. Cold costs are not averaged away.'}


def launch(output,expected):
    if sha(output/'preregistered_protocol.json')!=expected:raise ValueError('wrong_plan')
    if any((output/name).exists() for name in ('execution_claim.json','ledger.json','report.json','failure.json','bounded_execution.json')):
        raise ValueError('refuse_prior_execution')
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:json.dump({'plan_sha256':expected},stream)
    plan=read(output/'preregistered_protocol.json');verify_pins(output,plan)
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',ENTRY,'--campaign','--output',str(output),'--plan-sha256',expected,'--admission',admission]
    process=None;error=None
    try:
        remaining=120.-(time.perf_counter()-BOOT)
        if remaining<=0:raise TimeoutError('parent_setup_exhausted120')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,admission=admission,stdout=stdout,stderr=stderr,cwd=ROOT)
    except BaseException as problem:error=repr(problem)
    result={'status':'completed' if process and process['status']=='exited' and process['exitcode']==0 else 'unknown_or_failed',
        'process':process,'error':error,'command':command,'plan_sha256':expected,
        'parent_pre_final_export_wall_seconds':time.perf_counter()-BOOT,'native_calls':0,
        'full_wall':'External launch-to-exit envelope must include Python startup and final evidence export. Not full-platform cold start.'}
    write(output/'bounded_execution.json',result)
    return 0 if result['status']=='completed' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pure',type=Path)
    parser.add_argument('--plan-sha256');parser.add_argument('--admission')
    group=parser.add_mutually_exclusive_group(required=True)
    for key in ('prepare','launch','campaign','verify-saved'):group.add_argument('--'+key,action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output,args.pure.resolve());return 0
    if args.launch:return launch(output,args.plan_sha256)
    if args.verify_saved:print(codec.artifact_encode(verify_saved(output)).decode());return 0
    if sys.stdin.readline().strip()!=args.admission:raise ValueError('no_owned_job_admission')
    try:campaign(output,args.plan_sha256)
    except BaseException as error:
        write(output/'failure.json',{'status':'unknown_failed','error':repr(error),'traceback':traceback.format_exc(),'native_calls':0});raise
    return 0


if __name__=='__main__':raise SystemExit(main())
