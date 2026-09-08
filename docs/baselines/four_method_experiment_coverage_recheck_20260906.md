# 四方法实验覆盖与证据复核（2026-09-06）

**尚不能说四个方法都已有同一套“正确数值结果”。** 最新最终矩阵确有 G31、段身份修复版 HCA、用户采用的 V5 DH 各 60 格，共 180 格；有独立配置与原件支持的第四个文献基线是 **Tarău-2010 distributed route-only adaptation**，目前仅找到其旧 P1 协议的 6 个结果，不属于当前随机矩阵。若以同一 60 坐标覆盖四方法为目标，当前是 **180/240 个已归档观察**，Tarau 缺 60 个合格配对格。另一本轮 Java 专项新发现 HCA 时间一致性问题，尚待确认影响范围；180 格归档齐全不能据此等同 180 格全部物理语义已证明正确。

本次不启动模拟，不修改冻结数据、运行器或协议，不重新解压全部原生档案。检查了当前表与 manifest 的逐格绑定、报告/图表来源哈希、三方法的 60 组输入身份一致性、Tarau 六个原件及其六个 G31 对照原件。具体检查与 SHA 见同目录 [JSON 审计](four_method_experiment_coverage_recheck_20260906.json)。这里的“通过”仅指这些证据和统计资格检查，不是所有物理约束或论文精确复现认证。

## 方法身份与去重

| 本次所问对象 | 当前应使用的身份 | 证据与限定 |
|---|---|---|
| G31 | `G31_S4_NATIVE_SYSTEM` | 当前项目的 S4/J2/M3/E2 系统；60 个冻结控制观察，原生 binary `b00fd178…a91f5` |
| HCA | `HCA_SEGMENT_IDENTITY_V1` | 新跑 60 格；每个 canonical 段使用独立执行 ID，不能用旧 `FENG_NATIVE_HCA` 记录替代 |
| CIE-DH | `FENG_DH_BOUNDARY_CLEARANCE_V5` | 用户看过原始 map2 结果后采用的、披露假设的 DH 重构；南宁为该实现的移植，**不是作者源码精确复现** |
| 第四个独立文献基线 | `TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT` | [独立配置](../../configs/baselines/tarau_distributed_2010.yaml)及[文献对照](tarau_baseline_crosswalk.md)明确区分 2010 distributed adaptation 与 2009 local/CIE-DH 家族 |

`TARAU_LOCAL_2009`、`CIE_DH_2009`、`FENG_DH` 是旧 CIE-DH 家族的别名或旧适配实现，不能重复计为第四个独立文献方法。对代码、配置、baseline 文档及报告的本次查找未找到一个独立登记的 `LBD` 实现或结果；“第四个就是 Tarau”是依据当前仓库登记作出的识别，不替用户定义尚未指定的新方法。

旧汇总中还登记了 `SSP_TIME_ADAPTATION_NOT_FENG_DHA` 与 S5 dynamic-workload oracle，各有两图 1×/2× canonical 加两图 1× same-HCA，共 6 行，binary `639a6af5…9a31`。这些是另外的适配/机制对照，也没有当前三负载十种子的 60 格覆盖，不能借它们填 Tarau 或 CIE-DH 的空位。旧 `feng_dh`/`tarau_local_2009` 的不同 binary 观察亦不能与 V5 混作同一版本。[历史汇总](../../outputs/tables/cie_baseline_summary.csv)

## 当前 180 格：覆盖完整，人口完成须另读

逐方法在下列每组都有 10/10 个正常终止、具有正式记录的固定种子格。表内数量是**原始袋全完成的种子数**，不是运行完成数。

