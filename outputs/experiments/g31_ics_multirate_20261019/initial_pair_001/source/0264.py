"""Prepared fixed-two C digest substitution inside original delivered_peer.

ABBA32 is deliberately small and retains the two historically absent queries.
No policy replay, sampling of the full stream, native simulation or100ms claim.
All dependency checks, load/oracle, fixture guards, export and readback stay in
the shared120; B contains verification/classification overhead without discount.
"""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import gc
import json
import math
import os
from pathlib import Path
import statistics
import sys
import uuid
import xml.etree.ElementTree as ET
from . import measure_delivered_peer_cost as legacy
from . import measure_delivered_peer_cost_v4 as stage_logs
from . import delivered_peer_c_encoder_probe as probe
from . import planning_v2_c_encoder_authority as authority

ROOT,OUT=legacy.ROOT,legacy.OUT
MODULE='scripts.experiments.g31_ics_circulation.measure_delivered_peer_c_encoder'
TEST='tests/test_g31_circulation_delivered_peer_c_encoder.py'
SCHEMA='g31.delivered_peer.fixed_two_C_encoder.v1'
ARMS=('A','B','B','A');LIMIT=120.;PURE_COUNT=83
base=legacy.base
require,sha,encoded,loads,write=legacy.require,legacy.sha,legacy.encoded,legacy.loads,legacy.write


def sources():
    result=base.image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.')))
    # Preserve the old executable's explicitly named bare test helpers too;
    # its hand-listed roots are not inferred from an import of stage_logs.
    for name,data in stage_logs.sources().items():
        require(name not in result or result[name]==data,'prior_closure_conflict');result[name]=data
    # Include the complete accepted encoder project domain, including C/CMake
    # and test fixtures named by its private functions rather than imports.
    for name,digest in authority.gate.namespace()['project_closure']().items():
        value=(ROOT/name).read_bytes();require(base.sha_bytes(value)==digest,'encoder_source')
        require(name not in result or result[name]==value,'closure_conflict');result[name]=value
    return result


def archive_targets(output,files,absent):
    output=Path(output).resolve();archive=(output/'source').resolve()
    require(output.is_relative_to(OUT.resolve()) and output!=OUT.resolve(),'output_containment')
    result={}
    for name in files:
        relative=Path(name);require(not relative.is_absolute() and '..' not in relative.parts,'relative_source')
        live=(ROOT/relative).resolve();target=(archive/relative).resolve()
        require(live.is_relative_to(ROOT.resolve()) and live.relative_to(ROOT.resolve()).as_posix()==name,
            'canonical_live_source')
        require(target.is_relative_to(archive) and target!=live and archive.is_relative_to(output)
            and len(str(target))<260,'independent_short_archive')
        require(not absent or not target.exists(),'exclusive_archive')
        result[name]=target
    return result


def archive_sources(output,files):
    targets=archive_targets(output,files,True)  # Check all targets before the first write.
    for name,data in files.items():
        path=targets[name];path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:require(stream.write(data)==len(data),'archive_short_write')


def check_pure_external(value,command,outputs,runner):
    require(value['schema']=='g31.delivered_peer.C_encoder.pure_external.v1'
        and value['command']==command and value['runner']==runner,'pure_external_identity')
    require(type(value['exit_code']) is int and value['exit_code']==0 and value['source_changed']==[]
        and value['outer_timeout'] is False and value['exception'] is None,'pure_external_status')
    ticks,frequency,wall=value['elapsed_ticks'],value['tick_frequency'],value['whole_python_seconds']
    require(type(ticks) is int and ticks>=0 and type(frequency) is int and frequency>0 and ticks<=120*frequency and
        type(wall) in (int,float) and math.isfinite(wall) and 0<wall<=120 and abs(wall-ticks/frequency)<=1e-9,'pure_external_clock')
    require(value['output_sha256']==outputs,'pure_external_outputs')


