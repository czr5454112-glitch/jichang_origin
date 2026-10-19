"""Independent saved-only Cpublisher72 review; never loads the C extension.

Original identity guards are reused. Record equality, clocks and statistics are
recomputed here. Direct builtin support/container isolation remain source-bound
producer runtime observations, not independently repeated calls.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import traceback
import xml.etree.ElementTree as ET

from . import bounded_windows_job
from . import measure_complete_root_c_normalizer as m

ROOT, OUT = m.ROOT, m.OUT
PRODUCER = OUT/'C_publisher_pair_prepare_001'
WRAPPER = OUT/'user_resume_20261015_001/invoke_C_publisher_root_001_measured.ps1'
PURE = OUT/'C_publisher_saved_review_pure_001'
MODULE = 'scripts.experiments.g31_ics_circulation.review_complete_root_c_publisher_saved'
TEST = 'tests/test_g31_circulation_C_publisher_saved_review.py'
LIMIT = 120.
SCHEMA = 'g31.C_publisher.saved_independent_review.v1'
FIXED = {
    'plan.json': '840329a5c7eaf928f92b7c6d9a4bbfaf08bdf12260141e41f2863746e2df4072',
    'report.json': '19f4c29ce1f5ffa1897a3ccab62b3e1d522714c873adb5819f0863f902624f01',
    'receipt.json': '693a2f8bce7860fe6ef7cdadc1428f0b6dce4a219806c5a8b7750d884262a3e3',
    'external_application_wall.json': 'b0f515ce77c809c182435bbe8946783fc99a9f6c56cfb9db7811ddf653a59047',
}
sha, read, write = m.sha, m.read, m.write


def require(value, reason):
    if not value: raise ValueError('C_publisher_saved_review:'+reason)


def reference(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}
def exact(a, b): return m.parity.exact(a, b)


def finite(value): return type(value) in (int, float) and math.isfinite(value) and value >= 0


def remaining(elapsed):
    require(finite(elapsed), 'elapsed')
    result = LIMIT-elapsed-1.
    if result <= 0: raise TimeoutError('C_publisher_saved_review:budget_before_worker')
    return result


def no_execution_modules():
    require('_g31_complete_tree_normalizer' not in sys.modules and
        not any('czr005_circulation' in name for name in sys.modules), 'forbidden_extension_loaded')


def row_clock(row, previous=None):
    for key in ('started_ns', 'finished_ns', 'elapsed_ns', 'gzip_hash_elapsed_ns'):
        require(type(row[key]) is int and row[key] >= 0, 'exact_nonnegative_clock:'+key)
    require(row['finished_ns'] >= row['started_ns'] and
        row['elapsed_ns'] == row['finished_ns']-row['started_ns'], 'sample_elapsed')
    if previous is not None:
        require(row['started_ns'] >= previous['finished_ns']+previous['gzip_hash_elapsed_ns'],
                'sample_and_export_chronology')


def compare_record(record, fixture, row):
    m.mock.current_clock_bounds(record, row['started_ns'], row['finished_ns'])
    require(exact(m.mock.semantic_record(record), m.mock.semantic_record(fixture)), 'complete_semantics_changed')


def summarize(samples, keys):
    require(len(samples) == 72 and len(keys) == 18 and len(set(keys)) == 18, 'statistics_denominator')
    declaration = [{'key': key, 'arm': arm, 'position': i} for key in keys for i, arm in enumerate('ABBA')]
    require(all(exact({k: row[k] for k in ('key', 'arm', 'position')}, expected)
        for row, expected in zip(samples, declaration, strict=True)), 'statistics_ABBA_order')
    values = {arm: [r['elapsed_ms'] for r in samples if r['arm'] == arm] for arm in ('A', 'B')}
    require(all(len(v) == 36 and all(finite(x) for x in v) for v in values.values()), 'statistics_values')
    summary = {arm: {'count': len(v), 'min': min(v), 'median': statistics.median(v), 'max': max(v), 'sum': sum(v)}
        for arm, v in values.items()}
    pairs = {key: {arm: statistics.median([r['elapsed_ms'] for r in samples if r['key'] == key and r['arm'] == arm])
        for arm in ('A', 'B')} for key in keys}
    negative = [key for key, v in pairs.items() if v['B'] >= v['A']]
    return {'summary_ms': summary, 'per_root_median_ms': pairs, 'negative_or_equal_root_medians': negative}


def metadata_check(plan, receipt, report, outer, bounded):
    require(receipt['status'] == 'completed_fixed_entry_codec_C_mock_ABBA' and receipt['source_changed'] == [] and
        receipt['plan_sha256'] == FIXED['plan.json'] and receipt['native_calls'] == receipt['predictor_calls'] == 0 and
        receipt['GC_enabled'] is True, 'producer_terminal')
    require(report['status'] == 'passed_exact_complete_entry_codec18_C_normalizer_ABBA72' and
        report['GC_enabled_entry'] is report['GC_enabled_exit'] is True and report['native_calls'] == report['predictor_calls'] == 0 and
        report['complete_native_root_100ms_certified'] is False and report['direct_C_supported'] == 18, 'producer_report_scope')
    process = bounded['process']
    require(process['status'] == 'exited' and type(process['exitcode']) is int and process['exitcode'] == 0 and
        type(process['pid']) is int and process['pid'] > 0 and process['windows_job_kill_on_close'] is True and
        process['child_released_only_after_job_assignment'] is True, 'producer_owned_process')
    for value in (process['wall_seconds'], process['hard_timeout_seconds'], bounded['launcher_seconds_including_imports'],
                  receipt['worker_seconds_before_receipt'], outer['whole_python_application_seconds'],
                  report['fixture_load_binding_and_full_support_preflight_ms']):
        require(finite(value), 'producer_wall_field')
    require(receipt['worker_seconds_before_receipt'] <= process['wall_seconds'] <=
        bounded['launcher_seconds_including_imports'] <= outer['whole_python_application_seconds'] <= 240 and
        process['wall_seconds'] <= process['hard_timeout_seconds'] <= 240 and bounded['shared_limit_seconds'] == 240 and
        bounded['native_calls'] == bounded['predictor_calls'] == 0, 'producer_shared_wall')
    require(outer['status'] == 'application_exited_zero' and type(outer['exit_code']) is int and outer['exit_code'] == 0 and
        outer['error'] is None and outer['evidence_unchanged'] is True and outer['whole_python_within_240_seconds'] is True and
        outer['shared_owned_seconds'] == 240 and outer['plan_sha256'] == FIXED['plan.json'] and
        outer['python_sha256'] == plan['environment']['sha256'] and outer['fixed_inputs'] == 18 and
        outer['publisher_calls'] == 72 and outer['required_direct_C_supported'] == 18 and
        outer['model_calls'] == outer['native_simulation_calls'] == 0 and
        outer['complete_native_request_100ms_certified'] is False, 'producer_external')
    require(outer['wrapper_sha256'] == sha(WRAPPER) == 'b3f41cecc228bf5de11641844651f8bd2b6433e467aaae58e7078746e11a27a2',
            'producer_external_wrapper_identity')
    expected_command = [plan['environment']['python'], '-m', m.MODULE, '--worker', '--output', str(PRODUCER),
        '--plan-sha256', FIXED['plan.json']]
    require(bounded['command'] == expected_command, 'producer_worker_command')
    for obj, key, name in ((receipt, 'report', 'report.json'), (bounded, 'report', 'report.json'),
                           (receipt, 'direct_support', 'direct_support.json'), (report, 'direct_support', 'direct_support.json')):
        require(obj[key] == reference(PRODUCER/name), 'producer_output_reference')
    entry, exit = receipt['loaded_project_sources_entry'], receipt['loaded_project_sources_exit']
    require(len(entry) == 99 and len(exit) == 100 and all(exit.get(k) == v for k, v in entry.items()),
            'loaded_entry_exit')
    require(set(exit)-set(entry) == {'_g31_complete_tree_normalizer'}, 'loaded_extension_delta')
    for name, item in exit.items():
        path = Path(item['path']).resolve()
        if path.suffix == '.py': require(plan['source_sha256'].get(str(path)) == item['sha256'], 'loaded_source_identity:'+name)
        else: require(name == '_g31_complete_tree_normalizer' and str(path) == plan['binary']['path'] and
            item['sha256'] == plan['binary']['sha256'], 'loaded_binary_identity')
    runtime = report['actual_runtime']
    expected_runtime = {name: item for name, item in plan['runtime_dependencies'].items() if 'path' in item}
    require(set(runtime) == set(expected_runtime), 'runtime_denominator')
    for name, item in runtime.items():
        expected = expected_runtime[name]
        require(Path(item['path']).resolve() == Path(expected['path']).resolve() and item['sha256'] == expected['sha256'],
                'runtime_saved_identity:'+name)


def check_support(data, keys):
    require(type(data) is dict and list(data) == list(keys), 'direct_support_denominator')
    for item in data.values():
        require(tuple(item) == ('direct_C_supported', 'exact_and_new_owned_tree', 'raw_normalization_bytes_sha256', 'containers') and
            item['direct_C_supported'] is item['exact_and_new_owned_tree'] is True and type(item['containers']) is int and
            item['containers'] > 0 and type(item['raw_normalization_bytes_sha256']) is str and
            len(item['raw_normalization_bytes_sha256']) == 64 and
            all(c in '0123456789abcdef' for c in item['raw_normalization_bytes_sha256']), 'direct_support_record')


def own_sources():
    files = m.image.source_closure(ROOT, (MODULE, TEST[:-3].replace('/', '.')))
    # Producer-only C source and its focused tests are part of the original145
    # closure even though the audit never loads that binary.
    for path, digest in read(PRODUCER/'plan.json')['source_sha256'].items():
        data = Path(path).read_bytes(); require(hashlib.sha256(data).hexdigest() == digest, 'producer_source_prepare')
        files[str(Path(path).relative_to(ROOT))] = data
    return dict(sorted(files.items()))


def pure_gate():
    receipt, plan = read(PURE/'receipt.json'), read(PURE/'plan.json')
    require(receipt['status'] == 'passed_process' and receipt['source_changed'] == [] and
        receipt['native_calls'] == receipt['model_predictions'] == 0 and
        receipt['plan_sha256'] == sha(PURE/'plan.json'), 'pure_receipt')
    cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 14 and not any(c.tag in ('failure', 'error', 'skipped') for case in cases for c in case), 'pure14')
    for path, digest in plan['source_sha256'].items():
        require(sha(path) == digest == sha(PURE/'source'/Path(path).relative_to(ROOT)), 'pure_tested_source')
    return [PURE/name for name in ('plan.json', 'receipt.json', 'tests.xml')]


def prepare(output):
    no_execution_modules(); pure_paths = pure_gate(); output.mkdir(exist_ok=False)
    for name, digest in FIXED.items(): require(sha(PRODUCER/name) == digest, 'fixed_metadata:'+name)
    producer = read(PRODUCER/'plan.json'); ledger = read(PRODUCER/'ledger.json')
    require(len(producer['source_sha256']) == 145 and len(producer['input_raw']) == 18 and len(ledger) == 72, 'prepare_metadata_counts')
    files = own_sources(); sources = {}; archives = {}
    for relative, data in files.items():
        destination = output/'source'/relative; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(data)
        path = str(ROOT/relative); sources[path] = hashlib.sha256(data).hexdigest(); archives[path] = str(destination.relative_to(output))
    metadata = {str(PRODUCER/name): sha(PRODUCER/name) for name in (*FIXED, 'bounded_execution.json', 'ledger.json',
        'direct_support.json', 'preparation.json')}
    metadata[str(WRAPPER)] = sha(WRAPPER)
    metadata.update({str(path): sha(path) for path in pure_paths})
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'source_sha256': sources, 'source_archive': archives,
        'producer_metadata_sha256': metadata, 'producer_source_count': 145,
        'focused_pure_tests': 14, 'focused_pure_XML': reference(PURE/'tests.xml'),
        'historical_original_source_counts': [169, 135], 'toolchain_files': 6124,
        'input_raw': producer['input_raw'], 'published_raw': [r['raw'] for r in ledger],
        'row_order': producer['row_order'], 'hard_application_seconds': LIMIT,
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'source_guards': 'Original m.verify_pins at entry and exit; no m.worker/load_candidate/bind/direct_support/publish/model/native call.',
        'independent_checks': ['72 exact ABBA complete records against18 complete original root fixtures',
            'Every original event/root/deadline field preserved; only existing mock.semantic_record clock exclusions, each regenerated clock/formula independently checked',
            '36 samples perarm,18 paired medians including every negative/equal case,72 export clocks',
            'Producer loaded99→100 identities/runtime/GC/whole wall/owned process and explicit no100ms boundary',
            'Own source archives/loaded entryexit and all original pins rechecked; any failure remains unknown'],
        'direct_support_limit': '18 builtin support and owned-container checks are producer runtime declarations verified for saved shape/source linkage only; not independently re-executed.',
        'cost_basis': {'producer_whole_seconds': 76.6456392, 'producer_preflight_ms': 11960.1658,
            'producer_sample_ms_total': 12403.5928,
            'explanation': 'Audit omits extension loading,18 preflight publishers and72 measured publishers; it retains all pinning and18+72 decode/full-record comparisons.120 is a fixed failure bound, not a runtime guarantee.'},
        'preparation_raw_reads': 0, 'C_extension_loads': 0, 'native_calls': 0, 'predictor_calls': 0, 'performance_runs': 0}
    write(output/'plan.json', plan)
    write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': reference(output/'plan.json'),
        'source_count': len(sources), 'preparation_raw_reads': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--expected-plan', sha(output/'plan.json')]})


def check_own_pins(output, plan):
    values = {}
    for p, digest in plan['source_sha256'].items():
        values[p] = sha(p); values[str(output/plan['source_archive'][p])] = sha(output/plan['source_archive'][p])
        require(values[p] == digest == values[str(output/plan['source_archive'][p])], 'auditor_source_drift')
    for p, digest in plan['producer_metadata_sha256'].items(): values[p] = sha(p); require(values[p] == digest, 'producer_metadata_drift')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'auditor_interpreter')
    return values


def loaded_own(plan):
    no_execution_modules(); result = {}
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, '__file__', None)
        if not file: continue
        path = Path(file).resolve()
        if not path.is_relative_to(ROOT): continue
        require(path.suffix == '.py' and plan['source_sha256'].get(str(path)) == sha(path), 'auditor_loaded:'+name)
        result[name] = {'path': str(path), 'sha256': sha(path)}
    return result


def worker(output, expected):
    require(sha(output/'plan.json') == expected, 'review_plan'); plan = read(output/'plan.json')
    require(plan['schema'] == SCHEMA and plan['hard_application_seconds'] == LIMIT, 'review_scope')
    entry = check_own_pins(output, plan); write(output/'entry_pins.json', entry)
    loaded_entry = loaded_own(plan); write(output/'loaded_sources_entry.json', loaded_entry)
    started = time.perf_counter(); producer = m.verify_pins(PRODUCER, FIXED['plan.json'])
    require(plan['input_raw'] == producer['input_raw'] and plan['row_order'] == producer['row_order'] and
        len(producer['source_sha256']) == 145, 'review_producer_binding')
    receipt, report, outer, bounded = [read(PRODUCER/name) for name in ('receipt.json', 'report.json',
        'external_application_wall.json', 'bounded_execution.json')]
    metadata_check(producer, receipt, report, outer, bounded)
    support = read(PRODUCER/'direct_support.json'); check_support(support, producer['input_raw'])
    inputs = m.load_inputs(producer); ledger = read(PRODUCER/'ledger.json'); require(len(ledger) == 72, 'saved72')
    samples = []; audits = []; previous = None
    for index, (row, declaration) in enumerate(zip(ledger, producer['row_order'], strict=True)):
        require(tuple(row) == ('key', 'arm', 'position', 'status', 'started_ns', 'finished_ns', 'elapsed_ns',
            'raw', 'gzip_hash_elapsed_ns') and row['status'] == 'saved' and
            exact({key: row[key] for key in declaration}, declaration), 'saved_declaration')
        path = PRODUCER/'raw'/f'{index:03d}.json.gz'
        require(row['raw'] == plan['published_raw'][index] == reference(path), 'published_raw_identity')
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            data = json.load(stream, object_pairs_hook=m.image._pairs, parse_constant=m.image._constant)
        require(type(data) is dict and tuple(data) == ('declaration', 'record') and
            exact(data['declaration'], declaration), 'saved_raw_topology')
        row_clock(row, previous); compare_record(data['record'], inputs[row['key']], row)
        samples.append({**declaration, 'elapsed_ms': row['elapsed_ns']/1e6,
            'gzip_and_hash_ms': row['gzip_hash_elapsed_ns']/1e6, 'raw': row['raw']})
        audits.append({'index': index, **declaration, 'status': 'complete_saved_record_equal',
            'source_fixture': producer['input_raw'][row['key']], 'published_raw': row['raw'],
            'all_historical_event_and_deadline_fields_preserved': True, 'regenerated_clocks_checked': True})
        previous = row
        write(output/'row_progress.json', {'completed': len(audits), 'remaining_unknown': 72-len(audits), 'rows': audits})
    computed = summarize(samples, list(inputs))
    require(exact(samples, report['samples']), 'reported_samples')
    for key, value in computed.items(): require(exact(value, report[key]), 'reported_statistic:'+key)
    exports = [r['gzip_hash_elapsed_ns'] for r in ledger]
    closed = sum(r['closed'] is True for r in inputs.values())
    require(closed == 16 and len(inputs)-closed == 2, 'historical16closed2unknown')
    pins_end = m.verify_pins(PRODUCER, FIXED['plan.json']); require(exact(pins_end, producer), 'producer_end_pins')
    exit_pins = check_own_pins(output, plan); write(output/'exit_pins.json', exit_pins)
    require(exit_pins == entry, 'review_exit_pins')
    loaded_exit = loaded_own(plan); write(output/'loaded_sources_exit.json', loaded_exit)
    require(all(loaded_exit.get(k) == v for k, v in loaded_entry.items()), 'review_loaded_changed')
    result = {'schema': SCHEMA, 'status': 'passed_independent_saved72_complete_record_review',
        'producer_plan': reference(PRODUCER/'plan.json'), 'producer_report': reference(PRODUCER/'report.json'),
        'producer_receipt': reference(PRODUCER/'receipt.json'), 'producer_outer': reference(PRODUCER/'external_application_wall.json'),
        'producer_bounded': reference(PRODUCER/'bounded_execution.json'),
        'rows': audits, 'samples': samples, **computed, 'fixed_inputs': 18, 'historical_closed': 16, 'historical_unknown': 2,
        'export_clock_ns': {'count': len(exports), 'min': min(exports), 'median': statistics.median(exports),
                            'max': max(exports), 'sum': sum(exports)},
        'all_original_guards_retained': True, 'producer_source_count': 145, 'original_source_counts': [169, 135],
        'toolchain_files': 6124, 'producer_loaded_entry_count': 99, 'producer_loaded_exit_count': 100,
        'producer_GC_entry_exit_recorded_enabled': True, 'producer_whole_seconds': outer['whole_python_application_seconds'],
        'direct_support': {'rows': 18, 'saved_declarations_valid': True,
            'independent_builtin_calls': 0, 'independent_container_alias_reproof': False,
            'scope': 'Source-bound producer runtime declarations only; saved complete-output equality independently checked.'},
        'entry_pins': reference(output/'entry_pins.json'), 'exit_pins': reference(output/'exit_pins.json'),
        'loaded_sources_entry': reference(output/'loaded_sources_entry.json'), 'loaded_sources_exit': reference(output/'loaded_sources_exit.json'),
        'source_changed': [], 'audit_worker_seconds': time.perf_counter()-started,
        'C_extension_loads': 0, 'native_calls': 0, 'predictor_calls': 0, 'performance_runs': 0,
        'new_native_request_100ms_certified': False, 'business_effect_certified': False}
    write(output/'report.json', result)
    write(output/'receipt.json', {'status': 'saved_review_passed', 'plan': reference(output/'plan.json'),
        'report': reference(output/'report.json'), 'source_changed': [], 'C_extension_loads': 0,
        'native_calls': 0, 'predictor_calls': 0, 'performance_runs': 0})


def execute(output, expected):
    require(sha(output/'plan.json') == expected, 'launch_plan')
    with (output/'execution_claim').open('x'): pass
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', expected]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        elapsed = time.monotonic()-BOOT
        process = bounded_windows_job.run(command, timeout=remaining(elapsed), stdout=stdout, stderr=stderr,
            admission=expected, cwd=str(ROOT))
    wall = time.monotonic()-BOOT; passed = process['status'] == 'exited' and process['exitcode'] == 0 and wall <= LIMIT
    write(output/'bounded_execution.json', {'status': 'bounded_worker_completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'hard_application_seconds': LIMIT, 'parent_before_worker_seconds': elapsed,
        'whole_python_before_final_receipt_seconds': wall, 'external_launch_to_exit_required': True,
        'receipt': reference(output/'receipt.json') if (output/'receipt.json').exists() else None,
        'source_review_not_inferred_from_exit_code': True})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--expected-plan')
    args = parser.parse_args(); output = args.output.resolve(); no_execution_modules()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline() == args.expected_plan+'\n', 'owned_admission')
        try: worker(output, args.expected_plan)
        except BaseException:
            write(output/'failure.json', {'status': 'unknown_saved_review_failure', 'error': traceback.format_exc(),
                'C_extension_loads': 0, 'native_calls': 0, 'predictor_calls': 0}); raise
        return 0
    require(args.execute, 'explicit_execute'); return execute(output, args.expected_plan)


if __name__ == '__main__': raise SystemExit(main())
