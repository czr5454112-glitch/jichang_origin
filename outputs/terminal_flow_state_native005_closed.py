"""One-shot status update after genuine workflow005 closure; no scientific promotion."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CYCLE = Path('outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001')
DATA = Path('outputs/experiments/g31_ics_terminal_flow_20261021')
completion = ROOT / CYCLE / 'terminal_flow/workflow_005/completion.json'
ready = ROOT / DATA / 'offline_budget_spec_005_ready_003.json'
assert hashlib.sha256(completion.read_bytes()).hexdigest() == '658b421515f995c64a3bd29e34fed66c46f4c527c957909b4a598935399d3d4b'
assert hashlib.sha256(ready.read_bytes()).hexdigest() == '25be054117a868b3b9578875d6fca4baed898f45dc8bae39a2a8ff207aa779ba'
state_path = ROOT / 'docs/g31_ics_circulation/RESEARCH_STATE.json'
state = json.loads(state_path.read_text(encoding='utf-8'))
assert state['active_experiment']['status'] == 'terminal_flow_source005_four_parent_DEV_bridge_running_after_full_TRAIN_fit'
state['current_stage'] = ('P0-P4 scientific assessment pending: source005 finite workflow closed all 32 native runs '
    '(2 export gates, 2 full TRAIN, 28 full DEV), exit 0. The 580-row TRAIN-only supervised model remains frozen. '
    'The registered 11-task offline audit has started; native closure is not scientific promotion. '
    'Source003 harms and unstarted superseded004 are retained. TEST and R1 remain locked.')
active = state['active_experiment']
active['status'] = 'terminal_flow_source005_native_closed_offline_audit_started'
active['block'] = None
active['native_workflow005_closed'] = dict(
    completion=str(completion.relative_to(ROOT)).replace('\\', '/'),
    completion_sha256=hashlib.sha256(completion.read_bytes()).hexdigest(),
    native_runs_closed=32, full_DEV_runs_closed=28, original_ledger_total_native_starts=54,
    workflow_exitcode=0, successor_finished_at_utc='2026-10-22T02:42:17.774050+00:00',
    scientific_promotion=False)
active['offline_audit003'] = dict(
    ready_spec=str(ready.relative_to(ROOT)).replace('\\', '/'),
    ready_spec_sha256=hashlib.sha256(ready.read_bytes()).hexdigest(),
    output=(DATA / 'offline_budget_execution_005_003').as_posix(), tasks=11,
    status='started_pending_completion', native_starts=0)
state_path.write_bytes((json.dumps(state, ensure_ascii=False, indent=2)+'\n').replace('\n','\r\n').encode('utf-8'))
readme = ROOT / 'docs/g31_ics_circulation/README.md'
text = readme.read_text(encoding='utf-8')
old = '两场完整TRAIN已闭合，580条成熟TRAIN标签完成监督预测拟合并冻结，四父DEV桥接正在执行。'
assert text.count(old) == 1
text = text.replace(old, '两场完整TRAIN已闭合，580条成熟TRAIN标签完成监督预测拟合并冻结；截至北京时间2026-10-22，source005的32场原生运行已全部正式闭合，11项离线科学审计已启动，尚无服务晋级结论。')
old = '完整 59400 秒配对对照正在执行。'
assert text.count(old) == 1
text = text.replace(old, 'source005的28场完整59400秒DEV对照已闭合，正在核验逐袋服务、订单链、时间尺度和预测误差。')
readme.write_bytes(text.replace('\n','\r\n').encode('utf-8'))
print(json.dumps(dict(native_workflow_closed=True, scientific_promotion=False, native_started=False)))
