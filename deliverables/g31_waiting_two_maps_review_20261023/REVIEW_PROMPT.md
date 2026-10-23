# GPTPro 审阅入口

请审阅本分支相对 `9f23c25a631786ad4c1f47c442d72dcfb3ac098f` 的增量，实现和证据以仓库为准。先读 [README](README.md)，再读 [详细审阅清单](../../docs/g31_ics_circulation/PRO_REVIEW_CHECKLIST_20261023.md)、[候选实现](../../docs/g31_ics_circulation/S4_WAIT_ESTIMATOR_CANDIDATE_20261023.md) 和 [原生规则审计](../../docs/g31_ics_circulation/FENG_NATIVE_WAITING_RULES_AUDIT_20261023.md)。

任务范围：保留成熟 G31/S4/J2/PIBT，双方不增加线路容量，不跑空托盘；默认仍是 legacy，仅把 eta_calendar/eta_flow 作为可关闭评分候选。旧 G31 原已按到达 ETA 查询日历，正式邻居日历可见性也原已开启，不要把这两点当作本轮新增。

请独立检查以下问题，并以具体文件/代码/证据支持结论：

1. 新模式是否只改变评分，真实节点服务、恒速旅行、J2 授权和 PIBT 回滚是否保持？legacy 关闭等价、六组新回归及 checkpoint 状态覆盖是否充分？
2. Q 是服务后队列，预测是否分离日历等待和后服务等待、避免重复 Q+I？流量样本是否因果、是否遗漏临近 ETA 才完成的流入、是否出现较大尾部误差？已提交访问的 MAE/RMSE 不代表所有候选分数校准。
3. 每图主分母是否完整 43,603 段，Java generator release 是否与成功规划时刻分开？相同释放对照是否只改 release、保留身份/OD/截止时间/执行选项？
4. map2 与南宁分别是否仍优于原 Java，候选相对旧 S4 的收益或退化有多少？请同时看均值、尾部、超期和计算边界，不把不同计时范围的墙钟当 CPU 加速比。
5. 两图需求来自同一原始任务的投影，参数没有按 map2 调整；请按地图分别判定迁移表现，不推断独立客流采样意义或普遍最优。
6. Java 闭区间/G31 容差半开、Java 秒级报告/G31 连续事件、完整路线/逐跳策略等差异仍保留。EBS 因果异常没有被单方修正；不要把违规链的观察端到端值称为物理有效业务链。

可以运行 `python scripts/experiments/g31_feng_alignment/build_review_bundle.py verify` 从两份 ZIP 的全量账本重新计算各七臂指标。完整 native_payload 大文件未提供，只有 SHA/大小和明确缺项清单；不能声称已检查未提供的事件或全部原生细节。本地论文 PDF 仅有原件核验记录，没有包含原文。

请输出：可确认事实；具体代码或比较口径问题（按重要程度）；每图候选取舍；下一步最小实验。不需要为本轮重建托盘几何/驱动系统，不要自动启用新默认或将发布理解为已合并。
