"""Two static research figures from a COMPLETE, hash-bound 28-run DEV audit.

Example: python -B outputs/terminal_flow_science_figures005.py --complete
outputs/experiments/g31_ics_terminal_flow_20261021/final_science_005_001/COMPLETE.json
--output-dir outputs/experiments/g31_ics_terminal_flow_20261021/final_science_figures_005_001

No native dispatch, model fitting, raw observations, or native ACK reads.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

PARENTS = (2201, 2202, 2203, 2204)
METHODS = ('C00', 'C10', 'TF-current', 'TF-B1-60', 'TF-B1-300',
           'TF-B1-300-replan300', 'TF-predictor')
PAIRS = (('C00', 'C10'), ('C00', 'TF-current'), ('TF-current', 'TF-B1-60'),
         ('TF-B1-60', 'TF-B1-300'), ('TF-B1-300', 'TF-B1-300-replan300'),
         ('TF-B1-300', 'TF-predictor'))
LABELS = dict(zip(METHODS, ('C00', 'C10', 'TF-current', 'TF-B1-60', 'TF-B1-300',
                           'TF-B1-300 / replan 300 s', 'TF-predictor')))
EXPECTED_SOURCE_SHA = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'
CATEGORIES = {'exact_harmed', 'exact_improved', 'exact_equal', 'reference_only_finished',
              'candidate_only_finished', 'both_arrived_unfinished', 'both_not_yet_arrived'}

def need(ok, reason):
    if not ok:
        raise ValueError('science_figures:' + reason)

def bind(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path), 'sha256': digest.hexdigest()}

def read(path):
    path = Path(path)
    with (gzip.open(path, 'rt', encoding='utf8') if path.suffix == '.gz' else path.open(encoding='utf8')) as stream:
        return json.load(stream)

def verified(ref, refs, *, load=True):
    need(isinstance(ref, dict) and {'path', 'sha256'} <= ref.keys(), 'binding_required')
    actual = bind(ref['path'])
    need(actual['sha256'] == ref['sha256'], 'hash_changed:' + str(ref['path']))
    refs[actual['path']] = actual
    return read(actual['path']) if load else actual

def derive_data(report):
    """Validate exact population/comparison rosters before deriving plot values."""
    need(report.get('schema') == 'g31.terminal_flow.final_science.v1' and report.get('status') == 'complete', 'completed_report_required')
    need(report.get('registered_runs') == 28 and report.get('scientific_per_bag_pairs') == 24, '28_runs_24_pairs_required')
    need(tuple(map(tuple, report['scientific_pair_definitions'])) == PAIRS, 'pair_definitions')
    expected_runs = {(p, m) for p in PARENTS for m in METHODS}
    runs = [(r['parent'], r['method']) for r in report['runs']]
    need(len(runs) == 28 and set(runs) == expected_runs, 'exact_four_parent_seven_method_roster')
    need(report.get('all_unfinished_and_not_yet_arrived_bags_retained') is True, 'population_retention')
    need(report.get('strict_per_bag_nonharm_certified') is False, 'no_strict_nonharm_claim')
    expected_pairs = {(p, a, b) for p in PARENTS for a, b in PAIRS}
    seen, costs, harms, unknown = set(), {}, {}, {}
    for row in report['pair_summaries']:
        key = (row['parent'], row['reference_method'], row['candidate_method'])
        need(key in expected_pairs and key not in seen, 'duplicate_or_unregistered_pair')
        seen.add(key)
        need(row.get('population') == 28506 and row.get('population_exclusions') == 0, 'full_pair_population')
        need(row.get('cost_window') == [7200., 59400.], 'registered_cost_window')
        need(row.get('completion_times_imputed') is False and row.get('both_unfinished_never_declared_equal') is True, 'censoring_contract')
        need(row.get('independent_airport_day_claim') is False, 'derived_parent_scope')
        direction = row['completion_direction']
        counts = direction['categories']
        need(set(counts) == CATEGORIES and all(type(v) is int and v >= 0 for v in counts.values()), 'completion_categories')
        need(sum(counts.values()) == direction.get('population') == 28506, 'completion_denominator')
        need(direction.get('completion_times_imputed') is False and direction.get('bounds_are_not_completion_times') is True, 'direction_censoring_contract')
        harm = counts['exact_harmed'] + counts['reference_only_finished']
        need(direction['known_direction_harm'] == harm, 'known_harm_definition')
        harms[key] = harm
        unknown[key] = {k: counts[k] for k in ('both_arrived_unfinished', 'both_not_yet_arrived')}
        for side, method in (('reference', key[1]), ('candidate', key[2])):
            value = row[side + '_cost']['backlog_integral_bag_seconds']
            need(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'finite_J')
            cost_key = (key[0], method)
            need(cost_key not in costs or abs(costs[cost_key] - value) <= 1e-6, 'same_run_cost_disagrees')
            costs[cost_key] = value
        need(abs(row['gain_bag_seconds'] - (costs[key[0], key[1]] - costs[key[0], key[2]])) <= 1e-6, 'gain_direction')
    need(seen == expected_pairs and len(seen) == 24 and set(costs) == expected_runs, 'complete_pairs_and_costs')
    return dict(costs=costs, harms=harms, unknown=unknown, synthetic=False)

def load_completed(complete_path):
    refs = {}
    marker = verified(bind(complete_path), refs)
    need(marker.get('status') == 'complete', 'COMPLETE_required')
    for flag in ('source_bytes_checked_at_start_and_end', 'producer_bytes_checked_at_start_and_end', 'evidence_bytes_bound_before_consumption'):
        need(marker.get(flag) is True, 'incomplete_audit_provenance:' + flag)
    report = verified(marker['final_report'], refs)
    data = derive_data(report)
    need(report['source_bundle']['sha256'] == EXPECTED_SOURCE_SHA, 'source005_required')
    verified(report['source_bundle'], refs)
    workflow = verified(report['workflow'], refs)
    need(workflow['source_bundle'] == report['source_bundle'], 'workflow_source')
    need(workflow.get('TEST_unlocked') is False and workflow.get('R1_enabled') is False, 'registered_DEV_scope')
    verified(report['analysis_driver'], refs, load=False)
    structural = verified(report['campaign_structural_comparisons'], refs)
    need(structural.get('all_registered_closed') is True and structural.get('paired_comparison_complete') is True and len(structural['paired']) == 24, 'closed_structural_audit')
    templates = set()
    for row in report['runs']:
        run = verified(row['evidence'], refs)
        need((run['parent'], run['method']) == (row['parent'], row['method']), 'run_artifact_identity')
        plan = verified(run['evidence']['plan.json'], refs)
        receipt = verified(run['evidence']['receipt.json'], refs)
        worker = verified(run['evidence']['worker_report.json'], refs)
        need(receipt['worker'] == worker and worker.get('scientific_status') == 'closed', 'closed_run_required')
        need(plan['source_bundle'] == report['source_bundle'] and plan['horizon'] == 59400. and plan['activation'] == 7200., 'run_source_or_window')
        need((plan['parent']['parent_seed'], plan['method']) == (row['parent'], row['method']), 'plan_identity')
        need(plan['parent']['split'] == 'dev' and plan['parent']['synthetic'] is True, 'derived_DEV_parent')
        templates.add(plan['parent']['common_historical_template_sha256'])
    need(len(templates) == 1, 'one_shared_historical_template_required')
    expected_names = {f'P{p}_{a}_to_{b}_per_bag.json.gz' for p in PARENTS for a, b in PAIRS}
    pairs = report['per_bag_pair_evidence']
    need(len(pairs) == 24 and {Path(ref['path']).name for ref in pairs} == expected_names, '24_bound_pair_artifacts_required')
    for ref in pairs:
        verified(ref, refs, load=False)  # Hash full compressed per-bag evidence, use its bound compact summary above.
    return data, refs

def render(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    need(not output.exists(), 'fresh_output_directory_required')
    synthetic = bool(data.get('synthetic'))
    if synthetic:
        need(any('synthetic_test' in part for part in output.parts), 'synthetic_outputs_require_test_directory')
    output.mkdir(parents=True)
    colors = ('#0072B2', '#E69F00', '#009E73', '#CC79A7')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False, 'savefig.facecolor': 'white'})
    prefix = 'SYNTHETIC TEST DATA — ' if synthetic else ''
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    for i, parent in enumerate(PARENTS):
        values = [(data['costs'][parent, method] - data['costs'][parent, 'C00']) / 1e6 for method in METHODS]
        ax.scatter(values, [j + (i - 1.5) * .13 for j in range(len(METHODS))],
                   s=44, color=colors[i], label=f'P{parent}', edgecolor='white', linewidth=.5, zorder=3)
    ax.axvline(0., color='#555555', linewidth=.9)
    ax.set_yticks(range(len(METHODS)), [LABELS[m] for m in METHODS])
    ax.invert_yaxis(); ax.grid(axis='x', alpha=.22)
    ax.set_xlabel('ΔJ = method − C00 (million bag·seconds); negative is better')
    ax.set_title(prefix + 'Full-population backlog integral relative to C00', loc='left', fontsize=14, pad=15)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc='lower center', bbox_to_anchor=(.65, .075), frameon=False)
    fig.text(.02, .025, 'Cost window [7,200, 59,400] s; 28,506 planned bags per parent. Four DEV parents derive from one historical template.\nNo independent-airport-day or statistical-significance claim; no error bars.', fontsize=8.5, color='#444444')
    fig.tight_layout(rect=(0, .18, 1, 1))
    for ext in ('png', 'svg'):
        fig.savefig(output / ('J_relative_to_C00.' + ext), dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.1))
    maximum = max(data['harms'].values(), default=0)
    pad = max(maximum * .012, .5)
    comparison_labels = [LABELS[a] + ' → ' + ('replan 300 s' if b == 'TF-B1-300-replan300' else LABELS[b]) for a, b in PAIRS]
    for i, (parent, ax) in enumerate(zip(PARENTS, axes.flat)):
        values = [data['harms'][parent, a, b] for a, b in PAIRS]
        ax.barh(range(len(PAIRS)), values, color=colors[i], height=.65)
        for index, total in enumerate(values):
            ax.text(total + pad, index, f'{total:,}', va='center', fontsize=8.5)
        ax.set_xlim(0, max(maximum * 1.15, 1.))
        ax.set_yticks(range(len(PAIRS)), comparison_labels, fontsize=8.5)
        ax.invert_yaxis(); ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
        ax.set_title(f'P{parent}', loc='left', color=colors[i], fontweight='bold')
    fig.suptitle(prefix + 'Known completion-direction harm by registered comparison', x=.02, ha='left', fontsize=14)
    fig.supxlabel('Known completion-direction harm (bag cases within each parent)', y=.10, fontsize=10)
    fig.text(.02, .025, 'Known harm = later completion when both finished + reference-only completion. Both-unfinished cases remain censored, never equal.\nFour parents share one historical template; bag IDs repeat across panels. These are not four independent days or distinct populations.', fontsize=8.5, color='#444444')
    fig.tight_layout(rect=(0, .14, 1, .96), h_pad=2.2, w_pad=2.2)
    for ext in ('png', 'svg'):
        fig.savefig(output / ('known_completion_harm.' + ext), dpi=180)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    producer = bind(__file__)
    data, refs = load_completed(args.complete)
    render(data, args.output_dir)
    for ref in [producer, *refs.values()]:
        need(bind(ref['path']) == ref, 'input_changed_during_render')
    manifest = dict(schema='g31.terminal_flow.static_science_figures.v1', status='complete',
        source_manifest_sha256=EXPECTED_SOURCE_SHA, producer=producer, evidence=list(refs.values()),
        figures=[bind(args.output_dir / name) for name in ('J_relative_to_C00.png', 'J_relative_to_C00.svg', 'known_completion_harm.png', 'known_completion_harm.svg')],
        formula='delta_J = method_J - C00_J; negative is better', independent_airport_days=False,
        statistical_significance_claim=False, both_unfinished_treated_as_equal=False,
        raw_observations_or_native_ACK_read=False, native_starts=0)
    with (args.output_dir / 'COMPLETE.json').open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'output_dir': str(args.output_dir.resolve()), 'figures': 2, 'native_starts': 0}))

if __name__ == '__main__':
    main()
