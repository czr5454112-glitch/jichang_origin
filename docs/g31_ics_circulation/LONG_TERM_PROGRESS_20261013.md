# LT-1 实施记录：真实宿主、在线控制、强参考与原图反证

当前以文末“012—016实质研发、独立纠错与当前续跑位置”及RESEARCH_STATE为准；较早版本的“当前/下一步”与负结论保留作历史，不自动适用于016。

本记录从已经完成的 `codex/g31-ics-v3-circulation` 工作区继续，参照长期包，不回滚、不再次导入 V3。工作树 HEAD 仍为成熟 G31 `46cc46ab6bc121628fd6357e9f3c7636745fd732`；本轮源码未提交、未推送。旧结果及修复前失败全部保留。下面的工程通过不等于 P1–P7 全部完成。

完整阅读的总纲、起点说明和发送说明在 `docs/external_review/g31_ics_long_term_20261013/`；ZIP SHA256 为 `b1d5a52669da364dde2f64085e5cf51917f0c0ce32097b132d993efefc61a3e1`。唯一核验起点的 P0 对照包含旧交付24份实现及54份编译来源身份，未重复冒称旧1580项测试由本轮重新运行。

## 实际实现与验证范围

- `NativeSession` 持续推进成熟 G31 的唯一事件堆，支持异步区域请求、实时生成空盘意图、合法需求/服务预测消息、真实资源变化唤醒、checkpoint/restore/fork。完整状态与离线诊断不进入在线 owner 观察。
- 完整 circulation 状态与既有 J2/P2 能力、源/合流队列、头距、故障真值/已通知状态、结果分母共同捕获。checkpoint 只支持声明的安全事件边界，未声称支持任意事务中断或不可信对象文件反序列化。
- 区分物流区、控制分区、资源 owner。R1 的公开 A* 编解码保留真实已执行前缀、Storage 阶段和可替换后缀；异步交付时再次检查权限、版本、当前阶段合法后缀和已通知故障。S4 仍逐跳决定、原生 shield/JIT/P2 仍执行。
- R2 从 owner 观察和合法已送达消息生成请求，初始 `transfers=[]`。actual / firm / conditional 三种供给不混为现货。普通解析匹配、终点腾位、已公开条件服务窗口是强基线，均不宣称创新。
- 预测撤销通过原生延迟 tombstone 传递，可先于原快照到达；它只撤软预测，不能取消已出发托盘或接收义务。
- `live:` 在线请求命名空间与环境回放隔离；公开消息序号按通信通道分配，公开 traversal 版本按 tray 分配。内部全局 traversal 审计身份仍保留。修复前的两个跨 owner 计数泄漏有真实执行回执；未来请求 ID 问题只保留静态发现与实际修后证据，不补造不存在的修前日志。

当前稳定 native 构建是 `p1_build_006`，二进制位于 `build_lt_session_006/python/czr005_circulation.cp311-win_amd64.pyd`，SHA256：

`0bdd31835d8e9b7269bb2d45e14484054aad73abf3a10dc989f3574230b16190`

`live_validation_002` 实际记录146项通过、0失败/错误/跳过，且源与二进制身份绑定。随后 Python 解析控制开销优化如有变化，须另跑新回执，不能挪用该通过。`p1_checkpoint_validation_004` 对005源码实编专项，611个安全事件边界各做两个真实继续分支，并检查预测撤销等新增状态。`native_compat_001` 在其冻结源码上17/17 CTest通过；后续改动另有定向专项，不将该17项标签移植到新源码。`legacy_parity_002` 实际重跑固定成熟基线和当轮源码，无故障/故障两场共10类确定性输出相同。

最终006构建及源码绑定的 `live_validation_003` 实际 **180项通过，0失败/错误/跳过，source_changed=[]**。该次包含新增同H完成性、有限参考删失、原图阻塞证书和事前选样回归。`p1_checkpoint_validation_005` 再次实编通过611边界专项；不是把旧版本测试数量重贴到006。

## 实际失败与修正

| 发现 | 修前证据 | 修正及边界 |
|---|---|---|
| 路由偏好被原 scorer 覆写 | `p1_session_dev_001` | 在 scorer 之后应用已授权偏好，仍受 shield 和执行前缀限制 |
| 静态零容量域仍沿旧势走不可用捷径 | `static_closed_domain_before_*`、早期原图运行 | 在声明的零容量关闭合同中建立公共合法域，不改图方向/边数；零容量的现场含义仍未知 |
| 长等待仍由末尾兜底和首选路径规则重复轮询 | `p2_recovery_before_001`、`p2_preferred_wait_before_001` | 依赖真实容量/头距/队列变化唤醒；保留成熟 S3/S4 与 FIFO 权限。单出口不需要排名唤醒，发现回归后保留原断言修复 |
| 已知死后缀、已通知故障错误返回 updated | `p3_route_invalid_before_001` 两项真实失败 | 检查当前运输阶段目标与已收到故障，准确拒绝 |
| 有限参考把提交 pending 后的拒绝当可行动作 | 早期有限参考及专项反例 | 读取实际终态；异步拒绝保留原结果但排除可行动作，未解析/预算状态保持 unknown |
| 全局消息/运输序号泄漏不相关 owner 活动 | `private_message_counter_before_001`、`private_traversal_counter_before_001` | 改局部通道/实体版本，三个 `--require-fixed` 探针在005通过 |
| 有限参考把未到H的控制续跑当最优 | `analytic_independent_review_001/censored_continuation_receipt.json`：目标20，实际0.1，却认证最优 | 校验请求H、结果H、分支/结果/推进时钟及明确的完成标志，保留外层/内层删失；前缀物理审计不能替代完整性 |
| native时钟到H但同H还有未执行事件 | `same_timestamp_budget_before_002.json`：已报reached，继续同H又执行8事件 | 006内部检查所有到期事件已排空，返回horizon_complete；不向策略暴露未来事件堆；刚好用满预算但确已完成的正控制仍通过 |

