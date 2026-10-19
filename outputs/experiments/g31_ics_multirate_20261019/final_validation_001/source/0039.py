"""Saved native60 comparison and independent supplied-endpoint revalidation."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from . import diagnose_preexisting_native as diagnosis
from . import diagnose_preexisting_v3_endpoints as endpoints


def json_value(value):
    # Actual raw is JSON: integer map keys become strings and tuples become
    # arrays. Preserve every field/value; no semantic/timing field is removed.
    return json.loads(json.dumps(value, allow_nan=False))


def audit(old_path, new_path):
    old, new = diagnosis.diagnose(old_path), diagnosis.diagnose(new_path)
    pins = {**old["evidence_sha256"], **new["evidence_sha256"]}
    for module in (endpoints, endpoints.binding, endpoints.binding.data_adapter):
        pins[str(Path(module.__file__).resolve())] = diagnosis.sha(module.__file__)
    pins[str(Path(__file__).resolve())] = diagnosis.sha(__file__)
    old_ledger, new_ledger = (diagnosis.read(p / "branch_ledger.json") for p in (old_path, new_path))
    receipt = diagnosis.read(new_path / "receipt.json")
    diagnosis.require(set(old_ledger) == set(new_ledger), "paired_branch_domain")
    counts, operation_counts, rows, upgraded, changed = Counter(), Counter(), {}, [], []
    for key, row in new["rows"].items():
        raw = json.loads(gzip.decompress((new_path / new_ledger[key]["raw_artifact"]["path"]).read_bytes()))
        prior = json.loads(gzip.decompress((old_path / old_ledger[key]["raw_artifact"]["path"]).read_bytes()))
        diagnosis.require(raw["input"] == prior["input"], "matched_input:" + key)
        revalidated = []
        for owner, sequence in raw["decisions"].items():
            for decision in sequence:
                actual = decision["information"]
                replay = endpoints.replay_decision(raw, owner, decision)
                if replay["status"] == "conditional_validated_later_v3_data":
                    diagnosis.require(actual["status"] == "conditional_native_delivered_later_v3_model_input"
                        and actual["native_delivery_verified"] is True and actual["online_information_delivered"] is True,
                        "actual_verified_input_status:" + key)
                    for field in ("bundle", "envelopes", "own_delivered_ack", "endpoint_identity_binding"):
                        diagnosis.require(actual[field] == json_value(replay[field]), "actual_replayed_input:" + key + ":" + field)
                else:
                    diagnosis.require(actual["status"] == "unknown" and actual["reasons"] == replay["reasons"]
                        and actual.get("bundle") == json_value(replay.get("bundle")), "actual_unknown_replay:" + key)
                counts[(owner, decision["phase"], actual["status"], decision["fallback_used"])] += 1
                revalidated.append({"owner": owner, "phase": decision["phase"], "at": decision["at"],
                    "actual_status": actual["status"], "pure_replay_status": replay["status"],
                    "all_replayed_data_equal": True, "selected_first_action": decision["executed_first_action"],
                    "fallback_used": decision["fallback_used"], "reasons": replay.get("reasons", []),
                    "model_reasons": replay.get("bundle", {}).get("reasons", [])})
        old_row = old["rows"][key]
        deltas = {job: row["completion"][job] - old_row["completion"][job] for job in row["completion"]}
        if old_row["status_unchanged"] != row["status_unchanged"]: upgraded.append(key)
        if any(delta != 0 for delta in deltas.values()): changed.append(key)
        route_pairs = []
        for operation in row["route_operations"]:
            request, ack = operation["request"], operation["ack"]
            operation_counts[(request["business_bag_id"], request["next"], ack["status"], operation["selected_vs_actual_mismatch"])] += 1
            former = next(o for o in old_row["route_operations"] if o["request"]["business_bag_id"] == request["business_bag_id"])
            old_edges = [(e["time"], e["from"], e["to"]) for e in former["actual_edges"]]
            new_edges = [(e["time"], e["from"], e["to"]) for e in operation["actual_edges"]]
            route_pairs.append({"job":request["business_bag_id"], "old_requested_next":former["request"]["next"],
                "new_requested_next":request["next"], "old_ack":former["ack"], "new_ack":ack,
                "old_actual_edges":old_edges, "new_actual_edges":new_edges,
                "actual_edge_or_time_changed":old_edges != new_edges})
        later_call = next(c for c in raw["calls"] if c["kind"] == "route" and c["request"]["business_bag_id"] == "reuse1")
        former_call = next(c for c in prior["calls"] if c["kind"] == "route" and c["request"]["business_bag_id"] == "reuse1")
        cutoff = min(later_call["at"], former_call["at"])
        raw_calls = lambda value: [c for c in value["calls"] if c["at"] < cutoff]
        physics = lambda value: [r for r in value["result"]["receipts"] if r["time"] <= cutoff]
        rows[key] = {"old_status_retained":old_row["status_unchanged"], "new_actual_status":row["status_unchanged"],
            "old_completion":old_row["completion"], "new_completion":row["completion"], "new_minus_old_per_job":deltas,
            "all_five_raw_physical_deltas_nonpositive":all(d <= 0 for d in deltas.values()),
            "declared_protection_not_inferred_from_raw_deltas":True, "actual_inputs_independently_replayed":revalidated,
            "route_pairs":route_pairs, "pre_later_call_cutoff":cutoff,
            "ordered_prior_native_calls_equal":raw_calls(raw) == raw_calls(prior),
            "prior_physical_receipts_equal":physics(raw) == physics(prior),
            "independent_native_checkpoint_identity_claim":False,
            "all_five_completed_and_physical_audit_passed":row["business_complete"] and row["physical_audit"]["status"] == "passed"}
    diagnosis.require(all(diagnosis.sha(p) == h for p,h in pins.items()), "comparison_inputs_changed")
    groups = receipt["comparisons"]
    return {"schema":"g31.preexisting_bound_native_comparison.v1", "status":"saved_native60_and120_inputs_revalidated",
        "evidence_sha256":pins, "branch_count":len(rows), "actual_later_input_count":sum(counts.values()),
        "actual_later_input_counts":[{"owner":k[0],"phase":k[1],"status":k[2],"fallback":k[3],"count":v} for k,v in counts.items()],
        "route_counts":[{"job":k[0],"requested_next":k[1],"ack_status":k[2],"requested_actual_mismatch":k[3],"count":v} for k,v in operation_counts.items()],
        "newly_assessed_keys":upgraded, "completion_vector_changed_keys":changed,
        "all60_horizon_complete_5jobs_physical_pass":all(r["all_five_completed_and_physical_audit_passed"] for r in rows.values()),
        "declared_fixed_family_complete":{k:v["complete_fixed_family"] for k,v in groups.items()},
        "declared_comparison_status_counts":dict(Counter(r["status"] for g in groups.values() for r in g["methods"].values())),
        "rows":rows, "old_receipts_upgraded":False, "new_native_executions":0,
        "protected_joint_benefit_certified":False, "method_novelty_claim":False,
        "limits":["Newly assessed actions can have exactly the same physical effect as a former fallback.",
            "A completed but rejected-action control is not promoted to the preregistered accepted control.",
            "The remaining incomplete fixed families keep all registered protection comparisons unknown.",
            "Same saved prior calls/physical receipts are not an independently replayed hidden native state seal."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old",type=Path,required=True);parser.add_argument("--new",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    diagnosis.require(not args.output.exists(),"output_exists")
    result=audit(args.old.resolve(),args.new.resolve())
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","actual_later_input_counts","newly_assessed_keys",
        "completion_vector_changed_keys","declared_comparison_status_counts")},indent=2))


if __name__ == "__main__":main()
