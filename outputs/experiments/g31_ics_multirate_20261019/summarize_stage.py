"""Collect this stage's saved receipts; never execute native or model code."""
import hashlib
import json
from pathlib import Path

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[2]


def read(relative):
    return json.loads((STAGE / relative).read_bytes())


def reference(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


pair = read('initial_pair_001/receipt.json')
multirate = read('multirate_002/worker_report.json')
tests = read('final_validation_001/receipt.json')
transitions = read('owner_transition_001/transition_export_validation.json')
independent_initial = read('independent_initial_001/report.json')
independent_multirate = read('independent_multirate_001/audit_report.json')
assert pair['status'] == 'completed_initial_selector_campaign'
assert multirate['status'] == 'completed_multirate_late_refusal_probe'
assert all(item['status'] == 'passed' for item in (tests, transitions, independent_initial, independent_multirate))
protected = Path('C:/PROGRAMING/czr005/cpp/ics_core/runtime/bounded_local_pibt.hpp')
assert reference(protected)['sha256'] == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
pins = read('initial_pair_001/plan.json')['source_sha256']
changed = [path for path, expected in pins.items() if reference(path)['sha256'] != expected]
assert changed == [str(ROOT / 'scripts/experiments/g31_ics_circulation/foundation_multirate_probe.py')]
result = {'schema': 'g31.learning_execution_multirate_stage.v1', 'date': '2026-10-19',
    'status': 'completed_bounded_stage', 'training_performed': False, 'git_commit_or_push_performed': False,
    'initial_pair': pair['pair'], 'regression': tests,
    'multirate': {key: multirate[key] for key in ('physical_parity', 'actual_terminal_comparison',
        'poll_cost', 'worker_lifecycle_timing', 'enqueue_to_ready_observation_wall_ms', 'realtime_async',
        'new_current_admission_tested', 'on_time_admission_tested')},
    'native_progress_samples': multirate['native_progress_during_worker']['sample_count'],
    'native_progress_physical_events': multirate['native_progress_during_worker']['actual_receipt_count'],
    'current_delivery_screen': multirate['delivery']['screen'],
    'transition_export': transitions, 'source_changes_after_initial_pair': changed,
    'source_change_scope': 'P1 assessment only; P0 executed selector/dispatch/model bytes remain unchanged, all historical archives retained.',
    'protected_user_file': reference(protected),
    'feedback': [reference(path) for path in sorted((STAGE / 'feedback').glob('*.md'))],
    'evidence': [reference(STAGE / name) for name in ('initial_pair_001/receipt.json',
        'independent_initial_001/report.json', 'multirate_002/receipt.json', 'multirate_002/worker_report.json',
        'independent_multirate_001/audit_report.json', 'owner_transition_001/receipt.json',
        'owner_transition_001/transition_export_validation.json', 'final_validation_001/receipt.json')],
    'remaining': ['on-time fresh admission and feasible continuation', 'fixed-graph natural multi-scene batch',
        'multiple effective same-owner decisions', 'real flight version history and demand predictor',
        'complete R1 100ms verification', 'cross-event suffix reuse', 'airport-scale and universal protection evidence']}
with (STAGE / 'stage_summary_001.json').open('x', encoding='utf8') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(json.dumps({'status': result['status'], 'tests': tests['counts'], 'per_job_delta_s': pair['pair']['per_job_delta_s']}))
