# G4IRSF21 最终决策与下一步

状态：**KEEP_A0_S4_J2_E2_NO_LEARNED_POLICY**。

G21 没有找到值得进入 normal flow 的新控制机制。当前线上研究主线完整保持为 **Source A0 + Route S4 + Merge J2 + event E2**；没有模型、没有 learned mutation、没有 WAIT closed loop，也没有重新引入 HCA*、全局未来路径或集中式 MAPF 求解器。

## 1. 两个工程候选均为 no-go，并已撤回

### lean S4 hotpath

正式 order-balanced ABBA 验证中，lean S4 在完整 1x/2x 上保持语义一致；但 4x 有界中相对 rich S4 只有约 **+1.32% events/s**、**+1.38% completed segments**，`events/completed` 反而恶化约 **0.056%**。它没有达到预设的 5% 门槛，因此结论是 `NO_GO_KEEP_RICH_S4`，不是小幅优化晋级。

### guarded scalar beacon payload

20 秒交叉短测中，scalar 相对 rich 的中位数仅约 **+1.65% events/s**、**+1.22% completed segments**，`events/completed` 没有改善。该结果只够排除明显的大收益，不构成容量或业务时间结论，因此同样撤回。

**上述两个负候选的 normal-flow 代码路径均未保留。** 仓库保留的是负证据和数据审计能力，不保留 lean S4 或 scalar beacon 的运行时开关；不为了约 1% 的短测波动增加长期分支。

## 2. G20 的 5,022 组已经标完全部 edge

对既有 exact cache 的只读核对显示：5,022/5,022 eligible 组都恰有两条 `legal_next_edges`，observation 也都恰有两条 candidate；每组 `{S4 baseline edge, treatment edge}` 与完整合法 edge 集合完全相等。因此 G20 不是缺其他 edge 标签，实际缺口只有 **native legal WAIT**。

这项核对修正了“primary pair 可能遗漏更多 edge”的宽泛表述，但不改变 G20 no-go：当时确实没有 WAIT 标签，也没有完整三动作合同可供晋级判断。

## 3. G21 完成三动作合同，但 WAIT 没有收益

G21 先筛选 24 组，**24/24** 都完成 same-state、action-changed、horizon、live-safety 与 action-certificate 门；随后按预注册配额持久化 16 组 H_bag 完整 action set。每组正好包含：

1. S4 baseline edge；
2. 另一条 shield-legal one-hop edge；
3. native I4 WAIT 一次自然局部服务机会。

最终 16 组覆盖 8 个短等待和 8 个长等待状态、8 个 distinct original tasks。结果为：S4 baseline 16 个 neutral，另一 edge 16/16 harmful，WAIT 16/16 harmful；每个 WAIT 都使 affected segment **延后 1 秒**。WAIT 没有伪造 edge feature vector，数据只记录 action kind。

这是 `COMPLETE_ACTION_SET_TARGET_MET`，不是策略成功。样本只有 protected 1x、16 组和 8 个原始任务，不能代表完整状态分布，也没有训练模型。

## 4. H_system 小探针没有发现 WAIT 外部收益

4 个来自不同 edge-label / wait-age 层的 H_system WAIT 均通过 same-state、action-changed、complete、live-safety 与 certificate：

- beneficial：0/4；
- raw-bag/system exact zero：2/4；
- 仅 affected segment 延后 1 秒、没有其他 bag 外部收益：2/4；对应 raw-bag mean 只增加约 0.00003508 秒。

因此当前 1x 证据一致指向“保持 S4，不增加 WAIT 策略”。四个 H_system 样本很小，只能作为 veto/方向检查；它不能排除尚未测试的 2x 拥堵状态中存在 WAIT 收益。

## 5. 文献只约束方向，不替代本项目证据

- [PIBT, IJCAI 2019](https://www.ijcai.org/proceedings/2019/0076.pdf) 与 [AAMAS 2023 asynchronous local navigation](https://www.ifaamas.org/Proceedings/aamas2023/pdfs/p914.pdf) 支持相邻一步动作、局部 owner/grant 和 move/detour/wait 的简化边界；其拓扑与完备性条件不能外推到本机场有向图。
- [RHCR, AAAI 2021](https://ojs.aaai.org/index.php/AAAI/article/view/17344) 支持 bounded adaptation，但它仍依赖集中式 Windowed-MAPF solver；本项目不导入该求解器。
- [Traffic Flow Optimisation for LMAPF, AAAI 2024](https://ojs.aaai.org/index.php/AAAI/article/download/30054/31856) 说明拥堵 guidance 可能有价值，也同时显示全量 heuristic 重算可能超时；它不证明本机场需要 edge-flow penalty，更不授权全体 guide paths、FOCAL Search 或 refinement。
- [MAPD, AAMAS 2017](https://www.ifaamas.org/Proceedings/aamas2017/pdfs/p837.pdf) 支持把机场行李视为持续 pickup-and-delivery，但其全局 token、完整路径表和 well-formed 保证不移植到当前框架。

所以文献支持继续做“小范围、一步、局部、可撤回”的实验；是否采用 WAIT、flow penalty 或模型，只能由当前机场数据的闭环证据决定。

## 6. 唯一下一步：2x 拥堵状态 WAIT/action-set audit

下一步不训练模型，也不实现 edge-flow penalty。最窄实验是在 protected 2x 中只抽取确有 Route wait、目标队列或 merge contention 的状态，复用同一 checkpoint，为全部 shield-legal one-hop edges 与 native WAIT 生成小规模完整 action set：先做 H_bag，再用极少 H_system 作 raw-bag 外部性 veto。

只有出现可重复的 WAIT/alternative beneficial 支持、且 raw-bag/system 不反号，才讨论简单规则。若 2x 仍无信号，就关闭 WAIT 分支并保持 A0 + S4 + J2 + E2。**在此之前，不做 edge-flow penalty，不增加新模型，不运行 learned closed loop。**

## 证据位置

- `outputs/reports/g4irsf21_lean_s4_hotpath.md`
- `outputs/tables/g4irsf21_narrow_profile_probes.json`
- `outputs/reports/g4irsf21_route_action_sets.md`
- `outputs/reports/g4irsf21_wait_h_system_probe.md`
- `outputs/reports/g4irsf21_literature_and_next_ideas.md`
