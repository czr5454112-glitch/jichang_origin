"""Read-only historical DH/HCA workbook diagnostics, paired on exact shared D."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/runtime/feng_dh_historical_signatures_20260905"
BOOK = Path("C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料/毕业设计/仿真结果数据整理（与分散启发式方法对比）.xlsx")
N = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(archive: ZipFile, sheet: int):
    with archive.open(f"xl/worksheets/sheet{sheet}.xml") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != N + "row": continue
            result = {"excel_row": int(element.attrib["r"])}
            for cell in element.findall(N + "c"):
                if cell.attrib.get("t") in {"s", "str", "inlineStr"}: continue
                value = cell.findtext(N + "v")
                if value is not None:
                    result[re.match("[A-Z]+", cell.attrib["r"])[0]] = float(value)
            yield result
            element.clear()


def stats(values) -> dict:
    a = np.asarray(values, dtype=float)
    return {"count": int(len(a)), "min": float(np.min(a)), "p01": float(np.quantile(a, .01)),
            "p05": float(np.quantile(a, .05)), "median": float(np.median(a)),
            "mean": float(np.mean(a)), "p95": float(np.quantile(a, .95)),
            "p99": float(np.quantile(a, .99)), "max": float(np.max(a))}


def grouped(frame: pd.DataFrame, by: list[str], values: list[str]) -> pd.DataFrame:
    result = []
    for key, group in frame.groupby(by, sort=True, dropna=False):
        if not isinstance(key, tuple): key = (key,)
        row = dict(zip(by, key))
        row["count"] = len(group)
        for field in values:
            row.update({f"{field}_{k}": v for k, v in stats(group[field]).items() if k != "count"})
        result.append(row)
    return pd.DataFrame(result)


def output_table(name: str, frame: pd.DataFrame) -> None:
    frame.to_csv(OUT / name, index=False, lineterminator="\n", float_format="%.9f")


def physical_time_path(edges: dict, start: int, goal: int, stage_seconds: float = 3.0) -> tuple[float, tuple[int, ...]]:
    frontier = [(2.0, (start,), start)]
    settled = set()
    while frontier:
        time, path, node = heapq.heappop(frontier)
        if node in settled: continue
        if node == goal: return time, path
        settled.add(node)
        for (source, target), length in edges.items():
            if source == node and target not in path:
                heapq.heappush(frontier, (time + length / 2.5 + (0 if target == goal else stage_seconds), path + (target,), target))
    raise ValueError("unreachable physical path")


def run(book: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assert sha(book).upper() == "E8EE03FE5C75FFF2BEC88251566521E3E6283D549F5676BE624C55E050F771FB"
    with ZipFile(book) as archive:
        dh = pd.DataFrame(rows(archive, 2))
        hca = pd.DataFrame(rows(archive, 1))
        schedule = pd.DataFrame(rows(archive, 3))
    dh = dh[dh.A.notna()].copy()
    hca = hca[hca.A.notna()].copy()
    schedule = schedule[schedule.A.notna()].copy()
    assert len(dh) == len(hca) == len(schedule) == 43603
    dh["raw_bag_id"] = dh.A.astype(int)
    dh["start"] = dh.B.astype(int); dh["goal"] = dh.C.astype(int)
    dh["release_seconds"] = dh.D
    dh["historical_dh_seconds"] = dh.E - dh.D
    dh["historical_completion_seconds"] = dh.E
    dh["segment_id"] = dh.groupby("raw_bag_id").cumcount()
    assert dh.groupby("raw_bag_id").size().value_counts().to_dict() == {2: 15097, 1: 13409}
    hca_view = hca.rename(columns={"A": "raw_bag_id", "B": "start", "C": "hca_release_seconds", "D": "hca_completion_seconds"})
    df = dh.merge(hca_view[["raw_bag_id", "start", "hca_release_seconds", "hca_completion_seconds"]],
                  on=["raw_bag_id", "start"], how="left", validate="one_to_one")
    assert (df.release_seconds == df.hca_release_seconds).all()
    df["historical_hca_seconds"] = df.hca_completion_seconds - df.hca_release_seconds
    schedule_keys = {(int(r.A), int(r.B), int(r.C)): r.D for r in schedule.itertuples()}
    assert all(schedule_keys[(int(r.raw_bag_id), int(r.start), int(r.goal))] == r.release_seconds for r in df.itertuples())
    primary = ROOT / "outputs/runtime/feng_cie_dh_reconstruction/primary"
    current = pd.read_csv(primary / "segments.csv")
    current["current_dh_seconds"] = current.completion_time_seconds - current.release_seconds
    current = current.rename(columns={"release_seconds": "current_release_seconds"})
    df = df.merge(current[["raw_bag_id", "segment_id", "start", "goal", "current_release_seconds", "current_dh_seconds",
                           "moving_ticks", "stopped_ticks", "hold_count", "admission_time_seconds"]],
                  on=["raw_bag_id", "segment_id", "start", "goal"], validate="one_to_one")
    assert len(df) == 43603 and (df.release_seconds == df.current_release_seconds).all()
    df["current_source_wait_seconds"] = df.admission_time_seconds - df.release_seconds
    df["historical_minus_current_seconds"] = df.historical_dh_seconds - df.current_dh_seconds
    df["historical_dh_minus_hca_seconds"] = df.historical_dh_seconds - df.historical_hca_seconds
    df["segment_count"] = df.groupby("raw_bag_id").raw_bag_id.transform("size")
    df["leg_kind"] = np.where(df.segment_count == 1, "direct", np.where(df.segment_id == 0, "ebs_in", "ebs_out"))
    ff_path = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905/regression_final/repaired_map2_single_bag.jsonl.gz"
    ff = [json.loads(line) for line in gzip.decompress(ff_path.read_bytes()).decode().splitlines()]
    lines = (ROOT / "legacy/jichang_origin_readonly/map2.txt").read_text().splitlines()
    n = int(lines[0].split()[0])
    edges = {(int(f[0]), int(f[1])): float(f[2]) for f in (line.split() for line in lines[1+n+n:] if line.strip())}
    ff_records = []
    for row in ff:
        path = row["shortest_path"]
        distance = sum(edges[(a, b)] for a, b in zip(path, path[1:]))
        physical_min, physical_path = physical_time_path(edges, row["start"], row["goal"])
        diagnostic_min, diagnostic_path = physical_time_path(edges, row["start"], row["goal"], 3.1)
        ff_records.append({"start": row["start"], "goal": row["goal"], "free_flow_current_seconds": row["completion_tick"] * .2,
            "edge_count": len(path) - 1, "intermediate_nodes": len(path) - 2,
            "distance_meters": distance, "pure_motion_seconds": distance / 2.5,
            "node_path": ";".join(map(str, path)), "physical_model_min_seconds": physical_min,
            "physical_model_min_path": ";".join(map(str, physical_path)),
            "diagnostic_3p1_physical_min_seconds": diagnostic_min,
            "diagnostic_3p1_physical_min_path": ";".join(map(str, diagnostic_path))})
    df = df.merge(pd.DataFrame(ff_records), on=["start", "goal"], validate="many_to_one")
    df["historical_excess_over_current_free_flow"] = df.historical_dh_seconds - df.free_flow_current_seconds
    df["current_excess_over_free_flow"] = df.current_dh_seconds - df.free_flow_current_seconds
    # Five-minute counts are description of the frozen workload, not adjustable parameters.
    df["release_300s_bin"] = (df.release_seconds // 300).astype(int)
    df["origin_release_300s_count"] = df.groupby(["start", "release_300s_bin"]).raw_bag_id.transform("size")
    df["all_release_300s_count"] = df.groupby("release_300s_bin").raw_bag_id.transform("size")
    df["same_origin_release_count"] = df.groupby(["start", "release_seconds"]).raw_bag_id.transform("size")
    ordered = df.sort_values(["start", "release_seconds", "raw_bag_id", "segment_id"])
    df.loc[ordered.index, "previous_same_origin_release_gap"] = ordered.groupby("start").release_seconds.diff()
    # Independent cached aggregation: I indexed by H, and HCA G indexed by F.
    bag = df.groupby("raw_bag_id", sort=True).agg(
        segment_count=("segment_count", "first"), first_release=("release_seconds", "min"),
        historical_dh_seconds=("historical_dh_seconds", "sum"), historical_hca_seconds=("historical_hca_seconds", "sum"),
        current_dh_seconds=("current_dh_seconds", "sum"), delta=("historical_minus_current_seconds", "sum"))
    cached_dh = dh[dh.H.notna() & dh.I.notna()].set_index("H").I
    cached_hca = hca[hca.F.notna() & hca.G.notna()].set_index("F").G
    assert len(cached_dh) == len(cached_hca) == len(bag) == 28506
    assert np.allclose(bag.historical_dh_seconds, cached_dh.loc[bag.index], atol=1e-8, rtol=0)
    assert np.allclose(bag.historical_hca_seconds, cached_hca.loc[bag.index], atol=1e-8, rtol=0)
    fields = ["historical_dh_seconds", "historical_hca_seconds", "current_dh_seconds", "historical_minus_current_seconds",
              "historical_excess_over_current_free_flow", "current_excess_over_free_flow", "current_source_wait_seconds"]
    by_od = grouped(df, ["start", "goal"], fields).merge(pd.DataFrame(ff_records), on=["start", "goal"])
    by_od["historical_min_minus_free_flow"] = by_od.historical_dh_seconds_min - by_od.free_flow_current_seconds
    by_od["historical_min_minus_motion"] = by_od.historical_dh_seconds_min - by_od.pure_motion_seconds
    by_od["diagnostic_motion_plus_2_plus_3p1_each_intermediate"] = by_od.pure_motion_seconds + 2 + 3.1 * by_od.intermediate_nodes
    by_od["historical_min_minus_3p1_stage_signature"] = by_od.historical_dh_seconds_min - by_od.diagnostic_motion_plus_2_plus_3p1_each_intermediate
    by_od["historical_mean_excess_total_seconds"] = by_od.historical_minus_current_seconds_mean * by_od["count"]
    output_table("by_od.csv", by_od)
    output_table("od_minimum_timing_signatures.csv", by_od[["start", "goal", "count", "node_path", "edge_count", "intermediate_nodes",
        "distance_meters", "pure_motion_seconds", "free_flow_current_seconds", "historical_dh_seconds_min",
        "historical_min_minus_free_flow", "diagnostic_motion_plus_2_plus_3p1_each_intermediate", "historical_min_minus_3p1_stage_signature",
        "physical_model_min_seconds", "physical_model_min_path", "current_dh_seconds_min",
        "diagnostic_3p1_physical_min_seconds", "diagnostic_3p1_physical_min_path"]])
    output_table("by_leg_kind.csv", grouped(df, ["leg_kind"], fields))
    output_table("by_bag_segment_count.csv", grouped(bag.reset_index(), ["segment_count"], ["historical_dh_seconds", "historical_hca_seconds", "current_dh_seconds", "delta"]))
    output_table("by_release_300s.csv", grouped(df, ["release_300s_bin"], fields))
    output_table("by_origin_release_300s.csv", grouped(df, ["start", "release_300s_bin"], fields))
    df["origin_density_quantile"] = pd.qcut(df.origin_release_300s_count, 10, duplicates="drop").astype(str)
    output_table("by_origin_release_density.csv", grouped(df, ["origin_density_quantile"], fields))
    df["gap_group"] = pd.cut(df.previous_same_origin_release_gap, [-np.inf, 0, 1, 2, 5, 10, 30, 60, np.inf], right=True).astype(str)
    output_table("by_previous_origin_release_gap.csv", grouped(df, ["gap_group"], fields))
    # Residue tests expose 0.2-second global/OD phases without inventing a delay.
    df["dh_tenth_residue_mod2"] = np.mod(np.rint(df.historical_completion_seconds * 10).astype(np.int64), 2)
    df["dh_tenth_residue_mod10"] = np.mod(np.rint(df.historical_completion_seconds * 10).astype(np.int64), 10)
    output_table("historical_completion_residues.csv", df.groupby(["start", "goal", "dh_tenth_residue_mod10"]).size().rename("count").reset_index())
    clean_fields = ["raw_bag_id", "segment_id", "segment_count", "leg_kind", "excel_row", "start", "goal", "release_seconds",
        *fields, "free_flow_current_seconds", "pure_motion_seconds", "edge_count", "intermediate_nodes",
        "origin_release_300s_count", "same_origin_release_count", "previous_same_origin_release_gap"]
    joined_bytes = df[clean_fields].to_csv(index=False, lineterminator="\n", float_format="%.9f").encode()
    (OUT / "paired_segments.csv.gz").write_bytes(gzip.compress(joined_bytes, mtime=0))
    output_table("largest_extra_delay_segments.csv", df.nlargest(30, "historical_minus_current_seconds")[clean_fields])
    output_table("smallest_historical_per_od.csv", df.loc[df.groupby(["start", "goal"]).historical_dh_seconds.idxmin(), clean_fields])
    raw = pd.read_csv(ROOT / "legacy/jichang_origin_readonly/inputdata.txt", sep=r"\s+")
    phase = df.merge(raw[["ID", "EntryTime(s)"]], left_on="raw_bag_id", right_on="ID", validate="many_to_one")
    phase["raw_entry_rounded_tenth_parity"] = np.rint(phase["EntryTime(s)"] * 10).astype(np.int64) % 2
    phase_rows = []
    for kind, group in phase.groupby("leg_kind"):
        phase_rows.append({"leg_kind": kind, "count": len(group),
            "historical_completion_even_tenth_count": int((group.dh_tenth_residue_mod2 == 0).sum()),
            "historical_completion_odd_tenth_count": int((group.dh_tenth_residue_mod2 == 1).sum()),
            "completion_parity_matches_rounded_raw_entry_fraction_rate": float((group.dh_tenth_residue_mod2 == group.raw_entry_rounded_tenth_parity).mean())})
    output_table("phase_vs_raw_entry.csv", pd.DataFrame(phase_rows))
    paired_phase = phase.pivot(index="raw_bag_id", columns="segment_id", values="dh_tenth_residue_mod2").dropna()
    within_delta = df.historical_minus_current_seconds - df.groupby(["start", "goal"]).historical_minus_current_seconds.transform("mean")
    within_density = df.origin_release_300s_count - df.groupby(["start", "goal"]).origin_release_300s_count.transform("mean")
    min_gap = float((by_od.historical_min_minus_free_flow * by_od["count"]).sum())
    total_gap = float(df.historical_minus_current_seconds.sum())
    below = df.current_excess_over_free_flow < -1e-7
    output_table("current_faster_than_isolated_route.csv", grouped(df[below], ["start", "goal"], ["current_excess_over_free_flow"]))
    summary = {"workbook_path": str(book), "workbook_sha256": sha(book),
        "primary_segments_sha256": sha(primary / "segments.csv"), "primary_runner_status": json.loads((primary / "runner_status.json").read_text()),
        "exact_matched_segments": len(df), "exact_shared_schedule_rows": len(df), "raw_bags": len(bag),
        "cached_DH_and_HCA_bag_aggregations_recomputed_exactly": True,
        "do_not_use_DH_column_F_as_row_duration": {"mismatching_rows": int((np.abs(dh.F - (dh.E - dh.D)) > 1e-7).sum()), "numeric_rows": int(dh.F.notna().sum())},
        "bag_metrics": {field: stats(bag[field]) for field in ["historical_dh_seconds", "historical_hca_seconds", "current_dh_seconds", "delta"]},
        "segment_metrics": {field: stats(df[field]) for field in fields},
        "historical_completion_tenth_precision_max_error": float(np.max(np.abs(df.historical_completion_seconds * 10 - np.rint(df.historical_completion_seconds * 10)))),
        "completion_tenth_parity_counts": {str(k): int(v) for k,v in df.dh_tenth_residue_mod2.value_counts().items()},
        "correlations": {x: (float(df.historical_minus_current_seconds.corr(df[x])) if df[x].nunique() > 1 else None) for x in ["current_excess_over_free_flow", "current_source_wait_seconds", "origin_release_300s_count", "all_release_300s_count", "same_origin_release_count", "historical_hca_seconds"]},
        "within_od_correlation_extra_delay_vs_origin_300s_release_count": float(within_delta.corr(within_density)),
        "all_shared_D_are_integer_seconds": bool((df.release_seconds % 1 == 0).all()),
        "all_origins_have_no_same_D_duplicate_release": bool((df.same_origin_release_count == 1).all()),
        "phase_vs_raw_entry": phase_rows,
        "same_bag_early_and_outbound_completion_parity_agreement": float((paired_phase[0] == paired_phase[1]).mean()),
        "minimum_node_timing_signature": {
            "od_count": len(by_od),
            "historical_min_within_point1_of_motion_plus_2_plus_3p1_each_intermediate": int((by_od.historical_min_minus_3p1_stage_signature.abs() < .1000001).sum()),
            "counterexample_to_fixed_3p1_service_with_same_map": by_od.loc[
                by_od.historical_dh_seconds_min < by_od.diagnostic_3p1_physical_min_seconds - 1e-7,
                ["start", "goal", "historical_dh_seconds_min", "diagnostic_3p1_physical_min_seconds"]].to_dict("records"),
            "note": "A diagnostic signature, not a recovered service coefficient. The 53-to-50 minimum rules out simply using 3.1 seconds at every intermediate node with the same lengths and 2-second source induction."},
        "minimum_gap_decomposition": {"weighted_minimum_offset_seconds_per_segment": min_gap / len(df),
            "weighted_minimum_offset_seconds_per_raw_bag": min_gap / len(bag),
            "fraction_of_total_historical_minus_current_gap": min_gap / total_gap,
            "remaining_variable_or_route_gap_seconds_per_raw_bag": (total_gap - min_gap) / len(bag),
            "note": "Accounting decomposition against isolated distance-shortest routes, not proof of causal congestion share."},
        "route_acceleration_observation": {"segments_faster_than_own_isolated_policy_route": int(below.sum()),
            "total_time_below_isolated_route_seconds_per_raw_bag": float(-df.loc[below, "current_excess_over_free_flow"].sum() / len(bag)),
            "note": "The isolated policy minimizes geometric travel score, not physical motion plus the reconstructed 3 seconds per intermediate node; it is not a global physical lower bound."},
        "historical_earlier_than_current_count": int((df.historical_minus_current_seconds < -1e-7).sum()),
        "historical_below_current_free_flow_count": int((df.historical_excess_over_current_free_flow < -1e-7).sum()),
        "paired_segments_uncompressed_sha256": hashlib.sha256(joined_bytes).hexdigest()}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    dependencies = [book, primary / "segments.csv", primary / "runner_status.json", ff_path,
        ROOT / "legacy/jichang_origin_readonly/map2.txt", ROOT / "legacy/jichang_origin_readonly/inputdata.txt"]
    manifest = {"schema": "czr005.feng_historical_timing_signatures.v1",
        "generator": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha(Path(__file__))},
        "dependencies": [{"path": p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p),
            "sha256": sha(p), "size_bytes": p.stat().st_size} for p in dependencies],
        "artifacts": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p), "size_bytes": p.stat().st_size}
            for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"],
        "report": {"path": "outputs/reports/feng_dh_historical_timing_signatures_20260905.md",
            "sha256": sha(ROOT / "outputs/reports/feng_dh_historical_timing_signatures_20260905.md")},
        "portable_review": "The published paired_segments.csv.gz numerical extract supports aggregate and row-level review without the external workbook or primary file. Full independent source extraction requires both files at their listed hashes."}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k,v in summary.items() if k not in {"primary_runner_status"}}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=BOOK)
    run(parser.parse_args().workbook)
