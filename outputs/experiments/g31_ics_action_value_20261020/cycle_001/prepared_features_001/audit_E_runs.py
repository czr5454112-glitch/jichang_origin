"""Read-only closed E N18 development runs; never test input, fit or native."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker

OUT = Path(__file__).resolve().parent
CYCLE = OUT.parent
ALLOWED = {"E_N18_C00_P801_001", "E_N18_C10_P801_001"}


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def digest(value, ensure_ascii=False):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=ensure_ascii, allow_nan=False).encode("utf8")).hexdigest()


def bound(reference):
    assert sha(reference["path"]) == reference["sha256"]
    return read(reference["path"])


def verify_sources(directory, plan):
    for logical, expected in plan["sources"].items():
        assert sha(directory/"source"/logical) == expected, logical
    for key in ("input", "binary", "native_acceptance", "rule_freeze", "grid_freeze",
                "event_budget_calibration"):
        assert sha(plan[key]["path"]) == plan[key]["sha256"], key
    if plan["forecast_binding"] is not None:
        bound(plan["forecast_binding"])
    return len(plan["sources"])


def direct_cost(data, result, start, end):
    specifications = {row["business_bag_id"]: row for row in data["jobs"]}
    jobs = {row["business_bag_id"]: row for row in result["jobs"]}
    assert len(specifications) == len(data["jobs"]) == len(jobs) == len(result["jobs"]) == 28506
    assert set(specifications) == set(jobs)
    arrivals, completions, loads = {}, {}, {}
    for event in result["receipts"]:
        sink = {"BAG_ARRIVAL": arrivals, "UNLOAD_COMPLETE": completions, "LOAD_START": loads}.get(event["event"])
        if sink is not None:
            identity = event["business_bag_id"]
            assert identity not in sink
            sink[identity] = event["time"]
    costs, waits = [], []
    for identity, spec in specifications.items():
        arrival = spec["arrival"]
        completion = completions.get(identity, math.inf)
        assert (identity in arrivals) == (arrival <= end)
        if identity in arrivals:
            assert arrivals[identity] == arrival
        assert (completion < math.inf) == (jobs[identity]["completed_at"] >= 0)
        if completion < math.inf:
            assert completion == jobs[identity]["completed_at"]
        costs.append(max(0., min(completion, end)-max(arrival, start)))
        waits.append(max(0., min(loads.get(identity, math.inf), end)-max(arrival, start)))
    cost, waiting = math.fsum(costs), math.fsum(waits)
    return {"physical_population": len(jobs), "full_window_cost_bag_seconds": cost,
        "wait_for_tray_integral_bag_seconds": waiting,
        "loaded_processing_integral_bag_seconds": cost-waiting,
        "arrived_by_end": len(arrivals), "completed_by_end": len(completions),
        "arrived_unfinished_by_end": len(arrivals)-len(completions),
        "not_yet_arrived_by_end": len(jobs)-len(arrivals),
        "on_time_by_end": sum(at <= specifications[key]["deadline"] for key, at in completions.items()),
        "arrived_unfinished_past_deadline": sum(
            key in arrivals and key not in completions and spec["deadline"] < end
            for key, spec in specifications.items())}


def audit(name):
    assert name in ALLOWED
    directory = CYCLE/name
    receipt = read(directory/"receipt.json")
    plan = read(directory/"plan.json")
    worker = read(directory/"worker_report.json")
    assert receipt["worker"] == worker and receipt["plan_sha256"] == sha(directory/"plan.json")
    assert receipt["process"]["status"] == "exited" and receipt["process"]["exitcode"] == 0
    assert worker["status"] == receipt["status"] == "complete"
    assert worker["native_constructor_attempts"] == 1
    assert plan["batch"] == "E" and plan["parent"]["parent_seed"] == 801
    assert plan["parent"]["split"] == "dev" and plan["parent"]["fleet"] == 18
    source_count = verify_sources(directory, plan)
    data, result, evaluation = read(directory/"input.json"), read(directory/"final_result.json.gz"), read(directory/"evaluation.json")
    assert digest(data) == plan["input"]["semantic_sha256"] == evaluation["input_semantic_sha256"]
    assert result["physical_clock"] == worker["final_physical_time"] == 59400.
    assert result["advance"]["horizon_complete"] is True and len(result["trays"]) == 18
    cost = direct_cost(data, result, *plan["cost_window"])
    actual = evaluation["cost"]
    for key in ("physical_population", "arrived_by_end", "completed_by_end",
                "arrived_unfinished_by_end", "not_yet_arrived_by_end", "on_time_by_end",
                "arrived_unfinished_past_deadline"):
        assert cost[key] == actual[key], key
    assert abs(cost["full_window_cost_bag_seconds"]-actual["backlog_integral_bag_seconds"]) < 1e-6
    assert abs(cost["wait_for_tray_integral_bag_seconds"]-actual["waiting_for_tray_integral_bag_seconds"]) < 1e-6
    assert abs(cost["loaded_processing_integral_bag_seconds"]-actual["loaded_or_processing_integral_bag_seconds"]) < 1e-6
    print(json.dumps({"phase": "cost_and_all_sources_verified", "name": name, "cost": cost}), flush=True)
    audit_receipt = read(directory/"callback_audit_receipt.json")
    assert sha(directory/"callback_audit.jsonl.gz") == audit_receipt["sha256"]
    summary = read(directory/"planner_summary.json")
    counts, reasons, forecast_models = Counter(), Counter(), Counter()
    selectors, examples, p0 = [], [], None
    preloads = read(directory/"actual_plan_preload_receipts.json")
    if plan["information_variant"] == "C00":
        gate_status = read(directory/"actual_prepared_feature_gate_status.json")
        assert gate_status == worker["actual_prepared_feature_gate"]
        p0 = bound(gate_status["receipt"]["artifact"])
        callback = bound(p0["full_input"])["record"]
        comparison = bound(p0["comparison"])
        setup = bound(p0["setup"])
        assert p0["actual_candidate_count"] == 3 and p0["feature_count"] == 88
        assert comparison["historical_features"] == comparison["prepared_features"]
        assert len(comparison["candidates"]) == 3
        assert p0["current_context_build_count"] == p0["feature_matrix_build_count"] == 1
        assert not preloads and plan["forecast_binding"] is None
        assert p0["forward_calls"] == p0["forecast_models_consumed"] == 0
        assert digest({"observation": callback["observation"], "decision": callback["decision"]},
            ensure_ascii=True) == p0["original_callback_sha256"]
        for source in setup["current_sources"]:
            assert sha(source["path"]) == source["sha256"]
        for source in setup["historical_sources"]:
            assert sha(source["path"]) == source["sha256"]
        segment = next(item for item in worker["segments"] if item["target"] >= p0["at"])
        segment_data = read(Path(segment["raw"]))
        ticks = [tick for tick in segment_data["control_records"] if tick["tick"] == p0["callback_sequence"]]
        assert len(ticks) == 1 and ticks[0]["at"] == p0["at"]
        owner = next(item for item in ticks[0]["owner_decisions"] if item["owner_id"] == p0["owner_id"])
        assert owner["decision"] == callback["decision"] and owner["offline_evaluator_ms"] >= 1000.*gate_status["receipt"]["hook_total_wall_seconds"]
        p0 = {"status": p0["status"], "physical_time": p0["at"],
            "actual_batch_size_tested": 3, "actual_batch_size_maximum": gate_status["actual_maximum_batch_size"],
            "feature_count": 88, "features_exact": True, "one_current_one_matrix": True,
            "hook_total_wall_seconds_including_legacy_comparison_and_storage": gate_status["receipt"]["hook_total_wall_seconds"],
            "stage_seconds": p0["stage_seconds"], "storage": p0["storage"],
            "receipt_storage": gate_status["receipt"]["receipt_storage"],
            "protocol_offline_evaluator_ms": owner["offline_evaluator_ms"],
            "protocol_excludes_offline_diagnostic": "excluding_offline" in owner["timing_scope"],
            "full_input_matches_native_protocol_initial_decision": True,
            "full_input_matches_hash_chained_actor_callback": False,
            "native_13_candidate_gate_met": False, "historical_13_candidate_saved_replay_is_separate": True,
            "forward_calls": 0, "deployment_latency_certified": False,
            "new_pair_ranker_performance_claimed": False, "native_segment": ref(segment["raw"])}
    previous, count = "0"*64, 0
    with gzip.open(directory/"callback_audit.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            envelope = json.loads(line)
            row = envelope["record"]
            assert row["audit_sequence"] == count and row["previous_record_sha256"] == previous
            assert digest(row) == envelope["record_sha256"]
            previous, count = envelope["record_sha256"], count+1
            counts[row["status"]] += 1
            if row["status"] == "reference_fallback":
                reasons[row["reason"]] += 1
            if p0 is not None and row["observed_at"] == p0["physical_time"] and row["owner_id"] == callback["owner_id"]:
                assert row["observation"] == callback["observation"] and row["chosen_decision"] == callback["decision"]
                p0["full_input_matches_hash_chained_actor_callback"] = True
                p0["actor_record_sha256"] = envelope["record_sha256"]
            forecast = row.get("forecast_evidence")
            if forecast is not None:
                inference = {"parent": row["inference_parent"], "observation": row["observation"],
                    "forecast_evidence": forecast}
                ranker._forecast(inference)
                assert forecast["plan_receipt"] == preloads[row["owner_id"]]
                forecast_models[forecast["model_id"]] += 1
                assert row["selector_wall_ms"] >= 0
                selectors.append(row["selector_wall_ms"])
                if len(examples) < 3 and row.get("predicted_patch_advantage", 0.) != 0.:
                    examples.append({"record_sha256": envelope["record_sha256"],
                        "observed_at": row["observed_at"], "owner": row["owner_id"],
                        "selected_action_id": row["selected_action_id"],
                        "predicted_patch_advantage": row["predicted_patch_advantage"],
                        "forecast_model_id": forecast["model_id"],
                        "forecast_sha256": forecast["forecast_sha256"],
                        "actual_owner_plan_receipt_sha256": forecast["plan_receipt"]["receipt_sha256"]})
            elif plan["information_variant"] == "C00":
                assert "inference_rows" not in row
    assert count == audit_receipt["records"] == summary["counts"]["recorded_callbacks"]
    assert previous == audit_receipt["tail_record_sha256"]
    assert p0 is None or p0["full_input_matches_hash_chained_actor_callback"]
    if plan["information_variant"] == "C10":
        assert sum(forecast_models.values()) == summary["counts"].get("actual_scored_callbacks", 0)
    execution = read(directory/"execution_evidence.json.gz")
    execution_counts = {key: item for key, item in execution.items() if key != "rows"}
    g1 = sum(row["decision_differs"] and any(attempt["complete_G1_execution_chain"]
        for attempt in row["attempts"]) for row in execution["rows"])
    assert g1 == execution_counts["different_decision_with_complete_G1_chain"]
    final = {"schema": "g31.airport.closed_E_independent_audit.v1",
        "name": name, "status": "passed_closed_original_artifact_audit",
        "parent_split": "dev", "source_archive_files_verified": source_count,
        "source_contract": {key: plan[key] for key in ("binary", "rule_freeze", "grid_freeze")},
        "artifacts": [ref(directory/name) for name in ("plan.json", "receipt.json", "worker_report.json",
            "input.json", "final_result.json.gz", "evaluation.json", "callback_audit.jsonl.gz",
            "callback_audit_receipt.json", "planner_summary.json", "execution_evidence.json.gz")],
        "complete_population_cost_independently_recomputed": cost,
        "callback_stream_hash_chain_verified": True, "callback_records": count,
        "callback_status_counts": dict(counts), "fallback_reasons": dict(reasons),
        "actual_forecast_models_consumed": dict(forecast_models), "forecast_examples": examples,
        "selector_current_features_forward_call_count": len(selectors),
        "selector_median_ms": sorted(selectors)[len(selectors)//2] if selectors else None,
        "execution": execution_counts, "actual_native_prepared_feature_gate": p0,
        "test_data_opened": False, "fit_calls": 0, "new_native_jobs": 0,
        "strict_nonharm_certified": False, "learned_RL_benefit_established": False}
    target = OUT/(name+"_independent_audit.json")
    with target.open("x", encoding="utf8") as stream:
        json.dump(final, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"path": str(target), "cost": cost, "callback_counts": dict(counts),
        "fallback_reasons": dict(reasons), "forecasts": dict(forecast_models),
        "execution": execution_counts, "p0": p0}, indent=2), flush=True)


if __name__ == "__main__":
    audit(sys.argv[1])
