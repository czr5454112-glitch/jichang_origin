"""Offline descriptive mechanism evidence after a closed learned callback audit."""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path
import time

from audit_learned_callbacks_001 import (
    CYCLE, OUT, bound, digest, read, ref, rescore, ranker, sha)


def audit(name):
    started = time.perf_counter()
    directory = CYCLE / name
    assert "/" not in name and "\\" not in name and directory.parent == CYCLE
    verification_path = OUT / f"{name}_learned_callback_audit_001.json"
    verification = read(verification_path)
    assert verification["status"] == "passed_closed_callback_weight_and_raw_execution_audit"
    plan = bound(verification["artifacts"]["plan.json"])
    assert plan["information_variant"] in ("C01", "C11")
    reference_name = f"{plan['batch']}_N{plan['parent']['fleet']}_C00_P{plan['parent']['parent_seed']}_001"
    reference_dir = CYCLE / reference_name
    baseline_plan = read(reference_dir / "plan.json")
    baseline_receipt = read(reference_dir / "receipt.json")
    assert baseline_receipt["status"] == "complete"
    assert baseline_receipt["plan_sha256"] == sha(reference_dir / "plan.json")
    for key in ("parent", "input", "binary", "controller", "cost_window", "activate_at", "horizon", "sources"):
        if key == "input":
            assert baseline_plan[key]["sha256"] == plan[key]["sha256"]
            assert baseline_plan[key]["semantic_sha256"] == plan[key]["semantic_sha256"]
        else:
            assert baseline_plan[key] == plan[key], key
    assert baseline_plan["information_variant"] == "C00"
    result = bound(verification["artifacts"]["final_result.json.gz"])
    execution = bound(verification["artifacts"]["execution_evidence.json.gz"])
    baseline = read(reference_dir / "final_result.json.gz")
    assert baseline["physical_clock"] == result["physical_clock"] == plan["horizon"]
    arrivals, baseline_arrivals, baseline_loads = {}, {}, {}
    empty_starts = defaultdict(list)
    for event in result["receipts"]:
        if event["event"] == "BAG_ARRIVAL":
            arrivals[event["business_bag_id"]] = event
        if event["event"] == "LEG_START" and event["reason"] == "empty_return":
            empty_starts[event["tray_id"]].append(event)
    for event in baseline["receipts"]:
        if event["event"] == "BAG_ARRIVAL":
            baseline_arrivals[event["business_bag_id"]] = event
        if event["event"] == "LOAD_START":
            baseline_loads[event["business_bag_id"]] = event
    assert {k: v["time"] for k, v in arrivals.items()} == {
        k: v["time"] for k, v in baseline_arrivals.items()}
    result_jobs = {j["business_bag_id"]: j for j in result["jobs"]}
    baseline_jobs = {j["business_bag_id"]: j for j in baseline["jobs"]}
    eligible, direct_loads, exclusions = [], [], defaultdict(int)
    for selection in execution["rows"]:
        if not selection["decision_differs"]:
            continue
        for attempt in selection["attempts"]:
            if not attempt["complete_G1_execution_chain"]:
                exclusions["no_complete_G1"] += 1
                continue
            received, load = attempt["received_at"], attempt["next_load"]
            if received is None or load is None:
                exclusions["no_receive_or_next_load"] += 1
                continue
            request = attempt["actual_request"]
            if load["node"] != request["destination"]:
                exclusions["next_load_at_different_destination"] += 1
                continue
            intervening = [e for e in empty_starts[selection["tray_id"]]
                if received < e["time"] <= load["time"]]
            if intervening:
                exclusions["intervening_empty_relocation"] += 1
                continue
            bag = load["business_bag_id"]
            arrival = arrivals[bag]
            old_load = baseline_loads.get(bag)
            gain = old_load["time"] - load["time"] if old_load else None
            direct_loads.append({
                "audit_sequence": selection["audit_sequence"], "record_sha256": selection["record_sha256"],
                "owner_id": selection["owner_id"], "decision_at": selection["observed_at"],
                "tray_id": selection["tray_id"], "request_id": request["request_id"],
                "source": request["source"], "destination": request["destination"],
                "received_at": received, "arrival_at": arrival["time"], "next_load": load,
                "prearrival_ready": received < arrival["time"] - 1e-9,
                "baseline_same_bag_load": old_load,
                "same_bag_baseline_wait_minus_policy_wait_seconds": gain,
                "baseline_wait_gain_lower_bound_if_unloaded": (
                    result["physical_clock"] - load["time"] if old_load is None else None)})
            if received >= arrival["time"] - 1e-9:
                exclusions["received_after_or_at_actual_bag_arrival"] += 1
                continue
            assert received <= arrival["time"] <= load["time"]
            new_complete, old_complete = result_jobs[bag]["completed_at"], baseline_jobs[bag]["completed_at"]
            eligible.append({
                "audit_sequence": selection["audit_sequence"], "record_sha256": selection["record_sha256"],
                "owner_id": selection["owner_id"], "decision_at": selection["observed_at"],
                "tray_id": selection["tray_id"], "baseline_intent_at_this_callback": selection["baseline_intent"],
                "selected_intent": selection["chosen_intent"], "actual_request": request,
                "native_leg": attempt["native_leg"], "first_edge_at": attempt["first_edge_at"],
                "received_at": received, "actual_bag_arrival": arrival,
                "empty_ready_lead_seconds": arrival["time"] - received,
                "next_load": load, "baseline_same_bag_load": old_load,
                "same_bag_baseline_wait_minus_policy_wait_seconds": gain,
                "baseline_wait_gain_lower_bound_if_unloaded": (
                    result["physical_clock"] - load["time"] if old_load is None else None),
                "policy_bag_completed_at": new_complete if new_complete >= 0 else None,
                "baseline_bag_completed_at": old_complete if old_complete >= 0 else None,
                "same_bag_completion_gain_if_both_known_seconds": (
                    old_complete - new_complete if old_complete >= 0 and new_complete >= 0 else None),
                "intervening_empty_relocations_before_load": 0,
                "no_aggregate_or_isolated_causal_gain_attributed": True})
    chosen = next((r for r in eligible
        if r["same_bag_baseline_wait_minus_policy_wait_seconds"] is not None
        and r["same_bag_baseline_wait_minus_policy_wait_seconds"] > 0), eligible[0] if eligible else None)
    already_waiting = [r for r in direct_loads if not r["prearrival_ready"]]
    queued_positive = [r for r in already_waiting
        if r["same_bag_baseline_wait_minus_policy_wait_seconds"] is not None
        and r["same_bag_baseline_wait_minus_policy_wait_seconds"] > 0]
    queued_witness = max(queued_positive,
        key=lambda r: r["same_bag_baseline_wait_minus_policy_wait_seconds"], default=None)
    requested_replays = {r["audit_sequence"]: r for r in (chosen, queued_witness) if r is not None}
    if requested_replays:
        model = bound(plan["selected_model"]["checkpoint"])
        predictor = ranker.prepare_predictor(model)
        found = set()
        with gzip.open(directory / "callback_audit.jsonl.gz", "rt", encoding="utf8") as stream:
            for line in stream:
                packet = json.loads(line)
                row = packet["record"]
                if row["audit_sequence"] in requested_replays:
                    witness = requested_replays[row["audit_sequence"]]
                    assert digest(row) == packet["record_sha256"] == witness["record_sha256"]
                    witness["frozen_weight_actual_current_replay"] = rescore(row, model, predictor)
                    found.add(row["audit_sequence"])
                    if found == set(requested_replays):
                        break
        assert found == set(requested_replays), "chosen_actual_callback_not_found"
    gains = [r["same_bag_baseline_wait_minus_policy_wait_seconds"] for r in eligible
        if r["same_bag_baseline_wait_minus_policy_wait_seconds"] is not None]
    output = {
        "schema": "g31.foundation.offline_prearrival_mechanism_audit.v1",
        "name": name, "reference_name": reference_name,
        "status": "completed_descriptive_actual_chain_audit",
        "artifacts": {"script": ref(__file__), "callback_verification": ref(verification_path),
            "execution": verification["artifacts"]["execution_evidence.json.gz"],
            "policy_result": verification["artifacts"]["final_result.json.gz"],
            "reference_plan": ref(reference_dir / "plan.json"),
            "reference_receipt": ref(reference_dir / "receipt.json"),
            "reference_result": ref(reference_dir / "final_result.json.gz")},
        "same_input_sources_native_and_experiment_window": True,
        "information_variant": plan["information_variant"],
        "forecast_consumed_by_policy": plan["information_variant"] == "C11",
        "changed_decision_count": execution["proposed_decision_differences"],
        "prearrival_ready_and_direct_next_load_witnesses": len(eligible),
        "exclusion_counts_per_changed_attempt": dict(exclusions),
        "same_bag_known_load_comparison_counts": {
            "policy_wait_shorter": sum(x > 1e-9 for x in gains),
            "policy_wait_longer": sum(x < -1e-9 for x in gains),
            "equal": sum(abs(x) <= 1e-9 for x in gains),
            "baseline_load_unknown_at_horizon": len(eligible) - len(gains)},
        "all_eligible_witnesses": eligible,
        "selected_compact_witness": chosen,
        "all_direct_destination_load_comparisons": direct_loads,
        "already_waiting_bag_direct_load_comparison": {
            "count": len(already_waiting),
            "policy_wait_shorter": len(queued_positive),
            "policy_wait_longer": sum(r["same_bag_baseline_wait_minus_policy_wait_seconds"] is not None
                and r["same_bag_baseline_wait_minus_policy_wait_seconds"] < -1e-9 for r in already_waiting),
            "equal": sum(r["same_bag_baseline_wait_minus_policy_wait_seconds"] is not None
                and abs(r["same_bag_baseline_wait_minus_policy_wait_seconds"]) <= 1e-9 for r in already_waiting),
            "baseline_load_unknown_at_horizon": sum(
                r["same_bag_baseline_wait_minus_policy_wait_seconds"] is None for r in already_waiting)},
        "largest_known_wait_reduction_already_waiting_witness": queued_witness,
        "queued_witness_selection_limit": "Descriptive largest known same-bag wait reduction among all direct destination next loads after bag arrival; deliberately selected for mechanism illustration, not an unbiased effect estimate or one-action causal attribution.",
        "witness_selection_rule": "First chronologically eligible actual prearrival readiness witness with a known positive same-bag baseline wait difference; otherwise first eligible. All eligible witnesses and comparison counts are retained.",
        "limitations": [
            "This is a post-run descriptive native-event audit. Future arrivals and baseline outcomes are used only by this offline audit, never passed to the predictor.",
            "A C01 witness proves dispatch before actual arrival under current-only features; it does not demonstrate forecast use.",
            "Multiple policy decisions change the system. A same-bag wait difference cannot isolate the causal effect of this single transfer.",
            "Only an actual receive at the requested destination, before actual arrival, followed by a same-destination load without an intervening empty relocation qualifies.",
            "Unknown baseline load/completion times are preserved as unknown; any finite-horizon wait bound is explicitly labeled."],
        "fit_calls": 0, "native_jobs_started": 0, "runtime_sources_modified": False,
        "wall_seconds": time.perf_counter() - started}
    output_path = OUT / f"{name}_prearrival_mechanism_audit_001.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")
    return {"artifact": ref(output_path), "prearrival_witnesses": len(eligible),
        "comparison_counts": output["same_bag_known_load_comparison_counts"],
        "chosen": chosen, "exclusions": dict(exclusions)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    print(json.dumps(audit(parser.parse_args().name), ensure_ascii=False), flush=True)
