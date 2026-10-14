# Round11：显式投射运行与完整第一小时对照

2026-10-11，在任何Round11窗口运行前固定。全部属于同源研究代理开发，不是新独立运营日；不提交/推送，不改用户C++。

## 研究问题与不变量

将Round10完整父航班投射通过独立、可拒绝篡改的运行适配接入共同物理引擎。原BusinessWorkload、原final、raw/canonical、原44负结果保持。投射不是算法改善或真实机场分配声明；既有SHA排名与salt不根据本轮结果修改。

从完整原28506袋验证并构造完整投射后，仍按精确第一到达秒起3600秒右开窗选全部44袋，不先按窗口重算父航班分配。新旧全部origin、arrival、STD、deadline、protected、release、old_segments、ID和11初盘不变；仅显式投射格使用声明的新final。完整父组映射由上一轮sealed合同/内容SHA固定。未来完整映射只在环境/实验来源账，policy只读实际已观察任务。

## 固定4部署

- original与projected各h80/h21600，共4格；原固定FIFO、reactive空盘、whole_route、原node/edge容量、同盘库位及unload1s保持。
- 原runtime默认实际请求K1，合同candidate_count4；每query10000逻辑work、无wall deadline、isolated_replay_v1。不可加盘/删袋/改保护/延后deadline/重选salt。
- 每格epoch0真实运行，按60tick外层采集；physics上限600 CPU秒/900wall秒，chunk结束检查，实际超界如实记录。尾界max原44deadline+3600=28500；仅全部44已到且完成、盘/路线/空盘义务排空时才记transport_drained。其他停止均删失。
- 保存10080、11760、24180、28500相同时刻原件（若达到），每600tick检查点、最终检查点、逐query以及完整最终事件/任务/成本；时间提前排空时保留真实停止，不伪造未运行matched值。
- original新部署用于检测适配新增是否改变旧行为；与Round10同tick结果按确定物理字段比较，计时另列。投射格与原格比较仅为输入结构研究。不同停止时刻J不作质量或速度结论。
- 任何后续诊断/续跑/策略变体须另行声明且单列资源，不能改写本4格或补成原600预算内结果。

## 审核与资源

先完成作者和独立对抗测试、冻结生产源码再部署；全ICS回归及普通行为桥独立执行。全部来源先通过原loader重读raw/canonical，再固定外部投射合同和已封content SHA校验。原/投射完整字段审计、实际占用和同盘释放/卸载、未完成及不可达全分母、future信息与预算均复核。

每独立进程保存源前后SHA、CPU/wall、内存、raw及异常。parent包含嵌套输入/pytest/physics；只另加独立child，不重复加嵌套。已明确物理分支、独立query、测试未知次数不同口径。编辑/阅读/网页查阅/最后辅助及未覆盖进口计时仍未知；失败目录不覆盖。

另行并行研究入口头距、不可撤销尾窗和参考/W2贯通；本4部署不混入未接入的headway功能。
