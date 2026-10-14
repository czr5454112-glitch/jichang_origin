# 第六轮同区供盘独立审查

本目录记录独立设计审查、负例测试、源码绑定与纯文件原件审计；未修改旧核心、执行器、C++ 或实验负责人的实现。没有提交或推送。

## 证据入口

- `REVIEW_LOG.md`：风险、实际问题、修复过程与解释边界。
- `initial_binding.json`：继承第五轮的158个源码/测试文件与原C++绑定。
- `independent_focused_repaired_validation.json`：26项方法负例和3项运行器故障注入通过；此前失败fixture及日志原样保留。
- `full_validation/result.json`：777项全套通过，0 failure/error/skip，101源文件、64测试文件和C++前后SHA均一致。快照、JUnit、日志、资源与manifest在同目录。
- `post777_repair_binding.json`：之后仅新runner缓存比较器及其作者测试发生变化。修后11项受影响专项通过，包含2项新增；不能写成一次779项全套。
- `mechanism_initial_audit.json`、`mechanism_repaired_audit.json`、`nominal_pilot_audit.json`：各批保存原件的完整哈希、任务账与所有记录guard的独立重算。
- `nominal_observation_overlap.json`：9个名义原件的公开观察交集复核。
- `formal_artifact_audit.json`：正式81实例，77,560项检查无错误；11,340次真实slow调用、166个guard及427个事件前缀独立复算，27条环境tape独立重建相同，442个绑定文件前后不变。审计CPU129.15625秒。
- `final_analysis_comparison.json`：复用独立审计行表核对root最终81行、54配对和12组汇总，757项检查无错误，不再读全体raw。
- `audit_artifacts_v4.py`：正式81实例审计脚本；仅解析已保存JSON，独立生成预声明27条环境tape、重建需求身份、图距离、匹配和物理成本，不调用被审控制器或物理仿真。

## 当前结论与边界

新guard与有限时域的静态时序可达匹配合同一致；所有保存的候选仍由原执行验证器校验。该guard保护的是模型内的匹配能力，不能证明多个远端匹配联合满足容量，也不保证每个FIFO袋身份或部署成本不变。需求release、真实供盘时间、hold、目标credit、其他需求、exact-node确定供给和预算未完成分别核查。

新方法是W3中央代理对照。物流同区不等于同owner，更不等于现场供应商已经授权区内模块新功能。旧module参数、原执行器及用户C++保持冻结。

初始机制6格的两条旧32复现标记失败仅由JSON list与内存tuple比较造成；全部落盘缓存字段和物理结果相同。失败批次保留，修复不豁免任何缓存字段，修后6格与9名义pilot分别重新运行并通过。

名义轨迹新旧各180次机会，仅127次完整公开观察相同：counterflow19/72、cross_cycle51/51、near_full57/57。old64与old32为180/180。观察不含私有cache和续接方法身份，即使重合也不能自动许可价值标签复用。6次零候选保留；位置角色共27 origin、153 continuation。

正式81实例在预声明的3条开发流、nominal及8条固定误差tape、3个策略上运行，全部达到controller_quiescent，无失败或截断，独立原件审计通过。已有名义结果未用于选择验证分母。这些相关开发实例不能解释为独立新场景确认，逐状态局部regret不能相加为可部署整段收益。

| 全流开发队列 | old32成本合计 | old64成本合计 | 新方法成本合计 | 新方法配对 |
| --- | ---: | ---: | ---: | --- |
| counterflow，9条件 | 1278.6 | 1278.6 | 447.7 | 9降 |
| cross_cycle，9条件 | 282.0 | 282.0 | 260.0 | 2降、7平 |
| near_full，9条件 | 125.3 | 125.3 | 125.3 | 9平 |
| 合计，27条件 | 1685.9 | 1685.9 | 833.0 | 11降、16平、0升 |

每策略194个任务实例，三策略共582个全部完成且准时，含81个受保护实例。这是按实验实例累计的任务数，不能当成582个独立来源任务。全部实际loaded生成尝试4326次，包含150次零候选。old64在这27个条件中均与old32持平；查询数上限相同不意味着新guard计算工作或CPU相同。

最终比较CPU时钟增量0.0秒、wall0.0149859秒，0.0反映计时分辨率，不能解释为没有计算工作。首次比较因所需analysis文件尚未落盘而退出，证据见 `final_comparison_wait_failure.json`；其CPU未知单列，未覆盖失败或重新跑物理。

CPU只累计互不重叠的明确计量区间；父/子进程未知项保留，嵌套测试与cycle不重复相加。第六轮汇总见同级 `phase4_w3_round6_resource_ledger_20261010`。
