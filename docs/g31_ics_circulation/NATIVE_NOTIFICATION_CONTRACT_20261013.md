# Native owner notifications and strict circulation time, version 015

本文件记录 2026-10-13 实际实现与回执。它是工程接入及正确性修复说明，不构成方法创新、学习放行或完整 100 ms 通过声明。原用户文件及 011–014 二进制、输出均保留；没有提交或推送。

## 实际执行合同

G31 仍是唯一物理执行宿主。Python 不推进托盘、行李、Storage、有限盘库存或区域模块状态。S4 逐跳决策、即时合流仲裁、正常分拣保护、区内出口保底与接收权限沿用实际 native 路径。

显式加入以下输入启用通知：

```python
data["owner_protocol"] = {"enabled": True, ...}
data["owner_notifications"] = {"enabled": True}
session = native.NativeSession(data)
```

通知要求实际 owner protocol 已启用。其开关只控制通知状态；015 中所有 circulation 策略，无论采用定期控制还是事件控制，都使用下面相同的严格时间排序。旧 `legacy_g31` 保留原比较器和原行为。014 起 circulation 的封印格式发生明确变化，不能以 011–013 二进制的封印冒充新执行结果。

```python
owners = ["A", "B"]
cursor = {"A": 0, "B": 0}
reply = session.advance_until_owner_notification(
    owner_ids=owners, after_sequences=cursor, horizon=30., max_events=100000)
```

返回字段：

| 字段 | 合同 |
| --- | --- |
| `status` | `notified` / `horizon_reached` / `budget_exhausted` |
| `physical_time` | 当前 native 时钟；预算截断时仅为调度诊断，不能据此授权策略决策 |
| `timestamp_complete` | 当前时刻所有到期事件，包括处理中新增的同刻事件，已全部处理 |
| `horizon_complete` | 请求 H 已真实完整处理；数值时钟碰到 H 不足以认定完成 |
| `notifications` | `{owner: {sequence, observed_at, change_mask}}`，仅返回比对应 cursor 更新的 owner |

`owner_ids` 不得为空或重复，cursor 的键必须与 owner 集合完全一致，不接受未知 owner 或未来序号。序号是各 owner 独立递增的本地版本，不引用全局事件计数、全局 traversal ID 或队列序号。`observed_at` 是事件实际处理/承诺提交时的 `now_`，不能用未来 ready/admission 参数替代。mask 汇总该 owner 最新实际时刻发生的原因；它不是完整历史事件列表。策略仍需读取合法的当前 owner 投影。

`owner_notifications(owner_ids)` 只读当前本地版本，不消耗通知、不改封印；若当前时刻尚未处理完则拒绝。初始输入含 t=0 到达时，先用全零 cursor 调用 horizon=0 的推进接口完成真实初始化事件，再读取。控制器提交新命令后，零延迟 ACK 可以在相同逻辑时刻产生新序号；接口不会把该后继通知吞并为“以前已经处理”。调用方仍必须限制事件数和控制激活次数，防止零延迟反馈无限循环。

## 通知来源与权限

| bit | 实际来源 |
| --- | --- |
| 1 | 已发生的本地业务到达 |
| 2 | 真实本地装载、Storage、卸载/hold、服务、逐边移动或容量承诺/释放变化 |
| 4 | 实际送达该 owner 的需求快照 |
| 8 | 实际送达该 owner 的服务预测或撤销 |
| 16 | 实际送达客户端的 ACK，包括真实重复副本 |
| 32 | 本地客户端状态实际变为 `timeout_unknown` |
| 64 | 现有 `known_faults` 权限范围内，已实际送达并更新的本地边故障/修复消息 |

物理承诺在真实 `reserve_enter` 提交点通知相应源/接收 owner，使用提交时刻，而不是等将来的 EdgeEnter 才报告已存在的容量占用。固定区内模块权限不因通知开放。

隐藏的 owner outage、尚未送达的 wire/ACK、丢弃 ACK、未发布未来到达和远端私有物理活动不直接产生本 owner 通知。远端事件确实改变本地可见容量或送达消息时，其真实本地影响才合法触发。零延迟故障在成熟 E4 的 inline 实际送达路径也触发；`drop_notification` 分支不触发。circulation 内严格区分零延迟与正延迟：例如 `1e-10` 的消息延迟也必须等待实际送达，不能因小于旧 epsilon 而提前可见。

