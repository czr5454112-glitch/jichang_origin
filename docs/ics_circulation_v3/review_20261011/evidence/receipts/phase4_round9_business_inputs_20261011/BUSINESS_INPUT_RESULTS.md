# Round9：完整业务输入与显式运行适配

2026-10-11。实现文件为 `scripts/experiments/ics_circulation_v3/business_inputs.py` 和 `business_runtime.py`。本目录全部运行都是 **0 physics**：输入核验、合同构造、运行时对象适配和测试，不等同完整业务窗口已经运行。根代理另负责共同物理、小图与第一小时开发试验，结果必须引用其独立记录。

## 完成范围

`load_business_workload` 返回不可变 `BusinessTask / SourceReference / BusinessWorkload / OperationContract`。一件原始 raw 袋只生成一个业务对象，保存原始 SHA、ID、行号、parent 原源 SHA/ID/行、航班代理键、派生时移以及完整旧段身份。载具不是袋属性，不从旧 `pallet_id=task_id` 自动创建物理托盘。各层集合冻结为 tuple、各记录为 frozen dataclass。

读取先验证 Round8 规范化文件的输出 SHA 与全部实际输入文件 SHA，再逐袋重核 raw 精确秒、父身份、完整原/派生清单、完整航班同一时移/目的地、原始装卸角色、canonical 段集合与源属性、总袋/旧段/早包分母和 OD 边际。末次重新哈希输入以发现读取期间修改。所有零路由、早包和不可能截止仍在业务分母，读入不运行寻路或 Simulation。

`build_business_runtime(workload, profile_path, runtime_contract)` 返回共同物理引擎所需的 `StorageSnapshot(now=0, bags={})`、完整私有 `future_bags`、有限初盘、显式模块与生成器工厂。所有初态袋表和 storage progress 为空；包括 arrival=0 的袋也只由环境事件加入。直接袋用原 `Bag`，早包用 `StorageBag`，两者 destination 均保持最终业务卸载点。每个 early 固定公开合同在它自身到袋时发布；这里没有初始化时公开全日 bag ID、STD、release 表。

本轮只支持显式 `proxy_research / on_carrier / irrevocable_at_bag_arrival`。拒绝动态晚发布、off-carrier、非零装载服务、未知权限、暗设模块/路由预算、`confirmed` 自贴标签。完整 supplier 接口、动态授权、独立库位设备或真实入口头距仍需后续不同合同。输入对象 `runtime_adaptation_required=True` 只说明输入通过；共同运行还必须通过独立 RuntimeProxyContract。

## 全量分母及最终输入证据

最终纯输入源绑定为 `audit_004.json`；运行适配为 `runtime_adapter_audit_002.json`。前面的全部尝试均保留，它们对应不同实现阶段，不覆盖成最终结果。

| 项目 | 1× | 2× |
|---|---:|---:|
| 完整业务袋 | 28,506 | 57,012 |
| 旧运输段（只作源核验） | 43,603 | 87,206 |
| early_storage / StorageBag | 15,097 | 30,194 |
| direct / Bag | 13,409 | 26,818 |
| 原源袋 / 完整派生袋 | 28,506 / 0 | 28,506 / 28,506 |
| 原始航班代理组 / 含派生时移代理组 | 360 / 360 | 360 / 720 |
| 保留的正容量有向图无去程袋 | 4,001 | 8,002 |
| 显式有限初盘 | 11 | 11 |
| 初态公开未来业务袋 | 0 | 0 |
| 独立观测运行日 | 0 | 0 |

两档来自同一份原 timetable，2× 是完整航班清单增密，不能叫新的独立观测日。最终数据模型用 `source_timetable_count=1`、`independent_observed_operating_days=0` 区分这两件事。早期 001 的 `independent_source_days=1` 是一份输入来源计数；最终字段明确修正命名，不能将早期字段解释为新增真实机场观测。

1s 到达向上取整最大误差 0.99988 秒，deadline 向下、release/初盘可用/服务/行驶向上，原始秒全部保留。源 `STD` 不自动冒认为真实交付截止，只能由下面的显式 `STD−lead` 研究规则产生。不能把从旧 10s 到此处 1s 的模型变化计为算法增益。

## Explicit assumptions

纯输入示例 `proxy_contract_003.json`：1s，`deadline=STD−0s`，全部业务袋 protected，11 个源 loader 各一个显式盘，初库为空，所有节点共享占用容量 1、loaded waiting true；node53 作为明确授权的研究 EBS 等待节点，同节点容量 1，持盘存储，在每袋到达时固定发布其源 scheduled release。没有声称这些是现场参数；该例仅用于完整输入校验，不是单独可执行机场方案。

零初盘或零库容若**显式给出**是合法关闭压力输入，保留全部业务分母；`None` 是未确定，拒绝。二者不能混为“缺参数默认 0”。任意数量托盘都必须逐个列身份、初节点、可用秒，不接受袋数推导或隐含无限供给。

## Runtime proxy assumptions

根代理在物理结果出现前声明了 `runtime_input_contract_001.json` 和 `runtime_proxy_contract_001.json`：原图、1s、原记录边容量，普通 node 容量 4、storage53 容量 1，全部允许等待，unload=1s、逐 node hold=0、reception=1、export minimum=0、FIFO loading=0，原11盘不变。所有 151 节点及 227 原方向边保留；其中一条容量 0 边仍保留其原身份并关闭，未添加反向边或提高容量。

边旅行秒使用原 length/speed 的精确有理数，然后向上取到共同 tick；容量单独保留原整数。整段同时占用上限不是入段头距。两种托盘 mode 共用原向边、empty wait 沿用明确 loaded wait，都是写入合同的权限代理，不等于实际模块授权。原 profile 的零缺省/不完整服务信息不被当成现场 0 秒，运行模块只使用本次显式 FIFO 代理。