def verify_pure_external(pure):
    path=pure/'external_application_wall.json';value=loads(path.read_bytes())
    command=[str(authority.gate.old.PYTHON),'-m',MODULE,'--pure','--output',str(pure.resolve())]
    runner={'path':str(Path(__file__).resolve()),'sha256':sha(__file__)}
    outputs={name:sha(pure/name) for name in ('receipt.json','bounded_execution.json','tests.xml')}
    check_pure_external(value,command,outputs,runner)
    wrapper=value['wrapper'];require(type(wrapper) is dict and set(wrapper)=={'path','sha256'}
        and sha(wrapper['path'])==wrapper['sha256'],'pure_external_wrapper')
    return {'path':str(path.resolve()),'sha256':sha(path)}


def verify(output,plan):
    legacy.no_extensions();prior,public=legacy.original_plans()
    require(plan['schema']==SCHEMA and plan['shared_seconds']==120 and plan['arms']==list(ARMS)
        and type(plan['calls']) is int and plan['calls']==32,'fixed_scope')
    for key in ('files','fixture_metadata'):require(encoded(plan[key])==encoded(prior[key]),'fixed_'+key)
    require(encoded(plan['public_contract'])==encoded(public['public_contract']),'static_contract')
    current=sources();require(set(current)==set(plan['sources']),'source_domain')
    archive_targets(output,current,False)
    for name,data in current.items():require(base.sha_bytes(data)==sha(output/'source'/name)==plan['sources'][name],'source:'+name)
    for item in plan['files']:require(sha(item['source'])==sha(output/'fixtures'/item['file'])==item['sha256'],'fixture_pin')
    for item in plan['pure'].values():require(sha(item['path'])==item['sha256'],'pure_pin')
    require(verify_pure_external(Path(plan['pure']['receipt']['path']).parent)==plan['pure']['external'],'pure_external_recheck')
    require(sha(sys.executable)==plan['python_sha256'],'python_pin')
    require(encoded(probe.source_proof())==encoded(plan['source_proof']),'source_proof')
    require(encoded(authority.references())==encoded(plan['C_authority']),'C_authority')
    loaded={Path(m.__file__).resolve().relative_to(ROOT).as_posix() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    require(loaded<=set(current),'loaded_source_domain')


def prepare(output,pure):
    require(PURE_COUNT>0,'unreviewed_test_denominator')
    receipt=loads((pure/'receipt.json').read_bytes());rows=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and receipt['tests']==len(rows)==PURE_COUNT
        and sha(pure/'tests.xml')==receipt['XML_sha256'] and not any(c.tag in ('failure','error','skipped') for row in rows for c in row),'pure_gate')
    external_pure=verify_pure_external(pure)
    files=sources();require(set(files)==set(receipt['source_sha256']),'pure_domain')
    for name,data in files.items():
        require(base.sha_bytes(data)==receipt['source_sha256'][name]==sha(pure/'source'/name),'pure_source')
    archive_sources(output,files)
    prior,public=legacy.original_plans();(output/'fixtures').mkdir()
    for item in prior['files']:
        data=Path(item['source']).read_bytes();require(base.sha_bytes(data)==item['sha256'],'fixture_hash')
        path=(output/'fixtures'/item['file']).resolve()
        require(path.is_relative_to((output/'fixtures').resolve()) and path!=Path(item['source']).resolve()
            and len(str(path))<260,'fixture_archive_containment')
        with path.open('xb') as stream:require(stream.write(data)==len(data),'fixture_short_write')
    plan={'schema':SCHEMA,'shared_seconds':LIMIT,'arms':list(ARMS),'calls':32,
        'files':prior['files'],'fixture_metadata':prior['fixture_metadata'],'public_contract':public['public_contract'],
        'sources':{n:base.sha_bytes(d) for n,d in files.items()},'python_sha256':sha(sys.executable),
        'prior_plan_sha256':legacy.PRIOR_SHA,'public_plan_sha256':legacy.PUBLIC_SHA,
        'C_authority':authority.references(),'source_proof':probe.source_proof(),
        'pure':{n:{'path':str((pure/f).resolve()),'sha256':sha(pure/f)} for n,f in [('receipt','receipt.json'),('xml','tests.xml')]},
        'preparation_raw_decodes':0,'preparation_validator_calls':0,'preparation_C_loads':0,
        'oracle':'All fixed envelopes, in order. Original full bytes and actual C try before all measurements; fallback explicitly separate. Complete hex pairs retained, no hash-only substitute.',
        'scope':'Two original queries27212/27215, historically both absent. Ordinary rejection/accepted/absent outcomes all retained; no successful-path coverage extrapolation, policy frequency, full-day or100ms conclusion.',
        'timing':'A original/B exact same validator with only digest global substituted. B per-call verification/classification stays in validator span. Fixture/header guards, binding, byte oracle, all dependency entry/exit checks, export/readback/cleanup remain inwhole120. Batch spans include per-call setup and saves; not added to nested validator spans.',
        'failures':'Resource or unexpected exceptions, drift, failed oracle, missing rows and timeout remain unknown. No retry/expiry movement/capacity expansion.'}
    plan['pure']['external']=external_pure
    write(output/'plan.json',plan);verify(output,plan)
    write(output/'ready.json',{'status':'prepared_root_review_pending','plan_sha256':sha(output/'plan.json'),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--admission',sha(output/'plan.json')]})


def audit_records(records):
    require(type(records) is list,'records_type')
    order=[(o,b,a,r) for o in (27212,27215) for b,a in enumerate(ARMS) for r in range(4)]
    require([(r['ordinal'],r['batch'],r['arm'],r['repeat']) for r in records]==order,'exact32_order')
    last=-1
    for row in records:
        require(all(type(row[k]) is int and row[k]>=0 for k in ('ordinal','batch','repeat')),'index_types')
        require(row['outcome_file']==f"outcome_{row['ordinal']}_{row['batch']}_{row['repeat']}.json"
            and row['disposition'] in ('accepted','absent','rejected')
            and base.hexsha(row['outcome_sha256']),'outcome_identity')
        m=row['metrics'];require(type(m) is dict and set(m)=={'started_ns','finished_ns','validator_ns','digest_events'},'metrics_domain')
        require(all(type(m[k]) is int and m[k]>=0 for k in ('started_ns','finished_ns','validator_ns')),'clock_types')
        require(last<=m['started_ns']<=m['finished_ns'] and m['validator_ns']==m['finished_ns']-m['started_ns'],'clock_formula')
        last=m['finished_ns'];events=m['digest_events']
        if row['arm']=='A':require(events is None,'A_no_digest_classification')
        else:
            require(type(events) is list and len(events)<=1,'digest_count')
            for event in events:
                require(type(event['ordinal']) is int and event['ordinal']==0 and type(event['returned']) is bool,'event_types')
                require(event['classification'] in ('entered','direct_C_bytes','original_fallback'),'classification')
                if event['returned']:
                    require(set(event)=={'ordinal','classification','returned','sha256'} and event['classification']!='entered'
                        and base.hexsha(event['sha256']),'returned_digest')
                else:
                    error=event.get('error',{})
                    require(set(event)=={'ordinal','classification','returned','error'}
                        and set(error)=={'exception_type','exception_text','exception_args','exception_args_verified'}
                        and error['exception_type'] in ('ValueError','KeyError','TypeError')
                        and error['exception_args_verified'] is True and type(error['exception_text']) is str
                        and row['disposition']=='rejected','ordinary_digest_rejection_only')
    for ordinal in (27212,27215):require(len({r['outcome_sha256'] for r in records if r['ordinal']==ordinal})==1,'full_outcome_parity')
    return {str(o):{a:{'calls':8,'median_validator_ms':statistics.median(r['metrics']['validator_ns'] for r in records
        if r['ordinal']==o and r['arm']==a)/1e6,
        'direct_C_bytes':sum(e['classification']=='direct_C_bytes' and e['returned'] for r in records if r['ordinal']==o and r['arm']==a for e in (r['metrics']['digest_events'] or [])),
        'original_fallback':sum(e['classification']=='original_fallback' for r in records if r['ordinal']==o and r['arm']==a for e in (r['metrics']['digest_events'] or []))}
        for a in ('A','B')} for o in (27212,27215)}


def audit_batches(batches,records):
    require(type(batches) is list and len(batches)==8,'batch_denominator')
    require([(b['ordinal'],b['batch'],b['arm']) for b in batches]==[
        (o,b,a) for o in (27212,27215) for b,a in enumerate(ARMS)],'batch_order')
    last=-1
    for row in batches:
        require(set(row)=={'ordinal','batch','arm','started_ns','finished_ns','whole_batch_ns'}
            and all(type(row[k]) is int and row[k]>=0 for k in
                ('ordinal','batch','started_ns','finished_ns','whole_batch_ns')),'batch_types')
        require(last<=row['started_ns']<=row['finished_ns'] and
            row['whole_batch_ns']==row['finished_ns']-row['started_ns'],'batch_clock')
        members=[r for r in records if (r['ordinal'],r['batch'],r['arm'])==(row['ordinal'],row['batch'],row['arm'])]
        require(len(members)==4 and all(row['started_ns']<=r['metrics']['started_ns']<=
            r['metrics']['finished_ns']<=row['finished_ns'] for r in members),'batch_contains_calls')
        last=row['finished_ns']


class Journal:
    def __init__(self,path):self.stream=path.open('xb');self.count=0
    def mark(self,stage,event):
        require(self.count<64,'stage_journal_capacity')
        value={'ordinal':self.count,'stage':stage,'event':event,'at_ns':time.perf_counter_ns()};self.count+=1
        data=encoded(value)+b'\n';require(self.stream.write(data)==len(data),'stage_journal_write');self.stream.flush()
    def close(self):self.stream.close()


def execute(output,admission):
    records=[];batches=[];oracles=[];active=None;candidate=None;stages=None
    try:
        stages=Journal(output/'stages.jsonl');stages.mark('entry','started')
        plan=loads((output/'plan.json').read_bytes());require(sha(output/'plan.json')==admission,'execute_plan')
        verify(output,plan);require(gc.isenabled(),'default_GC');stages.mark('entry','completed')
        stages.mark('C_load_and_dependency_entry','started');candidate,entry=authority.begin(plan['sources'])
        stages.mark('C_load_and_dependency_entry','completed');write(output/'C_entry.json',entry)
        stages.mark('fixture_decode_and_oracle','started');rows=base.load_frozen(output,plan)
        for row in rows:
            for env_index,env in enumerate(row['result']):
                oracle=probe.byte_oracle(env['capture'],candidate)
                oracle.update(ordinal=row['ordinal'],envelope_ordinal=env_index,
                    matches_declared_payload=oracle['sha256']==env['payload_sha256'])
                oracles.append(oracle)
        write(output/'byte_oracle.json',oracles);stages.mark('fixture_decode_and_oracle','completed')
        with (output/'measurements.jsonl').open('xb') as journal:
            for row in rows:
                args=probe.original.arguments(row,plan['public_contract']);before=encoded(row);nodes_before=encoded(plan['public_contract'])
                for batch,arm in enumerate(ARMS):
                    label=f"{row['ordinal']}:{batch}:{arm}";stages.mark(label,'started');batch_start=time.perf_counter_ns()
                    for repeat in range(4):
                        active={'ordinal':row['ordinal'],'batch':batch,'arm':arm,'repeat':repeat,'attempt_started_ns':time.perf_counter_ns()}
                        outcome,metrics=probe.measure(args,arm,candidate,attempt=active)
                        require(encoded(row)==before and encoded(plan['public_contract'])==nodes_before,'mutation')
                        name=f"outcome_{row['ordinal']}_{batch}_{repeat}.json";write(output/name,outcome)
                        record={'ordinal':row['ordinal'],'batch':batch,'arm':arm,'repeat':repeat,'disposition':outcome['status'],
                            'metrics':metrics,'outcome_file':name,'outcome_sha256':sha(output/name)}
                        data=encoded(record)+b'\n';require(journal.write(data)==len(data),'measurement_journal_write');journal.flush()
                        records.append(record);active=None
                    batch_end=time.perf_counter_ns();batches.append({'ordinal':row['ordinal'],'batch':batch,'arm':arm,
                        'started_ns':batch_start,'finished_ns':batch_end,'whole_batch_ns':batch_end-batch_start})
                    stages.mark(label,'completed')
        stages.mark('saved_readback','started');summary=audit_records(records);audit_batches(batches,records)
        write(output/'batches.json',batches)
        reread=[loads(line) for line in (output/'measurements.jsonl').read_bytes().splitlines()]
        require(encoded(records)==encoded(reread) and encoded(audit_records(reread))==encoded(summary),'saved32_readback')
        for row in records:
            path=output/row['outcome_file'];require(sha(path)==row['outcome_sha256'],'saved_outcome_hash')
            require(loads(path.read_bytes())['status']==row['disposition'],'saved_outcome_status')
        saved=loads((output/'byte_oracle.json').read_bytes());require(encoded(saved)==encoded(oracles),'saved_oracle_identity')
        require([(r['ordinal'],r['envelope_ordinal']) for r in saved]==[(r['ordinal'],i) for r in rows for i in range(len(r['result']))],'oracle_denominator')
        for record in saved:require(bytes.fromhex(record['actual_hex'])==bytes.fromhex(record['expected_hex']),'saved_complete_bytes')
        saved_batches=loads((output/'batches.json').read_bytes());audit_batches(saved_batches,reread)
        require(encoded(saved_batches)==encoded(batches),'saved_batch_identity')
        stages.mark('saved_readback','completed');stages.mark('dependency_exit','started')
        exit_proof=authority.finish(candidate,plan['sources']);write(output/'C_exit.json',exit_proof)
        verify(output,plan);base.load_frozen(output,plan);require(gc.isenabled(),'exit_GC')
        stages.mark('dependency_exit','completed')
        write(output/'saved_verification.json',{'status':'passed_fixed_two_C_validator_saved','calls':32,
            'batches':8,'full_byte_oracles':len(oracles),'summary':summary,
            'files':{n:sha(output/n) for n in ('measurements.jsonl','batches.json','byte_oracle.json','C_entry.json','C_exit.json')}})
        write(output/'result.json',{'status':'completed_fixed_two_C_validator_comparison','plan_sha256':admission,
            'records':records,'batches':batches,'summary':summary,'byte_oracle_sha256':sha(output/'byte_oracle.json'),
            'entry_sha256':sha(output/'C_entry.json'),'exit_sha256':sha(output/'C_exit.json'),
            'journal_sha256':sha(output/'measurements.jsonl'),'source_changed':[],
            'saved_verification_sha256':sha(output/'saved_verification.json'),
            'calls':32,'C_oracle_attempts':sum(r['C_attempts'] for r in oracles),
            'oracle_original_byte_writer_calls':sum(r['original_byte_writer_calls'] for r in oracles),
            'post_BOOT_before_final_export_seconds':time.perf_counter()-BOOT,
            'native_calls':0,'model_calls':0,'policy_replays':0,'actual_activation_frequency_unknown':True,
            'known_input_scope':'Two historically absent late envelopes. No success-path/full-stream/100ms extrapolation.'})
        require(time.perf_counter()-BOOT<LIMIT,'whole_budget');return 0
    except BaseException as exc:
        write(output/'failure.json',{'status':'unknown_failed','error':probe.error_evidence(exc),
            'completed_measurements':len(records),'failed_attempt':active,'records':records,'completed_byte_oracles':len(oracles),
            'C_loaded':candidate is not None,'failed_call_not_counted_complete':True})
        return 1
    finally:
        if stages is not None:stages.close()


run_child=stage_logs.private(stage_logs.run_child,{'BOOT':BOOT,'LIMIT':LIMIT})


def pure(output):
    files=sources();before={n:base.sha_bytes(d) for n,d in files.items()};archive_sources(output,files)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--pure-worker','--output',str(output),'--admission',token]
    process=run_child(output,command,token)
    write(output/'bounded_execution.json',{'process':process,'shared_seconds':LIMIT,
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'whole_external_required':True})
    xml=output/'tests.xml';rows=ET.parse(xml).getroot().findall('.//testcase') if xml.exists() else []
    changed=[n for n,d in before.items() if sha(ROOT/n)!=d or sha(output/'source'/n)!=d]
    passed=process['status']=='exited' and type(process['exitcode']) is int and process['exitcode']==0
    passed=passed and time.perf_counter()-BOOT<LIMIT and len(rows)==PURE_COUNT and not changed and not any(
        c.tag in ('failure','error','skipped') for row in rows for c in row)
    write(output/'receipt.json',{'status':'passed' if passed else 'failed_or_unknown','process':process,
        'tests':len(rows),'source_sha256':before,'source_changed':changed,'XML_sha256':sha(xml) if xml.exists() else None,
        'C_loads':0,'actual_raw_reads':0,'native_calls':0,'model_calls':0,'actual_digest_calls':0,
        'external_typed_clock_required_before_prepare':True})
    return 0 if passed else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--admission');parser.add_argument('--pure-dir',type=Path)
    group=parser.add_mutually_exclusive_group(required=True)
    for mode in ('pure','pure-worker','prepare','prepare-worker','execute','worker'):group.add_argument('--'+mode,action='store_true')
    args=parser.parse_args();output=args.output.resolve();legacy.no_extensions()
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';os.environ['PYTEST_ADDOPTS']=''
    if args.pure_worker or args.prepare_worker or args.worker:
        require(sys.stdin.readline()==args.admission+'\n','owned_admission')
        if args.pure_worker:
            require(PURE_COUNT>0,'unreviewed_test_denominator');import pytest
            config=output/'pytest.ini'
            with config.open('x',encoding='utf8') as stream:stream.write('[pytest]\n')
            return pytest.main(['-q',TEST,'--noconftest','-c',str(config),'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        if args.prepare_worker:prepare(output,args.pure_dir.resolve());return 0
        return execute(output,args.admission)
    if args.pure or args.prepare:output.mkdir(parents=True,exist_ok=False)
    if args.pure:return pure(output)
    token=uuid.uuid4().hex if args.prepare else args.admission
    if args.execute:
        require(sha(output/'plan.json')==token,'parent_plan')
        with (output/'execution_claim.json').open('x') as stream:json.dump({'plan_sha256':token},stream)
    command=[sys.executable,'-m',MODULE,'--prepare-worker' if args.prepare else '--worker','--output',str(output),'--admission',token]
    if args.prepare:command+=['--pure-dir',str(args.pure_dir.resolve())]
    process=run_child(output,command,token)
    passed=process['status']=='exited' and process['exitcode']==0 and time.perf_counter()-BOOT<LIMIT
    write(output/('prepare_bounded.json' if args.prepare else 'bounded_execution.json'),{'status':'completed' if passed else 'unknown_failed_or_timeout',
        'process':process,'shared_seconds':LIMIT,'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'whole_external_required':True})
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
