# G4IRSF31 南宁地图可移植实验协议

## 目标和边界

G31 在同一份南宁拓扑、同一份行李流和同一固定仿真窗口内，比较原始集中式 HCA* 与当前 S4/J2/E2 节点局部决策框架。协议先于正式算法结果冻结；线路选择只使用 151 节点、227 条有向边的拓扑和 1× 投影业务量，不读取 HCA 或 S4 的结果。

两档业务量为：

- 1×：28,506 件 raw bag、43,603 个 segment、360 个航班；
- 2×：57,012 件 raw bag、87,206 个 segment、720 个航班。2× 在 raw 航班层插入完整航班，不复制已展开的 segment，也不压缩业务日。

两种算法都使用相同的 early-bag 判定 `STD - EntryTime >= 4800 s` 和 `storage-out = STD - 2700 s`。南宁工作簿没有标明真实 EBS，因此两臂固定使用同节点代理 `53 -> 53`（`IDK1 / ICS54`，原表类型 7“空托盘存储”）。它是公开的实验代理，不被描述为南宁机场真实 EBS。

## 公平比较的共同条件

- 固定窗口：epoch 8,260 到 98,259，不因 2× 或故障延长；
- 相同地图、raw population、expanded lifecycle、速度和故障边；
- HCA 保持原集中式逐任务 A* 与全局预约表，S4 保持 S4/J2/E2、节点局部 FIFO 和 service-aware static potential；S4 固定为 `local_queue_capacity=0`：no configured software queue cap; service calendar/R3 and E4/J2 retained; capacity-triggered PIBT relief inactive；S4 只额外读取直接相邻汇流节点已有的 service-calendar 标量，并沿用既有 calendar-wait 权重，E4/J2 仍是唯一授权与预约路径；
- S4 每个转向点只选择下一条边，不增加 learning、完整路径规划器或新的策略层；
- 正式 cell 每臂运行一次独立进程。只有进程失败或工件不完整时重跑，不把 canary 当作正式重复；
- 运行时吞吐仅作实现诊断，不替代仿真时钟中的业务完成量和 TTH。

胜负先比较固定 raw 分母上的完成件数。完成件数不同，较高者胜；若两者都达到 100% 或同一拓扑可达上限，则记合理上限平局。只有两臂完成同一个完整可比较 cohort 时，才比较 TTH；禁止用未完成运行的幸存者均值作正式胜负。

## Table 5.2：四种速度

1× 和 2× 分别运行 `1.5、2.0、2.5、3.0 m/s`。每个 cell 的两臂都把所有物理边设为同一速度，并用各自与该速度一致的启发式/静态势能。

若两臂都完整完成固定 population，主报告沿用论文的 `min / mean / max TTH`；`P95 / P99` 作为尾部补充。若一臂未完整完成，则该 cell 由固定分母完成量形成容量判定，TTH 判定为 `NOT_APPLICABLE_BASELINE_INCOMPLETE` 或对应的非完整状态。

## Table 5.3：算法比较边界

南宁地图在 2.5 m/s 上的 fresh HCA* 与 fresh S4 是同图、同业务的有效新实验，可以作为 G31 的两算法比较。它不是原论文 `dispersed heuristic` 实现的 exact 复现：仓库没有恢复该方法在南宁图上的可执行实现。因此：

- fresh HCA* 与 fresh S4 可以形成南宁地图 head-to-head 结论；
- 原论文 Table 5.3 的旧地图数字只能列作历史背景；
- 不能把跨地图的 archived 数值算成 G31 的 fresh 胜负或百分比提升。

## Table 5.4：速度偏差边界

仍保留论文的 12 格组织：标准速度 `1.5、2.0、2.5、3.0 m/s` 与偏差标签 `10%、20%、30%`。但原动态/静态偏差模拟器、随机偏差流和 HCA 中“标准速度规划、实际速度执行”的双速度接口没有恢复。

