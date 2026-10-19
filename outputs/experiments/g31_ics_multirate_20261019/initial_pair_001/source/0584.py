"""Owned120 synthetic static-inventory gate; never dispatch model/C/native.

All source/reference reads, canonical archive creation, pytest collection/run,
loaded-source entry/exit checks and exports occur in the admitted owned worker.
The outer PowerShell stopwatch additionally measures Python startup and exit.
Only this candidate's test file is collected; the collection itself, not a
manually typed test count, fixes the denominator before any test runs.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = __package__ + '.run_static_root_inventory_pure'
CANDIDATE = __package__ + '.initial_owner_route_static_inventory'
TEST = 'tests/test_g31_circulation_static_root_inventory.py'
BASE = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/single_owned_C18_prepare_002/campaign.json'
BASE_SHA = '4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc'
BASE_COUNT = 218
PYTHON_SHA = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
WRAPPER = ROOT/'outputs/invoke_sinv1.ps1'


def require(value, reason):
    if not value:
        raise ValueError('static_inventory_pure:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def canonical_sources(files, root=ROOT):
    """Read-only canonicalization; duplicate identities require equal bytes."""
    root = Path(root).resolve()
    result, seen = {}, {}
    for name, data in files.items():
        require(type(data) is bytes, 'source_bytes')
        source = Path(name)
        source = (source if source.is_absolute() else root/source).resolve()
        require(source.is_relative_to(root), 'source_outside_root')
        relative = source.relative_to(root).as_posix()
        if source in seen:
            require(result[seen[source]] == data, 'canonical_duplicate_bytes')
        else:
            seen[source] = relative
            result[relative] = data
    return dict(sorted(result.items()))


def archive_targets(root, output, files):
    """Validate EVERY destination before creating any archive directory/file."""
    root, output = Path(root).resolve(), Path(output).resolve()
    source_root = (output/'source').resolve()
    targets = {}
    for name, data in files.items():
        item = Path(name)
        require(type(data) is bytes and not item.is_absolute() and not item.drive and not item.anchor
            and '..' not in item.parts and item.as_posix() == name, 'canonical_archive_key')
        current, target = (root/item).resolve(), (source_root/item).resolve()
        require(current.is_relative_to(root) and target.is_relative_to(source_root)
            and target != current and len(str(target)) < 260, 'archive_containment_or_path_length')
        require(not target.exists() and target not in targets.values(), 'archive_target_exists_or_collision')
        targets[name] = target
    return targets


def archive_sources(root, output, files):
    targets = archive_targets(root, output, files)
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(files[name])
    return {name: target.relative_to(Path(output).resolve()).as_posix() for name, target in targets.items()}


def inherited_sources():
    require(sha(BASE) == BASE_SHA, 'frozen_base_plan')
    plan = json.loads(BASE.read_bytes())
    pins, archived = plan['source_sha256'], plan['source_archive']
    require(len(pins) == BASE_COUNT and set(pins) == set(archived), 'base_source_domain')
    files = {}
    for name, digest in pins.items():
        current = Path(name)
        current = (current if current.is_absolute() else ROOT/current).resolve()
        saved = Path(archived[name])
        saved = (saved if saved.is_absolute() else BASE.parent/saved).resolve()
        require(current.is_relative_to(ROOT) and saved.is_relative_to(BASE.parent.resolve())
            and current != saved, 'base_independent_archive')
        data = current.read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest == sha(saved), 'base_current_archive_changed')
        files[name] = data
    files = canonical_sources(files)
    require(len(files) == BASE_COUNT, 'base_unique_canonical_count')
    return files


def source_files():
    from . import initial_owner_route_image as image
    files = inherited_sources()
    closure = image.source_closure(ROOT, (MODULE, CANDIDATE, TEST[:-3].replace('/', '.')))
    closure[WRAPPER.relative_to(ROOT).as_posix()] = WRAPPER.read_bytes()
    for name in ('conftest.py', 'tests/conftest.py'):
        if (ROOT/name).is_file():
            closure[name] = (ROOT/name).read_bytes()
    for name, data in canonical_sources(closure).items():
        require(name not in files or files[name] == data, 'inherited_closure_disagreement')
        files[name] = data
    return canonical_sources(files)


def verify_sources(output, plan):
    require(set(plan['source_sha256']) == set(plan['source_archive']), 'new_archive_domain')
    changed = []
    for name, digest in plan['source_sha256'].items():
        current = (ROOT/name).resolve()
        saved = (output/plan['source_archive'][name]).resolve()
        require(current.is_relative_to(ROOT) and saved.is_relative_to((output/'source').resolve())
            and current != saved and plan['source_archive'][name] == 'source/' + name,
            'new_archive_containment')
        if sha(current) != digest or sha(saved) != digest:
            changed.append(name)
    require(sha(BASE) == BASE_SHA and sha(WRAPPER) == plan['wrapper']['sha256']
        and sha(sys.executable) == PYTHON_SHA, 'plan_wrapper_python_changed')
    # Recheck the original independent archive too; no raw/toolchain read.
    inherited_sources()
    return changed


def loaded_sources(pins):
    result = {}
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if not path:
            continue
        path = Path(path).resolve()
        if path.suffix != '.py' or not path.is_relative_to(ROOT):
            continue
        name = path.relative_to(ROOT).as_posix()
        require(name in pins and sha(path) == pins[name], 'unbound_loaded_source:' + name)
        result[name] = pins[name]
    return dict(sorted(result.items()))


def no_execution_extensions():
    require(not any('czr005_circulation' in name or name.startswith('_g31_')
        for name in sys.modules), 'native_or_custom_C_loaded')


class Collection:
    def __init__(self, output):
        self.output, self.items = output, None

    def pytest_collection_finish(self, session):
        require(self.items is None, 'repeated_collection')
        require(session.items and all(Path(item.path).resolve() == (ROOT/TEST).resolve()
            for item in session.items), 'empty_or_foreign_test_collection')
        self.items = [item.nodeid for item in session.items]
        require(len(self.items) == len(set(self.items)), 'duplicate_collected_nodeid')
        write(self.output/'collection.json', {'schema': 'g31.static_inventory.collected_tests.v1',
            'nodeids': self.items, 'count': len(self.items), 'test_file': TEST,
            'recorded_before_execution': True})


def worker(output, token):
    require(type(token) is str and token and sys.stdin.readline() == token+'\n', 'owned_worker_admission')
    started = time.perf_counter_ns()
    report = {'status': 'failed_or_unknown', 'native_calls': 0, 'model_predictions': 0,
        'custom_C_loads': 0, 'actual_raw_reads': 0, 'performance_runs': 0}
    plan = None
    try:
        no_execution_extensions()
        require(sha(sys.executable) == PYTHON_SHA, 'python_identity')
        environment = {name: os.environ.get(name) for name in (
            'PYTHONPATH', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'PYTHONIOENCODING')}
        require(environment == {'PYTHONPATH': 'src;.;tests',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'},
            'explicit_test_environment')
        files = source_files()
        # Preflight includes the largest inherited file path before ANY writes.
        targets = archive_targets(ROOT, output, files)
        archive = archive_sources(ROOT, output, files)
        plan = {'schema': 'g31.static_inventory.synthetic_pure.v1', 'shared_seconds': 120.,
            'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
            'source_archive': archive, 'source_count': len(files),
            'max_archive_path_characters': max(len(str(path)) for path in targets.values()),
            'base': {'path': str(BASE), 'sha256': BASE_SHA, 'source_count': BASE_COUNT},
            'test_file': TEST, 'test_count': 'actual collection recorded before first test',
            'bare_helper_imports': [], 'wrapper': {'path': str(WRAPPER), 'sha256': sha(WRAPPER)},
            'python': {'path': sys.executable, 'sha256': PYTHON_SHA}, 'output_directory': str(output),
            'environment': environment,
            'command': [sys.executable, '-m', MODULE, '--output', str(output)],
            'source_binding_only_not_C_or_native_authority': True}
        require(not verify_sources(output, plan), 'entry_source_changed')
        write(output/'plan.json', plan)
        report.update(plan_sha256=sha(output/'plan.json'), source_count=len(files),
            loaded_entry=loaded_sources(plan['source_sha256']))
        import pytest
        plugin = Collection(output)
        code = pytest.main(['-q', TEST, '--basetemp='+str(output/'tmp'),
                           '--junitxml='+str(output/'tests.xml')], plugins=[plugin])
        rows = ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        report.update(pytest_exitcode=int(code), collected_tests=len(plugin.items or ()),
            XML_tests=len(rows), XML_sha256=sha(output/'tests.xml'),
            collection_sha256=sha(output/'collection.json') if (output/'collection.json').is_file() else None)
        no_execution_extensions()
        report['loaded_exit'] = loaded_sources(plan['source_sha256'])
        report['source_changed'] = verify_sources(output, plan)
        if code == 0 and plugin.items and len(rows) == len(plugin.items) and not report['source_changed'] \
            and not any(child.tag in ('failure', 'error', 'skipped') for row in rows for child in row):
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        if plan is not None:
            try:
                no_execution_extensions()
                report['final_source_changed'] = verify_sources(output, plan)
                if report['final_source_changed']:
                    report['status'] = 'failed_or_unknown'
            except BaseException as error:
                report['status'] = 'failed_or_unknown'
                report['final_error'] = repr(error)
    report['worker_before_receipt_ns'] = time.perf_counter_ns()-started
    report['synthetic_provider_is_not_actual_C_support'] = True
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
    require(output.is_relative_to((ROOT/'outputs').resolve()), 'output_outside_workspace_outputs')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed_or_unknown', 'shared_seconds': 120.,
        'command': [sys.executable, '-m', MODULE, '--output', str(output)],
        'output_directory': str(output), 'native_calls': 0, 'model_predictions': 0,
        'custom_C_loads': 0, 'actual_raw_reads': 0}
    try:
        remaining = 120. - (time.monotonic()-BOOT) - 1.
        require(remaining > 0, 'budget_before_owned_worker')
        token = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--admission', token]
        with (output/'worker.stdout.log').open('x', encoding='utf8') as out, \
             (output/'worker.stderr.log').open('x', encoding='utf8') as err:
            report['process'] = bounded_windows_job.run(command, timeout=remaining, admission=token,
                stdout=out, stderr=err, cwd=ROOT)
        if (output/'receipt.json').is_file():
            receipt = json.loads((output/'receipt.json').read_bytes())
            report['receipt_sha256'] = sha(output/'receipt.json')
            if report['process']['status'] == 'exited' and report['process']['exitcode'] == 0 \
                and receipt['status'] == 'passed':
                report['status'] = 'passed'
    except BaseException as error:
        report['error'] = repr(error)
    report['post_interpreter_before_parent_export_seconds'] = time.monotonic()-BOOT
    if report['post_interpreter_before_parent_export_seconds'] >= 120.:
        report['status'] = 'failed_shared_budget'
    write(output/'bounded_parent_receipt.json', report)
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
