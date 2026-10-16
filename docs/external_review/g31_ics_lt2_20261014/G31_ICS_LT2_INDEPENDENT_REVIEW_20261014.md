# G31 × ICS：2026-10-14 独立审阅记录

## 1. 结论和范围

**允许在当前集成基础上继续长期实质研发；不放行“完整需求完成”“100ms 已满足”或“创新已成立”的主张。** 在本次实际检查与运行范围内，没有得到必须推倒当前成熟 G31 集成的新证据；发现并实测了接口接入缺口，同时确认作者披露的关键业务、强参考和计时限制。这里没有对全部仓库逐行审计或所有历史实验背书。

审阅对象为用户提供的 `G31_ICS_full_repository_20261014.zip`。发布材料 SHA `c3fba56679219ee274c9c2e2c946cb8d3074dd90`；其中指定的代码 SHA `89c2935ef2963d769ab6ca75764009b2b3e9365f`。通过 GitHub 连接器读取用户指定报告，并直接使用完整附件解压后的代码和保存证据。此次不是整仓下载失败，也不是只看摘要。

ZIP SHA256：`7a3fe9491d0fba8a11f03c42d96c56324160aad834cbb09ba67183cad7b8a2b4`。解压前检查路径安全。发布校验脚本实际返回 `passed`、5,869 项一致、`mismatches=[]`。**文件字节一致不等于已审完 5,869 项逻辑。** 解压目录没有 Git 历史数据库，不能据此声称重建了完整提交历史。

## 2. 实际运行、保存原件复算与未运行内容

| 类别 | 本轮做了什么 | 结果／限制 |
|---|---|---|
| 实际运行 | 发布清单验证脚本 | 5,869 项一致 |
| 实际新编译和运行 | Linux CMake Debug，`CZR005_BUILD_PYBIND=OFF`；`test_circulation_runtime` | CTest 指定单目标通过，记录和 JUnit 随包 |
| 实际新编译和运行 | `test_circulation_checkpoint` | 独立可执行程序退出码 0；cycle、delayed_fault、lost_notification、expired_message、headway_resource_wait 五场景检查通过 |
| 实际运行 | `tests/test_g31_circulation_p5_handoff.py` | 10 passed；它们是 Python 合同／有限参考检查，不是 10 个原生业务实验 |
| 保存原件只读复算 | native016 original24 五策略、请求账本、最终投影及 receipt | 复核完成／迟到／成本／route／预测／owner 计时及事件等价 |
| 保存原件只读复算 | P5 8 域 assessment 和原始分支行数 | 共 126 行；强服务指派有限域余量均为 0；不表示全局最优 |
| 保存原件只读复算 | `live_validation_012/junit.xml` | tests=407、failures/errors/skipped=0；不是本轮重跑 407 |
| 实际窄探针 | 合法观测缺少 version、同 stage 预测刷新、终态重试定时 | 见第 4 节；均为 Python 接口／mock 范围，不冒称 native 故障复现 |
| 没有运行 | Windows Python3.11 native016、011／015 历史扩展、legacy 全组及完整母流 | 本环境 Linux／Python3.13.5，不能直接加载 Windows `.pyd`；没有重建完整 Python native binding |
| 没有运行 | 两台目标机器冷／热／突发、全仓所有历史测试 | 本轮不能认证其结果 |

### 2.1 未隐去的运行限制

首次 C++ 多目标编译在容器命令 90 秒预算到达时被终止；runtime 已完成，checkpoint 编译当时未结束。随后 checkpoint 单独编译成功。合并 CTest 命令的那次也在记录到第二目标开始后被外层命令预算截断，不能据该日志说整组 CTest 通过。最后独立执行 checkpoint 程序，带 25 秒 `timeout`，实际退出码 0、五场景全部完成。保留初始终止和后续成功两类日志，不把命令超时说成已定位的算法缺陷。

本环境未提供可用的交互式容器 session，故使用普通进程执行；也没有 pybind11 Python 包。它们是工具／依赖范围限制，不是原项目物理正确性失败。没有因此停止源码和可执行 C++／Python 范围内的验证。

### 2.2 本轮审阅脚本自身修正

初版预测时序复算只按 `kind=service_forecast` 筛消息，误把 204 条 `withdrawn` 撤销记录算进原始公告，得到 408 条及错误匹配。它是**审阅脚本的过滤错误**，不是生产代码缺陷。

修订版以原始请求账中成功 `service_forecast` 请求 ACK 的 `result_id` 精确选择公告，排除撤销，再复算全部结果：204 条成功原始公告、204 条匹配、均在对应实际入边之后 0.5 秒送达。初版脚本和结果保存在 `evidence/reviewer_history/`，明确 NOT_FINAL；唯一最终输出为 `evidence/independent_recomputation.json`。

