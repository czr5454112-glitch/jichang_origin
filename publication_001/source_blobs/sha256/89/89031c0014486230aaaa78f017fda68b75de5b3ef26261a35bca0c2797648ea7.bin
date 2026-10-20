"""Preregistered pure conformance + AB/BA full model-batch comparison.

The parent owns a Windows Job for the entire120s worker including preflight,
conformance, measurements, exact comparison, archive checks and final output.
No native session is loaded. These are model-batch costs, not complete user
business-request timing or a100ms certificate.
"""
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

from . import public_preference_prefix_context as candidate
from . import public_preference_request_context as baseline
from . import bounded_windows_job
from .public_owned_action_state import bind_supplied_bundle
from .validate_public_native_preference_projection import sha, imported_source_pins

ROOT = Path(__file__).resolve().parents[3]


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exact_outputs(expected, actual, count):
    return (len(expected) == count and len(actual) == count
            and all(encoded(a) == encoded(b) for a, b in zip(expected, actual, strict=True)))


def source_inventory():
    sources = imported_source_pins()
    for suffix in ('public_preference_prefix_context', 'public_native_preference_projection',
                   'public_native_later_preference_projection', 'measure_public_preference_prefix'):
        test = ROOT / ('tests/test_g31_circulation_' + suffix + '.py')
        sources[str(test)] = sha(test)
    return sources


def check_plan(plan, audit):
    cases = sorted({key.split('/')[0] for key in audit['rows']})
    if (plan.get('schema') != 'g31.public_preference_prefix_pair.v1'
            or audit.get('status') != 'saved192_revalidated_no_new_native'
            or len(audit['rows']) != 192 or len(cases) != 6
            or plan.get('initial_candidate_denominator') != 192
            or plan.get('later_candidate_denominator') != 48
            or plan.get('hard_timeout_seconds') != 120.
            or plan.get('native_calls') != 0
            or [row['case'] for row in plan['cases']] != cases
            or plan.get('historical_native_status_counts') != dict(Counter(r['status_retained'] for r in audit['rows'].values()))):
        raise ValueError('changed_plan_denominator_or_semantics')
    for index, case in enumerate(plan['cases']):
        keys = sorted(key for key in audit['rows'] if key.startswith(case['case'] + '/'))
        if (len(keys) != 32 or keys[0] != case['case'] + '/vector_00'
                or case['initial_source_key'] != keys[0]
                or case['input'] != case['case'] + '.input.json'
                or case['batch_order'] != (['A', 'B', 'B', 'A'] if index % 2 == 0 else ['B', 'A', 'A', 'B'])
                or case['raw_path'] != audit['rows'][keys[0]]['raw_artifact']
                or case['raw_sha256'] != audit['rows'][keys[0]]['raw_sha256']):
            raise ValueError('changed_case_source_or_order')


