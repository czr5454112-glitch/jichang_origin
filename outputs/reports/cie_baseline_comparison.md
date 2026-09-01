# CIE 基线比较与机制证据报告

状态：**FINAL_READY_EVIDENCE_REPORT**

本报告只汇总当前已经存在且能够追溯到原始运行产物的证据。它不把尚未运行的格子、幸存者子集时延或修复前的 Tarau 数值补成“完整矩阵”。当前工作分支为 **codex/cie-baselines-ablation**，报告起草时 HEAD 为 **e58876320d6d72c185a702ef8a1e38b2fad7e344**。修复版 P1 G31/Tarau 公平对照使用的 C++ 二进制 SHA-256 为 **17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279**；CIE-DH local 冻结适配产物使用 **884f36f0ceebdb0fd56924fd00fe5c8a1ebef56eb05fac4f53d66306de647155**；SSP/S5 扩展运行使用 **639a6af52c3fe707ae929f148b485694c4a3577140e96cf06c41a338b09b9a31**。跨方法表均明确区分这些协议和二进制身份。

## 1. 结论先行

1. **G31 相对原始 HCA 的论文正式科目存在明确、跨地图的性能提升。** 在 1×、相同 HCA 释放、完整 28,506 件人口上，G31 的全人口平均时延相对 HCA 在 map2 降低 11.532%，在南宁降低 24.365%；P95 分别降低 17.599% 和 27.207%，P99 分别降低 23.479% 和 29.495%，最大值分别降低 27.101% 和 71.494%。在 2× 固定时域容量上，G31 两图均完成 57,012/57,012；HCA 在 map2 完成 56,917/57,012，在南宁完成 39,063/57,012。
2. **修复版 TARAU_DISTRIBUTED_2010 已形成合格的 adapted P1 四格结果。** 在同一 17d73f... 二进制和中性 FIFO 下，1× 正式时延另使用相同 HCA 释放，G31 的 mean/P95/P99/max 在 map2 和南宁均低于 Tarau；canonical 容量中，map2 2× 两者都完成全人口，但 Tarau 的截止成功达到 57,012，G31 为 56,872；南宁 2× G31 完成 57,012/57,012，Tarau 完成 47,707/57,012，截止成功分别为 20,963 和 20,767。
3. **修复前的 Tarau 数值继续隔离，但修复后的数值不再隔离。** 旧状态保留为历史审计标签 **QUARANTINED_PRE_FIX_RESULTS_EXCLUDED**：旧评分在 complete_on_goal_arrival=true 时仍把 w==goal 计入 goal queue/service，且公共 candidate_record 会接触不应提供给 Tarau 的 scheduled/calendar/live-two-hop。修复版对 w==goal 直接按终点到达处理，并以专用 route-only candidate record 切断这些动态字段；本报告只接受 SHA=17d73f... 的重跑。
4. **SSP_TIME 是有用但混合的适配基线。** 它在 map2 的平均/尾部时延略差于 G31，在南宁 1× 略好于 G31，但改善均很小；2× 虽完成全部人口，截止成功率也未跨地图优于 G31。因此没有形成可归因的跨地图优势。
5. **S5 动态工作量 oracle 是明确的 NO-GO。** 它不是去中心化文献基线；map2 没有稳定时延收益，南宁 1× 在原始固定人口下少完成 231 件。南宁 2× 也只完成 47,058/57,012（82.5405%），比 G31 少 9,954 件，且耗时 13,386.460 s、执行 8,403,557 次 runtime full-A* 和 4,593,068 次全局 scorer 扫描。不应继续把它包装为论文候选或为它叠加优化补丁。
6. **现有稳定 1× 消融没有发现值得继续叠加机制的跨地图信号。** 18 次运行（9 配置 × 2 地图）均完成全人口，但 Q、I、相邻服务等待、严格势下降、J2/M3→FIFO 和服务率归一化均未给出简单、稳定、可跨图归因的正效应。当前正确动作是保留负结果并停止围绕这些方向叠加 scorer/guard/模式。
7. **所有 2× 正式时延均为 N/A。** map2 的 HCA 少完成 95 件；南宁 HCA 的释放和完成均不是完整 2× 人口。不得报告 G31、CIE-DH、SSP 或 S5 的幸存者/自有释放时延作为正式跨算法结论。

## 2. 论文口径与比较边界

### 2.1 固定实验科目

| 项目 | 1× | 2× |
|---|---:|---:|
| 原始 raw bag 人口 | 28,506 | 57,012 |
| 原始 segment 人口 | 43,603 | 87,206 |
| 固定起始 epoch | 8,260 | 8,260 |
| 固定时域 | 90,000 epochs | 90,000 epochs |
| 固定结束 epoch | 98,259 | 98,259 |
| 速度 | 2.5 m/s | 2.5 m/s |
| canonical pass_time 范围 | 8,267.845453–81,900 | 8,267.845453–82,800 |

