# G4IRSF14 PIBT blocker taxonomy（Stage G）

- 状态：`TAXONOMY_MEASUREMENT_NOT_RUN_ZERO_APPLICABLE_SUPPORT`。
- 原始 1x 被动计数：prefilter candidate = 1,337；真正 applicable ready-slice boundary = 0；G4IRSF14 attempt = 0。
- 17 个 canonical primary reasons 已固化为完整枚举，但本轮没有可适用边界，所以每项 count=0、denominator=0，rate 留空。
- 这不是“17 类故障均未发生”的证据，也不是 runtime taxonomy complete；只是零支持下的 fail-closed 量测结果。
- raw commit/attempt、feasible commit/feasible attempt、resolved/applicable、system benefit/committed 四套计划口径均已保留；因 attempt=0、applicable=0 且未执行，rate 留空并标记 `NOT_MEASURED`，绝不把零分母写成 0% 或 100%。

PIBT 仅负责 blocker 可局部移动且需要多袋一步原子动作的异常协调；普通跨上游 merge request 仍由 destination merge arbiter处理。

生成绑定：`a8db7027c44c66614ac3f7b04f414b10ce7863f066eebcc901177d9cc1ff363a`。
