"""Bounded pure static-code context tests and complete32 paired measurements."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from scripts.experiments.g31_ics_circulation import public_preference_static_context as candidate
from scripts.experiments.g31_ics_circulation import preference_wall_budget as budget

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
SUPPLIED = OUT / 'preference_request_context_pair_001/worker/supplied_inputs.json'
PRIOR_PLAN = OUT / 'preference_request_context_pair_001/worker/plan.json'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
def write(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def sources():
    paths = {Path(__file__).resolve(), ROOT / 'launch_preference_static_context.py'}
    paths.update(candidate.implementation_sources())
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and str(path).lower().startswith(str(ROOT).lower()) and Path(path).suffix == '.py' and Path(path).resolve().is_relative_to(ROOT):
            paths.add(Path(path).resolve())
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def batch(bundle, implementation=None):
    context = candidate.base.RequestContext(bundle) if implementation is None else implementation.context(bundle)
    return [context.predict(action) for action in context.actions()]


def measured(function):
    start, cpu = time.perf_counter_ns(), time.process_time_ns()
    result = function()
    return result, {'wall_ns': time.perf_counter_ns()-start, 'cpu_ns': time.process_time_ns()-cpu}


def profile(output):
    started = time.perf_counter()
    prior = json.loads(PRIOR_PLAN.read_bytes())
    if sha(SUPPLIED) != prior['inputs_sha256']:
        raise ValueError('static_measurement:changed_supplied_input')
    inputs = json.loads(SUPPLIED.read_bytes())
    if len(inputs) != 12 or len({row['case'] for row in inputs}) != 6 or any(
            {row['owner'] for row in inputs if row['case'] == case} != {'A', 'B'} for case in {row['case'] for row in inputs}):
        raise ValueError('static_measurement:input_domain')
    pins = sources()
    for relative, digest in pins.items():
        target = output / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT / relative).read_bytes())
        if sha(target) != digest: raise ValueError('static_measurement:archive_changed')
    write(output / 'supplied_inputs.json', inputs)
    plan = {'schema': 'g31.static_preference_context.pure_pair.v1', 'source_sha256': pins,
        'input_evidence_sha256': {str(SUPPLIED): sha(SUPPLIED), str(PRIOR_PLAN): sha(PRIOR_PLAN)},
        'input_sha256': sha(output / 'supplied_inputs.json'), 'cases': 6, 'owners': ['A', 'B'],
        'actions': 32, 'paired_orders': [['reference_context', 'static_warm'], ['static_warm', 'reference_context']],
        'cold_scope': 'One explicit code-only factory build measured separately; all12 additionally measured with a fresh factory inside each whole32 batch.',
        'warm_scope': 'Initialized code-only factory. Per-request complete source reads/live identity, dynamic validation, isolated data/score potential, every candidate and method result are timed.',
        'budget_probe': 'Six ownerA supplied contexts, common100ms total/20ms finalization reserve/max32. Keep first conditional projection only; NOT a comparison of four scheduling methods. Final callback explicitly lacks native revalidation.',
        'measurement_exclusions': 'Equality comparison/output encoding outside each batch; complete worker/launch wall retains them. Budget probe separately includes response codec.',
        'native_executions': 0, 'outcomes_used_as_policy_input': False, 'complete_100ms_certified': False}
    write(output / 'plan.json', plan)
    implementation, factory = measured(candidate.StaticImplementation)
    print(json.dumps({'stage': 'factory_built', 'timing': factory}), flush=True)
    rows, cold_rows, probes = [], [], []
    for order in plan['paired_orders']:
        for item in inputs:
            values, timings = {}, {}
            for name in order:
                values[name], timings[name] = measured(lambda name=name: batch(item['bundle'],
                    None if name == 'reference_context' else implementation))
            if encode(values['reference_context']) != encode(values['static_warm']):
                raise ValueError('static_measurement:complete_ordered_output_difference')
            if len(values['reference_context']) != 32 or any(row['status'] != 'conditional_prediction' for row in values['reference_context']):
                raise ValueError('static_measurement:missing_prediction')
            rows.append({'case': item['case'], 'owner': item['owner'], 'order': order, 'timings': timings,
                'complete_output_sha256': hashlib.sha256(encode(values['reference_context'])).hexdigest()})
            write(output / 'partial.json', {'status': 'unknown_in_progress', 'paired_rows': rows,
                'cold_full32_rows': cold_rows, 'factory_cold_build': factory})
            print(json.dumps({'stage': 'paired_row', 'completed': len(rows), 'timings': timings}), flush=True)
    for item in inputs:
        value, timing = measured(lambda: batch(item['bundle'], candidate.StaticImplementation()))
        reference = batch(item['bundle'])
        if encode(value) != encode(reference): raise ValueError('static_measurement:cold_difference')
        cold_rows.append({'case': item['case'], 'owner': item['owner'], **timing,
            'complete_output_sha256': hashlib.sha256(encode(value)).hexdigest()})
        write(output / 'partial.json', {'status': 'unknown_in_progress', 'paired_rows': rows,
            'cold_full32_rows': cold_rows, 'factory_cold_build': factory})
        print(json.dumps({'stage': 'cold_row', 'completed': len(cold_rows), 'timing': timing}), flush=True)
        if item['owner'] == 'A':
            result, outer = measured(lambda: budget.run(item['bundle'], budget_ns=100_000_000,
                reserve_ns=20_000_000, maximum_candidates=32, implementation=implementation,
                select=lambda rows, previous: next((i for i, row in enumerate(rows) if row['status'] == 'evaluated'
                    and row['prediction']['status'] == 'conditional_prediction'), None),
                finalize=lambda snapshot, proposal, deadline: {'status': 'unknown_no_native_final_revalidation'}))
            response = json.loads(result.pop('response_bytes'))
            probes.append({'case': item['case'], 'envelope': result, 'outer_function': outer, 'response': response})
    implementation.verify_implementation()
    if sources() != pins or any(sha(path) != digest for path, digest in plan['input_evidence_sha256'].items()):
        raise ValueError('static_measurement:source_or_input_changed')
    report = {'status': 'passed_exact_pure_static_context_pair', 'factory_cold_build': factory,
        'paired_rows': rows, 'cold_full32_rows': cold_rows, 'budget_probes': probes,
        'source_changed': [], 'whole_worker_body_seconds': time.perf_counter()-started,
        'native_executions': 0, 'complete_100ms_certified': False}
    write(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'paired_rows': len(rows), 'cold_rows': len(cold_rows),
                      'wall_seconds': report['whole_worker_body_seconds']}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('tests', 'profile'), required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    if sys.stdin.readline().rstrip('\n') != args.admission: raise ValueError('static_measurement:missing_job_admission')
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        if args.mode == 'tests':
            import pytest
            pins = sources()
            test_path = ROOT / 'tests/test_g31_circulation_preference_static_context.py'
            pins[str(test_path.relative_to(ROOT))] = sha(test_path)
            for relative, digest in pins.items():
                target = args.output / 'source' / relative
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT / relative).read_bytes())
                if sha(target) != digest: raise ValueError('static_tests:archive_changed')
            write(args.output / 'plan.json', {'status': 'tests_source_frozen_before_pytest', 'source_sha256': pins,
                'native_executions': 0, 'bounded_parent_seconds': 120})
            code = pytest.main(['-q', 'tests/test_g31_circulation_preference_static_context.py',
                '--basetemp', str(args.output / 'tmp'), '--junitxml', str(args.output / 'tests.xml')])
            changed = [relative for relative, digest in pins.items() if sha(ROOT / relative) != digest]
            write(args.output / 'source_after.json', {'source_changed': changed})
            if changed: raise ValueError('static_tests:source_changed')
            raise SystemExit(code)
        profile(args.output)
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code == 0: raise
        write(args.output / 'failure.json', {'status': 'failed_or_unknown', 'error': repr(error), 'native_executions': 0})
        raise


if __name__ == '__main__': main()
