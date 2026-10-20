"""Finite C10 development selection and legal-view forecast diagnostics.

Only the two executed branches have labels. Full-catalog winners outside that
pair remain unknown; forecasts never manufacture counterfactual outcomes.
"""
from __future__ import annotations

from collections import Counter
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

from . import foundation_airport_strong_rule as rule
from . import foundation_airport_prospective_control as control
from .foundation_airport_batch_patch import digest
from .foundation_airport_paired_continuation import validate_parent

SCHEMA = "g31.foundation.airport_spi_C10_development_selection.v1"
METHODS = ("reference", "strong_rule_weight0", "strong_rule_weight1")


def require(ok, reason):
    if not ok:
        raise ValueError("airport_spi_rule_selection:" + reason)


def selection_contract():
    return {"schema": SCHEMA+".contract", "candidates": list(METHODS),
        "forecast_weights": [0., 1.], "expected_dev_pairs": 8, "expected_dev_parents": 4,
        "registered_dev_parent_seeds": [1201, 1202, 1203, 1204], "root_slots_per_parent": 2,
        "K_max": 13, "max_policy_replacements_per_parent": 1,
        "continuation_policy_id": "airport_common_inventory_pi0_v1",
        "label_horizon_seconds": 1800., "minimum_supported_fraction": 0.25,
        "known_direction_harm_limit": 0, "require_nonworse_on_time": True,
        "require_nonworse_overdue_unfinished": True,
        "unsupported_winner_cost": "unknown_not_reference_zero",
        "incomplete_development_J_blocks_promotion": True,
        "reference_wins_ties": True, "numerical_gain_tolerance_bag_seconds": 1e-6,
        "ranking_tolerance": 1e-6,
        "selection_order": ["closed_valid_labels", "service_constraints",
            "supported_fraction", "complete_parent_balanced_paired_J_gain", "reference_tie"],
        "development_unit": "registered_root_conditioned_pair_not_a_full_policy_rollout",
        "no_independent_bag_or_model_seed_replication": True,
        "test_used_for_selection": False, "protected_takeover_eligible": False}


def source_pins():
    from . import analytic_control, foundation_airport_learning_public, foundation_airport_pair_ranker
    from . import foundation_airport_batch_patch, foundation_airport_opportunities
    modules = (rule, control, analytic_control, foundation_airport_learning_public,
        foundation_airport_pair_ranker, foundation_airport_batch_patch, foundation_airport_opportunities)
    paths = [Path(__file__), *(Path(m.__file__) for m in modules)]
    return {"scripts/experiments/g31_ics_circulation/"+p.name:
        hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _read(reference):
    raw = Path(reference["path"]).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference["sha256"], "bound_dataset_bytes")
    return json.loads(gzip.decompress(raw) if str(reference["path"]).endswith(".gz") else raw)


def load_dev_inputs(inputs, contract):
    require(len(inputs) == contract["expected_dev_pairs"], "all_preregistered_dev_pair_slots_required")
    parents = [validate_parent(item["parent"]) for item in inputs]
    require(all(p["split"] == "dev" for p in parents), "reject_nondev_metadata_before_open")
    require(all(p.get("parent_seed") in contract["registered_dev_parent_seeds"]
        and p.get("rollout_round", 0) == 0 for p in parents), "registered_round0_dev_parent_namespace")
    require(len({p["parent_group"] for p in parents}) == contract["expected_dev_parents"],
        "fixed_dev_parent_denominator")
    require(all(count == contract["root_slots_per_parent"]
        for count in Counter(p["parent_group"] for p in parents).values()), "two_roots_per_dev_parent")
    require(len({str(Path(item["dataset"]["path"]).resolve()) for item in inputs}) == len(inputs),
        "registered_pair_slots_must_not_reuse_one_artifact")
    values = []
    for item, parent in zip(inputs, parents, strict=True):
        dataset = _read(item["dataset"])
        require(dataset["pair"]["parent"] == parent, "actual_declared_parent_binding")
        values.append(dataset)
    pair_ids = [d["pair"]["pair_id"] for d in values if d["pair"].get("pair_id")]
    require(len(pair_ids) == len(set(pair_ids)), "duplicate_closed_pair_identity")
    return values


