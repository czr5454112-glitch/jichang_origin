"""Prepared fixed saved-gate002 full18 x ABBA72 codec comparison; no native.

All fixture load, output export/hash, full saved checks and teardown belong to
one owned240s campaign. Sample clocks additionally delimit complete mock root
construction through original publisher return. Historical event clocks remain
data; no sample is an actual new request latency or an observation-gate test.
"""
import time
BOOT = time.monotonic()
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import traceback
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import complete_root_evidence_candidate as candidate
from . import root_evidence_mock as mock

c = candidate.single.old
LIMIT = 240.
SCHEMA = 'g31.complete_root_evidence_codec_ABBA.v1'
SOURCE = c.OUT/'initial_owner_route_gate_campaign_prepare_002'
CAMPAIGN_SHA = '659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4'
SUMMARY = c.OUT/'initial_owner_route_gate_independent_actual_review_001/report.json'
SUMMARY_SHA = '95361ce13acfd4711a3bc3c68fe37fb51aae1a9a841dd56ed3ddaae693bc9849'
CODEC_PURE = c.OUT/'complete_root_evidence_codec_pure_001/receipt.json'
CODEC_PURE_SHA = '3df735e6ef69fec3731e2f4691a80b686a115c8e803de152f16be08c51b89591'


def declarations(keys):
    return [{'key': key, 'arm': arm, 'position': n} for key in keys for n, arm in enumerate('ABBA')]


def _fixture_proof(root):
    # Saved data only, read by the unchanged evidence builder, never a native
    # capability or a substitute for live runtime collection in an actual root.
    return root._complete_saved_query_proof


def bindings(arm, clock=time):
    if arm == 'A': method, finish = candidate.frozen.EVIDENCE, candidate.frozen.finish_root
    elif arm == 'B': method, finish = candidate.EVIDENCE, candidate.finish_root
    else: raise ValueError('codec_mock_arm')
    method = mock.clone(method, time=clock, root_runtime_proof=_fixture_proof)
    finish = mock.clone(finish, time=clock, evidence=method)
    publish = mock.clone(candidate.single.publish_root, time=clock, finish_root=finish)
    return method, publish


def root_from_fixture(record, method):
    value = record['value']['evidence']
    c.require('runtime_query_proof' in value and type(value['runtime_query_proof']) is dict,
              'codec_complete_runtime_query_proof_missing')
    root = mock.root_from_evidence(value, method)
    root._complete_saved_query_proof = value['runtime_query_proof']
    return root


def _input_manifest():
    c.require(c.sha(SOURCE/'campaign.json') == CAMPAIGN_SHA and c.sha(SUMMARY) == SUMMARY_SHA,
              'codec_saved_authority_changed')
    campaign = c.read(SOURCE/'campaign.json')
    ledger = c.read(SOURCE/'branch_ledger.json')
    summary = c.read(SUMMARY)
    keys = campaign['row_order']
    c.require(len(keys) == 18 and list(ledger) == keys and list(summary['rows']) == keys,
              'codec_original18_denominator')
    refs = {}
    for key in keys:
        c.require(ledger[key]['status'] == 'raw_saved' and ledger[key]['raw'] == summary['rows'][key]['raw'],
                  'codec_original_raw_reference')
        refs[key] = ledger[key]['raw']
    return refs


def load_inputs(plan):
    """One decoded source raw at a time; retain only its complete root record."""
    inputs = {}
    for key, ref in plan['input_raw'].items():
        c.require(c.sha(ref['path']) == ref['sha256'], 'codec_input_raw_changed')
        with gzip.open(ref['path'], 'rt', encoding='utf8') as stream:
            raw = json.load(stream, object_pairs_hook=c.image._pairs, parse_constant=c.image._constant)
        c.require(len(raw['root_records']) == 1, 'codec_input_root_count')
        record = raw['root_records'][0]
        mock.semantic_record(record)  # Exact outer/value topology, all fields.
        value = record['value']['evidence']
        c.require(type(value['runtime_query_proof']) is dict, 'codec_input_proof')
        inputs[key] = record
        del raw
    return inputs


def _fixture_hash(record):
    # The fixture is strict source-authenticated JSON; this setup/check cost is
    # outside samples but inside the owned campaign, never amortized away.
    return hashlib.sha256(c.image.artifact_encode(record)).hexdigest()


