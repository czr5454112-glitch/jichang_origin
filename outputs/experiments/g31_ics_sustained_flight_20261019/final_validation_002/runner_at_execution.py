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
    parser.add_argument('--max-seconds', type=int, default=180)
    parser.add_argument('--resource-revision-reason')
    args = parser.parse_args()
    assert 1 <= args.max_seconds <= 600
    assert args.max_seconds == 180 or args.resource_revision_reason
    output = args.output.resolve()
    assert output.is_relative_to(ROOT) and not output.exists()
    output.mkdir(parents=True)
    # Windows fixtures add nested artifact paths; use a fresh short workspace path.
    basetemp = ROOT.parent / ('g31_pure_' + hashlib.sha256(str(output).encode()).hexdigest()[:12])
    assert basetemp.is_relative_to(ROOT.parent) and not basetemp.exists()
    patterns = ('test_g31_foundation_*.py', 'test_g31_native028_*.py',
                'test_g31_airport_*.py', 'test_g31_sustained_learning_ledger.py')
    tests = sorted({p for pattern in patterns for p in (ROOT / 'tests').glob(pattern)})
    tests.append(Path(__file__).with_name('test_verifier.py'))
    tests.append(Path(__file__).with_name('test_git_content_guards.py'))
    runner = Path(__file__).read_bytes()
    (output / 'runner_at_execution.py').write_bytes(runner)
    runner_identity = {'sha256': hashlib.sha256(runner).hexdigest(), 'archive': 'runner_at_execution.py'}
    sources = []
    for path in tests:
        data = path.read_bytes()
        archive = output / 'test_sources' / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        sources.append({'path': path.relative_to(ROOT).as_posix(),
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'archive': archive.relative_to(output).as_posix()})
    command = [sys.executable, '-m', 'pytest', '-o', 'addopts=', '-vv', '--durations=20',
               '--ignore-glob=*', '-p', 'no:cacheprovider',
               '--basetemp=' + str(basetemp),
               '--junitxml=' + str(output / 'tests.xml'), *map(str, tests)]
    env = dict(os.environ, PYTHONPATH='src;.', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONUNBUFFERED='1')
    started = time.perf_counter()
    error = None
    try:
        with (output / 'stdout.txt').open('wb') as stdout_file, (output / 'stderr.txt').open('wb') as stderr_file:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout_file,
                                    stderr=stderr_file, timeout=args.max_seconds)
        exitcode = result.returncode
        status = 'passed' if exitcode == 0 else 'failed'
    except subprocess.TimeoutExpired as failure:
        exitcode = None
        status, error = 'failed_timeout', 'Pure regression exceeded its declared ' + str(args.max_seconds) + '-second limit.'
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
               'declared_max_seconds': args.max_seconds,
               'resource_revision_reason': args.resource_revision_reason,
               'runner_source': runner_identity,
               'fixture_basetemp': str(basetemp),
               'collection_policy': 'All explicit test files retained; --ignore-glob=* excludes only unselected siblings. Independent collection audit preserves all ordered selected node IDs.',
               'wall_seconds': time.perf_counter() - started,
               'junit': summary, 'test_source_files': sources,
               'native_campaigns_executed': 0, 'compiled_cpp_suite_executed': False,
               'source_day_training_executed': False}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('command', 'test_source_files')}))
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
