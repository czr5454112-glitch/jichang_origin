"""Fixed saved18 ABBA72: current C publisher versus same C plus owned decode.

The accepted C publisher worker/launcher code is privately rebound with full
original globals. All direct18 support, full72 output/clock/ledger/hash checks,
default GC, failure ledger, toolchain/runtime/source checks and owned240 remain.
No performance/native/model run occurs on import or preparation.
"""
import time
BOOT = time.monotonic()
import hashlib
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

from . import measure_complete_root_c_normalizer as old
from . import complete_root_evidence_owned_decode_c_binding as binding

ROOT, OUT, LIMIT = old.ROOT, old.OUT, old.LIMIT
MODULE = 'scripts.experiments.g31_ics_circulation.measure_complete_root_owned_decode_c'
PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_complete_root_owned_decode_c_campaign_pure'
TEST = 'tests/test_g31_circulation_complete_root_owned_decode_c_campaign.py'
SCHEMA = 'g31.entry_complete_C_owned_decoder.ABBA72.v1'
OWNED_PURE = OUT/'complete_root_owned_decode_c_binding_pure_001/receipt.json'
OWNED_PURE_SHA = '230c62981522e47a70015796cdbdd68458b9d18dda68652ececb543f21077410'
REFERENCE_PACKAGE = OUT/'C_publisher_pair_prepare_001'
EXTRA_REFS = {
    'C_publisher_pair_prepare_001/plan.json': '840329a5c7eaf928f92b7c6d9a4bbfaf08bdf12260141e41f2863746e2df4072',
    'C_publisher_pair_prepare_001/receipt.json': '693a2f8bce7860fe6ef7cdadc1428f0b6dce4a219806c5a8b7750d884262a3e3',
    'C_publisher_pair_prepare_001/report.json': '19f4c29ce1f5ffa1897a3ccab62b3e1d522714c873adb5819f0863f902624f01',
    'C_publisher_pair_prepare_001/bounded_execution.json': 'b03dc2fbc9658dd85bdbf8bf1ef1a12302eef5fce8cd2d38dea582a6fd8570f9',
}
ARMS = {'A': 'Current complete publisher with verified C Candidate normalization and original decoded tree validation.',
        'B': 'Same verified C normalization facade and complete publisher; only internal decoded _tree omitted under owned source proof.'}
require, sha, read, write = old.require, old.sha, old.read, old.write
image, mock, legacy, parity = old.image, old.mock, old.legacy, old.parity
declarations, load_inputs = old.declarations, old.load_inputs
private = binding.owned.private


def bindings(arm, pair=None, clock=time):
    require(arm in ('A', 'B') and type(pair) is SimpleNamespace and
            set(vars(pair)) == {'A', 'B', 'proof'}, 'owned_C_pair_required')
    require(pair.A.EVIDENCE.__globals__['normalization'] is
            pair.B.EVIDENCE.__globals__['normalization'], 'owned_C_same_provider')
    source = pair.A if arm == 'A' else pair.B
    expected = old.binding.frozen if arm == 'A' else binding.owned
    method = mock.clone(source.EVIDENCE, time=clock, root_runtime_proof=legacy._fixture_proof)
    finish = mock.clone(source.finish_root, time=clock, evidence=method)
    publish = mock.clone(source.publish_root, time=clock, finish_root=finish)
    require(method.__code__ is expected.EVIDENCE.__code__ and
            finish.__code__ is old.binding.frozen.finish_root.__code__ and
            publish.__code__ is old.binding.frozen.publish_root.__code__, 'owned_C_publisher_codes')
    return method, publish


def frozen_references():
    references = old.frozen_references()
    for name, digest in EXTRA_REFS.items(): require(sha(OUT/name) == digest, 'owned_C_reference:' + name)
    plan = read(REFERENCE_PACKAGE/'plan.json')
    for name, digest in plan['source_sha256'].items():
        require(sha(name) == digest == sha(REFERENCE_PACKAGE/plan['source_archive'][name]),
                'owned_C_original_publisher_source')
    receipt = read(REFERENCE_PACKAGE/'receipt.json')
    require(receipt['status'] == 'completed_fixed_entry_codec_C_mock_ABBA' and
            receipt['source_changed'] == [], 'owned_C_original_publisher_unaccepted')
    return {**references, **EXTRA_REFS}


def source_files():
    entries = (MODULE, PURE_MODULE, TEST[:-3].replace('/', '.'),
        'tests.test_g31_circulation_complete_root_owned_decode_v2',
        'tests.test_g31_circulation_complete_root_owned_decode_c_binding',
        'tests.test_g31_circulation_complete_root_c_normalizer_campaign',
        'tests.test_g31_circulation_complete_root_evidence_codec_campaign')
    files = image.source_closure(ROOT, entries)
    for name in parity.CORE: files[name] = (ROOT/name).read_bytes()
    return dict(sorted(files.items()))


def check_owned_pure():
    require(sha(OWNED_PURE) == OWNED_PURE_SHA, 'owned_C_pure_identity')
    require(legacy._check_pure(OWNED_PURE, 105) == 105, 'owned_C_pure_count')
    receipt = read(OWNED_PURE)
    require(receipt['C_extension_loads'] == receipt['saved_raw_scans'] == 0,
            'owned_C_pure_must_not_load_C_or_fixtures')
    return legacy.c.reference(OWNED_PURE)


