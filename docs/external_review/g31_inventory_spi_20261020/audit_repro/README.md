# G31固定提交独立复算包

固定提交：`1d895da00644c9486568fe74b835e057aa93f8c8`。

仓库：[czr5454112-glitch/jichang_origin](https://github.com/czr5454112-glitch/jichang_origin/commit/1d895da00644c9486568fe74b835e057aa93f8c8)。本包对应2026-10-20独立审阅。它包含复算代码、执行后的JSON诊断和两份下一阶段任务书；**不包含完整仓库、原生二进制或第三方论文全文**。

## 1. 已实际执行的范围

- `results_recompute.py`：重算34支保存结果、完整28,506人口和20组成对比较，补充精确/删失延误方向及解释指标。
- `results_workload_bound.py`：从固定输入的图与业务构造非常乐观的纯载货工时必要下界；不是推荐配盘数。
- `physical_recompute.py`：重算N26/P902三个分支的实体终态、等待与最后进展；这是保存事件重算，不是新native复现。
- `learning_selection_audit.py`：重算12条开发选模链，将reference纳入同一排序作诊断；没有重新训练。
- `learning_identifiability_audit.py`：校验固定特征源码、重建成对差分特征，计算秩、行空间/零空间和首个N26/P902学习动作的敏感性；需要NumPy，没有fit/native。
- 发布方 `audit_bundle.py` 另行实际运行成功。`publication_audit_summary.json` 保留范围、计数、manifest及原完整审计结果SHA；原结果的66,019项excluded清单不是已验证字节。没有声称全callback流审计。

本次环境是Linux CPython 3.12.14。没有在此环境构建或运行Windows `.pyd`，没有训练模型。具体native失唤醒反例与R0均是下一阶段任务，不是本包已完成成果。

## 2. 复算方式

准备包含固定提交代码及 `outputs/experiments/g31_ics_action_value_20261020/cycle_001/` 证据的完整检出/导出。必须固定到上述完整SHA，不使用漂移分支。

每个命令的 `--root` 是固定仓库根目录，不是本审计包根目录。`--output` 指向新诊断文件，避免覆盖研究原件。

```text
python scripts/results_recompute.py --root /path/to/fixed_checkout --output fresh_results.json
python scripts/results_workload_bound.py --root /path/to/fixed_checkout --output fresh_workload_bound.json
python scripts/physical_recompute.py --root /path/to/fixed_checkout --output fresh_physical.json
python scripts/learning_selection_audit.py --root /path/to/fixed_checkout --output fresh_selection.json
python scripts/learning_identifiability_audit.py --root /path/to/fixed_checkout --output fresh_identifiability.json
```

前3个结果/物理脚本仅用Python标准库。学习识别性脚本需要NumPy；学习脚本会按固定来源hash校验并导入项目的特征/前向函数，不调用拟合或native。NumPy版本/数值库不同可能使SVD尾部浮点数有微小差异，应比较数值容差与科学结论，不要求跨平台JSON逐字节相同。

这些命令在缺文件或来源不一致时应报错，不能通过改SHA或替换当前模型绕过。Windows可使用相应的带引号仓库路径。

## 3. 发布审计与路径重定位

原发布清单使用 `code/...`、`source_blobs/...` 等bundle布局。本次建立只读硬链接审计视图，把固定提交的仓库文件映射为其声明的bundle路径。

- `provenance/portable_audit_path_mapping.json`：2558项明确路径映射；不是重新生成科学数据。
- `provenance/source_and_publication_acquisition.json`：2756项源码/发布来源核验，失败0；不是“完整仓库所有历史日志都已下载”。
- 三个历史B1输入按当前manifest期望SHA核对后复用旧固定导出，映射文件逐项保留实际来源。
- `results/publication_audit_summary.json`：发布方审计器的成功状态、输入审计器hash、原完整审计输出hash及范围声明。未重新执行native或fit。

不要把本复算包当成完整发布包，或直接对它运行原发布清单验证器。原发布方完整bundle另由仓库提供；本包只保存本次独立诊断所需代码和结果。

## 4. 文件结构

- `docs/`：审阅与Codex任务书、R0独立规格。
- `scripts/`：5个独立复算脚本。
- `results/`：5份已执行诊断JSON与发布审计摘要。
- `notes/`：学习、物理、结果及库存协议四份分项审阅记录。
- `provenance/`：固定来源取得记录与明确路径映射。
- `CONTENTS_SHA256.json`：本包每个文件的SHA256；校验本包完整性，不代表重新运行论文实验。

## 5. 最重要的口径

真实学习动作已有；稳定的预测净收益、机场多步RL与减盘尚未成立。共同失唤醒有强源码/轨迹依据，仍须定向native复现。最小范数投影是识别性诊断，不是已经验证更好的策略。R0是新增低信息对照，不代替原同信息强规则。所有失败、单边完成、未完成和未到达业务须保留正确分母。
