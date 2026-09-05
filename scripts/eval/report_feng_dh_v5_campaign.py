"""Generate the final Chinese V5 report from audited tables and archive metadata.

This module neither imports the plotting code nor executes a simulator. It
requires all 180 cells and an archive verification bound to that exact final
manifest. Native HORIZON_REACHED/DEADLOCK remain valid incomplete populations;
they never become eligible survivor-cohort THT measurements.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

METHODS = ("G31_S4_NATIVE_SYSTEM", "FENG_DH_BOUNDARY_CLEARANCE_V5", "FENG_NATIVE_HCA")
NAMES = dict(zip(METHODS, ("G31（档案控制）", "V5 DH（新跑重构）", "HCA（档案控制）")))
SHORT = dict(zip(METHODS, ("G31", "V5", "HCA")))
STATS = ("min", "mean", "max")
SOURCE_SHA = "7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7"
CLASS_SHA = "a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869"
TABLE_ROOT = ROOT / "outputs/tables"
EVIDENCE = ROOT / "outputs/evidence/feng_dh_boundary_clearance_v5_20260905"
OUTPUT = ROOT / "outputs/reports/feng_dh_v5_full_campaign_20260905.md"
HISTORICAL = ROOT / "outputs/runtime/feng_dh_v5_shared_D_20260905/comparison_and_audit.json"
CONTROL_NOTES = ROOT / "outputs/runtime/cie_external_baseline_boundary_clearance_v5/control_completion_notes.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: object) -> float | None:
    if value is None or str(value).strip() in {"", "N/A"}:
        return None
    result = float(value)
    require(math.isfinite(result), "non-finite report metric")
    return result


def boolean(value: object) -> bool:
    require(value in (True, False, "True", "False", "true", "false"), "invalid population-completion flag")
    return str(value).lower() == "true"


def close(left: object, right: object, label: str) -> None:
    a, b = number(left), number(right)
    require((a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 1e-6), label)


def key(row: dict) -> tuple:
    return row["map"], float(row["load_factor"]), int(row["seed"]), row["method"]


def pair_key(row: dict) -> tuple:
    return row["map"], float(row["load_factor"]), row["baseline"], row["reference"], row["metric"]


def load_control_notes(path: Path) -> dict | None:
    """Optional interpretation sidecar; it never changes metrics or runtime gates."""
    if not path.exists():
        return None
    value = read_json(path)
    require(value["schema"] == "czr005.feng_v5_hca_control_completion_notes.v1", "unknown control-accounting notes")
    cells = value["cells"]
    coords = {(c["map"], float(c["load_factor"]), int(c["seed"])) for c in cells}
    expected = {(m, l, s) for m in external.MAPS for l in external.LOAD_FACTORS for s in external.SEEDS}
    require(len(cells) == value["audited_cell_count"] == 60 and coords == expected, "control note coverage mismatch")
    for cell in cells:
        require(int(cell["residual"]) == int(cell["generated_count"]) - int(cell["completed_count"])
                - int(cell["active_route_count"]) - int(cell["unfinished_count"]), "control residual arithmetic differs")
    affected = [c for c in cells if int(c["residual"]) > 0]
    require(len(affected) == value["affected_cell_count"], "control affected count differs")
    value["_affected_groups"] = {(c["map"], float(c["load_factor"])) for c in affected}
    return value


def headline_pairs(pairs: dict, metric: str, affected_groups: set | None) -> tuple[list, int]:
    eligible = [p for p in pairs.values() if p["reference"] == METHODS[0] and p["baseline"] in METHODS[1:]
                and p["metric"] == metric and p["status"] == "COMPLETE"]
    selected = [p for p in eligible if p["baseline"] != METHODS[2]
                or (affected_groups is not None and (p["map"], float(p["load_factor"])) not in affected_groups)]
    return selected, len(eligible) - len(selected)


def completion_group(rows: list[dict], *, load: float) -> dict:
    require(len(rows) == 10 and {int(r["seed"]) for r in rows} == set(external.SEEDS), "report requires all ten frozen seeds")
    complete = sum(boolean(r["full_population_complete"]) for r in rows)
    counts = [number(r["TH_completed_raw_bags"]) for r in rows]
    rates = [number(r["completion_rate"]) for r in rows]
    require(all(v is not None for v in counts + rates), "completion metrics missing")
    timing = {}
    eligible = load != 2.0 and complete == 10
    for stat in STATS:
        values = [number(r[f"tht_scheduled_release_{stat}_seconds"]) for r in rows]
        timing[stat] = statistics.fmean(values) if eligible and all(v is not None for v in values) else None
    if not all(v is not None for v in timing.values()):
        timing = dict.fromkeys(STATS)
    return {"complete_seeds": complete, "TH_mean": statistics.fmean(counts), "TH_min": min(counts), "TH_max": max(counts),
            "completion_rate_mean": statistics.fmean(rates), "THT": timing,
            "THT_status": "2×协议" if load == 2 else "人口未全完" if complete != 10 else "时间证据不足" if timing["mean"] is None else "合格"}


def improvement_percent(baseline: float, reference: float, *, higher_is_better: bool) -> float | None:
    if baseline == 0:
        return None
    return 100 * ((reference - baseline) if higher_is_better else (baseline - reference)) / baseline


def validate_final_manifest(manifest: dict, verification: dict, manifest_path: Path) -> None:
    require(manifest["status"] == "COMPLETE" and manifest["expected_cells"] == 180 and manifest["observed_cells"] == 180,
            "final report requires all 180 audited cells")
    require(manifest["new_dh_cells"] == 60 and manifest["reused_control_cells"] == 120
            and manifest["qualified_control_reuse_count"] == 120, "new/reused method population mismatch")
    require(not manifest["failures"] and not manifest["missing_cells"] and manifest["archive_requested"], "final archive is incomplete")
    require(manifest["source_sha256"] == SOURCE_SHA and manifest["class_sha256"] == CLASS_SHA, "unfrozen V5 identity")
    require(verification["status"] == "PASS" and verification["observed_cells"] == 180
            and verification["campaign_status"] == "COMPLETE"
            and verification["campaign_manifest_sha256"] == sha(manifest_path), "archive verification is absent or stale")


def load_final(args: argparse.Namespace) -> tuple:
    paths = {"cells": args.table_root / "feng_dh_v5_cells_20260905.csv",
        "paired_csv": args.table_root / "feng_dh_v5_paired_20260905.csv",
        "paired_json": args.table_root / "feng_dh_v5_paired_20260905.json",
        "manifest": args.evidence_root / "campaign_manifest.json",
        "verification": args.evidence_root / "archive_verification.json", "historical": args.historical}
    control_notes_path = getattr(args, "control_notes", CONTROL_NOTES)
    if control_notes_path.exists():
        load_control_notes(control_notes_path)
        paths["control_accounting_notes"] = control_notes_path
    hashes = {name: sha(path) for name, path in paths.items()}
    manifest, verification = read_json(paths["manifest"]), read_json(paths["verification"])
    validate_final_manifest(manifest, verification, paths["manifest"])
    rows = read_csv(paths["cells"])
    indexed = {key(row): row for row in rows}
    expected = {(m, l, s, a) for m in external.MAPS for l in external.LOAD_FACTORS for s in external.SEEDS for a in METHODS}
    require(len(rows) == len(indexed) == 180 and set(indexed) == expected, "missing/duplicate/unfrozen cells")
    archived = {key(cell): cell for cell in manifest["cells"]}
    require(set(archived) == expected and len(manifest["cells"]) == 180, "archive cell identities differ")
    paired_identities = {}
    numeric_fields = ["completed_raw_bag_count", "completion_rate", "unfinished_raw_bag_count",
                      *[f"tht_scheduled_release_{stat}_seconds" for stat in STATS]]
    for coordinate, row in indexed.items():
        m, load, seed, method = coordinate
        require(float(row["fixed_horizon_seconds"]) == external.FIXED_HORIZON_SECONDS, "horizon differs")
        require(row["TH_definition"] == "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259", "TH definition differs")
        require(row["primary_timing_definition"] == "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE"
                and not boolean(row["historical_shared_D"]), "random matrix timing clock differs")
        raw, completed = int(row["raw_bag_count"]), number(row["completed_raw_bag_count"])
        require(raw == external.EXPECTED_POPULATIONS[load][0] and completed is not None and completed.is_integer()
                and 0 <= completed <= raw, "raw/completed population mismatch")
        close(row["TH_completed_raw_bags"], completed, "TH count columns differ")
        close(row["completion_rate"], completed / raw, "completion rate denominator mismatch")
        close(row["unfinished_raw_bag_count"], raw - completed, "unfinished raw population mismatch")
        require(boolean(row["full_population_complete"]) == (completed == raw), "complete flag mismatch")
        for field in numeric_fields:
            close(row[field], archived[coordinate]["exported_metrics"][field], f"table/archive mismatch: {field}")
        if method == METHODS[1]:
            require(row["source_sha256"] == SOURCE_SHA and row["class_sha256"] == CLASS_SHA, "cell V5 identity differs")
        eligible = load != 2 and boolean(row["full_population_complete"])
        timing = [number(row[f"tht_scheduled_release_{s}_seconds"]) for s in STATS]
        require(eligible or all(v is None for v in timing), "forbidden 2x/incomplete timing")
        if all(v is not None for v in timing):
            require(row["formal_timing_status"] == "FULL_POPULATION_RAW_BAG_TIMING"
                    and 0 <= timing[0] <= timing[1] <= timing[2], "invalid formal THT")
        identity_key = m, load, seed
        identity = row["workload_identity_sha256"]
        require(identity and (identity_key not in paired_identities or paired_identities[identity_key] == identity), "unpaired workloads")
        paired_identities[identity_key] = identity
    paired = read_json(paths["paired_json"])
    require(paired["status"] == "COMPLETE" and paired["expected_cells"] == paired["observed_cells"] == 180
            and paired["bootstrap_replicates"] == 10_000 and paired["confidence_level"] == .95,
            "expected complete ten-thousand-replicate paired bootstrap")
    require(paired["bootstrap_unit"] == "MATCHED_WORKLOAD_SEED_NOT_INDIVIDUAL_BAG"
            and paired["partial_seed_estimates_suppressed"], "invalid bootstrap unit/subset policy")
    pairs = {pair_key(row): row for row in read_csv(paths["paired_csv"])}
    json_pairs = {pair_key(row): row for row in paired["rows"]}
    require(len(pairs) == len(read_csv(paths["paired_csv"])) and set(pairs) == set(json_pairs), "paired table/json keys differ")
    for coordinate, row in pairs.items():
        expected_row = json_pairs[coordinate]
        require(row["status"] == expected_row["status"], "paired status differs")
        for field in ("paired_seed_count", "missing_seed_count", "baseline_mean", "reference_mean",
                      "mean_delta_reference_minus_baseline", "bootstrap_ci_low", "bootstrap_ci_high",
                      "reference_win_count", "tie_count", "reference_loss_count"):
            close(row.get(field), expected_row.get(field), "paired CSV/JSON statistic differs")
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for baseline in METHODS[1:]:
                for metric in ("completed_raw_bag_count", *[f"tht_scheduled_release_{s}_seconds" for s in STATS]):
                    pair = pairs[(map_name, load, baseline, METHODS[0], metric)]
                    values = [(number(indexed[(map_name, load, seed, baseline)][metric]),
                               number(indexed[(map_name, load, seed, METHODS[0])][metric])) for seed in external.SEEDS]
                    if metric != "completed_raw_bag_count" and load == 2:
                        require(pair["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL", "paired 2x timing not suppressed")
                    elif any(left is None or right is None for left, right in values):
                        require(pair["status"] == "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE", "paired missing timing not suppressed")
                    else:
                        require(pair["status"] == "COMPLETE" and int(pair["paired_seed_count"]) == 10, "ten-seed pair missing")
                        deltas = [right - left for left, right in values]
                        close(pair["baseline_mean"], statistics.fmean(left for left, _ in values), "paired baseline mean differs")
                        close(pair["reference_mean"], statistics.fmean(right for _, right in values), "paired reference mean differs")
                        close(pair["mean_delta_reference_minus_baseline"], statistics.fmean(deltas), "paired mean delta differs")
                        oriented = deltas if metric == "completed_raw_bag_count" else [-v for v in deltas]
                        require((int(pair["reference_win_count"]), int(pair["tie_count"]), int(pair["reference_loss_count"]))
                            == (sum(v > 1e-12 for v in oriented), sum(abs(v) <= 1e-12 for v in oriented), sum(v < -1e-12 for v in oriented)),
                            "paired win/tie/loss count differs")
    historical = read_json(paths["historical"])
    require(historical["pass"] and historical["every_D_OD_and_identity_matched"], "historical shared-D audit failed")
    history = historical["summaries_seconds"]
    for stat in STATS:
        rate = improvement_percent(history["V5_DH"][stat], history["G31"][stat], higher_is_better=False)
        close(rate, historical["G31_reduction_percent"]["V5_DH"][stat], "historical reduction differs")
    require(all(sha(path) == hashes[name] for name, path in paths.items()), "input changed during report validation")
    return rows, pairs, manifest, verification, historical, paths, hashes


def fmt(value: object, digits: int = 2) -> str:
    value = number(value)
    return "N/A" if value is None else f"{value:,.{digits}f}"


def link(output: Path, target: Path, label: str) -> str:
    return f"[{label}]({Path(os.path.relpath(target, output.parent)).as_posix()})"


def comparison_cells(pair: dict, *, metric: str) -> list[str]:
    if pair["status"] != "COMPLETE":
        reason = "2×协议" if pair["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL" else "全十种子时间资格不足"
        return [f"N/A（{reason}）", "N/A", "N/A", "N/A"]
    base, ref = number(pair["baseline_mean"]), number(pair["reference_mean"])
    rate = improvement_percent(base, ref, higher_is_better=metric == "completed_raw_bag_count")
    return ["N/A（对照为0）" if rate is None else f"{rate:+.2f}%",
            f"{number(pair['mean_delta_reference_minus_baseline']):+.2f}",
            f"[{number(pair['bootstrap_ci_low']):+.2f}, {number(pair['bootstrap_ci_high']):+.2f}]",
            f"{int(pair['reference_win_count'])}/{int(pair['tie_count'])}/{int(pair['reference_loss_count'])}"]


def render_report(args: argparse.Namespace, rows: list, pairs: dict, manifest: dict, verification: dict, historical: dict) -> str:
    output = args.output
    control_notes_path = getattr(args, "control_notes", CONTROL_NOTES)
    notes = load_control_notes(control_notes_path)
    affected_groups = None if notes is None else notes["_affected_groups"]

    def hca_mark(map_name: str, load: float, method: str) -> str:
        return "†" if method == METHODS[2] and (affected_groups is None or (map_name, load) in affected_groups) else ""
    v5_rows = [r for r in rows if r["method"] == METHODS[1]]
    terminal = Counter(r["native_terminal_status"] for r in v5_rows)
    full_counts = {method: sum(boolean(r["full_population_complete"]) for r in rows if r["method"] == method) for method in METHODS}
    evidence_link = link(output, args.evidence_root / "README.md", "完整压缩证据与复核入口")
    protocol_link = link(output, ROOT / "docs/baselines/feng_dh_v5_acceptance_and_campaign_protocol_20260905.md", "V5 采用记录与冻结实验协议")
    outcome_text = []
    for metric, label, better in (("tht_scheduled_release_mean_seconds", "平均 THT", -1),
                                  ("completed_raw_bag_count", "TH 完成量", 1)):
        eligible_pairs, excluded = headline_pairs(pairs, metric, affected_groups)
        deltas = [better * number(p["mean_delta_reference_minus_baseline"]) for p in eligible_pairs]
        good, tied, bad = sum(v > 1e-12 for v in deltas), sum(abs(v) <= 1e-12 for v in deltas), sum(v < -1e-12 for v in deltas)
        outcome_text.append(f"{label}在排除 {excluded} 个 HCA 账目异常或附注缺失条件后，有 {len(deltas)} 个具备十种子资格的地图/负载/对照条件，G31 的观测种子均值方向更优 {good}、持平 {tied}、更差 {bad} 个。")
    text = ["# V5 DH 两地图、三负载、十种子完整实验报告", "",
        f"**180/180 个方法格具有终态档案并通过字节与指标归档核验：60 格 V5 DH 新执行，120 格 G31/HCA 档案观测复用。** 方法格完成指运行记录与证据交付完整，不等于执行语义正确，也不等于所有行李均完成；60 个 V5 格中，全人口完成 {full_counts[METHODS[1]]} 格，未全完 {60-full_counts[METHODS[1]]} 格。",
        f"V5 原生终态计数：{'；'.join(f'{k} {v}' for k, v in sorted(terminal.items()))}。控制中 G31 全人口完成 {full_counts[METHODS[0]]}/60 格，HCA 全人口完成 {full_counts[METHODS[2]]}/60 格。未完成袋、失败尾部和不利条件均保留。", "",
        " ".join(outcome_text) + " 这些是条件级点估计的方向计数，不是显著性或容量优势计数，也不把原始 shared-D 结果纳入。G31 对 V5 的统计未变；受影响 HCA 原观测、差值区间和逐种子胜/平/负仍在下表保留。", "",
        f"本报告的全部数值从最终逐格表、配对统计表及证据清单派生，脚本再次核对分母、配对输入、种子、均值及胜/平/负；压缩归档验证通过 {verification['checked_unique_files']:,} 份唯一文件。{evidence_link}；{protocol_link}。", "",
        "**实验身份与口径。** 地图为 map2 和真实南宁图，负载为 1×、1.75×、2×，每种方法使用相同的十个固定工作负载种子：" + "、".join(map(str, external.SEEDS)) + "。",
        "各负载每种子的原始袋数依次为 " + "、".join(f"{external.EXPECTED_POPULATIONS[l][0]:,}" for l in external.LOAD_FACTORS) + "；EBS 段数依各格抖动后的 raw 实际展开，未固定成未抖动段数。共同绝对终止 epoch 为 98,259 秒；TH 是到该时点的完成原始袋数，完成率使用所有原始袋为分母，不是每小时容量。", "",
        "正式 THT 定义为每个原始袋所有业务段的 Σ（段完成时刻 − 共同 canonical scheduled release），先在每个种子的完整袋人口上求 min/mean/max，再对十种子统计量取均值。它区别于各方法原生起点：V5 first-admission；HCA/G31 processed_attempt（G31 对应 admitted_time）。这些 native 时间族尚未被证明代表同一物理入网事件；本报告的正式比较使用共同 canonical D，也不混用原始历史工作簿 D。HCA 实际整数 release 与 canonical D 可以存在不足 1 秒的差，偏移另存于逐格表，不能称三个执行器的实际释放 tick 完全相同。2× 的所有正式 THT 一律 N/A，即使全完；其他负载只要某方法组有一个种子人口未全完，该组 THT 也为 N/A。没有删袋、删种子、共同幸存者或可用子集均值。", "",
        "**随机矩阵主结果。** TH 方括号为十种子的最小—最大完成量；完成率为十种子的均值。THT 三列单位均为秒，数值是对应种子级统计量的均值，并非将十次运行拼成一个袋分布。"]
    if notes is None:
        text += ["", "**HCA 解释资格附注未提供。** HCA 观测与 N/A 继续保留，暂不纳入开头的优劣方向计数；没有因此要求新运行或修改已有统计。归档字节 PASS 不能作为执行语义正确的证明。"]
    else:
        affected_count, audited_count = notes["affected_cell_count"], notes["audited_cell_count"]
        case_seeds = "、".join(str(c["seed"]) for c in notes["detailed_cases"])
        nanning_1x_difference = statistics.fmean(number(r["TH_completed_raw_bags"]) for r in rows
            if r["map"] == "nanning" and float(r["load_factor"]) == 1 and r["method"] == METHODS[0]) - statistics.fmean(
            number(r["TH_completed_raw_bags"]) for r in rows
            if r["map"] == "nanning" and float(r["load_factor"]) == 1 and r["method"] == METHODS[2])
        group_parts = []
        for map_name in external.MAPS:
            for load in external.LOAD_FACTORS:
                group_cells = [c for c in notes["cells"] if c["map"] == map_name and float(c["load_factor"]) == load]
                positive = [int(c["residual"]) for c in group_cells if int(c["residual"]) > 0]
                if positive:
                    group_parts.append(f"{map_name} {load:g}×：{len(positive)}/10 格，每格正残差 {min(positive)}–{max(positive)} 段")
        text += ["", f"**历史 HCA 执行账目异常。** {audited_count} 格中 {affected_count} 格的 `generated−completed−active_routes−unfinished` 为正；这是段级账目残差，不直接等同于缺失原始袋数。" + "；".join(group_parts) + "。",
            f"南宁 1× 的 {len(notes['detailed_cases'])} 个细查种子（{case_seeds}）均记录同一原始袋的两段已释放、两次成功规划，却只有一次 raw-ID completion，终态 active/unfinished 都为 0；不能仅用普通时域排队解释。其 G31−HCA 平均完成量差为 {nanning_1x_difference:.1f} 袋，这不是无丢失物理基线的吞吐容量优势证据。可读源码按 raw task_id 保存活动路径，EBS 双段同键覆盖与日志吻合，但旧运行 class 身份未恢复，覆盖机制是高置信静态推断，具体完成段归属仍有歧义。其余 {affected_count-len(notes['detailed_cases'])} 格仅确认终态账目异常，未逐袋证明同一根因。",
            f"† 标记含异常格的 HCA 方法/负载组：仅保留档案观测及原 N/A/配对值，不作干净算法容量优越性证据，且从开头的条件级方向计数排除。其余 {audited_count-affected_count} 格本检查未发现正残差，不能由此泛化为全部 HCA 无效，也不能反推执行语义已获完整证明。" + link(output, control_notes_path, "控制完成账目复核与具体证据") + "。"]
    for map_name in external.MAPS:
        text += ["", f"**{'Map2' if map_name == 'map2' else '南宁'}**", "",
            "| 负载 | 方法 | TH 均值 [种子范围] | 完成率均值 | 全完种子 | THT min | THT mean | THT max |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                group = completion_group([r for r in rows if r["map"] == map_name and float(r["load_factor"]) == load and r["method"] == method], load=load)
                timing = [fmt(group["THT"][s]) if group["THT"][s] is not None else f"N/A（{group['THT_status']}）" for s in STATS]
                text.append("| " + " | ".join([f"{load:g}×", NAMES[method] + hca_mark(map_name, load, method),
                    f"{fmt(group['TH_mean'],1)} [{fmt(group['TH_min'],0)}–{fmt(group['TH_max'],0)}]",
                    f"{100*group['completion_rate_mean']:.4f}%", f"{group['complete_seeds']}/10", *timing]) + " |")
    text += ["", "**G31 对两个对照的十种子配对比较。** 正的改善率表示 G31 更优：THT 取（对照均值−G31 均值）/对照均值，TH 取（G31 均值−对照均值）/对照均值。负值明确表示劣化，零值为持平；相对百分比是两组种子均值的比，不是逐种子百分比的均值。", "",
        "差值及 95% 区间统一保持 **G31−对照** 原单位：THT 的负差较好，TH 的正差较好。区间来自以匹配工作负载种子为单位的 10,000 次配对 bootstrap，不是行李重采样，也不是相对百分比的区间。区间没有作多重比较校正；胜/平/负按指标方向逐种子判定。"]
    metrics = [(f"tht_scheduled_release_{s}_seconds", f"THT {s}（秒）") for s in STATS] + [("completed_raw_bag_count", "TH（袋）")]
    for map_name in external.MAPS:
        text += ["", f"**{'Map2' if map_name == 'map2' else '南宁'}：G31 配对改善**", "",
            "| 负载 | 对照 | 指标 | G31 改善率 | G31−对照 | 95% bootstrap 区间 | 胜/平/负 |",
            "|---|---|---|---:|---:|---:|---:|"]
        for load in external.LOAD_FACTORS:
            for baseline in METHODS[1:]:
                for metric, label in metrics:
                    pair = pairs[(map_name, load, baseline, METHODS[0], metric)]
                    text.append("| " + " | ".join([f"{load:g}×", SHORT[baseline] + hca_mark(map_name, load, baseline), label, *comparison_cells(pair, metric=metric)]) + " |")
        text += ["", "表注：† HCA 行仅描述有账目异常的档案记录；保留百分比、绝对差和区间不表示认可其容量解释，正值不得被改写成无丢失 HCA 物理系统的算法容量优势。"]
    text += ["", "完整逐格结果还保留准时率、未完成数、积压、迟到及入网后诊断时间：" +
        link(output, args.table_root / "feng_dh_v5_cells_20260905.csv", "逐格表") + "；" +
        link(output, args.table_root / "feng_dh_v5_paired_20260905.csv", "全部配对统计") + "。", "",
        "**原始 map2 shared-D 比较单列，不属于上述随机矩阵。** 该比较使用未抖动原始人口及逐段完全相同的历史 D；G31 为此独立重跑。"]
    h = historical["summaries_seconds"]
    mean_rate = improvement_percent(h["V5_DH"]["mean"], h["G31"]["mean"], higher_is_better=False)
    max_rate = improvement_percent(h["V5_DH"]["max"], h["G31"]["max"], higher_is_better=False)
    text += [f"在 {historical['raw_bags']:,} 袋、{historical['segments']:,} 段全部完成且 D/OD/身份对齐后，G31 相对 V5 的平均 THT 降低 **{mean_rate:.4f}%**，最大 THT 降低 **{max_rate:.4f}%**。这两个比例不混入随机十种子均值或 bootstrap，也不是独立留出结论。", "",
        "| 原始 shared-D 人口；秒 | THT min | THT mean | THT max |", "|---|---:|---:|---:|"]
    for method in ("V5_DH", "G31"):
        text.append("| " + " | ".join([method, *[fmt(h[method][s],3) for s in STATS]]) + " |")
    text += ["", link(output, ROOT / "outputs/reports/feng_dh_v5_shared_D_comparison_20260905.md", "原始 shared-D 完整独立报告") + "；" +
        link(output, args.historical, "逐段配对与审计") + "。", "",
        "**实现与证据限制。** V5 是用户在看过原始 map2 结果后采用的近似 DH 重构，属于明确披露的事后选择；后续本矩阵冻结实现、地图和参数，不按输赢调参。它包含尚未由原始实现恢复的 through/transfer/身体清空假设；尾部偏差及可能串行化身体清空与跟随的限制仍保留，不能因为均值可接受就称源代码精确复现。",
        "目前仍未取得相关 publisher 论文全文，已取得的论文文字、旧 Java、工作簿及 Demo3D 材料不足以还原全部原作者执行器。HCA 控制缺运行当时的 source/class 哈希，当前类文件不能补造旧运行身份；G31 旧控制格保留原聚合 JSON 和完整性门，未保存的逐袋 payload 不可凭空重建。V5 的全部袋/段及 HCA 实际可得生命周期均压缩保存；trace=0 的正式输出不能单独证明每 tick 的物理碰撞自由、FIFO 或零服务单次执行，这些另由独立微测试和 OD 预检支持。",
        "三方法运行在各自执行机制上，因此本结果是共同任务与业务口径下的系统比较，不能把差异全归因于单一路由规则，也不能解释成同一执行器下的纯策略因果效应。" +
        link(output, ROOT / "outputs/reports/feng_dh_map2_semantics_reaudit_20260905.md", "完整语义复审报告") + "；" +
        link(output, ROOT / "outputs/reports/feng_dh_boundary_clearance_tail_review_20260905.md", "V5 尾部审查") + "。", "",
        "**墙钟仅作运行诊断。** 下表保留各组十次记录的均值及范围；控制来自历史执行，V5 来自本次执行，硬件、编译器、并发和运行日期不受共同控制。因此不据此计算或声称算法加速比，决策计数也不跨执行器混为同一操作。", "",
        "| 地图 | 负载 | 方法 | 墙钟均值 [种子范围]，秒 | 有记录种子 |", "|---|---|---|---:|---:|"]
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                values = [number(r.get("wall_seconds")) for r in rows if r["map"] == map_name and float(r["load_factor"]) == load and r["method"] == method]
                measured = [v for v in values if v is not None]
                display = f"{fmt(statistics.fmean(measured))} [{fmt(min(measured))}–{fmt(max(measured))}]" if len(measured) == 10 else "N/A（记录不足，不取子集均值）"
                text.append("| " + " | ".join([map_name, f"{load:g}×", SHORT[method], display, f"{len(measured)}/10"]) + " |")
    text += ["", "**图与复现。** 图的每个大点为十种子统计量均值，浅点保留每个种子，须线是种子最小—最大范围，不是置信区间。图和报告均读取同一最终表，报告不依赖绘图脚本执行。"]
    figure_dir = ROOT / "outputs/figures/feng_dh_v5_20260905"
    for stem, label in (("feng_dh_v5_tht_min_mean_max_20260905", "正式 THT min/mean/max 图"),
                        ("feng_dh_v5_fixed_horizon_th_20260905", "固定时域 TH 完成量图")):
        text += ["", link(output, figure_dir / (stem + ".png"), label + "（PNG）") + "；" +
                 link(output, figure_dir / (stem + ".pdf"), "PDF") + "。"]
    text += ["", "复现统计与报告（不会启动新模拟）：", "", "```powershell",
        "python scripts/eval/export_feng_v5_campaign.py --archive --require-complete",
        "python scripts/eval/export_feng_v5_campaign.py --verify-archive",
        "python scripts/eval/plot_feng_dh_v5_comparison.py",
        "python scripts/eval/report_feng_dh_v5_campaign.py", "```", "",
        "长 SHA、逐文件压缩/解压哈希、输入身份和具体命令集中保存在证据清单及报告旁的 provenance JSON；正文不以路径或方法标签代替身份核验。"]
    return "\n".join(text) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-root", type=Path, default=TABLE_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--historical", type=Path, default=HISTORICAL)
    parser.add_argument("--control-notes", type=Path, default=CONTROL_NOTES,
                        help="Optional read-only accounting interpretation; never requires a new simulation")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows, pairs, manifest, verification, historical, paths, hashes = load_final(args)
    text = render_report(args, rows, pairs, manifest, verification, historical)
    require(all(sha(path) == hashes[name] for name, path in paths.items()), "input changed while report was generated")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    provenance = {"schema": "czr005.feng_v5_final_chinese_report.v1", "status": "COMPLETE",
        "observed_cells": len(rows), "new_v5_cells": 60, "reused_controls": 120,
        "bootstrap_replicates": 10000, "bootstrap_ci_is_absolute_difference_not_percentage": True,
        "source_sha256": SOURCE_SHA, "class_sha256": CLASS_SHA, "script_sha256": sha(Path(__file__)),
        "inputs": {name: {"path": str(path.resolve()), "sha256": hashes[name]} for name, path in paths.items()},
        "report": {"path": str(args.output.resolve()), "sha256": sha(args.output)}}
    args.output.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "cells": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
