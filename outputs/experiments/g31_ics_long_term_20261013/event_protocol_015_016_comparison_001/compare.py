"""Compare every returned semantic value, excluding declared compute timers."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TIMERS = {"compute_wall_ms", "compute_cpu_ms", "submit_compute_ms", "compute_ms",
          "preparation_compute_ms", "wall_ms", "cpu_ms", "wall_seconds", "native_event_ms"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k not in TIMERS}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def digest_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def main():
    folders = [ROOT/f"event_protocol_original24_{version}_001" for version in ("015", "016")]
    receipts = [json.loads((f/"receipt.json").read_text()) for f in folders]
    assert all(r["status"] == "executed_comparison_not_research_gate" and r["source_changed"] == [] for r in receipts)
    assert (folders[0]/"original24/input.json").read_bytes() == (folders[1]/"original24/input.json").read_bytes()
    rows = []
    for policy in receipts[0]["cases"]["original24"]["policies"]:
        paths = [f/"original24"/policy/"run.json.gz" for f in folders]
        runs = []
        for path in paths:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                runs.append(json.load(stream))
        checks = {key: normalize(runs[0][key]) == normalize(runs[1][key]) for key in runs[0] if key not in TIMERS}
        old, new = [r["cases"]["original24"]["policies"][policy] for r in receipts]
        checks.update(metrics=old["metrics"] == new["metrics"], final_native_seal=old["offline_final_state_sha256"] == new["offline_final_state_sha256"])
        diagnostic = []
        for run in runs:
            owner = [c["compute_wall_ms"] for c in run["control_records"] if "compute_wall_ms" in c]
            diagnostic.append({"controller_wall_seconds": run["wall_seconds"], "event_owner_samples": len(owner),
                "event_owner_max_ms": max(owner, default=None), "event_owner_over_100ms": sum(t > 100 for t in owner)})
        rows.append({"policy": policy, "checks": checks, "semantic_sha256": [digest_value(normalize(run)) for run in runs],
            "raw_sha256": [sha(p) for p in paths], "compute_diagnostics": diagnostic})
    receipt = {"status": "passed" if all(all(row["checks"].values()) for row in rows) else "failed",
        "runner_sha256": sha(Path(__file__)), "receipt_sha256": [sha(f/"receipt.json") for f in folders],
        "excluded_compute_timer_keys": sorted(TIMERS), "policies": rows,
        "scope": "All raw returned physics, requests, replies, control decisions, JSON continuation and final native seals; compute timers only excluded.",
        "performance_scope": "015 includes concurrent compilation and 016 is a separate local run. Timings are descriptive, not controlled full-request or deployment certification.",
        "complete_100ms_requirement_certified": False}
    (HERE/"assessment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return int(receipt["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