全部原件根目录为 `outputs/experiments/g31_ics_long_term_20261013/`。`RESULT_INDEX.jsonl` 为结果导航；不能以一场 `passed` 推断另一个物理合同通过。

## 原图和完整源：保留负结果，纠正语义过度解释

源表核验得到151节点、227有向边；1×完整28506袋、2×完整57012袋，保留父身份与既有增密规则。完整任务带只属环境；策略看不到未来任务数和到达带。

源表 F1 为“托盘容量（个）”，97→98 的 F7=0 是原数值；全部227条边恰好符合 `floor(length/2m)`。旧成熟 adapter 仅把容量保留为 metadata。因此 **原值0已确认，但“0意味着物理封闭”未获现场确认**。本轮保守 native 合同仍按关闭处理；没有擅自改成1。短连接零缓存、两端接管/尾窗的另一种物理合同尚未实现，不能拿一个推测解释把原失败改写成成功。

`p2_original_1x_live_s4_002` 在当前保守合同下真正到 H=86400：30877事件，28506全部观察，22装载、0业务完成，独立工序/盘守恒/容量审计通过。005的 `p2_original_offline005_001` 又输出精确原生队列：Storage53队列 `[22,23,24,25]` 对应袋0→99、袋2→116、袋1→99、袋3→47；队首22无正容量后缀，后面有可达业务仍被FIFO挡住。Storage在19500确实释放过4盘，不能把它们统称为尚未释放或全部不可达。

其余实际等待链为29/137/150/139→112→53，以及136→137；当前证据是无环的链式回堵，不是证明存在循环死锁。不能取消头袋、允许越过固定 FIFO、删掉4001个静态不可达业务或扩盘来伪造完成。

004同H=21600的1×/2×反应与预测四组均真实执行，完整输入都在分母：1×观察3485袋，18装载、0完成，6次导出/2次接收；2×观察6449袋，17装载、0完成，6次导出/1次接收。预测请求更多，逐袋受限耗时却相同。该组无业务收益，不据此删除区域自治或预测预平衡需求。

合法往返机制组按事前静态条件从原母流选择，使用完整原图、真实任务到达/目的地/Storage，单盘为单独库存因子；它不是完整运营流，也不能取代以上全流负结果。选样规则与被排除任务数量必须随结果一同交付。

`p2_original_mechanism_2_005_001` 的两个原源业务均由 `initial:26:0` 真正完成，中间一次真实跨区返回，反应与预测成本相同。相同事前规则扩至24件的 `p2_original_mechanism_24_005_001`，两法均24/24完成、23次真实返供received，同盘身份贯穿。预测总 arrival→unload 耗时418514.272581→414198.867581秒，约1.031%改善，逐件不恶化；但两法均 **19件逾期，仅5件按时**，不能称业务质量达标。完整151/227图、边方向和容量未改；母流28506件中10320件满足静态往返条件，再取首个合格loader的前24件，不按模拟胜负挑选。可读逐盘/逐业务事件账为该目录的 `actual_same_tray_event_table.md`，JSON保留运输段ID。

全流的 `p2_original_offline005_001/fixed_contract_blocking_certificate.json` 给出13项实际充分条件：队首独立BFS不可达、Storage4盘占满且固定FIFO覆盖全部占用、其余18盘都需要进入该库、真实接收依赖链终结于此、无空盘/在途盘/接收租约/可恢复隔离盘。仅证明固定FIFO、on-carrier、零边关闭且禁止撤任务卸盘的当前状态不能再完成服务，不是机场全局最优或现场不可行证明。

另新增并实算独立单盘FIFO乐观下界 `single_tray_lower_bound.py`。保留真实有向正容量最短旅行、Storage绝对释放/最小驻留、装卸及hold，放松所有非负节点服务/拥塞/头距/消息等待；限定唯一盘、同一FIFO loader、不同到达时刻且全24件仍在总体。`p4_single_tray_lower_bound_006_002` 对机制组两法及原图返供参考六支，共八组各1210条traversal重新审计，实际同盘加载顺序均符合下界适用前提。受限耗时下界395187.971581秒，必然最终逾期至少19件，本组截止均早于H，实际恰19件。因此这19件逾期在该一盘合同中无法仅靠合法同序路由消除。预测成本距乐观下界仍19010.896秒，约实际成本4.5898%；下界可能不可达到，不能把差值全当可学空间，更不能外推多盘/完整母流不可行。九项下界反例回归通过，该松弛属于强诊断而非方法创新。

