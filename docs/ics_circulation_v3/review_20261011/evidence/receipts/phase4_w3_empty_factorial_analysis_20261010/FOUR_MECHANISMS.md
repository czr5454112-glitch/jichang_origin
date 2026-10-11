# 四条差异流的已核对物理机制

前置完整分母是144次、36条流×4格，分析见FACTORIAL_RESULTS.md。这里解释原new比legacy损失的四条流，不能把四例当总体分母或独立确认。four_mechanism_traces.json按原件SHA提取四格全部t≤50慢层决策及t≤56物理trace；不重跑、不调参。

**选择规则而非预算。** timed/incumbent与earliest/incumbent在全部36条流的完整端点、route history和slow动作都一致；earliest/fewest与旧legacy也在全部36条流这三类物理记录完全一致。各格最大7动作、depth2=0、所有省略=0，故这是平局机制定位，并非扩大搜索的收益。

**s1_t1与s1_t5各恢复6成本、1准时。** t24/t26首次分歧，两tie格的snapshot SHA、候选完整顺序和proxy数值一致：B的loaded盘→C，以及no-transfer，均3.2；原incumbent承诺loaded盘，fewest选择no-transfer。同tickreactive从G派donor盘到C（同为2tick），当前任务完成不变但后续盘身份交换。t34后B有两盘，能向S预调；fewest/timed在t34再等，t36把donor送往S39可用；fewest/earliest在t34发出，S37可用。二者均在真实S袋t40到达前备盘，t40装载/t45完成；原incumbent直到t43装载/t48完成。wait−3、tardy−3、empty不变。no-transfer并不代表盘物理不移动，它允许同tickreactive以另一盘执行。

**s0_t5恢复2.1成本、1准时。** t34同state/pool，timed把delayed/no-transfer/early都评1.4；fewest在t34和t36等待，到t38 no-transfer升2.4，选CS38/SX39–41/XB41–42。该流真实逆向G→S袋t42才到，共享SX已经释放，S盘可由SX/XG回G46；袋t50完成，deadline50。原incumbent从t34预承诺CS40/SX41–43，真实t42到达仍挡SX，S盘绕SY/YG到G47，袋t51完成。成本恢复wait1+tardy1+加权empty0.1。earliest/fewest则t34直接发出（early1.4/no-transfer5.4），物理与legacy相同。

**s2_t8揭示残留差额。** timed/fewest在t0曾等一轮，但t14已与其他格重新达到完全相同snapshot SHA；t34再次同state/pool，排除把早期轨迹差异误当本次机制。timed预测delayed/no-transfer/early均2.6，fewest在t34/t36连续等待，t38才选CS38/SX39–43/XB43–44；no-transfer此时升5.6。真实逆向袋t40到G，SX仍在占用，S盘选SY40–44/YG44–47，t47装载、t51完成，deadline50。earliest/fewest在t34预测early2.6、no-transfer8.6，按physical key选CS34/SX35–39/XB39–40，t40实际逆向到达时S盘可走SX40–44/XG44–46，t46装载、t50完成。差额仍为wait1+tardy1+weighted empty0.1=2.1。

这里的timed proxy假设未来周期慢层继续原greedy；真实执行却在后续周期继续fewest优化器。因此它把“现在等、以后greedy补调”评为同分，实际反复选择等待会多推迟若干轮。这是已声明的one-step base-continuation与重复部署差别，不是递归deployment-matched MPC，也没有单调改善保证。s0和s2的相反时机后果说明不能把等待规则泛化为无条件更好。

完整144的同分修改没有新增成本回归，但这只是在同一开发族上的事实。保留原强对照，后续不因这四例加权或挑选种子；公开预测情景压力试验是另一个已预声明的开发问题，额外计算与未校准prior必须单独报告。
