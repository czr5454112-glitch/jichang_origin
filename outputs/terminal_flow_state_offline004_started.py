"""Record the closed offline003 failure and separately registered recovery004."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = root/'outputs/experiments/g31_ics_terminal_flow_20261021'
state_path = root/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state = json.loads(state_path.read_text(encoding='utf8'))
active = state['active_experiment']
assert active['offline_audit003']['status'] == 'started_pending_completion'
active['offline_audit003'].update(status='failed_closed_before_science_output',
    error='frozen TRAIN block validator resolved runtime calibration below frozen code root',
    actual_runner_seconds=85.730185,
    closure_review='outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_failure_closure_review_005_003.json')
spec = data/'offline_budget_spec_005_ready_004.json'
active['offline_audit004'] = dict(status='started_pending_completion', tasks=11, native_starts=0,
    ready_spec=spec.relative_to(root).as_posix(), ready_spec_sha256=hashlib.sha256(spec.read_bytes()).hexdigest(),
    output='outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_execution_005_004',
    path_binding_repair_only=True, task_caps_unchanged=True, pure_tests_passed=26,
    actual_TRAIN_metadata_preflight_passed=True)
state['current_stage'] += (' Offline attempt003 failed before science output due to a frozen-code/data path '
    'binding; its tree and original ledger closed. Reviewed path-only recovery004 started with unchanged caps '
    'after 26 pure tests and real TRAIN metadata preflight; no native rerun.')
state_path.write_bytes((json.dumps(state, ensure_ascii=False, indent=2)+'\n').replace('\n','\r\n').encode('utf8'))
print('offline003 failure retained; offline004 started; no promotion')
