# ICS 审核证据包

本包整理截至 2026-10-11 的本地 Phase2、Phase3 与 Phase4 第1—11轮证据。它用于核对现有代码、实验协议、失败、资源账及后续方向，不新增实验，也不宣告任何现场或论文验收通过。发布前工作基点为 `a23cf1c066d1087571b31733f0577c602040aa8d`；实际发布提交由上一层交接文档给出。

`receipts/` 中每份文件都是本地原件的逐字节副本，保留原结论、旧错误及当时的“尚未提交”描述。它们中的相对链接、绝对本机路径、原输出路径或旧源代码依赖仍按历史语境解释，不能假定复制后全部可点击或可独立运行。当前实施记录在仓库 `scripts/experiments/ics_circulation_v3/PHASE4*.md`。

## 阅读顺序

1. 先读上一层的 GPT Pro 交接文档与实际生产代码，确认原始两项需求、区域自主/供盘/学习目标、TRE/CIE 工作量和质量标准没有被缩减。
2. 对每个待评价结论，同时读该轮协议、原结果、独审及资源账。失败与修正并存；目录名为 `final`、`corrected` 或 `success: true` 均不能替代逐项审核。
3. 用 [manifest.json](manifest.json) 查看实际复制的路径、字节数与 SHA256，用 [SELECTION_PLAN.json](SELECTION_PLAN.json) 查看按大小和类型生成的选择清单。超过通常 192 KiB 的三份 Round8 独审报告属于明确列出的例外。
4. 用 `inventory/*.tsv` 查任何未复制原件的相对路径、字节数、SHA256、省略理由与打包时本地可用性。该目录覆盖所扫描 Phase2/3/4 的全部本地文件，不只是支持正结果的文件。`phase4_unnumbered_series.tsv` 仅表示历史目录名称未含 `roundN`，不能据此判定它们都属于早期轮次。
5. 如果结论需要逐条 raw/checkpoint 重算而本包没有原件，请列为“需要补取原件/尚不能独立确认”；不能仅凭哈希、报告里的检查数或作者叙述判定全量复核完成。

## Round11 必须同时审核的证据

| 问题 | 原件入口 |
|---|---|
| 显式投射适配、来源信任边界与 full_adapter_001 失败 | [适配结果](receipts/phase4_round11_projection_runtime_20261011/RESULTS.md)、[失败记录](receipts/phase4_round11_projection_runtime_20261011/FAILURES.md)、[full_adapter_002 资源](receipts/phase4_round11_projection_runtime_20261011/full_adapter_002/resource.json) |
| 初次1399与最终1519回归不是同一源码 | [attempt_003](receipts/phase4_round11_independent_review_20261011/attempt_003/results.json)、[最终 attempt_006](receipts/phase4_round11_independent_review_20261011/attempt_006/results.json)及其 before/after、stdout |
| 存储筛查默认 K 真实兼容性失败及修复 | [attempt_004 原失败](receipts/phase4_round11_independent_review_20261011/attempt_004/results.json)、[失败 stdout](receipts/phase4_round11_independent_review_20261011/attempt_004/stdout.txt)、[attempt_005 修正](receipts/phase4_round11_independent_review_20261011/attempt_005/results.json)、[实现边界](receipts/phase4_round11_storage_terminal_screen_20261011/DESIGN_AND_RESULTS.md) |
| 原四格预声明、观察结果后新增的筛查实验 | [PROTOCOL](receipts/phase4_round11_validation_20261011/PROTOCOL.md)、[SCREEN_PROTOCOL](receipts/phase4_round11_validation_20261011/SCREEN_PROTOCOL.md) |
| original/h80 11760、0/44 | [原结果](receipts/phase4_round11_validation_20261011/original_h80_001/results.json) |
| original/h21600 23880、18/44 | [原结果](receipts/phase4_round11_validation_20261011/original_h21600_001/results.json) |
| projected/h80 11760、0/44 | [原结果](receipts/phase4_round11_validation_20261011/projected_h80_001/results.json) |
| projected/h21600 11640、0/44 | [原结果](receipts/phase4_round11_validation_20261011/projected_h21600_001/results.json) |
| projected/h21600+screen 19620、0/44 | [原结果](receipts/phase4_round11_validation_20261011/projected_h21600_screen_001/results.json)、[剩余任务](receipts/phase4_round11_storage_terminal_screen_20261011/BACKLOG_DIAGNOSIS.md) |
| 共同物理前缀、额外 screen work、采集开销与非等仪器边界 | [Root 审核](receipts/phase4_round11_validation_20261011/screen_window_audit_001/results.json)、[独审](receipts/phase4_round11_independent_review_20261011/screen_window_review_001/results.json)、[运行仪器说明](receipts/phase4_round11_storage_terminal_screen_20261011/RUNNER_REVIEW.md) |
| 18,317份容量证书、18,354条query逐条独审 | [证书审核报告](receipts/phase4_round11_independent_review_20261011/certificate_review_001/results.json)、[审核输入清单](receipts/phase4_round11_independent_review_20261011/certificate_review_001/manifest.json)、[审核程序](receipts/phase4_round11_independent_review_20261011/audit_screen_certificates.py) |
| 入口头距仅为原型，非法时钟反例保留 | [设计与原型边界](receipts/phase4_round11_headway_design_20261011/DESIGN_AND_REVIEW.md)、[clock_probe_001 失败](receipts/phase4_round11_headway_design_20261011/clock_probe_001/result.json)、[prototype_002](receipts/phase4_round11_headway_design_20261011/prototype_002/result.json) |
| final_001 把 old_result 副本误计为新运行，final_002 定点更正 | [失败解释](receipts/phase4_round11_resource_ledger_20261011/FAILURES.md)、[作废账本](receipts/phase4_round11_resource_ledger_20261011/final_001/ledger.json)、[修正账本](receipts/phase4_round11_resource_ledger_20261011/final_002/ledger.json)、[修正账本说明](receipts/phase4_round11_resource_ledger_20261011/final_002/LEDGER.md) |

