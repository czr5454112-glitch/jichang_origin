"""Independent stdlib review of frozen R1 source and saved pure-test evidence.

No model/controller/runtime imports, simulation, training, or native loading.
Only the two isolated stdlib registry/timing modules are executed in pure tests.
"""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[3]
COUNT = 0


def require(value, message):
    global COUNT
    COUNT += 1
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def funcs(source):
    return {node.name: node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def shape(node):
    return ast.dump(node, include_attributes=False)


def pure_module(path, name):
    tree = ast.parse(Path(path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(all(alias.name in {'time', 'math'} for alias in node.names), 'stdlib module import')
        if isinstance(node, ast.ImportFrom):
            require(node.level == 0 and node.module in {'__future__', 'dataclasses'}, 'stdlib from import')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    freeze_path = BASE / 'async_audit_tool_001/R1_implementation_freeze_001.json'
    frozen = read(freeze_path)
    for item in list(frozen['source_bindings'].values()) + [frozen['design'], frozen['parity'], frozen['tests']['junit']] + frozen['tests']['sources']:
        require(ref(item['path']) == item, 'frozen reference bytes')
    parity = read(frozen['parity']['path'])
    require(sha(BASE / 'async_audit_tool_001/check_R1_parity.py') == parity['script_sha256'], 'parity producer bytes')
    for name, expected in parity['closed_raw_sha256'].items():
        require(sha(BASE / name / 'raw.json.gz') == expected, 'saved raw bytes')
    require(len(parity['evidence']) == 27
            and sum(row['status'] == 'conditional_current_seed' for row in parity['evidence']) == 19
            and sum(row['status'] == 'unknown' for row in parity['evidence']) == 8, 'saved parity denominator')
    require(all(row['all_candidate_results_exact_equal'] and row['zero_tolerance_guard_exact_equal']
                for row in parity['evidence']), 'saved parity complete flags')
    junit = ET.parse(frozen['tests']['junit']['path']).getroot()
    suites = list(junit.iter('testsuite'))
    require(sum(int(s.attrib['tests']) for s in suites) == 92
            and all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped')), '92 saved tests actually passed')
    old_dir = BASE / 'A_eval_negative_rule_001'
    old_plan = read(old_dir / 'plan.json')
    old_sources = {}
    for name, expected in frozen['source_sha256_before'].items():
        source = next(p for p in old_plan['source_sha256'] if Path(p).name == name)
        archive = old_dir / old_plan['source_archive'][source]
        require(sha(archive) == expected == old_plan['source_sha256'][source], 'historical comparison source')
        old_sources[name] = archive
    old_domain = funcs(old_sources['foundation_repeated_domain.py'].read_text())
    new_domain = funcs(Path(frozen['source_bindings']['foundation_repeated_domain.py']['path']).read_text())
    unchanged = []
    for name, function in old_domain.items():
        if name == 'identify':
            continue
        require(shape(function) == shape(new_domain[name]), 'domain function unchanged: ' + name)
        unchanged.append(name)
    def send(source):
        tree = ast.parse(Path(source).read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Transport')
        return copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'send'))
    old_send = send(old_sources['research_synthetic_reuse_chain.py'])
    new_send = send(frozen['source_bindings']['research_synthetic_reuse_chain.py']['path'])
    new_send.body = [node for node in new_send.body if not
        (isinstance(node, ast.Assign) and all(isinstance(target, ast.Name) and target.id.startswith('timing_') for target in node.targets))
        and not (isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'timing_enabled')]
    require(shape(old_send) == shape(new_send), 'exact original send body order after audit-only statements removed')
    registry = pure_module(frozen['source_bindings']['foundation_repeated_registry.py']['path'], 'r1_review_registry')
    declared = {'case': [1, 2]}; jobs = {'job': {'arrival': 1., 'protected': True}}
    compiled = registry.compile_registry(physical_canonical='p', registry_declaration=declared,
        contract_fields=('arrival', 'protected'), case_names=('one',), build_jobs=lambda _: jobs, clock=lambda: 5)
    signature = registry.immutable(declared)
    jobs['job']['arrival'] = 9.; declared['case'].append(3)
    actual = {'job': {'arrival': 1., 'protected': True}}
    require(compiled.identify('p', actual, declaration=signature, contract_fields=('arrival', 'protected')) == 'one', 'owns immutable static values')
    for physical, population, declaration, fields in [
        ('wrong', actual, signature, ('arrival', 'protected')),
        ('p', {}, signature, ('arrival', 'protected')),
        ('p', {**actual, 'extra': actual['job']}, signature, ('arrival', 'protected')),
        ('p', {'job': {'arrival': 2., 'protected': True}}, signature, ('arrival', 'protected')),
        ('p', actual, registry.immutable(declared), ('arrival', 'protected')),
        ('p', actual, signature, ('protected', 'arrival'))]:
        error = False
        try: compiled.identify(physical, population, declaration=declaration, contract_fields=fields)
        except ValueError: error = True
        require(error, 'static mutation refused')
    timing = pure_module(frozen['source_bindings']['foundation_repeated_timing.py']['path'], 'r1_review_timing')
    clock = [0]; recorder = timing.Recorder(clock=lambda: clock[0])
    row = recorder.request_start(owner='B', phase='cycle_route', root_id='r', target_job='j', generation=1, traversal_id=1, sim_at=1.)
    recorder.bind(row, 'collection'); clock[0] = 10_000_000; recorder.mark(row, 'ready_entry')
    recorder.submit(request_id='route', kind='route', owner='B', retry=False, started_ns=12_000_000, ended_ns=13_000_000, sim_at=1.04, status='pending')
    clock[0] = 15_000_000; recorder.request_end(row, status='protected_current', sim_at=1.04, command_id='route')
    recorder.ack_read(request_id='route', owner='B', sequence=1, status='updated', delivered_sim_s=1.05, started_ns=19_000_000, ended_ns=20_000_000)
    measured = recorder.audit()['requests'][0]
    require(measured['logical_wait_to_ready_wall_ms'] == 10. and measured['open_to_controller_done_wall_ms'] == 15.
            and measured['actual_native_submit_wall_ms'] == 1. and measured['open_to_native_submit_return_wall_ms'] == 13., 'separate wall interval arithmetic')
    require(measured['submit_to_ack_read_envelopes'][0]['submit_return_to_read_end_wall_ms'] == 7., 'ACK envelope arithmetic')
    partial_source = (ROOT / 'scripts/experiments/g31_ics_circulation/research_live_obligation_native_domain.py').read_text()
    capture = funcs(partial_source)['capture_partial']
    campaign = funcs(Path(frozen['source_bindings']['foundation_repeated_campaign.py']['path']).read_text())['worker']
    require('path_timing' not in ast.get_source_segment(partial_source, capture)
            and 'path_timing' not in ast.unparse(campaign), 'confirmed missing persistent failure timings in freeze001')
    training = ROOT / 'scripts/experiments/g31_ics_circulation/foundation_multistep_learning.py'
    gate = ast.unparse(funcs(training.read_text())['training_gate'])
    require("sha(domain.__file__) == contract['decision_contract_sha256']" in gate
            and 'current_projection_contract_changed' in gate, 'training rejects source drift before episode loading')
    native_path = Path(frozen['source_bindings']['foundation_repeated_native.py']['path'])
    report = {'schema': 'g31.foundation.R1_independent_review.v1', 'status': 'source_semantics_pass_with_timing_scope_limitations',
        'auditor': ref(__file__), 'freeze': ref(freeze_path), 'source_bindings': frozen['source_bindings'], 'checks': COUNT,
        'historical_source_plan': ref(old_dir / 'plan.json'), 'unchanged_domain_functions_except_identify': unchanged,
        'transport_original_send_ast_preserved': True, 'static_only_cache': True, 'dynamic_guard_or_TTL_cached': False,
        'saved_parity_evidence': {'report': frozen['parity'], 'raw_files_hash_verified': len(parity['closed_raw_sha256']),
            'distinct_evidence': 27, 'supported': 19, 'unknown': 8, 'independently_reran_prediction_engine': False},
        'saved_tests_verified': {'junit': frozen['tests']['junit'], 'passed': 92},
        'independent_pure_checks': ['static ownership and six mutation negatives', 'logical wait/native submit/ACK envelope arithmetic'],
        'findings': [
            {'id': 'R1-T1', 'severity': 'measurement_scope', 'file': str(native_path), 'line': 759,
             'finding': 'Initial client activation roots and final_outbox_collection/refresh bypass OwnerPolicy.activate timing; a first ACK read there has no recorded read envelope.',
             'impact': 'All owner activations and all ACK reads are broader than the measured continuation-policy scope; not a guard semantics defect.'},
            {'id': 'R1-T2', 'severity': 'measurement_denominator', 'file': frozen['source_bindings']['foundation_repeated_campaign.py']['path'], 'line': 263,
             'finding': 'Exception partial capture does not serialize client.path_timing.audit; successful run_branch return is the only path_timing output.',
             'impact': 'Exception runs must be kept as timing-censored failures; pure Recorder tests do not establish persistent failure timing coverage.'}],
        'finite_calibration_semantic_blocker_found': False, 'native_executed_by_audit': False, 'training_or_selection_executed': False,
        'full_request_100ms_certified': False, 'all_failure_timings_persisted': False,
        'physical_effect_exact_wall_time_measured': False,
        'followup_boundary': 'Do not mutate freeze001; a repair needs its own new freeze before a separately registered run.'}
    with (HERE / 'report.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({'status': report['status'], 'checks': COUNT, 'report_sha256': sha(HERE / 'report.json')}))


if __name__ == '__main__':
    main()
