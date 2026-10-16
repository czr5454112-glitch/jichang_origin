"""Fixed tail8 saved-audit cost diagnostic; never a policy/native replay.

Only a bounded, already-declared16-file excerpt is read. No raw_final input,
manifest repair, full saved acceptance or replacement of a verifier occurs.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
from types import FunctionType
import xml.etree.ElementTree as ET
from . import bridge_saved_linear_core as linear
from . import bounded_windows_job

base = linear.base
old = linear.original
ROOT, OUT = base.ROOT, base.OUT
MODULE = 'scripts.experiments.g31_ics_circulation.measure_bridge_saved_kernels'
SCHEMA = 'g31.bridge.saved_kernel_cost.fixed_tail8.v1'
LIMIT = 120.0
PURE_TESTS = 39
ORDINALS = tuple(range(27210, 27218))
ARMS = ('A', 'B', 'B', 'A')
OLD_CASE = OUT/'original_cooperative_bridge_prepare_001/bridge'
NEW_CASE = OUT/'original_bridge_serialize_once_prepare_001/bridge'
REVIEW = OUT/'bridge001_terminal_partial_review_001/review.json'
REVIEW_SHA = '0bd6bf3faf488b1fb0e488c6bf2c7f31d1c1e3419d707461bfe6df0bc4c3cbc2'


def require(ok, reason):
    if not ok:
        raise ValueError('bridge_kernel_cost:'+reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def strict_loads(text):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate_json_key')
            out[key] = value
        return out
    def bad_constant(value):
        raise ValueError('bridge_kernel_cost:nonfinite_json:'+value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)


def decoded_tree(value, seen=None):
    """Domain proof performed at load, not hidden inside either timed kernel.

    JSON-decoded trees have no shared mutable containers. Rejecting anything
    else is required before treating JSON reconstruction as a copy comparator.
    """
    seen = set() if seen is None else seen
    kind = type(value)
    require(kind in (dict, list, str, int, float, bool, type(None)), 'not_decoded_builtin')
    if kind in (dict, list):
        require(id(value) not in seen, 'mutable_alias_or_cycle')
        seen.add(id(value))
        if kind is dict:
            for key, child in value.items():
                require(type(key) is str, 'non_string_key')
                decoded_tree(key, seen)
                decoded_tree(child, seen)
        else:
            for child in value:
                decoded_tree(child, seen)
    elif kind is str:
        require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'surrogate_not_utf8_domain')
    elif kind is float:
        require(math.isfinite(value), 'nonfinite_value')
    elif kind is int:
        str(value)  # retain the interpreter's integer conversion bound
    return seen


def exact(a, b):
    """Independent typed/order oracle; no Python bool/int/float equality leak."""
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return len(a) == len(b) and all(ka == kb and exact(va, vb)
            for (ka, va), (kb, vb) in zip(a.items(), b.items()))
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is float:
        require(math.isfinite(a) and math.isfinite(b), 'oracle_nonfinite')
        return a.hex() == b.hex()
    return a == b


def json_copy(value):
    # Input is proved once to be the private, unmutated decoded domain above.
    # The complete C encoder and strict decoder are both in this timed call.
    return strict_loads(encoded(value))


def c_compare(a, b):
    return old.semantic_api(a) == old.semantic_api(b)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        stream.write(encoded(value)+'\n')


def source_paths():
    result = set()
    for entry in (Path(__file__), ROOT/'tests/test_g31_circulation_bridge_saved_kernels.py'):
        fn = FunctionType(base.source_paths.__code__, {**base.source_paths.__globals__, '__file__': str(entry)},
                          base.source_paths.__name__, base.source_paths.__defaults__, base.source_paths.__closure__)
        result.update(fn())
    return sorted(result)


def manifest_entries(path, expected_count):
    # Small metadata only. The unmanifested old027218 row is never opened.
    lines = path.read_bytes().splitlines(keepends=True)
    require(len(lines) == expected_count and all(x.endswith(b'\n') for x in lines), 'manifest_complete_domain')
    selected = {}
    for i, line in enumerate(lines):
        row = strict_loads(line.decode('utf8'))
        require(row['path'] == f'{i:06d}.json.gz', 'manifest_order')
        if i in ORDINALS:
            selected[i] = row
    require(tuple(selected) == ORDINALS, 'manifest_selection')
    return selected


def prepare(output, xml, pure_receipt):
    require(not output.exists(), 'preserve_output')
    require(sha(REVIEW) == REVIEW_SHA, 'historical_selection')
    review = strict_loads(REVIEW.read_text(encoding='utf8'))
    old_rows = review['complete_tail_rows_individually_hashed_and_decoded']
    require([r['ordinal'] for r in old_rows] == list(ORDINALS), 'selection_order')
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    require(counts == {'tests': PURE_TESTS, 'failures': 0, 'errors': 0, 'skipped': 0}, 'pure_counts')
    pure = strict_loads(pure_receipt.read_text(encoding='utf8'))
    require(pure['exitcode'] == 0 and pure['native_calls'] == pure['performance_runs'] == 0, 'pure_receipt')
    manifests = []
    for case, count in ((OLD_CASE, 27218), (NEW_CASE, 37270)):
        path = case/'api/manifest.jsonl'
        manifests.append((path, manifest_entries(path, count), count))
    output.mkdir(); (output/'fixtures').mkdir()
    files = []
    for side, (manifest, entries, count) in zip(('old', 'new'), manifests, strict=True):
        for i in ORDINALS:
            item = entries[i]; path = manifest.parent/item['path']
            require(sha(path) == item['sha256'], 'fixture_manifest_hash')
            if side == 'old':
                historical = old_rows[i-ORDINALS[0]]
                require(item['sha256'] == historical['sha256'] and item['endpoint'] == historical['endpoint'], 'historical_row')
            name = f'{side}_{i:06d}.json.gz'
            shutil.copyfile(path, output/'fixtures'/name)
            files.append({'side': side, 'ordinal': i, 'endpoint': item['endpoint'], 'source': str(path),
                          'file': name, 'sha256': item['sha256'], 'bytes': path.stat().st_size})
    sources = {str(p.relative_to(ROOT)): sha(p) for p in source_paths()}
    for rel in sources:
        destination = output/'source'/rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/rel, destination)
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'arms': list(ARMS), 'shared_seconds': LIMIT,
        'ordinals': list(ORDINALS), 'files': files, 'source_sha256': sources,
        'interpreter': {'path': sys.executable, 'sha256': sha(sys.executable)},
        'manifests': [{'path': str(p), 'sha256': sha(p), 'rows': n} for p, _, n in manifests],
        'historical_selection': {'path': str(REVIEW), 'sha256': REVIEW_SHA},
        'pure': {'xml': str(xml.resolve()), 'sha256': sha(xml), 'counts': counts,
                 'receipt': str(pure_receipt.resolve()), 'receipt_sha256': sha(pure_receipt)},
        'comparison': 'A=current linear.semantic_equal; B=original semantic_api(a)==semantic_api(b). ABBA,8 actual paired rows per batch. Sole native wall exclusion remains in those original functions.',
        'copy': 'A=deepcopy; B=strict JSON encode+decode on each of16 private decoded result trees. ABBA. Input domain validation and all independent typed/order/alias checks retained in total wall.',
        'counts': {'input_files': 16, 'compare_batches': 4, 'compares': 32, 'copy_batches': 4, 'copies': 64},
        'native_calls': 0, 'policy_replay_calls': 0,
        'scope': 'Retrospective fixed tail8 kernel diagnostic only. No full audit, throughput/100ms/native improvement, or new verifier acceptance. All27218/37270 manifests remain unchanged; only16 selected gzip rows are read.',
        'clocks': 'Per-operation includes only exact declared function and its result creation; independent checks/release/progress/export are separate but retained in whole worker/parent. Wall and process CPU are distinct; no sum of nested spans.',
        'failure': 'Any mismatch, source drift, malformed row or timeout yields unknown; retain every begun measurement and first failure. No attempt/filter/retry.'}
    write(output/'plan.json', plan); verify_pins(output, plan)
    ready = {'schema': SCHEMA+'.ready', 'status': 'prepared_unexecuted', 'output': str(output),
        'plan_sha256': sha(output/'plan.json'), 'source_count': len(sources), 'pure_counts': counts,
        'execute_command': [sys.executable, '-m', MODULE, '--output', str(output), '--execute', '--plan-sha256', sha(output/'plan.json')],
        'external_whole_python_clock_required': True, 'benchmark_executed': False, 'native_calls': 0}
    write(output/'ready.json', ready)
    return ready


def verify_pins(output, plan, runtime=False):
    require(plan['schema'] == SCHEMA and plan['arms'] == list(ARMS) and plan['shared_seconds'] == LIMIT, 'scope')
    require(plan['ordinals'] == list(ORDINALS) and plan['native_calls'] == plan['policy_replay_calls'] == 0, 'domain')
    require(plan['counts'] == {'input_files': 16, 'compare_batches': 4, 'compares': 32, 'copy_batches': 4, 'copies': 64}, 'counts')
    require(set(plan['source_sha256']) == {str(p.relative_to(ROOT)) for p in source_paths()}, 'source_closure')
    for rel, digest in plan['source_sha256'].items():
        require(sha(ROOT/rel) == sha(output/'source'/rel) == digest, 'source_changed:'+rel)
    require(sha(sys.executable) == plan['interpreter']['sha256'], 'interpreter')
    require(sha(REVIEW) == REVIEW_SHA == plan['historical_selection']['sha256'], 'review')
    expected = [(side, i) for side in ('old', 'new') for i in ORDINALS]
    require([(f['side'], f['ordinal']) for f in plan['files']] == expected, 'files_order')
    require(len(plan['manifests']) == 2, 'manifests')
    for item, case, count in zip(plan['manifests'], (OLD_CASE, NEW_CASE), (27218, 37270), strict=True):
        require(Path(item['path']) == case/'api/manifest.jsonl' and item['rows'] == count
                and sha(item['path']) == item['sha256'], 'manifest_pin')
    for f in plan['files']:
        case = OLD_CASE if f['side'] == 'old' else NEW_CASE
        require(Path(f['source']) == case/'api'/f"{f['ordinal']:06d}.json.gz"
                and f['file'] == f"{f['side']}_{f['ordinal']:06d}.json.gz", 'file_path')
        require(sha(f['source']) == sha(output/'fixtures'/f['file']) == f['sha256'], 'input_pin')
    pure = plan['pure']
    require(sha(pure['xml']) == pure['sha256'] and sha(pure['receipt']) == pure['receipt_sha256'], 'pure_pin')
    require(pure['counts'] == {'tests': PURE_TESTS, 'failures': 0, 'errors': 0, 'skipped': 0}, 'pure_fixed_denominator')
    if runtime:
        loaded = {str(Path(m.__file__).resolve().relative_to(ROOT)) for m in list(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
            and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded <= set(plan['source_sha256']), 'unarchived_runtime_import')


def load_rows(output, plan):
    rows = []
    for f in plan['files']:
        with gzip.open(output/'fixtures'/f['file'], 'rt', encoding='utf8') as stream:
            row = strict_loads(stream.read())
        decoded_tree(row)
        require(row['ordinal'] == f['ordinal'] and row['endpoint'] == f['endpoint']
            and 'result' in row and 'error' not in row, 'input_row')
        rows.append(row)
    return rows


def measure(rows, journal):
    require(len(rows) == 16, 'sixteen_rows')
    records = []
    # In-memory inputs are never changed. Independent checks are charged to
    # whole worker, not mislabelled as the isolated function-call span.
    for kind in ('compare', 'copy'):
        for batch, arm in enumerate(ARMS):
            items = list(zip(rows[:8], rows[8:], strict=True)) if kind == 'compare' else [(r,) for r in rows]
            for index, args in enumerate(items):
                row = {'kind': kind, 'batch': batch, 'arm': arm, 'index': index,
                    'ordinal': args[0]['ordinal'], 'side': None if kind == 'compare' else ('old' if index < 8 else 'new')}
                function = (linear.semantic_equal if arm == 'A' else c_compare) if kind == 'compare' else (deepcopy if arm == 'A' else json_copy)
                arguments = args if kind == 'compare' else (args[0]['result'],)
                start = time.perf_counter_ns(); cpu = time.process_time_ns()
                try:
                    value = function(*arguments)
                    cpu_end = time.process_time_ns(); end = time.perf_counter_ns()
                    row.update(started_ns=start, finished_ns=end, wall_ns=end-start, cpu_ns=cpu_end-cpu)
                    if kind == 'compare':
                        require(type(value) is bool and value, 'actual_pair_semantic_difference')
                        row['equal'] = value
                    else:
                        reference = args[0]['result']
                        require(exact(value, reference), 'copy_type_order_value_difference')
                        require(decoded_tree(value).isdisjoint(decoded_tree(reference)), 'copy_alias_to_input')
                        row['result_sha256'] = hashlib.sha256(encoded(value).encode('utf8')).hexdigest()
                except BaseException as error:
                    row.update(started_ns=start, status='unknown_failed', error=repr(error), failure_observed_ns=time.perf_counter_ns())
                    try:journal.write(encoded(row)+'\n'); journal.flush()
                    except BaseException:pass
                    raise
                text = encoded(row)+'\n'
                require(journal.write(text) == len(text), 'journal_short_write')
                journal.flush(); records.append(row)
                del value
    return records


def check_records(records):
    expected = [(kind, batch, arm, index) for kind, n in (('compare', 8), ('copy', 16))
                for batch, arm in enumerate(ARMS) for index in range(n)]
    require([(r['kind'], r['batch'], r['arm'], r['index']) for r in records] == expected, 'result_denominator_order')
    previous = -1
    for r in records:
        require(type(r['index']) is int and type(r['batch']) is int and type(r['ordinal']) is int
                and r['ordinal'] == ORDINALS[r['index'] % 8], 'record_identity')
        if r['kind'] == 'compare':
            require(r['side'] is None and r.get('equal') is True, 'comparison_not_passed')
        else:
            require(r['side'] == ('old' if r['index'] < 8 else 'new')
                and type(r.get('result_sha256')) is str and len(r['result_sha256']) == 64
                and all(c in '0123456789abcdef' for c in r['result_sha256']), 'copy_evidence')
        require('error' not in r and 'status' not in r, 'failed_record')
        require(all(type(r[k]) is int and r[k] >= 0 for k in ('started_ns', 'finished_ns', 'wall_ns', 'cpu_ns')),
                'clock_type')
        require(previous <= r['started_ns'] <= r['finished_ns'] and r['wall_ns'] == r['finished_ns']-r['started_ns'], 'clock_order')
        previous = r['finished_ns']
    return {kind: {arm: {'batch_ms': [sum(r['wall_ns'] for r in records if r['kind'] == kind and r['batch'] == b)/1e6
                for b, a in enumerate(ARMS) if a == arm],
            'median_batch_ms': statistics.median(sum(r['wall_ns'] for r in records if r['kind'] == kind and r['batch'] == b)/1e6
                for b, a in enumerate(ARMS) if a == arm)} for arm in ('A', 'B')} for kind in ('compare', 'copy')}


def worker(output, admission):
    require(sys.stdin.readline().rstrip('\n') == admission == sha(output/'plan.json'), 'owned_admission')
    start = time.perf_counter_ns(); plan = strict_loads((output/'plan.json').read_text(encoding='utf8'))
    verify_pins(output, plan, runtime=True)
    load_start = time.perf_counter_ns(); rows = load_rows(output, plan); load_end = time.perf_counter_ns()
    before = [hashlib.sha256(encoded(r).encode('utf8')).hexdigest() for r in rows]
    try:
        with (output/'measurements.jsonl').open('x', encoding='utf8', newline='\n') as journal:
            records = measure(rows, journal)
        require(before == [hashlib.sha256(encoded(r).encode('utf8')).hexdigest() for r in rows], 'input_mutation')
        saved = [strict_loads(x) for x in (output/'measurements.jsonl').read_text(encoding='utf8').splitlines()]
        require(exact(records, saved), 'measurement_readback')
        summary = check_records(saved)
        verify_pins(output, plan, runtime=True)
        write(output/'result.json', {'schema': SCHEMA, 'status': 'passed_fixed_saved_kernel_diagnostic_only',
            'plan_sha256': admission, 'records': saved, 'summary': summary,
            'load_decode_domain_ns': load_end-load_start, 'before_final_export_ns': time.perf_counter_ns()-start,
            'native_calls': 0, 'policy_replays': 0, 'source_changed': [],
            'whole_audit_accepted': False, 'same_endpoint_native_speedup_certified': False,
            'comparison_scope': plan['scope'], 'clock_scope': plan['clocks']})
    except BaseException as error:
        write(output/'worker_failure.json', {'status': 'unknown_failed', 'error': repr(error),
            'elapsed_ns': time.perf_counter_ns()-start, 'partial_measurements_preserved': True})
        raise


def execute(output, admission):
    write(output/'execution_claim.json', {'plan_sha256': admission, 'never_reuse': True})
    process = None; error = None
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--plan-sha256', admission]
    try:
        require(sha(output/'plan.json') == admission, 'plan_sha')
        verify_pins(output, strict_loads((output/'plan.json').read_text(encoding='utf8')), runtime=True)
        remaining = LIMIT-(time.perf_counter()-BOOT); require(remaining > 0, 'prelaunch_budget')
        with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, stdout=stdout, stderr=stderr,
                                             admission=admission, cwd=ROOT)
        require(process['status'] == 'exited' and process['exitcode'] == 0, 'worker_failed_or_timeout')
        report = strict_loads((output/'result.json').read_text(encoding='utf8'))
        require(report['status'] == 'passed_fixed_saved_kernel_diagnostic_only' and report['plan_sha256'] == admission
                and exact(check_records(report['records']), report['summary']), 'result_report')
        require(time.perf_counter()-BOOT <= LIMIT, 'parent_budget')
    except BaseException as exception:
        error = repr(exception)
    passed = error is None
    write(output/'launch_receipt.json', {'schema': SCHEMA+'.launch', 'status': 'completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'error': error, 'command': command, 'plan_sha256': admission, 'shared_seconds': LIMIT,
        'parent_after_BOOT_before_receipt_seconds': time.perf_counter()-BOOT,
        'external_clock_required_for_full_python_startup_and_final_export': True,
        'native_calls': 0, 'policy_replay_calls': 0,
        'artifacts': {p.name: sha(p) for p in (output/'result.json', output/'measurements.jsonl', output/'stdout.log', output/'stderr.log') if p.exists()}})
    return 0 if passed else 1


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepare', action='store_true'); p.add_argument('--tests-xml', type=Path); p.add_argument('--pure-receipt', type=Path)
    p.add_argument('--worker', action='store_true'); p.add_argument('--execute', action='store_true'); p.add_argument('--plan-sha256')
    a = p.parse_args(); output = a.output.resolve()
    require(sum((a.prepare, a.worker, a.execute)) == 1, 'mode')
    if a.prepare:
        print(encoded(prepare(output, a.tests_xml, a.pure_receipt))); return 0
    if a.worker:
        worker(output, a.plan_sha256); return 0
    return execute(output, a.plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
