"""Versioned exact typed clock readback; preserve prepared v1 unchanged."""
import time
BOOT=time.perf_counter()
from types import FunctionType
from . import measure_delivered_peer_cost as original

ROOT,OUT=original.ROOT,original.OUT
MODULE='scripts.experiments.g31_ics_circulation.measure_delivered_peer_cost_v2'
TEST=original.TEST
HARNESS_TEST='tests/test_g31_circulation_delivered_peer_cost_harness_v2.py'
PURE_COUNT=52
METRICS=frozenset(('started_ns','finished_ns','validator_ns','digest_entered','digest_completed',
    'digest_raised','digest_ns','validator_outside_digest_ns'))


def private(function, updates):
    result=FunctionType(function.__code__,{**function.__globals__,**updates},function.__name__,
                        function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


def sources():
    return original.base.image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.'),
        HARNESS_TEST[:-3].replace('/','.')))


def audit_records(records):
    original.require(type(records) is list,'typed_record_list')
    for row in records:
        original.require(type(row) is dict and all(type(row[k]) is int and row[k]>=0
            for k in ('ordinal','batch','repeat')),'typed_nonnegative_indices')
        m=row['metrics']
        original.require(type(m) is dict and set(m)==METRICS,'closed_metrics_domain')
        original.require(all(type(m[k]) is int and m[k]>=0 for k in
            ('started_ns','finished_ns','validator_ns')),'typed_nonnegative_clocks')
        if row['arm']=='B':original.require(all(type(m[k]) is int and m[k]>=0 for k in
            ('digest_entered','digest_completed','digest_raised','digest_ns','validator_outside_digest_ns')),
            'typed_nonnegative_nested_counts_and_clocks')
    return original.audit_records(records)


verify=private(original.verify,{'sources':sources})
run_child=private(original.run_child,{'BOOT':BOOT})
pure=private(original.pure,{'sources':sources,'MODULE':MODULE,'PURE_COUNT':PURE_COUNT,'run_child':run_child})
prepare=private(original.prepare,{'sources':sources,'PURE_COUNT':PURE_COUNT,'verify':verify,'MODULE':MODULE})
execute=private(original.execute,{'verify':verify,'audit_records':audit_records,'BOOT':BOOT})
main=private(original.main,{'BOOT':BOOT,'MODULE':MODULE,'HARNESS_TEST':HARNESS_TEST,'pure':pure,
    'prepare':prepare,'execute':execute,'run_child':run_child})


if __name__=='__main__':raise SystemExit(main())
