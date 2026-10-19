"""Saved64/text readback only. Does not call either actor-copy kernel."""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET
from . import measure_bridge_actor_reparse as producer
from . import review_bridge_saved_kernel_cost as helpers
from . import bounded_windows_job

ROOT,OUT=producer.ROOT,producer.OUT
PACKAGE=OUT/'bridge_actor_reparse_prepare_001'
PLAN='c56c64f5ecdd0aa3cd71f23eb9ef2bb6d9c65c7e9d0e2071a52890a74fcf234e'
RESULT='e23bc20c9e66fd7e6933149c3c8a214043c2bbe41dfa83e3f81f9d0d494e7b50'
LAUNCH='3409a4a04549c9304f520dc06a2b0b46f3ca3b8348933995496f70f58ebaf258'
EXTERNAL='9c02fa3b5b1216365c714542604df687c3ebd542b99a4f5d9a7186dc4da7257f'
MODULE='scripts.experiments.g31_ics_circulation.review_bridge_actor_reparse_saved'
LIMIT=120.
require,sha,read,write,exact=helpers.require,helpers.sha,helpers.read,helpers.write,helpers.exact


def audit(source_sha,helper_sha):
    require(sha(__file__)==source_sha and sha(helpers.__file__)==helper_sha,'review_source')
    for name,digest in [('plan.json',PLAN),('result.json',RESULT),('launch_receipt.json',LAUNCH),
                        ('external_application_wall.json',EXTERNAL)]:
        require(sha(PACKAGE/name)==digest,'authority:'+name)
    plan=read(PACKAGE/'plan.json');launch=read(PACKAGE/'launch_receipt.json')
    external=read(PACKAGE/'external_application_wall.json');result=read(PACKAGE/'result.json')
    producer.verify_pins(PACKAGE,plan)
    require(len(plan['sources'])==80,'source80')
    require(launch['status']=='completed' and launch['error'] is None and launch['plan_sha256']==PLAN
        and launch['shared_seconds']==120.,'launch')
    process=launch['process']
    require(process['status']=='exited' and type(process['exitcode']) is int and process['exitcode']==0
        and process['windows_job_kill_on_close'] is True and process['child_released_only_after_job_assignment'] is True,'owned_child')
    require(launch['command']==[sys.executable,'-m',producer.MODULE,'--output',str(PACKAGE),'--worker','--plan-sha256',PLAN],'command')
    require(external['status']=='application_exited_zero' and type(external['exit_code']) is int
        and external['exit_code']==0 and external['error'] is None and external['evidence_unchanged'] is True
        and external['plan_sha256']==PLAN and external['python_sha256']==plan['interpreter_sha256']
        and type(external['whole_python_application_seconds']) in (int,float)
        and 0<external['whole_python_application_seconds']<=120 and external['whole_python_within_120_seconds'] is True,'external')
    expected={'fixed_inputs':16,'comparison_calls':0,'copy_calls':64,'first_observer_parses':16,
        'second_actor_parses':32,'actor_deepcopies':32,'native_calls':0,'policy_replay_calls':0}
    require(all(type(external[k]) is int and external[k]==v for k,v in expected.items()),'external_counts')
    require(external['full_saved_audit_certified'] is False and external['complete_native_request_100ms_certified'] is False,'external_scope')
    require(set(launch['artifacts'])=={'result.json','measurements.jsonl','stdout.log','stderr.log'},'artifact_domain')
    for name,digest in launch['artifacts'].items():require(sha(PACKAGE/name)==digest,'artifact:'+name)
    require((PACKAGE/'stdout.log').stat().st_size==(PACKAGE/'stderr.log').stat().st_size==0
        and not (PACKAGE/'failure.json').exists(),'original_failure')
    lines=(PACKAGE/'measurements.jsonl').read_bytes().splitlines(keepends=True)
    require(len(lines)==64 and all(line.endswith(b'\n') for line in lines),'journal64')
    records=[helpers.loads(line.decode('utf8')) for line in lines]
    require(exact(records,result['records']),'journal_result')
    # Exactly one default parse per input. No deepcopy, actor_copy,
    # actor_reparse, second parse or timed diagnostic kernel is called.
    inputs=[];digests=[]
    for index,item in enumerate(plan['files']):
        path=PACKAGE/'fixtures'/item['file']
        require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],'input_bytes')
        with gzip.open(path,'rt',encoding='utf8') as stream:text=stream.read(producer.MAX_TEXT+1)
        require(len(text)<=producer.MAX_TEXT,'decode_bound')
        row=json.loads(text)
        producer.frozen.decoded_tree(row)
        require(type(row['ordinal']) is int and row['ordinal']==item['ordinal']
            and row['endpoint']==item['endpoint'] and 'result' in row and 'error' not in row,'row_identity')
        digest=hashlib.sha256(helpers.dumps(row['result']).encode('utf8')).hexdigest()
        digests.append(digest)
        meta={'side':item['side'],'ordinal':item['ordinal'],'gzip_sha256':item['sha256'],
            'decoded_text_sha256':hashlib.sha256(text.encode('utf8')).hexdigest(),'decoded_characters':len(text)}
        require(exact(meta,result['input_texts'][index]),'same_original_text')
        inputs.append({**meta,'gzip_bytes':item['bytes'],'result_sha256':digest})
        del row,text
    require(exact(digests,result['result_digests']),'all16_result_digests')
    require(exact(result['counts'],{'input_files':16,'batches':4,'actor_copies':64,
        'A_deepcopies':32,'B_second_parses':32,'first_observer_parses':16}),'result_counts')
    expected_order=[(batch,arm,index) for batch,arm in enumerate(('A','B','B','A')) for index in range(16)]
    require([(r['batch'],r['arm'],r['index']) for r in records]==expected_order,'record_order')
    previous=-1
    for row in records:
        require(set(row)=={'batch','arm','index','ordinal','side','started_ns','finished_ns',
            'wall_ns','cpu_ns','result_sha256','mutable_disjoint'},'record_fields')
        require(all(type(row[k]) is int and row[k]>=0 for k in
            ('batch','index','ordinal','started_ns','finished_ns','wall_ns','cpu_ns')),'clock_type')
        require(previous<=row['started_ns']<=row['finished_ns'] and row['wall_ns']==row['finished_ns']-row['started_ns'],'clock_order')
        require(row['ordinal']==27210+row['index']%8 and row['side']==('old' if row['index']<8 else 'new')
            and row['result_sha256']==digests[row['index']] and row['mutable_disjoint'] is True,'result_identity')
        previous=row['finished_ns']
    summary={}
    for arm in ('A','B'):
        batches=[sum(row['wall_ns'] for row in records if row['batch']==batch)/1e6
            for batch,chosen in enumerate(('A','B','B','A')) if chosen==arm]
        summary[arm]={'batch_ms':batches,'median_batch_ms':statistics.median(batches)}
    require(exact(summary,result['summary']),'summary')
    producer.check_saved_result(result,plan,PLAN)
    counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure']['xml']).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
    require(counts=={'tests':50,'failures':0,'errors':0,'skipped':0},'pure50')
    producer.verify_pins(PACKAGE,plan)
    loaded={str(Path(m.__file__).resolve().relative_to(ROOT)) for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    extra={str(Path(__file__).resolve().relative_to(ROOT)),str(Path(helpers.__file__).resolve().relative_to(ROOT))}
    require(loaded<=set(plan['sources'])|extra,'loaded_domain')
    require(sha(__file__)==source_sha and sha(helpers.__file__)==helper_sha,'review_source_after')
    return {'schema':'g31.bridge.actor_reparse.saved_readback.v1','status':'passed_saved_readback',
        'reviewer_role':'Producer author; independent saved aggregation, not author-independent certification.',
        'authority':{name:sha(PACKAGE/name) for name in ('plan.json','result.json','launch_receipt.json','external_application_wall.json','measurements.jsonl')},
        'source_count':80,'source_current_archive_exact':True,'pure_counts':counts,'loaded_sources':sorted(loaded),
        'input_rows':inputs,'measurement_rows':64,'summary':summary,
        'median_reduction_percent':100*(1-summary['B']['median_batch_ms']/summary['A']['median_batch_ms']),
        'original_full_python_seconds':external['whole_python_application_seconds'],
        'first_decode_domain_ms':result['first_decompression_parse_domain_ns']/1e6,
        'worker_before_export_ms':result['worker_before_final_export_ns']/1e6,
        'new_kernel_calls':0,'new_native_calls':0,'new_policy_replays':0,'full_bridge_audit_accepted':False,
        'limitations':['64 returned copy objects were not persisted. Their digest values are rechecked against all16 source texts; alias isolation remains pinned successful runtime checks plus50pure evidence.',
            'Fixed tail8 only, two batches perarm. Copy savings and earlier comparison savings are separate local costs, not an additive percentage or full600 completion guarantee.',
            'All initial decode/domain/identity, output validation, cleanup and export remain whole wall; no historical cost subtraction.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--source-sha');p.add_argument('--helper-sha')
    a=p.parse_args();out=a.output.resolve()
    if a.worker:
        require(sys.stdin.readline().rstrip('\n')==a.source_sha,'admission')
        try:write(out/'report.json',audit(a.source_sha,a.helper_sha))
        except BaseException as error:write(out/'failure.json',{'status':'unknown_failed','error':repr(error)});raise
        return 0
    require(not out.exists(),'preserve_output');out.mkdir()
    source,helper=sha(__file__),sha(helpers.__file__)
    cmd=[sys.executable,'-m',MODULE,'--output',str(out),'--worker','--source-sha',source,'--helper-sha',helper]
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        process=bounded_windows_job.run(cmd,timeout=LIMIT-(time.perf_counter()-BOOT),stdout=stdout,
            stderr=stderr,admission=source,cwd=ROOT)
    ok=process['status']=='exited' and process['exitcode']==0 and (out/'report.json').exists()
    write(out/'bounded_execution.json',{'status':'completed' if ok else 'unknown_failed_or_timeout','process':process,
        'command':cmd,'shared_seconds':LIMIT,'source_sha256':source,'helper_sha256':helper,
        'after_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'external_full_wall_required':True,
        'report_sha256':sha(out/'report.json') if (out/'report.json').exists() else None,'kernel_calls':0,'native_calls':0})
    return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())
