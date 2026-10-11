# Round8 正式批完整进程 CPU 补充计量

已核对 93 项绑定：实际 CLI 父进程及其 6 个 worker 均保留查询句柄至正常退出，2468 个物理调用的 receipt PID、创建时间、原协议、请求列表及结果 manifest 一致。

正式批完整 worker 生存期 CPU 为 38240.8125 秒，父进程为 12.75 秒，合计 **38253.5625 秒**。它替代分支 invocation 38180.359375 秒与 parent interval 4.875 秒，不能与这些重叠值相加。

观察器自身记录 CPU 为 2.4375 秒，另计；观察器导入、最终 JSON 写入及关闭句柄开销不在其自身计时内。准备、bridge17、pilot24、测试、审计和 root 分析也另计。单个 worker 内存峰值不能解释成总并发峰值。

晚接入仍能读取进程创建以来的累计 kernel/user CPU，这是由 [GetProcessTimes 的累计进程时间语义](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) 推得；[Windows 在进程退出后保留对象至全部句柄关闭](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process)，因此这里读取的是退出后的完整生存期值，不是观察时段差值。查询不改变仿真、优先级、亲和性或并发数。

首次普通沙箱查询无法看见既有进程，错误和 CPU 未知边界保留在 os_cpu_monitor_initial_failure.json；其后获准执行只读查询并成功绑定全部实际进程。这不是物理分支失败。
