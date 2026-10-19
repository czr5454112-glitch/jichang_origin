"""Bounded one-record offline profile; no labels, fitting, or native loading."""
from __future__ import annotations
import sys
TOKEN = 'g31_airport_public_profile_one_record_v1'
if __name__ == '__main__' and '--run' in sys.argv:
    if sys.stdin.readline().strip() != TOKEN:
        raise SystemExit('airport_public_profile:bounded_parent_admission_required')

import argparse
import copy
import cProfile
import gzip
import hashlib
import io
import json
from pathlib import Path
import pstats
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_public_profile'


def require(value, reason):
    if not value: raise ValueError('airport_public_profile:' + reason)


def read(path): return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def prepare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_output')
    audit_plan_path = BASE/'B2_public_feature_audit_002/plan.json'
    audit_plan = read(audit_plan_path)
    sources = {**audit_plan['source_sha256'], str(Path(__file__).resolve()): ref(__file__)['sha256']}
    plan = {'schema': 'g31.airport_public_profile_one_record.v1', 'status': 'prepared_not_executed',
        'output': str(output), 'audit_plan': ref(audit_plan_path), 'sources': sources,
        'saved_feature_rows': ref(BASE/'B2_public_feature_audit_002/public_feature_rows.jsonl.gz'),
        'native_branches': 0, 'fit_calls': 0, 'outcome_labels_created': 0,
        'selection': 'first_actual_trace_record_with_recorded_proposals_within_first64',
        'max_records_scanned': 64, 'profiled_repetitions': 1, 'unprofiled_repetitions': 1,
        'soft_wall_seconds': 45, 'profile_timer': 'explicit_perf_counter_wall_seconds',
        'stage_clocks': ['perf_counter_ns_wall', 'thread_time_ns_current_thread_CPU'],
        'frozen_B1_modified': False}
    output.mkdir(parents=True); write(output/'plan.json', plan)
    task = {'task_id': output.name, 'module': MODULE, 'args': ['--run', '--output', str(output)],
        'native_branches': 0, 'hard_seconds': 60, 'inner_admission': TOKEN,
        'sources': [*sources, *audit_plan['historical_collection_sources'],
            *(r['path'] for r in audit_plan['inputs'].values()), str(audit_plan_path),
            plan['saved_feature_rows']['path'], str(output/'plan.json')],
        'requires': [], 'assessment': {'path': str(output/'receipt.json'),
            'allowed_statuses': ['completed_one_record_public_profile']},
        'next_action': 'Inspect per-stage wall/CPU and explicit-wall cProfile hotspots before proposing any frozen B1 change. No native or labels.'}
    write(output.parent/(output.name+'_task.json'), task)
    return plan


