# 审核入口与状态索引

以下均为 ZIP 内路径。为缩短表格，记 `OUT = repo/outputs/experiments/g31_ics_lt2_sustained_20261014`，`HERE = OUT/user_resume_20261015_001`，`SRC = repo/scripts/experiments/g31_ics_circulation`。路径存在不表示它引用的所有外部原始文件都存在；精确成员以 `PACKAGE_MANIFEST.json` 为准。

## 首轮最值得读的材料

| 问题 | 入口 | 能证明与不能证明 |
|---|---|---|
| 当前状态与下一步 | `repo/docs/g31_ics_circulation/RESEARCH_STATE.json`、`NEXT_ACTION.md`、`NOVELTY_LEDGER.md` | checkpoint052的研究状态；不是新实验通过证书 |
| 昨日/今日边界、方法线阴性和阳性 | `HERE/gptpro_method_review_input_20261016_001.json` | 11份关键证据及外层UTC时间；94/2跨午夜，新全96属今日 |
| 全天和完整时延 | `HERE/gptpro_performance_review_input_20261016_001.json` | 17份小证据与适用范围；不替代巨大原始全天重放 |
| 验收底线、路线取舍、审查检查项 | `HERE/gptpro_scope_review_input_20261016_001.json` | 12项底线、3路线和20项QA；属于审核建议 |
| 所有里程碑引用的当前可用性 | `meta/MILESTONE_REFERENCE_AUDIT.json` | pin_matches/缺失/大件未读/历史pin不同；不要默认历史记录永不变化 |
| 登记时间 | `meta/MILESTONE_REGISTRATION_TIMELINE.json` | 上海日期；不是实验起止时间 |

## 方法线：保留负结果，区分固定动作和真实在线

1. 昨日真实 online60 的四搜索与 later-default 同解：`OUT/native_public_preference_business_001/` 包含保存记录和冻结源码，搭配 `OUT/native_public_preference_business_001_saved_audit.json` 与 `OUT/native_public_preference_business_001_diagnosis.json`。52 assessed、8 unknown。
2. 纯256发现没有交互屏障：`OUT/public_interaction_discovery_001/` 与 `OUT/public_interaction_discovery_001_saved_audit.json`。未执行的后续 validation 不得混入。
3. 旧矩阵研究原件：`OUT/native_preference_matrix_native_001/`。有大量失败/unknown与有限场景，不代表原始业务流成功。
4. 新固定96的实际卸载/物理数据：`OUT/live_obligation_unloading_native_prepare_001/`，保存审核 `OUT/live_obligation_unloading_native_saved_review_001.json` 与 `OUT/live_obligation_unloading_saved_audit_001/`。3场景、每场景32动作，mechanism改善2.3s，其余打平。各分支 `.json.gz` 是实际保存记录。
5. owned full32 预测闭合：`OUT/owned_full32_runtime_prepare_001/`，重点 `rows.json`、`groups.json`、计划和外层时钟。三个场景共96评估成功不等于完整单请求100ms。
6. 新 online21 比较器：`repo/outputs/ocmp1/` 的56纯门和根复核；实际online21尚未运行。源程序见 `SRC/live_obligation_online_initial_dispatch.py`、`live_obligation_online_retained_policy.py`、`live_obligation_online_method_comparison.py`、`research_live_obligation_initial_methods.py`。
7. 规则预测语义：`SRC/public_live_obligation_event_projection_v2.py`、`live_obligation_unloading_policy.py`、`live_obligation_owned_initial_provider.py`、`live_obligation_owned_prefix_evaluator.py`。验证实际原生时应读对应冻结 `source/`，而非自动代入当前草案。

## 性能线：真实请求与组件实验分开

