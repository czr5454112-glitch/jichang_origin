"""Source-bound owned120 preparation/diagnosis; no model, native or cache.

Preparation and synthetic tests never import the original future module.
Only --worker imports it, after the one owned admission and source gate.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import pstats
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET

from . import profile_future_source_inventory as kernel

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
BASE = OUT/'owned_full32_runtime_prepare_001'
BASE_PLAN = '6f4434bcf87d8e35d709eabfed5561b6461adde71389b92c8042072a9e6c4bc5'
BASE_RECEIPT = 'a6cebda0a1321415bc5ccdf4ebd1d8889a96adf73e62e3f5af973b2b350e94ed'
BASE_REVIEW = '1a0927f87248183ed4535e2e74cbe747e2a7f7e1e45424d84708545c8deb1054'
PURE = ROOT/'outputs/si65p1'
MODULE = __package__+'.diagnose_future_source_inventory'
PURE_MODULE = __package__+'.run_future_source_inventory_pure'
TESTS = ('tests/test_g31_circulation_future_source_inventory_profile.py',
    'tests/test_g31_circulation_future_source_inventory_driver.py')
EXPECTED_TESTS = 71
SCHEMA = 'g31.original_source_inventory.diagnostic.v1'
LIMIT = 120.
WRAPPER = ROOT/'outputs/invoke_si65p1.ps1'
WRAPPER_SHA = '277f427f4937dd7ebe54683854412720e267b8091f4c2ed1ef2897ffce5aaf46'
EXTERNAL_SCHEMA = 'g31.source_inventory_pure.external.v1'


def require(value, reason):
    if not value:
        raise ValueError('source_inventory_driver:'+reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def relative_python(name):
    require(type(name) is str and name and '\\' not in name and ':' not in name and '\x00' not in name, 'source_key')
    value = PurePosixPath(name)
    require(not value.is_absolute() and value.as_posix() == name and '..' not in value.parts
        and '.' not in value.parts and value.suffix == '.py', 'canonical_relative_python')
    return Path(*value.parts)


def locations(root, output, name):
    root, output = Path(root).resolve(), Path(output).resolve()
    relative = relative_python(name)
    current = (root/relative).resolve()
    archive_root = (output/'source').resolve()
    archive = (archive_root/relative).resolve()
    require(current.is_relative_to(root) and archive_root.is_relative_to(output)
        and archive.is_relative_to(archive_root) and archive != current, 'source_archive_containment')
    require(len(str(archive)) < 260, 'archive_path_under260')
    return current, archive


def archive_sources(root, output, files):
    require(type(files) is dict and files, 'nonempty_sources')
    targets = {}
    for name, data in files.items():
        require(type(data) is bytes, 'source_bytes')
        _, target = locations(root, output, name)
        require(target not in targets.values(), 'archive_collision')
        require(not target.exists(), 'archive_target_exists')
        targets[name] = target
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(files[name])
    return {name: path.relative_to(Path(output).resolve()).as_posix() for name, path in targets.items()}


def verify_archive(root, output, plan):
    require(set(plan['source_sha256']) == set(plan['source_archive']), 'archive_domain')
    for name, digest in plan['source_sha256'].items():
        current, archive = locations(root, output, name)
        require(plan['source_archive'][name] == archive.relative_to(Path(output).resolve()).as_posix(), 'archive_mapping')
        require(sha(current) == digest == sha(archive), 'current_archive_source:'+name)


def no_execution_extensions(*, pure=False):
    require(not any('czr005_circulation' in name or name.startswith('_g31_') for name in sys.modules), 'native_or_custom_C_loaded')
    if pure:
        require(__package__+'.live_obligation_future_later_fork' not in sys.modules, 'pure_imported_real_future')


def loaded_sources(pins):
    result = {}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if not name:
            continue
        path = Path(name).resolve()
        if path.suffix != '.py' or not path.is_relative_to(ROOT):
            continue
        key = path.relative_to(ROOT).as_posix()
        require(key in pins and sha(path) == pins[key], 'unbound_loaded_project_source:'+key)
        result[key] = pins[key]
    return dict(sorted(result.items()))


def base_gate():
    require(sha(BASE/'plan.json') == BASE_PLAN and sha(BASE/'receipt.json') == BASE_RECEIPT
        and sha(BASE/'root_saved_review_001.json') == BASE_REVIEW, 'accepted_base_identity')
    plan, receipt = read(BASE/'plan.json'), read(BASE/'receipt.json')
    require(receipt['status'] == 'exact_full96_future_suffixes' and receipt['exact_rows'] == 96
        and receipt['unknown_rows'] == 0 and receipt['source_changed'] == [], 'accepted_base_status')
    require(len(plan['source_sha256']) == 191, 'base191')
    verify_archive(ROOT, BASE, plan)
    return plan


def source_files():
    from . import initial_owner_route_image as image
    base = base_gate()
    files = {}
    for name, digest in base['source_sha256'].items():
        data = (ROOT/relative_python(name)).read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest, 'inherited_source_snapshot:'+name)
        files[name] = data
    entries = [MODULE, PURE_MODULE, __package__+'.profile_future_source_inventory',
        *(name[:-3].replace('/', '.') for name in TESTS)]
    extra = image.source_closure(ROOT, entries)
    for name in ('conftest.py', 'tests/conftest.py'):
        if (ROOT/name).is_file():
            extra[name] = (ROOT/name).read_bytes()
    for name, data in extra.items():
        relative_python(name)
        require(name not in files or files[name] == data, 'duplicate_source_bytes')
        files[name] = data
    return dict(sorted(files.items()))


def pure_gate():
    plan, receipt, bounded = (read(PURE/name) for name in ('plan.json', 'receipt.json', 'bounded_parent_receipt.json'))
    verify_external(read(PURE/'external_application_wall.json'), PURE, plan, receipt, bounded)
    cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status'] == 'passed' and receipt['tests'] == EXPECTED_TESTS
        and receipt['source_changed'] == [] and receipt['real_original_proof_calls'] == 0, 'pure_receipt')
    require(len(cases) == EXPECTED_TESTS and not any(n.tag in ('failure', 'error', 'skipped') for row in cases for n in row), 'pure_exact_count')
    require(receipt['XML_sha256'] == sha(PURE/'tests.xml') and bounded['status'] == 'passed'
        and bounded['receipt_sha256'] == sha(PURE/'receipt.json'), 'pure_artifacts')
    verify_archive(ROOT, PURE, plan)
    return {name: ref(PURE/name) for name in ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'external_application_wall.json')}


def pure_command(output):
    return [sys.executable, '-m', PURE_MODULE, '--output', str(Path(output).resolve())]


def verify_wrapper():
    require(type(WRAPPER_SHA) is str and len(WRAPPER_SHA) == 64
        and all(c in '0123456789abcdef' for c in WRAPPER_SHA), 'wrapper_not_frozen')
    require(sha(WRAPPER) == WRAPPER_SHA, 'wrapper_current_identity')
    return {'path': str(WRAPPER.resolve()), 'sha256': WRAPPER_SHA}


def verify_external(external, output, plan, receipt, bounded):
    """Accept the complete Python lifetime, not only the owned child result."""
    keys = {'schema', 'status', 'command', 'cwd', 'output_directory', 'python_sha256',
        'python_after_sha256', 'exitcode', 'wrapper_exitcode', 'stopwatch_frequency',
        'elapsed_ticks', 'external_application_seconds', 'clock_scope', 'wrapper',
        'wrapper_after_sha256', 'outputs', 'native_calls', 'model_predictions', 'real_original_proof_calls'}
    require(type(external) is dict and set(external) == keys, 'external_schema_keys')
    require(external['schema'] == EXTERNAL_SCHEMA and external['status'] == 'exited_zero', 'external_schema_status')
    output = Path(output).resolve(); command = pure_command(output)
    require(type(external['command']) is list and external['command'] == command
        and all(type(item) is str for item in external['command']), 'external_command')
    require(external['cwd'] == str(ROOT.resolve()) and external['output_directory'] == str(output), 'external_paths')
    require(type(external['exitcode']) is int and external['exitcode'] == 0
        and type(external['wrapper_exitcode']) is int and external['wrapper_exitcode'] == 0, 'external_exit')
    frequency, ticks, seconds = (external[name] for name in ('stopwatch_frequency', 'elapsed_ticks', 'external_application_seconds'))
    require(type(frequency) is int and frequency > 0 and type(ticks) is int and ticks >= 0, 'external_clock_types')
    require(ticks <= 120*frequency, 'external_whole120_ticks')
    require(type(seconds) in (int, float) and math.isfinite(seconds) and 0 <= seconds <= LIMIT, 'external_seconds')
    require(seconds == float(ticks)/float(frequency), 'external_clock_agreement')
    require(external['clock_scope'] == 'immediately_before_python_launch_through_process_return', 'external_clock_scope')
    wrapper = verify_wrapper()
    require(external['wrapper'] == wrapper and external['wrapper_after_sha256'] == WRAPPER_SHA
        and plan['external_wrapper'] == wrapper, 'external_wrapper_identity')
    python = {'python': sys.executable, 'sha256': sha(sys.executable)}
    require(plan['environment'] == python and external['python_sha256'] == python['sha256']
        and external['python_after_sha256'] == python['sha256'], 'external_python_identity')
    expected_outputs = {name: ref(output/name) for name in ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json')}
    require(external['outputs'] == expected_outputs, 'external_outputs')
    require(receipt['plan_sha256'] == expected_outputs['plan.json']['sha256']
        and bounded['receipt_sha256'] == expected_outputs['receipt.json']['sha256'], 'external_receipt_chain')
    require(plan['output_directory'] == str(output) and bounded['output_directory'] == str(output)
        and bounded['command'] == command, 'external_inner_command_binding')
    require(all(type(external[name]) is int and external[name] == 0
        for name in ('native_calls', 'model_predictions', 'real_original_proof_calls')), 'external_forbidden_calls')
    return {'status': 'validated_complete_external_pure_lifetime', 'elapsed_ticks': ticks,
        'stopwatch_frequency': frequency, 'external_application_seconds': seconds}


def remaining(elapsed):
    require(type(elapsed) in (int, float) and elapsed >= 0 and elapsed < LIMIT-1, 'remaining_budget')
    return LIMIT-elapsed-1.


def check_plan(output, plan):
    require(plan['schema'] == SCHEMA and plan['planned_calls'] == 65 and plan['whole_shared_seconds'] == LIMIT
        and plan['call_order'] == list(range(65)), 'fixed_scope')
    require(plan['comparison_origin'] == {'path': str(BASE/'plan.json'), 'sha256': BASE_PLAN,
        'JSON_field': 'source_proof'}, 'proof_source_field')
    target = plan['comparison_proof']
    require(Path(target['path']).resolve() == (Path(output)/'target.json').resolve()
        and sha(target['path']) == target['sha256'], 'target_identity')
    target_bytes = Path(target['path']).read_bytes()
    require(target_bytes == kernel.encoded(read(BASE/'plan.json')['source_proof']), 'original_proof_target_bytes')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'interpreter_identity')


def prepare(output):
    no_execution_extensions(pure=True)
    base = base_gate(); pure = pure_gate(); files = source_files()
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    mapping = archive_sources(ROOT, output, files)
    with (output/'target.json').open('xb') as stream:
        stream.write(kernel.encoded(base['source_proof']))
    evidence = {str(BASE/name): sha(BASE/name) for name in ('plan.json', 'receipt.json', 'root_saved_review_001.json',
        'entry_pins.json', 'exit_pins.json', 'bounded_execution.json', 'external_application_wall.json')}
    evidence.update({value['path']: value['sha256'] for value in pure.values()})
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'planned_calls': 65,
        'call_order': list(range(65)), 'whole_shared_seconds': LIMIT,
        'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        'source_archive': mapping, 'evidence_sha256': evidence, 'focused_pure': pure,
        'comparison_origin': {'path': str(BASE/'plan.json'), 'sha256': BASE_PLAN, 'JSON_field': 'source_proof'},
        'comparison_proof': ref(output/'target.json'),
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'rules': ['Exactly65 unchanged original source_proof calls; no function/global replacement or proof cache.',
            'Original callable is timed; cProfile records nested functions. Cumulative times overlap and cannot be summed.',
            'Complete proof is saved before byte comparison; returned report and ALL65 rows are written again in finalization.',
            'Preparation and pure tests never import the original future module; only admitted actual worker imports it.',
            'Imports/setup/pins, proof encoding/export, profile statistics and final source checks remain in shared120.',
            'No model/native/custom-data-C calls, speed claim, hidden-state claim or100ms certification.'],
        'model_predictions': 0, 'native_calls': 0}
    verify_archive(ROOT, output, plan); check_plan(output, plan)
    write(output/'plan.json', plan); check_plan(output, read(output/'plan.json'))
    write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': ref(output/'plan.json'),
        'source_count': len(files), 'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
            '--expected-plan', sha(output/'plan.json')], 'original_proof_calls_during_preparation': 0})
    no_execution_extensions(pure=True)


def empty_report():
    return {'schema': SCHEMA, 'status': 'unknown_worker_setup', 'planned_calls': 65,
        'actual_calls': 0, 'exact_proofs': 0, 'unknown_rows': 65, 'unexecuted_rows': 65,
        'rows': [{'ordinal': i, 'status': 'unknown_unexecuted', 'invoked': False} for i in range(65)],
        'model_predictions': 0, 'native_calls': 0}


def finalize_report(output, report):
    """Required again even if the kernel's last persistence callback failed."""
    require(type(report['rows']) is list and len(report['rows']) == 65
        and [row['ordinal'] for row in report['rows']] == list(range(65)), 'final_denominator')
    write(Path(output)/'rows.json', report['rows'])
    report['rows_file'] = ref(Path(output)/'rows.json')
    write(Path(output)/'report.json', report)


