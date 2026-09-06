# 南宁 1× / seed 155921：HCA 大时延的单格来源诊断

本次只诊断 `outputs/runtime/hca_segment_identity_20260906` 中修复后、清理脚本优化前的一个完整人口预检格，并与同种子旧 HCA 档案比较。它是后续统一 fast-cleanup campaign 的原生数值对照，不是最终 60 格或十种子聚合结论。未重新模拟、改算法、调参数或补造旧完成事件。

**结论：此格 5007.494781 秒的共同 D 平均 THT，并不是身份修复制造的大范围排队劣化。** 新旧 43,599 段的 D、实际 release 和成功 planning 时刻完全相同；旧记录中已完成的 28,505 袋，共同 D THT 逐袋全部完全相同。新完整人口只多纳入原先完成段归属不完整的袋 2806，其 THT 为 12653.447940 秒，故均值增加 0.268232 秒。该结论不推广到其余 59 格。

## 原生证据与计时分解

[`diagnose_hca_segment_identity_release_delay.py`](../../scripts/eval/diagnose_hca_segment_identity_release_delay.py) 从新原生 execution-ID 映射、release、planning、route 和 completion 重新构造所有段，再与保存的 lifecycle、raw-bag THT、normalized min/mean/p95/p99/max 核对；未把派生 CSV 当作唯一证据。所有文件身份、完整差异及原生 summary 见[独立诊断 JSON](../../outputs/runtime/hca_segment_identity_20260906/diagnostics/nanning_1p00x_seed_155921_release_delay.json)。

旧侧也直接核对原生 release 与成功 planning；对已具备全部完成事件的袋，独立用 `Σ(raw-ID completion epoch)−Σ(canonical 段 D)` 验证共同 D 时延，无需把旧 raw-ID completion FIFO 分配给某一段。只有完整袋的这个和不受同袋两段事件配对顺序影响；它不能确定歧义事件的物理段归属，也不能恢复旧缺失事件。

同一原始袋求各段之和，恒有 `Σ(E−D) = Σ(R−D) + Σ(P−R) + Σ(E−P)`：D 是共同 canonical 计划时刻，R 是原生实际释放，P 是成功规划，E 是完成。新人口 28,506 袋的分解如下。

| 每袋求和后的人口统计；秒 | 均值 | 最大值 |
|---|---:|---:|
| 正式共同 D THT，Σ(E−D) | 5007.494781 | 58115.872320 |
| 实际释放偏移，Σ(R−D) | 4634.256515 | 57595.982320 |
| 已释放后规划等待，Σ(P−R) | 6.586438 | 2441.000000 |
| 成功规划后运行，Σ(E−P) | 366.651828 | 1054.000000 |

均值的 **92.5464%** 来自实际释放之前的偏移。`R−D` 保留原整数时钟量化产生的小负数，没有额外截为零；各分量最大值不属于同一袋，不能相加当作 THT 最大值。旧原生 `processed_attempt` 口径在 28,505 个完成袋上的均值为 366.645957 秒；把它与新共同 D 均值 5007.494781 秒相除，不能解释为修复造成十余倍算法劣化。

旧同格正式表的 `formal_timing_status=NOT_MEASURED_FULL_POPULATION_INCOMPLETE`，共同 D THT 留空。仅为这次日志诊断，旧已完成 28,505 袋的共同 D 均值为 5007.226549 秒，最大值已是 58115.872320 秒；它仍不是合格的旧全人口性能估计。共同完成袋排序后的 `(raw_id,THT)` 数组，新旧 SHA256 均为 `142ba3fee97180899141c5451e7e9396cf1929dbdf12482580fb2295838fcd19`。不以该子集恢复旧 HCA 的正式资格，也不替代新完整人口结果。

新旧原生 summary 均为 43,599 段 generated；新为 43,599 completed、0 active、0 unplanned，旧为 43,598 completed、0 active、0 unplanned。旧 wrapper 的 `planned_count=43598` 只数新增活动路径键；旧 `outputstarttime.txt` 实际有 43,599 次成功规划，不能把这两个计划计数混为一项。

