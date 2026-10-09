# ICS V3 第三阶段运行说明

本轮沿用第二阶段的物理引擎、权限和合成场景族，在新模块中补充非线性学习、场景级配置选择、有限动作预调参考与请求故障统计。没有改变既有 G31/native/Java 基线，也没有接入供应方或真实网络。逐轮决定、发现与负结果见 [PROGRESS.md](PROGRESS.md)，保证范围见 [STRUCTURE.md](STRUCTURE.md)。

## 入口与复现

在仓库根目录运行；只使用已有 Python、NumPy 和 pytest。以下示例均用新的输出目录，避免覆盖已存档的实验。学习/预调参考/配置选择入口拒绝非空目录；请求服务入口同样应手动选择新目录。

```powershell
python -m scripts.experiments.ics_circulation_v3.run_phase3_learning --output outputs/experiments/ics_circulation_v3/phase3_learning_rerun
python -m scripts.experiments.ics_circulation_v3.run_prebalance_reference --output outputs/experiments/ics_circulation_v3/phase3_reference_rerun
python -m scripts.experiments.ics_circulation_v3.run_request_service --repeats 3 --output outputs/experiments/ics_circulation_v3/phase3_requests_rerun
python -m scripts.experiments.ics_circulation_v3.run_scene_configuration --output outputs/experiments/ics_circulation_v3/phase3_configuration_rerun
python -m scripts.experiments.ics_circulation_v3.run_matched_phase3 --output outputs/experiments/ics_circulation_v3/phase3_matched_rerun

$icsV3Tests = Get-ChildItem tests -Filter 'test_ics_circulation_v3_*.py' -File | Select-Object -ExpandProperty FullName
python -m pytest $icsV3Tests --basetemp .tmp/ics_v3_phase3_tests
```

计时实验串行运行。源码哈希覆盖实际依赖，结果目录保存源码快照；无关实验的新文件不影响其他已冻结入口。再次运行同一确认名字空间属于复现，不能称为另一批未见场景。

`run_matched_phase3` 读取本轮存档的冻结模型与配置选择器，将全部 14 个策略在配置测试的同一批 40 个场景重放，并统一使用 joint_control 的候选生成器。它只做冻结后的同场景补充核对，不进行任何拟合，不把已评估场景重新称为未见测试；与单独学习实验使用的候选池上限差异在协议中明确记录。第一次加载 bundle 元数据的失败和修复已记入 PROGRESS；成功结果位于 `phase3_matched_configuration_checked_20261009`。

## 非线性候选模型

`MLPValueModel.fit(rows, kind, config=MLPConfig(...), feature_names=...)`：单隐层 32 单元、tanh、全批 Adam。完整 23 特征时 801 参数；直接和残差模型结构相同。归一化仅使用训练行，显式非 train 行被拒绝。direct 拟合完整成本，residual 拟合 `f(x)-f(x0)` 与“真实成对增量减解析增量”的差；部署时二者都严格保持基准增量为零。

`to_dict/from_dict` 保存参数、标准化、配置、输入模式、训练数据指纹与损失历史。输入消融只读取所选字段；direct 可去除解析分数，residual 必须保留结构所需的时间化解析分数。模型评分不是授权接口。

正式协议先记录，再复用 phase2 确认实验中的 80/20 训练/验证源组。测试和部署各 40 个新 `phase3confirm` 源组；所有候选/未来分支按源组划分。固定 epochs=400，四种 lr/L2 配置，分别在种子 17/29/43 上仅用验证 regret、RMSE 选参数，不用测试选择最好种子。20/40/80 样本量曲线只使用主种子 17。两个输入消融是“无解析分数”和“仅路线属性”，它们不能孤立证明某个时间机制的因果贡献。

48 次拟合全部完成后才生成新测试标签。正式为 320 次新成对分支、160 次标签参考回放、14 策略×40=560 次完整部署，部署预测回放内部调用另列。既有 800 次训练/验证分支是复用标签，不能重复计作本轮新仿真。smoke 仅检验管线，其中 ridge 仍来自旧 80 组模型而 MLP 只用 8 组，不是公平收益比较。

## 场景开始时选择配置

`initial_features` 只接受初态与已发布预测。`fit_selectors` 在训练完整回报上拟合最佳固定配置与一层决策树；每叶最少 8 个训练组，切分阈值来自训练特征。验证集仅在两个已拟合选择器之间选择，持平优先固定配置。

四个完整配置是：基准＋反应式、时间化解析＋反应式、时间化解析＋预测先路由、时间化解析＋预测先预调。80/20/40 个新配置源场景各真实运行四个完整 episode，共 560 次。因为选择只发生在场景开始，可从存下的完整回报评估选择器，不重复仿真，也不称为带未知倾向概率的离线策略估计。这是全信息基线，不是 PPL/AIPW 或置信界实现。

## 有限动作预调参考

`BoundedForecastPrebalancer` 包含不调拨，并枚举最多两次合法空盘调拨的短序列。默认每次决策 12 次回放、每状态候选池 8、搜索调用 32、每请求路径 2，使用最早出发/需求时刻对应出发两个变体。每次转移仍通过原授权器，并复用源节点/源区的需求前缀保护；有未接纳保护任务时不新增调拨。

候选限定当前空闲可导出的盘与有已知缺口的目的地，未纳入任意暂存位置或未来释放盘的预约派发。评分只用公开预测构造代理未来，固定反应式继续策略，不递归调用预调器。匿名预测需要显式配置目的地代理，不能从评估真值推断目的地。

所有预算截断和回放失败均记录。即使生成的序列全部评分，也只是所生成的有限动作集合与声明预测代理上的比较，不是完整物理动作空间的最优 MPC。四个既有机制样例只算回归，另 8 个新源组单列。

## 请求服务与故障账本

`ResourceOwner` 持有本地快照、唯一授权器、锁和请求回执；提交内部再次绑定 bag/tray 身份。`RoutingRequestService.handle(request, transport)` 使用有界重试，保留原已接受承诺。仅经重新检查的完整旧承诺可作为旧路线回退，裸候选或进入中的安全前缀不能冒充完整可用旧路线。

七类结果：新路线成功、仍有效旧路线、搜索耗尽、有静态证明的不可达、通信失败、提交失败，以及本地处理失败。静态不可达必须在完整有向图上给出并复验割集；搜索预算耗尽不等于不可行。错误的生成器/评分器也保留在分母里。丢失回执时分别记录资源所有者是否已提交、请求方是否获知成功，重试通过幂等回执避免重复消耗资源。

TransportScript 的排队/传输时间是**合成输入**，不会让物理时钟自动前进；实际网络时间明确为空。真实 perf_counter 统计本地取快照、候选生成、特征、评分、复验和提交；再单列“本地实测＋合成传输”的会计总时长。17 类样例×3 次是故障覆盖，不是现场故障频率，也不证明生产端到端 100 ms。