def prepare(output, audit_path):
    output.mkdir(parents=True, exist_ok=False); archive = output / 'source'; archive.mkdir()
    audit_path = audit_path.resolve(); audit = json.loads(audit_path.read_text())
    if audit.get('status') != 'saved192_revalidated_no_new_native' or len(audit['rows']) != 192:
        raise ValueError('unexpected192_corpus')
    sources = source_inventory()
    archived = {}
    for index, (path, digest) in enumerate(sorted(sources.items())):
        name = f'{index:04d}.py'; (archive / name).write_bytes(Path(path).read_bytes())
        archived[path] = {'sha256': digest, 'archive': name}
    cases = []
    case_names = sorted({key.split('/')[0] for key in audit['rows']})
    if len(case_names) != 6: raise ValueError('unexpected_case_denominator')
    for index, case in enumerate(case_names):
        first_key = min(key for key in audit['rows'] if key.startswith(case + '/'))
        if (not first_key.endswith('/vector_00')
                or sum(key.startswith(case + '/') for key in audit['rows']) != 32):
            raise ValueError('unexpected_case_vectors')
        row = audit['rows'][first_key]; raw_path = Path(row['raw_artifact'])
        if sha(raw_path) != row['raw_sha256']: raise ValueError('changed_raw')
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        bundle = raw['initial_owners']['A']['information']['bundle']
        source_input = output / f'{case}.input.json'; write(source_input, bundle)
        cases.append({'case': case, 'initial_source_key': first_key, 'raw_path': str(raw_path),
                      'raw_sha256': row['raw_sha256'], 'input': source_input.name, 'input_sha256': sha(source_input),
                      'batch_order': ['A', 'B', 'B', 'A'] if index % 2 == 0 else ['B', 'A', 'A', 'B']})
    plan = {'schema': 'g31.public_preference_prefix_pair.v1', 'sources': archived,
        'audit': {'path': str(audit_path), 'sha256': sha(audit_path)}, 'cases': cases,
        'native_calls': 0, 'initial_candidate_denominator': 192, 'later_candidate_denominator': 48,
        'historical_native_status_counts': dict(Counter(r['status_retained'] for r in audit['rows'].values())),
        'hard_timeout_seconds': 120., 'A': 'unchanged public_preference_request_context.RequestContext',
        'B': 'new public_preference_prefix_context.PrefixContext',
        'later_A': 'Four unchanged independent public_native_later_preference_projection.predict calls',
        'later_B': 'One new LaterPrefixContext construction and all four predictions',
        'all_costs_in_batch': 'Context source checks/guard compilation/input copy/validation/static prep, every requested candidate, full dynamic clones and all result copies. Original32/4 vocabulary retained.',
        'outside_batch_but_inside_owned_worker': 'Input/source/archive reads, original independent conformance runs, canonical full-output comparison, report/ledger serialization. All included in outer process wall, not silently subtracted from a business-request claim.',
        'timing_scope': 'One supplied public model request with32 candidate predictions; not delivered owner controller or exhaustive business request, no100ms certification.',
        'conformance': 'All6 initial public snapshots×32 exactly compare original independent predictor. All6 representative raw first-return/reuse snapshots×4 compare original later predictor, retaining every unknown reason.',
        'corpus_scope': 'Exactly vector_00 raw from each of six cases. These are retrospective semantic-debugging/regression comparands, not held-out unseen data. The historical18 native unknown rows remain unknown and are not re-executed or promoted by pure projection equivalence.',
        'candidate_execution': 'Prefixes computed lazily only for actually requested candidates; no quiet-tail batching, no native forks, no outcome table policyinput.',
        'ordering': 'Per-case oneAB andoneBA pair; odd case reverses pair order. No discarded warmups; every sample retained.',
        'failure': 'Any source drift, unknown promotion, byte mismatch, timeout or regression remains recorded. No source or original evidence is rewritten.'}
    check_plan(plan, audit)
    write(output / 'preregistered_protocol.json', plan)
    write(output / 'prepare_receipt.json', {'status': 'prepared_zero_model_or_native_execution',
        'plan_sha256': sha(output / 'preregistered_protocol.json'), 'source_count': len(archived),
        'pure_projection_calls': 0, 'native_calls': 0})


def verify(output, plan):
    if source_inventory() != {path: entry['sha256'] for path, entry in plan['sources'].items()}:
        raise ValueError('loaded_source_inventory_drift')
    for path, entry in plan['sources'].items():
        if sha(path) != entry['sha256'] or sha(output / 'source' / entry['archive']) != entry['sha256']:
            raise ValueError('source_or_archive_drift:' + path)
    if sha(plan['audit']['path']) != plan['audit']['sha256']: raise ValueError('changed_audit')
    check_plan(plan, json.loads(Path(plan['audit']['path']).read_bytes()))
    for case in plan['cases']:
        if sha(output / case['input']) != case['input_sha256'] or sha(case['raw_path']) != case['raw_sha256']:
            raise ValueError('changed_input_or_raw')
        raw = json.loads(gzip.decompress(Path(case['raw_path']).read_bytes()))
        supplied = json.loads((output / case['input']).read_bytes())
        if encoded(supplied) != encoded(raw['initial_owners']['A']['information']['bundle']):
            raise ValueError('input_not_bound_to_selected_public_capture')