| 地图 | 负载 | 每种子原始袋数 | G31 全完种子 | V5 DH 全完种子 | 新 HCA 全完种子 | 正式 THT 资格 |
|---|---:|---:|---:|---:|---:|---|
| map2 | 1× | 28,506 | 10/10 | 10/10 | 10/10 | 三方法可报告 |
| map2 | 1.75× | 49,765 | 10/10 | 10/10 | 10/10 | 三方法可报告 |
| map2 | 2× | 57,012 | 10/10 | 10/10 | 10/10 | 三方法均为协议 N/A |
| 南宁 | 1× | 28,506 | 10/10 | 10/10 | 10/10 | 三方法可报告 |
| 南宁 | 1.75× | 49,765 | 10/10 | 0/10 | 0/10 | 仅 G31 有完整人口时间；跨方法 THT 配对不足 |
| 南宁 | 2× | 57,012 | 10/10 | 0/10 | 0/10 | 三方法均为协议 N/A |

南宁 1.75× 的十种子 TH 均值为 G31 49,765、V5 46,640.2、新 HCA 37,411.2；2×依次为 57,012、49,641.4、39,032.7。后两种方法高负载到达固定时域仍未全完，是保留的有效数值观察，不能把它们当缺失运行，也不能只对完成袋报告正式 THT。完整逐组数据，包括实际段数范围与终止状态，已列入本次 JSON。

共同种子为 104729、130363、155921、181081、205759、232003、257053、283303、308081、333667。共同负载为 1.0、1.75、2.0；原始袋抖动与 EBS 分类可能改变段数，不能给每个随机 1×格强写未抖动的 43,603 段。60 个坐标中，三方法的 `workload_identity_sha256`、raw/canonical/map SHA、人口/段数与固定时域字段均一致。本次额外读取并计算了 60 个 identity 原件及两张实际地图的 SHA，均与表和冻结清单吻合；没有重复 hash/解压全部大型 raw/canonical/原生档案。

地图字节身份为 map2 `55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f`、南宁 `daf51cf339862872ec1e6ce86fbdffccd326d83ebd80ebef0e926917c61ac0df`。速度 2.5 m/s、无故障，绝对末 epoch 为 98,259。TH 为到该时点全业务段完成的原始袋数；THT(D) 为每袋各段 `completion − common canonical scheduled D` 之和。2×均 N/A，其他组任一种子未全完则整组时间 N/A，不用完成者或可用种子子集。[新 HCA 协议](hca_segment_identity_campaign_protocol_20260906.md)

### 当前证据版本与绑定

- G31：binary `b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5`。旧聚合结果和原始完整性门被绑定复用；缺少当时未保留的逐袋原生 payload，不能宣称本次已独立重建 G31 全部逐事件轨迹。
- V5：source `7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7`；class `a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869`。袋/段结果及版本证据已保存；trace=0 证据不等于逐 tick 安全证明。[用户采用及限制](feng_dh_v5_acceptance_and_campaign_protocol_20260905.md)
- 新 HCA：source `74c1a899b879b0523d039e9fa650ef3c860557c7fc96e80ff3a8978ae3faf92c`；class `1fbd4c494aa21a34380ddcde6606a3a0d93883533144f0546a903ccf04a872b3`。本次表中 60/60 格终态账目残差为零，原生映射、事件及四态集合可便携重算。修复不单独加入 EBS 入库完成后才可出库的前置条件，故不能扩张为真实 EBS 顺序正确性证明。

当前 [manifest](../../outputs/evidence/hca_segment_identity_20260906/campaign_manifest.json) SHA 为 `00bebaf6217d5c58064e89790fc6b9411d09cb88b50f700ea9dcb17f204850a5`；[180 格表](../../outputs/tables/hca_segment_identity_cells_20260906.csv) SHA 为 `54d389e473c3e6c1dc2fd58e854c0611c90ba4fead993ff144d53f880301480b`。已有 [portable verification](../../outputs/evidence/hca_segment_identity_20260906/archive_verification.json) 为 PASS，并绑定这个当前 manifest，范围为 60 新 HCA 重算、120 G31/V5 控制档案核验。本次进一步实测报告 provenance 的所有输入、报告正文、生成器/格式 helper SHA，及 figure manifest 的输入与四个图文件 SHA，均吻合，未发现过期绑定。没有将这次轻量检查伪称又做了一轮 2,376 个归档文件的全量解压复算。

