"""Fixed6 ABBA24 conditional model comparison, fresh scope charged in every B.

No native/full32/complete-request claim. Default GC stays enabled; ordinary
Python object reclamation is not artificially moved out of the whole process.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import gc
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import traceback
import xml.etree.ElementTree as ET
from . import profile_live_lazy_six as base
from . import public_live_obligation_scoped_inputs as candidate
from . import public_live_obligation_lazy_communication_projection as lazy
from . import validate_live_communication_projection as prior
from . import bounded_windows_job, initial_owner_route_image as image

ROOT,OUT,ORDER=base.ROOT,base.OUT,base.ORDER
MODULE='scripts.experiments.g31_ics_circulation.measure_scoped_public_inputs_six'
PURE=OUT/'scoped_public_inputs_pure_001'
PROFILE=OUT/'live_lazy_six_profile_prepare_001'
LIMIT=120.
sha,read,write,ref=base.sha,base.read,base.write,base.ref


def require(value,reason):
    if not value:raise ValueError('scoped_inputs_cost:'+reason)


def declaration():return [{'key':key,'arm':arm,'position':i} for key in ORDER for i,arm in enumerate('ABBA')]


def sources():
    files=image.source_closure(ROOT,(MODULE,'tests.test_g31_circulation_scoped_public_inputs',
        'scripts.experiments.g31_ics_circulation.run_scoped_public_inputs_pure'))
    old=read(PROFILE/'plan.json')
    for p,d in old['source_sha256'].items():
        require(sha(p)==d==sha(PROFILE/old['source_archive'][p]),'frozen107_source')
        files[str(Path(p).relative_to(ROOT))]=Path(p).read_bytes()
    return files


def pure_guard():
    receipt,plan=read(PURE/'receipt.json'),read(PURE/'plan.json')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and len(cases)==16
        and not any(x.tag in ('failure','error','skipped') for c in cases for x in c),'pure16')
    require(receipt['plan']==ref(PURE/'plan.json') and receipt['XML']==ref(PURE/'tests.xml'),'pure_identity')
    for p,d in plan['source_sha256'].items():require(sha(p)==d==sha(PURE/'source'/Path(p).relative_to(ROOT)),'pure_source')


def prepare(output):
    base.no_execution_extensions();pure_guard()
    require(sha(PROFILE/'plan.json')=='222b1d66267921229866970bfd00ac843fa740e9e2a2695c786a3809887f7e85'
        and sha(PROFILE/'report.json')=='ca2c4e875ef32600aaf861a892ef115f8ae874d033d71f435fba94978d9b135d'
        and read(PROFILE/'report.json')['status']=='exact_six_profiled_diagnostic','diagnostic_identity')
    output.mkdir(exist_ok=False);files=sources();pins={};archives={}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        pins[str(ROOT/name)]=hashlib.sha256(data).hexdigest();archives[str(ROOT/name)]=str(path.relative_to(output))
    old=read(PROFILE/'plan.json');evidence=dict(old['evidence_sha256'])
    for folder,names in ((PROFILE,('plan.json','report.json','receipt.json','external_application_wall.json')),
        (PURE,('plan.json','receipt.json','tests.xml'))):
        for name in names:evidence[str(folder/name)]=sha(folder/name)
    # One original construction for source-binding review only, explicitly in
    # preparation. No initial context, model engine or saved target is read.
    proof_scope=candidate.PublicInputScope();proof=proof_scope.source_proof()
    plan={'schema':'g31.scoped_public_inputs.ABBA6.v1','status':'prepared_unexecuted',
        'source_sha256':pins,'source_archive':archives,'evidence_sha256':evidence,
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'rows':old['rows'],'order':list(ORDER),'declaration':declaration(),'hard_application_seconds':LIMIT,
        'source_proof':proof,'maximum_model_calls':24,'default_GC_required':True,
        'preparation_public_constructions':1,'preparation_model_calls':0,'preparation_raw_reads':0,
        'scope':'A original lazy.predict. B new fresh public input scope in each candidate.predict; all endpoint/lifecycle checks and complete model/event code unchanged. All inputs reads still fresh deepcopy. No endpoint/result/state cache.',
        'timing':'Each sample caller start to prediction return, including B scope construction/private binds and original guards/model. Initial supplied contexts built once per case outside samples, but inside whole120. Decode/strict full outputs/export/readback/entryexit pins andprocess teardown in whole. DefaultGC retained; natural collection timing is not an isolated allocator claim.',
        'failure':'Every24 stays in ledger. Returned predictions saved before target comparison; malformed/error/timeout/source drift remains unknown. No retry or row selection.',
        'not_certified':['full32','complete_request100ms','hidden_state_coverage','native_protection','joint_online_effectiveness']}
    write(output/'plan.json',plan)
    write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'sources':len(pins),'models':0,'native_calls':0,'C_loads':0,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def pins_now(output,plan):
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter')
    values={}
    for p,d in plan['source_sha256'].items():
        for path in (Path(p),output/plan['source_archive'][p]):
            values[str(path)]=sha(path);require(values[str(path)]==d,'source_drift')
    for p,d in plan['evidence_sha256'].items():values[p]=sha(p);require(values[p]==d,'evidence_drift')
    return values


def worker(output,expected):
    started=time.perf_counter();require(sha(output/'plan.json')==expected,'plan')
    plan=read(output/'plan.json')
    require(plan['declaration']==declaration() and plan['maximum_model_calls']==24
        and plan['hard_application_seconds']==LIMIT and gc.isenabled(),'fixed_scope')
    entry=pins_now(output,plan);write(output/'entry_pins.json',entry)
    loaded_entry=base.loaded_sources(plan,prior);write(output/'loaded_sources_entry.json',loaded_entry)
    ledger=[{**d,'status':'unknown_unexecuted'} for d in declaration()];write(output/'ledger.json',ledger)
    setup=[];model_calls=0
    for case_index,key in enumerate(ORDER):
        row=plan['rows'][key];setup_started=time.perf_counter()
        try:
            public=read(row['input']['path'])
            require(base.exact(public['action'],row['action']),'action')
            context=base.build_initial(public,prior)
            setup.append({'key':key,'status':'initial_context_prepared','seconds':time.perf_counter()-setup_started})
        except Exception:
            error=traceback.format_exc();setup.append({'key':key,'status':'unknown_setup_error','error':error})
            for item in ledger[case_index*4:case_index*4+4]:item.update(status='unknown_setup_error',error=error)
            write(output/'ledger.json',ledger);continue
        for index in range(case_index*4,case_index*4+4):
            item=ledger[index];item['status']='unknown_in_progress';write(output/'ledger.json',ledger)
            try:
                require(gc.isenabled(),'GC_changed')
                function=lazy.predict if item['arm']=='A' else candidate.predict
                model_calls+=1;require(model_calls<=24,'model_budget')
                begin=time.perf_counter_ns()
                try:prediction=function(context,public['action'])
                finally:
                    end=time.perf_counter_ns();item.update(started_ns=begin,finished_ns=end,elapsed_ns=end-begin)
                export_started=time.perf_counter_ns();encoded=base.bytes_of(prediction)
                path=output/'raw'/f'{index:03d}.json.gz';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(encoded,compresslevel=1,mtime=0))
                item.update(status='returned_audit_pending',raw=ref(path),export_ns=time.perf_counter_ns()-export_started)
                write(output/'ledger.json',ledger)
                target=gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
                require(all(base.compare_full(encoded,target).values()),'complete_prediction_changed')
                require(base.bytes_of(prediction['projected_collections'])==base.bytes_of(row['expected_collections']),'chronology')
                require(gc.isenabled(),'GC_changed');item['status']='exact_full_prediction'
            except Exception:item.update(status='unknown_error',error=traceback.format_exc())
            write(output/'ledger.json',ledger)
    # Saved readback is also inside the same owned budget, including all24.
    exact_count=0
    for item in ledger:
        if item['status']!='exact_full_prediction':continue
        require(item['raw']==ref(item['raw']['path']),'published_raw_changed')
        saved=gzip.decompress(Path(item['raw']['path']).read_bytes())
        target=gzip.decompress(Path(plan['rows'][item['key']]['comparison_only_saved_prediction']['path']).read_bytes())
        require(all(base.compare_full(saved,target).values()),'saved_full_prediction_changed');exact_count+=1
    summary={};pairs={};negative=[]
    if exact_count==24:
        values={arm:[r['elapsed_ns']/1e6 for r in ledger if r['arm']==arm] for arm in ('A','B')}
        summary={arm:{'count':len(v),'min':min(v),'median':statistics.median(v),'max':max(v),'sum':sum(v)} for arm,v in values.items()}
        pairs={key:{arm:statistics.median([r['elapsed_ns']/1e6 for r in ledger if r['key']==key and r['arm']==arm]) for arm in ('A','B')} for key in ORDER}
        negative=[key for key,pair in pairs.items() if pair['B']>=pair['A']]
    exit_pins=pins_now(output,plan);require(entry==exit_pins,'exit_pins');write(output/'exit_pins.json',exit_pins)
    loaded_exit=base.loaded_sources(plan,prior);require(all(loaded_exit.get(p)==d for p,d in loaded_entry.items()),'loaded_drift')
    write(output/'loaded_sources_exit.json',loaded_exit)
    report={'status':'passed_fixed_six_ABBA24_complete_prediction' if exact_count==24 else 'unknowns_preserved',
        'model_calls':model_calls,'exact':exact_count,'unknown':24-exact_count,'summary_ms':summary,
        'paired_median_ms':pairs,'negative_or_equal_cases':negative,'setup':setup,'ledger':ref(output/'ledger.json'),
        'source_changed':[],'GC_enabled':gc.isenabled(),'native_calls':0,'C_extension_loads':0,
        'worker_seconds':time.perf_counter()-started,'complete_request100ms_certified':False,
        'all_method_setup_and_state_filtering_costed':False,'closed_fixed_domain_only':True}
    write(output/'report.json',report);write(output/'receipt.json',{'status':report['status'],'report':ref(output/'report.json'),
        'plan':ref(output/'plan.json'),'exact':exact_count,'unknown':24-exact_count,'source_changed':[]})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--expected-plan');args=parser.parse_args()
    output=args.output.resolve();base.no_execution_extensions()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(sys.stdin.readline()==args.expected_plan+'\n','admission')
        try:worker(output,args.expected_plan)
        except BaseException:write(output/'failure.json',{'status':'unknown_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute and sha(output/'plan.json')==args.expected_plan,'explicit_reviewed_execute')
    with (output/'execution_claim').open('x'):pass
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',args.expected_plan]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        elapsed=time.monotonic()-BOOT
        process=bounded_windows_job.run(command,timeout=base.remaining(elapsed),stdout=out,stderr=err,
            admission=args.expected_plan,cwd=str(ROOT))
    wall=time.monotonic()-BOOT
    passed=process['status']=='exited' and process['exitcode']==0 and wall<=LIMIT
    write(output/'bounded_execution.json',{'status':'completed' if passed else 'unknown_failed_or_timeout',
        'process':process,'command':command,'whole_python_before_receipt_seconds':wall,'shared_limit_seconds':LIMIT})
    return 0 if passed and time.monotonic()-BOOT<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
