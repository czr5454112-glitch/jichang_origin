"""Post-hoc saved-record description of rule-variant unfinished tasks."""
from hashlib import sha256
from pathlib import Path
import json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    root = Path(__file__).resolve().parent
    summary_path = root / "summary.json"
    rows = read(summary_path)["records"]
    details = []
    for row in rows:
        if row["variant"] != "destination_first" or not row["uncompleted"]:
            continue
        folder = root / "units" / (row["stream"] + "__" + row["realization"])
        path = folder / (row["policy"] + "__destination_first.json")
        record, inputs = read(path), read(folder / "inputs.json")
        bags = {**inputs["initial"]["bags"], **{b["bag_id"]: b for b in inputs["actual_tape_event_engine_only"]}}
        for bag_id in row["uncompleted"]:
            calls = [h for h in record["destination_first_history"] if h["bag_id"] == bag_id]
            details.append({"stream": row["stream"], "realization": row["realization"], "policy": row["policy"],
                "bag": bags[bag_id], "horizon": inputs["horizon"], "source_artifact": str(path.relative_to(root)).replace("\\", "/"),
                "source_artifact_sha256": sha256(path.read_bytes()).hexdigest(), "calls": len(calls),
                "at_destination_calls": sum(h["at_destination"] for h in calls),
                "unload_eligible_calls": sum(h["eligible"] for h in calls),
                "overrides_for_this_bag": sum(h["overridden"] for h in calls),
                "call_times_and_nodes": [{"time": h["time"], "node": h["source_node"]} for h in calls],
                "final_carrier": [t for t in record["result"]["final_trays"].values() if t["bag_id"] == bag_id]})
    result = {"post_hoc_diagnostic_only": True, "input_summary_sha256": sha256(summary_path.read_bytes()).hexdigest(),
        "unfinished_instances": len(details), "unfinished_by_policy": {name: sum(d["policy"] == name for d in details) for name in sorted({d["policy"] for d in details})},
        "all_had_zero_destination_decision_calls": all(d["at_destination_calls"] == 0 for d in details),
        "details": details,
        "interpretation": "All saved unfinished instances belong to frozen R0 paired23 direct policies and never reached a routing decision at their actual final destination within the observed horizon. Their repeated off-destination node decisions remain delegated to the original model. The destination-only rule does not intervene there. This is a bounded-horizon description, not proof of infinite starvation or a newly tuned repair."}
    with (root / "remaining_tasks_diagnostic.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=2))


if __name__ == "__main__":
    main()