完成量分母始终是固定 raw bag 全人口。截止成功定义为完整 raw bag 且其所有 segment 的最大完成时刻不晚于 STD。未完成任务保留在分母中。

### 2.2 时延口径

正式跨算法时延只采用相同 HCA segment release 的完整人口：

**THT(raw bag) = Σsegments(finish_time − HCA segment release epoch)**

报告 min、mean、P95、P99、max。只有双方完成同一固定人口时才有效；不允许幸存者子集或事后共同完成子集。候选在 canonical/自有释放下的时延只能作为运行诊断，不能替代正式科目。

### 2.3 必须分开的协议

| 协议 | 目的 | 当前可进入该协议的证据 |
|---|---|---|
| 原生/项目论文容量协议 | 比较完整系统在固定时域内的业务完成量 | HCA_NATIVE、G31/S4_FULL_NATIVE；SSP_TIME 和 S5 作为明确标注的适配/诊断臂 |
| P1 中性 FIFO | 隔离下一跳选择，移除 G31 的 J2/M3 合流优势 | SHA=884f36... 的 G31/CIE-DH local；SHA=17d73f... 的修复版 G31/TARAU_DISTRIBUTED |
| HCA-release 完整人口时延 | 原论文正式跨算法时延 | 1× HCA、G31、SSP、S5；另表报告 P1 的 G31 与 CIE-DH |

不同协调协议之间的数值不得被解释为下一跳策略的因果效应。HCA 也没有被强行改造成一跳方法。

## 3. 方法身份、复现等级与信息边界

| 报告名称 | 身份/等级 | 运行时信息边界 | 本报告处理 |
|---|---|---|---|
| HCA_NATIVE | 项目原始 Java 基线；PROJECT_NATIVE_REFERENCE | 原生 HCA 搜索、预约与释放语义 | 正式容量与 1× 正式时延基线 |
| G31 / S4_FULL_NATIVE | 当前论文方法；PROJECT_NATIVE_CANDIDATE | 当前节点、直接候选邻居及已登记的直接邻居服务日历标量 | 正式容量与时延候选 |
| CIE_DH_REPLICA / TARAU_LOCAL_2009 / CIE_DH_2009 / FENG_DH | **ADAPTED_BASELINE；NOT_EXACT**；这些别名属于同一基线家族，只计一次 | 对每个出口沿健康静态图上的自由流续接路径统计 moving/stopped 占用，范围可超过严格一跳；权重冻结为 moving=1、stopped=2 | 进入 P1；不得写成原论文精确复现 |
| TARAU_DISTRIBUTED_2010 | **ADAPTED_BASELINE；NOT_EXACT**；有限邻居通信的 2010 distributed heuristic，高出入度推广和零开关成本均属适配 | 当前候选、候选的一跳后继及事件驱动 queue beacon；动态半径 2，tau_pred=5 s；不读取 scheduled incoming、service calendar、全局未来任务、全局预约、S4 DLP/严格下降 | 修复版 SHA=17d73f... 进入 P1；旧数值保留隔离历史 |
| SSP_TIME_ADAPTATION_NOT_FENG_DHA | 物理时间最短势适配；不是 Feng DHA，也不是对单位边 SSP 的精确复现 | 静态全图势可预计算，运行时只比较当前直接候选；无实时全网扫描 | 作为简单适配基线，保留混合/负结果 |
| S5_dynamic_workload_oracle | 全局动态诊断 oracle；不是文献去中心化基线 | 运行时全局 A*/工作量扫描 | 仅作诊断上界尝试；NO-GO，不进入去中心化主张 |

CIE-DH 的 moving/stopped 系数在可获得材料中未披露，当前 1/2 权重只是在正式测试前冻结的透明适配。因此，即使某些数值接近原 CIE 表 5.3，也不能升级为 exact。

## 4. 四格固定时域容量

### 4.1 原生/项目协议及适配诊断臂

括号内为完成率。四格均采用固定人口、固定结束 epoch 和相同速度；S5 的南宁 2× 已按完整协议自然运行到固定结束时刻。

| 方法 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---:|---:|---:|---:|
| HCA_NATIVE | 28,506/28,506 (100.000%) | 56,917/57,012 (99.833%) | 28,506/28,506 (100.000%) | 39,063/57,012 (68.517%) |
| G31 / S4_FULL_NATIVE | 28,506/28,506 (100.000%) | 57,012/57,012 (100.000%) | 28,506/28,506 (100.000%) | 57,012/57,012 (100.000%) |
| SSP_TIME_ADAPTATION | 28,506/28,506 (100.000%) | 57,012/57,012 (100.000%) | 28,506/28,506 (100.000%) | 57,012/57,012 (100.000%) |
| S5 global oracle | 28,506/28,506 (100.000%) | 57,012/57,012 (100.000%) | 28,275/28,506 (99.190%) | 47,058/57,012 (82.541%) |

对 HCA 的可归因正式结果是：1× 完成量到达天花板，G31 的收益体现在完整人口时延；2× map2 多完成 95 件，南宁多完成 17,949 件。后者不是通过改变分母或报告幸存者实现。

