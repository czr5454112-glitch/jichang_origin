# Feng 原始 Java、修复 HCA 与 DH V5 的实现一致性复核

2026-09-06。本次直接读取材料目录的原始 Java 文件并与仓库镜像逐文件比对，读取当前 Java 执行链，运行两个很小的原类诊断以及一次只读 60 格原生路线核算。没有改动冻结算法、输入、统计协议或任何正式实验结果。

**不能把当前四个算法统称为“已经正确复现冯论文项目”。新 HCA 的 EBS 身份丢失已修复、全人口账目可核，但本次新发现原始 A* 时间标签错误，并在全部 60 格的原生路线中发现与原时间递推公式不一致的记录。DH V5 是用户看结果后采用的近似重构，不是恢复出的 CIE-DH 原始程序。第四个 Tarau 适配也不是本次完整 60 格实验。** 原始观察应保留；先前的 identity/population/archive PASS 仍限于那些检查，不能扩展为预约、运动时间或论文复现的全面正确性认证。

## 原件身份与本次直接阅读范围

材料原目录：`C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料/ICS项目/代码-ICSsimulation`。仓库镜像：`legacy/jichang_origin_readonly`。原件 `src` 共 15 个 Java 文件：14 个与镜像字节完全相同；`App/Astar.java` 原件为 LF、镜像为 CRLF，规范换行后完全相同。原件 `map2.txt` 与镜像也仅换行不同；`inputdata.txt` 字节相同。不存在本次把 wrapper 当作原件的替代阅读。

[逐文件原件/镜像及当前源 SHA 清单](../../outputs/evidence/feng_java_consistency_recheck_20260906/source_identity_recheck.json)记录全部 15 源及 map/input 的原绝对路径、物理字节 SHA 和文本相等结果。关键身份：

| 文件/构件 | SHA-256 |
|---|---|
| 材料原件 `App/Astar.java` | `b2b7e001d55fd9cb265f73792918611b6d18aeea3b93bb0ebf36b975020c43f8` |
| 镜像 `App/Astar.java` | `1b46069ca968ecc3043a1f05091de65f95ca6ced65169ba23e82821cf4b63921` |
| 原件/镜像 `App/ICS_PathFinding.java` | `a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a` |
| 原件/镜像 `App/Tasks.java` | `dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b` |
| 原件/镜像 `App/Map.java` | `3e2af71a17d204fdc6639feb2fa8efd252881d6b18b0b15f5248ba68e0d6ece6` |
| 原件/镜像 `RUN/Main.java` | `af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af` |
| 新 `HcaSegmentIdentityBenchmark.java` | `3333729ba81c2e74ac98519e52b161a4b1fbbe37148e9f7c661690fcf28dfbbd` |
| 从材料原件现编译、及正式 HCA 的 `App/Astar.class` | 两者字节相同：`a0a643e3dd0b16fc58d619d16179b4734e8bba490d8aa9a8d96dcfd59f023606` |

本次用 JDK 18 直接编译原件的 9 个 App 源及原件 GUI 源，无改写。类字节与本次生产 build 匹配，见[编译身份记录](../../outputs/evidence/feng_java_consistency_recheck_20260906/probe_compilation_identity.json)。HCA 正式 build 的 source 清单聚合 SHA 为 `74c1a899b879b0523d039e9fa650ef3c860557c7fc96e80ff3a8978ae3faf92c`、class 清单聚合 SHA 为 `1fbd4c494aa21a34380ddcde6606a3a0d93883533144f0546a903ccf04a872b3`，build JSON 为 `eb32cea7c037568208afdc1c6de2a0a7cf90e9ba6d4963e425c42c46b7e12092`。这些聚合算法与 V5 的内容聚合算法不同，不能跨算法直接比较摘要值。

当前 V5 的五个源逐文件 SHA 也在清单中；正式 V5 source 聚合为 `7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7`，class 聚合为 `a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869`。该源目录独立于 HCA App 源；两者不是同一执行器只替换评分函数。

## 原始 A* 的实质缺陷：父路径更新而时间标签不更新

[原 `Astar.java`](../../legacy/jichang_origin_readonly/src/App/Astar.java) 第 55 行设起点 `t2=t1+node.t`；第 80–81 行沿边计算 `t1=parent.t2+length/v`、`t2=t1+node.t`。但第 109–114 行找到已有 open 节点的更小 `gcost` 时只改 `g/h/f/parentNode`，没有更新该节点的 `t1/t2`。第 80 行后续又从旧 `t2` 扩展；第 67–71 行返回路线则沿新 parent 回溯。于是返回的节点父链和该链的时间递推可能不一致。

