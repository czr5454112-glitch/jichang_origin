"""Saved-only paired summaries; no fitting, replay, or model selection."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json


def main():
    root = Path(__file__).resolve().parent
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = summary["records"]
    index = {(r["stream"], r["realization"], r["policy"], r["variant"]): r for r in rows}
    if len(rows) != len(index) or len(rows) != 1872:
        raise ValueError("Missing/duplicate episode denominator")
    groups = defaultdict(list)
    for key, original in index.items():
        if original["variant"] != "original":
            continue
        rule = index[key[:3] + ("destination_first",)]
        if original["input_sha256"] != rule["input_sha256"] or original["scheduled_bags"] != rule["scheduled_bags"]:
            raise ValueError("Paired population/tape changed")
        pair = {"stream": key[0], "realization": key[1], "original": original, "rule": rule}
        for regime in ("all", "nominal" if key[1] == "nominal" else "stress"):
            groups[regime, key[2]].append(pair)
    output = {}
    for (regime, policy), pairs in sorted(groups.items()):
        complete = [p for p in pairs if p["original"]["status"] == p["rule"]["status"] == "completed_run"]
        deltas = [p["rule"]["total_cost"] - p["original"]["total_cost"] for p in complete]
        stats = {"planned_pairs": len(pairs), "successful_pairs": len(complete),
            "failed_pairs": [{"stream": p["stream"], "realization": p["realization"]} for p in pairs if p not in complete],
            "completed_pair_cost_better_equal_worse": {
                "better": sum(d < -1e-9 for d in deltas), "equal": sum(abs(d) <= 1e-9 for d in deltas),
                "worse": sum(d > 1e-9 for d in deltas)},
            "completed_pair_cost_delta_sum": sum(deltas),
            "completed_pair_component_delta_sums": {k: sum(p["rule"]["cost_components"][k] - p["original"]["cost_components"][k] for p in complete)
                for k in ("tray_wait", "nonprotected_tardiness", "empty_distance", "terminal_backlog", "terminal_inflight")},
        }
        for variant, source in (("original", "original"), ("destination_first", "rule")):
            good = [p[source] for p in pairs if p[source]["status"] == "completed_run"]
            stats[variant] = {"episodes": len(pairs), "successful_runs": len(good),
                "scheduled_bags_all_runs": sum(p[source]["scheduled_bags"] for p in pairs),
                "completed": sum(p["completed"] for p in good), "on_time": sum(p["on_time"] for p in good),
                "cost_sum_successful_runs": sum(p["total_cost"] for p in good),
                "selector_calls": sum(p["selector_calls"] for p in good),
                "loaded_attempts": sum(p["loaded_attempts"] for p in good),
                "zero_authorized_loaded_attempts": sum(p["zero_authorized_loaded_attempts"] for p in good),
                "eligible_unload_calls": sum(p["eligible_unload_calls"] for p in good),
                "no_legal_unload_calls": sum(p["no_legal_unload_calls"] for p in good),
                "overrides": sum(p["overrides"] for p in good)}
        output.setdefault(regime, {})[policy] = stats
    destination = root / "paired_summary.json"
    result = {"input_summary_sha256": sha256(summary_path.read_bytes()).hexdigest(),
        "episodes": len(rows), "pairs": 936, "aggregates": output,
        "limitations": "Previously evaluated synthetic streams/tapes; descriptive paired comparison only. All models and seeds retained. Rule changes subsequent states, so differing invocation counts are not matched-state effects. Failed pairs stay in the denominator."}
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"episodes": len(rows), "pairs": 936,
        "all": {p: {"delta_J_sum": v["completed_pair_cost_delta_sum"],
            "delta_completed": v["destination_first"]["completed"] - v["original"]["completed"],
            "delta_on_time": v["destination_first"]["on_time"] - v["original"]["on_time"],
            "overrides": v["destination_first"]["overrides"]} for p, v in output["all"].items()}}, indent=2))


if __name__ == "__main__":
    main()
