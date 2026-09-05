# Demo3D 与工程文档的紧凑静态证据

原材料根为 `C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料`。本目录只保存静态提取记录；没有执行模型、DLL、脚本、工程文件或网络端点。完整解压文件与含 IP 的通信源码留在本机 `tmp/pdfs/feng_primary_reaudit/demo3d_container`，没有提交。

从工作树根重生成：

```powershell
python -X utf8 scripts/eval/extract_feng_demo3d_semantics_evidence.py
```

可用 `--source-root` 指向同一份材料的其他位置；输入文件 hash 在输出中核对。原件不随代码库分发，因此重提取需要原材料；下列摘要、参数、调用标记与短摘录可以直接审阅。

- [model_manifest.json](model_manifest.json)：外层 ZIP、内部 XML 的身份，73 个脚本容器及内嵌项目成员 hash。记录容器时间不等于恢复了作者修改。
- [scene_script_bindings.json](scene_script_bindings.json)：3,267 个直接绑定的脚本/类计数及相关实例，区别脚本库存在和场景绑定。
- [transfer_and_sensor_instances.json](transfer_and_sensor_instances.json)：全部 77 个路口控制器、47 个 lift 转运属性实例、23 个通信传感器的 GUID 与配置；不含 IP 配置。路口 0.6 秒与 lift 的自定义 2 秒不是同一属性。
- [source_excerpts.json](source_excerpts.json)：7 个相关脚本/成员的原始 hash 和原行号短摘录；未提交整份厂商库或通信实现。
- [flowcontrol_visual_procedures.json](flowcontrol_visual_procedures.json)：`FlowControl1` 的 7 个过程/函数静态 AST 摘录，按 XML 顺序保留可见标记并列明过程调用。**标记顺序不是执行轨迹**；`ast_sha256` 是 ElementTree UTF-8 序列化子树 hash，不是原 ZIP 成员的字节片段 hash。
- [engineering_document_excerpts.json](engineering_document_excerpts.json)：设计、安装、使用与仿真报告的原件 hash 和正文/表格段号摘录。此处段号包含表内段落。

实查结论见 [一手语义复核第 7 节](../../../../docs/baselines/feng_dh_primary_semantics_reaudit_20260905.md)。已恢复的是目标表/设备控制与外部路由接口的证据；没有恢复论文独立 DH 的 moving/stopped 评分器。Scene 保存的 linear-physics 设置会使可读路口控制器初始化为 `VisualOnly`，故不能把库方法直接当作该保存模式的实际运动轨迹；模型中的 0.2 秒又属于硬编码目标映射辅助过程，不能充当 DH tick 的代码证据。
