# G4IRSF31 固定提交独立审计证据包

> 固定提交：`46cc46ab6bc121628fd6357e9f3c7636745fd732`  
> 本文件是 `G4IRSF32_cross_map_next_stage_action_plan.md` 的证据附录。它不替代主文档。

## 1. Headline 重算

### 容量

- 南宁：40 admitted cells = 34 S4 wins + 6 full-pop ceiling ties + 0 losses。
- map2：38 measured cells = 23 S4 wins + 9 full-pop ceiling ties + 6 topology-upper ties + 0 losses。
- 合计：78 measured cells = 57 wins + 21 ties + 0 losses。
- map2 `pair_5_7` 的 1×和2×均为 `NOT_MEASURED`，不在 38 格内。

### 同释放、全人口时延

- 南宁：3 eligible speeds × 5 metrics = 15；14 S4 lower + 1 physical-resolution tie。
- map2：4 eligible speeds × 5 metrics = 20；17 S4 lower + 3 physical-resolution ties。
- 合计：35；31 S4 lower + 4 ties + 0 HCA lower。

## 2. 因果边界

`outputs/tables/g4irsf31_reporting.json::protocol` 明确记录：

- capacity 使用相同 scheduled population 和 fixed horizon；
- each framework own source admission；
- capacity 不是 segment-release paired；
- own-source timing 禁止生成跨算法 verdict；
- stable timing 只来自 same-HCA-release、full-pop artifacts；
- survivor-only timing 禁止；
- fault release pairing 为 false。

因此：

- 2×完成量优势是系统承载结论；
- 1× paired 时延才是逐 segment release 对齐后的正式时延结论；
- fault 场景当前只作容量结论。

## 3. 混合来源节点 49

Profile 证据：

- node53：type7 empty-pallet storage proxy，outgoing 49；
- node49：type1 loader/source，service 1.0，outgoing 50；
- node50：type4，service 2.0；
- node49 graph indegree=1，但有 local source。

Runtime 证据：

- destination merge edge 多处要求 `incoming_degree(target)>1`；
- node49 不会仅因 local source + one incoming edge 而进入图论 merge；
- service calendar 仍存在，因此这是仲裁/公平性表达缺口，不是已证明的物理互斥失效。

## 4. S4 分数单位

当前 S4 排序包含：

- travel seconds；
- static potential seconds；
- raw target queue count；
- raw scheduled incoming count；
- corridor wait seconds；
- target calendar wait seconds。

隐含 queue coefficient 为 1 s/bag。南宁 service time 包含 1、1.5、2、3 s。简单 count×service 可能和 calendar wait 双计数，不能直接恢复。

## 5. queue cap 0

- `G31_LOCAL_QUEUE_CAPACITY=0`；
- C++ 注释定义 zero 为 no configured queue cap；
- queue-full、capacity blocker、capacity-triggered PIBT 分支要求 capacity>0；
- service calendar、destination merge、fault interlock 并未关闭；
- committed G31 aggregate 缺少足够的 RSS、ordinary queue peak、event heap peak、backlog slope 证据；
- 现有结果只能证明有限 1×/2× fixed horizon 下通过，不能证明开放流渐近有界。

## 6. direct-neighbour visibility

- candidate 来自 current node outgoing；
- 读取 `junctions_[candidate].service_calendar`；
- 计算一个 earliest-start scalar；
- scorer 不写完整路线；
- J2 是实际 grant/reservation authority；
- 代码级一跳边界通过；
- 仍需 future-task perturbation 和 distant-state invariance 专项测试。

## 7. EBS 语义

Profile 明确：

- EBS 未识别；
- type7 是 empty-pallet storage；
- proxy 需预注册；
- adapter 不自动把 proxy 当真实 EBS。

所以节点53结果只能解释为实验代理，不能解释为真实机场 EBS 部署。

## 8. 硬编码清单

### 核心地图无关

- dynamic graph；
- one-hop candidate enumeration；
- service/corridor calendar；
- destination local controller；
- offline potential；
- fault windows；
- configurable storage nodes。

### 实验壳

- dense IDs；
- role/type/alias semantics；
- proxy53；
- workload OD projection；
- fixed populations；
- exact 2× duplication；
- speed/fault matrix；
- fixed horizon；
- pair5_7 labels；
- Table5.3/5.4 semantics。

## 9. 推荐修改

唯一推荐立即执行：

`SOURCE_AWARE_DESTINATION_SERVICE_SHADOW`

要求：

- default off；
- shadow no action；
- local released source work only；
- no future release；
- no global scan；
- pure virtual insertion wait；
- no calendar reservation；
- exact-off parity；
- synthetic 53→49→50 motif；
- Nanning slice；
- map2 sentinel；
- GO 后才 closed loop；
- closed-loop GO 后才 full matrix。

## 10. 审计限制

- 未在当前环境重新运行全部 Java/C++ full matrix；
- 结果判定基于固定提交内 admitted artifacts、CSV/JSON/Markdown、准入代码和测试；
- 因此“结果存在且被报告器正确分类”经过独立复核；
- “在另一台机器重新执行必得完全相同结果”仍需正式 reproduction job。