def public_candidate_rows(dataset):
    """Discard all labels before constructing full legal candidate inference rows."""
    pair = dataset["pair"]
    require(pair["status"] == "closed_actual_pair" and len(dataset["rows"]) == 2,
        "closed_pair_public_view_required")
    reference, patch = dataset["rows"]
    require(reference["observation"] == patch["observation"]
        and reference["opportunity"] == patch["opportunity"]
        and reference["baseline_decision"] == patch["baseline_decision"]
        and reference["parent"] == patch["parent"] == pair["parent"],
        "same_actual_current_and_baseline")
    opportunity = reference["opportunity"]
    require(1 <= opportunity["K"] <= 13 and opportunity["K_max"] == 13
        and opportunity["catalog_uses_future_plan"] is False, "registered_full_static_catalog")
    require(len({a["action_id"] for a in opportunity["candidates"]}) == opportunity["K"],
        "unique_full_catalog_actions")
    require(reference.get("forecast_evidence") == patch.get("forecast_evidence")
        and type(reference.get("forecast_evidence")) is dict, "same_actual_received_forecast")
    rows = []
    for rank in range(1, opportunity["K"]):
        rows.append(control.current_candidate_rows(reference["observation"],
            reference["baseline_decision"], opportunity, parent=pair["parent"],
            information_variant="C10", forecast_evidence=reference["forecast_evidence"],
            patch_rank=rank, copy_inputs=False))
    return rows


def _shortage_regime(prepared, semantic):
    """Exact piecewise signs of this visible-account proxy, never global truth."""
    now, _nodes, _trays, travel, free, supplies, waiting, curves, coverage, *_ = prepared
    free, supplies = free.copy(), copy.deepcopy(supplies)
    if semantic["kind"] == "transfer":
        free[semantic["source"]] -= 1
        destination = semantic["destination"]
        supplies[destination].append((rule._eta(semantic, now, travel), 1.))
    output = []
    horizon = 1800.
    for node, (edges, means) in sorted(curves.items()):
        cov = coverage[node]
        known = (means is not None and cov["observed_free_complete"]
            and cov["waiting_exact_captured_count"])
        if not known:
            output.append({"node": node, "regime": "unknown_account_coverage",
                "coverage": copy.deepcopy(cov)})
            continue
        events = supplies[node]
        boundaries = sorted({0., horizon, *[x for x in edges if 0 < x < horizon],
            *[t for t, _ in events if 0 < t < horizon]})
        values = []
        for left, right in zip(boundaries, boundaries[1:]):
            stock = free[node]+sum(count for at, count in events if at <= left)
            values.extend(waiting[node]+rule._cumulative(edges, means, at)-stock
                for at in (left, right))
        low, high = min(values), max(values)
        regime = ("always_nonnegative_shortage_proxy" if low >= -1e-9 else
            "always_nonpositive_shortage_proxy" if high <= 1e-9 else "crosses_zero_shortage_proxy")
        output.append({"node": node, "regime": regime, "minimum_deficit_proxy": low,
            "maximum_deficit_proxy": high, "coverage": copy.deepcopy(cov),
            "full_current_waiting_completeness_claimed": False})
    return output


def diagnose_candidate(reference, patch):
    prepared = rule._prepare(reference, patch)
    now, _nodes, _trays, travel, free, _supplies, waiting, curves, coverage, conditional, *_ = prepared
    action = patch["semantic_action"]
    destination = action["destination"]
    diagnostic = {"action_id": patch["action"]["action_id"],
        "current_visible_free_total": sum(free.values()),
        "conditional_supply_events": len(conditional), "account_coverage": copy.deepcopy(coverage),
        "reference_shortage_regimes": _shortage_regime(prepared, reference["semantic_action"]),
        "patch_shortage_regimes": _shortage_regime(prepared, action),
        "forecast_only_demand_opportunity": None,
        "static_arrival_before_first_positive_forecast_bin": None,
        "actual_prearrival_witness_claimed": False}
    if action["kind"] == "transfer":
        edges, means = curves[destination]
        cov = coverage[destination]
        known = means is not None and cov["waiting_exact_captured_count"] and cov["observed_free_complete"]
        if known:
            mass = rule._cumulative(edges, means, 1800.)
            eta = rule._eta(action, now, travel)
            potential = waiting[destination] == 0 and mass > 0 and eta <= 1800.
            first_bin = next((left for left, value in zip(edges, means) if value > 0.), None)
            diagnostic.update(forecast_only_demand_opportunity=potential,
                static_arrival_before_first_positive_forecast_bin=(
                    potential and first_bin is not None and eta <= first_bin),
                destination_captured_waiting=waiting[destination], predicted_mass_1800=mass,
                static_arrival_offset=eta, first_positive_forecast_bin_left=first_bin)
        else:
            diagnostic["opportunity_unknown_reason"] = "incomplete_visible_stock_waiting_or_forecast"
    else:
        diagnostic["opportunity_unknown_reason"] = "hold_has_no_destination_receipt"
    return diagnostic


