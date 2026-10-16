"""Single fixed-public-input A/B cost diagnosis;60s Job, zero native calls."""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import sys
import time
import traceback
import uuid
from . import measure_public_preference_quiet as measurement


def prepare(output, corpus):
    output.mkdir(parents=True, exist_ok=False); (output / 'source').mkdir()
    plan = json.loads((corpus / 'preregistered_protocol.json').read_bytes()); case = plan['cases'][0]
    sources = {}
    for index, (path, digest) in enumerate(sorted(measurement.imported_source_pins().items())):
        target = f'{index:04d}.py'; (output / 'source' / target).write_bytes(Path(path).read_bytes())
        sources[path] = {'sha256': digest, 'archive': target}
    protocol = {'schema': 'g31.quiet_profile.v1', 'case': case['case'], 'sources': sources,
        'input': {'path': str(corpus / case['input']), 'sha256': case['input_sha256']},
        'source_protocol': {'path': str(corpus / 'preregistered_protocol.json'), 'sha256': measurement.sha(corpus / 'preregistered_protocol.json')},
        'profiles': ['A', 'B'], 'candidates_per_profile': 32, 'hard_timeout_seconds': 60., 'native_calls': 0,
        'selection': 'First case in frozen same-six-case order. No outcome or speed selection. OneAthenB; no repeats/tuning.',
        'scope': 'Full context construction, codegen/source checks/guard/input copies, action enumeration and32 predictions inside cProfile. Comparison/export outside profiler but inside owned60s worker. Profile overhead is not a benchmark.'}
    measurement.write(output / 'plan.json', protocol)


def verify(output, plan):
    for path, row in plan['sources'].items():
        if measurement.sha(path) != row['sha256'] or measurement.sha(output / 'source' / row['archive']) != row['sha256']:
            raise ValueError('source_drift')
    for key in ('input', 'source_protocol'):
        if measurement.sha(plan[key]['path']) != plan[key]['sha256']: raise ValueError('input_drift')


def worker(output):
    start = time.perf_counter(); plan_path = output / 'plan.json'; digest = measurement.sha(plan_path)
    plan = json.loads(plan_path.read_bytes()); verify(output, plan)
    if plan['profiles'] != ['A', 'B'] or plan['candidates_per_profile'] != 32 or plan['hard_timeout_seconds'] != 60.: raise ValueError('budget_changed')
    data = json.loads(Path(plan['input']['path']).read_bytes()); reports = []; results = []
    for arm in plan['profiles']:
        profile = cProfile.Profile(); started = time.perf_counter()
        try:
            profile.enable()
            context = measurement.baseline.RequestContext(data) if arm == 'A' else measurement.quiet.QuietRequestContext(data)
            values = [context.predict(action) for action in context.actions()]
        finally: profile.disable()
        elapsed = time.perf_counter() - started; stats = pstats.Stats(profile)
        path = output / (arm + '.prof'); profile.dump_stats(str(path))
        functions = [{'file': file, 'line': line, 'function': name, 'primitive_calls': row[0], 'total_calls': row[1],
            'self_seconds': row[2], 'cumulative_seconds': row[3]} for (file, line, name), row in stats.stats.items()]
        reports.append({'arm': arm, 'profile_sha256': measurement.sha(path), 'wall_with_profiler_seconds': elapsed,
            'functions': sorted(functions, key=lambda row: row['cumulative_seconds'], reverse=True)})
        results.append(values)
    if not measurement.exact32(results[0], results[1]): raise ValueError('full_output_or_count_mismatch')
    verify(output, plan)
    if measurement.sha(plan_path) != digest: raise ValueError('changed_protocol')
    measurement.write(output / 'report.json', {'status': 'completed_pure_quiet_diagnosis', 'plan_sha256': digest,
        'source_changed': [], 'native_calls': 0, 'projection_outputs': 64, 'full_output_pairs_exact': 32,
        'profiles': reports, 'wall_seconds': time.perf_counter() - start,
        'scope': 'Profiler-instrumented fixed-case source diagnosis. Not a repeated benchmark, native replay or complete-request100ms certificate.'})


def launch(output):
    if any((output / name).exists() for name in ('report.json', 'failure.json', 'stdout.log', 'external_process.json')): raise ValueError('prior_execution_exists')
    token = str(uuid.uuid4()); command = [sys.executable, '-m', __package__ + '.profile_public_preference_quiet', '--worker', '--output', str(output), '--admission', token]
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        result = measurement.bounded_windows_job.run(command, timeout=60., stdout=stdout, stderr=stderr, admission=token, cwd=str(measurement.ROOT))
    measurement.write(output / 'external_process.json', {**result, 'native_calls': 0, 'command': command})
    if result['status'] != 'exited' or result['exitcode'] != 0: raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--corpus', type=Path); p.add_argument('--admission')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare', action='store_true'); g.add_argument('--launch', action='store_true'); g.add_argument('--worker', action='store_true')
    a = p.parse_args(); a.output = a.output.resolve()
    if a.prepare: prepare(a.output, a.corpus.resolve())
    elif a.launch: launch(a.output)
    else:
        if not a.admission or sys.stdin.readline().strip() != a.admission: raise ValueError('missing_owned_job')
        try: worker(a.output)
        except Exception as exc:
            measurement.write(a.output / 'failure.json', {'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc(), 'native_calls': 0}); raise
if __name__ == '__main__': main()
