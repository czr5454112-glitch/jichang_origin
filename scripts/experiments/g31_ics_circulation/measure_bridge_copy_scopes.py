"""Fixed synthetic copy/guard cost isolation. Prepare does not run the ABBA."""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import ast
import hashlib
import inspect
import json
import math
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image
from . import bridge_copy_scopes_fixture as f

ROOT=Path(__file__).resolve().parents[3]
MODULE='scripts.experiments.g31_ics_circulation.measure_bridge_copy_scopes'
LAUNCHER='scripts.experiments.g31_ics_circulation.launch_bridge_copy_scopes'
TEST='tests/test_g31_circulation_measure_bridge_copy_scopes.py'
PURE_MODULE='scripts.experiments.g31_ics_circulation.run_measure_bridge_copy_scopes_pure'
SCHEMA='g31.bridge.copy_scopes.synthetic_ABBA.v1'
ARMS=('A','B','B','A');FAMILIES=f.FAMILIES;PER_BATCH=32;LIMIT=120.
MAX_BYTES=16*1024*1024
COUNTS={'families':2,'batches':8,'measured_invocations':256,'invocations_per_batch':32,
        'jobs_per_capture':64,'self_capture_revisions':16,'extra_oracle_invocations':0}
SOURCE_PLAN=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/bridge_replay_copy_scopes_source_001/plan.json'
SOURCE_PLAN_SHA='421ff5c5db0ae9358412cef86ec6450286720e9a15ed05e574364a754512f142'
PURE_TESTS=79  # Original37 plus42 fixed functional harness guards.


def require(ok,reason):
    if not ok:raise ValueError('copy_scope_measure:'+reason)


def tree(value, active=None):
    active=set() if active is None else active
    t=type(value)
    if t in (str,int,bool,type(None)):return set()
    if t is float:
        require(math.isfinite(value),'nonfinite');return set()
    require(t in (dict,list),'builtin_tree')
    identity=id(value);require(identity not in active,'cycle');active.add(identity)
    result={identity}
    if t is dict:
        require(all(type(k) is str for k in value),'string_keys');items=value.values()
    else:items=value
    for item in items:result.update(tree(item,active))
    active.remove(identity);return result


def encoded(value):
    tree(value)
    data=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
    require(len(data)<=MAX_BYTES,'artifact_size');return data


def _pairs(rows):
    result={}
    for key,value in rows:
        require(key not in result,'duplicate_key');result[key]=value
    return result


def loads(raw):
    require(type(raw) is bytes and len(raw)<=MAX_BYTES,'saved_size')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=_pairs,
        parse_constant=lambda token:(_ for _ in ()).throw(ValueError('copy_scope_measure:nonfinite')))
    tree(value);return value


def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(Path(path).read_bytes())
def exact(a,b):return encoded(a)==encoded(b)


def write(path,value):
    with Path(path).open('xb') as stream:
        data=encoded(value)+b'\n';require(stream.write(data)==len(data),'short_artifact_write')


def inputs(case):
    result={k:case[k] for k in ('family','view','box','peer','plan')}
    if case['family']=='discard_refresh':result['query_responses']=case['session'].responses
    return result


def checked_result(case,arm,result,before):
    require(encoded(inputs(case))==before,'input_mutation')
    input_ids=tree(inputs(case))
    if case['family']=='discard_refresh':
        client=case['client'];session=case['session']
        require(result is None and client.calls==[],'unexpected_submit_or_return')
        expected=[['protocol_command','A','snapshot:'+format(i,'02d')] for i in range(f.REVISIONS)]
        require(exact(session.calls,expected),'query_order')
        require(all(client.state['outbox'][rid]['terminal'] is True for _,_,rid in expected),'terminal_state')
        require(not client._active_requests and not client._owner_active_requests['A'],'active_index')
        require(tree(client.state).isdisjoint(input_ids),'client_view_alias')
        return {'client_state':client.state,'queries':session.calls,'submissions':client.calls,
            'active_requests':list(client._active_requests),
            'owner_active_requests':{o:list(ids) for o,ids in client._owner_active_requests.items()}}
    own,barrier,choice=result
    require(own is not None and barrier is not None and choice is not None,'missing_consumer_result')
    ack=case['box']['snapshot:15']['client_view']['last_delivered_ack']
    expected={'request_id':'snapshot:15','ack':ack,'envelope':ack['planning_snapshot_v2']}
    require(exact(own,expected),'selected_full_capture')
    if arm=='B':require(own['ack'] is ack and own['envelope'] is ack['planning_snapshot_v2'],'borrow_identity')
    else:require(tree(own).isdisjoint(input_ids),'original_copy_alias')
    require(tree([barrier,choice]).isdisjoint(input_ids),'durable_consumer_alias')
    require(choice['kind']=='direct_supply' and choice['selected_current_job']['business_bag_id']=='peer:000',
        'synthetic_choice_identity')
    return {'selected':own,'barrier':barrier,'choice':choice}


