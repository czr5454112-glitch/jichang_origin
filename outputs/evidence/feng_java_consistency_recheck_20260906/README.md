# 原始 Java 一致性与时间标签诊断证据

本目录只含新审计材料，不修改或替代正式模拟数据。`native_route_time_audit_all.json` 是计入 source、goal 全部 through 后重新扫描全部 60 格的最终结果；早期 tmp 试算未计 goal dwell，已被替代，不发布为最终数字。主结论见 [独立报告](../../../docs/baselines/feng_java_implementation_consistency_recheck_20260906.md)。

- `source_identity_recheck.json`：材料原目录与仓库镜像15份Java、map2、原input，以及当前HCA/V5源码SHA。
- `probe_compilation_identity.json`：直接以未改写材料原App/GUI源编译；Astar.class与正式HCA逐字节相同。
- `OriginalAstarTimestampProbe.java` / `original_astar_timestamp_result.json`：五节点零预约、零through原类反例。
- `OriginalMapRouteTimeProbe.java`：打印返回路线的原节点t1/t2与真实父节点递推；两个JSON保留南宁受影响单OD和map2无异常对照。空预约诊断不冒称正式拥堵状态重放。
- `audit_native_route_times.py` / `native_route_time_audit_all.json`：只读正式60格，双SHA验证native压缩档案、检查地图原字节，按原Astar递推校验wrapper的goal T2。该项不是碰撞审计或修后性能预测。

从仓库根目录运行（Windows PowerShell，JDK18、Python3.11）：

```powershell
$taskSources = @(Get-ChildItem 'legacy/jichang_origin_readonly/src/App' -Filter '*.java' -File | ForEach-Object FullName)
$taskSources += (Resolve-Path 'legacy/jichang_origin_readonly/src/ICS_GUI/ICS_GUI.java').Path
$probeDir = 'outputs/evidence/feng_java_consistency_recheck_20260906'
$probeBuild = 'tmp/feng_java_consistency_recheck_reproduction/classes'
& javac -encoding UTF-8 -d $probeBuild @taskSources "$probeDir/OriginalAstarTimestampProbe.java" "$probeDir/OriginalMapRouteTimeProbe.java"
& java '-Djava.awt.headless=true' -cp $probeBuild App.OriginalAstarTimestampProbe
& java '-Djava.awt.headless=true' -cp $probeBuild App.OriginalMapRouteTimeProbe 'legacy/jichang_origin_readonly/map2.txt' 5 47 12471
$runRecord = Get-Content 'outputs/runtime/hca_segment_identity_20260906_fast_cleanup/nanning_1p00x/seed_104729/hca_segment_identity/runner_status.json' -Raw | ConvertFrom-Json
& java '-Djava.awt.headless=true' -cp $probeBuild App.OriginalMapRouteTimeProbe $runRecord.inputs.map.path 24 53 8866
python outputs/evidence/feng_java_consistency_recheck_20260906/audit_native_route_times.py --all
```

本次实际编译输入使用材料原目录的App与GUI文件；上面的仓库镜像复现输入文本等价，Astar唯一换行差异不会改变JDK18 class。原类产物只留tmp，不提交class文件。最后一条只读取固定新runtime中的terminal runner与原生gzip，不调用normalizer或仿真，不修改冻结输出；会重写本目录对应诊断JSON。移机若未恢复完整原生runtime，可凭报告中源路径和解压SHA到正式campaign档案定位恢复，不能把缺失数据当PASS。

对原THT直接减去route excess不是有效修复：实际修复会影响预约和后续路线。证据只支持该冻结程序的路线时间语义存在缺陷，保留此前身份、人口与归档审计原范围。