## 强参考与创新反证

R1 的 `regional_native_002` 在005实跑6种请求链，包含非慢层时刻、执行前缀、迟到、过期、权限拒绝及已通知故障绕行。三动作真实 fork 产生两种实际路径，但 Storage 释放余量吸收了0.2秒差异，业务 headroom=0。这个实际余量反例不是新求解算法。

R2 的9×2合成组支持自动预测意图与消息提前期作用，但普通解析已解释其收益。双向耦合组 `coupled_native_003` 显示：载盘路由改变释放；空盘共享节点占用又改变 B2 下一跳。普通预测将总耗时20.61降至19.55，却让B2从11.75变成12.05，故保护门失败。B2在6.2才到达，先前不允许偷看它来安排返盘。

独立的已知服务合同组让B2于0.5真实出现并加载5.8秒，保持其首跳约6.35；合法预测消息明确传播条件占用。`known_service_native_001` 的反应/普通预测/公开窗口预测成本为26.31/25.25/26.10。窗口组保留B1/B2完成时间，仅让B3从10.01提前至9.80；同信息十动作真实有限参考中5个通过逐件保护，强窗口基线 headroom=0。该0.21秒属于普通强基线解释，未晋升 C2 创新。

最新判定与原始文献访问回执见 `NOVELTY_LEDGER.md`：C0工程范围扩大；C1仍为研究假设；C2需要具体机制重构与更多强对照；C3未放行大训练。通用分层、消息接口、更多测试、普通匹配和余量检查不计论文创新。

完整性漏洞修正后，006重新实际运行 `analytic_native_009`、`known_service_native_003`、`coupled_native_005`、`forecast_lifecycle_native_003`、`regional_native_003`，全部source_changed=[]。强窗口26.10、保护反例及有限域headroom=0重现。原版本回执保留，但其参考入口存在已复现的误认证缺陷，不能仅靠旧通过来认证其他删失分支。

进一步独立复核还发现显式 `envelope.status=null` 被当作无包装，已保留反例并修复；最终 `analytic_native_010`、`known_service_native_004` 再次实跑正常结果不变，独立29组完整性检查全部通过。最终参考源码 SHA256 为 `3be0198c943d4c2eb520ef258e270146dfafe9709d360d13b67551e86616efe1`。审查细节见 `ANALYTIC_INDEPENDENT_REVIEW.md`，含未重跑而仅读取的证据边界。

`regional_original_001` 把真实按需请求接至原图：双方共同增加明确的研究路线权限因子（不是现场授权），按公开观察选择第一个载盘未入边且有两个合法后缀的事件边界。8888.531299秒在国际owner看到选择[2,28]，A*请求经真实消息完成updated，父checkpoint不变。两支从同一后续控制相位推进至86400，均24件完成、19件逾期、逐袋成本相同；这一原图无收益结果保留。

原图强参考已扩到实际两个事前边界。`regional_original_003` 枚举上述时刻的WAIT、next2、next28，三支均全H完成且经独立审计，产生两种真实物理轨迹，逐袋成本相等。`p4_original_first_return_reference_006_001` 在首个固定60秒tick公开空盘意图（19800秒）枚举WAIT/解析/+1/+15/+30/+60秒六动作，六支全H完成，五种物理轨迹。解析与+1秒并列最佳；其余逐袋保护不通过。两小域headroom=0，仅约束该边界、单次干预及固定继续策略，**不能说明提前预测、多次干预、其他端口或全流量没有改进空间**。首返供入口替换整个当前epoch，缓存与下次tick相同，并非任意连续控制的全域优化。

`regional_original_001/002` 的选择清单误保留了加授权前的base输入hash，实际input文件和事件未伪造或覆盖；003已分别保存base与最终输入hash并完整重跑，独立复算一致。首返供001仍绑定null补丁前的参考版本，实际每支status均明确reached，经最终完成性规则逐项复核通过，未冒称已绑定最终源码。

## 100ms 与后续接入

`regional_native_002` 测量从观察、转换、A*、编解码、提交，到真实消息事件/owner复验、确认与响应编解码，并把其间 native 事件计算也计入。6个小图样本为0.102–0.425ms。它是完整单进程小样本链的测量，不是原图、部署或硬实时验收，也未包含外部控制器跨tick自动继续。

完整原图第一次反应控制已观察最大818.2ms；同H预测组也有138.65/123.15ms，均明确未过100ms。正在依据分项 profile 优化需求投影和解析候选计算，拒绝、超时和无候选保留分母。不能仅报告 native 事件或网络前向时间。

