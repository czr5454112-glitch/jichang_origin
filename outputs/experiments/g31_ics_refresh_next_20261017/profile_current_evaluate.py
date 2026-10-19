"""Bounded profiling of new evaluate on saved actual current native evidence."""
from __future__ import annotations

import sys

if '--worker' in sys.argv:
    expected = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected:
        raise SystemExit('profile_current:missing_parent_admission')

import argparse
import copy
import cProfile
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import secrets
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / 'outputs/experiments/g31_ics_service_update_20261017/native_002/guarded_default/episode/native'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False))


def pins():
    paths = set((ROOT / 'scripts/experiments/g31_ics_circulation').glob('*.py'))
    paths.update((ROOT / 'src/czr005').rglob('*.py'))
    paths.add(ROOT / 'scripts/eval/run_g4irsf28_service_potential.py')
    paths.add(Path(__file__).resolve())
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


def changed(plan):
    return [path for path, expected_sha in plan['source_pins'].items() if sha(path) != expected_sha]


def stats_report(profile):
    stats = pstats.Stats(profile)
    rows = []
    for identity, values in stats.stats.items():
        primitive, calls, own, cumulative, callers = values
        rows.append({'file': identity[0], 'line': identity[1], 'function': identity[2],
            'primitive_calls': primitive, 'calls': calls, 'exclusive_ms': own * 1000,
            'cumulative_ms': cumulative * 1000,
            'callers': [{'file': caller[0], 'line': caller[1], 'function': caller[2],
                'raw_cprofile_tuple': list(counts) if isinstance(counts, tuple) else counts}
                for caller, counts in callers.items()]})
    selectors = {
        'dynamic_guard_subtrees': lambda row: row['function'] in ('later_context', 'revalidate',
            'validate_collected_endpoints', 'validate_later_pair', 'later_bundle', 'build_seed'),
        'strict_public_json': lambda row: row['function'] in ('payload_encoding', 'check', 'encoded', 'request_checked')
            and any(name in row['file'] for name in ('historical_adapter', 'delivered_context', 'foundation_later_seed')),
        'json_codec': lambda row: 'json' in row['file'] or 'json' in row['function'],
        'deepcopy': lambda row: Path(row['file']).name == 'copy.py',
        'static_catalog': lambda row: row['function'] in ('inputs', 'fixed_contracts', 'service_aware_potential'),
        'source_checks': lambda row: row['function'] in ('path_sha', 'check_sources', 'read_bytes', 'close')
            or '_path' in row['function'] and 'pathlib' in row['file'],
        'physical_event_loop': lambda row: row['file'] == '<foundation_current_state_physical_loop>'
            or row['function'] in ('seed_current', 'try_depart', 'choose_next', 'score', 'schedule'),
        'candidate_and_request': lambda row: row['function'] in ('evaluate', 'predict', '__init__')
            and 'foundation_' in row['file'],
    }
    categories = {}
    for name, select in selectors.items():
        selected = [row for row in rows if select(row)]
        categories[name] = {'selected_exclusive_sum_ms': sum(row['exclusive_ms'] for row in selected),
            'rows': sorted(selected, key=lambda row: row['cumulative_ms'], reverse=True)}
    return {'total_profiled_exclusive_ms': sum(row['exclusive_ms'] for row in rows),
        'primitive_calls': stats.prim_calls, 'total_calls': stats.total_calls,
        'top_cumulative': sorted(rows, key=lambda row: row['cumulative_ms'], reverse=True)[:35],
        'top_exclusive': sorted(rows, key=lambda row: row['exclusive_ms'], reverse=True)[:35],
        'categories': categories,
        'limits': 'Categories overlap. Cumulative values include descendants and must not be summed; profiler timings are not uninstrumented latency.'}


def comparable(report):
    return {name: report[name] for name in ('status', 'seed', 'candidate_results')}


