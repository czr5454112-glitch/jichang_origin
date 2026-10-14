# 原图 24 件、五策略 native015 独立事件审核

审核直接读取 `event_protocol_original24_015_001` 已完成的五套运行原始事件、请求/ACK 账和实际送达消息，没有重新运行 native。已核对共同输入、binary `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`、发布运行 `source_changed=[]`。全部断言通过；逐循环事件账在 `assessment.json`，逐条预测与时钟/迟到核对在 `detail.json`。

| 策略 | 完成 / 迟到 | 真实同盘返回再服务 | 累计到达至卸载时间 | 预测送达 / 拒绝 |
|---|---|---:|---:|---:|
| periodic_reactive | 24 / 19 | 23 | 418514.272581 | 0 / 0 |
| periodic_predictive | 24 / 19 | 23 | 414198.867581 | 0 / 16 |
| event_reactive | 24 / 19 | 23 | 414592.459581 | 0 / 0 |
| event_predictive | 24 / 19 | 23 | 414170.459581 | 204 / 320 |
| event_joint | 24 / 19 | 23 | 414170.459581 | 204 / 320 |

五套均逐一核对了实际卸载、hold 完成、真实 export grant、逐边空盘行驶、接收、收到 ACK、同盘再次装载和卸载。没有以预测释放替代空盘，没有提前跳过 hold；原始 circulation receipt 时间严格不倒退。event_predictive / event_joint 的 23 次返供请求均提前于对应实际卸载，真实 grant 仍在 hold 完成之后。

## 204 条预测的实际含义

event_predictive 和 event_joint 各 204 条已送达预测，全部与同 bag/tray/from 的真实下一跳匹配，入边估计误差严格为 0。它们全部来自节点服务恰为 2 秒的阶段，且全部在真实入边之后 **0.5 秒**才送达；没有一条先于真实入边。送达时估计窗口均尚未结束。

因此它们是准确描述已经入边、仍在持续的条件占用窗口，不能据此声称已提前公布入边或提前资源预约成功。320 条拒绝全部是 `no_local_uncommitted_loaded_service`；periodic_predictive 仍为 16 条同理由拒绝。消息送达数不是业务收益，也不是硬可行证明。

## 逐件比较与限制

- event_reactive 相对 periodic_reactive：21 件更快、0 件更慢，累计减少 3921.813 秒。
- event_predictive 相对 periodic_predictive：仅 `projected:1x:6` 更快 28.408 秒，其余相同。该件对应的首次返回由 periodic 的实际可用盘请求变成 event 的条件释放请求；请求时间从 19800 变为 19757.642。此为实际事件关联，尚未单独消融证明收益来自服务窗口。
- event_predictive 相对 event_reactive：21 件更快、0 件更慢，累计减少 422 秒。
- event_joint 与 event_predictive：逐件完成时间和规范化物理事件哈希完全相同。

共同输入中允许后缀改路的 business ID 数为 0，五套 route 请求也均为 0。故这些结果不能证明 R1 方法增量或 R1/R2 联合创新。19 件迟到在五套都存在；“已完成”不等于满足时限。这里仍是原图选出的同一单盘 24 件子集，不是全部 28506 件母体完成证明，也不是完整 100ms 认证。

检查了 event_reactive 的 3117 次、event_predictive / event_joint 各 4641 次含原生通知的激活，所有通知 `observed_at <= owner activation time`，无 epsilon 放宽。运行壁钟受并行编译等影响，本审核不把这些 campaign 的 wall time 当作正式性能比较。

复现只读审核：运行同目录 `review.py` 和 `review_detail.py`。两脚本会拒绝覆盖已有结果；原始五策略数据均保留。此处是正确性、接通和基础策略的证据，创新性仍未放行。
