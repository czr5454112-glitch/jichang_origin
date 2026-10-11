# 第六轮同区直接供盘：独立审查记录

2026-10-10。本目录由独立审查者维护；不修改旧核心、C++ 或实现/实验负责人的文件，不提交、不推送。实验解释仍限于既有合成来源的开发验证。

## 开始前审查

只读了上一轮 `phase4_w3_same_zone_supply_analysis_20261010/SAME_ZONE_SUPPLY.md`、`prebalance.py`、`runtime.py`、`distributed_local.py` 及相应测试。

1. **中央同区权限与 W2 本地权限不同。** node46 与 node26 同物流区、不同 control_partition。新基线可以维持 W3 已有中央 Snapshot 信息域，不能直接宣称复用了 W2 same-owner 服务许可。
2. **目标 credit 不能抵销其他需求损失。** 供盘目标只在完整路径的真实 usable_at 获得一份 credit；必须另查移除 donor 后其他需求每个前缀的匹配数，不能只比较含目标的总匹配数。W2 guard 的拓扑可达性不足以说明远端库存及时可用；新保护须明确时序模型、未来释放、hold 与有向可达条件。若使用静态时间下界，必须明确它只是保守程度有限的模型，不是所有匹配可同时执行的证明。
3. **身份与预测。** 原 `_demand` 输出会将预测单位折叠为 count；新命名目标必须从 accepted forecast identity 或真实 visible bag 稳定绑定。future publication、最新 cancellation、TTL、已观察/已装载/已完成 identity 去重不可被绕过。匿名 count 不应伪称真实袋 identity。
4. **不可撤销承诺。** plans、old_in_transit、empty_targets donor 都不能重新分配。无 ETA 的 empty obligation 可以阻止重复调拨，但不能获得伪造的即时供应。顺序多个提案必须以每次 commit 后的 scratch 重新校验。
5. **候选与预算公平。** 同区候选须在旧 cross-zone 选择之前进入同一次排序。保留旧 cross-zone guard、需求排序、迟滞/距离/tray_id 排序；明确候选域扩大，保留所有查询状态与实际 work。预算未搜索到不等于物理不可行。latest-departure shift 后需对最终 usable_at 再核服务保护。
6. **执行验证。** guard 不能替代 ExecutionValidator；有向路径、真实 hold、预约、容量、状态版本、终点、空盘身份仍原样校验。不存在“同区可以忽略硬约束”的许可。
7. **实验相位。** d40/t126 是 loaded routing callback，next slow 是127。四格干预必须保留当前 cursor/cache/clock；新控制器只在后续真实 slow 触发时接收当时公开的预测。未来 tape 仅作物理环境输入。
8. **解释边界。** 四格是同一状态干预，不能充当独立部署确认。三条完整流从原初态运行，实际新轨迹的机会数重采；不可沿用旧174作新策略分母，也不把相关局部 regret 相加为部署收益。

以上风险已通知方法和实验负责人。独立测试文件将是 `tests/test_ics_circulation_v3_same_zone_supply_audit.py`；当前等待新 API 后执行具体验证。最终完整回归将在全部新源冻结后运行，保留前后 hash、失败证据、完整资源和未知项。

## 设计反馈与处理

- 初始拟议 guard 只匹配 known_supply 的实际节点和释放时间。独立审查指出：唯一 donor 能及时到第三节点、而第三节点当前库存为零时，移走 donor 前后节点库存都是零，不能据此声称潜在服务能力不下降。
- root 与方法负责人采纳更强检查：在完整公开正容量有向图上计算静态最短旅行时间；使用供给真实释放时刻、目标 hold、需求 release 和所有可达时刻构造事件前缀，分别比较 other-demand 匹配能力和包含真实 target credit 的总匹配能力。仍保留 exact-node 确定供给不降的附加条件。同节点 known_supply 已含 hold，不重复添加。
- 需求 at 是 release 而非 deadline。只查需求 release 会漏掉已经等待的远端需求；因此事件时点须包含将来首次可达时刻，并明确 finite horizon。该检查是静态时序可达上界保护，不是含共享容量与预约的联合可执行证明。
- 独立审查要求保护需求账不得跟随可尝试目标数截断；工作预算耗尽单独记作未完成检查，而非已证明不可行。所有被拒候选的距离/匹配计算仍计资源。
- 新同区候选将增加未承诺可见 protected 任务保护；旧 cross-zone 行为保持原样。执行器与 FixedLocalModule 参数必须 byte/config 保持，不能将中央代理实验解释为供应商已授权的新模块功能。
- 实验协议扩展为 old32、old64、new32-cross+32-same：6 格机制干预、9 个全流名义 pilot，后续 81 个预声明全流条件（3 scene × nominal及8固定扰动 ×3策略）。名义重复运行单独计物理 CPU；实验未来仅进入 event engine，公开 forecasts 保持相同。

