"""Small saved-report readback only; no raw decode, imported policy, or rerun."""
from pathlib import Path
import hashlib
import json
import statistics
import time

START = time.perf_counter_ns()
HERE = Path(__file__).resolve().parent
OUT = HERE / 'single_owned_C18_prepare_002'

def read(path):
    return json.loads(path.read_bytes())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    return {'path': str(path), 'sha256': digest(path)}

def stats(values):
    return {'count': len(values), 'min': min(values) if values else None,
            'median': statistics.median(values) if values else None,
            'max': max(values) if values else None, 'sum': sum(values)}

def pairs_summary(report):
    pairs = {k: v for k, v in report['pairs'].items() if k.startswith('normal/')}
    assert len(pairs) == 6
    improved, equal, unknown = [], [], []
    for key, value in pairs.items():
        if value['all_five_strict_nonregression'] is not True:
            unknown.append(key)
        elif any(delta < 0 for delta in value['per_job_delta'].values()):
            improved.append(key)
        else:
            assert all(delta == 0 for delta in value['per_job_delta'].values())
            equal.append(key)
    return {'count': 6, 'all_five_nonregression': not unknown,
            'improved': improved, 'equal': equal, 'unknown_or_unprotected': unknown,
            'pairs': pairs}

plan = read(OUT / 'campaign.json')
verification = read(OUT / 'verification.json')
receipt = read(OUT / 'receipt.json')
external = read(OUT / 'actual_external_application_wall.json')
inner = read(OUT / 'external_launch_receipt.json')
c_lifetime = read(OUT / 'C_provider_lifetime.json')
rpc = read(OUT / 'predictor_lifetime.json')
ledger = read(OUT / 'branch_ledger.json')
for name, expected in external['artifacts'].items():
    assert digest(OUT / name) == expected, name
assert digest(OUT / 'verification.json') == receipt['verification']['sha256']
assert digest(OUT / 'campaign.json') == external['campaign_sha256'] == receipt['campaign_sha256']
assert receipt['status'] == 'completed_finite_request_cohort'
assert verification['status'] == 'passed_saved_with_complete_unknown_denominator'
assert external['status'] == 'completed_original18_once'
assert external['exitcode'] == 0 and inner['process']['exitcode'] == 0
assert receipt['source_changed'] == external['source_changed'] == []
assert len(verification['rows']) == len(ledger) == receipt['branches'] == 18
assert all(row['status'] == 'raw_saved' for row in ledger.values())
assert c_lifetime['actual_entry'] == c_lifetime['actual_exit']
assert c_lifetime['files_entry'] == c_lifetime['files_exit']
assert c_lifetime['actual_direct_C_supported'] is None
assert c_lifetime['actual_fallback_count'] is None

baseline_plan = Path(plan['frozen_single_capture_campaign']['path'])
assert digest(baseline_plan) == plan['frozen_single_capture_campaign']['sha256']
baseline_path = baseline_plan.parent / 'verification.json'
baseline = read(baseline_path)
assert list(verification['rows']) == list(baseline['rows'])
rows = []
for key, value in verification['rows'].items():
    old = baseline['rows'][key]
    root = value['root']
    actual_next = value['business'].get('initial_actual_next')
    previous_next = old['business'].get('initial_actual_next')
    same_initial_edge = actual_next == previous_next
    same_later = value['business'].get('actual_later_choices') == old['business'].get('actual_later_choices')
    rows.append({
        'key': key, 'root': root, 'reported_root': value['reported_root'],
        'endpoint_status': value['endpoint_status'], 'audit_status': value['audit_status'],
        'RPC_attempts': value['reported_root'].get('RPC_attempts'),
        'prediction_counts': value.get('prediction_counts'),
        'gate_steps': value.get('observation_gate', {}).get('steps'),
        'gate_skips': value.get('observation_gate', {}).get('skips'),
        'business_status': value['business']['status'],
        'business_completion': value['business'].get('completion'),
        'business_sum': value['business'].get('completion_sum'),
        'actual_initial_edge': actual_next,
        'baseline_actual_initial_edge': previous_next,
        'same_recorded_initial_edge_and_later_choices': same_initial_edge and same_later,
        'baseline_reported_root_status': old['reported_root']['status'],
        'baseline_warm_ms': old['root']['warm_ms'],
        'descriptive_warm_delta_ms': root['warm_ms'] - old['root']['warm_ms'],
        'raw_reference_not_reread': ledger[key]['raw'],
    })
closed = [row['root']['warm_ms'] for row in rows if row['root']['closed']]
all_warm = [row['root']['warm_ms'] for row in rows]
unknown = [row['key'] for row in rows if not row['root']['closed']]
assert len(closed) == verification['closed_roots'] == 16
assert len(unknown) == verification['open_or_unknown_roots'] == 2
assert sum(row['root']['observed_within_100ms'] for row in rows) == 0

