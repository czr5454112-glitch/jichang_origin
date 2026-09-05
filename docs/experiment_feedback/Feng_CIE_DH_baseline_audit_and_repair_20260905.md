# Feng CIE-DH 基线：独立代码审计与继续执行指令

审计日期：2026-09-05。主审计提交：`f101c2f6c21bd4a147e060ba09bf95b26b48b50c`。

补充核实：`a647b34594c8c5e50195873e8f93c622d84ad91c` 将检查点从 14/30 更新到 16/30，仅更新结果与文档，五个 Java 核心文件未变。

仓库：<https://github.com/czr5454112-glitch/jichang_origin>

分支：`codex/feng-paper-env-cie-dh-reconstruction`

## 1. 任务主线与本次决断

**继续完成一个更接近 Feng 论文、能够实际运行的 CIE-DH 基线，在可信的比较中体现 G31 的性能。** 本轮交付必须包含修复后的执行程序、有效实验和明确比较，不能止于审计报告或重新声明源码缺失。

**立即停止旧错误版本剩余的南宁运行，修复零通行时间中间节点的状态转移，然后恢复分阶段验证和必要实验。** 停止原因是已经实跑复现的实现缺陷。当前不应再花几十小时把同一错误版本补成 30/30。

原 MD《codex_feng_paper_env_cie_dh_reconstruction_and_remaining_experiments.md》§12.2 和 Gate E 的最低要求是 map2 三档负载；南宁 CIE-DH 是完成中立适配后可追加的扩展。后续聚合器设定的 180 格是扩展矩阵的完成条件，不会使有缺陷的运行获得科学价值，也不能据此要求把错误版本继续跑完。修复有效、成本可接受后，仍可以完成修正版的固定十种子比较。

本轮不修改地图、不为让 G31 获胜选择系数，也不通过人为加等待来逼近论文数值。可靠的基线越扎实，G31 真正获胜的指标、负载和条件越有说服力。

## 2. 已确认的阻断性错误

### 2.1 零时间节点交接永远不结束

