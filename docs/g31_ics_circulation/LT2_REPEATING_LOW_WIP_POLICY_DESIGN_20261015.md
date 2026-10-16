# 原权限、单循环盘的有界重复供盘设计

2026-10-15。仅设计与保存数据分析；未修改任何既有实验/控制器/native来源，未执行新native。后续实现应在独立模块中复用冻结005的停车与首次供盘，不能通过增加第四个特例继续堆叠。

## 已证事实与目标

`original_low_wip_third_prepare_001` 已由独立保存数据重放复核：14,600条API、25个实际received物理ACK、全部28,506件和22盘、同盘job2/6/8三条LOAD→UNLOAD→HOLD链。第三件从49到46，终点46属于 `owner:system_international`。前两次选择及其全部业务receipt与reuse002一致；源26下一头job14不可达，未越过它。独立回执为 `original_low_wip_third_independent_actual_review_001.json`，SHA256 `a86f11070293e70f0a42d5dba4b6cd1d21005847be05e3b839e7778a02d92a3c`。

下一目标是同一规则在当前持有者变化后还能继续，且能在缺证、拒绝或资源阻塞时明确停止。不是证明39件可实现，更不是完成全部业务或逐件保护。39仍只是原图、原FIFO和不可卸载条件下的松弛必要上界。

cap3/cap8是**累计供盘次数**，两臂始终只有1个循环盘，不能写成WIP3对WIP8。Root已接受两臂H86400及共同2400秒有限预算；本文不是最优WIP或新颖性主张。

## 最小策略

保留原22盘、停车匹配、完整原28506输入、R1=false、2秒wire、0.2秒ACK、60秒同ID重试、原FIFO/Storage/正容量图。21个停盘之后永不再调用。只有预注册token可发生新的物理操作。两个owner各自运行相同本地状态机，不共享运行时状态或对方outbox。

启动阶段完全调用冻结005，直到各自看到首次供盘/其实际peer action；此边界之前要求完整API顺序相同。此后使用通用循环，不继承固定second/third字段，也不固定最初token_owner。

1. 每次激活先处理自己实际ACK与同ID重试。当前owner只有在自己的fresh policy view中恰好看到token empty、无job/edge/reception、available<=now，且节点resource_owner是自己，才能成为下一轮发起者。旧owner的过期快照不授予权利。
2. 除首次供盘外，每轮必须有自己实际收到的v2 self-copy，包含该token在自己拥有的目的节点的最新 `UNLOAD_COMPLETE` receipt；当前empty/available另外证明HOLD已结束。用原生receipt_id作为一次性permit，提交前即标记已消费。已消费receipt不能因重复ACK、重复/乱序消息、失败或owner再次看到旧事实而重开。
3. 源自己尚有任何供盘未获实际received ACK时，不能开启下一轮。新owner不能读源私有outbox；它只认最新已交付peer v2的完整physical-action coverage，要求所有已声明parking/supply动作均有实际received ACK。未知kind、失败ACK、遗漏coverage、过期/withdrawn最新消息均不作“无在途操作”。
4. 发起者仅在本地返空候选存在时发布原生 `planning_snapshot_v2` 邀请。peer看到真正交付的邀请中有源拥有的empty token和该源新完成receipt，才回复自己的原生v2事实；没有token的回复不是邀请，不产生reply-to-reply循环。回复必须不早于本轮自己的邀请capture；原TTL/最新版本优先规则不变。
5. **必要的ACK状态转发：** 每个owner自己的供盘ACK首次变为received/terminal失败时，另发一次原生v2快照，即使token已离开自己。否则源在提交后保持安静，会让新目的owner永远缺少peer的received证据。该消息只有原生捕获体，不添加自定义payload，不从消息名推断tray/job/目的地。
6. 从实际peer body中按每个origin取最早 `(arrival,business_bag_id)` waiting头，再按同键排序各头。仍用冻结 `eligible_head` 的跨区权限、供盘正容量路、origin→mandatoryStorage→destination正容量路筛选。某loader头不可达时保留它、不得取该loader后件；可考虑另一loader的真实头。没有跨区头就等待新已交付事实，不增加同区中转或临时换停车盘。
7. 每轮最多提交一个新immutable transfer。ID用native UTF8 owner namespace及消费的completion receipt身份构造；ID仅作本地去重，不充当远端意图消息。请求保留真实source、所选origin、2秒wire、当前earliest_departure和原2000秒expiry规则。源记录完整选择的已交付FIFO体和自己的permit。任何拒绝/过期/未收到ACK均保留，不能换job或新ID绕过失败。
8. 成功的“供盘ACK”不等于业务完成。该轮业务链必须在保存的原生receipt中实际看到所选job同token的LOAD/UNLOAD/HOLD；在线下一轮只靠上述当前owner事实与真实完成receipt。不能根据ETA、job从capture消失或token已入对区推断完成。

### 该合同为什么可以跨owner

