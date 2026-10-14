# Round11 投射长窗口：终点完整驻留导致的重复搜索

2026-10-11。仅读取 root 四格试验中已完整保存的 checkpoint，复制到诊断目录后执行 shadow query。没有读取仍写入的 `queries.jsonl.gz`，没有推进、提交、改变生产源码/预算/容量或运行输入，不能把本诊断称为部署改善。

## 1. 先核对 10200，再明确追加 10800

[diagnosis_001/result.json](diagnosis_001/result.json) 绑定正式 `projected_h21600_001/checkpoint_10200.pickle`，SHA `71349ce671d8c18b8fbf557ea77108dabbd6c9a2d58b9f945ccf51ddbf9a3e5f`。该 checkpoint 为 `phase=load`，已观测 12 袋，11 盘全有 plan，没有可用的 loaded/no-plan，因此此快照没有查询复现；0 query、0 physics。这避免凭 root 的增长现象预设 10200 已发生拥堵。

root 随后授权追加已保存的 10800 原件：[diagnosis_002/result.json](diagnosis_002/result.json)，checkpoint SHA `dc7dfa5a51ba9b28826ef95ea02a59d7aba622c2dd9901cea9b4cd0b6c42d02b`。该状态观测 22 袋、0 完成、9 plans、2 loaded/no-plan。每个查询从同一 checkpoint 独立恢复原 private cache，未借前一个 shadow query 预热；cache export SHA 前后均为 `66ffcea8a995751da830bdbb5fcfd8f13def16f99f0c2fa039695838c77a6f68`。

实际默认配置为 `route_selector=None`，所以 `Simulation._generate` 请求 **K=1**；配置中的 candidate_count=4 未被错用。其他配置为 h21600、work10000、deadline_ms=None、isolated_replay_v1、whole_route。没有调用 observe/advance，以免加载或提交改变 checkpoint；直接对已有 loaded/no-plan tray 调用真实 `_generate`，保留其额外 validator 过滤。

## 2. 两个查询的实际结果

| 袋 / 持盘 | load tick / 当前节点 | 结果 | query CPU s | 日历区间扫描 / product labels / 完整验证 |
|---|---|---|---:|---|
| projected:1x:7 / proxy-initial-92 | 10434 / 0 | 10000 耗尽，0 候选 | 0.156250 | 5193 / 3514 / 1 |
| projected:1x:10 / proxy-initial-138 | 10489 / 95 | 10000 耗尽，0 候选 | 0.187500 | 5212 / 3439 / 1 |

两袋均 protected，final=47、storage=53、release=19500、deadline=22200；都尚无 storage ingress progress。资源放松下界为 final arrival 19684。分别再从原 checkpoint 恢复，执行一次显式标记的 validator instrumentation query：每次仅出现一个完整验证，arrival19684/unload19685，均以 `capacity:node:47@19684` 拒绝。前者 14 腿，后者 27 腿。插桩重放的候选、status、work 与未插桩查询完全相同；其 CPU 含插桩开销，不能用于未经插桩算法的性能断言。

这些查询中静态 topology/lower 已 cache hit，冷等价逻辑工作 566，实际预处理重用；没有证据支持再优化 static cache 是此处主因。约 52% 的工作发生在 interval scans、34–35% 在 product labels，其余是合法预处理、事件投射及一次最终验证。不能因为找到了一个根因就删除这些工作计量。

当前四条他盘完整承诺如下；全部是 node47 的有限容量预约，未凭“有预约”误当满载：

| tray | start | end |
|---|---:|---:|
| proxy-initial-0 | 19677 | 1000000000000 |
| proxy-initial-24 | 19678 | 1000000000000 |
| proxy-initial-95 | 19681 | 1000000000000 |
| proxy-initial-49 | 19682 | 1000000000000 |

节点容量为 4，19682 之后 occupancy=4。这解释了 19684 的实际完整候选拒绝。当前 search 继续展开晚到/循环标签也无法让 final 驻留避开这四个无限尾预约。运行器每 tick 重试 loaded/no-plan，因此装盘后可反复消耗完整预算；本诊断没有读取未封存 query 流来计算确切重试次数，也没有声称精确归因 10200–10800 的每一秒 CPU。