### 4.2 原生/适配臂的截止成功率

| 方法 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---:|---:|---:|---:|
| G31 / S4_FULL_NATIVE | 28,506 (100.000%) | 56,875 (99.760%) | 28,395 (99.611%) | 20,963 (36.769%) |
| SSP_TIME_ADAPTATION | 28,506 (100.000%) | 56,186 (98.551%) | 28,426 (99.719%) | 20,334 (35.666%) |
| S5 global oracle | 28,506 (100.000%) | 57,012 (100.000%) | 22,915 (80.387%) | 17,759 (31.150%) |

SSP 在南宁 1× 的截止成功率比 G31 高 31 件，但在 map2 2× 和南宁 2× 分别少 689 件和 629 件，没有跨地图一致收益。S5 的 map2 2× 截止天花板不能抵消南宁 1× 少完成 231 件且截止成功少 5,480 件，以及南宁 2× 少完成 9,954 件、截止成功少 3,204 件的失败。

### 4.3 P1 中性 FIFO：G31 与 CIE-DH local

这两组冻结产物使用相同的旧公平对照二进制 SHA=884f36f...、同一 canonical 人口和中性 FIFO；只把 CIE-DH 看作适配后的下一跳基线。它们与下一节 SHA=17d73f... 的 Tarau distributed 修复版分开报告。

| 方法 | 指标 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---|---:|---:|---:|---:|
| G31_NEUTRAL_FIFO | 完成量 | 28,506 | 57,012 | 28,506 | 57,012 |
| G31_NEUTRAL_FIFO | 截止成功 | 28,506 | 56,872 | 28,395 | 20,963 |
| CIE-DH adapted | 完成量 | 28,506 | 57,012 | 28,506 | 49,038 |
| CIE-DH adapted | 截止成功 | 28,506 | 57,012 | 27,133 | 16,525 |

南宁 2× 的核心结果为：CIE-DH 完成 **49,038/57,012 = 86.0135%**，同 SHA 的 G31 完成 **57,012/57,012 = 100%**；两者的正式 2× 时延仍均为 N/A。map2 2× 上 CIE-DH 的截止成功反而高于 G31 140 件，必须保留这一负结果，不能用南宁结果掩盖。

### 4.4 P1 中性 FIFO：修复版 G31 与 TARAU_DISTRIBUTED_2010

以下四格全部同时满足 binary.sha256=17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279、execution_integrity.pass=true、相同 canonical 人口和中性 FIFO。南宁 2× 的 G31 与 Tarau 文件已经成对通过该门槛。

| 方法 | 指标 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---|---:|---:|---:|---:|
| G31 repaired-pair | 完成量 | 28,506 | 57,012 | 28,506 | 57,012 |
| G31 repaired-pair | 截止成功 | 28,506 | 56,872 | 28,395 | 20,963 |
| TARAU_DISTRIBUTED_2010 adapted | 完成量 | 28,506 | 57,012 | 28,506 | 47,707 |
| TARAU_DISTRIBUTED_2010 adapted | 截止成功 | 28,506 | 57,012 | 24,463 | 20,767 |

map2 1× 两者均达到容量与截止天花板；map2 2× Tarau 比 G31 多 140 件截止成功，这是必须保留的 Tarau 正结果。南宁 1× 两者均完成全人口，但 Tarau 截止成功率为 85.817%，低于 G31 的 99.611%，差 3,932 件。南宁 2× Tarau 完成率为 **83.6789%**，比 G31 少完成 9,305 件；截止成功率为 **36.4257%**，比 G31 少 196 件。当前证据说明 distributed adaptation 的作用具有明显拓扑与负载差异。

## 5. 1× 正式完整人口时延

单位均为秒；所有行均是完整 28,506 件人口，且使用相同 HCA segment release。min 的约 0.001 秒差异属于物理时间分辨率平局，不作胜负解释。

### 5.1 HCA 与原生/适配诊断臂

| 地图 | 方法 | min | mean | P95 | P99 | max |
|---|---|---:|---:|---:|---:|---:|
| map2 | HCA_NATIVE | 188.000 | 238.000 | 300.000 | 332.000 | 383.000 |
| map2 | G31 / S4_FULL_NATIVE | 188.001 | 210.553 | 247.202 | 254.049 | 279.202 |
| map2 | SSP_TIME_ADAPTATION | 188.001 | 210.767 | 247.202 | 259.202 | 292.602 |
| map2 | S5 global oracle | 188.001 | 210.669 | 247.202 | 257.002 | 287.802 |
| 南宁 | HCA_NATIVE | 49.000 | 374.080 | 653.000 | 785.000 | 2,851.000 |
| 南宁 | G31 / S4_FULL_NATIVE | 48.401 | 282.934 | 475.339 | 553.466 | 812.698 |
| 南宁 | SSP_TIME_ADAPTATION | 48.401 | 281.724 | 473.152 | 552.369 | 808.585 |
| 南宁 | S5 global oracle | 48.401 | 281.361 | 472.995 | 549.385 | 805.080 |