原图cProfile优化前后全部28506条业务结果逐字段一致，事件审计通过。候选计算1.648→0.552秒，路径查询34906→1603次，匹配0.276→0.009秒；同时改变native需求投影和Python实现，因此不作单因素归因。带剖析器的峰值315.78→76.72ms只作诊断。原图R1上述完整单请求样本实测1.7575ms，CPU计时落入当前计时分辨率0；不能据此声称全天或所有请求100ms达标。

最终006四组同H21600、每组50次owner调用，1×反应/预测峰值34.791/41.117ms，2×31.684/64.992ms，业务与物理事件逐字段与优化前相同，完整分母不变。005目录中一次名为predictive却未传该flag的运行保留为重复反应组，按真实回执标记排除，不按目录名认定策略。

随后针对原来76500秒热点追加**唯一一组固定预算全天验收** `p2_original_1x_reactive_H86400_006_001`，实际72.142秒到H86400，28506全观察、18装载、0完成，物理审计通过。相同国际owner、相同27975公开需求/零供给热点从818.200降至136.725ms，仍超限。全日最大是83700秒国内owner的211.262ms（观察87.080＋解析124.178），194次中75次>100ms。因此 **100ms当前明确未达标，连已测owner子链都失败**。6小时样本峰值不能代替全天。完整请求还有未计的发布编解码、交付复验/确认等开销，不能通过改变统计对象或P99门槛放行。

后续实际接入点：完成最新源码的大流重测；保留全流阻塞合同，继续合法原图往返研究组；将服务预测修订/撤销与固定模块用盘次序接入真实修复候选，比较同权限解析、通用资源闭合和全域修复。只有候选覆盖、信息、标签与 P5 方法门成立后再进入 P6。P7的完整运营外推、独立来源、真实模块/无等待链/off-carrier、显式隔离与全链100ms仍有缺口，未因工程进展而降级。

当前具体续研顺序：先用只读原生索引及FIFO等价列设计紧凑控制投影，和全量观察逐动作/逐业务/逐事件对照，不删除offered分母或当前需求，也不缩K伪造低延迟；再按P5分支C检查服务约束/需求变动/长线条件下联合候选的剩余空间，固定强窗口与同信息参考，明确资源/源保护/策略读集边界。当前零headroom只来自受限首动作域，不能作为停止R1/R2或开始弱标签大训练的理由。

主要复跑命令（在本独立工作区执行，使用新的output目录）：

```powershell
$env:PYTHONPATH='src;.'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONIOENCODING='utf-8'
$g31Binary='build_lt_session_006/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_live --binary $g31Binary --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_006/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/live_validation_reproduce_001
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_original_regional --binary $g31Binary --reference --output outputs/experiments/g31_ics_long_term_20261013/regional_original_reproduce_001
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_original_reference --binary $g31Binary --output outputs/experiments/g31_ics_long_term_20261013/original_reference_reproduce_001
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_original_control --binary $g31Binary --scale 1 --horizon 86400 --control-period 900 --max-events 100000 --wall-budget 120 --output outputs/experiments/g31_ics_long_term_20261013/original_day_reproduce_001
```

精确续跑状态、命令与最新回执以 `RESEARCH_STATE.json` 为准；所有 runner 都要求新的输出目录，不能覆盖历史。

最终冻结复核：`live_validation_005` 为196项通过、0失败/错误/跳过，source_changed=[]，二进制与build006身份一致。004虽196项测试均过，但下界脚本在运行中改动，完整性门正确拒绝发布；失败回执保留，未冒用其测试计数作为最终通过。

## 本次继续研发：紧凑投影、联合候选反证与通信协议

用户取消推送时尚未进行任何提交或推送。继续沿原工作区实施，没有重新导入或回滚。

新增 native `observe_control`，保留全量 `observe`。完整真实队列、业务结果与已知业务身份遮蔽规则不变；每个 origin 给精确数量及 FIFO 前缀。K 来自本 owner 当前可见非隔离实体托盘数量，而非任意截断。公开 incoming 覆盖及本地最多 K 个留存之后，再保留最多 K 个等价匹配候选，所以保存前 `incoming+2K` 个身份足够当前 ETA 等价列目标。已知历史 origin、当前载盘业务、服务预测与撤销均保留。未来如果使用逐件 deadline/目的地/优先级成本，或允许单盘一次优化多轮服务，必须重新证明该等价键/上界，不能沿用本结论。

新 native007 SHA256 `c38268f976f8a0b8d546dd7c495b7daa2d02e80103a7c5a0aa0fa54c007054f5`。`compact_control_native_001` 的19组实际继续/分支全部等价；`compact_control_tests_002` 为90通过、0失败/跳过、source_changed=[]。首轮3个fixture错误保留真实失败摘要，明确当时未捕获JUnit和beforehash，不补造证据。

`p2_original_1x_reactive_{full,compact}_H86400_007_001` 串行实跑到86400秒，全部28506业务、输入crosswalk、逐tick动作及残余重算、所有真实事件、controller状态与native最终状态均一致。194次已测owner子链最大258.208→47.781ms，>100ms为86→0。新增发布签名/快照计算单独记录；owner子链加同owner发布的最大值为290.709→65.502ms。业务仍0完成，未改善原有物理阻塞，也未称完整100ms通过。

