# 航班动作价值模型六账户接口 v2（2026-10-19）

`foundation_action_value.py` 的六账户接口现要求逐账户、逐 forecast region 声明可见性和完整性，防止空列表或 compact 代表件被误当完整业务总量。这里只完成未来 C01/C11 候选接口修复；未运行 C 原生分支、未训练 C 动作模型，也未改变 B1 预测器或重复小域的冻结监督模型。

## 版本与输入

- Observation：`g31.foundation.flight_aware_observation.v2`
- Features：`g31.foundation.action_conditioned_features.v2`，88 维。
- Model：`g31.foundation.action_conditioned_value.v2`

旧 v1 数据或权重不自动补为“完整零账户”，也不迁移 43/52 维旧模型。调用 `wrap_observation(...)` 的六个账户仍为列表：`current_free_trays`、`known_waiting_jobs`、`loaded_release_forecast`、`committed_inbound`、`committed_outbound`、`unresolved_requests`。新增必填项：

```python
accounts['coverage_by_account_region'] = {
    account: {
        region: {'visible': True, 'complete': False, 'observed_at': now}
        for region in forecast['new_demand_mean_by_region']
    }
    for account in ACCOUNT_NAMES
}
```

`visible=False` 必须同时 `complete=False, observed_at=None`，且该账户区域不得存在已观察记录。部分观察到的账户用 `visible=True, complete=False`，保留已知记录。只有适配器确有该账户区域范围完整、当前合法可见的证据时才可声明 `complete=True`；这是适配器的输入声明，本数值模块不会把自填布尔值升级为原生完整性认证。完整空列表才代表已知 0；覆盖表不得少写或额外增加预测映射区域。所有记录均须带 `region`、`observed_at`，且不晚于对应覆盖观察时点和当前时刻。

每个候选的 source/destination 分别输出六账户的 `*_visible`、`*_complete`、`*_observation_age_s`，以及已经观察到的数量。数量属于相应观察时点的记录，不是全局真值，也不是当前可调度库存证明。未知账户不会把已有记录清零；未知未来承诺也不能借这些记录推定库存可用。

## 等待业务的两种记录

独立公开业务记录须写明 `kind='job'`、`origin`、`business_bag_id`、`region`、`arrival_at`、`observed_at`。一条实际业务计数为 1，未来到达和重复身份被拒绝。

Compact 等待组使用：

```python
row = {
    'kind': 'waiting_group', 'origin': group['origin'], 'region': mapped_region,
    'observed_at': group['demand_observed_at'], 'count': group.get('count'),
    'provenance': {
        'kind': 'public_control_projection_waiting_group',
        'group_sha256': digest(group),
    },
}
```

`group` 必须来自本次传入公开 `base_observation.control_projection.waiting_groups` 中相同 origin 的唯一一组，projection schema 必须为 `g31.analytic_control_projection.v1`。计数及摘要需与该公开组精确相符；不能用私有业务文件或最终结果补值。公开 count=7 即计 7，即使 `jobs` 仅包含 1 个代表件。代表业务自身也须已经到达、状态为等待，且属于该 origin。

公开 count 未知时，row 的 count 也必须为 `None`。此时保留公开代表业务数作为已知下界，输出 `*_known_waiting_count_missing=1`，并把有效 `*_known_waiting_jobs_complete` 置 0；即使调用者误称覆盖完整，也不能把未知 count 当作精确总量。同一 origin 的整组与个体不得重复相加；跨组或个体的重复业务身份也被拒绝。

## 缺口及承诺规则

只有候选区域六账户均完整且到达前需求预测已知时，才计算 `waiting + new_demand - free - release - inbound`。否则 `*_estimated_deficit_missing=1`，缺口数值填 0 仅作显式 masked 数值位；转移后的 scarcity/deficit 与依赖 scarcity 的 interaction 同样屏蔽，不能把该 0 当作平衡库存。

已有重复供应防护、conditional release 不算当前空托、已承诺 outbound 从所有 supply 项排除、inbound ACK 与账户时点先后检查、未解决请求不得同时计作 committed inbound 的规则继续保留。同一物理 `tray_id` 在 supply 或 outbound 账户出现不同 generation 时直接拒绝，不能把代次当成两台托盘，也不能用旧代次绕过 outbound 排除。

## 原始 ACK 与接收方公开证据

`committed_inbound` 接受原始 `ack_status` 为 `accepted`、`in_transit` 或 native027 实际使用的 `departed`，但必须保留完整 `native_ack` 原对象，不能把 accepted/pending 静默改名为 departed。accepted 只表示已接受的未来承诺，不表示实物已经出发；departed 也不成为 current_free。received、pending、rejected、unknown 不进入未来 inbound。

每条记录还须有 `ack_provenance={'kind':'public_inbound_ack_evidence','evidence_sha256':digest(evidence)}`，绑定 `base_observation.inbound_ack_evidence` 中同 request 的唯一当前公开证据。证据 schema 为 `g31.foundation.public_inbound_ack.v1`，含 `kind`、`source_owner`、`target_owner`、`request_id`、`tray_id`、`generation`、`region`、`captured_at`、`available_to_owner_at` 和原始 `native_ack`。kind 可为 `own_public_outbox`、`received_peer_ack`、`native_receiving_lease`；前者只能服务相同 owner 范围，peer 证据必须实际投递给当前 owner。ACK observed/delivered、capture、owner 可得时间、账户 observed 必须依次不晚于 now。

**这个接收证据包装目前只是严格接口和纯 fixture，尚无真实跨 owner C 适配闭合。** native027 `observe_protocol(owner)` 的客户端 ACK 属于该 owner 的发送账本；已有 v2/v3 已送达 capture 中的 action ACK 又缺 tray/source/destination 完整 payload，单独两者都不足以证明接收方 inbound。后续必须以合法发布的完整源承诺或受限接收端点建立适配，另行登记协议扩展。当前不得从 C 的 private result/全局 controller dump 补接收方证据；缺失时保留账户 unknown。本文新增 schema 不表示 native 已经提供该端点。

## 验证

定向测试覆盖六账户各自未知/完整零的区分、区域隔离、部分观察下界、compact 精确 7 件与单代表件的差异、未知 count、公开 provenance 绑定、私有补值拒绝、组和个体重复、时间顺序、原有 committed exclusion、旧版本拒绝，以及原有小型数值拟合契约测试。没有为本次修改生成 C01/C11 实验结果。
