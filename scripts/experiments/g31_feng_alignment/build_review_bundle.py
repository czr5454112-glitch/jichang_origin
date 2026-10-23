"""Build/verify the explicit two-map review publication, without running a simulator.

Run ``plan`` while experiments are active. Run ``build`` only after both campaigns
are frozen. Archives retain repository-relative paths; ordinary reports stay at
their original paths. Verification works from a review checkout and its ZIPs,
without original native payloads or access to the author's external directories.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_feng_alignment import metrics

BASE_COMMIT = "9f23c25a631786ad4c1f47c442d72dcfb3ac098f"
OUTPUT = "deliverables/g31_waiting_two_maps_review_20261023"
MANIFEST = OUTPUT + "/PUBLICATION_MANIFEST.json"
CHUNK = 1024 * 1024
SOURCE_FILES = (
    "CMakeLists.txt",
    "cpp/ics_core/bindings/czr005_cpp.cpp",
    "cpp/ics_core/runtime/event_driven_junction.hpp",
    "src/czr005/cpp_backend.py",
    "tests/test_g4irsf31_map_adapter.py",
    "cpp/ics_core/runtime/s4_wait_estimator.hpp",
    "cpp/tests/test_g31_eta_wait.cpp",
    "tests/test_g31_feng_alignment_metrics.py",
    "tests/test_g31_feng_alignment_map2.py",
    *["scripts/experiments/g31_feng_alignment/" + name for name in (
        "audit_requests.py", "experiment.py", "java_map2.py", "map2_experiment.py",
        "metrics.py", "summarize.py", "verify_historical_legacy.py", "build_review_bundle.py")],
    *["docs/g31_ics_circulation/" + name for name in (
        "FENG_NATIVE_WAITING_RULES_AUDIT_20261023.md",
        "S4_WAIT_ESTIMATOR_CANDIDATE_20261023.md",
        "PRO_REVIEW_CHECKLIST_20261023.md")],
)


@dataclass(frozen=True)
class Campaign:
    name: str
    directory: str
    canonical: str
    report_data: str
    java_directory: str
    input_paths: tuple[str, ...]


CAMPAIGNS = (
    Campaign("nanning", "outputs/experiments/g31_feng_alignment_20261023",
             "artifacts/tasks/g4irsf31_nanning/nanning_1x_canonical.jsonl",
             "report_data_002",
             "outputs/experiments/g31_physical_waiting_20261023/java_native_1x",
             ("data/processed/maps/nanning_airport_profile.json",
              "data/processed/maps/nanning_legacy.txt",
              "artifacts/tasks/g4irsf31_nanning/nanning_1x_raw.txt",
              "artifacts/tasks/g4irsf31_nanning/nanning_1x_manifest.json")),
    Campaign("map2", "outputs/experiments/g31_feng_alignment_map2_20261023",
             "data/processed/tasks/inputdata.jsonl", "report_data_001",
             "outputs/experiments/g31_feng_alignment_map2_20261023/java_native_1x",
             ("data/processed/maps/map2.json", "legacy/jichang_origin_readonly/map2.txt",
              "legacy/jichang_origin_readonly/inputdata.txt")),
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def digest_stream(handle):
    digest = hashlib.sha256()
    size = 0
    while data := handle.read(CHUNK):
        digest.update(data)
        size += len(data)
    return digest.hexdigest(), size


def file_evidence(root: Path, relative: str):
    path = checked_path(root, relative)
    with path.open("rb") as handle:
        sha, size = digest_stream(handle)
    return {"path": relative, "sha256": sha, "bytes": size}


def checked_relative(value: str):
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(p in ("..", "") for p in path.parts) or ":" in value:
        raise ValueError(f"unsafe repository-relative path: {value}")
    return path.as_posix()


def checked_path(root: Path, relative: str):
    relative = checked_relative(relative)
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    return target


def recorded_repo_path(value: str):
    """Rebind historical Windows evidence paths without depending on that drive."""
    normal = value.replace("\\", "/")
    root_text = ROOT.as_posix().rstrip("/") + "/"
    if normal.lower().startswith(root_text.lower()):
        return checked_relative(normal[len(root_text):])
    if ":" not in normal and not normal.startswith("/"):
        return checked_relative(normal)
    for marker in ("/outputs/", "/artifacts/", "/data/", "/build/", "/scripts/", "/cpp/", "/legacy/"):
        if marker in normal:
            return checked_relative(normal[normal.index(marker) + 1:])
    raise ValueError(f"cannot map external path into repository: {value}")


def report_path(campaign):
    return f"{campaign.directory}/{campaign.report_data}/report_data.json"


def load_campaign(root, campaign):
    report = read_json(checked_path(root, report_path(campaign)))
    if len(report["arms"]) != 7:
        raise ValueError(f"{campaign.name}: exactly seven full-population arms required")
    canonical_sha = file_evidence(root, campaign.canonical)["sha256"]
    if report["canonical"]["sha256"] != canonical_sha:
        raise ValueError(f"{campaign.name}: report canonical evidence mismatch")
    arms = []
    for label, value in report["arms"].items():
        directory = recorded_repo_path(value["table"]["run_directory"])
        if not directory.startswith(campaign.directory + "/"):
            raise ValueError(f"{campaign.name}: report arm belongs to another campaign")
        manifest = read_json(checked_path(root, directory + "/manifest.json"))
        summary = read_json(checked_path(root, directory + "/summary.json"))
        if manifest["canonical"]["sha256"] != canonical_sha:
            raise ValueError(f"{campaign.name}: arm canonical mismatch: {label}")
        if summary["metrics"]["offered_transport_legs"] != 43603 or summary["metrics"]["offered_business_bags"] != 28506:
            raise ValueError("publication requires the full original 1x population")
        if summary["metrics"]["completed_transport_legs"] != 43603:
            raise ValueError("this completed-campaign bundle requires every offered segment to finish")
        arms.append({"label": label, "directory": directory, "manifest": manifest,
                     "summary": summary, "table": value["table"]})
    native = [a for a in arms if "binary" in a["manifest"]]
    if len(native) != 6 or len({a["manifest"]["binary"]["sha256"] for a in native}) != 1:
        raise ValueError("six native arms must use one identical new binary")
    return report, arms


def public_metadata(root, campaign, arms):
    required = [campaign.directory + "/REPORT.md", report_path(campaign),
                f"{campaign.directory}/{campaign.report_data}/arm_table.csv",
                campaign.directory + "/final_audit_001/audit.json",
                campaign.directory + "/request_audit_001/audit.json"]
    for arm in arms:
        required += [arm["directory"] + "/summary.json", arm["directory"] + "/manifest.json"]
        exact = arm["directory"] + "/legacy_exact_regression.json"
        if checked_path(root, exact).is_file():
            required.append(exact)
    if campaign.name == "nanning":
        required += [campaign.directory + "/" + name for name in (
            "rollback_receipt.json", "implementation_receipt.json", "cpp_tests.xml",
            "eta_tests_final.xml", "python_regressions_002.xml", "api_tests.xml")]
    else:
        required += [campaign.directory + "/historical_legacy_exact.json",
                     campaign.directory + "/python_regressions_002.xml",
                     campaign.directory + "/final_cross_map_check_001.json",
                     campaign.directory + "/frozen_evidence_audit_001.json"]
        first_attempt = campaign.directory + "/python_regressions_001.xml"
        if checked_path(root, first_attempt).is_file():
            required.append(first_attempt)
    # Reports link these small receipts directly on GitHub, so their original
    # repository paths must be published as ordinary files as well as in ZIPs.
    for name in ("source_input_manifest.json", "compile_receipt.json"):
        required.append(campaign.java_directory + "/" + name)
    for name in ("source_delay_and_time_boundary_audit.json",
                 "independent_business_segment_audit.json", "post_run_source_audit.json"):
        relative = campaign.java_directory + "/" + name
        if checked_path(root, relative).is_file():
            required.append(relative)
    for path in required:
        if not checked_path(root, path).is_file():
            raise FileNotFoundError(path)
    return required


def add_entry(entries, root, relative, *, source=None, expected_sha=None, origin=None):
    relative = checked_relative(relative)
    source = Path(source) if source is not None else checked_path(root, relative)
    if not source.is_file():
        raise FileNotFoundError(source)
    if relative in entries:
        if entries[relative]["source"].resolve() != source.resolve():
            raise ValueError(f"conflicting ZIP entry: {relative}")
        return
    entries[relative] = {"source": source, "expected_sha256": expected_sha,
                         "origin": origin or "repository_relative_file"}


def campaign_entries(root, campaign, arms, metadata, include_binary):
    entries = {}
    omitted = []
    for relative in (campaign.canonical, *campaign.input_paths, *metadata):
        add_entry(entries, root, relative)
    for arm in arms:
        directory = arm["directory"]
        for filename in ("segments.jsonl", "business.jsonl"):
            add_entry(entries, root, directory + "/" + filename)
        if "binary" in arm["manifest"]:
            add_entry(entries, root, directory + "/request.json.gz")
            payload = directory + "/native_payload.json.gz"
            evidence = file_evidence(root, payload)
            expected = arm["manifest"].get("native_payload", {}).get("sha256")
            if expected and evidence["sha256"] != expected:
                raise ValueError(f"native payload hash changed before packaging: {payload}")
            omitted.append({**evidence, "included": False,
                            "reason": "large full native payload; full lifecycle rows, summary and request are included"})
            # Preserve the small, exact per-run harness snapshots when current
            # generic tooling has subsequently acquired map2 support.
            for name in ("experiment.py", "metrics.py", "map2_experiment.py"):
                snapshot = directory + "/source/scripts/experiments/g31_feng_alignment/" + name
                if checked_path(root, snapshot).is_file():
                    add_entry(entries, root, snapshot)
    java = campaign.java_directory
    for filename in ("source_input_manifest.json", "compile_receipt.json"):
        add_entry(entries, root, java + "/" + filename)
    for filename in ("release.csv", "segment_lifecycle.csv", "output.txt", "outputstarttime.txt",
                     "routes.csv", "run_status.json", "summary.csv"):
        add_entry(entries, root, java + "/run_01/" + filename)
    for filename in ("prepared_command.json", "independent_business_segment_audit.json",
                     "post_run_source_audit.json", "source_delay_and_time_boundary_audit.json"):
        if checked_path(root, java + "/" + filename).is_file():
            add_entry(entries, root, java + "/" + filename)
    if campaign.name == "map2":
        original = read_json(checked_path(root, java + "/source_input_manifest.json"))
        for record in original["source_comparison"]:
            add_entry(entries, root, java + "/source/" + record["path"],
                      expected_sha=record["original_sha256"], origin="exact_original_java_source_snapshot")
        if len(original["source_comparison"]) != 15:
            raise ValueError("exactly 15 original Java source snapshots required")
        for comparison in original["input_comparison"]:
            record = comparison["original"]
            add_entry(entries, root, java + "/source/original_inputs/" + comparison["name"],
                      source=record["path"], expected_sha=record["sha256"],
                      origin="external_original_bytes_at_declared_virtual_repository_path")
    if include_binary:
        native = next(a for a in arms if "binary" in a["manifest"])
        original = native["manifest"]["binary"]
        filename = original["path"].replace("\\", "/").rsplit("/", 1)[-1]
        frozen = native["directory"] + "/binary/" + filename
        add_entry(entries, root, frozen, expected_sha=original["sha256"],
                  origin="frozen_native_binary_shared_by_both_maps")
    return entries, omitted


def make_archive(root, campaign, entries):
    relative = OUTPUT + "/" + campaign.name + "_full_evidence.zip"
    target = checked_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite an existing evidence archive: {target}")
    records = []
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for name, item in sorted(entries.items()):
            source = item["source"]
            initial = source.stat()
            digest = hashlib.sha256()
            size = 0
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            with source.open("rb") as src, archive.open(info, "w", force_zip64=True) as dst:
                while data := src.read(CHUNK):
                    digest.update(data)
                    size += len(data)
                    dst.write(data)
            final = source.stat()
            sha = digest.hexdigest()
            if (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
                raise ValueError(f"source changed during archive construction: {source}")
            if item["expected_sha256"] and sha != item["expected_sha256"]:
                raise ValueError(f"snapshot differs from its recorded original: {source}")
            records.append({"path": name, "sha256": sha, "bytes": size,
                            "origin": item["origin"], "source_at_build": str(source.resolve())})
    result = {**file_evidence(root, relative), "map": campaign.name, "entries": records}
    if result["bytes"] >= 100_000_000:
        raise ValueError("single archive exceeds the intended GitHub regular-file limit")
    return result


def read_zip_json(archive, path):
    with archive.open(path) as handle:
        return json.load(io.TextIOWrapper(handle, encoding="utf-8"))


def read_zip_jsonl(archive, path):
    with archive.open(path) as handle:
        return [json.loads(line) for line in io.TextIOWrapper(handle, encoding="utf-8") if line.strip()]


def verify_archive(root, item, campaign_record):
    path = checked_path(root, item["path"])
    if file_evidence(root, item["path"]) != {k: item[k] for k in ("path", "sha256", "bytes")}:
        raise ValueError(f"ZIP hash/size mismatch: {path}")
    expected = {entry["path"]: entry for entry in item["entries"]}
    if len(expected) != len(item["entries"]):
        raise ValueError("duplicate expected ZIP entry")
    result = {"map": item["map"], "archive": item["path"], "entry_count": len(expected), "arms": []}
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or set(archive.namelist()) != set(expected):
            raise ValueError("ZIP contains a missing, extra or duplicate entry")
        for name, evidence in expected.items():
            checked_relative(name)
            with archive.open(name) as handle:
                sha, size = digest_stream(handle)
            if sha != evidence["sha256"] or size != evidence["bytes"]:
                raise ValueError(f"ZIP member hash/size mismatch: {name}")
        canonical = read_zip_jsonl(archive, campaign_record["canonical"])
        if len(canonical) != 43603 or len({row["task_id"] for row in canonical}) != 28506:
            raise ValueError("archive canonical cohort is not the complete 1x workload")
        for arm in campaign_record["arms"]:
            directory = arm["directory"]
            segments = read_zip_jsonl(archive, directory + "/segments.jsonl")
            recomputed, business = metrics.audit(canonical, segments, horizon=98259.0)
            archived_summary = read_zip_json(archive, directory + "/summary.json")
            public_summary = read_json(checked_path(root, directory + "/summary.json"))
            if archived_summary != public_summary or recomputed != public_summary["metrics"]:
                raise ValueError(f"full-segment metric recomputation differs: {directory}")
            if business != read_zip_jsonl(archive, directory + "/business.jsonl"):
                raise ValueError(f"business ledger recomputation differs: {directory}")
            result["arms"].append({"label": arm["label"], "segments_checked": len(segments),
                                   "business_rows_checked": len(business), "summary_exact": True,
                                   "business_ledger_exact": True})
    return result


def render_readme(root, campaign_data, archives):
    lines = ["# G31 双地图等待评分审阅包", "",
             "基于 `" + BASE_COMMIT + "` 的独立审阅分支；默认 `legacy` 保持不变。",
             "请从 [REVIEW_PROMPT.md](REVIEW_PROMPT.md) 开始审阅。源码修改仍在原仓库路径，报告和机器审计未移动。", "",
             "本次保留成熟 G31/S4/J2/PIBT，仅增加可关闭的拥堵评分候选。旧 G31 已有 ETA 日历等待，正式可见性原已开启。双方均不新增线路容量，不运行空托盘。",
             "两图使用同一原始 28,506 件业务／43,603 个运输段；南宁是 OD 投影。固定参数、不为 map2 重新调参，是地图迁移验证，不是两份独立客流样本或普遍优势证明。", "",
             "## 各图完整七臂结果", "",
             "单位为秒；每行使用全部 43,603 段。规范起点与实际释放起点分别列出，不能混为同一个比较。", "",
             "| 地图 | 实验臂 | 完成段 | 规范到达→完成均值 | 实际释放→完成均值 | 规范 P95 | EBS 因果异常业务 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for campaign, report, arms in campaign_data:
        for arm in arms:
            value = arm["summary"]["metrics"]
            own = value["full_population_segment_elapsed_from_canonical_pass_seconds"]
            released = value["full_population_segment_elapsed_from_actual_release_seconds"]
            lines.append(f"| {campaign.name} | {arm['label']} | {value['completed_transport_legs']:,} | {own['mean']:.3f} | {released['mean']:.3f} | {own['p95']:.3f} | {value['ebs_causality_violation_count']:,} |")
    lines += ["", "原释放各臂具有各自源策略；同 Java 释放臂才共享实际 generator release。表中同释放臂的规范耗时仍包含 Java 源生成延迟，不能误称实际释放后的耗时。", ""]
    directions = []
    for campaign, _, arms in campaign_data:
        def select(mode, own):
            matches = [a for a in arms if a["manifest"].get("score_overrides", {}).get("s4_wait_estimator") == mode
                       and a["manifest"]["release_contract"].startswith("canonical_pass_time") == own]
            if len(matches) != 1:
                raise ValueError("README requires the explicit three modes by two release-factor matrix")
            return matches[0]["summary"]["metrics"]
        key = "full_population_segment_elapsed_from_canonical_pass_seconds"
        baseline = select("legacy", True)[key]["mean"]
        deltas = {mode: 100 * (select(mode, True)[key]["mean"] - baseline) / baseline
                  for mode in ("eta_calendar", "eta_flow")}
        directions.append(deltas["eta_calendar"])
        lines.append(f"- {campaign.name} 原释放：相对旧 G31，eta_calendar 均值变化 {deltas['eta_calendar']:+.4f}%，eta_flow {deltas['eta_flow']:+.4f}%（正数变慢，负数变快）。")
        release_key = "full_population_segment_elapsed_from_actual_release_seconds"
        times = [select(mode, False)[release_key]["mean"] for mode in ("legacy", "eta_calendar", "eta_flow")]
        lines.append(f"  同 Java 释放的实际释放→完成均值：legacy {times[0]:.6f} 秒、calendar {times[1]:.6f} 秒、flow {times[2]:.6f} 秒。")
        java = next(a["summary"]["metrics"] for a in arms if "binary" not in a["manifest"])
        java_mean = java[release_key]["mean"]
        lines.append(f"  calendar 相对 Java 的 {java_mean:.6f} 秒低 {100 * (java_mean-times[1])/java_mean:.4f}%；相对同释放旧 G31 仅低 {100 * (times[0]-times[1])/times[0]:.5f}%。算法和执行边界差异仍保留，不能把全部优势归因于此次评分。")
    if min(directions) < 0 < max(directions):
        lines += ["", "**两图原释放下的纯日历候选收益方向不一致。** 南宁的改善没有在 map2 原释放工况中复现；默认继续保留 legacy，不按单张图或单一均值升级候选。"]
    lines += ["", "各图需分别判断收益、尾部和误差，不把南宁结论移植为 map2 结论。出现 EBS 因果异常时，业务端到端数字仅是观察值；主要结论使用完整独立运输段分母。", "",
              "## 原路径报告与审计", ""]
    for campaign, _, _ in campaign_data:
        prefix = "../../" + campaign.directory
        lines += [f"- {campaign.name}：[报告]({prefix}/REPORT.md)、[七臂比较]({prefix}/final_audit_001/audit.json)、[请求差异]({prefix}/request_audit_001/audit.json)、[报告数据]({prefix}/{campaign.report_data}/report_data.json)。"]
    map2_prefix = "../../outputs/experiments/g31_feng_alignment_map2_20261023"
    lines += ["", f"最终 Python 回归为同一组五个文件 33 项通过：[最终回执]({map2_prefix}/python_regressions_002.xml)。首次回执中的两个失败来自 sandbox 临时目录的 `os.replace` WinError 5；将 basetemp 改为工作区后原样重跑通过，没有为通过测试修改代码。首次回执也保留供核查，不能把该环境失败混入算法实验结果。"]
    lines += ["", "## 包含的证据与明确缺项", "",
              "每图一个 ZIP，内部保留仓库相对路径：七臂完整 segments/business 账本、六个 G31 请求、canonical、地图和任务源、Java release/lifecycle/output/starttime/routes/run_status，以及公开的 summary/manifest/audit。Java 自身没有 G31 request.json.gz，原始命令由 run_status 等记录。",
              "map2 ZIP 另含 15 个原 Java 源文件的精确字节快照及两份外部原地图/任务输入。外部输入在 ZIP 中声明为虚拟 repo-relative source/original_inputs 路径，未覆盖仓库镜像；换行差异保留在原 source manifest。",
              "仅 nanning ZIP 包含一份两图共用的原生 Windows CPython 3.11 模块。完整 native_payload.json.gz 未打包：每份的 SHA256、字节数和明确未包含状态列在 PUBLICATION_MANIFEST.json。没有伪称归档包含完整原生大 JSON、完整事件带或全部历史构建树；原有回归回执可供审阅，但重新逐字段对照历史 native payload 需要原文件。",
              "当前源码由基线提交加本次明确列出的修改重建；每次运行的原始 source/binary hash 保留在 manifest。少量运行时 harness 快照随 ZIP 保留，以解释后续通用脚本新增 map2 参数支持造成的哈希变化。本地论文 PDF 原文未加入公开包。", ""]
    for archive in archives:
        lines.append(f"- [{archive['map']} 全量证据]({Path(archive['path']).name})：{archive['bytes'] / 1024 / 1024:.2f} MiB，{len(archive['entries'])} 个文件。")
    lines += ["", "## 校验与发布文件清单", "",
              "从仓库根目录运行（无需解压、无需外部原路径、不会启动模拟器）：", "", "```text",
              "python scripts/experiments/g31_feng_alignment/build_review_bundle.py verify", "```", "",
              "verify 校验所有显式发布文件的 SHA256/字节数、ZIP 完整成员集合与每个成员哈希，并直接读取 ZIP 全量 canonical+segments 重算两图各七臂指标和业务账本，对照公开 summary。",
              "[PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json) 的 publication_paths 是本次允许发布的逐文件清单，不能用全目录 git add 替代。为避免循环哈希，manifest 自身单列而不对自身计算内嵌最终 SHA；其余发布文件均有 SHA/大小。Git 提交自身提供完整内容身份。",
              "ZIP 保留原始字节，若检出环境改变公开源码的换行，严格哈希可能失败；需按清单恢复本次发布字节后再复核。", ""]
    return "\n".join(lines)


def render_prompt():
    return """# GPTPro 审阅入口