`NativeBatchMeter` 仅包裹既有 advance/result 调用，不增加事件或推进边界。日志保留原生共享事件批次 wall/CPU 与离线结果序列化；900秒逻辑区间批次不能均摊伪装为单次请求耗时。送达owner复验的独立成本、完整ACK/确认和多进程部署仍需补齐。全部比较见 `p2_original_1x_reactive_representation_comparison_007_001.json`。这是工程表示优化，不是新求解机制。

P5已预声明短线/2km/5km/公开状态相同但新增未知源需求四组，固定2盘有限域31动作/组并全部做真实native fork。初次冻结124支中，前三组普通窗口、一轮固定指派重定时与联合指派重定时均无增益；未知源组联合方案恶化且保护失败。所有条件窗口冲突动作均保留并执行，不能用该不完整预测模型认证物理不可行。`p5_joint_windows_006_001` 和独立 WAIT 保护 assessment 保留原件；后续独立审查发现同刻 pledge 读取集失效漏检、terminal-clearing 时间字段、浮点候选ID等缺口，正在修复并将另行留存前后证据。

上述为本轮开发中间状态。后续已完成的协议、修复和真实运行见以下009冻结记录；原始失败仍保留。P6大训练继续受候选、信息、真native标签和P5方法门约束，没有降低门槛或用更多测试替代研究贡献。

## 009冻结：协议故障续跑、P5闭环反证与两倍全天复测

本次仍未暂存、提交或推送。009 binary SHA256为 `fbc97e38552c03af81c2c6d896a2d4d67fcf8c7eefd5a5319ef4651b37d3daea`；`p1_build_009` clean编译45.59秒成功。008是真实编译失败：在声明之前使用 `RuntimeEvent` 别名；改为已可见的完整类型名后重新clean构建。008原命令、退出码及编译输出保留，不能仅归为source_changed或写成成功。

`circulation_protocol_impl.hpp`、checkpoint和binding新增可选transfer协议：真实 ACK 发出/延迟/丢失/重复、超时重试、源/接收owner不可用及恢复。稳定请求身份避免重复调拨，旧响应保留其发出时快照。协议实现还修复了未收ACK前owner版本泄漏、相邻/重叠outage和同刻物理阶段短暂授权、恢复时多wire只回应旧attempt的问题，极端派生时间在写状态前拒绝。实际已出发盘继续，不借故障取消硬义务。默认disabled行为继续保留。

`owner_protocol_tests_001` 21项通过；`owner_protocol_native_002` 10场真实事件账通过，包含一场实际拒绝。每场都有fork/restore完整未来比对和独立物理审计。首轮native001的第9场暴露的是验收脚本把“最后ACK的attempt”误认为“最高已回应attempt”；单独probe保留真实ACK到达序列2、3、1，确认attempt3确有实际回应且只产生一份授权/转运。修正验收为检查实际最高attempt已回应与最后emission sequence，未更改native制造通过。**该协议尚未接通R1路由、需求/服务公告及现有R2控制器；它只是新增故障合同下的transfer子闭环。**

当前源码的 `live_validation_006` 为277通过、0失败/错误/跳过，编译源身份匹配且source_changed=[]，16.47秒。`p1_checkpoint_validation_006` 实编三个目标，82.73秒、6条命令成功；默认5场611个事件边界仍双分支一致。协议分支另由上述21专项和10场真实账验收。`legacy_parity_003` 两场与成熟46cc46独立fixture的全部五类hash一致，21.65秒。未将这些计数冒称全仓1519测试或全部历史实验复跑。

### P5从静态候选推进到实际反馈与持续循环

P5实验固定使用native006，不能把009通过的工程回归写成这些数值已经在009重跑。最终主实验 `p5_joint_windows_006_003` 完成4×31=124条真实分叉；前三组普通窗口已达到当前有限保护域最优，headroom=0。未知源组joint/一轮方案成本15002.65，普通方案10406.15；联合方法保护失败。完整观察域H5000、全部5/5/5/6业务与异步拒绝保留。

发现同刻pending pledge/取消虽不变owner事件版本和时钟，却改变合法供给读集。`p5_read_set_before_001` 实际加载保留旧源码，两个反例错误提交，require-fixed退出1；after001两例正确拒绝 `stale_read_set/public_dependency_changed` 且无状态修改。现在用完整合法公开投影的canonical digest补齐版本/时钟校验；保守且可能过度失效，未声称原子多owner提交或最小读集。终点压力时间字段、浮点候选ID合并和opaque ID排序改变策略也已修复；004专项19项通过，开发原件未覆盖。

`p5_joint_feedback_006_002` 在预声明0.91秒公开边界运行两个世界×三法。真实观察到T0已载上UNSEEN后，只取消两个自有软意图，保留有效T1分配并重定时；成本15002.65恢复至10406.15，与普通强窗口相同。无变化世界不取消，成本1210.40。原终点10容量1且无出边，TP卸载hold后仍停在那里，UNSEEN无法完成；真实诊断账单独保存，不能把它归咎于隐藏信息或用无穷训练弥补。

