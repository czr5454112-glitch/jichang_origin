# HCA 论文实验套件：现有代码能力与 V3 实现边界

本次直接读取原项目镜像的 `App/ICS_PathFinding.java`、`Tasks.java`、`Astar.java`、`Map.java` 以及时间标签修复 V2 的完整 wrapper。原材料、legacy 镜像、既有 V2 及旧实验均未修改。新目录 `benchmarks/java/hca_paper_suite_v3/` 只用于独立发展；没有运行任何全人口实验。

结论：**现成 HCA 可以真实改变规划及执行边速度；具有设备故障触发的路径重规划代码，但当前启用路径没有实时速度偏差重规划，也没有可执行的完整 LRA* 静态对照。** V3 首批实现只开放基线与从实验开始就已知的全日断边，明确拒绝非零偏差、动态和 LRA* 模式。这不是整套论文实验已经完成的声明。

本轮后续用户已取消动态/静态速度偏差实验。当前执行范围改为两图、两负载、10 个共同种子的基础三速 1.5/2.5/3 m/s，以及共同首轮已知的 16 个全天断线场景；以下动态能力审计保留为排除误用的证据，不是待本轮补跑的项目。主断线实验命名为“首次路由起已知的全天断线适应”，不宣称测量了中途故障后的在线改道能力。

## 原代码实际执行了什么

以下 App 行号为 `legacy/jichang_origin_readonly/src/App`；V2 的 ICS/Tasks/Map 字节不变，Astar 仅另加两条时间标签同步赋值。

| 能力 | 可执行代码证据 | 本次结论 |
|---|---|---|
| 速度 | Map 67–73 将距离表除以 2.5；83–87 初始化边速 2.5。V2 wrapper 335–346 将全部 `Edge.v` 设为指定速度，hcost 乘 `2.5 / speed`。Astar 79–81 以父节点 T2 + 边长/边速产生下一到达与服务结束时刻。Tasks 173–180 按路线 T1 产生到达/完成事件。 | 速度参数实际参与搜索和后续事件推进。可以测试 1.5、2、2.5、3 m/s；不能比例缩放已有 THT 代替执行。原 App 没有独立实际位置、实际速度与名义预约状态。 |
| 基线调度 | ICS 137–155 对未规划及新任务调用整条 Astar，成功后登记节点预约与首次成功规划日志；Tasks 149–166 每个源每整数 epoch 至多释放一段，未规划队列会阻塞同源继续释放。 | 保留 V2 原有调度、完成时钟及独立 EBS 分段合同。新实验的公共指标资格由外层协议决定，不应继承旧“2× 一律 THT N/A”的指标政策。 |
| 实时偏差输入 | Tasks 183–190 的延迟丢报告逻辑被注释。ICS 170–172 的观测偏差计算被注释，实际固定 `bias_time=0`。 | 改 `generate_tasks(..., delay)` 参数不会生成已声明的物理速度偏差。输入释放时间抖动也不等于运输速度偏差。 |
| 动态更新 | ICS 85–88 调用静态函数，动态函数调用被注释。200–217 名为 dynamic 的函数只随机加 `3*Math.random()` 到剩余路线时间。219–249 的预测冲突与 Astar 重规划分支全被注释。 | 不能把函数名或注释当作已启用的 IoT 动态重规划，更不能打开随机平移就声称复现。该函数也没有完整更新预约的生效代码。 |
| 静态 LRA* | ICS 175–196 有正偏差时检查当前/下一节点并加 2 秒、移动其他同边路线的代码，但 bias 被置零；该逻辑不维护独立实际占用。仓库这批 App 中没有独立可执行 LRA* 类。 | 当前无偏差 HCA 不能直接改名为 LRA*。原文“冲突发生时一袋通行、其余等待”需要真实实际冲突与等待状态、顺序规则及测试。 |
| 已知断边路径排除 | Tasks 129–137 将显式 fault 标记发给 ICS；ICS 101–104 合并故障集合；Astar 76 在扩展前排除故障边。 | 全日从起始 epoch 已断边可作明确的已知拓扑故障实验。需要外部提供已核验的有向节点对，不能拿未经核实的论文线号代替。 |
| 运行中故障/传播 | ICS 318–395 的 Handling_faults 会把正在故障弧上的袋转入 fault_routes；对接近未来故障的任务调用 Astar；无替代路时递归加入上游故障弧。ICS 107–134 另处理修复后任务。 | 这是实际代码，区别于缺失的速度偏差动态方法。但未证明它与论文传播模型完全一致；搜索重规划仅传入该次 E1（376），不是所有 Fault_edges，且会用当前已有预约。不得无微测地开放任意运行中故障。 |
| 故障终态 | V2 wrapper 的终态只有 COMPLETED、ACTIVE_ROUTE、UNPLANNED、NOT_RELEASED；fault_routes / fault_task_id_List 不计入这四态。 | 直接取消 V2 故障禁令会造成新终态漏算风险。首批 V3 只允许在首个任务之前确定的全日故障，并断言运行结束两个故障任务集合为空；违反即失败，不能静默丢失人口。 |

