"""Scientific figures from the complete, already audited JSON analysis only."""
import argparse
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(source, output):
    cpu, wall = process_time(), perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    raw = source.read_bytes()
    data = json.loads(raw)
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titleweight': 'bold', 'savefig.facecolor': 'white'})
    scenes = sorted({row['scene'] for row in data['pools']})
    fig, axes = plt.subplots(3, 1, figsize=(11.8, 9.2), layout='constrained')
    for ax, scene in zip(axes, scenes):
        rows = [r for r in data['pools'] if r['scene'] == scene and r['complete']]
        zero = [r['decision_index'] for r in data['pools'] if r['scene'] == scene and r['candidate_count'] == 0]
        ax.vlines([r['decision_index'] for r in rows], [r['best_cost'] for r in rows],
                  [r['worst_cost'] for r in rows], color='#b7c8db', linewidth=3, label='Range of candidate costs')
        ax.scatter([r['decision_index'] for r in rows], [r['best_cost'] for r in rows],
                   marker='_', s=100, color='#15765b', label='Best within the original pool', zorder=3)
        ax.scatter([r['decision_index'] for r in rows], [r['actual_chosen_cost'] for r in rows],
                   s=14, color='#214f82', label='Deployed choice', zorder=4)
        for at in zero:
            ax.axvline(at, color='#bbb', linestyle=':', linewidth=1)
        ax.set_title(scene.replace('_', ' ').title())
        ax.set_ylabel('Full-cycle cost J')
        ax.grid(axis='y', alpha=.18)
    axes[0].legend(loc='best', frameon=False, fontsize=9)
    axes[-1].set_xlabel('Actual generation attempt index (dotted lines: zero-candidate attempts)')
    fig.suptitle('New slow controller: every actual nominal candidate evaluated\n'
                 'Same checkpoint and original future within each pool; three reused development streams', fontsize=13)
    for suffix in ('png', 'svg'):
        fig.savefig(output / ('onpolicy_candidate_costs.' + suffix), dpi=170)
    plt.close(fig)
    history = [r for r in data['historical_old12'] if r['complete']]
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), layout='constrained')
    x = list(range(len(history)))
    axes[0].plot(x, [r['old_c0_regret'] for r in history], 'o-', color='#a65332', label='Old slow continuation')
    axes[0].plot(x, [r['new_c0_regret'] for r in history], 's-', color='#15765b', label='New slow continuation')
    axes[0].set_ylabel('c0 cost minus best candidate cost')
    axes[0].set_title('Continuation changes the action-value gap')
    axes[0].legend(frameon=False)
    axes[1].plot(x, [r['old_values']['0'] for r in history], 'o-', color='#a65332', label='Old: c0 cost')
    axes[1].plot(x, [r['new_values']['0'] for r in history], 's-', color='#15765b', label='New: c0 cost')
    axes[1].plot(x, [min(r['new_values'].values()) for r in history], '^-', color='#214f82', label='New: best candidate cost')
    axes[1].set_ylabel('Full-cycle cost J')
    axes[1].set_title('Same historical physical checkpoint')
    axes[1].legend(frameon=False)
    for ax in axes:
        ax.set_xticks(x, ['d' + str(r['decision_index']) for r in history], rotation=45)
        ax.grid(axis='y', alpha=.18)
    fig.suptitle('Historical old12 subgroup: all 48 original candidate actions\n'
                 'Posthoc diagnostic; not the new on-policy state distribution', fontsize=12)
    for suffix in ('png', 'svg'):
        fig.savefig(output / ('historical_continuation_comparison.' + suffix), dpi=170)
    plt.close(fig)
    evidence = {'input': str(source.resolve()), 'input_sha256': hashlib.sha256(raw).hexdigest(),
                'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
                'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.output)
