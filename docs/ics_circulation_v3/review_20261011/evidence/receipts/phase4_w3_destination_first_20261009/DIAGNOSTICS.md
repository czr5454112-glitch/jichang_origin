# Destination-first：完整分母与事后机制诊断

本文件仅分析已冻结的 1,872 个 episode，未新增仿真、训练、调参或规则修改。所有例子均为**事后解释性选择**，不是新的独立确认、模型选择或支配性证明。生成脚本：[analyze_decision_mechanisms.py](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/analyze_decision_mechanisms.py>)；逐项事件、原始评分、候选、每袋时刻及来源 SHA：[decision_mechanism_evidence.json](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/decision_mechanism_evidence.json>)。

## 整体结果与读法

36 个已使用过的名义/压力 tape × 26 个冻结策略 × 原版/规则版 = **1,872 次运行、936 对**。没有执行异常；936 个原版全部复现各自历史物理结果。规则版不是统一改善：成本 **236 对降低、541 对相同、159 对升高**。两侧各有 5,148 个任务实例，完成数 **4,960→5,137**，准时数 **3,628→3,886**，ΣJ **23,871.4→15,751.2**。规则仍有 11 个未完成任务，详见下表。独立审计已保存于 [destination_audit_final.json](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_diagnostic_audit_20261009/destination_audit_final.json>)，101,586 项检查没有错误。

固定代价为 `J = tray_wait + nonprotected_tardiness + 0.1×empty_distance + 10×terminal_backlog + 2×terminal_inflight`。`tray_wait` 仅累计尚未装载的已到达任务；途中时间和已装载后的等待不直接计入该项。`nonprotected_tardiness` 是迟到 tick 之和，未完成任务计至 horizon；它不是“不准时任务数”。`empty_distance` 在本离散代理中累计空行驶边的 travel_time。故减少缺盘等待可以伴随更晚的完成，也可能出现 ΣJ 改善但二元准时率下降；本轮不存在另加的准时个数硬罚。所有实际候选仍需正常权限与容量校验。

全表保留全部策略及 seed。R0 是原始训练，R1 是各自策略回收，SHARED 是每折六 owner 共同回收数据；23/31 为特征数，D/R 分别为 paired_direct/residual，尾数为 seed。`原→规则` 是同策略同 tape 的配对值，`ΔΣJ=规则−原`，负数较好；好/同/差是逐 episode 成本比较。完成与准时分母使用全部计划任务，失败不从分母排除（本轮没有执行异常）。baseline/timed 的合法卸载本已在第一动作完成，所以没有实际覆盖。

### 名义（每策略 4 对、24 个任务实例）

