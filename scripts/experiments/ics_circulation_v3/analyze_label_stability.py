"""Read-only analysis of completed common-future development labels."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from .experiment_protocol import create_output_directory
from .model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from .run_joint_feedback import save
from .runtime import ExecutionValidator


def physical_prefix_signatures(record):
    """Project retained witnesses to immediate commitments, using the owner rule.

    Only the fields used by this pure projection are decoded. This is not a
    reconstructed simulator or an authorization decision on a partial state.
    """
    raw = record['state']
    network = Network({k: Node(**v) for k, v in raw['network']['nodes'].items()},
                      {k: Edge(**v) for k, v in raw['network']['edges'].items()})
    state = Snapshot(raw['now'], network, {k: Tray(**v) for k, v in raw['trays'].items()},
                     {k: Bag(**v) for k, v in raw['bags'].items()})
    signatures = []
    for raw_candidate in record['proposals']:
        proposal = RouteCandidate(**{**raw_candidate, 'legs': tuple(Leg(**l) for l in raw_candidate['legs'])})
        prefix = ExecutionValidator._safe_prefix(state, proposal)
        signatures.append(json.dumps({'tray': prefix.tray_id, 'bag': prefix.bag_id,
            'legs': [asdict(l) for l in prefix.legs], 'unload': prefix.unload_complete, 'usable': prefix.usable_at,
            'destination': prefix.destination_node, 'prefix_only': prefix.prefix_only,
            'continuation_destination': prefix.continuation_destination}, sort_keys=True))
    return signatures


def analyze(source, output):
    source, output = Path(source), create_output_directory(output)
    summary_path = source / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if summary['failures'] or summary['source_changed_during_run']:
        raise ValueError('analysis requires a complete unchanged-source label run without failed branches')
    inputs = {summary_path.name: sha256(summary_path.read_bytes()).hexdigest()}
    rows, sample_details = [], []
    for sample in summary['samples']:
        path = source / (sample['identity'].replace(':', '_') + '.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        inputs[path.name] = sha256(path.read_bytes()).hexdigest()
        if record['summary'] != sample:
            raise ValueError('sample aggregate differs from raw label file')
        signatures = physical_prefix_signatures(record)
        costs = np.asarray(record['paired_costs'], dtype=float)
        # Exact within-numerical-tolerance empirical response classes, not a
        # claim of policy equivalence on unobserved futures.
        classes = {tuple(np.round(costs[:, i, :].ravel(), 9)) for i in range(costs.shape[1])}
        stats = sample['statistics']
        grouped = defaultdict(list)
        for row in stats['rows']:
            grouped[row['future_count']].append(row)
        per_size = {str(size): {'other_group_regret_mean': float(np.mean([r['other_replicates_regret'] for r in rs])),
                               'other_group_regret_max': max(r['other_replicates_regret'] for r in rs),
                               'different_from_own_32_optimal_set': sum(not r['same_block_32_optimal_tie'] for r in rs),
                               'replicate_count': len(rs)} for size, rs in grouped.items()}
        row = {'identity': sample['identity'], 'time': sample['time'], 'band': sample['band'],
               'retained_action_ids': len(set(record['actual_action_keys'])),
               'immediate_physical_prefixes': len(set(signatures)), 'empirical_value_classes': len(classes),
               'normal_actions': sample['normal_count'], 'value_range': stats['value_range'],
               'bounded_pool_coverage_loss': stats['bounded_pool_coverage_loss'],
               'timed_selection_loss': stats['timed_selection_loss_within_normal_pool'], 'sampling': per_size}
        rows.append(row)
        sample_details.append({'identity': sample['identity'], 'physical_prefix_signatures': signatures})
    aggregate = {'sample_count': len(rows), 'branch_count': summary['branch_count'],
        'multiple_immediate_prefix_states': sum(r['immediate_physical_prefixes'] > 1 for r in rows),
        'multiple_empirical_value_states': sum(r['empirical_value_classes'] > 1 for r in rows),
        'bounded_pool_coverage_loss_positive': sum(r['bounded_pool_coverage_loss'] > 1e-9 for r in rows),
        'timed_selection_loss_positive': sum(r['timed_selection_loss'] > 1e-9 for r in rows),
        'per_future_count': {str(size): {'mean_other_group_regret_across_sampled_states':
            float(np.mean([r['sampling'][str(size)]['other_group_regret_mean'] for r in rows])),
            'nonoptimal_own_32_group_count': sum(r['sampling'][str(size)]['different_from_own_32_optimal_set'] for r in rows)}
            for size in (2, 8, 32)}}
    save(output / 'analysis.json', {'source_directory': str(source.resolve()), 'input_sha256': inputs,
        'analyzer_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'physical_projection_runtime_sha256': sha256((Path(__file__).parent / 'runtime.py').read_bytes()).hexdigest(),
        'aggregate': aggregate, 'rows': rows, 'physical_projection': sample_details,
        'limitations': ['Four development streams; three time bands within each stream are correlated.',
                        'All boundaries count, but only the first eligible loaded tray at each tick is probed.',
                        'Monte Carlo futures and nested prefixes are not independent airport days.',
                        'Other-group regret is against an empirical minimum, not an unbiased population regret estimator.',
                        'Equal costs across these sampled futures do not establish global behavioral equivalence.',
                        'Analytic deployment looks ahead20 ticks; outcome labels measure24 ticks of that fixed continuation.',
                        'Expanded candidate pool is bounded; zero measured coverage loss is not a complete-domain certificate.']})
    lines = ['# W3 共同未来标签机会诊断', '', '本报告仅分析已完成的开发标签，不训练模型，不构成独立确认。', '',
             '| 状态 | 时刻 | 保留干预ID | 即时物理前缀 | 样本价值类 | 候选覆盖损失 | timed选择损失 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['identity']} | {row['time']} | {row['retained_action_ids']} | {row['immediate_physical_prefixes']} | {row['empirical_value_classes']} | {row['bounded_pool_coverage_loss']:.6g} | {row['timed_selection_loss']:.6g} |")
    lines += ['', '2/8/32统计、每个候选全部成对成本和输入哈希见 analysis.json 及原始目录。未来为显式取消/反转/抖动压力分布，不是现场概率。',
              '', '多个时间段相关；每个 tick 只探测第一个待路由盘。其他重复组经验regret仍有经验最小值偏差；不作总体置信结论。即时前缀相同但保留条件见证不同的干预仍保留原ID，样本价值相同也不删标签。']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(aggregate)
    return aggregate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.source, args.output)
