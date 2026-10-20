"""Prepared fixed16 saved-text actor-copy diagnostic; no policy/native replay."""
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
import xml.etree.ElementTree as ET
from . import measure_bridge_saved_kernels as frozen
from . import bounded_windows_job

ROOT, OUT = frozen.ROOT, frozen.OUT
SOURCE = OUT/'bridge_saved_kernel_cost_prepare_001'
SOURCE_PLAN_SHA = '0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc'
READBACK = OUT/'bridge_saved_kernel_cost_readback_001/report.json'
READBACK_SHA = '0df9dba718be1f555142711d168fc45a42cdb3717e4cee3100a8f76ce47b8c66'
SCHEMA = 'g31.bridge.actor_second_parse.fixed16.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.measure_bridge_actor_reparse'
TEST = 'tests/test_g31_circulation_bridge_actor_reparse.py'
LIMIT, MAX_TEXT = 120.0, 64*1024*1024
ARMS = ('A', 'B', 'B', 'A')
COUNTS = {'input_files':16, 'batches':4, 'actor_copies':64, 'A_deepcopies':32,
          'B_second_parses':32, 'first_observer_parses':16}
PURE_TESTS = 50
_LOADS, _LOAD = json.loads, json.load
require, sha, write, encoded = frozen.require, frozen.sha, frozen.write, frozen.encoded


def actor_copy(observer_row, text):
    return deepcopy(observer_row['result'])


def actor_reparse(observer_row, text):
    # No encode and no read of a new file. Same immutable text as first parse;
    # no object hooks, altered numeric parsers or snapshot/result cache.
    return json.loads(text)['result']


def decoded_text(text):
    require(type(text) is str and len(text) <= MAX_TEXT, 'actor_text_domain')
    row = json.loads(text)  # Same standard defaults as frozen base.gzread.
    frozen.decoded_tree(row)
    require(type(row) is dict and 'result' in row and 'error' not in row, 'actor_row_domain')
    return row


def load_fixture(path, item):
    # This is the original gzip text reader and default JSON parser, split only
    # so the exact text can remain private for the second standard parse.
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        text = stream.read(MAX_TEXT+1)
    row = decoded_text(text)
    require(type(row.get('ordinal')) is int and row['ordinal'] == item['ordinal']
        and type(row.get('endpoint')) is str and row['endpoint'] == item['endpoint'], 'actor_first_identity')
    return row, text


def source_paths():
    result = set()
    for entry in (Path(__file__), ROOT/TEST):
        function = frozen.linear.r.original.clone(frozen.base.source_paths,
            {**frozen.base.source_paths.__globals__, '__file__': str(entry)})
        result.update(function())
    return sorted(result)


