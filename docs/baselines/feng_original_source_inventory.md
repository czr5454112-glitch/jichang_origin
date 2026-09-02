# Feng 原始 Java 工程清单与可执行边界

## 结论

已找回并可构建的是 Feng 原始 **HCA** Java 调度器；没有在原工程或仓库冻结镜像中找回可执行的 native CIE-DH 实现。因此，原生 HCA 可进入 P0 回归和 P2 端到端系统对照，而 native CIE-DH 必须保持 `BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED`。当前 C++ 公共执行器中的 CIE-DH 适配只能属于 P1，不能改称 Feng-native。

## 源码与运行资产

| 资产 | 位置 | 已核实身份 | 用途 |
| --- | --- | --- | --- |
| 独立原工程 | `C:\PROGRAMING\czr004\jichang_origin` | Git 分支 `main`，提交 `c5c2d2cb050f62b5160cdfb6c29895f03af12486` | 追溯原始工程身份，不在本轮修改 |
| 仓库冻结镜像 | `legacy/jichang_origin_readonly` | 原始 Java、`map2.txt`、`inputdata.txt`、Eclipse 工程元数据 | 可复现实验输入与只读源码 |
| 无 GUI 观测包装器 | `benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java` | 直接调用原始 `App` 类；记录 release、route、completion | P0/P2 HCA 回归采集 |
| 回归运行器 | `scripts/eval/run_g4irsf24_fresh_hca.py` | 分进程运行、对齐 canonical raw-bag population | 汇总完整人口指标 |

本文件不登记未由构建/运行器生成的 SHA-256。后续产物身份应由正式运行器写入 manifest，而不是手工猜测。

## 原始调用链

GUI 原入口的主链为：

`RUN.Main.run` → `Map.read(map2.txt)` → `RUN.Main.ReadTaskList(inputdata.txt, ...)` → 每个整数 epoch 调用 `Tasks.generate_tasks(...)` → `ICS_PathFinding.ICS_path_finding(...)` → `Astar.research(...)` → `saved_routes` / `outputstarttime.txt` / `output.txt`。

无 GUI 包装器保留同一算法主链：它创建 `ICS_PathFinding`，读取同一 map/input，按 epoch 调用 `Tasks.generate_tasks` 和 `ICS_PathFinding.ICS_path_finding`，仅在调用前后记录释放、已规划路线与完成事件。包装器不是 CIE-DH 实现，也不得改变 `App.Astar`、`App.ICS_PathFinding` 或 `App.Tasks` 的路由语义。

## 搜索范围与缺失证据

对以下两个根目录的全部 `*.java`（每处 15 个文件）进行了文本扫描：

- `C:\PROGRAMING\czr004\jichang_origin\src`
- `legacy/jichang_origin_readonly/src`

搜索词覆盖 `CIE-DH`/`CIE_DH`、`decentralized`/`decentralised`、`moving`、`stopped`、`HOLD`、`BTI`、`DDI`，以及带 0.2 秒/200 ms 单位的离散步长表达。两处均为 0 个匹配。现有源码表现为整数 epoch 驱动、带时空约束的 A* 全路径规划与故障重规划；它没有足以实现论文所述 CIE-DH 的 0.2 秒位置级 moving/stopped 状态机、HOLD/BTI/DDI 分支或相应局部选择器。

“未找回”只针对上述工程与冻结镜像，不等价于证明该源码在世界上不存在；但在新的一手材料出现前，不能从 HCA 代码反向臆造 native CIE-DH。

## JDK 18 / Java 8 目标构建

在仓库工作树根目录执行以下 PowerShell 命令，可用 JDK 18 以 Java 8 目标构建原始 HCA 与无 GUI 包装器：

```powershell
$fengSources = @(Get-ChildItem 'legacy\jichang_origin_readonly\src\App\*.java' -File | ForEach-Object FullName)
$fengSources += (Resolve-Path 'legacy\jichang_origin_readonly\src\ICS_GUI\ICS_GUI.java').Path
$fengSources += (Resolve-Path 'benchmarks\java\LegacyIcsNoFaultWindowBenchmark.java').Path
New-Item -ItemType Directory -Force 'build\feng_native_hca_java' | Out-Null
& 'C:\PROGRAMING\jdk-18\bin\javac.exe' --release 8 -encoding UTF-8 -d 'build\feng_native_hca_java' @fengSources
```

正式 1× map2 HCA 回归应复用既有 runner，并跳过其内部再次编译，以确保实际使用上面的 `--release 8` 类文件：

```powershell
python scripts/eval/run_g4irsf24_fresh_hca.py run --profile full --repeats 1 --classes-dir build/feng_native_hca_java --output-root outputs/raw/cie_revision/feng_native_hca_map2_1x --java C:\PROGRAMING\jdk-18\bin\java.exe --skip-compile
```

## 完整回归结果

| 字段 | 值 |
| --- | --- |
| 运行状态 | `FENG_NATIVE_HCA_REGRESSION_PASS` |
| Java/JDK 身份 | OpenJDK 18，`javac --release 8` |
| 构建产物身份 | 27 个原工程 class，聚合 SHA-256 `005f2cca4ede5f9d08668830a1d02f2b33a6d5e789ab29a2ef09fdded18c2b1f` |
| canonical segment population | 43,603 |
| canonical raw-bag population | 28,506 |
| released / completed / deadline-success | 43,603 / 43,603 segments；deadline-success `NOT_MEASURED` |
| 全人口 mean / P95 / P99 / max | processed-attempt 236.710166 / 299 / 330 / 357 s |
| wall time / planner throughput | 243.787743 s / 178.86 completed segments·s⁻¹ |
| comparison-eligibility gate | `PASS`；100% raw-bag 与 segment 完成，无 survivor timing |

只有在 canonical 全人口、释放口径和执行完整性门槛都通过后，这一行才能作为 P0/P2 正式 HCA 证据；不完整人口的 survivor timing 必须为 `N/A`。
