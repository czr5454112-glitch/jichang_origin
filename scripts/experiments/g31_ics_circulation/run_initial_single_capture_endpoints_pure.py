"""One owned120 functional gate for endpoint dispatch; no native/model run."""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
TESTS = ('tests/test_g31_circulation_single_capture_endpoint_dispatch.py',
         'tests/test_g31_circulation_single_capture_failure_review.py')
EXPECTED_TESTS = 89


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline().strip() != args.admission: raise ValueError('pure_admission')
        import pytest
        return pytest.main(['-q', *TESTS, '--basetemp='+str(output/'temp'),
                            '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True, exist_ok=False)
    entries = (__package__+'.run_initial_single_capture_endpoints_pure',
        __package__+'.verify_initial_single_capture_endpoints',
        'tests.test_g31_circulation_single_capture_endpoint_dispatch',
        'tests.test_g31_circulation_single_capture_failure_review',
        'tests.test_g31_circulation_initial_owner_route_single_capture',
        'tests.test_g31_circulation_preexisting_online_model')
    files = image.source_closure(ROOT, entries)
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        path = output/'source'/name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    admission = uuid.uuid4().hex
    command = [sys.executable, '-m', __package__+'.run_initial_single_capture_endpoints_pure',
               '--output', str(output), '--worker', '--admission', admission]
    with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
        process = bounded_windows_job.run(command, timeout=max(.001, 120.-(time.perf_counter()-BOOT)),
            admission=admission, stdout=stdout, stderr=stderr, cwd=ROOT)
    changed = [name for name, digest in before.items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
    rows = ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    bad = any(c.tag in ('failure', 'error', 'skipped') for row in rows for c in row)
    report = {'schema': 'g31.initial_single_capture.endpoint_dispatch_pure.v1',
        'status': 'passed' if process['status'] == 'exited' and process['exitcode'] == 0
            and not changed and len(rows) == EXPECTED_TESTS and not bad else 'failed_or_unknown',
        'process': process, 'source_sha256': before, 'source_changed': changed,
        'tests': len(rows), 'expected_tests': EXPECTED_TESTS,
        'XML_sha256': hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'post_interpreter_wall_seconds': time.perf_counter()-BOOT,
        'wall_scope': 'Module BOOT through sample, excluding interpreter startup and final receipt write; owned child bound includes archive preparation.',
        'native_calls': 0, 'predictions': 0, 'actual_raw_reads': 0, 'benchmark_executed': False,
        'scope': 'Synthetic saved endpoint replay, identity/failure/denominator/clock and certificate tests only.'}
    (output/'receipt.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({key: report[key] for key in ('status', 'tests', 'expected_tests', 'XML_sha256', 'source_changed', 'post_interpreter_wall_seconds')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