[五节点原类夹具](../../outputs/evidence/feng_java_consistency_recheck_20260906/OriginalAstarTimestampProbe.java)用全零 through、空预约、零 heuristic、速度 1，以及边 `0→1:1, 0→2:2, 1→3:10, 2→3:1, 3→4:1`。原程序返回路线 `[0,2,3,4]`，其到达时间为 `[0,2,11,12]`；按返回路径自身的原始无等待递推应为 `[0,2,3,4]`。这不是拿另一个更优路径攻击原程序，而是同一返回路径内部不一致。[原始输出](../../outputs/evidence/feng_java_consistency_recheck_20260906/original_astar_timestamp_result.json)。

进一步用原类、正式南宁地图、空预约、单任务 `24→53`、起点 epoch 8866 验证：[逐节点输出](../../outputs/evidence/feng_java_consistency_recheck_20260906/nanning_empty_reservation_probe.json)。返回路径和结束时间 9073.976 与正式 `nanning_1p00x/seed_104729` 的 execution ID 1（raw ID 1，storage_in）相同，节点 35、39、40 的到达标签分别多出 2.680、0.632、0.280 秒，合计 3.592 秒。该单任务诊断不是正式拥堵状态重放，但说明这个实际 OD 无需任何他袋预约就能触发。也保留了 map2 `5→47` 空预约的无异常对照：[输出](../../outputs/evidence/feng_java_consistency_recheck_20260906/original_map2_empty_reservation_probe.json)，不声称每条 OD 必然异常。

### 正式 60 格路线的只读复核

[审计脚本](../../outputs/evidence/feng_java_consistency_recheck_20260906/audit_native_route_times.py)对每个 terminal runner 读取原生 `routes.csv`，先校验 native gzip 的压缩及解压 SHA，与仍存在的原 CSV 比字节，校验实际地图 SHA，确认零故障/零修复，按该格速度重算：

`expected_goal_T2 = planned_epoch + Σ(全部路径节点 through，包括 source 与 goal) + Σ(边长 / speed)`。

必须含 goal：新 wrapper [第 440 行](../../benchmarks/java/HcaSegmentIdentityBenchmark.java)把最后节点 `getT2()` 写作 route `finish_time`。初次 tmp 试算漏了 goal through，已经弃用；本持久结果是修正后重新遍历全部 60 格的结果。map2 实际 goal through 均为 0；南宁为 0、1 或 3 秒。阈值 `1e-7 s` 排除浮点尾差。没有将 DH 的 2 秒 transfer 套入 HCA。

全部 60 格、3,817,428 条已成功规划路线中，1,340,380 条与这个公式不一致，60/60 格均出现。分母是“已成功规划的业务段路线”，不是完成原始袋数；高负荷未规划段不在此分母内。

| 地图/负荷 | 格数 | 已规划路线 | 不一致路线 | 比例 | 各 seed 不一致数范围 | 最大正差（秒） |
|---|---:|---:|---:|---:|---:|---:|
| map2_1p00x | 10 | 436,014 | 22,934 | 5.260% | 2,221–2,374 | 44.600 |
| map2_1p75x | 10 | 761,075 | 37,660 | 4.948% | 3,647–3,853 | 44.600 |
| map2_2p00x | 10 | 872,035 | 44,080 | 5.055% | 4,324–4,475 | 44.600 |
| nanning_1p00x | 10 | 436,014 | 308,134 | 70.671% | 30,642–30,911 | 155.972 |
| nanning_1p75x | 10 | 631,452 | 446,566 | 70.720% | 44,591–44,821 | 254.280 |
| nanning_2p00x | 10 | 680,838 | 481,006 | 70.649% | 47,965–48,203 | 170.092 |

[完整结果与逐格前三例](../../outputs/evidence/feng_java_consistency_recheck_20260906/native_route_time_audit_all.json)包含 map/source/class/build 身份、原生档案 SHA、execution→raw/leg 映射及路径。map2 第一例是 1× seed 104729、execution ID 62、路径 `5;19;25;26;43;15;14;46;36;38;39;47`，计划 epoch 12471，节点 through 总计 10 秒、边时间总计 66.8 秒，公式终点 12547.8，原记录 12549.6，多 1.8 秒。