请审阅本分支相对 `9f23c25a631786ad4c1f47c442d72dcfb3ac098f` 的增量，实现和证据以仓库为准。先读 [README](README.md)，再读 [详细审阅清单](../../docs/g31_ics_circulation/PRO_REVIEW_CHECKLIST_20261023.md)、[候选实现](../../docs/g31_ics_circulation/S4_WAIT_ESTIMATOR_CANDIDATE_20261023.md) 和 [原生规则审计](../../docs/g31_ics_circulation/FENG_NATIVE_WAITING_RULES_AUDIT_20261023.md)。

任务范围：保留成熟 G31/S4/J2/PIBT，双方不增加线路容量，不跑空托盘；默认仍是 legacy，仅把 eta_calendar/eta_flow 作为可关闭评分候选。旧 G31 原已按到达 ETA 查询日历，正式邻居日历可见性也原已开启，不要把这两点当作本轮新增。

请独立检查以下问题，并以具体文件/代码/证据支持结论：

1. 新模式是否只改变评分，真实节点服务、恒速旅行、J2 授权和 PIBT 回滚是否保持？legacy 关闭等价、六组新回归及 checkpoint 状态覆盖是否充分？
2. Q 是服务后队列，预测是否分离日历等待和后服务等待、避免重复 Q+I？流量样本是否因果、是否遗漏临近 ETA 才完成的流入、是否出现较大尾部误差？已提交访问的 MAE/RMSE 不代表所有候选分数校准。
3. 每图主分母是否完整 43,603 段，Java generator release 是否与成功规划时刻分开？相同释放对照是否只改 release、保留身份/OD/截止时间/执行选项？
4. map2 与南宁分别是否仍优于原 Java，候选相对旧 S4 的收益或退化有多少？请同时看均值、尾部、超期和计算边界，不把不同计时范围的墙钟当 CPU 加速比。
5. 两图需求来自同一原始任务的投影，参数没有按 map2 调整；请按地图分别判定迁移表现，不推断独立客流采样意义或普遍最优。
6. Java 闭区间/G31 容差半开、Java 秒级报告/G31 连续事件、完整路线/逐跳策略等差异仍保留。EBS 因果异常没有被单方修正；不要把违规链的观察端到端值称为物理有效业务链。

