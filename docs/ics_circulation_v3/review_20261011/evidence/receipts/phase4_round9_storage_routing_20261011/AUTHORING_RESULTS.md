# 路由模块 authoring 结果

2026-10-11，`storage_routing.py` 已实现；最终 targeted authoring 共 26 项通过。Root 的 runtime / contracts 仍同步开发，此记录不替代后续完整冻结验证。

| 尝试 | 结果 | 区间 CPU 秒 | wall 秒 | 源 SHA 前后 |
|---|---|---:|---:|---|
| run_001 | 19 通过、4 失败 | 1.109375 | 1.3092092 | 相同 |
| run_002 | 23 通过 | 0.921875 | 0.9821176 | 相同 |
| run_003 | 26 通过 | 0.890625 | 0.9432154 | 相同 |

已计量累计 CPU 2.921875 秒。每轮完整日志、JUnit、source snapshot、before / after SHA、resource.json 均保留。计量范围是本进程 pytest 导入与执行，未计 Python startup、源快照捕获、最终写账；没有原图业务批次。一次解释失败原因的临时只读 Python probe、代码/文档/阅读及工具编排 CPU 未计量，属于 unknown auxiliary。

首轮四个失败均是测试前提错误。桥接测试先后调用进程全局缓存，导致原 Regional 的第一轮冷、第二轮热，候选相同而展开数 15 / 5；改用已存在的 isolated_replay_v1，在相同缓存状态比较 wrapper 与 delegate。三个容量测试初版使用了不存在的 tray 作为预约 owner；原校验器正确拒绝 unknown_reservation_owner。修复后 fixture 使用实际有限盘和完整合法已提交出库计划，或终点 holding 盘，保留相同手算容量约束。没有绕过原校验器或放宽实验阈值。

随后新增 3 项验证：private frozen-prefix 进度不会改写 actual ledger；恰好 release tick 可以出发而不平添一个等待 tick；已关闭必经边不能被直达路由绕过。最终新路由源 SHA-256：

`f438f178ba123d6cb002babc7f9ae50d6d918f28e83d9969846f26731288e116`

最终本组测试 SHA-256：

`c80d087fe2b9fb8c1a1a1268aabd039b5c6957e880aafd79a2cc379b6705f1d5`

不在本组新增 C++、路网、业务源、成本权重修改；不新增持久缓存，不提交或推送。

## 原图窗口发现后的定向修复

原图完整第一小时h21600查询揭示release造成的同f大平原，root授权解除本文件冻结后仅修复同f顺序。新增100个正旅行回路反例，run_004共27 tests通过，CPU0.828125秒；本目录authoring总CPU现为3.75秒。新源码431f4e4a1baf2a20e27561ac4ef722b67223b118dda9819aa3b96fa69340b4ea，测试e1870cbea9fa90f3d0773d8d8c1e424b8b6ce28fc8b93b75ba09f66936b10bc5。旧source/result完整保留于邻近phase4_round9_storage_release_plateau_20261011，完整旧/新实际query及仍未解决的容量平原见该目录REPAIR_RECORD.md。run_004 CPU同时在修复专题中引用，汇总资源不能重复计入。
