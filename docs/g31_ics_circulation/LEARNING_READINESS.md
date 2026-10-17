# G31 Learning 就绪状态

更新：2026-10-17；依据用户批准的 `G31_ICS_CODEX_FOUNDATION_LEARNING_20261017.md`（SHA256 `1baf33f00dd1c29cb9c2d74f5310340bc588d04482c520752530e0155011a4cf`）。本轮以本文件及 `NEXT_ACTION.md` 接续；`RESEARCH_STATE.json` 的上一轮阶段、旧实验和旧失败仍作为历史保存，不以其旧“先 T5、暂不训练”阻止本方案 L0。

## 当前边界

| 层／工作包 | 本轮实际能力 | 仍缺什么 |
|---|---|---|
| P0 | 核准研究分支 `codex/g31-ics-v3-circulation`、HEAD `a7f7821f`，保留此前未提交修改和用户父目录 PIBT | 不切换 main、不提交推送 |
| P1／P2 | 同一 native027 的 reset、owner 观察、候选、提交、下一事件推进和终态；原有源／接收检查、拒绝与重复策略激活 | 后续仍执行 retained-policy，尚不能提供新事件后的自由 R1/R2 学习动作；不宣称完整 P1/P2 或 L1 |
| P3 | 新 initial-only 按需提供器；排序先于推演，K 包含04；仅计算所选后缀，full32 保留参照 | 常驻跨请求绑定、内部 clone／rollout／source-check 独立归因、事件后提供器尚未完成；建议仍无执行权限 |
| P4／P5 | 原后续真实观察及不可撤前缀守卫继续保留 | 新释放预测刷新、当前事件重建与可变后缀修复尚未实现 |
| L0／P6 | 真实可训练样本、线性与两层64单元 MLP、按场景留组训练／重放、昂贵推演前的共享评分 API | 仅3旧场景 smoke，不是机场泛化或学习接管证据 |
| L1／L2／L3 | 明确门禁，不把排序或固定后续执行称为闭环RL | 后续可学习动作、配对多步评价、受限接管及完整100ms／原流认证 |

## 已运行的证据

结果集中在 `outputs/experiments/g31_ics_foundation_learning_20261017/`。

- `native_001`：新原生薄封装单格54.219秒／90秒硬限，5件完成、3盘守恒、18次遍历闭合。L盘3次装卸、2次跨区返空接收并再次装载；完整153条原生回执、jobs、trays和输入与原004同基线精确一致。4次影子记录未改物理hash；这是本实例证据，不是任意影子程序的隔离保证。1717次策略激活不是1717个自由决策。独立核查范围见 `native_001/independent_physical_audit.json`。
- `l0_002`：192候选行，6个owner决策组但只有3个场景组，43个合法语义特征；标签、对方行为假设和执行资格分开。CPU单线程80轮，首次训练7.983秒；各3个留组模型及全smoke集成模型。K8条件最优保留率：规则2/6、线性4/6、MLP5/6；平均条件regret分别0.212667、0.106333、0.018167秒。模型原始首选均有4/6不满足条件保护，不能绕过原保护门。不是独立机场泛化结论。
- `budgeted_001`及`native_001`：B真实当前观察下K4=[4,0,1,16]，只运行3组上下文、4次fork／resume；4份完整预测与随后full32逐字段相等。K4封存止2.638秒、导出止2.658秒；同场景full32封存止9.721秒。但K4漏掉joint25，条件regret2.419秒；也漏掉公开兼容域最优12，组件regret0.119秒。单次顺序诊断，不是ABBA，不声明因果加速百分比或100ms达标。
- `budgeted_learned_001`：独立新原生会话65.891秒／90秒硬限，留出mechanism的线性模型与同L0规则均在B的full32之前评分、各只推演K8（04含在8内）。两组16份完整预测与随后teacher精确相等，各24个未选候选未被推演；规则5组前缀、学习7组，各8次fork／resume、17次proof。规则封存止4.003秒、学习4.888秒、teacher10.281秒；顺序小样本不作因果测速。两组均选择04，条件joint regret同0.319秒、兼容组件regret同0.119秒，**本场景没有学习收益，学习组多算前缀且观测更慢**。原生仍执行原基线，非学习接管。
- 上述按需对照是在真实当前观察上的只读建议实验，teacher在其后为独立语义核对仍实际运行。不能称整条基线已去掉full32、整个实验少算或已经达成实时部署。
- `l0_001`旧特征草稿、P3测试最初临时目录setup错误及所有旧运行均保留；正式L0结论只用修正后的`l0_002`。没有把候选行当独立场景，没有用unknown填零标签。
- `pilot_001`：统一入口实际完成`smoke`（64.516秒／240秒硬限，原生基线→采样→真实训练）、`evaluate`（0.734秒，自动定位本次smoke产物）；两次均正常退出，来源与配置未变化。`train-rl`实测返回`blocked_L1_not_certified`，没有启动训练；工作子进程正常写出门禁回执，外层CLI按设计退出2。不是只跑`--help`或模拟成功。
- `final_validation_001`：旧447项及新113项合计**560项全部通过**，无失败、错误或跳过；81.125秒／180秒硬限，686份登记源码哈希前后不变。开发验证结束时未提交、推送，父目录用户PIBT源码哈希未改变。用户随后另行授权发布到既有GitHub研究分支；发布范围见 `docs/external_review/g31_foundation_20261017/RELEASE_SCOPE.json`，最终提交与远端核验见审阅包 `publication.json`。

## 统一入口

在研究工作树根目录执行；本机解释器为 `C:/PROGRAMING/python3.11.9/python.exe`：

```powershell
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_learning_pipeline --help
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_learning_pipeline smoke --config configs/g31_ics_circulation/learning_pilot_v1.json
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.run_learning_pipeline evaluate --config configs/g31_ics_circulation/learning_pilot_v1.json
```

另有 `baseline`、`collect`、`train-ranker`、`train-rl`。目录不允许覆盖；复现应先复制配置并登记新的`run_id`，不要删除已有输出。`collect`导出保存数据，不谎称产生新独立轨迹。`evaluate`重放留组评分，不冒充新的测试数据。`train-rl`目前明确返回`blocked_L1_not_certified`和非零退出，不执行假的RL训练。

CLI父进程使用Windows Job硬限制，冻结配置、保留失败与过程结果；子进程核对登记配置，退出时复核来源。配置K8只用于按需建议实验，原生retained基线仍支付每owner full32。观察／预测／提交、物理时间、墙钟／CPU、冷暖／关闭不能混账。

本机实测Python3.11.9、22逻辑CPU、约31.4GiB RAM；物理GPU为RTX4070 Laptop 8GiB，但现有PyTorch2.12.0是CPU版，CUDA不可用。本轮训练实际用CPU，没有连接其他机器或申请GPU预算。

## 下一项具体工作

先把真实later collection绑定到新的owner决策能力，再提供当前未发动作候选与原保护／提交链：优先B的first_reuse_route二元动作域，保留None的native_default语义、真实送达消息、既有完成承诺和不可撤前缀。必要时实现明确的`LaterSeedSpecification`及同语义重建，不复用旧initial未来分叉冒充当前状态。此后在已验证有限范围立即做一次真正多步RL；不再以没有headroom、全天未过或100ms未认证阻止已达门槛的首次学习。

最终R1/R2、逐件严格保护、全部原任务和完整100ms均保持目标；本轮不宣称新方案全部完成。
