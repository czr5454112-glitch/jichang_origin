"""Distinct exclusive stage logs; retains failed v3 before-worker attempt."""
import time
BOOT=time.perf_counter()
from . import measure_delivered_peer_cost_v3 as v3

ROOT=v3.ROOT
MODULE='scripts.experiments.g31_ics_circulation.measure_delivered_peer_cost_v4'
HARNESS_TEST='tests/test_g31_circulation_delivered_peer_cost_harness_v4.py'
PURE_COUNT=57
private=v3.private
require=v3.v2.original.require
bounded_windows_job=v3.v2.original.bounded_windows_job
LIMIT=120.


def sources():
    return v3.v2.original.base.image.source_closure(ROOT,(MODULE,
        v3.v2.TEST[:-3].replace('/','.'),HARNESS_TEST[:-3].replace('/','.'),
        v3.v2.HARNESS_TEST[:-3].replace('/','.'),v3.v2.original.HARNESS_TEST[:-3].replace('/','.')))


def run_child(output,command,token):
    modes={flag:name for flag,name in (('--prepare-worker','prepare'),('--pure-worker','pure'),('--worker','execute')) if flag in command}
    require(len(modes)==1,'one_child_stage')
    label=next(iter(modes.values()))
    remaining=LIMIT-(time.perf_counter()-BOOT)-1.;require(remaining>0,'before_child_budget')
    with (output/(label+'_stdout.log')).open('xb') as out,(output/(label+'_stderr.log')).open('xb') as err:
        return bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=token,cwd=ROOT)


verify=private(v3.verify,{'sources':sources})
pure=private(v3.pure,{'sources':sources,'MODULE':MODULE,'PURE_COUNT':PURE_COUNT,'run_child':run_child})
prepare=private(v3.prepare,{'sources':sources,'verify':verify,'MODULE':MODULE,'PURE_COUNT':PURE_COUNT})
execute=private(v3.execute,{'verify':verify,'BOOT':BOOT})
main=private(v3.main,{'BOOT':BOOT,'MODULE':MODULE,'HARNESS_TEST':HARNESS_TEST,'pure':pure,
    'prepare':prepare,'execute':execute,'run_child':run_child})


if __name__=='__main__':raise SystemExit(main())
