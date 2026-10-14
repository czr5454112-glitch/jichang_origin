"""Posthoc descriptive paired summaries; never modifies frozen experiments."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def summarize(rows):
    ok = [r for r in rows if r["status"] == "completed_run"]
    return {"episodes": len(rows), "failed": len(rows) - len(ok),
            "completed": sum(r["completed"] or 0 for r in rows),
            "scheduled_bags": sum(r["scheduled_bags"] for r in rows),
            "cost_sum_successful_episodes": sum(r["total_cost"] for r in ok),
            "on_time": sum(r.get("on_time", 0) for r in rows),
            "episodes_with_uncompleted": sum(bool(r.get("uncompleted")) for r in ok)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linear", type=Path, default=Path("outputs/experiments/ics_circulation_v3/phase4_w3_role_linear_20261009"))
    parser.add_argument("--public", type=Path, default=Path("outputs/experiments/ics_circulation_v3/phase4_w3_public_rollout_20261009"))
    parser.add_argument("--recovery", type=Path, default=Path("outputs/experiments/ics_circulation_v3/phase4_w3_paired_recovery_20261009"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("summary.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("analysis output must be new")
    summary = read(args.linear / "summary.json")
    metrics = summary["deployment_metrics"]
    methods = sorted({r["policy"] for r in metrics})
    groups = defaultdict(list)
    for row in metrics:
        groups[row["stream"], row["realization"]].append(row)
    paired = {}
    for method in methods:
        differences = []
        for key, values in sorted(groups.items()):
            a = next(r for r in values if r["policy"] == method)
            b = next(r for r in values if r["policy"] == "timed")
            valid = a["status"] == b["status"] == "completed_run"
            differences.append({"stream": key[0], "realization": key[1], "both_succeeded": valid,
                "cost_delta_vs_timed": a["total_cost"] - b["total_cost"] if valid else None,
                "completion_delta": a["completed"] - b["completed"] if valid else None,
                "scheduled_bags": a["scheduled_bags"]})
        valid = [r for r in differences if r["both_succeeded"]]
        paired[method] = {"pairs": len(differences), "failed_pairs": len(differences) - len(valid),
            "better": sum(r["cost_delta_vs_timed"] < -1e-9 for r in valid),
            "same": sum(abs(r["cost_delta_vs_timed"]) <= 1e-9 for r in valid),
            "worse": sum(r["cost_delta_vs_timed"] > 1e-9 for r in valid), "rows": differences}
    cross = []
    for (stream, realization), values in sorted(groups.items()):
        local_input = read(args.linear / f"{stream}__{realization}" / "inputs.json")
        public_input = read(args.public / f"{stream}__{realization}_inputs.json")
        input_equal = (local_input["initial"] == public_input["initial"]
            and local_input["forecasts"] == public_input["forecasts"]
            and local_input["horizon"] == public_input["horizon"]
            and local_input["actual_tape_event_engine_only"] == public_input["event_engine_only_tape"])
        for policy in ("baseline", "timed"):
            ours = read(args.linear / f"{stream}__{realization}" / (policy + ".json"))
            theirs = read(args.public / f"{stream}__{realization}__{policy}.json")
            left, right = ours.get("result", {}), theirs.get("result", {})
            row = {"stream": stream, "realization": realization, "policy": policy,
                "input_equal": input_equal, "both_complete_run": ours["metrics"]["status"] == theirs["metrics"]["status"] == "completed_run",
                "cost_components_equal": left.get("cost_components") == right.get("cost_components"),
                "physical_trace_equal": left.get("trace") == right.get("trace"),
                "final_snapshot_equal": left.get("final_snapshot") == right.get("final_snapshot"),
                "completion_equal": left.get("completed") == right.get("completed"),
                "slow_trigger_times_equal": ours.get("slow_trigger_times") == theirs.get("slow_trigger_times"),
                "input_semantic_sha256": digest(local_input)}
            cross.append(row)
    linear_labels = read(args.linear / "input_manifest.json")
    recovery_labels = read(args.recovery / "r0/input_manifest.json")
    label_equality = (linear_labels["manifest_sha256"] == recovery_labels["manifest_sha256"]
                      and linear_labels["files_sha256"] == recovery_labels["files_sha256"])
    by_policy = {m: summarize([r for r in metrics if r["policy"] == m]) for m in methods}
    by_regime = {regime: {m: summarize([r for r in metrics if r["policy"] == m and
        (r["realization"] == "nominal") == (regime == "nominal")]) for m in methods}
        for regime in ("nominal", "stress")}
    result = {"scope": "descriptive only; no model selection, training or new simulation",
        "linear_summary_sha256": sha256((args.linear / "summary.json").read_bytes()).hexdigest(),
        "public_summary_sha256": sha256((args.public / "summary.json").read_bytes()).hexdigest(),
        "recovery_r0_input_manifest_sha256": sha256((args.recovery / "r0/input_manifest.json").read_bytes()).hexdigest(),
        "identical_R0_label_files_to_MLP": label_equality, "policies": by_policy,
        "by_regime": by_regime, "paired_vs_timed": paired,
        "public_cross_check": {"pairs": len(cross), "all_match": all(all(r[k] for k in
            ("input_equal", "both_complete_run", "cost_components_equal", "physical_trace_equal",
             "final_snapshot_equal", "completion_equal", "slow_trigger_times_equal")) for r in cross), "rows": cross},
        "limits": ["Only four constructed development streams; repeated synthetic futures do not create independent operational days.",
            "No causal feature-necessity or universal nonlinear superiority follows from this finite reference.",
            "A feature constant across candidates cancels in a paired linear scorer; nonlinear feature interactions are absent.",
            "Ridge mean-loss regularizer alpha=1 differs from MLP l2=.001 and model capacity; neither was selected using these results."]}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"policies": by_policy, "same_labels": label_equality,
                      "public_control_pairs": len(cross), "all_public_matches": result["public_cross_check"]["all_match"]}))
    return int(not label_equality or not result["public_cross_check"]["all_match"])


if __name__ == "__main__":
    raise SystemExit(main())
