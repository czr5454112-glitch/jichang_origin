"""Fixed entry-codec saved18 x ABBA72 complete publisher comparison.

No native/model execution. Candidate loading, direct support checks, all setup,
fixture loads, complete publication,72 exports/readback and cleanup belong to
one240s owned application. No mock sample is an actual request/100ms result.
"""
import time
BOOT = time.monotonic()
import argparse
import gc
import gzip
import hashlib
import json
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET
from types import BuiltinFunctionType, SimpleNamespace
from . import bounded_windows_job as bounded
from . import complete_root_evidence_c_normalizer as binding
from . import measure_complete_root_evidence_codec as legacy
from . import review_complete_tree_normalizer_saved18_v2 as parity

ROOT, OUT = parity.ROOT, parity.OUT
MODULE = 'scripts.experiments.g31_ics_circulation.measure_complete_root_c_normalizer'
PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_complete_root_c_normalizer_pure'
TEST = 'tests/test_g31_circulation_complete_root_c_normalizer_campaign.py'
LIMIT = 240.0
SCHEMA = 'g31.entry_complete_C_normalizer.ABBA72.v1'
SUPPORT = OUT/'c_tree_normalizer_saved18_prepare_002'
FIXED_EXTRA = {
    'complete_C_publisher_binding_pure_001/plan.json': '49d5d42d82f4d0034016bea126802871bac106f1f7edb34f4702aee8eba0817c',
    'complete_C_publisher_binding_pure_001/receipt.json': 'a8d686a1e872534fb8e4d434ff1ca04d2d6301849d321fce723ea32926dd331c',
    'complete_C_publisher_binding_pure_001/tests.xml': 'da942161751cc745fa959c12359c137c220688a7b1fca085a9a3ef0fba1828c5',
    'c_tree_normalizer_saved18_prepare_002/plan.json': '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e',
    'c_tree_normalizer_saved18_prepare_002/report.json': '7961d01ebada0b428fa552baca465e8cdc0b07a056b45675283ed66045f52e01',
    'c_tree_normalizer_saved18_prepare_002/external_application_wall.json': '3cd556a54a1b5989c8b9fa5b7137b5e86a9e5e198915426b11d326131283cba8',
    'initial_entry_codec_saved_review_001/report.json': '283cadcc3ec8ba36b4b33da213c4b6f45ef9d33dd1ee29da690d2b8c703a3cee',
}
require, sha, read, write = parity.require, parity.sha, parity.read, parity.write
mock, image = legacy.mock, parity.image
declarations, load_inputs = legacy.declarations, legacy.load_inputs


def bindings(arm, candidate_binding=None, clock=time):
    if arm == 'A': source = binding.frozen
    elif arm == 'B':
        require(candidate_binding is not None, 'C_publisher_binding_missing')
        source = candidate_binding
    else: raise ValueError('C_publisher_arm')
    method = mock.clone(source.EVIDENCE, time=clock, root_runtime_proof=legacy._fixture_proof)
    finish = mock.clone(source.finish_root, time=clock, evidence=method)
    publish = mock.clone(source.publish_root, time=clock, finish_root=finish)
    require(method.__code__ is binding.frozen.EVIDENCE.__code__ and
        finish.__code__ is binding.frozen.finish_root.__code__ and
        publish.__code__ is binding.frozen.publish_root.__code__, 'same_publisher_codes')
    return method, publish


def check_payload(value, try_normalize, original_normalize):
    """Preflight only: original exact normalization argument, not a projected subset."""
    before = parity.source_bytes(value)
    expected = original_normalize(value)
    direct = try_normalize(value)
    require(direct is not NotImplemented, 'publisher_direct_C_unsupported')
    require(parity.exact(direct, expected), 'publisher_direct_C_tree')
    source_ids, _ = parity.containers(value)
    expected_ids, n = parity.containers(expected); direct_ids, count = parity.containers(direct)
    require(len(expected_ids) == n == count == len(direct_ids) and
        not (expected_ids & source_ids) and not (direct_ids & (source_ids | expected_ids)), 'publisher_direct_C_owned')
    require(parity.source_bytes(value) == before, 'publisher_preflight_mutated')
    return expected, {'direct_C_supported': True, 'exact_and_new_owned_tree': True,
        'raw_normalization_bytes_sha256': hashlib.sha256(before).hexdigest(), 'containers': n}