## 3. 业务与方法事实复核

### 3.1 原图五策略

输入 24 件、1 盘、R1 后缀授权数 0。保存 run 的物理时钟均到 86400，24 件均有真实完成记录、19 件超过各自截止时间、23 条 EMPTY_RECEIVED，五策略 route 请求均为 0。

| 策略 | arrival→unload 成本总和（秒） | owner 样本 >100ms／样本数 | owner 最大值 |
|---|---:|---:|---:|
| periodic_reactive | 418514.272581 | 本脚本未提取该类计时，不作零耗时结论 | 不适用 |
| periodic_predictive | 414198.867581 | 同上 | 不适用 |
| event_reactive | 414592.459581 | 0 / 6,215 | 66.9627ms |
| event_predictive | 414170.459581 | 15 / 7,890 | 128.0842ms |
| event_joint | 414170.459581 | 24 / 7,890 | 199.5798ms |

本轮逐对象比较保存的 event_joint 与 event_predictive 的 `result.jobs`、`result.receipts`，均完全一致。receipt 序列严格时间回退计数均为 0；该计数只覆盖所读 receipt，不宣称穷尽全部内部事件调度路径。

事件预测相比周期预测累计改善 28.408 秒，1 件更快、23 件相同、0 件更慢。成功服务预测 204 条、拒绝 320 条；周期预测的 16 条全部拒绝。成功公告的送达晚于相关入边 0.5 秒，不表示它们必然晚于所有下游释放／接收决策。作者报告中首次 conditional_release 调盘时机与该收益的关系，需要新因果消融；本轮没有运行这个消融。

这些数值均由保存原件复算，不是重新运行 Windows native016。单盘 24 件展示循环可行，不能覆盖 28,506／57,012 全分母，也不能因 event_reactive owner 子链未超时就认证完整 100ms。

### 3.2 P5 与旧反例

本轮读了全部 8 个 P5 域的保存 assessment，并计数对应 `native_branches.jsonl.gz`，合计 126 行。各域 `strong_service_assignment` 对应参考状态都是 `complete_executed_finite_domain`，`headroom_vs_baseline=0`。这支持“目前有限域被强服务指派解释”，不支持“整个 ICS 联合问题没有研究价值”。没有在本轮复跑这些 126 个 native 分支。

已读取 NOVELTY_LEDGER §§25—29 和最新进度中对旧 400 秒退化反例的撤回：旧近似同刻排序造成因果误判，严格015后旧结论不再适用。此次没有自行重跑全部011／015历史原件，按版本绑定的作者修正记录处理，不能重复引用已撤回结论证明当前机制失败。

## 4. 三个直接影响后续顺序的接口结论

### F1. P5 到真实 owner 协议必须改接入合同

`cpp/ics_core/bindings/circulation_session_binding.hpp` 的 `observe_protocol_impl` 明确删除 `version`，因为旧版本含未收到消息／ACK 的处理痕迹。`scripts/experiments/g31_ics_circulation/p5_handoff.py` 的候选构造仍要求 `observation['version']`。

本轮执行：现有测试的 public_projection 构造完整有限域成功；去掉 `version` 后同函数抛 `KeyError('version')`。这证明当前接口不能直接拼接；不证明旧有限域声明的输入无效。最重要的限制是**不能恢复泄露真值的 version**。新计划要求合法局部读集 token 和送达后真实复验。

源码同时显示 event_joint 的 activation 仍沿 `_publish_services` 与 `transfer_candidates` 顺序执行，而非直接调用该 P5 构造器。因此，F1 不是当前 event_joint 运行已经崩溃，而是下一步接入真正联合机制必须完成的工作。

### F2. 同 stage 刷新与主动定时不能依赖偶然事件

`protocol_control._publish_services` 在 stage key 不变、上次成功、没有撤销／拒绝时，不因时间推进而重新发布。mock-client 测试首次发 1 条、时间推进至1000后新增0条。`event_protocol_control._retry_time` 对只有 terminal=True、next_retry=5 的 outbox 返回 inf。

它们与作者披露的刷新／租约／终态 cooldown 缺口一致。需要原生真实通知和消息延迟下的后续场景测试，不得将 mock 探针描述为物理系统死锁。长期规划把这些放在训练和大批次机制实验之前。

### F3. 性能尚未过门，历史索引是可研究热点而非已确诊唯一原因

