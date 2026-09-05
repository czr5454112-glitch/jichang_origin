# V5 用户采用记录与两地图扩展实验合同（2026-09-05）

**当前决定：采用 `FENG_DH_BOUNDARY_CLEARANCE_V5` 作为披露假设的 DH 重构基线，继续 map2 与南宁正式扩展比较。决定类型为 `POST_RESULT_USER_SELECTION`。** 用户已经看过 V5 的全 map2 结果，包括均值相对历史约 +8.75%、最大值 819 秒，随后明确问“用这一版不可以吗？”并选择使用这一版。该采用发生在九次全 map2 诊断之后；本文件不是 V5 的预结果注册，也不追写成预先决定。

原 [V5 预结果机制合同](feng_dh_boundary_clearance_preregistration_20260905.md)及其他已冻结的预注册文件保持原字节。它们记录候选如何产生；本文件另行记录用户的采用决定与后续实验范围。此前审计不建议晋升 V5，是当时对几何依据和重尾的判断；该意见及全部不利结果继续保留，不能用作否定当前已授权扩展的自动门槛。采用 V5 不等于声称恢复了原作者源码、通过了旧百分比诊断门或消除了尾部差异。

## 1. 采用版本与已知结果的冻结身份

源目录为 `benchmarks/java/feng_cie_dh_boundary_clearance_v5/App`，五份文件保持 CRLF。source aggregate（以父目录 `feng_cie_dh_boundary_clearance_v5` 为根，按相对路径和实际文件内容作长度前缀 SHA-256）为 `7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7`。

| 源文件 | SHA-256 |
|---|---|
| `FengDhBagState.java` | `7f8e9043087709f9a01390fe20ba24671df43a38cec81eef0e965b5fcda0d45b` |
| `FengDhBenchmark.java` | `052176456427fe90a8d536448fca082d3ae65cfef086a419fa837a68a51a03d9` |
| `FengDhEdgeLattice.java` | `a6659d82f101984e60a3e1236c4054ccd4e815025f9d82f5c5647bb4944c3aa7` |
| `FengDhPolicy.java` | `fb839478ab62893949f8a745aab3ff9923425181513b1c4f68d66a1a7ea83fe6` |
| `FengDhSimulator.java` | `43e4dac5f7f79f03e1a630c1e4f327169d568a7433d92edf0a05083810b18d93` |

用户已知的 whole-map2 运行使用 JDK 18 默认 target，33-class aggregate 为 `a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869`，目录 `build/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5`。Java 8 target 夹具的 `0859243f...` 是另一套编译身份，不能冒充此正式二进制。扩展 runner 须验证上述五源及正式 class 身份，记录实际编译/执行命令；若编译器或产物变化，先记录差异及等价验证，不能默默替换。

已知运行见 [run_identity.json](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5/run_identity.json)，文件 SHA `80f8d34d58769c2085a96c6e24df6d59ff757a72d177fb8f1c4525eaa030d082`。全人口复核见 [population_and_gate.json](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5/population_and_gate.json)，SHA `f82882e3fa4986661b282659ade4b6f24e47f4e50f324104c421b8fee6a82838`。其中旧 `numerical_gate_pass=false` 和 `extension_authorized_by_this_runner=false` 保留为当时 runner 的输出；本文件记录后续用户授权，不改写旧 JSON。

| 已知 shared-D 全人口结果 | V5 | 历史 DH |
|---|---:|---:|
| 完成原始袋 / 运输段 | 28,506 / 43,603 | 28,506 / 43,603 |
| THT min（秒） | 206.40 | 213.30 |
| THT mean（秒） | 288.8264716200128 | 265.592131481 |
| THT P95 / P99（秒） | 620.00 / 753.20 | 336.90 / 384.595 |
| THT max（秒） | 819.00 | 517.20 |

该运行使用未抖动原始 map2/raw 及历史 shared-D：map SHA `55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f`；raw SHA `0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87`；schedule SHA `a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86`。完整 [bags.csv.gz](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5/bags.csv.gz) 与 [segments.csv.gz](../../outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5/segments.csv.gz) 的压缩/原始字节 SHA 均在 run identity 中。它是采用决策依据，不是后续随机矩阵中的一个种子格。

## 2. 保持的算法与必须披露的限制