**本次 Java 专项的新发现不在上述 PASS 内。** 根代理与专项代理报告：原 `Astar` 对已发现节点松弛并替换 parent 时，未同步更新对应 `t1/t2`；[真实五节点反例](../../outputs/evidence/feng_java_consistency_recheck_20260906/original_astar_timestamp_result.json)已复现，至少两个已检查原生格出现路由时间公式不一致。专项代理已说明两格首例的目标 47/53 均为零 through；全量统计仍须正确纳入所有节点（含 source/goal）的 dwell，当前初版统计不能当最终数量。本文件不预填完整 60 格最终异常数，也不重复扫描。该问题涉及路径父链与预约/完成时间的语义一致性，人口守恒、日志字节一致及 completion-ID 可关联的检查不能自动检出。旧 archive PASS 仍准确描述其原审计范围，**不能将其升级为新 HCA 所有运动/预约时间均正确，或在专项结论之前给当前 HCA 无条件科学正确标签**。

“正确”还必须附带计时范围：共同 D 与各执行器 native-start 的排序可能不同。例如 map2 1× 的 native-start 平均 THT，新 HCA 约 237.04 s、G31 约 237.15 s；南宁 1×依次约 366.45 s、611.35 s。它们并非已证明同一物理 entering 事件。V5 的身体清空近似、原论文计时起点未唯一恢复等限制，不能由矩阵齐全消除。[当前完整报告](../../outputs/reports/hca_segment_identity_full_campaign_20260906.md)；[论文计时边界](hca_segment_identity_paper_metric_clock_audit_20260906.md)

## Tarau：旧实验已运行，但不满足当前配对合同

逐份读取了 [Tarau 最终修复目录](../../outputs/runtime/cie_baselines/p1_neutral_fifo_final/tarau_distributed_2010) 的六个 JSON，及邻近 G31 的同坐标六个原件。每份 Tarau 均有 `status=COMPLETE`、`native_execution_started=true`、全部已报告 integrity gates 为真，并记录 requested/loaded binary 一致为 `17d73f94863e1de71e3ba8f1b41d01c25c3173614ae3edfbb071119265ceb279`。这是修复终点计费与路线信息边界后的版本；修复前结果不能补入。

| 地图 | 负载 | release 协议 | 原始袋完成数/分母 | 用途 |
|---|---:|---|---:|---|
| map2 | 1× | canonical | 28,506/28,506 | 旧 P1 固定时域观察 |
| map2 | 2× | canonical | 57,012/57,012 | 旧 P1 容量；正式 2× THT 仍 N/A |
| 南宁 | 1× | canonical | 28,506/28,506 | 旧 P1 固定时域观察 |
| 南宁 | 2× | canonical | 47,707/57,012 | 旧 P1 未全完观察；不能报幸存者正式时间 |
| map2 | 1× | same_hca | 28,506/28,506 | 旧 HCA release trace 对齐的时间观察 |
| 南宁 | 1× | same_hca | 28,506/28,506 | 旧 HCA release trace 对齐的时间观察 |

这六个原件都在 Git 中；每份 SHA、固定窗口、完成/失败段数和原始时间分布已收入本次 JSON。窗口数值同为 8260/90000/98259、2.5 m/s，但这只是部分合同相同。不能合并的具体原因如下。

