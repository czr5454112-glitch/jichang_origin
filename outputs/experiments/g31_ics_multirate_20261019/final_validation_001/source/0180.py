"""Own the entire synthetic ABBA campaign and verifier tree for at most120s."""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
MODULE='scripts.experiments.g31_ics_circulation.measure_bridge_copy_scopes'
LIMIT=120.


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
    a=p.parse_args();output=a.output.resolve();started=time.perf_counter();process=None;failure=None
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--campaign-child','--plan-sha256',a.plan_sha256]
    try:
        if hashlib.sha256((output/'plan.json').read_bytes()).hexdigest()!=a.plan_sha256:raise ValueError('outer_plan_sha')
        with (output/'outer_claim.json').open('x',encoding='utf8') as stream:
            json.dump({'plan_sha256':a.plan_sha256,'one_attempt_only':True},stream)
        with (output/'campaign_stdout.log').open('xb') as stdout,(output/'campaign_stderr.log').open('xb') as stderr:
            process=bounded_windows_job.run(command,timeout=max(.001,LIMIT-(time.perf_counter()-BOOT)),
                stdout=stdout,stderr=stderr,admission=a.plan_sha256,cwd=ROOT)
        if process['status']!='exited' or process['exitcode']!=0:raise ValueError('outer_campaign_exit')
        if time.perf_counter()-BOOT>LIMIT:raise ValueError('outer_whole_budget')
    except BaseException as error:failure=repr(error)
    receipt={'schema':'g31.bridge.copy_scopes.synthetic_ABBA.owned_launch.v1',
        'status':'completed' if failure is None else 'unknown_failed_or_timeout','error':failure,
        'command':command,'process':process,'plan_sha256':a.plan_sha256,'shared_seconds':LIMIT,
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,'dispatch_to_return_seconds':time.perf_counter()-started,
        'scope':'Outer Job contains campaign source checks, fixtures, all measurements, saved verification and exports; this final launcher receipt and interpreter startup require external launch-to-exit clock.',
        'native_calls':0,'full_audit_accepted':False}
    with (output/'bounded_execution.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2)
    return 0 if failure is None else 1


if __name__=='__main__':raise SystemExit(main())
