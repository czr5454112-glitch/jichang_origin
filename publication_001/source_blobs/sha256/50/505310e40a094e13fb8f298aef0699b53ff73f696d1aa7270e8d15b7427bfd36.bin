"""Versioned full96 v2 conformance; frozen v1 implementation/checks retained.

Only the model candidate, schema, source proof and focused pure gate are rebound
in a private full-global namespace. Original context/worker/early-save/journal,
ordinal late binding, 226/192 checks and all96 exact old outputs are unchanged.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import copy
import hashlib
from pathlib import Path
import sys
import traceback
from types import FunctionType
import xml.etree.ElementTree as ET
from . import validate_live_communication_scoped_inputs as frozen
from . import public_live_obligation_scoped_inputs_v2 as candidate
from . import measure_scoped_public_inputs_v2_six as cost

ROOT, OUT, ORDER = frozen.ROOT, frozen.OUT, frozen.ORDER
MODULE = 'scripts.experiments.g31_ics_circulation.validate_live_communication_scoped_inputs_v2'
TEST = 'tests/test_g31_circulation_live_communication_scoped_inputs_v2.py'
PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_live_communication_scoped_inputs_v2_pure'
PURE = OUT/'live_communication_scoped_inputs_v2_pure_001'
V1 = OUT/'live_communication_scoped_inputs_prepare_001'
V2 = OUT/'scoped_public_inputs_v2_six_cost_prepare_001'
V1_PLAN = '68024f30b1cc262a7162b67b8a9828885ed5d5c738316cfd44585fb40b1ad7f8'
V2_PLAN = 'b1e5a14e4362c84f79b16ca22607086b29db3213b0ff588248ec9461816292c0'
V2_REPORT = '05a338830db5d8b0b8e5ab54c2542a9ad4a4d9201d19538019dda672148d0063'
SCHEMA = 'g31.live_communication_scoped_inputs_conformance.v2'
LIMIT = 360.
PURE_COUNT = 25
sha, read, ref, write, require = frozen.sha, frozen.read, frozen.ref, frozen.write, frozen.require
SaveBeforeReturn = frozen.SaveBeforeReturn
early_inventory = frozen.early_inventory
mapping_allowed = frozen.mapping_allowed
exact_predictions = frozen.exact_predictions
run_original = frozen.run_original
no_execution_extensions = frozen.no_execution_extensions


def private(function, updates):
    result = FunctionType(function.__code__, {**function.__globals__, **updates}, function.__name__,
        function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def worker_function():
    return private(frozen.worker, {'candidate': candidate, 'SCHEMA': SCHEMA,
        'source_proof': source_proof, 'pure_gate': pure_gate})


def source_proof():
    function = worker_function(); original = frozen.worker
    allowed = {'candidate', 'SCHEMA', 'source_proof', 'pure_gate'}
    require(function.__code__ is original.__code__ and function.__defaults__ is original.__defaults__
        and function.__closure__ is original.__closure__ and function.__kwdefaults__ is original.__kwdefaults__
        and set(function.__globals__) == set(original.__globals__)
        and all(function.__globals__[key] is value for key,value in original.__globals__.items() if key not in allowed),
        'v2_full96_only_four_outer_globals')
    require(function.__globals__['candidate'] is candidate and function.__globals__['SCHEMA'] == SCHEMA
        and function.__globals__['source_proof'] is source_proof and function.__globals__['pure_gate'] is pure_gate,
        'v2_full96_bindings')
    inherited = private(frozen.source_proof, {'candidate': candidate})()
    require(all(function.__globals__[name] is getattr(frozen, name) for name in
        ('SaveBeforeReturn', 'run_original', 'early_inventory', 'mapping_allowed', 'exact_predictions', 'loaded_sources')),
        'v1_all_checks_and_early_save_identity')
    return {**inherited, 'schema': SCHEMA, 'v1_outer_worker_code_defaults_closure_unchanged': True,
        'v1_outer_globals_changed_only': sorted(allowed), 'fresh_candidate_version': 2,
        'initial_context_caller_unchanged': True, 'full96_original_old_targets_unchanged': True,
        'all96_invocations_before_ordinal_mapping': True,
        'old_modelspan_includes_export_hash_journal': True, 'component_ABBA_speed_comparison': False}


def pure_gate():
    receipt = read(PURE/'receipt.json'); cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status'] == 'passed' and receipt['source_changed'] == []
        and receipt['tests'] == len(cases) == PURE_COUNT and receipt['XML_sha256'] == sha(PURE/'tests.xml')
        and receipt['native_calls'] == receipt['model_calls'] == receipt['actual_saved_raw_decodes'] == 0
        and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'v2_focused_pure')
    for name, digest in receipt['source_sha256'].items():
        require(sha(ROOT/name) == digest == sha(PURE/'source'/name), 'v2_tested_source')
    outer = read(PURE/'external_application_wall.json')
    require(outer['exitcode'] == 0 and 0 < outer['whole_python_seconds'] <= 120
        and outer['includes_python_startup_and_exit'] is True, 'v2_focused_external_wall')
    # Original53 early-save/ordinal/exception counterexamples remain the same
    # functions, and their frozen source receipt remains required.
    frozen.pure_gate()
    return receipt


def source_union():
    files = frozen.image.source_closure(ROOT, (MODULE, PURE_MODULE, TEST[:-3].replace('/', '.')))
    for folder, expected, count in ((V1, V1_PLAN, 155), (V2, V2_PLAN, 157)):
        require(sha(folder/'plan.json') == expected, 'v2_prior_plan_identity')
        plan = read(folder/'plan.json'); require(len(plan['source_sha256']) == count, 'v2_prior_source_count')
        for path, digest in plan['source_sha256'].items():
            require(sha(path) == digest == sha(folder/plan['source_archive'][path]), 'v2_prior_source_archive')
            files[str(Path(path).relative_to(ROOT))] = Path(path).read_bytes()
    return files


def prepare(output):
    no_execution_extensions(); pure = pure_gate(); files = source_union()
    previous = read(V1/'plan.json'); previous_final = read(V1/'final_receipt.json')
    require(previous_final['status'] == 'exact_all96_original_checks_and_full_outputs'
        and previous_final['full_output_exact'] == 96 and previous_final['unknown_or_difference'] == 0
        and previous_final['actual_collection_data_checks'] == 226 and previous_final['actual_known_collection_data'] == 192
        and previous_final['early_ordinal_mapping_certified'] is True and previous_final['source_changed'] == [], 'v1_actual_complete')
    require(sha(V2/'report.json') == V2_REPORT, 'v2_actual_ABBA_identity')
    cost_report = read(V2/'report.json')
    require(cost_report['status'] == 'passed_fixed_six_ABBA24_complete_prediction'
        and cost_report['exact'] == 24 and cost_report['unknown'] == 0 and cost_report['source_changed'] == [], 'v2_actual_ABBA_passed')
    output.mkdir(exist_ok=False); pins = {}; archives = {}
    for name,data in sorted(files.items()):
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        pins[str(ROOT/name)] = hashlib.sha256(data).hexdigest(); archives[str(ROOT/name)] = str(path.relative_to(output))
    for name,digest in pure['source_sha256'].items(): require(pins[str(ROOT/name)] == digest, 'focused_source_in_plan')
    fixed = dict(previous['fixed_evidence_sha256'])
    fixed.update(read(V2/'plan.json')['evidence_sha256'])
    for folder,names in ((V1, ('plan.json', 'receipt.json', 'rows.json', 'final_receipt.json', 'equivalence96.json',
            'early_prediction_inventory.json', 'bounded_execution.json', 'external_application_wall.json')),
        (V2, ('plan.json', 'report.json', 'receipt.json', 'bounded_execution.json', 'external_application_wall.json')),
        (PURE, ('receipt.json', 'tests.xml', 'external_application_wall.json'))):
        for name in names: fixed[str(folder/name)] = sha(folder/name)
    for folder in (V1, V2):
        prior = read(folder/'plan.json')
        for path,digest in prior['source_sha256'].items(): fixed[str(folder/prior['source_archive'][path])] = digest
    plan = {**copy.deepcopy(previous), 'schema': SCHEMA,
        'source_sha256': pins, 'source_archive': archives, 'fixed_evidence_sha256': fixed,
        'source_proof': source_proof(), 'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'hard_timeout_seconds': LIMIT, 'model_variant': 'fresh_scoped_public_inputs_v2_per_prediction',
        'v1_full96_reference': ref(V1/'final_receipt.json'), 'v2_ABBA24_reference': ref(V2/'report.json'),
        'v1_full96_source_count': 155, 'v2_scoped_source_count': 157,
        'rules': previous['rules']+[
            'V1 outer worker code/defaults/closures/all check functions preserved; only candidate/schema/sourceproof/puregate private globals differ.',
            'V2 creates one fresh scope per prediction; selected-case deepcopy, identify-only read-only borrow and historical base alias fix only.',
            'Original initial-context caller remains unchanged and charged in whole; no initial-context sharing optimization in this version.',
            'V1 actual96 and v2 ABBA24 evidence are references; neither result cache nor future target is passed into a model.',
            'No comparison of this modelspan including early export against the ABBA-only predictor span.'],
        'budget': {**previous['budget'], 'fixed_application_seconds': LIMIT,
            'basis': 'V1 exact full96 whole79.9378395s; v2 six ABBA is promising but not a bound. Keep original shared360 for startup/hash/all checks/export/cleanup.'},
        'preparation_model_calls': 0, 'preparation_raw_decodes': 0}
    write(output/'plan.json', plan); write(output/'rows.json', copy.deepcopy(plan['rows']))
    write(output/'ready.json', {'status': 'prepared_source_review_pending', 'plan': ref(output/'plan.json'),
        'source_count': len(pins), 'focused_pure_tests': PURE_COUNT, 'retained_v1_pure_tests': 53,
        'fixed_application_seconds': LIMIT, 'native_calls': 0, 'model_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--expected-plan', sha(output/'plan.json')]})


def worker(output, expected):
    worker_function()(output, expected)
    require(read(output/'final_receipt.json')['status'] == 'exact_all96_original_checks_and_full_outputs', 'v2_complete_gate')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--expected-plan')
    args = parser.parse_args(); output = args.output.resolve(); no_execution_extensions()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(sys.stdin.readline() == args.expected_plan+'\n', 'v2_owned_admission')
        try: worker(output, args.expected_plan)
        except BaseException:
            write(output/'worker_failure.json', {'status': 'unknown_worker_failure', 'error': traceback.format_exc()}); raise
        return 0
    require(args.execute and sha(output/'plan.json') == args.expected_plan, 'v2_reviewed_execute')
    with (output/'execution_claim').open('x'): pass
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', args.expected_plan]
    remaining = LIMIT-(time.monotonic()-BOOT)-1.; require(remaining > 0, 'v2_before_worker_budget')
    with (output/'stdout.log').open('x') as out, (output/'stderr.log').open('x') as err:
        process = frozen.bounded_windows_job.run(command, timeout=remaining, stdout=out, stderr=err, admission=args.expected_plan, cwd=ROOT)
    wall = time.monotonic()-BOOT
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and wall <= LIMIT
    write(output/'bounded_execution.json', {'status': 'bounded_worker_completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'application_seconds_before_receipt': wall, 'fixed_application_seconds': LIMIT,
        'plan_sha256': args.expected_plan, 'source': ref(__file__),
        'final_receipt': ref(output/'final_receipt.json') if (output/'final_receipt.json').exists() else None,
        'external_python_launch_through_exit_required': True, 'native_calls': 0})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


if __name__ == '__main__': raise SystemExit(main())
