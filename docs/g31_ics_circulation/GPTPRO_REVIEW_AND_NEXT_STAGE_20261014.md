# 给 GPT Pro：G31 × ICS 当前实现审阅与下一阶段修订

日期：2026-10-14。请审核实际代码与证据，再为 Codex 给出可连续执行的修改任务。本文是作者交接说明，所有结论都允许被源码和重新运行的结果推翻；不是要求审核者认可已有判断。

## 1. 审核对象与访问入口

| 项目 | 本次冻结身份 |
|---|---|
| 仓库 | `https://github.com/czr5454112-glitch/jichang_origin` |
| 分支 | `codex/g31-ics-v3-circulation` |
| 本次代码提交 | `89c2935ef2963d769ab6ca75764009b2b3e9365f` |
| 配套发布证据包 | `仓库outputs/experiments原件＋docs/g31_ics_circulation/publication_20261014/windows_native_artifacts.zip` |
| 发布文件、大小、SHA256及缺失项清单 | `docs/g31_ics_circulation/publication_20261014/source_manifest.json` |
| 当前作者原生构建 | `build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd` |
| 016二进制SHA256 | `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0` |

请固定代码提交审核，不只读取会继续变化的分支首页。上面的代码提交与含本文的发布材料提交可以不同，须分别记录，不以发布文档的新提交推断生产代码又改变了。

本文列出的 `outputs/...` 是作者原始证据路径。**是否已随本次 GitHub 发布或证据包提供，以发布清单为准；列出路径不代表审核环境已经取得文件。** 若只能取到摘要，就按摘要证据报告；未取得的原始日志、历史二进制、完整业务输入、外部图纸及大文件须逐项列明，不补造验证结果。历史交付ZIP是增量实现/补丁，不自动等于完整代码仓库或完整实验档案。

若运行容器再次无法下载，保存实际命令、工具、退出码、stderr、HTTP记录、下载字节数及是否产生文件。先尝试读取已提供的代码压缩包/附件和发布清单；不能把 GitHub 连接器逐文件可读写成“整仓下载成功”，也不能把缺原始日志的猜测写成确定的 DNS 或权限故障。下载受限时仍继续可执行的静态审核，明确哪些结论受限。

本次发布补齐了仓内两份原始拓扑xlsx和明确版本的Windows原生工件，并修正5处测试路径选择；没有改任何业务断言或016原生实现。发布前 `outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001/live_001/` 已重新实际407通过；从固定Git提交直接导出的干净源码归档又以作者Windows工件实际复跑407通过，源码/工件哈希一致。该复跑不等于独立编译或第三方运行。完整发布范围、干净归档复跑、依赖恢复及平台限制请先读 [PUBLICATION_AND_REPRODUCIBILITY_20261014.md](PUBLICATION_AND_REPRODUCIBILITY_20261014.md)。