| 策略 | 完成/任务：原→规则 | 准时：原→规则 | ΣJ 原→规则 | ΔΣJ | 成本好/同/差 | 实际覆盖 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 24→24/24 | 18→18 | 58.4→58.4 | +0.0 | 0/4/0 | 0 |
| timed | 24→24/24 | 18→18 | 58.4→58.4 | +0.0 | 0/4/0 | 0 |
| R0-23-D17 | 16→24/24 | 10→14 | 483.1→79.4 | -403.7 | 3/0/1 | 13 |
| R0-23-D29 | 23→24/24 | 13→16 | 115.4→73.4 | -42.0 | 2/0/2 | 14 |
| R0-23-D43 | 15→24/24 | 10→16 | 613.2→73.4 | -539.8 | 2/1/1 | 11 |
| R0-23-R17 | 24→24/24 | 13→15 | 98.4→74.4 | -24.0 | 2/2/0 | 5 |
| R0-23-R29 | 23→24/24 | 9→17 | 163.4→75.4 | -88.0 | 4/0/0 | 14 |
| R0-23-R43 | 22→24/24 | 12→16 | 139.4→72.4 | -67.0 | 1/3/0 | 8 |
| R0-31-D17 | 24→24/24 | 17→17 | 60.4→60.4 | +0.0 | 0/4/0 | 0 |
| R0-31-D29 | 24→24/24 | 17→17 | 60.4→60.4 | +0.0 | 0/4/0 | 0 |
| R0-31-D43 | 24→24/24 | 17→17 | 60.4→60.4 | +0.0 | 0/4/0 | 0 |
| R0-31-R17 | 24→24/24 | 18→18 | 57.4→57.4 | +0.0 | 0/4/0 | 0 |
| R0-31-R29 | 24→24/24 | 18→18 | 58.4→58.4 | +0.0 | 0/4/0 | 0 |
| R0-31-R43 | 24→24/24 | 18→18 | 59.4→59.4 | +0.0 | 0/4/0 | 0 |
| R1-31-D17 | 24→24/24 | 17→17 | 64.4→63.4 | -1.0 | 1/2/1 | 10 |
| R1-31-D29 | 24→24/24 | 17→17 | 53.4→57.4 | +4.0 | 0/2/2 | 8 |
| R1-31-D43 | 24→24/24 | 18→17 | 64.4→60.4 | -4.0 | 1/2/1 | 8 |
| R1-31-R17 | 24→24/24 | 18→18 | 56.4→57.4 | +1.0 | 0/3/1 | 6 |
| R1-31-R29 | 24→24/24 | 17→18 | 65.4→56.4 | -9.0 | 2/2/0 | 9 |
| R1-31-R43 | 24→24/24 | 18→18 | 57.4→59.4 | +2.0 | 0/3/1 | 9 |
| SHARED-31-D17 | 24→24/24 | 17→17 | 61.4→57.4 | -4.0 | 1/3/0 | 7 |
| SHARED-31-D29 | 24→24/24 | 17→17 | 60.4→57.4 | -3.0 | 1/3/0 | 8 |
| SHARED-31-D43 | 24→24/24 | 17→17 | 60.4→62.4 | +2.0 | 0/3/1 | 4 |
| SHARED-31-R17 | 24→24/24 | 18→18 | 54.4→56.4 | +2.0 | 0/3/1 | 3 |
| SHARED-31-R29 | 24→24/24 | 18→18 | 61.4→58.4 | -3.0 | 1/3/0 | 8 |
| SHARED-31-R43 | 24→24/24 | 18→18 | 57.4→59.4 | +2.0 | 0/3/1 | 7 |

### 压力（每策略 32 对、174 个任务实例；复用旧 8 个 stress tape/stream）

| 策略 | 完成/任务：原→规则 | 准时：原→规则 | ΣJ 原→规则 | ΔΣJ | 成本好/同/差 | 实际覆盖 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 174→174/174 | 142→142 | 501.3→501.3 | +0.0 | 0/32/0 | 0 |
| timed | 174→174/174 | 142→142 | 501.3→501.3 | +0.0 | 0/32/0 | 0 |
| R0-23-D17 | 131→169/174 | 78→108 | 2568.5→767.9 | -1800.6 | 29/0/3 | 82 |
| R0-23-D29 | 151→171/174 | 96→112 | 1638.3→705.7 | -932.6 | 20/1/11 | 87 |
| R0-23-D43 | 117→171/174 | 71→113 | 3548.3→701.7 | -2846.6 | 24/3/5 | 76 |
| R0-23-R17 | 156→174/174 | 88→116 | 1141.1→597.4 | -543.7 | 22/5/5 | 57 |
| R0-23-R29 | 161→174/174 | 74→118 | 1166.8→685.4 | -481.4 | 25/1/6 | 82 |
| R0-23-R43 | 161→174/174 | 87→114 | 1009.8→602.0 | -407.8 | 23/3/6 | 67 |
| R0-31-D17 | 174→174/174 | 133→134 | 532.1→530.1 | -2.0 | 1/31/0 | 1 |
| R0-31-D29 | 174→174/174 | 133→134 | 521.3→524.1 | +2.8 | 1/30/1 | 4 |
| R0-31-D43 | 174→174/174 | 133→134 | 539.2→539.1 | -0.1 | 1/29/2 | 5 |
| R0-31-R17 | 174→174/174 | 140→142 | 488.2→480.4 | -7.8 | 3/25/4 | 16 |
| R0-31-R29 | 174→174/174 | 141→142 | 470.3→475.4 | +5.1 | 1/29/2 | 16 |
| R0-31-R43 | 174→174/174 | 140→142 | 481.2→482.4 | +1.2 | 2/27/3 | 16 |
| R1-31-D17 | 174→174/174 | 128→134 | 547.9→537.4 | -10.5 | 11/12/9 | 44 |
| R1-31-D29 | 174→174/174 | 125→131 | 531.0→519.4 | -11.6 | 8/17/7 | 38 |
| R1-31-D43 | 174→174/174 | 132→134 | 566.0→539.1 | -26.9 | 5/23/4 | 31 |
| R1-31-R17 | 174→174/174 | 137→141 | 469.1→464.6 | -4.5 | 5/17/10 | 41 |
| R1-31-R29 | 174→174/174 | 137→142 | 480.1→475.4 | -4.7 | 7/15/10 | 50 |
| R1-31-R43 | 174→174/174 | 140→142 | 462.6→484.4 | +21.8 | 4/17/11 | 57 |
| SHARED-31-D17 | 174→174/174 | 135→134 | 472.5→505.2 | +32.7 | 1/24/7 | 24 |
| SHARED-31-D29 | 174→174/174 | 128→130 | 489.7→544.0 | +54.3 | 4/19/9 | 38 |
| SHARED-31-D43 | 174→174/174 | 132→134 | 541.8→526.9 | -14.9 | 4/23/5 | 25 |
| SHARED-31-R17 | 174→174/174 | 140→142 | 483.9→473.4 | -10.5 | 4/22/6 | 29 |
| SHARED-31-R29 | 174→174/174 | 138→142 | 454.2→477.4 | +23.2 | 5/17/10 | 42 |
| SHARED-31-R43 | 174→174/174 | 140→142 | 462.0→482.4 | +20.4 | 5/17/10 | 47 |