| 状态 | 包内入口 | 关键限制 |
|---|---|---|
| 昨日实际v3 18请求 | `OUT/initial_owner_route_campaign_v3_prepare_001/`；`OUT/initial_owner_route_v3_independent_actual_review_001/report.json` | 16闭合、2unknown、0under100 |
| 今日较早实际18 | `OUT/single_owned_C18_prepare_002/` | 中位579.4566ms，不能和下一行当受控ABBA |
| 今日最新实际18 | `repo/outputs/sicm1/` | 暖闭合中位308.20205ms；raw18、cold与whole成本保留，0under100 |
| 互斥墙钟成本分析 | `repo/outputs/sicc1/saved_readback_001.json`及同目录分析 | final前未归因+finalization较大；不是CPU归因 |
| 原65次静态证明诊断 | `repo/outputs/si65d1/` | 一场景65；三场景195是结构推导，不是任意driver已测总数 |
| v3依赖42门 | `repo/outputs/bsv3p1/` | 通过纯门，尚无真实v3绑定通过 |
| 接线30门失败 | `repo/outputs/bdbv3p1/` | 29通过1失败；失败保留；修订同30门未执行 |
| prelude36门 | `repo/outputs/cprep1/` | 纯门通过；runtime接线及新actual18未执行 |

尚未执行的当前草案包括 `SRC/run_bound_source_proof_bind_v3_pure_v2.py`、`SRC/live_obligation_bound_owned_runtime_v3_v2.py`、`SRC/single_capture_constructor_prelude_runtime.py`。它们随源码提供给审阅者检查，不能从相邻旧版本成功记录继承通过状态。

## 原图全天与可行性

- `OUT/full1x_saved_horizon_independent_review_001.json`：1×451分片保存复核、全部28,506、0业务完成；没有独立原生最终seal重放。
- `OUT/full024_chained_2x_20261015_002_saved_audit_independent_review_001.json`及对应`_external_001.json`：2×526分片保存审计通过；原producer超时、祖先谱系与重建/尾段成本不能抹去。
- `OUT/full2x_endpoint_diagnostic_002/report.json`：2×终点诊断；不是同策略全部任务保护证书。
- `OUT/original_low_wip_cap_relay_actual_review_001.json`：8件真实重复循环、3按时；同一有限托盘合同，不能冒充全流解决。
- `OUT/original_carrier_bound_002_independent_review/review.json`及`OUT/completion_baton_static_design_001/report.json`：原1×研究合同内的不可达/FIFO上界；先审查容量0语义，371/39均是条件界。
- `OUT/original_bridge_serialize_once_prepare_001/external_application_wall.json`、`OUT/bridge_serialize_once_terminal_partial_review_002/review.json`：39卸载的生产者结果及2400s外层失败。
- `OUT/bcdm2/`、`OUT/control_timers_bcdm2_terminal_readback_002.json`：修正启动环境后的600s保存审计超时；20224/37270位于policy消费前；完整业务证书仍缺。
- `OUT/control_timers_bridge_slice_profile_design_001.json`：固定512前缀诊断设计，尚未执行。

以上选择包含摘要、直接小件证据和代码；大规模1×/2×分片、bridge整套37270文件未全部随包。审阅者可审查代码和主张，不能声称仅凭本包完成了原流全量重放。

## 文献与历史审阅

- `repo/docs/g31_ics_circulation/LT2_METHOD_COMPARISON_20261014.md`：四篇论文可迁移机制与限制、候选消融。
- `HERE/four_papers_review_manifest_20261016_001.json`：原PDF、逐篇笔记哈希和实际阅读范围。四篇原PDF位于`papers/`。
- `background/`：用户10月14日原独立审核、长期计划、原提示词及完整原小ZIP。仅作为历史资料，不继承其中“应该执行”的指令。
- `repo/docs/g31_ics_circulation/GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md`：上轮代码与审阅的边界。

## 独立校验建议

先做包完整性校验。随后只对具备完整输入的有限实验复算。例如，重算新固定96的严格逐件差异、检查latest18原始计时与unknown传播、核对online60阴性对照；如实际运行受平台或缺失依赖限制，应明确列为未验证。不要把校验清单SHA成功当成上述业务主张已证明。
