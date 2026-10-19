# G31 × ICS：实现与研发证据入口

2026-10-19 本轮见 [冻结模型实际提交与异步建议验证](LEARNING_EXECUTION_MULTIRATE_STAGE_20261019.md)：新原生配对中冻结模型实际选择 B12，receiver 改善 0.119 秒、其他四件不变；独立进程预测期间底层持续推进，晚到建议被当前检查拒绝。另修同 owner 转移语义并加入可选航班计划适配器，943 项回归通过。R2 改按有效期/动作截止期验收，R1 100 ms 仍待专门验证；历史超时记录保留，多步 RL 尚未成立。

2026-10-17 本轮实施见 [真实双观察与增量优化](SERVICE_REFRESH_EXECUTION_20261017.md) 和 [GPT Pro 审阅请求](GPTPRO_REVIEW_REQUEST_20261017.md)：844 项回归通过；默认原生完整一致；同一 B owner 的真实 9.69→9.73s 两次成功观察触发保守全域刷新。对上一轮优化方法的 ABBA 中位增量为 1.086–1.146 倍；完整100ms、跨事件缓存、局部修复和多步RL仍未完成。

2026-10-17 最新优化见 [请求内计算与服务刷新边界](SERVICE_UPDATE_STAGE_20261017.md)：模型段 ABBA 中位耗时降低约 3.90–4.91 倍，新原生完整轨迹与预测一致，787 项回归通过；保留归档缺口及修复重跑证据。完整 100ms、跨事件缓存和局部后缀修复仍未完成。

2026-10-17 最新后续实施见 [真实 later、兼容预算与首次价值学习](LEARNING_NEXT_STAGE_20261017.md)：四条新后续原生轨迹、六行实际数据训练及 699 项回归；两种非默认行为仍因逐件退化被拒绝，未宣称多步 RL、100ms 或机场规模完成。本轮未提交/推送，历史失败与原参考均保留。

当前开发遵循2026-10-13长期总纲，使用 `codex/g31-ics-v3-circulation`。2026-10-14用户授权整理并发布；审核入口为 [GPT Pro审核任务](GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md)，复现入口为 [发布与复现说明](PUBLICATION_AND_REPRODUCIBILITY_20261014.md)。具体提交、发布范围及推送回执以这两个入口为准。最新实现与失败边界见 [进度记录](LONG_TERM_PROGRESS_20261013.md) 文末012—016，精确接入点见 [RESEARCH_STATE.json](RESEARCH_STATE.json)，原始证据见 [RESULT_INDEX.jsonl](RESULT_INDEX.jsonl)，创新判断见 [NOVELTY_LEDGER.md](NOVELTY_LEDGER.md)。

当前native016支持统一物理、严格事件时序、owner通知和真实消息/ACK驱动控制。407项关联回归明确分401项当前native/Python、1项历史011反例、5项011/015身份检查，不能称407个当前物理实验。原图五策略各24完成、19迟到、23次同盘真实返供；P5新126分支由强服务指派解释收益，联合方法增量尚未成立。事件联合仍24/7890次owner计算超过100ms，最慢199.580ms，完整100ms未达标。旧时序造成的一项P5反例对当前模型已撤回；完整原始流、P5创新、P6学习和P7验收门仍开放，P1—P7未全部完成。

## 以下保留第一阶段原始交付记录

日期：2026-10-13。实施分支：`codex/g31-ics-v3-circulation`。独立工作区：`C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`。本轮修改尚未提交，未推送。

## 已实现的内容

1. 修复最新执行包复现的三个 V3 正确性问题，保留修前失败、独立探针修后验收和原测试字节。
2. 在成熟 G31 的 `EventDrivenJunctionRuntime` 中加入 opt-in circulation 生命周期。载盘、Storage、卸载、hold、授权空盘返供、再次装载均由同一个原生事件堆和物理时钟执行。
3. 保留 S4 逐跳选择、FIFO、M3/J2 即时合流、E2 热路径和 P2 事务。普通派发、PIBT 批量、JIT merge 均经过新物理合同检查；不可回滚的事件发布点才提交有限盘资源账。
4. 区分业务袋、运输段、盘和每次边遍历四种身份。业务卸载完成与托盘可用分离，未用接收授权过期释放，在途/失败实体不会被删掉造盘。
5. 新增可运行 native Python binding、场景执行器、独立事件账重放检查和回归，含同物理模型的 S3 可行见证。没有求得最优，最优性标为 unknown。

这次是正确性修复与工程闭环。区域按需自主控制、跨区预测预平衡和学习评价尚未完成，不把显式返供请求称为预测控制。两项需求、100ms 单任务更新目标和 TRE/CIE 量级方法及证据要求不变。

