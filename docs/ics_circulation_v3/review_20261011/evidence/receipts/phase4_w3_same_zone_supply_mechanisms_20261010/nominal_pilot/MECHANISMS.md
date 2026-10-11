# 第六轮供盘机制：nominal_pilot

全部请求 9，保存物理原件 9；只读检查 1276，失败 0，输入变化 0。无新增仿真。

| case | status | J | wait | empty distance | on time | same-zone commits | guard work |
|---|---|---:|---:|---:|---:|---:|---:|
| counterflow__nominal__old32 | controller_quiescent (physical:controller_quiescent) | 192.4 | 162.0 | 304.0 | 10/10 | 0 | 0 |
| counterflow__nominal__old64 | controller_quiescent (physical:controller_quiescent) | 192.4 | 162.0 | 304.0 | 10/10 | 0 | 0 |
| counterflow__nominal__same_zone32plus32 | controller_quiescent (physical:controller_quiescent) | 50.400000000000006 | 28.0 | 224.0 | 10/10 | 3 | 11644 |
| cross_cycle__nominal__old32 | controller_quiescent (physical:controller_quiescent) | 29.700000000000003 | 20.0 | 97.0 | 7/7 | 0 | 0 |
| cross_cycle__nominal__old64 | controller_quiescent (physical:controller_quiescent) | 29.700000000000003 | 20.0 | 97.0 | 7/7 | 0 | 0 |
| cross_cycle__nominal__same_zone32plus32 | controller_quiescent (physical:controller_quiescent) | 29.700000000000003 | 20.0 | 97.0 | 7/7 | 0 | 92 |
| near_full__nominal__old32 | controller_quiescent (physical:controller_quiescent) | 13.700000000000001 | 4.0 | 97.0 | 7/7 | 0 | 0 |
| near_full__nominal__old64 | controller_quiescent (physical:controller_quiescent) | 13.700000000000001 | 4.0 | 97.0 | 7/7 | 0 | 0 |
| near_full__nominal__same_zone32plus32 | controller_quiescent (physical:controller_quiescent) | 13.700000000000001 | 4.0 | 97.0 | 7/7 | 0 | 84 |

| old → new | ΔJ | Δwait | Δempty distance | Δon-time | first different slow action |
|---|---:|---:|---:|---:|---:|
| counterflow__nominal__old32 → counterflow__nominal__old64 | 0.0 | 0.0 | 0.0 | 0 | none |
| counterflow__nominal__old32 → counterflow__nominal__same_zone32plus32 | -142.0 | -134.0 | -80.0 | 0 | 45 |
| cross_cycle__nominal__old32 → cross_cycle__nominal__old64 | 0.0 | 0.0 | 0.0 | 0 | none |
| cross_cycle__nominal__old32 → cross_cycle__nominal__same_zone32plus32 | 0.0 | 0.0 | 0.0 | 0 | none |
| near_full__nominal__old32 → near_full__nominal__old64 | 0.0 | 0.0 | 0.0 | 0 | none |
| near_full__nominal__old32 → near_full__nominal__same_zone32plus32 | 0.0 | 0.0 | 0.0 | 0 | none |

完整逐袋变化、首次动作分歧的公共snapshot/forecast、所有动作差异、t127/139候选与拒绝、物理事件链和原件SHA见analysis.json。此自动表保留全分母，不把同轨迹局部regret相加。

本分析CPU 45.234375s、wall 46.254593s；实验worker资源仅作metadata，不计入分析耗时。
