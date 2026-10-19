"""Save one bounded pure-Python regression run and its exact test sources.

These tests use detached fixtures/mocked native endpoints. This does not rerun
the compiled C++ suite, native semantic gates, trained models, or campaigns.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT) and not output.exists()
    output.mkdir(parents=True)
    patterns = ('test_g31_foundation_*.py', 'test_g31_native028_*.py',
                'test_g31_airport_*.py', 'test_g31_sustained_learning_ledger.py')
    tests = sorted({p for pattern in patterns for p in (ROOT / 'tests').glob(pattern)})
    tests.append(Path(__file__).with_name('test_verifier.py'))
    tests.append(Path(__file__).with_name('test_git_content_guards.py'))
    sources = []
    for path in tests:
        data = path.read_bytes()
        archive = output / 'test_sources' / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        sources.append({'path': path.relative_to(ROOT).as_posix(),
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'archive': archive.relative_to(output).as_posix()})
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               '--basetemp=' + str(output / 'pytest_scratch'),
               '--junitxml=' + str(output / 'tests.xml'), *map(str, tests)]
    env = dict(os.environ, PYTHONPATH='src;.', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    started = time.perf_counter()
    error = None
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=180)
        stdout, stderr, exitcode = result.stdout, result.stderr, result.returncode
        status = 'passed' if exitcode == 0 else 'failed'
    except subprocess.TimeoutExpired as failure:
        stdout, stderr, exitcode = failure.stdout or b'', failure.stderr or b'', None
        status, error = 'failed_timeout', 'Pure regression exceeded its registered 180-second limit.'
    (output / 'stdout.txt').write_bytes(stdout)
    (output / 'stderr.txt').write_bytes(stderr)
    summary = None
    try:
        suites = ET.parse(output / 'tests.xml').getroot().findall('testsuite')
        if not suites:
            raise ValueError('JUnit has no testsuite')
        summary = {key: sum(int(suite.attrib.get(key, '0')) for suite in suites)
                   for key in ('tests', 'failures', 'errors', 'skipped')}
        if status == 'passed' and (summary['failures'] or summary['errors'] or not summary['tests']):
            status = 'failed'
    except (OSError, ET.ParseError, ValueError) as failure:
        if status == 'passed':
            status = 'failed_missing_or_invalid_junit'
        error = (error + ' ' if error else '') + 'JUnit: ' + str(failure)
    receipt = {'schema': 'g31.saved_final_pure_regression.v1',
               'status': status, 'exception_or_report_error': error,
               'command': command, 'exitcode': exitcode,
               'wall_seconds': time.perf_counter() - started,
               'junit': summary, 'test_source_files': sources,
               'native_campaigns_executed': 0, 'compiled_cpp_suite_executed': False,
               'source_day_training_executed': False}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('command', 'test_source_files')}))
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