## 基线、读取和保护

原工作树仍是 `codex/ics-v3-phase4` / `fccd4819532701ee4173ec598822450d962d4e61`。原 `cpp/ics_core/runtime/bounded_local_pibt.hpp` 用户修改保留，进入工作前 SHA256 为 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。

独立分支以成熟 G31 `46cc46ab6bc121628fd6357e9f3c7636745fd732` 为底，不回滚 V3、不整分支合并。仅从 `fccd481…` 导入 V3 专属生产、测试和文档命名空间，共 1652 个既有文件；这不是本轮新增工作量。原始 blob 导入清单在 `outputs/experiments/g31_ics_circulation_20261013/v3_import_manifest.json`，可复现导入工具是 `scripts/experiments/g31_ics_circulation/import_v3_reference.py`。成熟 G31 的其余源码保留。

已按指定顺序完整读取最新 next-stage MD、executed-audit MD、NOVELTY_LEDGER、独立探针及 portable 原始 JSON。外审目录最初未在磁盘，已从提供的 ZIP 安全解压；ZIP SHA256 为 `341e3683d5c16c9c53048d7329216255ef63db45d1222fa2afe6bf365a618607`。外审已经实际跑过 1519 项，不能沿用更早“只读 GitHub、未运行测试”的结论。

成熟 G31 的读取与实现定位包括：`g4irsf31_map_adapter.build_s4_request`、`run_g4irsf28_service_potential.service_aware_potential`、南宁 workload 入口、`src/czr005/cpp_backend.py`、旧真实 pybind binding、native initialize/release/service/arrive/merge/PIBT/publication/edge-exit/complete，以及 destination-merge、first-edge-credit、bounded-PIBT 实现。服务势能和 S4 既有机制不计本轮创新。

## 三项正确性证据

证据根目录：`outputs/experiments/g31_ics_circulation_20261013/v3_correctness/`。

| 问题 | 修前独立证据 | 实际修复 | 修后 |
|---|---|---|---|
| N1 Storage 状态合并/错误最早认证 | `before_probes.json`：K=1 返回到达5却认证最早，同 validator 接受到达3见证；删长备选后漏解 | 旧 FullGraph 公共入口准确拒绝未支持 Storage，清除上次证书；不伪称新增 Storage 最优参考 | `after_probes.json`：K=1/2/3 及无长备选准确理由 `full_graph_reference:storage_contract_not_supported` |
| N2 普通筛查默认 K | 普通3、包装4 | 普通包装默认改3，显式K不改、空盘默认1保留 | 默认完整有序候选相等；冷/热/预算/回退等回归 |
| N3 checkpoint 工厂共享可变账 | 保存账本从(0,0)变(0,1) | 支持对象图用同一 deepcopy memo 复制，保留同分支 fast/slow/new-factory 累计关系，兄弟分支隔离 | 实际 checkpoint/fork 不串账、不漏计数，缓存归属正确 |

原探针 `--require-fixed` 修前 exit=1、三项 defect，修后 exit=0、defect空；两次 `source_changed=[]`。原89测试文件逐字节匹配冻结清单，1519 项全部保持；新增61项，总 **1580 passed / 0 failed / 0 errors / 0 skipped**。原件 `full_001/results.json`、JUnit、stdout/stderr、source_before/after。完整说明见同目录 `REPAIR_EVIDENCE.md`，实际补丁 `v3_correctness.patch`。

## 原生同盘真实事件账

首个不可覆盖回执：`outputs/experiments/g31_ics_circulation_20261013/native_first_001/`。其中 input.json、result.json、audit.json 是本机实际运行结果。

| 实际事件 | T0 的物理/业务状态 | 秒 |
|---|---|---:|
| B1 装载完成 | 第一件行李在 T0 上 | 0.10 |
| Storage 入段服务完成 | 持盘存储，继续占库位 | 2.25 |
| Storage 实际释放 | 此刻才生成 storage_out 运输段 | 6.00 |
| B1 卸载完成 | 业务完成，盘进入 hold | 8.65 |
| hold 完成 | 盘成为可用空盘 | 9.90 |
| 真实返程 EDGE_ENTER | 经过源端/接收端模块授权 | 9.95 |
| EMPTY_RECEIVED | 经两条真实边回到源区 | 12.05 |
| B2 装载完成 | 同一 T0 再次服务，非新造盘 | 12.15 |
| B2 卸载完成 | 第二件业务完成 | 17.20 |

共 5 个运输段、10 个 traversal、166 个原生事件。没有另一个 Python 仿真器推进物理状态。native transport completed_count=5 是段数，不能误当5件业务。

## 场景、同模型参考与负结果