为拆开固定不可返程因子，新建**所有方法共享的独立合成合同**：仅增加10→7（0.5m、1m/s、容量1、头距0.2s），保留旧四组原图不变。这不是原机场图修复或现场授权。`p5_joint_circulation_factor_006_001` 执行两世界×31=62条真实分支，H2000，10.11秒起使用相同强解析连续控制；初始异步拒绝仍单列。所选方法均完成全部5或6袋，未知源世界同一TP真实服务P后，在10.21获返盘许可，经10→7→0→2→3于1202.30收到，再于1203.40完成D0。

真实闭环并未令研究门自动通过：未知源世界 ordinary/one-round/joint总成本同为2411.80，WAIT2649.331，但ordinary相对WAIT推迟D0和UNSEEN；joint相对ordinary又推迟D1。保护已有P/U0/U1不等于全部offered正常服务保护。各参照有限保护域headroom仍0，全局最优未知。普通反馈与既有解析机制已解释当前恢复，尚无独立新方法增量；P5仍research_candidate，P6未放行。

### 2×完整全天：保持语义的加速仍未通过100ms

009用输入静态node→owner索引替代观察和发布中的重复线性查找，restore重建该索引，不缓存物理真值。`p2_original_2x_reactive_compact_H86400_009_001` 串行157.36秒到达H86400；`p2_original_2x_owner_index_comparison_009_001.json` 明确允许007→009二进制变化，仍核对全部57012业务crosswalk及结果、57544真实事件、请求/回复、逐控制决策和最终controller/native状态完全相同。

| 2×紧凑表示全天 | 007 | 009 |
|---|---:|---:|
| 194次owner计算max | 89.244ms | 62.857ms |
| owner+同owner发布P99 | 129.299ms | 110.169ms |
| owner+同owner发布max | 131.468ms | 110.722ms |
| 合计超过100ms | 31/194 | 8/194 |

业务仍0/57012完成，全部分母保留；native completed_count是运输段，不能替换业务计数。这是零供给/积压压力下的工程优化，尚未覆盖活动多请求和完整两层链。共享native事件批次、离线序列化、逻辑通信延迟另记；当前累计还漏独立交付复验/完整确认成本。**已经测到的计算部分仍超100ms，P7未达标**，不改成P99口径、不均摊、不宣布达标。

下一具体工作从两个缺口接续：一是把合法route/demand/forecast和控制器状态接到实际ACK/不可用协议，逐消息族核对拒绝/超时/恢复及强基线公平权限；二是继续拆分公开队列构造/签名成本及活动请求交付复验，再在不改变事件轨迹的条件下优化。P5继续研究多次真实控制边界的供给/资源依赖修复，先与持续解析反馈和同预算参考比较；不扩大旧标签训练。原图零容量解释、等待/EBS物理合同未获现场依据的部分仍保持代理边界。

