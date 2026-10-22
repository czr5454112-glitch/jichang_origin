# Terminal-flow 服务与实际案例审计

本报告只消费闭合原生导出；没有新增 native start，没有修改物理合同、活动冻结源码或预算。完整 DEV 比较工具为 `foundation_airport_terminal_service_audit.py`；可读案例提取工具为 `foundation_airport_terminal_case_audit.py`。服务与案例针对性测试 13 项通过，另有最终导出内存范围测试 6 项通过。

## 完整服务评价口径与自比较验证

工具要求共同 input、parent、binary、source bundle、controller、activation、horizon、supply mode、600 秒 projection 与 cost scope。源码变化不静默配对，须另做桥接等价审计。每件行李必须匹配真实 BAG_ARRIVAL、UNLOAD_COMPLETE 和最终状态，重新计算既有 `window_cost` 与原始 J 核对；调用既有 `compare_completion_outcomes`，完整保留所有输入行李。

每件报告 reference/candidate 完成时刻、完成/未完成/未到达状态、真实完成延迟、迟到精确值或删失下界。单侧完成保留可证损害或改善方向；两侧未完成不能写成“完成相等”。未完成不会填入 horizon 当作实际完成时间。既有 observed-service gate 逐项输出；所有原生请求失败另列，防止仅审计可选策略动作漏掉上游真实需求请求。即使观察门槛通过，`strict_per_bag_nonharm_certified` 和 `protected_takeover_eligible` 仍为 false，TEST 不解锁。

旧完整 `JOINT_bridge_R0_legacy_P2201_001` 自比较（7200–59400 秒）已闭合验证：

| 全输入 | 按时完成 | 迟到完成 | 已到达未完成且过期 | 已到达未完成未过期 | 尚未到达 |
|---:|---:|---:|---:|---:|---:|
| 28,506 | 83 | 1,147 | 17,330 | 2,292 | 7,654 |

J=486,520,756.871371 bag·s，自比较增益 0；完成方向和迟到方向已知损害均 0。1,230 件完成精确相等；19,622 件两侧已到达未完成保持未知。原生请求包含 1,237 received、544 rejected、4 departed、4 undelivered，而可选策略 transfer decision 为 0；这是分母区别，不能据零策略失败称所有原生请求成功。

证据：`outputs/experiments/g31_ics_terminal_flow_20261021/full_legacy_self_service_audit_001.json`，其中 `per_bag` 含全部 28,506 行。它验证评价器，不是新方法优越性的证据。

另以短窗 `TF-current` 对 `TF-B1-60` 做实际非自比较，输出 `confirm003_current_vs60_service_audit_001.json`。共同 J=2,316,050.326901 bag·s，完成数均为 0：1,071 件已到达但未完成、27,435 件尚未到达。因此已知完成/迟到损害为 0 只表示尚无相应可观测结局，不能推成服务等价。候选 waiting-for-tray 积分比参考增加 7,059.273598 bag·s；所有原生失败由 6 增至 7，而可选策略失败仍为 0。完整窗口逐件评价仍是必要条件。

## 五笔实际预置单：计划到原生接收

以下全部来自 `TF_confirm_003_TF-B1-60_P2101`，闭合截止 H=18000 秒。每行是一笔唯一物理请求；全部是 `loader_optional → FORECAST_REPOSITION` 额外预置，ordinary return 实际覆盖为 0。来源真实空盘/未质押空盘均为 2、FIFO 保留均为 0；合法数按不同 tray_id 去重，不按 tray×destination 候选边计数。这两个盘各自可以成为单独候选，**不代表可以同时调走两个**：各源 `export_min_stock=0`，loader 的 `hard_minimum_reserve=max(1,export_min_stock)=1`，故 `source_cap=min(2,2-0-1)=1`。硬保留 1 与 FIFO 保留 0 是不同约束；五个计划的本源建议数量均为 1，已按绑定公开观察、原合同和完整候选目录逐一重算校验。目标当前等待行李均为 0；“预测缺口”指不搬运时 600 秒有限服务率投影的期末 backlog mass，不能解读成已经发生的行李等待。

| 源→目标 / tray | 决策时刻 | 来源空盘 / 本源合法盘 / 全目录合法盘 | 硬保留 / 本源同时供给上限 | 目标空盘 | 600 秒预测缺口 | 首次预测短缺偏移 | 建议数量 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 24→26 / initial:24:0 | 8400 | 2 / 2 / 4 | 1 / 1 | 0 | 0.142776 | 0.000 | 1 |
| 134→95 / initial:134:0 | 9060 | 2 / 2 / 12 | 1 / 1 | 1 | 0.190268 | 545.977 | 1 |
| 92→24 / initial:92:0 | 9420 | 2 / 2 / 12 | 1 / 1 | 0 | 0.759169 | 0.000 | 1 |
| 136→95 / initial:136:0 | 9720 | 2 / 2 / 6 | 1 / 1 | 1 | 0.813046 | 332.043 | 1 |
| 138→49 / initial:138:0 | 9780 | 2 / 2 / 4 | 1 / 1 | 0 | 0.968517 | 0.000 | 1 |

全部 dispatch slot=0，实际提交等于建议提交时刻；建议最早派出均为提交+2 秒。原生接受 5/5（请求入原生后均有 dispatching/departed 的正 ACK），接收 3/5，物理失败 0/5，在途删失 2/5。unique plan-item/order/submitted/accepted 分母均为 5，received 分子为 3；计划执行的提交率 100%，接收率 60%。这五笔来自五个单盘计划，不能称作已经观察到多盘计划执行。