def _check_pure(path, minimum):
    receipt = c.read(path)
    xml = path.parent/'tests.xml'
    cases = ET.parse(xml).getroot().findall('.//testcase')
    c.require(receipt['status'] == 'passed' and receipt['source_changed'] == [] and
        receipt['native_calls'] == receipt['predictor_calls'] == receipt['performance_runs'] == 0 and
        receipt['XML_sha256'] == c.sha(xml) and len(cases) == receipt['tests'] >= minimum and
        not any(child.tag in ('failure', 'error', 'skipped') for case in cases for child in case), 'codec_pure_gate')
    for name, digest in receipt['source_sha256'].items():
        c.require(c.sha(c.ROOT/name) == digest and c.sha(path.parent/'source'/name) == digest,
                  'codec_pure_source_changed')
    return len(cases)


def prepare(output, pure):
    output.mkdir(parents=True, exist_ok=False)
    c.require(c.sha(CODEC_PURE) == CODEC_PURE_SHA, 'codec_frozen68_receipt')
    _check_pure(CODEC_PURE, 68)
    count = _check_pure(pure, 8)
    inputs = _input_manifest()
    files = c.image.source_closure(c.ROOT, (__package__+'.measure_complete_root_evidence_codec',
        __package__+'.run_complete_root_evidence_codec_campaign_pure',
        'tests.test_g31_circulation_complete_root_evidence_codec_campaign'))
    sources, archives = {}, {}
    for name, data in files.items():
        destination = output/'source'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        sources[str(c.ROOT/name)] = hashlib.sha256(data).hexdigest()
        archives[str(c.ROOT/name)] = str(destination.relative_to(output))
    plan = {'schema': SCHEMA, 'row_order': declarations(inputs), 'historical_roots': 18,
        'publication_calls': 72, 'calls_per_arm': 36, 'hard_timeout_seconds': LIMIT,
        'source_sha256': sources, 'source_archive': archives,
        'environment': {'python': sys.executable, 'sha256': c.sha(sys.executable)},
        'input_campaign': c.reference(SOURCE/'campaign.json'), 'input_ledger': c.reference(SOURCE/'branch_ledger.json'),
        'input_saved_verification': c.reference(SOURCE/'verification.json'),
        'input_independent_review': c.reference(SUMMARY), 'input_raw': inputs,
        'codec_pure_reference': c.reference(CODEC_PURE), 'codec_pure_XML': c.reference(CODEC_PURE.parent/'tests.xml'),
        'harness_pure_reference': c.reference(pure), 'harness_pure_XML': c.reference(pure.parent/'tests.xml'),
        'codec_source_proof': candidate.source_proof(),
        'arms': {'A': 'Frozen actual gate002 complete evidence/strict decode/exact_tree/full return',
                 'B': 'Same complete evidence with redundant encode _tree removed and owned strict decode/C re-encode comparison'},
        'scope': {
            'sample': 'Mock root creation, full proof normalization/encode/strict roundtrip, hash, ledger, return codec, publisher append/return.',
            'whole': 'All startup, source/interpreter/input checks, fixture load, setup, 72 samples, full export/hash/ledger, exact saved verification and shutdown within owned240; external launch wall separately required.',
            'unchanged': 'All18 historical roots including2unknown, complete endpoint/query/outbox evidence and every scalar/key order. No native/predictor/firsthop/scheduler run.',
            'clock_exclusions': 'Only regenerated body_finished_ns/body_elapsed_ns/finalization_started_ns/outside_return_ns/warm_caller_elapsed_ns/derived within100 change. Original root/event/deadline clocks remain exact data. Every regenerated clock/formula is checked.',
            'budget_basis': 'Prior old-v3 18xABBA72 full mock cost152.7235709s; current gate002 root evidence is smaller (22,610,412 total bytes).240s is a fixed censoring bound, not a promised duration.',
            'no_claim': ['new native-root latency', '100ms certification', 'observation-gate acceleration', 'future full-day throughput'],
        }, 'status': 'prepared_unexecuted'}
    c.write(output/'plan.json', plan)
    c.write(output/'ledger.json', [{**row, 'status': 'unknown_unexecuted'} for row in plan['row_order']])
    expected = c.sha(output/'plan.json')
    verify_pins(output, expected)
    c.write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': c.reference(output/'plan.json'),
        'source_count': len(sources), 'codec_pure_tests': 68, 'harness_pure_tests': count,
        'native_calls': 0, 'predictor_calls': 0, 'performance_dispatched': False,
        'execute_command': [sys.executable, '-m', __package__+'.measure_complete_root_evidence_codec',
                            '--execute', '--output', str(output), '--plan-sha256', expected]})


