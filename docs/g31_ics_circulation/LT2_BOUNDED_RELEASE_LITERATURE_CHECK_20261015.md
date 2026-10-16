# 有界供盘与联合模型的文献核对

2026-10-15；用于约束当前重复供盘实验的解释与下一步设计。没有因此改变原图、FIFO、22盘、全部28506任务或验收标准。

## 本次实际读取

1. Spearman、Zazanis，1992，*Push and Pull Production Systems: Issues and Comparisons*，Operations Research 40(3):521–532，DOI 10.1287/opre.40.3.521。本次读取[出版社元数据和摘要](https://pubsonline.informs.org/doi/abs/10.1287/opre.40.3.521)，没有读到全文。摘要研究有界WIP、拥堵与推拉混合控制，并在所分析模型中提供支持；这不证明本图单盘策略最优或无死锁。
2. Zeinaly、De Schutter、Hellendoorn，2015，*An Integrated Model Predictive Scheme for Baggage-Handling Systems: Routing, Line Balancing, and Empty-Cart Management*，IEEE TCST 23(4):1536–1545，DOI 10.1109/TCST.2014.2363135。本次重读[作者公开全文](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf)摘要、引言及§II.A；此文已经在既有创新账中。其联合MPC包括路由、线平衡和空车管理；§II.A采用连续车流近似，假设目的处行李队列可忽略，并把旅行时间离散化。这些条件不同于当前逐盘FIFO和实际ACK模型，不能把它的流量解直接当合法原生命令或逐件保护证明。
3. Spearman、Woodruff、Hopp，1990，*CONWIP: a pull alternative to kanban*，DOI 10.1080/00207549008942761，检索得到书目信息；[出版社页面](https://www.tandfonline.com/doi/abs/10.1080/00207549008942761)本次返回403。未将搜索摘要当全文审阅，也未依此增加数值假设。

## 对当前实现的具体含义（本项目推论）

- 把“实际返空后才允许下一次供给”作为一个保守基线有研究依据，但有界在制数量不是创新主张。现有同盘三次完成是本项目原生证据；文献不能替代它。
- cap3与cap8两臂始终只有同一个循环token。这里的3/8是累计供给次数上限，**不是**在制盘数量的3对8比较；试验检验重复生命周期与跨owner继续能力，不估计最佳WIP水平。
- 本地真实UNLOAD、完成HOLD后的empty、原生self-copy、peer最新FIFO和已交付ACK构成实施条件。不能用“拉式”名义跳过不可达FIFO头、删任务、增盘或提前释放未完成载荷。
- 上层连续流、静态最短路或有限域预测只能提议动作。实际wire时刻权限、dispatch评分、容量/FIFO与接收端复验仍由原生语义约束；模型必须允许prefer被拒绝或native_default选择相同边。
- 未来增加并行循环盘之前，应另立同分母试验并检查停车占位、Storage等待和普通坐标搜索基线。当前cap3/cap8不能证明并发规模化，也不能拼接有限矩阵收益宣称联合创新。

## 已知本地反例与实验边界

原全天1×保存审计为0完成；有限低WIP第三门则完成job2/6/8。它们策略与作用域不同，不能据此直接给出逐件保护结论。源26在两件后下一FIFO头job14不可达，因此通用规则必须保留该头并从真正已交付的其他origin头中选择；不能按历史成功loader重复投盘。三个整体目标仍未闭合。

对应设计：[通用重复供盘](LT2_REPEATING_LOW_WIP_POLICY_DESIGN_20261015.md)。对应实际证据：[第三门独立核验](../../outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_third_independent_actual_review_001.json)、[192分支机制诊断](../../outputs/experiments/g31_ics_lt2_sustained_20261014/native_preference_matrix_native_001_mechanism_diagnosis.json)。
