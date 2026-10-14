# V3 三项独立审核问题的实际修复与验收

日期：2026-10-13。工作区：`C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`。
V3 修复比较基线：`fccd4819532701ee4173ec598822450d962d4e61`，其生产实现对应 `defd79effe02ee13f1a5bbbbc5143f6d0dce2f63`。
本记录仅说明 V3 正确性修复；不代替 native G31 闭环、原业务或实时性验收，不计作方法创新。

## 修复前后的独立原始探针

没有修改外审 `reproduce_audit_probes.py`。修复前以导入的固定字节执行 `--require-fixed`，退出 1；修复后相同参数退出 0。两次探针均完整执行，均 `source_changed=[]`。

| 问题 | 修复前实际观测 | 修复后实际观测 |
|---|---|---|
| A：旧 FullGraph 对 Storage 的错误证书 | K=1 返回 S-W-G，到达5、卸载6，最早标志true；同validator接受到达3、卸载4见证。只用30工作单位；去掉长备选则错误空返回并耗尽 | K=1/2/3、去掉长备选均准确拒绝 `full_graph_reference:storage_contract_not_supported`；不是把K加大或隐藏证书 |
| B：普通screen默认K | 原生成器3条，screen4条 | 完整有序候选相等，3条 |
| C：checkpoint账本 | 保存后(0,0)，原factory查询使保存状态变(0,1)，恢复也(0,1) | 保存后(0,0)，原factory查询后仍(0,0)，恢复仍(0,0)，factory不再与原engine共享 |

原件：`before_probes.json`、`before_stdout.log`、`before_stderr.log`、`before_exitcode.txt`；对应 `after_*`。完整小例输入、候选、手工可行见证和源哈希都在JSON中，不只保存PASS摘要。

## 实际实现与边界

1. `routing_reference.py`：公共 loaded/empty 入口拒绝含Storage合同的模型（包括StorageSnapshot普通袋壳、普通Snapshot隐藏StorageBag）。拒绝前清除上次普通查询的 earliest/exhausted 证书，设置明确能力边界；不把未知当不可行。现有独立Storage阶段oracle和StorageCandidateGenerator保持。消费旧证书的 `run_phase4_routing.py` 使用普通域；拒绝会阻断不支持的调用，未赋予它新Storage最优性。
2. `terminal_capacity_screen.py`：普通默认K从4改3，显式K原样传递，空盘默认1保持。新增冷/热、普通/空盘/Storage、正常/耗尽、记录上限回退的整组候选、状态、工作量和实际缓存比对。
3. `runtime.py`：checkpoint使用同一deepcopy memo一次复制支持的policy对象图，保留fast、新generator、真实slow搜索的同分支累计账本关系。已知可变factory包括TerminalScreenFactory和其BudgetFactory包装；内部配置/任意用户工厂保留原所有权约定，不承诺隔离用户闭包私有状态。`TerminalScreenFactory.__deepcopy__`明确复制自己的包装状态，避免代理 `__getattr__` 意外委托外部工厂的复制协议。

旧测试明确要求显式factory与wrapper共享累计账本，因此采用审核允许的完整对象图方案，未通过改变旧断言转换为每generator分账。两兄弟恢复与直接fork检查：保存状态不变、分支账本不串、fast/slow/new-factory累计不漏、Budget计数一致，热cache保留但跨分支不共享，新factory仍建冷cache；错误与预算耗尽各有账。

## 回归结果

`full_001/results.json`、`full_001/junit.xml`与stdout/stderr记录：

- 原89文件 **1519项通过**；逐文件字节与冻结清单完全相同。
- 新 `tests/test_ics_v3_executed_audit_regressions.py` **61项通过**。
- 总计 **1580 passed，0 failed，0 errors，0 skipped，pytest exit=0**。
- 被测212份原生产/测试及新增测试文件在运行期间未改变。
- 相对固定V3只有上述3个生产文件不同；原测试未删改。
- Python3.11.9，Windows，禁外部pytest插件，BLAS/OMP线程1。pytest子进程含启动wall165.8562675秒；CPU未测。这不是100ms单路由更新的证据，也不是跨平台加速比较。

完整六份夹具已按冻结gzip及展开字节哈希恢复，总133,186,733字节。`fixture_restoration_003.log`为成功原件。

## 复现命令

在上述工作区 PowerShell 中（每次输出选新的路径以保留历史）：

```powershell
& C:/PROGRAMING/python3.11.9/python.exe docs/external_review/g31_v3_20261011/reproduce_audit_probes.py --root . --output outputs/experiments/g31_ics_circulation_20261013/v3_correctness/recheck_probes.json --require-fixed
& C:/PROGRAMING/python3.11.9/python.exe docs/ics_circulation_v3/review_20261011/tools/prepare_fixtures.py --root C:/PROGRAMING/czr005/.g31_ics_circulation_worktree
& C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_circulation_20261013/v3_correctness/run_regressions.py --root C:/PROGRAMING/czr005/.g31_ics_circulation_worktree --output outputs/experiments/g31_ics_circulation_20261013/v3_correctness/full_002
```

`run_regressions.py`独立读取封存manifest中的89测试文件，不修改原发布runner或其源码身份约束，完整调用pytest并重算JUnit。相对固定V3的实际补丁：`v3_correctness.patch`，可用同目录 `export_patch.py`重新生成。

## 开发中失败记录与解决

- `targeted_001`：新增测试参数名 `request` 与pytest保留名冲突，收集失败，改为 `query_kind`。
- `targeted_002`：新增外部factory复制反例暴露 `TerminalScreenFactory.__getattr__`会泄漏内层 `__deepcopy__`，通过明确的factory复制协议修复。`targeted_003`90项通过，随后全套通过。
- 初两次fixture恢复在Windows sandbox内 `Path.resolve(strict=True)`报WinError5，分别保存 `fixture_restoration.log`、`fixture_restoration_002.log`。对同一个只写独立工作区的hash验证命令申请工具级提权后成功；不是删检查或改fixture。未发生自动审批拒绝。

## 未扩大的结论

这些修复不证明旧44袋0/44的原因，不改变现有Storage/分区参考的其他能力边界，不意味着旧整数FullGraph已支持Storage。三项均为 `engineering_only / correctness`。native G31真实循环和同模型方法增量继续另行实现及验收；本部分未提交、未推送。
