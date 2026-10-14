# Event control cost diagnosis and protocol serialization 016

本次从原图 24 件实际执行记录定位事件控制新增开销，并完成一个字段严格等价的 binding 优化。它是 P7 工程优化，不是方法创新；没有删除通知、历史消息、区域控制或跨区预测需求，也没有放宽完整 100 ms 要求。

## 原始执行记录说明了什么

输入为 `event_protocol_original24_015_001/original24/` 下相同物理合同。该轮存在并行编译，以下 wall 数据是诊断，不能当作公平的 P7 性能比较。所有策略的完整原件保留。

| 015 实际策略 | 总 wall 秒 | owner 激活数 | owner 计算及准备总秒 | native 事件 batch 总秒 | 提交调用总秒（已包含在 owner 计算中） |
| --- | ---: | ---: | ---: | ---: | ---: |
| periodic predictive | 6.720 | 2,882 | 6.398 | 0.107 | 0.0086 |
| event predictive | 68.460 | 7,890 | 62.132 | 0.390 | 0.0663 |
| event reactive | 14.188 | 6,215 | 12.686 | 0.269 | 0.0071 |
| event joint | 68.511 | 7,890 | 62.275 | 0.383 | 0.0640 |

不能将 submit 再加一次，也不能把未归入以上分项的剩余时间抹去。event predictive 仍有约 5.939 秒未在这些已有计时字段内分解，包含控制调度/状态整理等；现有证据不能把它全部归因于某个函数。

事件预测比定期预测激活多约 2.738 倍，但平均每次激活的完整准备/计算也从约 2.22 ms 增长到 7.87 ms，因此“只是通知变多”不足以解释全部差距。事件预测发布了 524 条服务预测及 524 条撤销，定期预测只发布 16 条服务预测、没有撤销；对应最终 outbox 为 1,119 对 79 条。事件预测 7,890 次激活中，4,641 次带通知原因，2,882 次带公共定期 tick，370 次带 retry timer；原因可能在一次激活中同时出现，不能直接相加当作激活总数。

记录中确有超过 100 ms 的局部计算：event predictive 的单 owner 激活共 19 次，国内 9、国际 10，最大 135.346 ms；event joint 共 23 次，最大 173.190 ms。它们还不是完整请求响应链。粗粒度 CPU 字段在许多慢调用中也为约 109–141 ms，不能简单把这些值归为“仅被并行编译挤占”。当前没有单独测定垃圾回收或系统调度的因果贡献。

H≥45,000 的后续 1,382 次事件预测激活全部没有发布、转移或服务动作，却仍消耗 19.082 秒 owner 计算，平均 13.807 ms。这个事实提示历史状态反复投影的成本会在业务已经平静后持续存在；它不是允许删掉历史、跳过合法消息或降低通知要求的理由。

机器可读分解：

`outputs/experiments/g31_ics_long_term_20261013/event_control_readonly_profile_015_001/existing_run_breakdown.json`

同目录 `summarize_existing.py` 只读取已有 run，不执行策略或物理模拟。

## 有限真实前缀的只读 cProfile

使用原 run 中已经实际提交的 request tape，在同一 015 native 输入上恢复 H=24,000、36,000、45,000 三个前缀；没有重新执行全天 Python 控制器。每一条重新提交的回复与原记录相同，每个前缀的完整物理及协议 receipts 与原 run 对应前缀精确相等。最后前缀含全部 1,489 次原实际命令/重试，但只推进到 H=45,000。

每个 owner 在每个固定前缀上只读测量 12 次。观测内容每次相同，测量前后 native seal 不变。015 整个恢复和测量用时 0.964 秒，016 为 0.839 秒，均远小于诊断预算 20 秒。cProfile、重复读取和当前机器状态会影响这些微测量，不能据此宣布端到端 100 ms 达标。

H=45,000 的 015 证据：

| owner | 自有 command 历史条数 | 一次 observe_protocol_control 均值 | 逐条查询全部自有 command 均值 | 本地需求签名均值 | 已缓存观察上的 matching 均值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 国内 | 401 | 5.079 ms | 2.991 ms | 0.047 ms | 1.244 ms |
| 国际 | 695 | 7.361 ms | 5.636 ms | 0.051 ms | 0.214 ms |

同一 owner 投影还包含其真实已送达 ACK、已送达预测及真实本地状态。小样例的签名开销不是本次主要来源，不应将此 24 件稀疏样例的结果外推为全量高负载需求窗口已经解决。

## 已完成的最小修复

原 `observe_protocol_impl` 遍历每条自有 command，然后调用 `protocol_command(owner, id)`；后者每次又从头扫描所有 command。输出 n 条历史记录产生了重复的二次查找。

016 只在 `cpp/ics_core/bindings/circulation_session_binding.hpp` 抽出 `render_protocol_command(const CirculationProtocolCommand&)`：单个 request 查询仍先执行原 owner/identity 查找；批量路径在已经取得并过滤 owner 的原生引用上直接序列化。两条路径共用原 `command_ack`，只有实际已送达 ACK 可见，历史字段、顺序、独立返回字典及 captured demand signature 语义完全保留。

