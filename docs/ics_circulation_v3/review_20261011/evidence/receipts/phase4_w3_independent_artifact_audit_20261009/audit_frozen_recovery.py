"""Content audit after all own-policy and shared-union stages are frozen.

No fitting, deployment or label generation is performed. Missing frozen
stages are a hard precondition failure, never a reason to omit their rows.
"""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3 import run_paired_recovery as main
from scripts.experiments.ics_circulation_v3 import run_shared_recovery as shared
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
from audit_candidate_coverage import snapshot, candidate, read, digest

OUT = Path(__file__).resolve().parent
BASE = ROOT / "outputs/experiments/ics_circulation_v3"


def run():
    target = OUT / "frozen_recovery_audit.json"
    if target.exists():
        raise ValueError("audit result must be new")
    master = BASE / "phase4_w3_paired_recovery_20261009"
    union = BASE / "phase4_w3_shared_recovery_20261009"
    # Historical snapshots are authoritative. A later documentation-only
    # source change must not cause any frozen experiment to be rewritten.
    def sha(path):
        return sha256(path.read_bytes()).hexdigest()
    def stage(folder, name):
        local = folder / name
        manifest = read(local / "stage_manifest.json")
        if manifest["source_changed_during_run"] is not False or manifest["protocol_sha256"] != sha(folder / "protocol.json"):
            raise ValueError("frozen stage protocol/unchanged-source assertion mismatch")
        if "input_manifest_sha256" in manifest and manifest["input_manifest_sha256"] != sha(folder / "input_manifest.json"):
            raise ValueError("frozen shared input manifest differs")
        files = {p.relative_to(local).as_posix() for p in local.rglob("*") if p.is_file()}
        if files != set(manifest["files_sha256"]) | {"stage_manifest.json"}:
            raise ValueError("frozen stage file set differs")
        if any(sha(local / key) != expected for key, expected in manifest["files_sha256"].items()):
            raise ValueError("frozen stage artifact hash differs")
        return read(local / "summary.json")
    stages = {name: stage(master, name) for name in ("r0", "r1", "evaluation")}
    union_stages = {name: stage(union, name) for name in ("fit", "evaluation")}
    source_current_differences = []
    for folder in (master, union):
        recorded = read(folder / "protocol.json")["source_sha256"]
        for name, expected in recorded.items():
            if sha(folder / "source_snapshot" / name) != expected:
                raise ValueError("recorded source snapshot hash differs")
            current = ROOT / "scripts/experiments/ics_circulation_v3" / name
            if sha(current) != expected:
                source_current_differences.append({"experiment": folder.name, "file": name,
                                                  "frozen": expected, "current": sha(current)})
            if name in {"runtime.py", "model.py"} and sha(current) != expected:
                raise ValueError("owner revalidation requires the exact frozen physics implementation")
    r0_inputs = read(master / "r0/input_manifest.json")
    r0_source = Path(r0_inputs["directory"])
    if sha(r0_source / "manifest.json") != r0_inputs["manifest_sha256"] or any(
            sha(r0_source / key) != expected for key, expected in r0_inputs["files_sha256"].items()):
        raise ValueError("original R0 label inputs differ")
    union_inputs = read(union / "input_manifest.json")
    if any(sha(master / key) != expected for key, expected in union_inputs["files_sha256"].items()):
        raise ValueError("shared union original master inputs differ")
    checks, classes = [], []
    def check(name, condition, **context):
        checks.append({"name": name, "passed": bool(condition), **context})
    r0 = read(master / "r0/rows.json")
    recovered = read(master / "r1/rows_by_owner.json")
    owner_set = set(main.recovery_owners())
    check("all_24_recovery_owners", set(recovered) == owner_set)
    check("all_original_fit_and_episode_counts", stages["r0"]["fits"] == 48 and stages["r1"]["fits"] == 24
          and stages["r1"]["collection_episodes"] == 72 and union_stages["fit"]["fits"] == 24)
    def check_fits(folder, phase, expected_count, expected_training):
        models = read(folder / "frozen_models.json")
        metadata = read(folder / "folds_and_bounds.json")
        check("complete_model_denominator", len(models) == len(metadata["folds"]) == expected_count, phase=phase)
        for name, value in models.items():
            fold = metadata["folds"][name]
            held, schema = fold["held_out_stream"], fold["schema"]
            train = expected_training(name, held)
            selected = [dict(r, features=r["features23" if schema == "paired23" else "features31"], split="train") for r in train]
            names = tuple(value["feature_names"])
            matrix = np.asarray([[r["features"][n] for n in names] for r in selected])
            scale = matrix.std(axis=0)
            scale[scale < 1e-9] = 1.
            expected_bounds = {n: {"minimum": float(matrix[:, i].min()), "maximum": float(matrix[:, i].max())}
                               for i, n in enumerate(names)}
            valid = (held not in {r["stream"] for r in train}
                and {r["stream"] for r in train} == set(main.PROTOCOL["streams"]) - {held}
                and fold["training_rows"] == len(train) and fold["training_rows_sha256"] == main.digest(selected)
                and value["center"] == matrix.mean(axis=0).tolist() and value["scale"] == scale.tolist()
                and metadata["bounds"][name] == expected_bounds
                and value["config"]["epochs"] == 400 and value["config"]["learning_rate"] == .01
                and value["config"]["l2"] == .001 and value["config"]["seed"] in (17, 29, 43))
            check("whole_stream_training_and_normalization_exact", valid, phase=phase, model=name)
    check_fits(master / "r0", "R0", 48, lambda name, held: [r for r in r0 if r["stream"] != held])
    check_fits(master / "r1", "R1_own", 24, lambda name, held: [r for r in r0 if r["stream"] != held] + recovered[name])
    corpora = read(union / "fit/training_rows_by_fold.json")
    for held in main.PROTOCOL["streams"]:
        expected = [r for r in r0 if r["stream"] != held]
        for kind in main.KINDS:
            for seed in main.SEEDS:
                expected += recovered[main.model_name(held, "physical31", kind, seed)]
        check("shared_union_preserves_every_original_owner_row_and_order", corpora[held] == expected, fold=held)
    check_fits(union / "fit", "R1_shared", 24, lambda name, held: corpora[held])
    requested = actual = reused = samples = 0
    roles, nodes, observed_roles = Counter(), Counter(), Counter()
    for owner in sorted(recovered):
        unit_folder = master / "r1_units" / owner
        unit = stage(master, "r1_units/" + owner)
        held = owner.split("__", 1)[0]
        check("owner_unit_complete_and_fold_isolated", unit["owner"] == owner and unit["held_out_stream"] == held
            and len(unit["episodes"]) == unit["collection_episodes"] == 3
            and {e["stream"] for e in unit["episodes"]} == set(main.PROTOCOL["streams"]) - {held}
            and read(unit_folder / "rows.json") == recovered[owner], owner=owner)
        check("shared_union_retains_original_owner_manifest_and_rows_hash",
            union_inputs["unit_manifests"][owner]["manifest_sha256"] == sha(unit_folder / "stage_manifest.json")
            and union_inputs["unit_manifests"][owner]["rows_sha256"] == sha(unit_folder / "rows.json"), owner=owner)
        rebuilt_rows = []
        for episode in unit["episodes"]:
            folder = unit_folder / episode["stream"]
            latest_attempt = sorted(folder.glob("collection_attempt_*.json"))[-1]
            collection = read(latest_attempt)
            for opportunity in collection["opportunities"]:
                observed_roles[opportunity["role"]] += 1
            for index, record in enumerate(episode["labels"]):
                raw_sample = read(folder / f"sample_{index:02d}.json")
                label = read(folder / f"label_{index:02d}.json")
                rebuilt_rows.extend(main.label_rows(label, episode["stream"], owner=owner))
                state = snapshot(label["state"])
                tray = state.trays[raw_sample["tray_id"]]
                bag = state.bags[tray.bag_id]
                role = "arrival_at_destination" if tray.node == bag.destination else "origin" if tray.node == bag.origin else "continuation"
                count = label["candidate_count"]
                check("sample_role_and_saved_causal_cursor_match_label", raw_sample["identity"] == label["identity"] == record["identity"]
                    and raw_sample["state"] == label["state"] and raw_sample["role"] == role == label["role"]
                    and raw_sample["source_node"] == tray.node == label["source_node"]
                    and raw_sample["normal_keys"] == label["actual_action_keys"]
                    and raw_sample["checkpoint_metadata"]["cursor"]["pending_tray_id"] == tray.tray_id,
                    sample=label["identity"])
                check("all_requested_branches_and_cache_accounted", label["requested_branches"] == len(label["raw_branches"])
                    == count * label["groups"] * 8 == label["actual_unique_branch_calls"] + label["cache_reused_branches"]
                    and label["cache_reused_branches"] == sum(b["cache_hit"] for b in label["raw_branches"])
                    and not label["failures"], sample=label["identity"])
                prefixes = []
                for raw in label["proposals"]:
                    action = candidate(raw)
                    check("sampled_action_owner_revalidation", ExecutionValidator().validate(state, action, route_mode="next_edge").accepted,
                          sample=label["identity"], candidate=action.candidate_id)
                    prefix = ExecutionValidator._safe_prefix(state, action)
                    end = state.network.edges[prefix.legs[-1].edge_id].target if prefix.legs else tray.node
                    prefixes.append(digest({"legs": [asdict(l) for l in prefix.legs], "end": end,
                        "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only}))
                vectors = [tuple(label["paired_costs"][g][c][f] for g in range(label["groups"]) for f in range(8)) for c in range(count)]
                classes.append({"owner": owner, "stream": episode["stream"], "identity": label["identity"], "node": tray.node,
                    "role": role, "revisit": raw_sample["revisit"], "candidate_count": count,
                    "actual_action_key_count": len(set(label["actual_action_keys"])), "immediate_prefix_count": len(set(prefixes)),
                    "exact_paired_cost_vector_classes": len(set(vectors)), "groups": label["groups"],
                    "future_draws_per_candidate": label["groups"] * 8})
                samples += 1
                roles[role] += 1
                nodes[tray.node] += 1
                requested += label["requested_branches"]
                actual += label["actual_unique_branch_calls"]
                reused += label["cache_reused_branches"]
        check("original_owner_rows_exactly_rebuilt_from_all_raw_labels", rebuilt_rows == recovered[owner], owner=owner)
    check("main_R1_complete_branch_and_sample_summary", samples == stages["r1"]["checkpoints"]
        and requested == stages["r1"]["requested_branches"] and actual == stages["r1"]["actual_branches"]
        and reused == stages["r1"]["cache_reused_branches"])
    controls, totals = [], {}
    public = BASE / "phase4_w3_public_rollout_20261009"
    for phase, folder, summary, expected_count, per_cell in (
            ("own", master / "evaluation", stages["evaluation"], 720, 20),
            ("shared", union / "evaluation", union_stages["evaluation"], 288, 8)):
        rows = summary["deployment_metrics"]
        keys = [(r["stream"], r["realization"], r["policy"]) for r in rows]
        cell_counts = Counter(k[:2] for k in keys)
        check("all_predeclared_deployment_rows_and_failures_retained", len(rows) == len(set(keys)) == expected_count
            and len(cell_counts) == 36 and set(cell_counts.values()) == {per_cell}
            and summary["scheduled_bag_denominator"] == sum(r["scheduled_bags"] for r in rows)
            and summary["completed_bags"] == sum(r["completed"] or 0 for r in rows)
            and summary["failures"] == [r for r in rows if r["status"] != "completed_run"], phase=phase)
        for (stream, realization) in cell_counts:
            saved = read(folder / (stream + "__" + realization) / "inputs.json")
            reference = read(public / f"{stream}__{realization}_inputs.json")
            equal = (saved["initial"] == reference["initial"] and saved["forecasts"] == reference["forecasts"]
                     and saved["horizon"] == reference["horizon"]
                     and saved["actual_tape_event_engine_only"] == reference["event_engine_only_tape"])
            check("deployment_same_initial_forecasts_and_actual_tape_as_public_reference", equal, phase=phase, stream=stream, realization=realization)
            for policy in ("baseline", "timed"):
                ours = read(folder / (stream + "__" + realization) / (policy + ".json"))
                theirs = read(public / f"{stream}__{realization}__{policy}.json")
                good = (ours["metrics"]["status"] == theirs["metrics"]["status"] == "completed_run"
                        and all(ours["result"][k] == theirs["result"][k] for k in
                            ("cost_components", "trace", "final_snapshot", "completed", "uncompleted_bag_ids"))
                        and ours["slow_trigger_times"] == theirs["slow_trigger_times"])
                check("control_full_physical_trace_cost_and_slow_phase_equal", good, phase=phase, stream=stream, realization=realization, policy=policy)
                controls.append(good)
        totals[phase] = {"episodes": len(rows), "failures": len(summary["failures"]), "scheduled_bags": summary["scheduled_bag_denominator"],
                         "completed_bags": summary["completed_bags"]}
    payload = {"scope": "all frozen R0/R1/shared data; zero new model fits or rollouts", "checks": len(checks),
        "passed": sum(r["passed"] for r in checks), "failed": [r for r in checks if not r["passed"]], "checks_detail": checks,
        "R1_samples": samples, "R1_roles": dict(roles), "R1_nodes": dict(nodes), "R1_all_opportunity_roles": dict(observed_roles),
        "R1_requested_branches": requested, "R1_actual_branch_calls": actual, "R1_cache_reused": reused,
        "physical_and_value_classes": classes, "control_comparisons": len(controls), "all_control_physics_equal": all(controls),
        "deployment_totals": totals,
        "frozen_source_snapshot_hashes_match_protocol": True,
        "current_source_differences_from_historical_snapshot": source_current_differences,
        "hash_limit": "checkpoint audit fingerprints contain wall/cache internals; candidate coverage uses strict saved physical/cursor/contract equality plus normal label reproduction. Separate cache-scope audit tests 208 branches only at budget2000/h20, not arbitrary replay exactness.",
        "resume_limit": "Completed immutable owner units can be reused by manifest. An interrupted unit's re-collected sample still requires equal checkpoint_sha256 in collect_and_label, so wall/cache internals may conservatively reject a physically matching cross-process resume. This audit does not certify arbitrary interrupted-sample resume.",
        "class_limit": "Distinct 32- or 16-draw empirical cost vectors are sampled value classes, not universal value equivalence. Immediate-prefix counts exclude retained conditional route state, which remains in actual_action_key.",
        "manifest_sha256": {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in
            (master / "r0/stage_manifest.json", master / "r1/stage_manifest.json", master / "evaluation/stage_manifest.json",
             union / "fit/stage_manifest.json", union / "evaluation/stage_manifest.json")}}
    with target.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in payload.items() if k not in {"checks_detail", "physical_and_value_classes", "manifest_sha256"}}))
    return int(bool(payload["failed"]))


if __name__ == "__main__":
    raise SystemExit(run())
