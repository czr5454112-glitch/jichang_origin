# 第七轮：真实截断查询的影子覆盖诊断

这项工作不替换部署生成器、原K4、慢层动作选择或目标权重。目标是区分有限搜索预算没有找到、区域抽象/局部标签遗漏、执行模式过滤与原候选内排序；影子参考只生成，不执行新增动作，也不读取真实未来tape。

## 完整普查及失败修正

纯文件读取第六轮full的全部old32/new共54案例、4378个query：旧50次截断全部是near_full、node134的loaded origin查询；新方法同样50次loaded截断，加counterflow中43次空盘查询。43条均唯一对应slow同tick/tray的搜索截断拒绝，其中18跨区、25同区。143条返回原始候选数均为0，没有截断后部分非空pool；全部使用RegionalCandidateGenerator(dynamic_local=True)，调用routing_reference中的共享event-time primitives不表示启用了FullGraphReferenceGenerator或额外fallback。

旧query schema缺destination、requested_k、state/version、callsite、完整诊断。loaded查询可以按唯一time/node/bag/tray绑定opportunity的真实公开Snapshot，加冻结network恢复物理查询输入；没有保存query之前的cache、隐藏tape及完整可继续engine。slow每次使用不断虚拟commit的scratch，因此不能把SlowAudit.snapshot_before当作每条空盘查询输入。

首次分析错误要求raw K等于post-validator K，产生28检查失败，已完整保存census.json与80.171875s分析CPU。源码runtime._generate明确按route_mode=next_edge再次校验；这28条raw K4被过滤为授权K2/K3。census_repaired.json改为唯一身份绑定且授权数不超过raw数，2885检查0失败，另0.421875s；没有重复仿真、删除旧失败或降低原validator标准。

## 新采集合同

`same_zone_query_probe.install_query_probe(engine,sink:list)`必须在bind_accounting之后安装。捕获所有query的实际传入Snapshot clone、method/destination/K、source/version、raw options、真实generator配置、完整diagnostics、cache before/after、有限调用栈和site。栈只留函数名/文件/行号，不保存frame或local；没有engine回指或外部future。

sink先获得phase=entered的record，结束原位更新returned/error；错误重抛并留部分工作，探针错误不可冒充空pool。deepcopy/pickle剥离probe层，只保留原Budget和cache；同一个memo保留共享owner关系，不清空live sink。collector仍另记授权后opportunity pool；两层不是强行数量相等。

覆盖采集独立复跑第六轮固定27条new tape（3场景×nominal及8条已冻结误差tape），完整排空。每条须与原new记录比较最终物理、全部search、机会、动作、cache及停止条件，排除的只限既定_ms计量。旧文件不回填。与另一个代理的3个nominal checkpoint采集身份重叠但确实独立执行，资源分别记账。

正式coverage包含27条中全部93条截断，不按已知目标收益选取。成功controls按截断覆盖cell=(scene,callsite,source,destination,requested_k,protected)选同27采集中最早一个成功query，顺序固定为case_id/time/query_ordinal；缺少成功control的cell显式missing，不改tape或放松身份匹配。所有截断重复时刻均保留请求分母，若以后做完全相同状态memo必须另列物理请求与reuse，不把alias算新工作。

## 固定影子搜索

每个真实状态固定四组，不依pilot收益改预算：regional原3000、regional12000、regional48000，以及full-graph event48000。H180、原K（loaded4/empty1）、原module/owner/业务可行性、原local_label_limit3/static_path_limit8与deadline_ms=None保持；参考不增加K。regional3000必须复现记录rawpool/status/logicalwork；温缓存物理预处理差异另列，冷等价逻辑账一致。

FullGraphReferenceGenerator绕过区域macro及局部标签限额，但继续使用相同有限event-time表示、原validator与同一公开Snapshot；每次独立冷拓扑/最短路预处理计入work，进程内旧global cache必须保存并恢复，不污染其它查询。它是有限强参考，不能声称全部K覆盖或全局成本最优；empty/loaded都分别记录原始路线和实际next_edge授权前缀。没有候选、再次截断、参考反而差都保留。

比较三个层次：原始全路线/到达与usable时点、授权后实际action_key与前缀差异、原候选内的现有解析分数（若后续需要）。物理全周期标签仍由另一项部署匹配continuation任务负责；影子生成不产生新的部署因果收益标签。integer_ticks参考只适用于另行声明的足够预算有限整数早到证书，当前原图正式方案不使用它。

pilot固定取每个有截断场景按case/time/query序的第一条截断及其预声明control；cross_cycle若无截断就如实无该pilot cell。pilot只检输入恢复、预算和资源，不筛结果。正式全部请求重新生成，pilot和正式分别计量；保留失败/未解/截断。

## 实现边界与资源

原代码、validator、控制器、C++与上一轮冻结源不变。新增probe及coverage模块/runner单独冻结，3个采集worker；原定与checkpoint/label runner合计最多6worker；在coverage采集前，root依据16物理/22逻辑核心、33.7GB内存及label pilot单worker峰值98.3MB，批准labels6+coverage3合计最多9worker。该资源修订先于coverage物理/收益结果，影子仍最多3worker。每次query生成CPU、work-stage、逻辑搜索计数、实际cache预处理与内存单独记，采集物理CPU和影子CPU分开，未知辅助开销不填零。第七轮新资源账不覆盖第六轮。

本设计依据已读仓库 `routing.py`、`routing_reference.py`、`routing_cache_contract.py`、`network_role_labels.py` 与 `role_coverage.py` 的实际实现，不需要把外部理论保证套给当前有界搜索。后续若引用方法资料，另记primary source和适用边界。

