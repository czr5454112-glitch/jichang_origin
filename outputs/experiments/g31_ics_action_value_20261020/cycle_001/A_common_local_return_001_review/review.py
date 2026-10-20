"""Read saved A1 evidence only. Never loads a native binary or constructs a session."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import audit_result

OUT = Path(__file__).resolve().parent
RUN = OUT.parent / "A_common_local_return_001"


def read(name):
    path = RUN / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf8"))


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


plan, value = read("plan.json"), read("input.json")
report, result = read("worker_report.json"), read("final_result.json.gz")
calls, views = read("client_calls.json.gz"), read("ack_views.json.gz")
transfer_calls = [c for c in calls if c["kind"] == "transfer"]
by_request = defaultdict(list)
for call in transfer_calls:
    by_request[call["request"]["request_id"]].append(call)
payloads = {rid: rows[0]["request"] for rid, rows in by_request.items()}
payload_conflicts = [rid for rid, rows in by_request.items()
                    if any(row["request"] != rows[0]["request"] for row in rows[1:])]
replay = dict(value, transfers=[dict(payloads[rid], issued_at=rows[0]["at"])
                               for rid, rows in by_request.items()])
physical_audit = audit_result(replay, result)

grants = [r for r in result["receipts"] if r["event"] == "EXPORT_GRANTED"]
grant_counts = Counter(r["reason"] for r in grants)
empty_legs = [r for r in result["leg_identities"] if r["kind"] == "empty_return"]
leg_counts = Counter(r["transport_leg_id"].rsplit(":empty_return:", 1)[0] for r in empty_legs)
duplicate_grants = [rid for rid, count in grant_counts.items() if count != 1]
duplicate_legs = [rid for rid, count in leg_counts.items() if count != 1]
grant_leg_mismatches = [rid for rid in set(grant_counts) | set(leg_counts)
                        if grant_counts[rid] != leg_counts[rid]]
scope_grants = Counter(payloads[r["reason"]].get("transfer_scope", "cross_zone_transfer") for r in grants)
scope_outcomes = defaultdict(Counter)
for row in result["transfers"]:
    scope_outcomes[row["transfer_scope"]][row["status"]] += 1

local_reload = []
for leg in empty_legs:
    rid = leg["transport_leg_id"].rsplit(":empty_return:", 1)[0]
    if payloads[rid].get("transfer_scope") != "local_empty_return":
        continue
    received = next((t for t in result["transfers"] if t["request_id"] == rid), None)
    if not received or received["received_at"] < 0:
        continue
    tray_id = result["trays"][leg["tray"]]["tray_id"]
    loaded = next((r for r in result["receipts"] if r["event"] == "LOAD_START"
                   and r["tray_id"] == tray_id and r["time"] >= received["received_at"]
                   and r["node"] == payloads[rid]["destination"]), None)
    if loaded:
        local_reload.append({"request_id": rid, "tray_id": tray_id,
                             "received_at": received["received_at"],
                             "next_load_at": loaded["time"],
                             "business_bag_id": loaded["business_bag_id"]})

ack_rows = [dict(row, owner=owner) for owner, view in views.items()
            for row in view["delivered_transfer_acks"]]
ack_keys = Counter((row["request_id"], row["sequence"]) for row in ack_rows)
unknown_acks = [row["request_id"] for row in ack_rows if row["request_id"] not in payloads]
owner_mismatches = [row["request_id"] for row in ack_rows
                    if row["request_id"] in payloads
                    and row["owner"] != payloads[row["request_id"]]["owner_id"]]
scope_mismatches = [row["request_id"] for view in views.values()
                    for row in view["client_transfer_ledger"]
                    if row["request_id"] in payloads and
                    row["transfer_scope"] != payloads[row["request_id"]].get("transfer_scope", "cross_zone_transfer")]

segments, batches = [], []
for path in sorted(RUN.glob("segment_*.json.gz")):
    segment = read(path.name)
    count = sum(row["processed_events"] for row in segment["native_batches"])
    batches.extend(segment["native_batches"])
    segments.append({"file": path.name, "processed_events": count,
                     "physical_time": segment["control_continuation"]["physical_time"],
                     "timestamp_complete": segment["control_continuation"]["timestamp_complete"],
                     "result_event_count": (segment["result"]["native_summary"]["event_count"]
                                            if segment["result"] else None)})
event_total = sum(row["processed_events"] for row in segments)
last = batches[-1]
late_rate = max(row["processed_events"] / 3600 for row in segments[-5:-1])
remaining = plan["requested_horizon"] - report["final_physical_time"]
projected_events = event_total + math.ceil(remaining * late_rate)
checks = {
    "independent_physical_receipt_audit": physical_audit["status"] == "passed",
    "retry_payload_immutable": not payload_conflicts,
    "unique_grant_per_request": not duplicate_grants,
    "unique_entity_leg_per_request": not duplicate_legs,
    "grant_entity_leg_bijection": not grant_leg_mismatches,
    "transfer_ack_ids_and_owners_bound": not unknown_acks and not owner_mismatches,
    "ack_request_sequence_keys_unique": all(count == 1 for count in ack_keys.values()),
    "client_ledger_scope_matches_own_payload": not scope_mismatches,
    "tray_identity_conserved": sorted(t["tray_id"] for t in value["trays"]) == sorted(t["tray_id"] for t in result["trays"]),
    "job_identity_conserved": sorted(j["business_bag_id"] for j in value["jobs"]) == sorted(j["business_bag_id"] for j in result["jobs"]),
    "exact_global_event_limit": event_total == plan["global_event_budget"] == 500000,
    "last_advance_below_per_call_limit": last["processed_events"] < plan["event_budget"],
}
summary = {
    "schema": "g31.A1_saved_native_review.v1",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "status": "passed" if all(checks.values()) else "failed",
    "native_constructors_used": 0,
    "evidence": [ref(RUN / name) for name in ["plan.json", "input.json", "worker_report.json",
        "final_result.json.gz", "client_calls.json.gz", "ack_views.json.gz", "segment_16.json.gz"]],
    "review_source": ref(Path(__file__)),
    "checks": checks,
    "time_scopes": {
        "requested_horizon": plan["requested_horizon"],
        "last_saved_complete_result": result["physical_clock"],
        "actual_native_stop": report["final_physical_time"],
        "last_fully_processed_control_boundary": last["start_at"],
        "partial_boundary_target": last["target"],
        "ack_observation_times": {owner: view["now"] for owner, view in views.items()},
        "final_result_is_not_actual_stop_state": True,
        "partial_native_timestamp_complete": segments[-1]["timestamp_complete"],
    },
    "event_budget": {
        "global_configured": plan["global_event_budget"], "per_advance_configured": plan["event_budget"],
        "exact_processed_events": event_total, "largest_actual_advance_events": max(x["processed_events"] for x in batches),
        "last_partial_advance": last, "segments": segments,
        "late_max_hourly_rate_events_per_second": late_rate,
        "simple_projection_to_requested_horizon": projected_events,
        "uniform_precomparison_calibration_frozen_by_root": 750000,
        "calibrated_headroom_over_projection": 750000 / projected_events - 1,
        "scope": "Projection is diagnostic, not a guarantee; retain censoring and equal budgets across methods.",
    },
    "last_complete_population": {
        "offered": len(value["jobs"]), "arrived": sum(j["arrival"] <= result["physical_clock"] for j in value["jobs"]),
        "jobs_by_status": dict(Counter(j["status"] for j in result["jobs"])),
        "trays": len(result["trays"]), "trays_by_mode": dict(Counter(t["mode"] for t in result["trays"])),
    },
    "transfer_evidence": {
        "all_time_submission_calls": len(transfer_calls), "unique_request_payloads": len(payloads),
        "snapshot_physical_transfer_rows": len(result["transfers"]), "grants": len(grants),
        "empty_entity_legs": len(empty_legs), "grants_by_scope": dict(scope_grants),
        "outcomes_by_scope": {scope: dict(counts) for scope, counts in scope_outcomes.items()},
        "local_return_then_load_count": len(local_reload), "local_return_then_load_witnesses": local_reload[:8],
        "delivered_ack_rows_at_later_observation": len(ack_rows),
        "ack_time_scope_warning": "ACK views extend to the partial stop; do not compare their latest status as if observed at57600.",
        "payload_conflicts": payload_conflicts, "duplicate_grants": duplicate_grants,
        "duplicate_entity_legs": duplicate_legs, "grant_leg_mismatches": grant_leg_mismatches,
        "unknown_ack_requests": unknown_acks, "ack_owner_mismatches": owner_mismatches,
        "ledger_scope_mismatches": scope_mismatches,
    },
    "physical_audit": physical_audit,
    "scientific_limit": "This is a repaired common analytic baseline, not an RL control result. A1 is censored before59400; same-horizon comparison needs A2.",
}
(OUT / "review.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
print(json.dumps({key: summary[key] for key in ["status", "checks", "last_complete_population", "transfer_evidence"]},
                 ensure_ascii=False))
