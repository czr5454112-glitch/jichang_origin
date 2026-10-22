# 需求预测、支持域和模型身份审计

本报告只评价预测层及其与固定分配器的连接。监督校准已经实际拟合，原始负结果和支持域修订均保留；这不是 RL，也尚不等于预测学习产生机场服务增量。没有启动 native，没有读取 TEST。主实验执行状态及预算继续以 campaign 的追加式账本为准。

## 数据、训练与合法信息

`forecast_offline_001` 从 `G05_P2101_C10`、`G08_P2102_C10` 两个已 closed 的 TRAIN 原生过程提取数据。每个父场景在 7200、9000、10800、12600、14400、16200 秒读取实际回调 B1，按 10 个装载站及 1800 秒完整、不重叠窗口形成 60 条标签；合计 120 条。各 owner 预测的同一需求人口只保留一次。标签是实际 `BAG_ARRIVAL` 回执，输入只用于核验已到达业务的身份、站点及时间；未到达 jobs 不作为标签。

每条标签保存预测签发时间、窗口、成熟时间、父谱系和来源摘要。只有窗口完全结束、回执过程成功关闭后才能训练。每个站的倍率为

`clip((实际到达量 + 8) / (B1 期望到达量 + 8), 0.25, 4.0)`。

这是 Gamma 先验约束的 Poisson 暴露率监督估计。参数输入没有盘号、运输订单或系统服务奖励。模型只修改未来新增到达均值，不能更改菜单、库存、在途盘、费用、运输期限或原生权限。它没有状态转移学习、预测动作的延迟强化奖励或策略更新链，因此 `is_RL=false`；旧 C01/C11 action-Q 不是本模型。

`forecast_audit_001/training.json` 独立重读绑定的原生来源、重数实际到达、复核 724 个实际回调的 B1/映射 availability，并重新生成全部 120 行。原校准及支持域模型均与重新拟合结果逐字段完全一致。部署同时检查 B1、映射、箱网格、模型摘要、模型 available 时间和非训练父谱系；`:r0` 与同一父的 `:r1` 不算独立父。availability 是登记的模拟日历坐标，不冒充壁钟上的历史部署时间。

| 身份 | 值 |
| --- | --- |
| B1 参数语义 SHA | `2058378b338e5c3d3e6cdb279405ada63cbb0b7d443484903b5a9d37df9f3934` |
| 固定 loader mapping 语义 SHA | `b1bfa1200d96986c974eb30cb13220a5ab77c2fcdbe3af5344f72313b0f053a7` |
| 原校准模型内部 SHA | `558ae07c50a6eebd2f488a999d06d853cb3bf386b4125806af19c31d9634e90d` |
| 支持域模型内部 SHA | `e06af9778d72153d9372580152bec505cacc36eceb64bfac4ca3b95c775c3074` |
| 支持域模型文件 SHA | `2d1f739e4d84be8b5d4ed54ef67d6b48e88895e16246713604aa7a69587ba1ca` |
| 标签关闭 / 模型可用 epoch seconds | `1793566800 / 1793566801` |

文件 SHA 绑定序列化字节，模型内部 SHA 绑定去除自身摘要后的规范内容，两者不能互换。

## 共同窗口结果和失败诊断

固定 DEV2201 的完整旧 legacy 原生轨迹提供真实到达标签；其旧 actor 未消费这些新预测。因此预测是明确标识的离线重建：公开计划、固定 B1、固定 TRAIN 映射，未读取未来到达作为输入。29 个 origin ×10 个站 ×3 个共同窗口构成同一 870 标签人口。相邻 5/15/30 分钟窗有依赖，合成父场景也共享历史模板；这里不是 870 个独立实机场样本。

| 表示/模型 | 5 分钟 MAE | 15 分钟 MAE | 30 分钟 MAE |
| --- | ---: | ---: | ---: |
| B1-300 | 3.609213 | 6.634240 | 11.740409 |
| 原全天倍率校准 | 3.879282 | 8.163481 | 14.909005 |
| TRAIN 支持域校准 | 3.615157 | 6.574036 | 11.563276 |

原模型仅见 `[7200,18000]`，却把早段 station 倍率 0.697–1.233 用到全天。30 分钟 MAE 在支持段由 3.46238 降至 2.60624，但在 `[18000,36000)` 从 12.70116 增至 17.66681，在后段从 14.82200 增至 18.46582。全日退化不能被早段收益掩盖。