`initial_binding.json` 已核对上一轮 158 个源码/测试文件无漂移，用户原 C++ SHA 一致。独立负例测试已写入上述新文件，目前等待实现后首次运行；尚未运行旧全套。

## 首次实现审查和测试

新模块将时间可达检查、确定节点供给检查、身份账与预算账分开；逐时点目标 credit 只在 `max(need_at, usable_at)` 生效。已核对 root 的 `phase4_w3_round6_design_20261010/GUARD_CONTRACT.md`，实现与其有限事件语义一致。目标有限遍历不截保护账，保护账/计算不完整会关闭 same-zone 增量。

- `guard_initial_validation.json`：最初9项 guard 负例通过；子进程 CPU 未采集，记未知而非零，父进程 CPU 0.015625秒。
- `controller_initial_validation.json`：扩展20项通过，CPU 0.859375秒。包括前缀/身份/不可撤销义务/工作量耗尽/顺序版本。
- `independent_focused_validation.json`：26个方法测试和2个后处理故障测试通过，1个强制动作故障测试失败。原因是独立测试 fixture 漏配本实验要求的 replay cache，尚未进入被测故障位置；并非生产实现失效。保留原失败日志，CPU 2.953125秒。
- `independent_focused_repaired_validation.json`：仅补 fixture 的 `enable_replay_cache` 后29项全部通过，CPU 1.359375秒。包含512个3×3二分图与穷举分配 oracle 的匹配数逐个比对；全部吻合。两独立测试文件当前冻结。

runner 首轮审查发现两个真实证据保留缺口，均已通知作者修复并用独立故障注入验证：

1. 物理调用已完成后，旧结果读取/比较或新 raw 序列化失败时，原异常处理可能只留状态而丢失完整 outcome。现先写独立 recovery JSON，保存 outcome、输入绑定、ledger、contract 和比较状态；已写一半的 gzip 保留不覆盖。
2. `choose_pending` 原先位于主 try 外，强制动作异常会越过运行器的 execution_failure 回执。现纳入同一 try，保留初态、cursor、任务分母和查询账。

当前 review 对新方法/runner 无阻断；已向 root 和两个 owner 回报可冻结后运行预声明机制和名义 pilot。尚未根据结果选择新场景或修改策略，尚未运行最终旧全套。

## 完整回归、比较器纠错与原件审计

full_validation/result.json：777/777 通过，0 failure/error/skip。101 个 Python 源文件、64 个测试文件和用户原 C++ 共166文件，运行前后全部 SHA 不变。总 CPU 70.109375 秒，wall 72.7449872 秒；其中测试 CPU 69.734375 是内层数据，不叠加。保留完整 before/after、源测试快照、JUnit、日志与 manifest。

初始机制6格产生2条 old32_replication_mismatch，因此团队暂停扩大实验。独立复核确认：两条的全周期物理结果、h80物理结果、全部查询账和停止时刻相等；唯一 false 是 cache_before。两份落盘 JSON 的完整 cache_before 所有字段实际相等；runner 比较历史 JSON list 与当前内存 tuple 导致误报。作者仅在比较器做完整 JSON 值规范化，未排除任何缓存字段；新增测试明确改变缓存实体内容或 digest 必须拒绝。原6格和计算资源保持封存，新 repaired 目录重新运行6/9/81。

修后作者专项首次因系统 Temp ACL 出现9 pass +2 fixture setup error；随后显式使用 workspace basetemp，11项通过。两次子进程 CPU 未采集，单列未知，不能记零。post777_repair_binding.json 证明777快照后仅新runner和其作者测试两文件改变，其他164文件未变，新repaired协议逐SHA一致。最终测试表述是 **777项全套 + 修后11项专项（其中2项新增）**，并非一次779项全套。

独立原件审计只读 JSON，不调用控制器或再跑物理：