完整显式路由设置：whole_route，horizon=80 tick，K=4，expansion=10000，static paths=12，local labels=3，dynamic_local=true，deadline_ms=null，isolated_replay_v1 cache；reactive=true、route_then_prebalance。每次 generator factory 生成独立缓存，runtime 的 StorageCandidateGenerator 负责共同 storage 硬约束。为此中央开发组逐 node 显式映射到 `central-development-proxy`；不是现场 owner 区划，也不是 W2 多 owner 通信验证。

该预算很可能不足以覆盖数小时已公告 EBS release。预算不足必须由执行记录为 bounded/unknown 或未服务，不能因此删除早包、缩短法定等待、弱化 protected、声称无路。运行 wall/CPU/物理 tail cap、完整第一小时 scope/prefix/tail 账和 observer 由根代理另行声明；adapter 不私自选窗、不运行 physics、不设置隐藏停止阈值。

使用方式：

```python
workload = load_business_workload(..., contract=input_contract_json)
adapted = build_business_runtime(workload, profile_path, runtime_contract_json)
engine = Simulation(adapted.initial, adapted.future_bags,
                    **adapted.simulation_kwargs())
```

上面是构造用法，不是本目录已经执行了此 Simulation。policy 只应得到引擎公开 Snapshot；`workload.tasks` 与 `adapted.future_bags` 属于环境。

## 实现中识别并处理的问题

1. `ceil(Decimal(value)/tick)` 会先受全局 Decimal 精度舍入；很长的小数在 tick 边界可能被提前。改为 Decimal 保存源值、Fraction 做精确 quotient；deadline 扣减使用按位数扩展的局部精度，再 floor。超过 28 位默认精度的反例已纳入测试。
2. 旧 canonical 早包两个独立运输段不能当两个业务袋。接口检查精确两段及其父源，只输出一个带 final destination 的 StorageBag；不发明每袋盘。
3. 已声明零库存/零库容是有效无供给/关闭压力，不能被“至少一个”约束误判成缺字段。本轮保留显式零，未确定值仍拒绝。
4. 直接保留 `independent_operating_days=1` 容易混淆一份源 timetable 与真实观测日。最终模型分别报告源数1、独立观测日0，全部旧审计保留并注明字段更正。
5. 模块数据不足不能靠默认 `FixedLocalModule()` 填参数。新 adapter 要求另一个完整显式代理合同，缺 node/hold/partition/route 等任何字段均报错；当前 core 无非零 loading stage，显式非零装载服务也拒绝。
6. **独立审查找到真实二次边界漏洞**：虽然 BusinessTask 是 frozen，调用者仍能用 `dataclasses.replace` 创建修改后的袋，旧 adapter 只核验类型和合同 ID，因此可以在保留同一合同 SHA 的同时解除保护、同步放宽 deadline 或将早包改成 direct。现在 loader 对完整 tasks/contract/source bindings/counts 生成 `content_sha256`，adapter 重新计算，拒绝在两层之间改变内容；同时再核 deadline=STD−lead、protected 规则、early 阈值和 release=STD−2700。内容 SHA 是复现完整性封印，**不是**对能同时改内容及封印的恶意调用者的签名；因此还增加了故意重封后篡改政策仍拒绝的反例。独立审查原件明确说明 pre-fix 是静态发现并经作者确认，未单独执行 pre-fix probe；修复后八项独立反例原件保留在独审目录。旧 author 26项全过不能掩盖此遗漏。

这些改进没有根据算法输赢或业务成本筛选。未改用户 C++、旧 worktree、Round8 原件；没有提交或推送。

## 验证、独审与资源边界

- input author tests：42 → 47 → 48项，三次均通过；修补完整内容封印后的合并回归仍包含全部48项，各次资源原件保留。
- runtime adapter author tests：26 → 最终34项，涵盖 private tape、完整分母、原图关闭边、精确旅行舍入、完整模块/预算/权限拒绝、缓存隔离、合同 SHA 与完整内容绑定、迟发布、暗丢存储合同、故意重封后的保护/截止/early/release政策篡改。最终合并82项通过。
- 独立 input 审查：`../phase4_round9_business_input_independent_audit_20261011/REVIEW.md`，14项独立 fixture 测试、1,311,318项机械检查，完整重算 1×/2×父源、时钟、派生、不可达计数；独审未复用 author fixture，CPU 10.953125 秒计在其目录，不重复加到本目录 author 总账。
- 本目录 CPU 逐 invocation 保留在 `author_tests_*.json / runtime_author_tests_*.json / audit_*.json / runtime_adapter_audit_*.json`。每次全量 audit 的 per-scale CPU 是已包含在总 CPU 的子区间，不能重复相加。代码导入以前、文件定位、阅读、编写和普通 shell 检查的 CPU 未完整测量，记未知辅助开销。
- author 显式审计均成功，没有物理失败或重跑；独立审查发现的 adapter 漏洞另保留，不能因 author 测试原先全过而忽略。故意构造的正确拒绝是 expected failures，不作为物理批次失败。一次 PowerShell 不支持的 brace 路径语法和两个尚不存在文件名的读取在定位时失败，随后改为实际 `storage_contracts.py` 和分别列路径；仅是未计 CPU 的工具定位，不影响输入/实验分母。

最终 author 源、测试、输出 SHA 与资源汇总在本目录 `manifest.json` / `resource_summary.json`。统一 core 物理回归和独立 runtime 复核由根代理在共同源码冻结后记录；本目录不以82项 author tests替代全仓共同回归。
