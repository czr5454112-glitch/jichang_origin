"""Failure and duplicate-weight checks for the read-only output adapter."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter
from analyse_results import state_analysis, service_summary


def main():
    cpu, wall = process_time(), perf_counter()
    checks = []
    detail = {'candidate_count': 4, 'actual_chosen_index': 0}
    task = {'bag_id': 'a', 'arrival': 0, 'deadline': 20, 'origin': 'A', 'destination': 'B',
            'protected': False, 'completed_at': 10}
    compact = {str(c): {'cost': 5 + c, 'request': {'sampled_future_sha256': 'same'},
        'ledger': [{**task, 'completed_at': 10 - c}]} for c in range(4)}
    rows = [{'block': b, 'candidate': c, 'future_index': f, 'physical_key': str(c),
             'physical_status': 'controller_quiescent'} for b in range(2) for c in range(4) for f in range(32)]
    result = state_analysis(detail, rows, compact)
    checks.append(('64 repeated future draws retain service weight', result['candidate_service'][1]['service_to_actual']['earlier_task_draws'] == 64))
    checks.append(('earlier but costlier is not joint dominance', not result['candidate_service'][1]['samplewise_cost_and_completion_weak_dominance_with_service_gain']))
    checks.append(('all six prefix choices use actual', all(p['selected_is_actual'] for p in result['statistics']['prefixes'])))
    unknown = deepcopy(rows)
    unknown[0]['physical_status'] = 'censored'
    result = state_analysis(detail, unknown, compact)
    checks.append(('one censored draw makes ranking unknown', result['status'] == 'unknown_state_ranking' and result['statistics'] is None and result['planned_logical'] == 256))
    zero = state_analysis({'candidate_count': 0, 'actual_chosen_index': None}, [], {})
    checks.append(('zero pool retained separately', zero['status'] == 'zero_candidate_pool_retained'))
    for name, callback in [
        ('missing draw rejected', lambda: state_analysis(detail, rows[:-1], compact)),
        ('duplicate coordinate rejected', lambda: state_analysis(detail, rows[:-1] + [rows[0]], compact)),
        ('cross-future pairing rejected', lambda: state_analysis(detail, rows, {**compact, '1': {**compact['1'], 'request': {'sampled_future_sha256': 'other'}}}))]:
        try:
            callback()
        except ValueError:
            checks.append((name, True))
        else:
            checks.append((name, False))
    directory = Path(__file__).parent
    result = {'checks': checks, 'failures': [name for name, ok in checks if not ok],
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'physical_simulations': 0, 'analysis_source_sha256': hashlib.sha256((directory / 'analyse_results.py').read_bytes()).hexdigest(),
        'scope': 'Analytical adapter examples, excludes imports/final receipt write.'}
    with (directory / 'adapter_validation.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
    assert not result['failures']


if __name__ == '__main__':
    main()
