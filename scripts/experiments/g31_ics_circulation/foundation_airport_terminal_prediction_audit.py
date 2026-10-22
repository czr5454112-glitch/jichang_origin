"""Independent forecast identity, TRAIN-support, and same-state allocation audit.

No native session is created. A same-state comparison is a cold-start one-step
diagnostic on saved public observations; its different orders are not executed
and do not alter the next saved observation or establish a causal service gain.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
from itertools import zip_longest
import json
from pathlib import Path

from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_forecast_evaluation as study
from . import foundation_airport_terminal_support_predictor as supported
from .foundation_airport_batch_patch import digest as public_digest
from .foundation_airport_inventory_spi_campaign import read_bound


def require(value, reason):
    if not value:
        raise ValueError("terminal_prediction_audit:" + reason)


def iter_json_array(path, *, chunk_bytes=1024*1024):
    """Bound memory to one complete observation/decision and a small read buffer."""
    require(type(chunk_bytes) is int and chunk_bytes > 0, "positive_stream_chunk")
    decoder = json.JSONDecoder()
    opener = gzip.open if Path(path).suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        buffer = ""
        while not buffer.strip():
            more = stream.read(chunk_bytes)
            require(bool(more), "JSON_array_stream")
            buffer += more
        buffer = buffer.lstrip()
        require(buffer.startswith("["), "JSON_array_stream")
        buffer = buffer[1:]
        first = True
        while True:
            while not buffer.strip():
                more = stream.read(chunk_bytes)
                require(bool(more), "complete_JSON_array_export")
                buffer += more
            buffer = buffer.lstrip()
            if first and buffer.startswith("]"):
                require(not (buffer[1:]+stream.read()).strip(), "no_trailing_JSON_data")
                return
            first = False
            while True:
                try:
                    value, end = decoder.raw_decode(buffer)
                    remaining = buffer[end:].lstrip()
                    if remaining and remaining[0] in ",]":
                        break
                except json.JSONDecodeError:
                    pass
                more = stream.read(chunk_bytes)
                require(bool(more), "complete_JSON_array_export")
                buffer += more
            yield value
            if remaining[0] == "]":
                require(not (remaining[1:]+stream.read()).strip(), "no_trailing_JSON_data")
                return
            buffer = remaining[1:]


def closed_plan(directory):
    directory = Path(directory)
    plan = study.read(directory/"plan.json")
    require(plan["parent"]["split"] != "test", "TEST_not_opened")
    worker, receipt = (study.read(directory/name) for name in ("worker_report.json", "receipt.json"))
    require(receipt["plan_sha256"] == study.sha(directory/"plan.json") and receipt["worker"] == worker,
            "bound_closed_process")
    require(worker.get("scientific_status") == "closed" and worker.get("process_status") == "completed"
            and receipt["process"]["exitcode"] == 0, "closed_successful_source_only")
    return plan, worker


def audit_training_model(original_directory, supported_directory):
    original_directory, supported_directory = Path(original_directory), Path(supported_directory)
    original, model = study.read(original_directory/"model.json"), study.read(supported_directory/"model.json")
    provenance = study.read(original_directory/"provenance.json")
    saved = study.read(original_directory/"training_rows.json.gz")
    rows, parents, source_reports = [], [], []
    for source in provenance["train"]:
        directory = Path(source["plan.json"]["path"]).parent
        for key in ("plan.json", "worker_report.json", "receipt.json", "terminal_evidence.json.gz", "decision_stream"):
            require(study.sha(source[key]["path"]) == source[key]["sha256"], "unchanged_TRAIN_source:"+key)
        produced, plan, _ = study.training_rows(directory)
        rows.extend(produced)
        parents.append(plan["parent"])
        mapping = read_bound(plan["mapping"])
        required_cutoffs = []
        for row in iter_json_array(directory/"decisions.json.gz"):
            evidence = row.get("forecast_binding")
            if evidence is None:
                continue
            now = plan["parent"]["calendar_start_epoch_seconds"] + row["decision_time"]
            required = max(evidence["model_available_at_epoch_seconds"], mapping["model_available_at_epoch_seconds"])
            require(required <= now, "B1_and_mapping_available_in_actual_TRAIN_callback")
            required_cutoffs.append(required)
        source_reports.append({"parent_id": plan["parent"]["parent_group"],
            "native_arrival_recount_and_actual_forecast_reproduction": True,
            "actual_callback_availability_checks": len(required_cutoffs),
            "latest_pipeline_available_at_epoch_seconds": max(required_cutoffs),
            "mapping": plan["mapping"]})
    require(rows == saved and demand.digest(rows) == original["training_labels_sha256"], "native_TRAIN_labels_reproduced_exactly")
    rebuilt = supported.fit(rows, train_parents=parents,
        training_labels_closed_at_epoch_seconds=original["training_labels_closed_at_epoch_seconds"],
        model_available_at_epoch_seconds=original["model_available_at_epoch_seconds"],
        bin_edges_seconds=original["bin_edges_seconds"], prior_exposure=original["prior_exposure"])
    require(rebuilt == model and rebuilt["base_calibration"] == original, "frozen_supported_model_reproduced_exactly")
    return {"schema": "g31.terminal_prediction_training_audit.v1", "status": "passed",
        "original_model": study.bound(original_directory/"model.json"),
        "supported_model": study.bound(supported_directory/"model.json"),
        "source_reports": source_reports, "training_rows": len(rows),
        "station_count": len(original["parameters"]), "support_by_station": model["support_by_station"],
        "parameter_learning": "stationwise_Gamma_prior_regularized_Poisson_rate_from_actual_mature_arrival_counts",
        "learned_scale_formula": "clip((sum_actual + prior_exposure)/(sum_expected + prior_exposure), 0.25, 4.0)",
        "support_learning": "intersection_of_labelled_TRAIN_physical_windows; no_DEV_threshold_search",
        "RL": "not_implemented_no_policy_state_transition_or_delayed_RL_reward_update",
        "training_actions_or_service_rewards_used": False, "runtime_reads_labels": False,
        "TEST_opened": False, "native_starts": 0,
        "causal_limit": "Simulated calendar availability is not wall-clock artifact creation time."}


def audit_recorded_forecasts(directory, *, max_reconstructions=40):
    """Separate historical provider hash from actual transformed inner hash.

    The old runtime003 artifact is never rewritten. At sampled callbacks the
    original provider and final inner forecast are independently reconstructed
    from bound B1/mapping/receipt and public observation, without future labels.
    """
    from . import foundation_airport_joint_calendar_prepared as prepared_forecast
    directory = Path(directory)
    plan, worker = closed_plan(directory)
    provider = prepared_forecast.prepare_forecast_provider(read_bound(plan["forecast_binding"]),
        study.read(directory/"plan_preload_receipts.json"), loader_mapping=read_bound(plan["mapping"]) if plan.get("mapping") else None)
    model = read_bound(plan["demand_model"]) if plan.get("demand_model") else None
    counts, samples = Counter(), []
    decisions = iter_json_array(directory/"decisions.json.gz")
    observations = iter_json_array(directory/"observations.json.gz")
    for row, captured in zip_longest(decisions, observations):
        require(row is not None and captured is not None, "same_callback_stream_lengths")
        obs = captured["observation"]
        require(public_digest(obs) == captured["digest"] == row["public_observation_ref"], "saved_public_observation_binding")
        evidence = row.get("forecast_binding")
        if evidence is None:
            continue
        counts["forecast_records"] += 1
        inner_sha = public_digest(evidence["forecast"])
        counts["outer_hash_matches_final_actor_forecast"] += evidence["forecast_sha256"] == inner_sha
        counts["outer_hash_is_distinct_from_final_actor_forecast"] += evidence["forecast_sha256"] != inner_sha
        if len(samples) >= max_reconstructions:
            continue
        original = provider(observation=obs, parent=plan["parent"])
        transformed = demand.rebin_forecast(original["forecast"], bin_edges_seconds=plan["forecast_bin_edges_seconds"])
        if model is not None:
            transform = supported.transform if model["schema"] == supported.SCHEMA else demand.predictor_transform
            transformed = transform(model, transformed, now=obs["now"], parent_id=plan["parent"]["parent_group"])
        require(transformed == evidence["forecast"], "exact_actor_forecast_reconstructed_without_labels")
        provider_sha = original["forecast_sha256"]
        require(evidence.get("source_forecast_sha256", evidence["forecast_sha256"]) == provider_sha,
                "original_provider_identity_preserved")
        samples.append({"decision_id": row["decision_id"], "owner": obs["owner_id"], "at": obs["now"],
            "recorded_outer_sha256": evidence["forecast_sha256"], "reconstructed_provider_sha256": provider_sha,
            "actual_inner_actor_sha256": inner_sha, "actual_inner_exactly_reproduced": True,
            "provider_hash_is_actor_hash": provider_sha == inner_sha})
    return {"schema": "g31.terminal_prediction_recording_audit.v1", "status": "passed",
        "plan": study.bound(directory/"plan.json"), "receipt": study.bound(directory/"receipt.json"),
        "observations": study.bound(directory/"observations.json.gz"),
        "decisions": study.bound(directory/"decisions.json.gz"), "execution_source_bundle": plan["source_bundle"],
        "final_physical_time": worker["final_physical_time"], "counts": dict(counts), "samples": samples,
        "historical_artifacts_rewritten": False, "actor_forecast_hash_claim": "recomputed_inner_sha_only",
        "runtime003_legacy_outer_hash_semantics": "prepared_provider_B1_before_rebin_or_calibration",
        "source_and_final_actor_forecast_identities_are_distinct": True,
        "future_truth_read": False, "native_starts": 0}


def physical_choice(choice, catalog):
    candidate = next(row for row in catalog["candidates"] if row["action_id"] == choice["action_id"])
    counts = Counter((row["source"], row["destination"]) for row in choice["flow_plan"].get("chosen", []))
    order = choice.get("empty_transport_order") or {}
    return {"action_id": candidate["action_id"], "kind": candidate["action_type"],
        "tray_id": candidate.get("tray_id"), "source": candidate.get("source"), "destination": candidate.get("destination"),
        "planned_quantity": sum(counts.values()),
        "allocation": [{"source": pair[0], "destination": pair[1], "quantity": count} for pair, count in sorted(counts.items())],
        "target_by": order.get("target_by"), "useful_until": order.get("useful_until"),
        "latest_issue_estimate": order.get("latest_issue_estimate"),
        "reason": choice["reason"], "exact_net_gain": choice["flow_verification"].get("exact_net_gain"),
        "current_supply_cap": choice["flow_plan"].get("total_current_supply_cap"),
        "source_offers": choice["flow_plan"].get("source_offers"),
        "hold_quantity": choice["flow_plan"].get("hold_quantity"),
        "protected_unallocated_quantity": choice["flow_plan"].get("protected_unallocated_quantity"),
        "invalid_first_action_reasons": dict(Counter(row["reason"] for row in choice["flow_verification"].get("invalid", [])))}


def compare_same_state(directory, model_path, *, stop_at=18000.):
    """Rebuild and verify the exact shared current-only catalogue before scoring."""
    from . import foundation_airport_joint_opportunities as opportunities
    from . import foundation_airport_inventory_rule as r0
    from . import foundation_airport_inventory_projection as projection
    from . import foundation_airport_transport_control as transport
    from . import foundation_airport_transport_allocation as allocation
    directory = Path(directory)
    plan, worker = closed_plan(directory)
    require(plan["parent"]["split"] == "dev", "held_out_DEV_observations_required")
    require(7200. < stop_at <= worker["final_physical_time"], "closed_comparison_window")
    model = study.read(model_path)
    supported.validate_model(model)
    require(plan.get("mapping"), "same_frozen_mapping_required")
    mapping = read_bound(plan["mapping"])
    require(mapping["sha256"] == model["base_calibration"]["mapping_sha256"], "same_loader_mapping")
    binding = read_bound(plan["forecast_binding"])
    support_contract = read_bound(plan["arrival_support_contract"])
    receipts = study.read(directory/"arrival_support_receipts.json")
    counts, differences, rows = Counter(), [], []
    policy = transport.TransportPolicy(config=allocation.DEFAULT_CONFIG, recompute_period_seconds=60.)
    decisions = iter_json_array(directory/"decisions.json.gz")
    observations = iter_json_array(directory/"observations.json.gz")
    for recorded, captured in zip_longest(decisions, observations):
        require(recorded is not None and captured is not None, "same_callback_stream_lengths")
        obs = captured["observation"]
        if obs["now"] >= stop_at:
            break
        require(public_digest(obs) == captured["digest"] == recorded["public_observation_ref"], "public_observation_digest")
        tick = int(obs["now"]//60.)
        baseline = r0.r0_priority_planner(obs, message_delay=2., request_prefix=f"protocol:{tick}:post_return:priority_check")
        current = opportunities.prepare_current(obs, baseline, message_delay=2.)
        catalog = opportunities.build_joint_catalog(current)
        require(catalog == recorded["catalog"], "exact_reproduced_current_only_catalog")
        counts["public_decision_states"] += 1
        item = {"decision_id": recorded["decision_id"], "at": obs["now"], "owner": obs["owner_id"],
            "observation_sha256": captured["digest"], "catalog_id": catalog["catalog_id"],
            "legal_transfer_candidates": catalog["K"]-1,
            "eligible_trays": catalog["candidate_source_tray_count"], "candidate_sources": catalog["candidate_source_node_count"],
            "candidate_destinations": catalog["candidate_destination_count"], "exclusions": catalog["exclusions"]}
        if catalog["K"] == 1:
            counts["no_current_legal_transfer"] += 1
            item.update(first_action_changed=False, allocation_changed=False, reason="no_current_legal_transfer_forecast_cannot_create_supply")
            rows.append(item)
            continue
        counts["states_with_legal_transfer"] += 1
        raw = study.reconstruct_forecast(binding, mapping, now=obs["now"], owner=obs["owner_id"])
        base = demand.rebin_forecast(raw, bin_edges_seconds=model["base_calibration"]["bin_edges_seconds"])
        revised = supported.transform(model, base, now=obs["now"], parent_id=plan["parent"]["parent_group"])
        changed_demand = base["new_demand_mean_by_region"] != revised["new_demand_mean_by_region"]
        counts["states_with_changed_demand"] += changed_demand
        item.update(demand_changed=changed_demand,
            forecast_mean_mass_adjustment=revised["predictor_calibration"]["mean_mass_adjustment"])
        choices = {}
        for name, forecast in (("B1-300", base), ("supported_predictor", revised)):
            state = projection.prepare_inventory_projection(obs, forecast=forecast, prepared_current=current,
                horizon_seconds=600., arrival_support_contract=support_contract,
                arrival_support_receipt=receipts[obs["owner_id"]])
            choice = policy.select(current, catalog, state, policy_state={}, decision_context={"tick": tick})
            choices[name] = physical_choice(choice, catalog)
        original, revised_choice = choices["B1-300"], choices["supported_predictor"]
        first_changed = original["action_id"] != revised_choice["action_id"]
        allocation_changed = original["allocation"] != revised_choice["allocation"]
        time_changed = any(original[key] != revised_choice[key] for key in ("target_by", "useful_until", "latest_issue_estimate"))
        counts["first_action_changed"] += first_changed
        counts["allocation_changed"] += allocation_changed
        counts["soft_time_changed"] += time_changed
        counts["both_HOLD"] += original["kind"] == revised_choice["kind"] == "noop"
        item.update(first_action_changed=first_changed, allocation_changed=allocation_changed,
                    soft_time_changed=time_changed, choices=choices,
                    native_commitments_in_observation=len(obs.get("client_transfer_ledger", [])))
        rows.append(item)
        if first_changed or allocation_changed or time_changed:
            differences.append(item)
    return {"schema": "g31.terminal_prediction_same_state_orders.v1", "plan": study.bound(directory/"plan.json"),
        "observations": study.bound(directory/"observations.json.gz"), "decisions": study.bound(directory/"decisions.json.gz"),
        "model": study.bound(model_path), "window": [7200., stop_at], "counts": dict(counts),
        "differences": differences, "states": rows, "allocator_config": allocation.DEFAULT_CONFIG,
        "projection_horizon_seconds": 600., "control_tick_seconds": 60., "model_bin_seconds": 300.,
        "same_current_only_catalog_verified": True, "cost_weights_or_eligibility_changed": False,
        "allocation_and_control_source": {name: study.bound(Path(__file__).with_name(name)) for name in (
            "foundation_airport_transport_allocation.py", "foundation_airport_transport_control.py")},
        "future_truth_or_private_state_read": False, "native_starts": 0,
        "interpretation": "cold_start_one_step_counterfactual_on_common_saved_DEV_public_states",
        "counterfactual_state_carried_to_next_saved_observation": False,
        "actual_native_obligations_retained_in_projection": True,
        "additional_hypothetical_pending_claims": "none_in_both_conditions",
        "orders_executed": False, "causal_service_gain_established": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("model", "recording", "same-state"))
    parser.add_argument("--original", type=Path)
    parser.add_argument("--supported", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh_audit_output")
    if args.command == "model":
        require(args.original is not None and args.supported is not None, "model_audit_inputs")
        result = audit_training_model(args.original, args.supported)
    elif args.command == "recording":
        require(args.run is not None, "recording_run")
        result = audit_recorded_forecasts(args.run)
    else:
        require(args.run is not None and args.model is not None, "same_state_inputs")
        result = compare_same_state(args.run, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "schema": result["schema"],
                      "status": result.get("status"), "counts": result.get("counts"), "native_starts": 0}))


if __name__ == "__main__":
    main()
