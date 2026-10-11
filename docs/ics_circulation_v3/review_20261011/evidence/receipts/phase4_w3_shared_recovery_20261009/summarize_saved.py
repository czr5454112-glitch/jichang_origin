"""Recompute descriptive shared-data results from frozen saved rows only."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
from statistics import mean


def main():
    root = Path(__file__).resolve().parent
    path = root / "evaluation/summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    records = summary["deployment_metrics"]
    paired = {(r["stream"], r["realization"], r["policy"]): r for r in records}
    if len(paired) != 288 or len(records) != 288:
        raise ValueError("Incomplete or duplicate deployment denominator")
    grouped = defaultdict(list)
    for row in records:
        if row["status"] != "completed_run":
            raise ValueError("Do not silently omit failed deployments")
        baseline = paired[row["stream"], row["realization"], "baseline"]
        timed = paired[row["stream"], row["realization"], "timed"]
        if len({row["input_sha256"], baseline["input_sha256"], timed["input_sha256"]}) != 1:
            raise ValueError("Policies lack identical paired input")
        if len({row["scheduled_bags"], baseline["scheduled_bags"], timed["scheduled_bags"]}) != 1:
            raise ValueError("Policies lack identical task denominator")
        for regime in ("all", "nominal" if row["realization"] == "nominal" else "stress"):
            grouped[regime, row["policy"]].append(row)
    metrics = {}
    for (regime, policy), rows in sorted(grouped.items()):
        metrics.setdefault(regime, {})[policy] = {
            "episodes": len(rows), "scheduled": sum(r["scheduled_bags"] for r in rows),
            "completed": sum(r["completed"] for r in rows), "on_time": sum(r["on_time"] for r in rows),
            "mean_cost": mean(r["total_cost"] for r in rows),
            "mean_paired_cost_delta_vs_baseline": mean(r["total_cost"] - paired[r["stream"], r["realization"], "baseline"]["total_cost"] for r in rows),
            "mean_paired_cost_delta_vs_timed": mean(r["total_cost"] - paired[r["stream"], r["realization"], "timed"]["total_cost"] for r in rows),
            "out_of_range_vectors": sum(r["out_of_range_vectors"] for r in rows),
            "candidate_feature_vectors": sum(r["candidate_feature_vectors"] for r in rows),
            "cpu_seconds_sum": sum(r["cpu_seconds"] for r in rows),
            "wall_seconds_sum_not_makespan": sum(r["wall_seconds"] for r in rows),
        }
    assessments = json.loads((root / "evaluation/held_out_checkpoints.json").read_text(encoding="utf-8"))
    assessment_groups = defaultdict(list)
    for stream, policies in assessments.items():
        for policy, value in policies.items():
            identity = policy.split("__", 2)[-1] if policy.startswith("shared__") else policy
            assessment_groups[identity].extend(value["decisions"])
    result = {
        "input_summary_sha256": sha256(path.read_bytes()).hexdigest(),
        "deployment_runs": len(records), "scheduled": sum(r["scheduled_bags"] for r in records),
        "completed": sum(r["completed"] for r in records), "on_time": sum(r["on_time"] for r in records),
        "policies": metrics,
        "held_out_checkpoint_aggregates": {name: {"checkpoints": len(rows), "mean_regret": mean(r["regret"] for r in rows)} for name, rows in sorted(assessment_groups.items())},
        "limits": "Descriptive reused four-stream evidence, not independent field generalization; all three seeds retained. Repeated rows and stress tapes are paired, not independent samples. Runtime measurements shared CPU load with the main recovery evaluation.",
    }
    destination = root / "saved_metrics_summary.json"
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
