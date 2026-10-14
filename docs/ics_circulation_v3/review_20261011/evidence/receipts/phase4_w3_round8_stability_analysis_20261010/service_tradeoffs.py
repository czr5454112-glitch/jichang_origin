"""Descriptive service differences among per-future J ties; no policy selection."""
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
EPSILON = 1e-8


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def classify(state):
    actual = state['state']['actual_chosen_index']
    counts = dict(same=0, earlier_only=0, later_only=0, mixed=0)
    max_delay, max_gain, protected_delays = 0, 0, 0
    task_pairs = earlier_tasks = later_tasks = 0
    examples = []
    for draw in state['draws']:
        assert len(draw['costs']) == len(draw['service_to_actual'])
        assert 0 <= actual < len(draw['costs'])
        for candidate, (cost, service) in enumerate(zip(draw['costs'], draw['service_to_actual'])):
            if candidate == actual or abs(cost - draw['costs'][actual]) > EPSILON:
                continue
            assert service['earlier'] + service['later'] == len(service['changes'])
            assert len({c['bag_id'] for c in service['changes']}) == len(service['changes'])
            assert all(c['completion_delta'] != 0 for c in service['changes'])
            assert service['earlier'] == sum(c['completion_delta'] < 0 for c in service['changes'])
            assert service['later'] == sum(c['completion_delta'] > 0 for c in service['changes'])
            assert len(service['changes']) <= service['task_count']
            task_pairs += service['task_count']
            earlier_tasks += service['earlier']
            later_tasks += service['later']
            key = ('mixed' if service['earlier'] else 'later_only') if service['later'] else ('earlier_only' if service['earlier'] else 'same')
            counts[key] += 1
            for change in service['changes']:
                delta = change['completion_delta']
                max_delay = max(max_delay, delta)
                max_gain = max(max_gain, -delta)
                protected_delays += change['protected'] and delta > 0
            examples.append({'block': draw['block'], 'future_index': draw['future_index'],
                'candidate': candidate, 'actual': actual, 'category': key,
                'cost': cost, 'baseline_cost': draw['costs'][actual], 'changes': service['changes']})
    return {'state_key': state['state']['state_key'], 'tie_action_draw_count': sum(counts.values()),
        'counts': counts, 'max_completion_delay_ticks': max_delay, 'max_completion_gain_ticks': max_gain,
        'task_pair_denominator': task_pairs, 'earlier_task_pairs': earlier_tasks, 'later_task_pairs': later_tasks,
        'unchanged_task_pairs': task_pairs - earlier_tasks - later_tasks,
        'protected_later_task_pairs': protected_delays, 'examples': examples}


def validate():
    # All four service categories, a cost-changing alternative, and a nonzero
    # actual index. A protected completion delay need not be a deadline miss.
    values = [[], [{'bag_id': 'a', 'completion_delta': -2, 'protected': False}],
              [{'bag_id': 'a', 'completion_delta': 3, 'protected': True}],
              [{'bag_id': 'a', 'completion_delta': -1, 'protected': False}, {'bag_id': 'b', 'completion_delta': 4, 'protected': False}], []]
    services = [{'task_count': 3, 'earlier': sum(x['completion_delta'] < 0 for x in v),
        'later': sum(x['completion_delta'] > 0 for x in v), 'changes': v} for v in values]
    state = {'state': {'actual_chosen_index': 4, 'state_key': 'analytic_fixture'},
        'draws': [{'block': 0, 'future_index': 0, 'costs': [5.] * 5, 'service_to_actual': services},
                  {'block': 1, 'future_index': 0, 'costs': [6., 6., 6., 6., 5.], 'service_to_actual': services}]}
    row = classify(state)
    assert row['counts'] == dict(same=1, earlier_only=1, later_only=1, mixed=1)
    assert (row['task_pair_denominator'], row['earlier_task_pairs'], row['later_task_pairs'], row['unchanged_task_pairs']) == (12, 2, 2, 8)
    assert (row['max_completion_delay_ticks'], row['max_completion_gain_ticks'], row['protected_later_task_pairs']) == (4, 2, 1)
    assert row['tie_action_draw_count'] == 4


