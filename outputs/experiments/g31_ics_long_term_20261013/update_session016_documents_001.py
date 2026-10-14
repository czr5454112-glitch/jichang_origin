"""Record the actual native012-016 milestone and exact remaining gates."""
from pathlib import Path
import json

ROOT = Path(__file__).absolute().parents[3]
D = ROOT / "docs/g31_ics_circulation"
E = ROOT / "outputs/experiments/g31_ics_long_term_20261013"
BINARY = "build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd"
SHA = "af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0"
v = json.loads((E/"live_validation_012/receipt.json").read_text(encoding="utf-8"))
assert v["status"] == "passed" and v["counts"] == dict(tests=407, failures=0, errors=0, skipped=0)
assert v["current_native_and_python_test_count"] == 401
s = json.loads((D/"RESEARCH_STATE.json").read_text(encoding="utf-8"))
s.update(
    current_stage="P1/P3 strict native time and legal owner-event activation supported in declared scope; P2 selected original circulation; P4/P5 strong reference and corrected negative evidence; P6 held; P7 not met",
    active_experiment=None,
    execution_status="Frozen local native016 milestone; continuous LT-1 development remains open at the exact P3/P5/P7 entry points below. No stage/commit/push.",
    current_binary=dict(path=BINARY, sha256=SHA, build_receipt="outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json"),
    final_regression=dict(artifact="outputs/experiments/g31_ics_long_term_20261013/live_validation_012/receipt.json", counts=v["counts"],
        source_changed=[], current_native_and_python_tests=401, frozen011_historical_counterexamples=1,
        pinned011_015_identity_checks=5, scope="407 aggregate related regressions; neither 407 current physical tests nor all repository historical tests."),
    last_verified_checkpoint="C++ checkpoint009: three compiled targets and six compile/run commands passed; exact compiled sources remain unchanged in016. Event controller native-budget/owner-budget JSON plus in-process native checkpoint continuation tested. No cross-process physical persistence.",
    source_freeze_note="session016_handoff_integrity_001 binds current source to build016/live012/checkpoint009/legacy005. Original five-policy016 comparison is also source-current. P5 results remain frozen011/015 experiments; later native_host identity guard changed one Python source, so do not transplant their old source freeze to current code.",
    committed=False, pushed=False, requires_user_decision=False)
