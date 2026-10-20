"""Owned120 fixed two historical queries, original validator ABBA attribution.

No C/native/model/full policy or late checkpoint. A is original, B is the
identical function with a nested original-digest timer; B is not an optimizer.
All envelopes and ordinary rejections are preserved in all32 saved outputs.
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
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import measure_planning_v2_digest_v2 as base
from . import delivered_peer_cost_probe as probe

ROOT,OUT=base.ROOT,base.OUT
MODULE='scripts.experiments.g31_ics_circulation.measure_delivered_peer_cost'
TEST='tests/test_g31_circulation_delivered_peer_cost_probe.py'
HARNESS_TEST='tests/test_g31_circulation_delivered_peer_cost_harness.py'
PRIOR=OUT/'planning_v2_digest_prepare_002/plan.json'
PRIOR_SHA='f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187'
PUBLIC=OUT/'original_low_wip_prepare_005/preregistered_protocol.json'
PUBLIC_SHA='71b278ac95c270fa18bde49a7da9f6f84031762b0da6ead494b39864cf7d7ece'
LIMIT=120.
PURE_COUNT=38
ARMS=('A','B','B','A')
require,sha,encoded,loads,write=base.require,base.sha,base.encoded,base.loads,base.write


def sources():
    return base.image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.'),HARNESS_TEST[:-3].replace('/','.')))


def no_extensions():
    require(not any('czr005_circulation' in n or n=='_g31_complete_tree_normalizer'
        for n in sys.modules),'no_native_or_C_extension')


def original_plans():
    require(sha(PRIOR)==PRIOR_SHA and sha(PUBLIC)==PUBLIC_SHA,'prior_public_pins')
    prior=loads(PRIOR.read_bytes()); public=loads(PUBLIC.read_bytes())
    require(public['input_sha256']==probe.original.INPUT_SHA and public['offered']==28506
        and public['trays']==22,'original_contract_scope')
    require([m['ordinal'] for m in prior['fixture_metadata']]==[27212,27215]
        and [m['envelope_count'] for m in prior['fixture_metadata']]==[1,1],'fixed_two')
    return prior,public


def verify(output,plan):
    no_extensions();prior,public=original_plans()
    require(plan['schema']=='g31.delivered_peer.fixed_two.v1' and plan['shared_seconds']==LIMIT
        and plan['arms']==list(ARMS) and plan['calls']==32,'fixed_scope')
    for key in ('files','fixture_metadata'): require(encoded(plan[key])==encoded(prior[key]),'fixed_'+key)
    require(encoded(plan['public_contract'])==encoded(public['public_contract']),'fixed_static_contract')
    current=sources();require(set(current)==set(plan['sources']),'source_inventory')
    for rel,data in current.items():require(base.sha_bytes(data)==sha(output/'source'/rel)==plan['sources'][rel],'source:'+rel)
    for item in plan['files']:require(sha(item['source'])==sha(output/'fixtures'/item['file'])==item['sha256'],'fixture_pin')
    for ref in plan['pure'].values():require(sha(ref['path'])==ref['sha256'],'pure_pin')
    require(sha(sys.executable)==plan['python_sha256'],'python_pin')
    require(encoded(probe.source_proof())==encoded(plan['source_proof']),'original_code_proof')
    loaded={Path(m.__file__).resolve().relative_to(ROOT).as_posix() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'
        and Path(m.__file__).resolve().is_relative_to(ROOT)}
    require(loaded<=set(current),'loaded_source_domain')


def pure(output):
    files=sources(); before={n:base.sha_bytes(d) for n,d in files.items()}
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--pure-worker','--output',str(output),'--admission',token]
    process=run_child(output,command,token)
    xml=output/'tests.xml';cases=ET.parse(xml).getroot().findall('.//testcase') if xml.exists() else []
    changed=[n for n,d in before.items() if sha(ROOT/n)!=d or sha(output/'source'/n)!=d]
    passed=process['status']=='exited' and process['exitcode']==0 and len(cases)==PURE_COUNT and not changed and not any(
        n.tag in ('failure','error','skipped') for c in cases for n in c)
    write(output/'receipt.json',{'status':'passed' if passed else 'failed_or_unknown','process':process,
        'tests':len(cases),'source_sha256':before,'source_changed':changed,'XML_sha256':sha(xml) if xml.exists() else None,
        'actual_raw_reads':0,'native_calls':0,'model_calls':0,'actual_digest_calls':0})
    return 0 if passed else 1


def prepare(output,pure_dir):
    r=loads((pure_dir/'receipt.json').read_bytes());xml=pure_dir/'tests.xml'
    cases=ET.parse(xml).getroot().findall('.//testcase')
    require(r['status']=='passed' and r['source_changed']==[] and r['tests']==len(cases)==PURE_COUNT
        and r['XML_sha256']==sha(xml) and not any(n.tag in ('failure','error','skipped') for c in cases for n in c),'pure_gate')
    files=sources();require(set(files)==set(r['source_sha256']),'pure_source_domain')
    for name,data in files.items():
        require(base.sha_bytes(data)==r['source_sha256'][name]==sha(pure_dir/'source'/name),'pure_source_pin')
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    prior,public=original_plans();(output/'fixtures').mkdir()
    for item in prior['files']:
        data=Path(item['source']).read_bytes();require(base.sha_bytes(data)==item['sha256'],'compressed_pin')
        (output/'fixtures'/item['file']).write_bytes(data)
    plan={'schema':'g31.delivered_peer.fixed_two.v1','shared_seconds':LIMIT,'arms':list(ARMS),'calls':32,
        'files':prior['files'],'fixture_metadata':prior['fixture_metadata'],'public_contract':public['public_contract'],
        'sources':{n:base.sha_bytes(d) for n,d in files.items()},'python_sha256':sha(sys.executable),
        'prior_plan_sha256':PRIOR_SHA,'public_plan_sha256':PUBLIC_SHA,'source_proof':probe.source_proof(),
        'pure':{n:{'path':str((pure_dir/f).resolve()),'sha256':sha(pure_dir/f)} for n,f in [('receipt','receipt.json'),('xml','tests.xml')]},
        'preparation_raw_decodes':0,'preparation_validator_calls':0,
        'scope':'Fixed original2queries. Exact query owner/time/full envelopes and original static node contract. No real late policy state, activation frequency, full day acceptance, native authority or100ms claim.',
        'timing':'A original validator; B same validator nested originaldigest timer. Private bind/setup, metadata guards, all full saved outcomes/readback and exit inwhole120; nested inclusive/exclusive times conserve, B instrumentation overhead not removed.'}
    write(output/'plan.json',plan);verify(output,plan)
    write(output/'ready.json',{'status':'prepared_root_review_pending','plan_sha256':sha(output/'plan.json'),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--admission',sha(output/'plan.json')]})


def audit_records(records):
    require([(r['ordinal'],r['batch'],r['arm'],r['repeat']) for r in records]==[
        (ordinal,batch,arm,repeat) for ordinal in (27212,27215) for batch,arm in enumerate(ARMS) for repeat in range(4)],'complete32_order')
    last=-1
    for r in records:
        require(r['outcome_file']==f"outcome_{r['ordinal']}_{r['batch']}_{r['repeat']}.json"
            and r['disposition'] in ('accepted','absent','rejected'),'outcome_identity')
        m=r['metrics'];require(last<=m['started_ns']<=m['finished_ns'] and m['validator_ns']==m['finished_ns']-m['started_ns'],'clock_order')
        last=m['finished_ns']
        if r['arm']=='B':require(m['digest_entered']==m['digest_completed']+m['digest_raised']<=1
            and m['digest_ns']>=0 and m['validator_outside_digest_ns']>=0
            and m['validator_ns']==m['digest_ns']+m['validator_outside_digest_ns'],'nested_conservation')
        else:require(all(m[k] is None for k in ('digest_entered','digest_completed','digest_raised','digest_ns','validator_outside_digest_ns')),'unmeasured_A_digest')
    for ordinal in (27212,27215):require(len({r['outcome_sha256'] for r in records if r['ordinal']==ordinal})==1,'full_outcome_parity')
    return {str(o):{arm:{'median_validator_ms':statistics.median(r['metrics']['validator_ns'] for r in records if r['ordinal']==o and r['arm']==arm)/1e6,
        'median_nested_digest_ms':statistics.median(r['metrics']['digest_ns'] for r in records if r['ordinal']==o and r['arm']==arm)/1e6 if arm=='B' else None,
        'median_outside_digest_ms':statistics.median(r['metrics']['validator_outside_digest_ns'] for r in records if r['ordinal']==o and r['arm']==arm)/1e6 if arm=='B' else None}
        for arm in ('A','B')} for o in (27212,27215)}


def execute(output,admission):
    records=[]
    try:
        plan=loads((output/'plan.json').read_bytes());require(sha(output/'plan.json')==admission,'execute_pin')
        verify(output,plan);require(gc.isenabled(),'default_GC');rows=base.load_frozen(output,plan)
        with (output/'measurements.jsonl').open('xb') as journal:
            for row in rows:
                args=probe.arguments(row,plan['public_contract']);before=encoded(row)
                nodes_before=encoded(plan['public_contract'])
                for batch,arm in enumerate(ARMS):
                    for repeat in range(4):
                        outcome,metrics=probe.measure(args,arm)
                        require(encoded(row)==before and encoded(plan['public_contract'])==nodes_before,'mutation')
                        name=f"outcome_{row['ordinal']}_{batch}_{repeat}.json"
                        write(output/name,outcome)
                        record={'ordinal':row['ordinal'],'batch':batch,'arm':arm,'repeat':repeat,
                            'disposition':outcome['status'],'metrics':metrics,'outcome_file':name,'outcome_sha256':sha(output/name)}
                        records.append(record);data=encoded(record)+b'\n';require(journal.write(data)==len(data),'journal_write');journal.flush()
        summary=audit_records(records)
        for record in records:
            path=output/record['outcome_file'];require(sha(path)==record['outcome_sha256'],'saved_full_outcome_hash')
            value=loads(path.read_bytes());require(value['status']==record['disposition'],'saved_disposition')
        journal=[loads(line) for line in (output/'measurements.jsonl').read_bytes().splitlines()]
        require(encoded(journal)==encoded(records) and encoded(audit_records(journal))==encoded(summary),'saved32_readback')
        verify(output,plan);base.load_frozen(output,plan)
        write(output/'result.json',{'status':'completed_original_delivered_peer_attribution','records':records,'summary':summary,
            'plan_sha256':admission,'journal_sha256':sha(output/'measurements.jsonl'),'source_changed':[],
            'GC_enabled':gc.isenabled(),'calls':32,'native_calls':0,'model_calls':0,'policy_replays':0,
            'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'not_optimization_or_actual_frequency':True})
        require(time.perf_counter()-BOOT<LIMIT,'whole_budget');return 0
    except BaseException as exc:
        write(output/'failure.json',{'status':'unknown_failed','error':repr(exc),'completed':len(records),'records':records});return 1


def run_child(output,command,token):
    remaining=LIMIT-(time.perf_counter()-BOOT)-1.;require(remaining>0,'before_child_budget')
    with (output/'stdout.log').open('xb') as out,(output/'stderr.log').open('xb') as err:
        return bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=token,cwd=ROOT)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--admission');p.add_argument('--pure-dir',type=Path)
    g=p.add_mutually_exclusive_group(required=True)
    for mode in ('pure','pure-worker','prepare','prepare-worker','execute','worker'):g.add_argument('--'+mode,action='store_true')
    a=p.parse_args();output=a.output.resolve();no_extensions()
    if a.pure_worker or a.prepare_worker or a.worker:
        require(sys.stdin.readline()==a.admission+'\n','owned_admission')
        if a.pure_worker:
            import pytest
            return pytest.main(['-q',TEST,HARNESS_TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        if a.prepare_worker:prepare(output,a.pure_dir.resolve());return 0
        return execute(output,a.admission)
    if a.pure or a.prepare:output.mkdir(parents=True,exist_ok=False)
    if a.pure:return pure(output)
    token=uuid.uuid4().hex if a.prepare else a.admission
    if a.execute:
        require(sha(output/'plan.json')==a.admission,'parent_plan_pin')
        with (output/'execution_claim.json').open('x') as f:json.dump({'plan_sha256':token},f)
    command=[sys.executable,'-m',MODULE,'--prepare-worker' if a.prepare else '--worker','--output',str(output),'--admission',token]
    if a.prepare:command+=['--pure-dir',str(a.pure_dir.resolve())]
    process=run_child(output,command,token)
    passed=process['status']=='exited' and process['exitcode']==0 and time.perf_counter()-BOOT<LIMIT
    write(output/('prepare_bounded.json' if a.prepare else 'bounded_execution.json'),{
        'status':'completed' if passed else 'unknown_failed_or_timeout','process':process,'shared_seconds':LIMIT,
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'whole_external_required':True})
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
