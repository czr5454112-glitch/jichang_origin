# 同五输入 native015 修复重放

五场均直接读取 `original_protocol_24_forecast_diagnosis_011_002/raw.json.gz` 的原输入和原请求，未改变装载时长、图、节点服务、通信延迟或接收合同。新 binary SHA256 为 `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`。

| Load / service（秒） | 原请求结果 | 实际首次入边 | 011 预测入边 | 015 预测入边 |
|---|---|---:|---:|---:|
| 0 / 0.001 | tray_not_visible_to_owner | 0.001 | 无 | 无 |
| 0 / 1.5 | no_local_uncommitted_loaded_service | 1.5 | 无 | 无 |
| 0 / 2 | delivered | 2 | 4 | 2 |
| 0 / 3 | delivered | 3 | 5 | 3 |
| 3 / 0.001 | delivered | 3.001 | 3.001 | 3.001 |

所有五场首次入边时间、接受/拒绝状态保持原样；三场成功预测均严格等于实际首次入边时间；全部物理账审计通过。运行退出码 0，`source_changed=[]`，完整 before/after、原始新事件和哈希在 `receipt.json` 与 `raw.json.gz`。

2 秒同刻案例仍于 2.5 秒才在接收端送达，晚于真实入边。正确预测不等于足够提前，也不等于业务收益。这只是指定合成边界的正确性回归，不能替代原图五策略对照或正常分拣保护证明。014 目录仅保留未执行的准备脚本；旧 011 失败证据未覆盖。