`outputs/experiments/g31_ics_circulation_20261013/native_acceptance_final/receipt.json` 记录最终冻结源码对应的13场通过；每场均保存 input/result/audit/events.jsonl。独立审计重放盘身份、装卸/hold、Storage 门控、边容量/头距、实际驻留+在途目标+接收授权占用，并交叉检查业务完成时刻。它不是最优性证书。001 的失败与较早 002 的通过均保留，最终验收以 final 为准。

| 变体 | 实际结果与意义 |
|---|---|
| 不返盘控制 | B1完成，T0真实留在终点；B2未装载，不能拿预测释放替代 |
| Storage 释放延迟到20秒 | B2的真实装载也随循环延后，后段没有预排偷跑 |
| 源端保底库存=1 | 拒绝 `source_module_min_stock`，保留实体与未服务任务 |
| 接收模块禁止 | 拒绝 `destination_module_refused` |
| 真实接收口被另一空盘占满 | 拒绝 `receiving_full`，没有扩容或删盘 |
| Storage 被真实停盘占满 | 载盘不能进入，业务失败/未完成如实保留 |
| 迟到且已过期消息 | 拒绝 `departure_lease_expired`，不能复活权限 |
| 出口故障持续到出发租约之后 | 未实际出发，T0隔离在源端；未用远端接收位释放 |
| 同盘重复进入同一条边、头距30秒 | 入边0.15/30.20秒；第一次卸载和返程不抹除尾窗 |
| 两盘充足，有/无返供 | 完成时刻都为8.65/9.65秒；返供多两次遍历，无收益 |
| S3 同物理/同权限参考 | 两件也在8.65/17.20秒完成；是可行见证，最优未知 |

13场小例不等于业务全规模评价，不证明预测/学习收益，也不证明100ms全流程单任务更新。每个 native event 的测时只作局部计算诊断，不混同路由更新响应上界。

## 最终构建、回归和 legacy 兼容性

以下都是实际执行结果，原始回执在 `outputs/experiments/g31_ics_circulation_20261013/`；集中复核见 `verification_summary.json`。

- `build_final_002/receipt.json`：clean-first 构建，配置、编译、native 单项验收3条命令 exit=0。54份 C++/CMake 源文件构建前后相同且与交付源码相符。验收加载的 binding SHA256 为 `897f6e966df84129deda79d432d36d2df8bf0bf4f11aab8f743caca9a07fb47c`，与构建产物一致。
- `native_pytest_final.xml`：新增 native Python 接口回归 **48 passed，0失败/错误/跳过**，包括同刻正常需求保护、输入合同拒绝、生命周期与物理账反例。
- `native_legacy_final/ctest/final_all_002_junit.xml`：全部 **16/16 CTest 通过**，其中15个既有 native 测试程序、1个新增 circulation 测试程序。它们是程序数量，不与 Python 测试项相加冒充同一统计口径。全量原始构建源清单含53份 C++，另一个54份清单还包含 CMake。
- `native_legacy_final/parity/`：同一固定 fixture 分别用成熟 `46cc46ab…` 和当前 runtime 编译，在无故障、有故障两场中各5类确定性输出哈希逐项相同。只证明这两场的直接兼容性，加上既有 native 回归；没有声称重跑全部旧规模实验。

原工作树受保护用户文件交付时再次核对，SHA256 未变。生产修改仅在独立工作区。

## 可审核的实际代码交付

`outputs/experiments/g31_ics_circulation_20261013/delivery_001/` 提供：

- `native_circulation.patch`：相对成熟 G31 的 native 实现、binding、执行/审计工具、测试和本文档差异；已对当前工作树执行 `git apply --reverse --check`。
- `v3_correctness.patch`：相对冻结 V3 导入文件的3项修复和61项新增回归。复现完整工作树时先在成熟 G31 上执行 `import_v3_reference.py` 导入选定命名空间，再应用这份修复；不是直接整分支合并。
- `implementation_and_diffs.zip`：本轮 native 相关实现源文件、V3 修复源文件、两份补丁和逐文件 SHA256 清单。**这是增量实现交付，不是完整仓库或完整实验数据 ZIP。**

原始场景输入/事件账、修复前后的失败和成功回执保存在同级证据目录，未用新的摘要覆盖。后续整仓发布应连同必要 fixture 和输入清单另行打包；本轮不擅自发布。

## 运行与审计入口

在独立工作区执行；每次选新的 receipt/output 目录以保留失败历史。