def verify_pins(output, expected):
    c.require(c.sha(output/'plan.json') == expected, 'codec_plan_sha')
    plan = c.read(output/'plan.json')
    c.require(plan['schema'] == SCHEMA and plan['historical_roots'] == 18 and plan['publication_calls'] == 72 and
        plan['calls_per_arm'] == 36 and plan['hard_timeout_seconds'] == LIMIT and
        plan['row_order'] == declarations(plan['input_raw']) and len(plan['input_raw']) == 18,
        'codec_denominator_or_order')
    c.require(plan['codec_source_proof'] == candidate.source_proof(), 'codec_source_proof_changed')
    for name, digest in plan['source_sha256'].items():
        c.require(c.sha(name) == digest and c.sha(output/plan['source_archive'][name]) == digest, 'codec_source_changed')
    for key in ('input_campaign', 'input_ledger', 'input_saved_verification', 'input_independent_review',
                'codec_pure_reference', 'codec_pure_XML', 'harness_pure_reference', 'harness_pure_XML'):
        ref = plan[key]; c.require(c.sha(ref['path']) == ref['sha256'], 'codec_input_changed:'+key)
    c.require(plan['input_raw'] == _input_manifest(), 'codec_exact_input_manifest')
    for ref in plan['input_raw'].values(): c.require(c.sha(ref['path']) == ref['sha256'], 'codec_raw_changed')
    c.require(c.sha(plan['environment']['python']) == plan['environment']['sha256'], 'codec_python_changed')
    return plan


def verify_outputs(output, plan, inputs):
    ledger = c.read(output/'ledger.json')
    c.require(len(ledger) == 72 and list(inputs) == list(plan['input_raw']), 'codec_saved_denominator')
    samples = []
    for index, (row, declared) in enumerate(zip(ledger, plan['row_order'])):
        c.require(tuple(row) == ('key', 'arm', 'position', 'status', 'started_ns', 'finished_ns',
            'elapsed_ns', 'raw', 'gzip_hash_elapsed_ns') and row['status'] == 'saved' and
            candidate.single.exact_tree({k: row[k] for k in declared}, declared),
                  'codec_saved_row_identity')
        path = output/'raw'/f'{index:03d}.json.gz'
        c.require(row['raw'] == c.reference(path), 'codec_saved_hash')
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            data = json.load(stream, object_pairs_hook=c.image._pairs, parse_constant=c.image._constant)
        c.require(type(data) is dict and tuple(data) == ('declaration', 'record') and
            candidate.single.exact_tree(data['declaration'], declared), 'codec_saved_topology')
        mock.current_clock_bounds(data['record'], row['started_ns'], row['finished_ns'])
        c.require(type(row['elapsed_ns']) is int and row['elapsed_ns'] == row['finished_ns']-row['started_ns'] and
            row['elapsed_ns'] >= 0 and type(row['gzip_hash_elapsed_ns']) is int and row['gzip_hash_elapsed_ns'] >= 0,
            'codec_saved_clocks')
        c.require(candidate.single.exact_tree(mock.semantic_record(data['record']),
            mock.semantic_record(inputs[declared['key']])), 'codec_all_complete_fields_changed')
        samples.append({**declared, 'elapsed_ms': row['elapsed_ns']/1e6,
                        'gzip_and_hash_ms': row['gzip_hash_elapsed_ns']/1e6, 'raw': row['raw']})
    values = {arm: [row['elapsed_ms'] for row in samples if row['arm'] == arm] for arm in ('A', 'B')}
    per_root = {key: {arm: statistics.median([row['elapsed_ms'] for row in samples
                if row['key'] == key and row['arm'] == arm]) for arm in ('A', 'B')} for key in inputs}
    return {'status': 'passed_exact_complete_gate002_saved18_ABBA72', 'samples': samples,
        'summary_ms': {arm: {'count': len(items), 'min': min(items), 'median': statistics.median(items),
                            'max': max(items), 'sum': sum(items)} for arm, items in values.items()},
        'per_root_median_ms': per_root,
        'negative_or_equal_root_medians': [key for key, result in per_root.items() if result['B'] >= result['A']],
        'native_calls': 0, 'predictor_calls': 0, 'complete_native_root_100ms_certified': False,
        'scope': 'Complete data-only root evidence construction. Historic physical/observation events are fixed input, not re-executed.'}


