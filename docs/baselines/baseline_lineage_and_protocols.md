# Baseline 谱系与 P0/P1/P2 协议

## 谱系去重

| 展示名 | 实际谱系/实现 | 证据标签 | 可进入协议 |
| --- | --- | --- | --- |
| Feng-native HCA | 原工程 `App.ICS_PathFinding` + `App.Astar` | `NATIVE_ORIGINAL_BASELINE` | P0 HCA 回归；P2 系统对照 |
| Feng-native CIE-DH | 原论文所述 native DH，源码尚未恢复 | `BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED` | P0 预留，当前 N/A |
| CIE-DH / Feng-DH / Tarău-local-2009 | 公共执行器内同一 adapted local heuristic 家族 | `ADAPTED_BASELINE_NOT_NATIVE` | P1；别名只计一个方法 |
| G31/S4 | 当前去中心化事件驱动实现 | `PROJECT_METHOD` | P1 算法机制对照；P2 端到端系统对照 |

同一家族的别名不得作为多个 baseline 重复计数，也不得通过改名制造更多胜负单元格。

## P0：Feng 原生 Java 执行器

- 执行器：`FENG_NATIVE_JAVA`。
- 固定对象：原始 map2、1× 输入、2.5 m/s、原始 HCA 调度代码。
- 合法比较：Feng-native HCA 对 Feng-native CIE-DH，前提是后者的一手源码和状态语义真正恢复。
- 当前状态：HCA 可运行；CIE-DH 被源码缺失阻塞。因此当前 P0 只能给 HCA 回归证据，不能给 native HCA-vs-DH 胜负。
- 包装器职责：headless 调用与事件观测；不得替换 HCA scorer、reservation 或 A*。

## P1：公共 C++ 事件执行器

- 执行器：`COMMON_CPP_EVENT_EXECUTOR`；合流协调固定为 neutral FIFO。
- 固定对象：同图、同任务人口、同负载、同释放协议、同速度和同物理服务语义。
- 1× 使用 same-HCA release；2× 使用 canonical release。只有完整 canonical 人口才报告正式全人口时延。
- 合法比较：G31/S4、CIE-DH adapted 及同执行器的势函数/动态项分解。
- CIE-DH 的 `H_FF` 与 `H_SA` 版本只允许改变静态 base potential；动态拥堵计数、执行器和其余规则必须相同。
- P1 回答“公共执行条件下算法机制的差异”，不能升级为原论文 native reproduction。

## P2：端到端系统对照

- 对象：Feng-native HCA Java 系统与 G31/S4 native C++ 事件系统。
- P2 可以报告完整人口下的端到端完成量、deadline-success、全人口延迟和计算代价。
- 因执行器、时间推进与协调实现不同，P2 的差距是“系统组合差距”，不能全部归因于单一 scorer 或写成同执行器算法消融。

## 禁止跨协议排名

P0、P1、P2 必须分表、分标题、分结论。尤其禁止：

- 用 P1 adapted CIE-DH 数值补 P0 native DH；
- 将 P0 Java HCA 的 wall time 与 P1 单个 scorer 的局部计算时间直接排名；
- 把 P2 系统差距称为严格算法支配；
- 将 2× 未完整释放/完成候选的幸存者时延用于任何正式排序。

## 共同报告门槛

1. 先报告 canonical population、released、completed、deadline-success 和 execution-integrity。
2. 只有释放与完成覆盖正式全人口时才报告 mean/P95/P99/max；否则全部为 `N/A`。
3. 同一比较表必须列出 executor、release protocol、map、load、speed 和运行产物身份。
4. adapted 与 native 标签必须出现在方法名附近，而不是只藏在脚注。
5. 旧冻结证据不覆盖；新结果写入新的 namespace，并由运行器回填精确身份与指标。

## P0 HCA 回归

| metric | value |
| --- | --- |
| run/artifact identity | `outputs/runtime/cie_revision/feng_native_hca_regression.json`；source aggregate `b0c7545a…acc9c25` |
| released / completed / deadline-success | 43,603 / 43,603 segments；deadline-success `NOT_MEASURED` |
| full-population mean / P95 / P99 / max | processed-attempt 236.710166 / 299 / 330 / 357 s |
| comparison eligibility | `PASS`；28,506/28,506 raw bags；survivor timing=false |

这些占位符只能由正式 runner 产物替换；不得根据旧报告手工抄写或估算。