def source_files():
    return image.source_closure(ROOT,(MODULE,LAUNCHER,PURE_MODULE,
        'tests.test_g31_circulation_measure_bridge_copy_scopes',
        'tests.test_g31_circulation_bridge_replay_copy_scopes'))


def source_review():
    proof=f.c.source_proof()
    seed=ast.parse(inspect.getsource(f.public_fixture)).body[0]
    old=ast.parse((ROOT/'tests/test_g31_circulation_bridge_replay_copy_scopes.py').read_text(encoding='utf8'))
    old=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='public_fixture')
    require(ast.dump(seed,include_attributes=False)==ast.dump(old,include_attributes=False),'synthetic_seed_changed')
    methods=(f.c.policy.BridgeOwner.publish,f.c.protocol.ProtocolClient.submit,f.c.protocol.ProtocolClient._send,
        f.c.policy.received_barrier,f.c.policy.choose_action,f.c.policy.current_own_fifo_heads,
        f.c.policy.fifo_heads,f.c.policy.completion_permit)
    return {'private_proof':proof,'synthetic_seed_AST_exact':True,
        'readonly_dependency_sources':{m.__module__+'.'+m.__qualname__:digest(inspect.getsource(m).encode()) for m in methods},
        'alias_scope':'In the serial closed source chain, publish constructs a new payload; submit deepcopies it and adds a new row; _send mutates only that new row and appends a copied call. None mutates a previously borrowed client_view/ACK/envelope. Original consumers read the borrowed input and return new barrier/path or copied job/completion; escaping PossessionGate remains original.',
        'claim_limit':'Source reasoning plus functional alias tests, not arbitrary callbacks/concurrent mutation safety. Removed allocations may change MemoryError timing; failure remains unknown.'}


def validate_plan(plan):
    require(plan['schema']==SCHEMA and exact(plan['counts'],COUNTS) and exact(plan['arms'],list(ARMS))
        and exact(plan['families'],list(FAMILIES)) and exact(plan['shared_seconds'],LIMIT),'plan_scope')


