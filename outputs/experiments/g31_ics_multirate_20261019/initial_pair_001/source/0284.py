"""Prepare-only until dispatch: fixed saved18 ABBA72 evidence/return mock.

No native session, request policy, predictor or observation is executed. Current
publication construction clocks are measured; historical event/root clocks are
immutable fixture data and cannot establish a new native-root latency result.
"""
import time
BOOT=time.monotonic()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import traceback
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import root_evidence_mock as m

c=m.old
LIMIT=240.
SCHEMA='g31.single_root_evidence_ABBA.v1'


def rows(keys):
    return [{'key':key,'arm':arm,'position':position} for key in keys for position,arm in enumerate('ABBA')]


def prepare(output,pure):
    output.mkdir(parents=True,exist_ok=False)
    p=c.read(pure);xml=pure.parent/'tests.xml';tests=ET.parse(xml).getroot().findall('.//testcase')
    c.require(p['status']=='passed' and p['source_changed']==[] and p['native_calls']==p['new_predictions']==0
        and p['XML_sha256']==c.sha(xml) and len(tests)==p['tests'] and len(tests)>=35 and
        not any(t.tag in ('failure','error','skipped') for case in tests for t in case),'pure_gate')
    for name,h in p['source_sha256'].items():
        c.require(c.sha(c.ROOT/name)==h and c.sha(pure.parent/'source'/name)==h,'pure_source_changed')
    original=c.verify_plan(m.SOURCE,m.CAMPAIGN_SHA)
    ledger=c.read(m.SOURCE/'branch_ledger.json')
    c.require(list(ledger)==original['row_order'] and len(ledger)==18 and
        all(r['status']=='raw_saved' for r in ledger.values()),'original18')
    files=c.image.source_closure(c.ROOT,(__package__+'.measure_single_root_evidence',__package__+'.single_root_evidence',
        __package__+'.root_evidence_mock',__package__+'.run_single_root_evidence_pure',
        'tests.test_g31_circulation_single_root_evidence'))
    sources,archive={},{}
    for name,data in files.items():
        dest=output/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        sources[str(c.ROOT/name)]=hashlib.sha256(data).hexdigest();archive[str(c.ROOT/name)]=str(dest.relative_to(output))
    plan={'schema':SCHEMA,'row_order':rows(original['row_order']),'publication_calls':72,
        'historical_roots':18,'calls_per_arm':36,'arms':{'A':'Frozen v3 complete evidence and return construction',
        'B':'Fresh complete normalize/encode once and ownership transfer; original strict artifact roundtrip retained'},
        'source_sha256':sources,'source_archive':archive,'input_campaign':c.reference(m.SOURCE/'campaign.json'),
        'input_ledger':c.reference(m.SOURCE/'branch_ledger.json'),
        'input_raw':{key:ledger[key]['raw'] for key in original['row_order']},
        'input_saved_verification':c.reference(m.SOURCE/'verification.json'),
        'pure_reference':c.reference(pure),'pure_XML':c.reference(xml),
        'hard_timeout_seconds':LIMIT,'environment':{'python':sys.executable,'sha256':c.sha(sys.executable)},
        'scope':{'fixed_data':'All original18 root events/endpoints/scalars/order preserved. No root, observation or native capability is recomputed.',
            'clock':'Only current evidence/publication construction is timed. Historic request/event clocks are data; regenerated body/outside/warm/within100 fields are never interpreted as native root latency.',
            'cost':'Each sample includes mock root construction, complete evidence normalization/encode, strict decode/equality, ledger/return codec and publisher append/return. Setup, source checks, all artifact export/readback and shutdown stay in whole240 campaign. Nothing removed from old timings.',
            'budget_basis':'36 old and36 candidate full constructions, plus18 saved fixture reads and72 complete exported readbacks. The known old finalization intervals reach3.1s;240s is a fixed censoring bound, not a promised runtime.',
            'no_claim':['algorithm acceleration','complete native request100ms','new prediction','observation gate benefit','physical trace change']},
        'status':'prepared_unexecuted'}
    c.write(output/'plan.json',plan)
    c.write(output/'ledger.json',[{**r,'status':'unknown_unexecuted'} for r in plan['row_order']])
    verify_pins(output,c.sha(output/'plan.json'))
    c.write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':c.reference(output/'plan.json'),
        'source_count':len(sources),'pure_tests':len(tests),'native_calls':0,'new_predictions':0,
        'performance_dispatched':False,'command':[sys.executable,'-m',__package__+'.measure_single_root_evidence',
            '--execute','--output',str(output),'--plan-sha256',c.sha(output/'plan.json')]})


def verify_pins(output,expected):
    c.require(c.sha(output/'plan.json')==expected,'mock_plan_sha')
    p=c.read(output/'plan.json')
    c.require(p['schema']==SCHEMA and p['publication_calls']==72 and p['historical_roots']==18 and
        p['calls_per_arm']==36 and p['hard_timeout_seconds']==LIMIT,'mock_denominator')
    for f,h in p['source_sha256'].items():
        c.require(c.sha(f)==h and c.sha(output/p['source_archive'][f])==h,'mock_source_changed')
    for ref in [p['input_campaign'],p['input_ledger'],p['input_saved_verification'],p['pure_reference'],p['pure_XML'],*p['input_raw'].values()]:
        c.require(c.sha(ref['path'])==ref['sha256'],'mock_input_changed')
    c.require(p['row_order']==rows(list(p['input_raw'])),'mock_order')
    c.require(c.sha(p['environment']['python'])==p['environment']['sha256'],'mock_interpreter_changed')
    return p