当前可执行项明确标为 `LEGACY_VARIANT_RECONSTRUCTION_NON_EXACT`：物理边速度和静态势能都保持标准速度，只在 S4 的局部位置观测与冲突预测时间上加入固定种子 `20260816` 的确定性 `U(0,k s)` 延迟，其中 `k=1、2、3` 分别对应三个偏差标签。相同速度的无偏 HCA cell 只是更容易的保守参照，不是 matched-disturbance 对照；这 24 格（1×/2× × 4 速度 × 3 标签）只作次级上下文，不驱动 fresh target，也不得与 archived dynamic/static 数字合并成“原实验全胜”。若以后恢复真正的双速度 baseline，再单独提升 evidence 等级，不改写本轮结果。

原地图 map2 使用完全相同的 24 格 `U(0,k s)` 合同和固定种子，唯一变化是加载 map2 的拓扑、1× 原人口与按 G29 逻辑生成的 2× 人口。`run_g4irsf31_map2_bias.py` 直接复用 map2 final-policy 请求和上述 NON_EXACT 偏差合同；其工件明确排除在 fresh exact 与 cross-map target 之外。

## Table 5.5：南宁 8 条线路

候选池只包含满足下列条件的边：不是 loader、unloader 或 type-7 storage 的入口/出口边；托盘容量大于 0；在 2.5 m/s 的 1× 名义最短路径上有真实业务暴露。这样排除了唯一容量为 0 的 `DD3 -> DD4`，也避免用单一卸载口末端边制造显然的不可达结果。

| Line | Dense edge | Source identity | Length / capacity | 1× nominal leg exposure | 选择依据 |
|---:|---|---|---:|---:|---|
| 1 | `50 -> 25` | `IU25(ICS51) -> ID26(ICS26)` | 21.90 m / 10 | 19,091 | 国际区：单边删除仍全可达的内部主干中业务暴露最高 |
| 2 | `28 -> 29` | `IU3(ICS29) -> IU4(ICS30)` | 5.00 m / 2 | 13,698 | 国际区：会阻断部分业务的正容量内部边中业务暴露最高 |
| 3 | `94 -> 76` | `DU38(ICS100) -> DU20(ICS82)` | 19.90 m / 9 | 11,208 | 国内区：单边删除仍全可达的内部主干中业务暴露最高 |
| 4 | `78 -> 80` | `DU22(ICS84) -> DU24(ICS86)` | 2.70 m / 1 | 10,905 | DU 环：会阻断业务的正容量内部支路中业务暴露最高 |
| 5 | `112 -> 113` | `DD18(ICS118) -> DD19(ICS119)` | 3.00 m / 1 | 6,405 | DD 环：单边删除造成的 raw-bag 可达损失最大 |
| 6 | `29 -> 112` | `IU4(ICS30) -> DD18(ICS118)` | 58.70 m / 29 | 10,504 | 两工作簿系统之间业务暴露最高的正容量内部联络边 |
| 7 | `34 -> 55` | `IU9(ICS35) -> IUMES(ICS156)` | 16.65 m / 8 | 15,054 | 进入已标注 recode 节点的边中业务暴露最高 |
| 8 | `100 -> 102` | `DD6(ICS106) -> DD8(ICS108)` | 4.60 m / 2 | 8,416 | 剩余 DD 内部支路中会阻断业务且业务暴露最高 |

“nominal leg exposure”按 raw bag lifecycle 计算：直达 bag 贡献一条 OD leg，early bag 贡献 `source -> 53` 与 `53 -> destination` 两条 leg。它只是选择依据，不是任一算法的完成结果。

### 16 个同形故障场景

故障均在 epoch 8,260 生效并持续到固定窗口结束，不在窗口内修复。组合完全沿用论文的 8 single、5 pair、3 triple 结构；旧地图 `pair_5_7` 的工作簿歧义不迁移到南宁图，本轮始终使用新注册的 line 5 与 line 7。

