"""Read-only independent shared-union audit before the main evaluation ends."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify_stage(folder, stage):
    local = folder / stage
    manifest = read(local / "stage_manifest.json")
    assert manifest["source_changed_during_run"] is False
    assert manifest["protocol_sha256"] == sha(folder / "protocol.json")
    assert {p.relative_to(local).as_posix() for p in local.rglob("*") if p.is_file()} == set(manifest["files_sha256"]) | {"stage_manifest.json"}
    assert all(sha(local / k) == v for k, v in manifest["files_sha256"].items())
    return read(local / "summary.json")


def main():
    output = Path(__file__).with_name("shared_preflight_audit.json")
    if output.exists():
        raise ValueError("new audit output required")
    master = BASE / "phase4_w3_paired_recovery_20261009"
    shared = BASE / "phase4_w3_shared_recovery_20261009"
    fit, evaluated = (verify_stage(shared, stage) for stage in ("fit", "evaluation"))
    for stage in ("r0", "r1"):
        verify_stage(master, stage)
    protocol = read(shared / "protocol.json")
    inputs = read(shared / "input_manifest.json")
    checks = []
    def check(name, passed, **context):
        checks.append({"name": name, "passed": bool(passed), **context})
    check("archived_source_self_hashes", all(sha(shared / "source_snapshot" / n) == h for n, h in protocol["source_sha256"].items()))
    check("original_frozen_master_input_hashes", all(sha(master / n) == h for n, h in inputs["files_sha256"].items()))
    r0, owners = read(master / "r0/rows.json"), read(master / "r1/rows_by_owner.json")
    corpora = read(shared / "fit/training_rows_by_fold.json")
    models = read(shared / "fit/frozen_models.json")
    metadata = read(shared / "fit/folds_and_bounds.json")
    expected_names = [f"{s}__physical31__{kind}_seed{seed}" for s in protocol["streams"] for kind in protocol["kinds"] for seed in protocol["seeds"]]
    check("all_24_model_names", set(models) == set(expected_names) and fit["fits"] == 24)
    rows_by_fold = {}
    for held in protocol["streams"]:
        fold_owners = [f"{held}__physical31__{kind}_seed{seed}" for kind in protocol["kinds"] for seed in protocol["seeds"]]
        expected = [r for r in r0 if r["stream"] != held]
        for owner in fold_owners:
            unit = master / "r1_units" / owner
            record = verify_stage(master, "r1_units/" + owner)
            check("original_owner_identity_three_training_streams_and_rows_retained",
                read(unit / "rows.json") == owners[owner] and record["owner"] == owner and record["held_out_stream"] == held
                and record["collection_episodes"] == len(record["episodes"]) == 3
                and {e["stream"] for e in record["episodes"]} == set(protocol["streams"]) - {held}
                and all(r["owner"] == owner and r["stream"] != held for r in owners[owner])
                and inputs["unit_manifests"][owner]["manifest_sha256"] == sha(unit / "stage_manifest.json")
                and inputs["unit_manifests"][owner]["rows_sha256"] == sha(unit / "rows.json"), owner=owner)
            expected += owners[owner]
        check("same_union_all_original_rows_in_exact_order", expected == corpora[held], fold=held)
        rows_by_fold[held] = len(expected)
        projected = [dict(r, features=r["features31"], split="train") for r in expected]
        for name in fold_owners:
            value, fold = models[name], metadata["folds"][name]
            names = value["feature_names"]
            matrix = np.asarray([[r["features31"][n] for n in names] for r in expected])
            scale = matrix.std(axis=0)
            scale[scale < 1e-9] = 1.
            bounds = {n: {"minimum": float(matrix[:, i].min()), "maximum": float(matrix[:, i].max())} for i, n in enumerate(names)}
            check("whole_stream_normalization_bounds_and_ordered_input_sha",
                fold["training_rows_sha256"] == digest(projected) and fold["training_rows"] == len(expected)
                and set(fold["training_streams"]) == set(protocol["streams"]) - {held}
                and value["center"] == matrix.mean(axis=0).tolist() and value["scale"] == scale.tolist()
                and metadata["bounds"][name] == bounds
                and value["config"]["epochs"] == 400 and value["config"]["l2"] == .001
                and value["config"]["learning_rate"] == .01 and value["config"]["seed"] in (17, 29, 43), model=name)
    stage_protocol = read(shared / "evaluation/stage_protocol.json")
    check("all_models_frozen_before_evaluation_and_unchanged",
        stage_protocol["fit_manifest_sha256"] == sha(shared / "fit/stage_manifest.json")
        and stage_protocol["frozen_model_sha256"] == sha(shared / "fit/frozen_models.json")
        and stage_protocol["all_24_models_frozen_before_evaluation"] is True)
    rows = evaluated["deployment_metrics"]
    keys = [(r["stream"], r["realization"], r["policy"]) for r in rows]
    cells = Counter(k[:2] for k in keys)
    check("all_288_episodes_unique_and_complete_failure_denominator", len(rows) == len(set(keys)) == 288
        and len(cells) == 36 and set(cells.values()) == {8}
        and evaluated["failures"] == [r for r in rows if r["status"] != "completed_run"]
        and evaluated["scheduled_bag_denominator"] == sum(r["scheduled_bags"] for r in rows)
        and evaluated["completed_bags"] == sum(r["completed"] or 0 for r in rows))
    comparisons = 0
    for stream, tape in cells:
        ours = read(shared / "evaluation" / f"{stream}__{tape}" / "inputs.json")
        check("stored_scene_input_hash_matches", ours["input_sha256"] == digest({k: v for k, v in ours.items() if k != "input_sha256"}), stream=stream, tape=tape)
        for reference in ("public_rollout", "role_linear"):
            ref = BASE / f"phase4_w3_{reference}_20261009"
            theirs = read(ref / f"{stream}__{tape}_inputs.json") if reference == "public_rollout" else read(ref / f"{stream}__{tape}" / "inputs.json")
            tape_field = "event_engine_only_tape" if reference == "public_rollout" else "actual_tape_event_engine_only"
            check("same_scene_information_and_tape", all(ours[k] == theirs[k] for k in ("initial", "forecasts", "horizon"))
                  and ours["actual_tape_event_engine_only"] == theirs[tape_field], stream=stream, tape=tape, reference=reference)
            for policy in ("baseline", "timed"):
                a = read(shared / "evaluation" / f"{stream}__{tape}" / (policy + ".json"))
                b = read(ref / f"{stream}__{tape}__{policy}.json") if reference == "public_rollout" else read(ref / f"{stream}__{tape}" / (policy + ".json"))
                check("same_control_cost_full_physical_trace_and_slow_phase", a["metrics"]["status"] == b["metrics"]["status"] == "completed_run"
                    and all(a["result"][k] == b["result"][k] for k in ("cost_components", "trace", "final_snapshot", "completed", "uncompleted_bag_ids"))
                    and a["slow_trigger_times"] == b["slow_trigger_times"], stream=stream, tape=tape, policy=policy, reference=reference)
                comparisons += 1
    aggregates = {}
    for method in sorted({r["policy"] for r in rows}):
        selected = [r for r in rows if r["policy"] == method]
        aggregates[method] = {"episodes": len(selected), "completed": sum(r["completed"] or 0 for r in selected),
            "scheduled": sum(r["scheduled_bags"] for r in selected), "on_time": sum(r.get("on_time", 0) for r in selected),
            "cost_sum_completed_runs": sum(r["total_cost"] for r in selected if r["total_cost"] is not None),
            "failed": sum(r["status"] != "completed_run" for r in selected)}
    result = {"scope": "shared only preflight while main 720 evaluation remains pending; no new fitting or rollouts",
        "checks": len(checks), "passed": sum(c["passed"] for c in checks), "failures": [c for c in checks if not c["passed"]],
        "check_results": checks, "ordered_training_rows_per_fold": rows_by_fold, "control_pairs_with_public_and_linear": comparisons,
        "policies": aggregates, "scheduled_bags": sum(r["scheduled_bags"] for r in rows),
        "completed_bags": sum(r["completed"] or 0 for r in rows), "on_time": sum(r.get("on_time", 0) for r in rows),
        "frozen_manifests_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
            (shared / "fit/stage_manifest.json", shared / "evaluation/stage_manifest.json", master / "r0/stage_manifest.json", master / "r1/stage_manifest.json")}}
    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"check_results", "frozen_manifests_sha256"}}))
    return int(bool(result["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
