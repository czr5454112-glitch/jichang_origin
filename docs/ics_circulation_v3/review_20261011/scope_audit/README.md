# ICS 发布范围与可复现性独立检查

本检查不修改 ICS 生产代码、既有测试或实验原件，不运行新的物理窗口，不执行 Git 写操作或推送。读取基点为 `a23cf1c066d1087571b31733f0577c602040aa8d`，分支为 `codex/ics-v3-phase4`。最终提交身份由发布者的最终清单给出，本文件不把工作区预测 blob 冒充已推送 blob。

## 冻源与发布范围

Round11 `phase4_round11_independent_review_20261011/closure_001/results.json` 的 212 文件逐一与当前原始字节比对，全部一致：122 个生产 Python 文件、89 个测试文件、1 个受保护 C++ 文件。最终 1519 测试的原有回执为该独审目录的 `attempt_006/results.json`；这里没有重复运行这批测试。

- `source_release_paths.txt` 精确列出应随这次 ICS 发布的 211 个 Python 源码与测试文件。
- `pytest_paths.txt` 精确列出同一批 89 个测试文件，用于发布包隔离回归。
- `recommended_repository_paths.txt` 列出上述文件、现有 ICS 文档、地图 fixture、环境配置和本次完整压缩 fixture，共 240 路径；它不是最终 stage 清单。发布者还必须加入整个 `docs/ics_circulation_v3/review_20261011/` 审核包及其最终交接文档，并按实际 Git 状态检查增删。
- `results.json` 逐文件保存冻结原 SHA256、工作区原 SHA256、LF 规范化 SHA256、预测 Git blob OID 与内容 SHA256。本次预测均为原字节；提交后还必须核对实际 commit blob。

仓库 `core.autocrlf=true`。已有 `.gitattributes` 对 ICS 生产目录、`test_ics_circulation_v3_*.py`、ICS outputs 与 docs 使用 `-text`。新增独审命名 `test_ics_v3_*.py` 原先缺少相同规则，发布者已获提醒补上。不能仅比较 Windows 文件内容就推断所有平台 checkout 的字节相同。

## C++ 例外必须披露

`cpp/ics_core/runtime/bounded_local_pibt.hpp` 是前轮一直保留的工作区修改：252 行新增、15 行删除，涉及 G4IRSF14 的 blocker 原因、grant 状态、局部事务失败归因等。此次 ICS Python 代码与测试没有导入或编译它。按照本次发布范围，**不 stage、不回退、不覆盖**该文件。

- 冻结／工作区原 SHA256：`b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。
- 基点 Git blob OID：`523268cb45f2d07d0a6d6df1cb10432767a825e0`。
- 基点 Git blob 内容 SHA256：`9d985f46a4e46148060dc2a8eee9cff1bde5c3ee28e6903f24e6644ab7c2b600`。

因此，“212 冻源核验通过”包含 1 个保留的工作区对象；不能写成“212 文件全部推送”或“当前提交包含已冻结的新 C++ 实现”。可发布并与本轮 Python 回归直接对应的是 211 文件。Python 回归不构成供应商 C++ 集成验证。

## 必需 fixture：完整保存，先准备再测试

发现 `tests/test_ics_circulation_v3_cursor_original_map.py` 的 3 个场景直接读取未跟踪的历史 outputs 文件。若只推源代码，它们在新 checkout 会失败。这 6 个 JSON 共 **133,186,733 字节**，现以完整 gzip 无损保存为 **4,776,309 字节**。没有抽样、删字段或减少测试。

`../fixtures/manifest.json` 绑定每份原相对路径、原 SHA256/长度、gzip SHA256/长度。gzip 使用零时间戳、空原文件名和 level 9。打包时逐字节解压回比原件全部通过。

新 checkout／Git archive 必须先执行：

```powershell
python docs/ics_circulation_v3/review_20261011/tools/prepare_fixtures.py
$icsReleaseTests = Get-Content docs/ics_circulation_v3/review_20261011/scope_audit/pytest_paths.txt
python -m pytest @icsReleaseTests
```

以上从仓库根执行，使用 Python 3.11+、`numpy`、`pytest`。`psutil` 只服务可选进程内存测量，缺失会显式记为空而不影响测试逻辑；它不是 Python suite 的强依赖。不要用整个项目 `pytest` 的其他 G4/C++ 测试代替此 89 文件清单。

准备工具完整验证压缩件和解压内容，仅允许 6 个固定仓库相对路径，拒绝越界与文件符号链接。已有目标仅核验，不覆盖；异物直接报错保留。新目标经同目录临时文件和不覆盖的硬链接原子发布，因此需要支持同文件系统硬链接的文件系统。工作区全部 6 原件的 `existing_verified` 路径已实际执行；独立 `bootstrap_probe.json` 还记录首次创建、重复验证、异物保留、压缩件损坏、4 类越界路径、manifest 路径篡改和失败临时文件清理检查。这个 I/O probe 使用小型合成字节，仅验证工具；不替代 133 MB 的真实 fixture。

## 依赖与证据边界

对 211 文件进行 AST 静态导入闭包检查，未发现缺失的本地模块。测试间导入的作者 fixture 模块均包含在 89 文件内。地图位于已跟踪的 `scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json`。窄路径检查未发现 suite 依赖本机 `C:/`、用户 Downloads/AppData 或隐藏 worktree。唯一直接读未跟踪 outputs 的测试就是上述 6 文件，已完整打包。

这不代表任意历史实验入口在新 checkout 可直接重放。若干 runner 的默认 `prior`、`baseline`、`OLD` 读取早先 outputs，`results.json` 的 `static_special_path_strings` 列出实际代码位置。例如 `run_network_full_cycle.py`、`run_empty_factorial.py`、`run_feature_diagnostics.py`、`run_same_zone_query_coverage.py` 与 `run_same_zone_supply.py` 均需对应历史目录。完整业务输入适配器还要求外部源输入、声明与哈希契约；这类实跑依赖由实验 manifest 绑定，不能靠 1519 个 regression tests 宣称全部长窗口或完整业务数据已经重放。发布文档应区分“可独立复跑测试”“已交付可核验的原始证据”和“需要另行取回的完整实验原件”。

检查 `C:/`、`C:/PROGRAMING`、仓库根及源码/测试祖先与仓库内 `AGENTS.md` 的搜索未发现适用指令文件；没有额外仓库审批规则被用于阻止已授权发布。

## 发布者的最小必要验收

1. 检查 stage 文件清单，仅含本次 ICS 源测、文档、fixtures 与压缩证据；C++ 工作区修改仍保留但不 stage。
2. 从实际待发布 Git tree 导出独立目录，准备完整 fixture，再对 `pytest_paths.txt` 的 89 文件运行一次全回归，要求 1519 passed、0 skipped/failed/error；保存新目录身份、命令和原始结果。不得从原工作区偷偷借文件或复用本机 outputs。
3. 从最终 commit 逐一读取 211 个实际 blob，核对本清单原字节 SHA256，并记录确切 commit 与远端确认。若 EOL 不同，明确 LF 等价和原 SHA 差异，不能隐去。
4. 推送后交接文档引用确切提交。已有业务负结果、CPU 截断、实验依赖缺口和仍未实现的工作目标继续保留。

本子任务实测资源见 `results.json` 与 `bootstrap_probe.json`：打包/静态核验 CPU 11.46875 秒，工具 probe CPU 0.140625 秒，合计可计量进程 CPU 11.609375 秒；Git 子进程、首次失败启动、其他交互和已有原件准备检查未计量，不视为零。物理窗口数 0，1519 suite 复跑数 0。