def verify_pins(output, plan, runtime=False):
    require(plan['schema'] == SCHEMA and frozen.exact(plan['arms'], list(ARMS))
        and frozen.exact(plan['shared_seconds'], LIMIT) and frozen.exact(plan['counts'], COUNTS), 'actor_plan_scope')
    require(sha(SOURCE/'plan.json') == SOURCE_PLAN_SHA and sha(READBACK) == READBACK_SHA, 'actor_prior_authority')
    prior = frozen.strict_loads((SOURCE/'plan.json').read_text(encoding='utf8'))
    frozen.verify_pins(SOURCE, prior)
    require(frozen.exact(plan['files'], prior['files']), 'actor_exact_fixed_inputs')
    require(plan['original_plan_sha256'] == SOURCE_PLAN_SHA and plan['saved_readback_sha256'] == READBACK_SHA, 'actor_plan_reference')
    require(set(plan['sources']) == {str(p.relative_to(ROOT)) for p in source_paths()}, 'actor_source_domain')
    for rel, digest in plan['sources'].items():
        require(sha(ROOT/rel) == sha(output/'source'/rel) == digest, 'actor_source_changed:'+rel)
    for item in plan['files']:
        require(sha(output/'fixtures'/item['file']) == item['sha256'], 'actor_fixture_changed')
    require(sha(sys.executable) == plan['interpreter_sha256'], 'actor_interpreter_changed')
    for key, digest_key in (('xml', 'xml_sha256'), ('receipt', 'receipt_sha256')):
        require(sha(plan['pure'][key]) == plan['pure'][digest_key], 'actor_pure_changed')
    require(frozen.exact(plan['pure']['counts'], {'tests':PURE_TESTS,'failures':0,'errors':0,'skipped':0}), 'actor_fixed_pure_denominator')
    require(json.loads is _LOADS and json.load is _LOAD, 'actor_standard_decoder_changed')
    if runtime:
        loaded = {str(Path(m.__file__).resolve().relative_to(ROOT)) for m in list(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
            and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded <= set(plan['sources']), 'actor_unpinned_runtime_import')


def prepare(output, xml, receipt):
    require(not output.exists(), 'actor_preserve_output')
    require(sha(SOURCE/'plan.json') == SOURCE_PLAN_SHA and sha(READBACK) == READBACK_SHA, 'actor_reference')
    prior = frozen.strict_loads((SOURCE/'plan.json').read_text(encoding='utf8'))
    frozen.verify_pins(SOURCE, prior)
    counts = {key: sum(int(s.get(key, 0)) for s in ET.parse(xml).getroot().iter('testsuite'))
              for key in ('tests', 'failures', 'errors', 'skipped')}
    require(counts == {'tests':PURE_TESTS,'failures':0,'errors':0,'skipped':0}, 'actor_pure_counts')
    pure = frozen.strict_loads(receipt.read_text(encoding='utf8'))
    require(pure['exitcode'] == 0 and pure['source_changed'] == []
        and pure['actual_raw_reads'] == pure['performance_runs'] == pure['native_calls'] == 0, 'actor_pure_receipt')
    output.mkdir(); (output/'fixtures').mkdir()
    for item in prior['files']:
        shutil.copyfile(SOURCE/'fixtures'/item['file'], output/'fixtures'/item['file'])
    sources = {str(p.relative_to(ROOT)): sha(p) for p in source_paths()}
    for rel in sources:
        destination = output/'source'/rel; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/rel, destination)
    plan = {'schema':SCHEMA, 'status':'prepared_unexecuted', 'arms':list(ARMS), 'shared_seconds':LIMIT,
        'original_plan_sha256':SOURCE_PLAN_SHA, 'saved_readback_sha256':READBACK_SHA,
        'files':prior['files'], 'sources':sources, 'interpreter_sha256':sha(sys.executable),
        'pure':{'xml':str(xml.resolve()),'xml_sha256':sha(xml),'receipt':str(receipt.resolve()),
            'receipt_sha256':sha(receipt),'counts':counts},
        'counts':dict(COUNTS),
        'scope':'Fixed original old/new tail8 only. No raw_final, native, predictor, policy or full-audit run.',
        'A':'deepcopy(observer_row[result])', 'B':'json.loads(the_same_decompressed_text)[result], standard defaults, no dumps',
        'first_read':'gzip.open(path, rt, encoding=utf8).read then standard json.loads, identical to json.load(stream) in original base.gzread. Both default text newline behavior and decoding options retained.',
        'domain':'The first private parsed row is proved a finite builtin string-key JSON tree without mutable alias/cycles/surrogates. This precondition is diagnostic-only, not a new default full-audit loader guard.',
        'clocks':'Initial16 decompressions/parses/domain proof are separately timed and retained in whole wall. Per-call A/B includes its full operation/return, including B second full-row parse and discarded fields. Both use the same preloaded observer rows. No first-parse or codec work is subtracted from whole wall.',
        'output_checks':'Each of64 actor results must preserve full type/order/float.hex and be mutable-disjoint from observer and all other observer trees. Inputs/text remain fingerprint-identical. All records remain, no retry/filter.',
        'failure':'Mismatch, exception, drift or timeout remains unknown with written prefix; no audit default changes.',
        'native_calls':0,'policy_replays':0,'full_audit_accepted':False}
    write(output/'plan.json', plan); verify_pins(output, plan)
    ready = {'schema':SCHEMA+'.ready','status':'prepared_unexecuted','output':str(output),
        'plan_sha256':sha(output/'plan.json'),'source_count':len(sources),'pure_counts':counts,
        'execute_command':[sys.executable,'-m',MODULE,'--output',str(output),'--execute','--plan-sha256',sha(output/'plan.json')],
        'external_whole_python_clock_required':True,'new_performance_executed':False,'native_calls':0}
    write(output/'ready.json', ready); return ready


