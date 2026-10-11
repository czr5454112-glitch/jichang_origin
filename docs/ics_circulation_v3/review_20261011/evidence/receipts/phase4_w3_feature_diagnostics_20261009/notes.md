# 旧 paired 学习负结果：可观察角色与特征诊断

这是对已保存开发结果的只读事后诊断，不拟合模型、不生成标签、不重跑部署。全部输入及实际依赖源码的前后 SHA256 记录在 `summary.json`；本次均未变化。既有 32 个 episode、192 袋和 6 袋未完成保留，完成量仍为 186/192。

## 可复验的机制证据

旧 12 个标签 checkpoint 全在 S，角色全是起点，任务都是 S→G；正常候选共 48 行。旧部署实际有 373 次路由调用：226 次起点、95 次中间节点、52 次已在目的地。按节点和角色细分为 S/起点 114、B/起点 112、S/中间 43、G/中间 23、C/中间 18、B/中间 11、C/目的地 45、G/目的地 7。

在 52 次已到目的地调用中，有 50 次存在通过原授权器的零边原地卸载候选，却选择了离开目的地的路线，并在保存的物理 `depart` 事件中实际驶离。这涉及 14 个 episode；6 个未完成 episode 全在其中。这是实际行为证据，不是仅查看模型分数或提案。它不等于计算了“改为立即卸载”的整段反事实收益，也不证明它解释全部成本退化。

具体例子是 `stream_L2_D3_slack0 / residual_seed17`：t7 的 `need:0` 已在 C，仍选择 C→S→X→G→C；其后任务也重复发生。该 episode 成本 77，timed 为 14.8；前者 tray_wait=25、nonprotected_tardiness=40、empty_distance=20、terminal_backlog=1。逐调用记录、可选动作、特征、目的地驶离物理事件及各折训练邻居见 `deployment_diagnostics.json`。

## 不能从数据推出的结论

48 个候选的旧 23 特征只有 32 个不同向量，形成 16 组精确重复；将参考候选特征一并加入成对输入，仍是 32 个不同键。4 组有不同的经验标签均值，但差值只为独立 Monte Carlo 差值标准误的约 0.13–1.81 倍，因此不能据此声称已经证明结构性不可辨或不可约误差。原始成对标签与标准误比较见 `feature_collisions.json`。

每条部署记录的最近邻仅在对应模型的三条训练 stream 内寻找，按训练折自身尺度标准化；同时给出同节点、同角色、同任务 OD 邻居。旧标签没有中间/目的地角色，所以这 147 次调用没有同角色训练邻居。邻居的解析误差不是当前部署状态的标签或 regret；没有保存这些部署状态的共同未来标签，因此相应字段明确为空。标签集 96 次既有 held-out 决策的 chosen regret 和 48 行解析误差则按原结果保存于 `label_role_errors.json`，没有扩充经验最优候选域。

最小的直接支持假设是加入“当前节点是否为本任务目的地”和“本次真实安全前缀是否完成交付”，并采集策略实际访问的起点、中间、目的地角色。距离、时间和资源余量等其他物理特征可以作为预声明假设检验，但这里没有证明它们必要，也没有证明新特征会改善完整 episode。旧 23 字段已经可能间接编码部分关系；角色覆盖不足、固定继续策略目标与 learned 部署状态变化仍需分别检验。

所有任务元数据仅在路由记录的 `visible_bag_ids` 含该 ID 且 arrival≤当前时刻后用于诊断；未观察事件带不作为特征输入。此处的完整事件文件仅供离线查回已经观察任务的不可变 origin/destination。安全前缀使用原授权器的纯投射函数，未用简化重建状态作授权或仿真。

## 复验

```powershell
python -m pytest tests/test_ics_circulation_v3_feature_diagnostics.py -q --basetemp .tmp/ics_v3_feature_diagnostics_tests_new
python -m scripts.experiments.ics_circulation_v3.run_feature_diagnostics --output outputs/experiments/ics_circulation_v3/feature_diagnostics_new
```

专项测试 5 项通过，分析运行约 2.24 秒。输出目录非空会拒绝覆盖。四条合成开发流、重复候选及多个时刻不是独立机场日，也不是新确认数据。本诊断不修改旧结果、C++ 或 Git。
