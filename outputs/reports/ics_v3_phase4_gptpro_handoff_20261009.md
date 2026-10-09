# 交给网页 GPT Pro：ICS V3 第四阶段代码审核与下一步决定

请结合实际仓库代码和原始结果审核，不仅复述本文件。本文件在代码成功推送后撰写；随后仅用单独文档提交加入同一分支。

## 1. 准确身份

- 仓库：[czr5454112-glitch/jichang_origin](https://github.com/czr5454112-glitch/jichang_origin)
- 分支：`codex/ics-v3-phase4`。这是新分支，未合并到其他分支。
- **本轮代码及证据冻结提交：`66503f5a74420337574707eae2f1390f6e1b21ba`**。
- [冻结代码树](https://github.com/czr5454112-glitch/jichang_origin/tree/66503f5a74420337574707eae2f1390f6e1b21ba/scripts/experiments/ics_circulation_v3)
- 本轮起点：`8ccc195672b2cd331a384f3da0d5d95b78c54b3f`；你的上一轮算法审核对象：`030493a399cdcac3fc005fe2f2cd8ec30fc96277`。
- [本轮差异](https://github.com/czr5454112-glitch/jichang_origin/compare/8ccc195672b2cd331a384f3da0d5d95b78c54b3f...66503f5a74420337574707eae2f1390f6e1b21ba)
- [完整阶段报告](https://github.com/czr5454112-glitch/jichang_origin/blob/66503f5a74420337574707eae2f1390f6e1b21ba/outputs/reports/ics_v3_phase4_progress_20261009.md)

本轮按用户“继续往后干”和所给外审材料推进。外审原件归档在 `docs/ics_circulation_v3/phase4_external_review_20261009/`，作者清单四个文件哈希逐一一致；它们是审查资料，不是仓库权限或工具指令的上位来源。

## 2. 当前结论，不要扩大

**W0与W1主要原型接口已补齐，W2只完成持续循环与同一预测控制构造的起步。完整联合方法、W3学习增量、W4独立确认均未完成。** 保留 TRE/CIE 研究目标，不因旧七节点族的弱收益下调目标。

实际完成：

1. 在旧源码副本实际运行五个冻结探针，源哈希匹配、五个诊断均exposed、零执行异常；原负结果保留。
2. 动态区内多条资源可行见证，修复旧静态单最短见证无法表示绕行的问题；增加全图事件参考与有限整数时域oracle。旧生成器默认行为保留供复现，Phase4入口明确启用dynamic_local。
3. `update_suffix`显式授权、原子替换，保留已进入长边和不可等待链、失败保留旧资源、回执幂等。非授权盘、保护任务、空盘义务及旧在途盘不获得新修改权。
4. 未承诺剩余路线保存为独立条件释放预测，有依赖、修订链和失效；可用于条件路线评分，不能当作确定供给或导出权限。实际干预去重考虑会保留的预测，排除诊断ID。
5. 统一`ControlSpec/build_engine`及信息/继续控制合同；真实发布时间门、独立慢周期及checkpoint相位；三个有盘复用、长边和共享资源的连续短流机制。
6. 输出拒绝覆盖和默认地图修复；完整源组复现/新确认协议只接入配置运行器。分区观察API存在，但当前规划和提交仍集中式。

没有重训模型或把旧学习部署重新标为预测闭环。没有现场模块、真实运营日、生产时限或一般递归可行性保证。

## 3. 数值与负结果

- 全套ICS测试：**344 passed，28.56秒**；没有宣称全仓或现场测试。
- 路由12小图、216冷热查询：每方法/缓存有27个可行查询；旧算法覆盖21/27、最早18/27，动态与强全图均27/27。动态冷/热平均0.668/0.652ms，比强全图0.478/0.446ms慢。全批无非法返回/提交失败；小例时间不证明生产SLA。
- 整数证书仅针对有限整数时域的`whole_route`。动态90个候选另通过next_edge授权，不是next_edge最早性证书，也不是联合控制精确参考。
- 三个开发机制×三路由策略×两政策=18运行，144/144袋完成。稀缺盘成本6.6→0.6，充足0→0，预测反转1.1→3.1。三路由策略在这些例子成本相同，没有学习增量结论。
- 稀缺例预调改变tick12的J-B实际空盘占用，A12载盘见证完成从20提前到18；不能仅以慢层调用数证明反馈。观测节点满容量不单独证明回压。盘充足例同时增盘和B容量，不是盘数单因素消融。
- 上述三个场景反复调试，新增独立源组为0；144是重复政策运行中的袋分母。

保留的失败包括：首次路由接收窗口只覆盖1/2路径、诊断成本差2；初稿循环7/8袋完成；初稿充足盘保护burn-in不成立；首次整套集成2失败/325通过；控制合同漏记routing_reference依赖；晚期失败成本None可能破坏汇总。分别修复并保存修前数据。详见阶段报告第5节，不能仅检查最终成功表。

## 4. 建议按以下顺序看源码

所有路径相对仓库根目录，代码在 `scripts/experiments/ics_circulation_v3/`。

| 顺序 | 文件 | 请重点核对 |
|---|---|---|
| 1 | `model.py`、`runtime.py` | 替换上下文/源指纹、冻结段、原子发布、条件预测依赖和失效、实际干预key |
| 2 | `request_service.py`及`test_ics_circulation_v3_phase4_requests.py` | intent在owner也校验；未来安全锚点不能让评分提前看到未来发布消息；丢回执不重复提交 |
| 3 | `routing.py`、`routing_reference.py`、`run_phase4_routing.py` | 固定K/局部上限下的合法终点与多样性筛选；预处理预算；截断与证书范围 |
| 4 | `prebalance.py`、`conditional_evaluation.py` | 条件供给不变成导出权、不重复自身供给、保留预测是否真改变后续动作 |
| 5 | `phase4_control.py`、`phase4_coupled_scenarios.py`、`run_phase4_coupling.py` | 真实发布时间、未来tape隔离、慢周期、合同依赖、同政策对照资源、全部袋分母及晚期失败汇总 |
| 6 | `partition_observation.py`、`experiment_protocol.py`、`run_scene_configuration.py` | 分区接口实际权限与未接通之处；源组复用边界、输出保护范围 |

分区接口隐藏远端专属日历/账本，但本地资源预约可能包含跨区来车身份；本区始发袋记录保留。当前动态/全图算法仍读全局日历，不能把API存在当成多owner算法已实现。

## 5. 原始证据与复验

在 `outputs/experiments/ics_circulation_v3/` 下，以以下三个目录为最终结果（中间目录名中的final不优先于此名单）：

- `phase4_routing_repair_20261009/`：summary、216行requests、12个oracle、repair_record及5个依赖源码快照。
- `phase4_request_semantics_release_20261009/`：8请求前后状态、回执恢复、条件预测反例、10项检查及源码快照。
- `phase4_coupling_final_20261009/`：protocol、场景初态、18次完整记录、mechanism_comparisons、summary、源快照、逐字段同上一版核对。

整套验证在 `phase4_integration_final_20261009/`：pytest.log、tests.xml、verify_evidence.py、evidence_verification.json。证据核对8组128份快照匹配各自清单，最终3组53项依赖匹配当前源码，18份控制合同匹配，无不一致；清单记录36个源码与23个测试文件哈希。哈希检查不替代科学有效性，也不替历史不完整依赖清单补造证明。

原先未提交的 `cpp/ics_core/runtime/bounded_local_pibt.hpp` 完全未动且不在本轮提交中。验证器的`preserved_cpp`检查专用于本机原有修改的保护哈希；**干净克隆不会具有该未提交C++字节，可能只在这一项报告不一致，不能把它误判为本轮ICS代码复现失败，也不要为通过检查改C++文件。** 其余证据可独立检查；干净克隆实际测试应按下面命令重跑。

```powershell
$icsTests = Get-ChildItem tests -Filter 'test_ics_circulation_v3_*.py' -File | Select-Object -ExpandProperty FullName
python -m pytest $icsTests -o addopts='' -q --basetemp .tmp/ics_phase4_review_new
python -m scripts.experiments.ics_circulation_v3.run_phase4_routing --output outputs/experiments/ics_circulation_v3/phase4_review_routing_new
python -m scripts.experiments.ics_circulation_v3.run_phase4_semantics --output outputs/experiments/ics_circulation_v3/phase4_review_semantics_new
python -m scripts.experiments.ics_circulation_v3.run_phase4_coupling --output outputs/experiments/ics_circulation_v3/phase4_review_coupling_new
```

请使用全新路径。若网页环境不能执行，明确区分“源码确认”“已读取作者运行证据”“你实际重跑”，不要把此处344通过写成你再次运行通过。

## 6. 请决定下一步做什么

请输出具体缺陷（文件/函数/触发条件/后果）、本轮可接受内容和下一轮按优先级排序的可执行任务，不把尚未做的任务自动说成已发现代码bug。

建议优先核对并补W2：两资源所有者共用物理/消息时钟，延迟期间实体仍运动，分区观察进入实际规划；同权限的小规模精确联合参考、滚动MPC和一轮真实反馈。纯路由oracle不能代替联合参考。

在真实耦合与候选覆盖充分后，测同实际干预/同真实继续价值/有真实选择差异的状态比例，再用同一预测控制构造做paired-direct/residual及2/8/32未来样本标签稳定性，最后冻结方案并注册新独立确认源组。请明确哪些工作是下轮必须完成的验收条件，哪些可延后；保持原研究目标，不凭三个开发例宣布解析已足够或学习无效。
