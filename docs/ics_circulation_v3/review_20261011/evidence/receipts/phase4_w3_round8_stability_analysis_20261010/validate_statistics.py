"""Small analytical counterexamples, no physical simulation or policy fitting."""
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter

import numpy as np
from paired_statistics import analyse_state, paired_statistics, service_delta


def main():
    cpu, wall = process_time(), perf_counter()
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})

    def reject(name, callback):
        try:
            callback()
        except ValueError:
            check(name, True)
        else:
            check(name, False)

    pair = paired_statistics([4., 5., 6., 7.], [5., 6., 7., 8.])
    check('constant paired benefit has zero standard error', pair['delta_mean_to_actual'] == -1 and pair['paired_standard_error'] == 0)
    pair = paired_statistics([0., 2.], [2., 0.])
    check('negative covariance can double paired variance', pair['negative_sample_covariance'] and pair['paired_to_independent_variance_proxy_ratio'] == 2.)
    costs = np.zeros((2, 2, 32))
    costs[0, 1, :2] = -4.
    costs[0, 1, 2:] = 4.
    costs[1, 1, :] = 5.
    result = analyse_state(costs, 0)
    early, eight = result['prefixes'][:2]
    check('prefix selection does not see heldout outcomes', early['selected_index'] == 1 and early['heldout_selected_minus_actual']['delta_mean_to_actual'] == 5.)
    check('nested prefix may reverse the selected action', eight['selected_index'] == 0 and not early['selected_in_same_block_32_optimal_set'])
    costs[:, 1, :] = -1.
    costs[:, 1, -1] = 31.
    result = analyse_state(costs, 0)
    check('duplicate tapes retain occurrence weighting', result['pooled64_means'] == [0., 0.] and result['pooled64_optimal_indices'] == [0, 1])
    check('cost ties preserve actual analytic choice', result['prefixes'][2]['selected_index'] == 0 and result['prefixes'][5]['selected_index'] == 0)
    costs[0, 0, 0] = np.nan
    reject('unknown label rejected', lambda: analyse_state(costs, 0))
    reject('one block is not independent evaluation', lambda: analyse_state(np.zeros((1, 4, 32)), 0))
    task = {'bag_id': 'same', 'arrival': 0, 'deadline': 4, 'origin': 'A', 'destination': 'B', 'protected': True, 'completed_at': 3}
    late = {**task, 'completed_at': 5}
    delta = service_delta([late], [task])
    check('worse protected service remains visible', delta['later'] == 1 and delta['protected_late'] == 1 and not delta['no_completion_later'])
    reject('different future cannot be paired', lambda: service_delta([{**task, 'arrival': 1}], [task]))
    reject('incomplete task is unknown', lambda: service_delta([{**task, 'completed_at': None}], [task]))
    source = Path(__file__).parent / 'paired_statistics.py'
    result = {'checks': checks, 'failures': [r for r in checks if not r['passed']],
              'physical_simulations': 0, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
              'scope': 'Analytical examples only; imports and final receipt serialization excluded.'}
    with (Path(__file__).parent / 'statistics_validation.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
    assert not result['failures']


if __name__ == '__main__':
    main()
