"""Single fresh bridge worker+saved audit inside one owned2400s Windows Job."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from . import bounded_windows_job

LIMIT=2400.
MODULE='scripts.experiments.g31_ics_circulation.research_original_cooperative_bridge'
SCHEMA='g31.original_cooperative_bridge.campaign.v1'


def retained_evidence(output):
    names=('receipt.json','branch_ledger.json','campaign.stdout.log','campaign.stderr.log',
        'bridge/heartbeat.json','bridge/api/manifest.jsonl','bridge/service_clocks.jsonl',
        'bridge/worker_elapsed.json','bridge/error_prefix.json.gz')
    return {name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in names if (output/name).is_file()}


def validate_internal(receipt,digest):
    if (receipt.get('schema')!=SCHEMA or receipt.get('status')!='completed_finite_campaign'
        or receipt.get('campaign_sha256')!=digest or receipt.get('source_changed')!=[]
        or set(receipt.get('cases',{}))!={'bridge'} or receipt.get('offered')!=28506
        or receipt.get('alloffered_business_success') is not False or receipt.get('complete_100ms_certified') is not False):
        raise ValueError('bridge_launch:unconfirmed_complete_receipt')
    case=receipt['cases']['bridge'];wall=receipt.get('wall_seconds')
    if (case.get('status')!='saved_replay_passed'
        or any(case.get(key,{}).get('exit_code')!=0 for key in ('execution','verification'))
        or type(wall) not in (int,float) or not math.isfinite(wall) or not 0<=wall<=LIMIT):
        raise ValueError('bridge_launch:incomplete_or_over_budget_case')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--campaign-sha256',required=True);args=parser.parse_args();output=args.output.resolve()
    digest=hashlib.sha256((output/'campaign.json').read_bytes()).hexdigest()
    if digest!=args.campaign_sha256:raise ValueError('bridge_launch:campaign_changed')
    if (output/'receipt.json').exists() or (output/'external_launch_receipt.json').exists():raise ValueError('bridge_launch:already_attempted')
    with (output/'external_launch_claim.json').open('x',encoding='utf-8') as stream:
        json.dump({'campaign_sha256':digest,'shared_seconds':LIMIT},stream)
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--campaign','--admission',digest]
    remaining=LIMIT-(time.monotonic()-BOOT)
    receipt={'schema':'g31.cooperative_bridge.launch_receipt.v1','status':'unknown_before_dispatch','command':command,
        'campaign_sha256':digest,'shared_seconds':LIMIT,'pre_job_wall_seconds':LIMIT-remaining,
        'outer_python_startup_before_BOOT_unmeasured':True,'complete_100ms_certified':False}
    try:
        if remaining<=0:raise TimeoutError('bridge_launch:budget_before_job')
        with (output/'campaign.stdout.log').open('x',encoding='utf-8') as stdout,(output/'campaign.stderr.log').open('x',encoding='utf-8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,
                admission=digest,cwd=Path(__file__).resolve().parents[3])
        receipt['process']=process
        receipt['status']='campaign_process_exited' if process['status']=='exited' and process['exitcode']==0 else 'unknown_campaign_process'
        if receipt['status']=='campaign_process_exited':validate_internal(json.loads((output/'receipt.json').read_bytes()),digest)
    except BaseException as error:receipt.update(status='unknown_launcher_error',error=repr(error))
    finally:
        receipt['artifact_sha256']=retained_evidence(output)
        receipt['partial_artifact_scope']='Hashes retain available bytes, including possibly incomplete final rows after timeout; they do not certify replay or completion.'
        receipt['dispatch_through_before_final_evidence_export_wall_seconds']=time.monotonic()-BOOT
        if receipt['dispatch_through_before_final_evidence_export_wall_seconds']>LIMIT:receipt['status']='unknown_shared_budget_overrun'
        with (output/'external_launch_receipt.json').open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2)
    return 0 if receipt['status']=='campaign_process_exited' else 1


if __name__=='__main__':raise SystemExit(main())