def score_catalog(dataset):
    rows = public_candidate_rows(dataset)
    scores = {0.: [], 1.: []}
    diagnostics = []
    for reference, patch in rows:
        for weight in scores:
            explained = rule.explain_pair(reference, patch, forecast_weight=weight)
            gain = explained["predicted_patch_advantage"]
            require(math.isfinite(gain) and explained["registered_forecast_weight"] == weight,
                "finite_registered_rule_score")
            scores[weight].append({"action_id": patch["action"]["action_id"],
                "predicted_advantage": gain, "explanation": explained})
        diagnostics.append(diagnose_candidate(reference, patch))
    choices, orders = {}, {}
    for weight, values in scores.items():
        ranked = sorted([{"action_id": "a_ref", "predicted_advantage": 0.}, *values],
            key=lambda row: (-row["predicted_advantage"], row["action_id"] != "a_ref",
                next((i for i, x in enumerate(values) if x["action_id"] == row["action_id"]), -1)))
        choices[weight] = ranked[0]["action_id"]
        orders[weight] = [r["action_id"] for r in ranked]
    deltas = [b["predicted_advantage"]-a["predicted_advantage"]
        for a, b in zip(scores[0.], scores[1.], strict=True)]
    return {"public_state_digest": dataset["rows"][0]["opportunity"]["public_state_digest"],
        "K": dataset["rows"][0]["opportunity"]["K"],
        "actual_uncommitted_tray_count": len(dataset["rows"][0]["opportunity"]["actual_uncommitted_trays"]),
        "scores": {str(int(k)): v for k, v in scores.items()},
        "winner_weight0": choices[0.], "winner_weight1": choices[1.],
        "ranking_weight0": orders[0.], "ranking_weight1": orders[1.],
        "winner_changes_with_forecast": choices[0.] != choices[1.],
        "ranking_changes_with_forecast": orders[0.] != orders[1.],
        "maximum_absolute_forecast_marginal_score_change": max(map(abs, deltas), default=0.),
        "candidate_diagnostics": diagnostics, "outcome_labels_read_for_scores": False}


def _label_for_winner(dataset, winner):
    """Select actual branch evidence; never evaluate an unexecuted alternative."""
    pair = dataset["pair"]
    if pair["status"] != "closed_actual_pair":
        return {"label_support": "unavailable_registered_pair", "reason": pair.get("reason", pair["status"]),
            "gain_bag_seconds": None, "known_direction_harm": None, "failures": None,
            "on_time_delta": None, "overdue_unfinished_delta": None}
    if winner == "a_ref":
        chosen, gain, harm, on_time, overdue = dataset["rows"][0], 0., 0, 0, 0
        support = "actual_reference_branch"
    elif winner == dataset["rows"][1]["action"]["action_id"]:
        chosen = dataset["rows"][1]
        gain = pair["advantage_bag_seconds"]
        direction = pair["censored_direction_summary"]
        require(direction["population"] == pair["reference_cost"]["physical_population"]
            and direction["known_direction_harm"] ==
            direction["categories"]["exact_harmed"]+direction["categories"]["reference_only_finished"],
            "complete_exact_censored_harm")
        harm = direction["known_direction_harm"]
        a, b = pair["reference_cost"], pair["patched_cost"]
        require(a["label_start"] == b["label_start"] and a["label_end"] == b["label_end"]
            and a["label_end"]-a["label_start"] == 1800.
            and math.isclose(a["backlog_integral_bag_seconds"]-b["backlog_integral_bag_seconds"],
                gain, rel_tol=1e-12, abs_tol=1e-6), "actual_common_window_paired_cost")
        on_time = b["on_time_by_end"]-a["on_time_by_end"]
        overdue = b["arrived_unfinished_past_deadline"]-a["arrived_unfinished_past_deadline"]
        support = "actual_registered_patch_branch"
    else:
        return {"label_support": "unsupported_unexecuted_winner", "reason": winner,
            "gain_bag_seconds": None, "known_direction_harm": None, "failures": None,
            "on_time_delta": None, "overdue_unfinished_delta": None}
    attempts = chosen["actual_execution"]["attempts"]
    failures = sum(not a["positive_delivered_ack"]
        or (a.get("native_transfer_at_export") or {}).get("status") == "failed" for a in attempts)
    return {"label_support": support, "gain_bag_seconds": gain, "known_direction_harm": harm,
        "failures": failures, "on_time_delta": on_time, "overdue_unfinished_delta": overdue}


