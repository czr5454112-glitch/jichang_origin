# G4IRSF30：3× 固定窗口实验产生的新想法与后续边界

## 1. 扩流单位继续保持为“完整航班”

3× 不需要新的订单生成器。沿同一 `(end, Unloader)` 航班序列，在相邻 STD 的三分之一、三分之二处放入两个完整 manifest，就能提高到达密度，同时保持每件行李的 slack、直达/EBS 分类和多段生命周期。

这一方法可以自然推广到其他整数倍率：先决定每个原航班间隔内的插班分数，再复制完整 manifest。不要从 canonical segment 倒推订单，也不要把同一个 segment 文件平移若干毫秒。

## 2. Own-source fixed-horizon capacity 是独立问题，不是 exact-release 的降级替身

当集中式 HCA* 在固定窗口内不能释放全部任务时，继续要求逐 segment exact-release 会把 Source admission 本身的容量瓶颈排除在外。G30 改为让 HCA* 和 S4 从同一 scheduled arrivals 各自运行 Source，再比较固定 85,518 分母的最终完成数。

这个指标回答的是“完整框架在论文固定业务日内能处理多少订单”，不是“相同注入以后谁的路由更快”。两种问题都合理，但不能混写：

- exact-release 适合隔离 Route/Merge；
- own-source fixed-horizon 适合端到端容量；
- G30 的主结论属于后者，因此必须持续标注 `NOT_RELEASE_PAIRED` 和 `NOT_TIMING_PAIRED`。

## 3. 四个计数已经足够定位第一层瓶颈

HCA aggregate 已保留每个重复的 released、planned、completed segment 和 completed raw bag 数量。对当前短期目标，先看这四个边界即可：

- released 少：Source admission 或上游注入是首要限制；
- released 与 planned 有差：集中规划阶段积压；
- planned 与 completed segment 有差：网络/设备服务积压；
- segment completion 与 raw-bag completion 有差：多段生命周期尾部未闭合。

先用计数缩小问题，再读取已有 wait 分解；无需增加新的全局追踪器、额外校验账本或防御层。

## 4. 建议保留 S4 的全总体描述性时延，但不要把它升级为 fresh timing 胜负

G30 已实现一个很小的记录改进：当 S4 own-source case 自身完成全部 85,518 件行李时，额外保留：

`OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE`

它只描述 S4 自身完整总体的 min/mean/P95/P99/max，可用于 Table 5.3 和 Table 5.4 的跨规模上下文。只要 HCA* 未完成固定总体，HCA 幸存者分布仍是 `CENSORED_SECONDARY`，两者不得形成 fresh timing verdict。

该字段已经由正式 native case 生成，并由报告器用于 Table 5.3/5.4 的描述性上下文。它不改变 S4 决策，也不属于 learning；fresh primary 仍只看容量，不能用它与删失的 HCA 幸存者时延形成胜负。

## 5. 固定窗口容量与事件截断必须分开

G30 full native case 使用统一的 60,000,000 事件预算。到达 epoch 98,259 仍有业务未完成，可以是有效的固定窗口容量结果；先触及事件上限则是计算截断，不能准入。两者不能用同一个 `FAILED` 标签混在一起。

对已经跑完固定窗口且结构安全、终端计数和事件预算都合格的旧产物，可以只更新分类标签；completed、failed、event_count 和各成功率必须原样保留。这样修正的是实验语义，不是事后修改结果。

## 6. Table 5.4 的缺口应保留，不应靠反推参数“补齐”

12 个 bias case 能复现观测扰动接口，但没有恢复原论文动态/静态实现的源码、随机流和逐 case 配对。合理做法是把每格的结果、loss 和 gap 全部显示为 reconstruction context。

如果以后取得原实现，应在同一个 3× 航班 manifest 和固定窗口上重新运行 fresh baseline；不要根据论文均值调参直到数字相似，也不要让归档 1× 表格决定 fresh 3× 主状态。

## 7. 并行优先放在独立 case/repeat 编排，不改动单次决策语义

四个速度、两个 HCA 重复和 15 个故障 case 彼此独立，可以在资源允许时按进程 lane 并行执行并分别 resume。这能直接减少整轮 wall time，而且不会把集中规划逻辑引入 S4。

单个仿真内部仍保持确定性的事件顺序和节点局部 ownership。将来若尝试真正的节点并行，应单独比较 wall time、业务完成数和事件顺序稳定性；在有证据前，不为了“看起来并行”重写当前简单 event hot path。

## 8. S4/J2/E2 不应被解释为三层规划

三者分别负责局部下一跳评分、目标节点合流许可和事件发布优化，是同一事件驱动框架中的三个协作 seam。它们不按“全局—区域—节点”形成层级，也不共同生成未来完整路线。

这个表述很重要：G30 的可扩展性来自局部状态、一步提交和独立接口，而不是把 HCA* 拆成三个名字不同的中心化模块。

## 9. 后续调整仍只允许证据指向的最小动作

如果某个 3× 主格退化：

1. 先判断是 Source、plan、network/merge 还是拓扑上限；
2. 检查它是否只出现在一个速度或一个局部故障结构；
3. 优先复用节点局部 FIFO、service-aware potential 和确定性故障值；
4. 只有证据明确指向已有局部拥堵项时，才对一个现有权重做很小的候选比较。

本轮继续禁止增加完整 A*、未来路线、全局预约表或新的 learning 层。负结果和未测项本身也是有效记录，不能靠扩大窗口或删除分母中的困难订单来隐藏。
