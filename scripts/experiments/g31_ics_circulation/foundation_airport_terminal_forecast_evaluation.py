"""Reproducible offline TRAIN calibration / DEV demand study; zero native starts.

The default sources are two closed C10 TRAIN prefixes and one complete legacy
DEV trajectory. Actual native BAG_ARRIVAL receipts supply labels. DEV forecasts
are explicit offline reconstructions from the public schedule and frozen B1;
they are not claimed as callbacks consumed by that legacy actor.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import copy
import gzip
import hashlib
import json
from pathlib import Path

from . import foundation_airport_joint_calendar as calendar
from . import foundation_airport_loader_mapping as loader_mapping
from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_predictor as predictor

ROOT = Path(__file__).resolve().parents[3]
CYCLE = ROOT / "outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001"
TRAIN_RUNS = ("G05_P2101_C10", "G08_P2102_C10")
DEV_RUN = "JOINT_bridge_R0_legacy_P2201_001"


def require(value, reason):
    if not value:
        raise ValueError("terminal_forecast_evaluation:" + reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def bound(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def load_closed_run(directory, *, split):
    """Verify process closure and count actual receipts, never offered future jobs."""
    directory = Path(directory)
    plan, worker, receipt = (read(directory/name) for name in ("plan.json", "worker_report.json", "receipt.json"))
    require(plan["parent"]["split"] == split, "registered_source_split")
    require(receipt["plan_sha256"] == sha(directory/"plan.json") and receipt["worker"] == worker,
            "source_process_binding")
    require(receipt["process"].get("exitcode") == 0 and worker.get("process_status") == "completed"
            and worker.get("scientific_status") == "closed", "completed_native_source")
    terminal = read(directory/"terminal_evidence.json.gz")
    end = worker["final_physical_time"]
    require(terminal["physical_clock"] == end and terminal["advance"]["horizon_complete"] is True
            and terminal["advance"]["status"] == "reached", "closed_physical_prefix")
    source = plan["input"]
    require(sha(source["path"]) == source["sha256"], "native_input_binding")
    native_input = read(source["path"])
    jobs = {row["business_bag_id"]: row for row in native_input["jobs"]}
    seen, arrivals = set(), {}
    for event in terminal["receipts"]:
        if event["event"] != "BAG_ARRIVAL":
            continue
        identity = event["business_bag_id"]
        require(identity in jobs and identity not in seen, "unique_actual_BAG_ARRIVAL")
        seen.add(identity)
        job = jobs[identity]
        require(0 <= event["time"] <= end and job["arrival"] == event["time"] and job["origin"] == event["node"],
                "actual_arrival_time_and_station")
        arrivals.setdefault(f"airport_node_{event['node']}", []).append(event["time"])
    require(seen == {key for key, job in jobs.items() if job["arrival"] <= end}, "complete_arrived_prefix_only")
    for times in arrivals.values():
        times.sort()
    provenance = {name: bound(directory/name) for name in
                  ("plan.json", "worker_report.json", "receipt.json", "terminal_evidence.json.gz")}
    provenance.update(native_input=dict(source), parent=plan["parent"], physical_clock=end,
                      native_arrival_count=len(seen), future_jobs_used_as_arrival_labels=False)
    provenance["source_evidence_id"] = demand.digest(provenance)
    return plan, arrivals, provenance


def count(arrivals, station, left, right):
    times = arrivals.get(station, [])
    return bisect_right(times, right)-bisect_right(times, left)


def training_rows(directory):
    plan, arrivals, provenance = load_closed_run(directory, split="train")
    decisions_path = Path(directory)/"decisions.json.gz"
    provenance["decision_stream"] = bound(decisions_path)
    records = read(decisions_path)
    parent = plan["parent"]
    start, end = parent["calendar_start_epoch_seconds"], provenance["physical_clock"]
    by_time = {}
    for decision in records:
        binding = decision.get("forecast_binding")
        if binding is None:
            continue
        origin = decision["decision_time"]
        if origin < 7200. or origin+1800. > end or (origin-7200.) % 1800. != 0:
            continue
        require(binding["actual_callback_consumption"] is True
                and binding["forecast_provenance"] == "actual_callback_received"
                and binding["forecast_sha256"] == calendar.public_digest(binding["forecast"]),
                "actual_callback_forecast_binding")
        forecast = binding["forecast"]
        require(forecast["forecast_origin"] == origin and forecast["owner_scope"] == decision["owner_id"],
                "current_callback_owner_and_time")
        if origin in by_time:
            require(by_time[origin]["new_demand_mean_by_region"] == forecast["new_demand_mean_by_region"],
                    "owner_summaries_same_population_no_duplicate_training")
        else:
            by_time[origin] = forecast
    expected_times = list(range(7200, int(end)-1800+1, 1800))
    require(sorted(by_time) == expected_times, "complete_nonoverlapping_training_forecast_windows")
    rows = []
    for origin, raw in sorted(by_time.items()):
        forecast = demand.rebin_forecast(raw, bin_edges_seconds=demand.bin_edges("300"))
        for station in sorted(forecast["new_demand_mean_by_region"]):
            expected = demand.expected_arrivals(forecast, origin, origin+1800., owner=forecast["owner_scope"], station=station)
            require(expected is not None, "known_training_expected_count")
            rows.append({"label_id": demand.digest([parent["parent_group"], station, origin, 1800]),
                "parent_id": parent["parent_group"], "split": "train", "station": station,
                "expected_arrivals": expected, "actual_arrivals": count(arrivals, station, origin, origin+1800.),
                "interval_start_epoch_seconds": start+origin, "interval_end_epoch_seconds": start+origin+1800.,
                "issued_at_epoch_seconds": start+origin, "label_available_at_epoch_seconds": start+end,
                "provenance_kind": "actual_arrival_count", "label_status": "mature",
                "forecast_sha256": demand.digest(forecast), "source_evidence_id": provenance["source_evidence_id"],
                "base_model_sha256": raw["model_sha256"], "mapping_sha256": raw["airport_mapping_sha256"]})
    return rows, plan, provenance


def reconstruct_forecast(binding, mapping, *, now, owner):
    """Offline only: identical public B1 parameters and mapping, no actual receipt claim."""
    checkpoint, manifest = calendar._validate_binding(binding)
    start = manifest["target_parent"]["calendar_start_epoch_seconds"]
    plan = copy.deepcopy(binding["absolute_plan_template"])
    plan["owner_scope"] = owner
    regional = calendar.arrays.predict(plan, checkpoint, now=start+now, owner=owner,
                                       observed_counts=None, horizon_seconds=1800)
    forecast = loader_mapping.project_forecast(regional, mapping, now=start+now, owner=owner)
    forecast["forecast_origin"] = float(now)
    forecast["absolute_bin_edges"] = [value-start for value in forecast["absolute_bin_edges"]]
    forecast["remaining_support_until"] -= start
    forecast["information_cutoffs"] = {key: None if value is None else value-start
                                       for key, value in forecast["information_cutoffs"].items()}
    forecast["calendar_provenance"] = {"calendar_start_epoch_seconds": start,
        "forecast_provenance": "offline_reconstruction_from_predeclared_static_schedule",
        "actual_callback_consumption": False, "observed_future_counts_used": False,
        "binding_sha256": binding["binding_sha256"]}
    return forecast


def run_study(output, *, cycle=CYCLE):
    output, cycle = Path(output), Path(cycle)
    require(not output.exists(), "fresh_evidence_output")
    rows, train_provenance, train_plans = [], [], []
    for name in TRAIN_RUNS:
        current, plan, source = training_rows(cycle/"runs"/name)
        rows.extend(current)
        train_provenance.append(source)
        train_plans.append(plan)
    closed = max(row["label_available_at_epoch_seconds"] for row in rows)
    model = predictor.fit(rows, train_parent_ids=[plan["parent"]["parent_group"] for plan in train_plans],
        training_labels_closed_at_epoch_seconds=closed, model_available_at_epoch_seconds=closed+1.,
        bin_edges_seconds=demand.bin_edges("300"))
    dev_plan, arrivals, dev_source = load_closed_run(cycle/"runs"/DEV_RUN, split="dev")
    parent = dev_plan["parent"]
    require(dev_source["physical_clock"] == 59400., "complete_fixed_DEV_physical_window")
    mapping_ref = train_plans[0]["mapping"]
    require(all(plan["mapping"]["sha256"] == mapping_ref["sha256"] for plan in train_plans)
            and sha(mapping_ref["path"]) == mapping_ref["sha256"], "same_TRAIN_mapping_artifact")
    mapping = read(mapping_ref["path"])
    binding = calendar.load_calendar_binding(parent)
    records = []
    for origin in range(7200, 59400-1800+1, 1800):
        raw = reconstruct_forecast(binding, mapping, now=float(origin), owner="offline:all_loader_demand")
        forecasts = {"TF-B1-"+mode: demand.rebin_forecast(raw, bin_edges_seconds=demand.bin_edges(mode))
                     for mode in ("60", "300", "600", "near_fine")}
        forecasts["TF-predictor"] = predictor.transform(model, forecasts["TF-B1-300"],
                                                       now=float(origin), parent_id=parent["parent_group"])
        start = parent["calendar_start_epoch_seconds"]
        labels = [{"station": station, "window_seconds": window,
                   "actual_arrivals": count(arrivals, station, origin, origin+window),
                   "label_available_at_epoch_seconds": start+dev_source["physical_clock"],
                   "source_evidence_id": dev_source["source_evidence_id"]}
                  for station in sorted(raw["new_demand_mean_by_region"]) for window in (300, 900, 1800)]
        records.append({"parent_id": parent["parent_group"], "split": "dev", "predictions": forecasts,
            "labels": labels, "observed_through_epoch_seconds": start+dev_source["physical_clock"]})
    report = predictor.evaluate_common_windows(records, model=model)
    report.update(training_window_physical_seconds=[7200., 18000.],
        evaluation_window_physical_seconds=[7200., 59400.],
        forecast_origins_stride_seconds=1800, same_B1_and_loader_mapping=True,
        DEV_forecast_provenance="offline_public_schedule_reconstruction_not_actual_legacy_callback",
        deployment_selection="candidate_only_not_promoted_by_this_offline_study",
        training_coverage_limitation="Only early 3-hour TRAIN prefixes; no full-day calibration guarantee.")
    provenance = {"schema": "g31.terminal_forecast_offline_study.v1", "train": train_provenance,
        "dev": dev_source, "mapping": mapping_ref,
        "source_files": {name: bound(Path(__file__).parent/name) for name in
                         (Path(__file__).name, "foundation_airport_terminal_predictor.py", "foundation_airport_terminal_forecast.py")},
        "model_sha256": model["sha256"], "training_label_rows": len(rows), "evaluation_records": len(records),
        "train_parent_selection": list(TRAIN_RUNS), "dev_parent_selection": DEV_RUN,
        "selection_uses_service_outcome": False, "native_starts": 0, "RL_predictor": "not_implemented",
        "future_truth_is_offline_labels_only": True, "DEV_consumed_for_model_fit": False,
        "training_calendar_is_simulated_availability_not_host_file_creation_time": True}
    output.mkdir(parents=True)
    for name, value in (("model.json", model), ("evaluation.json", report), ("provenance.json", provenance)):
        (output/name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    for name, value in (("training_rows.json.gz", rows), ("evaluation_records.json.gz", records)):
        with gzip.open(output/name, "wt", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"model": bound(output/"model.json"), "evaluation": bound(output/"evaluation.json"),
            "training_rows": len(rows), "evaluation_records": len(records), "native_starts": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-cycle", type=Path, default=CYCLE)
    args = parser.parse_args()
    print(json.dumps(run_study(args.output, cycle=args.source_cycle), indent=2))


if __name__ == "__main__":
    main()
