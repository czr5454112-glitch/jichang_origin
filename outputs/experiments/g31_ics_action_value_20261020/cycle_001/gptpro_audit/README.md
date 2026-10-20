# G31 固定提交独立复核包 — 2026-10-20

主文件：G31_REVIEW_13cf8eeb_AND_CODEX_NEXT_STAGE_20261020.md。

本包包含本次审阅使用的两个可移植标准库诊断及实际输出，不包含原始多GB仓库、训练依赖或Windows native。两个脚本已在完整固定提交上运行通过；没有启动native、重新拟合B1或训练学习策略。

## 重算

准备 https://github.com/czr5454112-glitch/jichang_origin 的完整固定提交 13cf8eeb9e9692eaf9eaf8b2ebbaeee8e1001626，包括 outputs 下的原始证据。在本包目录运行，替换 /absolute/path/to/fixed-checkout：

```text
python physical_circulation_diagnostic.py --root /absolute/path/to/fixed-checkout --output physical_recomputed.json
python learning_label_diagnostic.py --root /absolute/path/to/fixed-checkout --output learning_recomputed.json
```

Windows可使用带引号的本地绝对路径。输出路径单独指定，避免覆盖本包保存结果。无需改科学原件或历史Windows路径。

## 方法与范围

physical_circulation_diagnostic.py 独立读取原始C00终态/输入，统计完整人口、已到/未到、等盘及13只empty；独立实现正容量有向静态路径的服务与运输时间计算。它不证明FIFO、当前容量、lease或接收权限下立即可执行。

learning_label_diagnostic.py 独立以完整实际到达/完成记录重算81条300秒积压积分，并做同81行上的闭式一元描述回归。特征变化/缺失统计使用从固定 foundation_action_value.py 提取的纯函数，未导入整个项目，也不将其称为独立实现的第二套特征公式。时间回归是train-only可辨识性诊断，不是独立验证、控制策略或网络训练。全局积压仅用于离线解释，不是actor新增输入。

两个脚本都只读取固定仓库；其写入仅为指定诊断输出。脚本执行成功不替代重新构建C++、执行native、重新训练模型或1049项Python测试。

publication_verification_summary.json 保存本轮实际执行固定仓库发布核验的摘要，不声称是原核验器逐字节stdout。artifact_manifest.json 为本包文件字节哈希，不将哈希一致当作科学验收。
