# 站点图配给、空盘订单与时间尺度实验

本轮依据用户给定任务书实现需求预测 → 站点图整数配给 → 原生逐盘执行。研究分支仍为 `codex/g31-ics-v3-circulation`，起点 `c7121c12b3d59a1d6fcd4919bb13bb86aa2ff91f`；原工作树的 C++ 修改未动。下面区分已实现机制、实际实验与未满足的研究门槛。

## 实现合同

| 模块 | 职责及限制 |
| --- | --- |
| `foundation_airport_terminal_graph.py` | 保留真实站点；复用 PublicTravel 的有向路径与服务时间；保存路径见证、公开关闭版本和接收空间覆盖。未知空间不填零库存；宏观边不独占物理通道容量。 |
| `foundation_airport_transport_allocation.py` | 真 tray 节点、来源总保留上限、接收上限、ordinary return 受保护分层及可选 HOLD。负费用残差最小费用流只精确求解声明的可分离代理；凸/凹修正幅度有记录。 |
| `foundation_airport_transport_control.py` | 使用原完整当前菜单；计划按 tray/source/destination 重新绑定；首动作按精确 ETA 的短时收益核验。有 ordinary 时保留类别；没有正可选收益则 HOLD。重新排序后另存真实首动作的派出序列。 |
| `foundation_airport_transport_orders.py` | 普通回流、真实需求、必要腾位和预测预置共用实体订单/接收占位账本。pending 只去重，不增加库存；已提交请求不随预测或计划过期释放；新接收快照覆盖旧义务，包括盘已再次装载的情况。 |
| `foundation_airport_terminal_forecast.py` | 冻结 B1 的 60/300/600 秒和近细远粗表示；总量守恒，partial bins 和缺失传播显式；共同窗口只从该表示计算。没有协方差时不相加区间上下界。 |
| `foundation_airport_terminal_predictor*.py` | 仅实际 TRAIN 到达标签成熟后拟合监督 Poisson 校准；没有 action-Q 或调拨输出。支持域修订仅在 TRAIN 实际覆盖的时间范围内改变 B1。 |
| `foundation_airport_transport_campaign.py` | 同一旧预算下冻结、执行、恢复整块对照；失败/未启动保留分母；只有输入、原生、源码、控制合同等价才配对。 |
| `foundation_airport_transport_evidence.py` / `foundation_airport_terminal_flow_audit.py` | TRAIN 时间尺度、全链订单审计、实际回执、分箱动作差异及旧基线等价核对。 |

协调层准确称为**上层公开信息协调、来源 owner 确认、原生去中心化执行**。共享账本只保存合法 owner 观察和自身发单事实；它没有远端托盘提交权限，接收准入仍由原生协议完成。

首版参数固定为：1800 秒预测视野、600 秒单次用盘代理、`committed_only`、60 秒控制及 owner 派发槽、2 秒命令延迟。边际共同参考时刻为当前 +2 秒；运输费和超出参考时刻的延迟近似权重均为 0.01 bag-second/second。首动作精确复核只扣运输费，时序影响已在精确事件代理中计算，不重复扣延迟近似。原生出发 expiry 保留，`target_by` 为上层软目标，没有给业务 jobs 插入空盘伪行李。

规划重算独立比较 60 与 300 秒；库存、等待、合法菜单、公开故障、承诺/接收占位变化使缓存失效。缓存建议没有提交权，恢复后仍查当前菜单和原配额。每 owner/tick 一次新可选提交，异常和拒绝仍消费本次机会；重试使用同一个原生 request_id。

## 已有数据与预测负结果

启动差异见 [STARTUP_DELTA_TERMINAL_FLOW.md](STARTUP_DELTA_TERMINAL_FLOW.md)。旧 runner 已退出；第二旧 bridge 的 `unknown_missing_export` 保留，不推测其为 OOM 或超时。最初预算为 10/160 次、1450.03634/172800 秒，未另开预算。旧未启动 action-Q 阶段不再自动派发，旧注册和全部原始记录保留。

[TRAIN 时间尺度](TERMINAL_FLOW_TRAIN_EVIDENCE.md)显示多数合法机会存在多源多目标，但这不证明所有目标都有正边际价值。实际转运长尾与当前静态 ETA 的差别保留；短时代理不模拟未知循环。

