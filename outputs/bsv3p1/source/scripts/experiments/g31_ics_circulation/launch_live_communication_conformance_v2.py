"""Versioned whole-application budget wrapper; frozen first preparation unchanged.

Only lightweight standard-library imports precede the owned worker. Its model
imports, all evidence/source pins, fixed96 work and receipts share the remainder
of180s measured from this module's first clock. Python process creation/exit is
also recorded externally; it is never described as part of a child-only limit.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
LIMIT=180.
FINALIZATION_RESERVE=1.
MODULE='scripts.experiments.g31_ics_circulation.launch_live_communication_conformance_v2'
PURE=OUT/'live_communication_driver_pure_001.xml'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(ok,why):
    if not ok:raise ValueError('communication_v2:'+why)
def reference(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}


def remaining_budget(elapsed):
    require(type(elapsed) in (int,float) and 0<=elapsed<float('inf'),'elapsed_clock')
    remaining=LIMIT-elapsed-FINALIZATION_RESERVE
    if remaining<=0:raise TimeoutError('communication_v2:budget_before_worker')
    return remaining


def pure_gate():
    import xml.etree.ElementTree as ET
    suites=ET.parse(PURE).getroot().findall('testsuite')
    require(len(suites)==1 and int(suites[0].get('tests'))==10 and
        all(int(suites[0].get(k))==0 for k in ('failures','errors','skipped')),'10_driver_tests')


def prepare(output):
    from . import validate_live_communication_projection as prior
    pure_gate()
    old=OUT/'live_communication_conformance_prepare_001'
    require(sha(old/'plan.json')=='78c3b7883ba048cef78e2fbd49dc0c5c7ff12c3858a3f72711e54e900f591f31',
            'first_plan_preserved')
    require(read(old/'ready.json')['status']=='prepared_unexecuted' and not (old/'receipt.json').exists(),
            'first_preparation_unexecuted')
    plan=prior.prepare(output)
    # The original preparer already archives every loaded project module.
    # This new test is an additional entry, never a replacement of old tests.
    test=ROOT/'tests/test_g31_circulation_live_communication_driver_v2.py'
    rel=Path('source')/test.relative_to(ROOT);(output/rel).parent.mkdir(parents=True,exist_ok=True)
    (output/rel).write_bytes(test.read_bytes())
    plan['source_sha256'][str(test)]=sha(test);plan['source_archive'][str(test)]=str(rel)
    plan['fixed_evidence_sha256'][str(PURE)]=sha(PURE)
    boundary=OUT/'live_communication_source_boundary_review_002.json'
    plan['fixed_evidence_sha256'][str(boundary)]=sha(boundary)
    # Hash all96 original compressed bytes at both ends, in addition to the
    # frozen worker's per-row readback. Raw files remain targets, never inputs.
    for row in plan['rows'].values():
        ref=row['actual_raw'];plan['fixed_evidence_sha256'][ref['path']]=ref['sha256']
    plan['fixed_evidence_sha256'][str(old/'plan.json')]=sha(old/'plan.json')
    plan['schema']='g31.live_communication_conformance.v2'
    plan['environment']={'python':sys.executable,'sha256':sha(sys.executable)}
    plan['budget']={'fixed_application_seconds':LIMIT,'clock_start':'first_module_statement_before_heavy_imports',
        'worker_timeout':'180 minus parent elapsed minus1s finalization reserve',
        'owned_child_includes':'imports, all pins, all96 predictions, future-data checks, output and exit hashes',
        'overrun':'bounded status unknown and nonzero exit; never upgraded by worker receipt',
        'external_python_launch_through_exit_required':True}
    plan['rules']=[r for r in plan['rules'] if not r.startswith('Entry pins/import/setup/')]
    plan['rules'].append('Parent elapsed is subtracted before owned-worker release;1s reserved for parent receipt; whole Python wall recorded externally.')
    write(output/'plan.json',plan)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':reference(output/'plan.json'),
        'source_count':len(plan['source_sha256']),'native_executions':0,'model_evaluations':0,
        'old_prepare001_preserved':True,'fixed_application_seconds':LIMIT,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),
            '--expected-plan',sha(output/'plan.json')]})


def worker(output,expected):
    # Heavy imports occur only after assignment to the parent's kill-on-close
    # JobObject and consume its remaining deadline.
    from . import validate_live_communication_projection as prior
    require(sha(output/'plan.json')==expected,'plan_sha')
    plan=read(output/'plan.json')
    require(plan['schema']=='g31.live_communication_conformance.v2' and
        plan['budget']['fixed_application_seconds']==LIMIT and plan['hard_timeout_seconds']==LIMIT,'plan_budget')
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter_identity')
    pure_gate()
    prior.worker(output,expected)


def execute(output,expected):
    require(sha(output/'plan.json')==expected,'launch_plan_sha')
    plan=read(output/'plan.json')
    require(plan['schema']=='g31.live_communication_conformance.v2' and
        plan['environment']['python']==sys.executable and
        plan['environment']['sha256']==sha(sys.executable),'launch_environment')
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'plan_sha256':expected,'fixed_application_seconds':LIMIT},stream)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',expected]
    with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
        elapsed_before_worker=time.monotonic()-BOOT
        result=bounded_windows_job.run(command,timeout=remaining_budget(elapsed_before_worker),
            stdout=stdout,stderr=stderr,admission=expected,cwd=str(ROOT))
    elapsed=time.monotonic()-BOOT
    within=elapsed<=LIMIT
    status='bounded_worker_completed' if within and result['status']=='exited' and result['exitcode']==0 else 'unknown_failed_or_budget_exceeded'
    record={'schema':'g31.live_communication_bounded_execution.v2','status':status,'process':result,
        'plan_sha256':expected,'command':command,'fixed_application_seconds':LIMIT,
        'parent_elapsed_before_worker_seconds':elapsed_before_worker,'finalization_reserve_seconds':FINALIZATION_RESERVE,
        'application_seconds_before_final_receipt':elapsed,'within_fixed_budget_before_final_receipt':within,
        'source':reference(__file__),'worker_receipt':reference(output/'receipt.json') if (output/'receipt.json').is_file() else None,
        'external_python_launch_through_exit_required':True,'native_executions':0}
    write(output/'bounded_execution.json',record)
    # The final write itself is charged. An overrun cannot return success;
    # preserve the earlier timing field rather than rewriting it as zero cost.
    if time.monotonic()-BOOT>LIMIT:
        write(output/'budget_overrun.json',{'status':'unknown_budget_exceeded','elapsed_seconds':time.monotonic()-BOOT})
        return 1
    return 0 if status=='bounded_worker_completed' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--expected-plan')
    args=parser.parse_args();output=args.output.resolve()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline()==args.expected_plan+'\n','owned_job_admission')
        try:worker(output,args.expected_plan)
        except BaseException:
            write(output/'worker_failure.json',{'status':'unknown_worker_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute,'explicit_action')
    return execute(output,args.expected_plan)


if __name__=='__main__':raise SystemExit(main())
