"""Read-only offline diagnosis of the completed two-arm Storage experiment."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda name: json.load(gzip.open(args.campaign/(name+".json.gz"), "rt", encoding="utf-8"))
    data = read("input"); raw = {arm: read(arm) for arm in ("control", "candidate")}
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    target, beneficiary = "projected:1x:0", "projected:1x:2"
    arms = {}
    for arm, value in raw.items():
        result = value["result"]
        receipts = result["receipts"]
        stages = [r for r in receipts if r["business_bag_id"] in (target, beneficiary)
            and r["event"] in ("STORAGE_ENTER", "STORAGE_RELEASE", "LEG_START", "EDGE_ENTER", "EDGE_EXIT")]
        later = [r for r in stages if r["business_bag_id"] == beneficiary and r["time"] >= jobs[beneficiary]["storage_release_at"]]
        occupancy = {node["node"]: [t for t in result["trays"] if t["node"] == node["node"] and t["edge_to"] < 0]
            for node in data["node_contracts"] if node["node"] in (28, 29, 112, 53)}
        arms[arm] = {"reached_common_horizon": result["advance"]["horizon_complete"] and result["physical_clock"] == 22200.,
            "population": result["population"], "target_stages": stages, "beneficiary_post_release_edge_count": sum(r["event"] == "EDGE_ENTER" for r in later),
            "beneficiary_post_release_path": [r["from"] for r in later if r["event"] == "EDGE_ENTER"] + ([later[-1]["to"]] if later and later[-1]["event"] == "EDGE_EXIT" else []),
            "final_node_occupants": occupancy,
            "business_outcomes": [j for j in result["jobs"] if j["business_bag_id"] in (target, beneficiary)],
            "last_bag13_waits": [r for r in receipts if r["business_bag_id"] == "projected:1x:13" and r["event"] == "RESOURCE_WAIT"][-5:]}
    report = {"schema": "g31.original_tie_negative_offline_diagnosis.v1", "scope": "saved raw receipts and final occupancy only; no native replay or policy input",
        "source_sha256": {str(args.campaign/(name+".json.gz")): hashlib.sha256((args.campaign/(name+".json.gz")).read_bytes()).hexdigest()
            for name in ("input", "control", "candidate")}, "arms": arms,
        "node_contracts": [n for n in data["node_contracts"] if n["node"] in (28, 29, 112, 53)],
        "node_records": [n for n in data["node_records"] if n[0] in (28, 29, 112, 53)],
        "conclusions": ["Candidate changes actual Storage release order: bag2 starts storage_out26 before bag0 storage_out27; control is the reverse.",
            "Candidate bag2 departs53 at19500.001 and completes13 edges to28 by19721.791999999998; control never departs53.",
            "Candidate final28 has earlier bag13 and later bag2. Its only outgoing node29 has4 parked loaded trays, equal declared capacity4. No remaining in-flight tray can free that receiving capacity.",
            "Both arms have0 completed jobs atH22200; no completed-job gain and strict unfinished-job protection remain unknown.",
            "The entry-order intervention does produce intermediate progress, but the preregistered completion mechanism was not demonstrated. Downstream occupancy/FIFO remains blocking; no fabricated zero-regression from unfinished outcomes."],
        "exact_remote_committed_successors_certified": False,
        "limit": "Final occupancy and recorded waits support downstream blocking. Exact hidden queues/commit successors are not reconstructed or inferred from missing receipts."}
    if args.output.exists(): raise ValueError("diagnosis:immutable_output_exists")
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "paths": {a: r["beneficiary_post_release_path"] for a, r in arms.items()}}, indent=2))


if __name__ == "__main__": main()