s["blocked_claims"] = [
    "Full original 1x28506 and 2x57012 conservative zero-as-closed/FIFO/on-carrier results remain version-bound negative evidence; not rerun as016 full-flow campaigns.",
    "Raw zero capacities are verified, but zero-as-closed lacks field-confirmed physical semantics; no topology, tray expansion, task removal or FIFO bypass authorized.",
    "Original static selected24 on016 completes24 with23 actual same-tray returns and19 late; not full mother-stream success.",
    "Original R1 permission remains0/24 and route actions0; event joint equals event predictive, so no joint mechanism gain demonstrated.",
    "Original event predictive204 delivered service forecasts arrive0.5s AFTER actual edge entry; they do not establish advance foreknowledge or explain the28.408s benefit.",
    "All320 event service forecast rejections remain; stale same-stage estimates lack automatic long-block refresh. SourceQueue/PendingRelease lack a lawful loaded forecast contract.",
    "Single-tray selected24 optimistic bound395187.971581 and at least19 late are fixed-contract necessary bounds, not global/multi-tray/full-flow optimality.",
    "015 P5 handoff126 real branches have identical business metrics to011; strong service-completion assignment explains all eight finite-domain optima. Global optimum unknown.",
    "Old006/011 two-boundary D0+399 negative example was caused by invalid event order and is retracted for strict015/016. Historical witness retained separately. Unverified request-bundle references remainunknown.",
    "Synthetic known-service event reactive improves total cost but worsensB2 by0.3; total improvement is not all-offered normal-service protection.",
    "Native checkpoints remain process-bound. Event controller supports tested partial owner/native budgets; periodic v2 still does not support intra-tick recovery. Lease/rejected cooldown timers wait for legal activation/heartbeat.",
    "016 selected24 predictive owner computation exceeds100ms15/7890 (max128.0842ms); joint24/7890 (max199.5798ms). These are partial-chain samples, not complete request/deployment certification.",
    "Older full-day0102x owner+publication exceeded100ms2/194 (max101.0037ms). New selected24 data cannot replace that full-flow timing result.",
    "015/016 profiling and serial runs preserve semantics but are not controlled deployment benchmarks; one015 run had concurrent compilation. No two-machine/cold/hot/burst certification.",
    "P5 novelty, P6 same-G31 learning release, P7 complete100ms and TRE/CIE evidence targets remain open.",
    "Disk below20percent guard: bounded gzip evidence only; no bulk labels/training or deletion of history."
]
s["stage_gates"].update(
    P1="Partial: strict circulation event time, sealed owner notifications, unified message/ACK protocol, native+JSON continuation at tested budget cuts; legacy two fixtures exactly preserved. Cross-process native persistence and deployment remain open.",
    P2="Partial: original151nodes227edges selected24 on016 has24completed/23returns/19late with original task and permission contract. Complete mother flow remains blocked under unconfirmed conservative physical interpretation.",
    P3="Partial: lawful owner local/received-message activation implemented; private remote changes do not activate unrelated owners. Real source checks/rejections retained. Original R1 has no authorization, long-blocked forecast refresh and complete legal timer scheduling remain next.",
    P4="Finite same-G31 witnesses and necessary bounds;126 handoff branches on015 rechecked against011. Strong matching already reaches all eight finite-domain minima. No global optimality certification.",
    P5="research_candidate: earlier physical-order-induced two-boundary counterexample corrected; new handoff strong service assignment explains gains. Multi-candidate shared-resource coupling under legal distributed information still needs an independently novel solver.",
    P6="Held at candidate coverage, legal information, same-G31 continuation labels and main-mechanism evidence gates. No bulk training on old labels.",
    P7="NOT MET:016 selected24 has15 predictive and24 joint owner samples above100ms; full request revalidation/ACK, original full stream, cold/hot/burst/two-machine gates remain open.")
s["next_actions"] = [
    "Continue existing native016 source; read the012-016 progress section and novelty25-28. Do not reimport or repeat the old V3 fixes/one-tray milestones.",
    "P3: extend event_protocol_control pending_causes/published forecasts with lawful same-stage expiry/refresh and explicit lease/retry/cooldown timers. Share capabilities with periodic and event strong baselines; retain command delay/source-state rejection.",
    "P3: characterize cases where a legal forecast actually arrives before relevant entry/release. Original204 messages describe already-started service; do not infer causality from delivery counts.",
    "P5: test multiple real candidate paths with coupled shared resource occupancy and cross-owner contracts delivered by explicit messages. Compare independent service-cost assignment, strong rolling feedback, closure/retiming and same-G31 finite reference; require all-offered protection.",
    "P7: reuse same-owner observation within one unchanged activation and index pending outbox/active forecasts without removing ACK/history. Prove semantic equivalence, resumability and mutation isolation before any claimed speedup.",
    "P7: measure full original active request computation including delivery revalidation/confirmation on a frozen build; then controlled cold/hot/burst/two-machine checks when execution environments exist. Keep all current over100ms samples.",
    "P2: independently investigate zero-capacity handoff physical semantics from actual requirement evidence; do not silently turn0to1, add edges/trays, change fixed FIFO or drop unserved jobs.",
    "P6: release only justified small same-continuation diagnostics after information/candidate/strong-reference and distinct-method gates; P1-P7 and TRE/CIE quality unchanged.",
    "Use fresh output/build paths for new source; preserve failures, validate binary __file__/SHA in separate processes for version comparisons; no stage/commit/push/fees/equipment."
]
cmd = "python -m scripts.experiments.g31_ics_circulation."
out = "outputs/experiments/g31_ics_long_term_20261013/"
s["resume_commands"].update(
    rule="Runnable current commands use fresh output directories. Historical P5 frozen-source rechecks require their archived source identities; do not edit the current tree to satisfy them. Do not repeat unchanged passed runs without a new change or unresolved concern.",
    full_day_hotspot=cmd+"run_original_control --binary "+BINARY+" --scale 2 --horizon 86400 --control-period 900 --max-events 160000 --wall-budget 240 --compact-projection --output "+out+"original_2x_016_recheck_new",
    transfer_protocol=cmd+"validate_owner_protocol --binary "+BINARY+" --output "+out+"owner_protocol_016_recheck_new",
    unified_protocol=cmd+"validate_protocol_control --binary "+BINARY+" --output "+out+"protocol_016_recheck_new",
    original_protocol=cmd+"validate_event_protocol_control --binary "+BINARY+" --expected-binary-sha256 "+SHA+" --suite original24 --output "+out+"event_original_016_recheck_new",
    event_synthetic=cmd+"validate_event_protocol_control --binary "+BINARY+" --expected-binary-sha256 "+SHA+" --suite synthetic --output "+out+"event_synthetic_016_recheck_new",
    regression=cmd+"validate_live --binary "+BINARY+" --build-receipt "+out+"p1_build_016/receipt.json --output "+out+"live_016_recheck_new")
