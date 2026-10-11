"""Compare headline paired performance arithmetic to independent raw audit."""
from pathlib import Path
import hashlib
import json
import math
import statistics
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
AUTHOR = BASE / 'phase4_w3_round8_performance_analysis_20261010/formal/analysis.json'
bindings, failures = {}, []
checks = 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    bindings[str(path)] = sha(path)
    return json.loads(Path(path).read_text(encoding='utf8'))


def check(value, description):
    global checks
    checks += 1
    if not value:
        failures.append(description)


def compare(value, actual, label):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        check(isinstance(actual, (float, int)) and math.isclose(value, actual, rel_tol=1e-9, abs_tol=1e-8), label)
    else:
        check(value == actual, label)


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    audit = read(HERE / 'performance_formal_artifact_audit.json')
    author = read(AUTHOR)
    check(not audit['failures'] and not audit['drift'], 'entire raw audit passed')
    rows = audit['measures']
    grid = {(r['case_id'], r['block'], r['arm']): r for r in rows}
    identities = sorted({(r['case_id'], r['block']) for r in rows})
    check(len(grid) == 108 and len(identities) == 54, 'all physical arms and pairs')
    summaries = {}
    metrics = {'algorithm_cpu_seconds': 'algorithm_cpu_seconds',
               'algorithm_wall_seconds': 'algorithm_wall_seconds',
               'whole_process_cpu_seconds': 'process_cpu_seconds',
               'launch_wall_seconds': 'launch_to_exit_wall_seconds'}
    for field, target in metrics.items():
        off = [grid[c, b, 'off'][field] for c, b in identities]
        on = [grid[c, b, 'on'][field] for c, b in identities]
        delta = [right - left for left, right in zip(off, on)]
        expected = {'off_total': math.fsum(off), 'on_total': math.fsum(on),
            'on_minus_off_total': math.fsum(on) - math.fsum(off),
            'off_over_on_ratio': math.fsum(off) / math.fsum(on),
            'paired_delta_median': statistics.median(delta),
            'paired_delta_min': min(delta), 'paired_delta_max': max(delta),
            'on_lower_pairs': sum(d < 0 for d in delta),
            'equal_pairs': sum(d == 0 for d in delta),
            'on_higher_pairs': sum(d > 0 for d in delta)}
        for key, value in expected.items():
            compare(value, author['aggregate_nested_metrics_do_not_add'][target][key], target + ':' + key)
        summaries[target] = expected
    for arm in ('on', 'off'):
        for field, target in [('queries', 'search_calls'), ('search_work', 'search_work'),
                              ('screen_work', 'screen_work'), ('certified', 'certified_queries')]:
            compare(audit['totals'][arm + '_' + field], author['work'][arm][target], arm + ':' + target)
    cache = author['paired_query_cache_history']
    independent = audit['query_cache_comparisons']
    index = {(r['case_id'], r['block']): r for r in cache['cases']}
    for r in independent:
        a = index[r['case_id'], r['block']]
        for field, target in [('query_count', 'queries'), ('different_prior_cache_queries', 'private_cache_sha_mismatch_count'),
                              ('different_entry_count_queries', 'private_cache_entry_count_mismatch_count'),
                              ('first_different_prior_cache_ordinal_zero_based', 'first_cache_sha_divergence_ordinal'),
                              ('first_certified_ordinal_zero_based', 'first_certified_ordinal')]:
            compare(r[field], a[target], str((r['case_id'], r['block'])) + ':' + target)
        divergence, first = r['first_different_prior_cache_ordinal_zero_based'], r['first_certified_ordinal_zero_based']
        check(divergence is None or (first is not None and divergence > first), 'cache divergence follows a skipped query')
    counts = {'paired_query_count': sum(r['query_count'] for r in independent),
              'sha_mismatch_count': sum(r['different_prior_cache_queries'] for r in independent),
              'entry_count_mismatch_count': sum(r['different_entry_count_queries'] for r in independent)}
    for key, value in counts.items():
        compare(value, cache[key], key)
    compare(audit['totals']['process_cpu_seconds'], author['worker_full_process_cpu_seconds'], 'full OS CPU sum')
    for arm in ('on', 'off'):
        for timer in ('algorithm', 'search', 'screen', 'observer'):
            # Both inactive and active zero intervals were counted by the raw
            # auditor; the author deliberately exposes them separately.
            expected = sum(author['per_query_cpu_quantization_by_arm_role_timer'][arm + '/' + role + '/' + timer][name]
                           for role in ('loaded', 'empty') for name in ('active_zero_cpu_count', 'structurally_inactive'))
            compare(audit['totals'][arm + '_' + timer + '_zero_cpu'], expected, arm + ':' + timer + ':all zero CPU')
    drift = [p for p, expected in bindings.items() if sha(p) != expected]
    check(not drift, 'audit and author result unchanged')
    result = {'schema': 'round8_performance_independent_aggregate_comparison_v1', 'checks': checks,
              'failures': failures, 'drift': drift, 'independent_metric_summaries': summaries,
              'independent_cache_counts': counts, 'cpu_seconds': time.process_time() - cpu,
              'wall_seconds': time.perf_counter() - wall, 'files_sha256': bindings,
              'source_sha256': sha(__file__), 'physical_simulations': 0,
              'scope': 'Stdlib independent arithmetic from all 108 audited raw arms; nested metric summaries do not add to OS CPU. No additional routing or raw replay. Repeated timing blocks do not add independent business cases.'}
    target = HERE / 'performance_aggregate_comparison.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files_sha256'}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