这些总数不能把较弱 R0-23 的大收益外推给更强模型。例如 SHARED-31-D17 压力 ΣJ 增加 **32.7**、准时 **135→134**；SHARED-31-D29 压力 ΣJ 增加 **54.3**，但准时 **128→130**。准时数与总代价是不同统计量；全部 seed 均保留，没有挑最好 seed。

## A：一次真实卸载覆盖，随后空盘调拨竞争导致少一个准时任务

**SHARED-31-D17，L2_D1_slack3 / stress_1**。[原版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D1_slack3__stress_1/shared__physical31__paired_direct_seed17__original.json>)；[规则版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D1_slack3__stress_1/shared__physical31__paired_direct_seed17__destination_first.json>)。所有数组索引均为 **0-based JSON 数组索引**。

`destination_first_history[4]` 是首次且唯一覆盖：t=28，`round1:need` 在最终目的地 C、盘 `donor`；两版 `delegate_records[0].state_sha256` 和 K4 池相同。原评分为 `[0, -0.131861, -0.128647, -0.037551]`，原选择 index 1 的离站见证，规则选择经校验的 index 0：`legs=[]`、`prefix_only=false`，t=29 卸载完成。原版在 C→S→B 的实际反复运动后，至 t=41 才完成同一袋。这里不是把 witness 整条当成执行；路径由 `result.trace` 确认。

卸载后的实际耦合链如下：

1. 规则 `slow_history[17]` 在 t=34 接纳 donor 的完整空盘调拨：`CS[40,41), SX[41,43), XB[43,44)`，供应未来 B 队列。原版 donor 此时仍带袋绕行，直到 `slow_history[21]` t=42 才空盘调拨 `CS[42,43), SX[43,45), XB[45,46)`。
2. t=38，另一盘 `loaded` 从 G 反应式返回 S，服务已到达的 `round2:loaded`。原版 `trace[103,107,109,114]` 为 GC 出发38、C到达40、CS出发40、S装载41；规则 `trace[89,93,97,101]` 为 GC出发38、C到达40、CS出发41、S装载42。CS 容量为1，规则 donor 的 `[40,41)` 实际占用导致这一次推迟。
3. 规则 S 的 `destination_first_history[5]` 是正常 delegate 选路，**没有卸载覆盖**：SX 只能在43出发（donor 正占 `[41,43)`），XG45→47，48卸载。原版 `history[10]` 为 SX41→43、XG43→45，46卸载。规则 `trace[96,104,105,112,120]` 保存 donor SX41、donor XB43、loaded SX43、loaded XG45、loaded 卸载48。

| 任务（实际 origin→destination） | 到达/截止 | 装载：原→规则 | 卸载完成：原→规则 | 缺盘等待Δ | 迟到tick Δ |
|---|---:|---:|---:|---:|---:|
| `initial` (S→G) | 0/8 | 0→0 | 5→5 | +0 | +0 |
| `need:0` (B→C) | 2/22 | 5→5 | 8→8 | +0 | +0 |
| `round1:loaded` (S→G) | 20/28 | 23→23 | 28→28 | +0 | +0 |
| `round1:need` (B→C) | 26/46 | 26→26 | 41→29 | +0 | +0 |
| `round2:loaded` (S→G) | 38/46 | 41→42 | 46→48 | +1 | +2 |
| `round2:need` (B→C) | 42/62 | 46→44 | 49→47 | -2 | +0 |

