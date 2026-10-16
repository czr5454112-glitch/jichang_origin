"""Bounded pure test/measurement worker; consumes supplied bundles only."""
from __future__ import annotations
import argparse
import cProfile
import gzip
import hashlib
import io
import json
from pathlib import Path
import pstats
import sys
import time

from scripts.experiments.g31_ics_circulation import public_preference_request_context as candidate

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
def write(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def source_pins():
    paths = {Path(__file__).resolve(), ROOT/'launch_preference_request_context.py'}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT): paths.add(path)
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def captured_inputs():
    """Fixed vector00, all six existing cases; never reads outcomes into model."""
    path = OUT/'native_preference_matrix_native_001_independent_audit.json'
    audit = json.loads(path.read_bytes())
    if audit['status'] != 'saved192_revalidated_no_new_native' or len(audit['rows']) != 192:
        raise ValueError('input_inventory')
    selected = [(key, row) for key, row in audit['rows'].items() if key.endswith('/vector_00')]
    if len(selected) != 6: raise ValueError('six_input_contexts_required')
    inputs, pins = [], {str(path): sha(path)}
    for key, row in selected:
        raw_path = Path(row['raw_artifact'])
        if sha(raw_path) != row['raw_sha256']: raise ValueError('raw_input_changed')
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        pins[str(raw_path)] = row['raw_sha256']
        for owner in ('A', 'B'):
            information = raw['initial_owners'][owner]['information']
            if information['native_delivery_verified'] is not True: raise ValueError('saved_input_unavailable')
            inputs.append({'case': key.split('/')[0], 'owner': owner, 'bundle': information['bundle']})
    return inputs, pins


def reference_batch(bundle):
    model = candidate.original
    case = model.contract.infer_case(bundle['jobs'])
    windows = model.contract.domain.domain(case)['public_derivation']['supply_windows']
    actions = model.vocabulary.domain(windows)['actions']
    return [model.predict(bundle, action) for action in actions]


def context_batch(bundle):
    context = candidate.RequestContext(bundle)
    return [context.predict(action) for action in context.actions()]


def measured(function, bundle):
    started = time.perf_counter_ns(); cpu = time.process_time_ns()
    value = function(bundle)
    return value, {'wall_ns': time.perf_counter_ns()-started, 'cpu_ns': time.process_time_ns()-cpu}


def profile(output):
    started = time.perf_counter(); inputs, evidence = captured_inputs()
    pins = source_pins()
    for relative in pins:
        target = output/'source'/relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/relative).read_bytes())
    write(output/'supplied_inputs.json', inputs)
    plan = {'schema':'g31.preference_request_context.pure_pair.v1','source_sha256':pins,'input_evidence_sha256':evidence,
        'inputs_sha256':sha(output/'supplied_inputs.json'),'six_cases':6,'owners':['A','B'],'actions_each':32,
        'unprofiled_orders':[['reference','context'],['context','reference']],
        'profiled_passes':'One six-case owner-A pass per implementation; profiled time not speedup evidence.',
        'native_executions':0,'outcomes_used_as_policy_input':False,
        'timed_scope':'Domain construction, context AST/source checks, supplied-data validation, deepcopy, fingerprint, potential and all32 full event projections. Serialization/comparison is separately outside each batch; full worker wall retains it.',
        'complete_100ms_certified':False}
    write(output/'plan.json', plan)
    rows = []
    for order in plan['unprofiled_orders']:
        for item in inputs:
            values, timings = {}, {}
            for name in order:
                values[name], timings[name] = measured(reference_batch if name=='reference' else context_batch, item['bundle'])
            if encode(values['reference']) != encode(values['context']): raise ValueError('complete_ordered_output_difference')
            if len(values['reference']) != 32 or any(r['status']!='conditional_prediction' for r in values['reference']):
                raise ValueError('missing_full_candidate_output')
            rows.append({'case':item['case'],'owner':item['owner'],'order':order,'timing':timings,
                'candidate_count':32,'complete_output_sha256':hashlib.sha256(encode(values['reference'])).hexdigest()})
    for name, function in (('reference',reference_batch),('context',context_batch)):
        profiler=cProfile.Profile(); profiler.enable()
        for item in inputs:
            if item['owner']=='A': function(item['bundle'])
        profiler.disable();profiler.dump_stats(str(output/(name+'.pstats')))
        stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(45)
        (output/(name+'_profile.txt')).write_text(stream.getvalue(),encoding='utf8')
    if source_pins()!=pins or any(sha(path)!=digest for path,digest in evidence.items()): raise ValueError('source_or_input_changed')
    result={'status':'passed_exact_pure_pair','rows':rows,'source_changed':[],
        'full_worker_body_wall_seconds':time.perf_counter()-started,'native_executions':0,
        'scope':'Conditional supplied-input projection only; no native authority, speed or complete-request100ms certificate.'}
    write(output/'report.json', result)
    print(json.dumps({'status':result['status'],'rows':len(rows),'wall_seconds':result['full_worker_body_wall_seconds']}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('tests','profile'),required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--admission',required=True)
    args=parser.parse_args()
    if sys.stdin.readline().rstrip('\n')!=args.admission: raise ValueError('missing_owned_job_admission')
    args.output.mkdir(parents=True,exist_ok=False)
    try:
        if args.mode=='tests':
            import pytest
            raise SystemExit(pytest.main(['-q','tests/test_g31_circulation_preference_request_context.py',
                '--basetemp',str(args.output/'tmp'),'--junitxml',str(args.output/'tests.xml')]))
        profile(args.output)
    except BaseException as error:
        if isinstance(error,SystemExit) and error.code==0: raise
        write(args.output/'failure.json',{'status':'failed_or_unknown','error':repr(error),'native_executions':0})
        raise


if __name__=='__main__':main()