SSP 和 S5 在南宁 HCA-release 1× 时延上比 G31 略好，但幅度不到约 1%；SSP 在 map2 的 mean/P99/max 变差，S5 在 map2 的 tail 变差，而且 S5 的 canonical 南宁 1×/2× 均未完成全人口。因此它们不构成简单、通用、可复用的性能提升。

### 5.2 P1 中性 FIFO 的同释放时延

| 地图 | 方法 | min | mean | P95 | P99 | max |
|---|---|---:|---:|---:|---:|---:|
| map2 | G31_NEUTRAL_FIFO | 188.001 | 210.546 | 247.202 | 254.002 | 278.202 |
| map2 | CIE-DH adapted | 188.001 | 210.888 | 247.202 | 256.402 | 275.802 |
| 南宁 | G31_NEUTRAL_FIFO | 48.401 | 282.933 | 475.339 | 553.466 | 812.698 |
| 南宁 | CIE-DH adapted | 48.401 | 280.707 | 469.978 | 525.496 | 794.531 |

map2 上 CIE-DH 的 mean 和 P99 略差、max 略好；南宁上 mean、P95、P99 和 max 均略好。结合南宁 2× 的容量崩落，当前证据只支持“不同负载与拓扑上的权衡”，不支持 G31 或 CIE-DH 的统一支配关系。

### 5.3 P1 中性 FIFO：修复版 Tarau distributed

以下四个 1× 产物均使用修复版 SHA=17d73f...，完成同一 28,506 件 HCA-release 全人口，formal_same_hca_release_arm_eligible=true 且 survivor_or_common_cohort_used=false。

| 地图 | 方法 | min | mean | P95 | P99 | max |
|---|---|---:|---:|---:|---:|---:|
| map2 | G31 repaired-pair | 188.001 | 210.546 | 247.202 | 254.002 | 278.202 |
| map2 | TARAU_DISTRIBUTED_2010 adapted | 188.001 | 211.247 | 247.802 | 262.002 | 298.202 |
| 南宁 | G31 repaired-pair | 48.401 | 282.933 | 475.339 | 553.466 | 812.698 |
| 南宁 | TARAU_DISTRIBUTED_2010 adapted | 48.401 | 294.430 | 512.474 | 598.447 | 936.555 |

min 为物理分辨率平局。相对 Tarau，G31 在 map2 的 mean/P95/P99/max 分别降低 0.332%、0.242%、3.053% 和 6.707%；在南宁分别降低 3.905%、7.246%、7.516% 和 13.225%。因此，“G31 在修复版 Tarau distributed 的 1× 正式完整人口时延上跨地图更低”得到支持；南宁 2× 只形成固定时域容量/截止结论，所有 2× 正式时延仍为 N/A。

## 6. 为什么所有 2× 正式时延都是 N/A

| 地图 | 正式状态 | 原因 |
|---|---|---|
| map2 2× | **N/A** | HCA 只完成 56,917/57,012，缺 95 件；完整人口条件不成立。任何 56,917 件幸存者统计都被禁止。 |
| 南宁 2× | **N/A** | HCA 只完成 39,063/57,012；仅 52,991 件 raw bag 有释放记录，68,158/87,206 个 segment 被释放、68,062 个完成，无法构造完整固定人口的配对时延。 |

这项 N/A 对所有候选一视同仁。即使 G31 或 SSP 在 canonical 释放下完成 57,012 件，也不能把其自有释放时延拿来和不完整 HCA 比；CIE-DH、Tarau distributed 与 S5 的南宁 2× 自身也未完成全人口。

## 7. 原 CIE 表 5.3 复现审计

| 指标 | 原 CIE 分散启发式 | 当前 CIE-DH adapted | 相对误差 |
|---|---:|---:|---:|
| min | 3.56 min | 3.133350 min | −11.985% |
| mean | 4.43 min | 3.922897 min | −11.447% |
| max | 8.62 min | 7.875230 min | −8.640% |

三项绝对相对误差均超过预定的 5% 工程近似线，因此结论是 **ADAPTED_BASELINE**，不是 EXACT_REPRODUCTION，也不是 APPROXIMATE_REPRODUCTION。主要不可恢复项包括原 moving/stopped 惩罚系数、离散位置与当前连续时间/服务语义的映射、入口占用/HOLD 细节，以及原始任务和完成时刻定义。当前冻结权重未根据正式 map2/南宁结果后调。

## 8. TARAU_DISTRIBUTED_2010 修复与资格审计

结论标签：**ADAPTED_BASELINE；NOT_EXACT；REPAIRED_RUN_ACCEPTED**

修复版 SHA 为 **17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279**。它修复了两个会影响论文公平性的语义问题：

