"""Verify every saved v2 branch and causal comparison without native execution."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from . import research_synthetic_reuse_v2 as study
from .original_workload import digest, write_json


def verify(directory: Path, original: Path) -> dict:
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    protocol = json.loads((directory / "preregistered_protocol.json").read_text(encoding="utf-8"))
    ledger = json.loads((directory / "branch_ledger.json").read_text(encoding="utf-8"))
    if receipt["status"] != "executed" or receipt["source_changed"]:
        raise ValueError("reuse_v2_verify:invalid_execution")
    scenes, expected_manifest = study.plan_campaign(original)
    if protocol["scenes"] != scenes or protocol["branch_manifest"] != expected_manifest or set(ledger) != set(expected_manifest):
        raise ValueError("reuse_v2_verify:preregistration_or_denominator")
    hashes = {str(directory / name): digest(directory / name) for name in ("receipt.json", "preregistered_protocol.json", "branch_ledger.json")}
    for source, expected in receipt["source_before"].items():
        archived = directory / "source_archive" / Path(source).name
        if digest(archived) != expected:
            raise ValueError("reuse_v2_verify:archive_identity")
        if digest(Path(source)) != expected:
            raise ValueError("reuse_v2_verify:current_verification_source_drift")
    raw_by_key, original_comparisons = {}, {}
    for fullkey, row in ledger.items():
        expected = expected_manifest[fullkey]
        for field in ("gate", "initial_next", "departure", "later_mode", "phase"):
            if row[field] != expected[field]:
                raise ValueError("reuse_v2_verify:action_binding")
        folder, label = fullkey.split("/")
        raw_path = directory / folder / f"{label}.json.gz"
        raw = study.timing.read_gzip(raw_path)
        hashes[str(raw_path)] = digest(raw_path)
        raw_by_key[fullkey] = raw
        data = json.loads((directory / folder / "input.json").read_text(encoding="utf-8"))
        scene = scenes[str(row["gate"])]
        if data != scene["input"] or raw["checkpoint_identity"] != scene["old_checkpoint"] or raw["seed_views"] != scene["views"]:
            raise ValueError("reuse_v2_verify:checkpoint_input_information")
        for field in ("gate", "initial_next", "departure", "later_mode", "phase"):
            if raw["specification"][field] != expected[field]:
                raise ValueError("reuse_v2_verify:raw_action_binding")
        client = SimpleNamespace(rows=raw["outbox"], calls=raw["calls"])
        summary = study.assess_cell(data, raw["result"], client, raw["continuation"], row)
        if summary != row["summary"] or summary != raw["summary"] or summary["status"] != "assessed":
            raise ValueError("reuse_v2_verify:reassessment")
        first_calls, immutable = {}, {}
        for call in raw["calls"]:
            identity = call["request"]["request_id"]
            if immutable.setdefault(identity, call["request"]) != call["request"]:
                raise ValueError("reuse_v2_verify:mutated_retry")
            if not call["retry"]:
                if identity in first_calls:
                    raise ValueError("reuse_v2_verify:duplicate_new_identity")
                first_calls[identity] = call
        line = raw["continuation"]["supply_lineage"]
        first_supply = first_calls[line[0]]
        if first_supply["at"] != study.v1.START or first_supply["request"]["earliest_departure"] != row["departure"]:
            raise ValueError("reuse_v2_verify:initial_window")
        for identity in line:
            request = first_calls[identity]["request"]
            if (request["owner_id"], request["tray_id"], request["source"], request["destination"], request["expiry"], request["message_delay"]) != ("B", "E", 5, 1, 39., .01):
                raise ValueError("reuse_v2_verify:supply_contract")
        for index, decision in enumerate(raw["continuation"]["recovery_decisions"]):
            view = {"now": decision["at"], "trays": [decision["local_tray"]], "delivered_messages": [decision["delivered_demand"]]}
            basis = study.recovery_basis(view, client.rows[line[index]], index + 1)
            if not basis or {**basis, "request_id": line[index + 1]} != decision:
                raise ValueError("reuse_v2_verify:recovery_causality")
            call = first_calls[decision["request_id"]]
            if call["at"] != decision["at"] or call["request"]["earliest_departure"] != decision["at"]:
                raise ValueError("reuse_v2_verify:recovery_time")
        for choice in raw["continuation"]["route_choices"]:
            if any(m["delivered_at"] > choice["at"] for m in choice["delivered_forecasts"]):
                raise ValueError("reuse_v2_verify:forecast_before_delivery")
            view = {"now": choice["at"], "owner_id": "B", "node_records": data["node_records"],
                "edge_records": data["edge_records"], "node_contracts": [choice["local_node3"]] if "local_node3" in choice else [],
                "delivered_messages": choice["delivered_forecasts"]}
            decision = study.later_choice(view, choice["local_tray"], row["later_mode"])
            if any(choice[k] != v for k, v in decision.items()):
                raise ValueError("reuse_v2_verify:later_rule")
            if choice["request_id"]:
                request = first_calls[choice["request_id"]]["request"]
                tray = choice["local_tray"]
                if (request["owner_id"], request["tray_id"], request["business_bag_id"], request["from"], request["next"], request["expected_generation"], request["expected_traversal"]) != ("B", "L", choice["job"], 7, choice["next"], tray["generation"], tray["traversal_id"]):
                    raise ValueError("reuse_v2_verify:route_action")
                edge = next(r for r in raw["result"]["receipts"] if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == choice["job"] and r["from"] == 7)
                if client.rows[choice["request_id"]]["ack"]["delivered_at"] > edge["time"]:
                    raise ValueError("reuse_v2_verify:route_ack_after_edge")
        for decision in raw["continuation"]["returns"]:
            if decision["delivered_demand"]["delivered_at"] > decision["at"]:
                raise ValueError("reuse_v2_verify:return_before_demand")
        if row["phase"] == "old24":
            prior = study.timing.read_gzip(original / folder / f"{label.removeprefix('old_')}.json.gz")
            fields = {field: raw["result"][field] == prior["result"][field] for field in ("jobs", "trays", "transfers", "leg_identities")}
            def physical(branch):
                route_ids = {identity for identity, entry in branch["outbox"].items() if entry["kind"] == "route"}
                # Native command ACK reasons end with an immutable request ID
                # followed by the transport attempt. Remove only route ACKs;
                # transfer, demand, forecast and physical receipts stay exact.
                return [r for r in branch["result"]["receipts"]
                    if not r["event"].startswith("ROUTE_INTENT_")
                    and not (r["event"] == "PROTOCOL_COMMAND_ACK_DELIVERED"
                        and r["reason"].rsplit(":", 1)[0] in route_ids)]
            fields["physical_receipts_excluding_route_commands_and_their_delivered_acks"] = physical(raw) == physical(prior)
            original_comparisons[fullkey] = fields
    recalculated = study.reports(ledger, scenes)
    if recalculated != receipt["reports"]:
        raise ValueError("reuse_v2_verify:reference_report")
    causal = []
    for gate in study.v1.GATES:
        for route, window in [(2, 0), (1, 3)]:
            prefix = f"gate{int(gate)}/"
            adaptive = raw_by_key[f"{prefix}old_route{route}_window{window}"]
            baseline = ledger[f"{prefix}old_route1_window1"]["summary"]["completion"]
            for mode in ("occupancy_only", "native_keep"):
                ablation = raw_by_key[f"{prefix}ablate_route{route}_window{window}_{mode}"]
                a, b = adaptive["summary"]["completion"], ablation["summary"]["completion"]
                causal.append({"gate": gate, "initial_next": route, "old_window": window, "ablation": mode,
                    "adaptive_minus_ablation_per_job_seconds": {j: a[j] - b[j] for j in a},
                    "adaptive_protected": all(a[j] <= baseline[j] for j in a),
                    "ablation_protected": all(b[j] <= baseline[j] for j in b),
                    "adaptive_later_edges": adaptive["summary"]["actual_later_choices"],
                    "ablation_later_edges": ablation["summary"]["actual_later_choices"],
                    "scope": "Matched initial-action causal ablation; not same-continuation kappa"})
    protected_bypass = []
    for key, row in ledger.items():
        baseline = ledger[f"gate{int(row['gate'])}/old_route1_window1"]["summary"]["completion"]
        if row["later_mode"] == "adaptive" and all(t <= baseline[j] for j, t in row["summary"]["completion"].items()) and any(c["selected_next"] == 8 for c in row["summary"]["actual_later_choices"]):
            protected_bypass.append(key)
    return {"schema": "g31.lt2.reuse_v2_independent_verification.v1", "status": "verified", "native_branch_count": len(ledger),
        "all117_raw_reassessed": True, "all117_sources_checkpoints_actions_and_causal_messages_checked": True,
        "source_archive_hashes_match": True, "old24_physical_comparisons": original_comparisons,
        "old24_all_physical_fields_equal": all(all(v.values()) for v in original_comparisons.values()),
        "supply_recovery_branch_count": sum(r["summary"]["recovered_rejection_count"] > 0 for r in ledger.values()),
        "retained_and_recovered_receiving_full_rejections": sum(r["summary"]["recovered_rejection_count"] for r in ledger.values()),
        "protected_adaptive_cells_with_later_bypass8": protected_bypass,
        "causal_ablations": causal, "reports": recalculated, "evidence_hashes": hashes,
        "complete_100ms_requirement_certified": False, "extra_native_branches": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--original-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("reuse_v2_verify:output_exists")
    report = verify(args.evidence, args.original_study)
    report["verifier_sha256"] = digest(Path(__file__))
    write_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"reports", "evidence_hashes", "causal_ablations", "old24_physical_comparisons"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
