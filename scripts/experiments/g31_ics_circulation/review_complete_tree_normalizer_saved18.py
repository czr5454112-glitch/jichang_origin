"""One fixed180 saved-data parity gate; preparation never opens the18 raw files.

No predictor, native session, performance comparison or campaign installation.
The full original root record is compared, including evidence/ledger/clocks.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import ctypes
import gc
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback
from types import FunctionType, SimpleNamespace
import uuid
from . import bounded_windows_job as bounded
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE = 'scripts.experiments.g31_ics_circulation.review_complete_tree_normalizer_saved18'
LIMIT = 180.
PRODUCER = OUT/'initial_owner_route_entry_codec_campaign_prepare_001'
BUILD = OUT/'c_tree_normalizer_build_004'
FUNCTIONAL = OUT/'c_tree_normalizer_functional_001'
REFS = {
    'initial_owner_route_entry_codec_campaign_prepare_001/campaign.json': '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a',
    'initial_owner_route_entry_codec_campaign_prepare_001/receipt.json': '49b0d7e2f4d019c1546fb34f941813198d21189d39735eb6e0ac3101f8c184bf',
    'initial_owner_route_entry_codec_campaign_prepare_001/branch_ledger.json': '661896d2848c1bcffcf9e7e405222b7955bd9ab1bf03956381ec10e4538b052a',
    'initial_owner_route_entry_codec_campaign_prepare_001/verification.json': '2d948207fcd77a97dc29491c3f22e8d5c476e24c94a479759002bcece7c533dc',
    'complete_root_evidence_codec_pair_prepare_001/plan.json': '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff',
    'c_tree_normalizer_prototype_001/source_plan.json': '4253992c420d32a0e918724e3d398704025d21bfd1ac9420f2525f875ee5f9c1',
    'c_tree_normalizer_build_prepare_004/plan.json': 'f20f4d411e2cd519bf2fb509f89b18a6d08c0d5f547598f89bef346836816281',
    'c_tree_normalizer_build_004/receipt.json': 'cc44e186ee143b76bc1993deb3a8521f800650231887caffe300ef57d0777a79',
    'c_tree_normalizer_build_004/external_application_wall.json': 'c2aaa6c27d33c2d4470fdd79b75bf4d141d787772f87d6cc55e7a3ad9e5a67b3',
    'c_tree_normalizer_functional_001/receipt.json': 'add2eef6ee390eb7c8e97ce94c37095a5041aa17ddc0a4d4b5b85e18c4603dac',
    'c_tree_normalizer_functional_001/tests.xml': '72f91df0775cf9a79116439f8727b0b1e0963f60e4c7239ede1fcf0f92c36025',
    'c_tree_normalizer_functional_001/external_application_wall.json': '3ce72ef0fefcdd481e0dbd549a57e52e0435ca6ff4fdb0bea753cc342369cfe0',
}
FROZEN = ('initial_owner_route_entry_codec_campaign_prepare_001/campaign.json',
          'complete_root_evidence_codec_pair_prepare_001/plan.json')
CORE = ('cpp/experimental/complete_tree_normalizer/CMakeLists.txt',
        'cpp/experimental/complete_tree_normalizer/normalizer.cpp',
        'scripts/experiments/g31_ics_circulation/complete_tree_normalizer_candidate.py',
        'tests/test_g31_circulation_complete_tree_normalizer_candidate.py')


def require(ok, reason):
    if not ok: raise ValueError('C_saved18:'+reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf8')


def references():
    for name, digest in REFS.items(): require(sha(OUT/name) == digest, 'reference_changed:'+name)
    return dict(REFS)


def frozen_sources():
    result = {}
    for name in FROZEN:
        path = OUT/name; plan = read(path); rows = {}
        for source, digest in plan['source_sha256'].items():
            archived = path.parent/plan['source_archive'][source]
            require(sha(source) == digest == sha(archived), 'frozen_source_changed:'+source)
            rows[source] = {'sha256': digest, 'archive': str(archived)}
        require(len(rows) == (169 if name == FROZEN[0] else 135), 'frozen_count')
        result[name] = rows
    return result


def closure():
    files = image.source_closure(ROOT, (MODULE,
        'scripts.experiments.g31_ics_circulation.complete_tree_normalizer_candidate',
        'scripts.experiments.g31_ics_circulation.complete_root_evidence_codec'))
    for name in CORE: files[name] = (ROOT/name).read_bytes()
    return dict(sorted(files.items()))


def metadata():
    references()
    build, functional, campaign, ledger = read(BUILD/'receipt.json'), read(FUNCTIONAL/'receipt.json'), read(PRODUCER/'campaign.json'), read(PRODUCER/'branch_ledger.json')
    require(build['status'] == 'build_passed_imports_inspected_unloaded' and
        build['imports_inspected_before_any_extension_load'] and not build['source_changed'] and
        not build['toolchain_changed'], 'build_not_accepted')
    require(functional['status'] == 'functional_passed_saved18_excluded' and functional['tests'] == 61 and
        not functional['bad_tests'] and not functional['source_changed'] and not functional['toolchain_changed'], 'functional_not_accepted')
    prototype = read(OUT/'c_tree_normalizer_prototype_001/source_plan.json')
    for name in CORE:
        expected = prototype['source_sha256'][name]
        require(sha(ROOT/name) == expected == build['source_before'][name] == build['source_after'][name] ==
            functional['source_before'][name] == functional['source_after'][name], 'reviewed_core_changed:'+name)
        require(sha(BUILD/'source'/name) == expected == sha(FUNCTIONAL/'source'/name), 'core_archive_changed:'+name)
    require(len(ledger) == 18 and set(ledger) == set(campaign['rows']), 'fixed18_ledger')
    # This reads only manifest metadata, not even compressed raw bytes.
    raws = []
    for key in campaign['rows']:
        row = ledger[key]; require(row['status'] == 'raw_saved', 'missing_raw:'+key)
        path = Path(row['raw']['path']).resolve()
        require(path.is_relative_to(PRODUCER) and type(row['raw']['sha256']) is str and len(row['raw']['sha256']) == 64, 'raw_identity')
        raws.append({'key': key, 'path': str(path), 'sha256': row['raw']['sha256']})
    require(len({row['path'] for row in raws}) == 18, 'duplicate_raw')
    runtime = {name: dict(item) for name, item in build['resolved_runtime_identity'].items()}
    # The API-set import resolves to the Windows CRT implementation. Its actual
    # process path is checked after load; pin that installed file now as well.
    ucrt = Path('C:/Windows/System32/ucrtbase.dll')
    runtime['ucrtbase.dll'] = {'path': str(ucrt), 'sha256': sha(ucrt)}
    return build, raws, runtime


def prepare(output):
    started = time.perf_counter_ns(); output.mkdir(parents=True, exist_ok=False)
    build, raws, runtime = metadata()
    files = closure(); before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        dest = output/'source'/name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
    originals = frozen_sources()
    for name, item in runtime.items():
        if 'path' in item: require(sha(item['path']) == item['sha256'], 'runtime_changed:'+name)
    require(sha(build['binary']['path']) == build['binary']['sha256'], 'binary_changed')
    plan = {'schema': 'g31.C_normalizer.fixed18_saved_parity.v1', 'status': 'prepared_not_executed',
        'limit_seconds': LIMIT, 'module': MODULE, 'fixed_input_rows': raws,
        'source_sha256': before, 'original_frozen_sources': originals, 'references': dict(REFS),
        'binary': build['binary'], 'runtime_dependencies': runtime,
        'toolchain_identity': {'build_receipt': str(BUILD/'receipt.json'), 'entries': len(build['toolchain_before']),
                               'required_entry_exit_exact': True},
        'checks': ['all18 full root_records[0], no field/clock exclusion; original16closed2unknown denominator',
            'original Python normalization versus C: exact builtin type, key order, float.hex, scalar value and fresh containers',
            'same complete codec FunctionType code/default/closure, only a private normalizer facade differs; original strict decoder/encoder remain',
            'full original wire bytes and codec bytes equal; full strict decoded tree equal; all input representation bytes unchanged',
            'all169/135 live and source archives, own closure/archive, pyd, runtime,6124toolchain and18 raw hashes at entry and exit',
            'all setup/import/validation/loading/encoding/GC/export/exit retained; first row only decoded after owned admission'],
        'data_only': True, 'native_calls': 0, 'predictor_calls': 0, 'performance_benchmark': False,
        'preparation_raw_reads': 0, 'timing_scope': 'Gate wall is verification cost, not normalizer speed or complete-request100ms evidence.',
        'failure': 'Any source/import/domain/bytes/ownership/error/timeout failure is retained as failed or unknown. No native retry.',
        'ABI_scope': 'CPython3.11.9 non-limited ABI only; recursion_remaining private-field guard; stable private input.'}
    write(output/'plan.json', plan)
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--plan-sha256', sha(output/'plan.json')]
    receipt = {'schema': 'g31.C_normalizer.saved18.preparation.v1', 'plan_sha256': sha(output/'plan.json'),
        'execute_command': command, 'source_count': len(before), 'fixed_rows': 18,
        'preparation_wall_ns': time.perf_counter_ns()-started, 'raw_reads': 0, 'executed': False,
        'requires_external_whole_application_clock': True, 'owned_limit_seconds': LIMIT}
    write(output/'preparation.json', receipt); print(json.dumps(receipt))


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        # Keys in a normalized tree are exact str; their order is significant.
        return list(a) == list(b) and all(exact(a[key], b[key]) for key in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is float: return a.hex() == b.hex()
    return a == b


def containers(value):
    result = set(); count = 0
    def visit(v):
        nonlocal count
        if type(v) in (dict, list, tuple):
            result.add(id(v)); count += 1
            for member in (v.values() if type(v) is dict else v): visit(member)
    visit(value)
    return result, count


def source_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def comparator_controls():
    pairs = [({'a': 1}, {'a': 1.}), ({'a': True}, {'a': 1}), ({'a': -0.}, {'a': 0.}),
        ({'a': [], 'b': 2}, {'b': 2, 'a': []}), ({'a': [1]}, {'a': (1,)}),
        ({'a': 1}, {'a': 1, 'b': None}), ({'a': '🌍'}, {'a': '\ud83c\udf0d'})]
    require(all(not exact(a, b) for a, b in pairs), 'strict_comparator_negative')
    leaf = []; alias = [leaf, leaf]
    ids, occurrences = containers(alias)
    require(len(ids) == 2 and occurrences == 3, 'ownership_comparator_negative')
    require(source_bytes({'a': -0.}) != source_bytes({'a': 0.}) and
        source_bytes({'a': 1}) != source_bytes({'a': 1.}), 'source_bytes_negative')
    return {'type_order_signedzero_tuple_extra_unicode_negatives': 7, 'alias_negative': 1,
            'source_byte_negatives': 2}


def check_row(value, candidate, normalization, codec, candidate_codec):
    require(type(value) is dict and type(value.get('closed')) is bool, 'full_root_shape')
    before_bytes = source_bytes(value)
    expected = normalization.normalize(value)
    actual = candidate.normalize(value)
    require(exact(expected, actual), 'normalizer_type_order_floathex_value')
    source_ids, _ = containers(value); expected_ids, expected_count = containers(expected)
    actual_ids, actual_count = containers(actual)
    require(not (source_ids & expected_ids) and not (source_ids & actual_ids) and
        not (expected_ids & actual_ids) and expected_count == actual_count == len(actual_ids), 'fresh_container_isolation')
    again = candidate.normalize(value); again_ids, again_count = containers(again)
    require(exact(actual, again) and not (again_ids & (source_ids | actual_ids | expected_ids)) and
        again_count == len(again_ids) == actual_count, 'cross_call_isolation')
    full_a, bytes_a = codec.normalize_roundtrip(value)
    full_b, bytes_b = candidate_codec(value)
    require(exact(full_a, expected) and exact(full_b, expected), 'complete_codec_tree')
    wire_bytes = normalization.wire.artifact_encode(expected)
    require(bytes_a == bytes_b == wire_bytes, 'complete_codec_original_bytes')
    decoded = normalization.wire.artifact_decode(bytes_b)
    require(exact(decoded, expected), 'original_strict_decode')
    a_ids, a_count = containers(full_a); b_ids, b_count = containers(full_b)
    require(a_count == b_count == actual_count and not (a_ids & b_ids) and
        not ((a_ids | b_ids) & (source_ids | actual_ids | expected_ids | again_ids)), 'codec_container_isolation')
    require(source_bytes(value) == before_bytes and exact(value, expected), 'input_representation_mutated')
    return {'closed': value['closed'], 'whole_root_fields': list(value), 'container_occurrences': actual_count,
        'encoded_bytes': len(bytes_b), 'encoded_sha256': hashlib.sha256(bytes_b).hexdigest(),
        'input_representation_sha256': hashlib.sha256(before_bytes).hexdigest(),
        'normalizer_exact': True, 'complete_codec_exact': True, 'original_strict_decode_exact': True,
        'fresh_containers': True, 'source_bytes_unchanged': True}


def identities(output, plan, raw):
    references(); require(plan['references'] == REFS, 'reference_domain')
    require(frozen_sources() == plan['original_frozen_sources'], 'frozen_identity')
    for name, digest in plan['source_sha256'].items():
        require(sha(ROOT/name) == digest == sha(output/'source'/name), 'source_changed:'+name)
    files = closure()
    require({k: hashlib.sha256(v).hexdigest() for k, v in files.items()} == plan['source_sha256'], 'closure_domain_changed')
    build = read(BUILD/'receipt.json')
    require(plan['binary'] == build['binary'] and sha(plan['binary']['path']) == plan['binary']['sha256'], 'binary_identity')
    for name, digest in build['toolchain_before'].items(): require(sha(name) == digest, 'toolchain_changed:'+name)
    for name, item in plan['runtime_dependencies'].items():
        if 'path' in item: require(sha(item['path']) == item['sha256'], 'runtime_identity:'+name)
    if raw:
        for item in plan['fixed_input_rows']: require(sha(item['path']) == item['sha256'], 'raw_changed:'+item['key'])
    return {'own_sources': len(plan['source_sha256']), 'original_source_counts': [169, 135],
        'toolchain_files': len(build['toolchain_before']), 'raw_files': 18 if raw else 0, 'binary_sha256': plan['binary']['sha256']}


def loaded_runtime(plan):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,); api.GetModuleHandleW.restype = ctypes.c_void_p
    api.GetModuleFileNameW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint)
    api.GetModuleFileNameW.restype = ctypes.c_uint
    result = {}
    for name, item in plan['runtime_dependencies'].items():
        if 'path' not in item: continue  # API-set name; actual ucrtbase pinned separately
        handle = api.GetModuleHandleW(name); require(handle, 'runtime_not_loaded:'+name)
        buffer = ctypes.create_unicode_buffer(32768)
        length = api.GetModuleFileNameW(handle, buffer, len(buffer)); require(0 < length < len(buffer), 'runtime_path')
        path = Path(buffer.value).resolve()
        require(path == Path(item['path']).resolve() and sha(path) == item['sha256'], 'actual_runtime_mismatch:'+name)
        result[name] = {'path': str(path), 'sha256': item['sha256']}
    return result


def audit(output, expected):
    require(sha(output/'plan.json') == expected, 'plan_changed'); plan = read(output/'plan.json')
    report = {'schema': 'g31.C_normalizer.fixed18_saved_readback.v1', 'status': 'started', 'rows': [],
        'plan_sha256': expected, 'native_calls': 0, 'predictor_calls': 0, 'performance_runs': 0,
        'fixed_denominator': 18, 'complete_request_100ms_claim': False, 'original16closed2unknown_unchanged': False}
    try:
        report['entry_identity'] = identities(output, plan, True)
        report['comparator_controls'] = comparator_controls()
        require(gc.isenabled(), 'default_GC_required'); report['GC_enabled_entry'] = gc.isenabled()
        from . import complete_tree_normalizer_candidate as c
        from . import complete_root_evidence_codec as codec
        source_expected = {str(Path(m.__file__).resolve()): plan['source_sha256'][Path(m.__file__).resolve().relative_to(ROOT).as_posix()]
            for m in (c.original, c.original.wire)}
        candidate = c.load_candidate(plan['binary']['path'], plan['binary']['sha256'], source_expected)
        report['actual_loaded_runtime'] = loaded_runtime(plan)
        original_function = codec.normalize_roundtrip
        namespace = dict(original_function.__globals__)
        namespace['normalization'] = SimpleNamespace(normalize=candidate.normalize)
        candidate_codec = FunctionType(original_function.__code__, namespace, original_function.__name__,
            original_function.__defaults__, original_function.__closure__)
        candidate_codec.__kwdefaults__ = original_function.__kwdefaults__
        require(candidate_codec.__code__ is original_function.__code__ and
            original_function.__globals__['normalization'] is c.original and
            namespace['_check_owned_encoding'] is codec._check_owned_encoding,
            'private_codec_binding')
        report['codec_proof'] = {'same_code_defaults_closure': True,
            'normalizer_provider_only_private_substitution': True, 'original_proof': codec.source_proof(),
            'original_proof_normalization_unchanged_is_reference_only': True}
        for item in plan['fixed_input_rows']:
            with gzip.open(item['path'], 'rt', encoding='utf8') as stream: raw = json.load(stream)
            require(type(raw.get('root_records')) is list and len(raw['root_records']) == 1, 'exact_root_count')
            summary = check_row(raw['root_records'][0], candidate, c.original, codec, candidate_codec)
            report['rows'].append({'key': item['key'], **summary})
            write(output/'progress.json', {'completed': len(report['rows']), 'fixed_total': 18, 'last': item['key']})
            del raw
        counts = {str(closed): sum(r['closed'] is closed for r in report['rows']) for closed in (True, False)}
        require(len(report['rows']) == 18 and counts == {'True': 16, 'False': 2}, 'preserved_root_denominator')
        report['counts'] = {'roots': 18, 'closed': 16, 'unknown': 2}
        report['original16closed2unknown_unchanged'] = True
        report['loaded_project_modules'] = {}
        for name, module in sorted(sys.modules.items()):
            path = getattr(module, '__file__', None)
            if path and Path(path).resolve().is_relative_to(ROOT) and Path(path).suffix == '.py':
                path = Path(path).resolve(); rel = path.relative_to(ROOT).as_posix()
                require(plan['source_sha256'].get(rel) == sha(path), 'unarchived_loaded_source:'+rel)
                report['loaded_project_modules'][name] = {'path': rel, 'sha256': sha(path)}
        require(not any('czr005_circulation' in name for name in sys.modules), 'simulation_import')
        report['GC_enabled_exit'] = gc.isenabled(); require(gc.isenabled(), 'GC_changed')
        report['status'] = 'passed_all18_full_data_parity_no_performance_claim'
    except BaseException as error:
        report['status'] = 'failed_or_unknown'; report['error'] = {'type': type(error).__name__, 'message': str(error)}
        (output/'exception.txt').write_text(traceback.format_exc(), encoding='utf8')
    finally:
        try:
            report['exit_identity'] = identities(output, plan, True)
            require(report.get('entry_identity') == report['exit_identity'], 'identity_entry_exit')
        except BaseException as error:
            report['status'] = 'failed_or_unknown'; report['exit_identity_error'] = str(error)
        report['worker_seconds_including_imports'] = time.monotonic()-BOOT
        write(output/'report.json', report)
    return 0 if report['status'].startswith('passed_') else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--plan-sha256')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(sys.stdin.readline() == args.admission+'\n', 'admission')
        return audit(output, args.plan_sha256)
    with (output/'execution_claim').open('x'): pass
    require(sha(output/'plan.json') == args.plan_sha256, 'plan_before_dispatch')
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--plan-sha256', args.plan_sha256,
        '--worker', '--admission', token]
    with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
        process = bounded.run(command, timeout=LIMIT-(time.monotonic()-BOOT), admission=token,
            stdout=stdout, stderr=stderr, cwd=ROOT)
    record = {'schema': 'g31.C_normalizer.saved18.owned_execution.v1', 'process': process, 'command': command,
        'plan_sha256': args.plan_sha256, 'whole_limit_seconds': LIMIT,
        'launcher_seconds_including_imports': time.monotonic()-BOOT,
        'report_sha256': sha(output/'report.json') if (output/'report.json').is_file() else None}
    write(output/'bounded_execution.json', record); print(json.dumps(record))
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 else 1


if __name__ == '__main__': raise SystemExit(main())
