"""All per-bag paired completion differences from already audited raw extracts."""
from pathlib import Path
import hashlib
import json
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).parent
BASE = HERE.parent
PRIOR = BASE / 'phase4_w3_same_zone_labels_20261010'
INVENTORY = BASE / 'phase4_w3_round8_conditional_boundary_inventory_20261010/analysis.json'


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    bound, failures, checks = {}, [], []

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def read(path):
        bound[str(path)] = sha(path)
        return json.loads(path.read_text(encoding='utf8'))

    def check(okay, label):
        checks.append(label)
        if not okay:
            failures.append(label)

    audit = read(HERE / 'boundary_mechanism_artifact_audit.json')
    inventory = read(INVENTORY)
    check(not audit['failures'] and not audit['drift'], 'original independent audit passed')
    grid = {(r['state_key'], r['future_index'], r['candidate']): r for r in audit['rows'] if r['stage'] == 'full'}
    actuals = {r['state_key']: r['actual_index'] for r in audit['single_target_slice']}
    rows = []
    for selected in inventory['selected']:
        key, actual = selected['state_key'], actuals[selected['state_key']]
        path = PRIOR / selected['checkpoint_file']
        check(sha(path) == selected['checkpoint_sha256'], key + ':original checkpoint')
        bound[str(path)] = selected['checkpoint_sha256']
        with path.open('rb') as stream:
            payload = pickle.load(stream)
        initial = payload['checkpoint'].state.bags
        for f, future in enumerate(selected['finite_outcomes']):
            definitions = {bag.bag_id: {'protected': bag.protected} for bag in initial.values()}
            definitions.update({r['bag_id']: r for r in future['pending']})
            baseline = grid[key, f, actual]
            for c in range(selected['candidate_count']):
                if c == actual:
                    continue
                branch = grid[key, f, c]
                check(set(definitions) == set(branch['completed_at']) == set(baseline['completed_at']), key + ':same complete bag definitions')
                bags = [{'bag_id': bag, 'protected': definitions[bag]['protected'],
                         'actual_completed_at': baseline['completed_at'][bag],
                         'candidate_completed_at': branch['completed_at'][bag],
                         'completion_delta': branch['completed_at'][bag] - baseline['completed_at'][bag]}
                        for bag in sorted(definitions)]
                rows.append({'state_key': key, 'future_index': f, 'future_fraction': future['probability_fraction'],
                    'actual_candidate': actual, 'candidate': c, 'bags': bags,
                    'task_count': len(bags), 'earlier': sum(r['completion_delta'] < 0 for r in bags),
                    'later': sum(r['completion_delta'] > 0 for r in bags),
                    'equal': sum(r['completion_delta'] == 0 for r in bags),
                    'protected_completion_changed': sum(r['protected'] and r['completion_delta'] != 0 for r in bags),
                    'protected_later': sum(r['protected'] and r['completion_delta'] > 0 for r in bags),
                    'cost_difference': branch['cost'] - baseline['cost'],
                    'J_tied_but_service_different': abs(branch['cost'] - baseline['cost']) <= 1e-8 and any(r['completion_delta'] for r in bags)})
    summary = {'nonactual_comparisons': len(rows), 'paired_task_comparisons': sum(r['task_count'] for r in rows),
        'earlier_task_comparisons': sum(r['earlier'] for r in rows),
        'later_task_comparisons': sum(r['later'] for r in rows),
        'equal_task_comparisons': sum(r['equal'] for r in rows),
        'protected_completion_changed': sum(r['protected_completion_changed'] for r in rows),
        'protected_later': sum(r['protected_later'] for r in rows),
        'J_tied_but_service_different_comparisons': sum(r['J_tied_but_service_different'] for r in rows),
        'maximum_completion_delay': max(r['completion_delta'] for row in rows for r in row['bags'])}
    check(len(rows) == 18, 'all two states times three outcomes times three nonactual actions')
    drift = [name for name, expected in bound.items() if sha(Path(name)) != expected]
    check(not drift, 'all read artifacts stable')
    result = {'schema': 'round8_boundary_all_bag_service_comparison_v1', 'summary': summary, 'rows': rows,
        'checks': len(checks), 'failures': failures, 'drift': drift, 'files_sha256': bound,
        'cpu_seconds': time.process_time()-cpu, 'wall_seconds': time.perf_counter()-wall,
        'source_sha256': sha(Path(__file__)), 'physical_simulations': 0,
        'scope': 'Every bag in all 18 nonactual vs actual comparisons, reusing independently audited complete maps and original task protection. Repeated candidate/future task comparisons are not distinct physical bags or operating days. No new raw-branch read or simulation.'}
    target = HERE / 'boundary_service_comparison.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows', 'files_sha256')}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
