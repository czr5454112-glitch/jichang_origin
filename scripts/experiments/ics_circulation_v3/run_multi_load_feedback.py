"""Multiple loaded decisions compete with the same finite donor pool/corridor.

Development follow-up to single-load experiments where feedback tied the
cheaper two-order comparator. All cells and all four controls are retained.
"""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, process_time

from .adaptive_order_feedback import AdaptiveOrderPlanner
from .experiment_protocol import create_output_directory
from .feedback_scenarios import feedback_scene
from .joint_feedback import run_feedback_episode
from .learning import RoutingDemandForecast
from .model import Bag, Tray
from .run_joint_feedback import save


def scenes():
    result = []
    for length in (2, 4):
        for loaded_count in (2, 3):
            for donor_count in (1, 2):
                for urgency in ('mixed', 'all_slack', 'all_urgent'):
                    scene = feedback_scene(shared_travel=length, detour_extra=3)
                    state = scene.initial.clone()
                    state.network = replace(state.network, nodes={
                        n: replace(v, capacity=4) for n, v in state.network.nodes.items()})
                    state.bags, state.trays = {}, {}
                    for i in range(loaded_count):
                        urgent = urgency == 'all_urgent' or (urgency == 'mixed' and i == 0)
                        state.bags[f'loaded:{i}'] = Bag(f'loaded:{i}', 'S', 'G', 0, length + 3 if urgent else 40)
                        state.trays[f'loaded:{i}'] = Tray(f'loaded:{i}', 'S', 'loaded', f'loaded:{i}')
                    state.trays.update({f'donor:{i}': Tray(f'donor:{i}', 'C') for i in range(donor_count)})
                    forecasts, future = [], []
                    for i, at in enumerate((length + 2, length + 4)):
                        identity = f'need:{i}'
                        forecasts.append(RoutingDemandForecast(identity, 'B', 'C', at, at + 20, unit_ids=(identity,)))
                        future.append(Bag(identity, 'B', 'C', at, at + 20))
                    result.append(replace(scene, name=f'L{length}_loads{loaded_count}_donors{donor_count}_{urgency}',
                        initial=state, forecasts=tuple(forecasts), future_bags=tuple(future), horizon=40,
                        factors={**scene.factors, 'loaded_count': loaded_count, 'donor_count': donor_count,
                                 'urgency': urgency, 'node_capacity': 4,
                                 'purpose': 'shared_corridor_multiple_simultaneous_loaded_decisions_and_finite_donor_pool'}))
    return tuple(result)


def run(output):
    output = create_output_directory(output)
    source = Path(__file__).parent
    names = ('run_multi_load_feedback.py', 'adaptive_order_feedback.py', 'joint_feedback.py',
             'feedback_scenarios.py', 'phase4_control.py', 'runtime.py', 'model.py', 'prebalance.py',
             'learning.py', 'evaluation.py', 'conditional_evaluation.py', 'routing.py',
             'routing_reference.py', 'experiment_protocol.py', 'run_joint_feedback.py')
    hashes = {n: sha256((source / n).read_bytes()).hexdigest() for n in names}
    (output / 'source_snapshot').mkdir()
    for name in names:
        shutil.copyfile(source / name, output / 'source_snapshot' / name)
    cases = scenes()
    modes = ('route_then_prebalance', 'prebalance_then_route', 'one_round_feedback', 'adaptive_two_orders')
    save(output / 'protocol.json', {'scope': '24_cell_development_followup_not_independent_confirmation',
        'source_sha256': hashes, 'cases': [c.name for c in cases], 'factors': [c.factors for c in cases],
        'modes': modes, 'planned_runs': len(cases) * len(modes),
        'controls': {'planning_horizon': 20, 'candidate_count': 4, 'max_rollouts': 16,
                     'slow_period': 2, 'expansion_limit': 2000, 'route_mode': 'whole_route'},
        'unchanged_budgets': 'max_rollouts16 allows baseline plus all three alternatives per each of three loads; all actual work recorded',
        'fixed_truth_and_forecasts': 'both demand units match published forecast; uncertainty is a separate diagnostic',
        'failure_denominator': 'all cells including pending, failed planning and runtime exceptions retained',
        'claim_limit': 'Multiple choices in a shared corridor; no general joint optimality, airport calibration or learning result.'})
    metrics, failures = [], []
    for scene in cases:
        raw = {'initial': asdict(scene.initial), 'factors': scene.factors,
               'forecasts': [asdict(f) for f in scene.forecasts],
               'future_driver_only': [asdict(b) for b in scene.future_bags], 'runs': []}
        for mode in modes:
            started, cpu = perf_counter(), process_time()
            try:
                result, history = run_feedback_episode(scene.initial, scene.forecasts, scene.future_bags, scene.horizon,
                    mode=mode, planner=AdaptiveOrderPlanner(planning_horizon=20, max_rollouts=16))
                row = {'scene': scene.name, 'mode': mode, 'status': 'completed_run', 'cost': result.total_cost,
                       'scheduled': len(scene.initial.bags) + len(scene.future_bags), 'completed': len(result.completed),
                       'uncompleted': list(result.uncompleted_bag_ids),
                       'rollouts': sum(h['rollout_attempts'] for h in history),
                       'selection_changes': sum(h['actual_route_changed'] for h in history),
                       'proxy_failures': sum(len(h['failures']) for h in history),
                       'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - started}
                raw['runs'].append({'metrics': row, 'result': asdict(result), 'decisions': history})
                metrics.append(row)
            except (ValueError, AssertionError) as exc:
                row = {'scene': scene.name, 'mode': mode, 'status': 'failed',
                       'error': type(exc).__name__, 'reason': str(exc), 'wall_seconds': perf_counter() - started}
                failures.append(row)
                metrics.append(row)
                raw['runs'].append({'metrics': row})
        save(output / (scene.name + '.json'), raw)
        print({'scene': scene.name, 'runs': len(metrics), 'failures': len(failures)}, flush=True)
    summary = {'metrics': metrics, 'failures': failures, 'source_sha256': hashes,
               'source_changed_during_run': any(sha256((source / n).read_bytes()).hexdigest() != h for n, h in hashes.items())}
    save(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    outcome = run(parser.parse_args().output)
    raise SystemExit(int(bool(outcome['failures']) or outcome['source_changed_during_run']))