def worker(output, expected):
    started = time.perf_counter_ns(); report = empty_report(); plan = None; entry = None
    try:
        require(sha(output/'plan.json') == expected, 'worker_plan')
        plan = read(output/'plan.json'); check_plan(output, plan); verify_archive(ROOT, output, plan)
        no_execution_extensions(); require(gc.isenabled(), 'default_GC')
        for path, digest in plan['evidence_sha256'].items():
            require(sha(path) == digest, 'evidence_entry:'+path)
        entry = {name: sha(ROOT/name) for name in plan['source_sha256']}
        write(output/'entry_pins.json', entry)
        # Deliberately absent from pure and preparation execution paths.
        from . import live_obligation_future_later_fork as future
        original = future.source_proof
        kernel.bind_original(future, original)
        identity = (original.__code__, original.__defaults__, original.__kwdefaults__, original.__closure__)
        loaded_entry = loaded_sources(plan['source_sha256']); write(output/'loaded_entry.json', loaded_entry)
        comparison = Path(plan['comparison_proof']['path']).read_bytes()
        setup_end = time.perf_counter_ns(); export_ns = 0
        def save_proof(ordinal, raw):
            nonlocal export_ns
            begin = time.perf_counter_ns(); path = output/'proofs'/f'{ordinal:02}.json'
            path.parent.mkdir(exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
            value = ref(path); export_ns += time.perf_counter_ns()-begin
            return value
        def persist_rows(rows):
            nonlocal export_ns
            begin = time.perf_counter_ns(); write(output/'rows.json', rows)
            export_ns += time.perf_counter_ns()-begin
        report = kernel.profile_series(original, comparison, raw_profile_path=output/'calls.pstats',
            save_proof=save_proof, persist_rows=persist_rows)
        diagnostic_end = time.perf_counter_ns()
        report['driver_schema'] = SCHEMA
        report['clocks'] = {'setup_ns': setup_end-started, 'diagnostic_total_ns': diagnostic_end-setup_end,
            'callback_proof_export_and_rows_persist_ns': export_ns,
            'profile_original_call_ns': sum(row.get('timing', {}).get('elapsed_ns') or 0 for row in report['rows'])}
        kernel.bind_original(future, original)
        require(all(a is b for a, b in zip(identity, (original.__code__, original.__defaults__, original.__kwdefaults__, original.__closure__), strict=True)), 'original_identity_changed')
        report['original_function_identity_unchanged'] = True
        stats = pstats.Stats(str(output/'calls.pstats'))
        key = (original.__code__.co_filename, original.__code__.co_firstlineno, original.__code__.co_name)
        report['profile_original_calls'] = stats.stats.get(key, (0, 0, 0, 0))[1]
        require(report['profile_original_calls'] == report['actual_calls'], 'profile_call_count')
        write(output/'loaded_exit.json', loaded_sources(plan['source_sha256']))
        require(read(output/'loaded_exit.json') == loaded_entry, 'loaded_source_domain_changed')
        report['clocks']['post_diagnostic_checks_ns'] = time.perf_counter_ns()-diagnostic_end
    except BaseException as error:
        report['status'] = 'unknown_worker_failure'
        report['worker_error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        if plan is not None:
            try:
                verify_archive(ROOT, output, plan)
                exit_pins = {name: sha(ROOT/name) for name in plan['source_sha256']}
                write(output/'exit_pins.json', exit_pins)
                report['source_changed'] = [name for name, digest in plan['source_sha256'].items() if exit_pins.get(name) != digest]
                require(entry == exit_pins, 'entry_exit_source_change')
                for path, digest in plan['evidence_sha256'].items():
                    require(sha(path) == digest, 'evidence_exit:'+path)
                no_execution_extensions()
            except BaseException as error:
                report['status'] = 'unknown_final_binding_failure'
                report['binding_error'] = repr(error)
        export_started = time.perf_counter_ns()
        # Even failures that occurred after returning a proof or between two
        # incremental writes cannot disappear from the final saved denominator.
        finalize_report(output, report)
        receipt = {'schema': SCHEMA, 'status': report['status'], 'actual_calls': report['actual_calls'],
            'exact_proofs': report['exact_proofs'], 'unknown_rows': report['unknown_rows'],
            'report': ref(output/'report.json'), 'rows': ref(output/'rows.json'),
            'final_report_rows_export_ns': time.perf_counter_ns()-export_started,
            'worker_before_receipt_ns': time.perf_counter_ns()-started,
            'plan_sha256': expected, 'source_changed': report.get('source_changed'),
            'model_predictions': 0, 'native_calls': 0}
        write(output/'receipt.json', receipt)
    return 0 if report['status'] == 'exact65_original_source_proofs_profiled' else 1


def execute(output, expected):
    from . import bounded_windows_job
    require(sha(output/'plan.json') == expected and read(output/'plan.json')['schema'] == SCHEMA, 'launch_plan')
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': expected, 'shared_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', expected]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        before = time.monotonic()-BOOT
        process = bounded_windows_job.run(command, timeout=remaining(before), admission=expected,
            stdout=stdout, stderr=stderr, cwd=ROOT)
    elapsed = time.monotonic()-BOOT
    receipt = read(output/'receipt.json') if (output/'receipt.json').is_file() else None
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and elapsed <= LIMIT and receipt is not None and receipt['status'] == 'exact65_original_source_proofs_profiled'
    write(output/'bounded_execution.json', {'status': 'passed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'plan_sha256': expected, 'shared_seconds': LIMIT,
        'parent_setup_seconds': before, 'application_before_final_receipt_seconds': elapsed,
        'worker_receipt': ref(output/'receipt.json') if receipt else None,
        'external_python_launch_through_exit_required': True, 'model_predictions': 0, 'native_calls': 0})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


def prepare_bounded(output):
    """One metadata-only owned120 tree; preparation/execute logs are distinct."""
    from . import bounded_windows_job
    output = Path(output).resolve()
    require(not output.exists(), 'prepare_output_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    claim = output.with_name(output.name+'.prepare_claim.json')
    with claim.open('x', encoding='utf8') as stream:
        json.dump({'schema': SCHEMA+'.prepare_admission', 'shared_seconds': LIMIT}, stream)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--prepare-worker', '--output', str(output), '--prepare-token', token]
    stdout_path = output.with_name(output.name+'.prepare.stdout.log')
    stderr_path = output.with_name(output.name+'.prepare.stderr.log')
    report = {'schema': SCHEMA+'.bounded_prepare', 'status': 'unknown_prepare_failure',
        'shared_seconds': LIMIT, 'command': command, 'original_proof_calls': 0,
        'model_predictions': 0, 'native_calls': 0}
    try:
        with stdout_path.open('x') as stdout, stderr_path.open('x') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining(time.monotonic()-BOOT),
                admission=token, stdout=stdout, stderr=stderr, cwd=ROOT)
        report['process'] = process
        if process['status'] == 'exited' and process['exitcode'] == 0 and time.monotonic()-BOOT <= LIMIT:
            ready = read(output/'ready.json')
            require(ready['status'] == 'prepared_unexecuted' and ready['plan'] == ref(output/'plan.json'), 'prepared_ready')
            report.update(status='prepared_bounded_unexecuted', plan=ref(output/'plan.json'), ready=ref(output/'ready.json'))
    except BaseException as error:
        report['error'] = repr(error)
    report['application_before_final_export_seconds'] = time.monotonic()-BOOT
    if report['application_before_final_export_seconds'] > LIMIT:
        report['status'] = 'unknown_prepare_budget_exceeded'
    write(output.with_name(output.name+'.prepare_bounded.json'), report)
    return 0 if report['status'] == 'prepared_bounded_unexecuted' and time.monotonic()-BOOT <= LIMIT else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--expected-plan')
    parser.add_argument('--prepare-worker', action='store_true'); parser.add_argument('--prepare-token')
    args = parser.parse_args(); output = args.output.resolve()
    if args.prepare:
        return prepare_bounded(output)
    if args.prepare_worker:
        require(args.prepare_token and sys.stdin.readline() == args.prepare_token+'\n', 'owned_prepare_admission')
        try:
            prepare(output)
        except BaseException:
            write(output.with_name(output.name+'.prepare_failure.json'),
                {'status': 'unknown_prepare_failure', 'error': traceback.format_exc()})
            raise
        return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline() == args.expected_plan+'\n', 'owned_admission')
        return worker(output, args.expected_plan)
    require(args.execute, 'explicit_execute')
    return execute(output, args.expected_plan)


if __name__ == '__main__':
    raise SystemExit(main())
