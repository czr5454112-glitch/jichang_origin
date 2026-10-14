# 可选终点容量筛查合同

`terminal_capacity_screen.py` 只作为显式安装的包装器使用，不改变默认生成器、执行 validator、原 K 或控制器目标。安装顺序为 replay cache → same-zone policy → terminal screen → Budget accounting。

原 `candidate_reservations` 在最后一条边到达时（零边路线则为 now）增加终点 node 的 `[arrival, INFINITY)` 占位；unload 和 hold 另外占 reception，但不缩短 node 驻留。原 finite-horizon 生成器只允许 `arrival≤now+H`。在有效预留合并、排除本盘之后，如果 `[now+H, INFINITY)` 的任一非空时段不能再加入一盘，那么每个原终点区间都包含该冲突。这是固定公开 Snapshot 内完整 witness 不存在的充分条件。

这里不能只看 now+H 当刻：迟于 horizon 的已承诺 old transit 到达或终点 stock 仍然会与无限驻留冲突。释放恰好等于 horizon 的区间已结束；INFINITY 时点的空区间不构成证据。同一 tray 的显式和推导占位由原 `effective_reservations` 合并，自身所有占位被排除。no-wait 和 hold 不会消除此 node 必要条件。next_edge 仍先验证整条 witness，因此保留相同必要条件。未来尚未发生的资源释放、真实任务 tape 或未发布预测不进入筛查。

`certified=False` 包括未证实、非法/不支持输入和 bounded record cap 未知；全部交给原生成器。未知 bag 等行为保持原 `invalid_request`。明确证实的查询仍占一个 query call，返回原样空 tuple，search work 为 0，另记 screen record work、screen CPU 和 observation hash CPU。record work 不冒充 Python 排序比较总次数，调用总 CPU 包含排序和观测。

每次真实查询保存开始生成前的完整公开 Snapshot SHA，部署对照要求时间、version、bag/tray、目的、K、Snapshot SHA 和完整有序 rawpool 全等。实际物理 tick、事件、任务 ledger、slow 实际 proposal/trigger 和停止条件全等。搜索诊断明确发生改变；由于跳过空搜索也跳过私有 cache warming，cache/LRU 单列，不假称逐字段全等。

全部 2467 旧查询做筛查保守性与结构工作分析，不额外 generate。固定 3 nominal pilot 通过后独立跑全部 27 原输入，正式重复 pilot，分别计物理和 CPU；没有原件回填。当前完整部署 CPU 同时含新观测器，不能直接与观测范围不同的旧批相减宣称算法速度倍数；算法工作减少、筛查额外工作和实际 CPU 分开报告。
