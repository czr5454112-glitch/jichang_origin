"""Refresh live repository status after cancelling an unstarted workflow."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
path = root/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state = json.loads(path.read_text(encoding='utf8'))
state['current_stage'] = ('P0-P4 in progress: source003 full C00/C10 closed and its two TF runs retain frozen execution. '
    'Workflow004 was cancelled before all 32 successor native starts after a pure regression reproduced stale cross-owner capture releasing a later RECEIVED claim. '
    'Corrected working source is being verified for terminal_flow_runtime_005; no TEST or R1 unlock.')
state['working_tree_identity'] = ('codex/g31-ics-v3-circulation; task anchor c7121c12b3d59a1d6fcd4919bb13bb86aa2ff91f; '
    'active terminal_flow_runtime_003 remains frozen; terminal_flow_runtime_004 remains preserved but never dispatched; correction005 not yet frozen.')
active = state['active_experiment']
active['status'] = 'terminal_flow_source003_running_source004_cancelled_before_dispatch_source005_verification'
active['superseded_successor_004'] = {key: active.pop(key) for key in list(active) if key.startswith('successor_')}
active['superseded_successor_004'].update(native_starts=0,
    dispatch='outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_004/dispatch_001.jsonl',
    reason='Capture timestamps must dominate the receipt or issuance they supersede; pure reachable prepared-state counterexample.')
path.write_bytes((json.dumps(state, ensure_ascii=False, indent=2)+'\n').replace('\n','\r\n').encode('utf8'))
path = root/'docs/g31_ics_circulation/README.md'
lines = path.read_text(encoding='utf8').splitlines()
lines[2] = ('> 当前执行补充（2026-10-21）：完整同源 C00/C10 已闭合，C10 总积压改善但存在 234 件已知完成方向损害，服务门槛未通过。'
    '原 runtime003 的两个 TF 组保留冻结串行执行。复核发现旧跨 owner 快照可能过早释放已接收订单的去重占位，'
    'workflow004 已在派发前撤销（0 次原生启动）；修复正在验证，随后冻结005并重新登记相同有限对照。'
    '详见 [同源完整对照](TERMINAL_FLOW_FULL_SOURCE003_COMPARISON.md)。')
path.write_bytes(('\n'.join(lines)+'\n').replace('\n','\r\n').encode('utf8'))
