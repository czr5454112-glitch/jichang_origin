"""One-time documentation update after all four source003 full runs closed."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE = ROOT / 'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
DOC = ROOT / 'docs/g31_ics_circulation'

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def write_crlf(path, text):
    path.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf8'))

methods = ['C00', 'C10', 'TF-current', 'TF-B1-60']
workers = {}
for method in methods:
    run = CYCLE / 'runs' / f'TF_bridge_P2201_003_{method}_P2201'
    receipt = read(run / 'receipt.json')
    assert receipt['process']['exitcode'] == 0
    worker = receipt['worker']
    assert worker == read(run / 'worker_report.json')
    assert worker['scientific_status'] == 'closed' and worker['final_physical_time'] == 59400
    workers[method] = worker

comparisons = []
for key in ['C00_vs_TF60', 'TFcurrent_vs_TF60', 'C10_vs_TF60']:
    report = read(DATA / f'full003_{key}_service_audit_001.json')
    assert report['population'] == 28506 and not report['existing_observed_service_gate_passed']
    comparisons.append(report)

state_path = DOC / 'RESEARCH_STATE.json'
state = read(state_path)
state['current_stage'] = ('P0-P4 in progress: all four source003 full P2201 runs closed. '
    'TF-B1-60 has 332 known completion-direction harms versus TF-current and is worse in J than C10. '
    'Source005 workflow started its two strict export-equivalence gates at 2026-10-21T12:41:45Z; '
    'full TRAIN and four-DEV comparisons remain dependent. Workflow004 was superseded before dispatch '
    'with zero native starts. TEST and R1 remain locked; no service promotion.')
state['working_tree_identity'] = state['working_tree_identity'].replace(
    'active predecessor keeps its own runtime003 identity', 'closed predecessor keeps its own runtime003 identity')
active = state['active_experiment']
active.update(status='terminal_flow_source003_closed_source005_export_gate_running',
    predecessor_all_four_closed=True, successor_started_at_utc='2026-10-21T12:41:45.917027+00:00')
active['source003_TF60_comparisons'] = [dict(reference=x['reference_method'],
    gain_bag_seconds=x['gain_bag_seconds'], completed_delta=x['completed_delta'],
    on_time_delta=x['on_time_delta'], known_completion_harm=x['completion_direction']['known_direction_harm'],
    known_lateness_harm=x['known_lateness_harm'], service_gate=False) for x in comparisons]
write_crlf(state_path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

readme = DOC / 'README.md'
text = readme.read_text(encoding='utf8')
start = text.index('> 当前执行补充（2026-10-21）')
end = text.index('\n\n', start)
text = text[:start] + ('> 当前执行补充（2026-10-21）：source003 的完整 C00/C10/TF-current/TF-B1-60 四组均已闭合。'
    'TF-B1-60 相对 TF-current 的 J 改善 45,130.755852 bag·s，但有 332 件已知完成方向损害；'
    '相对 C10 的 J 恶化 93,884.666967 bag·s，未通过服务门槛。旧快照/接收记录去重修复已冻结为 '
    'terminal_flow_runtime_005，462 项回归通过；32 次有限后继对照已开始严格短门禁。'
    '004 在派发前撤销（0 次原生启动），历史证据保留。详见 [同源完整对照](TERMINAL_FLOW_FULL_SOURCE003_COMPARISON.md)。') + text[end:]
write_crlf(readme, text)

report_path = DOC / 'TERMINAL_FLOW_FULL_SOURCE003_COMPARISON.md'
text = report_path.read_text(encoding='utf8')
text = text.replace('本报告纳入正式 closed receipt 已落盘的 C00、C10 与 TF-current；source003 的 TF-B1-60 仍在原冻结串行链中运行。',
    '本报告纳入正式 closed receipt 已落盘的 C00、C10、TF-current 与 TF-B1-60，四组完整串行运行已经结束。')
text = text.replace('修复后将以 source005 重新登记统一对照', '修复后的 source005 统一对照已登记并开始短门禁')
title = '## TF-B1-60 完整闭合与三个独立参照'
assert title not in text
lines = ['\n' + title, '',
    'TF-B1-60 进程 exit0，总墙钟 2304.719 秒，物理终点 59400；所有 28,506 件均进入逐件审计。'
    '以下正 gain 表示候选 J 更低，负值表示更差。三个参照各自独立，不混为一个预测增量。', '',
    '| 参照→TF-B1-60 | J 改善 bag·s | 完成差 | 准时差 | 已知完成方向损害 | 已知迟到损害 | 服务门槛 |',
    '|---|---:|---:|---:|---:|---:|---|']
for x in comparisons:
    lines.append(f"| {x['reference_method']} | {x['gain_bag_seconds']:,.6f} | {x['completed_delta']:+d} | "
        f"{x['on_time_delta']:+d} | {x['completion_direction']['known_direction_harm']} | {x['known_lateness_harm']} | 未通过 |")
lines += ['', '| 方法 | J bag·s | 完成 | 准时 | 已到达未完成 | 过期未完成 |', '|---|---:|---:|---:|---:|---:|']
for method in methods:
    cost = workers[method]['cost']
    lines.append(f"| {method} | {cost['backlog_integral_bag_seconds']:,.6f} | {cost['completed_by_end']} | "
        f"{cost['on_time_by_end']} | {cost['arrived_unfinished_by_end']} | {cost['arrived_unfinished_past_deadline']} |")
lines += ['', 'TF-B1-60 的6次选中可选提交均有正向ACK/原生提交证据，选中物理失败为0；全部原生请求终态为'
    '1240 received、541 rejected、8 failed、5 departed、4 undelivered。上游真实需求/腾位请求不计为这6次可选订单。'
    '回调时间中位0.394590秒、p95 0.858667秒，仅覆盖选择评分和证据写入，排除候选目录、协议、原生推进与导出，不能认证完整请求100ms。', '',
    '三个 fresh 完整逐件文件为 `full003_C00_vs_TF60_service_audit_001.json`、'
    '`full003_TFcurrent_vs_TF60_service_audit_001.json`、`full003_C10_vs_TF60_service_audit_001.json`。'
    '旧source003的单父结论保持独立；后续source005必须重新跑共同基线，并通过自己的完整科学审计。', '']
write_crlf(report_path, text.rstrip() + '\n' + '\n'.join(lines))
print(json.dumps(dict(updated=['README.md', 'RESEARCH_STATE.json', report_path.name],
    source003_closed=4, source005_completion_claimed=False), ensure_ascii=False))