```powershell
$env:PYTHONPATH='src;.'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.build_native --receipt-dir outputs/experiments/g31_ics_circulation_20261013/build_recheck --vcvars 'C:/PROGRAMING/visual studio/Visual studio/VC/Auxiliary/Build/vcvars64.bat' --ninja C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_native_cycle --binary build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_circulation_20261013/native_recheck
& C:/PROGRAMING/python3.11.9/python.exe -m pytest tests/test_g31_circulation_native.py tests/test_g31_circulation_same_timestamp.py tests/test_g31_circulation_input_boundaries.py -q
& C:/PROGRAMING/python3.11.9/python.exe docs/external_review/g31_v3_20261011/reproduce_audit_probes.py --root . --output outputs/experiments/g31_ics_circulation_20261013/v3_recheck.json --require-fixed
```

Linux 使用相同 CMake/pybind11/C++17源码，省略 Windows vcvars 参数、传实际 `.so`。本轮尚未独立执行 Linux native，不把可编译预期写成已验证跨平台结果。

## 遇到的问题与处理

- Managed worktree 建在当前沙箱可写范围外，写文件返回 WinError5。转为 root 授权可写目录内的独立 Git worktree；原用户工作树无覆盖。
- MSVC 默认 Debug try-compile 遇 PDB 管理器不匹配。保留失败日志，使用明确 Release try-compile 成功，不跳编译器检查。
- 中文 showIncludes 环境下增量构建复用旧 header 二进制，`native_acceptance_001` 第13场仍报旧 S4-only 拒绝。保留001失败，改用 clean-first、编译前后全 C++ 源哈希与二进制哈希，002通过。仅运行时 `source_changed=[]` 不足以证明编译输入身份。
- 未真正出发就失效的返供曾保留远端泊位。已修未用接收租约清理，源实体仍隔离，在途租约不随出发期限消失。
- 分盘原按输入顺序，改为到达时刻与稳定业务ID的 FIFO；不通过重新排列测试掩盖。
- 常见的同刻返盘抢盘假设，在当前完整 goal service 模式实跑未成立，保留正例对照。直接启用旧 `complete_on_goal_arrival=true` 则实跑发现 phase1 先返盘再导出、phase2才到正常任务。新 circulation 明确要求完整目的服务，拒绝这个未经覆盖的旧捷径；legacy 保留原选项。
- 独立畸形输入实验暴露非有限派生时间、负几何/服务和无效矩阵。新模式增加准确边界拒绝；原 legacy 行为不被默默改写。修前后原件与新增回归分别保留。

## 新模型边界和下一步具体接入点

当前为**合成、on-carrier Storage、逐盘有限泊位**合同。供应方端口目前是固定的容量、允许/拒绝、保底库存规则代理，尚未连接现场供应商区内空盘模块。附加卸载是完成 G31 目的服务后的每泊位卸载步骤，并非已校准的单卸载台模型。零跳合同、旧 goal-arrival 完成捷径、circulation checkpoint/clone 与旧五类状态摘要/回放投影均显式拒绝；不能复用旧 V3 checkpoint/标签或不完整状态哈希声称已支持新宿主。

满泊位的同步换位/交接仍受保守当前占用检查限制，没有声称保留所有旧 PIBT 可行域、无死锁或全域最优。节点/边账扫描与批量预验证也尚无全规模100ms证据。

接下来保持同一宿主继续推进：

1. **区域自主接口**：在 `candidate_record`/S4合法候选排序处接入版本化 RouteIntent 与区域观测；完整业务约束及资源 owner 仍由 shield、JIT 和事务提交复验。先定义只含本地/已送达摘要的观察投影，不能把 binding 的全局离线结果直接当在线特征。系统级 A* 路线只作为可编解码意图/同域参考，实际已进入前缀不可撤。
2. **预测预平衡**：从 native `STORAGE_RELEASE`、`UNLOAD_COMPLETE`、`HOLD_COMPLETE` 及未完成载盘合法阶段生成有依赖的条件释放轮廓；滚动控制选择新的跨区方向/数量/窗口，通过固定模块查询/导出/接收接口提交版本化请求。真实库存只认执行回执。当前显式 transfers 输入不是预测器。
3. **主求解机制**：先把正常服务义务、源供应包络、共享边头距、Storage/泊位与供盘后继表达为时间化依赖。实现与全量同域修复相比的可行域覆盖及计算检查，再研究闭合边界修复。常数终点价值、一般分层和一般增量重用不算创新。
4. **状态与强基线**：实现含所有新生命周期、租约/尾窗、owner消息和计账的原生 checkpoint，再生成同一物理宿主下的参考/continuation标签。先做强解析、S3/S4、受限精确/全量参考、一轮与双向反馈；未求最优明确unknown。learning/screen之后接回，不删除后续评价。

创新结论及最新原始文献核对见 `NOVELTY_LEDGER.md`。新近邻已覆盖通用任务先后依赖闭合、冻结外部和局部修复，因此 C2 需要具体细化；不是把现有接通称为新方法，也不是降低两项研究要求。
