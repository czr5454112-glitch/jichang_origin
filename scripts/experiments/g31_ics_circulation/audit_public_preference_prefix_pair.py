"""Read saved pair evidence; no new projections or native execution."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())


def audit(directory):
    plan = read(directory / 'preregistered_protocol.json'); result = read(directory / 'receipt.json')
    external = read(directory / 'external_process.json'); application = read(directory / 'external_application_wall.json')
    bound = {}
    for name in ('preregistered_protocol.json', 'receipt.json', 'external_process.json',
                 'external_application_wall.json', 'timing_ledger.json', 'later_timing_ledger.json'):
        bound[str(directory / name)] = sha(directory / name)
    assert result['plan_sha256'] == bound[str(directory / 'preregistered_protocol.json')] == application['plan_sha256']
    assert result['status'] == 'completed_exact_pure_prefix_pair' and result['source_changed'] == []
    assert external['status'] == 'exited' and external['exitcode'] == 0 and external['hard_timeout_seconds'] == 120.
    assert external['windows_job_kill_on_close'] is True and external['child_released_only_after_job_assignment'] is True
    assert application['status'] == 'application_exited_zero' and application['exit_code'] == 0
    assert result['native_calls'] == external['native_calls'] == application['native_executions'] == 0
    assert result['unknown_promoted'] is False and result['complete_100ms_certified'] is False
    for path, row in plan['sources'].items():
        assert sha(path) == row['sha256'] == sha(directory / 'source' / row['archive'])
        bound[path] = row['sha256']
    initial = read(directory / 'timing_ledger.json'); later = read(directory / 'later_timing_ledger.json')
    assert initial == result['timing_samples'] and later == result['later_timing_samples']
    assert len(initial) == 24 and len(later) == 48 and len(plan['cases']) == 6
    assert all(type(row['wall_ns']) is int and row['wall_ns'] >= 0 and row['all_complete_outputs_exact'] is True
               and row['all_preparation_and_output_copies_included'] is True for row in initial + later)
    assert len(result['conformance']) == 18
    counts = Counter()
    for case in plan['cases']:
        conformance = [r for r in result['conformance'] if r['case'] == case['case']]
        assert sorted(r['phase'] for r in conformance) == ['first_return', 'first_reuse_route', 'initial']
        for row in conformance:
            expected = 32 if row['phase'] == 'initial' else 4
            assert row['candidate_count'] == len(row['checks']) == expected
            assert all(check is True for check in row['checks'])
            counts['initial' if row['phase'] == 'initial' else 'later'] += expected
        for phase, rows, expected in [('initial', initial, 32), ('first_return', later, 4), ('first_reuse_route', later, 4)]:
            selected = [r for r in rows if r['case'] == case['case'] and r.get('phase', 'initial') == phase]
            assert [r['sample'] for r in selected] == [0, 1, 2, 3]
            assert [r['arm'] for r in selected] == case['batch_order']
            assert all(r['candidate_count'] == expected for r in selected)
    assert counts == {'initial': 192, 'later': 48}
    historical = read(plan['audit']['path']); assert sha(plan['audit']['path']) == plan['audit']['sha256']
    native_counts = dict(Counter(r['status_retained'] for r in historical['rows'].values()))
    assert native_counts == result['historical_native_status_counts_retained'] == plan['historical_native_status_counts']
    medians = {arm: statistics.median(r['wall_ns'] for r in initial if r['arm'] == arm) / 1e6 for arm in ('A', 'B')}
    phases = {phase: {arm: statistics.median(r['wall_ns'] for r in later if r['arm'] == arm and r['phase'] == phase) / 1e6
                     for arm in ('A', 'B')} for phase in ('first_return', 'first_reuse_route')}
    pairs = [{ 'case': case['case'], **{arm: statistics.median(r['wall_ns'] for r in initial
        if r['arm'] == arm and r['case'] == case['case']) / 1e6 for arm in ('A', 'B')}} for case in plan['cases']]
    return {'status': 'saved_pure_pair_metadata_source_closed_candidate_slower', 'evidence': bound,
        'source_count': len(plan['sources']), 'exact_comparisons_reported_and_counted': dict(counts),
        'new_projection_calls': 0, 'native_calls': 0, 'historical_native_status_counts_retained': native_counts,
        'initial_batch_median_ms': medians, 'later_batch_medians_ms': phases, 'initial_case_medians_ms': pairs,
        'candidate_slower_all_six_cases': all(r['B'] > r['A'] for r in pairs),
        'initial_candidate_over_baseline_ratio': medians['B'] / medians['A'],
        'whole_python_application_seconds': application['whole_python_application_seconds'],
        'recommendation': 'Do not promote this candidate. Diagnose setup/AST/copy costs with a separately bounded profile.',
        'complete_100ms_certified': False,
        'scope': 'Recomputed saved counts, ordering, medians, native unknown denominator, live/archive source pins and bounded-process receipts. Full-output comparisons are the hash-bound producer checks; this read-only audit does not rerun projections or reconstruct output bodies absent from the saved report.'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--directory', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = audit(a.directory.resolve())
    result['auditor_source_sha256'] = sha(__file__)
    with a.output.open('x', encoding='utf-8') as f: json.dump(result, f, indent=2, allow_nan=False)
if __name__ == '__main__': main()
