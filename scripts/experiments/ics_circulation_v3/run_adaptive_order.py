"""Follow-up urgency factorial with an adaptive two-order strong comparator."""
import argparse
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, process_time

from .adaptive_order_feedback import AdaptiveOrderPlanner, urgency_matrix
from .experiment_protocol import create_output_directory
from .joint_feedback import run_feedback_episode
from .run_joint_feedback import SOURCES as BASE_SOURCES, save


MODES = ('route_then_prebalance', 'prebalance_then_route', 'one_round_feedback', 'adaptive_two_orders')


def run(output):
    output = create_output_directory(output)
    source = Path(__file__).parent
    names = ('run_adaptive_order.py', 'adaptive_order_feedback.py') + BASE_SOURCES
    hashes = {name: sha256((source / name).read_bytes()).hexdigest() for name in names}
    (output / 'source_snapshot').mkdir()
    for name in names:
        shutil.copyfile(source / name, output / 'source_snapshot' / name)
    scenes = urgency_matrix()
    save(output / 'protocol.json', {'scope': 'development_followup_not_fresh_confirmation',
        'reason': 'Previous54 cells had slack30 and all feedback results tied prebalance-first; test observed urgency tradeoff without altering old table.',
        'scene_count': len(scenes), 'planned_runs': len(scenes) * len(MODES), 'modes': MODES,
        'factors': [s.factors for s in scenes], 'planning_horizon': 20, 'candidate_count': 4,
        'slow_period': 2, 'feedback_max_rollouts': 8, 'adaptive_order_rollouts': 'two only when action bundles differ',
        'new_independent_source_count': 0, 'source_sha256': hashes,
        'timing_environment': 'Other independent experiments may run on same machine; CPU and wall both saved, no exclusive-SLA claim.'})
    metrics = []
    for scene in scenes:
        rows = []
        for mode in MODES:
            wall, cpu = perf_counter(), process_time()
            try:
                result, history = run_feedback_episode(scene.initial, scene.forecasts, scene.future_bags, scene.horizon,
                    mode=mode, planner=AdaptiveOrderPlanner(planning_horizon=20, max_rollouts=8))
                row = {'scene': scene.name, 'mode': mode, 'cost': result.total_cost, 'completed': len(result.completed),
                       'scheduled': len(scene.initial.bags) + len(scene.future_bags), 'failure': None,
                       'rollouts': sum(h['rollout_attempts'] for h in history),
                       'changed_loaded_decisions': sum(h['actual_route_changed'] for h in history),
                       'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall}
                rows.append({'metrics': row, 'result': asdict(result), 'history': history})
            except Exception as exc:
                row = {'scene': scene.name, 'mode': mode, 'cost': None, 'completed': None,
                       'scheduled': len(scene.initial.bags) + len(scene.future_bags),
                       'failure': {'type': type(exc).__name__, 'reason': str(exc)},
                       'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall}
                rows.append({'metrics': row})
            metrics.append(row)
        save(output / f'{scene.name}.json', {'initial': asdict(scene.initial), 'factors': scene.factors,
             'forecasts': [asdict(f) for f in scene.forecasts], 'driver_future': [asdict(b) for b in scene.future_bags], 'runs': rows})
    summary = {'run_count': len(metrics), 'failed_run_count': sum(r['failure'] is not None for r in metrics),
               'scheduled': sum(r['scheduled'] for r in metrics), 'completed': sum(r['completed'] or 0 for r in metrics),
               'metrics': metrics, 'source_sha256': hashes,
               'source_changed_during_run': any(sha256((source / name).read_bytes()).hexdigest() != h for name, h in hashes.items())}
    save(output / 'summary.json', summary)
    print({k: summary[k] for k in ('run_count', 'failed_run_count', 'scheduled', 'completed', 'source_changed_during_run')})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    raise SystemExit(int(result['failed_run_count'] > 0 or result['source_changed_during_run']))
