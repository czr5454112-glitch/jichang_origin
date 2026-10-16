"""Fixed two historical captures: original versus independent batched writer.

No performance execution during preparation. Four complete byte encodings
precede the32 measured digest calls and remain inside the same owned120 budget.
All candidate preflight work is inside B; policy authority is not replayed.
"""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import gc
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET

from . import measure_planning_v2_digest_v2 as base
from . import planning_capture_v2_batched_digest as candidate

ROOT, OUT = base.ROOT, base.OUT
MODULE='scripts.experiments.g31_ics_circulation.measure_planning_v2_batched_digest_cost'
LAUNCHER='scripts.experiments.g31_ics_circulation.launch_planning_v2_batched_digest_cost'
PURE='scripts.experiments.g31_ics_circulation.run_planning_v2_batched_digest_cost_pure'
TEST='tests/test_g31_circulation_planning_v2_batched_digest_cost.py'
SOURCE_TEST='tests/test_g31_circulation_planning_v2_batched_digest.py'
PRIOR=OUT/'planning_v2_digest_prepare_002/plan.json'
PRIOR_SHA='f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187'
SOURCE_PLAN=OUT/'planning_v2_batched_digest_source_prepare_001/plan.json'
SOURCE_PLAN_SHA='b0d8e8a85cabdbd9c658c539d4fbd59fbcbca0cebfd8b8dc747d689a927f3ea5'
SCHEMA='g31.planning_v2_batched_digest.fixed_two_cost.v1'
ARMS=('A','B','B','A')
LIMIT=120.
REPETITIONS=4
PURE_TESTS=123  # Unchanged75 writer cases plus48 focused harness guards.
require, sha, encoded, loads, write = base.require, base.sha, base.encoded, base.loads, base.write
_ORIGINAL=base.original.capture_digest_v2
_CANDIDATE=candidate.capture_digest_v2


def source_files():
    return base.image.source_closure(ROOT, (MODULE,LAUNCHER,PURE,
        'tests.'+Path(TEST).stem,'tests.'+Path(SOURCE_TEST).stem,
        'scripts.experiments.g31_ics_circulation.run_planning_v2_batched_digest_pure'))


def counts_for(metadata):
    old=base.counts_for(metadata)
    require([m['ordinal'] for m in metadata]==[27212,27215]
        and [m['envelope_count'] for m in metadata]==[1,1], 'fixed_two_single_envelopes')
    return {'query_rows':2,'envelopes':2,'batches':8,'repetitions_per_batch':4,
        'measured_digest_calls':old['digest_calls'],'A_digest_calls':16,'B_digest_calls':16,
        'additional_complete_byte_encoder_calls':4,'total_typed_encoder_runs':36,'profiles':0}


def proof():
    require(_ORIGINAL is base.original.capture_digest_v2 and _CANDIDATE is candidate.capture_digest_v2,
        'candidate_call_identity')
    return {'candidate':candidate.source_proof(),'A_original':base.source_proof(),
        'B_preflight_inside_callable':True,'original_75_source_unchanged':True,
        'oracle_output_is_complete_typed_bytes':True,'policy_authority_replayed':False}


def reference_plan():
    require(sha(PRIOR)==PRIOR_SHA and sha(SOURCE_PLAN)==SOURCE_PLAN_SHA,'prior_source_plan_pin')
    old=loads(PRIOR.read_bytes()); source=loads(SOURCE_PLAN.read_bytes())
    counts_for(old['fixture_metadata'])
    for rel,ref in source['source_pins'].items():
        require(sha(ROOT/rel)==sha(ref['archive'])==ref['sha256'],'frozen_75_source:'+rel)
    for name in ('path','XML_path'):
        expected='sha256' if name=='path' else 'XML_sha256'
        require(sha(source['pure'][name])==source['pure'][expected],'original_75_pure')
    return old


