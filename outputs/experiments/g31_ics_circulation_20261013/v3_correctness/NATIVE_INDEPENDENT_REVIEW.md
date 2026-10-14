# 首个 native circulation 切片的独立定向代码审查

日期：2026-10-13。审查者负责V3三项修复后，按root分工只读复核native新实现；没有改native文件。本文现在包含静态审查、本人通过真实native binding执行的反例和修后回执，并明确区分native作者另行完成的C++测试。

已完整阅读 `circulation.hpp`、`circulation_runtime_impl.hpp`、`bindings/circulation.cpp`、`native_host.py`、`validate_native_cycle.py`、`test_circulation_runtime.cpp`，并定向展开成熟 `event_driven_junction.hpp` 的publication/staging、shield、JIT merge、PIBT prevalidation/commit/rollback、entry/exit、完成/失败、checkpoint入口。

## 找到并反馈的问题

1. **空盘departure lease入口缺少即时复验。** 最初 `can_enter`没有核对expiry，而取消事件调度在expiry+1e-8；在1e-9合同容差与该定时事件之间存在提交窗口。已将问题同时发给root和native作者。后续只读复查见到 `can_enter` 增加仅针对dispatching、首次实际离开前的expiry守卫，C++回归加入expiry+5e-9拒绝与已departed后合法继续断言。该测试的实际编译运行回执由native负责者提供，不能以本段阅读代替。
2. **区内权限边界。** 初读transfer允许同zone source/destination，可能让名为跨区的接口隐式接管区内调拨。已通知作者，最终native已增加 `same_zone_transfer_not_authorized` 拒绝，独立Python事件审计也断言EXPORT_GRANTED必须跨zone。root回归 `test_cross_region_port_cannot_take_over_same_zone_module` 验证此边界；其执行统计以root最终验收回执为准。
3. **满节点原子handoff可行域保守。** 当前 `can_enter` 与PIBT预检以现有occupancy为依据，不扣同batch承诺离开的盘，满节点合法交换/链式handoff可能先被拒绝；已有远端接收lease的盘也可能被additional_receiving重复保守计算。这没有降低容量安全，却不能宣称完整继承旧PIBT可行域或获得通用无死锁保证。已提醒root记录边界；后续应给含满缓冲依赖传播的反例，不把增盘或删任务当解决方案。注意：在当前逐跳先取得空闲接收泊位合同下拒绝可以是有意的；若扩展原子离开/接收授权，必须让各算法共享该物理权限，不能把模型扩容伪装为方法收益。

## 本次已确认的结构

- 主clock与生命周期事件均由G31原生优先队列推进，Python宿主只构造输入/服务势及导出审计；未见第二个V3物理Simulation推进库存。
- 同一tray实体跨leg保存，business/leg/tray/traversal分开。Storage出段由真实storage完成事件触发；卸载后先hold，再变empty；完成一袋不会删除tray。
- `reserve_enter`在正常事件publication与PIBT不可逆、预分配的publication尾部才修改circulation资源；rollbackable staging阶段不提前改变该资源账，避免事务回滚漏恢复。
- JIT merge、候选shield和dispatch再次检查circulation容量，入口headway尾窗单独保留，未在卸载或离边清除。
- entry/exit核对active leg、edge、traversal ID及entry-observed状态。后续仍需对真实重复/迟到消息入口作执行测试，静态guard不等于所有故障已验证。
- fail/quarantine保留实体；未出发且未占edge的失败才释放未用远端接收lease，不把失败变可用库存。
- native circulation的capture、restore、deterministic digest均明确抛 `circulation:checkpoint_payload_not_implemented`；首包没有假checkpoint。但因此不能沿用依赖native causal clone的训练/标签结论。
- source本地waiting jobs先装载，再考虑空盘export；min-stock及allow_export/allow_receive仍作为固定port规则。它只保护当前声明的合同，不证明任意未知未来逐件零损失。

## 仍应保持的声明边界

首个单盘闭环及S3同物理可行见证是工程接通；尚无最优证明、真实预测预平衡、区域按需控制、完整原图业务验收或100ms完整单请求保证。native_event_ms的单事件测量不能替代100ms需求。原生legacy结果、circulation新物理结果和未来算法增量必须分别报告。

## 独立执行：同刻返盘与正常行李到达

初始静态疑点是EMPTY_RECEIVED后立即progress可能早于同刻BAG_ARRIVAL，从而让pending export抢走本地正常需求的托盘。用真实binding执行后，**默认完整goal service合同下此疑点没有复现，不能报告为已确认bug**。

`probe_same_timestamp.py`先实跑空盘返回并读取真实received_at=2.15，再让正常行李在相同时刻到达，同时保留此前已经delivered的第二条空盘export请求；另跑移除第二条export的对照。修前 `native_timestamp_before_002/` 与最终 `native_timestamp_after/` 均实际得到：

