"""Aggregate only after all 18 named learned audits exist; never poll or refit."""
from __future__ import annotations
import argparse
from collections import Counter
import datetime
import json
import math
from pathlib import Path

from audit_learned_callbacks_001 import OUT, CYCLE, bound, read, ref, sha


def execution_counts(execution):
    counts = Counter({key: 0 for key in (
        "changed_callbacks", "changed_callbacks_with_submission",
        "changed_callbacks_with_G1", "changed_callbacks_without_G1",
        "changed_callbacks_with_final_native_rejection", "changed_actual_attempts",
        "changed_attempts_with_G1", "changed_attempts_final_native_rejected")})
    reasons, missing = Counter(), Counter()
    for row in execution["rows"]:
        if not row["decision_differs"]:
            continue
        counts["changed_callbacks"] += 1
        attempts = row["attempts"]
        counts["changed_callbacks_with_submission"] += bool(attempts)
        counts["changed_callbacks_with_G1"] += any(a["complete_G1_execution_chain"] for a in attempts)
        counts["changed_callbacks_without_G1"] += not any(a["complete_G1_execution_chain"] for a in attempts)
        counts["changed_callbacks_with_final_native_rejection"] += any(
            a.get("native_transfer_at_export") is not None
            and a["native_transfer_at_export"]["status"] == "rejected" for a in attempts)
        if not attempts:
            missing["no_actual_submission"] += 1
        for attempt in attempts:
            counts["changed_actual_attempts"] += 1
            counts["changed_attempts_with_G1"] += attempt["complete_G1_execution_chain"]
            transfer = attempt.get("native_transfer_at_export")
            rejected = transfer is not None and transfer["status"] == "rejected"
            counts["changed_attempts_final_native_rejected"] += rejected
            if rejected:
                reasons[transfer.get("reason", "")] += 1
            if not attempt["complete_G1_execution_chain"]:
                for key, missing_key in (
                    ("selected_intent_matches_actual_submission", "intent_submission_mismatch"),
                    ("request_matches_native_transfer_entity", "native_transfer_entity_not_verified"),
                    ("native_leg_matches_entity_and_endpoints", "native_leg_endpoints_not_verified"),
                    ("positive_delivered_ack", "no_positive_delivered_ACK")):
                    if attempt.get(key) is not True:
                        missing[missing_key] += 1
                if attempt.get("first_edge_at") is None:
                    missing["no_first_edge"] += 1
    return dict(counts), dict(reasons), dict(missing)


def whole_run_native_summary(result, execution):
    """Keep failures outside the compared candidate separate from G1 coverage."""
    compared_requests = {
        a["actual_request"]["request_id"]
        for row in execution["rows"] for a in row["attempts"]
        if isinstance(a.get("actual_request"), dict)
        and "request_id" in a["actual_request"]}
    legs = {leg["runtime_id"]: leg for leg in result["leg_identities"]}
    quarantined = []
    for tray in result["trays"]:
        if tray["mode"] == "quarantined":
            quarantined.append({"tray": tray, "active_leg_identity": legs.get(tray["active_leg"])})
    failed_transfers = []
    for transfer in result["transfers"]:
        if transfer["status"] == "failed":
            failed_transfers.append({
                **transfer,
                "appears_in_compared_action_execution_rows":
                    transfer["request_id"] in compared_requests})
    return {
        "native_summary_failed_count": result["native_summary"]["failed_count"],
        "business_job_status_counts": dict(Counter(j["status"] for j in result["jobs"])),
        "tray_mode_counts": dict(Counter(t["mode"] for t in result["trays"])),
        "quarantined_trays": quarantined,
        "failed_transfers": failed_transfers,
        "scope": "Whole-run final native state. This includes failures outside the compared selected action and is separate from changed/G1/rejected counts."}