没有返回下一私有事件时刻、处理了多少全局事件或 owner 隐藏健康状态。预算耗尽返回空 `notifications`、`timestamp_complete=False`、`horizon_complete=False`。应保留原 cursor，继续 drain；不能拿部分时刻的通知喂给控制器。原有 `step`/完整结果等离线诊断入口不因此成为合法在线信息来源。

## 为什么必须修正 circulation 事件排序

原 `RuntimeEventLater` 在时间差不超过 epsilon 时按微阶段和序号排序。这种近似相等不具有传递性，也允许较晚物理事件先于较早 ACK 执行，随后 `now_` 回退。实际联调保留了 `6.05` 与 `6.049999999999999` 的反例；不是 Python 断言过严。

014/015 的 circulation 顺序为严格 `(time, microphase_priority, seq)`；只有完全相同的浮点时间才进入同刻微阶段。初始化 circulation 时重建已经由公共初始化阶段加入的故障堆；检查点复制实际 queue comparator，封印的 event_queue 部分写入 `circulation_strict_time_order.v1` 及比较器模式，空堆也绑定该模式。恢复要求 comparator 模式与 circulation 模式一致。发生真正排入过去的事件时，取出之前拒绝 `circulation:past_event_would_reverse_clock`，不钳制时钟隐藏错误。

同刻微阶段 floor、仲裁唤醒去重及更早唤醒替换也使用 circulation 严格时间判断；否则仅修堆仍可能吞掉相邻浮点时刻的合法机会。没有无差别改动物理容量、旅行、保底或服务约束中的数值容差。legacy 分支维持原判断。