支持域模型只在所有 TRAIN 父的已成熟标签时间窗交集内改变 B1；目前 10 站均为 `[7200,18000]`。跨边界箱按覆盖时长混合，支持域之外逐箱均值精确返回原 B1。参数及边界只由 TRAIN 导出；**选择这一修订方向发生在观察 DEV 退化之后**，所以复用 DEV2201 的改善是开发结果，不是新的独立留出。

箱宽 60/300/600 秒及近细远粗都固定 1800 秒视野。rebin 在分段均匀假设下守恒，不凭空提高时间精度；共同 5/15/30 分钟误差从各自表示重新积分。60/300/近细远粗在对齐共同窗口的误差相同，不说明它们在真实 ETA、箱边界和缺盘峰值上等价。缺失传播；没有联合箱协方差及映射/拟合不确定性时，方差、分位数和校准覆盖均记为不可用，没有把边际区间相加。

## runtime003 外层 hash 与执行预测身份

冻结的 `terminal_flow_runtime_003` source manifest 文件 SHA 是 `1b6e9f81b1e96c0607e1fac21b8b2e15cdd373bdce5e22eab121ba26611136c3`。该版本 RecordingPolicy 先取得 prepared B1 evidence，再替换其中 inner forecast 为 rebin/校准后的需求，但未更新外层 `forecast_sha256`。旧字段仍指向原 prepared provider B1。

`forecast_audit_001/runtime003_recording.json` 审计已关闭 `TF_confirm_003_TF-B1-300_P2101` 的全部 362 个预测记录：362 个 outer SHA 均不同于实际 inner SHA。前 40 个回调进一步从绑定 B1、映射、预加载回执和保存的公开观察独立重建，inner forecast 逐字段精确相同，原 outer SHA 逐个精确对应 provider B1。该发现是证据标识的语义错误，不是 inner 数值受未来标签污染；未改写历史归档。

当前待发布 RecordingPolicy 已保留 `source_forecast_sha256`、重算最终 `forecast_sha256`，并记录 grid/model 转换身份。特征 availability 取 B1、映射、需求模型的最大值；支持域模型从内部 `base_calibration` 取时间。8 个回归验证 B1-60、B1-300、普通校准、支持域校准，且用冻结003的 RecordingPolicy 代换当前 RecordingPolicy 比较，inner 数值及选中动作保持一致。这是对这次元数据修复的局部证明，不是全部发布源码与003的物理等价证明。

之后的发布代码还可能增加供给 cap 等诊断元数据，导致 plan/order ID 改变。完整新旧 source 桥接应比较 canonical action、公开状态、实际请求、回执和物理结果，不能要求所有内部 plan ID 相同。执行 source 身份与发布 source 身份分开记录；不得把修复后 hash 字段倒填到003，也不得拿 provider B1 hash 代表003的最终 actor forecast。

## 同公开观察上的订单诊断

`foundation_airport_terminal_prediction_audit.py same-state` 已提供独立入口。只读取已成功 closed 的 DEV 计划、公开观察、候选菜单及公开模型/支持域合同。先精确复建并核对整个 current-only 菜单，再将 B1-300 和支持域预测器交给同一固定分配器、600 秒代理、60 秒重算周期与同一费用。

该入口比较来源—目的地数量配额、真实首 action、软目标时间，并记录剩余可调总 cap、硬保留、HOLD 和首动作失效原因。它不把预测摘要变化导致的 plan ID 差异算成订单变化。两条件都使用空的额外假设计划状态，观察中已有原生义务保留；离线假设订单不执行，也不传入下一个已保存 C00 状态。因此这是同状态单步机制诊断，不能当成闭环服务因果增量。

旧完整 DEV legacy 没有导出完整 `observations.json.gz`/`decisions.json.gz`，仅控制摘要不足以精确复建同一完整菜单，故不能从它编造订单差异。

新 `TF_bridge_P2201_003_C00_P2201` 成功 closed 到59400后，`forecast_audit_001/same_state_orders.json` 流式读取其支持窗 `[7200,18000)` 的360个公开决策状态并逐一复核菜单。288个没有当前合法转移；72个有合法转移且校准均改变需求均值。其中64个两模型都HOLD，只有1个状态的配额/首动作改变，2个状态的软时间改变。