仅两条 lifecycle 的完成时刻字段不同，均属于袋 2806：旧 FIFO 关联把唯一 raw-ID completion 28708 归给 `storage_out`，`storage_in` 为空；新精确执行身份给出 `storage_in` 完成 28708、`storage_out` 完成 28501。其他 43,597 段的完成时刻也一致。旧完成段真实归属的档案歧义仍保留，不能声称事后无歧义恢复了旧物理轨迹。

## 源端等待来自什么规则

可读 legacy 代码有直接支持：

- [`HcaSegmentIdentityBenchmark.java`](../../benchmarks/java/HcaSegmentIdentityBenchmark.java) 487–490 行沿用 `(int)(left.pass_time−right.pass_time)` 排序；313、319 行每个 epoch 先 `generate_tasks`，后 `ICS_path_finding`。本诊断没有用别的排序器替换原生顺序。
- [`Tasks.java`](../../legacy/jichang_origin_readonly/src/App/Tasks.java) 149–168 行每个可释放源节点只尝试一个队头任务，且源端已有未规划任务时不再释放；`contains` 在 213–219 行按未规划任务的源节点判断。队头需满足 `D−epoch<1`，所以分数 D 最早可在 floor(D) 满足条件。
- [`ICS_PathFinding.java`](../../legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java) 138–150 行把新任务加入待规划列表；`Astar.research` 没找到路径时放回列表。因为源端生成发生在这一轮规划之前，前一任务在 P 时刻规划成功，下一同源任务最早到 P+1 才解除这项源端阻塞。

以**观察到的同源顺序和成功规划时刻**作为条件，逐段重放 `R_i = max(8260, floor(D_i), P_前一同源段+1)`；每源首段不含最后一项。43,599 段全部精确匹配原生 release。它解释了这些时刻与源端一段/epoch、待规划阻塞规则的关系，不是独立重跑 A*，也没有声称定位每一次规划失败的具体节点约束。

| 源节点 | 段数 | release−D 均值，秒 | release−D 最大值，秒 | 已释放后规划等待总和，秒 |
|---|---:|---:|---:|---:|
| 49 | 2807 | 30277.943677 | 50198.774440 | 62288 |
| 53（EBS 出库源） | 15093 | 3077.315179 | 7714.000000 | 41779 |

源 49、53 的等待已在旧日志中逐段存在。它们的“规划等待总和”描述成功规划前的实际等待；不能把不同源的该数值相加当作全系统额外墙钟时间或独立因果效应。

最大 THT 的袋 6559 提供直观例子：入库段 D=25175.12768、R=75373、P=75375、E=75587；出库段 D=29400、R=36603、P=36605、E=37104。两段共同 D 时延之和为 58115.87232 秒，与旧记录相同。出库完成早于入库完成也再次体现现有共同“独立 scheduled EBS 段”合同；该例不证明真实 EBS 的物理先后保管过程。

## 输入、方法与报告边界

新旧使用同一 workload identity SHA `2cd93fd7a8f79b0fd5996ec52e65121a03ea6a4a05a8646617989410245da918`；实际 raw/canonical/map 哈希逐文件相同，28,506 原始袋、43,599 段。两次原生 summary 的速度 2.5 m/s、start epoch 8260、90000 次 epoch、末 epoch 98259、无故障/无修复、无新任务截断均一致。

此次新 Java 使用 source 主聚合 `74c1a899b879b0523d039e9fa650ef3c860557c7fc96e80ff3a8978ae3faf92c`、class 主聚合 `1fbd4c494aa21a34380ddcde6606a3a0d93883533144f0546a903ccf04a872b3`；寻路 App 源码及上述源端规则保持，新增执行 ID 与允许七列后缀读取不改变共同业务输入。旧运行当时的 source/class 身份缺口仍存在，不能以当前可读 App 源码补造旧运行时身份。

报告可以说明“这一格的大量源端等待在旧档案已存在，主要是计时起点容易混淆；修复使漏段袋重新获得完整人口计时资格”。不能据此声称全部 60 格轨迹不变、其余负载未劣化、修复没有影响预约，或用旧完成子集替代全人口比较。新的 Python scratch 清理优化只影响文件清理开销；本诊断不将墙钟变化当作路由算法变化，后续统一版本的数值等价仍以对应预检比对为准。

复核本单格诊断（只读取现存事件并重写独立诊断 JSON，不运行 Java）：

```powershell
python scripts/eval/diagnose_hca_segment_identity_release_delay.py
```
