"""Independent saved72 codec readback; no new sample, predictor or native run.

The frozen producer's verify_saved is called unchanged once. All135 producer
sources and the separate audit closure are checked on entry/exit. Original
ABBA clocks remain data; this reader has its own fixed180 owned lifecycle.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import json
import math
from pathlib import Path
import sys
import traceback
from . import bounded_windows_job
from . import measure_complete_root_evidence_codec as frozen

c = frozen.c
PLAN = '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'
EXTERNAL = '554ce696b983bff406c2588da85eb4fb0c8f2158ee04e706d09d9eaf1dc87b01'
REPORT = '072226f85bf988d78aa42c2a622ffb52272541513cba6a15e5afa43f2fcd0605'
LIMIT = 180.
MODULE = 'scripts.experiments.g31_ics_circulation.review_complete_root_evidence_codec_saved'
METADATA = ('plan.json', 'preparation.json', 'root_ready_001.json', 'root_source_review_001.json',
    'execution_claim.json', 'bounded_execution.json', 'external_application_wall.json',
    'ledger.json', 'receipt.json', 'report.json', 'stdout.log', 'stderr.log')


def finite(value, name, positive=False):
    c.require(type(value) in (int, float) and math.isfinite(value) and
              (value > 0 if positive else value >= 0), name)
    return value


def check_import_map(paths, producer):
    c.require(type(paths) is list and paths == sorted(set(paths)) and paths and
        all(type(path) is str and path in producer['source_sha256'] for path in paths),
        'codec_review_producer_import_domain')


def producer_state(source):
    """Source/metadata-only precheck; outputs are not decoded here."""
    producer = frozen.verify_pins(source, PLAN)
    c.require(len(producer['source_sha256']) == 135, 'codec_review_producer135')
    evidence = {name: c.reference(source/name) for name in METADATA}
    outer = c.read(source/'external_application_wall.json')
    owned = c.read(source/'bounded_execution.json')
    receipt = c.read(source/'receipt.json')
    ready = c.read(source/'root_ready_001.json')
    review = c.read(source/'root_source_review_001.json')
    ledger = c.read(source/'ledger.json')
    c.require(evidence['external_application_wall.json']['sha256'] == EXTERNAL and
        evidence['report.json']['sha256'] == REPORT, 'codec_review_actual_identity')
    c.require(outer['status'] == 'application_exited_zero' and outer['exit_code'] == 0 and
        outer['error'] is None and outer['plan_sha256'] == PLAN and outer['evidence_unchanged'] is True and
        outer['fixed_historical_roots'] == 18 and outer['fixed_calls'] == 72 and outer['calls_per_arm'] == 36 and
        outer['shared_owned_seconds'] == 240 and outer['whole_python_within_240_seconds'] is True and
        outer['native_calls'] == outer['new_predictions'] == 0 and
        outer['complete_native_request_100ms_certified'] is False, 'codec_review_external_scope')
    wall = finite(outer['whole_python_application_seconds'], 'codec_review_external_wall', True)
    c.require(wall <= 240, 'codec_review_original_budget')
    process = owned['process']
    c.require(process['status'] == 'exited' and process['exitcode'] == 0 and
        process['windows_job_kill_on_close'] is True and
        process['child_released_only_after_job_assignment'] is True and
        owned['native_calls'] == owned['predictor_calls'] == 0 and
        owned['external_launch_through_exit_clock_required'] is True, 'codec_review_original_owned_job')
    c.require(finite(process['wall_seconds'], 'codec_review_child_wall', True) <= wall and
        0 < finite(process['hard_timeout_seconds'], 'codec_review_child_limit') <= 240 and
        0 < finite(owned['post_import_before_final_export_seconds'], 'codec_review_parent_wall') <= wall,
        'codec_review_clock_envelopes')
    c.require(owned['command'] == [producer['environment']['python'], '-m',
        'scripts.experiments.g31_ics_circulation.measure_complete_root_evidence_codec', '--worker',
        '--output', str(source), '--plan-sha256', PLAN], 'codec_review_exact_process_command')
    c.require(ready['plan_sha256'] == PLAN and ready['fixed_calls'] == 72 and ready['owned_seconds'] == 240 and
        ready['root_review'] == evidence['root_source_review_001.json'] and
        review['status'] == 'passed_fixed_saved18_mock_gate_ready' and review['plan_sha256'] == PLAN and
        review['live_archive_source_count'] == 135 and
        ready['wrapper_sha256'] == outer['wrapper_sha256'] == review['wrapper']['sha256'] and
        c.sha(review['wrapper']['path']) == review['wrapper']['sha256'] and
        outer['python_sha256'] == producer['environment']['sha256'], 'codec_review_review_wrapper_binding')
    c.require(receipt['status'] == 'completed_fixed_mock_ABBA' and receipt['plan_sha256'] == PLAN and
        receipt['source_changed'] == [] and receipt['native_calls'] == receipt['predictor_calls'] == 0 and
        receipt['report'] == evidence['report.json'] == owned['report'], 'codec_review_producer_receipt')
    for name in ('loaded_project_sources_entry', 'loaded_project_sources_exit'):
        check_import_map(receipt[name], producer)
    c.require(receipt['loaded_project_sources_entry'] == receipt['loaded_project_sources_exit'],
              'codec_review_producer_import_maps_changed')
    claim = c.read(source/'execution_claim.json')
    c.require(claim == {'plan_sha256': PLAN, 'shared_seconds': 240.} and
        type(ledger) is list and len(ledger) == 72 and
        all(row['status'] == 'saved' for row in ledger), 'codec_review_complete_ledger')
    c.require(not (source/'failure.json').exists(), 'codec_review_unexpected_producer_failure')
    return producer, evidence, outer, receipt, ledger


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    producer, evidence, outer, receipt, ledger = producer_state(source)
    # This invokes only the already frozen synthetic gate receipt checker; it
    # does not run tests, bindings, publication, or any historical raw decoder.
    tests = {}
    for name, minimum in (('codec', 68), ('harness', 18)):
        path = Path(producer[name+'_pure_reference']['path'])
        tests[name] = frozen._check_pure(path, minimum)
    files = c.image.source_closure(c.ROOT, (MODULE,))
    sources, archive = {}, {}
    for name, data in files.items():
        path = output/'source'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        sources[str(c.ROOT/name)] = c.image.sha_bytes(data)
        archive[str(c.ROOT/name)] = str(path.relative_to(output))
    plan = {'schema': 'g31.complete_root_evidence_codec.independent_saved72_plan.v1',
        'source_directory': str(source), 'producer_plan_sha256': PLAN, 'producer_external_sha256': EXTERNAL,
        'producer_report_sha256': REPORT, 'producer_evidence': evidence,
        'producer_output_raw': [row['raw'] for row in ledger], 'input_raw': producer['input_raw'],
        'source_sha256': sources, 'source_archive': archive, 'producer_source_count': 135,
        'producer_recorded_imports': receipt['loaded_project_sources_entry'],
        'pure_test_counts': tests, 'verifier': c.reference(Path(frozen.__file__)),
        'environment': {'python': sys.executable, 'sha256': c.sha(sys.executable)},
        'fixed_owned_seconds': LIMIT, 'historical_roots': 18, 'saved_publication_calls': 72, 'calls_per_arm': 36,
        'cost_reference_seconds': outer['whole_python_application_seconds'],
        'cost_basis': 'Original complete72 generation, export and saved verification took58.5363275s. The independent reader rehashes135 sources and reads18 source plus72 output artifacts once through the unchanged verifier.180s includes startup/imports/pins/readback/report/cleanup; not a guaranteed duration.',
        'scope': 'Saved-only original full ordered/type/floatbits/query-proof/clock readback; independently recomputed sums, medians, negative samples and all135 source entry/exit checks. No bindings/sample reconstruction, prediction, native call, or retiming.',
        'external_launch_through_exit_clock_required': True, 'status': 'prepared_unexecuted'}
    c.write(output/'plan.json', plan)
    expected = c.sha(output/'plan.json')
    verify_prepared(output, expected)
    loaded = actual_loaded(producer, plan, receipt)
    c.write(output/'preparation.json', {'status': 'prepared_source_review_pending',
        'plan': c.reference(output/'plan.json'), 'audit_source_count': len(sources),
        'producer_source_count': 135, 'tests_reexecuted': 0, 'native_calls': 0,
        'predictor_calls': 0, 'new_codec_samples': 0, 'full_readback_dispatched': False,
        'loaded_audit_prepare': loaded,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
                            '--plan-sha256', expected], 'fixed_owned_seconds': LIMIT})


def verify_prepared(output, expected):
    c.require(c.sha(output/'plan.json') == expected, 'codec_review_plan_hash')
    plan = c.read(output/'plan.json')
    c.require(plan['schema'] == 'g31.complete_root_evidence_codec.independent_saved72_plan.v1' and
        plan['producer_plan_sha256'] == PLAN and plan['producer_external_sha256'] == EXTERNAL and
        plan['producer_report_sha256'] == REPORT and plan['fixed_owned_seconds'] == LIMIT and
        plan['historical_roots'] == 18 and plan['saved_publication_calls'] == 72 and plan['calls_per_arm'] == 36 and
        plan['producer_source_count'] == 135 and plan['pure_test_counts'] == {'codec': 68, 'harness': 18},
        'codec_review_plan_contract')
    for name, digest in plan['source_sha256'].items():
        c.require(c.sha(name) == digest and c.sha(output/plan['source_archive'][name]) == digest,
                  'codec_review_audit_source_changed')
    source = Path(plan['source_directory']).resolve()
    c.require(tuple(plan['producer_evidence']) == METADATA, 'codec_review_exact_metadata_domain')
    for name, ref in plan['producer_evidence'].items():
        c.require(c.reference(source/name) == ref, 'codec_review_metadata_changed:'+name)
    c.require(c.reference(Path(frozen.__file__)) == plan['verifier'] and
        c.sha(plan['environment']['python']) == plan['environment']['sha256'],
        'codec_review_verifier_or_python_changed')
    return plan


def actual_loaded(producer, audit, receipt):
    overlap = set(producer['source_sha256']) & set(audit['source_sha256'])
    c.require(all(producer['source_sha256'][name] == audit['source_sha256'][name] for name in overlap),
              'codec_review_import_source_conflict')
    actual = c.check_loaded_sources({'source_sha256': {**producer['source_sha256'], **audit['source_sha256']}})
    # Same imported frozen producer implementation, with this audit as the only
    # additional project dependency. A missing or new producer import fails.
    projection = [name for name in actual if name in producer['source_sha256']]
    c.require(projection == receipt['loaded_project_sources_entry'] == receipt['loaded_project_sources_exit'],
              'codec_review_actual_producer_import_projection')
    return actual


def inspect_saved(output, expected):
    started = time.perf_counter_ns()
    audit = verify_prepared(output, expected)
    source = Path(audit['source_directory']).resolve()
    producer, evidence, outer, receipt, ledger = producer_state(source)
    loaded_entry = actual_loaded(producer, audit, receipt)
    c.require(audit['producer_output_raw'] == [row['raw'] for row in ledger] and
        audit['input_raw'] == producer['input_raw'] and
        audit['producer_recorded_imports'] == receipt['loaded_project_sources_entry'],
        'codec_review_exact_raw_and_import_manifest')
    # No wrapper/clone/guard edits: this is the producer's complete saved check.
    computed = frozen.verify_saved(source, PLAN)
    recorded = c.read(source/'report.json')
    c.require(tuple(recorded) == (*computed, 'fixture_load_and_binding_setup_ms'),
              'codec_review_report_exact_key_domain')
    c.require(frozen.candidate.single.exact_tree(computed, {key: recorded[key] for key in computed}),
              'codec_review_report_exact_recomputation')
    setup = finite(recorded['fixture_load_and_binding_setup_ms'], 'codec_review_setup_clock', True)
    c.require(setup <= outer['whole_python_application_seconds']*1000, 'codec_review_setup_envelope')
    for n, row in enumerate(ledger):
        if n:
            previous = ledger[n-1]
            c.require(row['started_ns'] >= previous['finished_ns']+previous['gzip_hash_elapsed_ns'],
                      'codec_review_sample_export_chronology')
    samples = computed['samples']
    a, b = (computed['summary_ms'][arm] for arm in ('A', 'B'))
    c.require((ledger[-1]['finished_ns']-ledger[0]['started_ns'])/1e9 <=
              outer['whole_python_application_seconds'], 'codec_review_sample_span')
    # Entry and exit both check every original135 live/archive source. This
    # audits present identity and recorded producer maps, not filesystem races.
    producer_state(source)
    verify_prepared(output, expected)
    loaded_exit = actual_loaded(producer, audit, receipt)
    for ref in audit['producer_output_raw']:
        c.require(c.sha(ref['path']) == ref['sha256'], 'codec_review_output_exit_drift')
    c.write(output/'recomputed_verification.json', computed)
    summary = {'schema': 'g31.complete_root_evidence_codec.independent_saved72.v1',
        'status': 'passed_complete_saved18_ABBA72_readback', 'plan': c.reference(output/'plan.json'),
        'recomputed_verification': c.reference(output/'recomputed_verification.json'),
        'producer_evidence': evidence, 'producer_source_count': 135, 'audit_source_count': len(audit['source_sha256']),
        'loaded_audit_entry': loaded_entry, 'loaded_audit_exit': loaded_exit,
        'producer_recorded_imports': receipt['loaded_project_sources_entry'],
        'source_entry_exit_unchanged': True, 'historical_roots': 18, 'saved_calls': 72, 'calls_per_arm': 36,
        'summary_ms': computed['summary_ms'], 'per_root_median_ms': computed['per_root_median_ms'],
        'negative_or_equal_root_medians': computed['negative_or_equal_root_medians'],
        'sum_reduction_fraction': 1-b['sum']/a['sum'], 'median_reduction_fraction': 1-b['median']/a['median'],
        'mock_samples_at_most_100ms': {arm: sum(row['elapsed_ms'] <= 100 for row in samples if row['arm'] == arm)
                                      for arm in ('A', 'B')},
        'fixture_load_and_binding_setup_ms': setup,
        'gzip_and_hash_sum_ms': {arm: sum(row['gzip_and_hash_ms'] for row in samples if row['arm'] == arm)
                                 for arm in ('A', 'B')},
        'whole_producer_python_seconds': outer['whole_python_application_seconds'],
        'new_native_calls': 0, 'new_predictor_calls': 0, 'new_codec_samples': 0,
        'complete_native_request_100ms_certified': False,
        'limits': ['All72 are complete saved-root evidence construction mocks, not new native or business request latencies.',
            'Original unknown roots remain in the18 fixture denominator. Every field outside explicitly regenerated wall fields is exact.',
            'Full sample construction, validation, codec and return costs are retained; fixture load/export/hash/check/cleanup remain whole-campaign costs.',
            'Negative/equal individual-root medians are retained; no selective window or timing rerun.',
            'This audit uses original unchanged full saved verifier and existing clock observations. It runs no predictor or candidate.',
            'Producer whole58.5363275s and this separate audit cost are both retained; neither is divided or deducted.'],
        'audit_seconds_before_report_export': (time.perf_counter_ns()-started)/1e9}
    c.write(output/'report.json', summary)
    print(json.dumps({key: summary[key] for key in ('status', 'summary_ms', 'negative_or_equal_root_medians',
        'sum_reduction_fraction', 'median_reduction_fraction', 'mock_samples_at_most_100ms',
        'audit_seconds_before_report_export')}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path); p.add_argument('--output', required=True, type=Path)
    p.add_argument('--prepare', action='store_true'); p.add_argument('--execute', action='store_true')
    p.add_argument('--worker', action='store_true'); p.add_argument('--plan-sha256')
    args = p.parse_args(); output = args.output.resolve()
    if args.prepare:
        prepare(args.source.resolve(), output); return 0
    if args.worker:
        c.require(sys.stdin.readline() == args.plan_sha256+'\n', 'codec_review_job_admission')
        try:
            inspect_saved(output, args.plan_sha256)
        except BaseException:
            c.write(output/'audit_failure.json', {'status': 'failed_or_unknown_saved_audit',
                'error': traceback.format_exc(), 'new_native_calls': 0, 'new_codec_samples': 0})
            raise
        return 0
    if not args.execute:
        raise ValueError('codec_review_explicit_action')
    verify_prepared(output, args.plan_sha256)
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': args.plan_sha256, 'fixed_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--plan-sha256', args.plan_sha256]
    remaining = LIMIT-(time.monotonic()-BOOT)
    if remaining <= 0:
        raise TimeoutError('codec_review_budget_before_worker')
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded_windows_job.run(command, timeout=remaining, admission=args.plan_sha256,
                                         stdout=out, stderr=err, cwd=c.ROOT)
    c.write(output/'bounded_execution.json', {'process': process, 'command': command,
        'source': c.reference(__file__), 'fixed_seconds': LIMIT,
        'post_interpreter_before_final_receipt_seconds': time.monotonic()-BOOT,
        'report': c.reference(output/'report.json') if (output/'report.json').is_file() else None,
        'external_launch_through_exit_clock_required': True,
        'new_native_calls': 0, 'new_predictor_calls': 0, 'new_codec_samples': 0})
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
