# Round11 作者适配问题及处理

author_tests_001 首次 44 项全通过，未发生需要隐藏或覆盖的失败运行。

在设计阶段明确处理上一轮边界：纯投射 API 的内容自封不能认证磁盘原件；新运行入口强制重读原 loader 并比较完整对象。作者对抗测试主动同时重封源对象、投射对象与 run 声明，仍由不变 raw/canonical 源拒绝。此处理没有修改上一轮冻结模块或历史产物。

未发现的问题不能据此宣称不存在。独立审核、完整源适配结果和资源在后续 RESULTS.md 另记；未仪表化辅助时间保持未知。

full_adapter_001 在完成 1× 原 loader 后失败，CPU 5.9375 秒、wall 6.1138175 秒、0 物理。审计 driver 错把 Round10 扁平 manifest 当作含 outputs 层的格式，KeyError: outputs；没有进入投射构造或运行适配。已保存失败 traceback、源码快照、资源及前后 SHA。仅修新审计 driver 的 manifest 索引，冻结 production 与 tests 未改变；后续用 full_adapter_002 新目录重跑，001 原件不覆盖。

全量核验期间一次 Get-CimInstance Win32_Process 只读进程查询被本机拒绝访问；没有申请提权、没有重复尝试或改变运行。该辅助查询未仪表化 CPU，归 general_auxiliary_cpu_unknown，不能按 0 计；它没有调用仿真。
