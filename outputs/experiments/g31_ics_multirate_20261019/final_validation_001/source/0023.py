"""Offline all-row audit of saved native025 captures; never an online policy."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from . import planning_inflight_bounds as bounds
from . import public_rolling_reuse_model as model
from .planning_capture_v2_digest import capture_digest_v2


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(campaign):
    rows, checks, files = [], [], {}
    paths = sorted(Path(campaign).glob("gate*/*.json.gz"))
    for path in paths:
        files[str(path)] = sha(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream: raw = json.load(stream)
        for owner, decisions in raw["decisions"].items():
            for decision in decisions:
                now = decision["at"]; identity = decision["collection"]["request_id"]
                own_acks = [r["ack"] for r in raw["ack_handling"] if r["owner"] == owner
                    and r["request_id"] == identity and r["at"] <= now and r["ack"].get("delivered_at", now+1) <= now]
                envelopes = decision["information"].get("envelopes")
                if envelopes is None:
                    peer = decision["information"].get("native_read", {}).get("native_returned_messages", [])
                    envelopes = {"own": own_acks[-1].get("planning_snapshot_v2") if own_acks else None,
                        **{f"peer{i}": value for i, value in enumerate(peer)}}
                row = {"branch": str(path.relative_to(campaign)), "owner": owner, "at": now,
                    "phase": decision["phase"], "original_information_status": decision["information"]["status"],
                    "original_fallback": decision["fallback_used"], "moving_trays": [],
                    "status": "stationary_capture_no_moving_tray_diagnostic"}
                view = decision["actual_local_view"]
                contract = model.initial.public_contract(view)
                contract["native_semantics"] = model.SUPPORTED_NATIVE_SEMANTICS
                for envelope in envelopes.values():
                    if not envelope:
                        row["status"] = "unknown_missing_saved_capture"; continue
                    body = envelope["capture"]; local = body["local_capture"]
                    valid = (capture_digest_v2(body) == envelope["payload_sha256"]
                        and local["captured_at"] <= envelope["delivered_at"] <= now < local["valid_until"])
                    checks.append(valid)
                    for tray in local["trays"]:
                        if tray["edge_to"] < 0: continue
                        bound = bounds.committed_loaded_arrival(local, tray["tray_id"], contract, now=now)
                        exact = bounds.committed_loaded_arrival(local, tray["tray_id"], contract, now=now,
                            own_current_view=view) if local["source_owner"] == owner else None
                        # Reference truth is read only after deriving the public
                        # bound; it is not passed to the diagnostic function.
                        matches = [r for r in raw["result"]["receipts"] if r["tray_id"] == tray["tray_id"]
                            and r["business_bag_id"] == tray["business_bag_id"] and r["event"] == "EDGE_EXIT"
                            and (r["from"], r["to"]) == (tray["edge_from"], tray["edge_to"])
                            and r["time"] > local["captured_at"]]
                        actual = min((r["time"] for r in matches), default=None)
                        public_unknown = (bound["status"] == "unknown"
                            and bound["reason"] == "committed_edge_has_no_observed_entry_bound")
                        own_exact = exact is None or (exact["status"] == "conditional_arrival_enclosure"
                            and exact["earliest_arrival"] == exact["latest_arrival"] == actual)
                        checks.extend((public_unknown, own_exact, not bound["native_protection_certified"], not bound["usable_by_stationary_model"]))
                        row["moving_trays"].append({"source_capture_message": local["message_id"], "source_owner": local["source_owner"],
                            "capture_digest_valid": valid, "public_only_bound": bound, "current_own_view_bound": exact,
                            "offline_reference_exit": actual, "public_only_unknown_without_observed_entry": public_unknown,
                            "own_exact_matches_offline_exit": own_exact})
                        row["status"] = "diagnostic_only_still_unknown_for_stationary_policy"
                rows.append(row)
    checks.extend((len(paths) == 12, len(rows) == 24, sum(bool(r["moving_trays"]) for r in rows) == 4))
    return {"schema": "g31.saved_inflight_bounds_audit.v2", "source_sha256": files,
        "analysis_source_sha256": {str(Path(__file__)): sha(__file__), str(Path(bounds.__file__)): sha(bounds.__file__)},
        "branch_count": len(paths), "decision_count": len(rows), "moving_decision_count": sum(bool(r["moving_trays"]) for r in rows),
        "checks": len(checks), "checks_passed": sum(checks), "status": "passed" if all(checks) else "unknown_or_failed",
        "rows": rows, "native_calls": 0, "model_evaluations": 0, "changes_to_saved_policy_status": 0,
        "correction": "Old generic capture+travel upper bound withdrawn: commitment can precede actual entry. All4 public-only diagnostic cases now unknown; their same-source current actual receipt-derived exit remains valid conditionally.",
        "limit": "offline validation of current source-only observed exits; no remote transfer of current own fields, no continuous-interval protection or new policy admission"}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    result = audit(args.campaign)
    with args.output.open("x", encoding="utf-8") as stream: json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: result[k] for k in ("status", "branch_count", "decision_count", "moving_decision_count", "checks", "checks_passed")}))


if __name__ == "__main__": main()
