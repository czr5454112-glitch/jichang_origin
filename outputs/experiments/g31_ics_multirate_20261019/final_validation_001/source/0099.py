"""Offline replay of all saved later endpoints; never upgrades native outcomes."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from . import diagnose_preexisting_native as base
from . import preexisting_v3_endpoint_identity as binding
from .planning_capture_v2_contract import PHYSICAL_KINDS


def actions_before_decision(raw, owner, decision):
    # The first new action follows collection in this actual activation. Use
    # ordered raw calls, not the final outbox's future operations.
    identity = decision["native_request_id"]
    indices = [i for i, call in enumerate(raw["calls"]) if call["request"]["request_id"] == identity]
    base.require(bool(indices), "missing_post_collection_action")
    rows = {}
    for call in raw["calls"][:indices[0]]:
        request = call["request"]
        if request["owner_id"] == owner and call["kind"] in PHYSICAL_KINDS:
            key = request["request_id"]
            base.require(key not in rows or rows[key] == call["kind"], "changed_prior_action_kind")
            rows[key] = call["kind"]
    return sorted(rows.items())


def replay_decision(raw, owner, decision):
    info = decision["information"]
    endpoints, read = info["raw_endpoints"], info["native_read"]
    publications = [call["request"] for call in raw["calls"] if call["request"]["request_id"] == read["own_request_id"]]
    base.require(bool(publications) and all(row == publications[0] for row in publications), "immutable_own_publication")
    return binding.validate_collected_endpoints(endpoints["view"], endpoints["command"], endpoints["received"],
        retained=raw["retained_ledgers"][owner], own_actions=actions_before_decision(raw, owner, decision),
        phase=decision["phase"], own_request_id=read["own_request_id"],
        peer_message_id=read["selected_peer_message_id"], collection_started_at=read["collection_started_at"],
        policy_quiet_since=read["collection_started_at"], own_request=publications[0])


def diagnose(directory):
    original = base.diagnose(directory)
    evidence = dict(original["evidence_sha256"])
    for module in (binding, binding.data_adapter):
        evidence[str(Path(module.__file__).resolve())] = base.sha(module.__file__)
    evidence[str(Path(__file__).resolve())] = base.sha(__file__)
    ledger = base.read(directory / "branch_ledger.json")
    counts, rows = Counter(), {}
    for key, item in ledger.items():
        raw = json.loads(gzip.decompress((directory / item["raw_artifact"]["path"]).read_bytes()))
        decisions = []
        for owner, sequence in raw["decisions"].items():
            for decision in sequence:
                result = replay_decision(raw, owner, decision)
                old = decision["information"]
                endpoints = old["raw_endpoints"]
                ack = endpoints["command"]["last_delivered_ack"]
                local = ack["planning_snapshot_v3"]["capture"]["capture_v2"]["local_capture"]
                native_read = old["native_read"]
                reasons = result.get("reasons", []) + result.get("bundle", {}).get("reasons", [])
                counts[(owner, decision["phase"], result["status"], tuple(reasons))] += 1
                decisions.append({"owner": owner, "phase": decision["phase"], "at": decision["at"],
                    "old_status": old["status"], "old_reasons": old.get("reasons"),
                    "actual_client_request_id": native_read["own_request_id"],
                    "actual_command_request_id": endpoints["command"]["request_id"],
                    "actual_ack_result_id": ack["result_id"], "actual_capture_message_id": local["message_id"],
                    "client_id_differs_from_generated_message_id": native_read["own_request_id"] != local["message_id"],
                    "actual_own_capture_at": local["captured_at"], "collection_started_at": native_read["collection_started_at"],
                    "own_actions_from_predecision_ordered_calls": actions_before_decision(raw, owner, decision),
                    "new_binding_offline_replay": result,
                    "not_executed_new_policy": True, "old_status_unchanged": True})
        rows[key] = {"old_status": item["status"], "decisions": decisions}
    base.require(all(base.sha(path) == digest for path, digest in evidence.items()), "evidence_changed_during_replay")
    return {"schema": "g31.preexisting_v3_endpoint_diagnosis.v1", "status": "offline_identity_replay_only",
        "evidence_sha256": evidence, "original_assessment": {k:v for k,v in original.items() if k not in ("rows", "evidence_sha256")},
        "later_decision_count": sum(len(r["decisions"]) for r in rows.values()),
        "new_binding_replay_counts": [{"owner": k[0], "phase": k[1], "status": k[2], "reasons": k[3], "count": v} for k,v in counts.items()],
        "rows": rows, "native_executions": 0, "online_delivery_certified": False,
        "native_business_verdict_changed": False,
        "limits": ["The new binding reaches downstream guards on frozen supplied endpoints only.",
            "A different chosen action can change later physics; this is not a new-policy outcome.",
            "All original rejected, mismatched, fallback and unknown outcomes remain unchanged."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base.require(not args.output.exists(), "output_exists")
    result = diagnose(args.directory.resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status", "later_decision_count", "new_binding_replay_counts")}, indent=2))


if __name__ == "__main__":
    main()
