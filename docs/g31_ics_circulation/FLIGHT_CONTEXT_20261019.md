# G31 可选航班上下文与数据可用性（2026-10-19）

新增 `scripts/experiments/g31_ics_circulation/foundation_flight_context.py`，提供独立、版本化的计划输入适配器。它不读取逐件任务流，不建立需求模型，也未接入原 initial 43 维 / later 52 维特征或 checkpoint。无独立计划源时仍为 `None`，原执行路径不变。

## 本地数据审计

检查范围为当前工作区的原始任务文件、processed 任务、G29/G31 工作负荷构造代码及其已有 manifest；不是机场所有外部资料的完整清点。

| 现有资料 | 本次实际核实 | 可用范围 / 缺口 |
|---|---|---|
| `legacy/jichang_origin_readonly/inputdata.txt` | 28,506 条非空任务记录，全部 7 列；表头 `ID EntryTime(s) STD(s) star end Unloader Loader` | 有逐件实际入流及 STD；无真实航班 ID、发布时间、owner 接收时点、历史计划版本或 ETA/ETD 更新 |
| `data/processed/tasks/inputdata.jsonl` | 字段为任务 / 盘 / 段 ID、起终点、实际或计划段时间、STD、早到标志、来源行号 | 未增加独立航班消息来源或消息可见时点，不能由任务 deadline 倒推出可提前订阅的计划 |
| `src/czr005/io/legacy_tasks.py` | `RawLegacyTask` 保留上述七列与来源行号；原 early bag / storage 展开规则独立存在 | 保留既有业务 deadline 与 storage 合同；计划更新不能自动修改这些规则 |
| `scripts/eval/run_g4irsf29_workload.py` | `_flight_key()` 使用 `(std, end, unloader)`；本地原始记录共有 360 个这种分组 | 属于 historical_group，不是已核实真实 flight_id |
| 同模块 `_flight_row()` | `raw_bag_count`、`first_entry_time`、`last_entry_time`、`source_counts`、`loader_counts` 汇总完整实际任务 | 仅可作离线标签 / 历史统计，不能直接作为早期 actor 先验。本地 artifacts 对应目录当前只有 workload manifest，没有独立计划更新日志 |
| `scripts/eval/run_g4irsf31_nanning_workload.py` / `original_workload.py` | 使用既有历史任务投影、STD / storage 构造及 1x/2x 规则 | 不提供发布 / 接收历史，也不能证明现场中转或注入口映射 |

本次检查的原始任务文件 SHA-256：
`0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87`。

因此当前资料足够实现接口和合成消息反例测试，**不支持真实航班更新回放或跨日需求预测评估**。适配器没有从这些完整任务表制造计划消息，没有把缺失发布时间填成零。

## 接口与语义

两个纯 Python 入口：

```python
adapt_context(payload=None, *, owner, now, expected_time_basis)
select_context(history=None, *, source_id, owner, now, expected_time_basis)
```

返回不可变 `FlightContext` 或 `None`；`to_dict()` 返回隔离的 JSON 数据副本。schema 为 `g31.foundation.flight_context.v1`，严格拒绝未知输入字段。单包完整字段：

- `schema_version`, `source_id`, `version`：一个 source 的单调正整数完整快照版本，不能把局部增量包当作整快照。
- `published_at`, `received_at`, `owner_scope`：每个包只绑定一个接收 owner；通常必须满足 `published_at <= received_at <= now`。
- `time_basis = {unit: "seconds", origin, timezone, conversion_version}`：所有消息及计划时间已经按声明转换到同一秒轴，必须与调用方声明严格相同。适配器不推断机场时区、不自动转换 STD，也不补写当前资料尚缺的时间映射。
- `availability_basis` / `static_assumption`：通常为 `source_publication` / `None`。发布时间不可得的静态计划必须显式使用 `static_predeclared`，保留 `published_at=None`、提供非空假设说明和真实 / 明示设定的接收时点；不能称历史更新回放。
- `validity_policy = {mode, valid_until}`：`until_superseded` 对应 `valid_until=None`；`expires_at` 使用排他的截止时点。它描述计划适用期，不是原生接纳 TTL，不产生任何当前执行资格。
- `entries`：独立计划条目；`flight_ref` / `identity_kind` 显式区分 `real_flight` 和 `historical_group`。STD/STA/SOBT/SIBT 分别只匹配 ETD/ETA/EOBT/EIBT，允许事件时间在 `now` 以后。

可选件数估计必须同时带 `estimate_source` 和 `estimate_kind`（`forecast` 或 `confirmed_advance_record`）；拒绝 `final_actual_total`。可选 `planned_injection_region` 必须绑定 `mapping_version`，未知区域与数量保留 `None`。`plan_status=cancelled` 只是已收到的计划事实，不删除已入流行李，不隐式把预测件数改成零。

`select_context()` 对指定 source / owner，仅解析截至 `now` 已收到的消息内容；其他 owner 收到的新版本和未来消息均不进入本地上下文。选择最高已收到版本，晚到旧版本不能回退；同版本不同内容拒绝，重传保留最早接收时点，避免信息年龄被清零。新版本过期返回 `None`，不会复活已被替代的旧版。空 `entries` 是明确的空计划快照，不能解读成零未来需求。

适配器检查结构和声明之间的一致性，不能认证发布方身份或证明其所标注的估计确实提前存在。接入真实源前仍需独立核对来源、字段可得时点、真实航班身份、时间转换与入口分配版本。不能把全天真值改名为 `forecast` 后声称通过了防泄漏证明。

## 本次验证与后续边界

定向命令：

```text
python -m pytest tests/test_g31_foundation_flight_context.py -q
```

结果：**34 项通过**。覆盖未收到 / 晚到 / 另一 owner 先收到、旧版回退、重传年龄、同版冲突、过期不能恢复旧计划、静态缺失发布时间、时基不匹配、事件语义、映射变更、取消、事后标签拒绝、无计划保留 None 和输入 / 输出隔离。均为合成接口测试，未运行 native 或需求训练。

没有生成未来 jobs、实际可用库存、区域需盘曲线或执行命令。已到未服务与未来剩余需求去重、双区域托盘释放去重、真实预测误差和业务收益属于后续预测 / 账户模块验证；本接口不声称完成这些证明。后续若消费航班特征，须新建训练数据与模型 schema，不能直接扩展旧权重输入。
