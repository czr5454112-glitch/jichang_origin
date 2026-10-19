"""Read-only exact native controller comparison for the public path cache."""
import argparse
import hashlib
import json
from pathlib import Path
from .validate_resume_full_day import encoded
from .resume_full_day import read_gz, sha, ROOT


def read(path):
    return read_gz(path) if path.suffix == ".gz" else json.loads(path.read_bytes())


def verify(directory):
    checks, identities, timing = {}, {}, {}
    for case in ("synthetic", "full1x"):
        dirs = [directory / (case + "-" + arm) for arm in ("reference", "optimized")]
        receipts = [read(d / "receipt.json") for d in dirs]
        summaries = [read(d / "summary.json") for d in dirs]
        manifests = [read(d / "run_shards.json") for d in dirs]
        for d, receipt in zip(dirs, receipts):
            for name, digest in receipt["source_before"].items():
                checks[f"{d.name}:source:{name}"] = sha(ROOT / name) == sha(d / "source_archive" / name) == digest
        checks[case + ":receipts"] = all(r["status"] == "completed" and r["source_changed"] == [] and
            r["binary_after_sha256"] == r["binary_sha256"] for r in receipts)
        checks[case + ":same_sources"] = receipts[0]["source_before"] == receipts[1]["source_before"]
        checks[case + ":same_binary"] = receipts[0]["binary_sha256"] == receipts[1]["binary_sha256"]
        checks[case + ":actual_modes"] = [r["cache_mode"] for r in receipts] == ["off", "on"]
        checks[case + ":ordered_input"] = encoded(read(dirs[0] / "input.json.gz")) == encoded(read(dirs[1] / "input.json.gz"))
        checks[case + ":counts"] = manifests[0]["counts"] == manifests[1]["counts"]
        checks[case + ":shard_count"] = len(manifests[0]["shards"]) == len(manifests[1]["shards"]) > 0
        for key in ("status", "physical_time", "horizon", "offered_total", "offered_by_current_time",
                    "owner_activations", "native_sha256", "native_state_sha256", "metrics", "audit"):
            checks[case + ":summary:" + key] = summaries[0].get(key) == summaries[1].get(key)
        for index, pair in enumerate(zip(manifests[0]["shards"], manifests[1]["shards"])):
            values = []
            for d, item in zip(dirs, pair):
                path = d / item["path"]
                checks[f"{d.name}:raw_hash:{index}"] = sha(path) == item["sha256"]
                identities[str(path)] = sha(path)
                values.append(read(path))
            checks[f"{case}:ordered_all_raw:{index}"] = encoded(values[0]) == encoded(values[1])
            checks[f"{case}:actual_native_seal:{index}"] = (isinstance(values[0].get("native_state_sha256"), str) and
                len(values[0]["native_state_sha256"]) == 64 and values[0]["native_state_sha256"] == values[1].get("native_state_sha256"))
        for d in dirs:
            for name in ("receipt.json", "summary.json", "input.json.gz", "run_shards.json", "travel_pool.json"):
                identities[str(d / name)] = sha(d / name)
        counts = read(dirs[1] / "travel_pool.json")
        checks[case + ":cache_exercised"] = counts["graph_hits"] > 0 and counts["graph_misses"] > 0
        timing[case] = [{"mode": r["cache_mode"], "parent_wall_seconds": r["wall_seconds"],
            "controller_wall_seconds": s["wall_seconds"]} for r, s in zip(receipts, summaries)]
    unchanged = all(sha(Path(p)) == digest for p, digest in identities.items())
    return {"schema": "g31.public_travel_pool_native_parity.v1",
        "status": "passed" if all(checks.values()) and unchanged else "failed", "checks": checks,
        "input_files": identities, "input_unchanged": unchanged, "timing": timing,
        "scope": "Exact declared native cohort; explicit diagnostic clocks excluded, all remaining ordered raw fields and native seals compared. Concurrent-work timing, not isolated speed, full-day or complete100ms certification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    target = args.directory / "independent_assessment.json"
    if target.exists():
        raise ValueError("travel_pool_pair:immutable_assessment_exists")
    report = verify(args.directory)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
        "failed": [key for key, value in report["checks"].items() if not value], "timing": report["timing"]}))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
