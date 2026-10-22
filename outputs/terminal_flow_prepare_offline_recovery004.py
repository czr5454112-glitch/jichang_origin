"""Register a reviewed path-only offline repair after closed failed attempt003."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
def bind(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path, value):
    with Path(path).open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')
    return bind(path)

old_path = DATA/'offline_budget_spec_005_ready_003.json'
assert bind(old_path)['sha256'] == '25be054117a868b3b9578875d6fca4baed898f45dc8bae39a2a8ff207aa779ba'
closure_path = DATA/'offline_budget_failure_closure_review_005_003.json'
assert bind(closure_path)['sha256'] == '07cf07e7081f45dbdb0188916fa4a424f4bc7a63cd529e97f4a434635e24cef3'
spec = read(old_path)
assert len(spec['tasks']) == 11
assert all(not Path(task['output']).exists() for task in spec['tasks'])
preflight = read(DATA/'full_train_time_scale_preflight_005_002.json')
assert preflight['status'] == 'ready' and preflight['closed_full_train_runs'] == 2 and preflight['science_executed'] is False
old_producers = list(spec['producer_bindings'])
for index, ref in enumerate(old_producers):
    new = bind(ref['path'])
    if Path(ref['path']).name == 'full_train_time_scale_audit_005.py':
        assert ref['sha256'] == '959be68873f72793b3fd80abf29cab3229b31df29ea9941e1084596c50bbfffa'
        spec['producer_bindings'][index] = new
    else:
        assert new == ref
spec.pop('template')
spec['ready'] = False
spec['reason_pending'] = 'Reviewed offline runtime-data path repair; seal unchanged genuine completion and model before one fresh execution.'
for key in ('model', 'workflow_completion'):
    spec[key]['sha256'] = None
spec['recovery'] = dict(previous_ready=bind(old_path), failed_execution_closure=bind(closure_path),
    failure='TRAIN block validator resolved runtime calibration under frozen code instead of registered data cycle',
    fix='temporarily bind frozen campaign CYCLE to hash-bound workflow cycle for unchanged block validation; restore in finally',
    changed_native_source=False, changed_time_or_memory_caps=False, failed_wall_seconds_charged=85.730185,
    metadata_preflight=bind(DATA/'full_train_time_scale_preflight_005_002.json'),
    pure_tests=bind(DATA/'full_train_time_scale_pure_004.xml'), pure_passed=26,
    task_outputs_all_still_absent=True, prior_failure_evidence_preserved=True)
pending = save(DATA/'offline_budget_spec_005_pending_004.json', spec)
history = DATA/'full_train_path_history_001'
save(history/'index.json', dict(old_producer=bind(history/'full_train_time_scale_audit_005.py'),
    old_tests=bind(history/'test_full_train_time_scale_audit_005.py'),
    repaired_producer=bind(DATA/'full_train_time_scale_audit_005.py'),
    repaired_tests=bind(DATA/'test_full_train_time_scale_audit_005.py'), recovery=spec['recovery']))
print(json.dumps(pending))