1. 在 complete_on_goal_arrival=true 下，若两跳后继 w 就是 goal，续接代价只计物理 travel，终点不再具有 queue 或 service；这消除了把真实更慢路径误排为更优的目标服务伪影。
2. Tarau 使用专用 route-only candidate record。公共物理可行性 shield 仍可 HOLD 已选路线，但 scheduled incoming、service calendar、公共 live-two-hop 特征不会再被物化进 Tarau 候选记录或数值 argmin。

修复后的运行时评分只读取当前候选 v 和 v 的真实后继 w 的事件驱动 queue beacon，以物理服务率在 tau_pred=5 s 内投影队列；动态信息半径为 2。静态自由流势预计算不属于实时全网状态。switch_cost=0，高出度使用所有合法出口上的稳定 argmin。published calibrated weights、机械开关状态、历史 branching rate 和原 route-time 数据不可恢复，所以仍是 adapted，而不是 exact。

| 格子 | SHA/状态 | 完成量 | 截止成功 | 主结论资格 |
|---|---|---:|---:|---|
| map2 1× | 17d73f... / COMPLETE | 28,506/28,506 | 28,506/28,506 | 合格 |
| map2 2× | 17d73f... / COMPLETE | 57,012/57,012 | 57,012/57,012 | 合格容量；正式时延 N/A |
| 南宁 1× | 17d73f... / COMPLETE | 28,506/28,506 | 24,463/28,506 | 合格 |
| 南宁 2× | 17d73f... / COMPLETE | 47,707/57,012 (83.6789%) | 20,767/57,012 (36.4257%) | 合格容量；正式时延 N/A |

修复前的所有 Tarau 数值均被删除出主表，历史状态只保留为 **QUARANTINED_PRE_FIX_RESULTS_EXCLUDED**，用于解释为什么必须重跑。正式证据目录现为：

outputs/runtime/cie_baselines/p1_neutral_fifo_final/tarau_distributed_2010/

该目录中的每个被接受文件都必须逐个核验 binary.sha256；目录名本身不构成资格。当前 map2/南宁 × 1×/2× canonical 及两张图 1× same_hca 均已核验为 17d73f...。Tarau 南宁 2× 的 execution_integrity.pass=true、reservation_conflicts=0、runtime full-A*=0、scorer global scan=0；它有 9,639 个未完成/失败 segment，因此 full_population_raw_bag_timing.status=NOT_MEASURED_FULL_POPULATION_INCOMPLETE，不能报告幸存者时延。

## 9. 消融证据与负结果

现有稳定 1× 诊断共有 18 个完整人口运行（9 配置 × map2/南宁），共同二进制 SHA 为 884f36f0ceebdb0fd56924fd00fe5c8a1ebef56eb05fac4f53d66306de647155。预登记停止结论是 **STOP_AT_1X_NO_ATTRIBUTABLE_DUAL_MAP_SIGNAL**：

- Q：没有形成跨地图可复用的净收益。
- I：方向具有拓扑依赖；移除后 map2 变差、南宁反而变好，不能宣称稳定贡献。
- successor service wait：没有清晰的双地图增益。
- B5 移除严格势下降：稳定 1× 与完整版本相同；既未证明它降低环路，也未证明它牺牲必要绕行。
- C1 将 J2/M3 改为中性 FIFO：南宁相同，map2 略好；没有正向 M3 因果证据。
- service-rate normalization：结果混合，没有形成量纲修正带来的统一提升。
- 故障 D 组、P2 有限缓存专项、E2 物理同构性尚未完成，均不得宣称贡献。

这些结果支持停止继续给失败方向增加 scorer、guard、参数或模式名；它们不支持为了“流程完整”扩展成低价值 2× 全矩阵。

## 10. 计算开销

以下墙钟时间为单次产物诊断，未做重复和置信区间，不应当作统计显著的算法排名。

### 10.1 原生/适配诊断臂墙钟秒

| 方法 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---:|---:|---:|---:|
| G31 | 25.0 | 45.6 | 51.0 | 537.5 |
| SSP_TIME | 19.8 | 52.1 | 43.7 | 755.5 |
| S5 global oracle | 24.4 | 68.3 | 435.4 | 13,386.5 |

S5 南宁 1× 产生 12,954,197 个事件、3,986,636 次 runtime full-A* 和 2,176,110 次全局 scorer 扫描，而 G31 对应为 7,087,605 个事件且不依赖该全局 oracle。南宁 2× 进一步产生 24,063,054 个事件、8,403,557 次 runtime full-A* 和 4,593,068 次全局扫描，wall/cpu 为 13,386.460/13,034.016 s，最终仍有 9,954 个 raw bag 未完成；event_limit_reached=false、固定时域正常结束、reservation_conflicts=0。其墙钟约为同格 G31 的 24.9 倍。这是性能和论文信息边界上的双重 NO-GO。

### 10.2 P1 中性 FIFO 墙钟秒

