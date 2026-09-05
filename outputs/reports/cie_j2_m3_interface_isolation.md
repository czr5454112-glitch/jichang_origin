# J2/M3 接口隔离审查

## 结论

本次小范围接口重构通过审查：在未启用学习型合流策略的确定性主路径中，`merge_grant_timing_mode` 只决定请求保留、机会生成、有效性重检和唤醒时刻，`merge_grant_rule` 独立决定同一 ready set 内的赢家。原先由 timing 名称隐式把 J2 强制映射到 M3 的 `destination_merge_grant_rule_for_timing(...)` 已移除，运行时改为读取显式配置的 priority rule。

这项修改复用已有的 timing 与 rule 两个控制轴；没有增加 scorer、guard、模式名、参数或排序层，也没有声称带来性能增益。它只为后续单变量因果对照提供可识别接口。

## 独立性证据

- 同一 `jit_fair_aging_deadline`（J2）机会合同现在可分别搭配 `M1` 或 `M3`。
- 聚焦微型用例中，两臂的首次 opportunity time、candidate count、candidate request-ID 集合、controller generation 和首次 grant commit time 相同。
- 唯一预期变化是 winner：J2/M1 选择 FIFO 上游 0，J2/M3 选择截止时间更紧的上游 1。
- 两臂均完整结束，reservation、物理故障、安全、grant conservation 与 active-bijection 检查通过。
- 旧枚举/字符串名称仍保留兼容性；此次没有引入第三套策略接口。

## G31 默认行为与 caller 审计

`scripts/eval/g4irsf31_map_adapter.py` 仍显式传入：

```text
merge_grant_timing_mode = jit_fair_aging_deadline
merge_grant_rule = M3
```

因此旧实现的“J2 隐式选 M3”和新实现的“J2 + 显式 M3”进入同一个 M3 比较器，G31 的确定性默认选择语义不变。对 `cpp/` 与 `scripts/` 的调用点做了静态审计：实际设置 J2 的 runtime caller 均同时显式设置 M3；未发现需要补写 M3 的生产 caller。`run_g4irsf24_dlp_campaign.py` 中只含一个不带 rule 的 summary-echo 字典，它不是 runtime request。

正式外部实验正在使用的冻结二进制未被重建或覆盖：

```text
build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd
SHA-256: b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5
```

## 验证

隔离构建目录：`build/j2_m3_interface_cpp`（未触碰冻结实验二进制）。

```text
ctest --test-dir build/j2_m3_interface_cpp -C Release \
  -R '^(event_driven_junction|destination_merge_grant_real_map|g4irsf18_jit_destination_merge|g4irsf24_dlp)$' \
  --output-on-failure

  event_driven_junction                 PASS
  destination_merge_grant_real_map     PASS
  g4irsf18_jit_destination_merge       PASS
  g4irsf24_dlp                          PASS

python -m pytest -q \
  tests/test_g4irsf31_map_adapter.py \
  tests/test_g4irsf18_native_merge_policy.py \
  tests/test_g4irsf19_route_campaign.py

  34 passed

git diff --check (three reviewed C++ files): PASS
```

`destination_merge_grant_real_map` 同时回归了 deadline/wait-age/starvation 比较、stale/recheck、grant expiry、retry/capability 与不可执行状态的 fail-closed 协议。新增 J2/M1 对 J2/M3 微型用例足以证明“固定一次 J2 机会时，只换 priority rule 可改变赢家”这一接口性质。

## 边界

本审查没有运行 map2 2× 或南宁 2× paired 性能实验，也不把接口隔离解释成算法收益。附件第 17 节要求的完整八类逐臂测试与双图性能对照仍属于后续完整因果实验；本提交只满足其 Gate F 所允许的接口设计、微型可识别性测试和 G31 默认行为回归证明。