def direct_support(record, candidate):
    require(type(candidate._try) is BuiltinFunctionType and candidate.module.try_normalize is candidate._try
            and candidate._try.__self__ is candidate.module, 'publisher_builtin_identity')
    calls = []
    def normalize(value):
        result, proof = check_payload(value, candidate._try, binding.provider.original.normalize)
        calls.append(proof)
        return result
    source = binding._bind_provider(normalize)
    method, publish = bindings('B', source)
    root = legacy.root_from_fixture(record, method); holder = []
    result = publish(root, holder)
    require(len(calls) == 1 and len(holder) == 1 and holder[0] is result, 'one_direct_payload_call')
    require(legacy.candidate.single.exact_tree(mock.semantic_record(result), mock.semantic_record(record)),
            'preflight_complete_record')
    return calls[0]


def frozen_references():
    refs = parity.references()
    for name, digest in FIXED_EXTRA.items(): require(sha(OUT/name) == digest, 'C_publisher_reference:'+name)
    support = read(SUPPORT/'report.json')
    require(support['status'] == 'passed_all18_full_data_parity_no_performance_claim' and
        support['counts'] == {'roots': 18, 'closed': 16, 'unknown': 2, 'direct_C_supported': 18}, 'C18_support_reference')
    return {**refs, **FIXED_EXTRA}


def source_files():
    files = image.source_closure(ROOT, (MODULE, PURE_MODULE, TEST[:-3].replace('/', '.')))
    for name in parity.CORE: files[name] = (ROOT/name).read_bytes()
    return dict(sorted(files.items()))


def check_binding_pure(path):
    require(path.resolve() == (OUT/'complete_C_publisher_binding_pure_001/receipt.json').resolve(), 'binding_pure_path')
    receipt = read(path); plan = read(path.parent/'plan.json')
    require(sha(path.parent/'plan.json') == receipt['plan_sha256'] == FIXED_EXTRA['complete_C_publisher_binding_pure_001/plan.json']
        and sha(path) == FIXED_EXTRA['complete_C_publisher_binding_pure_001/receipt.json'], 'binding_pure_identity')
    require(receipt['bounded']['status'] == 'exited' and receipt['bounded']['exitcode'] == 0 and
        receipt['bounded']['windows_job_kill_on_close'] is True and receipt['native_calls'] == receipt['model_calls'] ==
        receipt['C_extension_loads'] == 0 and receipt['tests'] == {'tests': 8, 'failures': 0, 'errors': 0, 'skipped': 0},
        'binding_pure_status')
    cases = ET.parse(path.parent/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 8 and receipt['tests_sha256'] == sha(path.parent/'tests.xml') and
        not any(c.tag in ('failure', 'error', 'skipped') for case in cases for c in case), 'binding_pure_XML')
    for name, digest in plan['sources'].items():
        require(sha(ROOT/name) == digest == sha(path.parent/'source'/name), 'binding_pure_source')
    return 8


def input_manifest():
    build, rows, runtime = parity.metadata()
    return build, {r['key']: {'path': r['path'], 'sha256': r['sha256']} for r in rows}, runtime


