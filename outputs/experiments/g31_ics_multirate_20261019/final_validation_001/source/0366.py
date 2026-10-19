"""One bounded source-only cost diagnosis; profiler times are not benchmarks."""
from __future__ import annotations
import argparse
import cProfile
import gzip
import json
from pathlib import Path
import pstats
import sys
import time
import traceback
import uuid
from . import measure_public_preference_prefix as pair


def prepare(output, corpus):
    output.mkdir(parents=True, exist_ok=False); (output / 'source').mkdir()
    old_plan = json.loads((corpus / 'preregistered_protocol.json').read_bytes())
    case = old_plan['cases'][0]
    pins = pair.imported_source_pins(); archived = {}
    for index, (name, digest) in enumerate(sorted(pins.items())):
        target = f'{index:04d}.py'; (output / 'source' / target).write_bytes(Path(name).read_bytes())
        archived[name] = {'sha256': digest, 'archive': target}
    plan = {'schema': 'g31.prefix_profile.v1', 'case': case['case'],
        'corpus_plan': {'path': str(corpus / 'preregistered_protocol.json'), 'sha256': pair.sha(corpus / 'preregistered_protocol.json')},
        'input': {'path': str(corpus / case['input']), 'sha256': case['input_sha256']},
        'raw': {'path': case['raw_path'], 'sha256': case['raw_sha256']}, 'sources': archived,
        'hard_timeout_seconds': 60., 'native_calls': 0, 'profile_calls': 6, 'prediction_outputs': 80,
        'order': ['initial_A', 'initial_B', 'first_return_A', 'first_return_B', 'first_reuse_route_A', 'first_reuse_route_B'],
        'selection': 'First case/vector00 fixed by the existing six-case order, not selected by speed or favorable completion.',
        'scope': 'cProfile covers complete context construction, all guard/source/AST/copy work, candidate enumeration and full predictions. Output equality and report export are outside profiler but inside the60s owned worker. No discarded profile runs; no performance-certification interpretation.',
        'failure': 'Preserve timeout, source drift and every mismatch; no changing the frozen002 candidate.'}
    pair.write(output / 'plan.json', plan)
    pair.write(output / 'prepare_receipt.json', {'status': 'prepared_no_execution', 'plan_sha256': pair.sha(output / 'plan.json'), 'native_calls': 0})


def verify(output, plan):
    for name, row in plan['sources'].items():
        if pair.sha(name) != row['sha256'] or pair.sha(output / 'source' / row['archive']) != row['sha256']:
            raise ValueError('source_drift:' + name)
    for key in ('corpus_plan', 'input', 'raw'):
        if pair.sha(plan[key]['path']) != plan[key]['sha256']: raise ValueError('evidence_drift:' + key)


def profile_call(output, name, callback):
    profiler = cProfile.Profile(); started = time.perf_counter()
    try:
        profiler.enable(); value = callback()
    finally: profiler.disable()
    elapsed = time.perf_counter() - started
    path = output / (name + '.prof'); profiler.dump_stats(str(path)); stats = pstats.Stats(profiler)
    functions = [{'file': file, 'line': line, 'function': function, 'primitive_calls': row[0],
                  'total_calls': row[1], 'self_seconds': row[2], 'cumulative_seconds': row[3]}
                 for (file, line, function), row in stats.stats.items()]
    return value, {'profile': name, 'profile_artifact_sha256': pair.sha(path),
        'wall_with_profiler_seconds': elapsed, 'total_profile_self_seconds': stats.total_tt,
        'functions': sorted(functions, key=lambda row: row['cumulative_seconds'], reverse=True)}