def run(output):
    from . import foundation_airport_learning_audit as audit
    from . import foundation_airport_learning_public as public
    from . import foundation_action_value as value
    from . import foundation_flight_forecaster as forecaster
    output = Path(output); plan = read(output/'plan.json')
    started = time.perf_counter(); deadline = started + plan['soft_wall_seconds']
    result = {'schema': plan['schema'], 'status': 'failed_one_record_public_profile', 'plan': ref(output/'plan.json'),
        'native_branches': 0, 'fit_calls': 0, 'outcome_labels_created': 0}
    try:
        require(plan['profiled_repetitions'] == plan['unprofiled_repetitions'] == 1
            and plan['max_records_scanned'] == 64 and plan['soft_wall_seconds'] == 45, 'fixed_small_budget')
        require(all(ref(path)['sha256'] == sha for path, sha in plan['sources'].items()), 'frozen_sources')
        require(ref(plan['audit_plan']['path']) == plan['audit_plan'], 'audit_plan_digest')
        source_plan = read(plan['audit_plan']['path']); audit.validate_plan(source_plan)
        require(ref(plan['saved_feature_rows']['path']) == plan['saved_feature_rows'], 'saved_features_digest')
        row = None
        with gzip.open(source_plan['inputs']['trace']['path'], 'rt', encoding='utf8') as stream:
            for index, line in enumerate(stream):
                require(index < plan['max_records_scanned'] and time.perf_counter() < deadline, 'bounded_selection')
                candidate = json.loads(line)
                if candidate['decision']['intents']:
                    row = candidate; break
        require(row is not None, 'actual_record_with_proposals')
        with gzip.open(plan['saved_feature_rows']['path'], 'rt', encoding='utf8') as stream:
            saved = next(json.loads(line) for line in stream if json.loads(line)['sequence'] == row['sequence'])
        require(saved['status'] == 'public_features_verified_no_labels' and saved['target_value'] is None,
            'existing_legal_record_not_a_label')
        model = forecaster.validate_checkpoint(read(source_plan['inputs']['checkpoint']['path']))
        static_plan = read(source_plan['inputs']['public_plan']['path']); mapping = read(source_plan['inputs']['mapping']['path'])
        setup_wall_seconds = time.perf_counter()-started
        def pipeline():
            stages = []
            def measured(name, function):
                wall, cpu = time.perf_counter_ns(), time.thread_time_ns()
                answer = function()
                end_cpu, end_wall = time.thread_time_ns(), time.perf_counter_ns()
                stages.append({'stage': name, 'wall_ms': (end_wall-wall)/1e6,
                    'current_thread_cpu_ms': (end_cpu-cpu)/1e6})
                return answer
            wall, cpu = time.perf_counter_ns(), time.thread_time_ns()
            context = measured('static_plan_copy', lambda: copy.deepcopy(static_plan)); context['owner_scope'] = row['owner_id']
            regional = measured('B1_predict', lambda: forecaster.predict(context, model,
                now=row['now'], owner=row['owner_id'], observed_counts=None))
            projected = measured('public_role_projection', lambda: audit.project(regional, mapping))
            wrapped, accounts = measured('wrap_record', lambda: public.wrap_record(row, projected,
                episode_id='C00_cyclic_od_001', episode_end=source_plan['episode_end']))
            candidates = measured('proposal_actions', lambda: public.proposal_actions(row))
            vectors = measured('all_candidate_features', lambda: [{'action': c, 'features': value.features(wrapped, c['semantic'])}
                for c in candidates])
            encoded = measured('output_digests', lambda: {'observation_sha256': audit.digest(row['observation']),
                'forecast_sha256': audit.digest(projected), 'wrapped_observation_sha256': audit.digest(wrapped),
                'accounts_audit': accounts, 'candidates': vectors})
            elapsed = {'wall_ms': (time.perf_counter_ns()-wall)/1e6,
                'current_thread_cpu_ms': (time.thread_time_ns()-cpu)/1e6}
            require(all(saved[key] == value for key, value in encoded.items()), 'exact_saved_public_feature_parity')
            return encoded, stages, elapsed
        require(time.perf_counter() < deadline, 'remaining_profile_budget')
        baseline, baseline_stages, baseline_elapsed = pipeline()
        require(time.perf_counter() < deadline, 'remaining_second_pass_budget')
        profiler = cProfile.Profile(timer=time.perf_counter)
        profiler.enable(); profiled, profile_stages, profile_elapsed = pipeline(); profiler.disable()
        require(profiled == baseline, 'exact_profiled_data_parity')
        summary = io.StringIO(); stats = pstats.Stats(profiler, stream=summary); stats.sort_stats('cumulative').print_stats(35)
        functions = [{'file': k[0], 'line': k[1], 'function': k[2], 'primitive_calls': v[0], 'total_calls': v[1],
            'self_profile_wall_seconds': v[2], 'cumulative_profile_wall_seconds': v[3]}
            for k, v in sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:60]]
        require(all(ref(path)['sha256'] == sha for path, sha in plan['sources'].items()), 'source_exit_pins')
        result.update(status='completed_one_record_public_profile', sequence=row['sequence'], owner=row['owner_id'], now=row['now'],
            plan_entries=len(static_plan['entries']), candidate_count=len(baseline['candidates']), exact_saved_feature_parity=True,
            setup_wall_seconds=setup_wall_seconds, unprofiled_stages=baseline_stages, unprofiled_elapsed=baseline_elapsed,
            profiled_stages=profile_stages, profiled_elapsed=profile_elapsed, function_profile=functions,
            profile_text=summary.getvalue(), source_exit_pins_passed=True,
            profile_timer='explicit_perf_counter_wall_seconds', stage_cpu_scope='thread_time_current_thread_not_process_or_native_full_request',
            unknown_counts_remain_None=True, no_future_or_private_labels_read=True,
            scope='One actual public row, two frozen B1 calls, exact saved feature parity. Diagnostic only; no latency distribution or native consumption claim.')
    except Exception:
        result['exception'] = traceback.format_exc()
    result['total_wall_seconds'] = time.perf_counter()-started
    write(output/'receipt.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True); group.add_argument('--prepare', action='store_true'); group.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    result = prepare(args.output) if args.prepare else run(args.output)
    print(json.dumps({'status': result['status'], 'native_branches': 0}))
    raise SystemExit(0 if result['status'] in ('prepared_not_executed', 'completed_one_record_public_profile') else 1)
