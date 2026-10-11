"""Independent multiset comparison of actual nominal decision observations."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w3_same_zone_supply_repaired_20261010"
OUT = Path(__file__).resolve().parent
FIELDS = ("time", "node", "bag_id", "tray_id", "cursor",
          "next_slow_trigger_at", "candidates", "visible_state")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row, fields):
    # Compare canonical JSON strings directly, without sharing the parent
    # analysis's digest function or accepting a hash-only equality.
    return json.dumps({field: row[field] for field in fields}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    summary_path = BASE / "nominal_pilot/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    bound, cases, errors = {str(summary_path): sha(summary_path)}, {}, []
    for item in summary["rows"]:
        path = BASE / item["file"]
        bound[str(path)] = sha(path)
        if bound[str(path)] != item["sha256"]:
            errors.append("raw hash:" + item["case_id"])
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)
        ops = raw["opportunities"]
        roles = Counter()
        for op in ops:
            bag = op["visible_state"]["bags"][op["bag_id"]]
            roles["destination" if op["node"] == bag["destination"] else
                  "origin" if op["node"] == bag["origin"] else "continuation"] += 1
        cases[item["scene"], item["policy"]] = {
            "count": len(ops), "zero": sum(not o["candidate_count"] for o in ops),
            "roles": dict(roles),
            "exact": Counter(key(op, FIELDS) for op in ops),
            "coarse": Counter(key(op, ("time", "node", "bag_id", "tray_id")) for op in ops),
        }
    pairs = []
    for scene in ("cross_cycle", "counterflow", "near_full"):
        old = cases[scene, "old32"]
        for policy in ("old64", "same_zone32plus32"):
            new = cases[scene, policy]
            intersection = old["exact"] & new["exact"]
            pairs.append({"scene": scene, "policy": policy, "old_attempts": old["count"],
                "new_attempts": new["count"], "old_zero": old["zero"], "new_zero": new["zero"],
                "old_roles": old["roles"], "new_roles": new["roles"],
                "exact_public_observation_multiset_overlap": sum(intersection.values()),
                "old_unmatched": sum((old["exact"] - intersection).values()),
                "new_unmatched": sum((new["exact"] - intersection).values()),
                "coarse_time_node_bag_tray_overlap": sum((old["coarse"] & new["coarse"]).values())})
    for path, digest in bound.items():
        if sha(Path(path)) != digest:
            errors.append("changed:" + path)
    result = {"schema": "round6_independent_nominal_observation_census_v1",
        "source_code_sha256": sha(Path(__file__)), "bound_files": bound,
        "errors": errors, "pairs": pairs, "fields": list(FIELDS),
        "semantics": [
            "Both zero and nonzero attempts counted; exact multiset intersection preserves multiplicity.",
            "Public topology is shared and pinned by experiment protocol; visible_state excludes the duplicate network serialization.",
            "Cursor, supplied candidate pool, and next slow clock are included. Same attempt count alone proves no shared state.",
            "Private route cache and continuation-policy identity are not in these public observation fields.",
            "Even a matching public observation does not authorize value-label reuse across different continuation policies or private caches.",
            "No outcomes were used to select comparison states; every nominal opportunity in all nine cases is included."
        ], "cpu_seconds": time.process_time() - cpu, "wall_seconds": time.perf_counter() - started}
    with (OUT / "nominal_observation_overlap.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "bound_files"}))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
