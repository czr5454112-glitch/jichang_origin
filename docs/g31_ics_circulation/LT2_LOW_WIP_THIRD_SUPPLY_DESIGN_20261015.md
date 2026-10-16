# 第三次同盘供给：原合同下的最小跨 loader 扩展

这是两次实际成功之后选择的有限后续试验，尚未 native 执行。它保留原 28506 件输入、22 盘、R1=false、FIFO、容量、方向、服务目标及 2 秒控制线延迟；只准多发一次 R2 供盘。静态路径与未来业务表只用于下面的离线可行性诊断，运行策略不读未来表或跨 owner 原生状态。

## 已有事实与下一候选

[reuse002 实际原件](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_reuse_prepare_002/receipt.json)及[独立复核](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_reuse_independent_actual_review_002.json)证明：`initial:0:0` 先后完成 source26 的 job2、job6；第二次 LOAD=20382.599，UNLOAD=20812.397，HOLD=20813.397，最后在 domestic116 返空。22 次停车和两次供盘均收到真实 received ACK；H28800 时 8740 件已到达，全部 28506 件仍保留，28504 件未完成。没有逐件保护或完整请求 100ms 结论。

原 source26 的下一个 FIFO 头 job14 必经 `53→99`，在固定正容量图中不可达；不能改发 job23 来越过它。另一个 international loader49 的当前首头是 job8（arrival10084.10648，Storage53 release20700，destination46，deadline23400）。从 domestic116 到 international49 是原合同允许的跨区供盘，无需另加中转、改权限或动用其他21只停车盘。

这不是把 job8 写入控制规则。新策略调用原 `eligible_head`：从最新实际已交付 peer capture 中，先取各 source 的最早已释放 waiting 头，再按 `(arrival,business_bag_id)` 排序；只筛公开正容量必经路径与跨区端口条件。若实际新 capture 不支持任何候选，就不发请求。job8 是原已保存状态与这一规则的离线预期。

公共图必要筛查结果：

| 阶段 | 自由流代价 | 需要保留的实际限制 |
|---|---:|---|
| 116→49 空供盘 | 476.379 s | 原R2源复验、接收预约、实际路径、ACK |
| 49→Storage53 | 252.767 s | 原loaded FIFO、接收容量、服务 |
| Storage53→46 | 183.656 s | 原storage release、loaded路径、UNLOAD/HOLD |

自由流总和912.802秒不是完成时刻上界，也不是 native 已可执行证明。49→53 会经过50/34/35/36/45/37/46/39/48/40/28/29等12个停车节点。原静态计划在每个点仅停1只空盘，容量4，静态仍有3个泊位；但实际队首阻塞、接收预约和串行服务仍可能失败。旧第二次空返通过了其中多数点，只能说明那一次轨迹可执行，不能保证新loaded轨迹。

## 最小在线阶段与界限

新增[独立模块](../../scripts/experiments/g31_ics_circulation/research_original_low_wip_third.py)继承冻结 `ReuseOwner`；原005及reuse002不改。第三阶段只在本 owner 已知第二次供盘/已见第二次动作之后开始。

1. 原 token owner 继续实际 ACK/retry。仅在自己的第二 transfer 已收到 received ACK，且当前本地同 token 空、stationary、available、无接收预约时，发真正的 `planning_snapshot_v2`。这里“第三轮”不表示改用v3消息或027二进制；仍使用已接受026。
2. 对方仅收到这个真实邀请，且邀请含第二供盘 received ACK及其后的 source-owned同盘完成记录，才重新发布自己的原生快照。旧第一次返空记录不够；reply本身不授权供盘。
3. 原 token owner 还须拿到自己的最新已送达 ACK 自副本，绑定第二件精确身份、目的地、同盘 UNLOAD_COMPLETE；当前本地 empty/available 另证 HOLD 已结束。peer快照必须是最新有效已交付版本，capture时间不得早于该自副本capture。然后调用原FIFO选择器。
4. 最多发一个新的 immutable `third-supply` 请求。拒绝、丢ACK、无头、过期、超时均保留，不换头、不换盘、不换目标。对方一旦在实际消息中看到第三动作，便停止新发布，双方的ACK/retry继续。无第四次供盘。

预算固定为 H28800、25个物理请求（22停车+3供盘）、2882 ticks；一个parent共享600秒，包含准备复验、native worker、完整保存API纯回放与导出。原输入和完整源闭包/026编译归档固定；执行claim拒绝重复执行或覆盖。判定必须同时看到三件不同任务、同盘顺序 LOAD/UNLOAD/HOLD、全部25 received ACK、完整H、最后empty与完整物理审计。缺少任何一项仍是unknown/no-third-witness，而不是从进程exit0推业务成功。

## 解释范围与后续

[39上界原件](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_carrier_bound_002/receipt.json)是零不可达装载的各loader好前缀之和：26=2、49=2、57=2、95=2、136=13、138=15、149=3，其余0。它不含时间、回程、停车阻塞约束，所以不是39件可实现排程。第三次仅尝试把已实证2扩到3，不能声称逼近全流成功。

若第三次在46返空，token的实际所在owner将变为international。将来才可另行预注册由该owner基于真实destination completion/selfcopy和最新domestic FIFO进行第四次跨区供给；离线首个候选可能是95/job3。不能让旧domestic控制器遥控46，也不能因49仍有第二件好前缀就违反same-zone禁令直接再供49。本包不实现这一扩张。

当前选择明确受已观察成功和静态可达性筛查影响。与reuse002的比较应先验证前两次实际API/动作前缀一致，再分别报告共同H28800的全部offered/到达/完成/未完成及第三次轨迹。旧baseline未全部完成，不能把新增一件称为全offered逐件保护；完整保护仍需独立相同输入/权限/信息/预算的对照和所有业务可比终态。任何有限后续失败都必须保留，不通过扩大H或改选成功loader覆盖。

## 准备门（0 native）

`original_low_wip_third_prepare_001` 已归档68个运行Python来源、67个026编译来源，plan SHA256=`2d40bea147cbe63efbeb1bc54d6383ee8a6a8fb3316d07d67da698302a56b1c8`；branch仍为`unknown_unexecuted`。最终第三阶段+原reuse组合97纯测试全部通过：[003 XML](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_third_pure_003.xml)。真实reuse002保存API逐文件哈希，并严格重放到第二次供盘19800；此前第三阶段新增观察数为0。旧002测试XML的9项Windows默认临时目录权限setup错误原样保留，换工作区独立临时目录后重跑003；没有以跳过测试作为通过。

准备门包含新鲜度、第二ACK、真实返空、旧第一次完成不能冒充第二次、不可达头不跳队、拒绝后不重选、所有三次生命周期、额外装载/未完成H/缺HOLD保持unknown、共享600秒和冻结source证据等反例。它不能替代第三次native实际轨迹。
