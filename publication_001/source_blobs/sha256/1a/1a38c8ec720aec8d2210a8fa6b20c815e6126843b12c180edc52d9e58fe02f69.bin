"""Read-only fidelity gate for consume/seal/lossless-export native runs."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path

CLOCK_FIELDS = {"wall_seconds", "compute_wall_ms", "compute_cpu_ms", "submit_compute_ms",
                "wall_ms", "cpu_ms", "native_event_ms", "runtime_seconds"}


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k not in CLOCK_FIELDS}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    checks, identities = {}, {}
    for case in ("synthetic", "full1x"):
        left, right = (args.directory / f"{case}-{arm}" for arm in ("reference", "optimized"))
        paths = [*left.rglob("*.json"), *right.rglob("*.json"), *left.rglob("*.gz"), *right.rglob("*.gz")]
        identities.update({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        receipts = [read(p / "receipt.json") for p in (left, right)]
        summaries = [read(p / "summary.json") for p in (left, right)]
        manifests = [read(p / "run_shards.json") for p in (left, right)]
        checks[case + ":completed_unchanged"] = all(r["status"] == "completed" and r["source_changed"] == [] for r in receipts)
        checks[case + ":input_exact"] = read(left / "input.json.gz") == read(right / "input.json.gz")
        checks[case + ":ordered_shard_count"] = len(manifests[0]["shards"]) == len(manifests[1]["shards"]) > 1
        checks[case + ":all_raw_counts"] = manifests[0]["counts"] == manifests[1]["counts"]
        checks[case + ":actual_flags"] = all(flag in receipts[1]["command"] for flag in ("--consume-controller-state", "--seal-shards", "--gzip-level"))
        checks[case + ":gzip_level"] = summaries[0]["gzip_level"] == 9 and summaries[1]["gzip_level"] == 1
        for key in ("status", "physical_time", "horizon", "offered_total", "offered_by_current_time", "owner_activations", "native_sha256", "native_state_sha256", "metrics"):
            checks[case + ":" + key] = summaries[0][key] == summaries[1][key]
        seals = []
        for i, (a, b) in enumerate(zip(manifests[0]["shards"], manifests[1]["shards"])):
            pa, pb = left / a["path"], right / b["path"]
            checks[f"{case}:shard_hashes:{i}"] = identities[str(pa)] == a["sha256"] and identities[str(pb)] == b["sha256"]
            va, vb = read(pa), read(pb)
            seals.append(vb.pop("native_state_sha256", None))
            cost = vb.pop("diagnostic_seal_wall_ms", None)
            checks[f"{case}:actual_seal:{i}"] = isinstance(seals[-1], str) and len(seals[-1]) == 64 and isinstance(cost, (int, float)) and cost >= 0
            checks[f"{case}:all_ordered_semantics:{i}"] = json.dumps(normalized(va), ensure_ascii=False) == json.dumps(normalized(vb), ensure_ascii=False)
        checks[case + ":last_seal_matches_summary"] = bool(seals) and seals[-1] == summaries[1]["native_state_sha256"]
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in identities.items())
    report = {"schema": "g31.native_stream_driver_fidelity.v1", "status": "passed" if all(checks.values()) and unchanged else "failed",
              "checks": checks, "input_files": identities, "input_unchanged": unchanged,
              "complete_request_100ms_certified": False,
              "scope": "Actual two native024 matched cases; all input, shard calls/observations/state/physics and final native seals. Intermediate seals producer-reported; no general or whole-day certificate."}
    (args.directory / "independent_assessment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed": [k for k, v in checks.items() if not v]}))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
