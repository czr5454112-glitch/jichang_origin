"""Write label-stage scope and measured-resource receipts from immutable inputs."""
import hashlib
import json
from pathlib import Path
from time import perf_counter, process_time

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    started, cpu = perf_counter(), process_time()
    protocol = read(BASE / 'protocol.json')
    history = read(BASE / 'historical_preparation.json')
    check = read(BASE / 'independent_choice_check/result.json')
    ties = read(BASE / 'independent_choice_check/service_ties_result.json')
    stages = {name: read(BASE / name / 'summary.json')
              for name in ('collection_run', 'normal_resume', 'pilot', 'old12', 'full')}
    entries = []
    for name, stage in stages.items():
        entries.append({'stage': name, 'source_file': str(BASE / name / 'summary.json'),
            'manifest_file': str(BASE / name / 'manifest.json'),
            **{k: stage[k] for k in ('planned_requests', 'status_counts',
                'actual_physical_calls_recorded', 'unknown_physical_call_statuses',
                'case_invocation_cpu_seconds_recorded', 'parent_cpu_seconds',
                'wall_makespan_seconds', 'complete_resource_accounting', 'source_input_test_unchanged')},
            'max_single_worker_lifetime_peak_working_set_bytes': max(r['memory']['peak_working_set_bytes'] for r in stage['rows']),
            'sum_route_search_calls_nested_not_extra_cpu': sum(r['search_calls'] for r in stage['rows']),
            'sum_route_search_work_nested_not_extra_cpu': sum(r['search_work'] for r in stage['rows'])})
    worker = sum(r['case_invocation_cpu_seconds_recorded'] for r in entries)
    parent = sum(r['parent_cpu_seconds'] for r in entries)
    preparation = protocol['preparation_cpu_seconds'] + history['cpu_seconds']
    resources = {'schema': 'ics_round7_labels_resource_receipt_v1', 'stage_entries': entries,
        'preparation': {'protocol_file': str(BASE / 'protocol.json'),
            'cpu_seconds': protocol['preparation_cpu_seconds'], 'wall_seconds': protocol['preparation_wall_seconds'],
            'scope': 'prepare function through protocol construction; later protocol/input/manifest writes not timed'},
        'historical_checkpoint_conversion': {'file': str(BASE / 'historical_preparation.json'),
            'cpu_seconds': history['cpu_seconds'], 'wall_seconds': history['wall_seconds'],
            'physical_calls': 0, 'checkpoints': history['checkpoints'],
            'scope': 'restore/verify/replace only inner slow/freeze checkpoints; final preparation manifest hashing/write excluded'},
        'known_worker_invocation_cpu_seconds': worker, 'known_parent_run_function_cpu_seconds': parent,
        'known_preparation_cpu_seconds': preparation,
        'known_label_pipeline_cpu_seconds_lower_bound': worker + parent + preparation,
        'recorded_physical_invocations': sum(r['actual_physical_calls_recorded'] for r in entries),
        'memo_hits': 0, 'unknown_case_invocation_statuses': sum(r['unknown_physical_call_statuses'] for r in entries),
        'known_function_scope': 'worker invocation includes setup/restore, simulation, raw serialization and final immutable verification; final memory snapshot/return bookkeeping excluded. Parent run timer ends before final summary/manifest serialization. Raw cycle CPU is nested and MUST NOT be added again.',
        'unmeasured_scope': ['Python CLI and spawned worker imports/startup before function timers',
            'final resource receipt and some preparation/summary/manifest writes after their timers',
            'ordinary read-only status inspections, py_compile and prefreeze author test child CPU'],
        'wall_scope': 'per-stage wall only; stages may overlap other team experiments and historical prepare overlaps collector; no sum claimed as total elapsed makespan',
        'memory_scope': 'maximum single worker lifetime working set, includes imports and earlier cases; not simultaneous aggregate process peak',
        'prefreeze_author_validation': {'file': str(BASE.parent / 'phase4_w3_round7_labels_authoring_20261010/validation_attempts.json'),
            'attempts': [{'tests': 7, 'passed': 5, 'failed': 2, 'tool_wall_seconds': 3.0135688, 'child_cpu_seconds': None},
                {'tests': 7, 'passed': 5, 'failed': 2, 'tool_wall_seconds': 3.1613244, 'child_cpu_seconds': None},
                {'tests': 28, 'passed': 28, 'failed': 0, 'tool_wall_seconds': 3.8793846, 'child_cpu_seconds': None}],
            'failure_scope': 'two tiny normal-resume assertion failures per first/second author invocation; physical result/search/cache matched, audit suffix indexing and terminal preview handling were corrected before freeze; no original-map run was omitted',
            'formal_normal_stage': 'all five original-map normal resumes including a real zero pool succeeded; no failed formal normal case'},
        'independent_choice_check': {'file': str(BASE / 'independent_choice_check/result.json'),
            'cpu_seconds': check['cpu_seconds'], 'wall_seconds': check['wall_seconds'], 'physical_calls': 0,
            'scope': check['timing_scope']},
        'additional_service_tie_check': {'file': str(BASE / 'independent_choice_check/service_ties_result.json'),
            'cpu_seconds': ties['cpu_seconds'], 'wall_seconds': ties['wall_seconds'],
            'physical_calls': 0, 'scope': ties['timing_scope']},
        'excluded_team_work': 'reviewer audit/full-suite, query-probe author tests, coverage27/expansion probes, immutable-trace supplement and root value analysis are separate team receipts; not included here'}
    with (BASE / 'label_resource_summary.json').open('x', encoding='utf-8') as stream:
        json.dump(resources, stream, indent=2, ensure_ascii=False)
    lines = ['# 第七轮标签阶段交接', '',
        '从原始三个 nominal 初态安装冻结的 same_zone32plus32 控制器，现场重新采到 **180 次尝试：174 个非空状态、6 次零候选、692 个候选**。所有检查点立即复制真实 cursor、私有 replay cache、待到达账本和实际继续策略合同，没有用可见状态重建 checkpoint。', '',
        '三个 collection 对第六轮 formal nominal 的完整结果（仅排除 policy_stats 中计时 *_ms）、逐次 search、cache、机会、selector/event/兼容 physical trace 和 slow clock 全部精确一致。5 个正常恢复分支在共同绝对终点再次严格复现；16 个固定 pilot、历史 12 状态 × 4 候选、正式全部 692 候选均完成真实任务账和 controller-quiescent，失败/截断为 0，memo 为 0。', '',
        '历史 12 状态明确属于旧策略轨迹的事后诊断子组，只更换未来慢控制器；state/cursor/cache/pool/clock 保持原值。d40 c0/c1 的 148.1/146.7、h80、全结果、逐查询、cache 与停止时刻逐字段复现第六轮。', '',
        '| 阶段 | 实际物理调用 | Worker invocation CPU 秒 | Parent run CPU 秒 | 阶段墙钟秒 |',
        '|---|---:|---:|---:|---:|']
    for row in entries:
        lines.append(f"| {row['stage']} | {row['actual_physical_calls_recorded']} | {row['case_invocation_cpu_seconds_recorded']:.6f} | {row['parent_cpu_seconds']:.6f} | {row['wall_makespan_seconds']:.6f} |")
    lines += ['', f'另有 prepare {protocol["preparation_cpu_seconds"]:.6f} CPU 秒、12 checkpoint 转换 {history["cpu_seconds"]:.6f} CPU 秒（0 次物理仿真）。上述已知标签流水线 CPU 下界为 **{worker + parent + preparation:.6f} 秒**，记录了 **{resources["recorded_physical_invocations"]} 次物理调用**。完整边界、逐阶段资源与路径见 `label_resource_summary.json`。', '',
        'CPU 是函数计时范围，不是操作系统全生命周期总量：worker/CLI import、启动及少量计时后的 receipt/manifest 写入未单独测量。raw 中 cycle CPU 已包含在 worker invocation，search/work 也只是嵌套工作账，禁止重复加总。单 worker lifetime 内存峰值不能当多进程同时总峰。', '',
        '冻结前作者两次 7 项测试各有 2 项 normal-resume 审计断言失败：先混用了完整 trace 与 suffix 索引，再遗漏 result() 的非执行 terminal tick preview；物理结果/搜索/cache 一直相同。修复后作者 7 项通过，随后独立 29 项通过；失败、诊断工具墙钟及未知 child CPU 明确保存在作者记录。正式 5 个 normal 分支没有失败。故障注入测试覆盖 partial query pickle、raw/recovery 写失败与已完成物理结果保留；其测试资源由独立审查记录计费。', '',
        '独立纯文件复算（0 新仿真）：', '',
        f'- 全部 174 状态 / 692 raw 候选逐账核对；非平坦状态 {check["nonflat"]}，实际选择非最优状态 {check["choice_nonoptimal"]}，最大局部 regret {check["max_regret"]:.9g}。',
        f'- 全部相同 bag 完成时刻均不晚于实际选择的候选子集（允许完全相等），最小 J 仍可改善的状态 {check["no_later_completion_positive_regret_samples"]}，最大可改善 {check["no_later_completion_max_regret"]:.9g}。',
        f'- 再要求 load_time 也不晚的更严子集，可改善状态 {check["no_later_load_and_completion_positive_regret_samples"]}，最大可改善 {check["no_later_load_and_completion_max_regret"]:.9g}；相同缺失初始 load_time 只视为未变，不猜测具体时间。',
        f'- 核验 CPU {check["cpu_seconds"]:.6f} 秒，墙钟 {check["wall_seconds"]:.6f} 秒；原 full manifest 前后字节不变。逐状态 cost vector、optset 和子集在 `independent_choice_check/result.json`。', '',
        f'另做 J 不高于实际选择、所有 bag 完成不晚且至少一件严格更早的服务诊断：**{ties["pools_with_completion_improvement_at_no_higher_cost"]} 个状态 / {ties["qualifying_completion_candidate_count"]} 个候选**满足；再要求 load_time 也不晚后为 **{ties["pools_with_load_and_completion_improvement_at_no_higher_cost"]} 个状态 / {ties["qualifying_load_and_completion_candidate_count"]} 个候选**。完整 174 状态含空集合逐池列出，见 `independent_choice_check/service_ties_result.json`。该额外纯文件核验 CPU {ties["cpu_seconds"]:.6f} 秒、墙钟 {ties["wall_seconds"]:.6f} 秒，未新增物理实验。', '',
        '这些是离线同一 nominal tape、单次动作偏离诊断，不是在线服务保证，也不是 174 个独立部署试验；局部 regret 不可相加称为可部署节省。692 候选任务账的重复计数不是新的独立真实任务源。仍只有三个重复使用的合成开发流，没有扩展为独立运行日或新的实物流量源。', '',
        '停止合同没有降低：全部固定任务已观察且完成、pending arrivals 为空、实际运输承诺排空、所有原预测公示与 TTL 过期，并经历完整真实 slow period 和实际 trigger。有限资源/tick cap 会显式记 censored，不会冒称不可行。未来任务仅供物理引擎和离线评价，控制器仍只读原公开预测和已观察状态。', '',
        '兼容 physical trace 沿用了冻结旧 helper；completed/load_times/empty_targets 字典可能反映后续更新，不能把这三项当即时 tick 账本。准确服务时点来自完整任务 ledger、event trace、真实 checkpoint 和 milestone；root 另补 immutable 即时 trace 复跑。本批控制、成本和搜索未使用这些输出 trace。checkpoint fingerprint 沿用旧 _semantic 的 *_ms 排除规则，实际控制标量（含 planning_budget_ms）另有 active continuation 显式绑定。', '',
        '全部新代码与测试快照在 `source_snapshot/`、`test_snapshot/`：104 source、67 tests，所有正式阶段结束均报告 source/input/test 不变。原 C++ `cpp/ics_core/runtime/bounded_local_pibt.hpp` 直接纳入输入 SHA，未修改。没有 commit/push。', '',
        '证据入口：`protocol.json`、`preparation_manifest.json`、`collection_run/summary.json`、`normal_resume/summary.json`、`pilot/summary.json`、`old12/summary.json`、`full/summary.json` 及各自 manifest。独立 reviewer 的终审与 root 主分析另行引用，不能把本纯文件交叉核验替代完整审计。', '']
    with (BASE / 'summary.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    receipt = {'physical_simulations': 0, 'cpu_seconds': process_time()-cpu,
        'wall_seconds': perf_counter()-started,
        'scope': 'write_summary function through resource JSON and Markdown writes; imports and this receipt write excluded',
        'sha256': {name: hashlib.sha256((BASE/name).read_bytes()).hexdigest()
                   for name in ('write_summary.py', 'label_resource_summary.json', 'summary.md')}}
    with (BASE / 'summary_authoring_receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
