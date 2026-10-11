"""Pure-artifact closeout: no simulation, no modification of frozen records."""
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.experiments.ics_circulation_v3.experiment_protocol import write_new_json
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import file_sha


def main():
    started, cpu = perf_counter(), process_time()
    base = Path(__file__).resolve().parent
    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    protocol = read(base / "protocol.json")
    records, bound = {}, {}
    for stage in ("bridge", "pilot", "full"):
        path = base / stage / "summary.json"
        manifest = read(base / stage / "manifest.json")
        if file_sha(path) != manifest[str(path.relative_to(base))]:
            raise ValueError("stage summary no longer matches its immutable manifest")
        bound[str(path.relative_to(base))] = file_sha(path)
        value = read(path)
        rows = value["rows"]
        records[stage] = {key: value[key] for key in ("planned_logical_requests", "planned_unique_physical",
            "memo_aliases", "actual_physical_calls_recorded", "unknown_physical_call_statuses", "status_counts",
            "logical_status_counts", "case_invocation_cpu_seconds_recorded", "parent_cpu_seconds",
            "wall_makespan_seconds", "complete_resource_accounting", "source_input_test_unchanged")}
        records[stage].update(search_calls_physical_once=sum(r.get("search_calls", 0) for r in rows),
            search_work_physical_once=sum(r.get("search_work", 0) for r in rows),
            nested_cycle_cpu_not_added=sum(r.get("nested_cycle_cpu_seconds", 0) for r in rows),
            max_single_worker_lifetime_peak_ws_bytes=max((r.get("memory", {}).get("peak_working_set_bytes", 0) or 0 for r in rows), default=0),
            unknown_search_records=sum("search_calls" not in r for r in rows))
        if stage == "full":
            logical_path = base / stage / "resolved_requests.json"
            if file_sha(logical_path) != manifest[str(logical_path.relative_to(base))]:
                raise ValueError("resolved requests changed")
            bound[str(logical_path.relative_to(base))] = file_sha(logical_path)
            by_key = {r["physical_key"]: r for r in rows}
            weighted = [by_key[r["physical_key"]] for r in read(logical_path)]
            records[stage]["task_instances"] = {
                scope: {"unknown_task_records": sum("task_count" not in r for r in group),
                    "known_record_sums": {key: sum(r[key] for r in group if key in r) for key in
                    ("task_count", "observed", "completed", "protected_expected", "protected_on_time")}}
                for scope, group in (("physical_unique_weighted", rows), ("logical_request_weighted", weighted))}
    result = {"schema": "ics_round8_label_resource_closeout_v1", "stages": records,
        "preparation_cpu_seconds": protocol["preparation_cpu_seconds"],
        "preparation_wall_seconds": protocol["preparation_wall_seconds"],
        "known_pipeline_cpu_lower_bound": protocol["preparation_cpu_seconds"] + sum(
            r["case_invocation_cpu_seconds_recorded"] + r["parent_cpu_seconds"] for r in records.values()),
        "recorded_physical_calls": sum(r["actual_physical_calls_recorded"] for r in records.values()),
        "resource_scope": protocol["resource_scope"], "task_scope": "both task ledgers repeat the same development tasks across alternative futures/actions; neither is new independent operational workload",
        "tests_and_audits": "author initial/second pytest child CPU unknown; independent audit/test CPU resides in separate reviewer output; do not impute zero or double-count",
        "original_graph_failed_attempts": [stage for stage, r in records.items() if any(k != "controller_quiescent" for k in r["status_counts"])],
        "input_summary_sha256": bound}
    write_new_json(base / "label_resource_summary.json", result)
    full = records["full"]
    text = """# Round8 共同外生未来标签：执行与资源记录

仅新增本轮恢复／条件采样／运行入口，旧算法、旧原件及 C++ 保持冻结。此批来自同三条合成开发流，不能称新的独立验证数据。

## 固定实验合同

在每条流按 origin／continuation × [0,40)、[40,80)、[80,∞) 取最早真实尝试，零池不补位。18 个格选中 17 个 K4 非空状态和 1 个零池，另保留全部其余 5 个零池；完整 180 次尝试见 inventory.json。状态选择不读取成本或未来任务数。

每状态两个独立 PRNG blocks，各保存 32 个共同未来，2／8／32 使用同块前缀。未观察软任务先验 cancel=3/24、三个 jitter 各 7/24，条件于取消或 arrival+j>now 后归一为 3+7m；不 clipping，不随机重抽。受保护任务逐字段不变且不消耗随机数；已观察任务不参与抽样。真实未来只进入引擎事件队列，原公开预测、时钟、控制器、候选池、私有缓存不变。

4352 个逻辑请求对应 2468 个唯一物理调用；1884 个重复未来引用保留原估计权重。memo 仅允许相同 state/checkpoint、candidate index/key、完整未来与继续策略/评价合同，绝不跨状态或动作缓存。所有正式请求只按唯一物理调用计计算资源。

终止要求全部固定评价任务账完成、物理承诺排空、原预测过期后完整真实慢周期触发；80 tick 只是附加固定观察端点。有限 cap 或预算只可称 censored。原兼容 trace 的历史可变映射限制仍明确标记；新即时 trace 用冻结的独立透明观察器逐 tick 深拷贝。

## 完成情况与资源

"""
    text += "| 阶段 | 逻辑请求 | 唯一物理 | worker CPU(s) | parent CPU(s) | 墙钟(s) |\n|---|---:|---:|---:|---:|---:|\n"
    for stage, r in records.items():
        text += f"| {stage} | {r['planned_logical_requests']} | {r['actual_physical_calls_recorded']} | {r['case_invocation_cpu_seconds_recorded']} | {r['parent_cpu_seconds']} | {r['wall_makespan_seconds']:.6f} |\n"
    text += f"\n正式 unique 状态：{full['status_counts']}；logical 加权状态：{full['logical_status_counts']}。全部阶段冻结校验：{all(r['source_input_test_unchanged'] for r in records.values())}。\n"
    text += f"\n准备 CPU {protocol['preparation_cpu_seconds']} 秒；已记录 pipeline CPU 下界合计 {result['known_pipeline_cpu_lower_bound']} 秒。原未来 bridge17 与 pilot24 都真实重复运行，独立计费，不从正式调用抵扣；嵌套 cycle CPU 和 search/work 不与 invocation CPU 重复加。所有成功和失败原件保留。\n"
    text += "\n计时不覆盖进程导入/启动、worker initializer 校验、最后 receipt 写入及 parent summary/manifest 收尾；这些未知开销不填零。内存为单个 worker 生存期峰值，不是同时运行总峰值。测试、独审、root 分析及性能线资源另列，不能重复叠加。\n"
    text += "\n正式任务统计包含候选／共同未来／memo 的重复权重，不能称新增独立任务源。各状态离线条件 regret 不能相加成为可部署的总节约。标签稳定性和互块验证由 root 的纯文件分析报告给出；本摘要不根据先见结果修改协议或选择状态。\n"
    summary = base / "summary.md"
    with summary.open("x", encoding="utf-8") as stream:
        stream.write(text)
    write_new_json(base / "summary_authoring_receipt.json", {"physical_calls": 0,
        "cpu_seconds": process_time()-cpu, "wall_seconds": perf_counter()-started,
        "files": {p.name: file_sha(p) for p in (Path(__file__), base / "label_resource_summary.json", summary)}})


if __name__ == "__main__":
    main()
