# G4IRSF14 故障回归（Stage K）

- 状态：`NOT_RUN_NO_ELIGIBLE_NEW_CANDIDATE`。
- G4IRSF13 的 DDI/BTI local control 仅作为冻结参考；本轮没有把其历史结果重命名为 G4IRSF14 新候选回归。
- 因 J 阶段没有合格闭环候选，计划中的 G0/G1/G2/G3、G5 delayed、G6 dropped、G7 repair、informative multi-fault、grant issue→fault、prepare/commit→fault 与 same-timestamp fault 均未运行。
- unsafe entry=0、fault generation monotone、stale grant reject、repair re-entry once、credit/grant cleanup 与 P2 transaction atomic 六项保持门均为 `NOT_EVALUATED`。
- 下一步必须在同一候选、同一暴露窗口和 generation 上比较 shield on/off，验证 unsafe=0、complete、安全回退和主动收益。

生成绑定：`a8db7027c44c66614ac3f7b04f414b10ce7863f066eebcc901177d9cc1ff363a`。
