"""Small saved-metadata review, without fresh prediction or native execution."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())


def review(directory):
    plan = read(directory / 'preregistered_protocol.json'); result = read(directory / 'receipt.json')
    process = read(directory / 'external_process.json'); external = read(directory / 'external_application_wall.json')
    pins = {str(directory / name): sha(directory / name) for name in
            ('preregistered_protocol.json', 'receipt.json', 'external_process.json', 'external_application_wall.json', 'timing_ledger.json')}
    assert result['plan_sha256'] == external['plan_sha256'] == pins[str(directory / 'preregistered_protocol.json')]
    assert result['status'] == 'completed_exact_pure_quiet_pair' and result['source_changed'] == []
    assert result['native_calls'] == process['native_calls'] == external['native_executions'] == 0
    assert process['status'] == 'exited' and process['exitcode'] == external['exit_code'] == 0
    assert process['windows_job_kill_on_close'] is True and process['child_released_only_after_job_assignment'] is True
    assert external['status'] == 'application_exited_zero' and external['evidence_unchanged'] is True
    assert result['wall_seconds'] < process['wall_seconds'] < external['whole_python_application_seconds'] < process['hard_timeout_seconds'] == 120.
    for path, row in plan['sources'].items():
        assert sha(path) == row['sha256'] == sha(directory / 'source' / row['archive']); pins[path] = row['sha256']
    ledger = read(directory / 'timing_ledger.json'); assert ledger == result['timing_samples'] and len(ledger) == 24
    assert len(plan['cases']) == len(result['conformance']) == len(result['case_pairs']) == 6
    total = 0; medians = []
    for case in plan['cases']:
        rows = [r for r in ledger if r['case'] == case['case']]
        assert [r['arm'] for r in rows] == case['order'] and [r['sample'] for r in rows] == [0, 1, 2, 3]
        assert all(r['candidate_count'] == 32 and r['all_complete_outputs_exact'] is True
                   and r['all_preparation_and_output_construction_charged'] is True
                   and type(r['wall_ns']) is int and r['wall_ns'] >= 0 for r in rows)
        check, = [r for r in result['conformance'] if r['case'] == case['case']]
        assert len(check['checks']) == check['candidate_count'] == 32 and all(v is True for v in check['checks'])
        total += check['candidate_count']
        medians.append({'case': case['case'], **{arm: statistics.median(r['wall_ns'] for r in rows if r['arm'] == arm) / 1e6 for arm in ('A', 'B')}})
    assert total == result['initial_conformance_count'] == plan['candidate_denominator'] == 192
    assert result['later_conformance_count'] == plan['later_candidate_denominator'] == 0
    audit = read(plan['audit']['path']); assert sha(plan['audit']['path']) == plan['audit']['sha256']
    native = dict(Counter(r['status_retained'] for r in audit['rows'].values()))
    assert native == result['historical_native_status_counts_retained'] == plan['historical_native_status_counts']
    assert result['prefix_sharing'] is result['unknown_promoted'] is result['complete_100ms_certified'] is result['new_native_or_online_claim'] is False
    global_medians = {arm: statistics.median(r['wall_ns'] for r in ledger if r['arm'] == arm) / 1e6 for arm in ('A', 'B')}
    assert global_medians['A'] * 1e6 == result['median_all_A_ns'] and global_medians['B'] * 1e6 == result['median_all_B_ns']
    return {'status': 'saved_quiet_pair_bound_candidate_slower', 'evidence_sha256': pins, 'source_count': len(plan['sources']),
        'producer_exact_initial_comparisons_counted': total, 'timed_batches': len(ledger), 'later_optimized_candidates': 0,
        'initial_batch_median_ms': global_medians, 'case_medians_ms': medians,
        'all_six_cases_slower': all(r['B'] > r['A'] for r in medians),
        'whole_python_application_seconds': external['whole_python_application_seconds'],
        'historical_native_status_counts_retained': native, 'new_projection_calls': 0, 'native_calls': 0,
        'recommendation': 'Retain this independent negative result; do not deploy or stack with prefix/static candidates.',
        'scope': 'Recomputed small saved counts/order/timing arithmetic and bound live/archive sources plus actual launch receipts. Producer full-output comparisons are retained, not independently rerun from absent prediction bodies. No native/online/complete-request certification.'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--directory', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = review(a.directory.resolve()); result['reviewer_source_sha256'] = sha(__file__)
    with a.output.open('x') as f: json.dump(result, f, indent=2, allow_nan=False)
if __name__ == '__main__': main()