def worker(output):
    started = time.perf_counter(); plan_path = output / 'preregistered_protocol.json'
    plan = json.loads(plan_path.read_text()); plan_hash = sha(plan_path)
    verify(output, plan)
    ledger = []; later_ledger = []; conformance = []; exceptions = []; results = []
    write(output / 'progress.json', {'status': 'worker_started', 'native_calls': 0})
    for case in plan['cases']:
        bundle = json.loads((output / case['input']).read_text())
        context = baseline.RequestContext(bundle); actions = context.actions()
        if len(actions) != 32: raise ValueError('unsupported_initial_case')
        references = [candidate.original.predict(bundle, a) for a in actions]
        prefix = candidate.PrefixContext(bundle)
        actual = [prefix.predict(a) for a in actions]
        if not exact_outputs(references, actual, 32):
            write(output / (case['case'] + '.initial_mismatch.json'), {'reference': references, 'candidate': actual})
            raise ValueError('initial_full_output_or_count_mismatch')
        initial_checks = [encoded(a) == encoded(b) for a, b in zip(references, actual, strict=True)]
        conformance.append({'case': case['case'], 'phase': 'initial', 'checks': initial_checks,
                            'candidate_count': len(actions), 'cache': prefix.describe()})
        raw = json.loads(gzip.decompress(Path(case['raw_path']).read_bytes()))
        decisions = [r for owner in ('A', 'B') for r in raw['decisions'][owner]]
        if len(decisions) != 2: raise ValueError('missing_later_stages')
        if sorted(d['phase'] for d in decisions) != ['first_return', 'first_reuse_route']:
            raise ValueError('changed_later_phase_denominator')
        for decision in decisions:
            information = decision['information']; data = information.get('bundle', {})
            if data.get('status') == 'conditional_model_input':
                data = bind_supplied_bundle(data, information['raw_endpoints']['view'])
            later_context = candidate.LaterPrefixContext(data)
            if len(candidate.later.ACTIONS) != 4: raise ValueError('changed_later_action_denominator')
            later_checks = []; later_references = []
            for action in candidate.later.ACTIONS:
                reference = candidate.later.predict(data, action); result = later_context.predict(action)
                later_references.append(reference)
                later_checks.append(encoded(reference) == encoded(result))
                if reference['status'].startswith('unknown'):
                    exceptions.append({'case': case['case'], 'phase': decision['phase'],
                                       'action': action, 'status': reference['status'], 'reasons': reference.get('reasons'),
                                       'unknown_preserved': result == reference})
                if reference != result:
                    write(output / (case['case'] + '.' + decision['phase'] + '.mismatch.json'), {'reference': reference, 'candidate': result})
                    raise ValueError('later_full_output_mismatch')
            conformance.append({'case': case['case'], 'phase': decision['phase'], 'checks': later_checks,
                                'candidate_count': 4, 'cache': later_context.describe()})
            for index, arm in enumerate(case['batch_order']):
                before = time.perf_counter_ns()
                if arm == 'A':
                    values = [candidate.later.predict(data, a) for a in candidate.later.ACTIONS]
                else:
                    c = candidate.LaterPrefixContext(data)
                    values = [c.predict(a) for a in candidate.later.ACTIONS]
                elapsed = time.perf_counter_ns() - before
                matches = exact_outputs(later_references, values, 4)
                later_ledger.append({'case': case['case'], 'phase': decision['phase'],
                    'sample': index, 'arm': arm, 'wall_ns': elapsed, 'candidate_count': len(values),
                    'all_complete_outputs_exact': matches, 'all_preparation_and_output_copies_included': True})
                write(output / 'later_timing_ledger.json', later_ledger)
                if not matches: raise ValueError('timed_later_full_output_mismatch')
        for index, arm in enumerate(case['batch_order']):
            before = time.perf_counter_ns()
            c = baseline.RequestContext(bundle) if arm == 'A' else candidate.PrefixContext(bundle)
            values = [c.predict(a) for a in c.actions()]
            elapsed = time.perf_counter_ns() - before
            matches = exact_outputs(references, values, 32)
            row = {'case': case['case'], 'sample': index, 'arm': arm, 'wall_ns': elapsed,
                   'candidate_count': len(values), 'all_complete_outputs_exact': matches,
                   'all_preparation_and_output_copies_included': True}
            ledger.append(row); write(output / 'timing_ledger.json', ledger)
            if not matches: raise ValueError('timed_full_output_mismatch')
        sample = [r for r in ledger if r['case'] == case['case']]
        a = [r['wall_ns'] for r in sample if r['arm'] == 'A']; b = [r['wall_ns'] for r in sample if r['arm'] == 'B']
        results.append({'case': case['case'], 'A_ns': a, 'B_ns': b,
                        'median_A_ns': statistics.median(a), 'median_B_ns': statistics.median(b),
                        'candidate_faster': statistics.median(b) < statistics.median(a)})
        write(output / 'progress.json', {'status': 'case_complete', 'cases_completed': len(results),
              'native_calls': 0, 'elapsed_wall_seconds': time.perf_counter() - started})
    verify(output, plan)
    if sha(plan_path) != plan_hash: raise ValueError('changed_protocol')
    if (len(ledger) != 24 or len(later_ledger) != 48 or len(conformance) != 18
            or sum(row['candidate_count'] for row in conformance if row['phase'] == 'initial') != 192
            or sum(row['candidate_count'] for row in conformance if row['phase'] != 'initial') != 48):
        raise ValueError('incomplete_executed_denominator')
    report = {'status': 'completed_exact_pure_prefix_pair', 'schema': 'g31.public_preference_prefix_pair.receipt.v1',
        'plan_sha256': plan_hash, 'source_changed': [], 'native_calls': 0,
        'initial_conformance_count': 192, 'later_conformance_count': 48,
        'conformance': conformance, 'retained_unknown_later': exceptions,
        'historical_native_status_counts_retained': plan['historical_native_status_counts'],
        'timing_samples': ledger, 'later_timing_samples': later_ledger, 'case_pairs': results,
        'median_all_A_ns': statistics.median(r['wall_ns'] for r in ledger if r['arm'] == 'A'),
        'median_all_B_ns': statistics.median(r['wall_ns'] for r in ledger if r['arm'] == 'B'),
        'later_phase_medians_ns': {phase: {arm: statistics.median(r['wall_ns'] for r in later_ledger
            if r['phase'] == phase and r['arm'] == arm) for arm in ('A', 'B')}
            for phase in ('first_return', 'first_reuse_route')},
        'wall_seconds': time.perf_counter() - started, 'complete_100ms_certified': False,
        'new_native_or_online_claim': False, 'unknown_promoted': False,
        'limits': 'Small pure model-batch AB/BA comparison under current concurrent host load; full inputs/outputs and all preparation charged. Not complete business-request timing. No quiet-tail optimization.'}
    write(output / 'receipt.json', report)


