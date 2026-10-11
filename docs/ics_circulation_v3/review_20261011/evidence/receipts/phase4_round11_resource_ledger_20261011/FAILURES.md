# Round11 账本故障与修复

final_001 的扫描器将 `phase4_round11_storage_terminal_screen_20261011/comparison_001/old_result.json` 当成独立运行，重复增加了 1.265625 CPU 秒和 4 个 query 入口调用。它是诊断目录 `phase4_round11_projection_query_diagnosis_20261011/diagnosis_002/result.json` 的完整复本；两者 SHA 均为 `a580a2960be070f1da2b286fba9e812a1105bf3f4b33c040ed41b3262819df50`，comparison_001/result.json 的 baseline_result_sha256 也绑定此值。

final_001 原件不覆盖，标为重复计费故障，不能再引用其上游总额或查询总数。其自身实际账本构建 CPU 0.390625 秒仍须计入后续总账。原 49 个明确物理运行计数不受影响。

根代理同意修复后新建 final_002，且唯一引用该修正版。去重器仅排除上述由原路径、完整对象、字节 SHA 与 comparison 绑定共同证明的单一别名，不将相同 SHA 的任意独立调用泛化为重复。source/result 原件没有修改，没有重跑测试、物理或 candidate query。修账前后阅读、编辑及最终封包辅助时间继续未知。