def check_records(records, digests):
    require(type(digests) is list and len(digests) == 16 and all(type(d) is str and len(d)==64
        and all(c in '0123456789abcdef' for c in d) for d in digests), 'actor_digest_domain')
    require(type(records) is list and len(records) == 64 and all(type(r) is dict for r in records), 'actor_record_domain')
    expected = [(batch, arm, index) for batch, arm in enumerate(ARMS) for index in range(16)]
    require([(r['batch'],r['arm'],r['index']) for r in records] == expected, 'actor_denominator_order')
    previous = -1
    for row in records:
        require(set(row) == {'batch','arm','index','ordinal','side','started_ns','finished_ns','wall_ns',
            'cpu_ns','result_sha256','mutable_disjoint'}, 'actor_record_fields')
        require(all(type(row[k]) is int and row[k] >= 0 for k in ('batch','index','ordinal','started_ns','finished_ns','wall_ns','cpu_ns')), 'actor_clock_type')
        require(row['ordinal'] == 27210+row['index']%8 and row['side'] == ('old' if row['index']<8 else 'new'), 'actor_identity')
        require(previous <= row['started_ns'] <= row['finished_ns']
            and row['wall_ns'] == row['finished_ns']-row['started_ns'], 'actor_clock_order')
        require(row['result_sha256'] == digests[row['index']] and row['mutable_disjoint'] is True
            and 'error' not in row and 'status' not in row, 'actor_result')
        previous = row['finished_ns']
    return {arm:{'batch_ms':[sum(r['wall_ns'] for r in records if r['batch']==batch)/1e6
                    for batch, chosen in enumerate(ARMS) if chosen==arm],
        'median_batch_ms':statistics.median(sum(r['wall_ns'] for r in records if r['batch']==batch)/1e6
                    for batch, chosen in enumerate(ARMS) if chosen==arm)} for arm in ('A','B')}


def check_saved_result(result, plan, expected):
    require(result['schema'] == SCHEMA and result['status']=='passed_fixed_saved_actor_parse_diagnostic_only'
        and result['plan_sha256']==expected and frozen.exact(result['counts'],COUNTS)
        and result['source_changed']==[] and type(result['native_calls']) is int and result['native_calls']==0
        and type(result['policy_replays']) is int and result['policy_replays']==0
        and result['full_audit_accepted'] is False, 'actor_saved_scope')
    require(all(type(result[key]) is int and result[key]>=0 for key in
        ('first_decompression_parse_domain_ns','worker_before_final_export_ns'))
        and result['first_decompression_parse_domain_ns']<=result['worker_before_final_export_ns'], 'actor_saved_clock')
    require(type(result['input_texts']) is list and len(result['input_texts'])==16, 'actor_saved_text_count')
    for row, item in zip(result['input_texts'],plan['files'],strict=True):
        require(type(row) is dict and set(row)=={'side','ordinal','gzip_sha256','decoded_text_sha256','decoded_characters'}
            and type(row['ordinal']) is int and row['ordinal']==item['ordinal'] and row['side']==item['side']
            and row['gzip_sha256']==item['sha256'] and type(row['decoded_characters']) is int
            and 0<=row['decoded_characters']<=MAX_TEXT and type(row['decoded_text_sha256']) is str
            and len(row['decoded_text_sha256'])==64 and all(c in '0123456789abcdef' for c in row['decoded_text_sha256']), 'actor_saved_text_binding')
    require(frozen.exact(check_records(result['records'], result['result_digests']), result['summary']), 'actor_saved_summary')