binding 中依然有全历史请求／命令遍历及取消查询；客户端重复访问 outbox 和预测历史。源码说明复杂度风险，保存计时证明部分 owner 子链超限；二者不能直接合成“所有超时都由这一处导致”的因果结论。

计划要求完整请求 span、同 activation 观察复用、活动索引与可重建的历史保留，先剖析后改。所有未知、重试和失败在分母；不采用平均计时、推理耗时或批次摊薄替代 100ms。

## 5. 原始需求与资料可用性的修正

本轮从 Library 取得《问题及约束说明.docx》版本1、3页，和《设备故障处置建议及紧急自动处理问题说明(3).docx》版本1、3页，完整读取文本。不是只依据以前生成的计划推断需求。

原始需求一明确 R1 的规划、A*编解码、区域上报、流量平衡／故障应对与100ms按需更新。需求二明确载盘目的地／路由预测、跨区预平衡、固定区内模块、长连接、多线平衡和正常分拣保护。附件说明允许改变第二份拓扑表“系统=/”的连接线长度。这一窄许可不能扩大到任意改图。

故障说明定义边托盘容量为同时在线移动的最大数量，但没有说明零值的特殊语义；其吞吐例子不是本项目盘量／容量校准值。本轮未取得所有现场图纸和具体模块物理定义。不能再说“原始需求 DOCX 完全未能读取”，也不能说“全部现场语义已经查明”。

## 6. 创新判断与文献核查范围

Zeinaly等2015 TCST 已研究联合路由、线平衡与空车管理；本轮读取作者公开全文的相关段和模型页图像。这篇也已经在仓库创新账中，不将其包装成本轮发现的重大漏引。

Chen等2021 RA-L 的原始摘要及发表信息支持服务实际代价、边际成本指派与 LNS 的已有性。本轮没有将读取摘要冒充重新核过全部算法正文。Parimi与Williams的2026年 arXiv v1 已有低余量、后继闭合、边界重规划／重定时与外部冻结，本轮直接读取相关段；按预印本对待。

因此，不同场景、分层架构、接入 G31、小网络或一般局部修复都不足以单独支撑创新。LT-2 把研究主线放在动作条件化的有限盘复用链、跨 owner 可执行条件、边界选择／扩张和预算内联合求解，要求对强匹配、滚动MPC及通用LNS做机制级对照。这只是有待检验的假设，不能保证创新最终成立或期刊录用。

完整书目信息和对应 DOI／arXiv 见主计划 §15。

## 7. 主要阅读清单与范围

以下是实际阅读与定向审查的主要文件，不代表完整逐行覆盖：

- 完整读取或读取完整相关最新章节：指定审阅入口、发布与复现说明、P5_HANDOFF_DIAGNOSTIC、NOVELTY_LEDGER §§25—29、LONG_TERM_PROGRESS 的012—016与发布段。
- LT-1 总纲的目录及 P5—P7／自主推进相关段、CURRENT_REVIEW_AND_START_POINT 开头；旧起点仅作历史，不据此认为当前 P1 尚未实现。
- 定向源码：`circulation_notifications_impl.hpp`、`circulation_online_impl.hpp` 相关 online advance 段；`circulation_session_binding.hpp` owner observation／命令序列化相关段；`event_protocol_control.py`；`protocol_control.py` 的客户端、路由、预测与重试；`p5_handoff.py`；`original_workload.py` 输入构造主要段；`native` 构建脚本与CMake目标；P5测试文件。
- 已保存证据：original24 五策略 run／request账本／delivered views／input；P5 8域 assessment／分支计数；407 JUnit；作者最终审计脚本前段用于了解证据结构。本轮独立复算执行的是本包脚本，**没有执行作者整个 audit.py**。
- 发布验证读取全部清单项用于散列，C++ 编译器读取必要编译依赖。这两者都不等于人工语义审阅所有文件。

## 8. 复查入口

本包 `evidence/recompute_and_probe.py` 只读原仓库、写外部新 JSON。需要原始完整仓库和其 Python 依赖，输出文件须不存在：

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python evidence/recompute_and_probe.py \
  --repo /path/to/G31_ICS_review \
  --output /path/outside/repository/recomputed_new.json
```

代码和日志中的本轮环境路径为实际运行记录，不是要求用户使用相同路径。脚本不复跑 Windows native，不下载依赖，不修改冻结源。`files_hashed_before` 与 `hashed_source_changed=[]` 覆盖所列5个关键源文件；完整发布身份另见 `manifest_verification.json`。

最终建议：执行同包 LT-2，尽快从控制补齐进入真耦合／强参考／主方法，性能与物理合同诊断并行。不要再把新增审计和测试数量当作未来几周的主要科研成果。
