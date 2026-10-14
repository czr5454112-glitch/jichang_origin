# 第七轮查询截断的实际机制

27 条重新采集的轨迹与第六轮逐项相同，2467 次查询里保留了全部 93 次截断。正式影子为这 93 次加 6 个按公开查询 cell 预先匹配的成功对照，共 99×4 次独立生成；四档预算没有随收益调整。所有原 3000 预算查询精确复现，正式没有新物理分支。

93 次截断在区域 12000、48000 及全图 event 48000 下均没有合法完整候选。43 次 counterflow 空盘查询在全图参考中全部队列耗尽，50 次 near_full loaded 查询在全图中仍然触顶。这里并未将“搜索为空”当成不可行证明。

独立的公开资源证据更强：对这 93 个实际查询，排除本盘并按 `effective_reservations` 合并物理占用后，目的节点在 `[now+H, INFINITY)` 已没有额外一盘容量。原完整 witness 在到达时刻 `arrival≤now+H` 必须加入 `[arrival, INFINITY)` 的终点驻留；后者包含前者，所以在同一个固定公开 Snapshot 与原 witness 合同内不能成立。`ExecutionValidator.validate(next_edge)` 也先验证完整 witness，才校验实际前缀，因此证据同样适用于原 loaded 生成入口。它不预言随后一次重新规划时资源仍满，更不判定真实未来任务不可服务。

固定六个截断 cell 的最早代表都能定位到两个占满容量 2 的终点盘：

| 代表输入 | 查询 | 公开终点驻留 |
|---|---|---|
| counterflow/error02 q73 | 114→49 | initial:134:0 从 144；initial:49:0 从 110 |
| counterflow/error02 q105 | 116→26 | initial:26:0 从 187；warm_tray 从 162 |
| counterflow/error02 q106 | 49→26 | 同上 |
| counterflow/error06 q34 | 46→26 | initial:49:0 从 126；warm_tray 从 100 |
| counterflow/error06 q116 | 26→49 | initial:134:0 从 179；initial:26:0 从 188 |
| near_full/error00 q0 | 134→46 | receiver_stock 从 4；warm_tray 从 24 |

这些是当时公开承诺的无限驻留端点，不是读取未来 tape 后补写的占用。`analysis.json` 逐查询保存原时刻、node 容量、有效预留和四种搜索的完整工作阶段；1195 项核验全部通过，直接 CPU 1.84375 秒。

near_full 的同 cell 成功对照说明了证书为何必须每次重新计算：error00 的 q6 在 t8 时，receiver_stock 的 node46 预留已经变为 `[8,21)`，其新 node134 终点预留从 46 起；warm_tray 仍从 24 起驻留 node46。此时目的节点留出一盘容量，原生成器返回 K4、最早 usable33。对 t2 的证书不能延伸为对 t8 的判断，更不能提前读取 t8 的改变来作 t2 决策。

另外固定追踪六个代表及六个成功对照，只在原 `EventTimeSearch.paths` 外记录 yield/结束/异常，不改参数或排序。12/12 与原 3000 查询 rawpool、status、work 一致。六个截断代表中的四个，在 `tuple(search.paths(...))` 耗尽预算时分别已有 7、3、6、2 个 portal label 被 yield，但整组尚未物化，因异常未交给 macro；丢弃的 destination label 都为 0。六个成功对照没有这种中断。批收集造成工作浪费的副作用得到证实，但不能解释成这批存在合法完整候选被遗漏。追踪另计 12 次生成、0 次物理，CPU 1.046875 秒，原件为 `local_yield_trace.json`。

6 个成功对照的四档搜索都返回非空候选；全图参考有 3 个查询产生不同的授权 action key，没有更早的最小 usable。对于 slow empty，这个 key 是整个已承诺空调路线；对于 loaded next_edge，它是实际安全前缀，不应把两者都称为局部下一条边。当前只证明候选域有差异，尚无对这些新增动作的完整周期价值标签，也未据此更改部署策略。

因此当前直接优化方向是先做可审计的终点容量充分筛查，在已证实无完整 witness 的公开状态上避免重复搜索；保持原 K、未证实查询的原生成器、原 validator 和控制器选择。局部 streaming/安全间隔压缩只能作为后续独立研究，不能把 SIPP 的 earliest-arrival 支配定理直接套到本项目 no-wait、多资源和多候选任务上。
