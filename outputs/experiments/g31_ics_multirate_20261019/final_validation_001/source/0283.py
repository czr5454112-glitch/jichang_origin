"""Prepared-only fixed saved-fixture ABBA tape cost gate. No native invocation.

The sole worker replays eight already-completed API values, never a simulator.
An owned120s Job includes loading, four complete logging batches, readback and
exports. A separate external Stopwatch must include parent Python startup.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
from types import FunctionType
from . import serialize_once_low_wip_tape as candidate
from . import bounded_windows_job

base=candidate.reference
ROOT,OUT=base.ROOT,base.OUT
MODULE='scripts.experiments.g31_ics_circulation.measure_serialize_once_tape'
LIMIT=120.
PURE_TESTS=48
ARMS=('legacy','serialize_once','serialize_once','legacy')
SOURCE_CASE=OUT/'original_cooperative_bridge_prepare_001'
PARTIAL_REVIEW=OUT/'bridge001_terminal_partial_review_001/review.json'
PARTIAL_SHA='0bd6bf3faf488b1fb0e488c6bf2c7f31d1c1e3419d707461bfe6df0bc4c3cbc2'


def require(ok,reason):
    if not ok:raise ValueError('serialize_once_measure:'+reason)


def source_paths():
    entries=[Path(__file__),Path(candidate.__file__),ROOT/'tests/test_g31_circulation_serialize_once_tape.py',
             ROOT/'tests/test_g31_circulation_serialize_once_measure.py']
    found=set()
    for entry in entries:
        function=FunctionType(base.source_paths.__code__,{**base.source_paths.__globals__,'__file__':str(entry)},
                              base.source_paths.__name__,base.source_paths.__defaults__,base.source_paths.__closure__)
        found.update(function())
    return sorted(found)


def verify_pins(output,plan,*,runtime=False):
    require(plan['schema']=='g31.serialize_once_tape.fixed8_ABBA.v1' and plan['arms']==list(ARMS)
        and plan['shared_seconds']==LIMIT and plan['native_calls']==0,'scope')
    require(set(plan['source_sha256'])=={str(p.relative_to(ROOT)) for p in source_paths()},'source_domain')
    for rel,digest in plan['source_sha256'].items():
        require(base.sha(ROOT/rel)==base.sha(output/'source'/rel)==digest,'source_changed:'+rel)
    require(base.sha(sys.executable)==plan['interpreter']['sha256'],'interpreter')
    require(base.sha(PARTIAL_REVIEW)==PARTIAL_SHA==plan['partial_review']['sha256'],'partial_review')
    require(len(plan['fixtures'])==8 and [r['original_ordinal'] for r in plan['fixtures']]==list(range(27210,27218)),'fixed_tail8')
    for entry in plan['fixtures']:
        require(entry['file']==f"{entry['original_ordinal']:06d}.json.gz"
            and Path(entry['source_path'])==SOURCE_CASE/'bridge/api'/entry['file'],'fixture_path')
        require(base.sha(output/'fixtures'/entry['file'])==base.sha(entry['source_path'])==entry['sha256'],'fixture')
    require(base.sha(plan['tests']['path'])==plan['tests']['sha256'],'tests')
    if runtime:
        loaded={str(Path(module.__file__).resolve().relative_to(ROOT)) for module in list(sys.modules.values())
            if getattr(module,'__file__',None) and Path(module.__file__).suffix=='.py'
            and Path(module.__file__).resolve().is_relative_to(ROOT)}
        require(loaded<=set(plan['source_sha256']),'unarchived_loaded_dependency')


def prepare(output,xml):
    import xml.etree.ElementTree as ET
    require(not output.exists(),'preserve_output')
    require(base.sha(PARTIAL_REVIEW)==PARTIAL_SHA,'review_identity')
    review=base.read(PARTIAL_REVIEW)
    require(review['status']=='verified_hard_timeout_partial_evidence_only' and review['native_executions']==0,'review_scope')
    entries=review['complete_tail_rows_individually_hashed_and_decoded']
    require([r['ordinal'] for r in entries]==list(range(27210,27218)),'eight_complete_tail')
    suites=list(ET.parse(xml).getroot().iter('testsuite'))
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    require(counts['tests']==PURE_TESTS and all(counts[k]==0 for k in ('failures','errors','skipped')),'pure_gate')
    output.mkdir();(output/'fixtures').mkdir()
    fixtures=[]
    for row in entries:
        name=f"{row['ordinal']:06d}.json.gz";src=SOURCE_CASE/'bridge/api'/name
        require(base.sha(src)==row['sha256'],'source_fixture')
        shutil.copyfile(src,output/'fixtures'/name)
        fixtures.append({'file':name,'source_path':str(src),'sha256':row['sha256'],
                         'original_ordinal':row['ordinal'],'endpoint':row['endpoint']})
    sources={str(p.relative_to(ROOT)):base.sha(p) for p in source_paths()}
    for rel in sources:
        target=output/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,target)
    plan={'schema':'g31.serialize_once_tape.fixed8_ABBA.v1','status':'prepared_unexecuted','arms':list(ARMS),
        'fixtures':fixtures,'batches':4,'calls_per_batch':8,'total_mock_calls':32,'native_calls':0,
        'shared_seconds':LIMIT,'source_sha256':sources,'interpreter':{'path':sys.executable,'sha256':base.sha(sys.executable)},
        'partial_review':{'path':str(PARTIAL_REVIEW),'sha256':PARTIAL_SHA},
        'tests':{'path':str(xml.resolve()),'sha256':base.sha(xml),'counts':counts},
        'measurement':'Each batch starts before Tape/clock-file creation and ends after every mock return, input snapshot, JSON, level1gzip, filehash, manifest append and clock append. Fixture loading/decode and independent readback are separate scopes, all retained in total worker/parent wall. Mock deepcopy cost remains included equally.',
        'selection':'The terminal review fixed the last8 complete manifested bridge001 API rows before this performance attempt. The unmanifested truncated27218 row is excluded explicitly, not repaired or measured as complete. No claim this late excerpt represents every endpoint or earlier/later original workload.',
        'clock_nesting':'Per-API capture envelope excludes its subsequent clock write; outer-call envelope includes it. Batch and whole worker retain every gap. Nested durations are never summed as disjoint cost.',
        'same_outputs':'Exact decoded ordered JSON rows; only ordinal is rebased0..7 for the fixed excerpt. Gzip bytes are new and independently hashed, not asserted equal. Original native logical times/results remain data, never execution.',
        'failure':'Any source/fixture/encoding/write/readback error makes the gate unknown, preserving files. No row omission or benchmark retry.',
        'limits':['Only diagnostic logging cost on a fixed retrospective eight-row workload, no native/online/100ms certificate.',
                  'ABBA one process; filesystem cache and same-host variation remain. No new tuning/window selection after measurement.',
                  'Unpaired-surrogate write error offsets/partial bytes can differ; both paths fail without manifest success. Candidate refuses subsequent calls after capture failure.',
                  'No policy cadence, notification, ACK retry, publication, physical capacity or input change.']}
    base.write(output/'plan.json',plan);verify_pins(output,plan)
    ready={'schema':'g31.serialize_once_tape.ready.v1','status':'prepared_unexecuted','output':str(output),
        'plan_sha256':base.sha(output/'plan.json'),'source_count':len(sources),'pure_counts':counts,
        'execute_command':[sys.executable,'-m',MODULE,'--output',str(output),'--execute','--plan-sha256',base.sha(output/'plan.json')],
        'native_calls':0,'benchmark_executed':False,'external_stopwatch_required':True}
    base.write(output/'ready.json',ready);return ready


class FixtureSession:
    def __init__(self,rows):self.rows=rows;self.index=0;self.physical_time=rows[0]['before']
    def __getattr__(self,name):
        def call(*args,**kwargs):
            require(self.index<len(self.rows),'fixture_exhausted');row=self.rows[self.index]
            require(name==row['endpoint'] and self.physical_time==row['before']
                and list(args)==row['args'] and kwargs==row['kwargs'],'fixture_invocation')
            self.index+=1;self.physical_time=row['after']
            # No saved error fixture is included. Exception semantics belong to
            # the functional adversarial gate, not fabricated native evidence.
            require('error' not in row and 'result' in row,'unsupported_error_fixture')
            return deepcopy(row['result'])
        return call


def batch(output,rows,arm):
    require(arm in ARMS,'arm')
    start=time.perf_counter_ns();cpu_start=time.process_time_ns()
    output.mkdir();clock=output/'clocks.jsonl';clock.open('x',encoding='utf8').close()
    session=FixtureSession(rows);cls=base.Tape if arm=='legacy' else candidate.SerializedOnceTape
    tape=cls(session,output/'api');outside=[]
    for ordinal,row in enumerate(rows):
        outer_start=time.perf_counter_ns();capture_start=time.perf_counter_ns()
        getattr(tape,row['endpoint'])(*row['args'],**row['kwargs'])
        item=tape.rows[-1]
        persisted=(tape.directory/item['path']).stat().st_size+len((json.dumps(item)+'\n').encode('utf8'))
        capture_end=time.perf_counter_ns()
        record={'ordinal':ordinal,'endpoint':row['endpoint'],'capture_started_ns':capture_start,
                'capture_finished_ns':capture_end,'persisted_bytes':persisted}
        with clock.open('a',encoding='utf8') as stream:
            text=json.dumps(record,separators=(',',':'),allow_nan=False)+'\n'
            require(stream.write(text)==len(text),'clock_short_write');stream.flush()
        outside.append({'ordinal':ordinal,'started_ns':outer_start,'finished_ns':time.perf_counter_ns()})
    require(session.index==len(rows)==len(tape.rows),'batch_denominator')
    result={'arm':arm,'calls':len(rows),'started_ns':start,'finished_ns':time.perf_counter_ns(),
        'cpu_ns':time.process_time_ns()-cpu_start,'outside_call_envelopes':outside,
        'clock_scope':'Nested capture includes API mock and complete Tape. Outer call also includes clock append; batch includes construction/gaps.',
        'native_calls':0}
    result['wall_ns']=result['finished_ns']-start
    # Summary encoding/export is outside batch but inside the whole worker.
    base.write(output/'batch.json',result);return result


def verify_batch(output,rows,record):
    require(record==base.read(output/'batch.json'),'batch_record')
    manifests=[json.loads(x) for x in (output/'api/manifest.jsonl').read_text().splitlines()]
    clocks=[json.loads(x) for x in (output/'clocks.jsonl').read_text().splitlines()]
    require(len(manifests)==len(clocks)==record['calls']==len(rows)==len(record['outside_call_envelopes']),'readback_count')
    for i,(item,expected,c,outer) in enumerate(zip(manifests,rows,clocks,record['outside_call_envelopes'],strict=True)):
        require(item['path']==f'{i:06d}.json.gz' and base.sha(output/'api'/item['path'])==item['sha256'],'row_hash')
        actual=base.gzread(output/'api'/item['path']);original={**expected,'ordinal':i}
        require(json.dumps(actual,ensure_ascii=False,allow_nan=False)==json.dumps(original,ensure_ascii=False,allow_nan=False),'ordered_row_parity')
        require(c['ordinal']==outer['ordinal']==i and c['endpoint']==item['endpoint']==expected['endpoint'],'clock_identity')
        require(type(c['persisted_bytes']) is int and c['persisted_bytes']==
            (output/'api'/item['path']).stat().st_size+len((json.dumps(item)+'\n').encode('utf8')),'persisted_bytes')
        times=[record['started_ns'],outer['started_ns'],c['capture_started_ns'],c['capture_finished_ns'],outer['finished_ns'],record['finished_ns']]
        require(all(type(t) is int and t>=0 for t in times) and times==sorted(times),'clock_nesting')
        if i:require(record['outside_call_envelopes'][i-1]['finished_ns']<=outer['started_ns'],'clock_order')
    require(type(record['cpu_ns']) is int and record['cpu_ns']>=0 and record['wall_ns']==record['finished_ns']-record['started_ns'],'batch_clock')


def worker(output,admission):
    require(sys.stdin.readline().rstrip('\n')==admission==base.sha(output/'plan.json'),'job_admission')
    started=time.perf_counter_ns();plan=base.read(output/'plan.json');verify_pins(output,plan,runtime=True)
    load_start=time.perf_counter_ns();rows=[base.gzread(output/'fixtures'/f['file']) for f in plan['fixtures']]
    require(all(row['ordinal']==f['original_ordinal'] and row['endpoint']==f['endpoint']
        for row,f in zip(rows,plan['fixtures'],strict=True)),'fixture_metadata')
    load_end=time.perf_counter_ns();records=[]
    for i,arm in enumerate(ARMS):records.append(batch(output/f'{i}.{arm}',rows,arm))
    verify_start=time.perf_counter_ns()
    for i,record in enumerate(records):verify_batch(output/f'{i}.{record["arm"]}',rows,record)
    verify_pins(output,plan,runtime=True);verify_end=time.perf_counter_ns()
    summary={arm:{'batches':2,'sum_ms':sum(r['wall_ns'] for r in records if r['arm']==arm)/1e6,
        'median_ms':statistics.median(r['wall_ns'] for r in records if r['arm']==arm)/1e6} for arm in set(ARMS)}
    result={'schema':plan['schema'],'status':'passed_saved_fixture_ABBA_only','plan_sha256':admission,
        'records':records,'summary':summary,'fixture_load_decode_ns':load_end-load_start,
        'saved_verify_ns':verify_end-verify_start,'worker_before_final_export_ns':time.perf_counter_ns()-started,
        'native_calls':0,'source_changed':[],'complete_100ms_certified':False,'end_to_end_native_speedup_certified':False}
    base.write(output/'result.json',result)


def execute(output,plan_sha):
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:json.dump({'plan_sha256':plan_sha,'never_reuse':True},stream)
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--worker','--plan-sha256',plan_sha]
    process=None;failure=None
    try:
        require(base.sha(output/'plan.json')==plan_sha,'plan_identity');verify_pins(output,base.read(output/'plan.json'),runtime=True)
        remaining=LIMIT-(time.perf_counter()-BOOT);require(remaining>0,'prelaunch_budget')
        with (output/'worker.stdout').open('xb') as stdout,(output/'worker.stderr').open('xb') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=plan_sha,cwd=ROOT)
        if process['status']=='exited' and process['exitcode']==0:
            result=base.read(output/'result.json')
            require(result['status']=='passed_saved_fixture_ABBA_only' and result['plan_sha256']==plan_sha
                and result['source_changed']==[] and result['native_calls']==0,'worker_result')
        require(time.perf_counter()-BOOT<=LIMIT,'total_budget_before_receipt')
    except BaseException as error:failure=repr(error)
    passed=failure is None and process is not None and process['status']=='exited' and process['exitcode']==0 and (output/'result.json').is_file()
    receipt={'schema':'g31.serialize_once_tape.launch.v1','status':'completed' if passed else 'unknown_failed_or_timeout',
        'plan_sha256':plan_sha,'process':process,'error':failure,'command':command,'shared_seconds':LIMIT,
        'parent_after_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'parent_startup_before_BOOT_requires_external_clock':True,
        'native_calls':0,'complete_100ms_certified':False,
        'artifact_sha256':{name:base.sha(output/name) for name in ('result.json','worker.stdout','worker.stderr') if (output/name).is_file()}}
    base.write(output/'launch_receipt.json',receipt)
    return 0 if passed else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--tests-xml',type=Path)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--worker',action='store_true');parser.add_argument('--plan-sha256')
    args=parser.parse_args();output=args.output.resolve()
    require(sum((args.prepare,args.execute,args.worker))==1,'mode')
    if args.prepare:print(json.dumps(prepare(output,args.tests_xml)));return
    if args.worker:worker(output,args.plan_sha256);return
    raise SystemExit(execute(output,args.plan_sha256))

if __name__=='__main__':main()
