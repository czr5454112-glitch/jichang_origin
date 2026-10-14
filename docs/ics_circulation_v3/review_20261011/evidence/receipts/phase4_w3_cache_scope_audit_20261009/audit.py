"""Cold/warm equality for fixed observed role checkpoints, not a general proof.

Runs in its own interpreter. clear_static_cache touches no other process. A
temporary generator-call logger returns the unchanged authorized options and
records keys/work without entering policy inputs or modifying source files.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3 import run_paired_recovery as recovery
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation, collect_role_decisions, branch_role_decision, sample_artifact
from scripts.experiments.ics_circulation_v3.routing import clear_static_cache
from scripts.experiments.ics_circulation_v3.runtime import actual_action_key
from scripts.experiments.ics_circulation_v3.model import Bag

OUT = Path(__file__).resolve().parent
BASE = ROOT / "outputs/experiments/ics_circulation_v3"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def semantic(result):
    value = asdict(result)
    value["policy_stats"] = {k: v for k, v in value["policy_stats"].items() if not k.endswith("_ms")}
    return value


def collected_matches(sample, saved):
    current = json.loads(json.dumps(sample_artifact(sample)))
    ignored = {"checkpoint_sha256", "search_work"}
    return [k for k in saved if k not in ignored and saved[k] != current[k]]


def main():
    if (OUT / "protocol.json").exists():
        raise ValueError("scope audit has already started; use a new output directory")
    wall, cpu = perf_counter(), process_time()
    code = ROOT / "scripts/experiments/ics_circulation_v3"
    source = {name: (code / name).read_bytes() for name in recovery.SOURCES}
    source["audit.py"] = Path(__file__).read_bytes()
    (OUT / "source_snapshot").mkdir()
    for name, value in source.items():
        (OUT / "source_snapshot" / name).write_bytes(value)
    save("protocol.json", {"schema": "ics_v3_role_cache_scope_v1", "scope": "current six-node development topology only",
        "r0_samples": 24, "r0_candidates_per_sample": 4, "r0_requested_rollouts": 192,
        "r1_extra_samples_maximum": 2, "r1_extra_rollouts_maximum": 16,
        "future": "saved group0 first common future, identical for every compared candidate",
        "horizon_ticks": 20, "candidate_count": 4, "expansion_limit": 2000, "deadline_ms": None,
        "cold": "clear module global static cache immediately before one branch_role_decision call",
        "warm": "repeat identical checkpoint/action/tape immediately after that cold branch, without clearing",
        "comparison": "all RolloutResult fields excluding policy *_ms; authorized continuation candidate keys/order; paired deltas",
        "continuation": "R0 exact timed controller; R1 original label's explicit fixed-timed replacement",
        "source_sha256": {n: sha256(v).hexdigest() for n, v in source.items()},
        "limitation": "A global cache is absent from the engine checkpoint and its cold work counts toward the bound. This does not certify arbitrary budgets, graphs, future tapes or checkpoint-exact replay under cache changes."})
    saved_summary = read(BASE / "phase4_w3_role_coverage_20261009/summary.json")
    inputs, cases = {}, []
    def load(path):
        inputs[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
        return read(path)
    for scene in recovery.sustained_scenes():
        collection = collect_role_decisions(scene, recovery.SPEC, quota=recovery.quota(), source_group="R0_timed")
        for sample in collection.samples:
            record = next(r for r in saved_summary["samples"] if r["identity"] == sample["identity"])
            folder = BASE / "phase4_w3_role_coverage_20261009"
            saved = load(folder / record["sample_file"])
            label = load(folder / record["stress_file"])
            mismatch = collected_matches(sample, saved)
            if mismatch:
                save("failure.json", {"stage": "recollection", "sample": sample["identity"], "different_fields": mismatch})
                raise ValueError("R0 saved physical/control evidence differs")
            cases.append(("R0", sample, label, None, None))
    assert len(cases) == 24 and sum(len(c[1]["pool"]) for c in cases) == 96
    recovered_root = BASE / "phase4_w3_paired_recovery_20261009"
    models = load(recovered_root / "r0/frozen_models.json")
    metadata = load(recovered_root / "r0/folds_and_bounds.json")
    chosen, seen_roles = [], set()
    for unit in sorted((recovered_root / "r1_units").iterdir()):
        if not (unit / "stage_manifest.json").is_file():
            continue
        summary = load(unit / "summary.json")
        for episode in summary["episodes"]:
            for label_index, row in enumerate(episode["labels"]):
                role = (row["source_node"], row["role"])
                if role[0] not in {"C", "G"} or role in seen_roles:
                    continue
                chosen.append((unit, episode["stream"], label_index))
                seen_roles.add(role)
                if len(chosen) == 2:
                    break
            if len(chosen) == 2:
                break
        if len(chosen) == 2:
            break
    recollections = {}
    for unit, scene_name, ordinal in chosen:
        owner = unit.name
        scene = next(s for s in recovery.sustained_scenes() if s.name == scene_name)
        model = recovery.MLPValueModel.from_dict(models[owner])
        bounds = metadata["bounds"][owner]
        key = (owner, scene_name)
        if key not in recollections:
            recollections[key] = collect_role_decisions(scene, replace(recovery.SPEC, routing="external"),
                quota=recovery.quota(), route_selector=recovery.RecoverySelector(model, bounds, scene.forecasts, schema="physical31"),
                selector_manifest=recovery.selector_manifest(model, bounds, "physical31"), source_group=owner)
        saved = load(unit / scene_name / f"sample_{ordinal:02d}.json")
        label = load(unit / scene_name / f"label_{ordinal:02d}.json")
        sample = next(s for s in recollections[key].samples if s["identity"] == saved["identity"])
        mismatch = collected_matches(sample, saved)
        if mismatch:
            save("failure.json", {"stage": "R1_recollection", "sample": sample["identity"], "different_fields": mismatch})
            raise ValueError("R1 saved physical/control evidence differs")
        timed = recovery.PublishedRoutingSelector(recovery.SPEC, scene.forecasts)
        cases.append(("R1", sample, label, timed, label["continuation_override"]))
    results, failures = [], []
    original_generate = CursorSimulation._generate
    trace_sink = []
    def recording_generate(engine, tray, destination=None):
        options = original_generate(engine, tray, destination)
        trace_sink.append({"time": engine.state.now, "version": engine.state.version,
            "tray": tray.tray_id, "destination": destination,
            "authorized_keys": [actual_action_key(engine.state, c, route_mode=engine.route_mode) for c in options],
            "work": getattr(engine._generator, "last_expansions", None),
            "status": getattr(engine._generator, "last_search_status", None)})
        return options
    CursorSimulation._generate = recording_generate
    try:
        for case_index, (phase, sample, label, continuation, manifest) in enumerate(cases):
            future = tuple(Bag(**b) for b in label["future_groups_offline_only"][0]["tapes"][0])
            rows = []
            save(f"sample_{case_index:02d}.json", {"phase": phase, "sample": sample_artifact(sample),
                "future_group0_first": [asdict(b) for b in future], "continuation_override": manifest})
            for candidate_index, action in enumerate(sample["pool"]):
                clear_static_cache()
                pair = []
                for condition in ("cold", "warm"):
                    trace_sink.clear()
                    before, before_cpu = perf_counter(), process_time()
                    result = branch_role_decision(sample["checkpoint"], action, future, sample["time"] + 20,
                        continuation_selector=continuation, selector_manifest=manifest)
                    value = semantic(result)
                    pair.append({"result": value, "generations": deepcopy(trace_sink),
                        "wall_seconds": perf_counter() - before, "cpu_seconds": process_time() - before_cpu})
                left, right = pair
                generation_semantic = lambda trace: [{k: v for k, v in r.items() if k not in {"work", "status"}} for r in trace]
                matches = left["result"] == right["result"]
                candidates_equal = generation_semantic(left["generations"]) == generation_semantic(right["generations"])
                original_cost = label["paired_costs"][0][candidate_index][0]
                row = {"candidate": candidate_index, "all_result_semantics_equal": matches,
                    "authorized_continuation_candidates_equal": candidates_equal,
                    "cold_cost": left["result"]["total_cost"], "warm_cost": right["result"]["total_cost"],
                    "saved_label_cost": original_cost, "saved_label_cost_reproduced": left["result"]["total_cost"] == original_cost,
                    "cold_result_sha256": recovery.digest(left["result"]), "warm_result_sha256": recovery.digest(right["result"]),
                    "generations": {c: p["generations"] for c, p in zip(("cold", "warm"), pair)},
                    "timings": {c: {k: p[k] for k in ("wall_seconds", "cpu_seconds")} for c, p in zip(("cold", "warm"), pair)}}
                if not matches or not candidates_equal or not row["saved_label_cost_reproduced"]:
                    failures.append({"sample": sample["identity"], **row})
                    save(f"mismatch_{case_index:02d}_{candidate_index}.json", pair)
                rows.append(row)
            cold_delta = [r["cold_cost"] - rows[0]["cold_cost"] for r in rows]
            warm_delta = [r["warm_cost"] - rows[0]["warm_cost"] for r in rows]
            results.append({"phase": phase, "identity": sample["identity"], "node": sample["source_node"], "role": sample["role"],
                "candidates": rows, "cold_deltas": cold_delta, "warm_deltas": warm_delta,
                "relative_costs_equal": cold_delta == warm_delta})
            print(json.dumps({"case": case_index, "phase": phase, "identity": sample["identity"], "failures": len(failures)}), flush=True)
    finally:
        CursorSimulation._generate = original_generate
    result = {"R0_samples": 24, "R1_samples": len(chosen), "rollout_calls": sum(2 * len(r["candidates"]) for r in results),
        "failures": failures, "rows": results, "all_relative_costs_equal": all(r["relative_costs_equal"] for r in results),
        "source_changed": any((Path(__file__) if n == "audit.py" else code / n).read_bytes() != data for n, data in source.items()),
        "input_changed": any(sha256((ROOT / p).read_bytes()).hexdigest() != h for p, h in inputs.items()),
        "input_sha256": inputs, "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu,
        "limitation": "Only saved group0 first tape on these actual checkpoints with budget2000/h20. Global cache absence from checkpoints remains a real general replay-contract limitation; this scoped equality does not erase it."}
    save("summary.json", result)
    save("manifest.json", {p.relative_to(OUT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob("*")) if p.is_file()})
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "input_sha256"}}), flush=True)
    return int(bool(failures) or result["source_changed"] or result["input_changed"] or not result["all_relative_costs_equal"])


if __name__ == "__main__":
    raise SystemExit(main())