问题位于 [FengDhSimulator.java](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/benchmarks/java/feng_cie_dh/App/FengDhSimulator.java#L543) 的 543–575 行，尤其 566–574 行。

当 `throughTicks == 0` 时，程序只调用：

```java
bag.beginBoundaryService(commitTick, proposal.node, commitTick, ...);
```

这条分支没有把行李从上游边移出，没有转入下一段 transfer timer，也没有注册到 `nodeThroughOccupants`。

[FengDhBagState.java](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/benchmarks/java/feng_cie_dh/App/FengDhBagState.java#L385) 的 `beginBoundaryService`（385–411 行）会保留原边、原位置和原来的 MOVING/STOPPED 状态。下一 tick，Simulator 319–331 行查不到该行李对应的 through occupant，又对同一个节点提出服务请求。于是它每个 tick 都重新开始一次“已经瞬间完成”的服务，却永远无法进入下一条边。

这是代码错误，不是正常拥堵、算法探索不足或未知系数导致的性能差异。假设账本 A14 还明确写了 zero-service transfer 可以腾空上游占用，实际代码违反了自己的声明。

### 2.2 错误还会绕过无进展检测

Simulator 575 行在每次重复服务时执行 `progress++`；244–252 行只在 `progress == 0` 时积累无进展 tick。因此空转会被当作进展，程序持续运行到 horizon。

实跑还观察到：已经停在边末端不动的行李仍是 `MOVING_ON_EDGE`。这会影响 moving/stopped 计数和路径罚项，因而污染的不只是墙钟时间，还包括物理通行、路由评分与拥堵解释。

### 2.3 为什么 map2 没暴露，南宁会暴露

| 地图 | 节点数 | throughTime=0 的节点 | 与本错误的关系 |
|---|---:|---:|---|
| map2 | 54 | 13 | 全是纯起点或纯终点，不作为合法路线的中间节点触发此分支 |
| 南宁 | 151 | 22 | 这 22 个节点都有入边和出边，零时间中间节点分支必须可正常工作 |

南宁零时间节点：`51,52,53,54,55,56,57,91,92,95,129,130,131,132,133,134,136,138,142,145,147,149`。

实际实验入口已核对：`run_cie_external_baseline_robustness.py` 使用 `data/processed/maps/nanning_legacy.txt`，将其传给 `run_feng_paper_env_cie_dh.py`，Java 直接解析节点第三列，没有将零时间修改为正数。

### 2.4 原样源码的短实跑证据

以下测试使用固定提交的原 Java 核心，没有修复或改写算法。

| 测试 | 条件 | 观察结果 |
|---|---|---|
| 三节点单袋 | 0→1→2，两条 2 m 边，中点 throughTime=0 | 到 100 tick 仍未完成；停在节点 1 前；记录 88 次服务开始 |
| 三节点控制 | 仅将测试夹具的中点 throughTime 改为 1 s | 第 33 tick 完成 |
| 真实南宁图单袋 | 合法路径 130→57→58；57 的 throughTime=0 | 到 5,000 tick（1,000 s）仍未完成，停在节点 57 前 |

真实图测试精确输出：

```text
path=[130, 57, 58]
status=HORIZON_REACHED completed=0 end=5000 pos=164 edge=141 node=57 nodeThrough=0.0 ready=5000 state=MOVING_ON_EDGE
```

130→58 是真实地图的合法拓扑测试，**本次没有声称它必定属于正式投影任务清单**。正式 raw 输入和逐袋生命周期没有完整提交在本次可访问的 Git 路径中。本机 Codex 必须从现有任务或 segments 中再抽出一件实际经过零时间中间节点的行李，保存首个错误状态转移。无需重跑全天实验来做这个核对。

这些证据足以使当前南宁实现失去正式比较资格；尚未通过修复前后全人口对照量化该 bug 对 44% 完成率和全部运行时间的具体贡献，不能声称它解释了所有差异。

## 3. 代码质量与结果可用性

### 3.1 已经做实的部分

- 五个独立 Java 类实现了位置状态、路由、同步模拟与统计；本次源码依赖检查没有发现调用 G31 公共 C++ 执行器。
- 原样代码可以编译。本次实际执行 T1–T10，10/10 通过；重复执行的 JSONL 逐字节相同。
- 状态、计数器、原生输出和 Python 调度有清晰分工；有地图、需求、源码和类身份约束。
- 不完整人口与正式 2× 的时延限制有实际代码支撑；进程正常结束不等于行李全部完成，两者已有分栏。
- 文档诚实保留了未知交接语义、未公开系数和历史数值偏差，没有把缺失源码包装成已恢复原版。

### 3.2 当前不能验收的部分

- **跨地图执行正确性不通过**：零时间中间节点单袋都不能通行。
- **无进展检测不足**：重复开始零服务被记为进展。
- **测试覆盖不足**：T5 只有一条边，终点就是 goal；T7 的中间交接测试明确用正 throughTime。没有覆盖“通过零时间中间节点并最终完成”。
- **运行效率存在可消除浪费**：每 tick 同一节点、同一目标、同一 snapshot 的积压行李重复评分；每次评分重新构造候选路径列表、反复统计边上 moving/stopped；`trace=0` 时仍无条件构造 `decision.traceDetail()` 字符串。应先修正确性，再做保持行为一致的优化。
- 数十小时任务没有 checkpoint，恢复能力不足。但本轮不应为了保住错误版本的计算而优先建设复杂 checkpoint 系统。

总体评价：这是有实际实现和证据管理基础的研究原型，但南宁适配遗漏了关键状态分支。它目前不能作为已通过验证的跨地图 CIE-DH 基线。

### 3.3 现有结果如何处理

| 现有证据 | 处理方式 |
|---|---|
| 南宁旧 Java CIE-DH 的 14/30、16/30 及后续同源码结果 | 保留原文件和原进程状态，另加科学有效性标记 `INVALIDATED_ZERO_THROUGH_STATE_MACHINE_BUG`；撤出正式性能对比 |
| 南宁约 44% 完成率 | 只能作为有缺陷程序的观测，不能再解释为 Feng CIE-DH 在南宁的真实水平 |
| 834.18× 决策数、582.73× 墙钟时间 | 比值算术含义正确，但来自受错误污染的程序；撤回其作为正常拥堵扩展性证据的解释 |
| map2 既有 CIE-DH 结果 | 不因本次 zero-intermediate bug 自动作废；保留原版本，并做修复后的 map2 行为回归 |
| G31/HCA 已有有效比较、析因与消融 | 本次未发现理由因这个独立 Java bug 而全部重跑或撤销 |
| Feng 表 5.3 历史测量 | 继续独立列为历史锚点，不能与新程序实跑行混合 |

834.18× 是**同一 Java 重构在南宁相对 map2 的路由决策次数比**，582.73× 才是对应墙钟时间比。它们都不是 G31 相对 CIE-DH 的加速倍数。

## 4. 更接近 Feng 的方向仍然是什么

继续保留已恢复或已有明确资料依据的部分：原 map2、原需求及两段任务组织、速度、0.2 s 位置更新、moving/stopped 路径占用评分、入口 HOLD，以及历史表的 shared-D `sum(E-D)` 计时。

当前最大的忠实度缺口仍是节点交接状态机，其次是系数：

- 中间节点“一秒 through 独占、之后两秒重叠 transfer”的组合不是找回的 DH 原始源码。
- 固定两秒 transfer 是从历史单袋 OD 下包络推断，不能当作作者明确公开的 DH 实现。
- `alpha_move=0.4 s, beta_stop=0.8 s` 有物理时间尺度解释，但不是恢复出的作者系数。
- 现有九组系数敏感性只改变 moving/stopped penalty，不能验证零时间节点正确性，也不能消除交接状态机的不确定性。

修复零时间分支属于正确性修复。第一步应让它遵守现有已声明的交接合同，不同时改一套新物理模型。若随后发现一手资料明确否定现合同，再单独冻结并验证语义修订；不要把多个未知改动混成一个“更接近论文”的版本。

现有 map2 历史核对：重构 mean 238.7023 s，对历史 265.5921 s；max 326.0 s，对历史 517.2 s。主均值和长尾仍偏乐观。不能通过结果导向加等待、改地图或挑选最接近的一组参数消除偏差。

修好后可以交付“Feng 论文环境下的可执行、语义部分重构 CIE-DH 基线”。在缺失关键源码证据时，继续保留 `SEMANTICALLY_PARTIAL_RECONSTRUCTION`，不妨碍它作为明确标注局限的独立可执行比较对象。**有实现 bug 与有公开资料无法消除的重构不确定性，是两种不同情况；前者必须修好，后者必须报告清楚。**

## 5. 给本机 Codex 的执行步骤

### P0：立即终止错误版本的计算扩张

1. 核对当前活动 DH 源码是否仍为 `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`。若已另行修复，先跑下述短复现判断本指令适用性，避免误停新版本。
2. 对受影响版本先停止自动串接新南宁格子，再有序结束其在途 Java 进程。限定在这一 campaign，不能按 Java 进程名称批量杀死其他任务。
3. 保留已完成、未启动和中止坐标；原 COMPLETE/HORIZON_REACHED 文件不伪改成执行失败，另写实现有效性结论。部分文件不归一化、不计为完整实验。
4. 旧南宁批次以实现缺陷停止；修正版另设版本目录，不覆盖旧产物、旧 SHA 或旧归档。

此步骤不需要为了修复而等待旧 12 个进程自然跑完。此前消耗的时间已经无法改变其结果有效性。

### P1：做最小正确性修复

1. 先加会在旧代码上失败的 zero-through intermediate 单袋测试，使用附录夹具。
2. 修复零 through 完成到下一 transfer 阶段的状态转移，保证零服务只执行一次，正确释放上游占用并更新行李状态。继续遵守 snapshot–plan–resolve–commit；同 tick 跟驰能否使用腾空位置必须与现有合同一致。
3. 不允许以把南宁所有 throughTime=0 改为 1 s、删边、过滤 OD、删未完成行李或加入绕路特判代替修复。
4. 检查 `guaranteedDepartures`、边占用、node service identity、后续 timer、FIFO 顺序和完成计数的一致性；不能只让单袋“跳过去”。
5. 给重复启动同一次零服务增加明确诊断或断言；无进展识别应反映实际移动、有效有限服务推进或完成，不能由空转事件持续重置。合法的正服务等待不能误判死锁。

### P2：完成必要回归，再进入实验

必须通过：

- 原 T1–T10。
- 零时间中间节点单袋有限时间完成。
- 正时间中间节点行为不变。
- 零时间中间节点上游双袋跟驰、同 tick 竞争、下游阻塞后释放；无穿越、重叠或袋身份丢失。
- 真实南宁图的 130→57→58 单袋完成；再从实际任务清单提取至少一条触及零时间中间节点的正式业务段验证。
- 两张地图中正式工作负载实际出现的可达 OD，各自做无拥堵单袋验证。终点节点的零时间语义和中间节点分开覆盖。
- map2 原始 1× 单次完整人口回归：28,506 件、43,603 段；核对逐袋完成结果和统计是否保持。若发生变化，先查清影响来源，不能只以总均值相近验收。

map2 没有零时间中间节点，纯粹修复此分支应保持原行为。不要为了源码 SHA 变化机械重跑所有历史矩阵：先用有效回归证明能否复用旧版本证据，任何真实改变的语义才触发相应重跑。

### P3：在修正后的程序上恢复南宁验证

顺序为：真实小样本 → 固定种子 104729 的南宁 1× → 必要的 1.75×/2× → 冻结十种子比较。

1. 小样本可以用短 horizon，但必须标为 smoke，不能替代正式 98,259 s horizon。
2. 南宁 1× 正式单格使用全部任务、原地图、原负载和原参数。输出所有行李的完成状态，并检查是否还存在零时间服务反复重启或物理不动却长期 MOVING 的异常。
3. 若仍发现实现错误，修复并重跑受影响验证。若实现有效但真实拥堵造成未完成，保留负结果；不能以 CIE-DH 必须输或必须完成作为有效性门。
4. 观察修复后实际运行成本，制定后续计算预算。若恢复到可接受成本，继续补齐修正版南宁固定十种子矩阵。不得把旧错误版本的格子混入新矩阵。
5. 若仍需十几小时一格，先定位保持语义不变的实现开销；不要直接再启动十二个超长作业。预算不足时明确保留不完整扩展状态，已有 map2 基线工作仍应正常交付。

### P4：只做有用的等价效率改进

若修复后仍有明显重复开销，按以下顺序选必要项，不开新的算法主线：

1. 仅在确实记录 trace 时构造 `traceDetail()`。
2. 每 snapshot 预聚合各边 moving/stopped 计数，避免每次候选路径评分重复扫描全部 occupants。
3. 缓存静态候选续接路径；在完全相同 snapshot 内复用同 node/goal 的评分。跨 tick 不能错误复用旧拥堵状态。
4. 保留局部 FIFO、每 tick 语义、确定性 tie-break、物理轨迹和逻辑决策次数定义；如果新增“实际评分计算次数”指标，要与“决策请求次数”分列。

优化前后在代表性拥堵案例核对逐 tick 动作及逐袋结果相同。不得换回 G31 公共执行器或改成事件推进后仍称原 0.2 s 位置更新实现。正确性修复与效率改动分开提交，便于识别差异。

### P5：形成能用于论文的实际基线比较

必须完成并交付：修复后的 Java 实现、必要回归、有效 map2 比较、修复后南宁的有效验证与明确矩阵状态，以及一份紧凑结果报告。若运行条件允许，继续执行预设矩阵，不在写完报告后提前结束。

比较分栏：

| 对象 | 用途 |
|---|---|
| Feng 表 5.3 原始历史测量 | 原算法历史锚点，注明不可在此直接执行 |
| 修复后 Feng 环境 Java CIE-DH 重构 | 独立可执行端到端基线，明示重构等级 |
| G31 与原生 HCA | 保留现有正式比较口径 |
| 公共 C++ 执行器上的 CIE-DH adapted | 共同执行器下路线机制隔离 |

不要为突出 G31 而将不同协议拼成一张全面胜利榜。用相同输入和相同指标，展示 G31 在完成量、平均时延、尾部、准时率、积压和实际计算成本上各自的优势与代价。

已有 map2 反例必须保留：十种子外部实验中 G31 的入网后平均耗时低约 1.79%，但 P95/P99/max 高约 15.32%/25.19%/42.07%；独立的 same_hca 临界负载 2× 中重构 DH 的准时率 98.89%，G31 为 53.03%。它们来自不同释放协议，应各自在所属实验内解释。

本次已核实外部随机实验计时公式：DH 的 `diagnostic_first_admission_to_completion` 与 G31 的 `processed_attempt` 都是逐运输段 `completion - admission` 再按 raw bag 求和。没有发现“DH 按入网、G31 按 release”这一混比错误。建议将表中模糊的 `population_latency` 解释清楚，避免读者误认为包含源端等待。如需增加统一 scheduled-release 计时分栏，可使用 DH 已有 `bags.csv` 与 G31 已有 `java_release` 分布重聚合；仍仅限全体完成且协议允许计时的有效格子，正式 2×、未完成格以及受错误污染的旧南宁结果不得因此恢复正式时延比较。该分栏不能冒充历史 shared-D，也无需仅为改列名重跑模拟。

## 6. 最终验收要求

1. 原零时间 bug 的旧程序反例与新程序通过证据均存在。
2. 真实南宁可达单袋路线上不再因零时间中间节点卡死。
3. map2 正确性与 HCA/G31 原有有效证据保持清楚的版本边界。
4. 新南宁正式比较不混用受缺陷污染的旧结果。
5. 修复后确有可运行、可重复、身份明确的 CIE-DH 基线，不以源码缺失或文档更新代替执行。
6. 报告区分：程序是否正确、论文机械语义恢复到什么程度、历史数值匹配程度、G31 实际性能比较。这四项不得合并成一个模糊 PASS。

## 附录 A：可以直接复制的最小复现

保存为临时测试 `ZeroThroughAudit.java`，与原五个 Java 核心类一起编译；不要修改只读 legacy 源码。

```java
package App;
import java.util.*;
public final class ZeroThroughAudit {
    public static void main(String[] args) {
        for (double through : new double[]{0.0, 1.0}) {
            FengDhEdgeLattice l = FengDhEdgeLattice.builder()
                .addNode(0, 1, 1, 0, 0)
                .addNode(1, 1, through, 0, 0)
                .addNode(2, 1, 1, 0, 0)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
            FengDhPolicy p = new FengDhPolicy(l, 0.4, 0.8);
            FengDhBagState b = new FengDhBagState(
                1, 1, 0, 1, 0, 0, 0, 999, 0, 2, false, "");
            FengDhSimulator s = new FengDhSimulator(l, p, Arrays.asList(b));
            FengDhSimulator.RunResult r = s.run(
                new FengDhSimulator.RunConfig(100, 1, 10));
            System.out.println("through=" + through + " status=" + r.status
                + " completed=" + r.completedRawBags + " end=" + r.endTick
                + " node=" + b.getCurrentNode() + " state=" + b.getStatus());
        }
    }
}
```

旧程序 through=0 时 `completed=0`，through=1 时 `completed=1`。修复验收应补成真正断言，并增加同步跟驰与阻塞释放用例；不能仅让日志看起来正常。

## 附录 B：本次审计范围与可追溯证据

- 已阅读上一轮完整 1,675 行 MD，审计五个 Java 类、运行/归一化入口、相关测试、地图和已推送结果表。
- 本地原样源码聚合 SHA 精确匹配正式报告的 `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`。
- 南宁 Git 文件为 LF；转换为 Windows CRLF 后匹配 runner 地图 SHA `daf51cf339862872ec1e6ce86fbdffccd326d83ebd80ebef0e926917c61ac0df`。二者节点字段一致，不是两张地图。
- 完成原样编译、原 T1–T10 两次运行、独立三节点微测、真实南宁路径单袋测试和依赖检查。
- 没有访问用户本机进程、没有停止其 Java 任务、没有修改或推送远端代码。停止与修复步骤由收到此文件的本机 Codex 执行。
- 已推送检查点和汇总可以读取，但原生逐袋文件未完整公开在本次可访问 Git 路径中。本次未独立重算全部正式格子的生命周期，也不据此声称12个进程的实时状态。

主要来源：

- [固定提交](https://github.com/czr5454112-glitch/jichang_origin/commit/f101c2f6c21bd4a147e060ba09bf95b26b48b50c)
- [16/30 更新提交](https://github.com/czr5454112-glitch/jichang_origin/commit/a647b34594c8c5e50195873e8f93c622d84ad91c)
- [Java 模拟器](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/benchmarks/java/feng_cie_dh/App/FengDhSimulator.java)
- [Java 行李状态](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/benchmarks/java/feng_cie_dh/App/FengDhBagState.java)
- [南宁地图](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/data/processed/maps/nanning_legacy.txt)
- [重构报告](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/outputs/reports/feng_paper_env_cie_dh_reconstruction_report.md)
- [假设账本](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/docs/baselines/feng_cie_dh_assumption_ledger.csv)
- [外部实验入口](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/scripts/eval/run_cie_external_baseline_robustness.py)
- [计算膨胀报告](https://github.com/czr5454112-glitch/jichang_origin/blob/f101c2f6c21bd4a147e060ba09bf95b26b48b50c/outputs/reports/feng_cie_dh_nanning_runtime_amplification.md)
