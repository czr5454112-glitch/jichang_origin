"""Read existing destination-role raw labels; never regenerate a branch."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean
import json


WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}
TOL = 1e-9


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    root = Path(__file__).resolve().parent
    master = Path(read(root / "input_manifest.json")["master_directory"])
    rows = read(master / "r1/rows_by_owner.json")
    row_groups = defaultdict(list)
    for values in rows.values():
        for row in values:
            if row["role"] == "arrival_at_destination":
                row_groups[row["source_group"]].append(row)
    counts, raw_deltas, files, groups, examples = Counter(), Counter(), {}, [], []
    for episode in read(master / "r1/summary.json")["episodes"]:
        for ordinal, record in enumerate(episode["labels"]):
            if record["role"] != "arrival_at_destination":
                continue
            path = master / "r1_units" / episode["owner"] / episode["stream"] / f"label_{ordinal:02d}.json"
            label = read(path)
            files[str(path.relative_to(master)).replace("\\", "/")] = sha256(path.read_bytes()).hexdigest()
            assert label["identity"] == record["identity"] and not label["failures"]
            assert label["groups"] == 4 and label["futures_per_group"] == 8 and label["horizon_ticks"] == 20
            state, candidates = label["state"], label["proposals"]
            baseline = candidates[0]
            bag, tray = state["bags"][baseline["bag_id"]], state["trays"][baseline["tray_id"]]
            assert tray["node"] == bag["destination"] == label["source_node"]
            assert baseline["legs"] == [] and baseline["prefix_only"] is False
            assert baseline["unload_complete"] == state["now"] + state["module"]["unload_ticks"]
            hold = state["module"]["hold_by_node"].get(tray["node"], 0)
            assert baseline["usable_at"] == baseline["unload_complete"] + hold
            assert label["features_physical"][0]["prefix_completes_delivery"] == 1.
            assert all(candidate["legs"] for candidate in candidates[1:])
            raw = {(r["group"], r["candidate"], r["future_index"]): r for r in label["raw_branches"]}
            deltas = []
            for index in range(1, len(candidates)):
                branch_pairs = [(raw[g, index, f], raw[g, 0, f]) for g in range(4) for f in range(8)]
                assert all(not a["failed"] and not b["failed"] and a["future_sha256"] == b["future_sha256"] for a, b in branch_pairs)
                differences = [a["total_cost"] - b["total_cost"] for a, b in branch_pairs]
                row = next(r for r in row_groups[label["identity"]] if r["normal_ordinal"] == index)
                assert abs(mean(differences) - row["delta_mean"]) < TOL
                assert all(abs(a - b) < TOL for a, b in zip(differences, row["paired_deltas"]))
                raw_deltas.update("cycle_better" if v < -TOL else "cycle_worse" if v > TOL else "equal" for v in differences)
                deltas.append(mean(differences))
                examples.append({"identity": label["identity"], "owner": episode["owner"], "stream": episode["stream"],
                    "label_path": str(path.relative_to(master)).replace("\\", "/"), "candidate_index": index,
                    "baseline_proposal": baseline, "cycle_proposal": candidates[index], "mean_cost_delta": mean(differences),
                    "weighted_component_mean_deltas": {key: mean(WEIGHTS[key] * (a["cost_components"][key] - b["cost_components"][key]) for a, b in branch_pairs) for key in WEIGHTS},
                    "candidate_better_equal_worse": {name: sum((v < -TOL if name == "better" else v > TOL if name == "worse" else abs(v) <= TOL) for v in differences) for name in ("better", "equal", "worse")},
                    "first_future_pair": {"candidate": branch_pairs[0][0], "unload": branch_pairs[0][1]}})
            counts.update(["unload_mean_optimal" if min(deltas) >= -TOL else "cycle_mean_strictly_better"])
            counts.update(["all_candidate_means_equal" if all(abs(v) <= TOL for v in deltas) else "candidate_means_differ"])
            groups.append({"identity": label["identity"], "owner": episode["owner"], "stream": episode["stream"],
                           "node": tray["node"], "future_count": 32, "nonbaseline_mean_deltas": deltas})
    assert len(groups) == len(row_groups) == 208
    deployed = defaultdict(Counter)
    for metrics in read(root / "evaluation/summary.json")["deployment_metrics"]:
        if not metrics["policy"].startswith("shared__"):
            continue
        folder = root / "evaluation" / (metrics["stream"] + "__" + metrics["realization"])
        record = read(folder / (metrics["policy"] + ".json"))
        for call in record["learned_feature_history"]:
            if call["role"] != "arrival_at_destination":
                continue
            selected = call["features"][call["chosen_index"]]
            assert selected["current_at_destination"] == 1.
            category = "completes_delivery" if selected["prefix_completes_delivery"] == 1. else "leaves_destination"
            deployed[metrics["policy"]][category] += 1
    examples.sort(key=lambda r: (r["mean_cost_delta"], r["identity"], r["candidate_index"]))
    result = {"scope": "Retrospective analysis of existing R1 labels and shared deployments; no replay, fit, new labels, or fresh confirmation.",
        "label_manifest_sha256": sha256((master / "r1/stage_manifest.json").read_bytes()).hexdigest(),
        "destination_role_owner_checkpoint_count": len(groups), "candidate_rows": sum(len(v) for v in row_groups.values()),
        "nonbaseline_candidate_rows": len(examples), "group_counts": dict(counts), "candidate_future_comparisons": dict(raw_deltas),
        "all_208_baselines_verified_no_legs_and_complete_delivery": True,
        "all_208_have_4_groups_times_8_common_futures": True,
        "unit_warning": "208 owner-specific checkpoints include repeated physical situations from different model collectors; 40 is not an independent confirmation denominator. The 19,968 candidate/future comparisons include correlated futures, owners and conditional witnesses sharing a physical prefix.",
        "groups": groups, "source_label_sha256": files,
        "post_hoc_counterexamples": {"strongest_cycle_benefit": examples[0], "strongest_cycle_harm": examples[-1]},
        "shared_deployment_destination_role_choices": {k: dict(v) for k, v in sorted(deployed.items())}}
    with (root / "destination_action_evidence.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"groups", "source_label_sha256", "post_hoc_counterexamples"}}, indent=2))


if __name__ == "__main__":
    main()