def evaluate_datasets(datasets, contract):
    records = []
    for index, dataset in enumerate(datasets):
        pair = dataset["pair"]
        parent = validate_parent(pair["parent"])
        require(parent["split"] == "dev", "development_only")
        record = {"registered_slot": index, "pair_id": pair.get("pair_id"),
            "parent_group": parent["parent_group"], "pair_status": pair["status"],
            "pair_reason": pair.get("reason"), "catalog": None}
        if pair["status"] == "closed_actual_pair":
            require(pair["policy_alignment"]["continuation_policy_id"] == contract["continuation_policy_id"]
                and pair["policy_alignment"]["improvement_round"] == 0
                and pair["policy_alignment"]["max_policy_replacements"] == 1,
                "only_pi0_one_step_development_labels")
            try:
                record["catalog"] = score_catalog(dataset)
            except (ValueError, KeyError, TypeError) as exc:
                record["diagnostic_failure"] = repr(exc)
        record["methods"] = {}
        for method in METHODS:
            winner = ("a_ref" if method == "reference" else record["catalog"][
                "winner_weight"+method[-1]] if record["catalog"] is not None else None)
            label = (_label_for_winner(dataset, winner) if winner is not None else {
                "label_support": "invalid_or_unavailable_current_view", "gain_bag_seconds": None,
                "known_direction_harm": None, "failures": None,
                "on_time_delta": None, "overdue_unfinished_delta": None})
            record["methods"][method] = dict(label, winner=winner)
        records.append(record)
    methods = []
    groups = sorted({r["parent_group"] for r in records})
    for method in METHODS:
        per_parent = []
        for group in groups:
            rows = [r["methods"][method] for r in records if r["parent_group"] == group]
            known = [r for r in rows if r["gain_bag_seconds"] is not None]
            per_parent.append({"parent_group": group, "registered_root_count": len(rows),
                "supported_root_count": len(known), "unsupported_root_count": len(rows)-len(known),
                "complete_paired_mean_gain": math.fsum(r["gain_bag_seconds"] for r in known)/len(rows)
                    if len(known) == len(rows) else None,
                "known_partial_gain_sum": math.fsum(r["gain_bag_seconds"] for r in known),
                "known_direction_harm_sum_across_root_contrasts": sum(r["known_direction_harm"] for r in known),
                "failure_count": sum(r["failures"] for r in known),
                "service_violation_root_count": sum(r["known_direction_harm"] > 0
                    or r["on_time_delta"] < 0 or r["overdue_unfinished_delta"] > 0 for r in known)})
        supported = sum(p["supported_root_count"] for p in per_parent)
        complete = all(p["complete_paired_mean_gain"] is not None for p in per_parent)
        fraction = supported/len(records) if records else 0.
        value = math.fsum(p["complete_paired_mean_gain"] for p in per_parent)/len(groups) if complete else None
        reasons = []
        if any(p["failure_count"] for p in per_parent): reasons.append("selected_actual_branch_failures")
        if any(p["service_violation_root_count"] for p in per_parent): reasons.append("known_service_constraint_violation")
        if fraction < contract["minimum_supported_fraction"]: reasons.append("insufficient_label_support")
        if not complete: reasons.append("incomplete_development_J_unknown")
        if value is not None and value <= contract["numerical_gain_tolerance_bag_seconds"]:
            reasons.append("does_not_improve_reference_on_complete_dev_J")
        methods.append({"method": method, "forecast_weight": None if method == "reference" else int(method[-1]),
            "per_parent": per_parent, "supported_fraction": fraction,
            "complete_parent_balanced_paired_gain": value,
            "eligible_for_promotion": method != "reference" and not reasons,
            "promotion_blockers": reasons})
    eligible = [r for r in methods if r["eligible_for_promotion"]]
    chosen = min(eligible, key=lambda r: (-r["complete_parent_balanced_paired_gain"], r["forecast_weight"])) if eligible else methods[0]
    return {"selected_method": chosen["method"], "methods": methods, "records": records,
        "diagnostic_denominators": summarize_diagnostics(records, contract),
        "parent_count": len(groups), "registered_pair_count": len(records),
        "independent_real_airport_days": 0, "full_policy_development_return_claimed": False,
        "bag_or_root_replications_are_independent_days": False}