v2 `submitted_physical_actions` 只有request_id/kind/source/last_delivered_ack，没有tray、目的loader或选中job。不能把这个字段当远端payload查询。新owner依据自己源拥有的真实完成receipt和本地token状态接管，而不是伪造前一owner选中job的知识。所有已知physical动作received是保守串行屏障，**不是**其与某job的远端映射证明。

在本实验明确的两owner合作规则下，只有一个token可移动、其余21盘固定，且每次提交前必须有本地真实empty。这阻止两个owner并发提交同盘新操作；同一owner的已消费permit和pending动作阻止重复提交。此论证依赖预声明合作策略，不是native快照能证明“不存在未来Python计划”。如果引入第三方动作或额外token，当前合同应拒绝，而不能沿用该论证。

## 有限分母、停止与独立对照

建议首次注册两个分支：同一通用policy的供盘上限3与8；其余参数完全相同、H86400、全部28506保留。每分支最多22次parking加其供盘上限，native事件/激活/消息预算写死。两个分支应在第三次真实完成前产生相同决策/通知/API/物理前缀（只排已列举有限非负诊断时钟），不拿历史H28800的third001冒充完整H86400对照。

推荐父共享硬上限2400秒作为待root审定的有限实验预算，覆盖两分支构建/完整运行/导出/纯核验；不是每分支2400，也不是100ms放宽。理由是已测third001总254.55秒仅到H28800，H86400和更晚大capture可能更贵；不能保证该预算足够。未执行/超时/错误分支一直保留unknown。若root先只批一个候选，不能据它报告增益或保护。

到供盘上限后不再创建新物理动作；仍收集全部既有ACK、实际完成/返空并到达H86400。缺少已交付证据或当前无可达头只是等待，不是全工作已完成。最新capture只有当时已释放任务，不能用离线未来任务表宣称永久无需求。消息预算耗尽、物理拒绝、缺completion、未知owner、scope缺口或H处仍pending，均须给出具体unknown/有限失败状态，保留每条已发生动作和所有业务分母。

实现明确区分策略失败与停止仿真：publication/physical决定失败进入实验级 `halt_new_actions`，两个owner继续真实refresh/immutable retry及native推进，直到H或native/父硬预算；到H仍为 `horizon_complete_with_policy_failure`。这个共享失败标志只用于截尾，不参与业务选择或授予owner权限。达到累计cap并实际本地返空后，sticky `cap_observed` 阻止快照过期后重启邀请；既有ACK/retry仍保留。

另外预声明每owner最多512个循环阶段v2新请求；停车阶段原记录另完整保留。若用尽，停止新供盘，保持immutable retries和native物理推进至H/预算，结果标记 `unknown_publication_budget`。该上限是资源界，不能把被截断轮次当无需求。所有阶段耗时、日志写入、完整setup、GC、重试和未知尾部保留；不关闭GC、不按件平均。

## 纯验证和实际门必须覆盖

- 原005完整API前缀；通用cap3/cap8同前缀；无producer outcome参与在线选择。
- 真实旧ACK已received但token仍loading/holding时不得发新供盘；源返回receipt较新但self ACK未交付不得使用。
- 旧receipt重复、先后乱序、最新过期/withdrawn、防旧版本复活；消费permit后rejection不能补发新ID或换头。
- token由domestic到international后，旧owner不再可发；新owner缺peer received时等待，ACK状态原生转发后才能继续。
- peer覆盖缺一action/非terminal/未知kind、owner不符、self/peer时间倒序、同token重复receipt身份均fail closed。
- 同origin不可达头挡住后件，但不挡另一个origin的合法头；无同区跨区绕行fallback。
- 新邀请、reply、ACK relay均有有限去重；消息预算耗尽、H截断、硬timeout不会删除分母或伪造闭合。
- 每轮实际LOAD/UNLOAD/HOLD与声明job唯一对应，22盘全量不丢；21停车盘无后续物理request，只有token移位。

## 只作必要路径筛查的下一步预测

使用原输入及已经完成的2/6/8做离线筛查，在21760时、token节点46，domestic当前最早可达头会是源95/job3，目的47。公共正容量图给出46→95约423.038秒、95→Storage53约409.653秒、53→47约188.106秒。其他可达头包括149/job9、57/job11、136/job106、138/job108；92/job16和134/job110仍不可达。这个筛查没有实际当前占用/许可交付，也没有未来native结果，不能写进policy的job选择，更不能作到达上界或承诺第四件完成。实际选择必须在新owner自己完成receipt、自副本、peer已交付FIFO和当前token状态齐备后重新得出。

以上策略仍可能被原停车占用、原FIFO、动态预约或Storage挡住。若实际cap8没有比cap3多完成，不应再挑loader/时点寻找正例；先保留具体阻塞链，判断通用策略的受限域。

实现位于独立 `research_original_low_wip_repeat.py`、`verify_original_low_wip_repeat.py`、`launch_original_low_wip_repeat.py`，旧005/reuse/third源码未改。launcher复用既有 `bounded_windows_job.py`，Job assignment完成才释放stdin barrier；两native子进程串行，所有campaign import/验证在同一树预算内。外层Python启动至BOOT前仍单独标为未测，不据此给冷启动100ms证书。
