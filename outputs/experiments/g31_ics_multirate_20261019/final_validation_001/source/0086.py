"""One cold bind and one warm proof: dependency-domain gate, not a speed test.

Preparation never imports the real future model. Only an owned, source-bound
worker may import its definitions and call bind_request once. A sticky profile
monitor counts original/private proof entries and rejects model entry points.
Unsupported dependency objects remain failed/unknown; there is no retry.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET

from . import diagnose_future_source_inventory as archive
from . import profile_future_source_inventory as codec

ROOT = archive.ROOT
MODULE = __package__ + '.diagnose_bound_source_proof_bind'
PURE = ROOT/'outputs/bsp1'
ORIGINAL = ROOT/'outputs/si65d1'
LIMIT = 120.
SCHEMA = 'g31.bound_source_proof.one_bind_one_use.v1'
PURE_PINS = {
    'plan.json': 'd6f98f3490ec66c510ed64e552a4b621c993d90e9cd07dd087c0ba0869b5c27c',
    'receipt.json': '25ccefdc80d011ec60235db52b6fedac3f30a05336e65e7d4652f7348ed77599',
    'tests.xml': 'f881423d8c3ba829d774dc58d34027750503ee0a8f20fd684cfab36b25013c10',
    'bounded_parent_receipt.json': '3a920c9bc712a0a362a12b373fe8d8d9713a2549f90d72d4f956a65ec6cf2482',
    'external_application_wall.json': '0cb3b8254b8b71ba0e7a56d412a03d22db4c78144673d5d46c18e6ca7e7380f9',
    'root_saved_review_001.json': 'b668953d24cad5e8e96a3bf0243f8048cbab94389debe2f4efbcf053a8f80949',
}
ORIGINAL_PINS = {
    'plan.json': 'cc6432f563f1b447ebac5c8058f93cc6e721f6711ba33e2c1dbe6baa60bec0c6',
    'receipt.json': '6f921d8be061073e95b410c21557308a36e49ff40245dd419da2a55edc38cb1c',
    'report.json': '7f919ed5e699c90dad78c78d0fc6859a83a2f90457d260c3a9f85e812e9c406f',
    'rows.json': 'caada336444cc9c7db6f545f12e6f483ef2bd9093e428cbb56910c2ac04f99ed',
    'bounded_execution.json': '94c6c5eaa00bd6625dfea4137f62d3cc7c0da3ba395737c8a0af4a60d9eda14f',
    'external_application_wall.json': '79d98ac99373a88d60f4b3ccc132eba2aff0749ee192b44004e3e18a8eb3d519',
}
sha, read, write, ref, require = archive.sha, archive.read, archive.write, archive.ref, archive.require


def prior_gate():
    evidence = {}
    for directory, pins in ((PURE, PURE_PINS), (ORIGINAL, ORIGINAL_PINS)):
        for name, digest in pins.items():
            require(sha(directory/name) == digest, 'prior_identity:' + name)
            evidence[str(directory/name)] = digest
    plan, receipt = read(PURE/'plan.json'), read(PURE/'receipt.json')
    outer, bounded = read(PURE/'external_application_wall.json'), read(PURE/'bounded_parent_receipt.json')
    require(plan['schema'] == 'g31.bound_source_proof.synthetic_pure.v1'
        and receipt['status'] == 'passed' and receipt['tests'] == 37
        and receipt['source_changed'] == [] and receipt['blocked_real_calls'] == []
        and receipt['monitor_active_after_tests'] is True, 'pure37_status')
    require(receipt['plan_sha256'] == PURE_PINS['plan.json']
        and receipt['XML_sha256'] == PURE_PINS['tests.xml']
        and bounded['receipt_sha256'] == PURE_PINS['receipt.json']
        and bounded['status'] == 'passed', 'pure_chain')
    frequency, ticks = outer['stopwatch_frequency'], outer['elapsed_ticks']
    require(outer['schema'] == 'g31.bound_source_proof.pure_external.v1'
        and outer['status'] == 'passed37_synthetic_with_external_bound'
        and type(frequency) is int and frequency > 0 and type(ticks) is int
        and 0 <= ticks <= 120*frequency and outer['exitcode'] == 0
        and outer['wrapper_exitcode'] == 0, 'pure_whole_budget')
    cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 37 and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'pure_XML')
    archive.verify_archive(ROOT, PURE, plan)
    original = read(ORIGINAL/'receipt.json')
    require(original['status'] == 'exact65_original_source_proofs_profiled'
        and original['actual_calls'] == original['exact_proofs'] == 65
        and original['unknown_rows'] == 0 and original['source_changed'] == [], 'original65_status')
    base = archive.base_gate()
    target = (ORIGINAL/'proofs/00.json').read_bytes()
    require(target == codec.encoded(base['source_proof']), 'original65_proof_target')
    evidence[str(ORIGINAL/'proofs/00.json')] = hashlib.sha256(target).hexdigest()
    evidence[str(archive.BASE/'plan.json')] = archive.BASE_PLAN
    return plan, evidence, target


def source_files():
    from . import initial_owner_route_image as image
    pure, _, _ = prior_gate()
    files = {}
    for name, digest in pure['source_sha256'].items():
        raw = (ROOT/archive.relative_python(name)).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'bind_inherited_source_identity:' + name)
        files[name] = raw
    extra = image.source_closure(ROOT, (MODULE,
        'tests.test_g31_circulation_bound_source_proof_bind_driver'))
    for name, raw in extra.items():
        archive.relative_python(name)
        require(name not in files or files[name] == raw, 'bind_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def fixed_scope():
    return {'cold_bind_requests': 1, 'maximum_original_source_proof_calls': 1,
        'warm_facade_proof_uses': 1, 'fork_calls': 0, 'resume_calls': 0,
        'engine_constructions': 0, 'model_predictions': 0, 'native_calls': 0,
        'custom_data_C_loads': 0, 'unsupported_dependency_policy': 'unknown_no_retry_no_omission'}


def driver_pure_gate():
    """Required only for preparation, never while collecting these tests."""
    output = (ROOT/'outputs/bdbp1').resolve()
    plan, receipt, bounded, external = (read(output/name) for name in
        ('plan.json', 'receipt.json', 'bounded_parent_receipt.json', 'external_application_wall.json'))
    expected_command = [sys.executable, '-m', __package__+'.run_bound_source_proof_bind_pure', '--output', str(output)]
    require(plan['schema'] == 'g31.bound_source_proof.synthetic_pure.v1'
        and plan['tests'] == ['tests/test_g31_circulation_bound_source_proof_bind_driver.py']
        and type(plan['expected_tests']) is int and plan['expected_tests'] == 15
        and plan['shared_seconds'] == LIMIT and plan['output_directory'] == str(output)
        and plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'driver_pure_plan')
    require(receipt['status'] == 'passed' and receipt['tests'] == receipt['expected_tests'] == 15
        and receipt['pytest_exitcode'] == 0 and receipt['source_changed'] == []
        and receipt['blocked_real_calls'] == [] and receipt['monitor_active_after_tests'] is True,
        'driver_pure_complete')
    require(all(type(receipt[k]) is int and receipt[k] == 0 for k in
        ('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads')), 'driver_pure_no_actual')
    require(receipt['plan_sha256'] == sha(output/'plan.json') and receipt['XML_sha256'] == sha(output/'tests.xml')
        and bounded['receipt_sha256'] == sha(output/'receipt.json') and bounded['command'] == expected_command
        and bounded['output_directory'] == str(output) and bounded['shared_seconds'] == LIMIT
        and bounded['status'] == 'passed' and bounded['process']['status'] == 'exited'
        and bounded['process']['exitcode'] == 0, 'driver_pure_bound_chain')
    cases = ET.parse(output/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 15 and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'driver_pure_XML15')
    archive.verify_archive(ROOT, output, plan)
    frequency, ticks, seconds = (external[k] for k in
        ('stopwatch_frequency', 'elapsed_ticks', 'external_application_seconds'))
    require(external['schema'] == 'g31.bound_source_proof.bind_driver_pure_external.v1'
        and external['status'] == 'passed15_synthetic_with_external_bound'
        and external['command'] == expected_command and external['cwd'] == str(ROOT.resolve())
        and external['output_directory'] == str(output) and external['launched'] is True
        and type(external['exitcode']) is int and external['exitcode'] == 0
        and type(external['wrapper_exitcode']) is int and external['wrapper_exitcode'] == 0,
        'driver_pure_external_execution')
    require(type(frequency) is int and frequency > 0 and type(ticks) is int and 0 <= ticks <= 120*frequency
        and type(seconds) in (int, float) and math.isfinite(seconds)
        and seconds == float(ticks)/float(frequency)
        and external['shared_limit_seconds'] == LIMIT
        and external['clock_scope'] == 'immediately_before_python_launch_through_process_return', 'driver_pure_external_clock')
    output_names = ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'stdout.log', 'stderr.log')
    require(external['outputs'] == {name: ref(output/name) for name in output_names}, 'driver_pure_external_outputs')
    wrapper = ROOT/'outputs/invoke_bdbp1.ps1'
    expected = {str(wrapper): sha(wrapper), sys.executable: sha(sys.executable)}
    for name in ('scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof.py',
                 'scripts/experiments/g31_ics_circulation/live_obligation_bound_future_fork.py',
                 'scripts/experiments/g31_ics_circulation/run_bound_source_proof_pure.py',
                 'tests/test_g31_circulation_bound_source_proof.py',
                 'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind.py',
                 'scripts/experiments/g31_ics_circulation/run_bound_source_proof_bind_pure.py',
                 'tests/test_g31_circulation_bound_source_proof_bind_driver.py'):
        expected[str(ROOT/archive.relative_python(name))] = plan['source_sha256'][name]
    require(external['expected_pins'] == external['pins_before'] == external['pins_after'] == expected,
        'driver_pure_external_all_pins')
    return {str(output/name): sha(output/name) for name in (*output_names, 'external_application_wall.json')} | {str(wrapper): sha(wrapper)}


def prepare(output):
    archive.no_execution_extensions(pure=True)
    _, evidence, target = prior_gate()
    evidence.update(driver_pure_gate())
    files = source_files()
    output.mkdir(parents=True, exist_ok=False)
    mapping = archive.archive_sources(ROOT, output, files)
    with (output/'target.json').open('xb') as stream:
        stream.write(target)
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'scope': fixed_scope(),
        'shared_seconds': LIMIT, 'output_directory': str(output),
        'source_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        'source_archive': mapping, 'evidence_sha256': evidence, 'target': ref(output/'target.json'),
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'limits': ['Only the dependency-domain gate; no full32 or unprofiled speed claim.',
            'Default GC retained. The sticky Python call monitor is included in measured costs.',
            'Complete proof bytes are saved before target comparison; each failure stage is retained.',
            'No fork/resume/engine. Actual unsupported dependencies abort rather than being omitted.']}
    write(output/'plan.json', plan)
    check_plan(output, read(output/'plan.json'))
    write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': ref(output/'plan.json'),
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
                            '--expected-plan', sha(output/'plan.json')]})


def check_plan(output, plan):
    require(plan['schema'] == SCHEMA and plan['scope'] == fixed_scope()
        and plan['shared_seconds'] == LIMIT and plan['output_directory'] == str(output), 'bind_fixed_scope')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'bind_interpreter')
    archive.verify_archive(ROOT, output, plan)
    for path, digest in plan['evidence_sha256'].items():
        require(sha(path) == digest, 'bind_evidence_changed:' + path)
    require(plan['target'] == ref(output/'target.json')
        and (output/'target.json').read_bytes() == (ORIGINAL/'proofs/00.json').read_bytes(), 'bind_target')


class CallMonitor:
    """Sticky source-code counters; this adds profiling overhead, not speed evidence."""
    def __init__(self, future):
        self.proof_code = future.source_proof.__code__
        self.proof_globals = future.source_proof.__globals__
        self.inventory_code = future._source_inventory.__code__
        self.forbidden = {getattr(future.core, name).__code__ for name in
            ('start_conditional', 'advance_to_collection_or_terminal', 'fork_conditional', 'resume_same_action', '_drive')}
        self.forbidden.update((future.fork_later_action.__code__, future.resume_future_later.__code__))
        for cls in future.core.Projection.__mro__:
            fn = vars(cls).get('__init__')
            if hasattr(fn, '__code__'):
                self.forbidden.add(fn.__code__)
        self.original = 0
        self.private = 0
        self.inventory = 0
        self.blocked = []

    def __call__(self, frame, event, arg):
        if event != 'call':
            return
        code = frame.f_code
        if code in self.forbidden:
            self.blocked.append({'file': code.co_filename, 'function': code.co_name})
            raise RuntimeError('bound_proof_bind:forbidden_model_entry')
        if code is self.proof_code:
            if frame.f_globals is self.proof_globals:
                self.original += 1
            else:
                self.private += 1
        if code is self.inventory_code:
            self.inventory += 1

    def summary(self):
        return {'original_source_proof_calls': self.original, 'private_proof_calls': self.private,
            'original_inventory_calls': self.inventory, 'blocked_model_calls': list(self.blocked)}


def probe(factory, output, target):
    """Testable orchestration only; the real factory is selected solely by worker."""
    report = {'status': 'unknown_bind_unexecuted', 'stages': [], 'cold_bind_requests': 0,
              'warm_proof_uses': 0, 'close_completed': False}
    handle = None
    try:
        report['stage'] = 'cold_bind'
        before = time.perf_counter_ns()
        report['cold_bind_requests'] += 1
        try:
            handle = factory()
        finally:
            report['cold_bind_ns'] = time.perf_counter_ns() - before
        report['stage'] = 'cold_proof_export'
        cold = codec.encoded(handle._proof._proof)
        with (output/'cold_proof.json').open('xb') as stream:
            stream.write(cold)
        report['cold_proof'] = ref(output/'cold_proof.json')
        report['binding_after_cold'] = handle.description()
        require(cold == target, 'cold_complete_proof_bytes')
        report['stages'].append('cold_bound_exact')
        report['stage'] = 'warm_use'
        before = time.perf_counter_ns()
        report['warm_proof_uses'] += 1
        try:
            warm = handle.facade.source_proof()
        finally:
            report['warm_use_ns'] = time.perf_counter_ns() - before
        report['stage'] = 'warm_proof_export'
        warm_bytes = codec.encoded(warm)
        with (output/'warm_proof.json').open('xb') as stream:
            stream.write(warm_bytes)
        report['warm_proof'] = ref(output/'warm_proof.json')
        report['fresh_returned_root'] = warm is not handle._proof._proof
        require(report['fresh_returned_root'] and warm_bytes == cold == target, 'warm_fresh_complete_proof')
        report['binding_after_warm'] = handle.description()
        report['stages'].append('warm_returned_exact')
        report['status'] = 'exact_one_bind_one_warm_pending_close'
    except BaseException:
        report['error'] = traceback.format_exc()
        report['status'] = 'unknown_failed_bind_or_use'
    finally:
        if handle is not None:
            before = time.perf_counter_ns()
            try:
                handle.close()
                report['close_completed'] = True
            except BaseException:
                report['close_error'] = traceback.format_exc()
                report['status'] = 'unknown_failed_close'
            report['close_ns'] = time.perf_counter_ns() - before
        if report['status'] == 'exact_one_bind_one_warm_pending_close' and report['close_completed']:
            report['status'] = 'exact_one_bind_one_warm'
    return report


def worker(output, expected):
    report = {'status': 'unknown_worker_failure', 'scope': fixed_scope()}
    plan = None
    prior = sys.getprofile()
    monitor = None
    try:
        require(sha(output/'plan.json') == expected, 'actual_plan_identity')
        plan = read(output/'plan.json'); check_plan(output, plan)
        require(prior is None and gc.isenabled(), 'bind_default_profile_GC')
        archive.no_execution_extensions(pure=True)
        write(output/'entry_pins.json', {'source_sha256': plan['source_sha256'], 'evidence_sha256': plan['evidence_sha256']})
        from . import live_obligation_bound_future_fork as candidate
        from . import live_obligation_future_later_fork as future
        report['loaded_entry'] = archive.loaded_sources(plan['source_sha256'])
        monitor = CallMonitor(future)
        sys.setprofile(monitor)
        try:
            report['probe'] = probe(candidate.bind_request, output, (output/'target.json').read_bytes())
            report['monitor_active'] = sys.getprofile() is monitor
        finally:
            sys.setprofile(prior)
        report['calls'] = monitor.summary()
        require(report['monitor_active'] and report['calls'] == {'original_source_proof_calls': 1,
            'private_proof_calls': 1, 'original_inventory_calls': 1, 'blocked_model_calls': []}, 'bind_actual_call_counts')
        require(report['probe']['status'] == 'exact_one_bind_one_warm' and gc.isenabled(), 'bind_complete_stages')
        report['status'] = 'validated_actual_dependency_domain_one_use'
    except BaseException:
        report['error'] = traceback.format_exc()
        report['status'] = 'unknown_failed_actual_dependency_domain'
    finally:
        sys.setprofile(prior)
        if monitor is not None:
            report['calls'] = monitor.summary()
        if plan is not None:
            try:
                check_plan(output, plan); archive.no_execution_extensions()
                report['loaded_exit'] = archive.loaded_sources(plan['source_sha256'])
                report['source_changed'] = []
                write(output/'exit_pins.json', {'source_sha256': plan['source_sha256'], 'evidence_sha256': plan['evidence_sha256']})
            except BaseException:
                report['final_binding_error'] = traceback.format_exc()
                report['status'] = 'unknown_final_binding_failure'
        report['plan_sha256'] = expected
        report['monitor_cost_included'] = True
        report['unprofiled_speedup_or_100ms_claim'] = False
        write(output/'report.json', report)
        write(output/'receipt.json', {'status': report['status'], 'plan_sha256': expected,
            'report': ref(output/'report.json'), 'source_changed': report.get('source_changed'),
            'scope': fixed_scope(), 'external_whole_python_clock_required': True})
    return 0 if report['status'] == 'validated_actual_dependency_domain_one_use' else 1


def parent(output, mode, expected):
    from . import bounded_windows_job
    token = uuid.uuid4().hex
    if mode == 'prepare':
        require(not output.exists(), 'bind_prepare_exists')
        prefix = output.with_name(output.name + '.prepare')
        prefix.parent.mkdir(parents=True, exist_ok=True)
    else:
        require(sha(output/'plan.json') == expected, 'bind_launch_plan')
        prefix = output/'actual'
    with prefix.with_suffix(prefix.suffix+'.claim.json').open('x') as stream:
        json.dump({'mode': mode, 'expected_plan': expected, 'shared_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker-mode', mode, '--output', str(output), '--admission', token]
    if expected is not None:
        command += ['--expected-plan', expected]
    report = {'status': 'unknown_owned_failure', 'shared_seconds': LIMIT, 'command': command, 'mode': mode}
    try:
        remaining = LIMIT - (time.monotonic() - BOOT) - 1.
        require(0 < remaining < LIMIT, 'bind_remaining_budget')
        with prefix.with_suffix(prefix.suffix+'.stdout.log').open('x') as stdout, prefix.with_suffix(prefix.suffix+'.stderr.log').open('x') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token, stdout=stdout, stderr=stderr, cwd=ROOT)
        report['process'] = process
        if process['status'] == 'exited' and process['exitcode'] == 0:
            name = 'ready.json' if mode == 'prepare' else 'receipt.json'
            expected_status = 'prepared_unexecuted' if mode == 'prepare' else 'validated_actual_dependency_domain_one_use'
            require(read(output/name)['status'] == expected_status, 'bind_owned_result')
            report.update(status='passed', worker_result=ref(output/name), plan=ref(output/'plan.json'))
    except BaseException:
        report['error'] = traceback.format_exc()
    report['application_before_export_seconds'] = time.monotonic() - BOOT
    if report['application_before_export_seconds'] > LIMIT:
        report['status'] = 'unknown_shared_timeout'
    write(prefix.with_suffix(prefix.suffix+'.bounded.json'), report)
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' and time.monotonic() - BOOT <= LIMIT else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker-mode', choices=('prepare', 'execute')); parser.add_argument('--admission')
    parser.add_argument('--expected-plan')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker_mode:
        require(args.admission and sys.stdin.readline() == args.admission+'\n', 'bind_owned_admission')
        if args.worker_mode == 'prepare':
            try:
                prepare(output)
            except BaseException:
                write(output.with_name(output.name+'.prepare_failure.json'), {'status': 'unknown_prepare', 'error': traceback.format_exc()})
                raise
            return 0
        return worker(output, args.expected_plan)
    require(args.prepare != args.execute, 'bind_explicit_mode')
    return parent(output, 'prepare' if args.prepare else 'execute', args.expected_plan)


if __name__ == '__main__':
    raise SystemExit(main())
