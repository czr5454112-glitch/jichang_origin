"""Compact actual terminal-flow cases and censored native resource evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .foundation_airport_batch_patch import ACTIVE, digest
from .foundation_airport_inventory_spi_campaign import read_bound
from .foundation_airport_json_stream import iter_json_array_gz
from .foundation_airport_terminal_flow_audit import closed_run
from .foundation_airport_terminal_service_audit import require
from .foundation_airport_transport_evidence import binding, read


def source_ceiling(decision, observation):
    """Recompute the frozen offer formula from public contracts and candidates."""
    require(digest(observation) == decision['public_observation_ref'] == decision['catalog']['public_state_digest'],
            'case_observation_catalog_binding')
    source = decision['requested_action']['source']
    contract = next(row for row in observation['node_contracts'] if row['node'] == source)
    pledged = {row['tray_id'] for row in list(observation.get('client_transfer_ledger', []))
               + list(observation.get('transfers', [])) if row.get('status') in ACTIVE}
    actions = [row for row in decision['catalog']['candidates']
               if row.get('kind') == 'transfer' and row['source'] == source and row['tray_id'] not in pledged]
    require(bool(actions), 'selected_source_has_unpledged_legal_candidates')
    minimum = int(contract.get('export_min_stock', 0))
    category = actions[0]['source_category']
    require(all(row['source_category'] == category for row in actions), 'consistent_source_category')
    reserve = max(1, minimum) if category == 'loader_optional' else minimum
    cap = min(len({row['tray_id'] for row in actions}), *(max(0,
        row['source_actual_unpledged']-row['source_fifo_reserved']-reserve) for row in actions))
    plan = decision['selection']['flow_plan']
    selected_count = sum(row['source'] == source for row in plan['chosen'])
    require(selected_count <= cap, 'plan_respects_recomputed_source_cap')
    recorded = plan.get('source_offers', {}).get(str(source), plan.get('source_offers', {}).get(source))
    if recorded is not None:
        require(recorded['source_cap'] == cap and recorded['hard_minimum_reserve'] == reserve,
                'recorded_source_offer_matches_recomputation')
    return dict(source_export_min_stock=minimum, source_hard_minimum_reserve=reserve,
        source_cap=cap, source_offer_eligible_unique_trays=len({row['tray_id'] for row in actions}),
        selected_quantity_from_source=selected_count, plan_respects_source_cap=True,
        source_cap_basis='public contract and unpledged catalog candidates; hard reserve is separate from FIFO reserve')


def case_row(decision, chain, *, cutoff, source_evidence=None):
    action, plan = decision["requested_action"], decision["selection"]["flow_plan"]
    selected = next(item for item in plan["chosen"] if item["tray_id"] == action["tray_id"])
    stations = {row["node"]: row for row in plan["station_table"]}
    projection = chain["exact_first_action_verification"]["exact_projection"]
    native, dispatch = chain["native_transfer_at_export"], chain["planned_dispatch"]
    received = native["received_at"] if native["received_at"] >= 0 else None
    departed = native["departed_at"] if native["departed_at"] >= 0 else None
    failed = native["status"] in ("failed", "rejected", "expired", "cancelled")
    censored = received is None and not failed
    legal = [row for row in decision["catalog"]["candidates"] if row.get("kind") == "transfer"]
    return dict(order_id=chain["order_id"], plan_id=chain["plan_id"], request_id=chain["request_id"],
        decision_id=chain["decision_id"], at=chain["proposed_at"], source=action["source"],
        destination=action["destination"], physical_tray_id=action["tray_id"], classification=chain["classification"],
        source_actual_empty=stations[action["source"]]["actual_empty"],
        source_actual_unpledged=selected["source_actual_unpledged"], source_fifo_reserved=selected["source_fifo_reserved"],
        source_legal_unique_trays=len({row["tray_id"] for row in legal if row["source"] == action["source"]}),
        all_legal_unique_trays=len({row["tray_id"] for row in legal}),
        destination_actual_empty=stations[action["destination"]]["actual_empty"],
        destination_current_waiting=decision["features_current"]["destination_waiting"],
        destination_forecast_backlog_at_600_without_move=projection["destination_without_move"]["ending_backlog"],
        destination_forecast_first_shortage_offset=projection["destination_without_move"]["first_shortage_offset"],
        target_deficit_basis="600-second finite-rate single-use forecast projection, not observed waiting bags",
        suggested_quantity=len(plan["chosen"]), submitted_quantity=1,
        planned_dispatch_slot=dispatch["dispatch_slot"], planned_submit_at=dispatch["submit_at"],
        planned_earliest_departure=dispatch["earliest_departure"], estimated_arrival=dispatch["estimated_arrival"],
        optimistic_advisory_only=True, exact_first_net_proxy_gain=chain["exact_first_action_verification"]["exact_net_gain"],
        target_by=chain["requested_order"]["target_by"], native_expiry=chain["actual_submission"]["expiry"],
        native_accepted=chain["accepted"], native_status=native["status"], native_delivered_at=native["delivered_at"],
        native_departed_at=departed, native_received_at=received, received_censored=censored,
        native_failed=failed,
        in_transit_seconds_lower_bound=(cutoff-departed if departed is not None and censored else None),
        eta_error_seconds=(received-dispatch["estimated_arrival"] if received is not None else None),
        eta_error_lower_bound_seconds=(cutoff-dispatch["estimated_arrival"] if censored else None),
        **(source_evidence or {}))


def audit_cases(directory, chain_audit_path):
    directory = Path(directory)
    plan, _, _ = closed_run(directory)
    audit = read(chain_audit_path)
    require(audit["task_id"] == plan["task_id"], "chain_task_binding")
    for name, ref in audit["evidence"].items():
        require(binding(directory/name)["sha256"] == ref["sha256"], "chain_evidence_changed:"+name)
    chains = {row["decision_id"]: row for row in audit["order_chains"]}
    decisions = [row for row in iter_json_array_gz(directory/"decisions.json.gz") if row["decision_id"] in chains]
    needed_observations = {row['public_observation_ref'] for row in decisions}
    observations = {row['digest']: row['observation'] for row in iter_json_array_gz(directory/'observations.json.gz')
                    if row['digest'] in needed_observations}
    require(set(observations) == needed_observations, 'all_selected_public_observations_present')
    cases = [case_row(row, chains[row["decision_id"]], cutoff=plan["horizon"],
        source_evidence=source_ceiling(row, observations[row['public_observation_ref']])) for row in decisions]
    require(len(cases) == len(chains), "each_actual_order_has_one_decision")
    terminal = read(directory/"terminal_evidence.json.gz")
    diagnostic = read(directory/"offline_diagnostics.json.gz")
    graph = read(directory/"wait_graph.json.gz")
    require(terminal["physical_clock"] == diagnostic["now"] == graph["at"] == plan["horizon"], "common_diagnostic_endpoint")
    trays = {row["tray_id"]: row for row in diagnostic["trays"]}
    legs = {row["runtime_id"]: row for row in diagnostic["legs"]}
    junctions = {row["node"]: row for row in diagnostic["junctions"]}
    waits = {row["runtime_id"]: row for row in diagnostic["resource_waits"]}
    specs = {row["business_bag_id"]: row for row in read_bound(plan["input"])["jobs"]}
    inflight = []
    for case in cases:
        if not case["received_censored"] or case["native_departed_at"] is None:
            continue
        tray = trays[case["physical_tray_id"]]
        leg = legs.get(tray["active_leg"])
        events = [row for row in terminal["receipts"] if leg is not None and row.get("transport_leg_id") == leg["transport_leg_id"]]
        progress = [row for row in events if row["event"] in ("EDGE_ENTER", "EDGE_EXIT")]
        queue = junctions.get(tray["node"], {}).get("queue", [])
        preceding = queue[:queue.index(tray["active_leg"])] if tray["active_leg"] in queue else []
        inflight.append(dict(request_id=case["request_id"], final_tray=tray, leg=leg,
            actual_leg_events=events, last_edge_progress=progress[-1] if progress else None,
            no_edge_progress_observed_seconds=(plan["horizon"]-progress[-1]["time"] if progress else None),
            final_local_queue_runtime_ids=queue, preceding_queue_legs=[dict(legs[x], resource_wait=waits.get(x)) for x in preceding],
            direct_resource_wait=waits.get(tray["active_leg"])))
    holds = []
    for edge in graph["edges"]:
        if edge["kind"] != "actual_hold":
            continue
        tray = trays[edge["to"].removeprefix("tray:")]
        job = terminal["jobs"][tray["job_index"]] if tray["job_index"] >= 0 else None
        spec = specs[job["business_bag_id"]] if job is not None else None
        holds.append(dict(edge=edge, tray=tray, business_bag_id=job["business_bag_id"] if job else None,
            storage_release_at=spec.get("storage_release_at") if spec else None,
            planned_storage_release_after_cutoff=bool(spec and spec.get("storage_release_at", -1) > plan["horizon"])))
    return dict(schema="g31.terminal_flow.actual_case_audit.v1", task_id=plan["task_id"], cutoff=plan["horizon"],
        chain_audit=binding(chain_audit_path), evidence={name: binding(directory/name) for name in
            ("plan.json", "receipt.json", "decisions.json.gz", "observations.json.gz", "terminal_evidence.json.gz", "offline_diagnostics.json.gz", "wait_graph.json.gz")},
        unique_planned_items=audit["denominators"]["unique_plan_item_keys"],
        unique_orders=len(cases), native_accepted=sum(row["native_accepted"] for row in cases),
        native_received=sum(row["native_received_at"] is not None for row in cases),
        native_failed=sum(row["native_failed"] for row in cases), cases=cases, censored_inflight=inflight,
        final_wait_graph_edges=graph["edges"], resource_holds=holds,
        witnessed_hold_wait_cycles=graph["witnessed_hold_wait_cycles"],
        permanent_deadlock_proven=False, causal_service_harm_from_these_orders_proven=False,
        multi_order_plan_actual_coverage=sum(row["suggested_quantity"] > 1 for row in cases),
        ordinary_return_actual_coverage=sum(row["classification"] == "ordinary_return" for row in cases), native_starts=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("chain_audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh_output_required")
    result = audit_cases(args.directory, args.chain_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("task_id", "unique_orders", "native_accepted", "native_received", "native_starts")}))


if __name__ == "__main__":
    main()
