# 固定提交 1d895da0：物理循环、保护与停滞审阅

固定提交：`1d895da00644c9486568fe74b835e057aa93f8c8`。本文是独立只读审阅条目，可并入总任务书。已读源码、已保存原始 input/final_result/client_calls，并用标准库独立重算三个 N26/P902 分支的实体占用、失败与停滞事件；**没有重建 C++、运行 native 或训练**。

## 结论

真实学习动作接入与普通同区回盘实现已有实质进展。但 27→1003 这个最大收益格，必须先排除一个源码和轨迹均强支持的底层活性缺陷：**等待资源的队首空返租约到期后，删除了唯一资源订阅者，却没有重新调度后续载货队列。** 目前应称为“高度可疑的失唤醒机制，待最小原生反例确认”，不能先归因为 RL 避开物理死锁。

## P0-1：到期移除等待队首后，剩余队列可能失去唤醒

### 源码定位

- `cpp/ics_core/runtime/circulation_runtime_impl.hpp:719–739`，`process_circulation_event` 的 `transfer_expiry` 分支：若 transfer 仍为 dispatching 且未入边，从所有 junction queue/source_queue 删除该 leg，然后调用 `fail_bag`。此分支没有对受影响队列执行 `observe_local_state`、队列变更通知或重新安排 arbitration。
- 同文件 `circulation_leg_failed:381–407`：386 行调用 `circulation_forget_resource_wait(runtime_id)`；失败实体隔离并释放未使用接收租约。
- `cpp/ics_core/runtime/circulation_recovery_impl.hpp:5–19` 删除所有该 leg 的 reverse wait 索引；126–136 的资源释放只唤醒仍登记的订阅者。
- `cpp/ics_core/runtime/event_driven_junction.hpp:14450–14452`：真实资源等待成立后不再安排固定时间轮询。`fail_bag:17116–17135` 本身也不唤醒后继队列。
- 对照同文件 `try_dispatch_one:13472–13495` 的其他失败出队路径，至少显式更新 local state/queue change。这里不能机械复制后就认为充分：`process_local_queue_update:15559–15575` 主要发 beacon，仍须通过现有调度入口确保剩余队列得到一次合法重评估。

### 已独立重算的实际证据

| 分支 | 业务完成 | 最后 EDGE_EXIT | 136 隔离时刻 | 隔离后节点136的 EDGE_ENTER/RESOURCE_WAIT/RESOURCE_WAKE | 最终136载货盘 |
|---|---:|---:|---:|---:|---:|
| G_N26_C00_P902_001 | 23 | 23552.403 | 11714.609000010001 | 0 | 3 |
| G_N26_C10_P902_001 | 27 | 23619.953 | 11534.609000010001 | 0 | 3 |
| G_N26_C11_S29_P902_001 | 1003 | 59399.799 | 隔离在149 | 149隔离后有239条同类事件 | 136未形成同样终态 |

C00 中 11042.001、11136.856、11196.856、11237.856 的节点136资源等待记录始终指向空盘 `initial:136:1`。三只载货盘随后到达136，在11714.609空盘到期前已经排在该节点。到期后该节点再无推进或资源等待事件。C10具有同样模式。

在失败时，137确实满；后续其实体盘离开，最终137为空。136→137正容量，137→112→53存在正容量静态路径。最终136的4个位置由3载货＋1隔离占满，138的4个位置全部由在途空盘远端接收租约占满；拥堵进一步堵住144/143/142的上游。**静态路径和空槽不是动态授权证明，但它们让“纯粹所有出口一直被占满”不足以解释136的无后继调度。** 保存材料没有此时完整 queue/wait 索引，不能宣布已证明永久死锁或已完成根因复现。

### 最小 native 反例规格（尚未执行）

