"""Bind completed OS lifetime observations to the immutable full-stage artifacts.

Pure file validation. This script neither starts nor modifies simulation processes.
"""
import hashlib
import json
from pathlib import Path
from time import perf_counter, process_time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started, cpu = perf_counter(), process_time()
    base = Path(__file__).resolve().parent
    names = ["os_cpu_monitor_start.json", "os_cpu_monitor_final.json",
             "observe_os_cpu.py", "protocol.json", "full/requested_rows.json",
             "full/summary.json", "full/manifest.json"]
    before = {name: sha(base / name) for name in names}
    read = lambda name: json.loads((base / name).read_text(encoding="utf-8"))
    start, final = read(names[0]), read(names[1])
    summary = read("full/summary.json")
    manifest = {name.replace("\\", "/"): value for name, value in read("full/manifest.json").items()}
    checks = {}
    check = lambda name, condition: checks.__setitem__(name, bool(condition))
    check("observer_declares_complete", final["complete_bound_parent_and_worker_lifetimes"])
    check("no_lifecycle_failure", not start["failures"] and not final["failures"])
    check("no_unexpected_children", not final["unexpected_child_observations"])
    check("protocol_exact", start["full_protocol_sha256"] == before["protocol.json"])
    check("requested_rows_exact", start["full_requests_sha256"] == before["full/requested_rows.json"])
    check("observer_source_exact", start["script_sha256"] == final["source_sha256"] == before["observe_os_cpu.py"])
    check("summary_bound_to_manifest", manifest["full/summary.json"] == before["full/summary.json"])
    check("requests_bound_to_manifest", manifest["full/requested_rows.json"] == before["full/requested_rows.json"])
    check("frozen_closure_unchanged", summary["source_input_test_unchanged"])
    check("planned_requests", summary["planned_logical_requests"] == 4352)
    check("planned_physical", summary["planned_unique_physical"] == 2468)
    check("actual_physical", summary["actual_physical_calls_recorded"] == 2468)
    check("no_unknown_physical", summary["unknown_physical_call_statuses"] == 0)
    check("full_rows", len(summary["rows"]) == 2468)
    check("all_rows_physical", all(row["actual_physical_call"] is True for row in summary["rows"]))
    worker_ids = sorted({row["memory"]["pid"] for row in summary["rows"]})
    check("six_actual_workers", len(worker_ids) == 6)
    check("worker_identities_exact", worker_ids == start["worker_pids"] == final["final_receipt_worker_pids"])
    check("all_identity_records_exact", start["identities"] == final["identities"])
    parent = str(start["parent_pid"])
    expected_ids = {parent, *(str(pid) for pid in worker_ids)}
    check("seven_distinct_processes", len(expected_ids) == 7)
    check("complete_final_handles", set(final["final_lifetime_times"]) == expected_ids)
    check("complete_initial_identities", set(start["identities"]) == expected_ids)
    identity = start["identities"][parent]
    command = identity["command_line"]
    check("exact_parent_module", "scripts.experiments.ics_circulation_v3.run_same_zone_stability" in command)
    check("exact_parent_full_stage", "--stage" in command and command[command.index("--stage") + 1] == "full")
    request_mtime = (base / "full/requested_rows.json").stat().st_mtime
    check("parent_created_with_requests", request_mtime - 180 <= identity["creation_unix_seconds_psutil"] <= request_mtime)
    for pid in sorted(expected_ids):
        identity = start["identities"][pid]
        initial = identity["initial_lifetime_times"]
        terminal = final["final_lifetime_times"][pid]
        check(f"{pid}_has_final", terminal is not None)
        if terminal is None:
            continue
        check(f"{pid}_same_creation", initial["creation_filetime_100ns"] == terminal["creation_filetime_100ns"])
        check(f"{pid}_psutil_creation", abs(identity["creation_unix_seconds_psutil"] - initial["creation_unix_seconds"]) <= .01)
        check(f"{pid}_exit_zero", terminal["exit_code"] == 0)
        check(f"{pid}_exit_after_create", terminal["exit_filetime_100ns"] >= initial["creation_filetime_100ns"])
        check(f"{pid}_cpu_monotone", terminal["total_cpu_seconds"] >= initial["total_cpu_seconds"])
        check(f"{pid}_cpu_components", terminal["total_cpu_seconds"] == terminal["kernel_cpu_seconds"] + terminal["user_cpu_seconds"])
        if pid != parent:
            check(f"{pid}_same_parent", identity["ppid"] == int(parent))
            check(f"{pid}_spawn_command", "--multiprocessing-fork" in identity["command_line"] and any(
                f"spawn_main(parent_pid={parent}," in part for part in identity["command_line"]))
    worker_cpu = sum(final["final_lifetime_times"][str(pid)]["total_cpu_seconds"] for pid in worker_ids
                     if final["final_lifetime_times"].get(str(pid)) is not None)
    parent_times = final["final_lifetime_times"].get(parent)
    parent_cpu = parent_times["total_cpu_seconds"] if parent_times is not None else None
    check("worker_total_exact", worker_cpu == final["known_worker_lifetime_cpu_seconds"])
    check("parent_total_exact", parent_cpu == final["known_parent_lifetime_cpu_seconds"])
    check("combined_total_exact", worker_cpu + (parent_cpu or 0) == final["known_bound_process_cpu_seconds"])
    check("worker_overlapping_timer_exact", summary["case_invocation_cpu_seconds_recorded"] == final["invocation_worker_cpu_seconds_overlapping"])
    check("parent_overlapping_timer_exact", summary["parent_cpu_seconds"] == final["recorded_parent_cpu_seconds_overlapping"])
    check("worker_os_covers_interval", worker_cpu >= summary["case_invocation_cpu_seconds_recorded"])
    check("parent_os_covers_interval", parent_cpu is not None and parent_cpu >= summary["parent_cpu_seconds"])
    check("input_bytes_unchanged", before == {name: sha(base / name) for name in names})
    result = {"schema": "ics_round8_os_lifetime_binding_audit_v1",
              "physical_simulation_calls": 0, "checks": checks,
              "check_count": len(checks), "failures": [name for name, ok in checks.items() if not ok],
              "all_passed": all(checks.values()), "inputs_sha256": before,
              "source_sha256": sha(Path(__file__)),
              "full_stage_lifetime_cpu_seconds": final["known_bound_process_cpu_seconds"],
              "resource_rule": "Use complete bound OS lifetime total instead of overlapping full invocation/parent intervals; do not add them. Other stages and observer remain separate.",
              "audit_cpu_seconds": process_time() - cpu,
              "audit_wall_seconds": perf_counter() - started}
    with (base / "os_cpu_monitor_binding_audit.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    if result["all_passed"]:
        text = "# Round8 正式批完整进程 CPU 补充计量\n\n"
        text += f"已核对 {len(checks)} 项绑定：实际 CLI 父进程及其 6 个 worker 均保留查询句柄至正常退出，2468 个物理调用的 receipt PID、创建时间、原协议、请求列表及结果 manifest 一致。\n\n"
        text += f"正式批完整 worker 生存期 CPU 为 {worker_cpu} 秒，父进程为 {parent_cpu} 秒，合计 **{final['known_bound_process_cpu_seconds']} 秒**。它替代分支 invocation {summary['case_invocation_cpu_seconds_recorded']} 秒与 parent interval {summary['parent_cpu_seconds']} 秒，不能与这些重叠值相加。\n\n"
        text += f"观察器自身记录 CPU 为 {final['observer_cpu_seconds']} 秒，另计；观察器导入、最终 JSON 写入及关闭句柄开销不在其自身计时内。准备、bridge17、pilot24、测试、审计和 root 分析也另计。单个 worker 内存峰值不能解释成总并发峰值。\n\n"
        text += "晚接入仍能读取进程创建以来的累计 kernel/user CPU，这是由 [GetProcessTimes 的累计进程时间语义](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) 推得；[Windows 在进程退出后保留对象至全部句柄关闭](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process)，因此这里读取的是退出后的完整生存期值，不是观察时段差值。查询不改变仿真、优先级、亲和性或并发数。\n\n"
        text += "首次普通沙箱查询无法看见既有进程，错误和 CPU 未知边界保留在 os_cpu_monitor_initial_failure.json；其后获准执行只读查询并成功绑定全部实际进程。这不是物理分支失败。\n"
        with (base / "os_cpu_summary.md").open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(json.dumps({key: result[key] for key in ("check_count", "all_passed", "failures", "audit_cpu_seconds")}))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
