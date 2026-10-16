"""One shared120 application budget, including native acceptance and save audit."""
import time
BOOT=time.monotonic()
import argparse
import json
from pathlib import Path
import sys
import traceback
from . import bounded_windows_job

MODULE=__package__+'.launch_live_initial_six_seam_v2'


def main():
    from . import research_live_initial_six_seam_v2 as campaign
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-plan',required=True)
    p.add_argument('--worker',action='store_true');args=p.parse_args();output=args.output.resolve()
    if args.worker:
        campaign.require(sys.stdin.readline()==args.expected_plan+'\n','worker_admission')
        try:campaign.worker(output,args.expected_plan)
        except BaseException:campaign.write(output/'failure.json',{'status':'unknown_failed','error':traceback.format_exc()});raise
        return 0
    campaign.require(campaign.sha(output/'plan.json')==args.expected_plan,'reviewed_plan')
    with (output/'execution_claim.json').open('x') as stream:json.dump({'plan_sha256':args.expected_plan,'no_restart':True},stream)
    report={'status':'unknown_launch_or_timeout','shared_application_seconds':campaign.LIMIT}
    try:
        remaining=campaign.LIMIT-(time.monotonic()-BOOT)-1.
        if remaining<=0:raise TimeoutError('initial_six:no_remaining_budget')
        command=[sys.executable,'-m',MODULE,'--output',str(output),'--expected-plan',args.expected_plan,'--worker']
        with (output/'stdout.log').open('x') as stdout,(output/'stderr.log').open('x') as stderr:
            result=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,
                admission=args.expected_plan,cwd=campaign.ROOT)
        report.update(process=result,command=command)
        if (output/'receipt.json').is_file():report['worker_receipt']=campaign.reference(output/'receipt.json')
        if result['status']=='exited' and result['exitcode']==0 and 'worker_receipt' in report:report['status']='worker_closed_status_not_inferred'
    except Exception:report['error']=traceback.format_exc()
    report['whole_python_before_final_export_seconds']=time.monotonic()-BOOT
    if report['whole_python_before_final_export_seconds']>campaign.LIMIT:report['status']='unknown_application_budget_exceeded'
    campaign.write(output/'bounded_execution.json',report)
    return 0 if report['status']=='worker_closed_status_not_inferred' and time.monotonic()-BOOT<=campaign.LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
