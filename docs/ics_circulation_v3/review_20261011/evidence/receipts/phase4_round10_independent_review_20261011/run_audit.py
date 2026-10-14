"""Retain every independent test attempt, input source and metered process CPU."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=ROOT)
parser.add_argument('--tests', nargs='+', default=['tests/test_ics_v3_storage_search_audit.py'])
parser.add_argument('--bridge', action='store_true')
args = parser.parse_args()
cpu, wall = process_time(), perf_counter()
for i in range(1, 10000):
    out = BASE / f'attempt_{i:03d}'
    try:
        out.mkdir()
        break
    except FileExistsError:
        continue
source = args.source.resolve()
sys.path.insert(0, str(source))
files = list((source / 'scripts/experiments/ics_circulation_v3').glob('*.py'))
files += [ROOT / p for p in args.tests]
files += [ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp']
def binding():
    return {str(p.relative_to(source) if p.is_relative_to(source) else p.relative_to(ROOT)).replace('\\','/'):
            sha256(p.read_bytes()).hexdigest() for p in files}
before = binding()
(out / 'before.json').write_text(json.dumps(before, indent=2))
for path in files:
    relative = path.relative_to(source) if path.is_relative_to(source) else path.relative_to(ROOT)
    target = out / 'source_snapshot' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
result = {'source': str(source), 'tests': args.tests, 'exception': None,
          'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
try:
    import pytest
    class Counter:
        def __init__(self):
            self.values = {'passed': 0, 'failed': 0, 'skipped': 0, 'errors': 0}
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                self.values[report.outcome] += 1
            elif report.failed:
                self.values['errors'] += 1
    counter = Counter()
    p_cpu, p_wall = process_time(), perf_counter()
    with (out / 'stdout.txt').open('w', encoding='utf-8') as stdout, (out / 'stderr.txt').open('w', encoding='utf-8') as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result['pytest_exit'] = int(pytest.main(['-q', '-p', 'no:cacheprovider', *args.tests], plugins=[counter]))
    result.update(test_outcomes=counter.values, pytest_cpu_seconds=process_time()-p_cpu,
                  pytest_wall_seconds=perf_counter()-p_wall)
    result['audit_counters'] = {name: dict(module.AUDIT_COUNTERS) for name, module in list(sys.modules.items())
                                if name.endswith('test_ics_v3_storage_search_audit')}
    result['physical_runs'] = sum(v.get('physical_runs', 0) for v in result['audit_counters'].values())
    result['physical_count_scope'] = 'Explicit calls instrumented in independent search audit only; other selected tests may run uncounted physics. Bridge child calls are separate.'
    result['exact_total_test_physical_runs'] = (result['physical_runs'] if args.tests == ['tests/test_ics_v3_storage_search_audit.py'] else None)
    if args.bridge:
        old = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_round8_independent_review_20261010/full_validation/source_snapshot'
        worker = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_round9_independent_review_20261011/direct_bridge_worker.py'
        result['bridge_worker_sha256'] = sha256(worker.read_bytes()).hexdigest()
        children = []
        for label, tree in [('round8_frozen', old), ('round10_current', source)]:
            child = subprocess.run([sys.executable, str(worker), '--source', str(tree),
                                    '--output', str(out / f'bridge_{label}.json')], cwd=ROOT, capture_output=True, text=True)
            (out / f'bridge_{label}_stdout.txt').write_text(child.stdout)
            (out / f'bridge_{label}_stderr.txt').write_text(child.stderr)
            if child.returncode:
                raise RuntimeError('bridge child failed: ' + label)
            children.append(json.loads((out / f'bridge_{label}.json').read_bytes()))
        result['bridge_exact'] = children[0]['cases'] == children[1]['cases']
        result['bridge_child_cpu_seconds'] = sum(v['cpu_seconds'] for v in children)
        result['bridge_physical_runs'] = sum(v['physical_runs'] for v in children)
except Exception:
    result['exception'] = traceback.format_exc()
after = binding()
result.update(source_changed=[p for p in before if before[p] != after[p]],
              cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
              scope='Source hashing/copy, imports, pytest and all independent oracle/physical calls. pytest interval nested; initial imports/final write excluded. Full source/test snapshot retained.')
(out / 'after.json').write_text(json.dumps(after, indent=2))
(out / 'results.json').write_text(json.dumps(result, indent=2))
print(json.dumps({'output': str(out), **result}, indent=2))
sys.exit(int(bool(result.get('pytest_exit') or result['exception'] or result['source_changed'] or
                  (args.bridge and not result.get('bridge_exact')))))
