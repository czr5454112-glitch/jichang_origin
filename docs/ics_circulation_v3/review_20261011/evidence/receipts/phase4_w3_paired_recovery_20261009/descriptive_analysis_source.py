"""Descriptive paired tables only; never fits, selects models or simulates."""
from collections import Counter, defaultdict
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
import types

import numpy as np

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write("\n")


def check_stage(output,stage):
    protocol=read(output/"protocol.json")
    for name,expected in protocol["source_sha256"].items():
        if sha(output/"source_snapshot"/name)!=expected:
            raise ValueError("Frozen source archive mismatch: "+name)
    folder=output/stage
    manifest=read(folder/"stage_manifest.json")
    if manifest["protocol_sha256"]!=sha(output/"protocol.json") or manifest["source_changed_during_run"] is not False:
        raise ValueError("Stage source/protocol integrity failure")
    files={p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if files!=set(manifest["files_sha256"])|{"stage_manifest.json"}:
        raise ValueError("Stage file set changed")
    for name,expected in manifest["files_sha256"].items():
        if sha(folder/name)!=expected:
            raise ValueError("Stage artifact checksum failure: "+name)
    return read(folder/"summary.json")


def load_frozen_physics(output):
    name="_ics_recovery_analysis_frozen"
    package=types.ModuleType(name)
    package.__path__=[str((output/"source_snapshot").resolve())]
    sys.modules[name]=package
    original=sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode=True
        model=importlib.import_module(name+".model")
        runtime=importlib.import_module(name+".runtime")
    finally:
        sys.dont_write_bytecode=original
    for key in ("Bag","Edge","Leg","Network","Node","RouteCandidate","Snapshot","Tray"):
        globals()[key]=getattr(model,key)
    globals()["ExecutionValidator"]=runtime.ExecutionValidator


def role_value_record(label):
    state = label["state"]
    minimal = Snapshot(state["now"], Network({n: Node(**v) for n,v in state["network"]["nodes"].items()},
        {e: Edge(**v) for e,v in state["network"]["edges"].items()}),
        {t: Tray(**v) for t,v in state["trays"].items()}, {b: Bag(**v) for b,v in state["bags"].items()})
    prefixes = []
    for proposal in label["proposals"]:
        candidate = RouteCandidate(**{**proposal, "legs": tuple(Leg(**leg) for leg in proposal["legs"])})
        prefix = ExecutionValidator._safe_prefix(minimal, candidate)
        prefixes.append((tuple((l.edge_id,l.depart,l.arrive) for l in prefix.legs), prefix.unload_complete,
                         prefix.usable_at,prefix.destination_node,prefix.prefix_only,prefix.continuation_destination))
    count = label["candidate_count"]
    if count:
        cost = np.asarray(label["paired_costs"])
        means = cost.mean(axis=(0,2))
        def classes(values):
            representatives = []
            for value in values:
                if not any(np.allclose(value, old, rtol=0, atol=1e-9) for old in representatives):
                    representatives.append(value)
            return len(representatives)
        value_classes = classes(means)
        vector_classes = classes([cost[:,c,:] for c in range(count)])
        value_range = float(means.max()-means.min())
    else:
        value_classes, vector_classes, value_range = 0, 0, None
    return {"identity":label["identity"],"node":label["source_node"],"role":label["role"],
        "normal_action_count":count,"physical_prefix_distinct":len(set(prefixes)),
        "mean_value_classes_tolerance_1e_minus9":value_classes,"paired_cost_vector_classes_tolerance_1e_minus9":vector_classes,
        "mean_value_range":value_range}


def main():
    output = Path(sys.argv[1])
    r0, r1, evaluation = [check_stage(output, s) for s in ("r0", "r1", "evaluation")]
    for owner,expected in read(output/"r1/stage_protocol.json")["unit_manifest_sha256"].items():
        if sha(output/"r1_units"/owner/"stage_manifest.json")!=expected:
            raise ValueError("Recovered unit manifest changed: "+owner)
        check_stage(output,"r1_units/"+owner)
    load_frozen_physics(output)
    records = evaluation["deployment_metrics"]
    lookup = {(r["stream"], r["realization"], r["policy"]): r for r in records}
    if len(lookup) != len(records):
        raise ValueError("Duplicate deployment identity")
    timed_boundaries = {}
    for row in records:
        if row["status"] != "completed_run":
            continue
        episode = output/"evaluation"/(row["stream"]+"__"+row["realization"])
        key = (row["stream"],row["realization"])
        if key not in timed_boundaries:
            timed_boundaries[key] = {b["time"]:b for b in read(episode/"timed.json")["boundaries"]}
        reference = timed_boundaries[key]
        boundaries = read(episode/(row["policy"]+".json"))["boundaries"]
        row["broad_snapshot_hash_differences"] = sum(b["state_sha256"]!=reference[b["time"]]["state_sha256"] for b in boundaries)
        row["completed_or_visible_bag_set_differences"] = sum((b["completed"],b["visible_bags"])!=(reference[b["time"]]["completed"],reference[b["time"]]["visible_bags"]) for b in boundaries)
        row["matched_boundary_denominator"] = len(boundaries)
    groups = defaultdict(list)
    for row in records:
        groups[("nominal" if row["realization"] == "nominal" else "stress_family", row["policy"])].append(row)
    tables = []
    for (realization, policy), rows in sorted(groups.items()):
        paired = []
        for row in rows:
            timed = lookup[(row["stream"], row["realization"], "timed")]
            if row["status"] == timed["status"] == "completed_run":
                paired.append(row["total_cost"] - timed["total_cost"])
        good = [r for r in rows if r["status"] == "completed_run"]
        tables.append({"realization": realization, "policy": policy, "scheduled_episodes": len(rows),
            "successful_episodes": len(good), "scheduled_bags": sum(r["scheduled_bags"] for r in rows),
            "completed_bags": sum(r["completed"] or 0 for r in rows),
            "total_cost_sum_successes_only": sum(r["total_cost"] for r in good),
            "paired_timed_denominator": len(paired), "mean_cost_delta_vs_timed": sum(paired)/len(paired) if paired else None,
            "wins_ties_losses_vs_timed": [sum(d < -1e-9 for d in paired), sum(abs(d) <= 1e-9 for d in paired), sum(d > 1e-9 for d in paired)],
            "runtime_cpu_seconds": sum(r["cpu_seconds"] for r in rows),
            "candidate_vectors": sum(r.get("candidate_feature_vectors", 0) for r in rows),
            "outside_training_range_vectors": sum(r.get("out_of_range_vectors", 0) for r in rows),
            "broad_snapshot_hash_differences":sum(r.get("broad_snapshot_hash_differences",0) for r in rows),
            "completed_or_visible_bag_set_differences":sum(r.get("completed_or_visible_bag_set_differences",0) for r in rows),
            "matched_boundary_denominator":sum(r.get("matched_boundary_denominator",0) for r in rows),
            "on_time_bags": sum(r.get("on_time", 0) for r in rows)})
    recovery = []
    for row in records:
        if not row["policy"].startswith("r1__"):
            continue
        baseline = lookup[(row["stream"], row["realization"], row["policy"].replace("r1__", "r0__", 1))]
        recovery.append({"stream": row["stream"], "realization": row["realization"], "policy": row["policy"],
            "before_status": baseline["status"], "after_status": row["status"],
            "before_cost": baseline["total_cost"], "after_cost": row["total_cost"],
            "delta": row["total_cost"] - baseline["total_cost"] if row["status"] == baseline["status"] == "completed_run" else None,
            "before_completed": baseline["completed"], "after_completed": row["completed"]})
    roles = Counter()
    for episode in r1["episodes"]:
        roles.update((s["source_node"], s["role"], s["groups"]) for s in episode["labels"])
    original = Path(read(output/"r0/input_manifest.json")["directory"])
    for name,expected in read(output/"r0/input_manifest.json")["files_sha256"].items():
        if sha(original/name)!=expected:
            raise ValueError("Original R0 artifact changed: "+name)
    original_summary = read(original/"summary.json")
    values = {"r0":[role_value_record(read(original/s["stress_file"])) for s in original_summary["samples"]],
              "r1":[role_value_record(read(path)) for path in sorted((output/"r1_units").glob("*/stream_*/label_*.json"))]}
    role_tables = []
    for stage, items in values.items():
        for node, role in sorted({(v["node"],v["role"]) for v in items}):
            selected = [v for v in items if (v["node"],v["role"]) == (node,role)]
            ranges = [v["mean_value_range"] for v in selected if v["mean_value_range"] is not None]
            role_tables.append({"stage":stage,"node":node,"role":role,"states":len(selected),
                "normal_actions":sum(v["normal_action_count"] for v in selected),
                "physical_prefix_distinct_sum":sum(v["physical_prefix_distinct"] for v in selected),
                "zero_mean_value_range_states":sum(v is not None and abs(v)<=1e-9 for v in ranges),
                "informative_mean_range_states":sum(v>1e-9 for v in ranges),
                "mean_value_range":sum(ranges)/len(ranges) if ranges else None,
                "max_value_range":max(ranges) if ranges else None})
    result = {"scope": "descriptive synthetic development; no model, seed, schema or hyperparameter selection",
        "input_manifests_sha256": {s: sha(output/s/"stage_manifest.json") for s in ("r0", "r1", "evaluation")},
        "r0_fits": r0["fits"], "r1_fits": r1["fits"], "deployment_runs": evaluation["deployment_runs"],
        "failures": evaluation["failures"], "policy_tables": tables, "all_matched_r0_r1_costs": recovery,
        "r1_label_accounting": {k: r1[k] for k in ("checkpoints", "candidate_rows", "collection_episodes", "requested_branches", "actual_branches", "cache_reused_branches", "recorded_collection_and_label_cpu_seconds_including_worker_processes")},
        "compute_accounting":{
            "r0_original_collection_and_nominal_stress_label_cpu_seconds":original_summary["cpu_seconds"],
            "r0_fit_cpu_seconds":sum(v["cpu_seconds"] for v in read(output/"r0/fit_history.json")),
            "r1_collection_cpu_seconds":sum(e["all_collection_attempt_cpu_seconds"] for e in r1["episodes"]),
            "r1_label_physical_and_cache_combined_cpu_seconds":sum(v["cpu_seconds"] for e in r1["episodes"] for v in e["labels"]),
            "r1_worker_completion_invocations_cpu_seconds":r1["worker_completion_invocations_process_cpu_seconds"],
            "r1_fit_cpu_seconds":r1["fit_cpu_seconds"],
            "evaluation_sum_episode_cpu_seconds":sum(r["cpu_seconds"] for r in records),
            "evaluation_sum_episode_wall_seconds":sum(r["wall_seconds"] for r in records),
            "peak_memory":None,"peak_memory_status":"not_measured","gpu_used":False,
            "limits":"Physical replay and cache-hit counts are separate; their CPU was not separately timed. Evaluation sums per-episode calls and excludes outer checkpoint assessment/serialization overhead. Shared-workstation timing is descriptive."},
        "r1_sample_roles_and_groups": [{"node": key[0], "role": key[1], "groups": key[2], "count": value} for key,value in sorted(roles.items())],
        "role_value_tables":role_tables,"all_role_value_records":values,
        "limits": ["31 inputs versus 23 increase trainable parameters from 801 to 1057; not pure semantics at fixed parameter count.",
            "R1 labels continue fixed timed policy, not the learned routing policy; improvement is one fixed-policy value recovery diagnostic.",
            "Own-policy R1 paired-direct and residual use different recovered rows; their cross-kind comparison does not isolate only the target definition.",
            "Role coverage and K4 action count do not imply informative ranking tasks. Flat-cost B states may pass precision gates trivially.",
            "Snapshot hashes include version and forecast/history records; hash differences are not an independent physical-trajectory distance. Coarse visible-task/completion differences are also incomplete state summaries.",
            "Stress deployment uses the same perturbation family, not the same state-conditional distribution as labels; nominal collection omits pressure-state recovery.",
            "A repeated future tape is one physical replay reused across requested Monte Carlo slots, not additional independent evidence.",
            "Complete unit manifests are resumable. Partial-unit re-collection checkpoint SHA includes volatile generator timing and can reject an otherwise equivalent retry; no partial retry was assumed here.",
            "No independent airport-day population, confidence interval or general superiority claim."]}
    save(output / "descriptive_analysis.json", result)
    archive = output/"descriptive_analysis_source.py"
    with archive.open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
    print(json.dumps({"tables":len(tables), "matched_before_after":len(recovery), "deployment_runs":evaluation["deployment_runs"]}))


if __name__ == "__main__":
    main()
