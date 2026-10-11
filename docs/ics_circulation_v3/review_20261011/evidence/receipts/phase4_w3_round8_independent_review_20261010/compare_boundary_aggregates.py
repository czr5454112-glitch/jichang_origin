"""Finite-slice comparison from independent raw extracts, no further replay."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import math
import time

HERE = Path(__file__).parent
OTHER = HERE.parent / 'phase4_w3_round8_conditional_boundary_mechanism_20261010/results'


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    bindings, failures, checks = {}, [], []

    def read(path):
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    def check(okay, label):
        checks.append(label)
        if not okay:
            failures.append(label)

    ours = read(HERE / 'boundary_mechanism_artifact_audit.json')
    other = read(OTHER / 'analysis.json')
    manifest = read(OTHER / 'manifest.json')
    for name, expected in manifest.items():
        check(hashlib.sha256((OTHER / name).read_bytes()).hexdigest() == expected, 'author manifest:' + name)
    check(not ours['failures'] and not ours['drift'], 'original independent audit passed')
    check(other['counts'] == {'bridges': 2, 'full_physical': 24, 'selected_states': 2, 'missing_cells': 4, 'memo': 0}, 'separate denominators')
    source = {r['state_key']: r for r in ours['single_target_slice']}
    raw = {(r['state_key'], r['future_index'], r['candidate']): r for r in ours['rows'] if r['stage'] == 'full'}
    for state in other['states']:
        key, independent = state['state_key'], source[state['state_key']]
        check(state['actual_chosen_index'] == independent['actual_index'], key + ':actual choice')
        check(state['weighted_optimal_candidates'] == independent['optimal_indices'], key + ':weighted optimum')
        check(abs(state['weighted_actual_choice_gap'] - independent['actual_regret']) <= 1e-8, key + ':weighted regret')
        for c, value in enumerate(independent['exact_single_target_slice_means']):
            check(math.isclose(value, state['weighted_costs'][c], abs_tol=1e-8), key + ':weighted scalar')
            exact = sum(Fraction(raw[key, f, c]['probability_fraction']) * Fraction(str(raw[key, f, c]['cost'])) for f in range(3))
            check(exact == Fraction(state['weighted_cost_fractions'][c]), key + ':exact serialized-cost fraction')
        for future in state['futures']:
            f = future['future_index']
            costs = independent['costs_by_outcome'][f]
            check(future['probability_fraction'] == raw[key, f, 0]['probability_fraction'], key + ':support fraction')
            check(future['optimal_candidates'] == [c for c, v in enumerate(costs) if abs(v-min(costs)) <= 1e-8], key + ':finite outcome optimum')
            check(abs(future['actual_choice_gap'] - (costs[independent['actual_index']] - min(costs))) <= 1e-8, key + ':finite outcome regret')
            for row in future['candidates']:
                r = raw[key, f, row['candidate']]
                check(r['cost'] == row['total_cost'], key + ':physical J')
                check(r['components'] == row['cost_components'], key + ':physical components')
                check(len(r['completed_at']) == row['task_count'], key + ':complete task count')
    drift = [name for name, expected in bindings.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected]
    check(not drift, 'inputs unchanged')
    result = {'schema': 'round8_boundary_independent_aggregate_comparison_v1', 'checks': len(checks),
        'failures': failures, 'drift': drift, 'cpu_seconds': time.process_time()-cpu,
        'wall_seconds': time.perf_counter()-wall, 'files_sha256': bindings, 'physical_simulations': 0,
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Independent raw-extract cost/components/task counts, all six finite outcome rankings, exact rational weighted serialized costs, fixed denominators and actual-choice gaps compared to author analysis. No extra raw read or physics.'}
    target = HERE / 'boundary_aggregate_comparison.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k != 'files_sha256'}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