| 报告 | 检查 | 错误 | 实际 slow 调用 | guard / 时点前缀复算 | CPU秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| mechanism_initial_audit.json | 2165 | 0 | 278 | 68 / 275 | 9.234375 |
| mechanism_repaired_audit.json | 2341 | 0 | 278 | 68 / 275 | 9.421875 |
| nominal_pilot_audit.json | 7365 | 0 | 1260 | 11 / 39 | 19.15625 |

初始审计0错误表示保存的物理和保护计算经过核查，并不改写原summary中的两个比较器误报。修后审计另独立从原始publication和真实可见袋/承载状态重建完整identity需求账；使用 Floyd-Warshall 距离与另一种递归匹配实现重算全部已记录guard，在顺序提案后的真实已承诺供给状态核对各时点，不复用被审方法的guard函数。所有quiet终态还核对全离线任务账、严格合法停车占位、真实加载等待、空载发车里程、迟到分量及总目标。旧32分支/原horizon的完整物理、查询、缓存复现单独核查。

正式81实例仍在运行。最终版纯文件审计脚本 audit_artifacts_v4.py 已准备，增加27条固定环境tape的独立种子再构造、主动合同和新轨迹全机会与实际selector绑定；待正式summary/manifest落盘再运行，不以当前名义收益挑选后续验证。

## 名义轨迹观察交集复核

root 请求确认“相同机会数量不等于相同状态”。nominal_observation_overlap.json 独立读9个名义原件，用完整规范 JSON 字符串的多重集直接比较（不复用 root 的摘要函数），0错误、CPU16.078125秒。counterflow 新旧都是72次机会，但完整观察只重合19次，双方各53次不同；仅 time/node/bag/tray 粗键仍有31次重合，不能代替完整状态。cross_cycle 51次、near_full 57次全部重合，因此新旧完整观察共127/180重合。near_full 的6次零候选保留，位置角色合计27 origin、153 continuation；old64 与 old32 的180次完整观察全相同。

完整观察键含 time/node/bag/tray、cursor、next slow、提供的候选池和全部 visible_state，公共图由同一冻结协议绑定。它没有私有 cache 与续接策略身份；即使公共观察相同，也不能据此批准跨控制方法复用价值标签。

已只读核查第六轮资源汇总器，确认 case/cycle 和总回归/test 内层不重复加，未知子进程 CPU 不填零，上一轮同名设计诊断不重复计。额外提醒将独立 observation census 显式纳入（名称不匹配默认 audit/comparison glob），并在封存前避免同一次分析在 analysis/manifest 两文件复制 directCPU 导致双算。

## 正式81原件终审

formal_artifact_audit.json：77,560项检查，0错误；审查11,340次真实slow调用，独立重算全部166个已记录guard和427个事件前缀，27条预声明环境tape按原种子再构造完全相等，442个绑定文件前后未变。正式81条任务、加载等待、空盘发车、迟到分量、完整任务身份、实际候选池与selector、公开forecast时钟、终端合法停车占位、源码/测试/原C++均通过。CPU129.15625秒、wall132.3989141秒；没有调用被审guard或新增仿真。

最终汇总比较仅复用以上已经独立核验的行表与root分析，不再读全体raw。首次在root目录已建但analysis.json尚未写完时过早启动，因FileNotFoundError退出，未生成比较结论；final_comparison_wait_failure.json保留该失败及toolwall1.1036973秒，CPU未知，0物理。等待作者完整落盘后用原脚本重跑。

作者完成通知后，原compare_final_analysis.py再次执行成功；final_analysis_comparison.json的757检查全部通过，81实际cost/task/机会、54完整配对、12汇总均与root一致。27个条件中新方法11降16平0升，old64全部持平；每策略194个任务，合计582全部准时完成（其中81受保护），实际loaded尝试4326次含150零候选。新方法开发队列成本1685.9→833.0，其中counterflow九条件减少830.9、cross_cycle两条件减少22.0、near_full九条件全平。配对成本合计只描述固定相关开发队列，不声称独立泛化或把逐状态oracle regret相加成部署收益。

成功比较CPU时钟增量0.0秒、wall0.0149859秒；该0.0是process_time分辨率，并非零计算工作。已通知资源负责人独立收录此前失败未知CPU和最终比较区间。此后仅补README、日志、证据manifest，不再增加物理或数值审计。
