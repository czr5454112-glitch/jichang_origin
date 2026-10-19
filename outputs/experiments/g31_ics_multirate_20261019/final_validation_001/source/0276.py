"""Fixed pure ABBA against RequestContext; every batch includes its baseline.

Preparation performs no projection. Execution is a separate, source-pinned
120-second owned job. No native session, saved outcome as policy input, GC
manipulation, discarded warmup or 100-ms certification is provided.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import pickle
import statistics
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import public_preference_protection_request_context as candidate
from . import public_preference_request_context as reference

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
INPUT = OUT / 'preference_static_context_pair_001/worker/supplied_inputs.json'
INPUT_SHA = '0066994f93a7a25a8aa0a005020bb262909d5c4c5aacbfea5e14bbb2b262b0cb'
CASES = tuple(f'block{b}_load{r}' for b in range(2) for r in range(3))
SCHEMA = 'g31.protection_request_context.abba.v1'
PARTIAL = 'conditional_protection_rejected_prefix'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def write(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def inventory():
    paths = {Path(__file__).resolve(), ROOT/'tests/test_g31_circulation_measure_protection_request_context.py',
        ROOT/'tests/test_g31_circulation_preference_protection_request_context.py'}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT): paths.add(path)
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def check_plan(plan):
    if (plan.get('schema') != SCHEMA or plan.get('native_calls') != 0
            or plan.get('hard_timeout_seconds') != 120. or plan.get('candidate_domain') != 32
            or plan.get('batch_count') != 24 or plan.get('full_baseline_per_batch') != 1
            or plan.get('input', {}).get('sha256') != INPUT_SHA
            or [row.get('case') for row in plan.get('cases', [])] != list(CASES)):
        raise ValueError('changed_plan_scope')
    for row in plan['cases']:
        if row.get('order') != ['A', 'B', 'B', 'A'] or row.get('input') != row['case']+'.input.json':
            raise ValueError('changed_case_or_order')
    if not plan.get('source_sha256') or any(Path(name).is_absolute() or '..' in Path(name).parts for name in plan['source_sha256']):
        raise ValueError('invalid_source_domain')


def check_pure_gate(pure, sources):
    report=json.loads((pure/'worker/report.json').read_bytes())
    pure_plan=json.loads((pure/'worker/plan.json').read_bytes())
    tests=ET.parse(pure/'worker/tests.xml').getroot().findall('.//testcase')
    if (report.get('status')!='passed_pure_cut_guard_tests' or report.get('pytest_exit_code')!=0
            or report.get('source_changed')!=[] or report.get('input_changed')!=[] or len(tests)<53
            or any(child.tag in ('failure','error','skipped') for test in tests for child in test)):
        raise ValueError('pure_gate_not_passed')
    for name,digest in sources.items():
        if pure_plan['source_sha256'].get(name)!=digest or sha(pure/'worker/source'/name)!=digest:
            raise ValueError('pure_gate_source_does_not_match')


def prepare(output, pure):
    output.mkdir(parents=True, exist_ok=False)
    if sha(INPUT) != INPUT_SHA: raise ValueError('changed_saved_public_inputs')
    rows = json.loads(INPUT.read_bytes()); selected = [row for row in rows if row['owner'] == 'A']
    if [row['case'] for row in selected] != list(CASES): raise ValueError('changed_six_cases')
    report_path = pure/'worker/report.json'
    before = inventory()
    check_pure_gate(pure,before)
    for name in before:
        target = output/'source'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT/name).read_bytes())
    cases = []
    for row in selected:
        name = row['case']+'.input.json'; write(output/name, row['bundle'])
        cases.append({'case': row['case'], 'input': name, 'input_sha256': sha(output/name), 'order': ['A','B','B','A']})
    plan = {'schema': SCHEMA, 'source_sha256': before, 'cases': cases,
        'input': {'path': str(INPUT), 'sha256': INPUT_SHA},
        'pure_gate': {str(p): sha(p) for p in (report_path, pure/'worker/tests.xml', pure/'worker/plan.json', pure/'receipt.json', pure/'external_wall.json')},
        'hard_timeout_seconds': 120., 'native_calls': 0, 'candidate_domain': 32, 'batch_count': 24, 'full_baseline_per_batch': 1,
        'A': 'Existing RequestContext; complete default baseline plus all32 candidate predictions.',
        'B': 'ProtectionRequestContext; same complete default baseline; all32 candidate queries, each full or strict completed-prefix rejection with unknown suffix.',
        'batch_scope': 'Wall and process CPU from before context construction to after actions, full baseline, all32 queries, certificate/full result construction and JSON encoding. All input validation, source checks, AST compilation, copies/fingerprint and potential construction remain charged. A baseline is copied once on both arms. No cost division or subtraction.',
        'whole_job_scope': 'Parent/import/setup, source/input reads, 24 complete batches, raw encoding files, ledger, independent paired checks, hash verification and reporting retained in owned-job/parent wall. External PowerShell launch-to-exit also records interpreter startup/final output.',
        'denominators': {'supplied_contexts': 6, 'distinct_candidates': 192, 'measured_queries': 768, 'separately_charged_full_baselines': 24},
        'failure': 'Any omitted/incomplete batch, unknown, incorrect strict witness, output/order/type difference, source drift, exception or timeout remains failed/unknown. Speed regressions are retained. No selective window or discarded warmup.',
        'fairness': 'Same six saved actual A public inputs, ABBA within every case, 32 fixed candidates. Existing pure tests separately bind all four search methods to the same selected full result/query order. No method uses saved native outcomes.',
        'limits': 'Retrospective pure initial-model supplied-input comparison only, not held-out validation, native protection, online availability, complete business-request timing or hard real-time.'}
    check_plan(plan); write(output/'preregistered_protocol.json', plan)
    write(output/'prepare_receipt.json', {'status': 'prepared_no_execution', 'plan_sha256': sha(output/'preregistered_protocol.json'),
        'source_count': len(before), 'projection_calls': 0, 'native_calls': 0})


def verify_pins(output, plan):
    check_plan(plan)
    if inventory() != plan['source_sha256']: raise ValueError('loaded_source_closure_changed')
    for name, digest in plan['source_sha256'].items():
        if sha(ROOT/name) != digest or sha(output/'source'/name) != digest: raise ValueError('source_or_archive_changed')
    if sha(plan['input']['path']) != INPUT_SHA: raise ValueError('input_changed')
    selected = [row for row in json.loads(Path(plan['input']['path']).read_bytes()) if row['owner']=='A']
    if [row['case'] for row in selected] != list(CASES): raise ValueError('case_source_changed')
    for row, source in zip(plan['cases'], selected, strict=True):
        path = output/row['input']
        if sha(path) != row['input_sha256'] or encoded(json.loads(path.read_bytes())) != encoded(source['bundle']):
            raise ValueError('not_exact_supplied_input')
    for path, digest in plan['pure_gate'].items():
        if sha(path) != digest: raise ValueError('pure_gate_changed')


def batch(bundle, arm):
    if arm not in ('A', 'B'): raise ValueError('unknown_arm')
    if arm == 'A':
        context = reference.RequestContext(bundle); actions = context.actions()
        baseline = copy.deepcopy(context.predict(actions[0] if actions else {}))
    else:
        context = candidate.ProtectionRequestContext(bundle); actions = context.actions(); baseline = context.baseline()
    if len(actions) != 32: raise ValueError('incomplete_action_domain')
    predictions = [context.predict(action) for action in actions]
    # Encoding is deliberately inside the measured batch, for both arms.
    return encoded({'baseline': baseline, 'actions': actions, 'predictions': predictions})


def _finite(value): return type(value) in (int, float) and math.isfinite(value) and value >= 0


def check_outputs(full, actual, fingerprint):
    if (set(full) != {'baseline','actions','predictions'} or set(actual) != set(full)
            or encoded(full['baseline']) != encoded(actual['baseline']) or encoded(full['actions']) != encoded(actual['actions'])
            or len(full['actions']) != 32 or len(full['predictions']) != 32 or len(actual['predictions']) != 32):
        raise ValueError('batch_domain_baseline_or_action_mismatch')
    baseline = candidate.proof._reference_times(full['baseline']); counts = {'full_exact': 0, 'strict_prefix_rejections': 0, 'unknown': 0}
    for source, result in zip(full['predictions'], actual['predictions'], strict=True):
        if result.get('status') != PARTIAL:
            if encoded(source) != encoded(result): raise ValueError('full_prediction_not_exact')
            counts['full_exact'] += 1; counts['unknown'] += source.get('status') != 'conditional_prediction'
            continue
        if baseline is None or source.get('status') != 'conditional_prediction': raise ValueError('cannot_validate_partial_against_unknown')
        witness = result.get('witness', {}); job = witness.get('job'); prefix = witness.get('completed_prefix')
        if (set(result) != {'status','completion','completion_sum','witness','supplied_snapshot_sha256','baseline_action','baseline_completion',
                'full_candidate_prediction','suffix_status','native_protection_certified','native_execution_certified','online_information_delivered','complete_100ms_certified'}
                or result['completion'] != {} or result['completion_sum'] is not None or result['full_candidate_prediction'] is not False
                or result['suffix_status'] != 'unknown_unexecuted' or any(result[k] is not False for k in ('native_protection_certified','native_execution_certified','online_information_delivered','complete_100ms_certified'))
                or encoded(result['baseline_action']) != encoded(full['actions'][0]) or encoded(result['baseline_completion']) != encoded(baseline)
                or result['supplied_snapshot_sha256'] != fingerprint
                or set(witness) != {'job','candidate_completed_at','baseline_completed_at','cut_at','completed_prefix','comparison','observed_point'}
                or job not in baseline or type(prefix) is not dict or job not in prefix
                or witness.get('comparison') != 'strict >; no tolerance'
                or witness.get('observed_point') != 'original unload assignment before its post-unload notification'
                or not _finite(witness.get('cut_at')) or not _finite(witness.get('candidate_completed_at'))
                or not _finite(witness.get('baseline_completed_at')) or witness.get('candidate_completed_at') != witness['cut_at']
                or witness.get('baseline_completed_at') != baseline[job]
                or source['completion'][job] != witness['candidate_completed_at'] or not source['completion'][job] > baseline[job]
                or any(k not in baseline or not _finite(v) or source['completion'][k] != v or v > witness['cut_at'] for k,v in prefix.items())):
            raise ValueError('invalid_partial_rejection_witness')
        counts['strict_prefix_rejections'] += 1
    return counts


def worker(output, expected_sha):
    started = time.perf_counter(); plan_path = output/'preregistered_protocol.json'
    if sha(plan_path) != expected_sha: raise ValueError('wrong_plan')
    plan = json.loads(plan_path.read_bytes()); verify_pins(output, plan)
    ledger = [{'case': case['case'], 'sample': n, 'arm': arm, 'status': 'unknown_unexecuted'} for case in plan['cases'] for n, arm in enumerate(case['order'])]
    write(output/'ledger.json', ledger); comparisons = []
    for case_index, case in enumerate(plan['cases']):
        bundle = json.loads((output/case['input']).read_bytes()); full = None
        fingerprint=hashlib.sha256(pickle.dumps(bundle,protocol=5)).hexdigest()
        for n, arm in enumerate(case['order']):
            row = ledger[case_index*4+n]; row['status']='unknown_in_progress'; write(output/'ledger.json', ledger)
            wall = time.perf_counter_ns(); cpu = time.process_time_ns()
            try: value = batch(bundle, arm)
            except BaseException:
                row.update(status='unknown_batch_error', wall_ns=time.perf_counter_ns()-wall, cpu_ns=time.process_time_ns()-cpu)
                write(output/'ledger.json',ledger); raise
            row.update(wall_ns=time.perf_counter_ns()-wall, cpu_ns=time.process_time_ns()-cpu)
            payload = json.loads(value); path = output/f"{case['case']}.{n}.{arm}.json.gz"
            path.write_bytes(gzip.compress(value.encode('utf8'),mtime=0)); row.update(raw=path.name,raw_sha256=sha(path))
            if full is None: full=payload
            checks=check_outputs(full,payload,fingerprint)
            if arm=='A' and encoded(full)!=encoded(payload): raise ValueError('reference_repeat_changed')
            row.update(status='completed',checks=checks);write(output/'ledger.json',ledger)
        comparisons.append({'case':case['case'], 'median_A_ns':statistics.median(r['wall_ns'] for r in ledger[case_index*4:case_index*4+4] if r['arm']=='A'),
            'median_B_ns':statistics.median(r['wall_ns'] for r in ledger[case_index*4:case_index*4+4] if r['arm']=='B')})
    verify_pins(output,plan)
    if sha(plan_path)!=expected_sha or len(ledger)!=24 or any(r['status']!='completed' for r in ledger): raise ValueError('incomplete_or_changed_campaign')
    write(output/'receipt.json',{'schema':SCHEMA,'status':'completed_pure_ABBA_with_validated_partial_suffixes','plan_sha256':expected_sha,
        'source_changed':[],'input_changed':[],'native_calls':0,'timing_samples':ledger,'case_pairs':comparisons,
        'median_A_ns':statistics.median(r['wall_ns'] for r in ledger if r['arm']=='A'),
        'median_B_ns':statistics.median(r['wall_ns'] for r in ledger if r['arm']=='B'),
        'worker_wall_seconds':time.perf_counter()-started,'candidate_queries':768,'full_baselines':24,
        'worker_wall_scope':'Entry through first receipt; subsequent complete saved-output readback remains in the owned-process and external wall.',
        'unknown_suffixes_retained':True,'complete_100ms_certified':False,'native_protection_certified':False})
    verify_saved(output,require_process=False)


def verify_saved(output, *, require_process=True):
    plan_path=output/'preregistered_protocol.json';plan=json.loads(plan_path.read_bytes());verify_pins(output,plan)
    receipt=json.loads((output/'receipt.json').read_bytes());ledger=json.loads((output/'ledger.json').read_bytes())
    if (receipt.get('status')!='completed_pure_ABBA_with_validated_partial_suffixes'
            or receipt.get('plan_sha256')!=sha(plan_path) or receipt.get('source_changed')!=[] or receipt.get('input_changed')!=[]
            or receipt.get('native_calls')!=0 or receipt.get('complete_100ms_certified') is not False
            or receipt.get('candidate_queries')!=768 or receipt.get('full_baselines')!=24
            or len(ledger)!=24 or encoded(receipt.get('timing_samples'))!=encoded(ledger)):
        raise ValueError('incomplete_saved_receipt')
    comparisons=[]
    for index,case in enumerate(plan['cases']):
        bundle=json.loads((output/case['input']).read_bytes());fingerprint=hashlib.sha256(pickle.dumps(bundle,protocol=5)).hexdigest();full=None
        rows=ledger[index*4:index*4+4]
        for n,(row,arm) in enumerate(zip(rows,case['order'],strict=True)):
            name=f"{case['case']}.{n}.{arm}.json.gz"
            if (row.get('case')!=case['case'] or row.get('sample')!=n or row.get('arm')!=arm or row.get('status')!='completed'
                    or row.get('raw')!=name or sha(output/name)!=row.get('raw_sha256')
                    or type(row.get('wall_ns')) is not int or row['wall_ns']<=0 or type(row.get('cpu_ns')) is not int or row['cpu_ns']<0):
                raise ValueError('saved_batch_identity_or_clock')
            value=json.loads(gzip.decompress((output/name).read_bytes()))
            if full is None:full=value
            if check_outputs(full,value,fingerprint)!=row.get('checks') or (arm=='A' and encoded(value)!=encoded(full)):
                raise ValueError('saved_output_mismatch')
        comparisons.append({'case':case['case'],'median_A_ns':statistics.median(r['wall_ns'] for r in rows if r['arm']=='A'),
            'median_B_ns':statistics.median(r['wall_ns'] for r in rows if r['arm']=='B')})
    if (encoded(comparisons)!=encoded(receipt.get('case_pairs'))
            or any(receipt.get('median_'+arm+'_ns')!=statistics.median(r['wall_ns'] for r in ledger if r['arm']==arm) for arm in ('A','B'))
            or not _finite(receipt.get('worker_wall_seconds')) or receipt['worker_wall_seconds']*1e9<sum(r['wall_ns'] for r in ledger)):
        raise ValueError('saved_cost_or_summary')
    if require_process:
        process=json.loads((output/'external_process.json').read_bytes())
        if (process.get('status')!='worker_exited_zero' or process.get('plan_sha256')!=sha(plan_path)
                or process.get('process',{}).get('status')!='exited' or process['process'].get('exitcode')!=0):
            raise ValueError('missing_successful_owned_process')
    return {'status':'saved_24_batches_rechecked','plan_sha256':sha(plan_path),'native_calls':0,'complete_100ms_certified':False}


def launch(output, expected_sha):
    with (output/'execution_claim.json').open('x',encoding='utf8') as handle: json.dump({'plan_sha256':expected_sha},handle)
    if any((output/name).exists() for name in ('ledger.json','receipt.json','failure.json','external_process.json','stdout.log','stderr.log')):
        raise ValueError('refuse_existing_execution')
    if sha(output/'preregistered_protocol.json')!=expected_sha: raise ValueError('wrong_plan')
    plan=json.loads((output/'preregistered_protocol.json').read_bytes());verify_pins(output,plan)
    admission=str(uuid.uuid4()); command=[sys.executable,'-m',__package__+'.measure_preference_protection_request_context','--worker','--output',str(output),'--plan-sha256',expected_sha,'--admission',admission]
    receipt={'status':'unknown_before_dispatch','command':command,'plan_sha256':expected_sha,'native_calls':0}
    try:
        remaining=120.-(time.perf_counter()-BOOT)
        if remaining<=0: raise TimeoutError('parent_setup_exhausted_budget')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=admission,cwd=ROOT)
        receipt.update(process=process,status='worker_exited_zero' if process['status']=='exited' and process['exitcode']==0 else 'failed_or_unknown')
    except BaseException as error:receipt.update(status='unknown_launcher_error',error=repr(error))
    finally:
        receipt.update(parent_post_interpreter_wall_seconds=time.perf_counter()-BOOT,
            evidence_sha256={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts},
            outer_wall_scope='External launch-to-exit Stopwatch additionally retains Python startup and final export; no subtraction or per-request averaging.')
        write(output/'external_process.json',receipt)
    return 0 if receipt['status']=='worker_exited_zero' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--pure',type=Path);p.add_argument('--plan-sha256');p.add_argument('--admission')
    modes=p.add_mutually_exclusive_group(required=True);modes.add_argument('--prepare',action='store_true');modes.add_argument('--launch',action='store_true');modes.add_argument('--worker',action='store_true');modes.add_argument('--verify-saved',action='store_true')
    a=p.parse_args();a.output=a.output.resolve()
    if a.prepare:prepare(a.output,a.pure.resolve());return 0
    if a.verify_saved:print(encoded(verify_saved(a.output)));return 0
    if a.launch:return launch(a.output,a.plan_sha256)
    if not a.admission or sys.stdin.readline().strip()!=a.admission:raise ValueError('missing_job_admission')
    try:worker(a.output,a.plan_sha256)
    except BaseException as error:
        write(a.output/'failure.json',{'status':'failed_or_unknown','error':repr(error),'traceback':traceback.format_exc(),'native_calls':0});raise
    return 0
if __name__=='__main__':raise SystemExit(main())