def prepare(output, pure, binding_pure):
    output.mkdir(exist_ok=False)
    references = frozen_references(); build, inputs, runtime = input_manifest()
    own_tests = legacy._check_pure(pure, 20)
    binding_tests = check_binding_pure(binding_pure)
    files = source_files(); sources, archives = {}, {}
    for name, data in files.items():
        destination = output/'source'/name; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(data)
        sources[str(ROOT/name)] = hashlib.sha256(data).hexdigest(); archives[str(ROOT/name)] = str(destination.relative_to(output))
    value = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'row_order': declarations(inputs), 'input_raw': inputs,
        'historical_roots': 18, 'publication_calls': 72, 'calls_per_arm': 36, 'hard_timeout_seconds': LIMIT,
        'source_sha256': sources, 'source_archive': archives, 'original_frozen_sources': parity.frozen_sources(),
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)}, 'references': references,
        'binary': build['binary'], 'runtime_dependencies': runtime, 'toolchain_count': len(build['toolchain_before']),
        'harness_pure': legacy.c.reference(pure),
        'binding_pure': legacy.c.reference(binding_pure), 'harness_tests': own_tests, 'binding_tests': binding_tests,
        'binding_source_proof': binding.source_proof(), 'default_GC_required': True,
        'arms': {'A': 'Actual entry_codec complete publisher with original Python normalize.',
            'B': 'Same complete publisher with verified C Candidate normalization; original fallback retained.'},
        'scope': {'sample': 'Fresh mock root creation, complete evidence, normalization, original encoding/strict decode/reencode, hash/ledger/return codec and publisher append/return.',
            'whole': 'Python startup/imports,6124 toolchain identities,169/135 original source checks, extension load/runtime checks,18fixture loads,18 direct-C payload full publisher preflights,72samples,all gzip/hash/ledger/readback,teardown/exit within shared240.',
            'clocks': 'Only existing regenerated body/finalization/return clock fields and derived formulas differ; original event/deadline/root clocks remain exact data.',
            'budget': 'Original complete codec72 campaign58.5363275s and C18 parity38.5607279s are separate historical cost references;240 is a fixed failure bound, not a duration guarantee.',
            'no_claim': ['new native-root latency', '100ms certification', 'new choice/protection effect', 'full-day throughput'],
            'direct_support': 'Each actual complete EVIDENCE normalization argument is captured by a private preflight provider; verified builtin must support it with exact result and fresh containers. All preflights charged towhole.'},
        'preparation_raw_reads': 0, 'native_calls': 0, 'predictor_calls': 0}
    write(output/'plan.json', value)
    write(output/'ledger.json', [{**row, 'status': 'unknown_unexecuted'} for row in value['row_order']])
    write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': legacy.c.reference(output/'plan.json'),
        'source_count': len(sources), 'pure_tests': own_tests, 'binding_tests': binding_tests,
        'preparation_raw_reads': 0, 'performance_dispatched': False, 'native_calls': 0, 'predictor_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
            '--plan-sha256', sha(output/'plan.json')]})
    print(json.dumps(read(output/'preparation.json')))


def verify_pins(output, expected):
    require(sha(output/'plan.json') == expected, 'C_publisher_plan'); plan = read(output/'plan.json')
    require(plan['schema'] == SCHEMA and plan['historical_roots'] == 18 and plan['publication_calls'] == 72
        and plan['calls_per_arm'] == 36 and plan['hard_timeout_seconds'] == LIMIT and
        plan['row_order'] == declarations(plan['input_raw']) and len(plan['input_raw']) == 18, 'C_publisher_denominator')
    require(plan['references'] == frozen_references() and plan['binding_source_proof'] == binding.source_proof(), 'C_publisher_proof')
    require(plan['original_frozen_sources'] == parity.frozen_sources(), 'original169135_changed')
    files = source_files()
    require(plan['source_sha256'] == {str(ROOT/name): hashlib.sha256(data).hexdigest() for name, data in files.items()}, 'C_publisher_closure')
    for name, digest in plan['source_sha256'].items(): require(sha(output/plan['source_archive'][name]) == digest, 'C_publisher_archive')
    build, raws, runtime = input_manifest()
    require(plan['input_raw'] == raws and plan['binary'] == build['binary'] and
        plan['runtime_dependencies'] == runtime and plan['toolchain_count'] == len(build['toolchain_before']) == 6124, 'C_publisher_build')
    require(sha(plan['binary']['path']) == plan['binary']['sha256'], 'C_publisher_binary')
    for path, digest in build['toolchain_before'].items(): require(sha(path) == digest, 'C_publisher_toolchain:'+path)
    for item in runtime.values():
        if 'path' in item: require(sha(item['path']) == item['sha256'], 'C_publisher_runtime')
    for item in raws.values(): require(sha(item['path']) == item['sha256'], 'C_publisher_raw')
    for label, minimum in (('harness_pure', 20), ('binding_pure', 8)):
        item = plan[label]; require(sha(item['path']) == item['sha256'], label+'_sha')
        if label == 'binding_pure': check_binding_pure(Path(item['path']))
        else: legacy._check_pure(Path(item['path']), minimum)
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'C_publisher_python')
    return plan


