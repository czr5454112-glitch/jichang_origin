# 直接空盘控制：完整252次开发对照的只读分析

重读全部原件及来源，36742项记录核对，错误0。未新增仿真、拟合或改参；所有252次结果纳入，以下不是独立确认。

| 策略 | 运行 | final J | ΔJ vs greedy | 改善/相同/变差 | 完成/任务 | 准时 | CPU秒 | 空调proxy调用 |
|---|---:|---:|---:|---|---|---:|---:|---:|
| greedy | 36 | 559.700 | +0.000 | 0/0/0 | 198/198 | 160 | 43.19 | 0 |
| legacy_empty12 | 36 | 368.400 | -191.300 | 26/5/5 | 198/198 | 167 | 48.22 | 551 |
| public_fast4 | 36 | 525.800 | -33.900 | 16/19/1 | 198/198 | 160 | 120.22 | 0 |
| empty2_h40 | 36 | 559.700 | +0.000 | 0/36/0 | 198/198 | 160 | 365.42 | 1738 |
| empty12_h40 | 36 | 384.600 | -175.100 | 26/5/5 | 198/198 | 163 | 336.97 | 2015 |
| empty24_h40 | 36 | 384.600 | -175.100 | 26/5/5 | 198/198 | 163 | 337.08 | 2015 |
| empty24_h80 | 36 | 384.600 | -175.100 | 26/5/5 | 198/198 | 163 | 583.97 | 2015 |

final指runner预声明的任务全到达、已完成、空盘运输排空、全部预测过TTL并经历真实慢层触发后的端点；若未满足则保留截断。h80和final全部216对、名义/压力分层、所有分项和预算细账在analysis.json。

## 预算与评价窗口

| 基础→增量 | final ΔJ | 改善/相同/变差 |
|---|---:|---|
| empty2_h40→empty12_h40 | -175.100 | 26/5/5 |
| empty12_h40→empty24_h40 | +0.000 | 0/36/0 |
| empty24_h40→empty24_h80 | +0.000 | 0/36/0 |

逻辑work包括新方法greedy构造、增强候选构造、每个proxy内fast/reactive/greedy查询；实际外层执行query另列。所有部分proxy禁止参加成本排名。no-demand省略只证明当前声明候选域只有同一空序列，未将其计为已执行回放或缓存命中。

## 实际动作与机制限制

完整changed-action类别计数：{'donor_assignment_change': 147}。

以下每种新策略取final收益最大和损失最大的已完成配对作事后解释；不存在该符号时明确为空。它们不参与budget/参数选择，也不替代完整分母。预测偏差只按已保存公开proxy与真实tape对读，不能据此独立归因。

### empty2_h40 / largest_final_gain

完整分母中没有此符号的配对。

### empty2_h40 / largest_final_loss

完整分母中没有此符号的配对。

### empty12_h40 / largest_final_gain

stream_L4_D3_slack0 / stress_3，final ΔJ=-17.000，h80 ΔJ=-17.000。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': -12.0, 'nonprotected_tardiness': -4.0, 'empty_distance': -10.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 6/26 | 9→9 | 12→12 |
| round1:loaded | S→G | 20/27 | 23→21 | 32→28 |
| round2:loaded | S→G | 42/49 | 45→45 | 52→52 |
| round2:need | B→C | 44/64 | 54→44 | 57→47 |

### empty12_h40 / largest_final_loss

stream_L4_D3_slack0 / stress_5，final ΔJ=+11.900，h80 ΔJ=+11.900。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': 7.0, 'nonprotected_tardiness': 4.0, 'empty_distance': 9.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 4/24 | 9→9 | 12→12 |
| round1:loaded | S→G | 22/29 | 25→23 | 32→30 |
| round1:need | B→C | 26/46 | 26→26 | 29→29 |
| round2:loaded | G→S | 38/45 | 38→47 | 43→51 |

### empty24_h40 / largest_final_gain

stream_L4_D3_slack0 / stress_3，final ΔJ=-17.000，h80 ΔJ=-17.000。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': -12.0, 'nonprotected_tardiness': -4.0, 'empty_distance': -10.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 6/26 | 9→9 | 12→12 |
| round1:loaded | S→G | 20/27 | 23→21 | 32→28 |
| round2:loaded | S→G | 42/49 | 45→45 | 52→52 |
| round2:need | B→C | 44/64 | 54→44 | 57→47 |

### empty24_h40 / largest_final_loss

stream_L4_D3_slack0 / stress_5，final ΔJ=+11.900，h80 ΔJ=+11.900。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': 7.0, 'nonprotected_tardiness': 4.0, 'empty_distance': 9.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 4/24 | 9→9 | 12→12 |
| round1:loaded | S→G | 22/29 | 25→23 | 32→30 |
| round1:need | B→C | 26/46 | 26→26 | 29→29 |
| round2:loaded | G→S | 38/45 | 38→47 | 43→51 |

### empty24_h80 / largest_final_gain

stream_L4_D3_slack0 / stress_3，final ΔJ=-17.000，h80 ΔJ=-17.000。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': -12.0, 'nonprotected_tardiness': -4.0, 'empty_distance': -10.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 6/26 | 9→9 | 12→12 |
| round1:loaded | S→G | 20/27 | 23→21 | 32→28 |
| round2:loaded | S→G | 42/49 | 45→45 | 52→52 |
| round2:need | B→C | 44/64 | 54→44 | 57→47 |

### empty24_h80 / largest_final_loss

stream_L4_D3_slack0 / stress_5，final ΔJ=+11.900，h80 ΔJ=+11.900。
分项Δ（空驶为原量，目标权重0.1）：{'tray_wait': 7.0, 'nonprotected_tardiness': 4.0, 'empty_distance': 9.0, 'terminal_backlog': 0.0, 'terminal_inflight': 0.0}。
首个增强动作发生于t14，类别donor_assignment_change，proxy ΔJ=-6.000。首变化前核对：{'incumbent_matches_greedy_actual_at_tick': True, 'past_physical_trace_equal': True, 'loaded_decisions_through_current_tick_equal': True}。
该点保存proxy中与实际tape不一致的任务1个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。

| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |
|---|---|---|---|---|
| initial | S→G | 0/7 | 0→0 | 7→7 |
| need:0 | B→C | 4/24 | 9→9 | 12→12 |
| round1:loaded | S→G | 22/29 | 25→23 | 32→30 |
| round1:need | B→C | 26/46 | 26→26 | 29→29 |
| round2:loaded | G→S | 38/45 | 38→47 | 43→51 |

原greedy无额外unadmitted-protected阻断；旧Bounded在该状态只允许no-transfer；新方法保留mandatory greedy/no-transfer而禁止增强序列，三者保守动作域差异显式存在。最终硬许可仍由同一个ExecutionValidator检查。不得将这次开发集收益称为真实未来支配、递归MPC最优或原图已验证改善。