| 时刻 / owner | B1-300 | 支持域预测器 | 限制与解释 |
| --- | --- | --- | --- |
| 9120 / domestic | HOLD，数量0 | `initial:92:0`，92→95，数量1；精确净代理7.68207 | 菜单8只盘分别合法，但来源57/92/136/138各硬保留1、各cap1，总cap4。预测差异越过同一固定收益阈值；没有改运输费。 |
| 9180 / domestic | 92→95，数量1；target_by9707.857 | 同盘同边数量1；target_by9671.268 | 软目标提前36.589秒；精确净代理3.22580→12.23154。它不代表物理上提前完成。 |

两状态的公开视图各已有2条原生转移账目，其投影义务原样保留。可调供给、硬保留及短时正收益限制解释了为什么72个需求变化只产生1个首动作变化。该例证明预测层确实可能改变固定优化器的可执行输出，但这些离线假设未提交，真实服务增量仍须原生配对。审计输出绑定当时allocation/control文件SHA，包含后加的供给cap诊断元数据；不将其称为003 actor的实际选择。

## P4/P5 的最小合规续行

现有注册来源中没有完整 59400 秒的 closed TRAIN 轨迹。joint TRAIN 最长18000，旧 SPI 最长46920，旧 action 系列最长55920/55800；它们不是完整共同全天支持，父命名空间和预报消费合同也不能无证据混用。需要完整 TRAIN 的目的，是消除早段倍率外推并检验全天映射/累计误差；不能把运行更长本身称为学习增益。

1. 主 runner 先完成已登记配对块。用原总账确认剩余 starts、累计活动时间、证据及磁盘余额；保持单 native runner。新的 TRAIN 支出须从原未启动额度重登记，保留完整后续验证块，不重置预算。
2. 用相同冻结 B1、映射、信息和采样规则，在 TRAIN2101、2102 完整执行到59400并保存实际预测回调、完整到达回执、输入/源码/过程绑定。短 prefix不能直接续作同一原生过程；若物理状态不支持恢复，应新 task 从头运行并重新计费。`training_rows()`已经按实际 closed end自动提取所有完整、不重叠1800秒窗；两父均完整时可得到580行，而不是继续120行。
3. 在读取后续 DEV 标签前，冻结一个简单候选、支持域推导、正则强度、预报窗口及共同指标。先验仍设8、箱宽300、视野1800，分配器、订单时间、原生规则完全固定。完整 TRAIN 并不保证更优；新拟合必须保留原两个候选及其负结果。映射或不确定性改进另立单轴候选，不能与运输成本改动混作预测增益。
4. 先做同公开观察诊断。若需求均值改变而数量/首动作不变，按当前可调cap、FIFO/硬保留、已有承诺、运输 ETA 和服务饱和逐项解释；不以调低运输费强造学习增量。无可行差异时，在 TRAIN 上改进需求或映射并冻结新候选，再执行完整配对，而不是宣称工程测试完成即P4完成。
5. 在新、未用于本候选诊断的 DEV 父场景上执行 B1-300/候选的完整配对块，同时报告共同窗口预测误差、真正接受/接收订单差异和完整人口服务变化。DEV2201已参与支持域设计，不能作为独立确认；至少保留一个此前未查看结果的开发父作为下一次确认。按现有门槛检查准时量、逾期未完成、物理失败和完整父cost，不仅看MAE。
6. 当前学习损失只是实际到达误差，不用服务作为参数更新反馈。如果改为服务反馈，必须另登记可运行训练合同，在与参数拟合父谱系隔离的TRAIN父上重新运行固定 ICS，记录预测—订单—服务—更新链；不能关闭现有同父谱系部署保护来伪造留出。只有满足真实多步决策/奖励合同才研究RL，否则继续准确称为监督预测。
7. source/model/support/DEV选择及服务门槛满足后，按注册才可解锁TEST并执行完整配对父块。预算不足时缩小完整配对块、保留弱势结果和精确续行计划；不能从本报告推导已经通过P4、正式TEST、R1组合或托盘节省。

## 复算入口

以下命令在研究工作树根目录执行，输出文件必须未存在；均不启动 native。

```powershell
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_prediction_audit model --original outputs/experiments/g31_ics_terminal_flow_20261021/forecast_offline_001 --supported outputs/experiments/g31_ics_terminal_flow_20261021/forecast_support_001 --output outputs/forecast_training_audit_fresh.json
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_prediction_audit recording --run outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/TF_confirm_003_TF-B1-300_P2101 --output outputs/forecast_recording_audit_fresh.json
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_prediction_audit same-state --run outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/TF_bridge_P2201_003_C00_P2201 --model outputs/experiments/g31_ics_terminal_flow_20261021/forecast_support_001/model.json --output outputs/forecast_same_state_orders_fresh.json
```

