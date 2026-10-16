"""Saved-only verification of the fixed tail8 diagnostic; never rerun kernels.

The reviewer is the producer's author. This fresh readback is independent of
the producer's result aggregation, not an author-independent review.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET
from . import measure_bridge_saved_kernels as producer
from . import bounded_windows_job

ROOT, OUT = producer.ROOT, producer.OUT
PACKAGE = OUT/'bridge_saved_kernel_cost_prepare_001'
PLAN_SHA = '0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc'
EXTERNAL_SHA = '6b64d7e7311c76fde7e70215df13520170dc8c270fc1651715c92abe9fddad04'
MODULE = 'scripts.experiments.g31_ics_circulation.review_bridge_saved_kernel_cost'
LIMIT = 120.0


def require(condition, reason):
    if not condition:
        raise ValueError('saved_kernel_review:'+reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('saved_kernel_review:nonfinite:'+value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def read(path, limit=2*1024*1024):
    path = Path(path)
    require(path.stat().st_size <= limit, 'metadata_size')
    return loads(path.read_text(encoding='utf8'))


def write(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        stream.write(dumps(value)+'\n')


def exact(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return len(left) == len(right) and all(ka == kb and exact(va, vb)
            for (ka, va), (kb, vb) in zip(left.items(), right.items()))
    if type(left) is list:
        return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
    if type(left) is float:
        require(math.isfinite(left) and math.isfinite(right), 'nonfinite_float')
        return left.hex() == right.hex()
    return left == right


def semantic_view(row):
    if row['endpoint'] != 'advance_to':
        return row
    view, result = dict(row), dict(row['result'])
    wall = result.pop('wall_seconds')
    require(type(wall) in (int, float) and math.isfinite(wall) and wall >= 0, 'native_wall')
    view['result'] = result
    return view


def audit(source_sha):
    require(sha(__file__) == source_sha, 'review_source')
    require(sha(PACKAGE/'plan.json') == PLAN_SHA, 'plan')
    require(sha(PACKAGE/'external_application_wall.json') == EXTERNAL_SHA, 'external_receipt')
    plan = read(PACKAGE/'plan.json')
    producer.verify_pins(PACKAGE, plan)
    require(len(plan['source_sha256']) == 79, 'source_denominator')
    launch = read(PACKAGE/'launch_receipt.json')
    external = read(PACKAGE/'external_application_wall.json')
    report = read(PACKAGE/'result.json')
    require(launch['status'] == 'completed' and launch['error'] is None
            and launch['plan_sha256'] == PLAN_SHA and launch['shared_seconds'] == 120.0, 'launch')
    require(launch['process']['status'] == 'exited' and type(launch['process']['exitcode']) is int
            and launch['process']['exitcode'] == 0
            and launch['process']['windows_job_kill_on_close'] is True
            and launch['process']['child_released_only_after_job_assignment'] is True, 'owned_process')
    expected_command = [sys.executable, '-m', producer.MODULE, '--output', str(PACKAGE),
                        '--worker', '--plan-sha256', PLAN_SHA]
    require(launch['command'] == expected_command, 'worker_command')
    require(external['status'] == 'application_exited_zero' and type(external['exit_code']) is int
            and external['exit_code'] == 0 and external['evidence_unchanged'] is True
            and external['plan_sha256'] == PLAN_SHA
            and type(external['whole_python_application_seconds']) in (int, float)
            and 0 < external['whole_python_application_seconds'] <= 120
            and external['whole_python_within_120_seconds'] is True, 'external_wall')
    require(external['python_sha256'] == plan['interpreter']['sha256'], 'external_interpreter')
    require(external['fixed_inputs'] == 16 and external['comparison_calls'] == 32
            and external['copy_calls'] == 64 and external['native_calls'] == 0
            and external['policy_replay_calls'] == 0, 'external_counts')
    for name, digest in launch['artifacts'].items():
        require(name in ('result.json', 'measurements.jsonl', 'stdout.log', 'stderr.log')
                and sha(PACKAGE/name) == digest, 'producer_artifact')
    require(set(launch['artifacts']) == {'result.json', 'measurements.jsonl', 'stdout.log', 'stderr.log'}, 'artifact_domain')
    require((PACKAGE/'stdout.log').stat().st_size == (PACKAGE/'stderr.log').stat().st_size == 0, 'producer_logs')
    require(not (PACKAGE/'worker_failure.json').exists(), 'failure_retained')
    require(report['status'] == 'passed_fixed_saved_kernel_diagnostic_only'
            and report['plan_sha256'] == PLAN_SHA and report['source_changed'] == []
            and report['native_calls'] == report['policy_replays'] == 0
            and report['whole_audit_accepted'] is False
            and report['same_endpoint_native_speedup_certified'] is False, 'producer_scope')
    journal = (PACKAGE/'measurements.jsonl').read_bytes()
    lines = journal.splitlines(keepends=True)
    require(len(lines) == 96 and all(x.endswith(b'\n') for x in lines), 'complete_journal')
    records = [loads(x.decode('utf8')) for x in lines]
    require(exact(records, report['records']), 'record_report_exact')

    # Independently read the 16 pinned bytes, once. No measure(), json_copy(),
    # c_compare(), deepcopy() or producer comparison kernel is called here.
    rows, result_hashes, input_rows = [], {}, []
    for entry in plan['files']:
        path = PACKAGE/'fixtures'/entry['file']
        blob = path.read_bytes()
        require(len(blob) == entry['bytes'] and hashlib.sha256(blob).hexdigest() == entry['sha256'], 'fixture_bytes')
        with gzip.open(path, 'rb') as stream:
            text = stream.read(64*1024*1024+1)
        require(len(text) <= 64*1024*1024, 'fixed_row_decode_bound')
        row = loads(text.decode('utf8'))
        producer.decoded_tree(row)
        require(type(row['ordinal']) is int and row['ordinal'] == entry['ordinal']
                and row['endpoint'] == entry['endpoint'] and 'result' in row and 'error' not in row, 'fixture_identity')
        digest = hashlib.sha256(dumps(row['result']).encode('utf8')).hexdigest()
        result_hashes[(entry['side'], entry['ordinal'])] = digest
        rows.append(row)
        input_rows.append({'side': entry['side'], 'ordinal': entry['ordinal'], 'endpoint': entry['endpoint'],
            'gzip_sha256': entry['sha256'], 'gzip_bytes': len(blob), 'decoded_utf8_bytes': len(text),
            'result_canonical_sha256': digest})
    require(len(rows) == 16 and all(exact(semantic_view(a), semantic_view(b))
                                  for a, b in zip(rows[:8], rows[8:], strict=True)), 'independent_actual_pair')

    expected = [(kind, batch, arm, index) for kind, count in (('compare', 8), ('copy', 16))
                for batch, arm in enumerate(('A', 'B', 'B', 'A')) for index in range(count)]
    require([(r['kind'], r['batch'], r['arm'], r['index']) for r in records] == expected, '96_order')
    previous = -1
    for record in records:
        require(all(type(record[k]) is int and record[k] >= 0
                    for k in ('batch', 'index', 'ordinal', 'started_ns', 'finished_ns', 'wall_ns', 'cpu_ns')), 'typed_clock_identity')
        require(record['ordinal'] == 27210 + record['index'] % 8, 'ordinal')
        require(previous <= record['started_ns'] <= record['finished_ns']
                and record['wall_ns'] == record['finished_ns'] - record['started_ns'], 'clock_order')
        previous = record['finished_ns']
        common = {'kind', 'batch', 'arm', 'index', 'ordinal', 'side', 'started_ns', 'finished_ns', 'wall_ns', 'cpu_ns'}
        if record['kind'] == 'compare':
            require(set(record) == common | {'equal'} and record['side'] is None and record['equal'] is True, 'compare_record')
        else:
            side = 'old' if record['index'] < 8 else 'new'
            require(set(record) == common | {'result_sha256'} and record['side'] == side
                    and record['result_sha256'] == result_hashes[(side, record['ordinal'])], 'copy_record_hash')
    summary = {}
    for kind in ('compare', 'copy'):
        summary[kind] = {}
        for arm in ('A', 'B'):
            batches = [sum(r['wall_ns'] for r in records if r['kind'] == kind and r['batch'] == batch)/1e6
                       for batch, selected in enumerate(('A', 'B', 'B', 'A')) if selected == arm]
            summary[kind][arm] = {'batch_ms': batches, 'median_batch_ms': statistics.median(batches)}
    require(exact(summary, report['summary']), 'recomputed_summary')
    xml = ET.parse(plan['pure']['xml'])
    counts = {key: sum(int(s.get(key, 0)) for s in xml.getroot().iter('testsuite'))
              for key in ('tests', 'failures', 'errors', 'skipped')}
    require(counts == {'tests': 39, 'failures': 0, 'errors': 0, 'skipped': 0}, 'pure_xml')
    legal = read(PACKAGE/'independent_source_review_legal_001.json')
    require(legal['status'] == 'no_concrete_source_semantics_blocker'
            and legal['plan']['sha256'] == PLAN_SHA, 'independent_source_review')
    producer.verify_pins(PACKAGE, plan)
    loaded = {str(Path(m.__file__).resolve().relative_to(ROOT)) for m in list(sys.modules.values())
              if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
              and Path(m.__file__).resolve().is_relative_to(ROOT)}
    require(loaded <= set(plan['source_sha256']) | {str(Path(__file__).resolve().relative_to(ROOT))}, 'loaded_closure')
    require(sha(__file__) == source_sha, 'reviewer_source_drift')
    artifacts = ['plan.json', 'result.json', 'measurements.jsonl', 'launch_receipt.json',
                 'external_application_wall.json', 'independent_source_review_legal_001.json']
    return {'schema': 'g31.bridge.fixed_kernel_saved_readback.v1', 'status': 'passed_saved_readback',
        'reviewer_role': 'Producer author performing a new saved-only recheck; not an author-independent certification.',
        'author_independent_source_review': {'path': str(PACKAGE/'independent_source_review_legal_001.json'),
            'sha256': sha(PACKAGE/'independent_source_review_legal_001.json')},
        'artifacts': {name: sha(PACKAGE/name) for name in artifacts}, 'source_count': 79,
        'source_current_and_archive_exact': True, 'loaded_sources': sorted(loaded), 'pure_counts': counts,
        'counts': {'input_files': 16, 'ordered_pairs': 8, 'measurement_rows': 96, 'compares': 32, 'copies': 64},
        'input_rows': input_rows, 'summary': summary,
        'median_reduction_percent': {kind: 100*(1-summary[kind]['B']['median_batch_ms']/summary[kind]['A']['median_batch_ms'])
                                     for kind in ('compare', 'copy')},
        'original_whole_python_seconds': external['whole_python_application_seconds'],
        'original_load_decode_domain_ms': report['load_decode_domain_ns']/1e6,
        'original_worker_before_final_export_ms': report['before_final_export_ns']/1e6,
        'new_native_calls': 0, 'new_kernel_measurements': 0, 'new_policy_replays': 0,
        'full_bridge_audit_accepted': False, 'recommendation': 'Prepare a versioned original-C-comparator-only audit candidate; retain actor deepcopy. Do not rerun the full audit without a separate cost decision.',
        'limitations': ['Fixed eight paired tail rows, two batches per arm; no general or full-audit speed guarantee.',
            'Saved copy objects do not exist. Digest equality is rechecked; successful-path alias separation remains producer runtime evidence plus pinned source/pure tests, not newly reconstructed alias identities.',
            'Worker process CPU and wall are distinct. The saved timings do not isolate source read, deepcopy or whole policy replay cost.',
            'Original bridge timeouts and unclosed full acceptance remain unchanged.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        require(sys.stdin.readline().rstrip('\n') == args.source_sha256, 'owned_admission')
        try:
            result = audit(args.source_sha256)
            write(output/'report.json', result)
        except BaseException as error:
            write(output/'failure.json', {'status': 'unknown_failed', 'error': repr(error), 'elapsed_seconds': time.perf_counter()-BOOT})
            raise
        return 0
    require(not output.exists(), 'preserve_output')
    output.mkdir()
    source_sha = sha(__file__)
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--source-sha256', source_sha]
    with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
        process = bounded_windows_job.run(command, timeout=LIMIT-(time.perf_counter()-BOOT),
            stdout=stdout, stderr=stderr, admission=source_sha, cwd=ROOT)
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and (output/'report.json').exists()
    write(output/'bounded_execution.json', {'status': 'completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'shared_seconds': LIMIT,
        'source': {'path': str(Path(__file__).resolve()), 'sha256': source_sha},
        'after_import_before_final_receipt_seconds': time.perf_counter()-BOOT,
        'report': {'path': str(output/'report.json'), 'sha256': sha(output/'report.json')} if (output/'report.json').exists() else None,
        'external_launch_through_exit_clock_required': True, 'new_native_calls': 0, 'new_measurements': 0})
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