def verify_saved(output,expected):
    plan=verify_pins(output,expected);inputs=dict(m.load_inputs());ledger=c.read(output/'ledger.json')
    c.require(len(ledger)==72,'saved_denominator')
    samples=[]
    for index,(row,declared) in enumerate(zip(ledger,plan['row_order'])):
        c.require(m.candidate.exact_tree({k:row[k] for k in declared},declared) and row['status']=='saved','saved_row_identity')
        path=output/'raw'/f'{index:03d}.json.gz';c.require(row['raw']==c.reference(path),'saved_row_hash')
        with gzip.open(path,'rt',encoding='utf8') as stream:data=json.load(stream)
        c.require(type(data) is dict and tuple(data)==('declaration','record'),'saved_artifact_topology')
        c.require(m.candidate.exact_tree(data['declaration'],declared),'saved_declaration')
        m.current_clock_bounds(data['record'],row['started_ns'],row['finished_ns'])
        c.require(type(row['elapsed_ns']) is int and row['elapsed_ns']==row['finished_ns']-row['started_ns'] and row['elapsed_ns']>=0,'sample_clock')
        c.require(m.candidate.exact_tree(m.semantic_record(data['record']),
            m.semantic_record(inputs[declared['key']])),'complete_ordered_semantics_changed')
        samples.append({**declared,'elapsed_ms':row['elapsed_ns']/1e6,'raw':row['raw']})
    arm_values={arm:[r['elapsed_ms'] for r in samples if r['arm']==arm] for arm in ('A','B')}
    return {'status':'passed_saved18_ABBA72_exact_evidence','plan_sha256':expected,'samples':samples,
        'summary_ms':{arm:{'count':len(v),'min':min(v),'median':statistics.median(v),'max':max(v)} for arm,v in arm_values.items()},
        'native_calls':0,'new_predictions':0,'complete_native_root_100ms_certified':False,
        'scope':'Current mock evidence/return construction only, not historical root time or live-policy performance. All72 samples retained; whole240 includes setup/export/full saved verification.'}


def worker(output,expected):
    plan=verify_pins(output,expected)
    loaded_entry=c.check_loaded_sources(plan)
    bindings={arm:m.functions(arm,time) for arm in ('A','B')}
    inputs=dict(m.load_inputs());ledger=c.read(output/'ledger.json')
    try:
        for index,row in enumerate(ledger):
            declared=plan['row_order'][index];value=inputs[row['key']]['value']['evidence']
            method,publish=bindings[row['arm']]
            row['status']='unknown_in_progress';c.write(output/'ledger.json',ledger)
            start=time.perf_counter_ns()
            root=m.root_from_evidence(value,method);holder=[]
            result=publish(root,holder)
            finished=time.perf_counter_ns()
            m.current_clock_bounds(result,start,finished)
            row.update(started_ns=start,finished_ns=finished,elapsed_ns=finished-start)
            path=output/'raw'/f'{index:03d}.json.gz';path.parent.mkdir(exist_ok=True)
            with gzip.open(path,'wt',encoding='utf8',compresslevel=1) as stream:
                json.dump({'declaration':declared,'record':result},stream,ensure_ascii=False,allow_nan=False)
            row.update(status='saved',raw=c.reference(path));c.write(output/'ledger.json',ledger)
            del root,holder,result
        report=verify_saved(output,expected)
        c.write(output/'report.json',report)
        verify_pins(output,expected)
        loaded_exit=c.check_loaded_sources(plan)
        c.write(output/'receipt.json',{'status':'completed_mock_ABBA','plan_sha256':expected,
            'source_changed':[],'report':c.reference(output/'report.json'),'native_calls':0,'new_predictions':0,
            'loaded_project_sources_entry':loaded_entry,'loaded_project_sources_exit':loaded_exit})
    except BaseException:
        c.write(output/'failure.json',{'status':'unknown_or_failed_mock','error':traceback.format_exc()})
        c.write(output/'ledger.json',ledger)
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--pure-receipt',type=Path)
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true')
    p.add_argument('--plan-sha256');a=p.parse_args();output=a.output.resolve()
    if a.prepare:prepare(output,a.pure_receipt.resolve());return 0
    if a.worker:
        if sys.stdin.readline()!=a.plan_sha256+'\n':raise ValueError('mock_job_admission')
        worker(output,a.plan_sha256);return 0
    if not a.execute:raise ValueError('explicit_action_required')
    verify_pins(output,a.plan_sha256)
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'plan_sha256':a.plan_sha256,'shared_seconds':LIMIT},stream)
    command=[sys.executable,'-m',__package__+'.measure_single_root_evidence','--worker',
        '--output',str(output),'--plan-sha256',a.plan_sha256]
    remaining=LIMIT-(time.monotonic()-BOOT)
    if remaining<=0:raise TimeoutError('mock_budget_before_worker')
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=remaining,
            admission=a.plan_sha256,stdout=out,stderr=err,cwd=c.ROOT)
    c.write(output/'bounded_execution.json',{'process':process,'command':command,
        'post_import_before_final_export_seconds':time.monotonic()-BOOT,
        'report':c.reference(output/'report.json') if (output/'report.json').exists() else None,
        'external_launch_through_exit_clock_required':True,'native_calls':0,'new_predictions':0})
    return 0 if process['status']=='exited' and process['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
