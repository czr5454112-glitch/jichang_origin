"""Proposed owned120 synthetic routing gate. No C load or saved policy replay.

The external launcher must separately bound and record full Python startup
through process exit; this runner cannot time before its own interpreter start.
"""
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
from . import measure_delivered_peer_c_encoder as reference

ROOT, OUT = reference.ROOT, reference.OUT
MODULE = 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_pure'
TEST = 'tests/test_g31_circulation_bridge_saved_c_digest.py'
HELPER = 'tests/test_g31_circulation_bridge_replay_copy_scopes.py'
EXPECTED_TESTS = 37
LIMIT = 120.
SCHEMA = 'g31.bridge.saved_C_digest.synthetic_pure.v1'


def require(ok, reason):
    if not ok: raise ValueError('bridge_C_digest_pure:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf8')
    with Path(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'short_write')


def sources():
    # Explicit union: accepted C gate's16, original validator executable's
    # hand-listed roots, current static closure and the bare test helper root.
    # reference.sources() reads only source files; it does not call metadata(),
    # decode a real fixture, load C, or execute a validator.
    result = reference.sources()
    extra = image.source_closure(ROOT, (MODULE, TEST[:-3].replace('/', '.'),
                                       HELPER[:-3].replace('/', '.')))
    for name, data in extra.items():
        require(name not in result or result[name] == data, 'source_union_conflict')
        result[name] = data
    require(TEST in result and HELPER in result, 'explicit_test_roots')
    return dict(sorted(result.items()))


def source_check(output, expected):
    current = sources()
    require(set(current) == set(expected), 'source_domain')
    reference.archive_targets(output, current, False)
    changed = [name for name, data in current.items()
               if hashlib.sha256(data).hexdigest() != expected[name]
               or sha(output / 'source' / name) != expected[name]]
    require(not changed, 'source_changed:' + ','.join(changed))
    loaded = {Path(m.__file__).resolve().relative_to(ROOT).as_posix()
        for m in list(sys.modules.values()) if getattr(m, '__file__', None)
        and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    require(loaded <= set(current), 'loaded_source_domain')
    require('_g31_planning_v2_typed_encoder' not in sys.modules, 'unexpected_C_module')
    return sorted(loaded)


def worker(output, admission):
    require(sys.stdin.readline().strip() == admission, 'admission')
    plan = json.loads((output / 'plan.json').read_text(encoding='utf8'))
    require(plan['schema'] == SCHEMA and plan['tests'] == EXPECTED_TESTS
            and plan['limit_seconds'] == LIMIT and plan['admission'] == admission, 'plan_scope')
    entered = source_check(output, plan['source_sha256'])
    import pytest
    code = pytest.main(['-q', TEST, '--basetemp=' + str(output / 'temp'),
                        '--junitxml=' + str(output / 'tests.xml')])
    exited = source_check(output, plan['source_sha256'])
    write(output / 'worker.json', {'pytest_exitcode': int(code), 'loaded_entry': entered,
        'loaded_exit': exited, 'source_entry_exit_exact': True,
        'extension_loads': 0, 'actual_fixture_reads': 0, 'native_calls': 0,
        'scope': 'Fabricated public bodies and actual unchanged Python factories; not C byte parity or a saved replay.'})
    return int(code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker: return worker(output, args.admission)
    require(output.is_relative_to(OUT.resolve()) and output != OUT.resolve(), 'output_domain')
    output.mkdir(parents=True, exist_ok=False)
    process = None; expected = {}; error = None; loaded_exit = None
    try:
        files = sources()
        # Complete canonical, independent, short-path and absent-domain checks
        # run before ANY source member is written. Original routine is exact.
        reference.archive_sources(output, files)
        expected = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        admission = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--output', str(output),
                   '--worker', '--admission', admission]
        plan = dict(schema=SCHEMA, tests=EXPECTED_TESTS, limit_seconds=LIMIT,
            admission=admission, source_sha256=expected, command=command,
            explicit_bare_helper=HELPER, previous_manual_and_C16_union=True,
            scope='Synthetic route coverage; no C/native/model/performance/actual raw.')
        write(output / 'plan.json', plan)
        source_check(output, expected)
        remaining = LIMIT - (time.perf_counter() - BOOT)
        require(remaining > 0, 'budget_before_child')
        with (output / 'parent_stdout.log').open('x', encoding='utf8') as stdout, \
             (output / 'parent_stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=admission,
                stdout=stdout, stderr=stderr, cwd=ROOT)
        write(output / 'bounded_execution.json', process)
        loaded_exit = source_check(output, expected)
    except Exception as failure:
        error = {'type': type(failure).__name__, 'message': str(failure)}
    rows = ET.parse(output / 'tests.xml').getroot().findall('.//testcase') if (output / 'tests.xml').is_file() else []
    bad = [{'name': row.get('name'), 'tags': [item.tag for item in row
            if item.tag in ('failure', 'error', 'skipped')]} for row in rows
            if any(item.tag in ('failure', 'error', 'skipped') for item in row)]
    worker_record = json.loads((output / 'worker.json').read_text(encoding='utf8')) if (output / 'worker.json').is_file() else None
    sampled = time.perf_counter() - BOOT
    passed = (error is None and process is not None and process['status'] == 'exited'
        and type(process['exitcode']) is int and process['exitcode'] == 0 and sampled <= LIMIT
        and len(rows) == EXPECTED_TESTS and not bad and worker_record is not None
        and type(worker_record['pytest_exitcode']) is int and worker_record['pytest_exitcode'] == 0)
    report = dict(schema=SCHEMA, status='passed_synthetic_routing' if passed else 'failed_or_unknown',
        process=process, tests=len(rows), expected_tests=EXPECTED_TESTS, bad_tests=bad, error=error,
        source_sha256=expected, loaded_parent_exit=loaded_exit,
        XML_sha256=sha(output / 'tests.xml') if rows else None,
        worker_sha256=sha(output / 'worker.json') if worker_record is not None else None,
        native_calls=0, extension_loads=0, actual_fixture_reads=0, benchmark_executed=False,
        post_import_wall_before_receipt_seconds=sampled,
        wall_scope='Module BOOT through sample, excluding interpreter startup and final receipt/export. External launch-through-exit typed ticks <=120 are separately required.',
        full_external_acceptance=False)
    write(output / 'receipt.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'tests', 'expected_tests', 'error', 'XML_sha256')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