def launch(output):
    if any((output / name).exists() for name in ('receipt.json', 'failure.json', 'external_process.json', 'stdout.log', 'stderr.log')):
        raise ValueError('refuse_to_overwrite_prior_execution')
    token = str(uuid.uuid4()); command = [sys.executable, '-m', __package__ + '.measure_public_preference_prefix',
                                        '--worker', '--output', str(output), '--admission', token]
    started = time.perf_counter()
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        result = bounded_windows_job.run(command, timeout=120., stdout=stdout, stderr=stderr,
                                        admission=token, cwd=str(ROOT))
    write(output / 'external_process.json', {**result, 'command': command,
          'outer_wall_seconds': time.perf_counter() - started, 'native_calls': 0})
    if result['status'] != 'exited' or result['exitcode'] != 0: raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--audit', type=Path); p.add_argument('--admission')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare', action='store_true'); g.add_argument('--launch', action='store_true'); g.add_argument('--worker', action='store_true')
    a = p.parse_args(); a.output = a.output.resolve()
    if a.prepare: prepare(a.output, a.audit)
    elif a.launch: launch(a.output)
    else:
        if not a.admission or sys.stdin.readline().strip() != a.admission: raise ValueError('missing_owned_job_admission')
        try: worker(a.output)
        except Exception as exc:
            write(a.output / 'failure.json', {'status': 'failed', 'exception': type(exc).__name__ + ':' + str(exc),
                'traceback': traceback.format_exc(), 'native_calls': 0})
            raise


if __name__ == '__main__': main()
