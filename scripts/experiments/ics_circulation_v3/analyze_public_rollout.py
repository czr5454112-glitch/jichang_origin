"""Recompute saved paired outcomes and inspect declared positive/negative cases."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .experiment_protocol import create_output_directory, write_new_json
from .runtime import COST_WEIGHTS


def run(inputs, output):
    inputs, output = Path(inputs), create_output_directory(output)
    hashes = {}
    def read(name):
        raw = (inputs / name).read_bytes()
        hashes[name] = sha256(raw).hexdigest()
        return json.loads(raw)
    summary = read("summary.json")
    if summary["failures"] or summary["source_changed_during_run"] or len(summary["rows"]) != 144:
        raise ValueError("incomplete or changed public-rollout evidence")
    rows = summary["rows"]
    matched = {(r["scene"], r["tape"], r["policy"]): r for r in rows}
    if len(matched) != 144:
        raise ValueError("duplicate matched episode")
    checked, decisions, branches = 0, 0, 0
    for row in rows:
        artifact = read(row["identity"] + ".json")
        result = artifact["result"]
        reconstructed = sum(COST_WEIGHTS[k] * v for k, v in result["cost_components"].items())
        if abs(reconstructed - row["total_cost"]) > 1e-9 or len(result["completed"]) != row["completed"]:
            raise ValueError("raw outcome does not match summary")
        for decision in artifact["public_rollouts"]:
            if (any(f["published_at"] > decision["time"] for f in decision["published_forecasts"])
                    or len(decision["rollouts"]) != decision["candidate_count"]
                    or decision["candidate_count"] > 4):
                raise ValueError("publication or candidate budget mismatch")
            chosen = min(range(len(decision["rollouts"])), key=lambda i: (decision["rollouts"][i]["cost"], i))
            if decision["chosen_index"] != chosen:
                raise ValueError("selection differs from all-candidate public rollout")
            for branch in decision["rollouts"]:
                if abs(branch["cost"] - sum(COST_WEIGHTS[k] * v for k, v in branch["cost_components"].items())) > 1e-9:
                    raise ValueError("branch component sum mismatch")
            decisions += 1
            branches += len(decision["rollouts"])
        checked += 1
    totals = []
    for regime in ("nominal", "stress"):
        for policy in ("baseline", "timed", "conditional_timed", "public_rollout"):
            group = [r for r in rows if r["policy"] == policy and (r["tape"] == "nominal") == (regime == "nominal")]
            totals.append({"regime": regime, "policy": policy, "runs": len(group),
                           **{key: sum(r[key] for r in group) for key in (
                               "total_cost", "scheduled_bags", "completed", "on_time", "internal_rollouts",
                               "process_cpu_seconds", "wall_seconds")}})
    pairs = []
    for row in rows:
        if row["policy"] != "public_rollout":
            continue
        baseline = matched[row["scene"], row["tape"], "timed"]
        delta = row["total_cost"] - baseline["total_cost"]
        pairs.append({"scene": row["scene"], "tape": row["tape"], "delta": delta,
                      "comparison": "better" if delta < -1e-9 else "worse" if delta > 1e-9 else "tie"})
    mechanisms = []
    for scene, tape in (("stream_L2_D1_slack3", "nominal"), ("stream_L4_D1_slack3", "stress_0")):
        for policy in ("timed", "public_rollout"):
            name = f"{scene}__{tape}__{policy}"
            artifact = read(name + ".json")
            mechanisms.append({"identity": name, "metrics": artifact["metrics"],
                "routes": [{"time": r["time"], "bag": r["bag_id"], "legs": r["chosen"]["legs"]}
                           for r in artifact["route_history"]],
                "accepted_slow": [r for r in artifact["slow_history"] if r["proposals"]],
                "load_times": artifact["result"]["final_snapshot"]["load_times"]})
    result = {"checked_episodes": checked, "checked_public_decisions": decisions,
              "checked_public_branches": branches, "totals": totals, "pairs": pairs,
              "paired_counts": dict(Counter(p["comparison"] for p in pairs)),
              "mechanism_cases": mechanisms, "source_input_sha256": hashes,
              "analyzer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "interpretation": "reused development streams; descriptive matched pairs, no independence or global improvement claim"}
    write_new_json(output / "analysis.json", result)
    (output / "analyze_public_rollout.py").write_bytes(Path(__file__).read_bytes())
    return {key: result[key] for key in ("checked_episodes", "checked_public_decisions", "checked_public_branches", "paired_counts")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(run(args.inputs, args.output))
