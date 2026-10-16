"""One fixed three-tape, three-sink pure comparison; 120-second owned Job."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from . import bounded_windows_job
from . import deferred_service_tape as candidate

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
REFERENCE = OUT / 'original_route_pending_ack_prepare_001'
CASES = ('baseline','drop_first_ack','ack_withheld_in_window')
HASHES = ('09439b3901953205d6d4c7ab73642f9ec06754a3f877be0702b8bfdefe7ff2b8',
          '24f0086c2a36e658a616ced21309306b8ccb6495bd89542e34918cf3d35877ed',
          'a31dc653b759acb9d4f68e0fa78104a7b9fd5c9fde8fb188d52ee883fc32d4f4')
ORDERS = (('immediate','ram','spool'),('spool','ram','immediate'),('immediate','ram','spool'))
SCHEMA = 'g31.deferred_service_tape.pure_cost.v1'
LIMIT = 120.


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)


def sources():
    return sorted(set(candidate.reference.source_paths()) | {Path(__file__).resolve(),Path(candidate.__file__).resolve(),
        Path(bounded_windows_job.__file__).resolve(),ROOT/'tests/test_g31_circulation_deferred_service_tape.py',
        ROOT/'tests/test_g31_circulation_deferred_service_tape_measurement.py'})


def prepare(output):
    if output.exists():raise ValueError('output_exists')
    output.mkdir(parents=True)
    paths=sources(); pins={str(p):sha(p) for p in paths}
    for path in paths:
        target=output/'source_archive'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    cases=[]
    for case,digest,order in zip(CASES,HASHES,ORDERS,strict=True):
        source=REFERENCE/case/'service_tape.jsonl.gz';raw=REFERENCE/case/'raw.json.gz'
        if sha(source)!=digest:raise ValueError('reference_tape_changed')
        metadata=json.loads(gzip.decompress(raw.read_bytes()))
        if metadata['api_sha256']!=digest:raise ValueError('raw_reference_mismatch')
        cases.append({'case':case,'path':str(source),'sha256':digest,'raw_path':str(raw),'raw_sha256':sha(raw),
            'rows':metadata['api_rows'],'arm_order':order,'gzip_isize':int.from_bytes(source.read_bytes()[-4:],'little')})
    plan={'schema':SCHEMA,'status':'pure_prepared_unexecuted','cases':cases,'max_bytes':candidate.MAX_BYTES,
        'max_rows':candidate.MAX_ROWS,'owned_job_seconds':LIMIT,'source_before':pins,
        'interpreter':{'path':sys.executable,'sha256':sha(sys.executable)},
        'scope':'One serial sample for each fixed case/sink. Input decode and JSON serialization remain real costs. Hot write+flush, deferred close, full replay and independent byte readback measured separately. No native or business-request timing claim.',
        'native_executions':0,'proof':candidate.unchanged_invocation_proof()}
    write(output/'plan.json',plan);verify(output,plan);return plan


def verify(output,plan):
    if (plan['schema']!=SCHEMA or len(plan['cases'])!=3 or plan['max_bytes']!=candidate.MAX_BYTES
            or plan['max_rows']!=candidate.MAX_ROWS or plan['owned_job_seconds']!=LIMIT):raise ValueError('plan_scope')
    for index,row in enumerate(plan['cases']):
        if (row['case']!=CASES[index] or tuple(row['arm_order'])!=ORDERS[index]
                or row['sha256']!=HASHES[index] or Path(row['path'])!=REFERENCE/CASES[index]/'service_tape.jsonl.gz'
                or type(row['rows']) is not int or not 0<row['rows']<=candidate.MAX_ROWS):raise ValueError('case_scope')
        if sha(row['path'])!=row['sha256'] or sha(row['raw_path'])!=row['raw_sha256']:raise ValueError('input_drift')
        raw=json.loads(gzip.decompress(Path(row['raw_path']).read_bytes()))
        if raw['api_rows']!=row['rows'] or raw['api_sha256']!=row['sha256']:raise ValueError('row_count_drift')
    if plan['source_before']!={str(p):sha(p) for p in sources()}:raise ValueError('source_drift')
    for path,digest in plan['source_before'].items():
        if sha(output/'source_archive'/Path(path).relative_to(ROOT))!=digest:raise ValueError('archive_drift')
    if sha(plan['interpreter']['path'])!=plan['interpreter']['sha256']:raise ValueError('interpreter_drift')


def measure(source,path,mode,expected_rows):
    began=time.perf_counter_ns();source_digest=hashlib.sha256();count=byte_count=0
    decode_ns=encode_ns=write_flush_ns=0
    stream=gzip.open(path,'wt',encoding='utf8',compresslevel=1) if mode=='immediate' else candidate.EncodedSink(path,mode=mode)
    try:
        with gzip.open(source,'rb') as incoming:
            for line in incoming:
                source_digest.update(line);byte_count+=len(line)
                t=time.perf_counter_ns();row=json.loads(line);decode_ns+=time.perf_counter_ns()-t
                if type(row) is not dict or row.get('ordinal')!=count:raise ValueError('input_ordinal_or_row_type')
                t=time.perf_counter_ns();text=json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n';encode_ns+=time.perf_counter_ns()-t
                # Assert byte-for-byte compatibility, not merely JSON equality.
                if text.replace('\n',os.linesep).encode('utf8')!=line:raise ValueError('reference_line_encoding_changed')
                t=time.perf_counter_ns();stream.write(text);stream.flush();write_flush_ns+=time.perf_counter_ns()-t
                count+=1
        if count!=expected_rows:raise ValueError('row_denominator')
    finally:
        close_began=time.perf_counter_ns();report=stream.close();close_ns=time.perf_counter_ns()-close_began
    replay_ns=time.perf_counter_ns()-began
    if mode!='immediate' and not report['evidence_complete']:raise ValueError('incomplete_candidate_capture')
    verified_began=time.perf_counter_ns();actual=hashlib.sha256();readback_bytes=0
    with gzip.open(path,'rb') as saved:
        for chunk in iter(lambda:saved.read(1024*1024),b''):actual.update(chunk);readback_bytes+=len(chunk)
    if actual.digest()!=source_digest.digest() or readback_bytes!=byte_count:raise ValueError('decompressed_bytes_mismatch')
    if mode=='spool' and sha(stream.spool_path)!=source_digest.hexdigest():raise ValueError('spool_prefix_bytes_mismatch')
    return {'mode':mode,'rows':count,'bytes':byte_count,'decompressed_sha256':actual.hexdigest(),
        'input_decode_ns':decode_ns,'json_encode_ns':encode_ns,'write_flush_ns':write_flush_ns,
        'hot_json_write_flush_ns':encode_ns+write_flush_ns,'deferred_close_ns':close_ns,
        'full_replay_ns':replay_ns,'readback_verification_ns':time.perf_counter_ns()-verified_began,
        'gzip_sha256':sha(path),'gzip_bytes':Path(path).stat().st_size,
        'capture':report if mode!='immediate' else None,'all_values_and_row_order_exact':True}


def worker(output):
    began=time.perf_counter();plan=json.loads((output/'plan.json').read_text());plan_hash=sha(output/'plan.json');verify(output,plan)
    ledger=[]
    for case in plan['cases']:
        for arm in case['arm_order']:
            path=output/(case['case']+'.'+arm+'.jsonl.gz')
            result=measure(case['path'],path,arm,case['rows']);result['case']=case['case'];ledger.append(result)
            write(output/('sample_%02d.json'%len(ledger)),result)
            print(json.dumps({'completed_sample':len(ledger),'case':case['case'],'mode':arm,
                'hot_seconds':result['hot_json_write_flush_ns']/1e9,'close_seconds':result['deferred_close_ns']/1e9,
                'replay_seconds':result['full_replay_ns']/1e9}),flush=True)
    verify(output,plan)
    if sha(output/'plan.json')!=plan_hash or len(ledger)!=9:raise ValueError('final_denominator_or_plan')
    write(output/'report.json',{'schema':SCHEMA,'status':'completed_exact_pure_sink_comparison','plan_sha256':plan_hash,
        'samples':ledger,'source_changed':[],'native_executions':0,'wall_seconds':time.perf_counter()-began,
        'limits':['One serial sample per arm and case; order/cache/background effects are not controlled.','RAM is not suitable for native hard-kill prefix retention; only spool retains each flushed uncompressed prefix.','Hot JSON serialization remains charged. Deferred compression/output/readback remain complete experiment cost.','Full replay includes source decode and independent encoding equality checks; it is not a prediction of native warm request latency.','No retrospective cost subtraction or complete100ms claim.']})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--launch',action='store_true');group.add_argument('--worker',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output);print(sha(output/'plan.json'));return
    if args.worker:
        if sys.stdin.readline().strip()!=sha(output/'plan.json'):raise ValueError('job_admission')
        try:worker(output)
        except BaseException as error:
            write(output/'failure.json',{'status':'unknown_failed_pure_comparison','error':repr(error),'traceback':traceback.format_exc(),'native_executions':0});raise
        return
    if any((output/n).exists() for n in ('stdout.log','stderr.log','process.json')):raise ValueError('execution_already_claimed')
    token=sha(output/'plan.json');command=[sys.executable,'-m',__package__+'.measure_deferred_service_tape','--output',str(output),'--worker']
    began=time.perf_counter()
    with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
        result=bounded_windows_job.run(command,timeout=LIMIT,stdout=stdout,stderr=stderr,admission=token,cwd=str(ROOT))
    write(output/'process.json',{**result,'command':command,'plan_sha256':token,'outer_elapsed_before_receipt_seconds':time.perf_counter()-began,'native_executions':0})
    if result['status']!='exited' or result['exitcode']!=0:raise SystemExit(1)


if __name__=='__main__':main()