def verify_pins(output, plan, *, runtime=False):
    old=reference_plan()
    require(plan['schema']==SCHEMA and plan['arms']==list(ARMS)
        and type(plan['shared_seconds']) is float and plan['shared_seconds']==LIMIT,
        'cost_plan_scope')
    require(encoded(plan['counts'])==encoded(counts_for(plan['fixture_metadata']))
        and encoded(plan['files'])==encoded(old['files'])
        and encoded(plan['fixture_metadata'])==encoded(old['fixture_metadata']), 'actual_fixed_inputs')
    files=source_files(); require(set(files)==set(plan['sources']),'source_domain')
    for rel,data in files.items():
        require(base.sha_bytes(data)==sha(output/'source'/rel)==plan['sources'][rel],'source_pin:'+rel)
    for item in plan['files']:
        require(sha(item['source'])==sha(output/'fixtures'/item['file'])==item['sha256'],'compressed_pin')
    for ref in plan['pure'].values(): require(sha(ref['path'])==ref['sha256'],'pure_pin')
    require(sha(sys.executable)==plan['interpreter_sha256'] and sys.version==plan['python_version'],
        'interpreter_identity')
    require(encoded(proof())==encoded(plan['source_proof']),'cost_source_proof')
    if runtime:
        loaded={Path(m.__file__).resolve().relative_to(ROOT).as_posix() for m in list(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'
            and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded<=set(plan['sources']),'runtime_loaded_domain')


def prepare(output, pure):
    require(output.is_dir() and not (output/'plan.json').exists(),'prepare_directory')
    r=loads((pure/'receipt.json').read_bytes()); tests=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
    require(r['status']=='passed' and r['source_changed']==[] and len(tests)==PURE_TESTS
        and not any(x.tag in ('failure','error','skipped') for t in tests for x in t)
        and r['XML_sha256']==sha(pure/'tests.xml') and r['real_raw_reads']==r['benchmark_runs']==0,
        'cost_pure_gate')
    files=source_files(); require(set(files)==set(r['source_sha256']),'tested_source_domain')
    for rel,data in files.items():
        require(base.sha_bytes(data)==r['source_sha256'][rel],'tested_source_drift')
        target=output/'source'/rel; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    old=reference_plan(); (output/'fixtures').mkdir()
    for item in old['files']:
        data=Path(item['source']).read_bytes()
        require(len(data)==item['bytes'] and base.sha_bytes(data)==item['sha256'],'prepare_compressed_pin')
        (output/'fixtures'/item['file']).write_bytes(data)
    plan={'schema':SCHEMA,'status':'prepared_unexecuted','arms':list(ARMS),'shared_seconds':LIMIT,
        'files':old['files'],'fixture_metadata':old['fixture_metadata'],'counts':counts_for(old['fixture_metadata']),
        'prior_plan_sha256':PRIOR_SHA,'source_plan_sha256':SOURCE_PLAN_SHA,
        'sources':{rel:base.sha_bytes(data) for rel,data in files.items()},
        'source_proof':proof(),'interpreter_sha256':sha(sys.executable),'python_version':sys.version,
        'pure':{name:{'path':str((pure/file).resolve()),'sha256':sha(pure/file)}
            for name,file in (('receipt','receipt.json'),('xml','tests.xml'))},
        'preparation':{'raw_decodes':0,'typed_encoder_calls':0,'digest_calls':0,
            'scope':'Only compressed copies/hashes and already-bound complete metadata; runtime rederives all raw/metadata.'},
        'scope':'Two fixed historical v2 captures, all envelopes. No native/model/fullpolicy/100ms/whole600 claim.',
        'oracle':'4 additional complete typed encodings before measurements; full byte equality and native SHA required; all oracle work/export/readback charged to the same120.',
        'arms_explanation':'A original unprofiled; B exact independent batched candidate including full per-call builtin preflight and grouping guards. No cProfile, forced GC or eliminated B checking.',
        'clocks':'Nested callable span includes B preflight. Whole includes startup/binding/input/guards/36encoder runs/journal/fullbyte exports/readback/cleanup; external launch-to-exit receipt required.',
        'failure':'Any mismatch/unsupported fast oracle/exception/drift/timeout unknown; preserve prefix, no retry/filter/cap increase.'}
    write(output/'plan.json',plan);verify_pins(output,plan,runtime=True)
    write(output/'ready.json',{'schema':SCHEMA+'.ready','status':'prepared_unexecuted',
        'output':str(output.resolve()),'plan_sha256':sha(output/'plan.json'),
        'execute_command':[sys.executable,'-m',LAUNCHER,'--execute','--output',str(output.resolve()),
            '--plan-sha256',sha(output/'plan.json')], 'external_launch_to_exit_required':True,'performance_executed':False})


def binary_name(ordinal, envelope, arm):return f'typed_{ordinal}_{envelope}_{arm}.bin'


def oracle(output, envelope, owner, meta, ordinal):
    started=time.perf_counter_ns()
    require(encoded(base.envelope_metadata(envelope,owner,meta['envelope_ordinal']))==encoded(meta),'oracle_input')
    begin_a=time.perf_counter_ns(); a=candidate.reference_bytes_v2(envelope['capture']);end_a=time.perf_counter_ns()
    # No fallback here: this fixed experiment must actually exercise the fast
    # path. The complete byte array is compared before either SHA is trusted.
    begin_b=time.perf_counter_ns(); b=bytes(candidate._fast_buffer(envelope['capture']));end_b=time.perf_counter_ns()
    require(type(a) is bytes and type(b) is bytes and a==b,'complete_typed_bytes_differ')
    require(len(a)<=base.MAX_RAW and base.sha_bytes(a)==base.sha_bytes(b)==meta['payload_sha256'],
        'oracle_native_SHA')
    files={}
    for arm,data in (('A',a),('B',b)):
        name=binary_name(ordinal,meta['envelope_ordinal'],arm)
        with (output/name).open('xb') as f: require(f.write(data)==len(data),'oracle_short_write')
        files[arm]={'name':name,'bytes':len(data),'sha256':base.sha_bytes(data)}
    require(encoded(base.envelope_metadata(envelope,owner,meta['envelope_ordinal']))==encoded(meta),'oracle_mutation')
    finished=time.perf_counter_ns()
    return {'ordinal':ordinal,'envelope_ordinal':meta['envelope_ordinal'],'started_ns':started,
        'A_started_ns':begin_a,'A_finished_ns':end_a,'B_started_ns':begin_b,'B_finished_ns':end_b,
        'finished_ns':finished,'whole_ns':finished-started,'files':files,
        'complete_bytes_equal':True,'candidate_fast_path':True,'body_sha256':meta['body_sha256']}


def check_oracles(output, oracles, metadata):
    expected=[(m['ordinal'],i) for m in metadata for i in range(m['envelope_count'])]
    require(type(oracles) is list and [(o['ordinal'],o['envelope_ordinal']) for o in oracles]==expected,
        'oracle_denominator_or_order')
    metas={m['ordinal']:m for m in metadata};previous=-1
    for row in oracles:
        require(type(row['ordinal']) is int and type(row['envelope_ordinal']) is int
            and row['envelope_ordinal']>=0,'oracle_index_type')
        meta=metas[row['ordinal']]['envelopes'][row['envelope_ordinal']]
        times=[row[k] for k in ('started_ns','A_started_ns','A_finished_ns','B_started_ns','B_finished_ns','finished_ns')]
        require(all(type(v) is int and v>=0 for v in times) and previous<=times[0]
            and times==sorted(times) and type(row['whole_ns']) is int and row['whole_ns']==times[-1]-times[0],
            'oracle_clocks')
        require(row['complete_bytes_equal'] is True and row['candidate_fast_path'] is True
            and row['body_sha256']==meta['body_sha256'] and list(row['files'])==['A','B'],'oracle_proof')
        actual=[]
        for arm in ('A','B'):
            ref=row['files'][arm];name=binary_name(row['ordinal'],row['envelope_ordinal'],arm)
            require(ref['name']==name and type(ref['bytes']) is int and 0<ref['bytes']<=base.MAX_RAW,'oracle_binary_ref')
            with (output/name).open('rb') as f:data=f.read(base.MAX_RAW+1)
            require(len(data)==ref['bytes'] and base.sha_bytes(data)==ref['sha256']==meta['payload_sha256'],
                'oracle_binary_identity')
            actual.append(data)
        require(actual[0]==actual[1],'saved_complete_bytes_differ')
        previous=times[-1]
    return {'complete_byte_pairs':len(oracles),'encoder_runs':2*len(oracles),'all_full_bytes_equal':True}


def measure_one(envelope, owner, meta, arm):
    started=time.perf_counter_ns();require(arm in ('A','B'),'cost_arm')
    require(encoded(base.envelope_metadata(envelope,owner,meta['envelope_ordinal']))==encoded(meta),'measure_input')
    begin=time.perf_counter_ns()
    value=(_ORIGINAL if arm=='A' else _CANDIDATE)(envelope['capture'])
    end=time.perf_counter_ns();require(value==meta['payload_sha256'],'measured_native_digest')
    require(encoded(base.envelope_metadata(envelope,owner,meta['envelope_ordinal']))==encoded(meta),'measure_mutation')
    finished=time.perf_counter_ns()
    return {'started_ns':started,'digest_started_ns':begin,'digest_finished_ns':end,'checked_ns':finished,
        'digest_ns':end-begin,'guard_and_check_ns':begin-started+finished-end,
        'digest':value,'body_sha256':meta['body_sha256'],'guards_passed':True}


def check_records(records, batches, metadata):
    require(type(records) is list and [(r['ordinal'],r['batch'],r['arm'],r['repeat'],r['envelope_ordinal'])
        for r in records]==base.expected_order(metadata),'measurement_order_or_count')
    require(type(batches) is list and [(b['ordinal'],b['batch'],b['arm']) for b in batches]==
        [(m['ordinal'],i,a) for m in metadata for i,a in enumerate(ARMS)],'batch_order_or_count')
    metas={m['ordinal']:m for m in metadata};previous=-1
    for row in records:
        require(all(type(row[k]) is int and row[k]>=0 for k in ('ordinal','batch','repeat','envelope_ordinal')),
            'measurement_index')
        times=[row[k] for k in ('started_ns','digest_started_ns','digest_finished_ns','checked_ns')]
        require(all(type(v) is int and v>=0 for v in times) and previous<=times[0] and times==sorted(times),'measurement_clocks')
        require(type(row['digest_ns']) is int and row['digest_ns']==times[2]-times[1]
            and type(row['guard_and_check_ns']) is int and row['guard_and_check_ns']==times[1]-times[0]+times[3]-times[2],
            'measurement_durations')
        meta=metas[row['ordinal']]['envelopes'][row['envelope_ordinal']]
        require(row['digest']==meta['payload_sha256'] and row['body_sha256']==meta['body_sha256']
            and row['guards_passed'] is True,'measurement_binding');previous=times[-1]
    previous=-1
    for row in batches:
        require(all(type(row[k]) is int and row[k]>=0 for k in ('ordinal','batch','started_ns','finished_ns','whole_ns'))
            and previous<=row['started_ns']<=row['finished_ns']
            and row['whole_ns']==row['finished_ns']-row['started_ns'],'batch_clocks')
        selected=[r for r in records if r['ordinal']==row['ordinal'] and r['batch']==row['batch']]
        require(row['started_ns']<=selected[0]['started_ns'] and selected[-1]['checked_ns']<=row['finished_ns'],
            'batch_containment');previous=row['finished_ns']
    return {'counts':counts_for(metadata),'per_fixture':{
        str(m['ordinal']):{arm:{'digest_median_ms':statistics.median(r['digest_ns'] for r in records
            if r['ordinal']==m['ordinal'] and r['arm']==arm)/1e6,
            'guard_check_median_ms':statistics.median(r['guard_and_check_ns'] for r in records
            if r['ordinal']==m['ordinal'] and r['arm']==arm)/1e6,
            'batch_whole_median_ms':statistics.median(b['whole_ns'] for b in batches
            if b['ordinal']==m['ordinal'] and b['arm']==arm)/1e6}
            for arm in ('A','B')} for m in metadata},
        'scope':'Fixed historical component comparison. B includes all builtin preflight; diagnostic guard costs are not actual delivered-policy costs.'}


def verify_saved(output, plan):
    result=loads((output/'result.json').read_bytes())
    require(result['schema']==SCHEMA+'.result' and result['status']=='completed_fixed_batched_comparison'
        and result['plan_sha256']==sha(output/'plan.json') and result['GC_enabled'] is True,'saved_result')
    records=[loads(line) for line in (output/'measurements.jsonl').read_bytes().splitlines()]
    require(encoded(records)==encoded(result['records']),'journal_binding')
    require(encoded(loads((output/'oracles.json').read_bytes()))==encoded(result['oracles']),'oracle_journal_binding')
    summary=check_records(records,result['batches'],plan['fixture_metadata'])
    require(encoded(summary)==encoded(result['summary']),'saved_summary')
    byte_report=check_oracles(output,result['oracles'],plan['fixture_metadata'])
    require(result['oracles'][-1]['finished_ns']<=result['batches'][0]['started_ns'],'oracle_before_measurements')
    verify_pins(output,plan,runtime=True)
    return {'schema':SCHEMA+'.saved','status':'passed_saved_complete_bytes_and_measurements','summary':summary,
        'byte_oracles':byte_report,'result_sha256':sha(output/'result.json'),
        'journal_sha256':sha(output/'measurements.jsonl'),'extra_encoder_runs_in_saved_review':0}


def execute(output, expected):
    require(sha(output/'plan.json')==expected,'execute_plan_sha')
    write(output/'execution_claim.json',{'one_attempt_only':True,'plan_sha256':expected})
    plan=loads((output/'plan.json').read_bytes());records=[];batches=[];oracles=[];stage='entry'
    try:
        verify_pins(output,plan,runtime=True);require(gc.isenabled(),'default_GC_disabled')
        started=time.perf_counter_ns();stage='complete_fixture_load';rows=base.load_frozen(output,plan)
        loaded=time.perf_counter_ns();stage='complete_byte_oracles'
        for row,metadata in zip(rows,plan['fixture_metadata']):
            for env,meta in zip(row['result'],metadata['envelopes']):
                oracles.append(oracle(output,env,metadata['owner'],meta,row['ordinal']))
        write(output/'oracles.json',oracles)
        stage='measurements'
        with (output/'measurements.jsonl').open('xb') as journal:
            for row,metadata in zip(rows,plan['fixture_metadata']):
                for batch,arm in enumerate(ARMS):
                    begin=time.perf_counter_ns()
                    for repeat in range(REPETITIONS):
                        for env_index,(env,meta) in enumerate(zip(row['result'],metadata['envelopes'])):
                            sample={'ordinal':row['ordinal'],'batch':batch,'arm':arm,'repeat':repeat,
                                'envelope_ordinal':env_index,**measure_one(env,metadata['owner'],meta,arm)}
                            data=encoded(sample)+b'\n';require(journal.write(data)==len(data),'short_journal')
                            journal.flush();records.append(sample)
                    end=time.perf_counter_ns();batches.append({'ordinal':row['ordinal'],'batch':batch,'arm':arm,
                        'started_ns':begin,'finished_ns':end,'whole_ns':end-begin})
        summary=check_records(records,batches,plan['fixture_metadata']);stage='exit_raw_source_checks'
        verify_pins(output,plan,runtime=True);base.load_frozen(output,plan)
        result={'schema':SCHEMA+'.result','status':'completed_fixed_batched_comparison','plan_sha256':expected,
            'records':records,'batches':batches,'oracles':oracles,'summary':summary,'GC_enabled':gc.isenabled(),
            'entry_fixture_load_ns':loaded-started,'native_calls':0,'model_calls':0,
            'post_BOOT_before_result_seconds':time.perf_counter()-BOOT}
        write(output/'result.json',result);stage='saved_readback'
        write(output/'saved_verification.json',verify_saved(output,plan))
        require(time.perf_counter()-BOOT<=LIMIT,'whole_budget')
        return 0
    except BaseException as error:
        write(output/'failure.json',{'schema':SCHEMA+'.failure','stage':stage,'error':repr(error),
            'completed_measurements_lower_bound':len(records),'completed_batches':len(batches),
            'oracles':oracles,'partial_records':records,'partial_batches':batches,'success':False})
        return 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare-child',action='store_true');parser.add_argument('--campaign-child',action='store_true')
    parser.add_argument('--pure',type=Path);parser.add_argument('--plan-sha256');parser.add_argument('--admission',required=True)
    a=parser.parse_args();require(sys.stdin.readline().strip()==a.admission,'owned_admission');output=a.output.resolve()
    if a.prepare_child:
        require(not a.campaign_child and a.pure is not None and a.admission==SOURCE_PLAN_SHA,'prepare_mode')
        prepare(output,a.pure.resolve());return 0
    require(a.campaign_child and a.plan_sha256==a.admission,'campaign_mode')
    return execute(output,a.plan_sha256)


if __name__=='__main__':raise SystemExit(main())