4节点环 `3→0→1→2→3`，节点0容量2、节点1容量1、节点2容量2。空盘X初始在0，0时提交0→2空返，expiry=5；节点1由盘B占用到10。盘Y初始在3，1时有3→2业务，到0后排在X后。10时B的业务从1离开，释放1。预期：X在5后仍隔离，未入边、未改变容量；Y在下游释放后获得一次合法调度并完成。若旧实现Y持续留0而新实现恢复，则此反例闭合。另保留无expiry对照与checkpoint继续一致性。

### 最小修复边界

只修“失败出队也是队列可运行状态变化”：记录实际受影响节点，按现有源接纳/仲裁规则更新队列状态、失效已过期调度身份、重评估新队首并重新登记资源依赖；保留同时间一次仲裁、dispatch quantum、FIFO、容量、源保护和真实失败盘隔离。**先做 wakeup-only，不在同一补丁自动恢复失败盘，不延长expiry，不增容量、不改路线权重。** 避免定时全图扫描作为掩盖修复。

## P0-2：owner protocol 没有隔离空盘恢复命令

这是现有设计边界/运行完整性缺口，不是接收租约泄漏。

- `circulation_leg_failed:395–401` 明确只在未实际离开时释放未使用接收租约；独立原始记录中的4个N26/P902失败均有对应 `UNUSED_RECEIVING_RELEASED`，最终 `reception_node=-1`、`job=-1`，首边数0。
- `cpp/ics_core/bindings/circulation_session_binding.hpp:363–366,998–1001` 的 legacy recovery 在 owner protocol 模式明确被拒绝。
- `cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp:19–21` 允许的命令没有 recovery。
- `docs/g31_ics_circulation/LT2_PLANNING_CAPTURE_V2_DESIGN_20261014.md:48–51` 早已明确 legacy empty recovery 不属当前协议合同。不能说团队未披露此限制。
- `circulation_online_impl.hpp:269–289` 的legacy接口把 expected_generation覆盖成当前内部generation；不应绕过协议直接调用并冒充安全异步恢复。

### 最小新增恢复合同

新建版本化 `recover_failed_empty` 协议命令，绑定 owner命名空间、tray_id、失败transfer_id、公开可见generation/traversal、当前node、有效期；身份进入重试等价、checkpoint和ACK。源端在真正执行时重新验证owner/generation/当前node、失败leg属于该transfer、无载荷、未入首边、无在途/接收承诺、没有其他活跃承诺，初版仅白名单 `departure_lease_expired_before_physical_entry`。**不得用内部当前generation替换请求值。**

恢复只使同一实体由quarantined转empty，保留失败请求历史、计数和原位置，generation单增；后续搬运/装载仍走原授权、FIFO和首边。重复/丢ACK只返回同一恢复结果，不再次重置实体；不同generation、错误owner、已有首边/载货/接收承诺均拒绝。为此定义独立源端冷却和单generation至多一个活跃恢复命令，避免无限失败—恢复忙循环。全四组共享同一新恢复政策，收益归共同基础设施。

## P0诊断预算：先修唤醒，再分离恢复

建议首批最多8条native构造/续行，失败和初始化后退出也计数，预登记短例与机场例各自墙钟上限：

1. 旧版/修复版最小队首expiry反例各1条；每条≤90秒wall。旧版不失败则停止声称该根因，转向完整等待快照。
2. 新版无expiry及restore/继续一致性两条（可复用已建立小夹具）；每条≤90秒wall。
3. wakeup-only 后 N26/P902 的C10及冻结C11各1条机场完整续行，保持同输入/盘数/R1/恢复关闭，导出23640前后与59400的等待快照；每条上限依最近校准预登记，建议先≤900秒wall。
4. 只在唤醒修复通过后，对同一固定C10物理前缀做有/无新恢复的两条共同策略续行，先取完整1800秒窗口；观察恢复实际首边、后继加载、同节点/全系统推进、租约与隔离计数。

如果共同唤醒修复消除26盘大差异，记录为环境活性修复，停止用旧差异作为学习主要优势。已见过结果的901/902继续只用于诊断，正式泛化另取冻结新父组。新代码域使旧模型只能以明确登记的固定模型迁移诊断使用，不能静默替换源码域哈希。若修复后差异仍大，再执行“首次57→149/保持 × 后续固定C10/C11”的2×2成对机制检验；不能提前把17.78m件秒归于首次动作。

