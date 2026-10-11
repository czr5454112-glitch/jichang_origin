# 第六轮供盘机制：mechanism

全部请求 6，保存物理原件 6；只读检查 292，失败 0，输入变化 0。无新增仿真。

| case | status | J | wait | empty distance | on time | same-zone commits | guard work |
|---|---|---:|---:|---:|---:|---:|---:|
| counterflow_d0040_c0__old32 | controller_quiescent (physical:controller_quiescent) | 192.4 | 162.0 | 304.0 | 10/10 | 0 | 0 |
| counterflow_d0040_c0__old64 | controller_quiescent (physical:controller_quiescent) | 192.4 | 162.0 | 304.0 | 10/10 | 0 | 0 |
| counterflow_d0040_c0__same_zone32plus32 | controller_quiescent (physical:controller_quiescent) | 148.1 | 114.0 | 341.0 | 10/10 | 2 | 24017 |
| counterflow_d0040_c1__old32 | controller_quiescent (physical:controller_quiescent) | 146.7 | 122.0 | 247.0 | 10/10 | 0 | 0 |
| counterflow_d0040_c1__old64 | controller_quiescent (physical:controller_quiescent) | 146.7 | 122.0 | 247.0 | 10/10 | 0 | 0 |
| counterflow_d0040_c1__same_zone32plus32 | controller_quiescent (physical:controller_quiescent) | 146.7 | 122.0 | 247.0 | 10/10 | 0 | 22476 |

| old → new | ΔJ | Δwait | Δempty distance | Δon-time | first different slow action |
|---|---:|---:|---:|---:|---:|
| counterflow_d0040_c0__old32 → counterflow_d0040_c0__old64 | 0.0 | 0.0 | 0.0 | 0 | none |
| counterflow_d0040_c0__old32 → counterflow_d0040_c0__same_zone32plus32 | -44.30000000000001 | -48.0 | 37.0 | 0 | 157 |
| counterflow_d0040_c1__old32 → counterflow_d0040_c1__old64 | 0.0 | 0.0 | 0.0 | 0 | none |
| counterflow_d0040_c1__old32 → counterflow_d0040_c1__same_zone32plus32 | 0.0 | 0.0 | 0.0 | 0 | none |
| counterflow_d0040_c0__old32 → counterflow_d0040_c1__old32 | -45.70000000000002 | -40.0 | -57.0 | 0 | 139 |
| counterflow_d0040_c0__old64 → counterflow_d0040_c1__old64 | -45.70000000000002 | -40.0 | -57.0 | 0 | 139 |
| counterflow_d0040_c0__same_zone32plus32 → counterflow_d0040_c1__same_zone32plus32 | -1.4000000000000057 | 8.0 | -94.0 | 0 | 139 |

完整逐袋变化、首次动作分歧的公共snapshot/forecast、所有动作差异、t127/139候选与拒绝、物理事件链和原件SHA见analysis.json。此自动表保留全分母，不把同轨迹局部regret相加。

本分析CPU 24.343750s、wall 24.898791s；实验worker资源仅作metadata，不计入分析耗时。