s["resume_commands"].pop("p5_continuous_factor",None)
s["delivery_scope"]="Current local source diff and archived bytes; not a complete repository, native binaries or full raw evidence archive. No Git publication."
(D/"RESEARCH_STATE.json").write_text(json.dumps(s,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

progress = """
## 012—016实质研发、独立纠错与当前续跑位置

本节是当前起点，前文006—011是版本绑定历史记录。仍在同一circulation独立工作区、成熟HEAD46cc46；父工作区HEADfccd481及受保护的用户文件哈希保持，未暂存、提交或推送。长期总纲、两项需求、成熟G31唯一物理宿主、固定区内权限与TRE/CIE证据要求不变。

### 实际代码与正确性里程碑

新增原生owner通知及按通知推进API，只有本地真实状态变化、实际送达需求/预测/撤销/ACK、公开超时和真实已通知故障会激活相应owner。不读取远区隐藏事件或尚未到达业务；新增能力公平提供给同组全部策略。时间戳必须完整drain后才返回通知；预算中断保留真实游标。通知序号、排序模式及状态纳入checkpoint/seal。新增事件控制器只激活合法owner，按owner持久化轮次、公开消息游标与待处理原因；真实native预算、owner预算、双预算中断后，JSON与进程内native checkpoint继续均与不间断执行一致。它不等于物理状态可跨进程持久恢复；旧periodic v2仍不支持中断tick恢复。

012/013实际失败暴露严格物理时间错误：epsilon比较把6.05与6.049999999999999当同刻按微阶段重新排序，导致晚事件先执行、时钟倒退和虚假H完成。只改通知标记不能修好；014改circulation的严格时间排序与精确同刻判定，重建初始故障堆并seal排序模式，拒绝使时钟回退的过去事件。legacy保持成熟原行为。015再修零延迟真实故障送达遗漏通知；正的1e-10延迟仍必须真正等待，drop不通知。各初始失败、通知时间探针、相邻浮点反例和fixture错误均保留，不合并成虚构的一次成功。

loaded服务预测不再从实际source执行时刻重复加完整节点服务：只用合法本地已承诺service calendar及当前stage。保存的五输入在011/015独立进程重放，真实入边不变，两个成功预测4→2与5→3分别对上实际2与3；loading案例3.001不变，真正不合法source阶段仍拒绝。详情与原始回执见原图forecast diagnosis目录。

独立审计还发现扩展模块缓存可令同进程请求011却悄悄返回已加载015。native_host现在核对实际module文件、SHA及首次身份，版本冲突明确要求独立进程；同artifact重复加载保留。before真实静默复用、after双向拒绝和独立011/015历史行为全部落盘。这是实验身份正确性修复，不是方法创新。

### 同模型原图五策略与合成故障/保护结果

event_protocol_synthetic_015_001完成7场×5策略的35次真实运行，保留丢ACK、重复、源/接收不可用、接收拒绝及known-service保护反例。拒绝组仍只服务1/2；known-service的event reactive虽总成本更低，却使B2晚0.3秒，不能按总成本宣布正常保护通过。

event_protocol_original24_015_001及016_001使用同一原151节点227边、事前静态24件选择、唯一真实托盘与相同通信/通知权限。五策略均真正到H86400、完成24件、迟到19件、真实同盘返回23次。独立015审计核验五组115条卸载→hold→授权→真实有向空返→再装载/卸载链；016全部物理事件和控制语义与015逐项相同。全部28506母流、静态选择及排除口径保留，不冒称完整原流成功。

| 策略 | arrival到unload成本和（秒） | 完成/迟到/实际返供 |
|---|---:|---|
| 周期反应 | 418514.272581 | 24 / 19 / 23 |
| 周期预测 | 414198.867581 | 24 / 19 / 23 |
| 事件反应 | 414592.459581 | 24 / 19 / 23 |
| 事件预测 | 414170.459581 | 24 / 19 / 23 |
| 事件联合 | 414170.459581 | 24 / 19 / 23 |

事件预测相对周期预测仅第一件受影响业务快28.408秒，其余23件相同。变化对应首次调拨从actual_available变为conditional_release请求；不能直接归因于预测消息。事件预测204条service forecast成功送达、320条拒绝；周期预测16条全拒绝。204条全在实际入边后0.5秒送达，虽然entry估计准确且窗口未结束，也不是提前告知入边。原R1许可0/24、真实route=0，事件joint与predictive规范化物理事件相同，无联合方法增量。

### 强参考提前、旧反例纠正与创新判定

P5新增四个预声明真实handoff因子及初始/滚动两阶段，共126个原生分支，含实际pending→cancelled→重新指派；完整有限域保留WAIT及未全服务分支。有Storage余量时普通空盘ETA成本22.07，固定指派重定时24.350001，独立最小费用流服务完成指派与联合选择均19.96；去掉余量或禁止第三源导出会出现正常业务恶化。八个有限域的强普通服务基线已解释所有收益，global optimum仍unknown。完整合同在合法resource_owner A内可见，远区C仅通过实际公告；没有注入私有Storage字段。011→015复跑所有126分支、40项策略选择及物理哈希一致。

另对旧两边界反例按原16域在011和015真实重跑。原D0约400秒退化源于401.75000000000006的T1在401.75的TP之前取得资源，不是新模型仍存在的算法退化。严格015后两次与一次修复逐件相同，旧因果结论对当前模型撤回；旧断言原样放入明确011独立进程历史回归，当前另加严格时间、真实资源授权与修复执行断言。006/011三类日志合计58处回退记录变为015的0，不是58个独立缺陷。未兑现的完整请求bundle仍unknown，不能自动改成headroom=0；旧必要cut界只保持自身限定前提。

上述P5回执绑定当时冻结011/015源码；随后native_host增加身份拒绝，使当前一份Python文件与历史归档不同。旧实验不是在当前016全套源码上重做。冻结P5 recheck有源码一致性守卫，复现应在独立归档上下文完成，不能修改当前树或绕过守卫冒称相同源码。

### 016序列化优化与真实性能失败

只读剖析以原请求带真实重建H24000/36000/45000，证明历史命令批量观察存在重复线性检索。016仅将已经选中的command引用直接序列化，保留全部历史、字段、顺序和ACK语义；不是删记录或改候选。三份完整观察与1489条单命令回复哈希完全相同，原生seal不变；专项覆盖pending、timeout、loss、duplicate、outage、retry、restore和可变dict隔离。

随后五策略实际完整复跑，015/016的输入字节、业务、物理事件、全部请求/回复、动作、控制器JSON、预算继续状态及最终native seal一致。只在比较中排除明确列出的计算计时字段。独立运行的事件预测wall总计68.460→49.168秒，联合68.511→50.527秒；015期间有并发编译，因此这些是描述性运行值，不能把全部差异认证为受控加速比。

016预测owner样本仍15/7890超过100ms，max128.0842ms；联合24/7890，max199.5798ms，反而比015的23次/max173.1897ms更差。既不隐藏尾部恶化，也不把仅owner子链等同完整任务更新。交付复验/确认、全原流、冷/热/突发与两机门均未过，P7仍NOT MET。旧全流010的2/194超限与保守代理0/57012业务完成保留，新24件组不能覆盖它们。

### 最终验证、可运行命令与剩余接入点

016 clean构建SHA256为af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0。p1_checkpoint_validation_009三项C++目标、六次编译/执行成功；legacy_parity_005两场、各五项确定性哈希与成熟G31一致。016只改binding，上述两回执的全部编译源哈希仍与当前相同。

live_validation_010保留真实390/391结果，唯一失败是旧物理顺序反例不再成立。011为407/407，后发现其中一条范围说明误写“其他都为当前native”，012只修回执范围并显式分组后重新实际运行：**407通过，0失败/错误/跳过，source_changed=[]；401项当前native及Python关联检查＋1项011历史反例＋5项固定011/015身份专项。** 不是407个当前物理实验，也不是整仓历史1519项重新执行。专项测试与407有重叠，不能相加扩大工作量。具体JUnit及源码绑定随回执保存。

在当前工作区，以下命令使用新output，可直接运行：

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$g31Binary='build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_live --binary $g31Binary --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/live_016_recheck_new
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_event_protocol_control --binary $g31Binary --expected-binary-sha256 af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0 --suite original24 --output outputs/experiments/g31_ics_long_term_20261013/event_original_016_recheck_new
```

没有新改动或未解决疑点时，不必重复以上已通过运行。准确接入点是：P3在event_protocol_control的pending_causes/forecast状态补长期同stage合法刷新与lease/retry/cooldown定时，测真正提前到达的预测；P5设计多个真实候选的共同资源占用耦合，并通过明确消息获得跨owner合同，与服务费用匹配、滚动反馈和通用闭合/重定时先对照；P7在不删除历史前提下复用同激活观察、索引pending outbox/active forecasts，随后补完整请求计算测量；P2继续核验0容量物理合同而不擅自松绑；P6须等待候选、信息、同G31标签及独立机制门，暂不做大规模旧标签训练。进度、结果索引与创新账保持同步，未降低两项需求或100ms/TRE/CIE标准。
"""
p = D/"LONG_TERM_PROGRESS_20261013.md"
text = p.read_text(encoding="utf-8")
assert "## 012—016实质研发、独立纠错与当前续跑位置" not in text
banner = "当前以文末“012—016实质研发、独立纠错与当前续跑位置”及RESEARCH_STATE为准；较早版本的“当前/下一步”与负结论保留作历史，不自动适用于016。\n\n"
text = text.replace("\n\n", "\n\n"+banner, 1)
p.write_text(text.rstrip()+"\n"+progress+"\n",encoding="utf-8")
p = D/"NOVELTY_LEDGER.md"
text = p.read_text(encoding="utf-8")
assert "## 28. LT-1 身份与序列化优化" not in text
text += """
## 28. LT-1 身份与序列化优化：工程成立不放行创新及100ms

同进程加载不同版本的同名native扩展可能静默复用旧模块，已用真实011/015预测4与2的不同物理行为确认。新增实际模块文件/SHA/首次身份守卫，版本对比改为独立进程；五项专项与before/after回执保留。该修复使研究版本证据可信，不构成新方法。407关联回归明确分401当前native/Python、1历史反例、5跨版本身份；不能把累计测试当创新工作量。

016批量命令观察去掉重复线性查找，保留完整历史和信息权限。三观察/1489单回复及原图五策略全部动作、业务、物理事件、JSON继续和最终seal与015一致。事件预测总wall68.460→49.168秒、联合68.511→50.527秒属于两次本机描述性测量；015有并发编译，不能认证因果加速比。预测仍15次owner超过100ms，联合24次且最慢199.5798ms，比旧联合尾部更差；完整请求、更大原流与两机部署仍未测全。P7保持NOT MET。

C0在明确工程范围扩大；C1仍hypothesis，C2仍refine_mechanism，C3仍hypothesis。服务费用强指派已解释P5当前有限域全部收益，事件joint原图没有额外收益，不以模块、测试、通知或小网络数宣称新算法。下一次机制设计及大训练前继续核验最近邻原始文献、合法信息、候选覆盖、同G31强参考与正常业务保护；两项业务目标、100ms和TRE/CIE证据门不变。
"""
p.write_text(text,encoding="utf-8")
print(json.dumps(dict(status="updated",state=str(D/"RESEARCH_STATE.json"),progress_section="012-016",novelty_section=28)))