## 原文给出的合同与尚未恢复的细节

一手定位沿用[实验设计复核](feng_paper_experiment_design_recheck_20260906.md)：F2 修订稿第 27–28 页、Table 5 说明规划使用标准速度、位置更新使用偏差速度，各输送机实际平均速度慢 10% / 20% / 30%；没有披露偏差分布、每段是否随机或刷新频率。将 `v_actual = v_standard × (1−δ)` 作为每条边恒定实际速度，是可以明确声明的操作化，不能称为恢复了未披露的扰动分布。

F2 第 18 页步骤 6–7 要求利用 DDI 更新图并重规划受影响袋，利用节点实际过点的 BTI 更新预约、预测后续冲突并将受影响任务回到待规划集合。第 27 页的静态 LRA* 要求实际冲突发生时一袋先行、其他等待，未指定冲突破平局规则。实现这些步骤，至少需要相互独立的名义计划、实际运输/等待状态与观测时间；用相同低速分别计算路线和推进事件，无法检验 IoT 纠偏的作用。

F2 的全日 16 个故障场景还统计传播/受影响线。首批 V3 的已知断边模式没有恢复物理堵塞传播，**不能用其直接断边数充当论文受影响线数**。旧 `arc.txt` 的同号边与论文图 6 的线号对应尚不能成立，应等待共同协议的几何/拓扑映射审计。

## 首批 V3 的科学差异与 CLI

源目录：[hca_paper_suite_v3](../../benchmarks/java/hca_paper_suite_v3)。10 个 App/GUI 文件逐字节复制 V2；新 wrapper 为 `HcaPaperSuiteBenchmark.java`，METHOD 为 `HCA_TIME_LABEL_REPAIR_V3`。保留 V2 的唯一 execution ID、时间标签修复、原生首次规划/完成事件、独立 scheduled EBS 两段、源队列及固定 horizon 循环。

新增的行为仅为：

1. 只允许 `BASELINE` 和 `FULL_DAY_KNOWN_EDGE_FAILURE`；后者要求所有有向故障同在 startEpoch，无修复、无重复、无随机故障。首次任务规划即看到故障。
2. 每条记录到的初始全路径必须只用真实存在且没有 fault 标记的边；终态不得出现未覆盖的 fault_routes 或 fault_task_id_List，故障集合数不得漂移。
3. 所有运行要求 repeats=1、warmupRepeats=0，保留单次完整事件证据；生成新的 `suite_audit.csv`，显式标记 dynamic/LRA 为 false。
4. 非零 bias 与 dynamic/LRA mode 在仿真之前报错。seed 仅作为外层共同任务种子的身份标签，本实现无内部有效随机扰动；不会为假装重复而引入随机 time shift。

原 20 个位置参数原样保留，追加 4 个参数：

```text
HcaPaperSuiteBenchmark map input startEpoch maxEpochs maxNewTasks repeats warmupRepeats
  routeCsv summaryCsv faultSchedule faultProbability repairProbability releaseCsv speedMps
  storageInGoal storageOutStart earlyBagThreshold storageLeadSeconds identityCsv terminalCsv
  suiteMode biasFraction seed suiteAuditCsv
```

`faultSchedule` 语法为 `epoch:from:to:fault;epoch:from:to:fault`；无故障使用 `none`。BASELINE 必须 biasFraction=0、故障概率与修复概率均为0。FULL_DAY_KNOWN_EDGE_FAILURE 同样 bias=0；默认外层不得把它标成已有动态传播模式。

旧 `routes.csv`、`release.csv`、`output.txt`、`outputstarttime.txt`、`segment_execution_identity.csv`、`execution_terminal.csv` 及 summary schema 保留。新增 `suite_audit.csv` 表头为：

```text
method,suite_mode,standard_speed_mps,actual_speed_mps,bias_fraction,seed,seed_role,fault_start_epoch,failed_edge_from,failed_edge_to,full_day_known_fault,dynamic_replanning_implemented,static_lra_implemented,active_fault_count,terminal_accounting_residual
```

## 有界验证及身份

