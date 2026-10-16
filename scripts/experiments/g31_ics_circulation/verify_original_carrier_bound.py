"""Independent offline numerical check of a saved fixed-carrier FIFO bound.

Uses bitset transitive closure and exact prefix-choice knapsack. It neither
imports the original analyzer nor constructs a native simulation session.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError("carrier_bound_review:" + reason)


def verify(directory):
    directory = Path(directory).resolve()
    receipt_path, analysis_path = directory / "receipt.json", directory / "analysis.json.gz"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(sha(analysis_path) == receipt["analysis_sha256"], "analysis_hash")
    analysis = json.loads(gzip.decompress(analysis_path.read_bytes()))
    input_path = Path(receipt["input_path"])
    require(sha(input_path) == receipt["input_sha256"], "input_hash")
    require(sha(directory / "analyzer.py") == receipt["analyzer_sha256"], "analyzer_archive_hash")
    data = json.loads(gzip.decompress(input_path.read_bytes()))
    require(analysis["input_sha256"] == receipt["input_sha256"] and
            analysis["analyzer_sha256"] == receipt["analyzer_sha256"], "analysis_receipt_identity")
    for key, value in analysis.items():
        if key not in {"loaders", "stages", "dp_tables"}:
            require(receipt.get(key) == value, "receipt_summary:" + key)

    nodes = sorted(row["node"] for row in data["node_contracts"])
    require(len(set(nodes)) == len(nodes), "duplicate_nodes")
    index = {node: i for i, node in enumerate(nodes)}
    capacities = {row["node"]: row["capacity"] for row in data["node_contracts"]}
    edges = {(row["from"], row["to"]): row["capacity"] for row in data["edge_contracts"]}
    require(len(edges) == len(data["edge_contracts"]), "duplicate_edges")
    # Different algorithm from the producer's per-stage breadth-first search.
    reachable = [1 << i for i in range(len(nodes))]
    positive_edges = set()
    for source, target, _, _ in data["edge_records"]:
        if edges[source, target] > 0 and capacities[source] > 0 and capacities[target] > 0:
            reachable[index[source]] |= 1 << index[target]
            positive_edges.add((source, target))
    for pivot in range(len(nodes)):
        for source in range(len(nodes)):
            if reachable[source] & (1 << pivot):
                reachable[source] |= reachable[pivot]

    def connected(source, target):
        return bool(reachable[index[source]] & (1 << index[target]))

    for key, witness in analysis["stages"].items():
        source, target = witness["source"], witness["target"]
        require(key == f"{source}->{target}", "stage_identity")
        require(witness["complete_reachable_set"] == [n for n in nodes if connected(source, n)] and
                witness["reachable"] is connected(source, target), "stage_reachability:" + key)
        path = witness["positive_path"]
        require((path is None and not connected(source, target)) or
                (isinstance(path, list) and path and path[0] == source and path[-1] == target and
                 all(pair in positive_edges for pair in zip(path, path[1:]))), "stage_path:" + key)

    jobs = data["jobs"]
    require(len({j["business_bag_id"] for j in jobs}) == len(jobs), "duplicate_jobs")
    require(len({(j["origin"], j["arrival"]) for j in jobs}) == len(jobs), "same_origin_arrival_tie")
    carriers = len(data["trays"])
    require(carriers > 0 and len({t["tray_id"] for t in data["trays"]}) == carriers, "carrier_identity")
    loaders, stage_keys = defaultdict(list), set()
    for job in jobs:
        sequence = [job["origin"], job["destination"]] if job["storage_node"] < 0 else [
            job["origin"], job["storage_node"], job["destination"]]
        stages = list(zip(sequence, sequence[1:]))
        stage_keys.update(f"{u}->{v}" for u, v in stages)
        loaders[job["origin"]].append((job["arrival"], job["business_bag_id"],
            all(connected(u, v) for u, v in stages), [f"{u}->{v}" for u, v in stages]))
    require(stage_keys == set(analysis["stages"]), "stage_denominator")
    saved_loaders = {row["origin"]: row for row in analysis["loaders"]}
    require(len(saved_loaders) == len(analysis["loaders"]) and set(saved_loaders) == set(loaders), "loader_denominator")
    choices, total_reachable, zero_bad = {}, 0, 0
    for origin, rows in sorted(loaders.items()):
        rows.sort()
        bad = good = 0
        possible, expected_rows = {0: 0}, []
        for arrival, identity, is_good, stages in rows:
            bad += not is_good
            good += is_good
            expected_rows.append({"business_bag_id": identity, "arrival": arrival,
                "mandatory_stages": stages, "reachable": is_good,
                "unreachable_through_prefix": bad, "reachable_through_prefix": good})
            if bad < carriers:
                possible[bad] = max(possible.get(bad, 0), good)
        require(saved_loaders[origin]["jobs_in_native_fifo_order"] == expected_rows, "loader_full_prefix:" + str(origin))
        rewards = [max((value for cost, value in possible.items() if cost <= budget), default=0)
                   for budget in range(carriers)]
        require(saved_loaders[origin]["reward_by_at_most_bad"] == rewards, "loader_rewards:" + str(origin))
        total_reachable += good
        zero_bad += possible[0]
        choices[origin] = possible

    frontier = {0: (0, {})}
    require(len(analysis["dp_tables"]) == len(choices), "dp_layer_denominator")
    for layer, (origin, options) in enumerate(sorted(choices.items())):
        following = {}
        for used, (count, allocation) in frontier.items():
            for consumed, gain in options.items():
                budget = used + consumed
                if budget < carriers and count + gain > following.get(budget, (-1, {}))[0]:
                    following[budget] = count + gain, {**allocation, str(origin): consumed}
        frontier = following
        best_by_budget = [max(count for used, (count, _) in frontier.items() if used <= budget)
                          for budget in range(carriers)]
        require(analysis["dp_tables"][layer] == {"through_origin": origin,
            "max_reachable_by_bad_budget": best_by_budget}, "dp_full_layer:" + str(origin))
    upper_bound, allocation = max(frontier.values(), key=lambda pair: pair[0])
    require((len(jobs), carriers, total_reachable, zero_bad, upper_bound) == tuple(analysis[k] for k in
        ("offered", "carriers", "topologically_reachable", "zero_unreachable_load_prefix_bound", "completion_upper_bound")), "summary_recalculation")

    return {"schema": "g31.independent_carrier_bound_review.v1", "status": "passed_independent_numerical_recalculation",
        "new_native_executions": 0, "producer_analyzer_imported": False,
        "method": "Bitset all-pairs positive-capacity transitive closure and exact physical-loader-prefix knapsack.",
        "evidence": {str(p): sha(p) for p in (receipt_path, analysis_path, directory / "analyzer.py", input_path)},
        "input_sha256": receipt["input_sha256"], "analyzer_sha256": receipt["analyzer_sha256"],
        "checked_stages": len(stage_keys), "checked_loader_prefix_rows": len(jobs),
        "checked_dp_layers": len(choices), "carriers": carriers, "topologically_reachable": total_reachable,
        "zero_unreachable_load_prefix_bound": zero_bad, "completion_upper_bound": upper_bound,
        "one_relaxed_bad_allocation": allocation, "same_origin_arrival_tie_groups": 0,
        "physical_source_review": {"status": "read_only_conditional_review",
            "facts": ["Loaded leg failure retains tray.job and quarantines the loaded tray.",
                "Empty recovery rejects tray.job>=0; only destination unload followed by hold completion clears tray.job.",
                "Each actual arrival immediately runs loading; this input has no equal-arrival pairs per origin.",
                "At the last counted completion at least its carrier has not been permanently trapped; at most N-1 permanently unreachable loads precede it."],
            "counterexample_conditions": ["A loaded job can release its tray before required destination completion.",
                "A later same-origin job can bypass an earlier released FIFO head, including unproved equal-arrival event order.",
                "The fixed positive-capacity graph or mandatory service goals are enlarged or changed.",
                "New trays are admitted or existing carriers are omitted from the denominator." ]},
        "online_use": False, "realizable_schedule_proved": False, "strict_protection_proved": False,
        "scope": "Only the pinned original1x fixed-contract input. No inference for different ties,2x,capacity/body models,or changed admission rules."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.evidence)
    physical = args.native_source / "cpp/ics_core/runtime/circulation_runtime_impl.hpp"
    report["physical_source_review"]["archived_source"] = {str(physical.resolve()): sha(physical)}
    report["verifier_sha256"] = sha(__file__)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.output / "verifier.py")
    (args.output / "review.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "checked_stages", "checked_loader_prefix_rows", "zero_unreachable_load_prefix_bound", "completion_upper_bound")}))


if __name__ == "__main__":
    main()
