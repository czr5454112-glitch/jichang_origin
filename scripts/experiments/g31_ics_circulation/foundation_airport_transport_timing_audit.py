"""Read-only timing trigger audit of saved terminal-flow decisions.

Compares common-reference and exact-ETA first-action rankings on the same
public menu. It is an offline proxy diagnostic, not a policy or native trial.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import json
from pathlib import Path
import statistics

from .foundation_airport_inventory_projection import prepare_inventory_projection, project_action
from .foundation_airport_transport_allocation import transport_cost

SCHEMA = "g31.terminal_flow.timing_trigger_audit.v1"


def _read(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _identity(action):
    return None if action is None else [action["source"], action["destination"]]


def _summary(values):
    ordered = sorted(values)
    return {"count": len(values), "minimum": min(values, default=None), "maximum": max(values, default=None),
        "median": statistics.median(values) if values else None,
        "p90": ordered[min(len(ordered)-1, int(.9*len(ordered)))] if ordered else None}


def audit_run(run_dir):
    run_dir = Path(run_dir)
    decisions = _read(run_dir/"decisions.json.gz")
    observations = {row["digest"]: row["observation"] for row in _read(run_dir/"observations.json.gz")}
    support = _read(run_dir/"arrival_support_contract.json")
    support_receipts = _read(run_dir/"arrival_support_receipts.json")
    counts, invalid, examples, exact_differences, eta, gain_gaps, multislots = Counter(), Counter(), [], [], [], [], []
    for decision in decisions:
        counts["decisions"] += 1
        selection = decision["selection"]
        plan = selection["flow_plan"]
        chosen = plan["chosen"]
        counts["zero_quantity_plans" if not chosen else "single_quantity_plans" if len(chosen) == 1 else "multi_quantity_plans"] += 1
        invalid.update(row["reason"] for row in decision["flow_verification"].get("invalid", []))
        if plan["dispatch_profile"] and selection["action_id"] != plan["dispatch_profile"][0]["action_id"]:
            counts["selected_first_differs_from_proxy_profile"] += 1
        for row in plan["dispatch_profile"]:
            if row["dispatch_slot"]:
                multislots.append(row["submit_at"]-decision["decision_time"])
        actual = decision["requested_action"]
        if actual["action_type"] == "transfer":
            counts["selected_transfers"] += 1
            eta.append(actual["nominal_arrival_time"]-decision["decision_time"])
            exact = decision["flow_verification"]["exact_net_gain"]
            if exact is not None:
                gain_gaps.append(plan["objective"]["net_proxy_gain"]-exact)
        # A pending shared claim has a marginal-rank effect absent from the
        # independent single-action proxy; do not mislabel it an ETA effect.
        if any(plan.get("receiver_claims_deducted", {}).values()):
            counts["ranking_excluded_pending_claims"] += 1
            continue
        observation = observations[decision["public_observation_ref"]]
        forecast = decision.get("forecast_binding", {}).get("forecast")
        projection = prepare_inventory_projection(observation, forecast=forecast,
            horizon_seconds=plan["projection_horizon_seconds"], supply_mode=plan["supply_mode"],
            arrival_support_contract=support, arrival_support_receipt=support_receipts[decision["owner_id"]])
        receivers = {row["node"]: row["receiver"] for row in plan["station_table"]}
        candidates = [row for row in decision["catalog"]["candidates"] if row["action_type"] == "transfer"
            and receivers[row["destination"]]["known"] and receivers[row["destination"]]["available_slots"] > 0]
        if any(row["source_category"] == "ordinary_return" for row in candidates):
            candidates = [row for row in candidates if row["source_category"] == "ordinary_return"]
        scores = []
        for candidate in candidates:
            common = copy.copy(candidate)
            common["nominal_arrival_time"] = projection.now+plan["config"]["marginal_reference_available_offset_seconds"]
            common["earliest_departure"] = min(common["earliest_departure"], common["nominal_arrival_time"])
            reference = project_action(projection, common)
            exact = project_action(projection, candidate)
            feature = decision["candidate_features"][candidate["action_id"]]
            recorded_gain = (feature["features_forecast"]["forecast_proxy_gain"] if forecast is not None else
                feature["features_current"]["current_proxy_gain"])
            if ((recorded_gain is None) != (exact["proxy_gain"] is None)
                    or recorded_gain is not None and abs(recorded_gain-exact["proxy_gain"]) > 1e-7):
                raise ValueError("timing_audit:reconstruction_differs_from_recorded_projection")
            if not reference["known"] or not exact["known"]:
                continue
            cost = transport_cost(candidate, plan["config"])
            scores.append((candidate, reference["proxy_gain"]-cost, exact["proxy_gain"]-cost,
                exact["proxy_gain"]-plan["config"]["transport_penalty_weight"]*candidate["static_travel_time"]))
        if len({_identity(row[0])[0] for row in scores}) > 1:
            counts["known_multi_source_ranking_opportunities"] += 1
        if len({tuple(_identity(row[0])) for row in scores}) < 2:
            continue
        counts["known_multi_od_ranking_opportunities"] += 1
        ordinary = bool(scores) and scores[0][0]["source_category"] == "ordinary_return"
        def best(index):
            ordered = sorted(scores, key=lambda row: (-row[index], row[0]["nominal_arrival_time"],
                row[0]["source"], row[0]["destination"], str(row[0]["tray_id"])))
            return ordered[0] if ordered and (ordinary or ordered[0][index] > plan["config"]["minimum_net_gain"]) else None
        reference, exact_same_cost, exact_actual_cost = best(1), best(2), best(3)
        timing_changed = _identity(reference[0] if reference else None) != _identity(exact_same_cost[0] if exact_same_cost else None)
        if timing_changed:
            counts["eta_only_best_first_changes_including_hold"] += 1
            if reference and exact_same_cost:
                counts["eta_only_source_or_destination_ranking_changes"] += 1
        if _identity(exact_actual_cost[0] if exact_actual_cost else None) != _identity(actual if actual["action_type"] == "transfer" else None):
            counts["full_exact_menu_best_differs_from_selected"] += 1
            if len(exact_differences) < 20:
                exact_differences.append({"decision_time": decision["decision_time"], "owner_id": decision["owner_id"],
                    "actual_selected": _identity(actual if actual["action_type"] == "transfer" else None),
                    "full_exact_menu_best": _identity(exact_actual_cost[0] if exact_actual_cost else None),
                    "full_exact_best_net": None if exact_actual_cost is None else exact_actual_cost[3],
                    "reference_best": _identity(reference[0] if reference else None),
                    "exact_same_cost_best": _identity(exact_same_cost[0] if exact_same_cost else None)})
        if timing_changed and len(examples) < 20:
            examples.append({"decision_id": decision["decision_id"], "decision_time": decision["decision_time"],
                "owner_id": decision["owner_id"], "reference_best": _identity(reference[0] if reference else None),
                "exact_same_cost_best": _identity(exact_same_cost[0] if exact_same_cost else None),
                "reference_best_net": None if reference is None else reference[1],
                "reference_best_exact_eta_net": None if reference is None else reference[2],
                "exact_best_net": None if exact_same_cost is None else exact_same_cost[2],
                "actual_selected": _identity(actual if actual["action_type"] == "transfer" else None)})
    lifecycle, arrival_errors = [], []
    calls = _read(run_dir/"calls.json.gz")
    acknowledgements = _read(run_dir/"delivered_ack_evidence.json.gz")
    final_requests = {row["request_id"]: (row, owner["now"]) for owner in acknowledgements.values()
        for row in owner["client_transfer_ledger"]}
    for decision in decisions:
        actual = decision["requested_action"]
        if actual["action_type"] != "transfer":
            continue
        matched = [row for row in calls if row.get("kind") == "transfer" and not row.get("retry")
            and row["at"] == decision["decision_time"] and row["request"]["tray_id"] == actual["tray_id"]
            and row["request"]["source"] == actual["source"] and row["request"]["destination"] == actual["destination"]]
        if len(matched) != 1:
            lifecycle.append({"decision_id": decision["decision_id"], "submission_match_count": len(matched)})
            continue
        call = matched[0]
        request, end = final_requests[call["request"]["request_id"]]
        received = request.get("received_at", -1.)
        arrived = request["status"] == "received" and received >= 0.
        error = received-actual["nominal_arrival_time"] if arrived else None
        if error is not None:
            arrival_errors.append(error)
        lifecycle.append({"decision_time": decision["decision_time"], "source": actual["source"],
            "destination": actual["destination"], "tray_id": actual["tray_id"], "request_id": request["request_id"],
            "nominal_arrival": actual["nominal_arrival_time"], "final_native_status": request["status"],
            "received_at": received if arrived else None, "arrival_error_seconds": error,
            "observed_through": end, "right_censored": not arrived,
            "unreceived_lateness_lower_bound_seconds": max(0., end-actual["nominal_arrival_time"]) if not arrived else None})
    for key in ("zero_quantity_plans", "single_quantity_plans", "multi_quantity_plans", "selected_transfers",
                "selected_first_differs_from_proxy_profile", "known_multi_source_ranking_opportunities",
                "known_multi_od_ranking_opportunities", "ranking_excluded_pending_claims",
                "eta_only_best_first_changes_including_hold", "eta_only_source_or_destination_ranking_changes",
                "full_exact_menu_best_differs_from_selected"):
        counts.setdefault(key, 0)
    return {"schema": SCHEMA, "run_dir": str(run_dir.resolve()), "counts": dict(counts),
        "verification_invalid_reasons": dict(invalid), "selected_eta_seconds": _summary(eta),
        "proxy_minus_exact_selected_gain": _summary(gain_gaps),
        "multi_dispatch_slot_offsets_seconds": _summary(multislots), "timing_change_examples": examples,
        "full_exact_menu_difference_examples": exact_differences,
        "selected_transfer_lifecycle": lifecycle, "received_only_eta_error_seconds": _summary(arrival_errors),
        "audit_scope": "saved_public_observations_frozen_forecasts_no_future_labels_no_native_start",
        "arrival_support_contract_sha256": support["sha256"],
        "reconstructed_exact_gain_checked_against_every_eligible_recorded_feature": True,
        "ranking_comparison": "same_transport_and_delay_penalty_with_only_arrival_event_changed",
        "counts_are_repeated_decisions_not_independent_scenes": True,
        "native_arrival_error_measured": True, "unreceived_not_dropped_from_denominator": True,
        "native_service_improvement_claimed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    report = audit_run(options.run_dir)
    output = Path(options.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
