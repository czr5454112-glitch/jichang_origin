# 2x 终止后是否迁移026：只读设计与成本记录

2026-10-15，当前优先完成相同024基线。本记录不预定迁移，不修改活动49来源，不准备新native包，也没有新native执行。最终选择须等14:30实际终态、最新完整sealed cut、终态receipt及准确parent/worker缺席证据；不能把运行中heartbeat当可续跑原生checkpoint。

读取时 `full024_chained_2x_20261015_001/heartbeat.json` 为segment486/H77319.45352；最新真实seal是475/H75600：`72f6545c8e6aea9fa109f95a584d9136cadb15659caa9a9dd57a2cd497b8d35a`。57012件全部保留，56308件已到达。这个活动快照会继续变化，不是未来迁移切点承诺。

## 最小可执行设计

现有 [resume_chained_sealed_stream](../../scripts/experiments/g31_ics_circulation/resume_chained_sealed_stream.py) 明确禁止binary变化，不能直接替换CLI或改旧cut的binary字段。若另行决定迁移，使用独立新schema/封装，分别记录原024 producer/input/policy/cut authority和candidate026 build/binary authority。原cut、receipt、heartbeat、全prefix及未sealed尾片原字节保留。

1. 用026和同一57012件输入创建fresh session，复用 [NativeTapeReconstructor](../../scripts/experiments/g31_ics_circulation/reconstruct_native_tape.py) 逐条实际提交、重试、查询、通知推进、result核对。先要求 `finish(原024 contemporaneous seal)` 通过；失败停止，不能导出已验证session或继续policy。不能把1x/H54000验收推广成2x迁移已通过。
2. 复用 [026验收 late_worker](../../scripts/experiments/g31_ics_circulation/accept_native_delivery_indices.py) 的局部门：在验证后的checkpoint，取旧未sealed尾部第一个完整500-owner分片，两臂串行reference/indexed；重置derived indices，分别用独立Python state。完整ordered raw、公共视图和两臂终点seal必须相同，并与原实际尾片已保存字段一致。没有原终点seal则不得声称原隐藏终点相同。若没有完整尾片，必须另定更早已sealed切点或保持024，不能制造对照。
3. 门通过后在同一个worker中直接保留indexed臂session/state继续，避免gate子进程退出后又重建一次。组合trace只追加一次indexed门分片；保留原offset、pending owner round、next target、事件与激活预算、完整输入、原owner配置和原公共旅行池。参考臂及旧excluded tail作为诊断证据保留，不重复追加进物理执行trace。
4. 输出明确记录024 prefix与026 continuation的binary来源分段，不能称全程同binary。继续使用完整原流物理审计；更新迁移专属校验，而不是绕过旧resume的same-binary校验。
5. 所有祖先controller/export/seal累计费、excluded tail费、祖先重建费、新重建费、两臂/视图/额外seal/导出费均保留。祖先累计controller费用已经含更早attempt，不能再把所有旧heartbeat相加而双计。父进程wall和分项费用分别陈列，不相加冒充互斥分解。未发布尾部开销仍unknown。

## 已测成本与选择条件

| 原件 | 实测事实 |
|---|---|
| `full024_resumed_2x_20261015_001/reconstruction.json` | 重建137片到H28800：294.1024068s |
| `full024_chained_2x_20261015_001/reconstruction.json` | 重建397片到H64800：1904.4055785s；共1026667次ACK查询、373673次native边界 |
| 上述两个祖先重建 | 累计2198.5079853s，未来仍需保留 |
| 实际024分片476/480/486 | 每片500 owner更新分别37.5310264/38.5705610/38.1529190s |
| 实际024分片475/H75600 | 336 owner更新24.3260685s，单次全历史seal另耗198.9683024s |
| `native026_acceptance_001/late/assessment.json`，1x/H54000后500更新 | reference15.404048s、indexed8.1961013s，同ordered trace/view/seal；仅该1x窗口事实 |

026优化的是delivered demand/forecast观察选择。重建器不重新执行policy观察，因此不存在已证明的026前缀重建加速；1x的843.2376s重建和2x的1904.4056s重建也不能跨输入直接比较。

相对于再次用024续跑，迁移是否省时取决于：新026重建与新024重建之差 + 两臂/额外seal/视图开销，是否小于剩余controller工作的实际节省。不能把1x的46.8%窗口节省当2x预测。两个额外晚期seal可能很昂贵，需实记；越接近H86400，固定验收费越可能超过收益。

原2x输入的最后arrival为82403.72582；H75600/79200/82800前分别有55290/56757/57012件已到达。H82800以后没有新业务到达，但仍可能有重试、预测和冷却激活，因此不能线性外推较早owner密度。等实际终态切点后再决策；优先保留继续024这一更简单的选项。不据此宣称100ms、孤立速度或业务成功。
