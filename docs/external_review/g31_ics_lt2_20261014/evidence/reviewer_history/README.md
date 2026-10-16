# 本轮审阅脚本的初版错误及修正

初版按 kind=service_forecast 选取所有消息，错误纳入 204 条撤销记录，得到 408 条与大量无法匹配的入边时间。它不是生产控制器缺陷，也不支持任何预测提前量结论。

修订版通过原始 request_ack_ledger 中成功 service_forecast 请求的 ACK result_id 选择确切发布记录，排除 withdrawn。重新执行得到 204 条原始成功公告，全部与实际 EDGE_ENTER 匹配，全部落后 0.5 秒。

本目录保留被替代的脚本与结果，仅作审计修正历史；唯一最终结果是上一级 independent_recomputation.json。初版其余业务、计时、P5 与接口探针输出不受此过滤问题影响，但最终仍全部重新复算。
