"""Closed-run terminal-flow chain and matched-public-state decision audits.

Pure offline evidence: no native constructor, policy dispatch, budget mutation
or live stream consumption. Plan items, issued orders and requests have distinct
deduplication keys so rolling suggestions never masquerade as delivered trays.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from .foundation_airport_batch_patch import digest
from .foundation_airport_inventory_spi_campaign import read_bound
from .foundation_airport_json_stream import iter_json_array_gz
from .foundation_airport_transport_evidence import binding, read

SCHEMA = "g31.terminal_flow.native_chain_audit.v1"
ACCEPTED = {"accepted", "granted", "dispatching", "departed", "in_transit", "received"}


def action_key(action):
    return tuple(action.get(k) for k in ("kind", "tray_id", "source", "destination"))


def closed_run(directory):
    directory = Path(directory)
    plan, receipt = read(directory/"plan.json"), read(directory/"receipt.json")
    if (receipt.get("process", {}).get("exitcode") != 0
            or receipt["worker"].get("scientific_status") != "closed"
            or receipt["worker"].get("process_status") != "completed"
            or receipt["worker"].get("final_physical_time") != plan["horizon"]):
        raise ValueError("terminal_flow_audit:closed_native_run_required")
    if receipt.get("plan_sha256") != binding(directory/"plan.json")["sha256"]:
        raise ValueError("terminal_flow_audit:receipt_plan_binding")
    trajectory = read(directory/"trajectory.json.gz")
    worker_path = directory/"worker_report.json"
    if not worker_path.exists() or read(worker_path) != receipt["worker"]:
        raise ValueError("terminal_flow_audit:worker_report_binding")
    if (trajectory.get("scientific_status") != "closed_finite_horizon"
            or trajectory.get("physical_clock") != plan["horizon"]
            or trajectory.get("process_status") != "completed" or trajectory.get("logs_complete") is not True):
        raise ValueError("terminal_flow_audit:closed_trajectory_clock")
    return plan, receipt, trajectory


def audit_records(decisions, trajectory_rows, terminal):
    """Join recorded plan/order metadata to actual request and native outcome."""
    trajectories = {r["decision_id"]: r for r in trajectory_rows}
    native = {r["request_id"]: r for r in terminal.get("transfers", [])}
    plans, issued_orders, request_to_order, counts, violations = {}, {}, {}, Counter(), []
    choices = []
    for decision in decisions:
        identity = decision["decision_id"]
        if identity not in trajectories:
            counts["final_endpoint_excluded_from_trajectory"] += 1
            continue
        row, choice = trajectories[identity], decision.get("selection", {})
        action = row["requested_action"]
        choices.append(dict(owner_id=row["owner_id"], at=row["decision_time"],
            public_state_digest=row["public_observation_ref"], catalog_id=row["legal_catalog_ref"],
            action=list(action_key(action)), flow_plan_id=row.get("flow_plan_id")))
        counts["policy_decisions"] += 1
        counts["cache_hits"] += bool(row.get("flow_cache", {}).get("hit"))
        counts["fallback_decisions"] += choice.get("fallback_reason") is not None
        plan = choice.get("flow_plan")
        if plan is None:
            continue
        pid = plan["plan_id"]
        item_keys = {(a["tray_id"], a["source"], a["destination"]) for a in plan.get("chosen", [])}
        if len(item_keys) != len(plan.get("chosen", [])):
            violations.append(dict(decision_id=identity, reason="duplicate_item_within_plan"))
        if pid not in plans:
            plans[pid] = dict(plan_id=pid, owner_scope=plan["owner_scope"],
                information_asof=plan["information_asof"], valid_until=plan["plan_valid_until"],
                forecast_id=plan.get("forecast_id"), item_keys=item_keys,
                chosen=plan.get("chosen", []), flows=plan.get("flows", []),
                dispatch_profile=plan.get("dispatch_profile", []),
                proxy_flow_objective_cost=plan.get("proxy_flow_objective_cost"),
                hold_quantity=plan.get("hold_quantity"), station_table=plan.get("station_table"),
                occurrences=0, linked_order_ids=set(), fulfilled_item_keys=set())
        elif plans[pid]["item_keys"] != item_keys:
            violations.append(dict(plan_id=pid, reason="same_plan_id_changed_items"))
        plans[pid]["occurrences"] += 1
        metadata = choice.get("empty_transport_order")
        if metadata is None:
            continue
        oid = metadata["order_id"]
        if oid in issued_orders:
            if issued_orders[oid]["decision_id"] != identity:
                violations.append(dict(order_id=oid, reason="same_order_in_distinct_decisions"))
            continue
        category = action.get("source_category")
        ordinary = category == "ordinary_return"
        expected_reason = "ORDINARY_RETURN" if ordinary else "FORECAST_REPOSITION"
        if metadata.get("reason") != expected_reason:
            violations.append(dict(order_id=oid, reason="metadata_category_disagrees_with_legal_source"))
        if any(metadata.get(k) != action.get(a) for k, a in
               (("physical_tray_id", "tray_id"), ("source_terminal", "source"), ("destination_terminal", "destination"))):
            violations.append(dict(order_id=oid, reason="metadata_action_identity_mismatch"))
        request = row.get("actual_submission")
        rid = row.get("request_id") or (request or {}).get("request_id")
        if rid is not None:
            if rid in request_to_order and request_to_order[rid] != oid:
                violations.append(dict(request_id=rid, reason="request_bound_to_multiple_orders"))
            request_to_order[rid] = oid
        transfer = native.get(rid)
        acknowledgements = row.get("ack") or []
        accepted = any(a.get("status") in ACCEPTED for a in acknowledgements)
        received = row.get("received_event") is not None
        if received and not accepted:
            violations.append(dict(order_id=oid, reason="physical_receipt_without_delivered_acceptance_evidence"))
        item_key = (action.get("tray_id"), action.get("source"), action.get("destination"))
        in_plan = item_key in item_keys
        if received and in_plan:
            plans[pid]["fulfilled_item_keys"].add(item_key)
        profile = next((x for x in plan.get("dispatch_profile", [])
                        if (x["tray_id"], x["source"], x["destination"]) == item_key), None)
        chain = dict(order_id=oid, decision_id=identity, plan_id=pid, request_id=rid,
            owner_id=row["owner_id"], proposed_at=row["decision_time"], physical_tray_id=action.get("tray_id"),
            source=action.get("source"), destination=action.get("destination"),
            classification="ordinary_return" if ordinary else "extra_reposition",
            classification_basis="actual legal source_category; ordinary rerouting counterfactual not inferred",
            forecast_guided=metadata.get("forecast_guided"), plan_item_match=in_plan,
            fallback_reason=choice.get("fallback_reason"), requested_order=metadata,
            actual_submission=request, submission_reply=row.get("reply_or_rejection"),
            accepted=accepted, delivered_acks=acknowledgements, received=received,
            native_transfer_at_export=transfer, first_edge_event=row.get("first_edge_event"),
            received_event=row.get("received_event"), physical_failure=bool(row.get("physical_failure")),
            exact_first_action_verification=row.get("flow_verification", choice.get("flow_verification")),
            planned_dispatch=profile, actual_submit_minus_plan_seconds=(None if profile is None or request is None else
                request["issued_at"]-profile["submit_at"]))
        issued_orders[oid] = chain
        plans[pid]["linked_order_ids"].add(oid)
    plan_rows = []
    for plan in plans.values():
        item_count, received_count = len(plan["item_keys"]), len(plan["fulfilled_item_keys"])
        plan_rows.append({k: v for k, v in plan.items() if k not in
            ("item_keys", "fulfilled_item_keys", "linked_order_ids", "chosen") } | dict(
                item_count=item_count, issued_order_count=len(plan["linked_order_ids"]),
                received_item_count=received_count,
                received_per_suggested_item=None if not item_count else received_count/item_count,
                linked_order_ids=sorted(plan["linked_order_ids"]),
                source_proposals=[{k: x.get(k) for k in ("tray_id", "source", "destination", "source_category",
                    "source_actual_unpledged", "source_fifo_reserved", "hard_eligibility_reasons",
                    "marginal_source_cost", "marginal_receiver_benefit", "suggested_submit_at", "suggested_arrival_at")}
                    for x in plan["chosen"]]))
    chains = list(issued_orders.values())
    accepted_ids = {x["request_id"] for x in chains if x["accepted"] and x["request_id"] is not None}
    received_ids = {x["request_id"] for x in chains if x["received"] and x["request_id"] is not None}
    per_category = {}
    for category in ("ordinary_return", "extra_reposition"):
        subset = [x for x in chains if x["classification"] == category]
        per_category[category] = dict(unique_orders=len(subset),
            unique_submitted_requests=len({x["request_id"] for x in subset if x["request_id"] is not None}),
            unique_accepted_requests=len({x["request_id"] for x in subset if x["accepted"] and x["request_id"] is not None}),
            unique_received_requests=len({x["request_id"] for x in subset if x["received"] and x["request_id"] is not None}))
    planned_items = sum(x["item_count"] for x in plan_rows)
    received_items = sum(x["received_item_count"] for x in plan_rows)
    return dict(counts=dict(counts), denominators=dict(unique_plan_ids=len(plans),
        unique_plan_item_keys=planned_items, unique_order_ids=len(chains), unique_submitted_request_ids=len(request_to_order),
        unique_accepted_request_ids=len(accepted_ids), unique_received_request_ids=len(received_ids),
        received_per_submitted=None if not request_to_order else len(received_ids)/len(request_to_order),
        received_per_issued_order=None if not chains else len(received_ids)/len(chains),
        realized_items_per_unique_plan_item=None if not planned_items else received_items/planned_items,
        plan_item_identity="(plan_id, tray_id, source, destination); cached repeats excluded; replans are distinct suggestions",
        later_replan_deliveries_credited_to_old_plan=False), by_source_category=per_category,
        plans=plan_rows, order_chains=chains, decision_choices=choices, violations=violations)


def audit_run(directory):
    directory = Path(directory)
    plan, receipt, trajectory = closed_run(directory)
    if not plan["method"].startswith("TF"):
        raise ValueError("terminal_flow_audit:transport_method_required")
    result = audit_records(iter_json_array_gz(directory/"decisions.json.gz"), trajectory["rows"],
                           read(directory/"terminal_evidence.json.gz"))
    return dict(schema=SCHEMA, task_id=plan["task_id"], method=plan["method"],
        parent=plan["parent"], horizon=plan["horizon"], system_J=trajectory["system_J"],
        native_starts=0, cost=receipt["worker"].get("cost"),
        evidence={name: binding(directory/name) for name in ("plan.json", "receipt.json", "decisions.json.gz",
            "trajectory.json.gz", "terminal_evidence.json.gz", "controller_checkpoint_scope.json")},
        **result, unified_order_book=audit_unified_order_book(directory),
        limitations=["finite-window mechanism audit; no full-window or TEST service improvement implied",
            "protected ordinary returns and optional reposition are classified by actual source role",
            "ordinary destination redirection benefit requires matched-rule comparison; forecast_guided alone is not proof",
            "plan suggestions are not simultaneously dispatched; only actual controller submissions are requests"])


def audit_unified_order_book(directory):
    """All reasons: actual demand, clearing, ordinary return and anticipation."""
    directory = Path(directory)
    checkpoint = read(directory/"controller_checkpoint_scope.json")
    book = (checkpoint.get("policy_state") or {}).get("empty_transport_orders", {})
    orders = book.get("orders", {})
    calls = {row["request"]["request_id"]: row for row in iter_json_array_gz(directory/"calls.json.gz")
             if row.get("kind") == "transfer" and not row.get("retry")}
    terminal = read(directory/"terminal_evidence.json.gz")
    native = {row["request_id"]: row for row in terminal["transfers"]}
    ack_index = defaultdict(list)
    ack_views = read(directory/"delivered_ack_evidence.json.gz")
    for view in ack_views.values():
        for ack in view.get("delivered_transfer_acks", []):
            ack_index[ack["request_id"]].append(ack)
    request_ids, chains, violations = set(), [], []
    categories = defaultdict(Counter)
    for order in orders.values():
        rid = order.get("request_id")
        if rid is None:
            continue
        if rid in request_ids:
            violations.append(dict(request_id=rid, reason="duplicate_order_request_identity"))
        request_ids.add(rid)
        call, actual = calls.get(rid), native.get(rid)
        payload = call["request"] if call else {}
        for field, source in (("physical_tray_id", "tray_id"), ("source_terminal", "source"),
                              ("destination_terminal", "destination"), ("owner_scope", "owner_id")):
            if call and order[field] != payload.get(source):
                violations.append(dict(request_id=rid, reason="order_payload_identity_mismatch", field=field))
        if call and order["native_expiry"] != payload.get("expiry"):
            violations.append(dict(request_id=rid, reason="departure_lease_changed"))
        leaked = sorted({"target_by", "useful_until", "plan_valid_until", "latest_issue_estimate"} & set(payload))
        if leaked:
            violations.append(dict(request_id=rid, reason="soft_order_times_in_native_payload", fields=leaked))
        accepted = any(a.get("status") in ACCEPTED for a in ack_index[rid])
        received = actual is not None and actual.get("received_at", -1) >= 0
        phase = "priority" if order.get("plan_id") is None else "post_priority"
        reason = order["reason"]
        categories[reason]["orders"] += 1
        categories[reason]["submitted"] += call is not None
        categories[reason]["accepted"] += accepted
        categories[reason]["received"] += received
        categories[reason]["failed_at_export"] += actual is not None and actual.get("status") in {"failed", "rejected", "expired"}
        chains.append(dict(order_id=order["order_id"], request_id=rid, reason=reason,
            phase=phase, phase_basis="plan_id present versus priority hook; phase not separately serialized",
            status=order["status"], native_status=None if actual is None else actual["status"],
            owner_scope=order["owner_scope"], source=order["source_terminal"], destination=order["destination_terminal"],
            physical_tray_id=order["physical_tray_id"], proposed_at=order["proposed_at"],
            target_by=order.get("target_by"), useful_until=order.get("useful_until"),
            plan_valid_until=order.get("plan_valid_until"), native_expiry=order["native_expiry"],
            payload_expiry=payload.get("expiry"), soft_fields_passed_to_native=leaked,
            accepted=accepted, received=received, native_transfer=actual,
            delivered_acks=ack_index[rid], actual_submission=payload if call else None))
    return dict(unique_order_requests=len(request_ids), unique_actual_submit_requests=len(calls),
        unique_native_requests=len(native), request_sets_equal=request_ids == set(calls) == set(native),
        native_without_order=sorted(set(native)-request_ids), order_without_actual_submit=sorted(request_ids-set(calls)),
        actual_submit_without_order=sorted(set(calls)-request_ids),
        by_reason={reason: dict(counts) for reason, counts in categories.items()},
        reason_coverage={reason: reason in categories for reason in
            ("REAL_DEMAND_SUPPLY", "NECESSARY_CLEARING", "ORDINARY_RETURN", "FORECAST_REPOSITION")},
        violations=violations, chains=chains,
        source_checkpoint=binding(directory/"controller_checkpoint_scope.json"),
        source_delivered_acks=binding(directory/"delivered_ack_evidence.json.gz"))


def compare_decisions(left_directory, right_directory):
    left, right = [audit_run(path) for path in (left_directory, right_directory)]
    la, ra = [{(r["owner_id"], r["at"]): r for r in run["decision_choices"]} for run in (left, right)]
    common = sorted(set(la) & set(ra))
    rows = [dict(owner_id=k[0], at=k[1], same_public_state=la[k]["public_state_digest"] == ra[k]["public_state_digest"],
        same_catalog=la[k]["catalog_id"] == ra[k]["catalog_id"], changed_action=la[k]["action"] != ra[k]["action"],
        left_action=la[k]["action"], right_action=ra[k]["action"]) for k in common]
    same = [r for r in rows if r["same_public_state"] and r["same_catalog"]]
    return dict(schema=SCHEMA+".matched_decisions", left_task=left["task_id"], right_task=right["task_id"],
        common_owner_times=len(rows), left_only_owner_times=len(set(la)-set(ra)), right_only_owner_times=len(set(ra)-set(la)),
        same_public_state_and_catalog_count=len(same),
        changed_action_same_public_state_and_catalog=sum(r["changed_action"] for r in same),
        changed_action_all_common_times=sum(r["changed_action"] for r in rows),
        changed_rows=[r for r in rows if r["changed_action"]],
        interpretation="only same-state same-catalog choices isolate representation at that callback; divergent paths are not pointwise counterfactuals")


def baseline_equivalence(left_directory, right_directory):
    from .foundation_airport_transport_campaign import comparison_contract
    directories = [Path(x) for x in (left_directory, right_directory)]
    left, right = [closed_run(path) for path in directories]
    plans, receipts, trajectories = list(zip(left, right))
    sources = [read_bound(p["source_bundle"]) for p in plans]
    terminal = [read(path/"terminal_evidence.json.gz") for path in directories]
    checkpoints = [read(path/"controller_checkpoint_scope.json") for path in directories]
    fields = ("physical_clock", "jobs", "trays", "transfers", "receipts", "leg_identities")
    physical_present = {k: all(k in row for row in terminal) for k in fields}
    physical_equal = {k: terminal[0].get(k) == terminal[1].get(k) for k in fields}
    actions = [[(r["owner_id"], r["decision_time"], r["requested_action"]) for r in t["rows"]] for t in trajectories]
    observations = [[r["digest"] for r in iter_json_array_gz(path/"observations.json.gz")] for path in directories]
    calls = [[(r["at"], r["kind"], r.get("retry"), r["request"], r["reply"])
              for r in iter_json_array_gz(path/"calls.json.gz")] for path in directories]
    contracts = {k: plans[0].get(k) == plans[1].get(k) for k in
        ("method", "parent", "input", "binary", "controller", "activation", "horizon", "supply_mode", "projection_horizon_seconds")}
    fixed = [comparison_contract(plan) for plan in plans]
    # This is a finite-window implementation bridge, not an experimental pair.
    # Source/export metadata may differ; no demand, allocator or timing axis may.
    allowed_metadata = ("sources", "worker_evidence_contract")
    fixed_equal = {key: fixed[0].get(key) == fixed[1].get(key)
                   for key in sorted(set(fixed[0]) | set(fixed[1])) if key not in allowed_metadata}
    worker_costs = [receipt["worker"].get("cost") for receipt in receipts]
    native_digests = [checkpoint.get("native_state_sha256") for checkpoint in checkpoints]
    checks = dict(terminal_physical_fields_present=all(physical_present.values()),
        terminal_history_fields_well_typed=all(isinstance(row.get(key), list)
            for row in terminal for key in fields if key != "physical_clock"),
        terminal_clocks_at_registered_horizon=all(row.get("physical_clock") == plan["horizon"]
            for row, plan in zip(terminal, plans)),
        terminal_timestamp_complete=all(row.get("advance", {}).get("status") == "reached"
            and row.get("advance", {}).get("horizon_complete") is True for row in terminal),
        native_state_digests_present=all(isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value) for value in native_digests),
        native_state_digests_equal=native_digests[0] == native_digests[1],
        checkpoint_clocks_at_registered_horizon=all(checkpoint.get("physical_time") == plan["horizon"]
            for checkpoint, plan in zip(checkpoints, plans)),
        terminal_physical_fields_equal=all(physical_equal.values()), physical_contract_equal=all(contracts.values()),
        fixed_policy_information_contract_equal=all(fixed_equal.values()),
        selected_canonical_actions_equal=actions[0] == actions[1],
        public_observation_digests_equal=observations[0] == observations[1],
        protocol_payloads_replies_and_times_equal=calls[0] == calls[1],
        system_J_equal=trajectories[0]["system_J"] == trajectories[1]["system_J"],
        worker_cost_present=all(isinstance(cost, dict) and bool(cost) for cost in worker_costs),
        worker_cost_equal=worker_costs[0] == worker_costs[1])
    passed = all(checks.values())
    return dict(schema=SCHEMA+".baseline_equivalence", left_task=plans[0]["task_id"], right_task=plans[1]["task_id"],
        evidence=[{name: binding(path/name) for name in ("plan.json", "receipt.json", "trajectory.json.gz",
            "terminal_evidence.json.gz", "observations.json.gz", "calls.json.gz",
            "controller_checkpoint_scope.json")} for path in directories],
        physical_contract_equal=contracts, terminal_physical_fields_present=physical_present,
        terminal_physical_fields_equal=physical_equal, fixed_policy_information_contract_equal=fixed_equal,
        required_equivalence_checks=checks, failed_equivalence_checks=[key for key, ok in checks.items() if not ok],
        selected_canonical_actions_equal=actions[0] == actions[1], public_observation_digests_equal=observations[0] == observations[1],
        protocol_payloads_replies_and_times_equal=calls[0] == calls[1],
        system_J=[t["system_J"] for t in trajectories], worker_cost_equal=checks["worker_cost_equal"],
        same_finite_run_behavior=passed, sources_interchangeable=False,
        allowed_implementation_bridge_metadata_differences=list(allowed_metadata),
        changed_source_files=sorted(k for k in sources[0]["files"].keys() & sources[1]["files"].keys()
                                    if sources[0]["files"][k] != sources[1]["files"][k]),
        added_source_files=sorted(set(sources[1]["files"]) - set(sources[0]["files"])),
        removed_source_files=sorted(set(sources[0]["files"]) - set(sources[1]["files"])),
        changed_plan_fields=sorted(k for k in plans[0].keys() | plans[1].keys() if plans[0].get(k) != plans[1].get(k)),
        export_added_fields=sorted(set(terminal[1]) - set(terminal[0])),
        interpretation="empirical equivalence for this closed parent/window only; different sources are not universally interchangeable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run"); p.add_argument("directory", type=Path)
    for name in ("compare-decisions", "baseline-equivalence"):
        p = sub.add_parser(name); p.add_argument("left", type=Path); p.add_argument("right", type=Path)
    for p in sub.choices.values():
        p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("terminal_flow_audit:fresh_output_required")
    result = (audit_run(args.directory) if args.command == "run" else
              compare_decisions(args.left, args.right) if args.command == "compare-decisions" else
              baseline_equivalence(args.left, args.right))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output.resolve()), schema=result["schema"], native_starts=0)))


if __name__ == "__main__":
    main()
