# 576 格实验发布盘点

本目录仅新增只读盘点，不更改实验结果、Git 索引或远端。权威计划为 `frozen_plan_v6/plan.json`，SHA-256 `7a4369b09efb8b2935a7197d6919375be730ffb5ee17a8cad55718fcdb262daf`。本次盘点完成不等于发布或全量归档字节校验完成。

`inventory.json` 可直接作为打包器的文件选择依据：

- `all_cell_files_for_optional_exact_directory_restore`：576 个正式目录现存全部 10,682 文件，共 17,346,104,251 字节，含明文副本，适用于原样恢复。
- `selected_cell_files`：4,728 份 gzip 加 3,098 份 JSON，共 7,826 文件、10,385,079,395 字节。gzip 为 10,363,625,204 字节；最大单文件 40,325,709 字节。该列表保留原生压缩证据，不含可由 gzip 恢复的明文大表。
- `cells`：每个正式 cell ID 到文件、原始 spec、runner 的映射。不得把未入选的旧故障或失败尝试算作正式 576 格。
- `inputs`：40 个地图/负荷/种子输入族的 raw、canonical、identity 及地图。120 份 workload 源文件未跟踪，但其旧 V5 归档共 78,227,961 字节已跟踪；本次逐项核对源 SHA、归档 SHA 与 Git index blob 相同。没有重新解压这些输入归档；原始内容身份来自已核验的旧 manifest。地图原件已跟踪。
- `support`：4 个 runner、576 个 spec、2 个协议、2 个地图 profile、最终 `.pyd`、61 个 Java class、16 个 Java 源文件的路径、大小、SHA。此项不是 Python/C++ 所有依赖的自动传递闭包。

## 必须保留的路径

所有下列路径均相对于仓库根 `C:/PROGRAMING/czr005/.feng_cie_dh_worktree`。

|用途|具体路径或选择规则|
|---|---|
|正式 576 格原生与归一化结果|`outputs/runtime/feng_paper_suite_20260907/cells/`，按 `inventory.json` 的 cell ID 选择|
|最终结果|`outputs/reports/feng_paper_suite_20260907/campaign_20260907T103048Z_87ca6ab5b9/`|
|最终主控|`outputs/runtime/feng_paper_suite_20260907/campaign_master/20260907T103048Z_87ca6ab5b9/`|
|基础 480 外层验收|`outputs/runtime/feng_paper_suite_20260907/orchestration/20260907T103503Z_c3cdea603a/`|
|故障 96 外层验收|`outputs/runtime/feng_paper_suite_20260907/orchestration/20260908T042131Z_9ddd661288/`|
|计划、来源变更与最终独立审核|`outputs/evidence/paper_suite_20260907/`；尤其保留 V4 specs、V5/V6 plan、parser recovery、scope reduction、base480 与 final576 独立审核。V6 并未复制所有 spec 到自身目录|
|共同 workload 已跟踪替身|`outputs/evidence/feng_dh_boundary_clearance_v5_20260905/{map}_{load}/seed_{seed}/workload/`，以 `inputs[].archive_path` 为准确列表|
|workload 替身来源索引|`outputs/evidence/hca_segment_identity_20260906/campaign_manifest.json` 及其引用的 V5 manifest；不得把旧 HCA 数值当作本次正式结果|
|最终 CPP 二进制|`outputs/evidence/g31_fault_potential_repair_20260907/builds/38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20/czr005_cpp.cp311-win_amd64.pyd`|
|CPP 源身份与源快照|`outputs/evidence/g31_fault_potential_repair_20260907/final_build_v1/{manifest.json,source_snapshot.zip}`；仓库相应 CMake、C++、Python 改动亦应提交|
|最终 HCA classes|`build/hca_paper_suite_v3_20260907/`，按 `support` 的 28 个 class 清单及 build identity 保存|
|最终 DH classes|`build/feng_dh_paper_suite_v6_20260907/`，按 `support` 的 33 个 class 清单及 build identity 保存|
|Java 生产源|`benchmarks/java/hca_paper_suite_v3/`、`benchmarks/java/feng_cie_dh_paper_suite_v6/App/`|
|协议、执行/后处理工具、语义说明|`configs/eval/feng_paper_suite*20260907.json`、计划实际绑定的 `scripts/eval/` 文件、相应 `docs/baselines/` 文档|

前置验证应根据最终 master 的 `prerequisites`/`phases` 引用继续收集，尤其正常 1×/2×等价及有界故障机制验证。相关专用根包括 `outputs/runtime/g31_fault_potential_repair_20260907/`、`outputs/runtime/hca_paper_suite_v3_20260907/`、`outputs/runtime/feng_dh_paper_suite_v6_20260907/`。这些是准入证据，不能混入正式格数量。DH 的 `b_nanning_2x_v2p5_s104729_q00_dh_postprocess_v2` 保留了不重跑原生的恢复来源；其旧失败目录和 `dh_na_parser_recovery_v2/` 应随来源证据保留。

## Git 忽略与可移植性

`git check-ignore --no-index` 确认：`data/processed/workloads/cie_external_robustness/` 被整根忽略；`build*/` 同时忽略 Java build 目录和最终 `.pyd` 所在的 `builds/` 目录。不能依赖常规 `git add` 自动纳入。当前新实验 runtime 根没有被忽略，整根加入则会额外加入 6,961,024,856 字节明文/其他文件。是否保留这些副本应由发布打包清单明确决定，不能静默丢弃原生档案。

冻结 plan/spec/status 含原机器绝对路径。归档内部条目多为相对路径，但 reporter 仍按原绝对路径取文件。因此应另建发布 manifest，将实际仓库相对路径、原始 provenance 路径、SHA/大小绑定，并提供显式路径重映射；不要为可移植性改写冻结原件。JDK/Python 的安装路径属于执行环境记录，不要求偷偷复制整套本机环境或论文原件。

## 发布完整性核对方案

1. 按 V6 精确 576 坐标构造文件集；结果包括 480 base、96 fault，413 全人口完成、163 截尾。保持全部截尾格和六项 THT 空值。
2. 对实际打包文件逐个计算 SHA-256。原生 gzip 与本清单所列既有声明 SHA 比对；请求/派生归档未统一绑定压缩 SHA 的，应在新的发布 manifest 中补充实际字节 SHA，不冒称原 runner 已记录。
3. 以仓库相对路径及每文件 SHA 建立总 manifest；分卷记录卷 SHA、字节数和所含文件索引。输入替身明确绑定原始内容 SHA 与归档 SHA，保留旧 manifest 的历史来源。
4. 在独立恢复目录验证分卷哈希、安全路径包含关系和全部文件字节；再按恢复映射读取小型元数据，重复 576 坐标、408 配对、80/52 分组、spec/runner/normalized/外层 receipt SHA 核验。
5. 将实际远端 commit、Release 标识、资产名/大小及下载后卷 SHA 与总 manifest 绑定。只有这一步完成才称“全部实验已推送”。本次 inventory 未执行上传、下载或全原生重算。
