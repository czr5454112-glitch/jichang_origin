"""Pair the completed V5 population with historical DH and the frozen control."""
from pathlib import Path
import gzip
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5"
HIST = ROOT / "outputs/runtime/feng_dh_historical_signatures_20260905/paired_segments.csv.gz"
OUT = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_tail_review"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(x):
    x = np.asarray(x, dtype=float)
    return {"count": len(x), "min": float(x.min()), "mean": float(x.mean()),
            "median": float(np.median(x)), "p95": float(np.quantile(x, .95)),
            "p99": float(np.quantile(x, .99)), "max": float(x.max())}


def csv(name, frame):
    frame.to_csv(OUT / name, index=False, lineterminator="\n", float_format="%.9f")


def table(frame, groups, fields):
    rows = []
    for key, part in frame.groupby(groups, sort=True):
        if not isinstance(key, tuple): key = (key,)
        row = dict(zip(groups, key)); row["count"] = len(part)
        for field in fields:
            row.update({field + "_" + k: v for k, v in stats(part[field]).items() if k != "count"})
        row["v5_above_historical_od_p95_count"] = int(part.above_historical_od_p95.sum())
        row["v5_minus_historical_total_seconds"] = float(part.v5_minus_historical.sum())
        row["v5_minus_control_total_seconds"] = float(part.v5_minus_control.sum())
        row["positive_v5_minus_historical_seconds"] = float(part.v5_minus_historical.clip(lower=0).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def interval_area(start, end, bins):
    area = np.zeros(len(bins))
    first = int(bins[0])
    for left, right in zip(start, end):
        for b in range(int(left // 300), int(np.ceil(right / 300))):
            area[b-first] += max(0, min(right, (b+1)*300) - max(left, b*300))
    return area / 300


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    identity = json.loads((BASE / "run_identity.json").read_text())
    for name in ("segments.csv.gz", "bags.csv.gz", "summary.csv", "event_summary.csv"):
        assert sha(BASE / name) == identity["outputs"][name]
    assert hashlib.sha256(gzip.decompress((BASE / "segments.csv.gz").read_bytes())).hexdigest() == identity["outputs"]["segments.csv"]
    assert identity["status"] == "COMPLETE"
    historical = pd.read_csv(HIST)
    v5 = pd.read_csv(BASE / "segments.csv.gz")
    assert len(v5) == len(historical) == 43603
    assert (v5.status == "COMPLETED").all()
    keys = ["raw_bag_id", "segment_id", "start", "goal", "release_seconds"]
    fields = ["admission_time_seconds", "completion_time_seconds", "moving_ticks", "stopped_ticks", "hold_count"]
    df = historical.merge(v5[keys + fields], on=keys, validate="one_to_one")
    assert len(df) == 43603
    df["v5_seconds"] = df.completion_time_seconds - df.release_seconds
    df["v5_source_wait"] = df.admission_time_seconds - df.release_seconds
    df["v5_after_admission"] = df.v5_seconds - df.v5_source_wait
    df["control_after_admission"] = df.current_dh_seconds - df.current_source_wait_seconds
    df["v5_minus_control"] = df.v5_seconds - df.current_dh_seconds
    df["v5_minus_historical"] = df.v5_seconds - df.historical_dh_seconds
    df["source_wait_delta"] = df.v5_source_wait - df.current_source_wait_seconds
    df["after_admission_delta"] = df.v5_after_admission - df.control_after_admission
    df["v5_motion_seconds"] = df.moving_ticks * .2
    df["v5_edge_stopped_seconds"] = df.stopped_ticks * .2
    df["v5_accounting_remaining_seconds"] = df.v5_after_admission - df.v5_motion_seconds - df.v5_edge_stopped_seconds
    df["release_hour"] = (df.release_seconds // 3600).astype(int)
    df["release_300s_bin"] = (df.release_seconds // 300).astype(int)
    df["historical_od_p95"] = df.groupby(["start", "goal"]).historical_dh_seconds.transform(lambda x: x.quantile(.95))
    df["above_historical_od_p95"] = df.v5_seconds > df.historical_od_p95 + 1e-7
    columns = ["historical_dh_seconds", "current_dh_seconds", "v5_seconds", "v5_minus_historical", "v5_minus_control",
               "v5_source_wait", "current_source_wait_seconds", "source_wait_delta", "after_admission_delta"]
    by_od = table(df, ["start", "goal"], columns)
    csv("by_od.csv", by_od)
    by_leg = table(df, ["leg_kind"], columns)
    csv("by_leg_kind.csv", by_leg)
    csv("by_release_hour.csv", table(df, ["release_hour"], columns))
    csv("by_release_300s.csv", table(df, ["release_300s_bin"], columns))
    csv("by_od_release_hour.csv", table(df, ["start", "goal", "release_hour"], ["v5_minus_historical", "v5_minus_control", "v5_source_wait"]))
    bag = df.groupby("raw_bag_id").agg(segment_count=("segment_count", "first"),
        first_release=("release_seconds", "min"), historical=("historical_dh_seconds", "sum"),
        control=("current_dh_seconds", "sum"), v5=("v5_seconds", "sum"),
        historical_delta=("v5_minus_historical", "sum"), control_delta=("v5_minus_control", "sum"),
        source_wait_delta=("source_wait_delta", "sum"), after_admission_delta=("after_admission_delta", "sum"),
        source_wait=("v5_source_wait", "sum"))
    assert len(bag) == 28506
    native_bags = pd.read_csv(BASE / "bags.csv.gz").set_index("raw_bag_id")
    assert np.allclose(bag.v5, native_bags.loc[bag.index].table53_scheduled_interval_seconds, atol=1e-7, rtol=0)
    top_bag_threshold = bag.v5.quantile(.95)
    top_bag_ids = bag.index[bag.v5 >= top_bag_threshold - 1e-7]
    bag["first_release_hour"] = (bag.first_release // 3600).astype(int)
    bag_hour = []
    for hour, group in bag.groupby("first_release_hour"):
        row = {"first_release_hour": int(hour), "count": len(group), "top5_v5_bag_count": int(group.index.isin(top_bag_ids).sum())}
        for field in ("historical", "control", "v5", "historical_delta", "source_wait_delta", "after_admission_delta"):
            row.update({field + "_" + k: v for k,v in stats(group[field]).items() if k != "count"})
        bag_hour.append(row)
    csv("by_bag_first_release_hour.csv", pd.DataFrame(bag_hour))
    tail = df[df.raw_bag_id.isin(top_bag_ids)]
    csv("top5_percent_bags_by_leg.csv", table(tail, ["leg_kind"], columns))
    csv("top5_percent_bags_by_od.csv", table(tail, ["start", "goal"], columns))
    csv("top5_percent_bags_by_release_hour.csv", table(tail, ["release_hour"], columns))
    csv("largest_bag_times.csv", bag.nlargest(30, "v5").reset_index())
    csv("largest_segment_excess.csv", df.nlargest(40, "v5_minus_historical")[["raw_bag_id", "segment_id", "excel_row", "leg_kind", "start", "goal", "release_seconds", *columns, "free_flow_current_seconds", "v5_motion_seconds", "v5_edge_stopped_seconds", "v5_accounting_remaining_seconds"]])
    bins = np.arange(int(df.release_seconds.min() // 300), int(np.ceil(df.completion_time_seconds.max() / 300)))
    profile = pd.DataFrame({"bin": bins, "begin_seconds": bins * 300, "end_seconds": (bins + 1) * 300})
    profile["v5_mean_admitted_active_segments"] = interval_area(df.admission_time_seconds, df.completion_time_seconds, bins)
    profile["control_mean_admitted_active_segments"] = interval_area(df.release_seconds + df.current_source_wait_seconds, df.release_seconds + df.current_dh_seconds, bins)
    profile["v5_mean_source_pending_segments"] = interval_area(df.release_seconds, df.admission_time_seconds, bins)
    profile["control_mean_source_pending_segments"] = interval_area(df.release_seconds, df.release_seconds + df.current_source_wait_seconds, bins)
    profile["v5_excess_active"] = profile.v5_mean_admitted_active_segments - profile.control_mean_admitted_active_segments
    profile["v5_to_control_active_ratio"] = profile.v5_mean_admitted_active_segments / profile.control_mean_admitted_active_segments.replace(0, np.nan)
    csv("admitted_population_300s.csv", profile)
    selected = profile.v5_to_control_active_ratio >= 2
    episodes = []
    for _, group in profile[selected].groupby((~selected).cumsum()[selected]):
        episodes.append({"begin_seconds": int(group.begin_seconds.min()), "end_seconds": int(group.end_seconds.max()),
            "duration_seconds": len(group) * 300, "v5_mean_admitted_active_segments": float(group.v5_mean_admitted_active_segments.mean()),
            "control_mean_admitted_active_segments": float(group.control_mean_admitted_active_segments.mean()),
            "v5_mean_source_pending_segments": float(group.v5_mean_source_pending_segments.mean())})
    csv("episodes_with_twice_control_active.csv", pd.DataFrame(episodes))
    od_paths = pd.read_csv(ROOT / "outputs/runtime/feng_dh_historical_signatures_20260905/od_minimum_timing_signatures.csv")
    route_frame = df.merge(od_paths[["start", "goal", "node_path"]], on=["start", "goal"], validate="many_to_one")
    route_frame["isolated_route_uses_24_to_27"] = route_frame.node_path.str.contains(";24;27;", regex=False)
    route_hour = route_frame.groupby(["release_hour", "isolated_route_uses_24_to_27"]).agg(
        segment_count=("raw_bag_id", "size"), v5_mean_seconds=("v5_seconds", "mean"), historical_mean_seconds=("historical_dh_seconds", "mean"),
        control_mean_seconds=("current_dh_seconds", "mean")).reset_index()
    csv("isolated_route_24_to_27_hourly_demand_proxy.csv", route_hour)
    sum_gap = float(bag.control_delta.sum())
    positive_hist = float(bag.historical_delta.clip(lower=0).sum())
    summary = {"schema": "feng.dh.boundary_clearance_tail_review.v1", "segments": len(df), "bags": len(bag),
        "inputs": {p.relative_to(ROOT).as_posix(): sha(p) for p in [HIST, BASE / "segments.csv.gz", BASE / "bags.csv.gz", BASE / "run_identity.json",
            ROOT / "outputs/runtime/feng_dh_historical_signatures_20260905/od_minimum_timing_signatures.csv"]},
        "bag_metrics": {x: stats(bag[x]) for x in ["historical", "control", "v5", "historical_delta", "control_delta", "source_wait_delta", "after_admission_delta", "source_wait"]},
        "control_delta_decomposition": {"source_wait_fraction": float(bag.source_wait_delta.sum() / sum_gap), "after_admission_fraction": float(bag.after_admission_delta.sum() / sum_gap)},
        "v5_top5_percent_bags": {"threshold_seconds": float(top_bag_threshold), "count": len(top_bag_ids),
            "fraction_of_total_v5_minus_control": float(bag.loc[top_bag_ids].control_delta.sum() / sum_gap),
            "fraction_of_positive_v5_minus_historical": float(bag.loc[top_bag_ids].historical_delta.clip(lower=0).sum() / positive_hist),
            "source_wait_delta_seconds_per_bag": float(bag.loc[top_bag_ids].source_wait_delta.mean()),
            "after_admission_delta_seconds_per_bag": float(bag.loc[top_bag_ids].after_admission_delta.mean())},
        "bag_count_v5_above_historical_p95": int((bag.v5 > bag.historical.quantile(.95)).sum()),
        "bag_count_v5_above_historical_p99": int((bag.v5 > bag.historical.quantile(.99)).sum()),
        "bag_count_v5_above_historical_max": int((bag.v5 > bag.historical.max()).sum()),
        "bag_count_v5_slower_than_historical": int((bag.historical_delta > 1e-7).sum()),
        "bag_count_v5_faster_than_historical": int((bag.historical_delta < -1e-7).sum()),
        "bag_historical_mean_in_top5_v5": float(bag.loc[top_bag_ids].historical.mean()),
        "bag_control_mean_in_top5_v5": float(bag.loc[top_bag_ids].control.mean()),
        "bag_v5_mean_in_top5_v5": float(bag.loc[top_bag_ids].v5.mean()),
        "top5_v5_bag_first_release_hour_counts": {str(k): int(v) for k,v in bag.loc[top_bag_ids].first_release_hour.value_counts().sort_index().items()},
        "top5_v5_bag_first_segments_with_isolated_route_24_to_27": int(route_frame.loc[route_frame.raw_bag_id.isin(top_bag_ids) & (route_frame.segment_id == 0), "isolated_route_uses_24_to_27"].sum()),
        "v5_below_isolated_policy_route_segment_count": int((df.v5_seconds < df.free_flow_current_seconds - 1e-7).sum()),
        "caveat": "Distance-shortest isolated policy time is not a global physical lower bound. Source wait and post-admission time are exact; network concurrency is reconstructed from interval overlap, not node-specific queue length.",
        "correlations": {"v5_and_historical_segment_duration": float(df.v5_seconds.corr(df.historical_dh_seconds)),
            "v5_control_delta_and_historical_control_delta": float(df.v5_minus_control.corr(df.historical_dh_seconds-df.current_dh_seconds)),
            "v5_source_wait_and_post_admission_time": float(df.v5_source_wait.corr(df.v5_after_admission))},
        "network_active_twice_control_episodes": episodes,
        "top_6_ods_by_positive_historical_excess": by_od.nlargest(6, "positive_v5_minus_historical_seconds")[["start", "goal", "count", "v5_seconds_mean", "historical_dh_seconds_mean", "v5_minus_control_mean", "positive_v5_minus_historical_seconds"]].to_dict("records"),
        "accounting_remainder_min_seconds": float(df.v5_accounting_remaining_seconds.min())}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = ROOT / "outputs/reports/feng_dh_boundary_clearance_tail_review_20260905.md"
    manifest = {"schema": "feng.dh.boundary_clearance_tail_artifacts.v1", "inputs": summary["inputs"],
        "generator": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha(Path(__file__))},
        "report": {"path": report.relative_to(ROOT).as_posix(), "sha256": sha(report)},
        "artifacts": [{"path": p.relative_to(ROOT).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__": run()
