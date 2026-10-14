"""Run frozen test files unchanged against repaired code; preserve each run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root, output = args.root.absolute(), args.output.absolute()
output.mkdir(parents=True, exist_ok=False)
manifest = json.loads((root/'docs/ics_circulation_v3/review_20261011/source_manifest.json').read_text())
original = manifest['python_source_and_tests']
tests = sorted(p for p in original if p.startswith('tests/'))
assert len(tests) == 89
new_test = 'tests/test_ics_v3_executed_audit_regressions.py'
paths = sorted([*original, new_test])
hashes = lambda: {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
before = hashes()
assert all(before[p] == original[p]['working_bytes_sha256'] for p in tests), 'Original tests changed'
env = os.environ.copy()
env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
command = [sys.executable, '-m', 'pytest', *tests, new_test, '-q', '--junitxml='+str(output/'junit.xml')]
(output/'command.json').write_text(json.dumps(command, indent=2))
started = time.perf_counter()
with (output/'stdout.log').open('wb') as stdout, (output/'stderr.log').open('wb') as stderr:
    process = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr)
wall = time.perf_counter()-started
after = hashes()
cases = list(ET.parse(output/'junit.xml').getroot().iter('testcase'))
counts = {'tests': len(cases), 'failed': sum(c.find('failure') is not None for c in cases),
          'errors': sum(c.find('error') is not None for c in cases),
          'skipped': sum(c.find('skipped') is not None for c in cases)}
counts['passed'] = counts['tests']-counts['failed']-counts['errors']-counts['skipped']
new_count = sum('test_ics_v3_executed_audit_regressions' in c.get('classname', '') for c in cases)
receipt = {'schema': 'g31_ics_v3_correctness_regression_v1', 'python': sys.version,
           'platform': platform.platform(), 'command': command, 'pytest_exitcode': process.returncode,
           'counts': counts, 'original_test_files': len(tests), 'original_test_count': len(cases)-new_count,
           'new_regression_count': new_count, 'original_test_bytes_unchanged': True,
           'wall_seconds': wall, 'cpu_seconds': None,
           'timing_scope': 'subprocess wall including pytest startup; CPU not measured; not a routing latency claim',
           'source_changed_during_test': [p for p in paths if before[p] != after[p]],
           'production_changes_since_frozen_v3': [p for p in original if before[p] != original[p]['working_bytes_sha256']]}
for name, value in [('source_before.json', before), ('source_after.json', after), ('results.json', receipt)]:
    (output/name).write_text(json.dumps(value, indent=2))
print(json.dumps(receipt, indent=2))
raise SystemExit(process.returncode or bool(receipt['source_changed_during_test']))
