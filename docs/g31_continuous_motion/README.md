# G31 连续运动标准入口

2026-10-24 起，标准 CLI、Python `prepare_request` 和缺少执行模型字段的调用都默认使用 `continuous_headway_2s`。这是用户指定的物理模型：系统内部不额外停车，正服务设备通过占用 2 秒，有向边入口保持至少 2 秒间隔，恰好 2 秒允许；原零服务连接点保持零占用。所有时间按微秒整数网格处理。源端可以等待，EBS 出库必须等实际入库完成。

当前[默认参数](../../configs/eval/g31_continuous/default_controls.json)采用已验证的 006 核心：单跳评分、零拥堵权重、源端绕行预算 120 秒、按首次实际规划后的等待年龄以速率 1 放宽预算。其登记为 `physics_default=true`、`performance_promoted=false`，**不表示在两图、各负载及所有指标上胜过 HCA**。010 等后续候选尚未成为正式默认。完整研究结论另见[结果记录](RESULTS_20261024.md)。

新检出的仓库先安装依赖并在本机重建；需要 Python 3.11 或以上、CMake 和支持 C++17 的编译器。下面是已配置编译器的 Windows Developer PowerShell 示例，构建和执行使用同一个 Python 环境；本次没有新增跨操作系统实测：

```powershell
python -m pip install -e . pybind11 cmake
python scripts/eval/build_g31_continuous.py --name local
$g31Binary = (Get-ChildItem -LiteralPath build/g31_continuous_local/python -Filter 'g31_nowait*.pyd').FullName
python scripts/eval/run_g31_standard.py inspect --map nanning --binary $g31Binary
python scripts/eval/run_g31_standard.py inspect --map map2 --scale 2 --binary $g31Binary
python scripts/eval/run_g31_standard.py run --map nanning --scale 1 --binary $g31Binary --output outputs/experiments/g31_continuous_new_run
```

`local` 构建的仍是正式默认 006 算法，不会自动切换到研究候选。构建名须未使用；输出含源码快照和构建凭据，运行时用 `--binary` 指定这次实际生成的扩展。若需指定 CMake 生成器，可使用构建脚本的 `--generator` 选项。

`inspect`只构造和校验请求，不执行仿真。默认合同使用原观察窗；新运行必须选新输出目录。`--controls` 可以显式覆盖性能参数，但不能放松连续运动、设备/边入口间隔、源端名义顺序或 EBS 因果约束。合同、参数、输入、二进制与源码身份都会写入结果。

途中到达节点后执行局部下一跳选择；新路径只有取得完整续行证书后才能替换旧证书，失败沿旧证书继续。安全查询和证书搜索可到达终点，并非纯一跳安全保证。当前实现是单进程串行事件引擎，尚未实现真实设备间的分布式事务协议，也没有测量其通信延迟。

主 THT 对每个原始业务行李，将各运输段的“实际到达该段目标 − 首次实际进入规划尝试时刻”相加。失败规划、重试和入网前规划等待仍在时钟内，EBS 两段之间的存储时间不计。名义释放到首次尝试的积压、实际入网后的输送历时、固定窗口完成量和未完成量必须同时报告；未完成全人口不能用完成子集均值代替。

历史等待模型需要明确选择。以下历史命令以匹配的历史构建和归档输入已按配置准备为前提：

```powershell
python scripts/eval/run_g31_standard.py inspect --map nanning --execution-model legacy_waiting
python scripts/eval/run_g31_standard.py inspect --map map2 --execution-model legacy_waiting --s4-wait-estimator eta_calendar
```

[历史配置](../../configs/eval/g31_standard.json)、已归档请求和二进制保持原身份。旧 Python 调用若需要等待模型，也必须显式传入 `execution_model="legacy_waiting"`；仅传 legacy 评分或释放文件不会隐式切换模型。

011 有限未来源端预约是研究参照，并非默认算法。使用独立重建入口：

```powershell
python scripts/eval/rebuild_g31_research.py --name local011
```

该脚本同样支持可选的 `--generator`，产物写入 `build/g31_research_011_local011/`。它同时生成绑定本次二进制的 `registered_contracts/physical_contract_original_window.json` 和 `physical_contract_drain200000.json`；调用研究入口 `outputs/experiments/g31_no_wait_20261024/candidate011/run_candidate.py` 时，须以 `--physical-contract` 指向对应的新合同，而不是直接使用历史机器二进制登记。其余参数见研究入口的 `--help`，运行仍使用新的输出目录。

南宁 2× 的主 THT 和原窗完成量改善，同时两项截止指标仍落后于修复 HCA；023/024 截止优先和已测可变视野均未取得整体优势，详见结果记录。

本次发布不附历史机器上的二进制、完整第三方论文、论文逐页全文提取或大体量运行日志。保留的源码、配置、精简证据及其身份以[发布清单](publication_20261025/MANIFEST.json)为准；历史记录中的文件名和 SHA 不表示相应原始附件已随库分发。
