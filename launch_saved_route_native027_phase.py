"""Bound the separate saved-only audit; this does not extend the native campaign."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from scripts.experiments.g31_ics_circulation import bounded_windows_job

LIMIT=1800.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--expected-auditor-sha256',required=True);parser.add_argument('--expected-launcher-sha256',required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parent
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if sha(__file__)!=args.expected_launcher_sha256 or sha(root/'audit_saved_route_native027_phase.py')!=args.expected_auditor_sha256:
        raise ValueError('saved_audit_source_changed')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m','audit_saved_route_native027_phase','--source',str(args.source.resolve()),
        '--output',str(output/'audit'),'--admission',args.expected_auditor_sha256]
    remaining=LIMIT-(time.monotonic()-BOOT)
    receipt={'schema':'g31.saved_route_phase_audit.bounded_launch.v1','status':'unknown_before_dispatch',
        'command':command,'source_campaign':str(args.source.resolve()),'hard_limit_seconds':LIMIT,
        'auditor_sha256':args.expected_auditor_sha256,'launcher_sha256':args.expected_launcher_sha256,
        'pre_job_seconds':LIMIT-remaining,'native_executions':0,
        'timing_scope':'Whole owned child startup/import/audit/export is bounded. Parent Python startup before BOOT is unmeasured; no platform startup or100ms claim.'}
    try:
        if remaining<=0:raise TimeoutError('saved_audit_budget_before_job')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,
                admission=args.expected_auditor_sha256,cwd=root)
        receipt['process']=process
        if process['status']=='exited' and process['exitcode']==0:
            report=json.loads((output/'audit/report.json').read_bytes())
            if report.get('status')!='passed_saved_six_cell_audit_after_original_timeout':raise ValueError('saved_audit_report_unknown')
            receipt['status']='saved_audit_process_completed'
        else:receipt['status']='unknown_saved_audit_process'
    except BaseException as error:
        receipt.update(status='unknown_saved_audit_launcher_error',error=repr(error));raise
    finally:
        receipt['whole_dispatch_wall_seconds']=time.monotonic()-BOOT
        if receipt['whole_dispatch_wall_seconds']>LIMIT:receipt['status']='unknown_saved_audit_budget_overrun'
        if sha(__file__)!=args.expected_launcher_sha256 or sha(root/'audit_saved_route_native027_phase.py')!=args.expected_auditor_sha256:
            receipt['status']='unknown_saved_audit_source_drift'
        receipt['artifacts']={str(path.relative_to(output)):sha(path) for path in output.rglob('*') if path.is_file()}
        with (output/'bounded_execution.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2)
    print(json.dumps({'status':receipt['status'],'wall_seconds':receipt['whole_dispatch_wall_seconds']}))
    return 0 if receipt['status']=='saved_audit_process_completed' else 1


if __name__=='__main__':raise SystemExit(main())
