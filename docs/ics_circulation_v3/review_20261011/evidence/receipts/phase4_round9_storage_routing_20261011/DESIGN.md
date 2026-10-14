# Round9 持盘早包路由实现记录

范围是固定且随袋合法公告的 `on_carrier` 单 waypoint 合同，库位是可等待节点的有限容量代理。未声称现场 EBS 接口、动态 release、off-carrier 检索或原图整日业务已完成。

`StorageCandidateGenerator` 包装既有生成器。没有 storage 合同的袋以及空盘调用原 delegate，候选对象、ID、K、状态和展开数原样透传。含合同的袋采用 `(node, tick, storage visited)` 标签，整个 witness 保留最终 `Bag.destination`，不把去库、出库当两个完成任务。库内等待形成原 `node:<id>` 半开预约，release 前不离库，中途不生成卸载或空盘信用。

没有采用“两段分别调用原生成器再拼接”：原生成器会将临时终点视作永久驻留、卸载/可用时刻；两段各自预算又会产生额外隐形工作及局部最优遗漏。新 product search 直接共用一次 horizon、expansion_limit、deadline_ms、K，完整候选仍由同一个 ExecutionValidator 原子校验。预算不足保留 unknown 语义，不报告物理不可行。

图和两组反向距离在每次 storage 请求计时内冷建，不添加未被现有缓存审计记录的隐藏持久 cache。图预处理、no-wait 时间端点投影、搜索标签和完整 witness 校验共用展开预算。等待时点使用已有 EventTimeSearch 对下游资源端点的投影，EBS 节点另加入 release 下界。曾到/曾离库进度只由实际事件或明确私有 replacement 冻结前缀投影提供；路由器不根据当前节点猜过去事件。

这改变了有 EBS 合同的候选域，是显式新增物理边 product search；没有宣称与原 regional 路由同域，也没有从候选更多推出算法收益。标签保留数为 K，event-time 表示与有限预算仍可能漏候选，不给全局最优或完整性证明。普通袋仍严格桥接。

`tests/test_ics_circulation_v3_storage_routing.py` 用手算反例覆盖必经、持盘等待、有限/满库、上游禁等、跨 owner 的 no-wait 链、最终硬截止、延迟入库、已有进度、非法进度、cold 预算、wall deadline、deepcopy、K 与普通袋/空盘桥接。每次执行由 `run_authoring.py` 生成新的 run 目录，保留失败输出、源快照、前后 SHA 和区间 CPU；不覆盖失败。设计与交互耗时未统一计量，单列 unknown auxiliary。