def summarize_diagnostics(records, contract):
    valid = [r["catalog"] for r in records if r["catalog"] is not None]
    candidates = [d for c in valid for d in c["candidate_diagnostics"]]
    regimes = Counter(row["regime"] for d in candidates for key in
        ("reference_shortage_regimes", "patch_shortage_regimes") for row in d[key])
    def counts(field):
        return {"true": sum(d[field] is True for d in candidates),
            "false": sum(d[field] is False for d in candidates),
            "unknown": sum(d[field] is None for d in candidates)}
    return {"registered_root_slots": len(records), "valid_saved_public_views": len(valid),
        "unavailable_or_invalid_public_views": len(records)-len(valid),
        "registered_no_eligible_root_slots": sum("no_eligible" in str(r["pair_reason"]) for r in records),
        "zero_nonreference_catalog_views": sum(c["K"] <= 1 for c in valid),
        "nonreference_candidate_rows": len(candidates),
        "winner_changed_weight0_to1": sum(c["winner_changes_with_forecast"] for c in valid),
        "full_ranking_changed_weight0_to1": sum(c["ranking_changes_with_forecast"] for c in valid),
        "all_action_marginal_scores_unchanged_within_tolerance": sum(
            c["maximum_absolute_forecast_marginal_score_change"] <= contract["ranking_tolerance"] for c in valid),
        "affected_action_node_proxy_regimes": dict(regimes),
        "forecast_only_demand_opportunities": counts("forecast_only_demand_opportunity"),
        "static_arrival_before_first_positive_forecast_bin": counts("static_arrival_before_first_positive_forecast_bin"),
        "counts_are_repeated_candidate_accounts_not_unique_nodes": True,
        "denominator_scope": "all registered development root slots; no claim to all native callbacks",
        "proxy_saturation_is_global_truth": False, "actual_prearrival_benefit_established": False}


def select_and_freeze(dev_inputs, *, output, contract=None):
    contract = copy.deepcopy(contract or selection_contract())
    require(contract == selection_contract(), "fixed_preregistered_C10_selection_contract")
    datasets = load_dev_inputs(dev_inputs, contract)
    evaluation = evaluate_datasets(datasets, contract)
    method = evaluation["selected_method"]
    frozen = {"schema": SCHEMA, "selected": "reference" if method == "reference" else "strong_rule",
        "forecast_weight": 0 if method == "reference" else int(method[-1]),
        "selected_method": method, "contract": contract, "rule_contract": rule.contract(),
        "rule_contract_sha256": digest(rule.contract()), "source_sha256": source_pins(),
        "dev_inputs": copy.deepcopy(dev_inputs), "evaluation": evaluation,
        "frozen_epoch_seconds": time.time(), "test_opened": False,
        "native_runs_started": 0, "fit_calls": 0, "protected_takeover_eligible": False,
        "selection_is_deployment_nonharm_certificate": False}
    # Per-node explanation maps have integer keys in memory. Canonicalize the
    # persisted JSON representation before binding its immutable identity.
    frozen = json.loads(json.dumps(frozen, ensure_ascii=False, allow_nan=False))
    frozen["selection_id"] = digest(frozen)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(frozen, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_rule_selection(reference):
    frozen = _read(reference)
    require(frozen["schema"] == SCHEMA and frozen["selection_id"] == digest({
        key: value for key, value in frozen.items() if key != "selection_id"})
        and frozen["contract"] == selection_contract()
        and frozen["source_sha256"] == source_pins()
        and frozen["rule_contract"] == rule.contract()
        and frozen["test_opened"] is False, "bound_C10_development_selection")
    return frozen