def worker(output, plan_sha):
    from scripts.experiments.g31_ics_circulation import foundation_later_seed as model
    output = Path(output)
    plan = json.loads((output / 'plan.json').read_text())
    result = {'schema': 'g31.refresh_next.current_evaluate_profile.v1', 'status': 'unknown', 'contexts': [],
        'native_executions': 0, 'legacy_evaluations': 0, 'production_mutations': 0,
        'complete_request_100ms_certified': False,
        'timing_scope': 'evaluate only; excludes caller copy, source import, output detachment and collection/submit/ACK.',
        'sample_limit': 'One unprofiled and one cProfile call per actual A/B context, not a latency distribution.'}
    try:
        assert sha(output / 'plan.json') == plan_sha and not changed(plan)
        assert sha(SOURCE / 'raw.json.gz') == plan['raw_sha256']
        receipt = json.loads((SOURCE / 'receipt.json').read_text())
        assert receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
        assert receipt['raw_artifact']['sha256'] == plan['raw_sha256']
        raw = json.loads(gzip.decompress((SOURCE / 'raw.json.gz').read_bytes()))
        for owner in ('A', 'B'):
            transition = next(row for row in raw['later_transitions'] if row['owner'] == owner)
            saved = transition['model_report']
            evidence = copy.deepcopy(saved['seed']['evidence'])
            actions = list(saved['candidate_results'])
            started = time.perf_counter_ns()
            unprofiled = model.evaluate(evidence, actions)
            wall_ms = (time.perf_counter_ns() - started) / 1e6
            assert encoded(comparable(unprofiled)) == encoded(comparable(saved))
            evidence = copy.deepcopy(saved['seed']['evidence'])
            profile = cProfile.Profile()
            started = time.perf_counter_ns()
            profile.enable()
            profiled = model.evaluate(evidence, actions)
            profile.disable()
            profile_wall_ms = (time.perf_counter_ns() - started) / 1e6
            assert encoded(comparable(profiled)) == encoded(comparable(saved))
            path = output / (owner + '.prof')
            profile.dump_stats(path)
            details = stats_report(profile)
            row = {'owner': owner, 'at': evidence['at'], 'phase': evidence['phase'],
                'unprofiled_evaluate_wall_ms': wall_ms, 'profiled_evaluate_wall_ms': profile_wall_ms,
                'complete_seed_and_two_predictions_exact': True, 'evaluation': profiled['evaluation'],
                'json_bytes': {name: len(encoded(value).encode()) for name, value in (
                    ('evidence', evidence), ('seed', saved['seed']),
                    ('candidate_results', saved['candidate_results']), ('bundle', saved['seed']['bundle']))},
                'profile': {'path': str(path.resolve()), 'sha256': sha(path)}, 'stats': details}
            write_new(output / (owner + '_profile.json'), row)
            result['contexts'].append(row)
        assert sha(output / 'plan.json') == plan_sha and not changed(plan)
        assert sha(SOURCE / 'raw.json.gz') == plan['raw_sha256']
        result.update(status='completed_exact_current_evaluate_profile', source_exit_pins_passed=True)
    except Exception:
        result['exception'] = traceback.format_exc()
    write_new(output / 'report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.worker:
        return 0 if worker(args.output, args.plan_sha256)['status'].startswith('completed_') else 1
    from scripts.experiments.g31_ics_circulation import bounded_windows_job
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT):
        raise SystemExit('fresh_workspace_output_required')
    output.mkdir(parents=True)
    plan = {'source_pins': pins(), 'raw_path': str(SOURCE / 'raw.json.gz'),
        'raw_sha256': sha(SOURCE / 'raw.json.gz'), 'receipt_sha256': sha(SOURCE / 'receipt.json'),
        'owners': ['A', 'B'], 'hard_seconds': 60, 'automatic_retries': 0}
    write_new(output / 'plan.json', plan)
    plan_sha = sha(output / 'plan.json')
    admission = secrets.token_hex(24)
    with (output / 'stdout.txt').open('x') as stdout, (output / 'stderr.txt').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--output', str(output), '--plan-sha256', plan_sha, '--admission', admission],
            timeout=60, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    report = json.loads((output / 'report.json').read_text()) if (output / 'report.json').exists() else {}
    changed_sources = changed(plan)
    complete = process['status'] == 'exited' and process['exitcode'] == 0 and not changed_sources
    receipt = {'status': 'completed' if complete else 'unknown_failed', 'process': process,
        'source_changed': changed_sources, 'report_status': report.get('status')}
    write_new(output / 'receipt.json', receipt)
    print(json.dumps(receipt))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