完整成本 **14.8→15.8**：`tray_wait 13→12`（round2:need 早装2 tick，但 round2:loaded 晚装1 tick），`tardiness 0→2`，`empty_distance 18→18`，终端两项均0。因此 **ΔJ=−1+2=+1**，任务 `round2:loaded` 由截止46恰好完成变48，准时数少1。更早卸载的那袋本身改善，并不阻止其可用空盘触发慢层预约后损害另一个任务。

## B：另一 seed 的回退——托盘所在位置改变，接续队列缺盘且 delegate 改选较慢支路

**SHARED-31-D29，L4_D3_slack0 / stress_3**。[原版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D3_slack0__stress_3/shared__physical31__paired_direct_seed29__original.json>)；[规则版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D3_slack0__stress_3/shared__physical31__paired_direct_seed29__destination_first.json>)。本例两次覆盖在规则 `history[2]`、`history[6]`，不是对单个动作的隔离实验。

首次覆盖在 t=11，`need:0`/donor 到 C；两版同一状态和 K4 池。原评分 `[0, -1.416463, -1.372232, -0.659709]` 选 index1 离开 C；规则零边卸载12完成，原版绕 C→S→B→C 后20完成。这个提前释放使 `slow_history[7]` t14 选 **donor** 去 B（CS20→21、SX21→25、XB25→26）；原版 donor 还载袋，直到 `slow_history[9]` t18 选 **loaded** 从 G 去 B（GC18→20、CS20→21、SX21→25、XB25→26）。实际 stress tape 没有 round1:need，但14时已经发布过这项预测，两版都按可见预测运行，没有使用该袋实际不会到达这一未来真值。

由此 t32 后两盘位置互换：原版 donor 完成 round1:loaded 在G，loaded 空盘在B；规则 loaded 完成 round1:loaded 在G，donor 空盘在B。t42 服务 round2:loaded 时，两版反应式均派 donor 返回S；原版从G出发，规则从B出发（原 `trace[90,91,94,100,103]`；规则 `[84,85,88,92,96]`），均45装载。但规则把B唯一盘带走了：t44 round2:need 到B时，原版直接用原地loaded盘装载；规则需要让loaded从G经C、S、X返回B（`trace[91,93,100,102,104,106,112,115]`），52才装载，**多等8 tick**。

另一个分歧可直接核验，不能误称为物理上只有慢路可走：t45 两版的正常 K4 候选见证相同，但可见状态与 MLP 评分不同。原版 `history[7]` 的分数 `[0, 0.790186, 3.231925, -2.476360]` 选 index3，实际安全前缀 SX45→49、XG49→51，随后到G再决定卸载52；规则 `history[4]` 的分数 `[0, -2.483425, 2.129369, -1.812885]` 选 index1，实际 SY45→49、YG49→54，卸载55。**规则版同池仍有 SX45→49、XG49→51 的合法候选**，因此这3 tick 完成回退是变化后的 delegate 评分选择，不能写成“拥堵强迫走SY”。规则的第二次零边覆盖 t54 使 round2:need 于55完成，反而早于原版59；但这没有消除先前8 tick 的缺盘等待。

| 任务（实际 origin→destination） | 到达/截止 | 装载：原→规则 | 卸载完成：原→规则 | 缺盘等待Δ | 迟到tick Δ |
|---|---:|---:|---:|---:|---:|
| `initial` (S→G) | 0/7 | 0→0 | 7→7 | +0 | +0 |
| `need:0` (B→C) | 6/26 | 9→9 | 20→12 | +0 | +0 |
| `round1:loaded` (S→G) | 20/27 | 22→23 | 32→32 | +1 | +0 |
| `round2:loaded` (S→G) | 42/49 | 45→45 | 52→55 | +0 | +3 |
| `round2:need` (B→C) | 44/64 | 44→52 | 59→55 | +8 | +0 |

成本 **18.6→31.2**：等待 **8→17**（round1:loaded +1、round2:need +8），迟到 **8→11**（round2:loaded +3），空行驶 **26→32**（加权+0.6），终端均0。故 **ΔJ=9+3+0.6=12.6**。准时数不变：round2:loaded 在两版都已迟到，仅迟到程度扩大。这条轨迹同时展示了空盘分配变化与后续模型选择变化，不能把全部代价归于首次卸载的局部耗时。

