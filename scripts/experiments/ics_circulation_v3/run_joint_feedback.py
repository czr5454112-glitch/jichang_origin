"""Predeclared 54-cell feedback factorial; constructed development evidence."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .feedback_scenarios import feedback_matrix
from .joint_feedback import ForecastResponsePlanner, run_feedback_episode


SOURCES = ('run_joint_feedback.py', 'joint_feedback.py', 'feedback_scenarios.py', 'phase4_control.py',
           'runtime.py', 'model.py', 'prebalance.py', 'learning.py', 'evaluation.py',
           'conditional_evaluation.py', 'routing.py', 'routing_reference.py', 'experiment_protocol.py')
MODES = ('route_then_prebalance', 'prebalance_then_route', 'one_round_feedback')


def save(path, payload):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def run(output):
    output = create_output_directory(output)
    code = Path(__file__).parent
    hashes = {name: sha256((code / name).read_bytes()).hexdigest() for name in SOURCES}
    (output / 'source_snapshot').mkdir()
    for name in SOURCES:
        shutil.copyfile(code / name, output / 'source_snapshot' / name)
    scenes = feedback_matrix()
    save(output / 'protocol.json', {'scope': 'constructed_development_factorial_no_independent_confirmation',
        'source_sha256': hashes, 'new_independent_source_count': 0, 'scene_count': len(scenes),
        'modes': MODES, 'planned_run_count': len(scenes) * len(MODES),
        'factors': [s.factors for s in scenes], 'future_access': 'driver_only_planner_receives_visible_publications',
        'controls': {'planning_horizon': 20, 'candidate_count': 4, 'max_rollouts': 8, 'slow_period': 2,
                     'route_mode': 'whole_route', 'expansion_limit': 2000},
        'comparison': 'same hard permissions, same candidates and greedy prebalancer; feedback pays its actual extra proxy rollouts',
        'limitations': ['Six-node proxy with two trays; not airport performance.',
                        'No-demand cells share equivalent information when only demand_shift changes; no independent sampling claim.',
                        'One single-route response round is neither joint exact search nor MPC.',
                        'Node capacity fixed at two; full buffer pressure and sustained workload are separate diagnostics.']})
    metrics, failures = [], []
    for scene in scenes:
        case = {'name': scene.name, 'factors': scene.factors, 'initial': asdict(scene.initial),
                'published_forecasts': [asdict(f) for f in scene.forecasts],
                'future_tape_driver_only': [asdict(b) for b in scene.future_bags], 'runs': []}
        for mode in MODES:
            start, cpu = perf_counter(), process_time()
            try:
                result, history = run_feedback_episode(scene.initial, scene.forecasts, scene.future_bags, scene.horizon,
                    mode=mode, planner=ForecastResponsePlanner(planning_horizon=20, candidate_count=4, max_rollouts=8))
                row = {'scene': scene.name, 'condition': scene.factors['condition'], 'mode': mode, 'status': 'completed_run',
                       'scheduled_bags': len(scene.initial.bags) + len(scene.future_bags), 'completed': len(result.completed),
                       'total_cost': result.total_cost, 'uncompleted': list(result.uncompleted_bag_ids),
                       'slow_triggers': len(history), 'rollout_attempts': sum(h['rollout_attempts'] for h in history),
                       'changed_loaded_decisions': sum(h['actual_route_changed'] for h in history),
                       'response_change_options': sum(r['response_changed'] for h in history for r in h['scored']),
                       'decision_opportunities': sum(h['single_deviation_count'] > 0 for h in history),
                       'proxy_failures': sum(len(h['failures']) for h in history),
                       'unscored_deviations': sum(h['unscored_deviations'] for h in history),
                       'planner_ms': sum(h['elapsed_ms'] for h in history),
                       'wall_seconds': perf_counter() - start, 'process_cpu_seconds': process_time() - cpu}
                case['runs'].append({'metrics': row, 'result': asdict(result), 'history': history})
            except Exception as exc:
                row = {'scene': scene.name, 'condition': scene.factors['condition'], 'mode': mode, 'status': 'failed_run',
                       'scheduled_bags': len(scene.initial.bags) + len(scene.future_bags), 'completed': None, 'total_cost': None,
                       'wall_seconds': perf_counter() - start, 'process_cpu_seconds': process_time() - cpu,
                       'failure': {'type': type(exc).__name__, 'reason': str(exc)}}
                failures.append(row)
                case['runs'].append({'metrics': row})
            metrics.append(row)
        save(output / f'{scene.name}.json', case)
    comparisons = []
    for scene in scenes:
        by_mode = {m['mode']: m for m in metrics if m['scene'] == scene.name}
        if any(m['total_cost'] is None for m in by_mode.values()):
            comparisons.append({'scene': scene.name, 'status': 'missing_due_to_failure'})
            continue
        comparisons.append({'scene': scene.name, 'condition': scene.factors['condition'], 'status': 'available',
                            'feedback_minus_route_first': by_mode['one_round_feedback']['total_cost'] - by_mode['route_then_prebalance']['total_cost'],
                            'feedback_minus_prebalance_first': by_mode['one_round_feedback']['total_cost'] - by_mode['prebalance_then_route']['total_cost']})
    summary = {'scope': 'development_mechanism_factorial_not_research_acceptance',
               'run_count': len(metrics), 'failed_run_count': len(failures),
               'scheduled_bag_denominator': sum(m['scheduled_bags'] for m in metrics),
               'completed_across_successful_runs': sum(m['completed'] or 0 for m in metrics),
               'metrics': metrics, 'comparisons': comparisons, 'source_sha256': hashes,
               'source_changed_during_run': any(sha256((code / name).read_bytes()).hexdigest() != value for name, value in hashes.items())}
    save(output / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('run_count', 'failed_run_count', 'scheduled_bag_denominator',
                                             'completed_across_successful_runs', 'source_changed_during_run')}))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(1 if result['failed_run_count'] or result['source_changed_during_run'] else 0)
