"""Record the actual closed full-TRAIN fit and subsequent DEV phase once."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
WORKFLOW = CYCLE/'terminal_flow/workflow_005'
SOURCE = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def bound(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def write_crlf(path, text):
    path.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))

fit_path = WORKFLOW/'training_fit_receipt.json'
fit = read(fit_path)
assert fit['row_count'] == 580 and fit['native_starts'] == 0
assert hashlib.sha256(Path(fit['model']['path']).read_bytes()).hexdigest() == fit['model']['sha256']
runs = []
for parent in (2101, 2102):
    directory = CYCLE/f'runs/TF_full_train_005_TF-B1-300_P{parent}'
    receipt, worker, plan = (read(directory/name) for name in ('receipt.json', 'worker_report.json', 'plan.json'))
    assert worker['scientific_status'] == 'closed' and worker['final_physical_time'] == 59400.
    assert plan['source_bundle']['sha256'] == SOURCE
    runs.append(dict(parent=parent, receipt=bound(directory/'receipt.json'), worker=bound(directory/'worker_report.json')))
events = [json.loads(line) for line in (CYCLE/'ledger.jsonl').read_text(encoding='utf-8').splitlines() if line]
opened = next(row for row in reversed(events) if row['event'] == 'runner_open' and row.get('purpose') == 'full_TRAIN_demand_fit_004')
closed = next(row for row in events if row['event'] == 'runner_close' and row['runner_id'] == opened['runner_id'])
from datetime import datetime
fit_seconds = (datetime.fromisoformat(closed['at'])-datetime.fromisoformat(opened['at'])).total_seconds()
assert any(row['event'] == 'native_start' and row.get('task_id') == 'TF_bridge_all_005_C00_P2201' for row in events)
state_path = ROOT/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state = read(state_path)
active = state['active_experiment']
assert 'full_TRAIN005_closed' not in active
active['full_TRAIN005_closed'] = dict(runs=runs, fitting=bound(fit_path), rows=580,
    model_file=bound(Path(fit['model']['path'])), model_internal_identity=fit['model_sha256'],
    fit_runner_open=opened['at'], fit_runner_close=closed['at'], fit_charged_seconds=fit_seconds,
    DEV_or_TEST_used_for_fit=False, native_starts_for_fit=0)
active['status'] = 'terminal_flow_source005_four_parent_DEV_bridge_running_after_full_TRAIN_fit'
active['block'] = 'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/bridge_all_005/block.json'
state['current_stage'] = ('P0-P4 in progress: source005 two full TRAIN runs closed at 59400 and the demand-only supervised '
    'Poisson model was frozen from 580 mature TRAIN rows. Four-parent DEV bridge is running serially; bin, replan '
    'and fixed-allocator predictor blocks follow the registered workflow. Full scientific, unified-order and '
    'four-parent forecast audits remain pending. Source003 service harms and unstarted superseded004 are retained. '
    'TEST and R1 remain locked; no service promotion.')
write_crlf(state_path, json.dumps(state, ensure_ascii=False, indent=2)+'\n')
readme = ROOT/'docs/g31_ics_circulation/README.md'
text = readme.read_text(encoding='utf-8')
old = '32 次有限后继对照已通过严格短门禁，正在执行完整TRAIN。'
assert text.count(old) == 1
text = text.replace(old, '32 次有限后继对照已通过严格短门禁；两场完整TRAIN已闭合，580条成熟TRAIN标签完成监督预测拟合并冻结，四父DEV桥接正在执行。')
write_crlf(readme, text)
print(json.dumps(active['full_TRAIN005_closed'], ensure_ascii=False, indent=2))
