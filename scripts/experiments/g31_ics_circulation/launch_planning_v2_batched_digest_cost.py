"""One owned120 for preparation, or a separate single owned120 comparison."""
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
MODULE='scripts.experiments.g31_ics_circulation.measure_planning_v2_batched_digest_cost'
SOURCE_PLAN_SHA='b0d8e8a85cabdbd9c658c539d4fbd59fbcbca0cebfd8b8dc747d689a927f3ea5'
LIMIT=120.


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    p.add_argument('--pure',type=Path);p.add_argument('--plan-sha256')
    a=p.parse_args();output=a.output.resolve();process=None;error=None
    label='prepare' if a.prepare else 'campaign';admission=SOURCE_PLAN_SHA if a.prepare else a.plan_sha256
    command=[sys.executable,'-m',MODULE,'--output',str(output),'--admission',str(admission)]
    if a.prepare:
        if a.pure is None:raise ValueError('prepare_requires_pure')
        output.mkdir(parents=True,exist_ok=False)
        command+=['--prepare-child','--pure',str(a.pure.resolve())]
    else:command+=['--campaign-child','--plan-sha256',str(a.plan_sha256)]
    try:
        if not a.prepare and hashlib.sha256((output/'plan.json').read_bytes()).hexdigest()!=a.plan_sha256:
            raise ValueError('plan_sha')
        with (output/(label+'_outer_claim.json')).open('x') as f:json.dump({'one_attempt_only':True,'admission':admission},f)
        with (output/(label+'_stdout.log')).open('xb') as stdout,(output/(label+'_stderr.log')).open('xb') as stderr:
            process=bounded_windows_job.run(command,timeout=max(.001,LIMIT-(time.perf_counter()-BOOT)),
                stdout=stdout,stderr=stderr,admission=admission,cwd=ROOT)
        if process['status']!='exited' or process['exitcode']!=0:raise ValueError('owned_child_exit')
        if time.perf_counter()-BOOT>LIMIT:raise ValueError('whole_budget')
    except BaseException as exc:error=repr(exc)
    receipt={'schema':'g31.planning_v2_batched_digest.owned_launch.v1','mode':label,
        'status':'completed' if error is None else 'unknown_failed_or_timeout','error':error,
        'command':command,'process':process,'shared_seconds':LIMIT,
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,
        'scope':'Owned120 includes all child startup/source/input hashes, full bytes oracle, measurement/readback/export. External launch-to-exit clock additionally includes parent Python startup and final receipt write.',
        'native_calls':0,'model_calls':0}
    with (output/(label+'_bounded_execution.json')).open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2)
    return 0 if error is None else 1


if __name__=='__main__':raise SystemExit(main())