当前可运行入口（输出需使用未存在的新目录）：

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$g31Binary='build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_owner_protocol --binary $g31Binary --output outputs/experiments/g31_ics_long_term_20261013/owner_protocol_recheck_new
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_live --binary $g31Binary --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_009/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/live_recheck_new
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_original_control --binary $g31Binary --scale 2 --horizon 86400 --control-period 900 --max-events 160000 --wall-budget 240 --compact-projection --output outputs/experiments/g31_ics_long_term_20261013/original_2x_recheck_new
```
## 010—011继续研发记录（后续冻结结果见本节末）

仍在原 `codex/g31-ics-v3-circulation` 工作区，HEAD为成熟G31的46cc46；未重新导入、回滚、暂存、提交或推送。当前第一项实质任务是把R1改路、需求/服务预测/撤销和R2调拨接入同一真实通信故障链；第二项是对多次真实边界修复做强对照和容量必要界分析。没有重新把三个V3修复或一盘两服务当作主要目标。

010 clean原生构建成功，SHA256 `079eaaeae53671d1a7d2a26437478850b329db80ec8eebc58b1fa70f5f0ddb7f`。增加五类原生command消息、真实source执行/peer交付/ACK事件、不可变重试和完整checkpoint；旧transfer协议保留。新增Python真实协议控制器和JSON状态，与native checkpoint成对续跑；物理推进仍只有成熟G31。预算中断返回unknown及精确原生停止状态，部分控制tick当前拒绝恢复，不冒称完整游标续跑已实现。细节见SERVICE_CONTRACT和CHECKPOINT_COVERAGE的010段。

独审与真实独立探针修复了三项初始控制器错误：预算耗尽后result_at另开预算偷偷推进同刻事件；预测撤销后旧缓存阻止同阶段恢复发布；路线去重忽略新公开故障/路径。`protocol_controller_before_010_001`使用保存的旧源码真实运行，三项均failed；`protocol_controller_after_010_001 --require-fixed`三项均passed，source_changed=[]。原始输入、回执、事件和修前源码保留。这些是正确性修复，不计作研究创新。

`live_validation_007`实际320项中319通过、1项error：Windows共享Temp下pytest目录权限错误，未把它描述为代码测试失败或全通过。验证runner现使用本次新output内独立basetemp，`live_validation_008`实际320通过、0失败/错误/跳过、source_changed=[]。68项协议专项包含在320中，不能相加为388项；两个68项专项运行是技术重复。当前C++ runtime经`p1_checkpoint_validation_007`实编三个目标，6条编译/执行命令成功，93.492秒；611个安全断点各双分支继续。`legacy_parity_004`22.381秒通过两场、每场五类确定性输出与成熟基线对照。这些回执均绑定其实际源码。

`protocol_control_native_010_001`在7种共同通信场景×4个解析控制对照上完成28次真实运行及独立物理审计。普通/丢ACK/重复ACK场景中reactive成本25.87，predictive与joint25.65，均2/2业务完成；源端或接收端不可用后预测优势消失。拒绝接收场景全部方法仅1/2完成，无调拨授权；known-service丢ACK场景三个R2方案都3/3、成本26.1，无新增联合收益。R1-only在该场景仅1/3，仍保留完整offered分母。允许后缀替换是该合成组共同明确合同，未改历史known-service合同。5个完整模拟改路请求测到最大0.5444ms，涵盖拒绝/超时unknown，不是原图全天或两机部署的100ms认证。

全日优化先在冻结009上做真实76500秒热点微剖析：`p7_native009_microprofile_002`重建172次决策和56405事件与原回执相同，60次只读测量不改状态。001因86400整数与旧86400.0浮点的输入编码哈希差异在执行前准确拒绝，原错误保留。热点主要在公开观察和需求签名，不是网络前向。010将owner固定任务顺序预构建，并以相同canonical bytes调用成熟SHA-256实现；不删业务或改候选。

`p2_original_2x_reactive_compact_H86400_010_001`195.068秒实际跑至H86400，全部57012业务、57544物理事件、输入crosswalk、请求/回复、逐tick决策、最终native和controller状态与009逐项相同，比较回执`p2_original_2x_signature_comparison_010_001.json`为equivalent。发布计算max50.7437→28.6099ms；owner加同owner发布max110.7216→101.0037ms，P99=100.7863ms，超100ms从8/194降至2/194。owner自身max62.8571→79.8689ms，不能忽略这一反向变化或把不同运行的总变化全归因于一项代码。最新全日实测子链仍失败，完整请求、两机冷/热/突发及部署要求仍未达标。原保守业务合同仍0/57012完成，优化没有消除物理阻塞。

P5新增16条真实两边界干预，最终`p5_dependency_repair_006_001`绑定native006，不能用010回归代替其身份。在新源未知世界，真实接收下界驱动第二次修复，把D1从1203.6提前到803.55，却把D0从803.35延后到1203.4，总成本仍2411.8；更准确局部占用不保证全体正常业务改善。同信息普通持续解析/源反馈/两次修复和全部异步失败都保留。固定3盘、容量1长入边的独立必要界证明特定两参照目标交集至少缺319.289秒；没有证明整个调度模型不可行。001检查器被发现“不同终点不等于两次cross”的复用漏洞，002加去cut后连续服务不可达守卫并保留反例，实际固定因子800秒下界不变。完整结果、30项重叠回归及限制见P5_JOINT_WINDOW_REPAIR。

随后独审又用真实局部占用复现路线A→B→A缓存问题，并用同盘实际卸载/hold/二次装载复现请求时签名与延迟capture不一致。`protocol_route_aba_before_001`和`protocol_demand_capture_before_001`均fixture_valid、物理audit通过且require-fixed退出1；冻结dead96旧源码保留。011正据这两个反例完善已送达ACK与客户端状态，不篡改capture时刻或取消正常业务；具体最终验证和原图24任务连续比较在后续冻结段记录。

### 011最终冻结、原图连续业务及精确续跑位置

011 clean构建47.64秒通过，binary SHA256 `19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`。相对010只改binding：根据实际已送达demand ACK引用的、已经seal绑定的immutable原消息计算capture摘要；核对身份、owner/target和真实采样/完成时刻，旧pending ACK不会获得后来数据。派生digest缓存不加入物理状态，restore/fork清除并重建，返回新dict防可变污染。controller状态升级v2，原v1请求时签名缓存明确拒绝恢复；每源→目标至多一个未确认公告，当前真实队列与已确认capture比较后才决定新发。route按当前stage最新请求串行确认，历史A的ACK不再遮蔽B→A回切，迟到旧重试也不会重新执行旧路线。

`protocol_route_aba_after_011_001`、`protocol_demand_capture_after_011_001`和`protocol_controller_after_011_001`全部require-fixed实际通过。后者仍包含最初三项反例，未删回归。额外发现并实际修复浮点终点：`protocol_tick_boundary_before_001`请求H=0.6099999999999999却因epsilon执行到0.61后回退报错；`protocol_tick_boundary_after011_001`严格停H、续到1.3与连续运行全部事件及native/controller状态一致，拒绝过去H时也不改状态。该修复没有放宽边界断言。

最终`live_validation_009`为**342项通过，0失败、0错误、0跳过，源码前后无变化**，与build011编译身份一致。这是circulation及关联模型回归，不是全仓历史1519项复跑。7项binding专项004、11项原图runner专项002及三项新真实probe均包含在342中。binding专项001—003保留测试构造错误的失败：同区导出按原权限正确拒绝、非法空fleet、混淆EDGE_EXIT/EMPTY_RECEIVED/LOAD_START/loaded_at；最终按真实接收和装载完成事件修正fixture，不改native权限或放宽语义。011仅binding改动，C++ checkpoint007与legacy004的编译来源仍相同；其611边界和两场旧模式结果的范围不扩张为历史全仓复跑。

`original_protocol_24_011_001`让同一151节点227边、原静态选择的24业务、原唯一托盘`initial:26:0`在真实owner协议下持续运行到86400。只共同新增通信合同，未改原盘/任务/容量/方向/权限；完整28506行母流crosswalk及选择哈希保留。三策略均24/24完成、23个物理跨区调拨全部received、独立物理审计通过。reactive成本418514.272581，predictive/joint414198.867581，减少4315.405（约1.031%）；24件中20更快、4相同、0更慢。期限违约仍19/24。各69条跨三策略实际同盘“卸载→hold→授权→真实有向空返→接收→再次装载”核验见`original_protocol_24_review_011_001/assessment.json`，无提前hold授权；没有用运输段完成冒充业务完成。

该原图组R1许可为0/24，因此真实route请求也为0；joint与predictive相同，不是双层联合增量。预测组22/23个调拨为卸载前conditional_release请求，仍由native等真实卸载和hold后才授权出发。16个服务预测command均实际ACK rejected，原因为`no_local_uncommitted_loaded_service`：延迟source执行时已无该合法未入边载盘状态，不能把这些拒绝写成有效资源窗，也不能将本组收益归给未实际成功的服务预测公告。新协议下三策略的业务结果与原合法24件组相同，支持工程连续性和普通预测基线，尚不支持主方法创新或完整母流业务目标。

另运行`original_protocol_24_budget_011_001`，三策略均在2秒部分tick用尽预算，metrics=null、declared_offered=24；保留原始部分段且不读取最终ACK快照、不补推进、不尝试恢复不支持的部分tick。主比较和预算对照均source_changed=[]。这也是对原图实验runner不能把截断结果记成完成的实际检验。

可执行命令（均须新的output目录，PowerShell环境`PYTHONPATH=src;.`、`PYTHONIOENCODING=utf-8`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`）：

