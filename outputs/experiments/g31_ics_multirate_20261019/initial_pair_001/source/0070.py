"""Compare full/compact original G31 runs without dropping failed business rows.

Timing is a serial technical comparison of these executions, not an independent
statistical replication or a complete deployment response-time certificate.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

from .original_workload import digest, write_json


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def compare_rows(left: Path, right: Path) -> dict:
    hashes = [hashlib.sha256(), hashlib.sha256()]
    counts = [0, 0]
    mismatch_count, samples = 0, []
    sentinel = object()
    for index, pair in enumerate(itertools.zip_longest(rows(left), rows(right), fillvalue=sentinel)):
        for side, value in enumerate(pair):
            if value is not sentinel:
                counts[side] += 1
                hashes[side].update(canonical(value) + b"\n")
        if pair[0] != pair[1]:
            mismatch_count += 1
            if len(samples) < 3:
                samples.append({"row": index, "left": None if pair[0] is sentinel else pair[0],
                                "right": None if pair[1] is sentinel else pair[1]})
    return {"equal": mismatch_count == 0, "counts": counts,
            "canonical_sha256": [h.hexdigest() for h in hashes],
            "mismatch_count": mismatch_count, "first_mismatches": samples}


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "max": None, "over_100ms": 0}
    ordered = sorted(values)
    # Observed nearest-rank quantiles, with no tail-distribution extrapolation.
    return {"count": len(values), "sum": sum(values), "max": ordered[-1],
            "p50": ordered[math.ceil(.50*len(values))-1],
            "p95": ordered[math.ceil(.95*len(values))-1],
            "p99": ordered[math.ceil(.99*len(values))-1],
            "over_100ms": sum(v > 100 for v in values),
            "over_100ms_fraction": sum(v > 100 for v in values)/len(values)}


def controls(path: Path):
    semantics, compute, publication, owner_plus_publication, publication_batches = [], [], [], [], []
    native_wall, native_cpu, result_render_wall = [], [], []
    hotspots = []
    for row in rows(path/"control_steps.jsonl"):
        for batch in row.get("native_batches", []):
            if batch["call"] == "advance_to":
                native_wall.append(batch["wall_ms"])
                native_cpu.append(batch["cpu_ms"])
            elif batch["call"] == "result_at":
                result_render_wall.append(batch["wall_ms"])
        semantics.append({key: row[key] for key in ("tick", "target", "status", "actual_clock",
                                                   "event_count", "observed", "completed", "loaded", "submitted")})
        identities = []
        pub_by_owner = {}
        for batch in row.get("publication_records", []):
            publication_batches.append(batch["including_due_native_delivery_ms"])
            for record in batch["owner_computations"]:
                ms = record["compute_ms"]
                publication.append(ms)
                pub_by_owner[record["owner_id"]] = pub_by_owner.get(record["owner_id"], 0.) + ms
        for record in row["owner_computations"]:
            identities.append({key: record[key] for key in ("owner_id", "decision_identity",
                "residual_decision_identities", "demands", "waiting", "intents", "reply_statuses")})
            ms = record["compute_ms"]
            compute.append(ms)
            owner_plus_publication.append(ms + pub_by_owner.get(record["owner_id"], 0.))
            hotspots.append({"target": row["target"], **record,
                             "publication_compute_ms": pub_by_owner.get(record["owner_id"], 0.)})
        semantics[-1]["decisions"] = identities
    return semantics, {"owner_compute_ms": distribution(compute),
                       "publication_compute_ms": distribution(publication),
                       "publication_batch_including_due_native_delivery_ms": distribution(publication_batches),
                       "shared_native_event_batch_wall_ms": distribution(native_wall),
                       "shared_native_event_batch_cpu_ms": distribution(native_cpu),
                       "result_advance_and_offline_render_wall_ms": distribution(result_render_wall),
                       "owner_plus_publication_compute_ms": distribution(owner_plus_publication),
                       "largest_owner_calls": sorted(hotspots, key=lambda r: r["compute_ms"], reverse=True)[:5]}


def compare(left: Path, right: Path, *, allow_binary_change: bool = False) -> dict:
    lr, rr = read(left/"receipt.json"), read(right/"receipt.json")
    left_controls, left_timing = controls(left)
    right_controls, right_timing = controls(right)
    metadata = ("binary_sha256", "predictive", "respect_service_forecasts", "control_period", "horizon", "max_events", "message_delay", "demand_delay")
    if allow_binary_change:
        metadata = tuple(k for k in metadata if k != "binary_sha256")
    checks = {"same_declared_configuration": all(lr.get(k) == rr.get(k) for k in metadata),
              "same_business_input_manifest": read(left/"input_manifest.json") == read(right/"input_manifest.json"),
              "source_unchanged_in_both_runs": not lr["source_changed"] and not rr["source_changed"],
              "both_reached": lr["status"] == rr["status"] == "reached",
              "same_submitted_requests_and_replies": read(left/"submitted_requests.json") == read(right/"submitted_requests.json"),
              "same_control_boundaries_and_decisions": left_controls == right_controls,
              "same_final_native_state": lr["offline_final_state_sha256"] == rr["offline_final_state_sha256"]}
    row_checks = {name: compare_rows(left/name, right/name) for name in (
        "business_crosswalk.jsonl.gz", "business_results.jsonl.gz", "physical_events.jsonl.gz")}
    with gzip.open(left/"controller_state.json.gz", "rt", encoding="utf-8") as stream:
        lc = json.load(stream)
    with gzip.open(right/"controller_state.json.gz", "rt", encoding="utf-8") as stream:
        rc = json.load(stream)
    checks["same_final_controller_state"] = lc == rc
    return {"schema": "g31.control_representation_comparison.v1",
            "status": "equivalent" if all(checks.values()) and all(r["equal"] for r in row_checks.values()) else "mismatch",
            "runs": [str(left), str(right)], "receipt_sha256": [digest(left/"receipt.json"), digest(right/"receipt.json")],
            "binary_change_explicitly_allowed": allow_binary_change,
            "same_binary": lr["binary_sha256"] == rr["binary_sha256"],
            "checks": checks, "row_checks": row_checks,
            "timing": {"baseline": left_timing, "candidate": right_timing},
            "complete_100ms_certified": False,
            "limits": ["Measured owner plus publication compute still omits delivery-time revalidation and actual confirmation/transport.",
                       "Serial technical executions are not independent source instances or two-machine deployment evidence.",
                       "Equal decision digests do not by themselves prove all hidden candidate arrays equal; actual requests, complete event rows, jobs and native state are additionally compared."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-binary-change", action="store_true",
                        help="Explicit version-to-version compatibility comparison; default requires the same native binary.")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = compare(args.baseline, args.candidate, allow_binary_change=args.allow_binary_change)
    write_json(args.output, result)
    print(json.dumps({key: result[key] for key in ("status", "checks", "complete_100ms_certified")}, indent=2))
    return int(result["status"] != "equivalent")


if __name__ == "__main__":
    raise SystemExit(main())