| 方法 | map2 1× | map2 2× | 南宁 1× | 南宁 2× |
|---|---:|---:|---:|---:|
| G31 repaired-pair, SHA=17d73f... | 25.3 | 62.9 | 56.4 | 915.2 |
| TARAU_DISTRIBUTED adapted, SHA=17d73f... | 24.2 | 56.6 | 73.1 | 1,473.0 |
| CIE-DH local adapted, SHA=884f36... | 27.8 | 64.2 | 70.4 | 1,744.4 |

修复版 Tarau 在 map2 1×/2×、南宁 1×/2× 分别产生 4,061,624/8,476,044/8,605,281/16,790,794 个事件；对应 G31 为 3,997,434/8,275,574/7,087,585/15,449,360。Tarau 南宁 2× 的 wall/cpu 为 1,473.016/1,442.234 s、决策数 1,278,494；G31 的 wall 为 915.152 s。Tarau 的 runtime full-A* 与 scorer global scan 均为 0，说明修复没有把它变成全局在线搜索，但当前产物没有单独记录 neighbor_messages 和 message_payload_bytes，因此不能虚构通信开销。CIE-DH 南宁 2× 到固定结束时仍未完成全人口，并进行了 3,300,395 次 scorer 全局路径扫描；其路径占用扫描成本和非严格一跳信息范围必须在论文中明示。

## 11. 安全与真实性审计

结论标签：**PARTIALLY_SUPPORTED**

当前进入主表的候选 JSON 均报告 execution_integrity.pass=true，已登记的稳定运行满足固定时域/人口回显、事件预算未超限、reservation_conflicts=0、稳定场景 fault/repair 事件为 0，并核对了实际加载二进制 SHA。修复版 Tarau 还明确通过 neutral FIFO、S4 strict-potential guard 关闭、S4 calendar visibility 关闭、runtime full-A*=0 和 runtime global scan=0 的运行门。没有发现已报告安全计数为非零的运行。

但是 cie_safety_audit.csv 和部分运行 JSON 并未逐项给出任务要求中的全部七个字段：illegal_edge_moves、failed_edge_commits、physical_capacity_violations、mutual_resource_conflicts、wrong_terminal_completions、partial_P2_commits、stale_commit_accepted。因此当前证据足以说明已实现的执行完整性门通过，**不足以声称完整七项安全认证**。未报告不等于非零，也不能被自动写成零。旧 Tarau 被隔离的原因是评分语义和信息边界错误；这两个问题在 17d73f... 中已修复，但并不因此自动补齐未报告的七项安全字段。

## 12. 对任务要求中 12 个问题的逐项回答

| # | 结论标签 | 回答 |
|---:|---|---|
| 1 | **PARTIALLY_SUPPORTED** | 原 CIE 去中心化启发式已形成可执行适配，但表 5.3 三项误差为 8.640%–11.985%，超过 5%，故不是忠实/近似复现。差距来自未披露权重、位置/服务/HOLD 与任务完成语义不能一一恢复。 |
| 2 | **SUPPORTED** | TARAU_LOCAL/CIE-DH 读取候选自由流续接路径的 moving/stopped 占用，可能超过严格一跳；修复版 TARAU_DISTRIBUTED 只读取候选及其真实后继的事件驱动 queue beacon，动态半径为 2、tau_pred=5 s，不读取 scheduled incoming、service calendar 或全局在线状态。 |
| 3 | **PARTIALLY_SUPPORTED** | 在分别冻结的两个 P1 cohort 中，17d73f... cohort 的 G31 1× 正式 mean/P95/P99/max 在两图均低于修复版 Tarau distributed，南宁 2× 还多完成 9,305 件；884f36... cohort 的 CIE-DH local 在南宁 1× 时延略优于其同 SHA G31，而且 Tarau 在 map2 2× 多 140 件截止成功。三臂不是同一构建，不能写成无条件三臂支配。 |
| 4 | **NOT_EVALUATED** | 尚无完整 P2 原生系统因子分解，不能量化源端准入、合流授权、服务日历与路线选择各占多少。 |
| 5 | **PARTIALLY_SUPPORTED** | 稳定 1× 已给出负证据：Q、WS 无跨图净收益，I 具有拓扑依赖；走廊等待尚不足以形成独立、稳定的完整矩阵结论。 |
| 6 | **PARTIALLY_SUPPORTED** | B5 在稳定 1× 与完整版本相同，只能说明该场景没有可测净效应；尚不能回答压力/故障下环路减少与必要绕行损失。 |
| 7 | **NOT_SUPPORTED** | 当前 C1 中性 FIFO 在南宁相同、map2 略好，没有支持 J2/M3 改善吞吐或尾部；J2 与 M3 的独立效应仍未分离。 |
| 8 | **NOT_EVALUATED** | E2 开/关的事件数与物理完成时刻同构实验未完成。 |
| 9 | **NOT_EVALUATED** | 故障存活图势函数与仅过滤故障边的配对故障实验未完成。 |
| 10 | **NOT_EVALUATED** | P2 有限缓存触发、解阻、回滚与深度专项未完成；主矩阵 0 触发不能算贡献。 |
| 11 | **PARTIALLY_SUPPORTED** | G31 相对 HCA 的优势在两图一致：1× 全人口时延显著下降，2× 完成量不低且南宁大幅提高；G31 相对修复版 Tarau 的 1× 正式时延跨图更低，并在南宁 2× 多完成 9,305 件，但 map2 2× 截止成功由 Tarau 更好，CIE-DH/SSP 仍有混合结果。 |
| 12 | **PARTIALLY_SUPPORTED** | 当前足以支持“去中心化 G31 相对原始 HCA 的跨地图容量/完整人口时延改进”、对合格 Tarau-2010 adapted 的四格容量/截止与 1× 正式比较，以及透明负基线结论；不足以支持 Tarau-2010 exact、所有近期方法、完整 78 条件矩阵或各机制独立因果贡献的强主张。 |

