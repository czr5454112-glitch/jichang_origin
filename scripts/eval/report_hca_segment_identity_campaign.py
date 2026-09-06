"""Report the new HCA execution-identity campaign without running a simulator.

Final output requires the complete 180-cell matrix and verification of the exact
archive manifest. Historical HCA accounting notes are a separate diagnostic;
their labels never qualify or disqualify the new HCA observations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import report_feng_dh_v5_campaign as common

METHODS = ("G31_S4_NATIVE_SYSTEM", "FENG_DH_BOUNDARY_CLEARANCE_V5", "HCA_SEGMENT_IDENTITY_V1")
SHORT = dict(zip(METHODS, ("G31", "V5 DH", "新 HCA")))
NAMES = dict(zip(METHODS, ("G31（复用）", "V5 DH（复用）", "HCA 段身份修复版（新跑）")))
STATS = ("min", "mean", "max")
METRICS = tuple(f"tht_scheduled_release_{s}_seconds" for s in STATS) + ("completed_raw_bag_count",)
SOURCE_SHA, CLASS_SHA = common.SOURCE_SHA, common.CLASS_SHA
TABLE_ROOT = ROOT / "outputs/tables"
EVIDENCE = ROOT / "outputs/evidence/hca_segment_identity_20260906"
OUTPUT = ROOT / "outputs/reports/hca_segment_identity_full_campaign_20260906.md"
OLD_CELLS = TABLE_ROOT / "feng_dh_v5_cells_20260905.csv"
CONTROL_NOTES = common.CONTROL_NOTES
TIMING_DIAGNOSTIC = ROOT / "outputs/runtime/hca_segment_identity_20260906/diagnostics/nanning_1p00x_seed_155921_release_delay.json"
CONTROL_NOTES_SHA = "2b405d184ad8748169caf98ddc3db18737634f50785628c64fe12832568e3d7c"
OLD_MANIFEST_SHA = "133808d1c2fb94149f2ec5e717d14f7384faea957ab3386deedabfef5c8f8f40"
require, sha, number, boolean = common.require, common.sha, common.number, common.boolean
read_json, read_csv, close, fmt, link = common.read_json, common.read_csv, common.close, common.fmt, common.link
completion_group, improvement_percent, comparison_cells = common.completion_group, common.improvement_percent, common.comparison_cells
key, pair_key = common.key, common.pair_key


def expected_keys() -> set:
    return {(m, l, s, a) for m in external.MAPS for l in external.LOAD_FACTORS for s in external.SEEDS for a in METHODS}


def validate_cells(rows: list[dict], *, allow_partial: bool = False) -> dict:
    indexed, paired_identities = {}, {}
    hca_builds = set()
    for row in rows:
        coordinate = key(row)
        require(coordinate in expected_keys() and coordinate not in indexed, "unfrozen or duplicate method cell")
        map_name, load, seed, method = coordinate
        require(float(row["fixed_horizon_seconds"]) == external.FIXED_HORIZON_SECONDS, "horizon differs")
        require(row["TH_definition"] == "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259", "TH definition differs")
        require(row["primary_timing_definition"] == "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE"
                and not boolean(row["historical_shared_D"]), "common canonical D contract differs")
        raw, completed = int(row["raw_bag_count"]), number(row["completed_raw_bag_count"])
        require(raw == external.EXPECTED_POPULATIONS[load][0] and completed is not None and completed.is_integer()
                and 0 <= completed <= raw, "invalid full population denominator")
        close(row["TH_completed_raw_bags"], completed, "TH columns differ")
        close(row["completion_rate"], completed/raw, "completion rate denominator differs")
        close(row["unfinished_raw_bag_count"], raw-completed, "unfinished population differs")
        complete = boolean(row["full_population_complete"])
        require(complete == (completed == raw), "population completion flag differs")
        timing = [number(row[f"tht_scheduled_release_{s}_seconds"]) for s in STATS]
        require((load != 2 and complete) or all(v is None for v in timing), "forbidden 2x/incomplete THT")
        require(all(v is None for v in timing) or all(v is not None for v in timing), "partially missing formal timing")
        if timing[0] is not None:
            require(row["formal_timing_status"] == "FULL_POPULATION_RAW_BAG_TIMING"
                    and 0 <= timing[0] <= timing[1] <= timing[2], "invalid formal THT")
        if method == METHODS[1]:
            require(row["source_sha256"] == SOURCE_SHA and row["class_sha256"] == CLASS_SHA, "V5 implementation differs")
        if method == METHODS[2]:
            source, classes = row["source_sha256"], row["class_sha256"]
            require(all(len(value) == 64 and all(c in '0123456789abcdef' for c in value) for value in (source, classes)),
                    "new HCA requires source/class SHA identity")
            hca_builds.add((source, classes))
        identity_key, identity = (map_name, load, seed), row["workload_identity_sha256"]
        require(identity and (identity_key not in paired_identities or paired_identities[identity_key] == identity), "unpaired workloads")
        paired_identities[identity_key] = identity
        indexed[coordinate] = row
    require(bool(indexed), "empty matrix")
    require(allow_partial or set(indexed) == expected_keys(), "final report requires all 180 frozen cells")
    require(len(hca_builds) <= 1, "mixed HCA builds in one campaign")
    return indexed


def validate_reused_controls(indexed: dict, old_rows: list[dict]) -> None:
    """Do not silently replace, relabel or recompute the 120 archived controls."""
    old = {key(row): row for row in old_rows}
    for coordinate, row in indexed.items():
        if coordinate[3] in METHODS[:2]:
            require(coordinate in old, "missing original G31/V5 control")
            previous = old[coordinate]
            require(all(row.get(k) == v for k, v in previous.items())
                    and all(v in ("", None) for k, v in row.items() if k not in previous), "reused G31/V5 CSV row changed")


def validate_manifest(manifest: dict, verification: dict, manifest_path: Path, indexed: dict) -> None:
    require(manifest.get("status") == "COMPLETE" and len(manifest.get("cells", [])) == 180,
            "final report requires complete 180-cell archive")
    require(manifest.get("new_hca_cells") == 60 and manifest.get("reused_control_cells") == 120
            and manifest.get("source_prior_manifest_sha256") == OLD_MANIFEST_SHA, "new/reused archive contract differs")
    require(not manifest.get("failures") and not manifest.get("missing_cells"), "archive has missing/failed cells")
    archived = {key(c): c for c in manifest["cells"]}
    require(len(archived) == 180 and set(archived) == expected_keys() == set(indexed), "archive cell identities differ")
    require(verification.get("status") == "PASS" and verification.get("campaign_manifest_sha256") == sha(manifest_path),
            "archive verification is absent or stale")
    require(verification.get("new_hca_cells_recomputed") == 60 and verification.get("reused_control_cells_verified") == 120,
            "archive verification coverage differs")
    for field in ("observed_cells", "expected_cells"):
        if field in manifest:
            require(manifest[field] == 180, "archive cell count differs")
    for field in ("observed_cells", "checked_cells"):
        if field in verification:
            require(verification[field] == 180, "verification cell count differs")
    for coordinate, row in indexed.items():
        origin = "NEW_EXECUTION" if coordinate[3] == METHODS[2] else "REUSED_PREVIOUS_FROZEN_ARCHIVE"
        require(archived[coordinate]["origin"] == origin, "archive method origin differs")
        if coordinate[3] == METHODS[2]:
            require(row["source_sha256"] == manifest["source_sha256"] and row["class_sha256"] == manifest["class_sha256"],
                    "new HCA differs from archived frozen build")
        bound = archived[coordinate]["table_row"]
        serialized = {k: "" if bound.get(k) is None else str(bound[k]) for k in row}
        require(set(bound) <= set(row) and serialized == row, "table differs from manifest-bound row")
        for field in ("completed_raw_bag_count", "completion_rate", "unfinished_raw_bag_count", *METRICS[:3]):
            close(row[field], archived[coordinate]["exported_metrics"][field], f"table/archive metric differs: {field}")


def validate_pairs(indexed: dict, paired: dict, pair_rows: list[dict]) -> dict:
    require(paired["status"] == "COMPLETE" and paired["expected_cells"] == paired["observed_cells"] == 180,
            "paired comparison is incomplete")
    require(paired["bootstrap_replicates"] == 10000 and paired["confidence_level"] == .95
            and paired["bootstrap_unit"] == "MATCHED_WORKLOAD_SEED_NOT_INDIVIDUAL_BAG"
            and paired["partial_seed_estimates_suppressed"], "paired bootstrap contract differs")
    pairs, from_json = {pair_key(r): r for r in pair_rows}, {pair_key(r): r for r in paired["rows"]}
    require(len(pairs) == len(pair_rows) and len(from_json) == len(paired["rows"]) and set(pairs) == set(from_json),
            "paired CSV/JSON coordinates differ")
    for coordinate, pair in pairs.items():
        reference = from_json[coordinate]
        require(pair["status"] == reference["status"], "paired CSV/JSON status differs")
        for field in ("paired_seed_count", "missing_seed_count", "baseline_mean", "reference_mean",
                      "mean_delta_reference_minus_baseline", "bootstrap_ci_low", "bootstrap_ci_high",
                      "reference_win_count", "tie_count", "reference_loss_count"):
            close(pair.get(field), reference.get(field), "paired CSV/JSON statistic differs")
    for m in external.MAPS:
        for load in external.LOAD_FACTORS:
            for baseline in METHODS[1:]:
                for metric in METRICS:
                    coordinate = m, load, baseline, METHODS[0], metric
                    require(coordinate in pairs, "main paired comparison missing")
                    pair = pairs[coordinate]
                    values = [(number(indexed[m, load, seed, baseline][metric]),
                               number(indexed[m, load, seed, METHODS[0]][metric])) for seed in external.SEEDS]
                    if metric != "completed_raw_bag_count" and load == 2:
                        require(pair["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL", "paired 2x THT leaked")
                    elif any(a is None or b is None for a, b in values):
                        require(pair["status"] == "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE", "paired survivor/subset estimate")
                    else:
                        require(pair["status"] == "COMPLETE" and int(pair["paired_seed_count"]) == 10, "ten-seed comparison missing")
                        differences = [b-a for a, b in values]
                        close(pair["baseline_mean"], statistics.fmean(a for a, _ in values), "paired baseline mean differs")
                        close(pair["reference_mean"], statistics.fmean(b for _, b in values), "paired reference mean differs")
                        close(pair["mean_delta_reference_minus_baseline"], statistics.fmean(differences), "paired delta differs")
                        oriented = differences if metric == "completed_raw_bag_count" else [-v for v in differences]
                        require(tuple(int(pair[f]) for f in ("reference_win_count", "tie_count", "reference_loss_count")) ==
                                (sum(v > 1e-12 for v in oriented), sum(abs(v) <= 1e-12 for v in oriented), sum(v < -1e-12 for v in oriented)),
                                "paired win/tie/loss differs")
    return pairs


def headline_pairs(pairs: dict, metric: str) -> list[dict]:
    """Historical HCA flags do not apply to this separately identified method."""
    return [p for p in pairs.values() if p["reference"] == METHODS[0] and p["baseline"] in METHODS[1:]
            and p["metric"] == metric and p["status"] == "COMPLETE"]


def load_timing_diagnostic(path: Path) -> dict | None:
    if not path.exists():
        return None
    value = read_json(path)
    scope = value["scope"]
    require(value["schema"] == "czr005.hca_segment_identity_release_delay_diagnostic.v1" and value["status"] == "PASS"
            and (scope["map"], scope["load_factor"], scope["seed"]) == ("nanning", 1.0, 155921)
            and scope["single_cell_only"] and scope["not_a_sixty_cell_or_ten_seed_conclusion"], "timing diagnostic scope differs")
    common = value["common_completed_cohort_diagnostic"]
    require(common["difference_count"] == 0 and not common["formal_timing_eligible"]
            and common["old_ordered_timing_sha256"] == common["new_ordered_timing_sha256"], "single-cell timing diagnostic differs")
    for field in ("scheduled_pass_time", "release_epoch", "processed_attempt_epoch"):
        require(value["segment_comparison"][field]["difference_count"] == 0, "diagnostic clock identity differs")
    return value


def load_final(args: argparse.Namespace) -> tuple:
    paths = {"cells": args.table_root / "hca_segment_identity_cells_20260906.csv",
             "paired_csv": args.table_root / "hca_segment_identity_paired_20260906.csv",
             "paired_json": args.table_root / "hca_segment_identity_paired_20260906.json",
             "manifest": args.evidence_root / "campaign_manifest.json",
             "verification": args.evidence_root / "archive_verification.json",
             "old_cells": args.old_cells, "historical_accounting_notes": args.control_notes}
    timing_path = getattr(args, "timing_diagnostic", TIMING_DIAGNOSTIC)
    if timing_path.exists():
        load_timing_diagnostic(timing_path)
        paths["single_cell_timing_diagnostic"] = timing_path
    hashes = {name: sha(path) for name, path in paths.items()}
    require(hashes["historical_accounting_notes"] == CONTROL_NOTES_SHA, "historical HCA notes changed")
    rows = read_csv(paths["cells"])
    indexed = validate_cells(rows)
    old_rows = read_csv(paths["old_cells"])
    validate_reused_controls(indexed, old_rows)
    manifest, verification = read_json(paths["manifest"]), read_json(paths["verification"])
    validate_manifest(manifest, verification, paths["manifest"], indexed)
    bound_tables = {Path(t["path"]).name: t["sha256"] for t in manifest["tables"]}
    for name in ("cells", "paired_csv", "paired_json"):
        require(bound_tables.get(paths[name].name) == hashes[name], "table SHA differs from verified archive manifest")
    pairs = validate_pairs(indexed, read_json(paths["paired_json"]), read_csv(paths["paired_csv"]))
    notes = common.load_control_notes(args.control_notes)
    require(notes["affected_cell_count"] == 43 and notes["audited_cell_count"] == 60, "historical accounting scope differs")
    require(all(sha(p) == hashes[n] for n, p in paths.items()), "input changed during report validation")
    return rows, pairs, manifest, verification, old_rows, notes, paths, hashes


def group(rows: list[dict], map_name: str, load: float, method: str) -> dict:
    return completion_group([r for r in rows if r["map"] == map_name and float(r["load_factor"]) == load and r["method"] == method], load=load)


def native_timing_group(rows: list[dict], map_name: str, load: float, method: str) -> dict:
    """Display the existing native clock under the same ten-seed timing rules.

    Copy the fields into the shared qualification helper; never mutate the
    primary table or infer missing native measurements from scheduled D.
    """
    selected = [dict(r, **{f"tht_scheduled_release_{s}_seconds": r.get(f"tht_admission_{s}_seconds")
                          for s in STATS})
                for r in rows if r["map"] == map_name and float(r["load_factor"]) == load and r["method"] == method]
    return completion_group(selected, load=load)


def native_headline(rows: list[dict]) -> str:
    """Make the other clock's favorable and adverse directions equally visible."""
    comparisons = {}
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            g31 = native_timing_group(rows, map_name, load, METHODS[0])
            for baseline in METHODS[1:]:
                control = native_timing_group(rows, map_name, load, baseline)
                if all(g["THT"][s] is not None for g in (g31, control) for s in ("mean", "max")):
                    comparisons[map_name, load, baseline] = g31["THT"], control["THT"]
    sentences = []
    for stat, label in (("mean", "均值"), ("max", "最大值")):
        delta = [g[stat]-c[stat] for g, c in comparisons.values()]
        sentences.append(f"原生起点 THT {label}在 {len(delta)} 个完整十种子条件中，G31 种子统计量均值更低 {sum(v < -1e-12 for v in delta)}、持平 {sum(abs(v) <= 1e-12 for v in delta)}、更高 {sum(v > 1e-12 for v in delta)} 个。")
    # Fixed illustrative condition, selected independently of its ranking.
    representative = comparisons.get(("map2", 1.75, METHODS[2]))
    if representative is not None:
        g31, hca = representative
        sentences.append(f"以 map2 1.75× 为例，G31 / 新 HCA 的原生起点 THT mean 为 {fmt(g31['mean'])} / {fmt(hca['mean'])} 秒，THT max 为 {fmt(g31['max'])} / {fmt(hca['max'])} 秒（均为十种子统计量的均值）。")
    return "**另一计时口径的方向。** " + " ".join(sentences) + " G31/V5/HCA 的这些起点事件不同，排除的等待阶段也不同；共同 D 与原生起点须并列解释，不能据任一列认定同一物理 THT 的全面优劣。"


