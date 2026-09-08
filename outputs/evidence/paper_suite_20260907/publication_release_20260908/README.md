# Feng 576 组完整实验发布索引

本次发布包含正常工况 480 组、四个代表全天已知断线场景形成的 96 组，共 576 组，已通过独立验收。全部正式实验目录、共同输入、生产执行文件和相关修复/准入证据均已入包；保留早期及被替代记录的原始身份，不将它们计入 576 组。

- 原始文件：21,645 个，共 18,651,152,701 字节。
- ZIP 分卷：13 个，共 12,487,603,897 字节；每个分卷可独立读取。
- 正式 576 组原目录：10,682 个文件，包括原生压缩归档、仍保留的明文结果及小型统计，不只包含汇总表。
- 另保留 40 个地图/负荷/种子输入族、两地图、最终 G31 `.pyd`、Java classes 与全局 build_identity、冻结源码快照。

Git 保存源码、协议、报告、小型结果与发布索引。大体积原生文件保存在同一仓库的 Release 附件中，原文件在本地保持完整。本发布没有使用 Git LFS，也不要求付费下载依赖。

[完整实验 Release](https://github.com/czr5454112-glitch/jichang_origin/releases/tag/feng-suite-576-20260908) · [最终结果说明](../../../reports/feng_paper_suite_20260907/final576_results_notes_20260908.md) · [完整报告](../../../reports/feng_paper_suite_20260907/campaign_20260907T103048Z_87ca6ab5b9/report.md)

## 下载和核对

下载 Release 的全部附件，或使用 GitHub CLI：

```powershell
gh release download feng-suite-576-20260908 --repo czr5454112-glitch/jichang_origin --dir ./feng-suite-download
python ./feng-suite-download/verify_feng_suite_release_20260908.py --manifest ./feng-suite-download/manifest.json --archives-dir ./feng-suite-download
```

校验器默认只读、不执行归档代码，依次核对 `files.jsonl` 的 SHA、全部 ZIP 的大小/SHA、每个成员的路径/归属/大小/SHA，以及缺失、重复和多余条目。全部通过时输出 JSON `PASS`。可选 `--extract-to <尚不存在的新目录>`，其父目录须已存在；必须在全部校验通过后才提取，且不能覆盖原始工作区。

`manifest.json` 绑定全部分卷和逐文件索引；`files.jsonl` 使用仓库相对路径，记录每个文件所在分卷及原字节 SHA。`coverage_verification.json` 核对正式 576 组和执行依赖的完整覆盖；`verification.json` 是实际完整分卷及成员的本地校验结果。远端发布与服务器 SHA 核对以完成后的 `publication_receipt.json` 为准。

## 原字节与运行身份

普通 Git 文本检出可能受换行设置影响。原始运行所对应的 C++/Python/Java 物理字节，以分卷内文件及既有 `source_snapshot.zip` 为准；它们不能用 Git 审阅版的自动换行结果替代。旧 plan/spec/日志中的 `C:\PROGRAMING\...` 绝对路径作为历史来源原样保留；ZIP 相对路径与逐文件索引支持在其他目录核对和恢复。校验归档不依赖这些旧绝对路径；直接重跑旧 runner 时仍需另行处理本机路径和运行环境。

执行环境依赖为原 Python 3.11 / Windows x64 CPython 扩展，以及 JDK 18。未把系统安装目录或凭证放入实验包。

## 结果解释

413 组全人口完成；163 组仍有未完成行李，其总体 THT 保持为空。G31 不能称为全场景、全指标全面领先：map2 2× 的耗时仍落后 Tarau，部分南宁配置的准时率也有反例。断线是四个代表场景的全天已知故障，不是完整 16 场景或中途断线重连复现；HCA 的部分低完成率还受不可达任务阻断同源后续释放的机制影响。

早前完成说明记录的是当时尚未推送的状态；本目录和 Release 的发布回执记录此次后续发布状态。
