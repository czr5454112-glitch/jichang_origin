# CIE 稿件主张修订清单 v2

本清单覆盖 `cie_claims_revision.md` 中与 Feng CIE-DH、新随机析因、定向消融、
J2/M3 和南宁 2× tail 相关的口径。每项主张都使用以下等级之一：
`SUPPORTED`、`SUPPORTED_WITH_CONDITION`、`MIXED`、`NEGATIVE`、`DORMANT`、
`NOT_IDENTIFIED`、`SOURCE_NOT_RECOVERED` 或 `NOT_APPLICABLE`。

## 1. 全局强制口径

1. `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED` 与
   `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` 永不合并。前者是原论文实测，
   后者是 `SEMANTICALLY_PARTIAL_RECONSTRUCTION`。
   南宁报告别名 `FENG_PAPER_ENV_CIE_DH_NANNING_PORTED` 进一步定级为
   `PORTED_SEMANTICALLY_PARTIAL_RECONSTRUCTION`，不得反向归因给原论文。
2. 不得称可执行版为 `faithful`、`source-exact`、原实现或 Feng-native exact。
   `FENG_SOURCE_EXACT_CIE_DH` 的状态始终为 `SOURCE_NOT_RECOVERED`，除非未来
   找到原作者源码、参数和状态机。
3. 历史实测是原 CIE-DH 效果的唯一主表性能锚点；可执行版只进入明确分隔的
   次级诊断表，用于可复查的机制、灵敏度、负载和跨图外推，不能覆盖历史值。
4. 公共执行器 `CIE_DH_COMMON_EXECUTOR_ADAPTED` 只进入副表/附录，不能改名
   后放入 Feng 原论文主基线行。
5. 所有正式 2× THT 为 `N/A`。不得报告 survivor timing、共同成功 cohort
   时延或由候选自己的 release timing 补齐的 THT。
6. G31 相对 HCA 的原始正式科目是明确主结论；G31 相对 CIE-DH、Tarău 和
   内部组件的证据按协议、地图、负载和指标逐项报告，不汇总成全面排名。
7. 不把偏乐观可执行 CIE-DH 当成“更忠实”，也不人为加慢它来贴合 Table 5.3。
   历史偏差本身就是复现等级限制。
8. 南宁 2×最大迟到的显著恶化必须与完成量改善同表保留。
9. J2/M3 接口隔离、E2 事件等价和 P2 dormant 均不得写成性能贡献。
10. 负结果触发停止或缩小主张，不触发新增 scorer、guard、模式、排序层或
    结果后权重。

## 2. 主张账本