def verify_pins(output,plan,runtime=False):
    validate_plan(plan)
    require(sha(SOURCE_PLAN)==SOURCE_PLAN_SHA==plan['source_plan_sha256'],'source_plan')
    previous=loads(SOURCE_PLAN.read_bytes())
    for name,value in previous['sources'].items():
        require(sha(ROOT/name)==sha(Path(previous['source_archive'])/name)==value,'previous_source:'+name)
    files=source_files();require(set(files)==set(plan['sources']),'source_closure')
    for name,value in plan['sources'].items():
        require(digest(files[name])==sha(output/'source'/name)==value,'source:'+name)
    require(sha(sys.executable)==plan['interpreter_sha256'],'interpreter')
    for key in ('receipt','xml'):
        require(sha(plan['pure'][key]['path'])==plan['pure'][key]['sha256'],'pure_'+key)
    require(exact(plan['pure']['counts'],{'tests':PURE_TESTS,'failures':0,'errors':0,'skipped':0}),'pure_denominator')
    require(exact(source_review(),loads((output/'source_review.json').read_bytes())),'source_proof')
    require(sha(output/'source_review.json')==plan['source_review_sha256'],'source_review_hash')
    if runtime:
        loaded={str(Path(m.__file__).resolve().relative_to(ROOT)).replace('\\','/') for m in list(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded<=set(plan['sources']),'loaded_source_closure')


def prepare(output,pure):
    require(not output.exists(),'preserve_output')
    receipt=pure/'receipt.json';xml=pure/'tests.xml';r=loads(receipt.read_bytes())
    counts={key:sum(int(s.get(key,0)) for s in ET.parse(xml).getroot().iter('testsuite')) for key in ('tests','failures','errors','skipped')}
    require(counts=={'tests':PURE_TESTS,'failures':0,'errors':0,'skipped':0} and r['status']=='passed'
        and r['source_changed']==[] and r['native_calls']==r['actual_raw_reads']==0 and r['benchmark_executed'] is False
        and r['XML_sha256']==sha(xml),'pure_receipt')
    files=source_files()
    require(set(files)==set(r['source_sha256']),'tested_source_domain')
    for name,data in files.items():require(digest(data)==r['source_sha256'][name],'tested_source_changed')
    output.mkdir(parents=True)
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    write(output/'source_review.json',source_review())
    plan={'schema':SCHEMA,'status':'prepared_unexecuted','counts':COUNTS,'arms':list(ARMS),'families':list(FAMILIES),
        'shared_seconds':LIMIT,'source_plan_sha256':SOURCE_PLAN_SHA,
        'sources':{name:digest(data) for name,data in files.items()},'interpreter_sha256':sha(sys.executable),
        'pure':{'receipt':{'path':str(receipt.resolve()),'sha256':sha(receipt)},'xml':{'path':str(xml.resolve()),'sha256':sha(xml)},'counts':counts},
        'source_review_sha256':sha(output/'source_review.json'),
        'scope':'One synthetic64-job16-revision shape, not execution-time history. No native/model/full-policy replay. No extrapolation to the19712-row stopped audit or full600 success.',
        'isolated_clock':'Immediately before invoke through return; refresh includes synthetic query deepcopy and retained client_view copy; selector includes all original guards and barrier/choice consumers. No fixture or validation cost is subtracted from total.',
        'batch_clock':'Before first fixture rebuild through32 rows, all fresh fixtures/client construction, fingerprints, validation, comparisons, journaling and cleanup. All256 measured calls retained.',
        'whole_clock':'Parent module BOOT through final budget check; external launch-to-exit receipt required for interpreter startup and final evidence export. One Job uses only remaining120. No amortization.',
        'oracle':'First A invocation per family is the full saved ordered reference; no additional oracle calls. All later127 full values compared exactly; each call separately checks query/state/index or selector/consumer/alias guards.',
        'failure':'Write available prefix, first error and stage; no retry, filtering, source change, capacity increase or success claim after timeout.',
        'native_calls':0,'policy_replays':0,'full_audit_accepted':False}
    write(output/'plan.json',plan);verify_pins(output,plan)
    ready={'schema':SCHEMA+'.ready','status':'prepared_unexecuted','output':str(output),
        'plan_sha256':sha(output/'plan.json'),'source_count':len(files),'pure_counts':counts,
        'execute_command':[sys.executable,'-m',LAUNCHER,'--output',str(output),'--plan-sha256',sha(output/'plan.json')],
        'external_whole_python_clock_required':True,'performance_executed':False,'native_calls':0}
    write(output/'ready.json',ready);return ready


def expected_order():
    return [(family,batch,arm,index) for family in FAMILIES for batch,arm in enumerate(ARMS) for index in range(PER_BATCH)]


def check_records(records,batches,input_hashes,result_hashes):
    require(type(records) is list and len(records)==COUNTS['measured_invocations'],'record_count')
    require([(r['family'],r['batch'],r['arm'],r['index']) for r in records]==expected_order(),'record_order')
    require(type(batches) is list and len(batches)==8,'batch_count')
    require([(b['family'],b['batch'],b['arm']) for b in batches]==[(f,i,a) for f in FAMILIES for i,a in enumerate(ARMS)],'batch_order')
    previous=-1
    for row in records:
        require(set(row)=={'family','batch','arm','index','started_ns','fixture_finished_ns','isolated_started_ns',
            'isolated_finished_ns','checked_ns','isolated_ns','cpu_ns','input_sha256','result_sha256','guards_and_aliases_passed'},'record_fields')
        keys=('batch','index','started_ns','fixture_finished_ns','isolated_started_ns','isolated_finished_ns','checked_ns','isolated_ns','cpu_ns')
        require(all(type(row[k]) is int and row[k]>=0 for k in keys),'clock_type')
        require(previous<=row['started_ns']<=row['fixture_finished_ns']<=row['isolated_started_ns']
            <=row['isolated_finished_ns']<=row['checked_ns'] and row['isolated_ns']==row['isolated_finished_ns']-row['isolated_started_ns'],'clock_order')
        require(row['input_sha256']==input_hashes[row['family']] and row['result_sha256']==result_hashes[row['family']]
            and row['guards_and_aliases_passed'] is True,'result_identity');previous=row['checked_ns']
    prior=-1
    for b in batches:
        require(set(b)=={'family','batch','arm','started_ns','finished_ns','whole_ns'},'batch_fields')
        require(all(type(b[k]) is int and b[k]>=0 for k in ('batch','started_ns','finished_ns','whole_ns')),'batch_clock_type')
        rows=[r for r in records if r['family']==b['family'] and r['batch']==b['batch']]
        require(prior<=b['started_ns']<=rows[0]['started_ns']<=rows[-1]['checked_ns']<=b['finished_ns']
            and b['whole_ns']==b['finished_ns']-b['started_ns'],'batch_containment');prior=b['finished_ns']
    return {family:{arm:{
        'isolated_batch_ms':[sum(r['isolated_ns'] for r in records if r['family']==family and r['batch']==i)/1e6 for i,a in enumerate(ARMS) if a==arm],
        'whole_batch_ms':[b['whole_ns']/1e6 for b in batches if b['family']==family and b['arm']==arm],
        'median_isolated_batch_ms':statistics.median(sum(r['isolated_ns'] for r in records if r['family']==family and r['batch']==i)/1e6 for i,a in enumerate(ARMS) if a==arm),
        'median_whole_batch_ms':statistics.median(b['whole_ns']/1e6 for b in batches if b['family']==family and b['arm']==arm)} for arm in ('A','B')} for family in FAMILIES}


def saved_check(output,plan,expected):
    result=loads((output/'result.json').read_bytes())
    require(result['schema']==SCHEMA and result['status']=='passed_synthetic_cost_diagnostic_only'
        and result['plan_sha256']==expected and exact(result['counts'],COUNTS) and result['source_changed']==[]
        and type(result['native_calls']) is int and type(result['policy_replays']) is int
        and result['native_calls']==result['policy_replays']==0 and result['full_audit_accepted'] is False,'saved_scope')
    rows=[loads(line) for line in (output/'measurements.jsonl').read_bytes().splitlines()]
    require(exact(rows,result['records']),'saved_record_readback')
    for family in FAMILIES:
        for kind,hashes in (('input',result['input_hashes']),('reference',result['result_hashes'])):
            data=(output/(family+'.'+kind+'.json')).read_bytes();loads(data)
            require(digest(data)==hashes[family],'saved_full_'+kind)
    require(exact(check_records(rows,result['batches'],result['input_hashes'],result['result_hashes']),result['summary']),'saved_summary')
    require(all(type(result[k]) is int and result[k]>=0 for k in
        ('worker_started_ns','worker_before_export_ns','worker_before_final_export_ns')),'worker_clock')
    require(result['worker_before_final_export_ns']==result['worker_before_export_ns']-result['worker_started_ns']
        and result['worker_started_ns']<=result['batches'][0]['started_ns']
        <=result['batches'][-1]['finished_ns']<=result['worker_before_export_ns'],'worker_containment')
    verify_pins(output,plan,runtime=True)
    return result


def worker(output,expected):
    require(sys.stdin.readline().strip()==expected==sha(output/'plan.json'),'owned_admission')
    started=time.perf_counter_ns();plan=loads((output/'plan.json').read_bytes());verify_pins(output,plan,runtime=True)
    records=[];batches=[];input_hashes={};result_hashes={};reference={};stage='entry'
    try:
        with (output/'measurements.jsonl').open('xb') as journal:
            for family in FAMILIES:
                for batch,arm in enumerate(ARMS):
                    batch_start=time.perf_counter_ns()
                    for index in range(PER_BATCH):
                        row={'family':family,'batch':batch,'arm':arm,'index':index,'started_ns':time.perf_counter_ns()}
                        try:
                            stage='fixture';case=f.make_case(family);before=encoded(inputs(case))
                            input_sha=digest(before);row['fixture_finished_ns']=time.perf_counter_ns()
                            stage='invoke';row['isolated_started_ns']=time.perf_counter_ns();cpu=time.process_time_ns()
                            value=f.invoke(case,arm)
                            cpu_end=time.process_time_ns();row['isolated_finished_ns']=time.perf_counter_ns()
                            row['isolated_ns']=row['isolated_finished_ns']-row['isolated_started_ns'];row['cpu_ns']=cpu_end-cpu
                            stage='exact_and_alias_checks';payload=checked_result(case,arm,value,before);data=encoded(payload)
                            if family not in reference:
                                require(batch==index==0 and arm=='A','first_reference')
                                reference[family]=data;input_hashes[family]=input_sha;result_hashes[family]=digest(data)
                                (output/(family+'.input.json')).write_bytes(before)
                                (output/(family+'.reference.json')).write_bytes(data)
                            require(input_sha==input_hashes[family] and data==reference[family],'full_value_or_fixture_mismatch')
                            row.update(input_sha256=input_sha,result_sha256=digest(data),guards_and_aliases_passed=True,checked_ns=time.perf_counter_ns())
                            line=encoded(row)+b'\n';require(journal.write(line)==len(line),'short_journal');journal.flush();records.append(row)
                            del value,payload,data,case,before
                        except BaseException as error:
                            failure={**row,'status':'unknown_failed','stage':stage,'error':repr(error),'failure_observed_ns':time.perf_counter_ns()}
                            try:journal.write(encoded(failure)+b'\n');journal.flush()
                            except BaseException as export_error:
                                error.add_note('failure journal export also failed: '+repr(export_error))
                            raise
                    end=time.perf_counter_ns();batches.append({'family':family,'batch':batch,'arm':arm,'started_ns':batch_start,'finished_ns':end,'whole_ns':end-batch_start})
        summary=check_records(records,batches,input_hashes,result_hashes);verify_pins(output,plan,runtime=True)
        before_export=time.perf_counter_ns()
        write(output/'result.json',{'schema':SCHEMA,'status':'passed_synthetic_cost_diagnostic_only','plan_sha256':expected,
            'records':records,'batches':batches,'input_hashes':input_hashes,'result_hashes':result_hashes,'summary':summary,
            'counts':COUNTS,'source_changed':[],'worker_started_ns':started,'worker_before_export_ns':before_export,
            'worker_before_final_export_ns':before_export-started,
            'native_calls':0,'policy_replays':0,'full_audit_accepted':False})
        saved_check(output,plan,expected)
    except BaseException as error:
        write(output/'failure.json',{'status':'unknown_failed','stage':stage,'error':repr(error),
            'completed_measurements':len(records),'elapsed_ns':time.perf_counter_ns()-started});raise


def execute(output,expected):
    write(output/'execution_claim.json',{'plan_sha256':expected,'no_retry':True})
    process=None;error=None
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--worker','--plan-sha256',expected]
    try:
        require(sha(output/'plan.json')==expected,'plan_identity');plan=loads((output/'plan.json').read_bytes());verify_pins(output,plan,runtime=True)
        remaining=LIMIT-(time.perf_counter()-BOOT);require(remaining>0,'prelaunch_budget')
        with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=expected,cwd=ROOT)
        require(process['status']=='exited' and process['exitcode']==0,'worker_exit')
        saved_check(output,plan,expected)
        require(time.perf_counter()-BOOT<=LIMIT,'whole_budget')
    except BaseException as failure:error=repr(failure)
    write(output/'launch_receipt.json',{'schema':SCHEMA+'.launch','status':'completed' if error is None else 'unknown_failed_or_timeout',
        'process':process,'command':command,'error':error,'plan_sha256':expected,'shared_seconds':LIMIT,
        'after_BOOT_before_final_receipt_seconds':time.perf_counter()-BOOT,'external_whole_python_clock_required':True,
        'artifacts':{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name in ('result.json','measurements.jsonl','failure.json','stdout.log','stderr.log')},
        'native_calls':0,'policy_replays':0})
    return 0 if error is None else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--pure',type=Path)
    p.add_argument('--prepare',action='store_true');p.add_argument('--campaign-child',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--plan-sha256')
    a=p.parse_args();require(sum((a.prepare,a.campaign_child,a.worker))==1,'mode');output=a.output.resolve()
    if a.prepare:print(encoded(prepare(output,a.pure.resolve())).decode());return 0
    if a.worker:worker(output,a.plan_sha256);return 0
    require(sys.stdin.readline().strip()==a.plan_sha256==sha(output/'plan.json'),'campaign_owned_admission')
    return execute(output,a.plan_sha256)


if __name__=='__main__':raise SystemExit(main())