## C：明确正例——打断到站后继续带袋绕行，释放有限盘完成后续任务

**R0-23-D43，L4_D1_slack3 / nominal**。[原版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__nominal/r0__paired23__paired_direct_seed43__original.json>)；[规则版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__nominal/r0__paired23__paired_direct_seed43__destination_first.json>)。这是本次保存结果中成本改善最大的单对，特意作为事后机制例，不能作为平均效应或新确认。

首次覆盖 `history[2]`，t8 need:0 到C；原版继续CS8→9并再选S→G→C，之后多次经过C都离开，horizon72仍载有need:0。规则零边卸载t9（`trace[28]`），接着慢层 `slow_history[7]` t14 将同盘送B，26装载round1:need（`trace[63]`），t28第二次零边覆盖，29完成（`trace[73]`）；34时再预调同盘，46装载round2:need（`trace[113]`），t48第三次覆盖，49完成（`trace[123]`）。原版 need:0 一直占 donor，后续 B 队列不能获得这份真实盘供给。另一盘原版带round1:loaded也持续绕行；规则的变化后正常delegate选择经Y到G，并完成后续S任务。没有增加盘或删除积压。

| 任务（实际 origin→destination） | 到达/截止 | 装载：原→规则 | 卸载完成：原→规则 | 缺盘等待Δ | 迟到tick Δ |
|---|---:|---:|---:|---:|---:|
| `initial` (S→G) | 0/10 | 0→0 | 8→8 | +0 | +0 |
| `need:0` (B→C) | 6/26 | 6→6 | 未完成→9 | +0 | -46 |
| `round1:loaded` (S→G) | 20/30 | 23→23 | 未完成→31 | +0 | -41 |
| `round1:need` (B→C) | 26/46 | 未完成→26 | 未完成→29 | -46 | -26 |
| `round2:loaded` (S→G) | 40/50 | 未完成→43 | 未完成→51 | -29 | -21 |
| `round2:need` (B→C) | 46/66 | 未完成→46 | 未完成→49 | -26 | -6 |

成本 **301.9→10.4**，完成 **1→6**，准时 **1→4**。分项为等待 **107→6**、迟到 **142→2**、空行驶 **9→24**、末端未完成 **5→0**、末端在途 **1→0**：`ΔJ=−101−140+1.5−50−2=−291.5`。空行驶反而增多，因为释放出的盘确实承担了后续供给；收益来自解除占盘和积压，并非只减少行驶距离。

## D：同一 seed 的较大成本回退，准时个数却没有进一步下降

**SHARED-31-D17，L2_D3_slack0 / stress_6**。[原版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D3_slack0__stress_6/shared__physical31__paired_direct_seed17__original.json>)；[规则版 episode](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D3_slack0__stress_6/shared__physical31__paired_direct_seed17__destination_first.json>)。规则覆盖索引2/5/8分别在t8/28/46的C目的地，将need:0、round1:need、round2:need完成时刻15→9、35→29、53→47。第一次释放后，t14慢层改由donor承担B供给，而原版当时用loaded从G去B；t34规则又提交donor的CS40→41、SX41→43、XB43→44空盘调拨。两个S任务因供盘/共享边时序变化，装载各晚3、完成各晚4（24→28、44→48）。对应规则正常决策为 `history[3]` SX23→25和 `history[6]` SX43→45；原版为 `history[5]` SX19→21和 `history[10]` SX39→41。详见证据 JSON 的全部 indexed trace 与 per_bag。

本例 `wait 2→8`、`tardiness 5→13`、`empty_distance 18→18`，因此 **J8.8→22.8，ΔJ=14**。两个S任务原本已迟到，故迟到总 tick 增加8但准时个数不变。这与例A“刚好跨越截止导致准时数下降”是不同机制口径。

## 规则下仍未完成的 11 个任务

