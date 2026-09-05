"""Generate the Chinese repair comparison from validated exported observations only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "outputs/tables"
EVIDENCE = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905"
DH = "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"
G31 = "G31_S4_NATIVE_SYSTEM"
HCA = "FENG_NATIVE_HCA"
SOURCE = "809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f"
CLASSES = "ad828f533bc34abb3527d92f0f476e69412fc14c0024cbf2694bf0f82b382fd0"
SEEDS = (104729, 130363, 155921, 181081, 205759, 232003, 257053, 283303, 308081, 333667)
MAPS = ("map2", "nanning")
LOADS = (1.0, 1.75, 2.0)
TIMING_SUFFIXES = ("mean", "p95", "p99", "max")
TIMING_KEYS = tuple(f"{prefix}_{suffix}_seconds" for prefix in
                    ("population_latency", "scheduled_release_latency") for suffix in TIMING_SUFFIXES)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def number(value: object) -> float | None:
    if value is None or str(value).strip().lower() in {"", "n/a", "none", "null"}:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite metric: {value}")
    return result


def full(row: dict) -> bool:
    value = str(row["full_population_complete"]).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"invalid full-population flag: {value}")
    return value == "true"


def key(row: dict) -> tuple:
    return row["map"], float(row["load_factor"]), int(row["seed"]), row["method"]


def validate_cells(rows: list[dict]) -> dict[tuple, dict]:
    expected = {(m, load, seed, method) for m in MAPS for load in LOADS
                for seed in SEEDS for method in (DH, G31, HCA)}
    indexed = {}
    for row in rows:
        coordinate = key(row)
        if coordinate not in expected or coordinate in indexed:
            raise ValueError(f"unexpected/duplicate cell: {coordinate}")
        population = number(row["raw_bag_count"])
        completed = number(row["completed_raw_bag_count"])
        if population is None or population <= 0 or completed is None or not 0 <= completed <= population:
            raise ValueError(f"invalid raw-bag denominator: {coordinate}")
        if full(row) != (completed == population):
            raise ValueError(f"full-population flag contradicts completed count: {coordinate}")
        if coordinate[0] == "nanning" and coordinate[3] == DH:
            if row["source_sha256"] != SOURCE or row["class_sha256"] != CLASSES:
                raise ValueError(f"old or unfrozen Nanning DH cell: {coordinate}")
        if coordinate[1] == 2.0 or not full(row):
            if any(number(row.get(metric)) is not None for metric in TIMING_KEYS):
                raise ValueError(f"ineligible formal latency is populated: {coordinate}")
        indexed[coordinate] = row
    return indexed


def paired_key(row: dict) -> tuple:
    return row["map"], float(row["load_factor"]), row["comparison"], row["metric"]


def validate_paired(aggregate: dict, paired_csv: list[dict], count: int) -> dict:
    if aggregate["observed_result_count"] != count or aggregate["expected_result_count"] != 180:
        raise ValueError("cell export and paired aggregate are different snapshots; rerun export first")
    left = {paired_key(row): row for row in aggregate["rows"]}
    right = {paired_key(row): row for row in paired_csv}
    if len(left) != len(aggregate["rows"]) or len(right) != len(paired_csv) or left.keys() != right.keys():
        raise ValueError("paired JSON/CSV coordinates differ")
    numeric = ("paired_seed_count", "baseline_mean", "reference_mean", "reference_win_count",
               "reference_loss_count", "tie_count", "bootstrap_ci_low", "bootstrap_ci_high")
    for coordinate, row in left.items():
        for field in numeric:
            a, b = number(row.get(field)), number(right[coordinate].get(field))
            if a != b:
                raise ValueError(f"paired JSON/CSV metric differs: {coordinate}, {field}")
        if row["status"] != right[coordinate]["status"]:
            raise ValueError(f"paired JSON/CSV status differs: {coordinate}")
    return {(row["map"], float(row["load_factor"]), row["metric"]): row
            for row in aggregate["rows"] if row.get("runtime_comparison") == DH}


def pairs_for(indexed: dict, map_name: str, load: float) -> list[tuple[dict, dict]]:
    pairs = []
    for seed in SEEDS:
        dh, g31 = indexed.get((map_name, load, seed, DH)), indexed.get((map_name, load, seed, G31))
        if dh is None or g31 is None:
            continue
        for field in ("workload_identity_sha256", "input_sha256", "map_sha256", "raw_bag_count", "segment_count"):
            if str(dh[field]) != str(g31[field]):
                raise ValueError(f"unpaired input identity: {map_name}/{load}/{seed}/{field}")
        pairs.append((dh, g31))
    return pairs


def mean(pairs: list, method: int, metric: str) -> float | None:
    values = [number(pair[method].get(metric)) for pair in pairs]
    if not values or any(value is None for value in values):
        return None
    return statistics.fmean(values)


def timing_eligible(pairs: list, load: float) -> bool:
    return bool(pairs) and load != 2.0 and all(full(row) for pair in pairs for row in pair)


def matrix_status(indexed: dict) -> str:
    corrected = sum(1 for coordinate in indexed if coordinate[0] == "nanning" and coordinate[3] == DH)
    return "COMPLETE" if len(indexed) == 180 and corrected == 30 else "INCOMPLETE"


def fmt(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:,.{digits}f}"


def both(pairs: list, metric: str, *, factor: float = 1.0, digits: int = 2) -> str:
    values = [mean(pairs, method, metric) for method in (0, 1)]
    return " / ".join(fmt(None if value is None else value * factor, digits) for value in values)


def label(map_name: str, load: float) -> str:
    return f"{'南宁' if map_name == 'nanning' else 'map2'} {load:g}×"


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
                     + ["| " + " | ".join(row) + " |" for row in rows])


def metric_change(pairs: list, metric: str, percentage_points: bool = False) -> str:
    dh, g31 = mean(pairs, 0, metric), mean(pairs, 1, metric)
    if dh is None or g31 is None:
        return "N/A"
    delta = g31 - dh
    if abs(delta) <= 1e-9:
        return "持平"
    direction = "高" if delta > 0 else "低"
    if percentage_points:
        return f"{direction} {abs(delta) * 100:.2f} 个百分点"
    if dh == 0:
        return f"{direction} {abs(delta):.2f}"
    return f"{direction} {abs(delta / dh) * 100:.2f}%"


def build_report(rows: list[dict], aggregate: dict, paired_csv: list[dict], evidence: Path,
                 portable: Path, input_hashes: dict[str, str]) -> str:
    indexed = validate_cells(rows)
    paired = validate_paired(aggregate, paired_csv, len(indexed))
    groups = {(m, load): pairs_for(indexed, m, load) for m in MAPS for load in LOADS}
    corrected = sum(1 for coordinate in indexed if coordinate[0] == "nanning" and coordinate[3] == DH)
    matrix_complete = matrix_status(indexed) == "COMPLETE"
    if matrix_complete != (aggregate["status"] == "COMPLETE"):
        raise ValueError("aggregate completion contradicts the frozen 180-cell coordinate matrix")
    status = "COMPLETE" if matrix_complete else "INCOMPLETE"
    for (m, load), pairs in groups.items():
        for metric in ("completed_raw_bag_count", "on_time_rate", "total_backlog_area_seconds",
                       "population_latency_mean_seconds"):
            record = paired.get((m, load, metric))
            if not pairs or (metric.startswith("population_latency") and not timing_eligible(pairs, load)):
                continue
            if record is None or int(record["paired_seed_count"]) != len(pairs):
                raise ValueError(f"paired seed count differs: {m}/{load}/{metric}")
            for method, field in ((0, "baseline_mean"), (1, "reference_mean")):
                observed = mean(pairs, method, metric)
                if observed is None or not math.isclose(observed, float(record[field]), rel_tol=1e-10, abs_tol=1e-7):
                    raise ValueError(f"paired aggregate differs from cells: {m}/{load}/{metric}")

    gates = {
        "correctness_map2": read_json(evidence / "regression_final/map2_full_population_regression.json"),
        "optimized_map2": read_json(evidence / "regression_optimized/map2_full_population_regression.json"),
        "all_od": read_json(evidence / "regression_optimized/single_bag_equivalence_and_archives.json"),
        "optimization_od": read_json(evidence / "regression_optimized/correctness_to_optimized_equivalence.json"),
        "optimization_population": read_json(evidence / "optimization_full_population_1x.json"),
        "optimization_traces": read_json(evidence / "optimization_equivalence_v1/verification.json"),
    }
    correctness_pass = all(value.get("pass") is True for name, value in gates.items()
                           if name != "optimization_traces") and gates["optimization_traces"]["status"] == "PASS"
    if not correctness_pass:
        raise ValueError("correctness/equivalence evidence is not PASS; cannot publish repaired comparison")
    program_status = "PASS（所列回归范围）" if correctness_pass else "NOT_VERIFIED"
    archive = read_json(portable) if portable.exists() else {"cell_count": 0, "cells": []}
    archive_coords = {(r["map"], float(r["load_factor"]), int(r["seed"])) for r in archive["cells"]}
    if len(archive_coords) != archive["cell_count"] or any((*c, DH) not in indexed for c in archive_coords):
        raise ValueError("portable archive does not match the exported corrected cells")
    matrix_rows, business_rows, latency_rows, release_rows, cost_rows, findings = [], [], [], [], [], []
    for (m, load), pairs in groups.items():
        counts = [sum((m, load, seed, method) in indexed for seed in SEEDS) for method in (DH, G31, HCA)]
        matrix_rows.append([label(m, load), *(f"{count}/10" for count in counts)])
        n = f"{len(pairs)}/10"
        denominators = sorted({int(float(pair[0]["raw_bag_count"])) for pair in pairs})
        population = ", ".join(f"{value:,}" for value in denominators) if pairs else "N/A"
        backlog = []
        for method in (0, 1):
            backlog.append(" / ".join(fmt(None if (value := mean(pairs, method, metric)) is None else value / 1e6)
                                      for metric in ("source_backlog_area_seconds", "network_backlog_area_seconds", "total_backlog_area_seconds")))
        business_rows.append([label(m, load), n, both(pairs, "completed_raw_bag_count", digits=1) + f"（分母 {population}）",
                              both(pairs, "on_time_rate", factor=100), *backlog])
        eligible = timing_eligible(pairs, load)
        eligibility = "2×协议 N/A" if load == 2 else (n if eligible else "N/A：无配对或有未完成格")
        latency_rows.append([label(m, load), eligibility, *[
            both(pairs, f"population_latency_{suffix}_seconds") if eligible else "N/A" for suffix in TIMING_SUFFIXES]])
        release_rows.append([label(m, load), eligibility, *[
            both(pairs, f"scheduled_release_latency_{suffix}_seconds") if eligible else "N/A" for suffix in TIMING_SUFFIXES]])
        cost_rows.append([label(m, load), n, both(pairs, "wall_seconds"), both(pairs, "cpu_seconds"),
                          both(pairs, "decision_requests", digits=0), "历史复用 / 历史记录" if m == "map2" else "本次修复优化 / 历史记录"])
        if pairs:
            prefix = f"{label(m, load)}（{'十种子' if len(pairs) == 10 else f'暂定 {n} 种子'}）"
            completion_delta = mean(pairs, 1, "completed_raw_bag_count") - mean(pairs, 0, "completed_raw_bag_count")
            metrics = ["G31 平均完成量" + metric_change(pairs, "completed_raw_bag_count")
                       + f"（G31 − DH：{completion_delta:+,.1f} 袋）"]
            if eligible:
                metrics.append("G31 入网后 mean " + metric_change(pairs, "population_latency_mean_seconds"))
                metrics.append("P95/P99/max 分别" + "、".join(metric_change(pairs, f"population_latency_{suffix}_seconds")
                                                             for suffix in ("p95", "p99", "max")))
                metrics.append("统一 scheduled-release mean " + metric_change(pairs, "scheduled_release_latency_mean_seconds"))
            metrics.append("准时率" + metric_change(pairs, "on_time_rate", True))
            metrics.append("总积压面积" + metric_change(pairs, "total_backlog_area_seconds"))
            record = paired.get((m, load, "on_time_rate"), {})
            wins = "/".join(str(record.get(field, "N/A")) for field in ("reference_win_count", "tie_count", "reference_loss_count"))
            completion_record = paired.get((m, load, "completed_raw_bag_count"), {})
            completion_wins = "/".join(str(completion_record.get(field, "N/A")) for field in
                                       ("reference_win_count", "tie_count", "reference_loss_count"))
            tail_note = ""
            if eligible:
                tail_record = paired.get((m, load, "population_latency_max_seconds"), {})
                tail_wins = "/".join(str(tail_record.get(field, "N/A")) for field in
                                      ("reference_win_count", "tie_count", "reference_loss_count"))
                tail_note = f"；入网后 max 为 {tail_wins}"
            findings.append(f"- **{prefix}**：" + "；".join(metrics)
                            + f"。完成量逐种子胜/平/负为 {completion_wins}；准时率为 {wins}{tail_note}。")

    prefix = "../runtime/feng_cie_dh_zero_through_repair_20260905/"
    optimized = gates["optimization_population"]
    walls = optimized.get("summary_differences", {}).get("wall_seconds", [])
    optimization_text = (f"南宁 1×、seed 104729 的正确性修复版与优化版均完成 {optimized['raw_bags']:,} 袋、"
                         f"{optimized['segments']:,} 段，逐袋/逐段/事件输出一致，逻辑决策 {optimized['logical_decisions']:,} 次不变。"
                         + (f"记录模拟墙钟 {float(walls[0]):.3f}→{float(walls[1]):.3f} s（{float(walls[0])/float(walls[1]):.2f}×）；" if len(walls) == 2 else "")
                         + "这是保持行为不变的实现优化对照，不是 G31 加速比。")
    text = [
        "# Feng CIE-DH 修复、实验与 G31 比较（2026-09-05）", "",
        f"**矩阵状态：`{status}`；有效执行格 {len(indexed)}/180，修复后南宁 DH {corrected}/30。** "
        + ("预设两地图、三负载、十种子、三方法矩阵已经齐全。" if matrix_complete else
           "仍缺的格子不纳入均值、不用旧缺陷版填补；下列南宁结果按已完成种子明确标为暂定。"), "",
        "本报告由 `scripts/eval/write_feng_repaired_report.py` 从[逐格 CSV](../tables/feng_cie_dh_repaired_cells_20260905.csv)、"
        "[配对 JSON](../tables/feng_cie_dh_repaired_paired_20260905.json)与[配对 CSV](../tables/feng_cie_dh_repaired_paired_20260905.csv)生成，"
        "配对 bootstrap 区间和全部指标保留在这些机器可读表中。", "",
        "## 四项独立结论", "",
        table(["检验轴", "结论"], [
            ["程序正确性", program_status + "；零服务有限完成、同步竞争/跟驰/阻塞释放、真实业务 OD、全人口回归通过后才接受新结果。"],
            ["论文语义恢复", "`SEMANTICALLY_PARTIAL_RECONSTRUCTION`；through/transfer 合同与 0.4/0.8 s 系数仍是披露的重构假设。"],
            ["历史数值匹配", "shared-D mean：238.7023 vs 265.5921 s；max：326.0 vs 517.2 s。原重构偏乐观的差距保留，未通过人为等待或调参抹平。"],
            ["G31 性能", "按同输入、同种子、同指标给出有条件的优势和代价；map2 1× 的尾部反例与独立 same_hca 2× 反例保留。"]]), "",
        f"正确性提交 `8da1844` 与等价优化提交 `0ca1f45` 分离；新南宁源 SHA-256 `{SOURCE}`，类 SHA-256 `{CLASSES}`。", "",
        "## 正确性、复用与原始证据", "",
        f"[regression_final]({prefix}regression_final/map2_full_population_regression.json)与"
        f"[regression_optimized]({prefix}regression_optimized/correctness_to_optimized_equivalence.json)记录原 map2 "
        "28,506 袋、43,603 段在旧版、正确性版、优化版间逐袋/逐段字节一致，统计只允许墙钟不同；"
        "因此复用 map2 90 格和不受独立 Java bug 影响的南宁 HCA/G31 60 格。外部随机实验段数从各格 identity 读取，"
        "不把原始 map2 的 43,603 段强行套到投影输入。"
        f"[发表追溯说明]({prefix}publication_traceability/README.md)提供可下载的 map2 共享全人口归档、"
        "60 格输入 identity，以及源码/输入换行转换和原始字节 SHA 的独立复核。", "",
        f"[无拥堵 OD 回归]({prefix}regression_optimized/single_bag_equivalence_and_archives.json)通过 "
        f"{gates['all_od']['complete_repaired_od_tests']} 个案例（25 个 map2、496 个南宁正式 OD，加 130→57→58 拓扑见证）。"
        f"[实际业务见证]({prefix}regression_final/repaired_formal_business_witness.json)保留 raw bag 7007、segment 0、"
        "0→20 经零时间中间节点 56 的旧错误与新完成状态。原 T1–T10、新 Z1–Z12、跨 snapshot 缓存失效均有独立断言。", "",
        f"[trace=1 拥堵对照]({prefix}optimization_equivalence_v1/verification.json)的 128 袋/256 段输出逐字节一致；"
        "样本包含 42,326 次 HOLD、40,210 个 stopped ticks 和 1,390 次同 snapshot/node/goal 重复请求。"
        f"[全人口优化对照]({prefix}optimization_full_population_1x.json)：" + optimization_text, "",
        f"[可移植归档](../evidence/feng_cie_dh_repair_20260905/archive_manifest.json)当前含 {archive['cell_count']}/30 个新南宁 DH 格，"
        "保留完整 bags/segments 的无损 gzip、summary、事件计数、runner 身份与压缩前后 SHA；"
        + ("归档已覆盖本次全部新南宁格。" if archive['cell_count'] == corrected else "归档状态与计算完成状态分别记录，尚未归档的格子不冒称已交付归档。"), "",
        "[全人口独立审计](../evidence/feng_cie_dh_repair_20260905/population_audit.json)逐格核对正式 OD、"
        "释放时刻、行李/运输段身份、完成状态和事件计数。正式 trace=0 终态文件没有逐 tick 位置或服务启动次数，"
        "不能单靠该审计证明逐 tick 无碰撞或零服务从不重启；这些性质的证据来自前述微测、拥堵轨迹对照与运行时断言。", "",
        "旧南宁 16 个终止文件和 14 个中断格均原样保留，另加"
        "[科学有效性旁车](../runtime/cie_external_baseline_robustness/scientific_validity_20260905.json) "
        "`INVALIDATED_ZERO_THROUGH_STATE_MACHINE_BUG`。旧约 44% 完成率不能表示有效 DH 性能；"
        "834.18× 是旧程序南宁/map2 决策数比，582.73× 是墙钟比，均不是 G31 加速比。"
        "它们作为正常拥堵扩展性证据的解释已经撤回。", "",
        "## 固定十种子矩阵与同口径结果", "",
        table(["地图/负载", "DH", "G31", "HCA"], matrix_rows), "",
        "以下每个“DH / G31”单元只用同一批已观测配对种子；数值为种子统计量的算术平均，"
        "不是把所有袋合并后重新算分位数。未齐十种子不作最终稳定性结论。所有格固定 horizon 为 98,259 s。", "",
        table(["地图/负载", "配对", "平均完成袋数 DH / G31", "准时率 % DH / G31", "DH 源/网/总积压（百万 bag-s）", "G31 源/网/总积压（百万 bag-s）"], business_rows), "",
        "入网后时延为 `Σsegments(completion - admission)`：DH `diagnostic_first_admission_to_completion` "
        "与 G31 `processed_attempt` 使用同一逐段求和口径，均不含源端等待。正式 2× 一律 N/A；"
        "低负载任何配对格未完成全人口时，整组时延显示 N/A，不挑完成种子或幸存袋。", "",
        table(["地图/负载", "计时资格/配对", "mean s DH / G31", "P95 s DH / G31", "P99 s DH / G31", "max s DH / G31"], latency_rows), "",
        "补充统一 scheduled-release 分栏为 `Σsegments(completion - scheduled release)`，包括该释放之后的源端等待。"
        "它从现有全人口输出重聚合，不是历史 shared-D，也没有为改列名重新模拟。资格限制与上表一致。", "",
        table(["地图/负载", "计时资格/配对", "mean s DH / G31", "P95 s DH / G31", "P99 s DH / G31", "max s DH / G31"], release_rows), "",
        *(["![完整十种子比较](../figures/feng_cie_dh_repaired_comparison_20260905.png)", "",
           "图中阴影为固定十种子的范围；实线/虚线分别对应入网后/计划释放后计时。", ""] if matrix_complete else []),
        "## 有数据支持的优势与代价", "", *findings, "",
        "独立无抖动、相同 HCA release 的 [same_hca 临界负载 2×](cie_critical_load_curve_v2.md)反例仍为："
        "DH 准时率 98.89%（56,379/57,012），G31 53.03%（30,231/57,012）；总积压面积分别约 1.563e8 与 2.935e8 bag-s。"
        "该释放协议不能与上面的随机外部实验拼接。正式 2× 时延继续为 N/A。", "",
        "[原生 HCA/G31 正式比较](cie_baseline_comparison.md)仍保留：在相同 HCA release 的 1× 完整人口上，"
        "G31 相对 HCA 的 mean 在 map2/南宁分别低 11.532%/24.365%，其尾部与容量证据来自原独立科目。"
        "同一报告中的公共 C++ 执行器 CIE-DH adapted 仅用于 P1 路由机制隔离；"
        "[析因](cie_random_factorial_full.md)和[消融](cie_targeted_ablation_report.md)也保持各自执行器及协议。", "",
        "## 实际计算成本与测量限制", "",
        table(["地图/负载", "配对", "wall s DH / G31", "CPU s DH / G31", "决策请求 DH / G31", "记录来源 DH / G31"], cost_rows), "",
        "DH wall 是 native simulator 计时，G31 wall/CPU 是原生 runtime 记录；HCA、Java、C++ 的计时边界并非完全同一进程包络。"
        "表中 map2 DH/G31 和南宁 G31 为历史有效记录，南宁 DH 为本次修复优化记录；"
        "不同采集时刻、JVM 预热和并发资源竞争影响墙钟，不能把这些数值当作受控单核速度排名。"
        "缺失 CPU 保持 N/A；决策请求定义按各方法原生日志，不据其数量直接推导算法时间复杂度。", "",
        "## 可重复生成", "",
        "`python scripts/eval/export_feng_repaired_evidence.py --archive` 依赖本机完整原生运行目录，"
        "用于更新逐格表和归档。使用已提交的逐格 CSV、配对 JSON/CSV 与回归证据，可直接运行 "
        "`python scripts/eval/write_feng_repaired_report.py` 重生成报告；完整矩阵还可运行 "
        "`python scripts/eval/plot_feng_repaired_comparison.py` 重生成图。报告和绘图步骤不启动模拟。报告生成器"
        "对旧南宁源码、重复坐标、跨方法输入身份不一致、JSON/CSV 不同步及不合格正式时延直接报错。", "",
        "本次输入 SHA-256：", "",
        *[f"- `{name}`：`{digest}`。" for name, digest in input_hashes.items()], "",
    ]
    return "\n".join(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=Path, default=TABLES / "feng_cie_dh_repaired_cells_20260905.csv")
    parser.add_argument("--paired-json", type=Path, default=TABLES / "feng_cie_dh_repaired_paired_20260905.json")
    parser.add_argument("--paired-csv", type=Path, default=TABLES / "feng_cie_dh_repaired_paired_20260905.csv")
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--portable-manifest", type=Path, default=ROOT / "outputs/evidence/feng_cie_dh_repair_20260905/archive_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reports/feng_cie_dh_repair_comparison_20260905.md")
    args = parser.parse_args()
    paths = (args.cells, args.paired_json, args.paired_csv)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    report = build_report(read_csv(args.cells), read_json(args.paired_json), read_csv(args.paired_csv),
                          args.evidence_root, args.portable_manifest, hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": "COMPLETE" if "`COMPLETE`" in report.splitlines()[2] else "INCOMPLETE"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
