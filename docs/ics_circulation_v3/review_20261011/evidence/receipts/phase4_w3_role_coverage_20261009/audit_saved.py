"""Independent stdlib-only audit of saved R0 role labels, without simulation."""
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WEIGHTS = {'tray_wait': 1, 'nonprotected_tardiness': 1, 'empty_distance': .1,
           'terminal_backlog': 10, 'terminal_inflight': 2}


def read(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main():
    checks = []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
    summary, protocol, manifest = read('summary.json'), read('protocol.json'), read('manifest.json')
    check('manifest_all_recorded_hashes', all(sha256((HERE / p).read_bytes()).hexdigest() == h for p, h in manifest.items()))
    check('snapshot_sources', all(sha256((HERE / 'source_snapshot' / p).read_bytes()).hexdigest() == h
                                  for p, h in summary['source_sha256'].items()))
    check('current_dependency_sources', all(sha256((ROOT / ('tests' if p.startswith('test_') else 'scripts/experiments/ics_circulation_v3') / p).read_bytes()).hexdigest() == h
                                           for p, h in summary['source_sha256'].items()))
    check('zero_failed_and_frozen', summary['failures'] == [] and summary['source_changed_during_run'] is False)
    check('declared_budget_20_K4_four_by_eight', protocol['label_horizon_ticks'] == protocol['spec']['planning_horizon'] == 20
          and protocol['spec']['candidate_count'] == 4 and protocol['stress_groups'] == 4 and protocol['stress_futures_per_group'] == 8)
    check('state_denominator', len(summary['samples']) == summary['sample_count'] == summary['opportunity_count'] == 24)
    nodes = Counter(s['source_node'] for s in summary['samples'])
    check('actual_nodes_not_inferred_coverage', dict(nodes) == summary['sampled_nodes'] == {'S': 12, 'B': 12})
    branch_counts = Counter()
    for entry in summary['samples']:
        sample = read(entry['sample_file'])
        key, state = entry['identity'], sample['state']
        cursor = sample['checkpoint_metadata']['cursor']
        check(key + ':actual_pending_cursor', sample['checkpoint_metadata']['phase'] == 'routes'
              and cursor['pending_tray_id'] == sample['tray_id']
              and cursor['route_tray_ids'][cursor['route_index']] == sample['tray_id'])
        check(key + ':state_hash', digest(state) == sample['state_sha256'])
        check(key + ':actual_node', state['trays'][sample['tray_id']]['node'] == entry['source_node'])
        check(key + ':no_future_bag_in_observation', all(b['arrival'] <= state['now'] for b in state['bags'].values()))
        check(key + ':normal_K4_alignment', len(sample['proposals']) == len(sample['features']) == len(sample['features_physical']) == entry['candidate_count'] == 4)
        check(key + ':feature_schemas', all(len(f) == 23 for f in sample['features']) and all(len(f) == 31 for f in sample['features_physical']))
        check(key + ':pending_pool', all(p in cursor['pending_options'] for p in sample['proposals']))
        for regime, groups, futures in (('nominal', 1, 1), ('stress', 4, 8)):
            label = read(entry[regime + '_file'])
            expected = {(g, c, f) for g in range(groups) for c in range(4) for f in range(futures)}
            indices = [(b['group'], b['candidate'], b['future_index']) for b in label['raw_branches']]
            check(key + ':' + regime + ':complete_denominator', len(indices) == len(expected) and set(indices) == expected)
            check(key + ':' + regime + ':same_exact_checkpoint', label['checkpoint_sha256'] == sample['checkpoint_sha256'] == entry['checkpoint_sha256'])
            check(key + ':' + regime + ':features_same_labels', label['features_physical'] == sample['features_physical']
                  and label['features_observable_only'] == sample['features'])
            check(key + ':' + regime + ':fixed_horizon', label['horizon_ticks'] == 20 and not label['failures'])
            consistent = True
            for b in label['raw_branches']:
                g, c, f = b['group'], b['candidate'], b['future_index']
                tape = label['future_groups_offline_only'][g]['tapes'][f]
                recomputed = sum(WEIGHTS[k] * v for k, v in b['cost_components'].items())
                consistent &= (set(b['cost_components']) == set(WEIGHTS) and not b['failed']
                               and math.isclose(recomputed, b['total_cost'])
                               and math.isclose(recomputed, label['paired_costs'][g][c][f])
                               and b['future_sha256'] == digest(tape)
                               and all(task['arrival'] > state['now'] and task['bag_id'] not in state['bags'] for task in tape))
            check(key + ':' + regime + ':physical_costs_and_common_future', consistent)
            branch_counts[regime] += len(indices)
    check('separate_nominal_stress_totals', dict(branch_counts) == {'nominal': 96, 'stress': 3072}
          and summary['nominal_branches'] == 96 and summary['stress_branches'] == 3072)
    for entry in summary['episodes']:
        episode = read(entry['file'])
        decisions = episode['opportunities']
        check(entry['scene'] + ':all_attempts_recorded', len(decisions) == entry['opportunities']
              and len(episode['metadata']['route_history']) == sum(d['selector_called'] for d in decisions))
        check(entry['scene'] + ':C_G_gap_explicit', episode['metadata']['empty_nodes'] == ['C', 'G'])
        check(entry['scene'] + ':episode_bag_denominator', len(episode['result']['final_snapshot']['bags']) == entry['bag_count'] == 6)
    result = {'audit': 'Read-only saved R0 role-coverage audit; no runtime/model imports or simulations',
              'check_count': len(checks), 'all_passed': all(c['passed'] for c in checks), 'checks': checks,
              'counts': {'samples': len(summary['samples']), 'nodes': dict(nodes), 'branches': dict(branch_counts)},
              'caveats': ['R0 contains S/B origins only; C/G states must come from actual later policies, not interpolated observations.',
                          'Saved checkpoint evidence identifies an in-memory exact cursor checkpoint; this audit does not reconstruct or replay it.',
                          'Runner noise agreement is selected-action membership in the optimal set; strict full-set equality gate is audited separately before any R1 reduction.',
                          'Four reused synthetic streams and conditional future replicas are correlated development evidence, not held-out airport data.']}
    (HERE / 'audit_saved.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, indent=2))
    if not result['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
