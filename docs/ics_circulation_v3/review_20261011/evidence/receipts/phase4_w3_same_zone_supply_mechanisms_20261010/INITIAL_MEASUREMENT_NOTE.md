# 初次6格测量边界

`mechanism/analysis.json` 与同目录 `analyze.py` 是针对首个 `phase4_w3_same_zone_supply_20261010` 目录的只读结果，CPU20.25秒；292检查0失败，所有绑定文件前后不变。首批物理6次真实运行不能从资源账删去。

原summary将两个old32标为 `old32_replication_mismatch`，而raw物理结果已controller_quiescent。具体仅 `cache_before_exact=False`：内存tuple与旧JSON list的直接比较不同；final result、h80 result、search序列及stop均exact。独立审查确认raw JSON的cache逐字段相同，runner在新目录修复比较器后重跑。此初稿自动表使用raw physical status，**不能拿它掩盖summary测量失败标签**；本说明显式保留该边界。

后续主分析脚本默认读取新 `phase4_w3_same_zone_supply_repaired_20261010`，输出`repaired_mechanism`并与初次6个物理结果逐项核对；作者不会修改首批原件或删除其计算成本。method的dbb9ec25源码和guard标准未因结果改变。

初次物理结果提示的机制是t157追加及时同区供盘，既有t139远盘承诺仍执行。t127/t139唯一donor受其他已知需求保护而拒绝；不是提前避免远盘承诺。等待−48、空载距离+37，待修复批次核对后作为正式机制叙述。