测试入口：[test_hca_paper_suite_v3.py](../../scripts/eval/test_hca_paper_suite_v3.py)，命令 `python scripts/eval/test_hca_paper_suite_v3.py`；只运行几节点、40 个 epoch 的原生 Java 夹具。检查 V2 无故障逐文件完全一致（summary 只允许 method 差异）、4 个真实速度的路线时间公式、断边后的真实改道、全源断开后的 UNPLANNED/NOT_RELEASED 守恒、独立 EBS 两段无新增先后约束，以及未实现模式/无效故障明确拒绝。

最终 METHOD 的证据输出：[production_microtests/microtests.json](../../outputs/runtime/hca_paper_suite_v3_20260907/preflight/production_microtests/microtests.json)，**14 项检查、15 个有界 case 全部 PASS**，包含源及 class 的逐文件 SHA、编译命令、所有原生微测文件哈希及 V2 未改变断言。此前顶层 preflight/microtests.json 使用临时 METHOD HCA_PAPER_SUITE_V3，仅保留为开发证据，不是正式类身份。最终微测构建在 `build/hca_paper_suite_v3_final_microtests/`，正式编译在 `build/hca_paper_suite_v3_20260907/`，两者 class 字节完全相同，不覆盖任何既有类目录。通过该检查不等于动态/LRA/传播已实现。

另用不改动的真实 App 类运行 [HcaFaultCapabilityAudit.java](../../tests/java/hca_paper_suite_v3/HcaFaultCapabilityAudit.java)，证据为 [fault_capability_probe/stdout.jsonl](../../outputs/runtime/hca_paper_suite_v3_20260907/preflight/fault_capability_probe/stdout.jsonl)：既有 0→1→2→3 路线在收到未来 2→3 故障后，确实重新 Astar 为 1→4→3；当前边故障则保留在 fault_routes/fault_ids。第三个小例同时复现了“已有 1→4 故障、随后通知 2→3 故障，重规划仍用 1→4”的原代码 E1-only 缺陷。主 16 个首轮同时已知的故障场景没有活动路线，因此不会进入此多次通知分支；没有为回避这个缺陷修改原件或擅自修复其余原算法。

Python 入口：[run_hca_paper_suite.py](../../scripts/eval/run_hca_paper_suite.py)，API `run_spec(spec_path, output_dir) -> dict`。spec 必需 `workload_identity_path`、`method=HCA_TIME_LABEL_REPAIR_V3`、`family=base/all_day_fault`、`speed_mps`、`seed`、`horizon_seconds=98259`、`timing_policy=full_population_only`、共同 `protocol_path/protocol_sha256`；all_day_fault 另需 `failed_edges=[[from,to],...]`、`scenario_id`、`fault_notification_epoch=8260`。`failed_edges` 指外层明确传入的实际禁用集合，可能包括共同预计算的闭包；结果只称其为 disabled_edge_count。若另外提供 initial_failed_edges，则验证它是禁用集合的无重复子集并单列初始数；不把全部禁用数称为初始断线数或 Java 内部传播。必须先用 `compile` 子命令建立独立身份清单，运行不会静默重编译。

此适配器重算完整 canonical population、逐段映射/释放/规划/完成/实际终态、全路径合法性及含源/目标 through 的 T2 时间公式。两种负载均仅在全部原始袋所有段完成时输出正式 THT；固定分母完成率、STD 成功率与 STD−2700 秒成功率始终保留。全部科学原生与逐段/逐袋派生文件经 gzip 解压 SHA 复核后，才删除本次独立目录中的 epoch 工作文件。`tests/test_hca_paper_suite.py` 有 6 项纯审计测试，包含 2× 全完可出 THT、未全完禁止幸存者 THT、双 deadline、重复事件、错误终态/速度/断边/时间公式和无效 spec 拒绝；不启动仿真。

本次直接读取的原镜像文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| App/ICS_PathFinding.java | `a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a` |
| App/Tasks.java | `dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b` |
| App/Astar.java | `1b46069ca968ecc3043a1f05091de65f95ca6ced65169ba23e82821cf4b63921` |
| App/Map.java | `3e2af71a17d204fdc6639feb2fa8efd252881d6b18b0b15f5248ba68e0d6ece6` |
| V2 wrapper | `493dca55e46bdc4c4a6c93c3358d092a1fc50455805bc20472a4c22f530f3128` |

完整新动态执行器和静态等待对照不在用户现已缩减的本轮范围；其缺失仍如实记录。主故障实验不输出推定的传播数量，直接断边与外部图闭包诊断须分列，不能将拓扑移除冒充在线改道或物理堵塞传播。
