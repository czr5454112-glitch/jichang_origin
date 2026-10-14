# Analytical controller and finite reference independent review — 2026-10-13

本次由未实现解析匹配器/有限域参考的协作审查者逐行复核，并独立运行测试和真实原生分支。审查中发现两项主要完整性缺陷和一个修补后的空值旁路，均保留真实失败并修正。原生同刻终点修复由审查者在主线程授权后实施，因此该修复的测试是执行证据，不冒充外部第三方认证。

结论限于本页列出的源码、原生006和输入：没有发现无供给快速路径、FIFO等价候选压缩或当次PublicTravel共享会漏掉当前业务任务、覆盖固定FIFO权限。完整性修补后，29组独立真实分支/元数据反例全部通过，四个相关测试文件65项通过；不能由此推断全局物理最优、全业务负载收益或完整100ms达标。全部属于正确性、参考可信度和计算实现审查，不计方法创新。

## 冻结对象与独立执行

- `analytic_control.py` SHA256：`35d06c712c7cb24958dacab5b82099d7b7dcd23315a914f25908c12288f05a1a`。
- `finite_reference.py` SHA256：`3be0198c943d4c2eb520ef258e270146dfafe9709d360d13b67551e86616efe1`。
- `build_lt_session_006/python/czr005_circulation.cp311-win_amd64.pyd` SHA256：`0bdd31835d8e9b7269bb2d45e14484054aad73abf3a10dc989f3574230b16190`。
- 独立29组：`outputs/experiments/g31_ics_long_term_20261013/analytic_completion_independent_after_003/receipt.json`，`source_changed=[]`。
- 独立65项：同结果根目录下 `analytic_independent_review_001/final_006_junit.xml`，0失败/错误/跳过。包括解析匹配、边界参考、真实原生预算截断和原生同刻终点测试。最初审核指定的34项已经先行独立重跑；新增完整性断言使最终相关套件增长为65项，没有删除或放宽原断言。

审查脚本和完整原始证据均在 `analytic_independent_review_001/`。其中 `final_evidence_checks.json` 是对已有campaign原始结果的只读交叉核对，不是独立重跑campaign。测试、元数据破坏探针、campaign作者运行和本次只读检查须分别引用。

## 实际发现及修复证据

### 1. 原控制继续策略丢失预算截断，错误认证完整动作域

在真实005上，`max_events=5`、要求H=20的两个WAIT分支只运行到0.1。`run_online_matching`外层正确报`budget_exhausted`，但调用`result_at(current_clock)`生成的内部结果以0.1作为horizon且报`reached`；继续包装器返回内部result后，原参考把两条分支都认证为verified和`optimal_in_enumerated_domain`。物理审计通过只能说明已执行前缀一致，不能证明执行到共同H。

修复前完整回执：`analytic_independent_review_001/censored_continuation_receipt.json`。这是实际native反例，不是伪造结果对象。

修复：控制继续策略在raw result持久保存原始请求H、控制器物理时钟及继续状态。参考在计价/审计前同时核对请求H、结果H、物理时钟、advance时钟、分支时钟、存在时的控制器H/时钟；字段必须为有限数值并与共同H一致，状态必须明确完成。截断、缺失和矛盾证据都保留为`incomplete_horizon`，没有metrics或audit，不能获得最优认证。外层完整性信息被保留时也须检查。

### 2. 时钟达到H但同H事件未执行完，原生错误返回reached

真实005先推进到0，然后`advance_to(.1,1)`消耗一个事件、返回时钟0.1和`reached`；再次推进到同一0.1又执行8个事件，物理状态摘要改变。仅比较所有时钟等于H仍不足以阻止错误认证。

修复前回执：`analytic_independent_review_001/same_timestamp_budget_before_002.json`。较早的`same_timestamp_budget_before.json`是正对照：H=0恰用完一个预算且无剩余到期事件，正确完成；没有把它改写成失败。

原生006使用内部事件队列判定：时钟达到H，且没有时间≤H的待处理事件，才给`horizon_complete=true/status=reached`。内部下一事件时刻不暴露给owner观察。真实回归覆盖同刻剩余事件、checkpoint恢复后继续、全局事件预算在H中途耗尽，以及恰好用完预算但确已完成的正例。`p1_build_006/receipt.json`记录clean build成功、源码未变；`p1_checkpoint_validation_005/receipt.json`记录新冻结下专项实编通过，611个安全边界的完整双分支继续不变。没有把较早17/17兼容性结果冒充006全套复跑。

### 3. 修补中的外层status=None旁路

初版Python修补把“没有envelope”和“envelope明确status=None”都用None表示，后者仍进入最优认证。独立29组检查首次于此失败；`analytic_completion_independent_before_null_001/receipt.json`完整保留`exhaustive=true`、两次audit调用与`outer_status=null`。`analytic_completion_independent_after_002`也保留原始断言失败，未覆盖。

最终修复仅在无envelope时使用缺省None；存在envelope但status不是字符串时标`invalid_status_type`并拒绝完整性。独立after003全部29组通过，既包括H=.1/20下真实native预算截断与raw/envelope/剥外层信息包装，也包括缺失/非有限/矛盾H、advance=None、空/None控制元数据、非布尔完成标志和null外层状态。完整真实分支仍能通过审计并得到明确限定域的最优结果。

## 匹配优化、任务分母与固定FIFO

`transfer_candidates`先收集全部当前公开等待业务，按(arrival,business_bag_id)排序，扣除本地保留盘和在途/已接收但晚于需求快照的覆盖。没有供给时仍返回全部未覆盖业务需求，仅跳过无用的路径构造/匹配。无实际来源盘的终端清位压力另有诊断计数；它是合成调拨需求，不能被误说成丢弃业务任务。