C++ 标准草案要求 `priority_queue` 比较器形成 strict weak ordering，并以该比较器构建堆：[priority.queue](https://eel.is/c++draft/priority.queue)、[alg.sorting](https://eel.is/c++draft/alg.sorting)。本次属于因果执行与正确性修复，不是论文创新。

## 同期修复：实际剩余节点服务的预测

011 的 loaded 分支曾从捕获时刻重新加完整节点服务。例如服务已于 t=0 开始、持续 3 秒，t=2 捕获却预测 t=5 入边，实际为 t=3。

现在读取已经封印的、本地实际承诺 `service_calendar` 中该 transport leg 的服务结束时刻。`InService` 使用实际剩余服务；已进入 `JunctionQueue` 的服务已完成，以当前时刻作为入边估计下界；尚无实际承诺的 `SourceQueue`/`PendingRelease` 明确拒绝 `no_committed_local_service`，不读未来 heap 填值。loading 分支继续根据真实 LOAD_START、装载时长与尚未开始的节点服务形成估计。无需建立另一套物理状态或增加预测用 checkpoint 字段。

这些值仍是 estimate，受真实路由、容量、仲裁和投递延迟影响；不是释放保证。service=2、command_delay=2 的精确同刻案例已实际验证可成功捕获，不能笼统判为“通知总是来不及”。其消息在 t=2.5 才送达时，仍可能晚于真实入边，不应把 ACK 成功直接记为业务收益。

## 检查点边界

通知 map 的每个 owner 序号、观测时刻和 mask 加入 `native_owner_notifications.v1` 封印部分，仅启用时追加；普通关闭通知的模式不引入该部分。013 与此前的局部兼容承诺不能覆盖后来发现的严格时序漏洞：014 起所有 circulation 都额外绑定严格排序版本。

同一进程内 native checkpoint / fork / restore 精确保存通知与协议状态，包含预算截断但仍处于安全事件边界的状态。Python 事件控制器的 cursor/outbox/待执行 owner 与计时器状态必须与对应 native checkpoint 成对恢复。独立 JSON 不是 native checkpoint 的持久化替代品；没有实现跨进程持久恢复。

## 实跑证据与失败链

全部目录位于 `outputs/experiments/g31_ics_long_term_20261013/`，计数互相包含，不相加为额外通过量。

| 原件 | 实际结果及用途 |
| --- | --- |
| `p1_build_012` | clean build 通过，48.246 s；原件保留 |
| `owner_notification_tests_012_001` | 22 项中 4 失败：一个预算 fixture 未制造同刻 cascade，三个测试字段名错误；未放宽断言 |
| `owner_notification_tests_012_002` | 修正 fixture/key 后 22 通过，native 仍为 012 |
| `owner_notification_remote_physics_012_001` | 新增真实远端盘移动/完成非干扰单项通过 |
| `event_notification_time_probe_012_001.json` | 根控制器记录真实通知时钟不一致 |
| `p1_build_013` / `owner_notification_tests_013_001` | 改通知 hook 使用 now_，构建通过、23 专项通过；尚未解决堆导致的时钟回退 |
| `event_notification_time_probe_013_001.json` | 根联调仍复现；因此不能仅凭小例通过宣称修复 |
| `adjacent_float_before_013_001` | 无 Python 策略的最小反例：通知开/关两项都失败；更早 ACK 被更晚服务挡住却误报 H 完成 |
| `p1_build_014` / `owner_notification_tests_014_001` | 严格 circulation 排序后相邻时刻反例通过；26 项中 1 个新增零延迟故障通知用例失败，定位为 inline 投递漏挂通知 |
| `p1_build_015` | 补齐 inline 故障路径及严格正延迟，clean build 通过，45.347 s，source_changed=[] |
| `owner_notification_tests_015_001` | 28 通过，0 失败/错误/跳过，1.239 s，source_changed=[]；包括 whole timestamp、部分预算续跑、fork/restore、非干扰、精确边界、故障堆重建及预测剩余服务 |
| `p1_checkpoint_validation_008` | 013 阶段曾完成 3 个程序编译/运行，82.118 s；只证明当时版本，不冒充 015 复验 |
| `p1_checkpoint_validation_009` | 015 源码实际 clean 编译/运行 `test_circulation_checkpoint`、`test_circulation_runtime`、`test_g4irsf14_state_clone_protocol`，6 个阶段退出码均 0，85.953 s，source_changed=[] |
| `legacy_parity_005` | 实际重新编译 015 源码，对成熟参照 `46cc46ab6bc121628fd6357e9f3c7636745fd732` 的固定 legacy 场景精确相等，22.689 s，source_changed=[] |

015 二进制：`build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd`，SHA-256 `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`。源文件清单/哈希在对应 build/pytest receipt 中；完整 stdout、stderr、JUnit 一并保留。

可运行专项：

```powershell
& 'C:/PROGRAMING/python3.11.9/python.exe' scripts/experiments/g31_ics_circulation/validate_owner_notification_tests.py `
  --binary build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd `
  --output outputs/experiments/g31_ics_long_term_20261013/owner_notification_tests_015_NEW
```

输出目录必须全新，避免覆盖原始证据。`live_validation_010` 的 391 项中 390 通过、1 个旧 P5 负例断言失败原件保留；这个失败属于旧 epsilon 排序下的历史反例，不能转写成当前严格排序模型的物理结论。

## 016 最终复核状态

016 仅优化 binding 的批量 command 序列化，runtime 编译输入哈希与 015 全部相同。所以上述 `p1_checkpoint_validation_009` 和 `legacy_parity_005` 保持其实际执行与源码身份范围，没有声称为 016 重新运行 C++ 编译验证。

`event_protocol_015_016_comparison_001/assessment.json` 已完成原图全天五策略对比：periodic reactive、periodic predictive、event reactive、event predictive、event joint。除明确列出的计算计时字段外，完整物理结果、请求与回复、控制记录、控制器 JSON 续跑状态、native batch/segment 记录、业务指标和最终 native seal 均逐项一致。它证明本次 binding 优化保持这些运行的语义，不证明方法收益或普遍等价。

最终回归原件为 `live_validation_012/receipt.json`：407 通过、0 失败/错误/跳过，退出码 0，`source_changed=[]`、`compiled_source_mismatch=[]`。其范围明确分为 401 项当前 native/Python 检查、1 项独立进程 frozen 011 历史排序反例、5 项独立进程版本身份检查；不能把 407 项全部称为 016 物理验证。`live_validation_011` 的通过记录保留，012 修正了回执中的历史范围说明后重新执行，不能将两轮计数相加。

完整 100 ms 要求仍未通过。016 事件预测的 7,890 次 owner 激活中有 15 次超过 100 ms，最大 128.084 ms；联合策略有 24 次，最大 199.580 ms。这些还只是 owner 计算子链。总 wall 虽分别由 68.460 降至 49.168 秒、68.511 降至 50.527 秒，联合策略长尾却比 015 的 173.190 ms / 23 次更差。015 存在并行编译且 016 是另一轮运行，因此这些时间只能描述实测现象，不是受控性能实验或 P7 达标证明；详见 `EVENT_CONTROL_PROFILE_AND_SERIALIZATION_20261013.md`。
