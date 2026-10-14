"""Explain the complete predeclared historical subgroup, using artifacts only."""
import gzip
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter

BASE = Path(__file__).resolve().parent.parent
RUN = BASE / 'phase4_w3_same_zone_labels_20261010'
OLD = BASE / 'phase4_w3_network_nominal_opportunities_repaired_20261010'
OUT = Path(__file__).parent / 'historical_mechanisms'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, expected=None):
    if expected is not None:
        assert sha(path) == expected, str(path)
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.name.endswith('.gz') else data)


def metric_difference(left, right):
    a, b = left['result'], right['result']
    delta = {key: b['cost_components'][key] - value for key, value in a['cost_components'].items()}
    tasks = []
    for key, at in a['final_snapshot']['completed'].items():
        after = b['final_snapshot']['completed'][key]
        load_before = a['final_snapshot']['load_times'][key]
        load_after = b['final_snapshot']['load_times'][key]
        if at != after or load_before != load_after:
            tasks.append({'bag_id': key, 'completion_before': at, 'completion_after': after,
                          'completion_delta': after - at, 'load_before': load_before, 'load_after': load_after,
                          'load_delta': load_after - load_before})
    return {'delta_cost': b['total_cost'] - a['total_cost'], 'delta_components': delta, 'task_changes': tasks}


def main():
    cpu, wall = process_time(), perf_counter()
    OUT.mkdir(exist_ok=False)
    summary = load(RUN / 'old12/summary.json')
    oldsummary = load(OLD / 'full/summary.json')
    newrows = {(r['decision_index'], r['candidate']): r for r in summary['rows']}
    oldrows = {(r['decision_index'], r['candidate']): r for r in oldsummary['rows'] if r['scene'] == 'counterflow'}
    inputs, results = {}, []
    for index in sorted({key[0] for key in newrows}):
        new, old = {}, {}
        for c in (0, 1):
            r = newrows[index, c]
            new[c] = load(RUN / r['file'], r['sha256'])
            inputs[str(RUN / r['file'])] = r['sha256']
            r = oldrows[index, c]
            old[c] = load(OLD / r['file'], r['sha256'])
            inputs[str(OLD / r['file'])] = r['sha256']
            assert new[c]['checkpoint_metadata']['historical_source_sha256'] == old[c]['request']['checkpoint_sha256']
            assert new[c]['forced_intervention']['actual_action_key'] == old[c]['request']['actual_action_key']
        interventions = []
        for c in (0, 1):
            proposals = []
            for tick in new[c]['slow_history_suffix']:
                diagnostics = tick['diagnostics']
                details = diagnostics.get('proposal_details', [])
                for proposal, detail in zip(tick['proposals'], details):
                    if detail['domain'] == 'same_zone':
                        proposals.append({'trigger_time': tick['trigger_time'], 'detail': detail,
                                          'proposal': proposal})
            interventions.append({'candidate': c, 'same_zone_proposals': proposals})
        results.append({'decision_index': index, 'time': new[0]['initial_state']['now'],
            'current_bag': new[0]['forced_intervention']['candidate']['bag_id'],
            'old_c1_minus_c0': metric_difference(old[0], old[1]),
            'new_c1_minus_c0': metric_difference(new[0], new[1]),
            'c0_new_minus_old': metric_difference(old[0], new[0]),
            'c1_new_minus_old': metric_difference(old[1], new[1]), 'same_zone_decisions': interventions})
    for path, expected in inputs.items():
        assert sha(Path(path)) == expected
    payload = {'scope': 'all historical 12 states; c0/c1 mechanism comparison only, all48 values remain in full analysis',
        'rows': results, 'input_sha256': inputs, 'source_sha256': sha(Path(__file__)),
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'resource_scope': 'pure saved-artifact analysis, no new simulator calls'}
    (OUT / 'mechanisms.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 历史12状态的继续策略机制', '',
        '旧12个状态是既有事后子组，本表不表示新on-policy分布，也不是新增独立样本。c1与c0来自同状态同未来。', '',
        '|d|t|旧 c1−c0 J|新 c1−c0 J|新差值：等待/空盘距离|同一c0换控制器 J变化|',
        '|---|---:|---:|---:|---|---:|']
    for row in results:
        delta = row['new_c1_minus_c0']['delta_components']
        lines.append(f"|{row['decision_index']}|{row['time']}|{row['old_c1_minus_c0']['delta_cost']:.1f}|{row['new_c1_minus_c0']['delta_cost']:.1f}|{delta['tray_wait']:.1f}/{delta['empty_distance']:.1f}|{row['c0_new_minus_old']['delta_cost']:.1f}|")
    lines += ['', '每件完成/加载差值和全部same-zone提案见 mechanisms.json。负成本差不等于逐件服务均不延后。']
    (OUT / 'MECHANISMS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (OUT / 'manifest.json').write_text(json.dumps({p.name: sha(p) for p in OUT.iterdir() if p.is_file()}, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'cpu_seconds': payload['cpu_seconds'], 'wall_seconds': payload['wall_seconds']}))


if __name__ == '__main__':
    main()