可以运行 `python scripts/experiments/g31_feng_alignment/build_review_bundle.py verify` 从两份 ZIP 的全量账本重新计算各七臂指标。完整 native_payload 大文件未提供，只有 SHA/大小和明确缺项清单；不能声称已检查未提供的事件或全部原生细节。本地论文 PDF 仅有原件核验记录，没有包含原文。

请输出：可确认事实；具体代码或比较口径问题（按重要程度）；每图候选取舍；下一步最小实验。不需要为本轮重建托盘几何/驱动系统，不要自动启用新默认或将发布理解为已合并。
"""


def verify(root, manifest_path=MANIFEST):
    manifest = read_json(checked_path(root, manifest_path))
    if manifest["base_commit"] != BASE_COMMIT:
        raise ValueError("unexpected review base")
    files = manifest["publication_files"]
    paths = [entry["path"] for entry in files]
    if len(paths) != len(set(paths)) or set(manifest["publication_paths"]) != set(paths) | {manifest_path}:
        raise ValueError("publication list is not exact and unique")
    for expected in files:
        if file_evidence(root, expected["path"]) != expected:
            raise ValueError(f"published file hash/size mismatch: {expected['path']}")
    campaigns = {value["map"]: value for value in manifest["campaigns"]}
    results = [verify_archive(root, archive, campaigns[archive["map"]]) for archive in manifest["archives"]]
    if set(campaigns) != {"map2", "nanning"} or len(results) != 2:
        raise ValueError("both separate maps must be included exactly once")
    for result in results:
        if len(result["arms"]) != 7:
            raise ValueError("each map needs seven independently verified arms")
    return {"all_passed": True, "publication_files_checked": len(files),
            "manifest_self_hash_excluded": True, "maps": results,
            "simulator_executed": False, "native_payload_required": False}


def build(root):
    output = checked_path(root, OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    if checked_path(root, MANIFEST).exists():
        raise FileExistsError("a published manifest already exists; do not silently rebuild frozen evidence")
    publication = set(SOURCE_FILES)
    archives, omissions, campaign_records, campaign_data = [], [], [], []
    expected_binary_sha = None
    for campaign in CAMPAIGNS:
        print(f"prepare {campaign.name}: frozen seven-arm evidence", flush=True)
        report, arms = load_campaign(root, campaign)
        metadata = public_metadata(root, campaign, arms)
        publication.update(metadata)
        native_sha = next(a["manifest"]["binary"]["sha256"] for a in arms if "binary" in a["manifest"])
        if expected_binary_sha and native_sha != expected_binary_sha:
            raise ValueError("the two maps did not use the same native binary")
        expected_binary_sha = native_sha
        entries, omitted = campaign_entries(root, campaign, arms, metadata, campaign.name == "nanning")
        archive = make_archive(root, campaign, entries)
        print(f"packed {campaign.name}: {archive['bytes']} bytes, {len(archive['entries'])} entries", flush=True)
        archives.append(archive)
        omissions.extend({"map": campaign.name, **entry} for entry in omitted)
        publication.add(archive["path"])
        campaign_records.append({"map": campaign.name, "canonical": campaign.canonical,
                                 "report_data": report_path(campaign), "horizon": 98259.0,
                                 "arms": [{"label": a["label"], "directory": a["directory"]} for a in arms]})
        campaign_data.append((campaign, report, arms))
    for name, text in (("README.md", render_readme(root, campaign_data, archives)),
                       ("REVIEW_PROMPT.md", render_prompt())):
        checked_path(root, OUTPUT + "/" + name).write_text(text, encoding="utf-8", newline="\n")
        publication.add(OUTPUT + "/" + name)
    results = [verify_archive(root, a, c) for a, c in zip(archives, campaign_records)]
    verification_path = OUTPUT + "/VERIFICATION.json"
    write_json(checked_path(root, verification_path), {
        "all_passed": True, "simulator_executed": False, "maps": results,
        "scope": "ZIP byte integrity, full per-segment metrics and business-ledger recomputation",
        "note": "Native internal summary counters and omitted native payloads are not reconstructed from lifecycle rows."})
    publication.add(verification_path)
    files = [file_evidence(root, path) for path in sorted(publication)]
    manifest = {"schema": "g31.waiting.two_maps.publication.v1", "base_commit": BASE_COMMIT,
                "created_utc": datetime.now(timezone.utc).isoformat(), "manifest_path": MANIFEST,
                "manifest_self_hash_policy": "self excluded to avoid circular hashing; publication_paths includes its path",
                "publication_paths": sorted(publication | {MANIFEST}), "publication_files": files,
                "archives": archives, "campaigns": campaign_records,
                "omitted_native_payloads": omissions,
                "scope": "two fixed-parameter maps; same underlying 1x workload; legacy remains default; no empty trays or added capacity",
                "source_reconstruction": "base commit plus explicit published source changes; exact original Java snapshots in map2 ZIP",
                "binary_sha256_shared_across_maps": expected_binary_sha}
    write_json(checked_path(root, MANIFEST), manifest)
    print(json.dumps(verify(root), ensure_ascii=False, indent=2))


def plan(root):
    required = set(SOURCE_FILES)
    campaigns = []
    for campaign in CAMPAIGNS:
        path = checked_path(root, report_path(campaign))
        value = {"map": campaign.name, "report_data": report_path(campaign), "report_ready": path.is_file()}
        if path.is_file():
            _, arms = load_campaign(root, campaign)
            value["arms"] = [{"label": a["label"], "directory": a["directory"]} for a in arms]
        campaigns.append(value)
        required.update((campaign.canonical, campaign.directory + "/REPORT.md", report_path(campaign)))
    print(json.dumps({"base_commit": BASE_COMMIT, "output": OUTPUT, "maps": campaigns,
                      "missing_prerequisites": sorted(p for p in required if not checked_path(root, p).is_file()),
                      "archives_created": False, "simulator_executed": False}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "build", "verify"))
    parser.add_argument("--repo-root", type=Path, default=ROOT,
                        help="review checkout root; verify never needs the original author's absolute paths")
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    if args.command == "plan":
        plan(root)
    elif args.command == "build":
        build(root)
    else:
        print(json.dumps(verify(root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
