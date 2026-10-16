"""Draft owned120 focused synthetic gate; no real proof/model/native call.

One test imports the frozen real definitions to inspect exact operation code
and complete globals. A sticky profile guard forbids entering the real proof
or continuation entry points. No operation from that imported model executes.
"""
import time
BOOT = time.monotonic()
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = __package__ + '.run_bound_source_proof_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof.py',)
EXPECTED_TESTS = 37
LIMIT = 120.


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def sources():
    from . import diagnose_future_source_inventory as archive
    from . import initial_owner_route_image as image
    files = archive.source_files()
    entries = (MODULE, __package__ + '.live_obligation_bound_source_proof',
               __package__ + '.live_obligation_bound_future_fork',
               *(p[:-3].replace('/', '.') for p in TESTS))
    for name, raw in image.source_closure(ROOT, entries).items():
        archive.relative_python(name)
        archive.require(name not in files or files[name] == raw, 'new_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def worker(output, token):
    if not token or sys.stdin.readline() != token + '\n':
        raise ValueError('bound_proof_pure:owned_admission')
    started = time.perf_counter_ns()
    report = {'status': 'failed_or_unknown', 'real_original_proof_calls': 0,
              'model_entry_calls': 0, 'native_calls': 0, 'custom_data_C_loads': 0}
    plan = None
    blocked = []
    prior_profile = sys.getprofile()
    root_text = str(ROOT).replace('\\', '/').lower() + '/scripts/experiments/g31_ics_circulation/'
    def guard(frame, event, arg):
        if event != 'call':
            return
        filename = frame.f_code.co_filename.replace('\\', '/').lower()
        name = frame.f_code.co_name
        proof = filename == root_text + 'live_obligation_future_later_fork.py' and name == 'source_proof'
        model = filename == root_text + 'live_obligation_conditional_continuation.py' and name in (
            'start_conditional', 'advance_to_collection_or_terminal', 'fork_conditional',
            'resume_same_action', '_drive')
        if proof or model:
            blocked.append({'file': filename, 'function': name, 'kind': 'proof' if proof else 'model'})
            raise RuntimeError('bound_proof_pure:forbidden_real_execution')
    try:
        from . import diagnose_future_source_inventory as archive
        archive.no_execution_extensions()
        archive.require(prior_profile is None and gc.isenabled(), 'default_profile_GC')
        files = sources()
        mapping = archive.archive_sources(ROOT, output, files)
        plan = {'schema': 'g31.bound_source_proof.synthetic_pure.v1',
            'source_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
            'source_archive': mapping, 'tests': list(TESTS), 'expected_tests': EXPECTED_TESTS,
            'shared_seconds': LIMIT, 'output_directory': str(output),
            'environment': {'python': sys.executable, 'sha256': archive.sha(sys.executable)},
            'scope': 'Fake static inventories/states and filesystem mutation tests. One frozen real-module import for exact code/globals identity only; sticky guard forbids real future proof and continuation entries.'}
        archive.verify_archive(ROOT, output, plan)
        write(output/'plan.json', plan)
        report.update(plan_sha256=archive.sha(output/'plan.json'),
                      loaded_entry=archive.loaded_sources(plan['source_sha256']))
        import pytest
        sys.setprofile(guard)
        code = pytest.main(['-q', *TESTS, '--basetemp=' + str(output/'tmp'), '--junitxml=' + str(output/'tests.xml')])
        monitor_active = sys.getprofile() is guard
        sys.setprofile(prior_profile)
        cases = ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        report.update(pytest_exitcode=int(code), tests=len(cases), expected_tests=EXPECTED_TESTS,
            XML_sha256=archive.sha(output/'tests.xml'), monitor_active_after_tests=monitor_active,
            loaded_exit=archive.loaded_sources(plan['source_sha256']))
        archive.verify_archive(ROOT, output, plan)
        archive.no_execution_extensions()
        report['source_changed'] = [name for name, digest in plan['source_sha256'].items()
            if archive.sha(ROOT/name) != digest or archive.sha(output/plan['source_archive'][name]) != digest]
        if code == 0 and len(cases) == EXPECTED_TESTS and not blocked and monitor_active and gc.isenabled() \
                and not report['source_changed'] and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c):
            report['status'] = 'passed'
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        sys.setprofile(prior_profile)
        report['blocked_real_calls'] = blocked
        report['real_original_proof_calls'] = sum(x['kind'] == 'proof' for x in blocked)
        report['model_entry_calls'] = sum(x['kind'] == 'model' for x in blocked)
        if blocked:
            report['status'] = 'failed_or_unknown'
        if plan is not None:
            try:
                archive.verify_archive(ROOT, output, plan)
                archive.no_execution_extensions()
                report['loaded_exit_final'] = archive.loaded_sources(plan['source_sha256'])
            except BaseException:
                report['status'] = 'failed_or_unknown'
                report['final_binding_error'] = traceback.format_exc()
        report['worker_before_receipt_ns'] = time.perf_counter_ns() - started
        write(output/'receipt.json', report)
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        return worker(output, args.admission)
    output.mkdir(parents=True, exist_ok=False)
    token = uuid.uuid4().hex
    report = {'status': 'failed_or_unknown', 'shared_seconds': LIMIT,
        'output_directory': str(output), 'command': [sys.executable, '-m', MODULE, '--output', str(output)],
        'real_original_proof_calls': 0, 'model_entry_calls': 0, 'native_calls': 0,
        'external_launch_through_exit_clock_required': True}
    try:
        remaining = LIMIT - (time.monotonic() - BOOT) - 1.
        if remaining <= 0:
            raise TimeoutError('bound_proof_pure:budget_before_worker')
        command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--admission', token]
        with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token,
                stdout=stdout, stderr=stderr, cwd=ROOT)
        report['process'] = process
        if (output/'receipt.json').is_file():
            raw = (output/'receipt.json').read_bytes()
            receipt = json.loads(raw)
            report['receipt_sha256'] = hashlib.sha256(raw).hexdigest()
            if process['status'] == 'exited' and process['exitcode'] == 0 and receipt['status'] == 'passed':
                report['status'] = 'passed'
    except BaseException:
        report['error'] = traceback.format_exc()
    report['application_before_final_export_seconds'] = time.monotonic() - BOOT
    if report['application_before_final_export_seconds'] > LIMIT:
        report['status'] = 'failed_shared_budget'
    write(output/'bounded_parent_receipt.json', report)
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' and time.monotonic() - BOOT <= LIMIT else 1


if __name__ == '__main__':
    raise SystemExit(main())
