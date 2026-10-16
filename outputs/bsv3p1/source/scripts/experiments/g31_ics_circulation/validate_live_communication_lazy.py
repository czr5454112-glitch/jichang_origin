"""Fresh fixed96 lazy-view conformance; no native and no old-row substitution."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import traceback
from types import FunctionType, SimpleNamespace
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
OLD=OUT/'live_communication_conformance_prepare_002'
LIMIT=360.
MODULE='scripts.experiments.g31_ics_circulation.validate_live_communication_lazy'
PURE=OUT/'live_communication_lazy_driver_pure_001.xml'
OLD_ROWS='11831be39a3a225a2fde2489a797fb71313485d1c75c1b0719d665215c431397'
PARTIAL='671f67f1831b9c1e43a0d3c1f879f0cdda06ead50253102f1b66cb1fcd430656'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def require(ok,why):
    if not ok:raise ValueError('lazy_conformance:'+why)


def pure_gate():
    import xml.etree.ElementTree as ET
    for path,count in ((OUT/'live_communication_lazy_pure_001.xml',8),(PURE,4)):
        suites=ET.parse(path).getroot().findall('testsuite')
        require(len(suites)==1 and int(suites[0].get('tests'))==count and
            all(int(suites[0].get(k))==0 for k in ('failures','errors','skipped')),'focused_pure_count')


def saved_prefix(rows):
    require(len(rows)==96,'96_old_rows')
    keys=list(rows)
    require(all(rows[k]['status']=='exact_conformance' for k in keys[:73]) and
        all(rows[k]['status']=='unknown_unexecuted' for k in keys[73:]),'preserved73_23')
    return {key:rows[key]['prediction'] for key in keys[:73]}


def exact_output_bytes(first,second):
    # This is deliberately stronger than endpoint equality and preserves JSON
    # order, scalar spelling and every projected event/message/guard result.
    return gzip.decompress(first)==gzip.decompress(second)


def prepare(output):
    from . import launch_live_communication_conformance_v2 as prior_launch
    from . import public_live_obligation_lazy_communication_projection as lazy
    pure_gate();require(sha(OLD/'rows.json')==OLD_ROWS,'old_rows_identity')
    report=OUT/'live_communication_partial_review_001/report.json'
    require(sha(report)==PARTIAL,'independent_partial_review')
    prior_launch.prepare(output)
    plan=read(output/'plan.json')
    for name in ('test_g31_circulation_lazy_communication_projection.py','test_g31_circulation_live_communication_lazy_driver.py'):
        path=ROOT/'tests'/name;rel=Path('source')/path.relative_to(ROOT)
        (output/rel).parent.mkdir(parents=True,exist_ok=True);(output/rel).write_bytes(path.read_bytes())
        plan['source_sha256'][str(path)]=sha(path);plan['source_archive'][str(path)]=str(rel)
    for path in (PURE,OUT/'live_communication_lazy_pure_001.xml',report,
                 OUT/'live_communication_lazy_source_cost_plan_001.json',OLD/'rows.json',
                 OLD/'bounded_execution.json',OLD/'external_application_wall.json'):
        plan['fixed_evidence_sha256'][str(path)]=sha(path)
    prefix=saved_prefix(read(OLD/'rows.json'))
    for reference in prefix.values():plan['fixed_evidence_sha256'][reference['path']]=reference['sha256']
    plan.update(schema='g31.live_communication_lazy_conformance.v1',hard_timeout_seconds=LIMIT,
        model_variant='lazy_trigger_view_only',source_proof=lazy.source_proof(),saved73_equivalence=prefix,
        original_timeout_preserved=True,old_rows_never_substituted_for_new_predictions=True,
        complete_gate_requires=['receipt.json exact_all96_conformance','equivalence73.json all_exact',
            'final_receipt.json exact_all96_and_saved73','bounded_execution.json bounded_worker_completed'])
    plan['budget']['fixed_application_seconds']=LIMIT
    plan['budget']['worker_timeout']='360 minus parent elapsed minus1s finalization reserve'
    plan['budget']['basis']={'partial73_report_sha256':PARTIAL,'linear_full96_seconds':235.68366627945204,
        'observed_max_model_plus_scaled_residual_seconds':274.65551053166695,
        'finite_offline_verification_only':True,'complete_request_100ms_certified':False}
    plan['rules']=[r for r in plan['rules'] if not r.startswith('Parent elapsed is subtracted')]
    plan['rules'].append('Parent elapsed deducted from shared360s. All96 fresh predictions, all actual endpoint checks, saved73 complete-output equality, source/raw exit pins and receipts included.')
    plan['rules'].append('No interleaved ABBA speedup claim; timings descriptive and actual physical/complete-request100ms performance remains uncertified.')
    write(output/'plan.json',plan)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':ref(output/'plan.json'),'source_count':len(plan['source_sha256']),
        'fixed_application_seconds':LIMIT,'native_calls':0,'model_evaluations':0,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def worker(output,expected):
    from . import validate_live_communication_projection as original
    from . import public_live_obligation_lazy_communication_projection as lazy
    require(sha(output/'plan.json')==expected,'plan_identity');plan=read(output/'plan.json')
    require(plan['schema']=='g31.live_communication_lazy_conformance.v1' and plan['hard_timeout_seconds']==LIMIT
        and plan['budget']['fixed_application_seconds']==LIMIT and plan['source_proof']==lazy.source_proof(),'closed_model_budget')
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter_identity');pure_gate()
    # Exact old worker code and all old guards/order/outputs, with only a
    # private model module argument choosing the independently proven subclass.
    facade=SimpleNamespace(physics=original.model.physics,predict=lazy.predict)
    run=FunctionType(original.worker.__code__,{**original.worker.__globals__,'model':facade},
        original.worker.__name__,original.worker.__defaults__,original.worker.__closure__)
    run.__kwdefaults__=original.worker.__kwdefaults__
    require(run.__code__ is original.worker.__code__,'same_worker_checks')
    run(output,expected)
    rows=read(output/'rows.json');comparisons={}
    require(list(rows)==plan['order'] and len(rows)==96 and len(plan['saved73_equivalence'])==73,'fresh96_saved73_counts')
    for key,previous in plan['saved73_equivalence'].items():
        new=rows[key].get('prediction')
        require(sha(previous['path'])==previous['sha256'],'previous_prediction_identity')
        valid=type(new) is dict and sha(new['path'])==new['sha256']
        comparisons[key]={'previous':previous,'new':new,'full_output_bytes_exact':valid and
            exact_output_bytes(Path(previous['path']).read_bytes(),Path(new['path']).read_bytes())}
    write(output/'equivalence73.json',comparisons)
    pins=read(output/'entry_pins.json');after={p:sha(p) for p in pins};require(after==pins,'final_source_raw_pins')
    write(output/'final_exit_pins.json',after)
    prior=read(output/'receipt.json');same=sum(row['full_output_bytes_exact'] for row in comparisons.values())
    final={'schema':plan['schema'],'status':'exact_all96_and_saved73' if prior['status']=='exact_all96_conformance'
        and same==73 else 'completed_with_unknowns_or_differences','plan':ref(output/'plan.json'),
        'model_receipt':ref(output/'receipt.json'),'rows':ref(output/'rows.json'),'equivalence73':ref(output/'equivalence73.json'),
        'full_output_exact_count':same,'compared_old_count':73,'new_model_evaluations':prior['model_evaluations'],
        'new_counts':prior['counts'],'original_timeout_preserved':True,'old23_not_reused':True,
        'final_exit_pins':ref(output/'final_exit_pins.json'),'source_changed':[],
        'native_calls':0,'online_executable':False,'complete_request_100ms_certified':False}
    write(output/'final_receipt.json',final);print(json.dumps(final))


def execute(output,expected):
    require(sha(output/'plan.json')==expected,'launch_plan_sha');plan=read(output/'plan.json')
    require(plan['schema']=='g31.live_communication_lazy_conformance.v1' and
        plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'launch_environment')
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'plan_sha256':expected,'fixed_application_seconds':LIMIT},stream)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',expected]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        elapsed=time.monotonic()-BOOT;remaining=LIMIT-elapsed-1
        require(remaining>0,'budget_before_worker')
        process=bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=expected,cwd=str(ROOT))
    end=time.monotonic()-BOOT
    passed=process['status']=='exited' and process['exitcode']==0 and end<=LIMIT
    write(output/'bounded_execution.json',{'status':'bounded_worker_completed' if passed else 'unknown_failed_or_budget_exceeded',
        'process':process,'command':command,'plan_sha256':expected,'fixed_application_seconds':LIMIT,
        'parent_elapsed_before_worker_seconds':elapsed,'application_seconds_before_final_receipt':end,
        'source':ref(__file__),'final_receipt':ref(output/'final_receipt.json') if (output/'final_receipt.json').exists() else None,
        'external_python_launch_through_exit_required':True,'native_calls':0})
    return 0 if passed and time.monotonic()-BOOT<=LIMIT else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true')
    p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan');args=p.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline()==args.expected_plan+'\n','owned_job_admission')
        try:worker(output,args.expected_plan)
        except BaseException:
            write(output/'worker_failure.json',{'status':'unknown_worker_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute,'explicit_action');return execute(output,args.expected_plan)

if __name__=='__main__':raise SystemExit(main())
