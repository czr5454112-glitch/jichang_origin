"""Read-only raw-controller cross-check of a saved bundle capture, no native run."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from .request_bundle_measurement import analyze_bundles


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify(directory):
    directory = Path(directory)
    report = {"status": "unknown", "native_calls": 0, "complete_100ms_requirement_certified": False}
    try:
        manifest = json.loads((directory/"manifest.json").read_text())
        ledger = read(directory/"ledger.json.gz")
        analysis = analyze_bundles(ledger)
        if manifest["status"] != "captured" or manifest["source_changed"] or analysis["status"] != "complete_conservative_bundle_accounting":
            raise ValueError("capture_or_accounting_not_complete")
        shards = sorted(directory.glob("segment_*.json.gz"))
        limits = manifest["requested_activation_limits"]
        if len(shards) != manifest["segments"] or len(shards) != len(limits) or len(shards) != len(ledger["service_windows"]):
            raise ValueError("missing_raw_segment")
        roots = {r["request_id"]: r for r in ledger["requests"]}
        messages = {m["request_id"]: m for m in ledger["messages"]}
        attempts, owner_rows, native_rows = Counter(), [], 0
        seen_roots = set()
        for index, (shard, window, limit) in enumerate(zip(shards, ledger["service_windows"], limits), 1):
            if shard.name != f"segment_{index:04d}.json.gz":
                raise ValueError("noncontiguous_raw_segments")
            part = read(shard)
            if len(part["control_records"]) > limit:
                raise ValueError("activation_budget_mismatch")
            actual = sorted([("owner_activation", r) for r in part["control_records"]] +
                            [("native_advance_full", r) for r in part["native_batches"]],
                            key=lambda item: item[1]["trace_sequence"])
            measured = sorted([b for b in ledger["bundles"]
                if window["start_ns"] <= b["start_ns"] <= b["end_ns"] <= window["end_ns"]
                and b["kind"] in {"owner_activation", "native_advance_full"}], key=lambda b: b["start_ns"])
            if len(actual) != len(measured) or [r[1]["trace_sequence"] for r in actual] != list(range(len(actual))):
                raise ValueError("raw_execution_sequence_mismatch")
            for (kind, row), bundle in zip(actual, measured):
                if kind != bundle["kind"]:
                    raise ValueError("wrapper_execution_order_mismatch")
                if kind == "owner_activation":
                    rid = bundle["activation_root_id"]
                    root = roots[rid]
                    if rid in seen_roots or any(root[k] != row[k] for k in ("owner_id", "owner_epoch")) or root["activation_causes"] != row["causes"]:
                        raise ValueError("owner_identity_or_causes_mismatch")
                    seen_roots.add(rid)
                    inner = row["compute_wall_ms"]
                    outer = (bundle["end_ns"]-bundle["start_ns"])/1e6
                    if not isinstance(inner, (int, float)) or not math.isfinite(inner) or inner < 0 or inner > outer+.001:
                        raise ValueError("inner_owner_timing_outside_wrapper")
                    owner_rows.append({"request_id": rid, "inner_compute_ms": inner, "outer_wrapper_ms": outer,
                                       "wrapper_minus_inner_ms": outer-inner})
                else:
                    native_rows += 1
                    if (bundle["native_status"] != row["status"] or bundle["timestamp_complete"] != row["timestamp_complete"] or
                            bundle["physical_time"] != row["end_at"]):
                        raise ValueError("native_boundary_mismatch")
            for call in part["client_calls"]:
                mid = call["request"]["request_id"]
                if mid not in messages or digest(call["request"]) != messages[mid]["payload_sha256"]:
                    raise ValueError("submission_identity_or_payload_mismatch")
                attempts[mid] += 1
            final_state = part["controller_state"]
        if seen_roots != {r["request_id"] for r in roots.values() if not r["maintenance_only"]}:
            raise ValueError("activation_denominator_mismatch")
        if dict(attempts) != {mid: m["attempts"] for mid, m in messages.items()}:
            raise ValueError("attempt_or_message_denominator_mismatch")
        outbox = final_state["client"]["outbox"]
        if set(outbox) != set(messages):
            raise ValueError("outbox_history_omitted")
        for mid, row in outbox.items():
            if digest(row["payload"]) != messages[mid]["payload_sha256"] or bool(row["terminal"]) != (messages[mid]["closed_ns"] is not None):
                raise ValueError("final_client_lifecycle_mismatch")
        report.update(status="verified_raw_execution_and_bundle_accounting", owner_activations=len(owner_rows),
            native_advance_calls=native_rows, protocol_identities=len(messages), submission_attempts=sum(attempts.values()),
            open_roots=analysis["open_root_count"], max_complete_compute_upper_ns=analysis["max_complete_compute_upper_ns"],
            inner_owner_over_100ms=sum(r["inner_compute_ms"] > 100 for r in owner_rows),
            outer_owner_over_100ms=sum(r["outer_wrapper_ms"] > 100 for r in owner_rows),
            max_inner_owner_ms=max((r["inner_compute_ms"] for r in owner_rows), default=None),
            max_outer_owner_ms=max((r["outer_wrapper_ms"] for r in owner_rows), default=None),
            largest_inner_owner_intervals=sorted(owner_rows, key=lambda r:r["inner_compute_ms"], reverse=True)[:10],
            scope="Finite instrumented owner-update cohort; raw-trace coverage cross-check, not isolated native stages, business-request or deployment certification.")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        report.update(status="unknown_invalid_or_missing_raw_evidence", error=str(exc))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.capture)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "verified_raw_execution_and_bundle_accounting" else 2


if __name__ == "__main__":
    raise SystemExit(main())