```powershell
$g31Binary='build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd'
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_live --binary $g31Binary --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_011/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/live_recheck_new
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.validate_protocol_control --binary $g31Binary --output outputs/experiments/g31_ics_long_term_20261013/protocol_control_recheck_new
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_original_protocol --binary $g31Binary --expected-binary-sha256 19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec --output outputs/experiments/g31_ics_long_term_20261013/original_protocol_recheck_new
```

下一实际接入点：P3在合法本地状态变化处触发区域改路/预测，避免所有自动控制只能等共同慢tick；保留延迟source复验及拒绝，分别诊断16个stale-service拒绝、一次点预测过期后不刷新与真正候选不足。新增通知须来自已观察本地变化，不能借用私有未来事件时刻。P5先用必要界筛掉不相容目标，再对有可达调度余量的共同模型研究时间化接收/联合交接和强滚动对照；只增加重定时时点或网络不足以晋升创新。P7继续定位公开观察序列化，补原图活跃请求的完整投递复验/确认与明确序列化隔离，两机硬门保持未过；010的2/194超限和0/57012业务完成不能被小图或24件覆盖。P6仍在候选/信息/真实G31标签与主方法门前，不开展大训练。所有问题、失败和方法边界留在本记录、RESULT_INDEX与NOVELTY_LEDGER中；当前没有提交或推送。

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


## 2026-10-14 用户授权发布与复现准备

用户明确要求整理、推送GitHub并交GPT Pro审核，因此此前不提交/不推送的限制在本次发布范围内被更新；没有授权force push或改其他分支。原生016及业务/方法代码不变。发布审查发现四个测试默认glob被急切求值、一个测试硬编码仓外xlsx；已最小修正路径选择，五个文件全部assert AST保持。两份原拓扑xlsx逐字节纳入map_nanning，成熟adapter已原生支持仓内优先。publication_20261014_001/live_001重新实际407通过，0失败/错误/跳过，仍按401+1+5解释。历史011/015/016及成熟legacy fixture以哈希绑定Windows附件单列；不声称其可在Linux直接运行或等同独立重编译。

发布采用字节保真属性，使编译源和原始回执的SHA不被Git换行转换破坏；成熟依赖中仅换行表示变化的文件另列manifest，语义未改。具体代码提交、后续发布资料提交、公开文件清单、复现限制及推送验证由PUBLICATION_AND_REPRODUCIBILITY_20261014.md和GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md记录。历史回执中uncommitted/pushed=false表示其原执行时状态，不追改旧回执。