| ID | 等级 | 可发表主张 | 必须同时写出的边界 | 主要证据 |
|---|---|---|---|---|
| C1 | `SUPPORTED` | G31 相对 Feng 原生 HCA 在 map2、南宁 1×完整人口 mean/P95/P99/max 均更低；2×固定时域 G31 两图均完成 57,012，HCA 分别完成 56,917、39,063 | 不把 2×完成量写成 2× THT 改善 | `cie_manuscript_patch.md`; `cie_baseline_comparison.md` |
| C2 | `SUPPORTED` | 原 Table 5.3 CIE-DH 完整人口 min/mean/P95/P99/max 为 213.3/265.592131/336.9/384.595/517.2 s，按每件 raw bag 的 `sum(E-D)` 统计；印刷的 HCA min/mean/max 3.13/3.96/5.98 min 均低于 CIE-DH 3.56/4.43/8.62 min | 历史行不可执行，只覆盖 map2 1×；这是原论文中 CIE-DH 作为较弱对照凸显 HCA 的水平锚点 | `feng_cie_dh_table53_audit.csv`; reconstruction manifest/report |
| C3 | `SOURCE_NOT_RECOVERED` | 原作者 CIE-DH 源码、数值系数和完整状态机未恢复 | 不生成任何 source-exact 数值或 “native pass” | `feng_cie_dh_source_search_addendum.md` |
| C4 | `SUPPORTED_WITH_CONDITION` | 独立旧 Java 可执行 CIE-DH 重构完成 28,506/28,506 bags、43,603/43,603 segments，使用恢复的 shared-D 公式 | 仅为 `SEMANTICALLY_PARTIAL_RECONSTRUCTION`，只进次级可执行诊断表；不能称忠实、原实现或 source-exact | `feng_paper_env_cie_dh_reconstruction_report.md`; `feng_cie_dh_reconstruction_spec.md` |
| C5 | `NEGATIVE` | 可执行版相对历史实测 mean 快 10.124%、max 快 36.968%，历史 numerical shape 未复现 | 这是偏乐观/尾部不足的 fidelity 限制，不是 CIE-DH 性能提升 | `feng_cie_dh_table53_audit.csv` |
| C6 | `SUPPORTED_WITH_CONDITION` | 九格预冻结 penalty envelope 全人口完成，mean/P95/P99/max 仍整体快于历史测量 | 只说明 fidelity 缺口对系数包络稳定；不得选择最接近或最快格，也不升级身份 | `feng_cie_dh_sensitivity_envelope.csv`; reconstruction report |
| C7 | `SUPPORTED_WITH_CONDITION` | 公共执行器 CIE-DH 能隔离路线策略；静态 1,510/1,510 OD 路径一致 | 执行器机械不同，完整人口差不是 route-only 效应；不能替代 Feng 历史基线 | `feng_common_executor_bridge_audit.md` |
| C8a | `MIXED` | 最终 SHA 的 map2 临界曲线中，G31 在 1.00–1.75×完整人口 mean/P95/P99/max 逐格低于语义部分 CIE-DH；2×两者均完成全人口，但 CIE-DH 准时率 98.89% 对 G31 53.03%，总 backlog AUC 1.563e8 对 2.935e8 bag-s | 这是不同原生执行器的端到端 partial-reconstruction 次级诊断；2× THT N/A，不能汇总成全面胜负或放回原 CIE-DH 主基线行 | `cie_critical_load_curve_v2.md` |
| C8b | `NOT_IDENTIFIED` | 2026-09-05 关机检查点为 166/180：map2 全部完成，南宁 ported DH 仅 16/30；完整随机跨图/跨负载方向仍只能在最终 SHA、每格 10/10 paired seeds 和全矩阵 180/180 strict normalized cells 门通过后陈述 | 180 格=2 maps×3 loads×10 seeds×3 methods；map2 partial 与南宁 ported 均为 secondary executable diagnostics；当前 1× 7 seeds、1.75× 4 seeds 和 2× 5 seeds 只作检查点，不得进入最终胜负 | `cie_external_baseline_checkpoint_20260905.md`; `cie_external_baseline_robustness.md` |
| C9 | `MIXED` | 2×2 随机析因显示 potential 和 dynamic state 的效应及交互随地图、负载变化 | 不写成两个独立、跨图稳定增益；2× THT N/A | `cie_random_factorial_full.md` |
| C10 | `MIXED` | 12/12 定向 2×必需消融格执行并通过完整性门；部分组件在南宁容量上必要、在 map2 中中性或负向 | 不给 Q/I/ws 分别授予双图稳定贡献 | `cie_targeted_ablation_report.md` |
| C11 | `DORMANT` | `FULL_MINUS_WC` 因零 wc activation opportunity 未运行 | 不人为改变负载、节点容量或参数来激活 | `cie_targeted_ablation_report.md` |
| C12 | `SUPPORTED` | J2 timing 与 M1/M3 priority rule 已在接口和微型测试中可识别地分离，默认 G31 保持 J2+M3 | 这不是性能收益，完整双图逐臂实验仍缺 | `cie_j2_m3_interface_isolation.md` |
| C13 | `NEGATIVE` | 南宁 2× P1D1−P0D0 最大迟到 +2,555.10 s，CI [1,027.27, 4,083.66]，9/10 seeds 恶化 | 同时写 10/10 seeds 完成更多；不以 mean 或完成量覆盖 extreme tail | `nanning_2x_tail_risk_audit.md` |
| C14a | `SUPPORTED_WITH_CONDITION` | 20/20 最大迟到 bag 均为 DIRECT、source wait=0，local wait 的 100% 为 junction queue；最差 1% 人口在 P0D0/P1D1 分别覆盖 25/32 个 OD，top-5 占 48.4%/43.4% | 支持 `EXPECTED_CAPACITY_TRADEOFF_WITH_JUNCTION_WAIT_DOMINATED_TAIL`，不支持源端准入转移或少数 OD 特例 | `nanning_2x_tail_risk_audit.md`; `nanning_2x_worst_bags.csv` |
| C14b | `NOT_IDENTIFIED` | seed 层最大等待变化与最大迟到变化相关 0.952，20/20 个 detail replay 已通过身份与聚合结果校验 | 原运行无 decision/hold trace；bag-result replay 不能定位 priority starvation、route oscillation、具体节点/scorer 或首个策略分叉，保留 `NOT_IDENTIFIED_NO_TRACE_REPLAY` | `nanning_2x_tail_risk_audit.md` |
| C15 | `NOT_APPLICABLE` | 所有正式 2× population latency/THT | 只报告固定分母 completion/on-time/tardiness/backlog/time-to-X | 所有 formal 2×表 |
| C16 | `DORMANT` | P2 正有限容量机制 | 没有机场/制造商/原图可验证容量，不进入主要创新 | v1 claim ledger; activation audit |

