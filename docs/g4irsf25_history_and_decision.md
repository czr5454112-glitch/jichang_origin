# G4IRSF25 历史、证据与最终决策

> 状态：`FINAL_DECISION`
> 证据冻结日：`2026-08-22`
> active policy：`S4`
> 决策：`DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE`

## 1. 为什么进入 G25

| 阶段 | 冻结证据 | G25 取舍 |
|---|---|---|
| G16–G20 | 学习能改变动作，但收益稀少或不稳定 | mutation 不等于收益，不扩大模型 |
| G21–G23 | WAIT/alternate edge 和局部 signature 未形成稳定部署收益；private 与 system benefit 常不一致 | 只保留合法 first-edge，并分开 system/private cost |
| G24 | 一步式 S4 在 fresh 1× 超过 HCA；静态学习 0 mutation；静态 corridor 在 2× 有均值信号但有 tail 风险 | 保留去中心化主架构，增加局部上下文和公平 veto |
| G25 | 真实 trajectory、同 checkpoint oracle、T0/L1/L2/L3、native 1×/2×/4× 和 HCA capacity 均已执行 | 以完整闭环选择 active，不因离线排序晋级 |

项目主线一直保持简单：不再建立中央规划器，只研究当前接口的一个合法下一跳是否值得覆盖 S4。

## 2. G24/S4 已确认的接管结果

原始 1× exact-release、43,603 segments、28,506 raw bags 全部完成：

| 方法 | mean | p95 | p99 | max |
|---|---:|---:|---:|---:|
| Fresh HCA | 236.710166 s | 299.000 s | 330.000 s | 357.000 s |
| S4 | 210.769735 s | 247.204 s | 254.004 s | 407.404 s |

S4 mean 改善 `10.958732%`，p95/p99 更好，completion 相同，runtime full A* 为 0；max 未胜，所以结论只限于 mean 与中高分位。这已经确认“去中心化规则式主框架接管集中式 HCA”，不依赖 G25 learning 是否晋级。

## 3. G25 纠正了真实 corridor 语义

observe 得到 `48,516` 条真实 trajectory：

```text
25,778 completed rejoin
   204 true timeout
22,534 censored
     0 loop
     0 unsafe
```

observed registered-arm fraction 为 `0.8125`。旧记录把 `22,534` censored 写成 timeout 是错误的：这些轨迹多数因 bag 在到旧 rejoin 之前完成、到达其他目标或被新登记取代而结束。逐接口重新决策没有义务沿 nominal arm 的静态未来路径走到底。

反馈也已统一：local-system cost 与在线反馈都用 `bag-seconds`；只允许 L3 读取有界 branch-arm `short EWMA - long EWMA` 差，L1/L2 不读取在线反馈。因此不存在旧文档所述的 `short_EWMA - static_duration` 无条件 bias。

## 4. paired oracle：机会存在，但不是部署结论

正式 paired 数据为 `1,024` checkpoint groups、`2,048` arm outcomes、固定 `21D` local observation：

- alternative-win fraction `0.53125`；
- opportunity mass `2,323,446.867805 bag-seconds`；
- useful opportunities `544`；
- local-observation ranking ceiling `0.900390625`，固定 S4 action accuracy `0.46875`；
- unsafe forced arms `0`。

这证明局部观测有能力区分部分动作，但 oracle 是同 checkpoint 短程反事实上限，不能替代 native full-population 结果。

## 5. 学习与闭环结果

### T0

T0 test ranking 只有 `0.4293`；144/512/8192 native prefix screen 全部为 0 mutation。按预设停止线不运行 full 1×/2×/4×，这些结果保持 `NOT_MEASURED`，不是零收益。

### L1

L1 offline test ranking 为 `0.8293`，明显高于固定 S4 `0.46875`。native paired repeats 却呈明显负载差异：

