"""Own imports, all96 branches and final audits under one unchanged600s Job."""
import argparse,json,sys,time,traceback,uuid
from pathlib import Path
from . import bounded_windows_job
from . import research_live_obligation_unloading as campaign

def launch(output):
    with (output/'launch_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'no_restart':True,'hard_timeout_seconds':campaign.HARD_TIMEOUT},stream)
    campaign.require(not (output/'receipt.json').exists() and not (output/'external_process.json').exists(),'attempt_already_started')
    token=uuid.uuid4().hex;started=time.perf_counter()
    command=[sys.executable,'-m','scripts.experiments.g31_ics_circulation.launch_live_obligation_unloading',
             '--worker','--output',str(output),'--admission',token]
    try:
        with (output/'stdout.log').open('w') as stdout,(output/'stderr.log').open('w') as stderr:
            result=bounded_windows_job.run(command,timeout=campaign.HARD_TIMEOUT,stdout=stdout,stderr=stderr,
                admission=token,cwd=str(campaign.ROOT))
    except Exception:
        campaign.write(output/'external_process.json',{'status':'launch_failed','error':traceback.format_exc(),
            'parent_post_import_wall_seconds':time.perf_counter()-started,'no_native_success_claim':True});raise
    campaign.write(output/'external_process.json',{**result,'command':command,
        'parent_post_import_wall_seconds':time.perf_counter()-started,
        'whole_application_wall':'measured_by_external_invocation_wrapper','no_native_success_claim':True})
    if result['status']!='exited' or result['exitcode']!=0 or not (output/'receipt.json').exists():raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--admission')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true');modes.add_argument('--launch',action='store_true');modes.add_argument('--worker',action='store_true')
    args=parser.parse_args();args.output=args.output.resolve()
    if args.prepare:print(json.dumps(campaign.prepare(args.output)))
    elif args.launch:launch(args.output)
    else:
        if not args.admission or sys.stdin.readline().strip()!=args.admission:raise ValueError('owned_job_admission_required')
        try:campaign.worker(args.output)
        except Exception:
            campaign.write(args.output/'failure.json',{'status':'failed','error':traceback.format_exc()});raise