`forecast_offline_001` 用两个 TRAIN 父场景的 120 个成熟、非重叠站点窗拟合，并在完整 DEV2201 上比较同一 870 个标签。B1 的 5/15/30 分钟 MAE 为 3.60921/6.63424/11.74041；原校准变为 3.87928/8.16348/14.90900，明确退化。诊断发现只覆盖前 18000 秒的倍率被错误外推到全天。

`forecast_support_001` 保留原负结果，仅用 TRAIN 支持窗交集 `[7200,18000]` 校准，其余返回 B1。相同 DEV 指标为 3.61516/6.57404/11.56328，15/30 分钟有改善而 5 分钟略差。这是观察 DEV 失败后的修订，不能称为独立留出结论。该次支持域诊断时，尚无已登记 campaign 中完整 59400 秒的 closed TRAIN 轨迹；新增完整TRAIN按005工作流另行执行，未读取 TEST。真正 RL 需求预测为 `not_implemented`，监督校准不改名为 RL。

## 实际原生执行

`terminal_flow_runtime_002` 的五组短程门禁已全部到达 18000 秒，输入固定 28506 件计划业务、22 盘；该窗口实际只到达部分人口。新 C00 与旧 G03 的全部 360 个轨迹动作、请求/回复、业务/盘/转移/运输段和回执等价，总积压积分同为 2316050.326900999 bag-seconds。审计文件为 `gate002_C00_baseline_equivalence_001.json`。

TF-B1-60 的五个可选计划条目均实际提交、接受，其中三条在短窗内接收。例：8400 秒的 24→26，精确短时净收益代理 37.9588；9060 秒的 134→95，净代理 2.7049。它们证明执行链存在，代理数值不等于真实机场服务收益。当前短窗 60/300 的总积压指标相同；完整服务、逐件损害、学习增量和 R1 组合需要各自证据。

runtime003 再将原有真实需求/必要腾位的元数据纳入同一订单账本，并接入支持域预测候选。其确认块与后续完整窗口的状态以追加式 ledger、各场 receipt、独立审计及最终结果表为准，不能从本段文字推断已经运行。

## 接收时间、旧快照和历史请求修复

后续纯状态复核发现，消息仍在有效期内不表示它晚于某次接收：时刻 60 仍可合法读到时刻 2 的快照，而托盘在时刻 30 已接收。旧订单账本可能据旧源端身份释放目标占位；sender 自己的投影器也可能把旧目标身份当作更新接收的覆盖证据。原生账本保留历史请求，同一盘的旧 received 与更新 accepted 还可能错误争用同一个供给身份。这些是通过真实 PreparedCurrent/PreparedProjection 复现的风险案例，尚未被宣称为既有原生负结果的实际原因。

修复要求快照时间支配对应接收或发单时间；旧身份仍参与快照计数一致性验证，但不能同时充当现存盘和更新接收供给。更新的已确认承诺可替代同盘历史 received，pending 不能替代。所有方法共用这个投影修复，新的比较必须同源；不能把修复收益归给某一箱宽或学习模型。诊断、合法公开输入、修复前后结果及原测试字节见 `outputs/experiments/g31_ics_terminal_flow_20261021/claim_capture_fix005_001/DIAGNOSIS.md`。

原冻结003运行保持不变；004工作流已在派发前由监督者撤销，原生启动为0，注册、源码及停止记录保留。修复冻结为 `terminal_flow_runtime_005`，source manifest SHA256 为 `22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef`；894个源码文件的工作副本和冻结副本逐个相符，扩大回归462项通过、0失败/错误/跳过（63.594秒）。测试不是原生服务收益证据。

`workflow_005/registration.json` 固定32次后继启动：短导出等价2、完整TRAIN2、四DEV上的C00/C10/TF-current/TF-B1-60共16、300秒箱4、300秒重算4、固定TRAIN校准模型4。计划仍使用原预算，不包括TEST或R1。注册SHA256为 `1509684b0eaa8433795343d508142654f90927ef70553783c272f343205aa30d`。本文此处记录的是执行注册，实际完成与否须看各receipt及工作流completion；原始004驱动代码经验证后原字节复用，注册005决定实际source、阶段和父场景。

## 文献与贡献边界