def main():
    cpu, wall = process_time(), perf_counter()
    validate()
    source = HERE / 'results'
    manifest_path = source / 'manifest.json'
    manifest_sha = sha(manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    paths = sorted((source / 'states').glob('*.json')) + [source / 'summary.json']
    for path in paths:
        assert sha(path) == manifest[str(path.relative_to(source))]
    summary = json.loads((source / 'summary.json').read_bytes())
    states = [json.loads(path.read_bytes()) for path in paths[:-1]]
    rows = [classify(state) for state in states if state['status'] == 'complete']
    assert len(rows) == summary['complete_states']
    output = HERE / 'service_tradeoffs'
    output.mkdir(exist_ok=False)
    totals = {k: sum(row[k] for row in rows) for k in ('tie_action_draw_count', 'task_pair_denominator',
        'earlier_task_pairs', 'later_task_pairs', 'unchanged_task_pairs', 'protected_later_task_pairs')}
    totals['counts'] = {k: sum(row['counts'][k] for row in rows) for k in rows[0]['counts']}
    result = {'states': rows, 'totals': totals, 'epsilon': EPSILON, 'scope':
        'Per-future nonactual actions with J equal to the actual action. Draw occurrence weights retained; repeated candidates, futures, states and bags are not independent business observations. Descriptive offline comparison, not a runtime guard or replacement objective.'}
    write(output / 'analysis.json', result)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.facecolor': 'white'})
    fig, (left, right) = plt.subplots(1, 2, figsize=(12.5, max(6, .38 * len(rows))), gridspec_kw={'width_ratios': [2.4, 1.]})
    y, start = np.arange(len(rows)), np.zeros(len(rows))
    colors = ['#c9d4d8', '#3f8b8b', '#be6b50', '#9279a6']
    for (key, label), color in zip([('same', 'Same completion times'), ('earlier_only', 'Earlier only'),
            ('later_only', 'Later only'), ('mixed', 'Some earlier, some later')], colors):
        widths = np.array([r['counts'][key] for r in rows])
        left.barh(y, widths, left=start, color=color, height=.66, label=label)
        start += widths
    labels = [r['state_key'].replace('cross_cycle', 'cross').replace('counterflow', 'counter').replace('near_full', 'near') for r in rows]
    left.set_yticks(y, labels)
    left.set_xlim(0, max(max(start, default=0), 1) * 1.17)
    for pos, total in enumerate(start):
        left.text(total + 1, pos, str(int(total)), va='center', fontsize=8)
    left.set_xlabel('Nonactual candidate × draw occurrences with equal J')
    left.set_title('Cost ties can conceal later completion', loc='left')
    delays = [r['max_completion_delay_ticks'] for r in rows]
    right.barh(y, delays, color='#be6b50', height=.66)
    right.set_yticks(y, [])
    right.set_xlim(0, max(max(delays, default=0), 1) * 1.2)
    right.set_xlabel('Largest delay among these ties (ticks)')
    right.set_title('Delay to an individual bag', loc='left')
    for pos, value in enumerate(delays):
        right.text(value + .15, pos, str(value), va='center', fontsize=8)
    for ax in (left, right):
        ax.invert_yaxis()
        ax.set_axisbelow(True)
        ax.grid(axis='x', alpha=.16)
    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, .035), fontsize=9)
    fig.suptitle('Service differences within scalar-cost ties', x=.02, ha='left', fontsize=15)
    fig.text(.02, .015, 'Fixed reused decision states; 64 occurrence-weighted futures each. Offline diagnostics; counts are dependent. Zero pools retained separately.', fontsize=8)
    fig.tight_layout(rect=[0, .10, 1, .94])
    for suffix in ('png', 'svg'):
        fig.savefig(output / ('equal_cost_service.' + suffix), dpi=170)
    plt.close(fig)
    for path in paths:
        assert sha(path) == manifest[str(path.relative_to(source))]
    assert sha(manifest_path) == manifest_sha
    write(output / 'resource.json', {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'physical_simulations': 0, 'analytic_checks': 4, 'source_sha256': sha(Path(__file__)),
        'input_manifest_sha256': manifest_sha, 'scope': 'Pure service aggregation and figure; matplotlib imports included, receipt/manifest write excluded.'})
    write(output / 'manifest.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(totals))


if __name__ == '__main__':
    main()
