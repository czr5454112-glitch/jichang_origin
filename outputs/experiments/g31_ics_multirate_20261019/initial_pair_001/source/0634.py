"""Compare completed physical horizons across diagnostic shard sizes."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from .verify_stream_driver_pair import normalized, read


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_shards(directory):
    found = []
    for path in sorted((directory / "segments").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            prefix = stream.read(100)
        if prefix.startswith('{"status": "reached",'):
            found.append(path)
        elif not prefix.startswith('{"status": "control_budget_exhausted",'):
            raise ValueError("prefix_audit:unexpected_shard_status_or_serialization")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("left", "right", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    left, right = completed_shards(args.left), completed_shards(args.right)
    count = min(len(left), len(right))
    if not count:
        raise ValueError("prefix_audit:no_common_complete_horizon")
    pa, pb = left[count - 1], right[count - 1]
    a, b = read(pa), read(pb)
    checks = {
        "ordered_input_exact": json.dumps(read(args.left / "input.json.gz"), ensure_ascii=False) == json.dumps(read(args.right / "input.json.gz"), ensure_ascii=False),
        "both_completed": a["status"] == b["status"] == "reached",
        "same_physical_horizon": a["control_continuation"] == b["control_continuation"],
        "ordered_controller_state": json.dumps(normalized(a["controller_state"]), ensure_ascii=False) == json.dumps(normalized(b["controller_state"]), ensure_ascii=False),
        "ordered_physical_result": json.dumps(normalized(a["result"]), ensure_ascii=False) == json.dumps(normalized(b["result"]), ensure_ascii=False),
    }
    report = {"schema": "g31.completed_full_input_prefix_comparison.v1", "status": "passed" if all(checks.values()) else "failed",
              "checks": checks, "physical_horizon": a["control_continuation"]["physical_time"],
              "left": {"path": str(pa), "sha256": sha(pa)}, "right": {"path": str(pb), "sha256": sha(pb)},
              "right_native_state_sha256": b.get("native_state_sha256"),
              "original_left_native_seal_available": "native_state_sha256" in a,
              "scope": "Exact ordered whole controller state and completed-horizon physical result, excluding only named timing fields. Per-shard trace arrays span different activation counts and are not compared here. No original hidden-state or whole-day/timing certificate."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps({"status": report["status"], "horizon": report["physical_horizon"], "checks": checks}))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