这已足以否定“当前 HCA 时间语义已经全面正确”的结论，但边界必须保留：正式 native 没有输出各中间节点的完整 `t1/t2` 预约表，本审计没有证明实际碰撞或量化所有预约冲突；也不能从原 THT 减去上述差值当成修后结果。修正时间标签会改变预约、后续路线、放行与拥堵，修后性能方向和幅度均未知。完成量、原始 THT 等仍是该冻结程序的可追溯观测；科学比较资格需要专项处理，不是删除旧观测。

原件还有未扩展修复的算法限制：`Astar.java` 第 9–15、136–143 行按物理节点而非 `(node,time)` 判重，第 83–88 行遇冲突直接跳过邻点且 goal 免预约检查；第 22 行把 F 差转 int。它不搜索节点等待动作、不是完整时空最优规划器。此处仅记录实现边界；除上述时间标签缺陷外，本次未构造新的碰撞或最优性反例，也不将这些限制笼统等同于所有结果无效。

## 执行语义逐项对照

| 项目 | 原件/修复 HCA 的实际实现 | DH V5 的实际实现与一致性边界 |
|---|---|---|
| 运行主链 | 原 `RUN/Main.java` 54–78：从 8260 起，每整数秒先 `Tasks.generate_tasks`，再 `ICS_path_finding`。新 wrapper 307–320 保留此顺序；原 9 App 类未改。 | `FengDhSimulator.java` 281–286：0.2 秒 snapshot→plan→resolve→commit；不是 HCA 的任务/预约执行链。 |
| EBS 展开 | 原 Main 111–127：提前量≥4800 秒时，独立加入 source→47 与 52→goal，第二段 D=STD−2700；原两段同 raw ID。新 wrapper 514–556 解析原前五列、保留第一段 ID，对 storage_out 分配 maxRawID+1+ordinal；Task_ID/Pallet_ID/预约/完成全贯穿唯一 execution ID。 | `FengDhBenchmark.java` 546–610 同样独立展开两段、支持冻结共同 schedule，ID=raw×2+segment。两方法均没有增加 inbound 完成后才能 outbound 的物理先后约束；相同业务合同不证明真实 EBS 连贯性。 |
| 源端放行 | 原 `Tasks.java` 150–168：每源每整数 tick 至多一个队头；该源存在未规划任务则停止新增；`D−epoch<1` 可早于小数 D 不到 1 秒。排序 Main 89–95 /新 wrapper 486–492 保留 int 截断差比较。 | simulator 736–765 一次释放全部 releaseTick≤tick 的段；每段先独立 2 秒源 transfer，之后参与入口竞争。量化 D 向上取0.2秒tick；没有照搬 HCA 的每源每秒限制。共同 scheduled D 不代表相同真实放行事件。 |
| 调度/初始路线 | 原 ICS 137–155：旧未规划队列后接新任务，逐任务全路径 A*，成功后立即更新其他任务可见的预约；失败下一epoch重试。原 Tasks 171–195 按 HashMap 活动 ID 推进。 | policy 140–209 对每个出口的一条静态最短续接评分；simulator 412/433 按冻结视图选出口与 FIFO 仲裁。相等分数按字典序路径破平局；不是恢复的原逐袋遍历次序。改变 HCA storage_out 整数键可能改变 HashMap 桶遍历，已在身份修复协议披露。 |
| Route horizon | 原 Astar 58–123 搜到目标或 open 耗尽；无固定步数/秒数的规划截断；ICS 294–305 对返回全路径建立节点预约。no-fault 使用静态更新（ICS 85–88、172 bias=0），不是每tick重新路由。 | policy 217–285 对各出口算到完整 goal 的静态最短 suffix，按该整条候选路径计数；实际只执行所选下一条边，下一节点重新选。它既不是有限若干跳，也不是在所有可行路径上搜索动态全局最优。simulation horizon 与 route horizon 不同。 |
| 速度/节点时长 | 原 Map 69/79 把 heuristic 除2.5、边速度固定2.5；Astar 55/80–81 按 node.t 与 length/v 推进。新 wrapper 335–346 允许显式统一速度且同步缩放heuristic；正式为2.5。 | lattice 23–25 固定0.2秒、0.5米格；65把边长ceil成cellCount，simulator 665 每tick前进一格。正式域为2.5 m/s；代码可读额外edge speed不代表格点推进已经支持任意速度。V5边离散可带来不足0.2秒量化。 |
| 占用/服务 | 原 Map 30–31读取carrier/safety，但 Astar 的可行性检查是节点 `[t1,t2]` 闭区间，第85行端点相触也算冲突；未发现独立逐边实体格点/车长碰撞检查。goal免预约；Tasks按计划到达时刻生成反馈。 | lattice 185–192、476 强制两reference point间距；simulator 365同tick可复用即将空出的node server，434使用已规划入口位置与确定离开者；原STOPPED入口仍阻断。中间 map through服务保留上游实体，map2为1秒；随后 V5只保留几何clearance（map2=0.4秒），从总2秒transfer扣除这段后离边，后续等待可继续不占边。 |
| 移动/拥堵评分 | 原 HCA 主链没有 CIE moving/stopped 路径拥堵项。GUI只是按预计时间插值画位置（GUI 603–609），不能当作另一个安全执行层。 | policy 162–177 用 tick-start各边MOVING/STOPPED数量加罚；默认α=headway=0.4、β=0.8（Benchmark 377–379），不包含map through/固定transfer的评分项。node/离边等待不进入边计数；service开始commit的旧状态标签及FIFO顺序是重构约定。 |
| 停止/完成 | 原 Main 61由GUI结束绝对epoch控制；新 wrapper 307逐步执行固定90000整数epoch，正式8260…98259。原Tasks 173–178按goal到达T1反馈，ICS79–82/484–489在整数epoch记completion；并非route export的goal T2事件。 | simulator 225–251 在全段完成、98259horizon或50000个无进展tick时结束；goal边到达直接完成，不另付goal through/transfer（313–318）。因此复杂goal时长不是无条件相同口径。 |
| 指标 clock | 原Java产出ID+成功规划epoch、ID+整数完成epoch（ICS 153/487），没有当前完整逐袋THT聚合实现；四字段新任务经Tasks 45–51重建后pass_time默认0，不能把outputstarttime第三列误认canonical D。 | 当前后处理明确定义每袋全段 `Σ(E−canonical D)`；secondary是V5首次edge admission、HCA成功planning，未证明同一物理事件。`run_hca_segment_identity.py` 334–343实现段和、2×或未全完N/A；这是共同实验协议，不是恢复出的论文exact THT程序。 |

