"""Independent quiet-tail AB/BA; full batch costs, no prefix sharing/native."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import statistics
import sys
import time
import traceback
import uuid
from . import public_preference_quiet_context as quiet
from . import public_preference_request_context as baseline
from . import bounded_windows_job
from .validate_public_native_preference_projection import sha, imported_source_pins

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'g31.public_preference_quiet_pair.v1'


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exact32(expected, actual):
    return (len(expected) == len(actual) == 32
            and all(encoded(a) == encoded(b) for a, b in zip(expected, actual, strict=True)))


def inventory():
    result = imported_source_pins()
    for name in ('public_preference_quiet_context', 'public_native_preference_projection', 'measure_public_preference_quiet'):
        path = ROOT / ('tests/test_g31_circulation_' + name + '.py'); result[str(path)] = sha(path)
    return result


def check_plan(plan, audit):
    cases = sorted({key.split('/')[0] for key in audit['rows']})
    if (plan.get('schema') != SCHEMA or audit.get('status') != 'saved192_revalidated_no_new_native'
            or len(audit['rows']) != 192 or len(cases) != 6
            or plan.get('candidate_denominator') != 192 or plan.get('later_candidate_denominator') != 0
            or plan.get('hard_timeout_seconds') != 120. or plan.get('native_calls') != 0
            or [case['case'] for case in plan['cases']] != cases
            or plan.get('historical_native_status_counts') != dict(Counter(row['status_retained'] for row in audit['rows'].values()))):
        raise ValueError('unsupported_plan_denominator_or_scope')
    for index, case in enumerate(plan['cases']):
        keys = sorted(key for key in audit['rows'] if key.startswith(case['case'] + '/'))
        if (len(keys) != 32 or keys[0] != case['case'] + '/vector_00'
                or case['source_key'] != keys[0] or case['input'] != case['case'] + '.input.json'
                or case['raw_path'] != audit['rows'][keys[0]]['raw_artifact']
                or case['raw_sha256'] != audit['rows'][keys[0]]['raw_sha256']
                or case['order'] != (['A', 'B', 'B', 'A'] if index % 2 == 0 else ['B', 'A', 'A', 'B'])):
            raise ValueError('changed_case_binding_or_ABBA_order')


def prepare(output, audit_path):
    output.mkdir(parents=True, exist_ok=False); (output / 'source').mkdir()
    audit_path = audit_path.resolve(); audit = json.loads(audit_path.read_bytes())
    if audit.get('status') != 'saved192_revalidated_no_new_native' or len(audit['rows']) != 192:
        raise ValueError('unsupported_audit')
    sources = {}
    for index, (path, digest) in enumerate(sorted(inventory().items())):
        target = f'{index:04d}.py'; (output / 'source' / target).write_bytes(Path(path).read_bytes())
        sources[path] = {'sha256': digest, 'archive': target}
    cases = []
    for index, name in enumerate(sorted({key.split('/')[0] for key in audit['rows']})):
        key = name + '/vector_00'; row = audit['rows'][key]; raw_path = Path(row['raw_artifact'])
        if sha(raw_path) != row['raw_sha256']: raise ValueError('changed_source_raw')
        raw = json.loads(gzip.decompress(raw_path.read_bytes())); path = output / (name + '.input.json')
        write(path, raw['initial_owners']['A']['information']['bundle'])
        cases.append({'case': name, 'source_key': key, 'raw_path': str(raw_path), 'raw_sha256': row['raw_sha256'],
            'input': path.name, 'input_sha256': sha(path),
            'order': ['A', 'B', 'B', 'A'] if index % 2 == 0 else ['B', 'A', 'A', 'B']})
    plan = {'schema': SCHEMA, 'sources': sources, 'cases': cases, 'audit': {'path': str(audit_path), 'sha256': sha(audit_path)},
        'candidate_denominator': 192, 'later_candidate_denominator': 0,
        'historical_native_status_counts': dict(Counter(row['status_retained'] for row in audit['rows'].values())),
        'hard_timeout_seconds': 120., 'native_calls': 0,
        'A': 'Unchanged public_preference_request_context.RequestContext',
        'B': 'Independent public_preference_quiet_context.QuietRequestContext',
        'per_batch_charged': 'Context construction, all per-request codegen/source checks/guard validation/input copies/static preparation, action enumeration, all32 full predictions, heap eligibility scans/remaining exact pops and all output construction.',
        'outside_batch_inside_owned_worker': 'All raw/input/archive reads, original32 independent reference predictions percase, canonical full-output comparison and diagnostics export. These remain in wholeworker wall; no complete-business-request timing claim.',
        'corpus': 'Same six vector00 supplied public bundles as prior comparison. Retrospective semantic-debugging/regression comparands, not held-out unseen inputs. Old174assessed/18unknown native rows remain unchanged.',
        'order': 'Each case oneAB andoneBA, oddcases reverse pair order. No discarded warmup.24 full32 batches retained.',
        'scope': 'Only initial32 model requests. No later4 optimization, no prefix-sharing composition, native call, permission change, online authority or100ms certification.',
        'failure': 'All output/count/status mismatches, source drift, timeout and speed regressions are retained. Existing evidence is immutable.'}
    check_plan(plan, audit); write(output / 'preregistered_protocol.json', plan)
    write(output / 'prepare_receipt.json', {'status': 'prepared_no_execution', 'plan_sha256': sha(output / 'preregistered_protocol.json'),
        'source_count': len(sources), 'projection_calls': 0, 'native_calls': 0})


def verify(output, plan):
    if inventory() != {path: row['sha256'] for path, row in plan['sources'].items()}:
        raise ValueError('loaded_source_inventory_drift')
    for path, row in plan['sources'].items():
        if sha(path) != row['sha256'] or sha(output / 'source' / row['archive']) != row['sha256']:
            raise ValueError('source_or_archive_drift')
    if sha(plan['audit']['path']) != plan['audit']['sha256']: raise ValueError('audit_drift')
    check_plan(plan, json.loads(Path(plan['audit']['path']).read_bytes()))
    for case in plan['cases']:
        if sha(output / case['input']) != case['input_sha256'] or sha(case['raw_path']) != case['raw_sha256']:
            raise ValueError('input_or_raw_drift')
        raw = json.loads(gzip.decompress(Path(case['raw_path']).read_bytes()))
        if encoded(json.loads((output / case['input']).read_bytes())) != encoded(raw['initial_owners']['A']['information']['bundle']):
            raise ValueError('input_not_exact_selected_public_bundle')


def worker(output):
    started = time.perf_counter(); plan_path = output / 'preregistered_protocol.json'; plan_sha = sha(plan_path)
    plan = json.loads(plan_path.read_bytes()); verify(output, plan)
    comparisons, ledger, case_stats = [], [], []
    for case in plan['cases']:
        bundle = json.loads((output / case['input']).read_bytes())
        reference_context = baseline.RequestContext(bundle); actions = reference_context.actions()
        if len(actions) != 32: raise ValueError('candidate_domain_changed')
        expected = [baseline.original.predict(bundle, action) for action in actions]
        candidate = quiet.QuietRequestContext(bundle); candidate_actions = candidate.actions()
        if encoded(candidate_actions) != encoded(actions): raise ValueError('candidate_action_domain_changed')
        actual = [candidate.predict(action) for action in candidate_actions]
        if not exact32(expected, actual):
            write(output / (case['case'] + '.mismatch.json'), {'expected': expected, 'actual': actual})
            raise ValueError('conformance_full_output_or_count_mismatch')
        comparisons.append({'case': case['case'], 'candidate_count': 32, 'checks': [encoded(a) == encoded(b) for a, b in zip(expected, actual, strict=True)],
            'reference_status_counts': dict(Counter(row['status'] for row in expected)), 'candidate': candidate.describe()})
        for index, arm in enumerate(case['order']):
            before = time.perf_counter_ns()
            context = baseline.RequestContext(bundle) if arm == 'A' else quiet.QuietRequestContext(bundle)
            values = [context.predict(action) for action in context.actions()]
            elapsed = time.perf_counter_ns() - before
            match = exact32(expected, values)
            ledger.append({'case': case['case'], 'sample': index, 'arm': arm, 'wall_ns': elapsed,
                'candidate_count': len(values), 'all_complete_outputs_exact': match, 'all_preparation_and_output_construction_charged': True})
            write(output / 'timing_ledger.json', ledger)
            if not match:
                write(output / (case['case'] + f'.sample_{index}.mismatch.json'), {'expected': expected, 'actual': values})
                raise ValueError('timed_full_output_or_count_mismatch')
        medians = {arm: statistics.median(row['wall_ns'] for row in ledger if row['case'] == case['case'] and row['arm'] == arm) for arm in ('A', 'B')}
        case_stats.append({'case': case['case'], 'median_A_ns': medians['A'], 'median_B_ns': medians['B'], 'candidate_faster': medians['B'] < medians['A']})
        write(output / 'progress.json', {'status': 'case_complete', 'cases_completed': len(comparisons), 'elapsed_wall_seconds': time.perf_counter() - started, 'native_calls': 0})
    verify(output, plan)
    if sha(plan_path) != plan_sha or len(ledger) != 24 or len(comparisons) != 6 or sum(row['candidate_count'] for row in comparisons) != 192:
        raise ValueError('incomplete_denominator_or_plan_drift')
    write(output / 'receipt.json', {'schema': 'g31.public_preference_quiet_pair.receipt.v1', 'status': 'completed_exact_pure_quiet_pair',
        'plan_sha256': plan_sha, 'source_changed': [], 'native_calls': 0, 'initial_conformance_count': 192,
        'later_conformance_count': 0, 'conformance': comparisons, 'timing_samples': ledger, 'case_pairs': case_stats,
        'median_all_A_ns': statistics.median(row['wall_ns'] for row in ledger if row['arm'] == 'A'),
        'median_all_B_ns': statistics.median(row['wall_ns'] for row in ledger if row['arm'] == 'B'),
        'historical_native_status_counts_retained': plan['historical_native_status_counts'],
        'wall_seconds': time.perf_counter() - started, 'unknown_promoted': False, 'prefix_sharing': False,
        'complete_100ms_certified': False, 'new_native_or_online_claim': False,
        'limits': 'Small initial-only pure model-batch ABBA under concurrent host load, all per-request preparation charged. No later-stage speed claim or complete-business-request certificate.'})


def launch(output):
    if any((output / name).exists() for name in ('receipt.json', 'failure.json', 'external_process.json', 'stdout.log', 'stderr.log')):
        raise ValueError('refuse_prior_execution_overwrite')
    token = str(uuid.uuid4()); command = [sys.executable, '-m', __package__ + '.measure_public_preference_quiet', '--worker', '--output', str(output), '--admission', token]
    start = time.perf_counter()
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        result = bounded_windows_job.run(command, timeout=120., stdout=stdout, stderr=stderr, admission=token, cwd=str(ROOT))
    write(output / 'external_process.json', {**result, 'command': command, 'parent_post_import_wall_seconds': time.perf_counter() - start, 'native_calls': 0})
    if result['status'] != 'exited' or result['exitcode'] != 0: raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--audit', type=Path); p.add_argument('--admission')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare', action='store_true'); g.add_argument('--launch', action='store_true'); g.add_argument('--worker', action='store_true')
    a = p.parse_args(); a.output = a.output.resolve()
    if a.prepare: prepare(a.output, a.audit)
    elif a.launch: launch(a.output)
    else:
        if not a.admission or sys.stdin.readline().strip() != a.admission: raise ValueError('missing_owned_job_admission')
        try: worker(a.output)
        except Exception as exc:
            write(a.output / 'failure.json', {'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc(), 'native_calls': 0}); raise
if __name__ == '__main__': main()