## 3. 数值与措辞修订

| 旧措辞 | v2 必须改成 | 原因 |
|---|---|---|
| “Feng-native CIE-DH 因源码缺失只能 N/A” | “source-exact 轨仍缺失；另有可执行、语义部分的旧 Java 重构” | 缺源码不再阻止可执行 baseline |
| “Feng 论文环境下的忠实 CIE-DH 重构” | “Feng 论文环境下的语义部分 CIE-DH 重构” | 未识别节点交接和系数，且历史 tail 明显不匹配 |
| “G31 超过原 CIE-DH” | “历史行给出描述性参照；可执行重构比较按协议和负载逐项报告” | 历史实现不可执行，partial 重构不是原实现 |
| “随机实验验证 G31 对外部 baseline 的优势” | “完成门通过的 paired 表逐项报告 W/T/L 与 CI；未完成或混合方向不汇总为优势” | 避免从新指标或筛选 seeds 制造胜利 |
| “potential 与 dynamic state 都有独立贡献” | “二者存在地图和负载相关主效应与交互” | 南宁 1×与2×存在反向/拮抗证据 |
| “南宁 2×总体更好” | “完成能力改善与最大迟到恶化并存” | 最大迟到 +2,555.10 s 且 CI 不跨 0 |
| “J2/M3 解耦提升了性能” | “J2/M3 解耦只证明接口可识别，性能尚未由该对照估计” | 微型接口测试不是性能实验 |
| “2× THT 更低” | “2× THT N/A；比较固定分母业务指标” | 禁止幸存者时延 |

## 4. 可直接使用的主张

### 4.1 对 HCA 的主结论

> 在两张已知拓扑的原始正式科目中，G31 相对 Feng 原生 HCA 同时改善了
> 1×完整人口 mean 与尾部运输时延，并提高了 2×固定时域完成能力；该结论
> 不使用幸存者时延，正式 2× THT 保持 N/A。

### 4.2 对 CIE-DH 的条件结论

> 原论文 Table 5.3 实测仍是 CIE-DH 的首要历史数值。本文另在 Feng 旧
> Java 环境中实现了一个完整可运行的语义部分重构，用于可复查的负载和
> 灵敏度实验。由于原源码、系数和交接状态机未恢复，且可执行版的 mean
> 与 max 分别比历史实测快 10.124% 与 36.968%，本文不把它称为原实现或
> 忠实复现，只把它放在次级可执行诊断表中，也不由此声称 G31 已击败原
> CIE-DH。

### 4.3 对组合机制的结论

> 冻结随机析因和定向消融表明，服务感知势与动态局部状态的作用依赖地图、
> 负载和业务指标；它们的组合可提高高负载完成能力和总体积压表现，但在
> 南宁 2×伴随显著的最大迟到恶化。该证据支持系统级权衡，不支持把每个
> 内部组件分别包装成跨图稳定贡献。

## 5. 投稿前机械检查

- 搜索并删除对可执行 CIE-DH 的 `faithful`、`source-exact`、`original
  implementation` 和 “Feng-native exact” 描述。
- 确认历史 measured 行与 executable partial 行在每张表中有不同 method ID。
- 确认原 CIE-DH 主表性能锚点只有 historical measured；partial/ported 行只在
  明确分隔的次级可执行诊断表中出现。
- 确认 external/critical 表使用最终 Java source/class SHA；旧 SHA 或 smoke
  只能留在审计记录。
- 确认每个 2× latency/THT 单元格为 `N/A`，且没有 survivor/common-cohort
  数值出现在正文。
- 确认南宁 2× maximum tardiness 负结果与 completion 改善同页出现。
- 确认 common-executor CIE-DH 只在副表/附录，且负/混合结果没有删除。
- 确认没有把接口重构、事件减少、哈希核验或 dormant P2 写成算法贡献。