V5 的身体清空期由 `(地图行李长度 + 安全距离) / 入边速度` 向上取整到 0.2 秒 tick；map2 为 0.4 秒。through 服务身份按父版本时刻释放；清空期仍保留上游 STOPPED 身体，清空后才释放；总 transfer ready 仍为 through 完成后原有 2 秒，不重新计时。保持原 FIFO、路线候选、全路径 moving/stopped 计数及 0.4/0.8 罚项、源/目标处理、EBS 分段，不为改变排名另外调参。南宁也从本地图长度/速度推导，不能硬填 map2 的 0.4 秒；必须满足原合同 `0 < clearanceTicks < transferTicks`，不满足时报告不支持并定位，不静默截断或延长。

该规则是粗几何重构：保留 STOPPED 身体可能将可同步的清空和跟随串行化；清空后下游持续堵塞的离边等待合同仍未解决。均值可接受并不代表尾部贴合，最大值与 P95/P99 偏高、早高峰持续积压和未恢复的几何来源必须一并报告。[独立尾部审查](../../outputs/reports/feng_dh_boundary_clearance_tail_review_20260905.md)保留其原结论。正式标签必须含 V5 或明确版本标识，并称“披露假设的 DH 重构 / 南宁移植”；不得称 `FENG_SOURCE_EXACT_CIE_DH`、原作者二进制或已复现全部论文行为。

## 3. 新矩阵、输入及固定时域

沿用已完成外部随机实验的[生成、身份与指标合同](../../scripts/eval/run_cie_external_baseline_robustness.py)，只替换 DH 实现为冻结 V5：

| 项目 | 固定内容 |
|---|---|
| 地图 | `map2`、`nanning`；原图原 OD；速度 2.5 m/s |
| 负载 | 1.0×、1.75×、2.0× |
| 配对种子 | 104729、130363、155921、181081、205759、232003、257053、283303、308081、333667 |
| 时域 | 共同绝对终止 epoch `98,259.0` 秒；完整提前结束可记为提前全完，不延长失败格时域 |
| 原始袋人口 | 各负载依次 28,506、49,765、57,012；每格完整需求，不删种子/袋/OD |
| 抖动与分段 | 沿用每袋 UniformInteger[-5,5] 秒及原随机流；同一 seed/load 两图共用既有选择规则；段数由抖动后 raw 实际展开决定，允许 4,800 秒边界自然改变 direct/EBS 分类 |
| 存储节点 | map2 入库 47、出库 52；南宁入库/出库 53；沿用既有业务时钟 |
| 规模 | **新跑 60 个 V5 DH 格**；计划复用同坐标 **60 G31 + 60 HCA 控制格**，共 180 格 |

源输入身份继续为：南宁 map SHA `daf51cf339862872ec1e6ce86fbdffccd326d83ebd80ebef0e926917c61ac0df`，南宁原始 1× raw SHA `5fc1a834f1cf03d28417d3e5a6c16114967a7f9f352af9b795f25a00df983ae6`，map2 身份见第 1 节。实际每格读取 `data/processed/workloads/cie_external_robustness/{map}_{load}/seed_{seed}/identity.json` 所绑定的 raw/canonical，而不是重新生成一个近似工作负载。未抖动的 43,603/76,108/87,206 段数只作基础资料，不强制套给随机格。

新 campaign 使用独立 runner 和独立结果根，不能覆盖本次九次 map2 诊断、旧 robustness 根或修复版 optimized 根。已有 DH 60 格属于其他实现，全部不能替代新 V5 格。每格运行前记录新合同 SHA、五源/class 身份、方法标签、map/raw/canonical/identity SHA、seed/load/horizon 和命令。先完成 V5 522-OD/零 through/地图几何域预检，再按同一合同完成新 60 格；这是实现校验，不要求 G31 获胜或新增百分比晋升门槛。

## 4. 120 个控制格的复用证据与限制

控制方法仍为 `G31_S4_NATIVE_SYSTEM` 和 `FENG_NATIVE_HCA`。候选归一化记录位于 `outputs/runtime/cie_external_baseline_zero_through_optimized_v1`，其原生证据多数仍指向 `outputs/runtime/cie_external_baseline_robustness`。路径名称或表格存在本身不是复用证明；新 runner 为每格保存原/新位置、原 JSON SHA、下列检查及结论：