新增完整TRAIN拟合入口：

```powershell
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_full_training --train-runs <closed_TRAIN2101_run_directory> <closed_TRAIN2102_run_directory> --output outputs/experiments/g31_ics_terminal_flow_20261021/forecast_full_train_001
```

必须等待两条同source、同B1/映射、完整59400秒的TF-B1-300原生过程关闭；短窗、DEV/TEST、重复谱系、未成熟标签、不同source、不同映射或已校准actor的预测均拒绝。默认模型available为最晚TRAIN标签关闭+1秒；可用 `--model-available-at <epoch_seconds>` 指定更晚的模拟日历时间。输出 `model.json`、580行 `training_rows.json.gz`、绑定原生输入/回执/决策/source/model可用性和拟合源码的 `provenance.json`。候选仍用现有支持域模型schema，campaign直接用 `--demand-model` 绑定这个新文件；不覆盖原短窗模型。

## freeze004前的接口与留出复核

复核未发现需要改变actor预测数值的泄漏或接口错误。runtime传入的是相对物理 `now`，校准器只加一次forecast中的日历起点；B1、映射与校准可用时间均在同一epoch坐标上比较。TRAIN2101/2102的完整结束分别为1793521800、1793608200，因此r0完整模型默认available应为1793608201；DEV2201首回调为1796925600。这个时间顺序成立，但模拟日期不能充当实际部署历史。若显式指定更晚available，部署仍须逐回调验证，不能仅因model文件存在就认为当时可用。

完整模型依然只是站点倍率的监督拟合；增加全时段标签并没有自动产生时段特征、改良映射、可信区间或RL。580个窗并非580个独立真实机场样本。固定的先验8、clip范围、300秒网格与窗口不根据DEV误差改选；失败和退化继续保留。真实原生配对还必须使用同source、B1、映射、分配器、订单与控制合同，只有demand_model可以不同；离线共同误差无法替代这个检查。

完整模型产生后，可独立运行以下DEV报告，actor无须修改：

```powershell
python -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_forecast_holdout --run outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/TF_bridge_P2201_003_C00_P2201 --model outputs/experiments/g31_ics_terminal_flow_20261021/forecast_full_train_001/model.json --output outputs/experiments/g31_ics_terminal_flow_20261021/forecast_full_train_DEV2201_001
```

此入口先验证冻结模型，再流式核对实际保存C00公开观察与decision摘要，以实际startup preload receipt复建同一B1-300和候选的29个预登记时刻；owner重复人口去重后才打开成熟DEV到达回执并计算870个共同标签。重建预测明确设置 `actual_callback_consumption=false`，不会把C00没消费过的预测冒充实际actor回调。报告含5/15/30分钟MAE、RMSE、bias及早/中/晚三个origin分段，调用链没有fit。它不会据DEV指标选参数或输出promotion。可以将`--run`改为之后完整closed的新DEV C00；曾用于诊断的DEV2201仍不算独立确认。

报告分别绑定原生数据source和当前离线producer源码；003 C00归档与之后004训练模型一起做离线需求评分，不等同于003/004原生策略公平配对。当前入口以及完整TRAIN拟合入口均在开始前绑定producer文件并在结束核验未变，避免运行中编辑造成源码身份误记。首次报告入口验证`forecast_saved_public_dev_001`遇到这类报告源码编辑，已保留并追加独立invalidation，不用作冻结发布证据；稳定源码的复算另存002。训练和评价活动时间由外层budget runner登记，API本身不新增native支出。

`forecast_saved_public_dev_002` 已实际完成：以仍冻结的120窗短TRAIN支持域模型验证报告入口，复用003 closed C00的29个真实保存origin，870标签和两模型5/15/30分钟MAE与前述开发评价逐值相同，producer结束一致检查通过。它验证保存公共观察→合法预测→成熟评分的完整离线路径，**不是尚未拟合的580窗完整TRAIN模型结果**。

相关预测、prepared provider、记录与campaign回归共126项通过，JUnit为 `outputs/forecast_final_audit_tests_001.xml`；stream/物理数量诊断15项也通过。随后新增的完整TRAIN16项、DEV报告9项共25项通过，最新JUnit为 `outputs/forecast_holdout_tests_005.xml`，包含运行中producer变动拒绝测试。测试与离线复算不占native starts，不替代完整服务验证。
