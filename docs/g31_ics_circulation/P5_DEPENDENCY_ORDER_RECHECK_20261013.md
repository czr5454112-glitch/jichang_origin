# P5 两边界旧反例：严格时间修正与历史回归范围

本附录更正旧 `p5_dependency_repair_006_001` 的适用范围，旧输入、原始结果与原断言均保留。不能要求修复后的native继续复现依赖错误事件顺序的业务损害，也不能把本次修正计为算法收益。

## 原合同与实际复跑

按原16分支协议，用完全相同的两份输入、两种初始策略、四种固定干预和后续强解析控制，分别实际运行native011和015：

- `outputs/experiments/g31_ics_long_term_20261013/p5_dependency_repair_011_001/`
- `outputs/experiments/g31_ics_long_term_20261013/p5_dependency_repair_015_001/`
- 与原006逐项比较：`outputs/experiments/g31_ics_long_term_20261013/p5_dependency_order_recheck_015_001/assessment.json`，SHA256 `ec5429709615ef3cbfffe86b4af457177864bec6cd3c3d0d5acc986542282c10`。

三个版本归档中的11份研究源码完全一致。新两次执行均完成16条分支，`source_changed=[]`；006与011全部业务指标相同。所有初始、源修复、占用修复的实际请求、取消回复和已观察窗口在011与015之间精确相同。实际供给变动、硬在途最短占用窗与第二次软请求修复并未被取消。

011→015只有以下三个分支的业务指标改变，均属于原 `long_2000m_unknown_source_demand`：普通初始＋两边界、联合初始＋持续强解析、联合初始＋两边界。另一场景八条及本场景其余五条不变。三个原始日志通道（native events、receipts、decisions）在整个16条回放中的严格时间回退记录数，006/011各58，015为0。这是本次有限回放的计数，多个通道/分支可能记录同一因果事件，不等于58个独立缺陷。

## 造成旧约400秒反例的事件顺序

原普通初始的 `branch_002` 为只修源，`branch_003` 为源与占用两边界修复。两版都实际观察到T0正在0→2，预计物理退出401.7，node2服务后的已承诺最短占用延续到401.75。第二边界仍将T1的软返盘请求改为：

```text
earliest_departure = 401.70000000000005 = nextafter(401.7, +inf)
T1节点服务完成     = 401.75000000000006
TP已等待的可入时刻  = 401.75
```

旧006/011在401.75000000000006已处理T1节点服务、申请及授权，然后回到401.75处理TP被释放资源唤醒后的仲裁。稍晚T1先占据node2的400秒入边接收权，TP只能再等一个长边周期。这不是单纯可容忍的浮点成本误差，而是事件因果先后改变了资源授权。

015先完成401.75的所有必要微阶段：UNSEEN从2离开，TP被实际唤醒，TP在401.75取得0→2入边；之后才处理401.75000000000006的T1服务完成。T1真实等待至801.8进入1→2。完整的前后native事件与业务事件均在 `assessment.json` 各分支的 `causal_event_excerpt` 中，不由静态路径预测替代。

| 同一原普通初始 | D0完成 | D1完成 |
|---|---:|---:|
| 011只修源 | 803.35 | 1203.60 |
| 011两边界 | 1203.40 | 803.55 |
| 015只修源 | 803.35 | 1203.60 |
| 015两边界 | 803.35 | 1203.60 |

所有六件业务在015这两个分支中的完整metrics精确相同，T0/UNSEEN、P和两个源业务仍保持。原结论“该输入中第二次修复使D0恶化约400秒”只能绑定旧epsilon排序版本，不能继续用作新物理合同的反例。旧cut证书的图、盘数和独占长入边必要界未因此自动失效；也没有据此证明任何一般正常业务保护。

原runner中的 `relative_to_frozen_ordinary/WAIT` 明确引用006 factor基准，保留其历史命名和版本，不能冒称新015重新运行的配对基准。本次主因果结论来自同015、同输入的只修源和两边界比较，而非跨版本保护比较。

## 原断言保留，新增当前合同回归

原未改测试文件保存为 `p5_dependency_order_recheck_015_001/test_g31_circulation_p5_dependency_repair_before_scope.py`。原D0 `> +399`、D1 `< -399`及审计/修复断言未降低或删除，改以明确命名的 `test_historical_epsilon_order_scope_later_soft_retime_can_harm_other_service` 真正运行历史011。

历史fixture只读取明确的 `G31_HISTORICAL_ORDER_BINARY`，默认本仓 `build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd`。强制SHA256 `19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`；文件缺失、身份不符或执行失败直接失败，没有skip或替换构建。

实际验证发现，同一进程先 `load_native(015)` 再 `load_native(011)` 不报错，却仍返回015的 `__file__` 和同一个 `NativeSession` 类；直接双DLL导入会造成历史假回归。因此历史用独立Python子进程，同时核对传入pyd与实际加载模块文件的SHA，实际执行两条原native分支后返回结果。当前015的测试仍在主进程运行，两者执行范围由主验证器分别记录。

新增 `test_strict_time_retime_cannot_preempt_an_earlier_ready_competing_tray` 在当前构建检查：真实repair_submitted、T0原硬下界不变、T1仍为nextafter候选、软取消实际成功、TP更早获得入边、T1等待超过400秒、两分支所有六件metrics精确相同，以及两条完整轨迹三类时间序列严格不回退。它比仅改业务时间容差更直接约束正确物理合同。

专项最终12项全通过，JUnit `outputs/experiments/g31_ics_long_term_20261013/p5_dependency_order_tests_015_002.xml`。新增测试初版出现TP腿误选（误取P服务时0.85的载盘腿）和系统临时目录访问失败，`..._001.xml` 保留；已分别限定TP从0出发的返盘腿、通过子进程stdout传回结果解决。它们不是native失败，也未用于抹除旧负例。

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:G31_CIRCULATION_BINARY='C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd'
C:/PROGRAMING/python3.11.9/python.exe -m pytest -q tests/test_g31_circulation_p5_dependency_repair.py
```

研究判断：这次移除一个错误物理顺序制造的旧反例；并未得到新联合修复收益。固定图必要界、强参考、所有offered逐件保护和后续两项研发要求继续保留，历史结论按真实版本收紧。
