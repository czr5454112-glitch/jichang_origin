"""Declared R0 role coverage and common-future labels; no fitting or held-out claim."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import mean
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory
from .label_stability import sustained_scenes
from .phase4_control import ControlSpec
from .role_coverage import RoleQuota, collect_role_decisions, label_role_decision, sample_artifact


SOURCES = ("run_role_coverage.py", "role_coverage.py", "role_features.py", "nonlinear_learning.py",
           "label_stability.py", "feedback_scenarios.py", "phase4_control.py", "runtime.py", "model.py",
           "prebalance.py", "learning.py", "evaluation.py", "conditional_evaluation.py", "routing.py",
           "routing_reference.py", "experiment_protocol.py")
SPEC = ControlSpec(routing="timed", predictive=True, planning_horizon=20, slow_period=2,
                   route_mode="next_edge", candidate_count=4, expansion_limit=2000)
QUOTA = RoleQuota(max_samples=9, selection_rule="node_role_round_robin")


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def noise_record(label):
    """Nested-future and held-group diagnostics on complete paired costs only."""
    values = label["paired_costs"]
    if label["failures"] or not label["candidate_count"]:
        return {"eligible": False, "reason": "failed_or_zero_candidate", "identity": label["identity"]}
    if len(values) != 4 or any(len(r) != 8 for group in values for r in group):
        raise ValueError("noise gate requires the declared four groups of eight")
    count = label["candidate_count"]
    full = [mean(values[g][c][f] for g in range(4) for f in range(8)) for c in range(count)]
    nested, cross, two_groups = [], [], []
    for g in range(4):
        two = [mean(values[g][c][:2]) for c in range(count)]
        eight = [mean(values[g][c]) for c in range(count)]
        chosen_two = min(range(count), key=lambda c: (two[c], c))
        chosen_eight = min(range(count), key=lambda c: (eight[c], c))
        other = [mean(values[j][c][f] for j in range(4) if j != g for f in range(8)) for c in range(count)]
        nested.append({"group": g, "chosen_first2": chosen_two, "chosen_first8": chosen_eight,
                       "optimal_agreement": eight[chosen_two] <= min(eight) + 1e-9,
                       "other_groups_regret": other[chosen_two] - min(other)})
        cross.append({"group": g, "chosen": chosen_eight, "other_groups_regret": other[chosen_eight] - min(other)})
    for training, heldout in (((0, 1), (2, 3)), ((2, 3), (0, 1))):
        estimate = [mean(values[g][c][f] for g in training for f in range(8)) for c in range(count)]
        other = [mean(values[g][c][f] for g in heldout for f in range(8)) for c in range(count)]
        chosen = min(range(count), key=lambda c: (estimate[c], c))
        two_groups.append({"choosing_groups": training, "heldout_groups": heldout, "chosen": chosen,
                           "all4_optimal_agreement": full[chosen] <= min(full) + 1e-9,
                           "heldout_regret": other[chosen] - min(other)})
    return {"identity": label["identity"], "source_node": label["source_node"], "role": label["role"],
            "eligible": True, "candidate_count": count, "all4_cost_means": full,
            "nested_future2_vs8": nested, "group8_leave_group_out": cross, "two_groups_vs4": two_groups}


def noise_gate(records):
    output = {}
    for group, selected in (("all_states", [r for r in records if r["eligible"]]),
                             ("B_states", [r for r in records if r["eligible"] and r["source_node"] == "B"])):
        nested = [x for r in selected for x in r["nested_future2_vs8"]]
        cross = [x for r in selected for x in r["group8_leave_group_out"]]
        halves = [x for r in selected for x in r["two_groups_vs4"]]
        if not selected:
            output[group] = {"sample_count": 0, "pass": False}
            continue
        row = {"sample_count": len(selected), "nested_decision_count": len(nested), "two_group_decision_count": len(halves),
               "nested2_vs8_optimal_agreement": mean(x["optimal_agreement"] for x in nested),
               "nested2_other_groups_mean_regret": mean(x["other_groups_regret"] for x in nested),
               "group8_other_groups_mean_regret": mean(x["other_groups_regret"] for x in cross),
               "two_groups_vs4_optimal_agreement": mean(x["all4_optimal_agreement"] for x in halves),
               "two_groups_heldout_mean_regret": mean(x["heldout_regret"] for x in halves)}
        row["pass"] = (row["nested2_vs8_optimal_agreement"] >= .95
                       and row["two_groups_vs4_optimal_agreement"] >= .95
                       and row["nested2_other_groups_mean_regret"] <= .1
                       and row["group8_other_groups_mean_regret"] <= .1
                       and row["two_groups_heldout_mean_regret"] <= .1)
        output[group] = row
    output["all_required_groups_pass"] = all(output[g]["pass"] for g in ("all_states", "B_states"))
    output["recommended_R1_groups"] = 2 if output["all_required_groups_pass"] else 4
    output["automatic_R1_launch"] = False
    return output


def run(output, *, labels=False):
    output = create_output_directory(output)
    source = Path(__file__).parent
    paths = [source / name for name in SOURCES] + [source.parents[2] / "tests/test_ics_circulation_v3_role_coverage.py"]
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in paths}
    (output / "source_snapshot").mkdir()
    for path in paths:
        shutil.copyfile(path, output / "source_snapshot" / path.name)
    protocol = {"schema": "ics_v3_role_coverage_R0_v1", "spec": asdict(SPEC), "quota": asdict(QUOTA),
                "labels_enabled": labels, "stress_groups": 4, "stress_futures_per_group": 8,
                "nominal_groups": 1, "nominal_futures_per_group": 1, "label_horizon_ticks": 20,
                "source_sha256": hashes, "sampling": "actual generation/selector position; first attempt per cell including zero; round-robin node/role then time band; no labels/outcomes used",
                "checkpoint": "actual physical engine checkpoint plus exact loaded-route cursor and already-generated options; no reconstruction from Snapshot",
                "R1_gate_predeclared": {"all_states_and_B_subgroup_required": True,
                    "nested_future2_vs8_optimal_agreement_min": .95, "two_groups_vs4_optimal_agreement_min": .95,
                    "nested2_other_groups_regret_max": .1, "group8_other_groups_regret_max": .1,
                    "two_groups_heldout_regret_max": .1, "if_any_fail_R1_groups": 4,
                    "if_all_pass_R1_groups": 2, "futures_per_group": 8},
                "scope": "four reused constructed development streams; fixed timed continuation; not independent airport days, not held-out confirmation",
                "future_law": "Stress only: existing declared independent cancellation 1/8, OD reversal 1/8, jitter {-2,0,2}; unobserved task tape only; fixed publication schedule. Nominal is separately recorded.",
                "features": "same candidate/checkpoint labels serve observable base23 and physical31; no hidden future inputs",
                "limitations": ["Empty C/G strata are reported, never filled with synthetic checkpoints.",
                    "First attempts with zero candidates consume quota and remain unlabelable; all attempts stay in the opportunity denominator.",
                    "Label groups/candidates/checkpoints from one trajectory are correlated; noise summaries are descriptive conditional Monte Carlo diagnostics.",
                    "The copied finite continuation dispatcher is tested against the unchanged runtime; all physics, FIFO, authorizations and candidate generator remain shared.",
                    "Shared-machine wall/CPU time is recorded, not used as a production performance claim."]}
    save(output / "protocol.json", protocol)
    episodes, samples, failures, noises = [], [], [], []
    started, cpu = perf_counter(), process_time()
    for scene in sustained_scenes():
        collection = collect_role_decisions(scene, SPEC, quota=QUOTA, source_group="R0_timed")
        episode_name = scene.name + "_episode.json"
        episode = {"scene": scene.name, "metadata": collection.metadata,
                   "bag_count": len(scene.initial.bags) + len(scene.future_bags),
                   "completed_count": len(collection.episode_result.completed), "total_cost": collection.episode_result.total_cost,
                   "opportunities": len(collection.opportunities), "sample_count": len(collection.samples), "file": episode_name}
        episodes.append(episode)
        save(output / episode_name, {"scene": scene.name, "initial": asdict(scene.initial),
            "nominal_future_driver_only": [asdict(b) for b in scene.future_bags],
            "forecast_publications": [asdict(f) for f in scene.forecasts], "metadata": collection.metadata,
            "opportunities": collection.opportunities, "result": asdict(collection.episode_result), "contract": collection.contract})
        for sample in collection.samples:
            stem = sample["identity"].replace(":", "_")
            save(output / (stem + "_sample.json"), sample_artifact(sample))
            row = {"identity": sample["identity"], "source_node": sample["source_node"], "role": sample["role"],
                   "band": sample["band"], "time": sample["time"], "candidate_count": len(sample["pool"]),
                   "checkpoint_sha256": sample["checkpoint_sha256"], "sample_file": stem + "_sample.json"}
            if labels:
                for regime in ("nominal", "stress"):
                    label = label_role_decision(sample, scene.future_bags, regime=regime)
                    filename = stem + "_" + regime + ".json"
                    save(output / filename, label)
                    row[regime + "_file"] = filename
                    row[regime + "_branches"] = len(label["raw_branches"])
                    failures.extend({"sample": sample["identity"], "regime": regime, **f} for f in label["failures"])
                    if regime == "stress":
                        noises.append(noise_record(label))
                print(json.dumps({"sample": sample["identity"], "role": sample["role"],
                                  "candidates": len(sample["pool"]), "failed_branches": len(failures)}), flush=True)
            samples.append(row)
    summary = {"episodes": episodes, "samples": samples, "sample_count": len(samples),
               "opportunity_count": sum(e["opportunities"] for e in episodes),
               "stress_branches": sum(r.get("stress_branches", 0) for r in samples),
               "nominal_branches": sum(r.get("nominal_branches", 0) for r in samples), "failures": failures,
               "sampled_nodes": dict(Counter(s["source_node"] for s in samples)),
               "source_sha256": hashes, "source_changed_during_run": any(sha256(p.read_bytes()).hexdigest() != hashes[p.name] for p in paths),
               "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu,
               "noise_gate": noise_gate(noises) if labels else None}
    save(output / "noise_diagnostics.json", {"records": noises, "gate": summary["noise_gate"]})
    save(output / "summary.json", summary)
    manifest = {str(p.relative_to(output)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*")) if p.is_file()}
    save(output / "manifest.json", manifest)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--labels", action="store_true")
    args = parser.parse_args()
    summary = run(args.output, labels=args.labels)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"episodes", "samples", "source_sha256"}}, indent=2))
    raise SystemExit(int(bool(summary["failures"]) or summary["source_changed_during_run"]))
