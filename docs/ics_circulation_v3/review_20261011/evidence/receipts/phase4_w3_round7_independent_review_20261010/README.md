# 第七轮独立审查交付

2026-10-10。本目录记录独立反例测试、原件审计及修复过程。旧核心、第六轮源码、原C++和历史原件均保留；未commit/push。审查没有新增原图仿真，必要小图测试单独计量。

## 结论

最终全ICS整合 **879 passed，0失败/错误/跳过**，109源文件、72测试文件和原C++的运行前后SHA一致。原842全套、早期专项和失败尝试均保留。

新控制器的180次真实机会含174非空、6零池；全部692候选标签均排空。174个实际chosen的完整事件、query/work、私有cache、slow和同绝对终点结果严格复现原nominal，只差强制当前候选所省去的一次selector调用/history。全任务账、未到达任务、保护准时和真正排空均独立核查。

全2467查询及93次截断分母齐全。99正式shadow请求固定原K/H/授权器；额外候选没有进入部署。终点容量筛查只用于当前Snapshot、固定H的整条witness必要条件，93次拒绝全部有真实占位证据，原非空池零误拒。27次独立部署的2467个完整查询输入和有序候选池、194任务全部物理结果一致。search_work从1666386降至1387386，另计73465筛查record-work；二者计数单位不同，旧/新观测成本不同，**不宣称CPU加速**。

新标签20池J非平坦，但174个实际chosen全在原候选池内J最优。75池服务完成向量不同，55池J相等而服务不同；57池有J最优但使某任务更晚的替代动作。服务不延后子集的oracle gap全0；旧12状态切换新续接后相应集合全仅c0。这里只支持三个重复使用的合成nominal流中的条件结论，不能外推全局最优或部署收益。

## 证据索引

| 文件 | 独立检查/测试 | 结果 |
|---|---:|---|
| initial_binding.json | 第六轮101源+64测试+C++ | 166文件无漂移 |
| focused_initial_validation.json / focused_extended_validation.json | 21 / 29 | 全通过 |
| full_validation/result.json | 842 tests | 全通过、107源/69测试绑定 |
| full_validation_terminal/result.json | 879 tests | 全通过、109源/72测试绑定 |
| collection_artifact_audit.json | 12130 checks | 180 checkpoint / 289 query |
| normal_resume_artifact_audit_v2.json | 2408 | 5正常恢复严格复现 |
| pilot_artifact_audit_v2.json | 2900 | 16分支 / 4实际chosen |
| old12_artifact_audit_v2.json | 4522 | 历史12×4，d40严格复现 |
| full_artifact_audit_v2.json | 35805 | 692分支 / 174实际chosen |
| instant_observation_artifact_audit.json | 8101 | 837即时tick |
| query_coverage_pilot_audit.json | 42257 | 全27 / 2467query / 4×4shadow |
| query_coverage_formal_audit.json | 20351 | 99×4shadow全授权重验 |
| terminal_screen_validation.json / terminal_screen_binding_validation.json | 19 / 20 tests | 证书边界、故障、全Snapshot绑定 |
| terminal_corpus_artifact_audit.json | 25658 | 独立区间算法重算全2467 |
| terminal_pilot_artifact_audit.json | 13119 | 3部署 / 289query |
| terminal_formal_artifact_audit.json | 29158 | 27部署 / 2467query |
| value_aggregation_audit.json | 3633 | 全成本/聚合；24特征选原服务向量+old48 |

所有成功审计错误数为0。各JSON记录来源SHA、运行范围和实际CPU；相应audit脚本均在本目录。两个全suite含完整源/测试快照、前后SHA、pytest原日志、JUnit和独立manifest。

## 保留的问题与边界

- 首次normal原件审查有10项审脚本失败：错误将trace长度当作invariant检查数。runtime的unload_complete只追加事件，因此修正为减去该类记录。失败报告 normal_resume_artifact_audit.json、audit_labels_v1.py 和修后v2均保留，两次CPU分别计量。
- 冻结旧physical_projection的completed/load_times/empty_targets保留字典引用。旧记录的458个tick完成map、355个tick加载map不是即时值；兼容digest不证明即时ledger。旧标签未重写；新增opt-in深拷贝观察及额外3nominal补证单列。真正服务时间依据事件、checkpoint、最终ledger和milestone。
- 聚合审计复用已独立核查的全692成本，并重算所有174服务delta记录与场景/角色统计；额外原服务向量抽查按每场首origin/continuation选择24分支，以及全部old48。其余备用服务向量的提取经绑定分析源码审查，未在该次聚合中再全量重解析。
- 私有cache/LRU会因筛掉查询而改变，已显式比较记录，不能冒称cache字节不变。search work、screen work、观察CPU、worker总CPU分别记录；并发wall及嵌套计时不相加。
- 同区直接供盘仍是中央代理强对照，未修改固定本地模块参数或validator，不代表真实供应商权限、W2自治或现场接口完成。

详细问题与处理顺序见 [REVIEW_LOG.md](REVIEW_LOG.md)。本目录所有文件由 [manifest.json](manifest.json) 封存。最终资源账见 [RESOURCE_LEDGER.md](../phase4_w3_round7_resource_ledger_20261010/final/RESOURCE_LEDGER.md) 和 [ledger.json](../phase4_w3_round7_resource_ledger_20261010/final/ledger.json)；辅助未计量CPU明确为未知。

原C++ SHA：b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951。
