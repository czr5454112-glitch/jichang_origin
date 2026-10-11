"""W3 development opportunity/noise audit before choosing any learning model."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, process_time

import numpy as np

from .experiment_protocol import create_output_directory
from .label_stability import (branch_with_future, collect_decisions, digest, sampled_futures,
                              stability_summary, sustained_scenes)
from .phase4_control import ControlSpec
from .run_joint_feedback import save
from .runtime import actual_action_key


SOURCES = ('run_label_stability.py', 'label_stability.py', 'feedback_scenarios.py', 'phase4_control.py',
           'runtime.py', 'model.py', 'prebalance.py', 'learning.py', 'evaluation.py',
           'conditional_evaluation.py', 'routing.py', 'routing_reference.py',
           'experiment_protocol.py', 'run_joint_feedback.py')


def run(output, *, replicates=4, futures_per_group=32):
    output = create_output_directory(output)
    source = Path(__file__).parent
    hashes = {name: sha256((source / name).read_bytes()).hexdigest() for name in SOURCES}
    (output / 'source_snapshot').mkdir()
    for name in SOURCES:
        shutil.copyfile(source / name, output / 'source_snapshot' / name)
    scenes = sustained_scenes()
    spec = ControlSpec(routing='timed', predictive=True, planning_horizon=20, slow_period=2,
                       route_mode='next_edge', candidate_count=4, expansion_limit=2000)
    save(output / 'protocol.json', {'scope': 'W3_development_diagnosis_no_training_or_unseen_confirmation',
        'source_sha256': hashes, 'scenes': [s.name for s in scenes], 'factors': [s.factors for s in scenes],
        'deployed_spec': asdict(spec), 'labels': 'restore_exact_collected_controller_checkpoint_then_intervene',
        'label_horizon_ticks': 24, 'sample_bands': [0, 20, 40], 'expanded_candidate_count': 12,
        'sampling_rule': 'first feasible soft decision in each time band; no label-dependent filtering',
        'replicate_groups': replicates, 'futures_per_group': futures_per_group, 'nested_prefixes': [2, 8, 32],
        'future_law': 'Per nominal pending task: cancel 1/8, reverse OD 1/8, keep 6/8; independent uniform arrival jitter {-2,0,2}; clip strictly after observed now. Public forecast publication schedule is held fixed.',
        'label_information': 'Offline only; scenario nominal pending tasks are not supplied to any scorer or features.',
        'forecast_quality_claim': 'Synthetic stress law, not calibrated probabilities or airport conditional posterior.',
        'coverage_claim': 'larger bounded candidate pool only, not exhaustive joint oracle',
        'drift_diagnostic': 'baseline-vs-timed observed state distributions with identical greedy predictive controller; no learned deployment yet',
        'independent_airport_day_count': 0, 'no_model_or_seed_selected_on_these_labels': True})
    all_summaries, episodes, failures = [], [], []
    branch_count = 0
    start, cpu = perf_counter(), process_time()
    for scene in scenes:
        samples, history, result = collect_decisions(scene, spec)
        alternate = ControlSpec(**{**asdict(spec), 'routing': 'baseline'})
        _, alt_history, alt_result = collect_decisions(scene, alternate)
        left = {r['time']: r['state_sha256'] for r in history}
        shifted = sum(left[r['time']] != r['state_sha256'] for r in alt_history)
        episode = {'scene': scene.name, 'timed_cost': result.total_cost, 'baseline_cost': alt_result.total_cost,
                   'timed_completed': len(result.completed), 'baseline_completed': len(alt_result.completed),
                   'scheduled': len(scene.initial.bags) + len(scene.future_bags),
                   'routing_boundaries': len(history), 'boundaries_with_eligible_load': sum(r['eligible_loaded_count'] > 0 for r in history),
                   'normal_multiple_actions': sum(r.get('normal_interventions', 0) > 1 for r in history),
                   'expanded_multiple_actions': sum(r.get('distinct_interventions', 0) > 1 for r in history),
                   'sampled_decisions': len(samples), 'baseline_vs_timed_state_hash_differences': shifted}
        episodes.append(episode)
        save(output / f'{scene.name}_episode.json', {'metrics': episode, 'initial': asdict(scene.initial),
             'nominal_future_driver_only': [asdict(b) for b in scene.future_bags],
             'forecast_publications': [asdict(f) for f in scene.forecasts],
             'timed_result': asdict(result), 'baseline_result': asdict(alt_result),
             'timed_boundaries': history, 'baseline_boundaries': alt_history})
        for sample in samples:
            checkpoint, pool = sample['checkpoint'], sample['pool']
            state = checkpoint.state
            keys = [actual_action_key(state, p, route_mode=spec.route_mode) for p in pool]
            costs, future_groups, raw_branches = [], [], []
            sample_cpu, sample_start = process_time(), perf_counter()
            for replicate in range(replicates):
                seed = int(digest([sample['identity'], 'future_group', replicate])[:16], 16)
                futures = sampled_futures(scene.future_bags, state, count=futures_per_group, seed=seed)
                future_groups.append({'seed': seed, 'tapes': [[asdict(b) for b in f] for f in futures]})
                group = []
                for candidate_index, candidate in enumerate(pool):
                    row = []
                    for future_index, future in enumerate(futures):
                        try:
                            outcome = branch_with_future(checkpoint, candidate, future, min(scene.horizon, state.now + 24))
                            row.append(outcome.total_cost)
                            raw_branches.append({'replicate': replicate, 'candidate': candidate_index,
                                'future_index': future_index, 'cost_components': outcome.cost_components,
                                'completed': outcome.completed, 'uncompleted': outcome.uncompleted_bag_ids,
                                'invariant_checks': outcome.invariant_checks})
                        except (ValueError, AssertionError) as exc:
                            failures.append({'sample': sample['identity'], 'replicate': replicate,
                                             'candidate': candidate_index, 'future_index': future_index,
                                             'error': type(exc).__name__, 'reason': str(exc)})
                            row.append(None)
                        branch_count += 1
                    group.append(row)
                costs.append(group)
            failed = any(value is None for group in costs for row in group for value in row)
            stats = None if failed else stability_summary(costs, [keys.index(k) for k in sample['normal_keys']],
                                                          [f['timed_analytic_absolute'] for f in sample['features']])
            row = {'identity': sample['identity'], 'time': state.now, 'band': sample['band'],
                   'candidate_count': len(pool), 'normal_count': len(sample['normal_keys']), 'failed': failed,
                   'cpu_seconds': process_time() - sample_cpu, 'wall_seconds': perf_counter() - sample_start,
                   'statistics': stats}
            all_summaries.append(row)
            save(output / (sample['identity'].replace(':', '_') + '.json'), {
                'summary': row, 'state': asdict(state), 'source_state_sha256': digest(asdict(state)),
                'actual_action_keys': keys, 'normal_action_keys': sample['normal_keys'],
                'proposals': [asdict(p) for p in pool], 'features_observable_only': sample['features'],
                'generation': sample['generation'], 'continuation_contract': sample['continuation_contract'],
                'checkpoint_metadata': {'phase': checkpoint.phase, 'accrued_cost': checkpoint.cost_components,
                    'next_slow_trigger_at': checkpoint.slow_controller.next_trigger_at,
                    'slow_trigger_history': checkpoint.slow_controller.trigger_times},
                'future_groups_offline_only': future_groups, 'paired_costs': costs, 'raw_branches': raw_branches})
            print({'sample': sample['identity'], 'candidates': len(pool), 'branches_total': branch_count,
                   'failed': failed, 'value_range': None if stats is None else stats['value_range']}, flush=True)
    summary = {'episodes': episodes, 'samples': all_summaries, 'branch_count': branch_count, 'failures': failures,
        'wall_seconds': perf_counter() - start, 'cpu_seconds': process_time() - cpu,
        'source_sha256': hashes,
        'source_changed_during_run': any(sha256((source / n).read_bytes()).hexdigest() != h for n, h in hashes.items()),
        'timing_context': 'shared development workstation; work counts and CPU disclosed, not production latency'}
    save(output / 'summary.json', summary)
    print({'samples': len(all_summaries), 'branches': branch_count, 'failures': len(failures),
           'source_changed_during_run': summary['source_changed_during_run']}, flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    raise SystemExit(int(bool(result['failures']) or result['source_changed_during_run']))
