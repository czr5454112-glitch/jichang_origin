"""Plot all predeclared destination-first policies; no selection or simulation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main(source, output):
    data = json.loads(source.read_text(encoding='utf-8'))
    aggregates = data['aggregates']
    if data['episodes'] != 1872 or data['pairs'] != 936 or len(aggregates['all']) != 26:
        raise ValueError('Expected full frozen 26-policy by36 paired evidence')
    for policy, group in aggregates['all'].items():
        if group['successful_pairs'] != 36 or group['failed_pairs']:
            raise ValueError('Incomplete policy cannot be plotted as complete')
    all_names = list(aggregates['all'])
    # Separate x axes stop the very poor legacy23 baselines from concealing
    # the real cost and on-time regressions of physical31 policies.
    sections = [[p for p in all_names if 'paired23' in p],
                [p for p in all_names if 'paired23' not in p]]
    if set(sections[0] + sections[1]) != set(all_names):
        raise ValueError('Policy partition lost rows')
    fig, axes = plt.subplots(2, 3, figsize=(16, 16),
                             gridspec_kw={'height_ratios': [6, 20]}, layout='constrained')
    for row, names in enumerate(sections):
        y = np.arange(len(names))
        labels = [p.replace('__', ' / ').replace('paired_direct', 'direct').replace('physical31', '31').replace('paired23', '23').replace('_seed', ' s') for p in names]
        for col, (metric, title) in enumerate((('cost_sum_successful_runs', 'Cost change (lower is better)'),
                                               ('completed', 'Completed-task change (higher is better)'),
                                               ('on_time', 'On-time-task change (higher is better)'))):
            ax = axes[row, col]
            for offset, part, color in ((-.18, 'nominal', '#3B668F'), (.18, 'stress', '#D88735')):
                deltas = [aggregates[part][p]['destination_first'][metric] - aggregates[part][p]['original'][metric] for p in names]
                ax.barh(y + offset, deltas, .34, color=color, label=part)
            ax.set_yticks(y, labels if col == 0 else [''] * len(names), fontsize=8)
            ax.invert_yaxis()
            ax.axvline(0, color='#4D4D4D', linewidth=.8)
            ax.grid(axis='x', alpha=.2)
            ax.set_axisbelow(True)
            ax.set_title(title, fontsize=10)
            if row == 0:
                ax.legend(fontsize=8, loc='lower right')
    fig.suptitle('Legal destination-first minus original: all 26 frozen policies\n4 nominal +32 stress paired episodes per policy; separate legacy23 / remaining-policy axes', fontsize=13)
    fig.supxlabel('Reused development streams and correlated futures; this is not independent confirmation.', fontsize=10)
    output.mkdir()
    fig.savefig(output / 'destination_policy_deltas.png', dpi=160)
    fig.savefig(output / 'destination_policy_deltas.svg')
    plt.close(fig)
    shutil.copyfile(__file__, output / Path(__file__).name)
    manifest = {'input': str(source.resolve()), 'input_sha256': sha256(source.read_bytes()).hexdigest(),
                'policy_count': len(all_names), 'partition': sections,
                'metric': 'destination_first minus original; nominal/stress separated; raw sums',
                'files_sha256': {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'policies': len(all_names), 'files': list(manifest['files_sha256'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.output)
