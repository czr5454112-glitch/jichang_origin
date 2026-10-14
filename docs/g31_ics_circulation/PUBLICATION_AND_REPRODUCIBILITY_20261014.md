# G31 × ICS：2026-10-14 发布与复现说明

用户本次明确授权整理并推送。代码固定提交为 **89c2935ef2963d769ab6ca75764009b2b3e9365f**，成熟基线仍为46cc46ab6bc121628fd6357e9f3c7636745fd732。包含本文和GPT Pro任务书的随后提交是发布材料，不表示原生实现再次变更。推送以原始push回执及远端ref核对为准，不使用force push。

- 仓库：[jichang_origin](https://github.com/czr5454112-glitch/jichang_origin)
- 专用分支：[codex/g31-ics-v3-circulation](https://github.com/czr5454112-glitch/jichang_origin/tree/codex/g31-ics-v3-circulation)
- 代码固定树：[89c2935](https://github.com/czr5454112-glitch/jichang_origin/tree/89c2935ef2963d769ab6ca75764009b2b3e9365f)
- 交给GPT Pro的主任务：[审核与下一阶段修订](GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md)
- 发布原文件清单：[source_manifest.json](publication_20261014/source_manifest.json)
- 发布材料覆盖清单：[release_manifest.json](publication_20261014/release_manifest.json)；核对最终树时先用source_manifest，再按该清单更新文档/回执项。它不修改固定代码身份。
- 作者原生工件清单：[author_artifacts_manifest.json](publication_20261014/author_artifacts_manifest.json)

## 发布范围与字节身份

固定代码提交包含当前circulation实现、选择导入的V3参考命名空间、测试、两份原始拓扑xlsx、长期总纲/外审材料、原始失败与成功证据。清单列出5831份源文件/证据约418.7 MB，清单自身另外提供；成熟仓库其余文件由既有Git历史继承。大量文件是历史导入、旧记录和重复版本证据，不计新增方法工作量。

已包含 `outputs/experiments/` 下本地声明范围的原始JSON、gzip、回执、测试日志和压缩fixture；旧V3六份原始cursor JSON也随此提交提供，不需要依赖作者电脑上的缺失outputs路径。构建树、编译对象、pytest临时目录、缓存、虚拟环境、其他工作区及本地传输调试日志不进入发布。manifest明确列出额外排除项。清单不自包含自身哈希，也不包含后来才可写入代码SHA的本交接MD，避免循环身份声明。

Git属性保留本地原始字节，使回执中的源码SHA可逐项核对。44个成熟C++依赖仅将Git中的LF表示保留为作者构建时CRLF字节，语义未改，完整路径在manifest的 `eol_only_mature_cpp_dependencies`。审查实质代码差异可使用：

```text
git diff --ignore-space-at-eol 46cc46ab6bc121628fd6357e9f3c7636745fd732 89c2935ef2963d769ab6ca75764009b2b3e9365f -- cpp CMakeLists.txt
```

发布暂存区5832份文件已逐一验证Git blob与磁盘字节、清单SHA一致。代码空白检查显式把CRLF识别为换行，未用重新格式化破坏冻结哈希。原父工作区受保护的bounded_local_pibt.hpp仍为b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951；未合并或覆盖父分支。

## 本次重新验证的范围

本次未更改016原生实现或业务求解。发布审查修复四处测试的环境变量默认值被急切求值，以及一处原图测试硬编码仓外目录；所有assert AST保持不变。两份xlsx逐字节复制到仓内 `map_nanning/`，成熟adapter本来就优先该路径。

`outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001/live_001/` 为修复后的真实407通过回执，0失败/错误/跳过，source_changed=[]。407分为401项当前native/Python关联检查、1项冻结011历史反例、5项011/015身份专项；不能称407项当前物理实验，也不是本次重新跑完V3历史1580项或整仓全部测试。

本次另从固定Git提交直接归档生成全新checkout，使用归档内fixture及下述明确版本工件复跑。其实际结果、命令、源哈希和JUnit在 `outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001/fresh_checkout_validation/`。这使用作者现有Python/依赖和已编译Windows工件，属于干净源码复跑，**不是独立工具链重编译、第三方执行或Linux兼容性证明**。实际最终407通过，0失败/错误/跳过，compiled_source_mismatch=[]、source_changed=[]，运行43.79秒；前后5831个manifest文件和5个作者工件均重新核验。首次标准解包遇到279字符Windows路径而失败，原traceback保留；同一tar使用Windows扩展长度路径解包后完成复跑。完整证据以该目录final receipt为准，未用测试删减或父目录fallback取得通过。

历史回执中的绝对Windows路径、uncommitted或pushed=false是当时执行元数据，保留原件；不能因本次发布而回写旧结果。当前代码及发布提交身份以本文、任务MD及最新远端核对为准。

## Windows完整407复跑

需要CPython3.11、Windows x64和可用VC运行库。使用现有作者二进制时不需要重新编译，但应验证身份。仓内2.36 MB ZIP包含011、015、016三个pyd，以及成熟G31固定fixture exe及其原始身份回执；这些是作者构建，不冒称源码可移植性。

在仓库根运行：

```powershell
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python docs/g31_ics_circulation/publication_20261014/verify_published_files.py
python docs/g31_ics_circulation/publication_20261014/restore_author_artifacts.py
python -m scripts.experiments.g31_ics_circulation.validate_live --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json --output outputs/experiments/g31_ics_long_term_20261013/reviewer_live_new
```

恢复脚本先核ZIP和每个工件SHA、路径范围，拒绝覆盖不同的已有文件。它不安装系统软件，不执行二进制，仅恢复验证需要的明确文件。不要把011/015换成016或跳过历史检查后仍称完整407通过。每个新实验使用未存在的独占输出目录。

依赖以 `pyproject.toml`、测试导入及作者构建/执行回执为准，至少检查pytest、numpy、pybind11、cmake；读取xlsx采用既有解析器，不能从缺包推断代码已失败。没有本机Windows环境时可先只读核回执和原始事件，明确区别证据级别。

## 其他平台、重新构建与历史行为

`.pyd` 不能直接用于Linux/macOS。当前源码的构建入口是 `scripts/experiments/g31_ics_circulation/build_native.py`，以 `--help` 查询编译器参数，使用新的build及receipt目录。重新编译应记录新产物的实际SHA，不能期待与作者MSVC产物逐字节相同。

完整407还明确绑定旧011历史行为和011/015扩展模块缓存行为；跨平台只构建当前源码不能自动取得这两个历史二进制。可以将当前测试与历史测试分别执行、精确报告选择/排除数量，但不得放宽原断言、伪造历史构建或把部分回归写成407。P5冻结重查的Python源码守卫也须尊重，不能用当前native_host替换旧归档后仍称版本相同。

成熟legacy直接对照入口 `validate_legacy_parity.py` 需要MSVC环境和附件恢复的pinned.exe/原始final_receipt.json。本次代码源和旧 `legacy_parity_005` 的编译输入一致，旧两场哈希结果仍限定于原验证范围；没有声称本轮重跑全部成熟G31规模实验。

## 文件取得失败与完整ZIP备用

GitHub逐文件读取可直接固定89c2935。若审核容器无法下载GitHub archive，请保存真实命令、退出码、stderr和字节数；这与作者本机推送网络问题是不同事件，不得相互补证。

本次给用户另外生成 `G31_ICS_full_repository_20261014.zip`，由最终发布提交直接 `git archive` 生成，包含该Git树全部文件和本次发布的原件/工件ZIP；它是完整**已提交仓库树**，不同于历史增量diff包。不含.git历史、忽略的完整构建目录、用户父工作区修改或未提供的外部图纸。ZIP SHA、提交与实际大小由旁边独立archive receipt给出，用户可直接上传到GPT Pro避开其容器DNS/下载限制。Windows解压建议使用短目录（例如C:/g31-review），或支持扩展长度路径的工具，避免本次已经真实复现的深路径失败。

原需求DOCX完整图纸、现场零容量真实物理语义、未发布的全业务checkpoint、旧约230 MB证书状态等，不因“完整已提交仓库树”而自动补齐。本文不声称它们全都存在；审阅者应根据manifest和实际取得文件列出缺失项。原始任务母流、两份本次用于校验的拓扑xlsx与本轮raw实验结果已包括在明确发布范围内。

## 本次审核仍应面对的未完成项

两项业务要求、正常保护、区内权限、完整100ms与TRE/CIE目标均保持。原图24件仍19迟到且未启用R1授权；联合零增量；204条预测晚于真实入边送达；当前强服务指派解释P5有限域全部收益；完整原流物理代理有阻塞；P6学习尚未放行；P7仍有超100ms并缺完整请求/两机确认。任务MD要求GPT Pro依据实际代码给出具体修复和下一轮路线修订，而非认可作者总结或重抄长期总纲。
