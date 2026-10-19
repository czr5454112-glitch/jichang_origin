"""Fixed six ABBA24: scoped v1 versus scoped v2, preparation before dispatch.

The frozen worker retains all its original input/context/GC/output/chronology
checks. A private namespace changes only the predictor arms and adds a saved
v1 output check before the final report. No saved result enters a predictor.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import ast
import copy
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
import traceback
from types import FunctionType
import xml.etree.ElementTree as ET
from . import measure_scoped_public_inputs_six as frozen
from . import public_live_obligation_scoped_inputs as v1
from . import public_live_obligation_scoped_inputs_v2 as v2

ROOT, OUT, ORDER = frozen.ROOT, frozen.OUT, frozen.ORDER
MODULE = 'scripts.experiments.g31_ics_circulation.measure_scoped_public_inputs_v2_six'
TEST = 'tests/test_g31_circulation_scoped_public_inputs_v2_cost.py'
RUNNER = 'scripts.experiments.g31_ics_circulation/run_scoped_public_inputs_v2_cost_pure.py'
OLD = OUT/'scoped_public_inputs_six_cost_prepare_001'
SOURCE_PURE = OUT/'scoped_public_inputs_v2_pure_001'
COST_PURE = OUT/'scoped_public_inputs_v2_cost_pure_002'
SOURCE_PREPARE = OUT/'scoped_public_inputs_v2_source_prepare_001'
LIMIT = 120.
SCHEMA = 'g31.scoped_public_inputs.v1_vs_v2.ABBA6.v1'
OLD_PLAN = 'd4c69fe70c5c6bd567677f9a04c2b024b47f1a6e25a9e671a932ef8e938b6d04'
OLD_REPORT = 'f6c8c0ebda0a87d727196bd9afffda795b0267fd492a6e9679ea5a3204fd0f55'
sha, read, write, ref = frozen.sha, frozen.read, frozen.write, frozen.ref


def require(value, reason):
    if not value: raise ValueError('scoped_v2_cost:'+reason)


def _dump(value): return ast.dump(value, include_attributes=False)


def _worker_code():
    original = ast.parse(textwrap.dedent(inspect.getsource(frozen.worker)))
    changed = copy.deepcopy(original); body = changed.body[0].body
    tail = ast.parse("write(output/'report.json',report)").body[0]
    positions = [i for i, node in enumerate(body) if _dump(node) == _dump(tail)]
    require(len(positions) == 1, 'unique_report_write')
    insertion = ast.parse('report = _extend_report(output, plan, ledger, report)').body[0]
    body.insert(positions[0], insertion)
    inverse = copy.deepcopy(changed); del inverse.body[0].body[positions[0]]
    require(_dump(inverse) == _dump(original), 'worker_inverse_AST')
    namespace = {}
    exec(compile(ast.fix_missing_locations(changed), str(Path(__file__)), 'exec'), namespace)
    return namespace['worker'].__code__, hashlib.sha256(_dump(original).encode()).hexdigest()


_WORKER_CODE, _WORKER_AST = _worker_code()


def worker_function():
    namespace = {**frozen.worker.__globals__, 'lazy': v1, 'candidate': v2,
        'pins_now': pins_now, '_extend_report': _extend_report}
    function = FunctionType(_WORKER_CODE, namespace, frozen.worker.__name__,
        frozen.worker.__defaults__, frozen.worker.__closure__)
    function.__kwdefaults__ = frozen.worker.__kwdefaults__
    return function


def source_proof():
    function = worker_function(); old = frozen.worker.__globals__; new = function.__globals__
    allowed = {'lazy', 'candidate', 'pins_now', '_extend_report'}
    require(set(new) == set(old) | {'_extend_report'} and
        all(new[key] is value for key, value in old.items() if key not in allowed), 'complete_worker_globals')
    require(new['lazy'] is v1 and new['candidate'] is v2 and new['pins_now'] is pins_now
        and new['_extend_report'] is _extend_report, 'worker_bindings')
    require(function.__defaults__ is frozen.worker.__defaults__
        and function.__closure__ is frozen.worker.__closure__
        and function.__kwdefaults__ is frozen.worker.__kwdefaults__, 'worker_metadata')
    require(v2.prior is v1 and frozen.candidate is v1, 'predictor_versions')
    return {'schema': SCHEMA, 'original_worker_AST_sha256': _WORKER_AST,
        'worker_inverse_AST_exact_except_final_saved_v1_check': True,
        'unchanged_worker_global_identities_except_explicit_four': True,
        'A': 'frozen scoped v1.predict, fresh scope on every call',
        'B': 'scoped v2.predict, fresh scope on every call',
        'initial_context_caller_unchanged': True,
        'prediction_saved_before_lazy_target_read': True,
        'v1_comparison_only_after_all_model_calls': True,
        'target_read_order_proof_scope': 'source call order, no independent target-read clock',
        'native_or_complete_request_authority': False}


def _extend_report(output, plan, ledger, report):
    """No model/guard call. Inspect every returned prediction, retaining errors."""
    require(len(ledger) == 24 and [(x['key'], x['arm'], x['position']) for x in ledger] ==
        [(x['key'], x['arm'], x['position']) for x in frozen.declaration()], 'full_ledger')
    rows = []; exact = 0
    for item in ledger:
        result = {k: item[k] for k in ('key', 'arm', 'position')}
        result['status'] = 'unknown_no_returned_output'
        if 'raw' in item:
            try:
                require(item['raw'] == ref(item['raw']['path']), 'raw_hash')
                comparator = plan['rows'][item['key']]['comparison_only_v1_prediction']
                require(comparator == ref(comparator['path']), 'v1_comparator_hash')
                saved = gzip.decompress(Path(item['raw']['path']).read_bytes())
                target = gzip.decompress(Path(comparator['path']).read_bytes())
                checks = frozen.base.compare_full(saved, target)
                result.update(checks=checks, raw=item['raw'], comparison_only_v1_prediction=comparator)
                require(all(checks.values()), 'full_v1_prediction_changed')
                result['status'] = 'exact_v1_full_output'
                if item['status'] == 'exact_full_prediction': exact += 1
            except Exception:
                result.update(status='unknown_saved_v1_error', error=traceback.format_exc())
        rows.append(result)
    require(sum(x['arm'] == 'A' for x in rows) == sum(x['arm'] == 'B' for x in rows) == 12, 'arm_denominator')
    report = {**report, 'schema': SCHEMA,
        'status': 'passed_fixed_six_ABBA24_complete_prediction' if exact == 24 else 'unknowns_preserved',
        'exact': exact, 'unknown': 24-exact, 'v1_full_output_checks': rows,
        'source_proof': source_proof(), 'A_version': 'scoped_v1', 'B_version': 'scoped_v2',
        'per_sample_scope_construction_included': True,
        'initial_context_caller_separate_unchanged_inside_whole': True,
        'default_GC_retained': True, 'per_sample_cycle_cleanup_certified': False,
        'whole_process_includes_teardown': True,
        'saved_targets_provided_to_predictor': False}
    if exact != 24:
        report.update(summary_ms={}, paired_median_ms={}, negative_or_equal_cases=[])
    return report


def _pure_receipt(directory, count):
    receipt = read(directory/'receipt.json'); cases = ET.parse(directory/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status'] == 'passed' and receipt['source_changed'] == []
        and receipt['tests'] == count == len(cases)
        and receipt['native_calls'] == receipt['model_engine_runs'] == receipt['performance_runs'] == 0
        and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'focused_pure')
    require(receipt['XML_sha256'] == sha(directory/'tests.xml'), 'focused_XML')
    external = read(directory/'external_application_wall.json')
    require(external['exitcode'] == 0 and 0 < external['whole_python_seconds'] <= 120
        and external['includes_python_startup_and_exit'] is True, 'focused_external_wall')
    for relative, digest in receipt['source_sha256'].items():
        require(sha(ROOT/relative) == digest == sha(directory/'source'/relative), 'focused_pure_source')
    return receipt


def _files():
    files = frozen.image.source_closure(ROOT, (MODULE, TEST[:-3].replace('/', '.'), RUNNER[:-3].replace('/', '.')))
    require(sha(OLD/'plan.json') == OLD_PLAN and sha(OLD/'report.json') == OLD_REPORT, 'prior_actual_identity')
    old = read(OLD/'plan.json')
    for path, digest in old['source_sha256'].items():
        require(sha(path) == digest == sha(OLD/old['source_archive'][path]), 'frozen151_source')
        files[str(Path(path).relative_to(ROOT))] = Path(path).read_bytes()
    # The functional runner is not imported by the performance worker; retain
    # its entire tested source closure nevertheless, including test evidence.
    pure = _pure_receipt(SOURCE_PURE, 36)
    for relative, digest in pure['source_sha256'].items():
        require(sha(ROOT/relative) == digest, 'functional_source')
        files[relative] = (ROOT/relative).read_bytes()
    return files


def _archive(output, files):
    pins = {}; archives = {}
    for name, data in sorted(files.items()):
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        pins[str(ROOT/name)] = hashlib.sha256(data).hexdigest(); archives[str(ROOT/name)] = str(path.relative_to(output))
    return pins, archives


def prepare_source(output):
    frozen.base.no_execution_extensions(); files = _files(); output.mkdir(exist_ok=False)
    pins, archives = _archive(output, files)
    scope = v2.PublicInputScope(); proof = scope.source_proof()
    plan = {'status': 'prepared_source_only', 'source_sha256': pins, 'source_archive': archives,
        'candidate': ref(v2.__file__), 'frozen_v1': ref(v1.__file__), 'source_proof': proof,
        'functional_pure': {name: ref(SOURCE_PURE/name) for name in ('receipt.json', 'tests.xml', 'external_application_wall.json')},
        'native_calls': 0, 'model_engine_runs': 0, 'performance_runs': 0,
        'preparation_public_constructor_calls': 1, 'preparation_saved_endpoint_decode': 0,
        'change_scope': 'Historical helper base alias, selected-case deepcopy, identify-only read-only table borrow. All dynamic guards execute; original initial_context caller unchanged.'}
    write(output/'plan.json', plan)
    write(output/'source_preparation.json', {'status': 'prepared_unexecuted_model', 'plan': ref(output/'plan.json'),
        'sources': len(pins), 'pure_tests': 36, 'source_changed': []})


def prepare(output):
    frozen.base.no_execution_extensions(); _pure_receipt(COST_PURE, COST_TESTS)
    source = read(SOURCE_PREPARE/'plan.json')
    require(source['status'] == 'prepared_source_only' and source['candidate'] == ref(v2.__file__), 'source_preparation')
    for path, digest in source['source_sha256'].items():
        require(sha(path) == digest == sha(SOURCE_PREPARE/source['source_archive'][path]), 'candidate_source_frozen')
    files = _files(); output.mkdir(exist_ok=False); pins, archives = _archive(output, files)
    old = read(OLD/'plan.json'); ledger = read(OLD/'ledger.json'); report = read(OLD/'report.json')
    require(report['exact'] == 24 and report['unknown'] == 0 and report['source_changed'] == [], 'prior_actual_passed')
    require([(r['key'], r['arm'], r['position']) for r in ledger] ==
        [(r['key'], r['arm'], r['position']) for r in frozen.declaration()], 'prior_declaration')
    rows = copy.deepcopy(old['rows']); evidence = dict(old['evidence_sha256'])
    for key in ORDER:
        selected = [r for r in ledger if r['key'] == key and r['arm'] == 'B' and r['position'] == 1]
        require(len(selected) == 1 and selected[0]['status'] == 'exact_full_prediction', 'prior_v1_comparator')
        comparison = selected[0]['raw']; require(comparison == ref(comparison['path']), 'prior_v1_raw')
        rows[key]['comparison_only_v1_prediction'] = comparison
        evidence[comparison['path']] = comparison['sha256']
    for directory, names in ((OLD, ('plan.json', 'report.json', 'receipt.json', 'ledger.json', 'external_application_wall.json')),
        (SOURCE_PREPARE, ('plan.json', 'source_preparation.json')),
        (SOURCE_PURE, ('receipt.json', 'tests.xml', 'external_application_wall.json')),
        (COST_PURE, ('receipt.json', 'tests.xml', 'external_application_wall.json'))):
        for name in names: evidence[str(directory/name)] = sha(directory/name)
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'source_sha256': pins, 'source_archive': archives,
        'evidence_sha256': evidence, 'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'rows': rows, 'order': list(ORDER), 'declaration': frozen.declaration(),
        'hard_application_seconds': LIMIT, 'maximum_model_calls': 24, 'default_GC_required': True,
        'source_proof': source_proof(), 'preparation_model_calls': 0, 'preparation_raw_decodes': 0,
        'scope': 'Fixed six x ABBA. A scoped v1 and B scoped v2; every call builds a fresh scope inside measured call. No observation/result/validation cache and no new initial-context optimization.',
        'timing': 'Samples are prediction caller entry to return including scope construction. The unchanged original initial-context caller is separately reported and inside whole120. Source/input hashes, startup, raw loading, all24 output gzip/hash, lazy/v1 full checks, saved readback, exit pins, and process cleanup share120. Default GC remains; private cycles can be reclaimed after a sample, no per-sample destruction claim.',
        'comparison_order': 'Frozen worker saves each returned output before lazy target read. Additional v1 target comparison occurs after all model calls. Target-read ordering is source evidence, not independently timestamped authority.',
        'failure': 'All24 retained including setup/model/export/audit/timeout errors. No retry, row replacement, budget extension or cherry-picking; summaries require all24 exact.',
        'not_certified': ['native', 'complete_request100ms', 'full32', 'hidden_state_coverage', 'online_protection']}
    write(output/'plan.json', plan)
    write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': ref(output/'plan.json'),
        'sources': len(pins), 'focused_pure_tests': COST_TESTS, 'functional_pure_tests': 36,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--expected-plan', sha(output/'plan.json')]})


# Updated only while this new, unprepared harness is developed. Its pure
# receipt, source archive and preparation bind the final exact count.
COST_TESTS = 32


def pins_now(output, plan):
    require(plan['schema'] == SCHEMA and plan['order'] == list(ORDER)
        and plan['source_proof'] == source_proof(), 'fixed_v1_v2_protocol')
    return frozen.pins_now(output, plan)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare-source', action='store_true'); parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true'); parser.add_argument('--worker', action='store_true')
    parser.add_argument('--expected-plan'); args = parser.parse_args(); output = args.output.resolve()
    frozen.base.no_execution_extensions()
    if args.prepare_source: prepare_source(output); return 0
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(sys.stdin.readline() == args.expected_plan+'\n', 'owned_admission')
        try:
            worker_function()(output, args.expected_plan)
            require(read(output/'report.json')['status'] == 'passed_fixed_six_ABBA24_complete_prediction', 'complete_fixed_denominator')
        except BaseException:
            write(output/'failure.json', {'status': 'unknown_failure', 'error': traceback.format_exc()}); raise
        return 0
    require(args.execute and sha(output/'plan.json') == args.expected_plan, 'explicit_reviewed_execute')
    with (output/'execution_claim').open('x'): pass
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', args.expected_plan]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        process = frozen.bounded_windows_job.run(command, timeout=frozen.base.remaining(time.monotonic()-BOOT),
            stdout=stdout, stderr=stderr, admission=args.expected_plan, cwd=str(ROOT))
    wall = time.monotonic()-BOOT
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and wall <= LIMIT
    write(output/'bounded_execution.json', {'status': 'completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'whole_python_before_receipt_seconds': wall, 'shared_limit_seconds': LIMIT})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


if __name__ == '__main__': raise SystemExit(main())