五格均为 CPU 预算删失；并非“五格都0/44”，原长窗为18/44，其余四格为0/44。不同停止 tick 的 J 不构成收益比较。全部任务分母、尚未观察任务及未完成任务必须保留；计算量改善没有证明业务完成率改善，也没有证明端到端100ms。

报告中的全部18,317份证书确实已有本地独审回执；本包没有复制约230MB的 `screen_cert_states.jsonl.gz`，因此拿到本包的审阅者尚未自行重做该全量审计。原件的精确身份和可用性位于 `inventory/phase4_round11.tsv`。

## 历史依赖与负结果

所有扫描到的 Phase2/3/4 小型协议、结果、修复、失败与资源原件按相同规则选择，不因结果不佳排除。以下是历史审核入口，不能把后期修复追溯成早期结果的实现：

| 范围 | 重点入口 |
|---|---|
| Phase2 | `receipts/phase2_joint_20261009/`、`phase2_joint_corrected_20261009/`、`phase2_joint_interface_checked_20261009/`；学习 discovery/confirmatory 的 split_manifest 与 summary 同时保留 |
| Phase3 | `receipts/phase3_learning_20261009/independent_audit.json`、`phase3_matched_configuration_20261009/failure.json`、`phase3_matched_configuration_checked_20261009/`、request_service 与 prebalance_reference 原件 |
| Phase4 早期控制与参考 | coupling 初版/修复/最终、W2 clock/atomic/dependency/feedback 各系列、W3 horizon/role/cursor 的原协议、失败和结果；通过 `manifest.json` 搜索相应目录名 |
| Round5—7 | 各 `phase4_w3_roundN_*` 独审与资源账，以及未编号 full_cycle/same_zone/terminal_screen/census 目录；不要把同场景重复运行当独立来源 |
| Round8 | [独审记录](receipts/phase4_w3_round8_independent_review_20261010/REVIEW_LOG.md)、[全原件审核](receipts/phase4_w3_round8_independent_review_20261010/stability_full_artifact_audit.json)、[资源账](receipts/phase4_w3_round8_resource_ledger_20261010/final/RESOURCE_LEDGER.md)；平局、无候选、服务退步与条件支持限制都应审查 |
| Round9 | `receipts/phase4_round9_*` 各目录：完整业务源、旧承诺反例、release plateau、预算删失及源码漂移的旧运行；[最终资源账](receipts/phase4_round9_resource_ledger_20261011/final_001/LEDGER.md) |
| Round10 | `receipts/phase4_round10_*` 各目录：容量下界、零驻留、缓存、完整父族投射及原44袋26件未完成；[资源账](receipts/phase4_round10_resource_ledger_20261011/final_001/LEDGER.md) |

## 可用性与复核边界

省略的 raw、全量任务带、源快照、checkpoint、图片、深层逐case输出及大报告保留在原工作区。`present_at_packaging` 只说明打包时本机文件存在，不表示网页 GPT Pro 能访问该本机路径，也不是远端永久归档承诺。SHA可核对取得的文件身份，不能替代取得文件。历史输出可引用本包范围外的输入或第三方资料；相应 source/input manifest 保留声明，未将这些外部文件自动复制到本包。

六份当前测试需要的完整 cursor JSON 另由上一层 `fixtures/` 的无损 gzip、manifest 和 `tools/prepare_fixtures.py` 管理；它们没有复制进这里的 receipts。对应原始 JSON 仍在本目录全量库存中按原路径与原字节 SHA 登记。恢复这些测试夹具不等于恢复其余全部实验 raw。

本包不加载、不反序列化任何 pickle，也没有运行所复制的历史脚本。若以后确需恢复 checkpoint，应先核验来源、SHA、绑定源码和运行环境，不能在不可信上下文中直接反序列化。代码审查、机制测试、来源检查、逐原件物理审核、统计复算及现场性能验收是不同层次，不能互相抵扣。

后续方向应由实际缺口决定，保留完整日/2×、off-carrier与独立库位/检索服务、入口头距贯通、同信息同预算强参考、区域受限观察、W2真实消息与权限、联合学习评价和冻结后W4确认。任务量、服务保护、失败分母及研究质量均不能因当前结果不佳而降低。