## 13. 权威产物与字段

### 13.1 HCA/G31 原论文口径

- 聚合协议、容量与时延资格：outputs/tables/g4irsf31_reporting.json
  - /protocol
  - /primary_rows 中 case_id=t5_2_nanning_1x_speed_2p5 与 t5_2_nanning_2x_speed_2p5
  - /map2_context/capacity/rows 中对应 map2 case_id
  - /map2_context/same_hca_release_timing
- map2 1× 原始 HCA metrics：C:/PROGRAMING/czr005/.g4irsf24_worktree/build/g4irsf24_fresh_hca_full/run_01/metrics.json
- map2 1× G31/HCA 同释放：outputs/runtime/g4irsf31_map2_paired/t5_2_map2_1x_speed_2p5.json
- map2 2× HCA：C:/PROGRAMING/czr005/.g4irsf24_worktree/build/g4irsf29_hca/t5_2_speed_2p5/fresh_hca_summary.json
- 南宁 HCA 原始运行：C:/PROGRAMING/czr005/.g4irsf24_worktree/outputs/runtime/g4irsf31_nanning_hca/
- G31 四格：outputs/runtime/g4irsf35_full_population/g31/{map2_1x,map2_2x,nanning_1x,nanning_2x}.json
- G31 正式 1× 时延：outputs/runtime/g4irsf35_full_population/g31/same_hca/{map2_1x,nanning_1x}.json

容量字段为 /outcome/completed_raw_bag_count 或 /paper_subjects/fixed_horizon_capacity/{denominator_raw_bags,completed_raw_bag_count,completion_rate,finish_le_std}。正式时延字段为 /paper_subjects/full_population_raw_bag_timing/metrics_seconds/paper_network_from_admission，且必须同时核验 raw_bag_count、survivor_or_common_cohort_used=false 和 formal comparison 资格。

### 13.2 新增基线

- 修复版 P1 G31：outputs/runtime/cie_baselines/p1_neutral_fifo_final/g31/{canonical,same_hca}/
- 修复版 Tarau distributed：outputs/runtime/cie_baselines/p1_neutral_fifo_final/tarau_distributed_2010/{canonical,same_hca}/
- CIE-DH local 对照 G31：outputs/runtime/cie_baselines/p1_neutral_fifo/g31/canonical/
- CIE-DH canonical 四格：outputs/runtime/cie_baselines/p1_neutral_fifo/tarau_local_2009/canonical/
- CIE-DH 同 HCA 释放 1×：outputs/runtime/cie_baselines/p1_neutral_fifo/tarau_local_2009/{map2_1x,nanning_1x}.json
- SSP：outputs/runtime/g4irsf35_full_population/ssp_time/{canonical,same_hca}/
- S5：outputs/runtime/g4irsf35_full_population/s5/{canonical,same_hca}/
- 汇总表：outputs/tables/cie_baseline_summary.csv、outputs/tables/cie_runtime_scaling.csv、outputs/tables/cie_safety_audit.csv
- 复现等级审计：outputs/reports/cie_dh_reproduction_audit.md
- 消融负结果：outputs/reports/cie_ablation_report.md
- 文献—代码对照：docs/baselines/tarau_baseline_crosswalk.md

修复版容量字段为 /paper_subjects/fixed_horizon_capacity，1× 正式时延字段为 /paper_subjects/full_population_raw_bag_timing/metrics_seconds/paper_network_from_admission；每份文件还必须核验 /binary/sha256、/execution_integrity/pass、formal_same_hca_release_arm_eligible 和 survivor_or_common_cohort_used。汇总 CSV 只作索引；若与单次 JSON、二进制 SHA 或本报告的语义资格冲突，以原始 JSON 和资格判断为准。

## 14. 可复现命令模板

下面命令从仓库根目录运行；它们写入新的审计路径，不覆盖本报告使用的原始证据。两个 cohort 必须分别运行和解释，不能把不同二进制下的三臂拼成同一公平比较。

