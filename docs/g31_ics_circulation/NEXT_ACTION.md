# 当前执行入口 — 20261017 Foundation / Learning

用户已批准新任务书，原生闭环与L0并行、具备L1后立即多步学习。本轮以 `LEARNING_READINESS.md` 接续；`RESEARCH_STATE.json` 保留上一轮历史，不再用旧“先T5、暂不训练”阻止L0。完整100ms、原流、R1/R2和严格逐件保护目标不变。

1. 统一入口：`python -m scripts.experiments.g31_ics_circulation.run_learning_pipeline --help`；配置 `configs/g31_ics_circulation/learning_pilot_v1.json`；结果集中 `outputs/experiments/g31_ics_foundation_learning_20261017/`。输出不覆盖，失败和未执行保留。
2. `native_001`真实基线闭合：同L盘三次装卸、两次跨区返空再装载，原生回执与004同基线精确一致。后续仍是retained-policy，不等于有新R1/R2自由动作；L1/RL尚未准入。
3. `l0_002`已有192候选行／3场景、线性与小MLP真实训练和留组重放。只是smoke，不当泛化；原始top1存在条件保护失败。按需提供器已能先评分再只推演K，full32保留teacher；不把少查询冒充少推演，不把建议当执行权限。
4. 下一件代码：当前later-decision→不可变LaterSeedSpecification及当前未发二元动作门，随后同语义重建与真实新pair执行。保留None的native_default、已发前缀、逐件承诺和合法接收；此真实缺口关闭后立即启动有限范围多步RL，不等待全天或100ms认证。
5. 保留04参考、12/25→09损伤反例、正常带21格及全部历史失败；不再无目的重跑保存96、21格、旧600s验证器或H86400。有限兼容域A=04不等于完整R1/R2，T2故障带与真正后缀修复仍未完成。
6. 有限载盘EBS研究合同保留，type7不是已证现场EBS；0容量不擅自改1，零缓冲连接未启用。原始28506／增流分母、100ms及严格保护不变。2026-10-17用户另行授权将本阶段推送既有GitHub研究分支并整理GPTPro审阅包；不扩展到其它外发或合并main。

本轮实际结果与运行命令见 `LEARNING_READINESS.md`；历史依据仍见 `REVIEW_FOLLOWUP_20261017.md`、`PHYSICAL_CONTRACT_DECISION.md`、`REPAIR_METHOD_BOUNDARY_20261017.md`。后两者的旧研发排序被新任务书覆盖，物理／信息／执行保护约束不变。