| scale | mean ΔS4 | p95 ΔS4 | p99 ΔS4 | verdict |
|---:|---:|---:|---:|---|
| 1× | `+5.921 s` | `+25.398 s` | `+21.400 s` | FAIL |
| 2× | `-7.549 s` | `-48.801 s` | `-207.381 s` | PASS |

4× bounded progress 也支持高负载信号：

| window | S4 completed/backlog | L1 completed/backlog |
|---:|---:|---:|
| 60 s | 25,218 / 14,211 | 25,724 / 13,554 |
| 180 s | 50,584 / 20,619 | 56,696 / 17,089 |

L1 的 safety/locality 全部通过，但 1× 回归超过门槛，所以 eligibility 为 FAIL。

### L2/L3

L2 由 train+validation oracle 条件触发，但 test ranking 只有 `0.5463`。native 1× mean/p95/p99 为 `+4.716/+14.400/+21.000 s`，2× mean 为 `+1.821 s`，因此 no-go；即使 4× bounded progress 通过，也不能抵消完整 1×/2× gate。

L3 residual-feedback correlation 为 `0.0`，未触发、未导出、未运行。没有为了追求复杂度而强行增加在线层。

## 6. 规模边界

### Native S4/L1 4×

S4 与 L1 的 60/180 s 结果只是 `BOUNDED_PROGRESS`。canonical population 未完整，二者 4× full-population mean/p95/p99/max TTH 均为 `NOT_MEASURED`。

### Fresh HCA

| scale | segments released/completed | complete/incomplete raw bags | parent wall | full-population TTH |
|---:|---:|---:|---:|---|
| 2× | 87,206 / 87,111 | 56,917 / 95 | 321.065 s | `NOT_MEASURED` |
| 4× | 117,626 / 117,270（canonical 174,412） | 70,018 / 44,006 | 419.947 s | `NOT_MEASURED` |

HCA 4× 只释放 `67.441%` canonical segments；released cohort completion `99.697%`，说明主要瓶颈是 admission/planning throughput。parent wall 与 survivor latency 都不是 full-population TTH。

## 7. 实施效率证据

短程 paired runner 的旧 trusted path 仍在每个 event 计算 full-state SHA，并构造富状态快照。这是与算法目标无关的主要热点。改为 trusted next-event time 和 O(1) 局部 queue/incoming 计数后，同语义 pilot pair 从 `190.171 s` 降至 `2.029 s`，约 `93.7×`，结果语义一致。

这项改动没有降低正常 checkpoint 的验证边界；它只移除了同进程可信实验的逐事件安全式开销，避免把执行时间消耗在无助于算法推进的 hash 上。

## 8. 最终联合选择

| candidate | 1× | 2× | 4× bounded | offline | eligibility |
|---|---|---|---|---|---|
| T0 | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | PASS | FAIL：0 mutation screen |
| L1 | FAIL | PASS | PASS | PASS | FAIL：1× regression |
| L2 | FAIL | FAIL | PASS | PASS | FAIL |
| L3 | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | trigger false | NOT TRIGGERED |

因此：

```text
active = S4
status = KEEP_S4
reason = NO_ELIGIBLE_CHANGED_ACTION_WINNER
decision = DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE
```

没有 eligible changed-action winner，所以 winner-only H_system/fault 正确状态是 `NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER`，而不是把未运行写成 PASS。

## 9. 结论边界

可以声明：

- 一步式去中心化 S4 在原始 1× mean/p95/p99 超过 fresh 集中式 HCA；
- HCA 在 2×/4× fixed window 出现 admission/planning capacity boundary；
- paired oracle 和 native 2×/4× 证明局部、负载相关的动作机会真实存在；
- 当前 L1/L2 尚未同时满足 1× 不退化与 2× 获益，不能替代 S4。

不能声明：

- S4 或 CLCR 的 4× full-population TTH；
- HCA 2×/4× full-population TTH；
- learning 已跨负载优于 S4；
- 未执行的 winner-only H_system/fault 已通过。