## 能说到什么程度

1. **原件 HCA 的实现可追溯，但原件本身有缺陷。** 本次修复唯一执行 ID 解决了同 raw ID 覆盖活动路径/预约的问题（原 ICS 第150与294–315行）。这一正确性修复有独立微测和全人口证据；它没有修原 A*，本次已确认的新时间缺陷也不因与原件一致而变成正确。应保留 `HCA_SEGMENT_IDENTITY_V1` 的精确身份，不称“原 HCA 所有物理语义已验证”。
2. **V5 不足以称 source-exact CIEDH。** 所读15个Java源是 HCA/A* 主链及 GUI/通信支持，没有 CIE-DH 的原始逐袋更新实现。V5 的 fixed 2秒transfer、0.4秒上游保留、snapshot顺序、FIFO、平局、数值罚项、离边等待缓冲均含无法由该原 Java 推出的独立假设。单袋域预检和零through修复只能验证当前合同自洽，不能恢复这些原始选择。用户采用 V5 的决定仍有效，但名称应保留“披露假设的近似重构”。[采用协议](feng_dh_v5_acceptance_and_campaign_protocol_20260905.md)、[一手语义复核](feng_dh_primary_semantics_reaudit_20260905.md)。
3. **当前三执行器比较是系统比较。** 它共同固定需求、map与指标公式，却没有固定同一源放行、路由器/物理执行器、离边缓冲或实际clock事件。不能把总 THT差全部归因于routing算法。出版社全文与实际统计程序尚未恢复，见[指标clock审计](hca_segment_identity_paper_metric_clock_audit_20260906.md)。
4. **第四 baseline 不能补成当前四算法齐全矩阵。** 本仓库登记的是 `TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT`，可追踪的旧 binary为 `17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279`；仅6个旧P1摘要，没有本次两图×三负荷×十seed的60格及同等级全population输入身份链。它不是 CIE-DH/Feng-DH 的另一个别名。该项由独立代理直接inventory，本复核引用[四方法覆盖专项](four_method_experiment_coverage_recheck_20260906.md)，不重复宣称审读了Tarau原论文实现。

本次没有据此修改排名、扣减旧时间、选择更好种子、替换矩阵或修补冻结源。可重复命令和所有新诊断文件的SHA见[证据README](../../outputs/evidence/feng_java_consistency_recheck_20260906/README.md)与[manifest](../../outputs/evidence/feng_java_consistency_recheck_20260906/manifest.json)。
