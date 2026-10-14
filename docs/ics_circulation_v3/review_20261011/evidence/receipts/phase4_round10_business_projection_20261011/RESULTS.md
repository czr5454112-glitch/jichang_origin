# Round10 全航班目的地研究投射

2026-10-11。新增纯输入模块 `business_projection.py`、38项专用测试，以及独立版本的1×/2×完整投射。没有修改原 `business_inputs.py`、`business_runtime.py`、原图、原任务或Round9六次原目的地窗口。没有运行物理，也没有把新目的地结果替换原试验的负结果。

## 结果与完整分母

`full_audit_002/resource.json` 为完整成功原件；对应manifest绑定全部逐袋、逐组、合同和源码快照。每条记录嵌入完整原 `BusinessTask`，另列原final、新final及父组ID。原origin、arrival秒/tick、STD、deadline秒/tick、protected、release、publication、旧段ID、raw/parent身份及来源SHA均逐对象相等。原操作合同和11个初始真实盘也逐对象保留。

| 项目 | 1× | 2×派生增密 |
|---|---:|---:|
| 完整业务袋 | 28,506 | 57,012 |
| 原始袋 / 派生袋 | 28,506 / 0 | 28,506 / 28,506 |
| 旧运输段来源 | 43,603 | 87,206 |
| early / direct | 15,097 / 13,409 | 30,194 / 26,818 |
| 完整父航班代理组 | 360 | 360 |
| 航班实例 | 360 | 720 |
| 每组必要目的域 | 36 | 36 |
| 改变目的地的父组 | 48 | 48 |
| 改变目的地的袋 | 4,001 | 8,002 |
| 保留原目的地的袋 | 24,505 | 49,010 |
| 有限初盘 | 11 | 11 |
| 原时序来源 / 独立观测日 | 1 / 0 | 1 / 0 |

两档的对应父组ID和新final完全相同。2×派生航班的 `flight_surrogate` 仍指向原父组；模块按完整父航班族统一选择，不拆航班、不按单袋选择，不把增密当新增观测日。

Root另行完成不导入作者模块的[独立产物审核](../phase4_round10_validation_20261011/projection_independent_001/results.json)：对全部85,518条记录执行2,312,980项机械核验，重算内容seal、整组membership及固定salt选择，并逐字段对照原normalized、Round9 clock和raw身份；必要域使用Round9独立Floyd核验结果。该审核通过，CPU13.8125秒、物理0次，计入validation目录而不混入本作者187.5625秒。

## 已声明的规则

`projection_declaration.json` 在全量计算前固定了规则、salt、节点排序和1s最终卸载代理。其source workload SHA占位符为null，不能直接执行；审计先通过原完整loader取得source fingerprint，写入各档完整 `projection_contract_1x.json` / `projection_contract_2x.json`，再计算投射。没有根据吞吐、成本、路由结果或目的地负载修改salt。

- 候选仅为原graph business role的42个合法unloader；151个节点不会全部成为final。
- 每候选对组内全部任务检查原origin及direct/early生命周期。early必须先到原storage，再等到原release后继续。final必须沿正容量原有向边回到至少一个原合法loader；不是要求回某个特定原origin。
- 原容量0边保持关闭。秒级最短路使用精确有理数；tick最短路独立使用逐边向上取整，不能用整路径秒数的ceil替代。原protected袋还要满足原秒级及保守floor后的tick截止下界，包含显式最终卸载服务。
- 合法原final保持。仅域外原final用 `SHA256([schema, salt, canonical_parent_key, candidate])` 最小值选择，按显式Unicode字典序处理节点平局。候选域、原值、新值、选择摘要均保留。
- 48个改变父组落到26个目标，仅是既定规则的结果。该规则不是负载均衡优化；没有容量公平或性能主张。

1×全部360组的raw ID集合、原final、结构必要域和截止必要域与Round9 `static_domains_001`逐组相符。2×同样满足36点域，原派生身份与所有时间平移都保留。

这些是静态必要条件。联合路段/接收/库位容量、实际空盘可用性、调度拥塞、owner与现场设备许可仍可能使任务不可执行或长时间等待。回到合法loader也不证明特定时刻原source有盘。新投射不是实际机场分配、可持续稳态或算法收益证据。

## 类型边界与未来接入

接口为：

```python
projected = project_business_destinations(original_workload, profile_path, explicit_contract)
validate_business_projection(projected, original_workload, profile_path)
```

返回独立frozen `BusinessProjection`，其中 `records` 保存 `ProjectedBusinessTask(original, group_id, original_destination, projected_destination)`。它刻意不是 `BusinessWorkload`。现有 `build_business_runtime(projected, ...)` 会在类型边界拒绝；专用测试已覆盖。没有自动启用新的运行时场景。

后续需要新显式适配合同，将这一投射版本与原runtime合同、完整物理分母、原始对照和固定窗口共同绑定，才能把新final作为新环境输入。原Round9实验继续保留。现阶段没有提供默默替换final再重封旧workload的便捷接口。

验证器会从给定原workload和原图重算完整分组、必要域和选择，比较全部原字段及投射内容。16项未重封/主动重封的输出变更反例覆盖origin、deadline、release、raw身份、newfinal、删袋、组域及分母/运行标记；全部拒绝。SHA256是可复现完整性绑定，不是抵抗调用者替换整套来源与合同的签名。

**上游信任边界必须区分：**纯投射API信任调用者提供的、已由loader审核的 `BusinessWorkload` 与固定投射合同。它只自行重读绑定图，不会重新读取raw/canonical/normalized来认证该上游对象。保持合同 `source_workload_sha256` 不变时，改workload并重封仍会被拒；如果调用者连workload和合同中的source SHA一起替换，就换了声明的输入信任根，不能把API通过称为“仍已证明来自原raw”。部分单元fixture直接构造并重封研究对象，只检查投射行为，不是原源认证测试。本次完整driver在每档投射前均重新运行原完整loader，另有root独立逐产物源对照；因此此处全量数据的来源证据来自这些实际步骤。独审提出此区别后，root明确冻结当前代码并要求记录接口限制；没有在已启动回归/窗口中改动模块。未来接收外部对象的运行适配器必须明确执行上游源审核。

## 验证、失败及资源

| 尝试 | 结果 | CPU秒 | Wall秒 | 物理 |
|---|---|---:|---:|---:|
| `author_tests_001` | 38 passed | 2.109375 | 2.152098099992145 | 0 |
| `full_audit_001` | 历史对照字段名错误，失败原件保留 | 42.453125 | 43.56197410001187 | 0 |
| `full_audit_002` | 完整1×/2×通过 | 143.0 | 145.83358790000784 | 0 |

已知独立进程区间CPU合计 **187.5625秒**。成功审计内1×47.390625秒、2×95.484375秒已经包含在143秒中，不再相加。这包含加载、完整生成/重验证和输出写入，不是在线算法延迟。读取、编辑、失败路径检索、探索性JSON键查找、导入和最终封包中未计量部分仍为未知辅助工作；wall不作为并发总历时。

失败原因、影响阶段与修复见 `FAILURES.md`，未覆盖任何失败原件。此次全量成功未发生任何输入或源码漂移。

冻结实现SHA：`f3767ab6b5a3bd226935da6541281f6c1ee2ae2460f2c20d775528eb9a5b18b5`；专用测试SHA：`9902fd7fb269441d57a781297121f716598ff4f57d3df51817fb64c27019dbe2`。完整依赖、图、规范化记录、原raw/canonical/manifest及审稿规格的SHA在每次resource/manifest中。