def worker(output, expected):
    require(sys.stdin.readline().rstrip('\n') == expected == sha(output/'plan.json'), 'actor_owned_admission')
    start = time.perf_counter_ns(); plan = frozen.strict_loads((output/'plan.json').read_text(encoding='utf8'))
    verify_pins(output, plan, runtime=True)
    rows, texts, text_hashes, metadata, digests = [], [], [], [], []
    initial_start = time.perf_counter_ns()
    for item in plan['files']:
        row, text = load_fixture(output/'fixtures'/item['file'], item)
        rows.append(row); texts.append(text)
        text_hashes.append(hashlib.sha256(text.encode('utf8')).hexdigest())
        digests.append(hashlib.sha256(encoded(row['result']).encode('utf8')).hexdigest())
        metadata.append({'side':item['side'],'ordinal':item['ordinal'],'gzip_sha256':item['sha256'],
            'decoded_text_sha256':text_hashes[-1],'decoded_characters':len(text)})
    initial_end = time.perf_counter_ns()
    observer_ids = set().union(*(frozen.decoded_tree(row) for row in rows))
    before = [hashlib.sha256(encoded(row).encode('utf8')).hexdigest() for row in rows]
    records=[]
    try:
        with (output/'measurements.jsonl').open('x',encoding='utf8',newline='\n') as journal:
            for batch, arm in enumerate(ARMS):
                for index, (row,text) in enumerate(zip(rows,texts,strict=True)):
                    evidence={'batch':batch,'arm':arm,'index':index,'ordinal':row['ordinal'],
                              'side':'old' if index<8 else 'new'}
                    begin=time.perf_counter_ns(); cpu=time.process_time_ns()
                    try:
                        result=(actor_copy if arm=='A' else actor_reparse)(row,text)
                        cpu_end=time.process_time_ns(); end=time.perf_counter_ns()
                        evidence.update(started_ns=begin,finished_ns=end,wall_ns=end-begin,cpu_ns=cpu_end-cpu)
                        require(frozen.exact(row['result'],result),'actor_exact_result')
                        require(frozen.decoded_tree(result).isdisjoint(observer_ids),'actor_alias')
                        evidence.update(result_sha256=hashlib.sha256(encoded(result).encode('utf8')).hexdigest(),mutable_disjoint=True)
                    except BaseException as error:
                        evidence.update(status='unknown_failed',error=repr(error),started_ns=begin,failure_observed_ns=time.perf_counter_ns())
                        journal.write(encoded(evidence)+'\n');journal.flush();raise
                    line=encoded(evidence)+'\n';require(journal.write(line)==len(line),'actor_short_journal');journal.flush()
                    records.append(evidence);del result
        require(before == [hashlib.sha256(encoded(row).encode('utf8')).hexdigest() for row in rows]
            and text_hashes == [hashlib.sha256(text.encode('utf8')).hexdigest() for text in texts], 'actor_input_mutation')
        saved=[frozen.strict_loads(line) for line in (output/'measurements.jsonl').read_text(encoding='utf8').splitlines()]
        require(frozen.exact(records,saved),'actor_saved_records')
        summary=check_records(saved,digests);verify_pins(output,plan,runtime=True)
        write(output/'result.json',{'schema':SCHEMA,'status':'passed_fixed_saved_actor_parse_diagnostic_only',
            'plan_sha256':expected,'records':saved,'summary':summary,'input_texts':metadata,'result_digests':digests,
            'first_decompression_parse_domain_ns':initial_end-initial_start,
            'worker_before_final_export_ns':time.perf_counter_ns()-start,'source_changed':[],
            'counts':plan['counts'],'native_calls':0,'policy_replays':0,'full_audit_accepted':False})
    except BaseException as error:
        write(output/'failure.json',{'status':'unknown_failed','error':repr(error),'elapsed_ns':time.perf_counter_ns()-start})
        raise


def execute(output, expected):
    write(output/'execution_claim.json',{'plan_sha256':expected,'never_reuse':True})
    process=None;error=None
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--worker','--plan-sha256',expected]
    try:
        require(sha(output/'plan.json')==expected,'actor_plan_identity')
        plan=frozen.strict_loads((output/'plan.json').read_text(encoding='utf8'));verify_pins(output,plan,runtime=True)
        remaining=LIMIT-(time.perf_counter()-BOOT);require(remaining>0,'actor_prelaunch_budget')
        with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=expected,cwd=ROOT)
        require(process['status']=='exited' and process['exitcode']==0,'actor_worker_exit')
        result=frozen.strict_loads((output/'result.json').read_text(encoding='utf8'))
        check_saved_result(result, plan, expected)
        verify_pins(output, plan, runtime=True)
        require(time.perf_counter()-BOOT<=LIMIT,'actor_whole_budget')
    except BaseException as failure:error=repr(failure)
    write(output/'launch_receipt.json',{'schema':SCHEMA+'.launch','status':'completed' if error is None else 'unknown_failed_or_timeout',
        'process':process,'command':command,'error':error,'plan_sha256':expected,'shared_seconds':LIMIT,
        'after_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'external_whole_python_clock_required':True,
        'artifacts':{p.name:sha(p) for p in (output/'result.json',output/'measurements.jsonl',output/'stdout.log',output/'stderr.log') if p.exists()},
        'native_calls':0,'policy_replays':0})
    return 0 if error is None else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--tests-xml',type=Path);p.add_argument('--pure-receipt',type=Path)
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--plan-sha256')
    a=p.parse_args();output=a.output.resolve();require(sum((a.prepare,a.execute,a.worker))==1,'actor_mode')
    if a.prepare:print(encoded(prepare(output,a.tests_xml,a.pure_receipt)));return 0
    if a.worker:worker(output,a.plan_sha256);return 0
    return execute(output,a.plan_sha256)


if __name__=='__main__':raise SystemExit(main())
