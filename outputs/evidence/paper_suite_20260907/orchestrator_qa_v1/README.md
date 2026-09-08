# 调度器合成验收

18 项通过。这里只测试冻结身份、筛选、互斥池、失败停止追加、拒绝覆盖、调用复核接口、未完成人口的有效终态，以及真实但无害的 Python sleeper 超时。没有运行交通/行李仿真，没有修改正式结果。

本机 `taskkill /T` 对新建 Python sleeper 返回“拒绝访问”。调度器因此准确记录 `TIMEOUT_TERMINATION_FAILED`，不声称已终止进程树，并保留整池锁，要求检查所记 PID 和单格锁后手动恢复。默认 `--timeout-seconds 0` 不启用超时终止。QA 的 sleeper 两秒后自行退出；旧错误地等待并声称终止的探针保留在本地 build 目录，没有冒称通过。

`archive_manifest.json` 绑定正式调度器 SHA 及此处源码/结果/实际超时输出。复跑时将 `check_orchestrator.py` 的原始字节复制到仓库 `build/paper_suite_orchestrator_qa/check_orchestrator.py`，用 Python 3.11 执行。脚本每次生成独立 UUID 目录，不覆盖先前产物；它仅启动无害 Python sleeper。其余运行器调用由合成 fixture 替身隔离。

正式入口：`python scripts/eval/run_feng_paper_suite.py run --plan <最终冻结计划> --workers 4`。`--family`、`--method`、`--map`、`--load`、`--seed`、`--speed`、`--scenario`、`--cell-id` 可重复筛选；`status` 仅查看状态，不是新科学复核；`verify` 调用对应单格审计。已完成格须验证后复用，已有未完成尝试拒绝覆盖。一次池的状态与 stdout/stderr 存于 campaign 的 `orchestration/<run_id>/`。
