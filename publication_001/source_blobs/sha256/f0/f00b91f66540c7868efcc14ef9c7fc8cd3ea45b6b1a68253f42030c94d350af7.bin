"""Read-only diagnosis of every stronger-timing branch, without a native worker."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

from . import reference_reuse_timing as reference
from .original_workload import digest, write_json


def diagnose_branch(raw: dict) -> dict:
    summary, result = raw["summary"], raw["result"]
    selected = [row for row in raw["outbox"].values() if row["kind"] in {"transfer", "route"}]
    pending = []
    for row in selected:
        ack = row.get("ack", {})
        delivered = ack.get("delivered_at")
        if (ack.get("status") not in reference.study.TERMINAL
                or not isinstance(delivered, (int, float)) or not math.isfinite(delivered)
                or not 0 <= delivered <= reference.study.HORIZON):
            pending.append(row["request"]["request_id"])
    horizon = (result.get("advance", {}).get("status") == "reached"
               and result["advance"].get("horizon_complete") is True
               and result["advance"].get("physical_time") == reference.study.HORIZON)
    mismatches = []
    for choice in raw["continuation"]["route_choices"]:
        edges = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER"
                 and r["business_bag_id"] == choice["job"] and r["from"] == 7]
        if len(edges) != 1 or edges[0]["to"] != choice["next"]:
            mismatches.append({"job": choice["job"], "decision_at": choice["at"],
                "declared_next": choice["next"], "request_id": choice["request_id"],
                "actual_edges": [{"at": e["time"], "from": e["from"], "to": e["to"]} for e in edges]})
    initial = [r for r in selected if r["kind"] == "transfer"
               and r["request"]["request_id"].endswith(":initial-supply")]
    ack = initial[0].get("ack", {}) if len(initial) == 1 else {}
    if not horizon:
        category = "unknown_censored_horizon"
    elif pending:
        category = "unknown_unresolved_or_unverifiable_selected_ack"
    elif summary["status"] == "assessed":
        category = "assessed_executable"
    elif (ack.get("status") == "rejected" and ack.get("reason") == "receiving_full"
          and summary.get("completion", {}).get("receiver") == -1.
          and summary.get("audit", {}).get("status") == "passed"):
        category = "proven_selected_initial_intent_rejected_receiving_full"
    elif (mismatches and all(m["declared_next"] == 3 and m["request_id"] is None
                            and len(m["actual_edges"]) == 1 and m["actual_edges"][0]["to"] == 8 for m in mismatches)
          and summary.get("business_complete") is True and summary.get("all_transfers_received") is True
          and summary.get("all_routes_updated") is True and summary.get("same_L_two_returns_and_two_reloads") is True
          and summary.get("audit", {}).get("status") == "passed"):
        category = "declared_keep3_noop_did_not_match_native_next8"
    else:
        category = "unknown_other_execution_contract"
    return {"category": category, "strict_saved_status": summary["status"],
        "horizon_complete": horizon, "unresolved_selected_ack_ids": pending,
        "initial_supply_ack": ack, "later_route_mismatches": mismatches,
        "completion": summary["completion"], "audit_status": summary["audit"]["status"],
        "same_L_two_returns_and_two_reloads": summary["same_L_two_returns_and_two_reloads"],
        "does_not_upgrade_reference_status": True}


def assess_saved(directory: Path) -> dict:
    receipt_path = directory / "receipt.json"
    protocol_path = directory / "preregistered_protocol.json"
    ledger_path = directory / "branch_ledger.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if receipt["status"] not in {"executed", "completed_with_unknowns"} or receipt["source_changed"]:
        raise ValueError("reference_assessment:invalid_execution_receipt")
    if set(ledger) != set(protocol["branch_manifest"]) or len(ledger) != reference.MAX_BRANCHES:
        raise ValueError("reference_assessment:missing_full_denominator")
    archive_valid = {path: digest(directory / "source_archive" / Path(path).name) == expected
                     for path, expected in receipt["source_before"].items()}
    if not all(archive_valid.values()):
        raise ValueError("reference_assessment:source_archive_identity")
    hashes = {str(p): digest(p) for p in (receipt_path, protocol_path, ledger_path)}
    diagnostics, regimes = {}, {}
    old = Path(receipt["original_study"])
    for gate in reference.study.GATES:
        key = str(gate)
        sub = directory / f"gate{int(gate)}"
        data = json.loads((sub / "input.json").read_text(encoding="utf-8"))
        if data != json.loads((old / f"gate{int(gate)}" / "input.json").read_text(encoding="utf-8")):
            raise ValueError("reference_assessment:original_input_not_identical")
        rows = {}
        for fullkey, row in ledger.items():
            if row["gate"] != gate:
                continue
            label = fullkey.split("/")[1]
            raw_path = sub / f"{label}.json.gz"
            raw = reference.read_gzip(raw_path)
            hashes[str(raw_path)] = digest(raw_path)
            client = SimpleNamespace(rows=raw["outbox"], calls=raw["calls"])
            summary = reference.study.assess_cell(data, raw["result"], client, raw["continuation"], row["initial_next"])
            if summary != raw["summary"] or summary != row["summary"]:
                raise ValueError("reference_assessment:summary_drift")
            if raw["checkpoint_identity"] != receipt["regimes"][key]["checkpoint_identity"]:
                raise ValueError("reference_assessment:checkpoint_identity")
            if reference.candidate_plan(data, raw["seed_views"]) != protocol["gates"][key]:
                raise ValueError("reference_assessment:plan_drift")
            expected = protocol["branch_manifest"][fullkey]
            if (row["initial_next"], row["departure"]) != (expected["initial_next"], expected["departure"]):
                raise ValueError("reference_assessment:action_metadata")
            initial_calls = [call for call in raw["calls"] if not call["retry"] and call["kind"] == "transfer"
                             and call["request"]["request_id"].endswith(":initial-supply")]
            if len(initial_calls) != 1 or initial_calls[0]["request"]["earliest_departure"] != row["departure"]:
                raise ValueError("reference_assessment:submitted_departure_mismatch")
            immutable = {}
            for call in raw["calls"]:
                identity = call["request"]["request_id"]
                if immutable.setdefault(identity, call["request"]) != call["request"]:
                    raise ValueError("reference_assessment:mutated_retry")
            for choice in raw["continuation"]["route_choices"]:
                if any(m["delivered_at"] > choice["at"] for m in choice["delivered_forecasts"]):
                    raise ValueError("reference_assessment:future_forecast")
            for decision in raw["continuation"]["returns"]:
                if decision["delivered_demand"]["delivered_at"] > decision["at"]:
                    raise ValueError("reference_assessment:future_demand")
            diagnostics[fullkey] = {"departure": row["departure"], **diagnose_branch(raw)}
            rows[label] = row
        report = reference.assess_gate(rows, protocol["gates"][key], {j["business_bag_id"] for j in data["jobs"]})
        expected_report = copy.deepcopy(receipt["regimes"][key])
        expected_report.pop("checkpoint_identity")
        if not expected_report.pop("original_incumbent_replayed_exactly") or report != expected_report:
            raise ValueError("reference_assessment:regime_drift")
        counts = {}
        for fullkey, diagnostic in diagnostics.items():
            if fullkey.startswith(f"gate{int(gate)}/"):
                counts[diagnostic["category"]] = counts.get(diagnostic["category"], 0) + 1
        best = report["best_observed_protected_fixed_timing_not_minimum_claim"]
        fixed = report["cells"].get(best)
        challenger = report["cells"]["challenger"]
        contrast = (fixed["completion_sum"] - challenger["completion_sum"]
                    if fixed and challenger["all_offered_protected"] else None)
        protected_union_gain = max(0., contrast) if contrast is not None else 0. if fixed else None
        regimes[key] = {"strict_finite_reference_status": report["status"], "diagnostic_counts": counts,
            "best_observed_protected_fixed_cell": best, "best_observed_protected_fixed": fixed,
            "replayed_old_joint_challenger": challenger,
            "observed_pairwise_contrast_seconds_not_reference_optimality": contrast,
            "observed_protected_union_gain_seconds_not_reference_optimality": protected_union_gain,
            "unresolved_finite_reference_minimum": report["best_protected_fixed_timing"],
            "continuous_optimality": "unknown"}
    return {"schema": "g31.lt2.stronger_timing_diagnostics.v1", "status": "saved_evidence_verified",
        "source_archive_hashes_match": archive_valid, "evidence_hashes": hashes,
        "branch_denominator": len(ledger), "offered_job_branch_denominator": 4 * len(ledger),
        "regimes": regimes, "branches": diagnostics,
        "information_scope": "Centralized OFFLINE reference may combine owner A's local loaded_at with public durations. loaded_at is not delivered to B and is NOT a lawful B-only online proposal input. Imported continuing policies still use only their local observations and delivered messages.",
        "unknowns_are_retained": True, "extra_native_branches": 0,
        "complete_100ms_requirement_certified": False,
        "claim": "The old1.41s finite-grid contrast reduces to observed1.401s. Unknown action-contract rows prevent a certified stronger finite-reference minimum; no continuous or online headroom claim."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("reference_assessment:output_already_exists")
    report = assess_saved(args.evidence)
    report["assessor_source_sha256"] = digest(Path(__file__))
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "branch_denominator": report["branch_denominator"],
        "regimes": report["regimes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