固定代码树：[89c2935](https://github.com/czr5454112-glitch/jichang_origin/tree/89c2935ef2963d769ab6ca75764009b2b3e9365f)。若网页容器依然无法联网下载，可由用户直接上传本次生成的完整仓库ZIP；它与历史增量diff ZIP不同，具体SHA和范围见旁边的归档回执。原始需求DOCX图纸、未交付的全业务checkpoint及230MB旧证书状态文件不因本次代码发布自动存在，应逐项标记可用性。

## 2. 项目关系与不可降低的目标

成熟 G31 参照为 `46cc46ab6bc121628fd6357e9f3c7636745fd732`，原分支 `codex/g4irsf31-nanning-portability`。V3 审核代码为 `defd79effe02ee13f1a5bbbbc5143f6d0dce2f63`，其后发布材料为 `fccd4819532701ee4173ec598822450d962d4e61`。后者不能冒称对 V3 生产实现又完成一轮修复。

当前 circulation 工作区以成熟 G31 为代码基础，再选择性导入 V3 专属参考、测试及文档并修复其已复现问题；没有把 V3 包内较早 native 文件当成熟 G31，也没有整分支合并覆盖原工作区。原始选择导入清单见 `outputs/experiments/g31_ics_circulation_20261013/v3_import_manifest.json`。这些导入文件及既有 G31 成果不是本阶段新增方法工作量。

当前物理由 G31 `EventDrivenJunctionRuntime` 的一个事件堆和时钟执行，保留逐跳 S4、即时合流及原有高效事件机制；Python 用于控制、参考和诊断，不能另推进一份物理真相。`legacy_g31` 保留已有实验合同；`circulation` 明确有限盘、存储、卸载、hold、接收和导出权限。请沿真实构造—调用—事件—仲裁—完成链阅读，不仅看类名或接口名称。

最终目标仍为：**成熟 G31 执行＋区域按需自主路由（R1）＋载盘驱动跨区预测预平衡（R2）**，形成同一算法系统。固定区内空盘模块的权限、正常分拣保护、全体 offered 业务及失败分母、完整单任务更新计算不超过100ms、TRE/CIE量级方法与证据标准均保留。

请修正具体机制和研发顺序，不因已有结果无收益而删除 R1/R2、放宽保护、加盘/扩容/改边/改FIFO、删除业务、隐藏超时，或把小图工程闭环当最终完成。也不要继续把三项 V3 修复或首个“一盘两服务”当主要下一阶段任务：它们是已完成的历史正确性/工程里程碑。

## 3. 先读这些文件，再定向核代码

建议按以下顺序读取，并记录实际读到的文件、提交、范围及缺失项：

1. `docs/external_review/g31_ics_long_term_20261013/G31_ICS_LONG_TERM_CODEX_PLAN_20261013.md`、`CURRENT_REVIEW_AND_START_POINT_20261013.md`、`SEND_TO_CODEX_20261013.txt`。LT-1总纲是阶段门与失败替代路线的来源，不代表里面的旧起点描述仍是最新代码。
2. `docs/g31_ics_circulation/RESEARCH_STATE.json`，以及 `LONG_TERM_PROGRESS_20261013.md` 最后的“012—016实质研发”段落。
3. `NOVELTY_LEDGER.md` §25—28；旧§22的某项反例已被§25纠正，不能只摘录旧结论。
4. `NATIVE_NOTIFICATION_CONTRACT_20261013.md`、`P5_DEPENDENCY_ORDER_RECHECK_20261013.md`、`P5_HANDOFF_DIAGNOSTIC_20261013.md`、`P5_HANDOFF_NATIVE_RECHECK_20261013.md`、`EVENT_CONTROL_PROFILE_AND_SERIALIZATION_20261013.md`。
5. `outputs/experiments/g31_ics_long_term_20261013/session016_final_review_001/REVIEW.md`、`assessment.json`、`audit.py`，再核对它引用的原始运行与JUnit。该审计是独立只读复算作者保存的原件，**没有重跑 native 或 pytest**。

实现重点如下，行号请在固定提交重新定位：

| 实际代码入口 | 应核实的合同/风险 |
|---|---|
| `cpp/ics_core/runtime/event_driven_junction.hpp` 及 `circulation_*_impl.hpp` | 一份物理状态、严格时序、真实资源占用、同刻阶段、保护与原子提交；不要漏读成熟G31调用路径 |
| `cpp/ics_core/runtime/circulation_notifications_impl.hpp` | 只有合法本地变化及实际收到的消息/故障通知激活owner；整时间戳排空、预算切断、checkpoint/seal |
| native circulation binding 中的 `observe_protocol_impl`、`render_protocol_command` | 016消除重复查找是否保留全部历史、顺序、ACK快照、权限与字典隔离 |
| `scripts/experiments/g31_ics_circulation/event_protocol_control.py` | `_activate_owner`、通知游标、`pending_causes`、owner轮次、续跑状态、时间/预算完成声明 |
| 同目录 `protocol_control.py` | `ProtocolClient` 的重试/ACK状态；`_publish_services` 的预测发布、撤销、过期、刷新以及延迟source复验 |
| 同目录 `p5_handoff.py`、`p5_handoff_run.py` 与P5依赖修复实现 | 候选域、合法信息、条件窗、真实继续策略、未知/未兑现请求及全体业务保护 |
| 同目录 `native_host.py` | 请求二进制与实际加载模块路径/SHA的一致性；跨版本必须独立进程 |
| 同目录 `validate_event_protocol_control.py`、`validate_live.py` | 输入/源码/二进制冻结，H是否真实完成，截断是否保留全部业务，计时与测试口径 |

## 4. 当前事实：哪些已实现，哪些没有证明

| 阶段 | 已有实际证据 | 未达到的门 |
|---|---|---|
| P1 在线宿主/恢复 | 原生session、进程内checkpoint、消息/ACK/故障合同、严格circulation时间、合法owner通知；测试中的native/owner预算停点可继续 | 不能将进程内恢复称跨进程持久恢复；旧周期控制器仍不支持中断tick恢复；部署隔离未认证 |
| P2 原图/业务 | 原151节点227有向边，预先静态选择24业务、1真实托盘，016五策略均完成24件、真实返供23次 | 仍19件迟到；24件不是28506母流或57012两倍流；保守代理合同下全流阻塞历史保留，零容量现场语义尚未确认 |
| P3 两项需求 | 合法区域事件激活；路由/需求/服务预测/撤销/取消/transfer走原生通信链；保留拒绝、丢失、重复和故障 | 本次原图24件R1授权0/24、route请求0；长期同stage预测刷新及完整lease/cooldown定时仍缺；尚无该原图上R1/R2共同起效证据 |
| P4 强参考 | 同G31有限枚举、必要界、可行见证、独立服务完成代价匹配及滚动对照 | 有限域最优不等于全局最优；未兑现完整请求参考必须unknown；仍需耦合候选/信息诊断 |
| P5 主方法 | 126个新handoff分支，原16域跨011/015重查，保留失败与反例修正 | 强服务指派已解释所测八个有限域全部收益；原图joint等于predictive；独立新增求解机制尚未获支持，状态research_candidate |
| P6 学习 | 放行条件、合法信息与真实继续策略要求已明确 | 尚未通过候选覆盖、同G31标签、P3/P5主机制门；不开展大规模旧标签训练，不把小网络称创新 |
| P7 正式确认 | 工程回归、固定fixture兼容性、原图机制见证、计时失败原件 | 完整100ms、全规模、两台机器冷/热/突发、正常保护完整分母、确认集与论文方法证据均未闭合 |

最新回归 `live_validation_012` 为 **407 passed / 0 failed / 0 errors / 0 skipped**，33个指定测试文件，`source_changed=[]`。组成是 **401项当前native或Python关联检查＋1项冻结011历史反例＋5项固定011/015身份检查**。401也不是401个物理实验，407不是全仓测试，不能与重叠专项相加扩大工作量。第一阶段1580、旧发布1519等是各自版本/范围的历史回执，不是本次重新执行。

`p1_checkpoint_validation_009` 编译并运行三个C++目标，六条命令通过；`legacy_parity_005` 的两场固定fixture、每场五项hash与成熟G31一致。016只更改binding，上述回执覆盖的编译源哈希仍匹配。只能据此表述相应兼容范围，不能称所有旧大规模实验已重做。

## 5. 必须认真审阅的负证据与已修正结论

### 5.1 严格时间修复改变了一项旧方法反例

012/013联调暴露旧epsilon事件比较将 `6.05` 与 `6.049999999999999` 当同刻，微阶段再排序使晚事件先执行、时钟回退、H虚假完成。014/015改circulation为严格double时间排序，仅精确同刻才按阶段/序号，初始化故障堆重建，排序合同纳入seal；legacy保留其旧行为。另修正零延迟实际故障遗漏通知、正微小延迟提前通知以及loaded预测重复叠加服务时长。

原006/011中“两次修复令D0晚约400秒”反例，是 `401.75000000000006` 的T1抢在 `401.75` 的TP前获得资源造成。固定输入、候选和请求在015重跑，16分支中恰三条业务结果变化；相关三类日志回退计数合计58→0。当前两次与一次修复逐件相同，**该旧因果反例对严格模型撤回**。旧断言及011独立进程回放保留，另加当前严格顺序和真实修复回归。这不证明一般联合修复有效，也不把未兑现请求的参考从unknown改成最优。

请核查修复是否充分、是否存在其他版本绑定结果应撤回/重跑，并区分“仿真正确性修复改变证据”与“方法进步”。不能为了保留旧论文叙事回滚严格时间。

### 5.2 原图五策略有工程收益，但未证明联合创新

共同输入、通信权限与H86400下：

| 策略 | arrival到unload成本和（秒） | 完成 / 迟到 / 实际同盘返供 |
|---|---:|---|
| periodic_reactive | 418514.272581 | 24 / 19 / 23 |
| periodic_predictive | 414198.867581 | 24 / 19 / 23 |
| event_reactive | 414592.459581 | 24 / 19 / 23 |
| event_predictive | 414170.459581 | 24 / 19 / 23 |
| event_joint | 414170.459581 | 24 / 19 / 23 |

事件预测比周期预测仅一件快28.408秒，其余23件相同，涉及首次返盘从actual_available转为conditional_release请求的时机。204条成功服务预测全部在实际入边后0.5秒送达，320条拒绝均为 `no_local_uncommitted_loaded_service`；周期预测16条全拒绝。准确估计在途服务窗不等于提前预知入边，更没有消融证明204消息造成28.408秒收益。事件joint与predictive的规范化物理事件相同，R1实际未被该输入授权启用。

合成known-service组event reactive成本26.1→25.26，但B2晚0.3秒、B3早1.14秒，全体正常服务保护不通过。拒绝组仍只完成1/2。请检查单项保护与总成本是否被不当混用，保留失败分母。

### 5.3 先排除强普通方法，不能把更弱基线上的收益当创新

P5四个预声明handoff因子、初始与滚动两阶段共126个真实native分支。有Storage余量时，普通空盘ETA成本22.07，固定指派重定时24.350001，独立最小费用流服务完成指派与联合选择均19.96。去掉Storage余量后D1由2.31变4.21；禁止第三源导出又出现劣化。强服务匹配已达到八个有限域的已核验最优，当前域方法余量为零，**全局最优未知**。

完整合同可见性在合法resource_owner A内；C只通过真实公告提供条件窗。这不是完整跨owner私有合同交换已完成。后续若改成真正跨owner求解，必须显式设计消息、延迟、撤销、未知、版本与提交协议，且同能力给强基线。

请回查原始近邻，而非只引用综述或我们写的摘要：已有G31服务势能/S4、Chen等2021服务完成代价及重指派、Parimi与Williams2026余量种子/依赖闭合/外部冻结/重定时。`P5_HANDOFF_DIAGNOSTIC_20261013.md` 已记录原文核查范围。请指出哪些机制已经被覆盖，哪些具体差别仍值得实现验证，不把“分层＋MLP”、更多测试或通知接口当创新。

### 5.4 100ms仍失败，平均变快不能替代硬门

016去掉批量历史命令观察的重复线性查找，没有删除ACK/历史。三份完整观察、1489条单回复及原图五策略的输入、动作、全部请求/回复、物理事件、继续状态与最终seal和015一致，仅比较时排除明确计算计时字段。

事件预测总wall68.460→49.168秒，联合68.511→50.527秒，但015有并发编译，属于非受控描述性比较。016预测owner仍 **15/7890** 超100ms，最大 **128.0842ms**；联合 **24/7890**，最大 **199.5798ms**，尾部比015更差。这还只是owner子链。旧010完整两倍流已测owner加同owner发布也有2/194超限、max101.0037ms，不能被24件样本覆盖。

请查完整单请求的观测/预测/候选/求解/提交、实际交付复验及确认计算边界，明确各时间是否重复或漏计。逻辑通信等待与实际计算分别报告，不能将模拟900秒窗口均摊成单请求100ms，不能把“≤100ms”改成P99≤100ms。两机、冷/热、突发及失败/unknown计时均尚未完成。

## 6. 可追溯证据索引

下表除第一行外均相对 `outputs/experiments/g31_ics_long_term_20261013/`；可用性请核对本次发布清单。原件较多时，先检查决定性原输入/输出、生成程序与哈希，再抽查其余记录；不能把未审到的项目写成已验证。

| 证据 | 原始位置 | 可支持的范围 |
|---|---|---|
| 总索引 | `docs/g31_ics_circulation/RESULT_INDEX.jsonl` | 导航；不是替代原始结果的证明 |
| 本机代码/回执一致性 | `session016_handoff_integrity_001.json` | 源码、构建、回归、兼容性绑定 |
| 只读独立复算 | `session016_final_review_001/` | 原件哈希、JUnit计数、五策略业务/事件与声明审计；非重跑 |
| 016构建与最终回归 | `p1_build_016/`、`live_validation_012/` | 命令、stdout/stderr、JUnit、源码身份及407精确范围 |
| 历史失败 | `live_validation_010/`、`event_control_tests_012_001.*`、`event_control_tests_013_001.*`、`adjacent_float_before_013_001/` | 修前真实失败；不能要求旧错误在当前模型继续成立 |
| 原图最终五策略 | `event_protocol_original24_016_001/` | 共同input、五条完整原生运行、时限/请求/动作及全部offered结果 |
| 原图独立链核查 | `event_protocol_original24_review_015_001/` | 五组共115条真实卸载/hold/授权/空返/再服务链；版本015 |
| 015/016行为等价 | `event_protocol_015_016_comparison_001/` | 五策略排除显式计时字段后的完整返回语义等价 |
| 合成故障与保护反例 | `event_protocol_synthetic_015_001/` | 七场×五策略，包含失败、无收益与保护恶化 |
| 预测时刻修前后 | `original_protocol_24_forecast_diagnosis_011_002/`、`original_protocol_24_forecast_diagnosis_015_001/` | 相同输入/请求、独立进程的实际入边与估计比较 |
| 126分支强参考 | `p5_handoff_011_003/`、`p5_handoff_015_001/`、`p5_handoff_015_001_recheck_context/` | 有限域、真实分支及强普通方法解释；不能转移为当前全套源码冻结 |
| 旧反例重查 | `p5_dependency_repair_011_001/`、`p5_dependency_repair_015_001/`、`p5_dependency_order_recheck_015_001/` | 原16域，旧时序缺陷和应撤回结论 |
| 性能与序列化 | `event_control_readonly_profile_015_001/`、`event_control_readonly_profile_016_001/`、`protocol_serialization_tests_016_001/` | 局部剖析、内容等价和专项，非全请求SLA |
| 旧模式与checkpoint | `legacy_parity_005/`、`p1_checkpoint_validation_009/` | 明确两场fixture和三C++目标的验证范围 |

历史P5冻结之后，`native_host.py` 加入模块身份守卫；不能把旧P5回执移植为016全部源码已经重做。重查历史行为需保留归档源码和对应二进制身份；不得修改当前树去绕过历史源检查。

## 7. 有执行条件时的复核方法

先核发布清单、依赖和代码身份，再运行。作者平台为Windows、Python3.11，原生扩展为该平台产物；其他平台不能直接加载该 `.pyd`。重新构建的产物SHA会不同，应记录自己的构建回执和实际SHA，不能期待复现作者二进制字节。不可静默切换二进制。以下是作者平台命令模板，工作目录为仓库根：

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python docs/g31_ics_circulation/publication_20261014/verify_published_files.py
python docs/g31_ics_circulation/publication_20261014/restore_author_artifacts.py
$g31Binary='build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd'
$g31ExpectedSha='af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0'
python -m scripts.experiments.g31_ics_circulation.validate_event_protocol_control --binary $g31Binary --expected-binary-sha256 $g31ExpectedSha --suite original24 --output outputs/experiments/g31_ics_long_term_20261013/pro_review_original24_new
python -m scripts.experiments.g31_ics_circulation.validate_event_protocol_control --binary $g31Binary --expected-binary-sha256 $g31ExpectedSha --suite synthetic --output outputs/experiments/g31_ics_long_term_20261013/pro_review_synthetic_new
python -m scripts.experiments.g31_ics_circulation.validate_live --binary $g31Binary --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/pro_review_live_new
```

每次使用新的独占输出目录。完整407回归还包含冻结011历史反例和011/015身份检查，需清单中对应历史构建和fixture；缺失时如实报依赖缺失，不能删除检查后仍称407通过。重新构建可查看 `build_native.py --help` 并使用新build/receipt目录；构建前先检查工具链，避免反复重跑相同环境失败。历史归档重演与当前代码评估应分别报告。

## 8. 请回答的研发决策，而非重新抄写旧计划

请按证据强度给出下面四类结果，并指出会改变研发顺序的关键理由：

1. **当前代码必须修改的具体问题。** 每项给提交/文件/函数、触发输入、实际或预期失败、原因、最小正确修复、回归与业务验证。区分确定缺陷、当前合同的有意限制、方法假设及证据缺失；不要从接口限制直接推断某个业务结果的原因。
2. **未来主机制是否需要修正。** 先判断当前零增量来自物理不可达、权限不允许、候选覆盖不足、弱/不合法信息、继续策略/目标不匹配，还是独立强基线已足够。给出少数有判别力的下一实验和停止/转向条件，不再默认增加扫描、窗口或网络规模。
3. **下一轮可直接交给Codex的任务包。** 按依赖排实质工作，写明改哪些接口、保持什么合同、怎样运行、成功/负结果/unknown怎样判断，以及失败后仍能继续的替代路线；不要每个小步要求用户批准。受阻时只阻断依赖它的任务，其余可独立推进。
4. **论文级证据与创新缺口。** 对照最近邻原始论文和既有G31成果，说明候选机制真正新增了哪个求解对象/约束耦合/结构性质，哪些已经是标准方法。为每项研究主张给强基线、消融、反证、统计单位、确认集和失效边界；没有支持就保留hypothesis，不用测试量替代工作量。

作者建议下一入口如下，**请依据审查修订，勿机械照做**：

- P3：在 `event_protocol_control` 的预测状态和合法定时唤醒处补同stage长期阻塞刷新、lease/retry/cooldown；保留延迟source检查，构造预测真正先于有关入边/释放送达的可解释情形。先隔离“激活更及时”“信息更早”“实际求解不同”三个作用，所有强基线共享能力。
- P2：核零容量、等待/Storage及on/off-carrier物理语义；维持研究代理/现场合同区分。已有必要界说明固定单盘24件至少19迟到，不能将此界泛化为全图/多盘最优，也不能擅自改物理使数据变好。
- P4/P5：先形成有合法R1权限、多真实候选、共享资源占用耦合和明确跨owner消息合同的预声明域；与服务完成匹配、同信息强滚动反馈、通用闭合/重定时、真实G31有限参考竞争。检查目标保护交集是否物理相容，再研究边界选择/局部修复。不要只在已被强基线解释的八域添加时点。
- P7：先保持语义地复用同owner未变化观察、索引pending outbox/active forecasts，保留历史/ACK及恢复隔离；再测完整活跃请求与原流。成功门是实际符合原100ms合同，不是总wall下降。
- P6：只有覆盖、合法信息、参考余量、同G31继续标签和可独立开关的主机制满足门时再放行。小批诊断也需记录全部失败候选和标签继续策略；无收益先诊断，不用扩大旧残差训练替代机制工作。

## 9. 请交回的审核产物

请输出可直接交给Codex执行的中文任务MD，并配套读取/运行清单。建议包含：

- 固定的审核SHA、实际读取文件、实际取得的证据、缺失文件与访问错误原件。
- “作者报告 / 审核者独立只读复算 / 审核者亲自运行 / 尚待验证”四列证据表。我们保存的session016审计也属于作者交付中的只读复算，不能算你亲自执行。
- 按严重性排序的代码修改清单，每项有位置、触发、修法和验收；若无确定缺陷，也说明读到的边界，勿凑数。
- 经修正的P1—P7状态、明确撤回/保留/新增的主张与理由。
- 下一轮按依赖排序的实质任务、强对照、失败诊断分支、停止/转向条件和精确续跑入口；区分近期工程补齐、主方法验证、学习及正式确认。
- 更新创新账的建议：工程接通、正确性修复、研究假设、有实验支持增量分别列明。当前并无已证明的独立联合方法增量，不能先设论文结论再挑实验。

目标是让下一轮研发真正解决剩余问题，而不是降低两项需求、100ms或TRE/CIE质量，也不是把长期总纲原样重写一次。请保留有证据的既有成果，主动纠正缺陷和错误归因，并给出可执行、可反证的下一步。