| Scenario | Lines | 1× topology upper | 2× topology upper |
|---|---|---:|---:|
| `single_1` | 1 | 28,506 (100.00%) | 57,012 (100.00%) |
| `single_2` | 2 | 25,886 (90.81%) | 51,772 (90.81%) |
| `single_3` | 3 | 28,506 (100.00%) | 57,012 (100.00%) |
| `single_4` | 4 | 27,813 (97.57%) | 55,626 (97.57%) |
| `single_5` | 5 | 23,669 (83.03%) | 47,338 (83.03%) |
| `single_6` | 6 | 28,506 (100.00%) | 57,012 (100.00%) |
| `single_7` | 7 | 28,506 (100.00%) | 57,012 (100.00%) |
| `single_8` | 8 | 27,839 (97.66%) | 55,678 (97.66%) |
| `pair_1_7` | 1, 7 | 28,506 (100.00%) | 57,012 (100.00%) |
| `pair_2_4` | 2, 4 | 25,193 (88.38%) | 50,386 (88.38%) |
| `pair_3_5` | 3, 5 | 12,186 (42.75%) | 24,372 (42.75%) |
| `pair_4_5` | 4, 5 | 22,976 (80.60%) | 45,952 (80.60%) |
| `pair_5_7` | 5, 7 | 23,669 (83.03%) | 47,338 (83.03%) |
| `triple_2_4_6` | 2, 4, 6 | 25,193 (88.38%) | 50,386 (88.38%) |
| `triple_3_5_8` | 3, 5, 8 | 12,115 (42.50%) | 24,230 (42.50%) |
| `triple_4_6_7` | 4, 6, 7 | 27,813 (97.57%) | 55,626 (97.57%) |

topology upper 的判定对 early bag 同时要求 `source -> 53` 和 `53 -> destination` 可达，对 direct bag 要求 `source -> destination` 可达。它是删除故障边后的业务可达上限，不是 S4 或 HCA 结果；所有 16 个场景的上限都大于 0，因此没有预先制造“双方必为 0”的无信息 cell。

Table 5.5 的主指标是 `固定窗口内完成 raw bags / 固定 raw population`。拓扑不可达 bag 保留在分母中。若某算法完成数达到上述上限，可记 `TOPOLOGY_SATURATED`；两臂都达到同一上限时是合理上限平局。只有两臂完成同一完整拓扑可行 bag 集时，故障 TTH 才可作为次级比较。

## 可复算文件

- `scripts/eval/run_g4irsf31_nanning_protocol.py`：只读地图和 1×/2× raw workload，生成线路身份、16 个组合和 topology upper；
- `scripts/eval/run_g4irsf31_map2_bias.py`：在原地图上复用同一 24 格 Table 5.4 NON_EXACT 合同；
- `configs/eval/g4irsf31_nanning_fault_scenarios.json`：当前冻结协议；
- `tests/test_g4irsf31_nanning_protocol.py`：检查同形矩阵、同节点 53 EBS 代理、正容量内部边和 1×/2× 上限；
- `scripts/eval/run_g4irsf31_reporting.py`：在南宁 40 个容量 cell、3 个南宁 same-HCA-release 工件、原地图 map2 的 38 个可测容量 cell 与 4 个 1× same-HCA-release 工件全部齐备后，生成 JSON、CSV、Markdown，并用 `--validate-committed` 做逐字节陈旧检查。map2 的 2× HCA 未完成全人口，因此四种速度的时延均为 N/A，但容量仍按 G29 的固定 57,012 分母比较；两图 Table 5.4 aggregate 只作为可选 NON_EXACT 上下文读取，不参与完成门或胜负计数。

生成命令：

```powershell
python scripts/eval/run_g4irsf31_nanning_workload.py --scale 1
python scripts/eval/run_g4irsf31_nanning_workload.py --scale 2
python scripts/eval/run_g4irsf31_nanning_protocol.py
python scripts/eval/run_g4irsf31_nanning_smoke.py --scale 1 --earliest-bags 4
python scripts/eval/run_g4irsf31_map2_bias.py resume --case-root .tmp_g31_map2_bias_dry --dry-run --force
python scripts/eval/run_g4irsf31_reporting.py --validate-committed
```

前两个命令从原始一天航班流按冻结逻辑生成 1×/2× 南宁业务；protocol 命令不启动 full campaign，也不读取任何 HCA/S4 运行结果；smoke 只跑 4 件完整 raw bag，用于确认两种真实实现和所选 Release 后端都能在南宁图上启动；map2 bias 命令只检查 24 格合同和真实输入，不加载 native binary；最后一个命令只读取已提交的聚合与报告，不重跑实验。