rpc_rows = []
for row in rpc['ledger']:
    rpc_rows.append({'sequence': row['sequence'], 'request_id': row['request_id'],
                     'caller_ms': row['caller_elapsed_ns'] / 1e6,
                     'worker_compute_ms': row['response']['compute_wall_ns'] / 1e6,
                     'caller_bookkeeping_ms': row['caller_bookkeeping_ns'] / 1e6})
assert len(rpc_rows) == verification['predictor_requests'] == 8

critical = ['campaign.json', 'root_review_001.json', 'source_preparation.json',
            'actual_external_application_wall.json', 'external_launch_receipt.json',
            'receipt.json', 'verification.json', 'branch_ledger.json',
            'C_provider_lifetime.json', 'predictor_lifetime.json', 'run_acceptance.json',
            'stdout.log', 'stderr.log']
report = {
    'schema': 'g31.single_owned_C18.saved_compact_summary.v1',
    'status': 'producer_reports_read_back_and_cross_bound',
    'independent_full_saved_audit': False,
    'scope': 'Producer-author small JSON readback and arithmetic only. Existing full saved verification is bound, not rerun; no raw decode, native, predictor, C load, or performance rerun.',
    'actual_process': {'exitcode': 0,
        'python_launch_to_exit_seconds': external['python_launch_to_exit_seconds'],
        'wrapper_through_preexport_seconds': external['wrapper_through_preexport_seconds'],
        'owned_process': inner['process'], 'automatic_retries': 0},
    'counts': {'all_branches': 18, 'closed': 16, 'unknown': 2, 'observed_within_100ms': 0,
               'invalid_or_error': len(verification['invalid_or_error_branches']),
               'gate_steps': sum(row['gate_steps'] or 0 for row in rows),
               'gate_skips': sum(row['gate_skips'] or 0 for row in rows)},
    'closed_warm_ms': stats(closed), 'all_warm_ms': stats(all_warm), 'unknown_keys': unknown,
    'normal_pairs': pairs_summary(verification),
    'rows': rows,
    'RPC': {'protocol_closed': verification['predictor_protocol_closed'],
            'startup_ms': verification['predictor_startup_ms'],
            'close_cleanup_ms': verification['predictor_close_with_cleanup_ms'],
            'prediction_counts': verification['prediction_counts'],
            'prediction_counts_complete': verification['prediction_counts_complete'],
            'rows': rpc_rows, 'caller_ms': stats([r['caller_ms'] for r in rpc_rows]),
            'worker_compute_ms': stats([r['worker_compute_ms'] for r in rpc_rows])},
    'C_provider': {**verification['C_provider_lifetime'],
                   'actual_identity_entry_equals_exit': True,
                   'files_entry_equals_exit': True,
                   'file_spec_loader_path': c_lifetime['actual_entry']['file'],
                   'binary_sha256': c_lifetime['actual_entry']['binary_sha256'],
                   'DLLs': c_lifetime['actual_entry']['actual_DLLs'],
                   'toolchain_count_each_pass': 6124, 'full_file_passes': 3,
                   'load_and_binding_within_setup_ms': (c_lifetime['setup_finished_ns'] - c_lifetime['load_started_ns']) / 1e6},
    'source': {'producer_changed': receipt['source_changed'],
               'outer_changed': external['source_changed'], 'campaign_sources': len(plan['source_sha256']),
               'native_archived_sources': len(plan['compiled_source_archive_sha256']),
               'loaded_entry_count': len(receipt['loaded_project_sources_entry']),
               'loaded_exit_count': len(receipt['loaded_project_sources_exit'])},
    'baseline_descriptive_only': {'verification': ref(baseline_path),
        'campaign': ref(baseline_plan), 'normal_pairs': pairs_summary(baseline),
        'changed_recorded_initial_edge': [r['key'] for r in rows if r['actual_initial_edge'] != r['baseline_actual_initial_edge']],
        'same_recorded_initial_edge_and_later_choices_count': sum(r['same_recorded_initial_edge_and_later_choices'] for r in rows),
        'limitation': 'Different serial campaigns, no randomized ABBA or controlled same-wall decision schedule. The same recorded initial edge/later choices do not prove every timing, admission, or execution path identical. Deadline-dependent selection changes are retained. No causal full-request speedup or method-selection improvement is inferred.'},
    'complete_100ms_certified': False,
    'artifacts': {name: ref(OUT / name) for name in critical},
    'reader_source': ref(Path(__file__).resolve()),
    'readback_before_export_ms': (time.perf_counter_ns() - START) / 1e6,
}
destination = OUT / 'actual_compact_summary_001.json'
with destination.open('x', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
print(json.dumps({'report': ref(destination), 'counts': report['counts'],
                  'closed_warm_ms': report['closed_warm_ms'],
                  'baseline_changed': report['baseline_descriptive_only']['changed_recorded_initial_edge'],
                  'RPC_caller_ms': report['RPC']['caller_ms'],
                  'RPC_worker_ms': report['RPC']['worker_compute_ms']}, ensure_ascii=False))
