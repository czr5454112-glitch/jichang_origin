"""Independent saved-only six-passive readback; no model or snapshot execution."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job as bounded

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
PRODUCER = OUT/'live_phase_b_pause_prepare_001'
MODULE = 'scripts.experiments.g31_ics_circulation.review_live_phase_b_pause_saved'
LIMIT = 120.0
ORDER = ('mechanism/vector_00', 'mechanism/vector_25', 'no_overlap/vector_00',
         'no_overlap/vector_25', 'insufficient_advance/vector_00', 'insufficient_advance/vector_17')
FIXED = {
    'plan.json': 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb',
    'receipt.json': '693628a6dacec21a16f5b312f7443a1c4963970445495449637437219afb3710',
    'rows.json': 'a5d50fb71f7b1435f9140caca97e106c2ca89109049e5175d1d666ffd55f8f20',
    'external_application_wall.json': '8bfc10df9f64768570ff1ae8fbb9e5df528aba5bc7b953d097bfc8fcb9192013',
}


def require(ok, reason):
    if not ok: raise ValueError('passive_saved_review:'+reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def read(path): return json.loads(Path(path).read_bytes())
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')
def ref(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        return list(a) == list(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list: return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is float: return math.isfinite(a) and math.isfinite(b) and a.hex() == b.hex()
    return type(a) in (str, int, bool, type(None)) and a == b


def finite(value): return type(value) in (int, float) and math.isfinite(value) and value >= 0


def metadata():
    for name, digest in FIXED.items(): require(sha(PRODUCER/name) == digest, 'fixed:'+name)
    plan, rows, receipt = (read(PRODUCER/name) for name in ('plan.json', 'rows.json', 'receipt.json'))
    require(tuple(plan['rows']) == ORDER and tuple(rows) == ORDER and plan['order'] == list(ORDER), 'fixed_six')
    require(len(plan['source_sha256']) == 105 and set(plan['source_sha256']) == set(plan['source_archive']), '105_source_domain')
    require(receipt['status'] == 'exact_six_passive_conformance' and receipt['exact_rows'] == 6
            and receipt['unknown_rows'] == 0 and receipt['hook_count'] == 14 and receipt['model_calls'] == 6
            and receipt['native_calls'] == 0 and receipt['source_changed'] == [], 'producer_receipt')
    require(plan['maximum_model_calls'] == 6 and plan['expected_hook_points'] == 14
            and plan['hard_application_seconds'] == 120, 'producer_bound')
    return plan, rows, receipt


def prepare(output):
    # Only metadata and source bytes are read here. No gzip/input/point payloads.
    plan, rows, receipt = metadata()
    output.mkdir(exist_ok=False)
    references = {str(PRODUCER/name): digest for name, digest in FIXED.items()}
    for name in ('entry_pins.json', 'exit_pins.json', 'loaded_sources.json', 'exit_loaded_sources.json',
                 'bounded_execution.json', 'stdout.log', 'stderr.log', 'execution_claim.json'):
        references[str(PRODUCER/name)] = sha(PRODUCER/name)
    source = dict(plan['source_sha256'])
    source[str(Path(__file__).resolve())] = sha(__file__)
    archives = {}
    for path, digest in source.items():
        data = Path(path).read_bytes(); require(hashlib.sha256(data).hexdigest() == digest, 'source_prepare')
        if path in plan['source_archive']:
            require(sha(PRODUCER/plan['source_archive'][path]) == digest, 'producer_archive_prepare')
        relative = Path('source')/Path(path).relative_to(ROOT)
        (output/relative).parent.mkdir(parents=True, exist_ok=True); (output/relative).write_bytes(data)
        archives[path] = str(relative)
    data_pins = dict(plan['evidence_sha256'])
    for key in ORDER:
        for name in ('input', 'prediction', 'point_audit', 'comparison_only_saved_prediction', 'comparison_only_actual_raw'):
            item = rows[key][name]
            if item['path'] in data_pins: require(data_pins[item['path']] == item['sha256'], 'conflicting_data_pin')
            data_pins[item['path']] = item['sha256']
    value = {'schema': 'g31.passive_six.independent_saved_plan.v1', 'producer': str(PRODUCER),
        'producer_plan_sha256': FIXED['plan.json'], 'order': list(ORDER), 'source_sha256': source,
        'source_archive': archives, 'references': references, 'data_sha256': data_pins,
        'python': ref(sys.executable), 'hard_application_seconds': LIMIT,
        'producer_source_count': 105, 'source_count': len(source), 'new_model_calls': 0, 'new_native_calls': 0,
        'new_snapshot_or_alias_tests': 0, 'input_payloads_opened_during_prepare': 0,
        'scope': ['Six complete prediction decompressed byte comparisons against frozen lazy results.',
            'Fourteen saved point metadata/chronology checks; graph objects were NOT saved and alias/copy claims are producer-only.',
            'Rebuild initial and later supplied-data contexts using original guards; independently compare complete support inventories.',
            'All105 producer live/archive/entry/exit/import identities and all references/data are checked inside120 at entry and exit.',
            'No model, native, PointRecorder, snapshot clone, restart or performance execution. No native authority or100ms claim.'],
        'budget_basis': {'producer_whole_seconds': 12.4314135, 'reference_only_not_runtime_prediction': True,
            'maximum_seconds': LIMIT, 'all_imports_hashes_decode_guards_compare_exports_exit_included': True,
            'external_whole_python_wall_required': True}}
    write(output/'plan.json', value)
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--plan-sha256', sha(output/'plan.json')]
    write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': ref(output/'plan.json'),
        'execute_command': command, 'source_count': len(source), 'new_model_calls': 0, 'new_native_calls': 0,
        'input_payloads_opened_during_prepare': 0, 'preparation_seconds': time.monotonic()-BOOT})
    print(json.dumps(read(output/'ready.json')))


def pins(output, plan):
    original, _, _ = metadata()
    require(plan['producer_plan_sha256'] == FIXED['plan.json'] and plan['order'] == list(ORDER)
            and plan['hard_application_seconds'] == LIMIT and plan['producer'] == str(PRODUCER), 'audit_plan_scope')
    require(set(plan['source_sha256']) == set(original['source_sha256']) | {str(Path(__file__).resolve())}, 'audit_source_domain')
    all_pins = {**plan['references'], **plan['data_sha256'], **plan['source_sha256']}
    for path, digest in plan['source_sha256'].items():
        require(digest == (original['source_sha256'].get(path) or sha(__file__)), 'source_crosslink')
        all_pins[str(output/plan['source_archive'][path])] = digest
    for path, digest in original['source_sha256'].items(): all_pins[str(PRODUCER/original['source_archive'][path])] = digest
    require(plan['python'] == ref(sys.executable), 'python_identity')
    actual = {path: sha(path) for path in all_pins}
    require(actual == all_pins, 'identity_changed')
    return actual


def producer_identity(plan):
    original, rows, receipt = metadata()
    expected = {**original['source_sha256'], **original['evidence_sha256']}
    expected.update({str(PRODUCER/original['source_archive'][p]): d for p, d in original['source_sha256'].items()})
    for name in ('plan', 'rows', 'entry_pins', 'exit_pins', 'loaded_sources', 'exit_loaded_sources'):
        require(receipt[name] == ref(PRODUCER/({'plan': 'plan', 'rows': 'rows'}.get(name, name)+'.json')), 'receipt_ref:'+name)
    require(read(PRODUCER/'entry_pins.json') == expected == read(PRODUCER/'exit_pins.json'), 'producer_entry_exit')
    loaded = read(PRODUCER/'loaded_sources.json'); end = read(PRODUCER/'exit_loaded_sources.json')
    require(loaded and loaded == end and all(original['source_sha256'].get(p) == d for p, d in loaded.items()), 'producer_loaded_closure')
    for suffix in ('validate_live_phase_b_pause.py', 'public_live_obligation_phase_b_pause.py',
                   'live_obligation_phase_b_support.py', 'live_obligation_delivered_context.py'):
        require(any(Path(p).name == suffix for p in loaded), 'required_producer_import:'+suffix)
    outer = read(PRODUCER/'external_application_wall.json'); process = read(PRODUCER/'bounded_execution.json')
    require(outer['status'] == 'application_exited_zero' and outer['exit_code'] == 0 and outer['error'] is None
            and outer['evidence_unchanged'] is True and outer['plan_sha256'] == FIXED['plan.json']
            and outer['python_sha256'] == plan['python']['sha256'] and outer['shared_owned_seconds'] == LIMIT
            and outer['whole_python_within_120_seconds'] is True and outer['whole_python_application_seconds'] == 12.4314135,
            'external_exit')
    command = [sys.executable, '-m', 'scripts.experiments.g31_ics_circulation.validate_live_phase_b_pause',
               '--worker', '--output', str(PRODUCER), '--expected-plan', FIXED['plan.json']]
    p = process['process']
    require(process['status'] == 'bounded_worker_completed' and process['command'] == command
            and process['plan_sha256'] == FIXED['plan.json'] and process['worker_receipt'] == ref(PRODUCER/'receipt.json')
            and p['status'] == 'exited' and p['exitcode'] == 0 and p['windows_job_kill_on_close'] is True
            and p['child_released_only_after_job_assignment'] is True, 'owned_producer')
    require(all(finite(v) for v in (receipt['worker_seconds'], p['wall_seconds'], p['hard_timeout_seconds'],
        process['parent_before_worker_seconds'], process['application_seconds_before_final_receipt'])), 'producer_clocks')
    require(receipt['worker_seconds'] <= p['wall_seconds'] <= process['application_seconds_before_final_receipt']
            <= outer['whole_python_application_seconds'] <= LIMIT and p['hard_timeout_seconds'] <= LIMIT, 'clock_envelopes')
    for name, count in (('live_phase_b_pause_pure_001', 16), ('live_phase_b_pause_driver_pure_001', 10)):
        suites = ET.parse(OUT/name/'tests.xml').getroot().findall('testsuite')
        require(len(suites) == 1 and int(suites[0].get('tests')) == count and
            all(int(suites[0].get(k)) == 0 for k in ('failures', 'errors', 'skipped')), 'saved_pure_xml')
    return original, rows, {'source_count': 105, 'loaded_count': len(loaded), 'whole_seconds': outer['whole_python_application_seconds'],
        'original_model_calls': 6, 'original_points': 14, 'original_native_calls': 0}


def actual_imports(plan):
    loaded = {}
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(ROOT):
            path = Path(path).resolve()
            require(path.suffix == '.py' and plan['source_sha256'].get(str(path)) == sha(path), 'unbound_import:'+name)
            loaded[name] = {'path': str(path), 'sha256': sha(path)}
    require(not any('czr005_circulation' in n or '_g31_complete_tree_normalizer' in n for n in sys.modules), 'forbidden_C_import')
    return loaded


def check_point_metadata(points, expected):
    require(type(points) is list and len(points) == len(expected), 'point_count')
    previous = -1.0
    for point, collection in zip(points, expected, strict=True):
        for key in ('owner', 'at', 'phase', 'recollection_index'):
            require(exact(point[key], collection[key]), 'point_chronology:'+key)
        require(finite(point['at']) and point['at'] >= previous, 'point_time_order'); previous = point['at']
        require(point['schema'] == 'g31.live_obligation.passive_decision_point.v1' and
            point['program_counter'] == 'decide_after_collect_before_record_and_action' and
            point['information_status'] == collection['information_status'] and
            point['retry_status'] == collection['retry_admission']['status'], 'point_metadata')
        for key in ('resumable', 'native_authority', 'coverage_certified', 'python_stack_and_run_local_counter_saved'):
            require(point[key] is False, 'point_limit:'+key)
        for key in ('pending_is_owner_pending', 'world_engine_backref', 'recorder_detached',
                    'complete_graph_copy_equal', 'clone_mutation_isolated'):
            require(point[key] is True, 'producer_graph_attestation:'+key)
        digest = point['graph_sha256']
        require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'graph_digest_shape')
        for key in ('graph_encoded_bytes', 'heap_events', 'event_sequence', 'client_row_count'):
            require(type(point[key]) is int and point[key] >= (1 if key == 'graph_encoded_bytes' else 0), 'graph_count:'+key)


def audit_row(key, row, planned, context, support):
    require(row['status'] == 'exact_passive_conformance' and row['whole_prediction_bytes_exact'] is True, 'row_status')
    for field in planned: require(exact(row[field], planned[field]) or field == 'status', 'row_plan:'+field)
    require(finite(row['model_and_capture_seconds']), 'model_clock')
    encoded = gzip.decompress(Path(row['prediction']['path']).read_bytes())
    target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
    require(encoded == target, 'whole_prediction_bytes')
    prediction = json.loads(encoded)
    require(prediction['status'] == 'conditional_prediction' and
        exact(prediction['projected_collections'], planned['expected_collections']), 'saved_prediction_collections')
    detail = read(row['point_audit']['path']); points = detail['points']
    check_point_metadata(points, prediction['projected_collections'])
    require(row['returned_hook_count'] == row['hook_count'] == len(points), 'reported_hook_count')
    require(all(detail[k] is False for k in ('model_point_relation_established', 'resumable', 'native_authority')), 'detail_limits')
    raw = json.loads(gzip.decompress(Path(row['comparison_only_actual_raw']['path']).read_bytes()))
    public = read(row['input']['path'])
    require(list(public) == ['initial_owners', 'action'] and list(public['initial_owners']) == ['A', 'B']
            and exact(public['action'], row['action']), 'public_input_shape')
    facts = {}
    for owner in ('A', 'B'):
        endpoints = raw['initial_owners'][owner]['raw_endpoints']; request_id = endpoints['command']['request_id']
        matches = [c for c in raw['calls'] if c['at'] <= .11 and c['request']['owner_id'] == owner
                   and c['request']['request_id'] == request_id and c['retry'] is False]
        require(len(matches) == 1, 'initial_immutable_request')
        expected = {**copy.deepcopy(endpoints), 'own_request': copy.deepcopy(matches[0]['request'])}
        require(exact(public['initial_owners'][owner], expected), 'only_initial_owner_evidence')
        supplied = context.initial_context(**expected)
        require(type(supplied) is context.SuppliedContext, 'initial_original_guards')
        facts[owner] = context.initial_projection_bundle(supplied)
    require(all(context.encoded({'value': facts['A'][k]}) == context.encoded({'value': facts['B'][k]})
        for k in ('jobs', 'trays', 'contract', 'now')), 'independent_initial_facts')
    inventories = []
    for owner in ('A', 'B'):
        for attempt in raw['collection_attempts'][owner]:
            p = attempt['collection']; endpoints = attempt['information']['raw_endpoints']
            supplied = context.later_context(**endpoints, retained=raw['retained_ledgers'][owner],
                own_calls=[c for c in raw['calls'][:attempt['predecision_call_prefix_count']] if c['request']['owner_id'] == owner],
                phase=attempt['phase'], own_request_id=p['request_id'], peer_message_id=p['peer_message'],
                collection_started_at=p['at'], policy_quiet_since=p['policy_quiet_since'])
            inventory = support.inspect_supplied_context(supplied)
            inventories.append({'owner': owner, 'phase': attempt['phase'], 'at': attempt['at'],
                'recollection_index': p['recollection_index'], 'source': 'saved_actual_owner_endpoints_only',
                'model_point_relation_established': False, 'actual_delivery_capability_minted': False, 'inventory': inventory})
    require(exact(inventories, detail['independent_actual_support_inventories']), 'complete_actual_inventories')
    return {'key': key, 'whole_prediction_bytes_exact': True, 'prediction_bytes': len(encoded),
        'decompressed_sha256': hashlib.sha256(encoded).hexdigest(), 'points': len(points),
        'point_metadata_chronology_exact': True, 'initial_guard_owners': 2,
        'independent_actual_inventory_count': len(inventories),
        'inventory_status_counts': {status: sum(v['inventory']['status'] == status for v in inventories)
            for status in sorted({v['inventory']['status'] for v in inventories})},
        'original_model_and_capture_seconds': row['model_and_capture_seconds'],
        'saved_graph_claims_only': True, 'independent_alias_or_snapshot_reverified': False}


def audit(output, expected):
    require(sha(output/'plan.json') == expected, 'plan_changed'); plan = read(output/'plan.json')
    report = {'schema': 'g31.passive_six.independent_saved_review.v1', 'status': 'started', 'plan_sha256': expected,
        'rows': [], 'new_model_calls': 0, 'new_native_calls': 0, 'new_snapshot_or_alias_tests': 0,
        'native_authority': False, 'resumable': False, 'hidden_history_coverage': False, 'complete_request_100ms_claim': False,
        'limits': ['Snapshot object graphs were not saved. Their digest/alias/isolation fields are producer attestations, not independently reverified graphs.',
            'Actual inventories rerun supplied-data guards only; no model/native ID correspondence, delivery capability or restart state is minted.']}
    try:
        entry = pins(output, plan); write(output/'entry_pins.json', entry)
        original, rows, report['producer_identity'] = producer_identity(plan)
        from . import live_obligation_delivered_context as context
        from . import live_obligation_phase_b_support as support
        report['loaded_entry'] = actual_imports(plan)
        for key in ORDER:
            result = audit_row(key, rows[key], original['rows'][key], context, support)
            report['rows'].append(result)
            write(output/'progress.json', {'verified_rows': len(report['rows']), 'last': key})
        require(len(report['rows']) == 6 and sum(v['points'] for v in report['rows']) == 14, 'six_fourteen')
        report['counts'] = {'exact_rows': 6, 'unknown_rows': 0, 'point_metadata': 14,
            'initial_owner_guards': 12, 'independent_actual_inventories': sum(r['independent_actual_inventory_count'] for r in report['rows'])}
        report['status'] = 'passed_saved_six_and_fourteen_metadata_original_guards'
    except BaseException as exc:
        report.update(status='failed_or_unknown', error={'type': type(exc).__name__, 'message': str(exc)})
        (output/'exception.txt').write_text(traceback.format_exc(), encoding='utf8')
    finally:
        try:
            report['loaded_exit'] = actual_imports(plan)
            require(all(report['loaded_exit'].get(name) == value for name, value in report.get('loaded_entry', {}).items()),
                    'audit_loaded_changed')
            end = pins(output, plan); write(output/'exit_pins.json', end)
            require(entry == end, 'audit_entry_exit_changed')
        except BaseException as exc: report.update(status='failed_or_unknown', exit_error=str(exc))
        report['worker_seconds_including_imports'] = time.monotonic()-BOOT
        write(output/'report.json', report)
    return 0 if report['status'].startswith('passed_') else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--plan-sha256')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(args.admission and sys.stdin.readline() == args.admission+'\n', 'owned_admission')
        return audit(output, args.plan_sha256)
    with (output/'execution_claim').open('x'): pass
    require(sha(output/'plan.json') == args.plan_sha256, 'plan_before_dispatch')
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--plan-sha256', args.plan_sha256,
               '--worker', '--admission', uuid.uuid4().hex]
    with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
        process = bounded.run(command, timeout=LIMIT-(time.monotonic()-BOOT)-1, stdout=stdout,
            stderr=stderr, admission=command[-1], cwd=ROOT)
    record = {'process': process, 'command': command, 'plan_sha256': args.plan_sha256, 'shared_limit_seconds': LIMIT,
        'launcher_seconds_including_imports': time.monotonic()-BOOT,
        'report_sha256': sha(output/'report.json') if (output/'report.json').exists() else None,
        'external_whole_python_clock_required': True, 'new_model_calls': 0, 'new_native_calls': 0}
    write(output/'bounded_execution.json', record); print(json.dumps(record))
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 and time.monotonic()-BOOT <= LIMIT else 1


if __name__ == '__main__': raise SystemExit(main())
