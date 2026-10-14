"""Standalone publication-style descriptive figures; no policy or outcome fitting."""
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    cpu, wall = process_time(), perf_counter()
    directory = HERE / 'results'
    summary = json.loads((directory / 'summary.json').read_bytes())
    states = [json.loads(p.read_bytes()) for p in sorted((directory / 'states').glob('*.json'))]
    complete = [s for s in states if s['status'] == 'complete']
    output = HERE / 'visuals'
    output.mkdir(exist_ok=False)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.facecolor': 'white'})
    labels = [s['state']['state_key'].replace('cross_cycle', 'cross').replace('counterflow', 'counter').replace('near_full', 'near') for s in complete]
    n = len(complete)
    y = np.arange(n)
    fig, axes = plt.subplots(1, 3, figsize=(14, max(6, .37 * n)), gridspec_kw={'width_ratios': [1.1, 1.1, 1.]})
    quantities = [([s['statistics']['pooled64_value_range'] for s in complete], 'Pooled 64: candidate mean range', '#36738a'),
                  ([s['statistics']['actual_within_pooled64_regret'] for s in complete], 'Pooled 64: actual minus best mean', '#ba6948'),
                  ([max(d['actual_empirical_regret'] for d in s['draws']) for s in complete], 'Largest one-future gap', '#927244')]
    for ax, (values, title, color) in zip(axes, quantities):
        ax.barh(y, values, color=color, height=.65)
        ax.set_yticks(y, labels if ax is axes[0] else [])
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11, loc='left')
        ax.set_xlabel('Cost J (descriptive; not additive gain)')
        limit = max(max(values, default=0), 1.)
        ax.set_xlim(0, limit * 1.22)
        for j, value in enumerate(values):
            ax.text(value + .015 * limit, j, f'{value:.3g}', va='center', fontsize=8)
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('Conditional future sensitivity on fixed real decision states', fontsize=15, x=.02, ha='left')
    fig.text(.02, .013, f"{summary['complete_states']}/17 states complete; all 6 zero pools retained separately. Two frozen blocks of 32 draws; reused synthetic development streams.", fontsize=9)
    fig.tight_layout(rect=[0, .04, 1, .95])
    for suffix in ('png', 'svg'):
        fig.savefig(output / ('conditional_value_gaps.' + suffix), dpi=170)
    plt.close(fig)

    selections = [p for s in complete for p in s['statistics']['prefixes']]
    matrix = np.array([[next(p['selected_index'] for p in s['statistics']['prefixes'] if p['selection_block'] == b and p['selection_draws'] == count)
                        for count in (2, 8, 32)] for s in complete for b in range(2)])
    fig, ax = plt.subplots(figsize=(9, max(7, .32 * 2 * n)))
    from matplotlib.colors import ListedColormap, BoundaryNorm
    palette = ListedColormap(['#dfe9e8', '#a5c9d2', '#dcc69a', '#cfaab6'])
    ax.imshow(matrix, cmap=palette, norm=BoundaryNorm(np.arange(-.5, 4.5), 4), aspect='auto')
    ax.set_xticks(range(3), ['2 selection draws', '8 selection draws', '32 selection draws'])
    ax.set_yticks(range(n * 2), [f'{label} / select block {b}' for label in labels for b in range(2)], fontsize=8)
    for i, s in enumerate(complete):
        for b in range(2):
            for j, count in enumerate((2, 8, 32)):
                p = next(p for p in s['statistics']['prefixes'] if p['selection_block'] == b and p['selection_draws'] == count)
                delta = p['heldout_selected_minus_actual']['delta_mean_to_actual']
                later = p['heldout_service_to_actual']['draws_with_any_later']
                ax.text(j, 2 * i + b, f"c{p['selected_index']} | dJ {delta:+.3g} | late {later}/32", ha='center', va='center', fontsize=8)
    ax.set_title('Select on one block; evaluate on the other 32 draws\nCost ties retain the actual analytic choice', loc='left', pad=14, fontsize=13)
    ax.set_xticks(np.arange(-.5, 3, 1), minor=True)
    ax.set_yticks(np.arange(-.5, n * 2, 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=1.5)
    ax.tick_params(which='minor', bottom=False, left=False)
    fig.text(.02, .01, 'dJ = held-out mean cost minus actual baseline; late = draws with any later completion (not deadline misses).\nRows and nested prefixes are dependent simulation comparisons, not independent operational days.', fontsize=8)
    fig.tight_layout(rect=[0, .04, 1, 1])
    for suffix in ('png', 'svg'):
        fig.savefig(output / ('cross_block_selection.' + suffix), dpi=170)
    plt.close(fig)
    result = {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall, 'physical_simulations': 0,
        'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob('*.json'))},
        'figures': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()},
        'scope': 'Static descriptive figures; plotting imports and final receipt excluded.'}
    with (output / 'resource.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ('inputs', 'figures')}))


if __name__ == '__main__':
    main()
