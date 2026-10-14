# 本轮定向复核与长期任务起点

日期：2026-10-13。此文件记录本轮做了什么，不能替代主计划，也不把作者回执写成审核者重新运行。

## 1. 结论

当前工程基础可以继续用于后续研发，不建议推倒、回滚或再次把“一盘两服务”作为主要交付。允许的结论是“在已声明的合成合同和已有工程证据上继续构建”，不是“整个算法系统、现场模型或创新已经通过”。

本次三项V3修复的新增回归独立运行没有失败；本轮未重新编译或执行最新native整体验收。下一阶段应从在线宿主/完整checkpoint、物理与服务合同、原图持续运行和两个真实控制层开始。完整执行要求见 `G31_ICS_LONG_TERM_CODEX_PLAN_20261013.md`。

## 2. 实际取得和校验

上传 `implementation_and_diffs.zip` 为308989字节，SHA256：

`bce9c6c9e4954439d157a7bc00610ec691a0668076b9bb70e75a5b1140b96f86`

27个ZIP成员，CRC检查通过，路径检查未发现越出解压根或符号链接。manifest列出的24份工作文件和2份patch哈希26/26匹配。它们包括文档，不称作24份生产实现。

本包没有完整成熟G31仓库依赖、构建产物、`native_acceptance_final`逐场结果和相关原始回执。README中所报1580、48、16、13各有不同口径；本轮没有重跑这些全集，也没有从摘要直接重新计算它们。

## 3. 本轮实际执行的测试

用此前用户上传的精确 `fccd481…` ZIP，按其顶层source_manifest逐项读取122份V3生产Python源码；它们各自哈希匹配原冻结清单。覆盖本轮交付的3份修复源码，加入1份新的回归文件。

实际命令：

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. OPENBLAS_NUM_THREADS=1 \
python -m pytest tests/test_ics_v3_executed_audit_regressions.py -q \
  --junitxml=v3_targeted_exact_002_junit.xml
```

执行环境：Python3.13.5 / Linux。实际结果：61 passed，0 failed，0 errors，0 skipped，进程exit=0；测试前后已绑定源码无变化。对应 `targeted_test_receipt.json`、JUnit和stdout/stderr在证据目录。

这是新增61项定向回归，不是1580项全套，也不是新的原生G31事件测试。它加强了三项修复的验证，不贡献新业务实验或论文创新。

最初本地提取采用了过宽的路径匹配，可能把ZIP内历史source_snapshot混入；该初次重建及其测试不用于最终证据。随后另建exact_002，只从顶层manifest取得122份源码、逐项校验并重新执行。本轮最终测试结论只来自exact_002。未改写旧结果。

## 4. 实际读取范围

| 文件 | 范围/用途 |
|---|---|
| 用户README.md、NOVELTY_LEDGER.md、literature_read_receipt_20261013.json | 完整交付文字；作者自述与本轮验证分开 |
| circulation.hpp | 全文1–194：实体、合同、占用、头距与入边准入 |
| circulation_runtime_impl.hpp | 全文1–475：初始化、生命周期、transfers、恢复/失败处理 |
| bindings/circulation.cpp | 全文1–236：一次性run、输入、配置和输出 |
| native_host.py | 输入/示例及事件审计相关部分；未声称每一行都独立审核 |
| validate_native_cycle.py | 全文1–173：13场构造、验收断言、执行与落盘 |
| event_driven_junction.hpp | circulation定向检索和事件接点；重点11080–11140、18100起checkpoint拒绝；不是约1.9万行全文审核 |
| test_ics_v3_executed_audit_regressions.py | 前部反例与接口测试阅读；完整61项实际执行 |
| V3修复runtime/routing_reference/terminal_capacity_screen | 作为定向测试实际导入执行，相关实现核对；不声称所有路径全审 |
| manifest与patch | 身份和增量定位；完整哈希校验不等于全文代码审查 |

## 5. 新计划必须处理的接口/研究缺口

### 5.1 在线控制与完整状态

binding目前只公开一次性run；circulation checkpoint显式拒绝。没有live请求、完整clone之前，不能在同宿主上做可信的在线滚动控制和反事实标签。这是后续首要依赖，不是要求把正确拒绝删掉。

### 5.2 区域权限不等于zone字段

当前NodeContract只有zone、容量和port控制字段，没有完整的control_partition/resource_owner/等待权限表达；底层can_enter可扫描所有实体，作为物理内核可以接受，但不能将这种全局视图直接作为区域策略输入。未来区域接口要明确投影、消息延迟和权威提交边界。

### 5.3 deadline结果统计不等于事前服务保证

新增Job结构携带deadline，但尚无等价V3 protected对象和完整服务义务；UNLOAD_COMPLETE处记录deadline_met。这个事实不能被写成“已保证每件正常行李不受影响”。需要将原合同转换为实际观测、候选和提交检查，并区分全体业务、已接受义务及不可实现输入。

### 5.4 自动预平衡尚未出现

transfers仍由输入给定，运行时是等待条件后执行请求，而非依据载盘释放预测优化新请求。静态请求保留作回放接口，P3必须允许策略在运行中生成/更新请求。

### 5.5 安全隔离与持续运行

quarantined保留实体是安全基础，不是故障恢复目标完成。需要资源释放/故障修复/新授权驱动重试及恢复，不能永久隔离后用“无冲突”宣布成功。

### 5.6 扩展性与候选域

occupancy/edge_index/库存扫描、全等待任务排序、batch复制历史input/legs/transfers、逐事件计时和全回执汇集均可能成为规模瓶颈；没有本轮全规模性能结果，不定量夸大。先测后改索引、事件唤醒和差分投射，保留所有资源语义。

batch对当前投射状态逐个准入带来保守联合域，README已说明；应由同模型可行证据判断是否需要联合接纳扩展，而不是直接删容量检查。现阶段没有把这一点定性成已发生碰撞bug。

## 6. 创新性核对范围

本轮直接打开并核对arXiv:2603.28968v1的§2–4.5，确认其离线任务后继闭合、冻结外部和阶段化修复。宽泛C2不再适合作主创新。重新打开当前arXiv条目，显示v1；不借未知更新声称已发表。

同时核对Wan/Shin预测派发与Ahn/Park区域OHT的原作者机构/出版社摘要，前者的忙车释放预测与指派、后者的区域去中心化学习已有直接相关内容。两篇的完整方法仍未取得，不声称已排除其覆盖。OHT Neural Double Q-Routing、LPA*和LNS2+RL的本轮阅读范围按主计划来源表记录。

可以继续研究，但只能将循环反馈/边界条件/轻量近似保留为待证假设。创新门应该前置，而不是增加工程量后自动通过。

## 7. Codex不需要等待的新行动

读取主计划后，先在现有完整工作区核对一次final运行身份，然后直接开始P1；已完成工程和三项修复不重做。原件在Codex工作区可访问时不要求用户再次上传。缺现场材料只阻止对应现场结论，不阻止明确代理下的算法和强参考研究。

不得将本复核的“可以继续”改写成网页审核者全量native验收通过。