等价候选键为(origin,clearing_source,demand_kind)。当前目标与可行性只依赖来源供给及该键，每组保留最早K个候选，K为可用供给数。任一解最多匹配K列，后序等价列可注入交换为未使用的前K列，保持匹配数与成本。完整需求身份仍保留在返回结果。测试对80个小方阵作独立全排列对照，对160个含不可达代价的等价组矩阵枚举全部行子集和列排列，对照压缩前后最大匹配数/最小成本；不是只比较两次同一求解器。

这一论证只覆盖当前ETA目标。若以后加入deadline、不同任务权重、时序耦合或不同容量义务，必须扩充等价键或停用压缩；不能套用现有证明。调拨命令的目标是端口，business ID只是控制请求标识，实际装载仍由native固定FIFO选择，没有从匹配结果取得跳队或改业务身份权限。

PublicTravel只在当前候选调用内构造并共享，用相同owner观察中的静态图、公开闭边和已通知故障。没有跨观察版本缓存，也没有读取未来带。条件服务窗口仍是点估计/软消息，不能替代容量授权或鲁棒分拣保证。`_visible_demand`依赖原生“每通道最新已送达快照”的合同；若改接任意历史快照列表，则还须显式按发布序号处理同刻乱序。

## 异步拒绝、原图边界和最优性范围

立即权限拒绝和已经真实终结的异步rejected/failed/expired等动作被记录为已解析但不进入成功候选；`timeout_unknown`、`failed_no_safe_continuation`以及到H仍pending的动作不当作不可行证明，都会阻止exhaustive认证。未经过正向独立审计的候选不获得最优认证。`max_seconds`只在分支间检查，不能把单次继续策略视为可抢占的硬实时过程。

只读复核了`validate_original_reference.py`及其原始6分支回执：数据集先按原图静态完整OD与返供可达性选同源24件，并明确采用一只现有盘的机制研究因子，不按仿真成功挑样本。边界是固定60秒控制tick上首个owner可见实际空盘返供意图。动作域为WAIT、当前解析返供、推迟1/15/30/60秒；整个当前epoch被替换，所有分支共同不重发该epoch需求，保留发布缓存并从next_tick=tick+1继续同一reactive策略。每条分支仍检查共同H=86400，逐bag比较正常服务保护。

因此，该原图headroom=0仅说明此24件/单盘因子、此首个返供边界、此六动作域、同真实未来和固定继续策略中的余量为零。它不能证明其他边界、提前返供、不同目标端口、多次干预、全流量或区域与慢层联合优化没有余量。它也不能被当作任意时刻连续执行部署控制器的等价替身，因为实验明确替换了一个完整epoch。

只读复核了`validate_original_regional.py`：首个公开loaded、未进入边、具有两条正容量阶段后缀的边界通过真实逐事件推进选取，不查看候选未来结果；Storage阶段目标未被绕过。所有组共享显式`allow_suffix_reroute=True`研究授权，不能称现场原始授权。主比较在相同原生延迟后启动同相位预测返供继续策略；有限域只有WAIT与该点公开next候选，后续路由和调拨分配没有穷举。全H保护与global unknown继续保留。

主线程另发现regional选择清单在添加共同授权因子后仍保留base输入hash；其原始001/002应解释为base selection hash，不是最终运行input hash。修补将base_selected_input_sha256与最终input_sha256明确分开，不能覆盖历史结果伪装本来一致。本页附属只读检查已核对regional003的3条原始分支均达到H86400、24件全部完成、全H审计通过、global未知，并独立重算最终input hash与清单一致。其两种真实轨迹成本相同，有限域headroom为0；本审查没有重新执行这些campaign。

原图首返供`p4_original_first_return_reference_006_001`的有限参考来源仍为null补丁前`7ed5bfde…`，实际6条均携带明确reached而非null，逐条完整性检查通过；该旁路没有影响这些已跑分支，但不可将其来源改写成最终`3be0198c…`。regional003和最终合成campaign已绑定最终参考源码。

## 已运行campaign与尚未证明的内容

最初审核的005 `analytic_native_008`三动作和`known_service_native_002`十动作真实结果均已逐条核对达到其H80/H40；这些具体成功场景没有触发截断缺陷。因此不能因反例而不加区分地撤销旧场景结果，但其旧参考程序完整性不适合用于新标签。

最终006 `analytic_native_010`与`known_service_native_004`已由主实验agent实际重新运行，本审查者读原始完整结果和SHA256，逐行检查新的horizon_complete、共同H、独立物理审计及global unknown。解析三动作最佳成本25.75；已知服务窗口域成本26.1，强基线已消除此前小域余量。该收益/无收益是合成机理证据，不能推广原图全流量或作为新方法贡献。

下一阶段仍需全负载物理瓶颈诊断、更多有辨识力的预声明边界/联合候选、强松弛与完整计算预算，以及候选覆盖、信息和真实native继续标签检查。无收益时不能删除区域自主或载盘驱动跨区预测需求；本审查不放行大规模学习或TRE/CIE级确认。

## 重跑入口

```powershell
$env:G31_CIRCULATION_BINARY='C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_session_006/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m pytest -q tests/test_g31_circulation_analytic_reference.py tests/test_g31_circulation_boundary_reference.py tests/test_g31_circulation_finite_reference_native.py tests/test_g31_circulation_horizon_completion.py
& C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_long_term_20261013/analytic_independent_review_001/independent_completion_checks.py --binary $env:G31_CIRCULATION_BINARY --output outputs/experiments/g31_ics_long_term_20261013/analytic_completion_independent_new_run
```

独立脚本要求新output目录，不覆盖before/after历史。任何后续源码变化均须重新绑定新运行证据，不能沿用上述冻结hash作整套通过声明。
