"""Shared600s owned child tree, including all native/RPC/saved verification."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from . import bounded_windows_job

LIMIT=600.
MODULE='scripts.experiments.g31_ics_circulation.initial_owner_route_campaign_v3'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--campaign-sha256',required=True)
    a=p.parse_args();output=a.output.resolve()
    digest=hashlib.sha256((output/'campaign.json').read_bytes()).hexdigest()
    if digest!=a.campaign_sha256:
        raise ValueError('initial_launch:campaign_changed')
    if any((output/name).exists() for name in ('receipt.json','worker_claim.json','external_launch_receipt.json')):
        raise ValueError('initial_launch:already_attempted')
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'campaign_sha256':digest,'shared_seconds':LIMIT},stream)
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--campaign-sha256',digest,'--admission',digest]
    receipt={'status':'unknown_before_dispatch','campaign_sha256':digest,'command':command,
             'shared_seconds':LIMIT,'external_application_startup_clock_required':True}
    try:
        remaining=LIMIT-(time.monotonic()-BOOT)
        if remaining<=0:
            raise TimeoutError('initial_launch:budget_before_assignment')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            result=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,
                admission=digest,cwd=Path(__file__).resolve().parents[3])
        receipt['process']=result
        if result['status']=='exited' and result['exitcode']==0:
            internal=json.loads((output/'receipt.json').read_bytes())
            if (internal['status']!='completed_finite_request_cohort' or internal['branches']!=18 or
                    internal['campaign_sha256']!=digest or internal['source_changed']!=[]):
                raise ValueError('initial_launch:unconfirmed_completion')
            receipt['status']='campaign_process_exited'
        else:
            receipt['status']='unknown_campaign_process'
    except BaseException as error:
        receipt.update(status='unknown_launcher_error',error=repr(error))
        raise
    finally:
        receipt['before_final_evidence_export_seconds']=time.monotonic()-BOOT
        if receipt['before_final_evidence_export_seconds']>LIMIT:
            receipt['status']='unknown_shared_budget_overrun'
        receipt['scope']='Owned child imports/acceptance/native/RPC/shutdown/export/verification bounded. External launch-to-exit clock must include launcher startup beforeBOOT and final receipt export; no amortization or complete100ms certificate.'
        for name in ('receipt.json','branch_ledger.json','predictor_lifetime.json','run_acceptance.json','verification.json','stdout.log','stderr.log'):
            path=output/name
            if path.is_file():
                receipt.setdefault('artifacts',{})[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        with (output/'external_launch_receipt.json').open('x',encoding='utf8') as stream:
            json.dump(receipt,stream,ensure_ascii=False,allow_nan=False,indent=2)
    return 0 if receipt['status']=='campaign_process_exited' else 1


if __name__=='__main__':
    raise SystemExit(main())