- 同刻事件顺序：BAG_ARRIVAL → LEG_COMPLETE → EMPTY_RECEIVED → LOAD_START。
- 有export和无export两例均在2.25完成装载，在6.1499999999999995完成行李，正常服务没有延迟。
- 同刻没有EXPORT_GRANTED，第二次export最终因 `carrier_not_at_export_port` 拒绝。

原因是当前默认goal完成由ARRIVE phase处理，预先排入的BAG_ARRIVAL先于同phase的后来完成事件；没有为这个被实际结果反证的猜测擅自改原生微相位。对应可重复回归是 `tests/test_g31_circulation_same_timestamp.py`。

native作者随后通过直接C++ API设置 `complete_on_goal_arrival=true` 得到了另一项真实反例：该配置跳过goal service，完成发生于较早微相位，从而抢占同刻正常需求。作者修前日志为 `build_g31_current/goal_contract_before.log`；修后circulation在初始化时明确拒绝 `circulation:goal_arrival_completion_unsupported`，legacy原有true合同未改。本文只读核对该guard；该C++运行证据属于native作者，不能与本人默认binding执行混写。

## 独立执行：非有限时间和非法图输入

修前binary SHA256 `84d99f496972e3b8892d8d4352083a30deff62cf9827a1279e8ba2622acad948` 的原始结果完整保存在 `native_input_before/`，包括每例输入/结果与 `receipt.json`。本人实际复现了：

| 输入 | 修前真实结果 | 修后实际拒绝理由 |
| --- | --- | --- |
| issued_at=1e308、message_delay=1e308，单项有限而相加溢出 | 接受，physical_clock和delivered_at为inf，两个事件时间为inf | `circulation:nonfinite_derived_time` |
| 边length=-1 | 接受并按最短1ms传播 | `circulation:invalid_edge_geometry` |
| 边speed=0 | 接受，候选model_score含inf | `circulation:invalid_edge_geometry` |
| node service=-1 | 接受并被下界处理 | `circulation:invalid_node_service` |
| 7节点的heuristic只有[[0]] | 运行中泛化的IndexError，invalid vector subscript | `circulation:invalid_heuristic_shape` |
| 尚未查询的heuristic[0][2]=NaN | 接受，未全面验证输入 | `circulation:invalid_heuristic_value` |

原始非法输入文件使用Python JSON的NaN/Infinity扩展值以保留真实输入/输出，不能当作标准JSON文件；receipt用字符串显式列出非有限数位置。最后一例的文件名沿用 `nan_matrix_used_entry`，实际上该cell在旧运行中未查询，此处纠正语义而不改历史文件名。

问题已交由native作者和root分别修复。native入口验证整个Graph的服务、边几何/行程、矩阵和所有派生时间；fault通知在旧initialize排事件前就验证fault/repair+delay。native publication另有非有限事件时间守卫。binding增加矩阵完整shape/value及重复/短图记录拒绝。legacy分支不施加这批新circulation合同。

修后本人重跑同一个未修改探针，六例全部按表中准确理由拒绝，证据为 `native_input_after_002/receipt.json`。所用最终binary SHA256为 `897f6e966df84129deda79d432d36d2df8bf0bf4f11aab8f743caca9a07fb47c`，与root `build_final_002/receipt.json` 一致；该clean build记录 `source_changed=[]`。`native_timestamp_after/`也记录同一binary。

另新增 `tests/test_g31_circulation_input_boundaries.py` 的26项回归，覆盖负数/NaN/Inf服务和边、有限length/speed除法溢出、消息/装载/卸载hold/故障通知加法溢出、矩阵所有cell的shape/value、重复/短记录，以及**合法零服务和零长边仍按native最小1ms执行并完成两件行李**。连同1项同时刻保护，27项在root `build_final_001` 后实际通过；原始JUnit/log为 `native_boundary_pytest_001.xml/.log`，exit0。该次没有在启动前额外保存binaryhash，因此不冒称27项已由本人用final002重跑；root统一最终回归另有回执。

### 执行中环境问题也保留

`native_timestamp_before.log` 是sandbox的Path.resolve权限错误，未运行到native；重新用授权工作区的正常加载权限后，`native_timestamp_before_002`成功。`native_input_after.log` 是root同时重编时Windows DLL占用，exit1，未运行到输入验证；待clean build完成后新建 `native_input_after_002`成功。两者不是模型拒绝，也不是自动审批拒绝，没有覆盖失败日志。

### 可运行命令

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:G31_CIRCULATION_BINARY='C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m pytest -q tests/test_g31_circulation_input_boundaries.py tests/test_g31_circulation_same_timestamp.py
& C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_circulation_20261013/v3_correctness/probe_input_boundaries.py --binary build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_circulation_20261013/v3_correctness/native_input_recheck_003
& C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_circulation_20261013/v3_correctness/probe_same_timestamp.py --binary build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_circulation_20261013/v3_correctness/native_timestamp_recheck_003
```

所有probe输出目录要求不存在，以保留历史证据。probe_input_boundaries用于捕获行为，进程成功本身不表示六例通过，须检查receipt；精确验收由pytest断言完成。本批修复和测试是正确性/物理权限工程，不计作论文方法创新。