def aggregate():
    grid_path = CYCLE / "prospective_evaluation_grid_001.json"
    grid = read(grid_path)
    names = [r["name"] for r in grid["rows"]
        if r["batch"] in ("D", "G") and r["variant"] in ("C01", "C11")]
    assert len(names) == len(set(names)) == 18
    required = [OUT / f"{name}_{suffix}.json" for name in names
        for suffix in ("learned_callback_audit_001", "prearrival_mechanism_audit_001")]
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        raise ValueError("all_18_closed_audits_required_before_aggregate:" + ",".join(missing))
    rows, artifacts = [], {}
    total_counts, total_rejections, total_missing = Counter(), Counter(), Counter()
    prearrival_counts, queued_counts = Counter(), Counter()
    callback_count = scored_count = main_replays = unique_replays = 0
    selector_sum = planner_sum = persistence_sum = branch_wall_sum = 0.
    strict_positive = []
    for name in names:
        audit_path = OUT / f"{name}_learned_callback_audit_001.json"
        mechanism_path = OUT / f"{name}_prearrival_mechanism_audit_001.json"
        audit, mechanism = read(audit_path), read(mechanism_path)
        assert audit["status"] == "passed_closed_callback_weight_and_raw_execution_audit"
        assert mechanism["status"] == "completed_descriptive_actual_chain_audit"
        assert audit["name"] == mechanism["name"] == name
        assert audit["callback_hash_chain_complete"] is True and audit["parser_check_on_E"] is False
        assert mechanism["artifacts"]["callback_verification"] == ref(audit_path)
        assert all(audit[k] == 0 for k in ("fit_calls", "native_jobs_started"))
        assert all(mechanism[k] == 0 for k in ("fit_calls", "native_jobs_started"))
        assert audit["runtime_sources_modified"] is False and mechanism["runtime_sources_modified"] is False
        assert sha(audit["audit_script"]["path"]) == audit["audit_script"]["sha256"]
        assert sha(mechanism["artifacts"]["script"]["path"]) == mechanism["artifacts"]["script"]["sha256"]
        execution = bound(audit["artifacts"]["execution_evidence.json.gz"])
        counts, reasons, gaps = execution_counts(execution)
        native_summary = whole_run_native_summary(
            bound(audit["artifacts"]["final_result.json.gz"]), execution)
        verified = audit["execution_counts_independently_joined"]
        assert counts["changed_callbacks"] == verified["proposed_decision_differences"]
        assert counts["changed_callbacks_with_G1"] == verified["different_decision_with_complete_G1_chain"]
        assert counts["changed_callbacks_with_submission"] == verified["different_decision_with_actual_submission"]
        assert verified["mismatched_actual_submission_count"] == 0
        total_counts.update(counts)
        total_rejections.update(reasons)
        total_missing.update(gaps)
        callback_count += audit["callback_records"]
        scored_count += audit["actual_scored_callbacks"]
        replays = audit["fixed_weight_replays"]
        assert all(r["absolute_score_error"] <= 1e-7 and r["outcome_or_target_fields_used"] is False
            and r["current_validation_retained"] is True for r in replays)
        main_replays += len(replays)
        replay_ids = {r["audit_sequence"] for r in replays}
        for key in ("selected_compact_witness", "largest_known_wait_reduction_already_waiting_witness"):
            witness = mechanism.get(key)
            if witness:
                replay = witness["frozen_weight_actual_current_replay"]
                assert replay["absolute_score_error"] <= 1e-7
                assert replay["outcome_or_target_fields_used"] is False
                replay_ids.add(replay["audit_sequence"])
        unique_replays += len(replay_ids)
        assert mechanism["prearrival_ready_and_direct_next_load_witnesses"] == len(
            mechanism["all_eligible_witnesses"])
        pre = mechanism["same_bag_known_load_comparison_counts"]
        queue = mechanism["already_waiting_bag_direct_load_comparison"]
        assert sum(pre.values()) == mechanism["prearrival_ready_and_direct_next_load_witnesses"]
        prearrival_counts.update(pre)
        queued_counts.update(queue)
        for witness in mechanism["all_eligible_witnesses"]:
            gain = witness["same_bag_baseline_wait_minus_policy_wait_seconds"]
            if gain is not None and gain > 1e-9:
                strict_positive.append({
                    "branch": name, "audit_sequence": witness["audit_sequence"],
                    "request_id": witness["actual_request"]["request_id"],
                    "tray_id": witness["tray_id"], "destination": witness["actual_request"]["destination"],
                    "bag_id": witness["next_load"]["business_bag_id"],
                    "decision_at": witness["decision_at"], "received_at": witness["received_at"],
                    "arrival_at": witness["actual_bag_arrival"]["time"],
                    "ready_lead_seconds": witness["empty_ready_lead_seconds"],
                    "same_bag_wait_difference_seconds": gain,
                    "same_bag_completion_difference_if_known_seconds":
                        witness["same_bag_completion_gain_if_both_known_seconds"],
                    "forecast_consumed_by_policy": mechanism["forecast_consumed_by_policy"]})
        timings = audit["timing"]
        selector = timings["selector_current_features_and_fixed_forward"]
        planning = timings["planner_before_audit_stream"]
        persistence = timings["callback_audit_persistence"]
        assert selector["count"] == audit["actual_scored_callbacks"]
        assert planning["count"] == persistence["count"] == audit["callback_records"]
        selector_sum += selector["sum_ms"]
        planner_sum += planning["sum_ms"]
        persistence_sum += persistence["sum_ms"]
        branch_wall_sum += timings["native_branch_process_wall_seconds"]
        artifacts[name] = {"callback_audit": ref(audit_path), "mechanism_audit": ref(mechanism_path)}
        rows.append({
            "name": name, "variant": audit["information_variant"],
            "parent_seed": audit["parent"]["parent_seed"], "fleet": audit["parent"]["fleet"],
            "training_domain": audit["selected_model"]["training_domain"],
            "model_seed": audit["selected_model"]["seed"],
            "model_id": audit["selected_model"]["model_id"],
            "callback_hash_chain_rows_verified": audit["callback_records"],
            "scored_callbacks_recorded": audit["actual_scored_callbacks"],
            "main_audit_fixed_weight_replay_samples": len(replays),
            "unique_fixed_weight_replay_samples_including_mechanisms": len(replay_ids),
            **counts,
            "changed_rows_received_verified": verified.get("changed_rows_received_verified", 0),
            "changed_rows_next_load_at_requested_destination":
                verified.get("changed_rows_next_load_at_requested_destination", 0),
            "final_native_rejection_reasons": reasons, "G1_missing_link_counts": gaps,
            "whole_run_final_native_summary": native_summary,
            "fallback_reasons": audit["fallback_reasons"],
            "strict_prearrival_direct_load_witnesses": mechanism["prearrival_ready_and_direct_next_load_witnesses"],
            "strict_prearrival_same_bag_wait_comparisons": pre,
            "already_waiting_direct_load_same_bag_comparisons": queue,
            "selector_p50_ms": selector["p50_ms"], "selector_p95_ms": selector["p95_ms"],
            "selector_p99_ms": selector["p99_ms"], "selector_max_ms": selector["max_ms"],
            "selector_total_seconds": selector["sum_ms"] / 1000.,
            "planner_total_seconds": planning["sum_ms"] / 1000.,
            "recorded_audit_persistence_seconds": persistence["sum_ms"] / 1000.,
            "planner_p95_ms": planning["p95_ms"],
            "branch_process_wall_seconds": timings["native_branch_process_wall_seconds"]})
    result = {
        "schema": "g31.foundation.all18_learned_execution_audit_rollup.v1",
        "status": "all_18_closed_learned_branches_independently_audited",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "script": ref(__file__), "registered_grid": ref(grid_path),
        "expected_and_completed_branches": 18, "artifacts": artifacts, "rows": rows,
        "coverage": {
            "full_callback_hash_chain_rows_verified": callback_count,
            "online_scored_callbacks_recorded": scored_count,
            "main_audit_fixed_weight_replays": main_replays,
            "unique_fixed_weight_replay_callbacks_including_mechanisms": unique_replays,
            "every_online_score_independently_recomputed": False,
            "all_saved_execution_rows_joined_to_raw_native_calls_ACKs_and_events": True},
        "operational_totals_across_repeated_scenarios": dict(total_counts),
        "final_native_rejection_reasons": dict(total_rejections),
        "G1_missing_links_nonexclusive": dict(total_missing),
        "strict_prearrival_same_bag_wait_comparison_totals": dict(prearrival_counts),
        "already_waiting_direct_load_same_bag_comparison_totals": dict(queued_counts),
        "strict_prearrival_witnesses_with_known_positive_same_bag_wait_difference": strict_positive,
        "timing_totals": {
            "selector_total_seconds": selector_sum / 1000.,
            "planner_total_seconds": planner_sum / 1000.,
            "recorded_audit_persistence_seconds": persistence_sum / 1000.,
            "planner_plus_recorded_audit_seconds": (planner_sum + persistence_sum) / 1000.,
            "sum_of_branch_process_wall_seconds": branch_wall_sum,
            "pooled_p95_computed": False, "per_branch_quantiles_retained": True,
            "note": "Quantiles are never averaged into pooled quantiles. Branch wall times overlap under concurrency and their sum is not campaign elapsed time."},
        "limitations": [
            "Hash-chain verification covers every recorded initial callback; weight replay covers explicitly listed samples only.",
            "G1 means selected request/entity, positive delivered ACK and first edge; receipt and direct next-load counts are separate.",
            "Final native rejection counts are read from matched actual transfer status. Changed-minus-G1 is not called rejected.",
            "Whole-run failed transfers and quarantined trays are reported separately, including failures outside the compared action rows; G1 verification does not imply failure-free operation.",
            "Missing-link categories overlap and must not be summed as distinct requests.",
            "All count totals repeat bags/scenarios across seeds and resource settings; they are not independent real airport days or unique bags.",
            "Strict prearrival with a positive same-bag wait difference is descriptive whole-policy evidence, not an isolated one-transfer causal estimate.",
            "Selector, planner, audit persistence and full branch wall times have different scopes. No 100ms controller SLA is established.",
            "No model/strategy changes, refits or native starts are performed by the audits or this rollup."],
        "native_jobs_started": 0, "fit_calls": 0, "runtime_sources_modified": False}
    path = OUT / "learned_execution_audit_summary_001.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")
    return {"artifact": ref(path), "coverage": result["coverage"],
        "execution": dict(total_counts), "strict_prearrival": dict(prearrival_counts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(aggregate(), ensure_ascii=False), flush=True)