GRAND 已由 RL 输出聚合区域目标分布，再用运输优化和局部匹配分配实际智能体；本实现不声称首次组合学习、图聚合和 MCF。此处学习接口严格输出外生需求，真实 tray 资格、owner 提交槽、承诺去重和软到达目标是 ICS 适配。[GRAND V–VI](https://arxiv.org/html/2512.03194v3)

预测需求与滚动运输优化、时间展开及第一时段任务下发已有直接先例；本轮没有继承其交通假设下的完整最优性或整数性结论。[Iglesias 等 III](https://arxiv.org/html/1709.07032)

LaCAM 的高层是所有智能体位置序列，不能把这里的站点图称为 LaCAM 或宣称继承它的完备性。[LaCAM 原论文](https://arxiv.org/abs/2211.13432)

## 可复跑入口

以下均在研究工作树根目录使用本地 `C:/PROGRAMING/python3.11.9/python.exe`，新输出目录须未存在。状态与预算是实测动态量。

```powershell
python -m scripts.experiments.g31_ics_circulation.foundation_airport_transport_campaign status
python -m scripts.experiments.g31_ics_circulation.foundation_airport_transport_campaign run-block outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/confirm_003/block.json
python -m scripts.experiments.g31_ics_circulation.foundation_airport_transport_campaign evaluate outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/gate_002/block.json --output outputs/terminal_flow_gate_evaluation_fresh.json
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_predictor_diagnostics --source outputs/experiments/g31_ics_terminal_flow_20261021/forecast_offline_001 --output outputs/terminal_flow_forecast_diagnostics_fresh
```

`run-block`复用已完成且 plan SHA 匹配的 receipt；有活动 runner 或未结清 native 时拒绝重复启动。物理检查点不支持恢复为原 prefix；重跑必须登记新 task 并再次计费。没有合并主分支、没有修改原生 G31/FIFO/容量/盘数或开放 TEST。

## 005实际短门禁与继续执行

2026-10-21本地20:41:45，旧003四组完整闭合后，监督者自动启动005。C00与TF-B1-300两场18000秒短门禁均正式closed，分别与旧002 C00、旧003 TF300通过全部16项等价检查：公共观察摘要、规范动作、原生状态摘要、请求payload/回复/时间、完整physical字段与成本均一致。精确报告为 `workflow_005/export_equivalence_C00.json` 和 `export_equivalence_TF-B1-300.json`。这是限定父场景/窗口等价，不证明不同source普遍可互换。

两父完整TRAIN现均正式closed，终点59400、每场1742次回调；P2101/P2102的进程墙钟分别为2082.734/1887.609秒，峰值内存分别为14,485,458,944/14,478,540,800字节。监督Poisson校准实际使用580条成熟TRAIN标签（两父各29个非重叠窗×10站），支持范围为[7200,59400]；未用DEV/TEST拟合。模型文件SHA256为 `c2d00b588272e0df52e672c607983df6b9b43ff7c761084eba4f044dc8f4834d`，内部模型身份为 `87ffe492603d71e65b0563f81ecaf69047a75c413f68cfdec65e0d4f76c9fc36`，两者含义不同。

原账本中的拟合区间为2026-10-21T13:51:50.117514Z至13:52:06.344847Z，实际计费16.227333秒、原生启动0次。`workflow_005/training_fit_receipt.json` SHA256为 `799c7eaf9c9bee9549eec03cf2bdcfd240bbe88f317a5e35ea1fd3c015e46f83`，记录模型、训练行及来源绑定。截至2026-10-22北京时间14:18，source005登记的32次原生运行和后续9项离线任务均已闭合。四DEV七方法主比较、强基线补审、统一账本、完整分箱敏感性及四父预测留出结果见[完整source005结果](TERMINAL_FLOW_FULL_SOURCE005_COMPARISON.md)。预测误差改善但主服务门槛未通过；原生completion、审计完成与服务晋级分别记录。因600秒分箱离线动作确有差异，另登记四父原生补充，仍使用source005和原预算；四父原生及8组逐袋补充审计现已完成，600秒分箱未获得服务增益。更长库存视野诊断经用户指示安全中止，候选副本从未激活。最终停止状态与原因分析见 [GPT Pro交接](TERMINAL_FLOW_GPT_PRO_HANDOFF_20261022.md)。
