# P5 handoff：native011 → native015 同合同复核

这是独立追加回执，不覆盖 `P5_HANDOFF_DIAGNOSTIC_20261013.md`、011 原始分支或原创新判断。014 仅曾作为等待构建的候选版本，没有运行本次 P5 campaign，也没有生成014执行结果。最终重验采用已由主线确认的015构建。

## 身份与复现

- 基准：`outputs/experiments/g31_ics_long_term_20261013/p5_handoff_011_003/receipt.json`，SHA256 `9e1c7f959ae1d8e0218b08cf0733bcf5e0eb469886d4aaf2d1533edabaef6c14`。
- 新运行：`outputs/experiments/g31_ics_long_term_20261013/p5_handoff_015_001/receipt.json`，SHA256 `2b04cc78128d885790724a9f47249ee3065dd260bfa3e6f94c6af39b89ddb782`。
- native015：`build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd`，SHA256 `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`。
- 逐分支比较：`outputs/experiments/g31_ics_long_term_20261013/p5_handoff_015_001_recheck_context/comparison.json`，SHA256 `7e658f6843baba7882eef8a75126281d10835fc424b2f577c0480c35c25a17ff`。

新增独立入口 `p5_handoff_recheck.py`，执行前要求011归档中的全部10份Python研究源码与当前逐字节相同，并验证用户明确传入的native SHA。它只在调用冻结runner时将其 `EXPECTED` 构建身份常量替换成经校验的015身份，不修改输入、候选、求解、权限或预算。原runner仍执行自己的binary校验。替换范围、旧常量、wrapper源码及事前哈希保存在新的 `p5_handoff_015_001_recheck_context/prerun.json` 和源码副本中；该文件先于任何新native分支写入。正式运行的全部源码前后哈希相同，wrapper自身也未变。

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONDONTWRITEBYTECODE='1'
C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.p5_handoff_recheck run --baseline outputs/experiments/g31_ics_long_term_20261013/p5_handoff_011_003 --binary build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd --expected-binary-sha256 5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098 --output outputs/experiments/g31_ics_long_term_20261013/p5_handoff_015_recheck_new
```

输出目录必须全新；既有输出和比较回执会被拒绝覆盖。默认预算仍为180秒、最多256分支、每分支100000事件、H160。本次不是隔离性能测量，不能用执行墙时认证完整100ms要求。

## 实際执行与精确比较

四份输入文件逐字节相同。初始与真实pending取消后的滚动相位，各保持19、19、9、16个动作，共126个实际native分支。比较保留提交顺序和完整物理请求；只把公共读集修订引起的request名称、expected_version与物理动作身份分开记录。时刻不舍入，相差一个浮点ULP也会被标为不同动作。每个动作仍核对请求实际状态、全部六件业务、原始时间序列和物理审计。

| 检查 | 011003 → 015001 |
|---|---|
| 四因子、八个相位的完整物理候选域 | 全部相同 |
| 126条分支推进与新请求兑现 | 全部到H160，全部verified |
| 126条分支的逐件业务指标与总成本 | 精确相同，0条改变 |
| 40个策略选择（五策略×八相位） | 动作、指标、保护状态全部相同 |
| 请求兑现时间和理由（去名称后） | 全部相同 |
| 独立物理audit | 全部passed，审计摘要相同 |
| 各分支offline physical hash | 126条全部相同 |
| 所有父状态 | 运行前后不变 |
| 强服务基线对本有限域参考的headroom | 八组仍全部0 |

`verified`不表示每条分支均完成六件业务；WAIT和部分指派继续保留未服务业务与完整六件分母。所有完整指派策略仍完成六件。无Storage余量时D1变慢、第三源最低库存约束时D0变慢的反例与严格保护失败都保留；未通过的结果不因新native版本改写成通过。

独立逐项检查 `native_events`、`receipts`、`decisions` 的记录顺序，011和015本组均为0次严格时间回退。因此这次能够支持的是：015时间处理修正没有改变这个冻结P5诊断的动作、物理和业务结果；不能据此说该组曾复现另一场景的near-EPS故障，也不能把内核修正写成此组业务收益。

## 新增验证与研发结论

新增 `tests/test_g31_circulation_p5_handoff_recheck.py` 的5项检查均实际通过，JUnit：`outputs/experiments/g31_ics_long_term_20261013/p5_handoff_recheck_tests_001.xml`。覆盖近邻时刻不得合并、重复物理动作必须拒绝、亚EPS回退必须原样记录、缺失业务指标保持unknown、构建身份不符必须在执行前拒绝。既有10项P5测试文件未改动。

原判断保持：强服务感知普通指派解释全部本组收益，没有独立联合求解增量；工程复核与正确性修复不计论文创新。全部offered逐件保护、同一native物理宿主、固定区内权限、两项业务需求以及完整100ms门槛不变。下一研究接入仍须在有权读取完整业务合同或真实收到相应消息的控制域内，检验多个候选共同资源耦合和有界修复；不能在此零headroom域中堆时点或小网络作为方法推进。
