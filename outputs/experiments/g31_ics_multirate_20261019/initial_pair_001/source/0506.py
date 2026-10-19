"""New synthetic gate: correct only the old-assessor test reference.

bcp1 and its three sources stay immutable. No C load, fixture decoding or
saved replay. The existing owned120 runner code executes with private globals.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import hashlib
from types import FunctionType

from . import run_bridge_saved_c_digest_pure as old

MODULE = 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_pure_v2'
TEST = 'tests/test_g31_circulation_bridge_saved_c_digest_v2.py'
SCHEMA = 'g31.bridge.saved_C_digest.synthetic_pure.v2'
OLD_TEST_SHA = 'fd14f20da0e4cf938d9cd6c803127199631eee572d4847b0a510f7ddecdb25b7'
NEW_TEST_SHA = 'c4f31ce0e81c41e38b51a51fba2a5fb7c4690147dad308665ed382a6108c66f5'
OLD_RUNNER_SHA = '169a7ea117dd04cedda6ad4c796b6cafb4f030dec971bf18f234c5231a0c6c98'
OLD_REFERENCE = b'old = c.r.original.assess(raw, plan)'
NEW_REFERENCE = b"old = c.r.runner_namespace()['assess'](raw, plan)"


def source_revision():
    before = (old.ROOT / old.TEST).read_bytes()
    after = (old.ROOT / TEST).read_bytes()
    old.require(hashlib.sha256(before).hexdigest() == OLD_TEST_SHA
        and hashlib.sha256(after).hexdigest() == NEW_TEST_SHA
        and old.sha(old.__file__) == OLD_RUNNER_SHA, 'v2_frozen_sources')
    old.require(before.count(OLD_REFERENCE) == after.count(NEW_REFERENCE) == 1
        and after.replace(NEW_REFERENCE, OLD_REFERENCE) == before,
        'v2_only_test_baseline_expression')
    return {'schema': 'g31.bridge.saved_C_digest.assessor_reference_fix.v1',
        'only_test_change': 'Use the actual old serialize-once runner factory assessor, including its SCHEMA. Full ordered bytes comparison is retained.',
        'prior_failed_gate': 'bcp1;37 collected,36 passed,1 baseline-schema assertion failure; no retry or rewritten result.',
        'binder_changed': False, 'guards_or_comparison_fields_removed': False,
        'private_assessor_calls': 2, 'expected_original_digest_spy_calls': 2,
        'full_C_or_stream_acceptance': False}


def sources():
    source_revision()
    result = old.sources()
    extra = old.image.source_closure(old.ROOT, (MODULE, TEST[:-3].replace('/', '.')))
    for name, data in extra.items():
        old.require(name not in result or result[name] == data, 'v2_source_union')
        result[name] = data
    old.require(old.TEST in result and TEST in result and old.HELPER in result,
                'v2_explicit_old_new_helper_roots')
    return dict(sorted(result.items()))


def namespace():
    # All inherited functions retain their defining module's full namespace,
    # original defaults/kwdefaults/cells and one shared fresh dictionary.
    source_revision()
    values = dict(vars(old))
    for name, function in vars(old).items():
        if isinstance(function, FunctionType) and function.__globals__ is vars(old):
            copied = FunctionType(function.__code__, values, function.__name__,
                function.__defaults__, function.__closure__)
            copied.__kwdefaults__ = function.__kwdefaults__
            copied.__annotations__ = dict(function.__annotations__)
            values[name] = copied
    values.update(BOOT=BOOT, MODULE=MODULE, TEST=TEST, SCHEMA=SCHEMA, sources=sources)
    old.require(values['main'].__code__ is old.main.__code__
        and values['worker'].__code__ is old.worker.__code__
        and values['source_check'].__code__ is old.source_check.__code__
        and values['main'].__globals__ is values['worker'].__globals__ is values
        and values['source_check'].__globals__ is values,
        'v2_complete_private_runner_wiring')
    return values


def main():
    return namespace()['main']()


if __name__ == '__main__':
    raise SystemExit(main())
