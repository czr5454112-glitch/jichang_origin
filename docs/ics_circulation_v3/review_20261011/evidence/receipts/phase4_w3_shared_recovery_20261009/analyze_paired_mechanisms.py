"""Post-hoc descriptive decomposition; no fitting, simulation, or selection."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json


WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}
TOLERANCE = 1e-9


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def compare(value):
    return "better" if value < -TOLERANCE else "worse" if value > TOLERANCE else "equal"


def main():
    root = Path(__file__).resolve().parent
    evaluation = root / "evaluation"
    summary_path = evaluation / "summary.json"
    records = read(summary_path)["deployment_metrics"]
    index = {(r["stream"], r["realization"], r["policy"]): r for r in records}
    if len(index) != 288 or len(records) != 288 or any(r["status"] != "completed_run" for r in records):
        raise ValueError("Do not drop failed, duplicate, or absent requests")
    grouped, pairs = defaultdict(list), []
    for row in records:
        if not row["policy"].startswith("shared__"):
            continue
        control = index[row["stream"], row["realization"], "timed"]
        if row["input_sha256"] != control["input_sha256"] or row["scheduled_bags"] != control["scheduled_bags"]:
            raise ValueError("Unpaired inputs or task population")
        for metrics in (row, control):
            if abs(sum(WEIGHTS[k] * v for k, v in metrics["cost_components"].items()) - metrics["total_cost"]) > TOLERANCE:
                raise ValueError("Stored cost disagrees with declared physical objective")
        pair = {"stream": row["stream"], "realization": row["realization"], "policy": row["policy"],
                "input_sha256": row["input_sha256"], "scheduled_bags": row["scheduled_bags"],
                "cost": row["total_cost"], "timed_cost": control["total_cost"],
                "cost_delta": row["total_cost"] - control["total_cost"],
                "on_time": row["on_time"], "timed_on_time": control["on_time"],
                "on_time_delta": row["on_time"] - control["on_time"],
                "cost_components": row["cost_components"], "timed_cost_components": control["cost_components"],
                "weighted_component_deltas": {k: WEIGHTS[k] * (row["cost_components"][k] - control["cost_components"][k]) for k in WEIGHTS}}
        pairs.append(pair)
        for regime in ("all", "nominal" if row["realization"] == "nominal" else "stress"):
            grouped[regime, row["policy"]].append(pair)
    aggregates = {}
    for (regime, policy), rows in sorted(grouped.items()):
        aggregates.setdefault(regime, {})[policy] = {
            "paired_episodes": len(rows), "scheduled_bags": sum(r["scheduled_bags"] for r in rows),
            "cost_comparison": {status: sum(compare(r["cost_delta"]) == status for r in rows) for status in ("better", "equal", "worse")},
            "on_time_comparison": {status: sum(compare(-r["on_time_delta"]) == status for r in rows) for status in ("better", "equal", "worse")},
            "cost_better_but_on_time_worse_episodes": sum(r["cost_delta"] < -TOLERANCE and r["on_time_delta"] < 0 for r in rows),
            "cost_sum": sum(r["cost"] for r in rows), "timed_cost_sum": sum(r["timed_cost"] for r in rows),
            "cost_delta_sum": sum(r["cost_delta"] for r in rows),
            "on_time": sum(r["on_time"] for r in rows), "timed_on_time": sum(r["timed_on_time"] for r in rows),
            "on_time_delta": sum(r["on_time_delta"] for r in rows),
            "weighted_component_delta_sums": {k: sum(r["weighted_component_deltas"][k] for r in rows) for k in WEIGHTS},
        }
    examples = []
    for policy in sorted({r["policy"] for r in pairs}):
        local = [r for r in pairs if r["policy"] == policy]
        for category, subset, greatest in (
            ("largest_cost_improvement", [r for r in local if r["cost_delta"] < -TOLERANCE], False),
            ("largest_cost_regression", [r for r in local if r["cost_delta"] > TOLERANCE], True),
            ("cost_improvement_with_fewer_on_time", [r for r in local if r["cost_delta"] < -TOLERANCE and r["on_time_delta"] < 0], False),
        ):
            if not subset:
                continue
            chosen = sorted(subset, key=lambda r: ((-1 if greatest else 1) * r["cost_delta"], r["stream"], r["realization"]))[0]
            folder = evaluation / (chosen["stream"] + "__" + chosen["realization"])
            inputs = read(folder / "inputs.json")
            actual, control = read(folder / (policy + ".json")), read(folder / "timed.json")
            tasks = {**inputs["initial"]["bags"], **{b["bag_id"]: b for b in inputs["actual_tape_event_engine_only"]}}
            details = []
            for bag_id, bag in sorted(tasks.items()):
                finish, baseline_finish = actual["result"]["completed"][bag_id], control["result"]["completed"][bag_id]
                details.append({"bag_id": bag_id, "arrival": bag["arrival"], "deadline": bag["deadline"], "protected": bag["protected"],
                    "completed_at": finish, "timed_completed_at": baseline_finish,
                    "tardiness": max(0, finish - bag["deadline"]), "timed_tardiness": max(0, baseline_finish - bag["deadline"]),
                    "on_time": finish <= bag["deadline"], "timed_on_time": baseline_finish <= bag["deadline"]})
            if sum(d["on_time"] for d in details) != chosen["on_time"] or sum(d["timed_on_time"] for d in details) != chosen["timed_on_time"]:
                raise ValueError("Saved per-task completion disagrees with aggregate on-time count")
            examples.append({"post_hoc_diagnostic_only": True, "selection_rule": category,
                **chosen, "task_completion_comparison": details,
                "actual_artifact": str((folder / (policy + ".json")).relative_to(root)).replace("\\", "/"),
                "control_artifact": str((folder / "timed.json").relative_to(root)).replace("\\", "/")})
    analysis = {"input_summary_sha256": sha256(summary_path.read_bytes()).hexdigest(),
        "purpose": "Post-hoc paired mechanism description only; no new data, fit, policy tuning, seed selection, or confirmation claim.",
        "cost_weights": WEIGHTS, "paired_episode_denominator": len(pairs), "aggregates": aggregates,
        "examples": examples,
        "explanation": [
            "The objective penalizes accumulated tray waiting and nonprotected tardiness in ticks, plus 0.1 times empty-edge distance and terminal penalties. It does not directly optimize the number of tasks meeting deadlines.",
            "Binary on-time counts treat one tick and many ticks late equally. Moving several bags slightly past their deadlines can lower summed tardiness if another late bag improves enough; waiting savings can also offset increased tardiness.",
            "All tasks complete in these saved deployments, so backlog penalties are zero. The exact weighted component deltas show which savings pay for which regressions; this accounting is not proof of a particular neural feature causing a choice.",
            "Nominal and stress totals stay separate. All three declared seeds are reported. Examples are explicitly selected after observing outcomes and cannot validate generalization.",
        ]}
    with (root / "paired_mechanism_analysis.json").open("x", encoding="utf-8") as handle:
        json.dump(analysis, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"paired_episodes": len(pairs), "post_hoc_examples": len(examples), "aggregates": aggregates}, indent=2))


if __name__ == "__main__":
    main()