def loaded_sources(plan):
    result = {}
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, '__file__', None)
        if not raw: continue
        path = Path(raw).resolve()
        if not path.is_relative_to(ROOT): continue
        if path.suffix == '.py':
            require(plan['source_sha256'].get(str(path)) == sha(path), 'C_publisher_loaded:'+name)
        else: require(str(path) == str(Path(plan['binary']['path']).resolve()) and sha(path) == plan['binary']['sha256'], 'C_publisher_unexpected_extension')
        result[name] = {'path': str(path), 'sha256': sha(path)}
    require(not any('czr005_circulation' in name for name in sys.modules), 'C_publisher_native_import')
    return result


def verify_outputs(output, plan, inputs):
    # Unchanged72-row/ordered type/float/clock/whole-record checker. Labels below
    # state the new reference; none of its field checks are replaced or skipped.
    result = legacy.verify_outputs(output, plan, inputs)
    result['status'] = 'passed_exact_complete_entry_codec18_C_normalizer_ABBA72'
    result['scope'] = 'Fixed saved entrycodec18 complete publisher only; no live observation, policy, model or native execution.'
    return result


def verify_saved(output, expected):
    plan = verify_pins(output, expected)
    return verify_outputs(output, plan, load_inputs(plan))


def worker(output, expected):
    ledger = read(output/'ledger.json')
    try:
        plan = verify_pins(output, expected); require(gc.isenabled(), 'C_publisher_default_GC')
        entry = loaded_sources(plan)
        setup = time.perf_counter_ns()
        source_expected = {str(Path(m.__file__).resolve()): plan['source_sha256'][str(Path(m.__file__).resolve())]
            for m in (binding.provider.original, binding.provider.original.wire)}
        candidate = binding.provider.load_candidate(plan['binary']['path'], plan['binary']['sha256'], source_expected)
        runtime = parity.loaded_runtime(plan); candidate_binding = binding.bind(candidate)
        functions = {arm: bindings(arm, candidate_binding) for arm in ('A', 'B')}
        inputs = load_inputs(plan); fingerprints = {key: legacy._fixture_hash(record) for key, record in inputs.items()}
        support = {key: direct_support(record, candidate) for key, record in inputs.items()}
        require(len(support) == 18 and all(x['direct_C_supported'] and x['exact_and_new_owned_tree'] for x in support.values()), 'C_publisher_direct18')
        write(output/'direct_support.json', support)
        setup_end = time.perf_counter_ns()
        require(len(ledger) == 72 and all(row == {**declared, 'status': 'unknown_unexecuted'}
            for row, declared in zip(ledger, plan['row_order'], strict=True)), 'fresh_ledger')
        for index, row in enumerate(ledger):
            declared = plan['row_order'][index]
            row['status'] = 'unknown_in_progress'; write(output/'ledger.json', ledger)
            method, publish = functions[row['arm']]
            start = time.perf_counter_ns()
            root = legacy.root_from_fixture(inputs[row['key']], method); holder = []
            result = publish(root, holder)
            require(len(holder) == 1 and holder[0] is result, 'C_publisher_append_identity')
            end = time.perf_counter_ns()
            mock.current_clock_bounds(result, start, end)
            row.update(started_ns=start, finished_ns=end, elapsed_ns=end-start)
            export_start = time.perf_counter_ns()
            path = output/'raw'/f'{index:03d}.json.gz'; path.parent.mkdir(exist_ok=True)
            with gzip.open(path, 'wt', encoding='utf8', compresslevel=1) as stream:
                json.dump({'declaration': declared, 'record': result}, stream, ensure_ascii=False, allow_nan=False)
            row.update(status='saved', raw=legacy.c.reference(path), gzip_hash_elapsed_ns=time.perf_counter_ns()-export_start)
            write(output/'ledger.json', ledger)
            del root, holder, result
        require(fingerprints == {key: legacy._fixture_hash(record) for key, record in inputs.items()}, 'C_publisher_fixture_changed')
        report = verify_outputs(output, plan, inputs)
        report.update(direct_C_supported=18, direct_support=legacy.c.reference(output/'direct_support.json'),
            fixture_load_binding_and_full_support_preflight_ms=(setup_end-setup)/1e6,
            actual_runtime=runtime, GC_enabled_entry=True, GC_enabled_exit=gc.isenabled())
        require(gc.isenabled(), 'C_publisher_GC_changed')
        write(output/'report.json', report)
        verify_pins(output, expected); end_loaded = loaded_sources(plan)
        require(all(end_loaded.get(name) == value for name, value in entry.items()), 'C_publisher_loaded_changed')
        del inputs, functions, candidate_binding, candidate, fingerprints
        write(output/'receipt.json', {'status': 'completed_fixed_entry_codec_C_mock_ABBA', 'plan_sha256': expected,
            'source_changed': [], 'report': legacy.c.reference(output/'report.json'), 'direct_support': legacy.c.reference(output/'direct_support.json'),
            'loaded_project_sources_entry': entry, 'loaded_project_sources_exit': end_loaded,
            'native_calls': 0, 'predictor_calls': 0, 'GC_enabled': gc.isenabled(),
            'worker_seconds_before_receipt': time.monotonic()-BOOT})
    except BaseException:
        write(output/'failure.json', {'status': 'failed_or_unknown', 'error': traceback.format_exc()})
        write(output/'ledger.json', ledger)
        raise


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--pure-receipt', type=Path)
    parser.add_argument('--binding-pure-receipt', type=Path); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--plan-sha256')
    args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output, args.pure_receipt.resolve(), args.binding_pure_receipt.resolve()); return 0
    if args.worker:
        require(sys.stdin.readline() == args.plan_sha256+'\n', 'C_publisher_admission')
        worker(output, args.plan_sha256); return 0
    require(args.execute, 'C_publisher_explicit_execute')
    with (output/'execution_claim').open('x'): pass
    require(sha(output/'plan.json') == args.plan_sha256, 'C_publisher_launch_plan')
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--plan-sha256', args.plan_sha256]
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded.run(command, timeout=LIMIT-(time.monotonic()-BOOT)-1,
            admission=args.plan_sha256, stdout=out, stderr=err, cwd=ROOT)
    write(output/'bounded_execution.json', {'process': process, 'command': command,
        'launcher_seconds_including_imports': time.monotonic()-BOOT, 'shared_limit_seconds': LIMIT,
        'report': legacy.c.reference(output/'report.json') if (output/'report.json').is_file() else None,
        'external_whole_python_launch_through_exit_required': True, 'native_calls': 0, 'predictor_calls': 0})
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 and time.monotonic()-BOOT <= LIMIT else 1


if __name__ == '__main__': raise SystemExit(main())