没有移除历史行，没有改变原生事件、算法候选、消息时延、owner 通知或任何物理状态。015 与 016 编译输入对比中唯一变化的文件就是该 binding header；runtime 全部文件哈希不变。因此 015 对应 `p1_checkpoint_validation_009` 和 `legacy_parity_005` 的实际 native runtime 复核身份继续适用，不重复声称重新执行了这些检查。

## 016 已执行的结果

- `p1_build_016`：独立 clean build 通过，46.625 秒，source_changed=[]。
- `protocol_serialization_tests_016_001`：5 项通过，0 失败/错误/跳过，1.338 秒，source_changed=[]。覆盖批量与逐条查询的 full/compact 字段等价、pending/timeout、丢 ACK、重复 ACK、outage、同 ID 重试、fork/restore 及调用方修改返回字典不污染后续观察。
- `event_control_readonly_profile_016_001/comparison.json`：三个真实前缀、两个 owner 的完整观察摘要全部与 015 相同；对应 receipts 与 native seal 也全部相同，重放的回复逐条一致。

同一固定晚段前缀，观察均值：

| owner | 015 | 016 | 本次微测量下降 |
| --- | ---: | ---: | ---: |
| 国内 | 5.079 ms | 2.957 ms | 41.8% |
| 国际 | 7.361 ms | 4.014 ms | 45.5% |

016 二进制：`build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd`。

SHA-256：`af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`。

微测量的 015 原件位于 `event_control_readonly_profile_015_001/raw/`，016 位于 `event_control_readonly_profile_016_001/`；包含 `.prof`、可读 pstats、输入/源代码/二进制身份和结果摘要。

## 全天等价与最终回归结果

`event_protocol_015_016_comparison_001/assessment.json` 已核对原图全天五种策略。periodic reactive、periodic predictive、event reactive、event predictive、event joint 均通过：完整返回物理结果、请求及回复、控制记录、controller state、native batch/segment、JSON 续跑状态、业务指标和最终 native seal 一致。仅回执列出的计算计时字段不参加语义摘要比较，原始文件和计时值全部保留。这是本次运行范围内的语义等价证据，不是业务增益。

| 策略 | 015 总 wall 秒 | 016 总 wall 秒 | 015 owner 最大 ms | 016 owner 最大 ms | 015 超过 100 ms / 激活数 | 016 超过 100 ms / 激活数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| event reactive | 14.188 | 12.175 | 83.406 | 66.963 | 0 / 6,215 | 0 / 6,215 |
| event predictive | 68.460 | 49.168 | 135.346 | 128.084 | 19 / 7,890 | 15 / 7,890 |
| event joint | 68.511 | 50.527 | 173.190 | 199.580 | 23 / 7,890 | 24 / 7,890 |

定期策略总 wall 也保留在同一回执：reactive 为 5.949→6.184 秒，predictive 为 6.720→6.903 秒；该比较器没有为定期策略汇总 event-owner 口径，不能将其空字段或零样本当成全部调用均低于 100 ms。

事件预测和联合策略总耗时下降，但联合策略最大 owner 计算及超限次数反而上升。015 运行时存在并行编译，016 为另一轮本地运行，二者不是受控性能实验，不能将全天 wall 差值全部归因于这次序列化改动。超过 100 ms 的字段还只是 owner 计算子链，完整请求链要求仍未通过；也不能用 event reactive 的局部零超限代替完整 100 ms 认证。

最新回归为 `live_validation_012/receipt.json`：407 通过、0 失败/错误/跳过，退出码 0，`source_changed=[]`、`compiled_source_mismatch=[]`。407 的范围是 401 项当前 native/Python 检查、1 项在独立进程运行 frozen 011 的历史排序反例、5 项独立进程版本身份检查，不是 407 项 016 物理验证。`live_validation_011` 保留；012 在明确修正回执历史范围说明后重新执行。通知和序列化等专项已包含在总回归中，各轮或各专项计数不得相加。回归通过不等于 P7 通过。

## 下一批优化的具体入口与边界

1. `_activate_owner` 先在 `_publish_services` 取一次完整协议观察，随后匹配又取一次。应研究同一完整 native timestamp 的物理投影复用，明确提交新命令后新增的客户端已知 outbox 如何覆盖；不能直接缓存整个旧观察而遗漏本 owner 新待确认意图。
2. `ProtocolClient.refresh`、`_retry_time` 及 `_publish_services` 的撤销遍历仍扫描完整历史。可增加按 owner 的未决索引和显式活动预测索引，JSON checkpoint 必须包含或可确定地重建索引；完整历史保留用于审计，不能靠删除终态记录省事。
3. 即使二次查找已去除，binding 每次仍序列化全部命令与 ACK。后续可研究另一个明确契约的增量客户端投影/缓存，在真实已送达本地 revision 上失效，并保留旧全量 API；必须逐字段、逐动作及 fork/restore 非干扰验收。不能用隐藏 server 状态版本做缓存依据。
4. 已记录的 >100 ms owner 调用和未分解约 5.9 秒仍需在串行、完整计费的请求链中验证。后续如测垃圾回收，应实际记录其耗时和发生点，不能从偶发长尾直接下因果结论。

这些是工程优化接入点，不证明联合控制方法增量，也不改变强参考、两项业务需求或正常分拣保护的门槛。
