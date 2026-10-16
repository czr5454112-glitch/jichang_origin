"""Read saved finite-domain evidence without running native or changing its verdict."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from . import research_native_preexisting_occupancy as producer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(value, reason):
    if not value:
        raise ValueError("preexisting_diagnostic:" + reason)


def diagnose(directory: Path):
    directory = directory.resolve()
    evidence = {str(directory / name): sha(directory / name) for name in
                ("receipt.json", "branch_ledger.json", "preregistered_protocol.json")}
    receipt, ledger, plan = (read(directory / name) for name in
                             ("receipt.json", "branch_ledger.json", "preregistered_protocol.json"))
    require(set(ledger) == set(plan["rows"]) == set(receipt["raw_artifacts"]), "denominator")
    require(receipt["source_changed"] == [] and receipt["source_closure_changed"] == [], "producer_drift")
    require(set(plan["source_archive"]) == set(plan["source_sha256"]), "source_denominator")
    for source, digest in plan["source_sha256"].items():
        archived = directory / plan["source_archive"][source]
        require(sha(archived) == digest == sha(source), "source_identity:" + source)
        evidence[str(archived)] = digest
        evidence[source] = digest
    own = str(Path(__file__).resolve())
    evidence[own] = sha(own)
    rows = {}
    failures, input_reasons, ack_statuses, choices = Counter(), Counter(), Counter(), Counter()
    for key, specification in plan["rows"].items():
        saved = ledger[key]
        artifact = saved["raw_artifact"]
        require(artifact == receipt["raw_artifacts"][key], "artifact_metadata:" + key)
        raw_path, input_path = directory / artifact["path"], directory / artifact["input_path"]
        require(sha(raw_path) == artifact["sha256"] and sha(input_path) == artifact["input_sha256"]
                == plan["input_file_sha256"][key], "artifact_bytes:" + key)
        evidence[str(raw_path)], evidence[str(input_path)] = artifact["sha256"], artifact["input_sha256"]
        with gzip.open(raw_path, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)
        data = read(input_path)
        require(raw["input"] == data and producer.config_sha(data) == plan["row_configuration_sha256"][key], "input:" + key)
        require(all(raw["specification"][field] == saved[field] == specification[field]
                    for field in ("case", "method", "fault")), "row_identity:" + key)
        require(raw["summary"] == saved["summary"] and raw["summary"]["status"] == saved["status"], "summary:" + key)
        selected = raw["initial_owners"]["A"]["decision"]["selected_action"]
        assessed = producer.assess_cell(data, raw["result"], SimpleNamespace(rows=raw["outbox"], calls=raw["calls"]),
                                       raw["continuation"], {**selected, "later_mode": "rolling"})
        require(all(raw["summary"].get(k) == v for k, v in assessed.items()), "reassessment:" + key)
        failed = [k for k, v in assessed.items() if v is False]
        for name in failed:
            failures[name] += 1
        route_rows = []
        for identity, operation in raw["outbox"].items():
            if operation["kind"] != "route":
                continue
            request, ack = operation["request"], operation.get("ack", {})
            ack_statuses[(ack.get("status"), ack.get("reason"))] += 1
            edges = [r for r in raw["result"]["receipts"] if r["event"] == "EDGE_ENTER"
                     and r["business_bag_id"] == request["business_bag_id"] and r["from"] == request["from"]]
            native_decisions = [r for r in raw["result"]["decisions"] if any(
                r["event_time"] == edge["time"] and r["current_node"] == edge["from"] for edge in edges)]
            mismatch = len(edges) != 1 or edges[0]["to"] != request["next"]
            if mismatch:
                choices[(request["business_bag_id"], request["next"], tuple(e["to"] for e in edges))] += 1
            route_rows.append({"request_id": identity, "request": request, "ack": ack,
                               "actual_edges": edges, "selected_vs_actual_mismatch": mismatch,
                               "native_dispatch_decisions": native_decisions})
        decisions = []
        for owner, sequence in raw["decisions"].items():
            for decision in sequence:
                info = decision["information"]
                bundle = info.get("bundle", {})
                detail = {"owner": owner, "phase": decision["phase"], "at": decision["at"],
                          "information_status": info["status"], "information_reasons": info.get("reasons", []),
                          "model_reasons": bundle.get("reasons", []), "model_status": bundle.get("status"),
                          "native_delivery_verified": info.get("native_delivery_verified"),
                          "fallback_used": decision["fallback_used"], "selected_action": decision["executed_first_action"],
                          "receiver_tray_supplied_facts": bundle.get("trays", {}).get("E"),
                          "native_read": info.get("native_read")}
                decisions.append(detail)
                for reason in detail["information_reasons"] + detail["model_reasons"]:
                    input_reasons[(owner, decision["phase"], reason)] += 1
        rows[key] = {"status_unchanged": saved["status"], "reassessment_matches": True,
                     "failed_predicates": failed, "completion": assessed["completion"],
                     "business_complete": assessed["business_complete"], "physical_audit": assessed["audit"],
                     "initial_action": selected, "initial_A_local_view": raw["initial_owners"]["A"]["local_action_view"],
                     "route_operations": route_rows, "later_inputs": decisions,
                     "raw_sha256": artifact["sha256"], "input_sha256": artifact["input_sha256"]}
    require(all(sha(path) == digest for path, digest in evidence.items()), "evidence_changed_during_read")
    return {"schema": "g31.preexisting_native_failure_diagnosis.v1", "status": "saved_evidence_reassessed_no_verdict_change",
            "source_directory": str(directory), "evidence_sha256": evidence, "branch_count": len(rows),
            "status_counts": dict(Counter(r["status_unchanged"] for r in rows.values())),
            "failed_predicate_counts": dict(failures),
            "route_ack_status_reason_counts": [{"status": k[0], "reason": k[1], "count": v} for k, v in ack_statuses.items()],
            "route_mismatch_counts": [{"job": k[0], "selected": k[1], "actual": k[2], "count": v} for k, v in choices.items()],
            "later_input_reason_counts": [{"owner": k[0], "phase": k[1], "reason": k[2], "count": v} for k, v in input_reasons.items()],
            "rows": rows, "native_executions": 0, "old_receipt_upgraded": False,
            "strict_protection_certified": False, "complete_request_100ms_certified": False,
            "limits": ["Offline examination of saved native outcomes; no remote facts enter online policy.",
                       "Completion and physical validity do not certify that selected actions executed.",
                       "A route updated ACK is distinct from its later executed edge.",
                       "No original unknown row is dropped or promoted."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output_exists")
    result = diagnose(args.directory)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "branch_count", "status_counts", "failed_predicate_counts",
                                            "route_ack_status_reason_counts", "route_mismatch_counts", "later_input_reason_counts")}, indent=2))


if __name__ == "__main__":
    main()