def worker(output):
    start = time.perf_counter(); plan_path = output / 'plan.json'; digest = pair.sha(plan_path)
    plan = json.loads(plan_path.read_bytes()); verify(output, plan)
    if plan['profile_calls'] != 6 or plan['prediction_outputs'] != 80 or plan['hard_timeout_seconds'] != 60.:
        raise ValueError('changed_budget')
    initial = json.loads(Path(plan['input']['path']).read_bytes())
    raw = json.loads(gzip.decompress(Path(plan['raw']['path']).read_bytes()))
    if pair.encoded(initial) != pair.encoded(raw['initial_owners']['A']['information']['bundle']):
        raise ValueError('initial_public_input_mismatch')
    def initial_call(cls):
        context = cls(initial)
        return [context.predict(action) for action in context.actions()]
    profiles = []; checks = []; outputs = 0
    left, record = profile_call(output, 'initial_A', lambda: initial_call(pair.baseline.RequestContext)); profiles.append(record)
    right, record = profile_call(output, 'initial_B', lambda: initial_call(pair.candidate.PrefixContext)); profiles.append(record)
    if not pair.exact_outputs(left, right, 32): raise ValueError('initial_profile_mismatch')
    checks.append({'phase': 'initial', 'count': 32, 'exact': True}); outputs += len(left) + len(right)
    decisions = [row for owner in ('A', 'B') for row in raw['decisions'][owner]]
    if [row['phase'] for row in decisions] != ['first_return', 'first_reuse_route']: raise ValueError('later_phase_denominator')
    for decision in decisions:
        info = decision['information']; data = info.get('bundle', {})
        if data.get('status') == 'conditional_model_input': data = pair.bind_supplied_bundle(data, info['raw_endpoints']['view'])
        def later_b():
            context = pair.candidate.LaterPrefixContext(data)
            return [context.predict(action) for action in context.actions()]
        left, record = profile_call(output, decision['phase'] + '_A', lambda: [pair.candidate.later.predict(data, action) for action in pair.candidate.later.ACTIONS]); profiles.append(record)
        right, record = profile_call(output, decision['phase'] + '_B', later_b); profiles.append(record)
        if not pair.exact_outputs(left, right, 4): raise ValueError('later_profile_mismatch')
        checks.append({'phase': decision['phase'], 'count': 4, 'exact': True}); outputs += len(left) + len(right)
    verify(output, plan)
    if pair.sha(plan_path) != digest or [r['profile'] for r in profiles] != plan['order'] or outputs != 80:
        raise ValueError('plan_or_executed_denominator_changed')
    pair.write(output / 'report.json', {'status': 'completed_pure_cost_diagnosis', 'plan_sha256': digest,
        'source_changed': [], 'native_calls': 0, 'profiles': profiles, 'checks': checks,
        'prediction_outputs': outputs, 'wall_seconds': time.perf_counter() - start,
        'scope': 'Profiler-instrumented retrospective source cost diagnosis. Not an uninstrumented benchmark, native validation, new policy or complete-request100ms claim.'})


def launch(output):
    if any((output / name).exists() for name in ('report.json', 'failure.json', 'external_process.json', 'stdout.log')):
        raise ValueError('prior_execution_exists')
    token = str(uuid.uuid4()); command = [sys.executable, '-m', __package__ + '.profile_public_preference_prefix', '--worker', '--output', str(output), '--admission', token]
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        result = pair.bounded_windows_job.run(command, timeout=60., stdout=stdout, stderr=stderr, admission=token, cwd=str(pair.ROOT))
    pair.write(output / 'external_process.json', {**result, 'native_calls': 0, 'command': command})
    if result['status'] != 'exited' or result['exitcode'] != 0: raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--corpus', type=Path); p.add_argument('--admission')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare', action='store_true'); g.add_argument('--launch', action='store_true'); g.add_argument('--worker', action='store_true')
    a = p.parse_args(); a.output = a.output.resolve()
    if a.prepare: prepare(a.output, a.corpus.resolve())
    elif a.launch: launch(a.output)
    else:
        if not a.admission or sys.stdin.readline().strip() != a.admission: raise ValueError('missing_job_admission')
        try: worker(a.output)
        except Exception as exc:
            pair.write(a.output / 'failure.json', {'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc(), 'native_calls': 0}); raise
if __name__ == '__main__': main()
