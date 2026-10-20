"""Proposed standalone22 synthetic gate; owned120 and external120 required.

No invocation is authorized by writing/importing this file. Source collection
uses one original image resolver over the runner and the explicit test root;
it does not invoke another source collector or cache hashes between checks.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import hashlib
import json
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE = 'scripts.experiments.g31_ics_circulation.run_live_obligation_online_retained_policy_pure'
TEST = 'tests/test_g31_circulation_live_obligation_online_retained_policy.py'
SCHEMA = 'g31.live_obligation.online_retained_policy.synthetic22.v1'
LIMIT = 120.
EXPECTED_TESTS = 22
FROZEN = {
    'scripts/experiments/g31_ics_circulation/live_obligation_online_retained_policy.py':
        '6b284683e77ca9a3121f8c02c8641cd000091ad7c815fb0b30391c091d66b462',
    TEST: '42ac004798f9bbdb3cb776d8b7e5b0d1abd0dcc2dee1f1d948b2afc269e31055',
}


def require(value, reason):
    if not value: raise ValueError('retained_policy_pure:' + reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf8')
    with Path(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'short_write')


class Journal:
    def __init__(self, path):
        self.path, self.count = path, 0

    def emit(self, phase, event):
        require(self.count < 64, 'journal_limit')
        row = dict(sequence=self.count, phase=phase, event=event, at_ns=time.perf_counter_ns())
        with self.path.open('ab' if self.count else 'xb') as stream:
            raw = (json.dumps(row, allow_nan=False) + '\n').encode('utf8')
            require(stream.write(raw) == len(raw), 'journal_short_write')
            stream.flush()
        self.count += 1


def sources(journal):
    journal.emit('source_closure', 'started')
    result = image.source_closure(ROOT, (MODULE, TEST[:-3].replace('/', '.')))
    for name, expected in FROZEN.items():
        require(name in result and hashlib.sha256(result[name]).hexdigest() == expected,
                'frozen_subject:' + name)
    require(MODULE.replace('.', '/') + '.py' in result, 'runner_in_complete_domain')
    journal.emit('source_closure', 'completed')
    return result


def targets(output, files, create):
    result = []
    archive = (output / 'source').resolve()
    for name in files:
        image.safe_name(name)
        current, target = (ROOT / name).resolve(), (archive / name).resolve()
        require(current.is_relative_to(ROOT) and target.is_relative_to(archive)
            and current != target and len(str(target)) < 260 and current.is_file(), 'archive_path')
        require(not target.exists() if create else target.is_file(), 'archive_existence')
        result.append(target)
    require(len(set(result)) == len(files), 'archive_alias')
    return result


def archive_sources(output, files, journal):
    journal.emit('archive', 'started')
    paths = targets(output, files, True)  # Entire domain before writing a member.
    for (name, data), path in zip(files.items(), paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            require(stream.write(data) == len(data), 'archive_short_write')
    journal.emit('archive', 'completed')


def source_check(output, expected, journal):
    journal.emit('current_archive_loaded_check', 'started')
    current = sources(journal)
    require(set(current) == set(expected), 'exact_source_domain')
    targets(output, current, False)
    for name, data in current.items():
        require(hashlib.sha256(data).hexdigest() == expected[name]
            and sha(output / 'source' / name) == expected[name], 'source_drift:' + name)
    loaded = set()
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename: continue
        path = Path(filename).resolve()
        if not path.is_relative_to(ROOT): continue
        require(path.suffix.lower() not in ('.pyd', '.dll'), 'unexpected_project_extension')
        if path.suffix == '.py': loaded.add(path.relative_to(ROOT).as_posix())
    require(loaded <= set(current), 'loaded_source_not_archived')
    journal.emit('current_archive_loaded_check', 'completed')
    return sorted(loaded)


def worker(output, admission):
    require(sys.stdin.readline() == admission + '\n', 'owned_admission')
    plan = json.loads((output / 'plan.json').read_bytes())
    require(plan['schema'] == SCHEMA and plan['admission'] == admission
        and plan['tests'] == EXPECTED_TESTS and plan['limit_seconds'] == LIMIT, 'plan_contract')
    journal = Journal(output / 'worker_stages.jsonl')
    entered = source_check(output, plan['source_sha256'], journal)
    journal.emit('synthetic22', 'started')
    import pytest
    code = pytest.main(['-q', TEST, '--basetemp=' + str(output / 'temp'),
                       '--junitxml=' + str(output / 'tests.xml')])
    journal.emit('synthetic22', 'completed')
    exited = source_check(output, plan['source_sha256'], journal)
    write(output / 'worker.json', dict(pytest_exitcode=int(code), loaded_entry=entered,
        loaded_exit=exited, source_entry_exit_exact=True, native_calls=0,
        extension_loads=0, actual_fixture_reads=0, predictions=0,
        scope='Fabricated collector/transport doubles only; no native capability or physical result is certified.'))
    return int(code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(OUT.resolve()) and output != OUT.resolve(), 'output_domain')
    if args.worker: return worker(output, args.admission)
    output.mkdir(parents=True, exist_ok=False)
    journal = Journal(output / 'parent_stages.jsonl')
    process = None; expected = {}; error = None; loaded = None
    rows = []; worker_record = None
    try:
        files = sources(journal)
        archive_sources(output, files, journal)
        expected = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        admission = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--output', str(output),
                   '--worker', '--admission', admission]
        write(output / 'plan.json', dict(schema=SCHEMA, tests=EXPECTED_TESTS, limit_seconds=LIMIT,
            admission=admission, source_sha256=expected, frozen_subjects=FROZEN, command=command,
            source_collection='One original source_closure call with runner + explicit test root per check. No cross-check hash cache.',
            scope='Only22 synthetic cases; no saved fixture, C load, native, prediction, benchmark or full audit.'))
        source_check(output, expected, journal)
        remaining = LIMIT - (time.perf_counter() - BOOT)
        require(remaining > 0, 'budget_before_owned_child')
        journal.emit('owned_child', 'started')
        with (output / 'parent_stdout.log').open('x', encoding='utf8') as stdout, \
             (output / 'parent_stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=admission,
                stdout=stdout, stderr=stderr, cwd=ROOT)
        journal.emit('owned_child', 'completed')
        write(output / 'bounded_execution.json', process)
        loaded = source_check(output, expected, journal)
        if (output / 'tests.xml').is_file():
            rows = ET.parse(output / 'tests.xml').getroot().findall('.//testcase')
        if (output / 'worker.json').is_file():
            worker_record = json.loads((output / 'worker.json').read_bytes())
    except Exception as failure:
        error = dict(type=type(failure).__name__, message=str(failure), traceback=traceback.format_exc())
    bad = [{'name': row.get('name'), 'tags': [item.tag for item in row
        if item.tag in ('failure', 'error', 'skipped')]} for row in rows
        if any(item.tag in ('failure', 'error', 'skipped') for item in row)]
    elapsed = time.perf_counter() - BOOT
    passed = (error is None and process is not None and process['status'] == 'exited'
        and type(process['exitcode']) is int and process['exitcode'] == 0 and elapsed <= LIMIT
        and len(rows) == EXPECTED_TESTS and not bad and worker_record is not None
        and type(worker_record['pytest_exitcode']) is int and worker_record['pytest_exitcode'] == 0
        and worker_record['source_entry_exit_exact'] is True)
    receipt = dict(schema=SCHEMA, status='passed_synthetic22' if passed else 'failed_or_unknown',
        process=process, tests=len(rows), expected_tests=EXPECTED_TESTS, bad_tests=bad, error=error,
        source_sha256=expected, loaded_parent_exit=loaded,
        XML_sha256=sha(output / 'tests.xml') if (output / 'tests.xml').is_file() else None,
        worker_sha256=sha(output / 'worker.json') if worker_record is not None else None,
        native_calls=0, extension_loads=0, predictions=0, actual_fixture_reads=0,
        benchmark_executed=False, post_import_wall_before_receipt_seconds=elapsed,
        wall_scope='Module BOOT through sample, excluding earlier interpreter startup and final receipt/exit. External typed launch-through-exit120 is mandatory.',
        full_external_acceptance=False)
    write(output / 'receipt.json', receipt)
    print(json.dumps({key: receipt[key] for key in ('status', 'tests', 'expected_tests', 'error')}))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