def verify_saved(output, expected):
    plan = verify_pins(output, expected)
    return verify_outputs(output, plan, load_inputs(plan))


def worker(output, expected):
    plan = verify_pins(output, expected)
    loaded_entry = c.check_loaded_sources(plan)
    setup_start = time.perf_counter_ns()
    functions = {arm: bindings(arm) for arm in ('A', 'B')}
    inputs = load_inputs(plan)
    fingerprints = {key: _fixture_hash(record) for key, record in inputs.items()}
    setup_end = time.perf_counter_ns()
    ledger = c.read(output/'ledger.json')
    try:
        for index, row in enumerate(ledger):
            declared = plan['row_order'][index]
            row['status'] = 'unknown_in_progress'; c.write(output/'ledger.json', ledger)
            method, publish = functions[row['arm']]
            start = time.perf_counter_ns()
            root = root_from_fixture(inputs[row['key']], method); holder = []
            result = publish(root, holder)
            c.require(len(holder) == 1 and holder[0] is result, 'codec_original_append_identity')
            end = time.perf_counter_ns()
            mock.current_clock_bounds(result, start, end)
            row.update(started_ns=start, finished_ns=end, elapsed_ns=end-start)
            export_start = time.perf_counter_ns()
            path = output/'raw'/f'{index:03d}.json.gz'; path.parent.mkdir(exist_ok=True)
            with gzip.open(path, 'wt', encoding='utf8', compresslevel=1) as stream:
                json.dump({'declaration': declared, 'record': result}, stream, ensure_ascii=False, allow_nan=False)
            row.update(status='saved', raw=c.reference(path))
            row['gzip_hash_elapsed_ns'] = time.perf_counter_ns()-export_start
            c.write(output/'ledger.json', ledger)
            del root, holder, result
        c.require(fingerprints == {key: _fixture_hash(value) for key, value in inputs.items()}, 'codec_fixture_mutated')
        report = verify_outputs(output, plan, inputs)
        report['fixture_load_and_binding_setup_ms'] = (setup_end-setup_start)/1e6
        c.write(output/'report.json', report)
        verify_pins(output, expected)
        loaded_exit = c.check_loaded_sources(plan)
        c.write(output/'receipt.json', {'status': 'completed_fixed_mock_ABBA', 'plan_sha256': expected,
            'source_changed': [], 'report': c.reference(output/'report.json'),
            'loaded_project_sources_entry': loaded_entry, 'loaded_project_sources_exit': loaded_exit,
            'native_calls': 0, 'predictor_calls': 0})
    except BaseException:
        c.write(output/'failure.json', {'status': 'failed_or_unknown_mock', 'error': traceback.format_exc()})
        c.write(output/'ledger.json', ledger)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--pure-receipt', type=Path)
    parser.add_argument('--execute', action='store_true'); parser.add_argument('--worker', action='store_true')
    parser.add_argument('--plan-sha256'); args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output, args.pure_receipt.resolve()); return 0
    if args.worker:
        if sys.stdin.readline() != args.plan_sha256+'\n': raise ValueError('codec_mock_job_admission')
        worker(output, args.plan_sha256); return 0
    if not args.execute: raise ValueError('codec_explicit_action_required')
    verify_pins(output, args.plan_sha256)
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': args.plan_sha256, 'shared_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', __package__+'.measure_complete_root_evidence_codec', '--worker',
               '--output', str(output), '--plan-sha256', args.plan_sha256]
    remaining = LIMIT-(time.monotonic()-BOOT)
    if remaining <= 0: raise TimeoutError('codec_budget_before_worker')
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded_windows_job.run(command, timeout=remaining, admission=args.plan_sha256,
                                         stdout=out, stderr=err, cwd=c.ROOT)
    c.write(output/'bounded_execution.json', {'process': process, 'command': command,
        'post_import_before_final_export_seconds': time.monotonic()-BOOT,
        'report': c.reference(output/'report.json') if (output/'report.json').is_file() else None,
        'external_launch_through_exit_clock_required': True, 'native_calls': 0, 'predictor_calls': 0})
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 else 1


if __name__ == '__main__': raise SystemExit(main())
