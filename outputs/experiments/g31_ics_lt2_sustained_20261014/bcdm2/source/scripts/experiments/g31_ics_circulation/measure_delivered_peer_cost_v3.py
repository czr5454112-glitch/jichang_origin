"""Explicitly archive the imported bare test helper; v1/v2 stay immutable."""
import time
BOOT=time.perf_counter()
from . import measure_delivered_peer_cost_v2 as v2

ROOT=v2.ROOT
MODULE='scripts.experiments.g31_ics_circulation.measure_delivered_peer_cost_v3'
private=v2.private


def sources():
    # source_closure does not resolve a bare import from the tests search path.
    # Name its source explicitly, since the v2 test reuses all nine old tests.
    return v2.original.base.image.source_closure(ROOT,(MODULE,
        v2.TEST[:-3].replace('/','.'),v2.HARNESS_TEST[:-3].replace('/','.'),
        v2.original.HARNESS_TEST[:-3].replace('/','.')))


verify=private(v2.verify,{'sources':sources})
run_child=private(v2.run_child,{'BOOT':BOOT})
pure=private(v2.pure,{'sources':sources,'MODULE':MODULE,'run_child':run_child})
prepare=private(v2.prepare,{'sources':sources,'verify':verify,'MODULE':MODULE})
execute=private(v2.execute,{'verify':verify,'BOOT':BOOT})
main=private(v2.main,{'BOOT':BOOT,'MODULE':MODULE,'pure':pure,'prepare':prepare,
    'execute':execute,'run_child':run_child})


if __name__=='__main__':raise SystemExit(main())
