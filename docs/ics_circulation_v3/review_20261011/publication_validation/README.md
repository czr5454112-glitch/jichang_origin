# 实际提交导出与发布复核

本目录在代码提交 `defd79effe02ee13f1a5bbbbc5143f6d0dce2f63` 形成后追加，属于发布复核，不改写 Round11 已封存资源账，不改变生产源码或测试。

## 验证对象和结果

1. `archive.json`：由上述实际 Git 提交导出固定 ZIP，14,251,028 字节、1,636 个文件，记录 SHA256、独立解压位置及父进程计时。
2. `staging_validation.json`：代码提交前限定1,627个允许路径，实际1,571个变更路径；读取暂存blob核对字节，211份Python源码/测试全部匹配冻结文件。既有C++工作区改动未暂存。
3. `fixture_restoration_verified.json`：六份gzip全部恢复并核对133,186,733原始字节的完整大小及SHA，不抽样。bootstrap原始成功输出在工具记录中，本文没有伪造其stdout文件。
4. `isolated_validation_001/`：首次`python -I`屏蔽user-site中的Pygments，导入pytest时失败，测试尚未收集/运行；保留traceback、源前后SHA及运行脚本。
5. `isolated_validation_002/`：解压目录使用正常Python依赖环境、同一脚本、全部89个测试文件；1519通过，失败/错误/跳过均0，211文件字节不变。完整JUnit和结果保留，没有删测试或改变fixture。
6. `environment_probe.json`：实际解释器/依赖版本和模块路径，两个ICS入口从解压目录导入。依赖来自已安装环境，这是独立代码导出复核，不是新装操作系统或全部历史实验的自包含重放。
7. `code_push_verified.json`：实际成功push及随后ls-remote输出，远端SHA一致。首次连接重置及读操作连接失败保留；临时HTTP/1.1和获授权的网络访问完成核验，无强推或持久Git配置修改。
8. `collection.json`：收集时逐字节复制的14份文件及SHA，只绑定当时集合；后来新增的本README及push回执未假称属于该集合。`collect_publication_receipts.py`是原执行脚本副本，原位置在本地`outputs/reports/ics_v3_publication_20261011/`，移动后的相对路径不适合直接重跑。

实际回归命令：

```text
python docs/ics_circulation_v3/review_20261011/tools/run_release_tests.py --output C:/PROGRAMING/czr005/outputs/reports/ics_v3_publication_20261011/isolated_validation_002
```

cwd为独立解压根目录，前置运行`tools/prepare_fixtures.py`。新复核须使用新输出目录。没有重新运行完整原图业务窗口或全量证书审计，其结论仍按历史证据及公开访问边界理解。

## 问题解决及计算范围

六份测试依赖原来仅在本地outputs，现完整无损封装，并提供校验、拒绝覆盖及路径边界处理；恢复后原测试全部正常运行。这解决发布可复核性，不是新增算法收益。

Python启动参数导致依赖不可见，改用已安装完整环境解决，没有改冻结211文件。Git暂存首次因沙箱禁止写`.git/index.lock`失败，获授权的Git写操作随后成功；未发生自动审批拒绝。整理期间工具字符串/PowerShell语法错误在目标操作前失败，规范调用后完成，未用失败结果冒充检查通过。

发布计时单列：证据打包CPU153.34375秒；scope核查11.46875秒；bootstrap I/O探针0.140625秒；archive/extract父进程10.90625秒；首次pytest依赖失败0.1875秒；实际全回归105.109375秒（wall108.4056324秒）；回执收集另见`collection.json`。这些有范围的片段不构成完整总成本。Git子进程、网络、阅读/编辑/编排等未全部仪表化，保持未知；回归内部物理次数未知。哈希/复制阶段本身无物理实验。

1519通过不等于两项需求最终验收、业务完成、100ms达标或研究创新成立。下一步按正式交接任务独立审核和修订。
