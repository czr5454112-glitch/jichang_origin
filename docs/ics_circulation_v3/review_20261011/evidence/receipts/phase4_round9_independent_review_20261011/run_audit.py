"""Meter independent tests and frozen/new direct bridge, preserving failures."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import shutil
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--bridge', action='store_true')
parser.add_argument('--snapshot', action='store_true')
parser.add_argument('--tests', nargs='*', default=['tests/test_ics_v3_storage_audit.py'])
args = parser.parse_args()
cpu, wall = process_time(), perf_counter()
sys.path.insert(0, str(ROOT))
attempt = 1
while True:
    output = BASE / f'attempt_{attempt:03d}'
    try:
        output.mkdir()
        break
    except FileExistsError:
        attempt += 1

files = sorted((ROOT / 'scripts/experiments/ics_circulation_v3').glob('*.py'))
files += [ROOT / name for name in args.tests]
files += [ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp']
def bindings():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in files}

before = bindings()
(output / 'before.json').write_text(json.dumps(before, indent=2))
if args.snapshot:
    for path in files:
        target = output / 'source_snapshot' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
outcome = {'tests': args.tests, 'bridge': None, 'exception': None}
try:
    import pytest
    class CountTests:
        def __init__(self):
            self.counts = {'passed': 0, 'failed': 0, 'skipped': 0, 'errors': 0}
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                self.counts[report.outcome] += 1
            elif report.failed:
                self.counts['errors'] += 1
            elif report.skipped:
                self.counts['skipped'] += 1
    counter = CountTests()
    test_cpu, test_wall = process_time(), perf_counter()
    with (output / 'pytest_stdout.txt').open('w', encoding='utf-8') as stdout, (output / 'pytest_stderr.txt').open('w', encoding='utf-8') as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            outcome['pytest_exit'] = int(pytest.main(['-q', '-p', 'no:cacheprovider', *args.tests], plugins=[counter]))
    outcome['test_outcomes'] = counter.counts
    outcome['pytest_cpu_seconds'] = process_time() - test_cpu
    outcome['pytest_wall_seconds'] = perf_counter() - test_wall
    if args.bridge:
        bridge = []
        old = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_round8_independent_review_20261010/full_validation/source_snapshot'
        for label, source in (('round8_frozen', old), ('round9_current', ROOT)):
            result = subprocess.run([sys.executable, str(BASE / 'direct_bridge_worker.py'), '--source', str(source),
                                     '--output', str(output / f'bridge_{label}.json')], cwd=ROOT, text=True, capture_output=True)
            (output / f'bridge_{label}_stdout.txt').write_text(result.stdout, encoding='utf-8')
            (output / f'bridge_{label}_stderr.txt').write_text(result.stderr, encoding='utf-8')
            bridge.append({'source': label, 'exit': result.returncode})
        outcome['bridge'] = bridge
        if all(row['exit'] == 0 for row in bridge):
            old_result = json.loads((output / 'bridge_round8_frozen.json').read_text())
            new_result = json.loads((output / 'bridge_round9_current.json').read_text())
            outcome['bridge_exact'] = old_result['cases'] == new_result['cases']
            outcome['bridge_child_cpu_seconds'] = old_result['cpu_seconds'] + new_result['cpu_seconds']
            outcome['bridge_physical_runs'] = old_result['physical_runs'] + new_result['physical_runs']
except Exception as exc:
    import traceback
    outcome['exception'] = traceback.format_exc()
after = bindings()
outcome.update(source_changed=[p for p in before if before[p] != after[p]],
               parent_cpu_seconds=process_time() - cpu, parent_wall_seconds=perf_counter() - wall,
               scope='Parent CPU includes pytest/import/binding checks; pytest CPU is nested, do not add. Bridge child CPU separate. Parent wall overlaps children. Initial interpreter imports/final writes are excluded; auxiliary reading/editing CPU unknown.')
(output / 'after.json').write_text(json.dumps(after, indent=2))
(output / 'resource.json').write_text(json.dumps(outcome, indent=2))
print(json.dumps({'output': str(output), **outcome}, indent=2))
sys.exit(int(bool(outcome.get('pytest_exit') or outcome['exception'] or outcome['source_changed'] or
                  (args.bridge and (not outcome.get('bridge_exact'))))))