## 3. 终点必要条件为何可用于存储完整 witness

已有 `terminal_capacity_certificate` 在两个 shadow 查询均返回 sufficient certificate：cutoff=`now+horizon=32400`，other occupancy=capacity=4，screen_work332。其分解为 input_records166、effective_slots157、target_event_insertions8、event_visits1；调用 CPU 落在系统 process_time 的 0 分辨格，wall 约 0.00045 秒，不能称零成本。

证明只使用当前物理合同：

1. 原 generator 在该查询域生成的任何 full witness 最终到达 `a <= now+horizon`；protected deadline 只会进一步缩小此域。
2. `runtime.candidate_reservations` 无论普通/StorageBag，均为不变的最终 destination 生成 `[a, INFINITY)` 的节点驻留。存储要求增加中途 waypoint/release，不把入库当完成，不移除最终驻留。
3. 因而任何该域候选都占用公共子区间 `[now+horizon,INFINITY)`。若该区间任一时刻已有其他盘占用达到容量，再加当前盘必冲突；不论其早到、晚到、绕路或提前经过 final。
4. 两个查询在 32400 的四条他盘预约就是该冲突见证。屏蔽的是**当前公开日历下这次完整 witness 查询域**，不是现实中永久不可行、不是不可调整调度的全系统证明。

该证明不因 storage release、有限库位或同盘而失效，但也不能把只到库的 prefix 套进来。替换视图要使用已证明正确的 frozen/calendar 合同；当前 root 业务查询是未计划 tray 的 whole_route，不涉及取消他盘预约。未来实际到达卸载后，空盘控制可能给其他盘建立离场计划，node47 无限驻留可能变为有限；证书必须对新状态重新计算，不能跨版本持久缓存负结果。

`TerminalScreenGenerator` 目前明确要求 `type(generator) is RegionalCandidateGenerator`；直接在 wrapper 上换类型或删检查不算完成支持。正式接入仍需显式允许已知 storage delegate、保留 invalid contract/request 行为、normal/no-storage 桥接、checkpoint/cache 恢复与独立小图反例。更合理的储存查询入口可在合法性校验后、昂贵搜索前执行等价证书。

**预算不能靠外置 screen 偷加：**当前辅助 certificate 的 work 与原 10000 只作分开 shadow 计量；正式要把 screen 的输入、合并、事件扫描工作计入原共同预算，并在计量中途耗尽时返回 unknown/原预算耗尽，不能给没有完成的检查贴 certificate。未能认证时仍保留搜索硬约束，说明由于新预处理占预算可能改变 bounded candidate set；不能宣称无条件保留所有旧预算边界结果。跳过查询不应偷偷预热 private cache，也不能改动普通/no-storage 默认路径。这个扩展本轮尚未实现。

## 4. 资源、源绑定与后续

| 主 receipt | CPU s | wall s | standalone query | physics |
|---|---:|---:|---:|---:|
| diagnosis_001 | 0.421875 | 0.434625 | 0 | 0 |
| diagnosis_002 | 1.265625 | 1.313991 | 4（2 默认 + 2 明示插桩重放） | 0 |

合计已计量 CPU **1.687500 秒**、4 查询、0 物理运行/继续。主 receipt 已包含 imports、读取、SHA、source snapshot、恢复、certificate、query、validator 与序列化；嵌套 query CPU 不再相加。两次状态不变、正式 checkpoint 字节不变、所有绑定源码前后 SHA 相同。完整 snapshot、完整配置、candidate/verdict、cache digest、源码副本均在对应目录；没有删除失败查询。此前源码阅读、脚本编辑、工具编排为未计量辅助工作。

下一步应待四格正式运行封存，以此快照作为失败基准，做包含存储的新终点容量 screen 支持及同预算独立对照。当前证据已经足以解释两个具体查询的无效展开，但不支持扩节点容量、删任务、放宽 full witness、把 K4 当实际默认，或把不同输入的投射完成率记成同 OD 算法改善。
