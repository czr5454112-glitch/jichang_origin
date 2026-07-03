# G4IRSF3 Plain Language Summary

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

这轮做了三件事：

1. 把 8x 高流量任务文件按 manifest 做了 hash 复核，确认大文件可以用脚本再生成，不需要放进 Git。
2. 把全量 `348824` 个任务拆块覆盖到 `348824` 个任务；这些块里 no-A* 规划 `348098/348824`，节点时间窗冲突 `0`，运行时完整 A* 调用为 0。
3. 对 18->22 故障做了前避让审计：不是到了 18 再神奇选路，而是要在 16、19 或更早位置发现前面是断路。

最好的 fault-aware shadow 变体从旧失败里恢复 `0` 个，但它还只是 shadow，没有真正接入当前 C++ runtime。

原始 Java/CIE 完整 baseline 可运行状态：`False`。所以现在仍不能宣布最终替代 A*。

结论：G4IRSF3 是扎实推进，不是 paper-grade 终点。下一步应该优先做跨块状态接续和把 fault-aware 前避让真实接入 runtime。