| 场景 / tape | 策略 | 未完成任务 / 实际 OD | 该袋决策次数 | 到目的地决策/覆盖次数 |
|---|---|---|---:|---:|
| L2_D3_slack0 / stress_5 | [R0-23-D17](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D3_slack0__stress_5/r0__paired23__paired_direct_seed17__destination_first.json>) | `round2:need` C→B | 8 | 0 / 0 |
| L2_D3_slack0 / stress_5 | [R0-23-D29](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D3_slack0__stress_5/r0__paired23__paired_direct_seed29__destination_first.json>) | `round2:need` C→B | 8 | 0 / 0 |
| L2_D3_slack0 / stress_5 | [R0-23-D43](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L2_D3_slack0__stress_5/r0__paired23__paired_direct_seed43__destination_first.json>) | `round2:need` C→B | 8 | 0 / 0 |
| L4_D1_slack3 / stress_0 | [R0-23-D17](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__stress_0/r0__paired23__paired_direct_seed17__destination_first.json>) | `round2:loaded` S→G | 13 | 0 / 0 |
| L4_D1_slack3 / stress_0 | [R0-23-D29](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__stress_0/r0__paired23__paired_direct_seed29__destination_first.json>) | `round2:loaded` S→G | 13 | 0 / 0 |
| L4_D1_slack3 / stress_0 | [R0-23-D43](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__stress_0/r0__paired23__paired_direct_seed43__destination_first.json>) | `round2:loaded` S→G | 13 | 0 / 0 |
| L4_D1_slack3 / stress_1 | [R0-23-D17](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__stress_1/r0__paired23__paired_direct_seed17__destination_first.json>) | `round2:loaded` S→G | 10 | 0 / 0 |
| L4_D1_slack3 / stress_4 | [R0-23-D17](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D1_slack3__stress_4/r0__paired23__paired_direct_seed17__destination_first.json>) | `round1:loaded` S→G | 17 | 0 / 0 |
| L4_D3_slack0 / stress_2 | [R0-23-D17](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D3_slack0__stress_2/r0__paired23__paired_direct_seed17__destination_first.json>) | `round1:need` C→B | 11 | 0 / 0 |
| L4_D3_slack0 / stress_2 | [R0-23-D29](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D3_slack0__stress_2/r0__paired23__paired_direct_seed29__destination_first.json>) | `round1:need` C→B | 11 | 0 / 0 |
| L4_D3_slack0 / stress_2 | [R0-23-D43](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/units/stream_L4_D3_slack0__stress_2/r0__paired23__paired_direct_seed43__destination_first.json>) | `round1:need` C→B | 11 | 0 / 0 |

这11个实例全部来自 R0-23 paired_direct，seed17/29/43分别5/3/3个。对**这些袋本身**，真实 selector 从未在其实际 destination 调用（0次），所以没有合法零边卸载机会、也没有覆盖。这不是规则绕过了一个已存在的卸载候选。保存的实际节点序列反复经过非目标C/S/G或C/S/B；最终仍由真实盘携带并在途中。这里描述的是horizon72内的未完成，不能证明无限期饥饿。压力tape会改变实际OD，表中的C→B/S→G采用实际bag身份，不能凭任务名字把need一律当B→C。详细时刻、最终盘及来源SHA见 [remaining_tasks_diagnostic.json](<C:/PROGRAMING/czr005/outputs/experiments/ics_circulation_v3/phase4_w3_destination_first_20261009/remaining_tasks_diagnostic.json>)。

## 可以得出的机制结论与边界

1. 合法到站卸载能避免某些带袋离站循环，并把有限盘归还后续调度；在较弱23维模型上这是主要改善来源。
2. 它**不是当前闭环代价下的无条件支配动作**。卸载改变真实空盘何时/何地可用，慢层可据此作新的不可撤预约，正常路由也会在变化后的可见状态选择不同动作。例A给出只有一次覆盖的实际资源冲突链；例B同时保留空盘分配和MLP改选的证据。
3. 当前规则仅覆盖“已经到实际终点且正常池内有合法完整零边卸载”的边界。非目的地循环、无候选、到不了目标等问题仍由原控制器处理；11个未完成实例界定了这个覆盖范围。
4. 全部36 tapes复用既有开发条件，模型/规则有相关性，1872次运行不是1872个独立样本；没有从这些事后例子推断统计显著性、现场表现或新工况泛化。不同seed不筛选。原版936次完整物理复现是这些条件下的兼容证据，不是全局cache无影响定理。
5. 本分析没有重新演算“只改一次然后强迫后续不变”的反事实，也没有用结果修改规则。候选后缀是可行见证，实际next-edge执行以事件trace为准。后续若设计新规则/约束，应单独预声明并保留本次反例，不能将经验直觉写成强制卸载定理。
