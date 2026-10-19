"""Owned120 synthetic profiling/driver tests; original future never imported."""
import time
BOOT = time.monotonic()
import argparse
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = __package__+'.run_future_source_inventory_pure'


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def worker(output, token):
    if not token or sys.stdin.readline() != token+'\n':
        raise ValueError('source_inventory_pure:owned_admission')
    report = {'status': 'failed_or_unknown', 'real_original_proof_calls': 0,
        'model_predictions': 0, 'native_calls': 0, 'custom_data_C_loads': 0}
    started = time.perf_counter_ns(); plan = None
    try:
        from . import diagnose_future_source_inventory as driver
        driver.no_execution_extensions(pure=True)
        wrapper = driver.verify_wrapper()
        files = driver.source_files()
        mapping = driver.archive_sources(ROOT, output, files)
        plan = {'schema': 'g31.source_inventory_diagnostic.synthetic_pure.v1',
            'source_sha256': {name: driver.hashlib.sha256(data).hexdigest() for name, data in files.items()},
            'source_archive': mapping, 'tests': list(driver.TESTS), 'expected_tests': driver.EXPECTED_TESTS,
            'output_directory': str(output), 'external_wrapper': wrapper,
            'environment': {'python': sys.executable, 'sha256': driver.sha(sys.executable)},
            'shared_seconds': 120., 'scope': 'Only fake original functions and small JSON/file fixtures; original future module may not be imported.'}
        driver.verify_archive(ROOT, output, plan); write(output/'plan.json', plan)
        report.update(plan_sha256=driver.sha(output/'plan.json'),
            loaded_entry=driver.loaded_sources(plan['source_sha256']))
        import pytest
        code = pytest.main(['-q', *driver.TESTS, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
        cases = ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        report.update(pytest_exitcode=int(code), tests=len(cases), expected_tests=driver.EXPECTED_TESTS,
            XML_sha256=driver.sha(output/'tests.xml'), loaded_exit=driver.loaded_sources(plan['source_sha256']))
        driver.no_execution_extensions(pure=True); driver.verify_archive(ROOT, output, plan)
        report['source_changed'] = [name for name, digest in plan['source_sha256'].items()
            if driver.sha(ROOT/name) != digest or driver.sha(output/plan['source_archive'][name]) != digest]
        if code == 0 and len(cases) == driver.EXPECTED_TESTS and not report['source_changed'] and not any(n.tag in ('failure', 'error', 'skipped') for row in cases for n in row):
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = repr(error)
    report['worker_before_receipt_ns'] = time.perf_counter_ns()-started
    if plan is not None:
        try:
            driver.verify_archive(ROOT, output, plan)
            driver.no_execution_extensions(pure=True)
            driver.verify_wrapper()
        except BaseException as error:
            report['status'] = 'failed_or_unknown'; report['final_error'] = repr(error)
    write(output/'receipt.json', report)
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        return worker(output, args.admission)
    output.mkdir(parents=True, exist_ok=False); token = uuid.uuid4().hex
    report = {'status': 'failed_or_unknown', 'shared_seconds': 120.,
        'real_original_proof_calls': 0, 'model_predictions': 0, 'native_calls': 0,
        'output_directory': str(output),
        'command': [sys.executable, '-m', MODULE, '--output', str(output)]}
    try:
        remaining = 120.-(time.monotonic()-BOOT)-1.
        if remaining <= 0:
            raise TimeoutError('source_inventory_pure:budget_before_worker')
        command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--admission', token]
        with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token, stdout=stdout, stderr=stderr, cwd=ROOT)
        report['process'] = process
        if (output/'receipt.json').is_file():
            import hashlib
            receipt = json.loads((output/'receipt.json').read_bytes())
            report['receipt_sha256'] = hashlib.sha256((output/'receipt.json').read_bytes()).hexdigest()
            if process['status'] == 'exited' and process['exitcode'] == 0 and receipt['status'] == 'passed':
                report['status'] = 'passed'
    except BaseException as error:
        report['error'] = repr(error)
    report['post_interpreter_before_final_export_seconds'] = time.monotonic()-BOOT
    if report['post_interpreter_before_final_export_seconds'] > 120.:
        report['status'] = 'failed_shared_budget'
    write(output/'bounded_parent_receipt.json', report); print(json.dumps(report))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
