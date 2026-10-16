"""Separate saved-only full bridge audit; the original2400 failure is immutable.

Original full policy/physical replay and old27218 comparison code are retained.
Only the derived all_job_states export/hash is redirected into this audit's
directory. Runtime imports are checked against old82 plus this frozen closure.
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
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import research_original_bridge_serialize_once as r
from . import verify_original_bridge_serialize_once as original

ROOT,OUT,base,require=r.ROOT,r.OUT,r.base,r.require
SOURCE=OUT/'original_bridge_serialize_once_prepare_001'
CAMPAIGN_SHA='d976e7f2d473e64ddb4e11895c06bfb9f21a11b43133babb71cd02491bb94464'
EXTERNAL_SHA='95a682b80bb76d1788ae6c7f3ab522cfc44ca8a8d248308527b53bcc64b317a4'
SCHEMA='g31.bridge.serialize_once.separate_saved_audit.v1'
MODULE='scripts.experiments.g31_ics_circulation.audit_bridge_serialize_once_saved'
TEST='tests/test_g31_circulation_bridge_saved_audit.py'
LIMIT=600.


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)


def closure():
    found=set(r.source_paths())
    for entry in (Path(__file__),ROOT/TEST):
        found.update(r.original.clone(base.source_paths,{**base.source_paths.__globals__,'__file__':str(entry)})())
    return sorted(found)


def loaded_sources():
    return {str(Path(m.__file__).resolve()) for m in list(sys.modules.values()) if getattr(m,'__file__',None)
        and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}


def check_runtime(plan):
    actual=loaded_sources();pins=plan['source_before']
    require(actual<=set(pins),'audit_unlisted_loaded_source')
    for name in actual:require(base.sha(name)==pins[name],'audit_loaded_source_changed')
    return sorted(actual)


class DerivedOutput:
    """A capability for exactly one derived path; all original inputs stay readonly."""
    def __init__(self,source,output):
        self.old=(Path(source)/'bridge/all_job_states.json.gz').resolve()
        self.new=(Path(output)/'all_job_states.json.gz').resolve()
        require(self.old!=self.new and not self.new.is_relative_to(Path(source).resolve()),'audit_output_inside_source')
        require(not self.old.exists() and not self.new.exists(),'audit_derived_output_exists')
        self.writes=0;self.hashes=0
    def gzwrite(self,path,value):
        require(Path(path).resolve()==self.old and self.writes==0,'audit_unexpected_write')
        require(not self.new.exists(),'audit_derived_output_exists')
        base.gzwrite(self.new,value);self.writes+=1
    def sha(self,path):
        if Path(path).resolve()==self.old:
            require(self.writes==1 and self.new.is_file(),'audit_hash_before_write')
            self.hashes+=1
            return base.sha(self.new)
        return base.sha(path)
    def map_result(self,result):
        require(self.writes==1 and self.hashes==1,'audit_derived_output_denominator')
        old=str(self.old);new=str(self.new);evidence=result['evidence_sha256']
        require(old in evidence and new not in evidence and evidence[old]==base.sha(self.new),'audit_mapping_identity')
        value=dict(result)
        value['evidence_sha256']={new if path==old else path:h for path,h in evidence.items()}
        return value,{'old_derived_path':old,'new_derived_path':new,'sha256':evidence[old],
            'original_path_written':False,'redirected_gzwrite_calls':self.writes,'redirected_sha_calls':self.hashes}


def bound_verifier(plan,redirect):
    """Private globals only; neither original module nor producer plan is changed."""
    def verify_source_pins(directory,producer_plan,runtime=False):
        # Every old live/archive/input/026/reference pin remains checked.
        r.verify_pins(directory,producer_plan,runtime=False)
        if runtime:check_runtime(plan)
    namespace=r.runner_namespace()
    namespace['verify_pins']=verify_source_pins
    runner=SimpleNamespace(**namespace)
    def factory(replay_type):
        private_base=SimpleNamespace(**{**vars(base),'ReplayTape':replay_type,
            'gzwrite':redirect.gzwrite,'sha':redirect.sha})
        function=r.original.clone(original.original.verify_case,{**original.original.verify_case.__globals__,
            'r':runner,'base':private_base})
        require(function.__code__ is original.original.verify_case.__code__,'audit_changed_original_verifier')
        return function
    function=r.original.clone(original.verify_case,{**original.verify_case.__globals__,'verifier_function':factory})
    require(function.__code__ is original.verify_case.__code__,'audit_changed_prefix_wrapper')
    return function


def terminal_refs():
    names=('campaign.json','external_application_wall.json','external_launch_receipt.json','branch_ledger.json',
        'root_prelaunch_review_001.json','bridge/preregistered_protocol.json','bridge/input.json.gz',
        'bridge/raw_final.json.gz','bridge/assessment.json','bridge/worker_elapsed.json','bridge/heartbeat.json',
        'bridge/worker.log','bridge/verification.log','bridge/api/manifest.jsonl','bridge/service_clocks.jsonl')
    return {name:base.sha(SOURCE/name) for name in names}


def require_terminated():
    require(base.sha(SOURCE/'campaign.json')==CAMPAIGN_SHA and
        base.sha(SOURCE/'external_application_wall.json')==EXTERNAL_SHA,'audit_wrong_terminal_campaign')
    external=base.read(SOURCE/'external_application_wall.json');launch=base.read(SOURCE/'external_launch_receipt.json')
    require(external['exit_code']==1 and external['evidence_unchanged'] is True and
        launch['process']['status']=='hard_timeout' and launch['process']['windows_job_kill_on_close'] is True,
        'audit_original_not_expected_timeout')
    require(not (SOURCE/'receipt.json').exists() and not (SOURCE/'bridge/independent_verification.json').exists(),
        'audit_unexpected_original_completion')
    return external,launch


def check_pure_references(plan):
    proof=plan['pure']
    require(base.sha(proof['path'])==proof['sha256'] and base.sha(proof['XML_path'])==proof['XML_sha256'],
        'audit_pure_reference_changed')


def current_cost_metadata(result):
    """Only relabel inherited audit bookkeeping; original checker code is intact."""
    prior=result['same_policy_old001_complete_prefix']
    old_cost=prior['cost']
    require(old_cost=='Runs inside the same saved replay and shared2400 parent; no time deducted.',
        'audit_unexpected_inherited_cost_scope')
    value=dict(result);value['same_policy_old001_complete_prefix']={**prior,
        'cost':'Runs inside this separate saved-only600s audit with full reads/hash/replay/export charged; original2400 timeout remains unchanged.'}
    return value,{'original_verifier_cost_text':old_cost,'role':'Historical text emitted by the unchanged original verifier; not the budget of this new run.',
        'current_owned_budget_seconds':LIMIT}


def prepare(output,pure):
    require(not output.exists(),'audit_preserve_output');require_terminated()
    receipt=base.read(pure);xml=pure.parent/'tests.xml';cases=ET.parse(xml).getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and receipt['tests']==len(cases)>0
        and receipt['XML_sha256']==base.sha(xml) and not any(x.tag in ('failure','error','skipped') for t in cases for x in t),
        'audit_pure_gate')
    for name,h in receipt['source_before'].items():require(base.sha(name)==base.sha(pure.parent/'source'/Path(name).relative_to(ROOT))==h,'audit_pure_source_changed')
    r.isolated_runner().verify_campaign(SOURCE)
    pins={str(p):base.sha(p) for p in closure()};output.mkdir()
    for name,h in pins.items():
        dest=output/'source'/Path(name).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(Path(name).read_bytes())
        require(base.sha(dest)==h,'audit_archive_copy')
    plan={'schema':SCHEMA,'source':str(SOURCE),'original_campaign_sha256':CAMPAIGN_SHA,
        'original_external_sha256':EXTERNAL_SHA,'source_before':pins,'original_refs':terminal_refs(),
        'old_prefix_manifest_sha256':r.MANIFEST_SHA,'expected_new_rows':37270,'expected_old_prefix_rows':27218,
        'hard_timeout_seconds':LIMIT,'native_calls':0,'predictions':0,'pure':{'path':str(pure),'sha256':base.sha(pure),'XML_path':str(xml),'XML_sha256':base.sha(xml)},
        'interpreter':{'path':sys.executable,'sha256':base.sha(sys.executable)},
        'scope':'Independent saved-only audit with all original policy,physical,FIFO,Storage,cap,clock and ordered prefix checks unchanged. Every new37270 and old27218 row retains original hash and replay checks.',
        'write_scope':'Only new audit all_job_states and audit reports/claims/logs; old path never written. Private base gzwrite/sha redirects exactly the single derived output.',
        'runtime_scope':'Old82 plus frozen audit closure. No sys.modules filtering or old pin removal.',
        'budget_scope':'Separate600 includes child imports,all reads/hashes/replays/derived export/verification. Parent startup and final receipt export additionally recorded by required external Python launch-to-exit wrapper. No old2400 completion upgrade.',
        'status':'prepared_unexecuted'}
    write_new(output/'plan.json',plan)
    verify_plan(output,base.sha(output/'plan.json'))
    write_new(output/'preparation.json',{'status':'prepared_source_review_pending','plan_sha256':base.sha(output/'plan.json'),
        'source_count':len(pins),'pure_tests':len(cases),'native_calls':0,'predictions':0,'saved_audit_executed':False,
        'command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--plan-sha256',base.sha(output/'plan.json')]})


def verify_plan(output,expected):
    require(base.sha(output/'plan.json')==expected,'audit_plan_sha');plan=base.read(output/'plan.json')
    require(plan['schema']==SCHEMA and plan['source']==str(SOURCE) and plan['hard_timeout_seconds']==LIMIT and
        plan['expected_new_rows']==37270 and plan['expected_old_prefix_rows']==27218 and plan['old_prefix_manifest_sha256']==r.MANIFEST_SHA,'audit_scope')
    require_terminated()
    for name,h in plan['source_before'].items():require(base.sha(name)==base.sha(output/'source'/Path(name).relative_to(ROOT))==h,'audit_source_changed')
    for name,h in plan['original_refs'].items():require(base.sha(SOURCE/name)==h,'audit_original_changed:'+name)
    require(base.sha(plan['interpreter']['path'])==plan['interpreter']['sha256'],'audit_interpreter')
    check_pure_references(plan)
    return plan


def audit(output,expected):
    with (output/'worker_claim.json').open('x') as f:json.dump({'plan_sha256':expected},f)
    began=time.perf_counter_ns();plan=verify_plan(output,expected);entry=check_runtime(plan)
    redirect=DerivedOutput(SOURCE,output)
    write_new(output/'stage_started.json',{'stage':'unchanged_full_saved_replay','at_ns':time.perf_counter_ns()})
    result=bound_verifier(plan,redirect)(SOURCE/'bridge')
    require(result['replay']['api_rows']==37270 and result['same_policy_old001_complete_prefix']['rows']==27218,
        'audit_actual_denominator')
    result,mapping=redirect.map_result(result)
    result,inherited_cost=current_cost_metadata(result)
    verify_plan(output,expected);exit_sources=check_runtime(plan)
    report={'schema':SCHEMA,'status':'passed_complete_saved_audit','original_campaign_status':'timeout_preserved',
        'plan_sha256':expected,'result':result,'derived_output_mapping':mapping,'inherited_verifier_metadata':inherited_cost,
        'loaded_sources_entry':entry,'loaded_sources_exit':exit_sources,
        'elapsed_before_report_ns':time.perf_counter_ns()-began,'native_calls':0,'predictions':0,
        'limits':['No native or known-seal replay. Saved hash is checked as recorded evidence.','Original2400 experiment remains failed/unknown; this is separately budgeted saved evidence.',
                  'Full-horizon observation,cap certificate,alloffered business success and100ms remain separate.']}
    write_new(output/'report.json',report)


def pure(output,worker=False):
    if worker:
        require(sys.stdin.readline()=='bridge_saved_audit_pure\n','audit_pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(ROOT/'outputs'/('tmp_'+output.name)),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(exist_ok=False);pins={str(p):base.sha(p) for p in closure()}
    for name in pins:
        path=output/'source'/Path(name).relative_to(ROOT);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(Path(name).read_bytes())
    command=[sys.executable,'-m',MODULE,'--pure-worker','--output',str(output)]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,60-(time.monotonic()-BOOT)),stdout=out,stderr=err,admission='bridge_saved_audit_pure',cwd=ROOT)
    tests=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    changed=[p for p,h in pins.items() if base.sha(p)!=h]
    passed=process['status']=='exited' and process['exitcode']==0 and tests and not changed and not any(x.tag in ('failure','error','skipped') for t in tests for x in t)
    write_new(output/'receipt.json',{'status':'passed' if passed else 'failed_unknown','process':process,'source_before':pins,
        'source_changed':changed,'tests':len(tests),'XML_sha256':base.sha(output/'tests.xml') if tests else None,
        'native_calls':0,'predictions':0,'full_saved_replays':0})
    return 0 if passed else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--pure-receipt',type=Path);p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true')
    p.add_argument('--pure',action='store_true');p.add_argument('--pure-worker',action='store_true');p.add_argument('--plan-sha256');args=p.parse_args()
    output=args.output.resolve()
    require(sum((args.prepare,args.execute,args.worker,args.pure,args.pure_worker))==1,'audit_mode')
    if args.pure or args.pure_worker:return pure(output,args.pure_worker)
    if args.prepare:prepare(output,args.pure_receipt.resolve());return 0
    if args.worker:
        require(sys.stdin.readline()==args.plan_sha256+'\n','audit_job_admission')
        try:audit(output,args.plan_sha256);return 0
        except BaseException:
            write_new(output/'failure.json',{'status':'unknown_failed_saved_audit','traceback':traceback.format_exc()});raise
    require(base.sha(output/'plan.json')==args.plan_sha256,'audit_parent_plan')
    with (output/'execution_claim.json').open('x') as f:json.dump({'plan_sha256':args.plan_sha256,'shared_seconds':LIMIT},f)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--plan-sha256',args.plan_sha256]
    remaining=LIMIT-(time.monotonic()-BOOT);require(remaining>0,'audit_budget_before_worker')
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        process=bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=args.plan_sha256,cwd=ROOT)
    write_new(output/'bounded_execution.json',{'process':process,'command':command,'hard_seconds':LIMIT,
        'post_import_before_final_receipt_seconds':time.monotonic()-BOOT,'external_full_python_clock_required':True,
        'report_sha256':base.sha(output/'report.json') if (output/'report.json').exists() else None,'native_calls':0,'predictions':0})
    return 0 if process['status']=='exited' and process['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
