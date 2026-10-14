"""Render the complete frozen analysis, preserving all state/zero denominators."""
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter
import statistics

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cpu, wall = process_time(), perf_counter()
    source = HERE / 'results'
    manifest = json.loads((source / 'manifest.json').read_bytes())
    for name, expected in manifest.items():
        assert sha(source / name) == expected
    summary = json.loads((source / 'summary.json').read_bytes())
    states = [json.loads(p.read_bytes()) for p in sorted((source / 'states').glob('*.json'))]
    complete = [s for s in states if s['status'] == 'complete']
    lines = ['# Conditional future stability: complete frozen analysis', '',
        f"Planned requests: **{summary['planned_logical']} logical / {summary['planned_unique_physical']} unique physical**; {summary['memo_aliases']} exact aliases retain original draw weights.", '',
        f"State records: {summary['selected_records']}; complete ranking states {summary['complete_states']}/17; zero pools {summary['zero_states']}/6; unknown ranking states {summary['unknown_states']}.", '',
        'These are conditional simulations on reused development states. Two pseudorandom blocks and repeated future draws are not independent airport operating days. The law is synthetic, not a calibrated forecast posterior.', '',
        '## Statewise cost and support', '',
        '| State | Role / time | Distinct / possible futures | Seen law mass | Pooled64 mean range | Actual pooled64 gap | Block32 best sets |',
        '|---|---|---:|---:|---:|---:|---|']
    for s in states:
        d, support = s['state'], s['finite_support']
        v = s['statistics']
        counts = f"{support['sampled_distinct_tapes']}/{support['support_size']}"
        if v is None:
            lines.append(f"| {d['state_key']} | {d['role']} / {d['time']} | {counts} | {support['sampled_support_mass']['float']:.6g} | {s['status']} | unknown / no action | — |")
        else:
            lines.append(f"| {d['state_key']} | {d['role']} / {d['time']} | {counts} | {support['sampled_support_mass']['float']:.6g} | {v['pooled64_value_range']:.6g} | {v['actual_within_pooled64_regret']:.6g} | {v['blocks32_optimal_sets']} |")
    lines += ['', 'Zero-pool future supports are retained as inventory only; they have no candidate evaluation. Low seen probability mass alone does not invalidate Monte Carlo estimation, but does not support an exhaustive-future claim.', '',
        '## Select on one block, evaluate on the other', '',
        '| Selection draws | Complete / planned state-block choices | Select actual | Held-out mean better / tied / worse | Largest mean harm | Largest mean benefit | Any later completion in held-out block |',
        '|---:|---:|---:|---|---:|---:|---:|']
    for p in summary['prefixes']:
        lines.append(f"| {p['selection_draws']} | {p['complete_selections']}/{p['planned_state_block_selections']} | {p['selected_actual']} | {p['heldout_mean_better']}/{p['heldout_mean_tied']}/{p['heldout_mean_worse']} | {p['max_heldout_mean_harm']:.6g} | {p['max_heldout_mean_benefit']:.6g} | {p['heldout_any_completion_later']} |")
    lines += ['', 'Cost ties within 1e-8 retain the actual analytic action; otherwise choose the lowest ordinal. A second block evaluates the selected action against the actual action on the same futures. Its empirical minimum is only a noisy reference, not the true optimum. State gaps must not be summed as deployment improvement.', '',
        '## Paired difference variability', '',
        '| Prefix draws | Nonbaseline candidate-block comparisons | Negative covariance | Undefined independent-variance proxy | Paired/proxy ratio > 1 | Median paired SE | Largest paired SE |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    variance = []
    for n in (2, 8, 32):
        pairs = [p for s in complete for r in s['statistics']['prefixes'] if r['selection_draws'] == n
                 for c, p in enumerate(r['paired_candidates']) if c != s['state']['actual_chosen_index']]
        row = {'draws': n, 'pairs': len(pairs), 'negative_covariance': sum(p['negative_sample_covariance'] for p in pairs),
            'undefined_ratio': sum(p['paired_to_independent_variance_proxy_ratio'] is None for p in pairs),
            'ratio_above_one': sum(p['paired_to_independent_variance_proxy_ratio'] is not None and p['paired_to_independent_variance_proxy_ratio'] > 1 + 1e-8 for p in pairs),
            'median_paired_se': statistics.median([p['paired_standard_error'] for p in pairs]) if pairs else None,
            'max_paired_se': max([p['paired_standard_error'] for p in pairs], default=None)}
        variance.append(row)
        lines.append(f"| {n} | {len(pairs)} | {row['negative_covariance']} | {row['undefined_ratio']} | {row['ratio_above_one']} | {row['median_paired_se']} | {row['max_paired_se']} |")
    lines += ['', 'These standard errors describe paired Monte Carlo differences within a fixed state and law. The variance ratio uses an estimated independent-draw comparator; no separate independent-random-number experiment was performed, and no universal variance reduction is asserted.', '',
        '## Per-task service remains a separate outcome', '',
        f"Across {summary['state_draw_denominator']} complete state-future draws, {summary['all_draws_with_completion_difference']} have some candidate completion difference. Of those, {summary['cost_flat_draws_with_completion_difference']} have an entirely flat J pool.", '',
        f"There are {summary['optimal_nonactual_candidate_draws_with_later_completion']} nonactual, J-optimal candidate-draw combinations with at least one later task completion. These are repeated simulation task instances, not distinct operational bags or deadline-miss counts.", '',
        f"Nonactual candidates with no higher J on every one of 64 draws, no later completion on any draw, and at least one earlier completion: {summary['samplewise_cost_completion_dominant_nonactual_candidates']}. This is an offline diagnostic, not a deployable guard.", '',
        'All individual bag changes, protected lateness, per-draw candidate costs, all tie sets and all selection-block/evaluation-block choices are retained in results/states/*.json.', '',
        '## Complete finite-support auxiliary expectation', '',
        '| State | Entire support | Expected candidate costs under declared finite law | Best set | Actual gap |',
        '|---|---:|---|---|---:|']
    for s in complete:
        v = s['exhaustive_law_cost']
        if v is not None:
            lines.append(f"| {s['state']['state_key']} | {s['finite_support']['support_size']} | {', '.join(f'{x:.6g}' for x in v['means'])} | {v['optimal_indices']} | {v['actual_regret']:.6g} |")
    lines += ['', 'These expectations use every legal finite-law future with its exact rational probability and recorded floating-point costs. They do not reweight the primary 2/8/32 sample estimates, do not assume unseen costs, and do not establish a real-world probability law.', '',
        '## Figures and reproducibility', '',
        '[Candidate value gaps](../visuals/conditional_value_gaps.png) · [Cross-block selections](../visuals/cross_block_selection.png). SVG versions are beside the PNG files.', '',
        'Read-only extraction receipts bind every compact shard to its raw physical result. The final input binding checks frozen preparation, live source/tests, original inputs and all consumed compact shards before/after analysis. Independent raw and aggregate review is recorded in the separate Round8 review directory.', '']
    output = HERE / 'report'
    output.mkdir(exist_ok=False)
    (output / 'ANALYSIS.md').write_text('\n'.join(lines), encoding='utf-8')
    (output / 'variance_summary.json').write_text(json.dumps(variance, indent=2), encoding='utf-8')
    resource = {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall, 'physical_simulations': 0,
        'input_manifest_sha256': sha(source / 'manifest.json'), 'source_sha256': sha(Path(__file__)),
        'scope': 'Read-only report generation, excludes imports and final resource/manifest write.'}
    (output / 'resource.json').write_text(json.dumps(resource, indent=2), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps({p.name: sha(p) for p in output.iterdir()}, indent=2), encoding='utf-8')
    print(json.dumps(resource))


if __name__ == '__main__':
    main()
