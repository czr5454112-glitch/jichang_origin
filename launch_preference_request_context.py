"""Own a <=120s pure worker Job; preserves failures and full dispatch envelope."""
import time
BOOT=time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from scripts.experiments.g31_ics_circulation import bounded_windows_job


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('tests','profile'),required=True)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parent;output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    admission=sha(root/'measure_preference_request_context.py')
    command=[sys.executable,'-m','measure_preference_request_context','--mode',args.mode,'--output',str(output/'worker'),'--admission',admission]
    receipt={'status':'unknown_before_dispatch','mode':args.mode,'command':command,'hard_limit_seconds':120.,
        'worker_source_sha256':admission,'launcher_source_sha256':sha(__file__),'native_executions':0,
        'parent_python_startup_before_BOOT':'Unmeasured internally; external measured wrapper records launch-to-exit.'}
    try:
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
                stdout=stdout,stderr=stderr,admission=admission,cwd=root)
        receipt['process']=process
        receipt['status']='child_passed' if process['status']=='exited' and process['exitcode']==0 else 'child_failed_or_unknown'
    except BaseException as error:
        receipt.update(status='launcher_failed_or_unknown',error=repr(error));raise
    finally:
        receipt['artifact_sha256']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}
        receipt['dispatch_through_evidence_hash_wall_seconds']=time.perf_counter()-BOOT
        if receipt['dispatch_through_evidence_hash_wall_seconds']>120.:receipt['status']='unknown_dispatch_budget_exceeded'
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'seconds':receipt['dispatch_through_evidence_hash_wall_seconds']}))
    return 0 if receipt['status']=='child_passed' else 1


if __name__=='__main__':raise SystemExit(main())
