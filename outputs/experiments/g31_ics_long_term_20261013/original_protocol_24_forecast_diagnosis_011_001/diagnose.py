"""Read-only extraction of frozen011 executed forecasts; no new simulation."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = HERE.parent
CAMPAIGN = BASE / "original_protocol_24_011_001"


def read(path):
    return json.load(gzip.open(path, "rt", encoding="utf-8")) if path.suffix == ".gz" else json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


data = read(CAMPAIGN / "input.json")
service = {n[0]: max(.001, n[2]) for n in data["node_records"]}
rows = {}
input_hashes = {"input": sha(CAMPAIGN / "input.json"), "campaign_receipt": sha(CAMPAIGN / "receipt.json")}
for policy in ("predictive_r2", "joint_r1_r2"):
    run_path = CAMPAIGN / policy / "run.json.gz"
    ledger_path = CAMPAIGN / policy / "request_ack_ledger.json.gz"
    run, ledger = read(run_path), read(ledger_path)
    input_hashes[policy] = {"run": sha(run_path), "ledger": sha(ledger_path)}
    requests = {r["request_id"]: r for r in ledger["requests"]}
    events = run["result"]["receipts"]
    exits = {e["traversal_id"]: e for e in events if e["event"] == "EDGE_EXIT"}
    calls = [c for c in run["client_calls"] if c["kind"] == "service_forecast" and not c["retry"]]
    detail = []
    for c in calls:
        p = c["request"]
        ack = requests[p["request_id"]]["last_delivered_ack"]
        entered = next(e for e in events if e["tray_id"] == p["tray_id"] and e["event"] == "EDGE_ENTER" and e["time"] > c["at"])
        local_start = [e for e in events if e["tray_id"] == p["tray_id"] and e["business_bag_id"] == entered["business_bag_id"]
            and e["node"] == entered["from"] and e["event"] in ("LOAD_COMPLETE", "STORAGE_RELEASE", "EDGE_EXIT") and e["time"] <= c["at"]]
        start = local_start[-1]
        active_edges = [e for e in events if e["tray_id"] == p["tray_id"] and e["event"] == "EDGE_ENTER"
            and e["time"] <= ack["executed_at"] < exits.get(e["traversal_id"], {"time": float("inf")})["time"]]
        assert ack["status"] == "rejected" and ack["reason"] == "no_local_uncommitted_loaded_service"
        assert entered["time"] < ack["executed_at"] and active_edges
        assert ack["executed_at"] == c["at"] + p["message_delay"]
        detail.append({"request_id": p["request_id"], "tray_id": p["tray_id"],
            "business_bag_id": entered["business_bag_id"], "source_node": entered["from"], "next": p["next"],
            "source_owner": p["owner_id"], "target_owner": p["target_owner"],
            "eligible_interval_start_event": start["event"], "eligible_interval_start": start["time"],
            "whole_timestamp_issue": c["at"], "physical_edge_enter": entered["time"],
            "real_owner_execution": ack["executed_at"], "delivered_rejection": ack["delivered_at"],
            "node_service_seconds": service[entered["from"]],
            "observed_uncommitted_interval_seconds": entered["time"] - start["time"],
            "sample_lag_seconds": c["at"] - start["time"],
            "remaining_interval_when_sampled": entered["time"] - c["at"],
            "earliest_notification_would_execute_at": start["time"] + p["message_delay"],
            "earliest_notification_can_precede_edge_enter": start["time"] + p["message_delay"] < entered["time"],
            "observed_inflight_at_revalidation": [{k: e[k] for k in ("time", "from", "to", "traversal_id")} for e in active_edges],
            "reason": ack["reason"]})
    rows[policy] = {"count": len(detail), "source_nodes": dict(Counter(str(r["source_node"]) for r in detail)),
        "interval_start_events": dict(Counter(r["eligible_interval_start_event"] for r in detail)),
        "earliest_event_notification_cannot_beat_delay": sum(not r["earliest_notification_can_precede_edge_enter"] for r in detail),
        "earliest_event_notification_might_beat_delay": sum(r["earliest_notification_can_precede_edge_enter"] for r in detail),
        "self_owner_publications": sum(r["source_owner"] == r["target_owner"] for r in detail),
        "rows": detail}

identity = {}
for name in ("p1_build_011", "live_validation_009"):
    path = BASE / name / "receipt.json"
    receipt = read(path)
    entries = receipt["source_before"]
    mismatches = []
    for key, expected in entries.items():
        path_source = Path(key)
        if not path_source.is_absolute():
            path_source = ROOT / path_source
        actual = sha(path_source) if path_source.exists() else None
        if actual != expected:
            mismatches.append({"path": key, "expected": expected, "actual": actual})
    identity[name] = {"receipt_sha256": sha(path), "status": receipt.get("status"),
        "recorded_source_changed": receipt.get("source_changed"), "recorded_counts": receipt.get("counts"),
        "source_files_checked": len(entries), "current_source_mismatches": mismatches}
binary = ROOT / "build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd"
identity["binary_sha256"] = sha(binary)
identity["expected_011_binary_matches"] = identity["binary_sha256"] == "19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec"
user_file = Path("C:/PROGRAMING/czr005/cpp/ics_core/runtime/bounded_local_pibt.hpp")
identity["protected_user_file"] = {"path": str(user_file), "sha256": sha(user_file),
    "matches_prior_protected_hash": sha(user_file) == "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"}
for label, path in (("circulation_worktree", ROOT), ("original_user_worktree", Path("C:/PROGRAMING/czr005"))):
    p = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=path, capture_output=True, text=True, check=True)
    identity[label + "_staged_paths"] = p.stdout.splitlines()
result = {"schema": "g31.original24.forecast_delay_diagnosis.v1", "status": "passed",
    "scope": "offline frozen011 raw extraction only; earliest-event comparisons are necessary timing diagnostics, not a replay or improvement claim",
    "input_hashes": input_hashes, "runner_sha256": sha(Path(__file__)), "identity": identity,
    "load_unload_hold_contracts": sorted({(j["load_seconds"], j["unload_seconds"], j["hold_seconds"]) for j in data["jobs"]}),
    "policies": rows}
(HERE / "diagnosis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "policies": {k: {a: b for a, b in v.items() if a != "rows"} for k, v in rows.items()},
    "source_mismatch_counts": {k: len(v["current_source_mismatches"]) for k, v in identity.items() if isinstance(v, dict) and "current_source_mismatches" in v},
    "binary_matches": identity["expected_011_binary_matches"], "protected_user_file_unchanged": identity["protected_user_file"]["matches_prior_protected_hash"]}, ensure_ascii=False))
