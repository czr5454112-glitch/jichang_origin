"""Explicit closed-run protection counts; standard library, no native or model calls.

Use either --names RUN ... or --final-review FINAL_REVIEW_JSON. The latter
requires exactly the predeclared 34 E/D/G rows. Every named end receipt is
checked before any other run output is read. This script does not open full
callback streams, replay physical events, fit models, tune policies, or claim G2.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys


SOURCE_NAMES = (
    "analytic_control", "protocol_control", "foundation_airport_protocol_v2",
    "foundation_airport_batch_patch", "foundation_airport_opportunities",
    "foundation_airport_prospective_control", "foundation_airport_prospective_campaign",
)
ACTIVE = {"pending", "undelivered", "dispatching", "departed"}
KNOWN_ADMISSION_REFUSALS = {"receiving_full", "receiver_transit_reserve", "departure_lease_expired"}


def require(condition, reason):
    if not condition:
        raise ValueError("protection_audit:" + reason)


def read(path):
    with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz"
          else path.open(encoding="utf-8")) as stream:
        return json.load(stream)


def sha(path):
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            "file_changed_while_reading:" + str(path))
    return digest.hexdigest()


def ref(path):
    return {"path": str(path.resolve()), "sha256": sha(path)}


def run_directory(cycle, name):
    require(isinstance(name, str) and Path(name).name == name and "/" not in name
            and "\\" not in name and ":" not in name and name not in (".", ".."), "safe_run_name")
    directory = (cycle / name).resolve()
    require(directory.parent == cycle, "run_must_be_direct_child")
    return directory


def audit(cycle, names, *, review=None, semantic_audit=None):
    cycle = cycle.resolve()
    grid = read(cycle / "prospective_evaluation_grid_001.json")
    slots = {row["name"]: row for row in grid["rows"]}
    require(len(slots) == 34, "fixed_34_prospective_grid")
    require(names and len(names) == len(set(names)) and set(names) <= set(slots),
            "explicit_unique_registered_names")
    receipts = {}
    # This is intentionally a separate first pass: no partially closed set is read.
    for name in names:
        path = run_directory(cycle, name) / "receipt.json"
        require(path.is_file(), "closed_receipt_required:" + name)
        receipt = read(path)
        require(receipt.get("status") not in (None, "running", "pending", "prepared", "not_run"),
                "run_not_closed:" + name)
        receipts[name] = receipt
    reviewed = None
    if review:
        reviewed = {row["name"]: row for row in read(review)["rows"] if row["batch"] in ("E", "D", "G")}
        require(set(reviewed) == set(slots) == set(names), "all_34_final_review_rows_required")
        require(all(receipts[name]["status"] == reviewed[name]["status"] for name in names),
                "final_review_receipt_status")
    rows, prefixes, versions = [], defaultdict(list), defaultdict(set)
    for name in names:
        directory = run_directory(cycle, name)
        receipt = receipts[name]
        plan_path = directory / "plan.json"
        plan = read(plan_path)
        require(sha(plan_path) == receipt["plan_sha256"] and plan["name"] == name,
                "actual_plan_receipt_binding")
        require(plan["batch"] == slots[name]["batch"], "registered_batch")
        source_pins = {k.replace("\\", "/"): v for k, v in plan["sources"].items()}
        source_versions = {}
        for source in SOURCE_NAMES:
            key = "scripts/experiments/g31_ics_circulation/" + source + ".py"
            expected = source_pins[key]
            require(sha(directory / "source" / key) == expected, "archived_runtime_source_pin")
            source_versions[key] = expected
            versions[key].add(expected)
        row = {"name": name, "batch": plan["batch"], "status": receipt["status"],
               "parent_seed": plan["parent"]["parent_seed"], "fleet": plan["parent"]["fleet"],
               "variant": plan["information_variant"], "model_seed": plan["model_seed"],
               "source_versions": source_versions, "receipt": ref(directory / "receipt.json"),
               "plan": ref(plan_path), "full_callback_stream_opened": False,
               "full_receipt_physical_replay_performed": False}
        final_path = directory / "final_result.json.gz"
        if not final_path.is_file():
            require(receipt["status"] != "complete", "complete_run_missing_final_result")
            row.update(diagnostic_status="unknown_missing_final_result", physical_invariants="unknown")
            rows.append(row)
            continue
        result = read(final_path)
        data = read(directory / "input.json")
        require(sha(directory / "input.json") == plan["input"]["sha256"], "input_plan_binding")
        job_ids = {x["business_bag_id"] for x in result["jobs"]}
        require(len(result["jobs"]) == len(job_ids) == len(data["jobs"]) == 28506
                and job_ids == {x["business_bag_id"] for x in data["jobs"]}, "full_population_identity")
        tray_ids = {x["tray_id"] for x in result["trays"]}
        require(len(tray_ids) == len(result["trays"]) == len(data["trays"]) == row["fleet"]
                and tray_ids == {x["tray_id"] for x in data["trays"]}, "tray_identity_conservation")
        transfers = {x["request_id"]: x for x in result["transfers"]}
        require(len(transfers) == len(result["transfers"]), "unique_transfer_identity")
        legs = {x["transport_leg_id"]: x for x in result["leg_identities"]}
        require(len(legs) == len(result["leg_identities"]), "unique_leg_identity")
        calls_path = directory / "client_calls.json.gz"
        calls = read(calls_path) if calls_path.is_file() else []
        calls_by_id = {}
        retry_conflicts = []
        for call in calls:
            if call["kind"] != "transfer":
                continue
            request = call["request"]
            rid = request["request_id"]
            if rid in calls_by_id and calls_by_id[rid]["request"] != request:
                retry_conflicts.append(rid)
            else:
                calls_by_id.setdefault(rid, call)
        events = defaultdict(list)
        failures = []
        rejects = Counter()
        for event in result["receipts"]:
            if event["transport_leg_id"]:
                events[event["transport_leg_id"]].append(event)
            if "REJECT" in event["event"]:
                rejects[event["event"] + ":" + event["reason"]] += 1
            if event["event"] == "LEG_FAILED":
                failures.append(event)
        failure_details = []
        for transfer in transfers.values():
            if transfer["status"] != "failed":
                continue
            rid = transfer["request_id"]
            matching = [x for x in legs.values() if x["transport_leg_id"].startswith(rid + ":empty_return:")]
            require(len(matching) <= 1, "one_empty_leg_per_request")
            actual_events = events[matching[0]["transport_leg_id"]] if matching else []
            call = calls_by_id.get(rid)
            failure_details.append({
                "transfer": transfer, "first_actual_submission": call,
                "native_leg": matching[0] if matching else None,
                "first_edge_count": sum(e["event"] == "EDGE_ENTER" for e in actual_events),
                "unused_receiver_release_count": sum(e["event"] == "UNUSED_RECEIVING_RELEASED"
                                                    for e in actual_events),
                "failure_receipts": [e for e in actual_events if e["event"] == "LEG_FAILED"],
                "allocation_reason": call["request"].get("control_reason") if call else None,
                "causal_attribution": "whole-policy observed outcome; not an isolated action-effect estimate",
            })
        prefix_path = directory / "activation_prefix.json.gz"
        prefix = read(prefix_path)["prefix"] if prefix_path.is_file() else None
        if prefix:
            prefixes[(row["parent_seed"], row["fleet"])].append((name, prefix))
        native = result["native_summary"]
        diagnostics = {key: native.get(key) for key in
                       ("reservation_conflicts", "physical_fault_edge_entry_violation_count")}
        require(all(value is None or type(value) is int and value >= 0
                    for value in diagnostics.values()), "native_diagnostic_integer_or_unknown")
        timing_path = directory / "callback_audit_receipt.json"
        timing = read(timing_path) if timing_path.is_file() else None
        row.update(
            diagnostic_status="counts_collected_from_actual_final_artifacts",
            final_result=ref(final_path), input=ref(directory / "input.json"),
            client_calls=ref(calls_path) if calls_path.is_file() else None,
            physical_clock=result["physical_clock"], advance=result["advance"],
            native_summary=native, explicit_native_violation_counters=diagnostics,
            zero_on_both_explicit_native_counters=all(value == 0 for value in diagnostics.values()),
            full_population_identity_verified=True, tray_identity_conservation_verified=True,
            job_status_counts=dict(Counter(x["status"] for x in result["jobs"])),
            tray_mode_counts=dict(Counter(x["mode"] for x in result["trays"])),
            quarantined_trays=[x for x in result["trays"] if x["mode"] == "quarantined"],
            transfer_status_counts=dict(Counter(x["status"] for x in transfers.values())),
            pending_transfers=sum(x["status"] in ACTIVE for x in transfers.values()),
            transfer_reasons=dict(Counter(x["reason"] for x in transfers.values() if x["reason"])),
            rejection_receipt_counts=dict(rejects), leg_failed_receipts=failures,
            failed_transfer_details=failure_details, unique_transfer_requests=len(calls_by_id),
            repeated_payload_conflicts=sorted(set(retry_conflicts)),
            direct_submit_reply_rejections=sum(x["reply"].get("status") == "rejected" for x in calls),
            activation_prefix=prefix,
            callback_receipt=ref(timing_path) if timing_path.is_file() else None,
            measured_callback_wall_ms={key: {
                "count": len(timing["timings_ms"]),
                "sum": sum(x[key] for x in timing["timings_ms"]),
                "max": max((x[key] for x in timing["timings_ms"]), default=None)}
                for key in ("planning", "audit_persistence")} if timing else None,
        )
        if receipt["status"] == "complete":
            require(result["physical_clock"] == 59400. and result["advance"]["status"] == "reached"
                    and result["advance"]["horizon_complete"] is True, "complete_exact_endpoint")
        rows.append(row)
        print(json.dumps({"event": "closed_protection_counts_collected", "name": name}), flush=True)
    semantic = None
    if semantic_audit:
        semantic_data = read(semantic_audit)
        semantic = {"artifact": ref(semantic_audit), "named_coverage": semantic_data["read_scope"],
                    "scope": "Separate pinned-source/initial-stream and pure physical-receipt replay audit. "
                    "Do not expand its seven-run coverage to these counts automatically."}
    return {
        "schema": "g31.closed_prospective_protection_counts.v1",
        "status": "all_explicit_closed_run_counts_collected",
        "explicit_run_count": len(names), "final_all34_scope": set(names) == set(slots),
        "closed_status_denominator": dict(Counter(row["status"] for row in rows)),
        "diagnostics_available_runs": sum("explicit_native_violation_counters" in r for r in rows),
        "runs_zero_on_both_explicit_native_counters": sum(r.get("zero_on_both_explicit_native_counters", False)
                                                       for r in rows),
        "runs_with_final_quarantine": sum(bool(r.get("quarantined_trays")) for r in rows),
        "final_quarantined_tray_count": sum(len(r.get("quarantined_trays", [])) for r in rows),
        "actual_leg_failed_receipt_count": sum(len(r.get("leg_failed_receipts", [])) for r in rows),
        "per_parent_fleet_activation_prefix": [
            {"parent_seed": key[0], "fleet": key[1], "runs": [x[0] for x in values],
             "all_available_prefixes_equal": all(x[1] == values[0][1] for x in values),
             "comparison_does_not_cross_fleet_or_parent": True}
            for key, values in sorted(prefixes.items())],
        "runtime_source_versions": {key: sorted(value) for key, value in versions.items()},
        "frozen_protection_scope": {"artifact": ref(cycle / "protection_scope_001.json"),
                                    "content": read(cycle / "protection_scope_001.json")},
        "rows": rows, "separate_semantic_audit": semantic,
        "source_review": ref(review) if review else None,
        "auditor": ref(Path(__file__)), "native_starts": 0, "fit_calls": 0,
        "full_callback_streams_read": False, "models_rescored": False,
        "strict_nonharm_certified": False, "protected_takeover_eligible": False,
        "full_G2_established": False,
        "interpretation": [
            "Zero on named native counters establishes only those recorded diagnostics, not all physical invariants.",
            "Receiver-capacity/reserve and lease rejections are protective refusals; count them separately from actual violations.",
            "Expiry before first physical entry may quarantine a tray and release its reception lease. This is real availability loss even when capacity checks held.",
            "Known per-job delays and unfinished completion comparisons remain separate evidence against a universal nonharm claim.",
            "Same activation prefix supports common warmup only; residual-observation refresh semantics require the separately scoped source/stream audit.",
            "J has units of physical bag-seconds. Synchronous controller wall milliseconds pause native time; no validated asynchronous latency-cost mapping or real-time guarantee is established.",
            "These counts cannot establish shared-channel/future-route protection, protected takeover or full G2.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--names", nargs="+")
    choice.add_argument("--final-review", type=Path)
    parser.add_argument("--semantic-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), "fresh_output_required")
        names = args.names
        if args.final_review:
            names = [r["name"] for r in read(args.final_review)["rows"] if r["batch"] in ("E", "D", "G")]
        result = audit(args.cycle, names, review=args.final_review, semantic_audit=args.semantic_audit)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"status": result["status"], "runs": len(names),
                          "output": str(args.output.resolve()), "sha256": sha(args.output)}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": str(error), "native_starts": 0, "fits": 0}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
