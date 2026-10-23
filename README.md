# 冯汝琛原始 Java 项目：代码审阅版

本分支供 GPT Pro 检查原始 ICSsimulation Java 实现。`src/` 中的 15 个 Java 文件直接复制自原工程，保留原始字节、注释和换行，没有修改算法。整理日期：2026-10-23。

## 审阅范围与来源

- 原件来源：冯汝琛相关材料 / ICS项目 / 代码-ICSsimulation / src。
- 15 个文件与当前项目的冻结镜像 `legacy/jichang_origin_readonly/src` 逐字节一致。
- 与本仓库原始提交 [`c5c2d2cb050f62b5160cdfb6c29895f03af12486`](https://github.com/czr5454112-glitch/jichang_origin/tree/c5c2d2cb050f62b5160cdfb6c29895f03af12486/src) 的全部 15 个源码逐一比较，统一 CRLF/LF 后内容完全一致。
- 该分支当前目录只包含 Java 源码、本说明、审阅提示词和 SHA-256 清单。原始提交保留在历史中。
- 地图、任务数据、GUI 图片、第三方 JAR 和 Eclipse 元数据可在上述原始提交中查阅；此代码审阅快照不包含它们，因此不是独立可运行发行包。
- 后续 Python/C++ 方法、CIE-DH 复现、HCA 修复包装器和实验结果不属于本分支的审阅范围。

## 建议阅读顺序

| 文件 | 阅读重点 |
| --- | --- |
| [RUN/Main.java](src/RUN/Main.java) | GUI 仿真入口、任务读取、早到行李拆段、epoch 驱动 |
| [App/Tasks.java](src/App/Tasks.java) | 任务释放、故障与修复事件生成 |
| [App/ICS_PathFinding.java](src/App/ICS_PathFinding.java) | 路径调度、预约、路线推进、未完成重试、故障重规划 |
| [App/Astar.java](src/App/Astar.java) | 搜索状态、启发函数、时间约束和目标判定 |
| [App/Map.java](src/App/Map.java) | 地图解析、边速度与节点时间 |
| [App/Node.java](src/App/Node.java)、[Vertex.java](src/App/Vertex.java)、[Edge.java](src/App/Edge.java)、[Route.java](src/App/Route.java)、[task.java](src/App/task.java) | 状态模型与标识 |
| [ICS_GUI/ICS_GUI.java](src/ICS_GUI/ICS_GUI.java) | GUI 时间推进、共享状态、暂停与重载 |
| [RUN/test.java](src/RUN/test.java) 与 [communication/](src/communication) | 网络输入、JSON 解码、规划调用、结果发送、重连与资源释放 |

GUI 调用链：`RUN.Main.run → Map.read / ReadTaskList → Tasks.generate_tasks → ICS_PathFinding.ICS_path_finding → Astar.research`。

`RUN.test` 是网络联调入口，不能仅依据文件名把它当作单元测试。请从实际启用的调用路径判断算法行为，区分注释、未启用分支和运行代码。当前原工程可见全路径 A* 调度逻辑；是否满足某篇论文的全部定义，需要论文证据单独核实。

## 本次验证

2026-10-23 使用 JDK 18、`javac --release 8 -encoding UTF-8`，通过原工程自带 JAR 编译了全部 15 个 Java 文件，生成 29 个 class。编译仅提示 GUI 使用已弃用 API。未运行 GUI、网络联调或完整仿真实验；编译成功不表示算法正确。

在另行取得原工程依赖后，可在此快照目录中以 PowerShell 编译：

```powershell
$jarRoot = '原工程目录/Java_jar/Java_jar'
$cp = (Join-Path $jarRoot '*') + ';' + (Join-Path $jarRoot 'netty-4.0.56.Final/jar/all-in-one/netty-all-4.0.56.Final.jar')
$sources = @(Get-ChildItem src -Recurse -Filter '*.java' -File | ForEach-Object FullName)
New-Item -ItemType Directory -Force build/classes | Out-Null
javac --release 8 -encoding UTF-8 -cp $cp -d build/classes @sources
```

文件完整性见 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)。可直接将 [REVIEW_PROMPT.md](REVIEW_PROMPT.md) 的文字和本分支链接交给 GPT Pro。