~~~powershell
$py = 'C:\PROGRAMING\python3.11.9\python.exe'
$tarauBinary = 'build_cie_baselines\python\Release\czr005_cpp.cp311-win_amd64.pyd'
$cieDhBinary = 'build_cie_ablation\python\Release\czr005_cpp.cp311-win_amd64.pyd'

# Cohort 1: repaired G31 vs TARAU_DISTRIBUTED_2010, all four canonical cells.
foreach ($arm in @('g31', 'tarau_distributed_2010')) {
    foreach ($map in @('map2', 'nanning')) {
        foreach ($scale in @(1, 2)) {
            & $py scripts/eval/run_g4irsf35_full_population.py `
                --map $map --scale $scale --arm $arm `
                --coordination neutral_fifo --release-mode canonical `
                --binary $tarauBinary `
                --output "outputs/runtime/reproduction/tarau_pair/$arm/canonical/${map}_${scale}x.json"
        }
    }
}

# The same cohort's formal 1x full-population timing cells.
foreach ($arm in @('g31', 'tarau_distributed_2010')) {
    foreach ($map in @('map2', 'nanning')) {
        & $py scripts/eval/run_g4irsf35_full_population.py `
            --map $map --scale 1 --arm $arm `
            --coordination neutral_fifo --release-mode same_hca `
            --binary $tarauBinary `
            --output "outputs/runtime/reproduction/tarau_pair/$arm/same_hca/${map}_1x.json"
    }
}

# Cohort 2: G31 vs the CIE-DH/TARAU_LOCAL_2009 family adaptation.
foreach ($arm in @('g31', 'tarau_local_2009')) {
    foreach ($map in @('map2', 'nanning')) {
        foreach ($scale in @(1, 2)) {
            & $py scripts/eval/run_g4irsf35_full_population.py `
                --map $map --scale $scale --arm $arm `
                --coordination neutral_fifo --release-mode canonical `
                --binary $cieDhBinary `
                --output "outputs/runtime/reproduction/cie_dh_pair/$arm/canonical/${map}_${scale}x.json"
        }
        & $py scripts/eval/run_g4irsf35_full_population.py `
            --map $map --scale 1 --arm $arm `
            --coordination neutral_fifo --release-mode same_hca `
            --binary $cieDhBinary `
            --output "outputs/runtime/reproduction/cie_dh_pair/$arm/same_hca/${map}_1x.json"
    }
}

& $py scripts/eval/aggregate_cie_results.py `
    --input-root outputs/runtime/reproduction/tarau_pair `
    --input-root outputs/runtime/reproduction/cie_dh_pair `
    --output-dir outputs/runtime/reproduction/tables
~~~

正式 Tarau 运行前必须确认 build_cie_baselines 二进制 SHA 为 17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279，且包含 goal-arrival 与 route-only candidate_record 信息边界修复；CIE-DH cohort 的 build_cie_ablation SHA 必须为 884f36f0ceebdb0fd56924fd00fe5c8a1ebef56eb05fac4f53d66306de647155。聚合表中的 `binary_sha256`、`coordination_protocol` 与 `release_mode` 是 cohort 过滤键；不能只按算法名跨 cohort 比较。

## 15. 最终状态与剩余非阻塞项

1. **TARAU_DISTRIBUTED_2010：** 修复版 map2/南宁 × 1×/2× canonical 与两图 1× same_hca 已完成；G31/Tarau 南宁 2× 双文件均已核验为 SHA=17d73f...，旧值未回填。
2. **S5 南宁 2×：** 已按完整固定协议结束，47,058/57,012、截止 17,759、wall 13,386.460 s，正式 2× 时延为 N/A。它同时在完成量、截止量、计算开销和信息边界上失败，结论为 NO-GO。
3. **P2、故障 D 组、E2：** 仅在对应机制确实是论文主张时做最小专项；不得用它们扩展 scorer 或为稳定场景负结果打补丁。
4. **完整 CIE 稿件结论：** 当前可写 G31 相对 HCA 的跨图提升、对修复版 Tarau adapted 的四格容量/截止与 1× 正式比较，以及新增基线和 S5 的负/混合结果；在完整安全字段和必要故障/机制专项完成前，不应声称“完整因果消融”或“全面安全认证”。

最终 paired 更新格式：

| 方法/版本 | map2 1× 完成/截止 | map2 2× 完成/截止 | 南宁 1× 完成/截止 | 南宁 2× 完成/截止 | 1× 正式时延 | 2× 正式时延 |
|---|---|---|---|---|---|---|
| G31 repaired-pair, SHA=17d73f... | 28,506/28,506 | 57,012/56,872 | 28,506/28,395 | 57,012/20,963 | map2 210.546/247.202/254.002；南宁 282.933/475.339/553.466（mean/P95/P99 秒） | **N/A** |
| TARAU_DISTRIBUTED_2010 adapted, SHA=17d73f... | 28,506/28,506 | 57,012/57,012 | 28,506/24,463 | 47,707/20,767 | map2 211.247/247.802/262.002；南宁 294.430/512.474/598.447（mean/P95/P99 秒） | **N/A** |
