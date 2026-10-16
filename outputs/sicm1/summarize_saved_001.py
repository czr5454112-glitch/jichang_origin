"""Saved scalar summary only: no project import, raw gzip, C or model call."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

START = time.perf_counter()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/single_owned_C18_prepare_002'


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def check(value, label):
    if not value:
        raise ValueError('saved_summary:' + label)


def dist(values):
    check(bool(values) and all(type(v) in (int, float) and math.isfinite(v) for v in values), 'finite_values')
    return {'count': len(values), 'min_ms': min(values), 'median_ms': statistics.median(values),
        'max_ms': max(values), 'sum_ms': sum(values)}


plan = read(HERE/'campaign.json')
verification = read(HERE/'verification.json')
receipt = read(HERE/'receipt.json')
outer = read(HERE/'actual_external_application_wall.json')
base = read(BASE/'verification.json')
check(outer['status'] == 'completed_original18_once' and outer['exitcode'] == outer['wrapper_exitcode'] == 0,
    'outer_status')
check(outer['source_changed'] == receipt['source_changed'] == [], 'source_changes')
check(receipt['status'] == 'completed_finite_request_cohort' and receipt['branches'] == 18, 'receipt')
check(ref(HERE/'verification.json') == receipt['verification'], 'verification_binding')
check(ref(HERE/'campaign.json')['sha256'] == receipt['campaign_sha256'] == outer['campaign_sha256'], 'plan_binding')
check(verification['status'] == 'passed_saved_with_complete_unknown_denominator', 'full_saved_status')
check(set(verification['rows']) == set(plan['row_order']) and len(plan['row_order']) == 18, 'all18')
check(not verification['invalid_or_error_branches'] and not verification['unverified_RPC_branches'], 'errors_or_RPC_unknown')
for name, artifact in outer['artifacts'].items():
    check(ref(HERE/name) == artifact, 'outer_artifact:' + name)
static = verification['static_inventory_lifetime']
check(static['status'] == 'passed_constructor_sidecar_bound_to_original_saved_checks'
    and static['constructor_rows'] == 18 and set(static['rows']) == set(plan['row_order'])
    and not static['missing_before_constructor_failures'] and not static['unverified_missing_raw_constructor_rows'],
    'all_constructor_rows')

rows = []
for key in plan['row_order']:
    value, prior = verification['rows'][key], base['rows'][key]
    root, constructor = value['root'], static['rows'][key]
    check(type(root['closed']) is bool and type(root['observed_within_100ms']) is bool, 'root_flags')
    check(root['observed_within_100ms'] == (root['closed'] and root['warm_ms'] <= 100), '100ms_count')
    check(constructor['status'] == 'constructor_returned' and 0 <= constructor['wall_ms'] <= root['warm_ms'],
        'constructor_nested')
    rows.append({'key': key, 'closed': root['closed'], 'root_status': root['status'],
        'reported_status': value['reported_root']['status'], 'warm_ms': root['warm_ms'],
        'observed_within_100ms': root['observed_within_100ms'], 'constructor_nested_wall_ms': constructor['wall_ms'],
        'root_less_constructor_ms_diagnostic_only': root['warm_ms']-constructor['wall_ms'],
        'initial_actual_next': value['business']['initial_actual_next'],
        'business_status': value['business']['status'], 'audit_status': value['audit_status'],
        'baseline_warm_ms': prior['root']['warm_ms'], 'baseline_closed': prior['root']['closed'],
        'baseline_initial_actual_next': prior['business']['initial_actual_next'],
        'same_initial_actual_next_as_prior_run': value['business']['initial_actual_next'] == prior['business']['initial_actual_next'],
        'same_later_choice_records_as_prior_run': value['business']['actual_later_choices'] == prior['business']['actual_later_choices']})

normal_pairs = {}
jobs = ('blocker', 'loaded', 'receiver', 'reuse1', 'reuse2')
for key, pair in verification['pairs'].items():
    if not key.startswith('normal/'):
        continue
    default = verification['rows'][key.rsplit('/', 1)[0]+'/fixed_default']
    candidate = verification['rows'][key]
    check(default['root']['closed'] and candidate['root']['closed'] and pair['request_pair_completed'], 'normal_closed')
    before, after = default['business']['completion'], candidate['business']['completion']
    check(set(before) == set(after) == set(jobs), 'all_five_jobs')
    deltas = {job: after[job]-before[job] for job in jobs}
    nonregression = all(delta <= 0 for delta in deltas.values())
    check(pair['per_job_delta'] == deltas and pair['all_five_strict_nonregression'] == nonregression, 'pair_recompute')
    normal_pairs[key] = {'all_five_nonregression': nonregression,
        'strict_improvement': nonregression and any(delta < 0 for delta in deltas.values()),
        'equal_all_five': all(delta == 0 for delta in deltas.values()), 'per_job_delta': deltas}
check(len(normal_pairs) == 6 and all(p['all_five_nonregression'] for p in normal_pairs.values()), 'normal6')
closed = [row for row in rows if row['closed']]
same = [row for row in rows if row['closed'] and row['baseline_closed']
    and row['same_initial_actual_next_as_prior_run'] and row['same_later_choice_records_as_prior_run']]
check(len(closed) == verification['closed_roots'] == 16 and verification['open_or_unknown_roots'] == 2, 'denominator')
report = {
    'schema': 'g31.static_inventory_campaign.saved_scalar_summary.v1',
    'status': 'saved_producer_scalar_bindings_and_arithmetic_checked',
    'scope': 'Producer-authored saved scalar summary, not a second full raw/endpoint/policy verifier. Only existing JSON summaries and named evidence hashes were read; no raw gzip, source tree,6124 toolchain, model, native or C load.',
    'sources': {name: ref(HERE/name) for name in ('campaign.json', 'receipt.json', 'verification.json',
        'actual_external_application_wall.json', 'external_launch_receipt.json', 'branch_ledger.json',
        'C_provider_lifetime.json', 'static_inventory_lifetime.json', 'predictor_lifetime.json',
        'run_acceptance.json', 'root_prelaunch_review_001.json')},
    'baseline_verification': ref(BASE/'verification.json'), 'summary_source': ref(__file__),
    'external_python_seconds': outer['python_launch_to_exit_seconds'],
    'external_typed_ticks': outer['elapsed_ticks'], 'external_tick_frequency': outer['stopwatch_frequency'],
    'rows': rows, 'roots': {'total': 18, 'closed': 16, 'unknown': 2,
        'observed_within_100ms': sum(row['observed_within_100ms'] for row in rows),
        'complete_100ms_certified': False, 'closed_warm': dist([row['warm_ms'] for row in closed]),
        'all18_warm': dist([row['warm_ms'] for row in rows])},
    'constructor': {'all18_nested_wall': dist([row['constructor_nested_wall_ms'] for row in rows]),
        'cold_binding_ms': static['cold_binding_ms'], 'cold_binding_nested_in_C_setup': True,
        'not_CPU_or_inventory_only': True, 'not_additive_to_root_wall': True,
        'per_root_cycle_cleanup_certified': False,
        'all16_closed_root_minus_constructor_still_over100': all(row['root_less_constructor_ms_diagnostic_only'] > 100 for row in closed)},
    'normal6': {'all_five_protected': 6,
        'strict_improvement': sum(p['strict_improvement'] for p in normal_pairs.values()),
        'equal_all_five': sum(p['equal_all_five'] for p in normal_pairs.values()), 'pairs': normal_pairs},
    'RPC': {'requests': verification['predictor_requests'], 'counts': verification['prediction_counts'],
        'counts_complete': verification['prediction_counts_complete'],
        'startup_ms': verification['predictor_startup_ms'],
        'close_with_cleanup_ms': verification['predictor_close_with_cleanup_ms']},
    'C_provider': verification['C_provider_lifetime'],
    'source_changed': receipt['source_changed'],
    'baseline_comparison': {'scope': 'Separate runs, not ABBA or causal performance attribution; changed route choices and wall-sensitive60ms fallback remain explicit. Matching executed initial/later choice records alone does not establish equal all events/scheduler/GC/system state.',
        'baseline_closed_warm': dist([r['root']['warm_ms'] for r in base['rows'].values() if r['root']['closed']]),
        'changed_initial_actual_next': [row['key'] for row in rows if not row['same_initial_actual_next_as_prior_run']],
        'same_executed_choice_closed_keys': [row['key'] for row in same],
        'same_choice_baseline_warm': dist([row['baseline_warm_ms'] for row in same]),
        'same_choice_current_warm': dist([row['warm_ms'] for row in same])},
    'readback_before_export_seconds': time.perf_counter()-START,
    'new_predictions': 0, 'new_native_calls': 0, 'new_C_loads': 0, 'raw_reads': 0,
}
with (HERE/'actual_scalar_summary_001.json').open('x', encoding='utf8') as stream:
    stream.write(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
print(json.dumps({key: report[key] for key in ('roots', 'constructor', 'normal6', 'RPC', 'C_provider')}, indent=2))
