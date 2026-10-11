# 第七轮固定影子查询覆盖诊断

输入来自 27 条已声明的新策略轨迹。保留全部 93 次截断及匹配成功 controls；四档固定搜索只生成，不执行新增候选。

| 查询域 | 场景 | 搜索 | 查询数 | 授权非空 | 新授权前缀 | 更早 usable | work |
|---|---|---|---:|---:|---:|---:|---:|
| all_truncated | counterflow | regional3000 | 43 | 0 | 0 | 0 | 129000 |
| all_truncated | counterflow | regional12000 | 43 | 0 | 0 | 0 | 516000 |
| all_truncated | counterflow | regional48000 | 43 | 0 | 0 | 0 | 2064000 |
| all_truncated | counterflow | fullgraph_event48000 | 43 | 0 | 0 | 0 | 857374 |
| all_truncated | near_full | regional3000 | 50 | 0 | 0 | 0 | 150000 |
| all_truncated | near_full | regional12000 | 50 | 0 | 0 | 0 | 600000 |
| all_truncated | near_full | regional48000 | 50 | 0 | 0 | 0 | 2400000 |
| all_truncated | near_full | fullgraph_event48000 | 50 | 0 | 0 | 0 | 2400000 |
| earliest_successful_control | counterflow | regional3000 | 5 | 5 | 0 | 0 | 2953 |
| earliest_successful_control | counterflow | regional12000 | 5 | 5 | 0 | 0 | 2953 |
| earliest_successful_control | counterflow | regional48000 | 5 | 5 | 0 | 0 | 2953 |
| earliest_successful_control | counterflow | fullgraph_event48000 | 5 | 5 | 2 | 0 | 2132 |
| earliest_successful_control | near_full | regional3000 | 1 | 1 | 0 | 0 | 500 |
| earliest_successful_control | near_full | regional12000 | 1 | 1 | 0 | 0 | 500 |
| earliest_successful_control | near_full | regional48000 | 1 | 1 | 0 | 0 | 500 |
| earliest_successful_control | near_full | fullgraph_event48000 | 1 | 1 | 1 | 0 | 414 |

公开终点长期占用证书覆盖 93 / 93 条截断。证书仅针对当前公开预留模型下的终点无限期驻留要求，不能推导真实未来任务不可服务。

纯文件检查 1195 项，失败 0；直接分析 CPU 1.843750s。

局部标签或搜索预算的遗漏只能由找到的合法反例证明；同样未找到不等于完整覆盖。全图 event 参考也有时刻表示、K 与预算边界，不能套用 SIPP 最早标签支配定理。
