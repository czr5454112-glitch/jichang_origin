"""One-off read-only current later-state profile; never creates a native session."""
import sys

if '--worker' in sys.argv:
    admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != admission:
        raise SystemExit('missing_parent_job_admission')

import cProfile
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import secrets
import time
import traceback

ROOT = Path('C:/PROGRAMING/czr005/.g31_ics_circulation_worktree')
OUTPUT = Path(__file__).resolve().parent / 'repaired_002'
OUTPUT.mkdir(exist_ok=True)
RAW = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/later_episodes_001/guarded_default/episode/native/raw.json.gz'
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def profile_rows(profile):
    statistics = pstats.Stats(profile)
    rows = [{'file': filename, 'line': line, 'function': function,
             'primitive_calls': values[0], 'total_calls': values[1],
             'self_seconds': values[2], 'cumulative_seconds': values[3]}
            for (filename, line, function), values in statistics.stats.items()]
    file_self = {}
    for row in rows:
        file_self[row['file']] = file_self.get(row['file'], 0.) + row['self_seconds']
    return {'top_cumulative': sorted(rows, key=lambda row: row['cumulative_seconds'], reverse=True)[:35],
            'top_exclusive': sorted(rows, key=lambda row: row['self_seconds'], reverse=True)[:35],
            'exclusive_by_file': sorted(file_self.items(), key=lambda row: row[1], reverse=True),
            'total_calls': statistics.total_calls, 'primitive_calls': statistics.prim_calls,
            'total_profiled_seconds': statistics.total_tt}


def worker():
    from scripts.experiments.g31_ics_circulation import foundation_later_seed as model
    from scripts.experiments.g31_ics_circulation import live_obligation_delivered_context as delivered
    raw = json.loads(gzip.decompress(RAW.read_bytes()))
    source_paths = sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, '__file__', None) and str(module.__file__).endswith('.py')
        and Path(module.__file__).resolve().is_relative_to(ROOT)
        and not Path(module.__file__).resolve().is_relative_to(ROOT / 'outputs')})
    pins = {str(path): sha(path) for path in source_paths}
    write(OUTPUT / 'plan.json', {'schema': 'g31.later_current_profile.v1', 'hard_process_seconds': 60,
        'raw': {'path': str(RAW), 'sha256': sha(RAW)}, 'source_sha256': pins,
        'probe_sha256': sha(__file__), 'native_calls': 0,
        'method': 'One unprofiled and one cProfile invocation per stage and owner; no event-crossing cache'})
    report = {'schema': 'g31.later_current_profile.v1', 'status': 'unknown', 'stages': [],
        'native_calls': 0, 'sources_modified': False, 'independent_scenarios': 1,
        'timing_scope': 'Offline saved current-state conditionals; cProfile overhead explicitly separated',
        'source_check_scope': 'physics.check_sources runs during current_run construction at import, not each predict'}
    def segment(owner, name, factory, summarize):
        operation = factory()
        started = time.perf_counter_ns()
        value = operation()
        elapsed = (time.perf_counter_ns() - started) / 1e6
        unprofiled = summarize(value)
        operation = factory()
        profile = cProfile.Profile()
        started = time.perf_counter_ns()
        profile.enable()
        try:
            value = operation()
        finally:
            profile.disable()
        profiled_ms = (time.perf_counter_ns() - started) / 1e6
        captured = summarize(value)
        profile.dump_stats(str(OUTPUT / (owner + '_' + name + '.prof')))
        row = {'owner': owner, 'stage': name, 'unprofiled_wall_ms': elapsed,
            'profiled_wall_ms': profiled_ms, 'unprofiled_result': unprofiled,
            'profiled_result': captured, 'result_signature_exact': unprofiled == captured,
            **profile_rows(profile)}
        report['stages'].append(row)
        write(OUTPUT / (owner + '_' + name + '.json'), row)
    def summary(value):
        return {'status': value.get('status'),
            'sha256': hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
            'completion': value.get('completion'), 'event_count': value.get('event_count')}
    try:
        segment('shared', 'source_checks', lambda: model.physics.check_sources, lambda value: {'returned_none': value is None})
        for transition in raw['later_transitions']:
            owner = transition['owner']
            saved_seed = transition['model_report']['seed']
            evidence = saved_seed['evidence']
            actions = model.ACTIONS[evidence['phase']]
            segment(owner, 'build_seed', lambda: lambda: model.build_seed(evidence), summary)
            segment(owner, 'revalidate_seed', lambda: lambda: model.revalidate_seed(saved_seed), summary)
            segment(owner, 'projection_initialization', lambda: lambda: model.Projection(saved_seed, actions[0]),
                    lambda value: {'at': value.time, 'trays': sorted(value.trays), 'events': len(value.events)})
            segment(owner, 'event_loop', lambda: model.Projection(saved_seed, actions[0]).run, summary)
            segment(owner, 'two_candidate_predict',
                lambda: lambda: {action: model.predict(saved_seed, action) for action in actions},
                lambda value: {action: summary(prediction) for action, prediction in value.items()})
        report['sources_unchanged'] = all(sha(path) == expected for path, expected in pins.items())
        report['all_profiled_results_exact'] = all(row['result_signature_exact'] for row in report['stages'])
        report['status'] = 'completed_current_state_profile' if report['sources_unchanged'] and report['all_profiled_results_exact'] else 'unknown_changed_or_nonrepeatable'
    except Exception:
        report['exception'] = traceback.format_exc()
    write(OUTPUT / 'report.json', report)
    print(json.dumps({'status': report['status'], 'stages': len(report['stages'])}))
    return report['status'] == 'completed_current_state_profile'


def launch():
    from scripts.experiments.g31_ics_circulation import bounded_windows_job
    write(OUTPUT / 'launch.json', {'hard_process_seconds': 60, 'automatic_retries': 0,
        'probe_sha256': sha(__file__), 'native_calls': 0})
    admission = secrets.token_hex(24)
    with (OUTPUT / 'stdout.log').open('x') as stdout, (OUTPUT / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--admission', admission],
            timeout=60, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    complete = process['status'] == 'exited' and process['exitcode'] == 0 and (OUTPUT / 'report.json').exists()
    write(OUTPUT / 'receipt.json', {'status': 'completed' if complete else 'unknown_incomplete', 'process': process,
        'automatic_retries': 0, 'native_calls': 0})
    print(json.dumps(process))


if __name__ == '__main__':
    if '--worker' in sys.argv:
        raise SystemExit(0 if worker() else 1)
    launch()


