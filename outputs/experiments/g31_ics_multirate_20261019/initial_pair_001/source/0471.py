"""Separate bounded actual18 saved audit: no native, RPC, or prediction.

The complete frozen verifier is reused with one passive same-decoded-row
summary callback. Producer success and import maps are checked, rather than
inferred from the earlier failed entry producer's separate recovery.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import traceback
from types import FunctionType
from . import bounded_windows_job
from . import verify_initial_owner_route_entry_codec_campaign as verifier
from . import review_initial_owner_route_gate_saved_v2 as details_source

c = verifier.c
MODULE = 'scripts.experiments.g31_ics_circulation.review_initial_owner_route_entry_codec_saved'
PLAN = '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'
EXTERNAL = '6c9ec7215158cd4429344c18e9c89c0688ed140b98385f197f451001334097c1'
RECEIPT = '49b0d7e2f4d019c1546fb34f941813198d21189d39735eb6e0ac3101f8c184bf'
VERIFICATION = '2d948207fcd77a97dc29491c3f22e8d5c476e24c94a479759002bcece7c533dc'
LIMIT = 180.
METADATA = ('campaign.json', 'source_preparation.json', 'root_prelaunch_review_001.json',
    'root_ready_001.json', 'branch_ledger.json', 'receipt.json', 'verification.json',
    'predictor_lifetime.json', 'run_acceptance.json', 'external_launch_receipt.json',
    'external_application_wall.json', 'stderr.log', 'stdout.log', 'predictor.stderr.log',
    'execution_claim.json', 'worker_claim.json')
HISTORY = {
    'gate002': ('initial_owner_route_gate_independent_actual_review_001/report.json',
        '95361ce13acfd4711a3bc3c68fe37fb51aae1a9a841dd56ed3ddaae693bc9849'),
    'entry_recovered': ('initial_owner_route_entry_independent_actual_review_001/report.json',
        '4f552bfddaaaa8e9f981438e63e9a9a84f1971c45e6e7389d60ab27084325792')}
JOBS = {'blocker', 'loaded', 'receiver', 'reuse1', 'reuse2'}


def finite(value, reason, positive=False):
    c.require(type(value) in (int, float) and math.isfinite(value) and
        (value > 0 if positive else value >= 0), reason)
    return value


def import_map(value, plan):
    c.require(type(value) is list and value and all(type(p) is str for p in value) and
        value == sorted(set(value)) and set(value) <= set(plan['source_sha256']),
        'entry_codec_review_recorded_import_domain')


def producer_state(source):
    """Small artifacts plus full pinned source/archive/input identities; no raw decode."""
    plan = c.verify_plan(source, PLAN)
    c.require(len(plan['source_sha256']) == 169 and len(plan['compiled_source_archive_sha256']) == 67,
        'entry_codec_review_producer_domain')
    evidence = {name: c.reference(source/name) for name in METADATA}
    outer = c.read(source/'external_application_wall.json')
    launch = c.read(source/'external_launch_receipt.json')
    receipt = c.read(source/'receipt.json')
    ledger = c.read(source/'branch_ledger.json')
    ready = c.read(source/'root_ready_001.json')
    review = c.read(source/'root_prelaunch_review_001.json')
    c.require(evidence['external_application_wall.json']['sha256'] == EXTERNAL and
        evidence['receipt.json']['sha256'] == RECEIPT and
        evidence['verification.json']['sha256'] == VERIFICATION, 'entry_codec_review_actual_identity')
    c.require(outer['status'] == 'application_exited_zero' and outer['exit_code'] == 0 and
        outer['error'] is None and outer['campaign_sha256'] == PLAN and outer['evidence_unchanged'] is True and
        outer['shared_owned_job_seconds'] == 600 and outer['whole_python_within_600_seconds'] is True and
        outer['native_branch_budget'] == 18 and outer['max_concurrent_native_workers'] == 1 and
        outer['complete_100ms_certified'] is False, 'entry_codec_review_external_scope')
    wall = finite(outer['whole_python_application_seconds'], 'entry_codec_review_external_wall', True)
    c.require(wall <= 600, 'entry_codec_review_original_budget')
    process = launch['process']
    c.require(launch['campaign_sha256'] == PLAN and launch['status'] == 'campaign_process_exited' and
        launch['shared_seconds'] == 600 and process['status'] == 'exited' and process['exitcode'] == 0 and
        process['windows_job_kill_on_close'] is True and
        process['child_released_only_after_job_assignment'] is True, 'entry_codec_review_owned_process')
    c.require(finite(process['wall_seconds'], 'entry_codec_review_child_wall', True) <= wall and
        0 < finite(process['hard_timeout_seconds'], 'entry_codec_review_child_limit') <= 600 and
        0 < finite(launch['before_final_evidence_export_seconds'], 'entry_codec_review_parent_wall') <= wall,
        'entry_codec_review_clock_envelopes')
    c.require(launch['command'] == [plan['environment']['interpreter'], '-m',
        'scripts.experiments.g31_ics_circulation.initial_owner_route_entry_codec_campaign', '--output', str(source),
        '--campaign-sha256', PLAN, '--admission', PLAN], 'entry_codec_review_exact_command')
    c.require(ready['campaign_sha256'] == PLAN and ready['owned_seconds'] == 600 and
        ready['root_review'] == evidence['root_prelaunch_review_001.json'] and
        review['status'] == 'passed_finite_native_attempt_ready' and review['sources'] == 169 and
        review['compiled_sources'] == 67 and review['campaign_sha256'] == PLAN and
        ready['wrapper_sha256'] == outer['wrapper_sha256'] == review['wrapper']['sha256'] and
        c.sha(review['wrapper']['path']) == review['wrapper']['sha256'] and
        c.sha(plan['environment']['interpreter']) == outer['python_sha256'] == plan['environment']['interpreter_sha256'] and
        c.sha(c.ROOT/'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_entry_codec_campaign.py') ==
            outer['launcher_sha256'], 'entry_codec_review_launch_binding')
    c.require(set(launch['artifacts']) == {'receipt.json', 'branch_ledger.json', 'predictor_lifetime.json',
        'run_acceptance.json', 'verification.json', 'stdout.log', 'stderr.log'}, 'entry_codec_review_launch_artifact_domain')
    for name, digest in launch['artifacts'].items():
        c.require(evidence[name]['sha256'] == digest, 'entry_codec_review_launch_artifact')
    c.require(receipt['schema'] == c.SCHEMA and receipt['status'] == 'completed_finite_request_cohort' and
        receipt['source_changed'] == [] and receipt['branches'] == 18 and receipt['campaign_sha256'] == PLAN and
        receipt['verification'] == evidence['verification.json'], 'entry_codec_review_receipt')
    for name in ('loaded_project_sources_entry', 'loaded_project_sources_exit'):
        import_map(receipt[name], plan)
    c.require(receipt['loaded_project_sources_entry'] == receipt['loaded_project_sources_exit'],
        'entry_codec_review_producer_import_maps_changed')
    start, end = (receipt[k] for k in ('worker_started_after_import_ns', 'before_final_receipt_export_ns'))
    c.require(type(start) is int and type(end) is int and 0 <= start <= end and
        (end-start)/1e9 <= wall, 'entry_codec_review_receipt_clock')
    c.require(list(ledger) == plan['row_order'] and len(ledger) == 18 and
        all(row['status'] == 'raw_saved' for row in ledger.values()), 'entry_codec_review_complete_raw_ledger')
    return plan, evidence, outer, receipt, ledger


def actual_loaded(producer, audit, receipt):
    overlap = set(producer['source_sha256']) & set(audit['source_sha256'])
    c.require(all(producer['source_sha256'][p] == audit['source_sha256'][p] for p in overlap),
        'entry_codec_review_import_source_conflict')
    actual = c.check_loaded_sources({'source_sha256': {**producer['source_sha256'], **audit['source_sha256']}})
    c.require(set(receipt['loaded_project_sources_entry']) <= set(actual),
        'entry_codec_review_missing_recorded_producer_import')
    return actual


def summary_counts(rows, pairs):
    normals = {key: value for key, value in pairs.items() if key.startswith('normal/')}
    c.require(len(normals) == 6, 'entry_codec_review_normal_denominator')
    improvements, equals, unknown, regressions = [], [], [], []
    for key, pair in normals.items():
        if pair['all_five_strict_nonregression'] is None:
            unknown.append(key); continue
        delta = pair['per_job_delta']
        c.require(type(delta) is dict and set(delta) == JOBS and all(type(v) in (int, float) and
            math.isfinite(v) for v in delta.values()), 'entry_codec_review_normal_five_job_domain')
        protected = all(v <= 0 for v in delta.values())
        c.require(pair['all_five_strict_nonregression'] is protected, 'entry_codec_review_normal_protection')
        (regressions if not protected else improvements if any(v < 0 for v in delta.values()) else equals).append(key)
    warm = [finite(row['root']['warm_ms'], 'entry_codec_review_warm') for row in rows.values()
            if row['root'].get('warm_ms') is not None]
    closed = [row['root']['warm_ms'] for row in rows.values() if row['root']['closed']]
    return {'normal_pairs': {'count': 6, 'strict_nonregression_count': len(improvements)+len(equals),
        'improved': improvements, 'equal': equals, 'unknown': unknown, 'regressed': regressions},
        'root_warm_ms': {'recorded': len(warm), 'min': min(warm) if warm else None,
            'max': max(warm) if warm else None, 'median': statistics.median(warm) if warm else None},
        'closed_root_warm_ms': {'count': len(closed), 'min': min(closed) if closed else None,
            'max': max(closed) if closed else None, 'median': statistics.median(closed) if closed else None}}


def comparisons(rows, before):
    c.require(list(rows) == list(before['rows']), 'entry_codec_review_history_denominator')
    result = {}
    for key, row in rows.items():
        old = before['rows'][key]
        result[key] = {'old_warm_ms': old['root'].get('warm_ms'), 'new_warm_ms': row['root'].get('warm_ms'),
            'old_choice': old.get('choice'), 'new_choice': row.get('choice'),
            'old_hop': old.get('hop'), 'new_hop': row.get('hop'),
            'old_encoded_root_bytes': old.get('encoded_root_bytes'), 'new_encoded_root_bytes': row.get('encoded_root_bytes'),
            'old_partition_ms': old.get('warm_boundary_partition_ms'), 'new_partition_ms': row.get('warm_boundary_partition_ms'),
            'same_completion_vector': verifier.exact(old.get('business', {}).get('completion'),
                row.get('business', {}).get('completion')),
            'same_recorded_final_seal': old.get('native_state_sha256') == row.get('native_state_sha256')}
    return result


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    producer, evidence, outer, receipt, ledger = producer_state(source)
    references = {}
    for key, (name, digest) in HISTORY.items():
        ref = c.reference(c.OUT/name); c.require(ref['sha256'] == digest, 'entry_codec_review_history_hash')
        references[key] = ref
    files = c.image.source_closure(c.ROOT, (MODULE,))
    sources, archive = {}, {}
    for name, data in files.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        sources[str(c.ROOT/name)] = c.image.sha_bytes(data); archive[str(c.ROOT/name)] = str(path.relative_to(output))
    plan = {'schema': 'g31.initial_entry_codec.independent_saved18_plan.v1', 'source_directory': str(source),
        'producer_campaign_sha256': PLAN, 'producer_external_sha256': EXTERNAL,
        'producer_receipt_sha256': RECEIPT, 'producer_verification_sha256': VERIFICATION,
        'producer_evidence': evidence, 'producer_raw': {key: row['raw'] for key, row in ledger.items()},
        'producer_recorded_imports': receipt['loaded_project_sources_entry'],
        'source_sha256': sources, 'source_archive': archive, 'saved_verifier_source_proof': verifier.source_proof(),
        'previous_descriptive_reports': references, 'producer_source_count': 169, 'compiled_archive_count': 67,
        'environment': {'python': sys.executable, 'sha256': c.sha(sys.executable)}, 'fixed_owned_seconds': LIMIT,
        'cost_reference_seconds': 53.422411,
        'cost_basis': 'Prior full saved18 entry recovery took53.422411s. New reader calls unchanged complete saved verifier once and uses the same decoded branch for summary;180s includes imports/pins/all checks/hash/report/cleanup. Not a duration guarantee.',
        'scope': 'All18 endpoint/physical/RPC/entry/gate/full outbox/strict codec and root clocks. All169live/archive+67compiled and producer imports/receipt/outer pinned entry/exit. No native/predictor/candidate/codec retiming.',
        'external_launch_through_exit_clock_required': True, 'status': 'prepared_unexecuted'}
    c.write(output/'plan.json', plan); expected = c.sha(output/'plan.json')
    verify_prepared(output, expected)
    loaded = actual_loaded(producer, plan, receipt)
    c.write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': c.reference(output/'plan.json'),
        'audit_source_count': len(sources), 'producer_source_count': 169, 'compiled_archive_count': 67,
        'loaded_audit_prepare': loaded, 'full_saved_audit_dispatched': False, 'native_calls': 0, 'predictor_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--plan-sha256', expected],
        'fixed_owned_seconds': LIMIT})


def verify_prepared(output, expected):
    c.require(c.sha(output/'plan.json') == expected, 'entry_codec_review_plan_hash')
    plan = c.read(output/'plan.json')
    c.require(plan['schema'] == 'g31.initial_entry_codec.independent_saved18_plan.v1' and
        plan['producer_campaign_sha256'] == PLAN and plan['producer_external_sha256'] == EXTERNAL and
        plan['producer_receipt_sha256'] == RECEIPT and plan['producer_verification_sha256'] == VERIFICATION and
        plan['producer_source_count'] == 169 and plan['compiled_archive_count'] == 67 and
        plan['fixed_owned_seconds'] == LIMIT and plan['saved_verifier_source_proof'] == verifier.source_proof(),
        'entry_codec_review_plan_contract')
    for path, digest in plan['source_sha256'].items():
        c.require(c.sha(path) == digest and c.sha(output/plan['source_archive'][path]) == digest,
            'entry_codec_review_audit_source_changed')
    source = Path(plan['source_directory']).resolve()
    c.require(tuple(plan['producer_evidence']) == METADATA, 'entry_codec_review_metadata_domain')
    for name, ref in plan['producer_evidence'].items():
        c.require(c.reference(source/name) == ref, 'entry_codec_review_metadata_changed:'+name)
    c.require(set(plan['previous_descriptive_reports']) == set(HISTORY), 'entry_codec_review_history_domain')
    for key, ref in plan['previous_descriptive_reports'].items():
        c.require(ref['sha256'] == HISTORY[key][1] and c.sha(ref['path']) == ref['sha256'],
            'entry_codec_review_history_changed')
    c.require(c.sha(plan['environment']['python']) == plan['environment']['sha256'], 'entry_codec_review_python_changed')
    return plan


def inspect_saved(output, expected):
    started = time.perf_counter_ns(); audit = verify_prepared(output, expected)
    source = Path(audit['source_directory']).resolve()
    plan, evidence, outer, receipt, ledger = producer_state(source)
    loaded_entry = actual_loaded(plan, audit, receipt)
    c.require(audit['producer_raw'] == {key: row['raw'] for key, row in ledger.items()} and
        audit['producer_recorded_imports'] == receipt['loaded_project_sources_entry'], 'entry_codec_review_raw_import_manifest')
    life = c.read(source/'predictor_lifetime.json'); samples = {row['request_id']: row for row in life['ledger']}; rows = {}
    def visit(raw, row, key):
        result = verifier.verify_branch(raw, row, key)
        rows[key] = details_source.details(raw, result, samples)
        rows[key]['raw'] = ledger[key]['raw']
        return result
    readback = FunctionType(verifier.verify_saved.__code__, {**verifier.verify_saved.__globals__, 'verify_branch': visit},
        verifier.verify_saved.__name__, verifier.verify_saved.__defaults__, verifier.verify_saved.__closure__)
    readback.__kwdefaults__ = verifier.verify_saved.__kwdefaults__
    c.require(readback.__code__ is verifier.verify_saved.__code__ and
        readback.__closure__ == verifier.verify_saved.__closure__, 'entry_codec_review_no_guard_rewrite')
    computed = readback(source, PLAN)
    c.require(verifier.exact(computed, c.read(source/'verification.json')), 'entry_codec_review_saved_result_changed')
    for key, value in computed['rows'].items():
        rows.setdefault(key, {'root': value['root'], 'failure': value.get('failure')})
        rows[key]['branch_attempt'] = value['branch_attempt']
    c.require(list(rows) == plan['row_order'] and len(rows) == 18, 'entry_codec_review_denominator')
    counts = summary_counts(rows, computed['pairs'])
    history = {key: comparisons(rows, c.read(ref['path'])) for key, ref in audit['previous_descriptive_reports'].items()}
    producer_state(source); verify_prepared(output, expected); loaded_exit = actual_loaded(plan, audit, receipt)
    for ref in audit['producer_raw'].values():
        c.require(c.sha(ref['path']) == ref['sha256'], 'entry_codec_review_raw_exit_drift')
    c.write(output/'recomputed_verification.json', computed)
    report = {'schema': 'g31.initial_entry_codec.independent_saved18.v1',
        'status': 'passed_complete_saved_endpoint_physical_RPC_entry_gate_outbox_codec_audit',
        'evidence': evidence, 'audit_plan': c.reference(output/'plan.json'),
        'recomputed_verification': c.reference(output/'recomputed_verification.json'),
        'producer_source_count': 169, 'compiled_archive_count': 67, 'audit_source_count': len(audit['source_sha256']),
        'producer_recorded_imports_entry': receipt['loaded_project_sources_entry'],
        'producer_recorded_imports_exit': receipt['loaded_project_sources_exit'],
        'loaded_audit_entry': loaded_entry, 'loaded_audit_exit': loaded_exit, 'source_entry_exit_unchanged': True,
        'branches': 18, 'closed_roots': computed['closed_roots'], 'open_or_unknown_roots': computed['open_or_unknown_roots'],
        'roots_at_most_100ms': sum(row['root'].get('observed_within_100ms', False) for row in rows.values()),
        'prediction_counts': computed['prediction_counts'], 'RPC_requests': computed['predictor_requests'],
        'predictor_protocol_closed': computed['predictor_protocol_closed'],
        'predictor_startup_ms': computed['predictor_startup_ms'],
        'predictor_close_with_cleanup_ms': computed['predictor_close_with_cleanup_ms'],
        'full_worker_setup_through_predictor_ready_ms': (life['ready_ns']-life['worker_setup_started_ns'])/1e6,
        'whole_producer_python_seconds': outer['whole_python_application_seconds'],
        'whole_campaign_unamortized_sensitivity_ms_per_root': outer['whole_python_application_seconds']*1000,
        'gate_steps': sum(row.get('gate', {}).get('steps', 0) for row in rows.values()),
        'gate_skips': sum(row.get('gate', {}).get('skips', 0) for row in rows.values()),
        'root_encoded_bytes': sum(row.get('encoded_root_bytes', 0) for row in rows.values()),
        **counts, 'rows': rows, 'pairs': computed['pairs'], 'previous_descriptive_reports': audit['previous_descriptive_reports'],
        'previous_descriptive_comparisons': history,
        'limits': ['One unchanged complete saved verifier traversal; no native/RPC/predictor or new timing samples.',
            'Six recorded-boundary intervals sum to root wall; they are not isolated function cost measurements.',
            'Prior failed entry producer and its missing exit receipt/import proof stay failed; recovered saved proof is distinct.',
            'Different rounds and deadline-dependent choices: no ABBA or causal claim about codec, choices or business improvements.',
            'All startup/native/shared/RPC/codec/output/cleanup costs remain; no subtraction or amortization.',
            'Finite initial-A two-choice firsthop scope, not original business100ms/full32/two-machine/all-day certification.',
            'Separate180s audit cost is retained and never deducted from producer costs.'],
        'new_native_calls': 0, 'new_predictor_calls': 0, 'review_seconds_before_report': (time.perf_counter_ns()-started)/1e9}
    c.write(output/'report.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'closed_roots', 'open_or_unknown_roots',
        'roots_at_most_100ms', 'normal_pairs', 'closed_root_warm_ms', 'gate_steps', 'gate_skips', 'review_seconds_before_report')}))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepare', action='store_true'); p.add_argument('--execute', action='store_true')
    p.add_argument('--worker', action='store_true'); p.add_argument('--plan-sha256'); args = p.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(args.source.resolve(), output); return 0
    if args.worker:
        c.require(sys.stdin.readline() == args.plan_sha256+'\n', 'entry_codec_review_job_admission')
        try: inspect_saved(output, args.plan_sha256)
        except BaseException:
            c.write(output/'audit_failure.json', {'status': 'failed_or_unknown_separate_saved_audit',
                'error': traceback.format_exc(), 'new_native_calls': 0, 'new_predictor_calls': 0}); raise
        return 0
    if not args.execute: raise ValueError('entry_codec_review_explicit_action')
    verify_prepared(output, args.plan_sha256)
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': args.plan_sha256, 'fixed_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--plan-sha256', args.plan_sha256]
    remaining = LIMIT-(time.monotonic()-BOOT)
    if remaining <= 0: raise TimeoutError('entry_codec_review_budget_before_worker')
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded_windows_job.run(command, timeout=remaining, admission=args.plan_sha256, stdout=out, stderr=err, cwd=c.ROOT)
    c.write(output/'bounded_execution.json', {'process': process, 'command': command, 'source': c.reference(__file__),
        'fixed_seconds': LIMIT, 'post_interpreter_before_final_receipt_seconds': time.monotonic()-BOOT,
        'external_launch_through_exit_clock_required': True, 'new_native_calls': 0, 'new_predictor_calls': 0,
        'report': c.reference(output/'report.json') if (output/'report.json').is_file() else None})
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 else 1


if __name__ == '__main__': raise SystemExit(main())
