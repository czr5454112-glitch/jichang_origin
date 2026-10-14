# Round8 同仪器 terminal-screen 性能结论

固定 27 原输入、on/off、两个反向顺序区块，共 108 次独立进程物理运行；此前 12 次 pilot 独立计费、不复用。54 个配对全部排空，实际 query Snapshot、K、完整有序候选池、动作、任务、事件、即时深拷贝逐 tick 轨迹均严等；两臂也都与 Round7 冻结旧筛查原件吻合。默认策略、旧源码、C++ 未改。

查询算法区间（validity/dispatch/screen/search，排除共同 observer）CPU **32.09375 → 24.6875 秒**，这批观测减少 **23.08%**；完整仿真 **1357.40625 → 1348.015625 秒**，减少 **0.692%**；完整 Windows OS 子进程寿命 CPU **1588.25 → 1579.5 秒**，减少 **0.551%**。这些是嵌套口径，不能相加。完整进程收益远小于查询区间收益，没有普遍加速或硬实时结论。

全部负例保留：54 个配对的算法 CPU 为 37 降／3 平／14 升，完整进程为 37 降／0 平／17 升；按每个输入两个区块均值，8／27 算法更慢、9／27 完整进程更慢。两个区块算法 CPU 差分别为 −3.515625、−3.890625 秒，进程差为 −5.390625、−3.359375 秒。只有两个计时重复，不代表独立运营日或可泛化概率保证。

逻辑搜索工作 **3,332,772 → 2,774,772**，另付筛查记录工作 **146,930**；每臂 4,934 查询。两臂每 episode 初始 routing cache 确实为空，但后续对应 query 中 130 个 private-cache SHA 不同、20 个 entry count 不同，全部发生在首次跳过搜索之后；不强制补齐缓存，不把每 query 耗时差全归于其当前 certificate。OS 文件页缓存未清空，也未宣称冷机测试。

实际 CPU 正增量和配对差最小非零粒度为 **15.625 ms**；大量 active query 的 CPU 读数为 0，但 elapsed 非 0。ns 返回单位不等于 ns 测量精度。全量分 loaded/empty、on/off、algorithm/search/screen/observer 的零值普查和最小增量均保留，关闭筛查或跳过 search 的结构性 0 单独分类。计时解释与官方资料见 [CLOCK_SOURCES.md](CLOCK_SOURCES.md)。

正式运行完整子进程 CPU 合计 **3167.75 秒**，协调进程测量区间 **277.3125 秒**，阶段 makespan **1193.2561737 秒**；最大单子进程 lifetime peak working set **103,079,936 B**，不得把各子进程峰值相加当同时总峰值。正式运行时最多 3 个性能子进程与主线 6 worker 并行，墙钟不是无负载延迟。没有故障、删样本或收益驱动重跑。

纯文件分析 623 检查／0 失败，CPU 26.40625 秒；静态全 27 输入图 CPU 1.703125 秒，PNG 已视觉检查，标签和注释无裁切。图中线段是两个重复的范围，不是置信区间。

- [全量结果、每输入表及计时边界](formal/PERFORMANCE.md)
- [机器可复算原件分析](formal/analysis.json)
- [两区块全 27 输入图 PNG](visuals/all27_paired_cpu.png)
- [同源矢量 SVG](visuals/all27_paired_cpu.svg)
- [固定设计与初始作者故障记录](../phase4_w3_round8_performance_authoring_20261010/PERFORMANCE_DESIGN.md)
- [正式协议及源码快照](../phase4_w3_terminal_screen_performance_20261010/protocol.json)

独立原件终审由另一 agent 单独生成在 Round8 review 目录；总 Round8 资源账仍等待共同 future 主线及其最终分析/审查，不能提前把它们记作已完成。