## 应验收的已有部分

`local_empty_return` 确实贯穿 typed input 默认scope（`circulation.hpp:56–64`）、Python解析/结果序列化（`bindings/circulation.cpp:110–117,243`）、live/protocol输入与client ledger（`circulation_session_binding.hpp:341–347,390–394,524,808`）、请求重试身份（`circulation_protocol_impl.hpp:43–46`）、checkpoint扩展（`circulation_checkpoint.hpp:138–150`）。提交与实际授予均检验同zone/同owner/static loader（`circulation_online_impl.hpp:61–81`、`circulation_runtime_impl.hpp:460–471`），后续源stock、接收capacity/reserve与真实leg沿用原路径（473–505）。本次源码范围未发现通过scope绕过这些保护的证据；没有重跑native029门禁。

`foundation_airport_batch_patch.py:67–129` 把修改绑定到当前公开观察/原batch/不可撤前缀，并且122–124逐项保留其他初始batch intent；`foundation_airport_protocol_v2.py:154–163` 每次pending提交后重新观察再求残余。hold在`foundation_airport_prospective_control.py:113–120,174–177`保持至同owner当前timestamp结束，配对版也有对应过滤；本次未发现明显“hold在残余立即复活”的问题。此合同保证初始batch其余内容保留、后续重新验证，不保证旧列表所有剩余intent最终都会提交。

## 服务保护与研究界限

当前patch保护只有current surplus/FIFO，明确不认证共享路径逐件不害（batch_patch.py:128–129）。当前已等待的远端需求分配可被当optional修改（opportunities.py:20–25）。这允许隔离研究，却不能等价为先前严格逐件保护已保留。

保存保护审计中，C11 P901 seed17相对C10有295个共同完成业务更晚，最大17394.699秒；seed29有274个更晚，最大15655.695秒。应表述“有明显服务取舍”，不能概括成只有极少数个别延误。全人口J、完成/准时、已知同件延误、未完成未知、各origin队列/尾部等待、真实失败/隔离、端口可用性应共同报告。不要以未完成业务删分母或用0物理违规计数替代服务不退化。

## 用户新增：加入极简无预测回流基线

现C00不是“往空盘最少的地方”。`analytic_control.transfer_candidates:500–545` 用当前已送达queue和承诺，保留本地FIFO/min-stock；568–601仅为terminal clearing选最近已知origin；604–661做当前未覆盖需求的最小ETA最大匹配。`foundation_airport_action_campaign.py:25` 的 common `predictive=True` 还允许已知在用盘的未来释放估计。C00缺少新增航班B1，但不等于完全无估计的库存均衡。

新增独立命名R0：仅实际可用未承诺空盘，先保留当前本地FIFO/min-stock与mandatory clearing；静态loader集合中按合法已知库存最少选接收端，平手按公开行程/节点号；将本方已承诺incoming去重记录为承诺而非实际现货；预先冻结最小库存差/冷却避免盘在低需求区来回搬运。其submit→ACK→接收/实体首边完全复用原协议。

同owner可用现有public node `actual_available`；跨owner只能使用真实已送达、带as-of的库存消息，未知不等于0。若需新增库存发布，应版本化并让各比较组具有同样公开消息，绝不能从最终result或offline全图状态构造中央即时库存。保持现C00名称与历史成绩，将R0单列。**共同失唤醒修复先于R0/C00/C10/RL的任何新比较。**

## 可携带的独立重算

```text
python physical_recompute.py --root <fixed-commit-export> --output <new-output>/physical_stall_recompute.json
```

脚本只用标准库，读3条固定分支input/final_result/client_calls，重建实体/接收租约占用并逐盘核对最终原始位置。输出保留输入SHA与源码/轨迹的推断边界；native_starts=0、fit_calls=0。当前已实际执行成功。