def render_report(args: argparse.Namespace, rows: list[dict], pairs: dict, manifest: dict,
                  verification: dict, old_rows: list[dict], notes: dict, *, synthetic_qa: bool = False) -> str:
    output = args.output
    full_counts = {m: sum(boolean(r["full_population_complete"]) for r in rows if r["method"] == m) for m in METHODS}
    terminal = Counter(r["native_terminal_status"] for r in rows if r["method"] == METHODS[2])
    headline = []
    for metric, label, direction in ((METRICS[1], "共同 D 平均 THT", -1), (METRICS[3], "TH 完成量", 1)):
        values = [direction*number(p["mean_delta_reference_minus_baseline"]) for p in headline_pairs(pairs, metric)]
        headline.append(f"{label}具备十种子比较资格的 {len(values)} 个地图/负载/对照条件中，G31 种子均值方向更优 {sum(v > 1e-12 for v in values)}、持平 {sum(abs(v) <= 1e-12 for v in values)}、更差 {sum(v < -1e-12 for v in values)} 个。")
    title = "# HCA 段身份修复后的两地图、三负载、十种子实验"
    if synthetic_qa:
        title = "# SYNTHETIC QA — NOT EXPERIMENT RESULTS\n\n" + title
    text = [title, "",
        "**180/180 方法格档案完整：60 格新 HCA 执行，复用已冻结的 G31、V5 各 60 格。** 新 HCA 使用 `HCA_SEGMENT_IDENTITY_V1`；全部旧 HCA 观测退出本次主矩阵并保留为历史诊断。档案完整、段身份账目通过和全人口完成是不同概念。" if not synthetic_qa else
        "**仅作合成数据布局与口径测试，以下数字不属于真实实验，不能用作结果或通过证明。**",
        f"新 HCA 原生终态：{'；'.join(f'{k} {v}' for k, v in sorted(terminal.items()))}；全人口完成 {full_counts[METHODS[2]]}/60 格。G31、V5 全人口完成分别为 {full_counts[METHODS[0]]}/60、{full_counts[METHODS[1]]}/60 格。未完成人口仍保留。", "",
        " ".join(headline) + " 这是各条件点估计的方向计数，不能读成全部指标胜利、显著性计数或每小时容量结论。逐种子胜/平/负及不利结果见配对表。", "",
        native_headline(rows), "",
        "**修复范围。** 两个 EBS 段在进入旧 HCA 前取得独立执行编号，使活动路径、节点预约、推进和完成均按段关联；不是给旧日志补袋。路由代价、预约公式、源端释放及原 epoch 循环保持。新增编号与未被覆盖的预约可能改变 HashMap 遍历和实际轨迹，这是单独标识的修复版本，不能称与旧结果逐字相同。",
        "三方法继续采用共同 canonical 的独立 scheduled EBS 段，没有仅对 HCA 加入“入库完成后才出库”的新等待。该模型允许同袋两段重叠，不代表真实 EBS 物理先后依赖已验证。" +
        link(output, ROOT / "docs/baselines/hca_segment_identity_repair_semantics_20260906.md", "共同合同与独立语义审查") + "；" +
        link(output, ROOT / "docs/baselines/hca_segment_identity_campaign_protocol_20260906.md", "本次冻结协议") + "。", "",
        "**统一口径。** 两地图均使用负载 1×、1.75×、2×及相同十个种子：" + "、".join(map(str, external.SEEDS)) + "。各负载每种子的原始袋数为 " +
        "、".join(f"{external.EXPECTED_POPULATIONS[l][0]:,}" for l in external.LOAD_FACTORS) + "，段数按每格实际 raw 展开。共同绝对末 epoch 为 98,259 秒。TH 是该时点前全部业务段完成的原始袋数，不是每小时峰值容量。",
        "本实验冻结协议的主 THT 是每袋 Σ（段完成时刻−共同 canonical scheduled D）。先在种子内完整袋人口上求 min/mean/max，再对十个种子统计量取均值，不能混同十次袋人口合并后的统计。共同 D 列和下方原生起点列均遵守同一资格：2× THT 一律 N/A；其他负载只要该方法组有一个种子人口未全完或缺时间证据，整组 THT 为 N/A，不取幸存者或可用种子子集。",
        "**论文指标与本实验计时的区别。** Feng CIE 一审修订稿第 24 页 §5.2 将 THT 称为 baggage throughput time，TH 为给定 T 内的处理袋数；第 26 页对全部袋统计 min/mean/max。第 14 页把任务的 t_k 定义为 entering time，学位论文正文段 123、218、227 对应上述描述。但这些文字没有给出可把 canonical scheduled D、实际 release 或成功 planning 日志唯一映射到原文 t_k 的证据，也没有明确本实验的 EBS 两段求和实现。本报告采用论文指标名称及本实验明确的操作定义，不宣称复现论文原始计时起点；共同 D 的优势不能冒称 Feng 原论文 exact-THT 优势。" +
        link(output, ROOT / "docs/baselines/hca_segment_identity_paper_metric_clock_audit_20260906.md", "原文定位、源身份与计时边界") + "。",
        "各执行器原生 release/admission/processed 并非已证明相同的物理事件。HCA 原生整数规则可以使 release 比分数 D 早不足一秒，源端释放与排队又可能使其晚很多；共同 D 主列包括这些偏移。HCA 成功 planning 后计时排除了此前等待，不能自动视为论文 entering time。原始未抖动 shared-D 另见旧独立报告，不混入这次随机矩阵。", "",
        "**主结果：共同 scheduled D。** TH 方括号为十种子的最小—最大；完成率为十种子均值。THT 单位为秒。"]
    for map_name in external.MAPS:
        text += ["", f"**{'Map2' if map_name == 'map2' else '南宁'}**", "",
            "| 负载 | 方法 | TH 均值 [种子范围] | 完成率 | 全完种子 | THT(D) min | THT(D) mean | THT(D) max |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                g = group(rows, map_name, load, method)
                timings = [fmt(g["THT"][s]) if g["THT"][s] is not None else f"N/A（{g['THT_status']}）" for s in STATS]
                text.append("| " + " | ".join([f"{load:g}×", NAMES[method], f"{fmt(g['TH_mean'],1)} [{fmt(g['TH_min'],0)}–{fmt(g['TH_max'],0)}]",
                    f"{g['completion_rate_mean']*100:.4f}%", f"{g['complete_seeds']}/10", *timings]) + " |")
    text += ["", "**另一计时口径：各执行器原生 admission/processed 起点。** 下表直接使用已导出的 `tht_admission_*`，对每袋求 Σ（段完成−该段原生起点），再按与主表相同的完整十种子规则汇总，单位为秒。G31 为 `processed_attempt`（对应 `admitted_time`）；V5 为 `first_admission`；新 HCA 为成功 planning 的 `processed_attempt_epoch`。它们均排除各自起点之前的时间，但不能据名称相近就称同一物理入网时刻，也不能自动称论文 exact-THT。两表覆盖的计时阶段不同，应分别判断各列的优势与代价。", "",
             "| 地图 | 负载 | 方法 | 原生起点 | THT(native) min | THT(native) mean | THT(native) max |",
             "|---|---|---|---|---:|---:|---:|"]
    native_clocks = dict(zip(METHODS, ("processed_attempt / admitted_time", "first_admission", "成功 planning / processed_attempt_epoch")))
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                g = native_timing_group(rows, map_name, load, method)
                timings = [fmt(g["THT"][s]) if g["THT"][s] is not None else f"N/A（{g['THT_status']}）" for s in STATS]
                text.append("| " + " | ".join([map_name, f"{load:g}×", SHORT[method], native_clocks[method], *timings]) + " |")
    text += ["", "**G31 配对比较：共同 D THT 与固定时域 TH。** 改善率正为 G31 更优，负为更差；THT 用（对照均值−G31 均值）/对照均值，TH 用（G31 均值−对照均值）/对照均值，均为种子均值之比。差值及 95% 区间均为 G31−对照的原单位，不是百分比区间。区间采用匹配种子为单位的 10,000 次配对 bootstrap，未做多重比较校正；胜/平/负按各指标方向逐种子计算。"]
    for map_name in external.MAPS:
        text += ["", f"**{'Map2' if map_name == 'map2' else '南宁'}：配对差值**", "",
                 "| 负载 | 对照 | 指标 | G31 改善率 | G31−对照 | 95% 区间 | 胜/平/负 |",
                 "|---|---|---|---:|---:|---:|---:|"]
        for load in external.LOAD_FACTORS:
            for baseline in METHODS[1:]:
                for metric in METRICS:
                    label = "TH（袋）" if metric == METRICS[3] else "THT " + metric.split("_")[-2] + "（秒）"
                    p = pairs[map_name, load, baseline, METHODS[0], metric]
                    text.append("| " + " | ".join([f"{load:g}×", SHORT[baseline], label, *comparison_cells(p, metric=metric)]) + " |")
    text += ["", "准时率、未完成数、积压与其他尾部指标保留在" + link(output, args.table_root / "hca_segment_identity_cells_20260906.csv", "完整逐格表") + "与" +
             link(output, args.table_root / "hca_segment_identity_paired_20260906.csv", "全部配对统计") + "；不能因主表只列 THT/TH 而推断其他指标均占优。", "",
             "**旧 HCA 的处理与修复后观测。** 旧 60 格中的 43 格有正的段账目残差；其余 17 格仅为未检出该残差，不表示执行语义已充分验证。三个细查的南宁 1×种子出现同袋两次成功规划、一次 raw-ID completion 且末态无活动/待规划任务；旧构建身份未恢复，具体完成段归属仍有歧义，不能从旧日志补造完成事件。该附注仅指旧 `FENG_NATIVE_HCA`，不贴到本次新方法。" +
             link(output, args.control_notes, "原 43/60 科学附注与证据") + "。", "",
             "下表单列旧/新 HCA 的 TH 观测变化。旧值存在上述证据限制；差值不等于补回的丢失袋数，也不是纯路由策略效应，因为编号修复保留了真实预约并可能改变执行顺序。", "",
             "| 地图 | 负载 | 旧 HCA TH 均值 | 新 HCA TH 均值 | 新−旧 | 新 HCA 全完种子 |",
             "|---|---|---:|---:|---:|---:|"]
    for m in external.MAPS:
        for load in external.LOAD_FACTORS:
            old, new = group(old_rows, m, load, "FENG_NATIVE_HCA"), group(rows, m, load, METHODS[2])
            text.append(f"| {m} | {load:g}× | {fmt(old['TH_mean'],1)} | {fmt(new['TH_mean'],1)} | {new['TH_mean']-old['TH_mean']:+.1f} | {new['complete_seeds']}/10 |")
    timing_path = getattr(args, "timing_diagnostic", TIMING_DIAGNOSTIC)
    diagnostic = None if synthetic_qa else load_timing_diagnostic(timing_path)
    if diagnostic is not None:
        d = diagnostic["timing_decomposition_seconds"]["new"]
        shared = diagnostic["common_completed_cohort_diagnostic"]
        text += ["", f"**单格大时延的来源诊断。** 清理优化前的南宁 1× / seed 155921 对照预检中，共同 D 平均 THT 为 {d['scheduled_D_THT']['mean']:.6f} 秒，其中实际释放之前的偏移均值为 {d['native_release_minus_D']['mean']:.6f} 秒。新旧各段 D、release、成功 planning 全部相同，旧共同完成的 {shared['bags']:,} 袋 THT 逐袋完全一致；完整人口均值改变来自纳入原漏段袋，不能把旧成功规划后计时与新共同 D 计时相除并称修复造成性能崩坏。该旧完成子集仅用于诊断，不能恢复旧全人口资格；此结论也不能推广到其他 59 格。" +
            link(output, ROOT / "docs/baselines/hca_segment_identity_release_delay_diagnostic_20260906.md", "单格源端释放规则与计时分解") + "；" +
            link(output, timing_path, "原生事件独立重算证据") + "。"]
    text += ["", "**证据与解释边界。** 新 HCA 保存构建身份、段映射、实际释放、成功规划、完成事件及来自实际集合的四态终账；每袋仅在其全部段完成时计入 TH。每格段账目通过与完整压缩字节核验不等于所有连续时间预约、碰撞、FIFO 或物理 EBS 约束获得穷尽证明。",
        "原生微测试支持同袋两段同时调度、两次独立完成及普通单段日志等价；另以冻结生产类的真实 update_constrain/Contains 验证两个执行 ID 在共享节点的预约并存，更新一个不会删除另一个。后者检验预约存储隔离，不检验重叠区间的路线可行性或物理碰撞自由。" +
        link(output, ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight/microtests.json", "原生微测试") + "；" +
        link(output, ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight/reservation_audit.json", "共享节点预约身份补充验证") + "。",
        "G31/V5 的 120 个 CSV 控制行与先前最终表原样核对，工作负载与方法身份由证据清单绑定。G31 保留的原生聚合与档案审计不应被表述为恢复了当时未保存的完整逐事件轨迹；V5 保存完整袋/段结果。旧 HCA 的运行时 source/class 缺口仍属于旧档案，不能套用新 HCA 的构建哈希补填。",
        "V5 是用户看过原始 map2 结果后的明确事后选择，包含披露的 through/transfer/身体清空假设，不能称作者源码精确复现。相关 publisher 正式全文仍未取得，论文 DH 步骤与表格的细节核对仍以本地一审修订稿为边界。三方法使用各自执行器，本实验是共同任务与口径下的系统比较，不能把全部差异归因于单一路由规则。", "",
        "**墙钟诊断。** 新 HCA 与复用控制的运行日期、并发及执行环境不同；下表仅列记录值，不据此计算算法加速比。缺少完整十次记录时不取子集均值。", "",
        "| 地图 | 负载 | 方法 | 墙钟均值 [种子范围]，秒 | 有记录种子 |", "|---|---|---|---:|---:|"]
    for m in external.MAPS:
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                values = [number(r.get("wall_seconds")) for r in rows if r["map"] == m and float(r["load_factor"]) == load and r["method"] == method]
                available = [v for v in values if v is not None]
                display = f"{fmt(statistics.fmean(available))} [{fmt(min(available))}–{fmt(max(available))}]" if len(available) == 10 else "N/A（记录不足）"
                text.append(f"| {m} | {load:g}× | {SHORT[method]} | {display} | {len(available)}/10 |")
    text += ["", "**图与复现。** 大点是十种子统计量均值，浅点是各个种子，须线是种子范围而非置信区间；2×和未全完组的 THT 均显式 N/A。"]
    figures = ROOT / "outputs/figures/hca_segment_identity_20260906"
    for stem, label in (("hca_segment_identity_tht_min_mean_max_20260906", "THT min/mean/max"),
                        ("hca_segment_identity_fixed_horizon_th_20260906", "固定时域 TH")):
        text += ["", link(output, figures / (stem + ".png"), label + " PNG") + "；" + link(output, figures / (stem + ".pdf"), "PDF") + "。"]
    text += ["", link(output, args.evidence_root / "README.md", "压缩证据与独立复核入口") + "。最终 manifest SHA 与表、图、报告输入哈希见旁边 provenance JSON。", "",
        "从已导出表和证据重生成图与报告，不启动模拟：", "", "```powershell",
        "python scripts/eval/plot_hca_segment_identity_campaign.py",
        "python scripts/eval/report_hca_segment_identity_campaign.py", "```", ""]
    return "\n".join(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-root", type=Path, default=TABLE_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--old-cells", type=Path, default=OLD_CELLS)
    parser.add_argument("--control-notes", type=Path, default=CONTROL_NOTES)
    parser.add_argument("--timing-diagnostic", type=Path, default=TIMING_DIAGNOSTIC)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows, pairs, manifest, verification, old_rows, notes, paths, hashes = load_final(args)
    text = render_report(args, rows, pairs, manifest, verification, old_rows, notes)
    require(all(sha(p) == hashes[n] for n, p in paths.items()), "input changed while generating report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    builds = sorted({(r["source_sha256"], r["class_sha256"]) for r in rows if r["method"] == METHODS[2]})
    provenance = {"schema": "czr005.hca_segment_identity_chinese_report.v1", "status": "COMPLETE",
        "observed_cells": 180, "new_hca_cells": 60, "reused_g31_v5_cells": 120,
        "historical_hca_accounting_annotation_is_not_new_hca_annotation": True,
        "hca_source_class_sha256": builds, "script_sha256": sha(Path(__file__)),
        "format_helpers_sha256": sha(Path(common.__file__)),
        "inputs": {n: {"path": str(p.resolve()), "sha256": hashes[n]} for n, p in paths.items()},
        "report": {"path": str(args.output.resolve()), "sha256": sha(args.output)}}
    args.output.with_suffix(".provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "cells": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
