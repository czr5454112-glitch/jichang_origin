"""Read-only diagnosis of what a legacy coarse request profile can establish.

No native execution and no conversion of coarse spans into invented precise
intervals. New output paths preserve previous profiles and their limitations.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagnose(run: dict, summary: dict, input_data: dict) -> dict:
    owners, batches = run["control_records"], run["native_batches"]
    if len(owners) != summary["owner_activations"] or len(input_data["jobs"]) != summary["offered_total"]:
        raise ValueError("measurement_audit:denominator_mismatch")
    if run["status"] != summary["status"] or run["wall_seconds"] != summary["wall_seconds"]:
        raise ValueError("measurement_audit:run_summary_mismatch")
    durations = [r["compute_wall_ms"] for r in owners]
    native = [r["wall_ms"] for r in batches]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0
           for x in durations + native):
        raise ValueError("measurement_audit:invalid_duration")
    no_new = [r for r in owners if not any(item.get("request_id") for key in ("publications", "service_actions", "attempts")
                                           for item in r.get(key, []))]
    outbox = run["controller_state"]["client"]["outbox"]
    call_ids = {c["request"]["request_id"] for c in run["client_calls"]}
    if set(outbox) != call_ids:
        raise ValueError("measurement_audit:incomplete_message_history")
    residual = run["wall_seconds"]*1000 - sum(durations) - sum(native)
    if residual < -1e-6:
        raise ValueError("measurement_audit:inconsistent_envelopes")
    return {"schema": "g31.request_measurement_gap_audit.v1", "status": "diagnosed_coarse_trace",
        "offered_total": len(input_data["jobs"]), "offered_by_current_time": summary["offered_by_current_time"],
        "run_status": run["status"], "physical_time": summary["physical_time"], "horizon": summary["horizon"],
        "cprofile_enabled": summary.get("cprofile_enabled"),
        "owner_update_count": len(owners), "protocol_request_count": len(outbox),
        "protocol_attempt_count": len(run["client_calls"]),
        "owner_updates_without_new_protocol_message": len(no_new),
        "owner_update_max_measured_ms": max(durations, default=None),
        "owner_update_measured_over_100ms_count": sum(x > 100 for x in durations),
        "no_new_message_update_max_measured_ms": max((r["compute_wall_ms"] for r in no_new), default=None),
        "no_new_message_update_measured_over_100ms_count": sum(r["compute_wall_ms"] > 100 for r in no_new),
        "native_batch_max_envelope_ms": max(native, default=None),
        "global_unlocated_residual_ms": max(0., residual),
        "scope": "Owner activation measurements include any cProfile overhead. Native batch durations include physics. Message lifetime upper envelopes are not isolated request compute. No-action updates remain visible here.",
        "missing_for_complete_request_acceptance": [
            "Explicit business-update identities or a declared owner-activation proxy scope before observation",
            "Monotonic interval locations for scheduler/restore/copy/serialization work",
            "Causal root-to-protocol identities for retries, fallback and delivered ACK processing",
            "Native permission validation and commit spans separated from unrelated physics",
            "Complete declared original-input workload horizon and complete selected request lifetimes",
            "Unprofiled acceptance measurements on the declared hardware/load matrix"],
        "complete_request_compute_measured": False,
        "complete_100ms_requirement_certified": False,
        "native_runs_performed_by_this_audit": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: args.profile/name for name in ("summary.json", "run.json.gz", "input.json.gz")}
    identities = {name: sha(path) for name, path in paths.items()}
    summary = json.loads(paths["summary.json"].read_text(encoding="utf-8"))
    with gzip.open(paths["run.json.gz"], "rt", encoding="utf-8") as stream:
        run = json.load(stream)
    with gzip.open(paths["input.json.gz"], "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    report = diagnose(run, summary, data)
    if identities != {name: sha(path) for name, path in paths.items()}:
        raise ValueError("measurement_audit:input_changed")
    report.update(profile_root=str(args.profile.resolve()), input_sha256=identities, source_sha256=sha(__file__))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/"receipt.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (args.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