| 源→目标 | 建议提交 / 最早派出 / 到达 | 原生接受 / 实际首边派出 | 原生接收 | 截止时在途下界 | 首行动作精确代理净增益 |
|---|---|---|---:|---:|---:|
| 24→26 | 8400 / 8402 / 8622.162 | 是 / 8403.000 | 8622.162 | — | 37.958792 |
| 134→95 | 9060 / 9062 / 9305.453 | 是 / 9062.001 | 9305.453 | — | 2.704903 |
| 92→24 | 9420 / 9422 / 9969.418 | 是 / 9422.001 | 9969.418 | — | 30.343897 |
| 136→95 | 9720 / 9722 / 10138.054 | 是 / 9722.001 | 未接收 | 8277.999 s | 93.722466 |
| 138→49 | 9780 / 9782 / 10014.177 | 是 / 9782.001 | 未接收 | 8217.999 s | 249.883207 |

“精确”只指按当前 ETA 重算 600 秒投影的首步收益，不是原生实际收益或服务无损保证。三个已接收样本的 ETA 残差约零；两个未接收样本的 ETA 低估下界分别为 7861.946 与 7985.823 秒。仅统计成功样本会掩盖这一长尾。

`target_by` 与 departure lease `native_expiry` 分开保存。例如 136→95 为 10052.043/10198.054，138→49 为 9780.000/10074.177；两笔都在 native expiry 前完成首边派出。expiry 不是到达截止，原生继续在途不能据此判作过期违规。完整 5 单的 request_id、状态、两种时间、硬保留/同时供给上限及原始事件见 `confirm003_actual_five_cases_003.json`，所有来源文件有 SHA256 绑定。早期 `_001.json` 尚未区分失败/删失，`_002.json` 尚未加入本源总量上限；审阅以 `_003.json` 为准。

## 两笔长期在途的共享资源证据

136→95 在 9789.001 秒到达节点 112，此后直到 18000 未发生下一次 EDGE_ENTER/EXIT，静止观察跨度 8210.999 秒。最终 112 本地队列 runtime ids 为 `[9, 14, 17, 18]`，本单为 14；排在前面的 9 是真实行李 `projected:1x:24` 的 storage_in，原生 resource_wait 明确等待 node 53 的接收位。14 自身没有独立 resource_wait 条目，不能把“没有等待条目”误读为可以立刻前行。

138→49 在 9820.651 秒到节点 139，9823.651 起记录等待 node 112；17786.916836 与 17787.917836 两次资源唤醒后仍等待。最终节点 112 被 initial:0:1、initial:49:1、initial:136:0、initial:149:0 四托盘占用，其中包含第一笔预置单。由此有可读的共同瓶颈链：139 等待 112；112 的队头行李等待 53，额外预置盘留在同一队列中。

节点 53 四盘处于真实 storage，绑定任务的 release_at 分别为 19706.996337、20228.875870、18980.807622、19119.607996，全部晚于短窗口截止。原生 wait graph 的 witnessed_hold_wait_cycles 为空，且有未来已登记的释放事件，因此证据支持有界窗口内的共享接收容量/队列阻塞，不支持永久死锁。它也不能单独证明两笔预置单造成了某件行李服务损害；该结论需要共同输入完整逐件对比。

下一步先消费完整 DEV 同父比较的完成方向、迟到方向和 all-native 请求状态，再检查长尾在途是否延续到更长窗口。P2201 完整结果与本例 P2101 是不同父，不能当作本例续跑。在不改物理合同前提下，可另行评估上层公开可见的共享节点拥塞/保守 ETA 是否应进入代价与重算；本次离线 diagnostics 不能送回在线 actor。当前不建议从三个准时样本得出静态 ETA 已充分校准的结论。

60 与 300 秒分箱的既有短窗审计包含 360 个同 owner、同时间、同公开状态与目录的配对决策，实际动作差异为 0；两组同为上述 5 单。多盘、多目标分配及竞争仅有纯函数测试覆盖，尚无实际 multi-order plan/ordinary-return 原生案例，报告保留这个边界。

## 复现

最终导出内存修复只作用于当前未冻结 `joint_campaign.py`：构建原有 terminal subset 后立即释放完整 native export；逐 owner 读取完整 observation 后仅保留 schema/now/owner_id/scope、完整 delivered_transfer_acks 与完整 client_transfer_ledger，下一次 observe 前释放其余大历史。每个 owner 导出有显式 `evidence_scope`，不会冒充完整协议观察；旧完整导出原件保留。没有截断、去重或成功筛选 transfer ACK。

`final_export_subset_equivalence_001.json` 记录旧闭合完整 DEV `E_N18_C10_P801_001`（native029，H59400）的 28,506 件行李、1,244 笔实际请求、12,626 条完整 ACK、1,244 条 ledger：裁剪前后物理字段、window_cost、physical_progress、全部请求的执行 joins、ACK/ledger 内容严格相等；另以 native030 confirm003 验证 wait_graph 不变。该验证不包含 TEST，也没有推算尚未实测的新 worker 峰值内存降幅。

```powershell
C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_service_audit <closed_reference_run> <closed_candidate_run> --output <new_audit.json>
C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_case_audit <closed_tf_run> <existing_chain_audit.json> --output <new_cases.json>
```

两条命令拒绝覆写已有报告。第一条读取共同输入逐件服务，第二条读取计划—订单—原生请求链与期末等待证据；都不会运行原生模拟。
