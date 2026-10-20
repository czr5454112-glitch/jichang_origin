"""Independent full saved96 readback; no model or native execution."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse, gzip, json, math, statistics, sys, traceback
from pathlib import Path
from . import bounded_windows_job
from . import diagnose_live_communication_conformance as comparison
from . import validate_live_communication_projection as verifier
from . import live_obligation_delivered_context as context

ROOT=verifier.ROOT;OUT=verifier.OUT
SOURCE=OUT/'live_communication_lazy_prepare_001'
MODULE='scripts.experiments.g31_ics_circulation.review_live_communication_lazy_saved'
LIMIT=180.
sha,read,ref,require,write=(getattr(comparison,k) for k in ('sha','read','ref','require','write'))
EXPECTED={
 'plan.json':'afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497',
 'rows.json':'7753bc2c9731ded83300435814f5b9c033197237cbaaa0c33721fe09c1a74a3e',
 'receipt.json':'14fa792612e889e06873675b22407f8ccf32c3c925c69e374c38e90f6e3e14f4',
 'final_receipt.json':'07b26e476cd5ab328498e919a88503aa2ee64ef73ed21d6c02eb9af0f01c36b0',
 'equivalence73.json':'0efdd4b8d2bfadeb453c1872abb6b422ff1daaa0960eb126de0abac7cb735b1f',
 'bounded_execution.json':'0fa334b9e8ef4a9bc8a31657ab05e4763903dcecae8da8f6ec50252f45c0e044',
 'external_application_wall.json':'44c8a3ebe28f4649e5fa273419d90f675fa2ea6f71dc6b7fcd2581db9511268b',
 'final_exit_pins.json':'1eb0e423e2b25abf405b20a4d8f4ff00dd49fb80ea18b20094d375c4eb25a782'}


def producer():
    require(all(sha(SOURCE/k)==v for k,v in EXPECTED.items()),'saved96_terminal_identities')
    p=read(SOURCE/'plan.json');r=read(SOURCE/'receipt.json');f=read(SOURCE/'final_receipt.json')
    b=read(SOURCE/'bounded_execution.json');e=read(SOURCE/'external_application_wall.json')
    require(p['order']==comparison.ORDER and len(p['source_sha256'])==100 and len(p['saved73_equivalence'])==73,'saved96_domain')
    require(r['status']=='exact_all96_conformance' and r['counts']=={'exact_conformance':96}
        and r['model_evaluations']==96 and r['actual_collection_data_checks']==226
        and r['actual_known_collection_data']==192 and r['source_changed']==[],'saved96_producer_receipt')
    require(f['status']=='exact_all96_and_saved73' and f['full_output_exact_count']==73
        and f['new_model_evaluations']==96 and f['new_counts']=={'exact_conformance':96}
        and f['source_changed']==[] and f['native_calls']==0,'saved96_final_gate')
    for key,name in (('model_receipt','receipt.json'),('rows','rows.json'),('equivalence73','equivalence73.json'),
                     ('final_exit_pins','final_exit_pins.json'),('plan','plan.json')):
        require(f[key]==ref(SOURCE/name),'saved96_final_reference')
    require(b['status']=='bounded_worker_completed' and b['process']['status']=='exited'
        and b['process']['exitcode']==0 and b['process']['windows_job_kill_on_close'] is True
        and b['process']['child_released_only_after_job_assignment'] is True
        and b['final_receipt']==ref(SOURCE/'final_receipt.json')
        and b['plan_sha256']==EXPECTED['plan.json'] and b['fixed_application_seconds']==360.,'saved96_bounded')
    require(e['status']=='application_exited_zero' and e['exit_code']==0 and e['error'] is None
        and e['evidence_unchanged'] is True and e['whole_python_within_360_seconds'] is True
        and 0<b['process']['wall_seconds']<=b['application_seconds_before_final_receipt']
        <=e['whole_python_application_seconds']<=360,'saved96_outer_clock')
    require(e['plan_sha256']==EXPECTED['plan.json'] and e['shared_owned_seconds']==360
        and e['native_calls']==0 and e['maximum_model_evaluations']==96,'saved96_outer_scope')
    ready=read(SOURCE/'root_ready_001.json');review=read(ready['root_review']['path'])
    require(sha(ready['root_review']['path'])==ready['root_review']['sha256']
        and review['plan']==ref(SOURCE/'plan.json') and ready['plan_sha256']==EXPECTED['plan.json']
        and ready['wrapper_sha256']==e['wrapper_sha256']==review['wrapper']['sha256']
        and sha(review['wrapper']['path'])==e['wrapper_sha256'],'saved96_root_identity')
    require(p['environment']=={'python':sys.executable,'sha256':sha(sys.executable)}
        and e['python_sha256']==p['environment']['sha256'],'saved96_python_identity')
    pins={**p['source_sha256'],**p['fixed_evidence_sha256']}
    for path,digest in p['source_sha256'].items():pins[str(SOURCE/p['source_archive'][path])]=digest
    require(all(read(SOURCE/name)==pins for name in ('entry_pins.json','exit_pins.json','final_exit_pins.json')),
        'saved96_recorded_entry_exit_pins')
    original=read(verifier.ACTUAL/'preregistered_protocol.json')
    require(len(original['source_sha256'])==93,'saved96_original93')
    for path,digest in original['source_sha256'].items():
        require(path not in pins or pins[path]==digest,'saved96_source_conflict')
        pins[path]=digest;pins[str(verifier.ACTUAL/original['source_archive'][path])]=digest
    for key,value in EXPECTED.items():pins[str(SOURCE/key)]=value
    return p,pins,e


def prepare(output):
    p,pins,e=producer();output.mkdir(parents=True,exist_ok=False)
    sources={str(path):sha(path) for path in verifier.source_paths()};archives={}
    for path,digest in sources.items():
        target=Path('source')/Path(path).relative_to(ROOT);(output/target).parent.mkdir(parents=True,exist_ok=True)
        (output/target).write_bytes(Path(path).read_bytes());archives[path]=str(target)
    plan={'schema':'g31.lazy96.independent_saved_plan.v1','source_sha256':sources,'source_archive':archives,
        'producer_expected':EXPECTED,'producer_pins':pins,'fixed_seconds':LIMIT,'native_calls':0,'model_evaluations':0,
        'basis':'Partial73 full saved audit took32.5775669s; full96 plus73 byte equivalence uses fixed180. No guarantee.',
        'scope':'All96 saved outputs, original initial/later guards, exact endpoints/chronology and all saved producer pins; no prediction.'}
    write(output/'plan.json',plan)
    print(json.dumps({'plan':ref(output/'plan.json'),'audit_sources':len(sources),'fixed_seconds':LIMIT}))


def verify_plan(output,expected):
    require(sha(output/'plan.json')==expected,'saved96_audit_plan')
    plan=read(output/'plan.json');require(plan['producer_expected']==EXPECTED and plan['fixed_seconds']==LIMIT,'saved96_audit_scope')
    for path,digest in plan['source_sha256'].items():
        require(sha(path)==sha(output/plan['source_archive'][path])==digest,'saved96_audit_source')
    return plan


def worker(output,expected):
    start=time.perf_counter();audit=verify_plan(output,expected);plan,pins,outer=producer()
    require(pins==audit['producer_pins'],'saved96_frozen_producer_pins')
    for path,digest in audit['source_sha256'].items():
        require(path not in pins or pins[path]==digest,'saved96_audit_source_conflict')
        pins[path]=digest;pins[str(output/audit['source_archive'][path])]=digest
    loaded_entry=verifier.source_paths()
    require(set(map(str,loaded_entry))<=set(audit['source_sha256']),'saved96_loaded_entry')
    entry={p:sha(p) for p in pins};require(entry==pins,'saved96_current_and_archive_entry');write(output/'entry_pins.json',entry)
    rows=read(SOURCE/'rows.json');require(list(rows)==comparison.ORDER,'saved96_row_order')
    oldchecks=read(SOURCE/'equivalence73.json');require(list(oldchecks)==list(plan['saved73_equivalence']),'saved73_domain')
    checks={};prediction_pins={};attempt_count=known_count=equal_count=0
    for index,key in enumerate(comparison.ORDER):
        saved=rows[key];require(saved['status']=='exact_conformance' and saved['execution_index']==index,'saved96_row_status')
        pred=saved['prediction'];prediction_pins[pred['path']]=pred['sha256'];require(sha(pred['path'])==pred['sha256'],'saved96_prediction_hash')
        body=gzip.decompress(Path(pred['path']).read_bytes());projected=json.loads(body)
        rawref=plan['rows'][key]['actual_raw'];require(sha(rawref['path'])==rawref['sha256'],'saved96_actual_hash')
        raw=json.loads(gzip.decompress(Path(rawref['path']).read_bytes()))
        require(raw['specification']['case']==key.split('/')[0]
            and comparison.exact(raw['specification']['vector'],plan['rows'][key]['action']),'saved96_case_action')
        contexts={o:context.initial_context(**verifier.public_initial(raw,o)) for o in ('A','B')}
        require(all(type(v) is context.SuppliedContext for v in contexts.values()),'saved96_initial_guard')
        facts={o:context.initial_projection_bundle(v) for o,v in contexts.items()}
        require(all(context.encoded({'value':facts['A'][field]})==context.encoded({'value':facts['B'][field]})
            for field in ('jobs','trays','contract','now')),'saved96_owner_facts')
        later=[]
        for owner in ('A','B'):
            for attempt in raw['collection_attempts'][owner]:
                supplied=verifier.future_context(raw,owner,attempt);known=type(supplied) is context.SuppliedContext
                require(known==(attempt['information'].get('native_delivery_verified') is True),'saved96_later_guard')
                later.append({'owner':owner,'at':attempt['at'],'known':known,'matches_saved':True})
        require(comparison.exact(later,saved['actual_collection_contexts']),'saved96_later_saved_rows')
        actual_rows=verifier.actual_collection_rows(raw);projected_rows=verifier.projected_collection_rows(projected)
        require(comparison.exact(actual_rows,saved['actual_collection_rows'])
            and comparison.exact(projected_rows,saved['projected_collection_rows'])
            and comparison.exact(projected_rows,actual_rows),'saved96_ordered_chronology')
        require(comparison.exact(raw['summary']['completion'],saved['actual_completion'])
            and comparison.exact(projected.get('completion'),saved['predicted_completion'])
            and verifier.exact_completion(projected.get('completion'),raw['summary']['completion'])
            and projected['status']==saved['predictor_status']=='conditional_prediction','saved96_five_exact_endpoints')
        if key in plan['saved73_equivalence']:
            old=plan['saved73_equivalence'][key]
            require(sha(old['path'])==old['sha256'] and gzip.decompress(Path(old['path']).read_bytes())==body,'saved73_full_byte_equality')
            require(oldchecks[key]=={'previous':old,'new':pred,'full_output_bytes_exact':True},'saved73_recorded_equality')
            equal_count+=1
        attempt_count+=len(later);known_count+=sum(r['known'] for r in later)
        checks[key]={'status':'saved_exact_rechecked','prediction':pred,'actual':rawref,
            'five_endpoints_exact':True,'chronology_exact':True,'initial_owner_checks':2,'actual_attempts':len(later),
            'actual_known_attempts':sum(r['known'] for r in later),'model_wall_seconds':saved['model_wall_seconds']}
        write(output/'checked_rows.json',checks)
    require((len(checks),attempt_count,known_count,equal_count)==(96,226,192,73),'saved96_complete_totals')
    expected_artifacts=set(prediction_pins)
    actual_artifacts={str(p.resolve()) for case in comparison.CASES for p in (SOURCE/case).glob('*.json.gz')}
    require(actual_artifacts==expected_artifacts,'saved96_exact_artifact_domain')
    producer();verify_plan(output,expected)
    loaded_exit=verifier.source_paths();require(loaded_entry==loaded_exit,'saved96_loaded_exit')
    exitpins={p:sha(p) for p in pins};require(exitpins==entry,'saved96_current_archive_exit')
    require(all(sha(p)==d for p,d in prediction_pins.items()),'saved96_prediction_exit')
    write(output/'exit_pins.json',exitpins)
    times=[r['model_wall_seconds'] for r in rows.values()]
    require(all(type(v) is float and math.isfinite(v) and v>=0 for v in times),'saved96_cost_domain')
    report={'schema':'g31.lazy96.independent_saved_review.v1','status':'passed_all96_and_saved73_full_readback',
        'plan':ref(output/'plan.json'),'producer_expected':EXPECTED,'checked_rows':ref(output/'checked_rows.json'),
        'exact_count':96,'unknown_count':0,'initial_owner_checks':192,'actual_later_checks':226,
        'actual_known_later':192,'saved73_full_byte_equivalence':73,'source_count':len(audit['source_sha256']),
        'producer100_and_original93_current_archive_unchanged':True,'loaded_entry_exit':list(map(str,loaded_entry)),
        'entry_pins':ref(output/'entry_pins.json'),'exit_pins':ref(output/'exit_pins.json'),
        'model_cost_seconds':{'min':min(times),'max':max(times),'median':statistics.median(times),'sum':sum(times)},
        'producer_whole_python_seconds':outer['whole_python_application_seconds'],
        'new_native_calls':0,'new_model_evaluations':0,'complete_request_100ms_certified':False,
        'limits':['Retrospective finite-domain regression; actual future outcomes only verifier targets.',
            'Lazy view equivalence is limited to the guarded valid model-state domain; arbitrary malformed-state exceptions need not match.',
            'Initial prediction conformance is not later rolling replanning support or online joint efficacy.',
            'Separate rounds do not establish causal speedup; all producer and separate audit costs retained.'],
        'audit_seconds_before_report':time.perf_counter()-start}
    write(output/'report.json',report)
    print(json.dumps({k:report[k] for k in ('status','exact_count','unknown_count','saved73_full_byte_equivalence','audit_seconds_before_report')}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan')
    args=p.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(sys.stdin.readline()==args.expected_plan+'\n','saved96_owned_admission')
        try:worker(output,args.expected_plan)
        except BaseException:write(output/'failure.json',{'status':'unknown_saved_audit_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute,'saved96_explicit_action');verify_plan(output,args.expected_plan)
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:json.dump({'plan_sha256':args.expected_plan},stream)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',args.expected_plan]
    remaining=LIMIT-(time.monotonic()-BOOT)-1;require(remaining>0,'saved96_budget_before_worker')
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=remaining,admission=args.expected_plan,stdout=out,stderr=err,cwd=str(ROOT))
    passed=process['status']=='exited' and process['exitcode']==0 and time.monotonic()-BOOT<LIMIT
    write(output/'bounded_execution.json',{'status':'completed' if passed else 'unknown','process':process,
        'command':command,'fixed_seconds':LIMIT,'application_seconds_before_receipt':time.monotonic()-BOOT,
        'plan':ref(output/'plan.json'),'report':ref(output/'report.json') if (output/'report.json').exists() else None,
        'new_native_calls':0,'new_model_evaluations':0})
    return 0 if passed and time.monotonic()-BOOT<LIMIT else 1

if __name__=='__main__':raise SystemExit(main())
