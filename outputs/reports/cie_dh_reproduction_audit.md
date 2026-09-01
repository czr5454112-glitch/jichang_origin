# CIE-DH 表 5.3 复现审计

## 结论

**`ADAPTED_BASELINE`**。当前 `TARAU_LOCAL_2009_CIE_DH_ADAPTED_NOT_EXACT` 不是 `EXACT_REPRODUCTION` 或 `APPROXIMATE_REPRODUCTION`：相对原 CIE 表 5.3 的 DH 行，MIN/MEAN/MAX 绝对相对误差分别为 11.985% / 11.447% / 8.640%，均超过 5% 工程目标。

本审计只使用原表报告的 MIN/MEAN/MAX，不伪造原表未给出的 P95/P99。

## 输入与口径

- 原 CIE 表 5.3 锨点（用户提供）：DH = 3.56 / 4.43 / 8.62 min；IoT-DRPA = 3.13 / 3.96 / 5.98 min。
- 当前 DH 适配产物：`outputs/runtime/cie_baselines/p1_neutral_fifo/tarau_local_2009/canonical/map2_1x.json`。
- 当前 G31 上下文产物：`outputs/runtime/cie_baselines/p1_neutral_fifo/g31/canonical/map2_1x.json`。
- 取值字段：`paper_subjects.full_population_raw_bag_timing.metrics_seconds.paper_network_from_admission`，按 `seconds / 60` 转换为分钟。
- 有符号相对误差：`(current - Table_5_3) / Table_5_3`。

两个产物均使用 map2、1x、2.5 m/s、28,506 件完整 raw-bag 人口、固定窗口 8260–98259，且 28,506 件全部完成；`survivor_or_common_cohort_used=false`。两者共用 binary SHA-256 `884f36f0ceebdb0fd56924fd00fe5c8a1ebef56eb05fac4f53d66306de647155` 和 neutral FIFO 协调。但 canonical release 产物的 `formal_same_hca_release_arm_eligible=false`，因此这是表 5.3 口径审计，不是 same-HCA-release 的跨 arm 因果时延结论。

## DH 复现误差

| 指标 | CIE 表 5.3 DH (min) | 当前 Tarău/CIE-DH 适配 (min) | 有符相对误差 | 5% 目标 |
|---|---:|---:|---:|---|
| MIN | 3.560000 | 3.133350 | -11.985% | FAIL |
| MEAN | 4.430000 | 3.922897 | -11.447% | FAIL |
| MAX | 8.620000 | 7.875230 | -8.640% | FAIL |

负号只表示当前仿真时间更短，不表示复现更忠实。三个指标都超出允差，所以不得为达到 5% 而在该正式 cell 上调整权重。

## IoT-DRPA 数值上下文

G31 S4 不是原 CIE IoT-DRPA 的代码复现。下表只显示数值差异，不赋予 G31 任何 IoT-DRPA 复现等级。

| 指标 | CIE 表 5.3 IoT-DRPA (min) | 当前 G31 S4 (min) | 有符相对差 |
|---|---:|---:|---:|
| MIN | 3.130000 | 3.133350 | +0.107% |
| MEAN | 3.960000 | 3.956810 | -0.081% |
| MAX | 5.980000 | 8.743762 | +46.217% |

MIN/MEAN 的数值接近不足以证明语义复现，且 MAX 差异显著。

## 为什么只能标为适配

1. 当前仿真是 event-driven 节点/边执行；原 CIE/Tarău 语义依赖 DCV/开关和离散位置。
2. 当前没有可一一对齐的输送带离散位置；MOVING 映射为 `scheduled_incoming`，STOPPED 映射为节点队列。
3. 原文的移动/停止惩罚精确系数未公开。当前仅在观察结果前冻结 ordinal 权重 moving:stopped = 1:2，因此必须使用 `...COEFFICIENTS_UNDISCLOSED_NOT_EXACT` 身份。
4. R3 节点服务可行性/互斥资源执行器在两个 arm 中均保留，但不是原文机械开关与入口位置的 exact 模型。
5. 当前完成语义是物理到达目标边界后终止，不再预留/执行目标节点服务；未证明与原表记时终点完全一致。
6. P1 将合流协调统一为 `M1` + `jit_fifo` neutral FIFO，而非复现原研究的静态/动态优先级或机械开关控制。这提高了当前 arm 间公平性，但降低了历史表的忠实复现等级。

## 基线计数边界

`TARAU_LOCAL_2009`、`CIE_DH_2009` 和 `FENG_DH` 是同一 `TARAU_LOCAL_2009_CIE_DH` 家族的别名，只计一个文献基线。不得将别名重复列为多个独立方法或多次获胜。

## 可复现命令

在仓库根目录 `C:\PROGRAMING\czr005\.g4irsf35_worktree` 运行：

```powershell
C:\PROGRAMING\python3.11.9\python.exe scripts/eval/run_g4irsf35_full_population.py --map map2 --scale 1 --arm g31 --coordination neutral_fifo --release-mode canonical --binary build_cie_ablation/python/Release/czr005_cpp.cp311-win_amd64.pyd --output outputs/runtime/cie_baselines/p1_neutral_fifo/g31/canonical/map2_1x.json --force

C:\PROGRAMING\python3.11.9\python.exe scripts/eval/run_g4irsf35_full_population.py --map map2 --scale 1 --arm tarau_local_2009 --coordination neutral_fifo --release-mode canonical --binary build_cie_ablation/python/Release/czr005_cpp.cp311-win_amd64.pyd --output outputs/runtime/cie_baselines/p1_neutral_fifo/tarau_local_2009/canonical/map2_1x.json --force
```

`--force` 会重建同名产物；审计性复运行可将 `--output` 指向新目录，以保留上述已审计 JSON。
