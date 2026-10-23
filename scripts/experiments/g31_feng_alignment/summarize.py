"""Extract full-denominator result tables and additive source-delay contrasts."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_feng_alignment import experiment, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", required=True, help="Name=run_directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, default=experiment.CANONICAL,
                        help="explicit map workload; defaults to the original Nanning campaign")
    parser.add_argument("--horizon", type=float, default=98259.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    canonical = metrics.read_jsonl(args.canonical)
    expected = {r["segment_id"]: r for r in canonical}
    arms, table, releases_by_arm = {}, [], {}
    phase_names = ("generator_minus_canonical", "entry_minus_generator", "finish_minus_entry", "finish_minus_canonical")
    for arg in args.arm:
        name, rawpath = arg.split("=", 1)
        if name in arms:
            raise ValueError("duplicate arm name")
        path = Path(rawpath)
        manifest = experiment.read(path / "manifest.json")
        if manifest["canonical"]["sha256"] != experiment.sha(args.canonical):
            raise ValueError("canonical source changed")
        rows = metrics.read_jsonl(path / "segments.jsonl")
        releases_by_arm[name] = {row["segment_id"]: row["released"] for row in rows}
        summary, _ = metrics.audit(canonical, rows, horizon=args.horizon)
        saved = experiment.read(path / "summary.json")
        if summary != saved["metrics"]:
            raise ValueError("full-population recalculation differs from saved metrics")
        full = summary["completed_transport_legs"] == len(canonical)
        phases, native_phases = {k: [] for k in phase_names}, {
            k: [] for k in ("reported_edge_travel_seconds", "reported_node_service_seconds", "reported_local_wait_seconds",
                           "in_network_wait_excluding_source_seconds", "network_unattributed_residual_seconds", "release_to_finish_counter_residual_seconds")}
        error = []
        for row in rows:
            if not row["completed"] or row["entered"] is None or row["released"] is None:
                continue
            source = expected[row["segment_id"]]
            a, b = row["released"] - source["pass_time"], row["entered"] - row["released"]
            c, total = row["finish"] - row["entered"], row["finish"] - source["pass_time"]
            for key, value in zip(phase_names, (a, b, c, total)):
                phases[key].append(value)
            error.append(abs(a + b + c - total))
            keys = tuple(native_phases)[:3]
            if all(row.get(key) is not None for key in keys):
                for key in keys:
                    native_phases[key].append(row[key])
                # The native total_local_wait counter includes source waiting.
                # Admission delay must be removed before adding it to network time.
                network_wait = row["reported_local_wait_seconds"] - b
                native_phases["in_network_wait_excluding_source_seconds"].append(network_wait)
                native_phases["network_unattributed_residual_seconds"].append(
                    c - row["reported_edge_travel_seconds"] - row["reported_node_service_seconds"] - network_wait)
                native_phases["release_to_finish_counter_residual_seconds"].append(
                    row["finish"] - row["released"] - sum(row[key] for key in keys))
        decomposition = {k: metrics.distribution(v) if len(v) == len(canonical) else None for k, v in phases.items()}
        native_decomposition = {k: metrics.distribution(v) if len(v) == len(canonical) else None for k, v in native_phases.items()}
        native = saved.get("native_summary") or {}
        wait = native.get("s4_wait_metrics") or {}
        wait_checks = None
        if wait:
            wait_checks = {
                "all_finite": all(math.isfinite(v) for v in wait.values()),
                "forecast_count_identity": wait["commit_forecast_count"] == wait["resolved_forecast_count"] + wait["censored_forecast_count"],
                "nonnegative_counts": all(wait[k] >= 0 for k in ("commit_forecast_count", "resolved_forecast_count", "censored_forecast_count")),
                "predicted_mae_bounds_bias": wait["predicted_post_wait_mae"] + 1e-7 >= abs(wait["predicted_post_wait_bias"]),
                "predicted_rmse_bounds_mae": wait["predicted_post_wait_rmse"] + 1e-7 >= wait["predicted_post_wait_mae"],
                "legacy_mae_bounds_bias": wait["legacy_queue_proxy_mae"] + 1e-7 >= abs(wait["legacy_queue_proxy_bias"]),
                "legacy_rmse_bounds_mae": wait["legacy_queue_proxy_rmse"] + 1e-7 >= wait["legacy_queue_proxy_mae"],
            }
            if not all(wait_checks.values()):
                raise ValueError(f"wait forecast aggregate invariant failed: {name}")
        primary = summary["full_population_segment_elapsed_from_canonical_pass_seconds"] or {}
        released = summary["full_population_segment_elapsed_from_actual_release_seconds"] or {}
        business = summary["full_population_observed_end_to_end_seconds"] or {}
        wall = next((manifest[k] for k in ("native_call_wall_seconds_excluding_serialization", "wall_seconds_original_native_call", "wall_seconds_original_run") if k in manifest), None)
        item = {"arm": name, "run_directory": str(path.resolve()), "reused": manifest["reused"],
                "execution_contract": manifest["execution_contract"], "release_contract": manifest["release_contract"],
                "completed_segments": summary["completed_transport_legs"], "offered_segments": len(canonical),
                "segment_canonical_mean_seconds": primary.get("mean"), "segment_canonical_p95_seconds": primary.get("p95"),
                "segment_canonical_p99_seconds": primary.get("p99"), "segment_actual_release_mean_seconds": released.get("mean"),
                "generator_minus_canonical_mean_seconds": (decomposition["generator_minus_canonical"] or {}).get("mean"),
                "entry_minus_generator_mean_seconds": (decomposition["entry_minus_generator"] or {}).get("mean"),
                "network_mean_seconds": (decomposition["finish_minus_entry"] or {}).get("mean"),
                "observed_business_mean_seconds": business.get("mean"), "completed_business": summary["completed_business_bags"],
                "offered_business": summary["offered_business_bags"], "ebs_causality_violations": summary["ebs_causality_violation_count"],
                "business_deadline_misses": summary["deadline_misses_including_unfinished"], "recorded_wall_seconds": wall,
                "wait_resolved_forecasts": wait.get("resolved_forecast_count"), "wait_censored_forecasts": wait.get("censored_forecast_count"),
                "post_wait_prediction_mae": wait.get("predicted_post_wait_mae"), "post_wait_prediction_bias": wait.get("predicted_post_wait_bias"),
                "same_run_legacy_queue_proxy_mae": wait.get("legacy_queue_proxy_mae")}
        table.append(item)
        arms[name] = {"table": item, "manifest": manifest, "metrics": summary, "full_segment_population_complete": full,
                      "source_decomposition_seconds": decomposition, "max_additive_identity_error_seconds": max(error, default=None),
                      "native_network_accounting_seconds": native_decomposition, "wait_metrics": wait, "wait_aggregate_invariants": wait_checks,
                      "evidence": [experiment.evidence(path / p) for p in ("manifest.json", "summary.json", "segments.jsonl")]}
    contrasts = []
    for left, right in itertools.combinations(arms, 2):
        a, b = arms[left], arms[right]
        x, y = a["table"]["segment_canonical_mean_seconds"], b["table"]["segment_canonical_mean_seconds"]
        phases = {k: a["source_decomposition_seconds"][k]["mean"] - b["source_decomposition_seconds"][k]["mean"]
                  if a["source_decomposition_seconds"][k] and b["source_decomposition_seconds"][k] else None for k in phase_names}
        contrasts.append({"left": left, "right": right,
                          "same_declared_execution_contract": a["manifest"]["execution_contract"] == b["manifest"]["execution_contract"],
                          "same_release_contract": a["manifest"]["release_contract"] == b["manifest"]["release_contract"],
                          "actual_release_epochs_exactly_equal": releases_by_arm[left] == releases_by_arm[right],
                          "segment_mean_left_minus_right_seconds": x - y if x is not None and y is not None else None,
                          "right_mean_reduction_vs_left_percent": 100 * (x-y)/x if x and y is not None else None,
                          "additive_difference_left_minus_right_seconds": phases,
                          "interpretation": "Additive phase accounting is descriptive, not a causal attribution across different execution/source rules."})
    with (args.output / "arm_table.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0])); writer.writeheader(); writer.writerows(table)
    experiment.write(args.output / "report_data.json", {
        "schema": "g31.feng_alignment.report_data.v1", "canonical": experiment.evidence(args.canonical),
        "script": experiment.evidence(Path(__file__)), "argv": sys.argv, "arms": arms, "contrasts": contrasts,
        "boundaries": [f"Primary denominator is all {len(canonical):,} independently scheduled transport segments; no unilateral EBS correction.",
                       "Business final-delivery values are observed only; EBS anomalies prevent full business causal-validity claims.",
                       "Same-HCA-release uses generator release_epoch, not successful-plan epoch; runtime admission and routing rules remain original.",
                       "Native total_local_wait includes source waiting. In-network wait subtracts admitted-minus-release before summing travel, service, and network wait; residuals remain explicit.",
                       "Wait forecast calibration uses actual resolved visits in that run; the legacy proxy is evaluated on those same visits, not a replay of another policy.",
                       "Java wall time and native-call wall time have different instrumentation boundaries; no cross-language CPU speedup is inferred."]})
    print(json.dumps({"output": str(args.output), "arms": list(arms), "contrasts": len(contrasts)}))


if __name__ == "__main__":
    main()