1. method/map/load/seed、horizon、raw/segment 分母、storage 节点完全对应；调用既有 workload audit 重新验证实际 map/raw/canonical 字节与各 identity 声明，包含 raw-ID/segment-ID 集、重数与 canonical 展开。仅调用 `load_normalized_result` 不足以代替输入文件的重新 hash。
2. 原 native evidence 每份文件存在且 SHA 与旧记录一致；运行正常终止、完成/未完成标志及固定时域一致；不复用已被科学失效旁车标记的 DH。保留原完成量、准时量和积压，不把未完成控制格删掉。
3. G31 核对 native integrity、固定时域、canonical hash、原 `COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE` 身份及二进制 SHA `b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5`；保存原 request/revision manifest 身份和运行时长。
4. HCA 核对原命令输入、`LegacyIcsNoFaultWindowBenchmark`、2.5 m/s、无故障、起止 epoch、native lifecycle 与 raw timings。**已查到的旧 HCA run_status/外层 campaign 没有运行当时的 source/class SHA，不能以当前 build hash补造历史身份。** [Git/原件身份档案](../../outputs/runtime/feng_cie_dh_zero_through_repair_20260905/publication_traceability/frozen_input_and_source_identity.json)可恢复 legacy 源字节，但不独立证明每次旧运行加载了哪个 class。若无补充运行时档案，复用必须明确记为“历史控制结果复用，HCA 构建身份记录存在缺口”，而非完整运行二进制已验证；该限制随比较结果披露。

原 [publication_traceability](../../outputs/runtime/feng_cie_dh_zero_through_repair_20260905/publication_traceability/README.md) 已保存全部 60 workload identity 和 150 个旧 normalized 记录的精确字节，其中含本次需要的 120 控制格。该 bundle 有原生文件 hash，**没有**复制全部控制轨迹：HCA 逐袋/逐段文件仍在本机旧根 `hca_native/run_01/{raw_bag_timings,segment_lifecycle}.csv`；G31 的旧 native JSON提供聚合业务与时间结果，不能宣称其中存在完整逐袋轨迹。新交付保存实际可得的控制 native JSON/HCA lifecycle 及 hash，区分已公开记录与本机原件，不把“表已归档”写成“所有方法逐 tick 已可核验”。

若某格输入或原生证据 identity 检查失败，记录缺口并重新运行该控制格；不得靠复制 normalized 数值让检查通过。HCA 已明确披露的历史 build 记录缺口单列为复用资格限制，不伪装成新执行，也不因此暗改 V5。计划复用数量与实际通过/条件复用数量分别报告。

## 5. 统计资格、呈现与完成定义

沿用固定分母业务指标：完成数/率、准时数/率、迟到下界、源/网内/总积压面积及达到 90%/95%/99% 的时间。时间至少明确分为各方法原 native `processed_attempt`/DH first-admission 后的段和时延，以及同一随机 scheduled release 起算的段和时间；二者分表、定义随表出现，不把本次历史 shared-D 数字拼到随机矩阵或把 native 系统比较解释成纯路由策略因果实验。

**2× 正式 latency/THT 的 min/mean/P95/P99/max 一律 N/A，即使个别方法全完；任何其他负载只要比较人口未全部完成也不能报幸存者或共同子集正式时延。** 配对汇总保留 10 个固定种子，任一方法在某组缺全人口时间资格时明确标不足；不按完整子集偷偷报告“10 种子优势”。全人口允许的时间分布、业务完成量/准时量/积压差以及配对胜/平/负同时呈现。报告原记录墙钟，并说明控制为历史记录、新 V5 为当前记录、硬件/并发/编译配置的可比限制。

只有新 60 个 DH 方法格全部正常终止并通过身份/守恒/固定时域检查，120 个控制格的证据资格逐格列明，180 格无重复缺失且归档核验完成，才称 campaign 完成。`HORIZON_REACHED` 可是有效格，不能冒称全人口完成。实验进行中始终用实数 `n/60`、`n/180` 和 `INCOMPLETE`，不提前填写新结果。

G31 的优势、劣势与负载/地图条件由新共同矩阵测量。用户选择 V5 是采用一个可用且披露局限的重构比较对象，不是授权调参让 G31 全面胜出；所有已知尾部差异、先前独立意见及九次诊断记录保持可追溯。
