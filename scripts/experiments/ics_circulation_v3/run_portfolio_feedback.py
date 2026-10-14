"""Same 24 development cells with retained strong order incumbents."""
import argparse
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .joint_feedback import run_feedback_episode
from .portfolio_feedback import PortfolioFeedbackPlanner
from .run_joint_feedback import save
from .run_multi_load_feedback import scenes


def run(output):
    output = create_output_directory(output)
    source = Path(__file__).parent
    names = ('run_portfolio_feedback.py', 'portfolio_feedback.py', 'run_multi_load_feedback.py',
             'adaptive_order_feedback.py', 'joint_feedback.py', 'feedback_scenarios.py', 'phase4_control.py',
             'runtime.py', 'model.py', 'prebalance.py', 'learning.py', 'evaluation.py',
             'conditional_evaluation.py', 'routing.py', 'routing_reference.py',
             'experiment_protocol.py', 'run_joint_feedback.py')
    hashes = {n: sha256((source / n).read_bytes()).hexdigest() for n in names}
    (output / 'source_snapshot').mkdir()
    for name in names:
        shutil.copyfile(source / name, output / 'source_snapshot' / name)
    cases = scenes()
    modes = ('adaptive_two_orders', 'feedback_with_order_incumbents')
    save(output / 'protocol.json', {'scope': 'development_reuse_of_all_24_multi_load_cells',
        'source_sha256': hashes, 'scenes': [s.name for s in cases], 'modes': modes, 'planned_runs': 48,
        'controls': {'planning_horizon': 20, 'candidate_count': 4, 'max_rollouts': 16, 'slow_period': 2},
        'changes': 'Always offer both conventional responses before route-first single deviations. Deduplicate exact full response geometry before scoring.',
        'confirmation_claim': False, 'timing_context': 'shared development workstation',
        'monotonicity_scope': 'same boundary proxy value when scoring succeeds; not full real episode objective'})
    metrics, failures = [], []
    for scene in cases:
        runs = []
        for mode in modes:
            started, cpu = perf_counter(), process_time()
            try:
                result, history = run_feedback_episode(scene.initial, scene.forecasts, scene.future_bags, scene.horizon,
                    mode=mode, planner=PortfolioFeedbackPlanner(planning_horizon=20, max_rollouts=16))
                row = {'scene': scene.name, 'mode': mode, 'cost': result.total_cost,
                       'completed': len(result.completed), 'scheduled': len(scene.initial.bags) + len(scene.future_bags),
                       'rollouts': sum(h['rollout_attempts'] for h in history),
                       'proxy_failures': sum(len(h['failures']) for h in history),
                       'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - started}
                metrics.append(row)
                runs.append({'metrics': row, 'result': asdict(result), 'decisions': history})
            except (ValueError, AssertionError) as exc:
                row = {'scene': scene.name, 'mode': mode, 'error': type(exc).__name__, 'reason': str(exc)}
                failures.append(row)
                runs.append(row)
        save(output / (scene.name + '.json'), {'initial': asdict(scene.initial),
            'forecasts': [asdict(f) for f in scene.forecasts], 'future_driver_only': [asdict(b) for b in scene.future_bags],
            'factors': scene.factors, 'runs': runs})
        print({'scene': scene.name, 'runs': len(metrics), 'failures': len(failures)}, flush=True)
    summary = {'metrics': metrics, 'failures': failures, 'source_sha256': hashes,
               'source_changed_during_run': any(sha256((source / n).read_bytes()).hexdigest() != h for n, h in hashes.items())}
    save(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    raise SystemExit(int(bool(result['failures']) or result['source_changed_during_run']))