1. **负荷和随机输入不匹配。** 只有 1×、2×，没有 1.75×；没有当前十种子的 seed 或 workload identity。旧 1×/2×分别 43,603/87,206 段，当前种子输入由抖动实际展开。六个旧结果不是六个当前随机格，所以缺口不是 54 格。
2. **协调与构建不同。** Tarau 及其旧 G31 对照使用 P1 `neutral_fifo`、M1/jit_fifo 与 `17d73f…`。当前 G31 是 native J2/M3 系统与 `b00fd…`，不能改标签当作旧 P1 同执行条件的 G31。Tarau 是 route-only adaptation，缺失原机械开关、权重等；不能称 native/exact Tarau。
3. **释放/计时不相同。** 两个 same_hca 结果按旧 HCA trace 对齐；不能与当前 canonical D 随机矩阵或历史 Feng shared-D workbook 混成同一计时组。canonical 原件中即使保存全人口时间分布，也不自动获得另一协议的正式比较资格。
4. **身份与逐袋复核等级不足。** 六个结果 JSON 没有逐格 map/raw/canonical 文件 SHA、输入 identity 或完整原生 bags payload。它们保存已运行状态、人口与执行门摘要，可说明历史运行发生及其已报告检查通过；单靠这些摘要不能重建当前版本的输入字节链和逐袋独立审计。旧 requested binary 绝对路径在当前机器不存在；两个 same_hca 的 HCA `source_root` 目录仍存在，但目录存在本身不是文件哈希绑定。当前 runner 默认路径说明如何装载旧 canonical/map profile，不是过去每次实际读取字节的证明。

因此，历史 Tarau 不是“根本没跑”或“所有数值失效”，而是**仅可保留为其旧协议下、带证据限制的 6 个适配观察**。本次没有重新审计其连续时间物理碰撞，不能把 `reservation_conflicts=0` 扩写为完整七项安全认证。

## 不可混入与尚未同步的材料

旧 `FENG_NATIVE_HCA` 的 60 个随机观察中，43 格有正段账目残差；17 格只是未检出该残差，不能解释成所有执行语义已证明正确。这些旧观察仅作历史诊断，不能替换新 HCA 的 60 格或补新矩阵缺项。[旧控制说明](../../outputs/runtime/cie_external_baseline_boundary_clearance_v5/control_completion_notes.json)

早期 Java DH、零 through 修复/优化版本、共同 C++ 执行器 CIE-DH 适配及原始历史 workbook 都有独立意义，但版本、执行器或输入时钟不同，不能改成 V5 标签。历史 map2 shared-D 的 V5 28,506/43,603 袋段结果是用户采用依据，不是随机矩阵的一次种子试验。作者 DH 源码仍未恢复，原始历史观察也没有提供南宁三负载十种子的来源精确结果。

**投稿稿尚未与最终实验同步。** [cie_manuscript_patch_v2.md](../paper/cie_manuscript_patch_v2.md) 第 58 行仍写早期 DH mean=238.702287 s；第 82、88–92 行仍将旧 `FENG_NATIVE_HCA` 与 238.000/374.080 s、56,917/39,063 袋等观察作为主体结论。它们不是当前 V5 与新 HCA 随机矩阵的数值，不能据这些 statement 回答“四个方法均已正确跑完”。这次仅登记差异，不覆盖历史稿；投稿正文、摘要、图表与结论需要按当前版本和计时边界另行同步。

## 最小补齐路径

若目标是当前共同任务/口径下的四系统比较，先明确冻结 Tarau adaptation 与执行器配置，再对现有 60 个 identity **新跑全部 60 格**，保存实际输入、source/binary/命令、完整人口、原生逐段终态与便携证据；沿用固定时域、未完成人口和 2× N/A 规则。单纯缺少 Tarau 列不意味着要机械重跑其他方法，但本轮 HCA 时间缺陷必须先独立处理，其 60 格的科学复用资格待专项结论评估；身份哈希相同不能消除已发现的语义问题。全部原始观察继续保留，不能以删除旧记录代替修复和重新验证。

若另一个目标是 P1 的“只有路线选择不同”，还需为 Tarau 配同 binary、同 neutral-FIFO 合同的 G31 对照；不能直接用当前 native M3 结果冒充这种机制隔离。是否需要该额外对照取决于待回答的问题，不能通过暗改 Tarau 协调规则省略。

已有三方法观察可在明确证据范围与新 HCA 专项限定下报告；四方法统一随机矩阵、HCA 时间语义资格和投稿正文则仍有上述明确缺口。任何补齐或修复都不以 G31 必须胜出为门槛。
