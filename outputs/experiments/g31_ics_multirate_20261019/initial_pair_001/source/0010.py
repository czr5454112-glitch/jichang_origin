"""Unexecuted saved18 cost draft: integer intervals, no policy/model/C call.

One decode per original gzip. Reuses the accepted LF-corrected saved analyzer;
adds only the new measured constructor interval and observational old-report
comparison. Constructor overlap is removed explicitly before residual debit.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'outputs/sicm1'
OUTPUT = ROOT/'outputs/sicc1'
MODULE = __package__+'.analyze_static_inventory_C18_cost'
LIMIT = 120.
OLD_REPORT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/single_owned_C18_cost_analysis_002/report.json'
PINS = {
    'campaign.json': '8aa7f63c50310532fa97b0b6251ec118aeae247ff6b072ddbc73edb7f9d3018e',
    'verification.json': 'd6bbe42acb7597d58298d9fc79da2730bfcfe237f3baa877bd1aee4ce0111c3c',
    'receipt.json': '2e831eb1e5f3f5845c1be823f8f88ba7b32e959943204e00a9043d431fd4d84f',
    'actual_external_application_wall.json': 'f33d1debdde90b47c59f6db13b1c432bb571546a37d499aca2fe46895333298a',
    'branch_ledger.json': '32b657aff86cf813c9ab22d3c6e8991c2c94877ef78fdac50caa4b422412e544',
    'static_inventory_lifetime.json': '7e515d40de80e7c942fa5b018d22f93cc9d8d0b102484999756dbef8d5627050',
    'C_provider_lifetime.json': '91080a901fc81d87c53b0501dcdb817eb1d342760a52c11caf5ff310a65fa281',
    'predictor_lifetime.json': '2b5937732789d617997d5e5bea6f853a9bbed69a93c942ab5aeec0d3907f8563',
    'actual_scalar_summary_001.json': 'c79fa1fc427b92a0e4b42d955f7c414b3cca59f97abbd6d5c4d8bb6abb9b0984',
}
ANALYZER = Path(__file__).with_name('analyze_single_owned_C18_cost_v2.py')
ANALYZER_SHA = '1219b5e961fae554683f921429ea6c00be99f949aa18c19099fb98e989cde987'
OLD_REPORT_SHA = 'a5ac730be202fd8b3452bfd5935965d967d1d034f9ad15b400896bcf83a0c7ad'


def require(value, message):
    if not value:
        raise ValueError('static_saved_cost:' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reference(path):
    return {'path': str(path), 'sha256': sha(Path(path).read_bytes())}


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def outside(interval, occupied):
    """Subtract sorted/disjoint half-open integer intervals, retaining gaps."""
    start, end = interval
    cursor, result = start, []
    for left, right in sorted(occupied):
        if right <= cursor or left >= end:
            continue
        if cursor < left:
            result.append((cursor, min(left, end)))
        cursor = max(cursor, min(right, end))
    if cursor < end:
        result.append((cursor, end))
    return result


def analyze(old, raw, verified, sample, constructor):
    result = old.analyze(raw, verified, sample)
    record = raw['root_records'][0]
    root = record['value']['evidence']
    start, final, end = root['root_started_ns'], record['finalization_started_ns'], record['outside_return_ns']
    details = constructor['root']
    require(details == {'request_id': root['root_id'], 'started_ns': start,
        'deadline_ns': start+100_000_000, 'cutoff_ns': start+60_000_000}, 'constructor_exact_root')
    require(constructor['status'] == 'constructor_returned' and constructor['error_type'] is None,
        'constructor_status')
    ctor = old.interval(constructor['started_ns'], constructor['finished_ns'])
    require(start <= ctor[0] <= ctor[1] <= final <= end, 'constructor_prefinal_nesting')
    trace = root['runtime_query_proof']['trace']
    categories = {
        'recorded_native_advance_with_response_copy': old.clipped([
            old.interval(c['started_ns'], c['finished_ns'])
            for c in root['runtime_query_proof']['advance_calls']], start, final),
        'original_refresh_with_trace_and_queries': old.clipped([
            old.interval(c['started_ns'], c['finished_ns']) for c in trace['refreshes']], start, final),
        'RPC_attempt_with_validation': old.clipped([
            old.interval(e['value']['started_ns'], e['value']['finished_ns'])
            for e in root['events'] if e['stage'] == 'RPC_attempt'], start, final),
    }
    occupied = [item for group in categories.values() for item in group]
    old.disjoint(occupied)
    overlaps = {name: old.total(old.clipped(items, ctor[0], ctor[1]))
        for name, items in categories.items()}
    uncovered = outside(ctor, occupied)
    old.disjoint(occupied + uncovered)
    require(old.total(uncovered)+sum(overlaps.values()) == ctor[1]-ctor[0], 'constructor_overlap_conservation')
    measured = {name: old.total(items) for name, items in categories.items()}
    measured['constructor_outside_other_recorded_envelopes'] = old.total(uncovered)
    measured['unclassified_prefinalization_after_constructor'] = final-start-sum(measured.values())
    measured['complete_finalization'] = end-final
    require(measured['unclassified_prefinalization_after_constructor'] >= 0
        and sum(measured.values()) == end-start, 'whole_integer_conservation')
    result['constructor'] = {
        'ordinal': constructor['ordinal'], 'started_ns': ctor[0], 'finished_ns': ctor[1],
        'nested_full_call_ns': ctor[1]-ctor[0], 'overlap_ns_by_original_category': overlaps,
        'exclusive_ns': old.total(uncovered), 'exclusive_fragments': uncovered,
        'root_minus_full_constructor_ns_diagnostic': end-start-(ctor[1]-ctor[0]),
        'scope': 'Full constructor call wall, not CPU or isolated inventory. Timer boundary.check and metadata/append before the first timer clock are NOT inside this interval and remain unclassified unless another saved clock covers them.',
    }
    result['refined_exclusive_ns'] = measured
    result['refined_exclusive_ms'] = {name: value/1e6 for name, value in measured.items()}
    return result


def worker():
    started = time.perf_counter_ns()
    own = reference(Path(__file__).resolve())
    require(reference(ANALYZER)['sha256'] == ANALYZER_SHA, 'old_analyzer_source')
    # Original analyzer imports only standard-library data readers; no policy.
    from . import analyze_single_owned_C18_cost_v2 as old
    values, rows, raw_pins, active_key = {}, {}, {}, None
    try:
        for name, digest in PINS.items():
            data = (SOURCE/name).read_bytes()
            require(sha(data) == digest, 'input_pin:' + name)
            values[name] = json.loads(data)
        old_data = OLD_REPORT.read_bytes()
        require(sha(old_data) == OLD_REPORT_SHA, 'old_observational_report')
        prior = json.loads(old_data)
        plan, verification, ledger = (values[name] for name in ('campaign.json', 'verification.json', 'branch_ledger.json'))
        require(verification['status'] == 'passed_saved_with_complete_unknown_denominator'
            and verification['branches'] == 18 and values['receipt.json']['source_changed'] == [], 'complete_saved_denominator')
        require(set(plan['row_order']) == set(ledger) == set(verification['rows']) and len(ledger) == 18, 'all18_keys')
        constructors = {}
        for ordinal, item in enumerate(values['static_inventory_lifetime.json']['constructors']):
            require(type(item['ordinal']) is int and item['ordinal'] == ordinal, 'constructor_ordinal')
            identity = item['root']['request_id']
            require(identity not in constructors, 'constructor_duplicate')
            constructors[identity] = item
        require(len(constructors) == 18, 'constructor_count')
        samples = {item['request_id']: item for item in values['predictor_lifetime.json']['ledger']}
        for key in plan['row_order']:
            active_key = key
            entry = ledger[key]
            path = Path(entry['raw']['path']).resolve()
            require(path.is_relative_to(SOURCE.resolve()) and path.suffix == '.gz', 'raw_path_domain')
            compressed = path.read_bytes()  # one read: this same buffer is hashed and decompressed
            require(sha(compressed) == entry['raw']['sha256'], 'raw_hash')
            decoded = gzip.decompress(compressed)
            raw = json.loads(decoded)
            require(raw['key'] == key, 'raw_key')
            root_id = raw['root_records'][0]['value']['evidence']['root_id']
            rows[key] = analyze(old, raw, verification['rows'][key], samples.get(root_id), constructors[root_id])
            require(rows[key]['constructor']['nested_full_call_ns']/1e6
                == verification['static_inventory_lifetime']['rows'][key]['wall_ms'], 'constructor_saved_verifier_agreement')
            rows[key]['prior_run_observation'] = {
                'same_choice_label': rows[key]['choice'] == prior['rows'][key]['choice'],
                'prior_warm_ms': prior['rows'][key]['root']['warm_ms'],
                'prior_original_partition_ms': prior['rows'][key]['warm_partition_ms'],
                'prior_constructor_wall_ms': None,
                'constructor_savings_attribution': 'unknown; old run has no constructor clock',
            }
            raw_pins[key] = {**entry['raw'], 'compressed_bytes': len(compressed), 'decoded_bytes': len(decoded)}
            del raw, decoded, compressed
        require(len(rows) == 18 and sum(row['root']['closed'] for row in rows.values()) == 16, 'complete16_unknown2')
        groups = {'all18': list(rows.values()), 'closed16': [row for row in rows.values() if row['root']['closed']],
            'unknown2': [row for row in rows.values() if not row['root']['closed']]}
        summaries = {name: {
            'warm_ms': old.stats([row['root']['warm_ms'] for row in group]),
            'refined_exclusive_ms': {field: old.stats([row['refined_exclusive_ms'][field] for row in group])
                for field in group[0]['refined_exclusive_ms']},
            'nested_constructor_ms': old.stats([row['constructor']['nested_full_call_ns']/1e6 for row in group]),
            'warm_adjacent_partitions_ms': {field: old.stats([row['warm_partition_ms'][field] for row in group])
                for field in old.PHASES},
        } for name, group in groups.items()}
        for name, digest in PINS.items():
            require(reference(SOURCE/name)['sha256'] == digest, 'input_exit_pin:' + name)
        require(reference(Path(__file__).resolve()) == own
            and reference(ANALYZER)['sha256'] == ANALYZER_SHA and reference(OLD_REPORT)['sha256'] == OLD_REPORT_SHA,
            'reader_or_baseline_changed')
        report = {'schema': 'g31.static_inventory_campaign.saved_cost.v1', 'status': 'saved18_integer_partition_complete',
            'inputs': {name: {'path': str(SOURCE/name), 'sha256': digest} for name, digest in PINS.items()},
            'reader': own, 'old_analyzer': reference(ANALYZER), 'old_observational_report': reference(OLD_REPORT),
            'rows': rows, 'summaries': summaries, 'raw_inputs_read_once': raw_pins,
            'scope': 'Saved data analysis, not an independent full endpoint/physical verifier or new performance experiment. Six adjacent integer-clock intervals retain the original checks; native/refresh/RPC recorded envelopes stay disjoint. Constructor is debit only where outside them. Query remains nested in refresh. Medians/cumulative categories must not be summed.',
            'limits': ['No inference about old constructor savings.', 'No attribution of unclassified time to source inventory, guard, JSON, GC or native CPU.',
                'Event-to-event timestamps are not isolated function costs.', 'Actual C direct/fallback count remains unknown.',
                'Cold bind is inside C setup, and all cold/cleanup/three6124 checks remain in full campaign.',
                'Separate prior run comparisons are observational, including changed deadline-sensitive choices; not ABBA or causation.'],
            'cold': {'C_provider': verification['C_provider_lifetime'],
                'static_binding_ms_nested': verification['static_inventory_lifetime']['cold_binding_ms'],
                'RPC_startup_ms': verification['predictor_startup_ms'],
                'RPC_cleanup_ms': verification['predictor_close_with_cleanup_ms']},
            'no_new_native_model_C_profile': True, 'full_saved_verifier_rerun': False,
            'elapsed_before_export_ms': (time.perf_counter_ns()-started)/1e6}
        write(OUTPUT/'report.json', report)
        print(json.dumps({'report': reference(OUTPUT/'report.json'), 'rows': len(rows), 'closed16': summaries['closed16']}))
    except BaseException as error:
        write(OUTPUT/'failure.json', {'status': 'failed_saved_analysis', 'error': repr(error),
            'active_key': active_key, 'completed_keys': list(rows), 'completed_raw_pins': raw_pins,
            'reader': own, 'partial_denominator_not_promoted': True})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    if args.worker:
        require(args.admission == reference(Path(__file__).resolve())['sha256'], 'admission_source')
        require(sys.stdin.readline() == args.admission+'\n', 'owned_admission')
        worker()
        return 0
    from . import bounded_windows_job
    OUTPUT.mkdir(exist_ok=False)
    admission = reference(Path(__file__).resolve())['sha256']
    command = [sys.executable, '-m', MODULE, '--worker', '--admission', admission]
    execution = {'schema': 'g31.static_saved_cost.owned_execution.v1', 'limit_seconds': LIMIT,
        'command': command, 'reader': reference(Path(__file__).resolve()), 'no_native_model_C': True,
        'external_full_startup_exit_clock_required': True, 'status': 'unknown_before_dispatch'}
    try:
        remaining = LIMIT-(time.monotonic()-BOOT)-1.
        require(remaining > 0, 'parent_budget')
        with (OUTPUT/'worker.stdout.log').open('x', encoding='utf8') as out, (OUTPUT/'worker.stderr.log').open('x', encoding='utf8') as err:
            execution['process'] = bounded_windows_job.run(command, timeout=remaining, stdout=out,
                stderr=err, cwd=ROOT, admission=admission)
        execution['status'] = 'passed' if execution['process']['status'] == 'exited' and execution['process']['exitcode'] == 0 else 'failed_or_unknown'
    except BaseException as error:
        execution.update(status='failed_or_unknown', error=repr(error))
    finally:
        execution['before_final_export_seconds'] = time.monotonic()-BOOT
        if execution['before_final_export_seconds'] >= LIMIT:
            execution['status'] = 'failed_or_unknown'
        if (OUTPUT/'report.json').exists():
            execution['report'] = reference(OUTPUT/'report.json')
        write(OUTPUT/'execution.json', execution)
    return 0 if execution['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
