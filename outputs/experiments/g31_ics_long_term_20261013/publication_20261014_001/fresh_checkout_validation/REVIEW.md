# 提交 A 的干净归档复核（2026-10-14）

复核提交：`89c2935ef2963d769ab6ca75764009b2b3e9365f`。

实际使用 `git archive --format=tar` 从该提交导出源代码，没有从工作区复制源码。原始 tar 大小为 1,090,867,200 字节，SHA256 为 `53033ce9a21e642747e2376a3814c869aef63d7a2655643a0a9df94628d84135`。归档包含 8,631 个普通文件。

**验收通过：407 项测试，0 失败、0 错误、0 跳过。** 范围是 401 项当前 native/Python 测试、1 项明确使用 frozen011 的历史反例、5 项明确使用 011/015 的原生模块身份检查。不得把全部 407 项都描述成当前物理模型的验证。

`validate_live` 子进程实际运行 43.79 秒；`compiled_source_mismatch=[]`、`source_changed=[]`。运行前后分别核验源码清单的 5,831 个文件，SHA256 和长度均匹配。发布脚本恢复的 5 个作者工件（native011、015、016、legacy exe 和其回执）均匹配声明 SHA256；没有克隆、下载外部工件或使用旧 build fallback。干净根只存在明确恢复的 `build_lt_session_011`、`build_lt_session_015`、`build_lt_session_016` 和 `build_g31_parity`。

这是**同一作者 Windows 工具链和作者预编译工件上的干净源码归档回归**，不属于独立编译、第三方外部审核、全套物理实验重跑或完整 100ms 认证。原始图/任务输入从归档内的默认路径读取；没有把父工作区文件复制过来。

## 首次失败及处理

首次解包失败被保留在 `execution_receipt.json`。随后逐成员复现得到真实 traceback，保存在 `extraction_diagnosis.json`：目标路径长 279 字符，`tarfile.makefile` 打开该路径时抛出 `FileNotFoundError`。这不是仓库缺文件。

在同一个独占解包根上使用 Windows `\\?\` 扩展长度路径后成功。已存在的 970 个文件逐字节与原始 tar 验证，其余 7,661 个文件从同一 tar 恢复；没有从工作区补文件，也没有修改测试。完整成功结果见 `long_path_execution_receipt.json`。外部审核建议将归档解压到短路径，例如 `C:\g31`，或用支持扩展长度路径的工具；不可因路径限制删除仓库文件。

## 可运行命令

先在新的短路径目录解出指定提交的 Git 归档，再在该目录运行（Windows、Python 3.11 x64）：

```powershell
python docs/g31_ics_circulation/publication_20261014/restore_author_artifacts.py
$env:PYTHONPATH='src;.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m scripts.experiments.g31_ics_circulation.validate_live --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --build-receipt outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json --output fresh_check_live
```

输出目录必须尚不存在。Linux 环境不能直接执行这些 Windows `.pyd`；本复核没有验证 Linux 构建。

`fresh_check_live/receipt.json` 和 `fresh_check_live/junit.xml` 是这次新执行的结果，不是原工作区历史回执。`postcheck.json` 保存复跑后清单/工件核验和关键文件 SHA256。保留的执行脚本、stdout/stderr、首次失败和处理后的成功证据共同说明全过程。

`fresh_checkout_validation_evidence.zip` 只收集本次小型验收证据，**不是完整代码库压缩包**；不含 1.09GB 原始 tar、干净检出或 pytest 临时目录。