def worker_source_proof():
    require(worker.__code__ is old.worker.__code__ and worker.__closure__ is old.worker.__closure__ and
            set(worker.__globals__) == set(old.worker.__globals__) and
            {key for key in old.worker.__globals__
             if worker.__globals__[key] is not old.worker.__globals__[key]} == set(_WORKER_CHANGES),
            'owned_C_worker_namespace_or_code')
    require(worker.__globals__['direct_support'] is old.direct_support and
            worker.__globals__['load_inputs'] is old.load_inputs and
            main.__code__ is old.main.__code__, 'owned_C_preflight_loader_or_launcher_changed')
    return {'original_worker_code_identity': True, 'original_launcher_code_identity': True,
        'original_worker_source_sha256': hashlib.sha256(inspect.getsource(old.worker).encode()).hexdigest(),
        'changed_worker_globals': sorted(_WORKER_CHANGES),
        'original_full18_direct_support_preflight': True,
        'original_72_output_checker_called_complete': True,
        'unknowns_failure_ledger_GC_and_cost_boundaries_retained': True}


def prepare(output, pure, binding_pure):
    output.mkdir(exist_ok=False)
    references = frozen_references(); build, inputs, runtime = old.input_manifest()
    tests = legacy._check_pure(pure, 131)
    require(tests == 131, 'owned_C_harness_pure_exact131')
    original_tests = old.check_binding_pure(binding_pure)
    owned_pure = check_owned_pure()
    sources, archives = {}, {}
    for name, data in source_files().items():
        target = output/'source'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        sources[str(ROOT/name)] = hashlib.sha256(data).hexdigest()
        archives[str(ROOT/name)] = str(target.relative_to(output))
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'row_order': declarations(inputs),
        'input_raw': inputs, 'historical_roots': 18, 'publication_calls': 72, 'calls_per_arm': 36,
        'hard_timeout_seconds': LIMIT, 'source_sha256': sources, 'source_archive': archives,
        'original_frozen_sources': parity.frozen_sources(),
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)}, 'references': references,
        'binary': build['binary'], 'runtime_dependencies': runtime,
        'toolchain_count': len(build['toolchain_before']),
        'harness_pure': legacy.c.reference(pure), 'binding_pure': legacy.c.reference(binding_pure),
        'harness_tests': tests, 'binding_tests': original_tests, 'owned_pure': owned_pure,
        'owned_tests': 105, 'binding_source_proof': binding.source_proof(),
        'worker_source_proof': worker_source_proof(), 'default_GC_required': True, 'arms': ARMS,
        'scope': {
            'sample': 'Fresh mock root through complete evidence, same verified C normalize/fallback, original UTF8 encoder, strict parse/canonical compare, hash/ledger/return codec and append/outside-return.',
            'whole': 'Python startup/import, full6124 toolchain/runtime/source checks, C load/both bindings,18 raw loads and exact directC full-publisher support preflights,all72 samples,exports,hashes,ledger,complete saved readback,teardown/exit shared240.',
            'clocks': 'Original event/root/deadline times are historical input; only original regenerated body/publication clocks and their exact formulas change.',
            'budget': 'Fixed240 from accepted full72 publisher design. Profile identifies repeated decoded tree work; instrumented times are not predicted unprofiled savings.',
            'resource_failures': 'Different MemoryError/recursion/allocation points may fail unknown; no success fallback or failure deletion.',
            'no_claim': ['new native root or100ms certificate', 'Python-to-C gain', 'policy/protection change', 'full-day certificate'],
            'unknown_roots': 'All18 unchanged including2 historically unknown; no sample exclusion.'},
        'preparation_raw_reads': 0, 'native_calls': 0, 'predictor_calls': 0}
    write(output/'plan.json', plan)
    write(output/'ledger.json', [{**row, 'status': 'unknown_unexecuted'} for row in plan['row_order']])
    write(output/'preparation.json', {'status': 'prepared_source_review_pending',
        'plan': legacy.c.reference(output/'plan.json'), 'source_count': len(sources),
        'pure_tests': tests, 'owned_binding_tests': 105, 'preparation_raw_reads': 0,
        'performance_dispatched': False, 'native_calls': 0, 'predictor_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
                            '--plan-sha256', sha(output/'plan.json')]})
    print(old.json.dumps(read(output/'preparation.json')))


def verify_pins(output, expected):
    # Execute every original build/input/source/toolchain/pure/denominator check.
    checker = private(old.verify_pins, {'SCHEMA': SCHEMA, 'frozen_references': frozen_references,
        'source_files': source_files, 'binding': SimpleNamespace(source_proof=binding.source_proof)})
    plan = checker(output, expected)
    require(plan['owned_pure'] == check_owned_pure() and plan['owned_tests'] == 105 and
            plan['harness_tests'] == 131 and read(Path(plan['harness_pure']['path']))['tests'] == 131 and
            plan['arms'] == ARMS and plan['worker_source_proof'] == worker_source_proof(),
            'owned_C_extra_proof_or_arm_changed')
    return plan


def verify_outputs(output, plan, inputs):
    result = old.verify_outputs(output, plan, inputs)
    result['status'] = 'passed_exact_complete_entry18_same_C_owned_decode_ABBA72'
    result['scope'] = 'Same verified C publisher versus its private owned-decoder change only; all historical unknowns preserved. No actual native request or100ms claim.'
    return result


def verify_saved(output, expected):
    plan = verify_pins(output, expected)
    return verify_outputs(output, plan, load_inputs(plan))


_WORKER_CHANGES = {'BOOT': BOOT, 'verify_pins': verify_pins, 'bindings': bindings,
    'binding': SimpleNamespace(provider=old.binding.provider, bind=binding.bind),
    'verify_outputs': verify_outputs}
worker = private(old.worker, _WORKER_CHANGES)
# Full original launcher includes exclusive execution claim, stdin admission,
# remaining shared240 Job assignment, error output and final external-wall flag.
main = private(old.main, {'BOOT': BOOT, 'MODULE': MODULE, 'prepare': prepare, 'worker': worker})


if __name__ == '__main__': raise SystemExit(main())
