"""Supplemental bounded K4/K12 value coverage at newly sampled B decisions.

Only the first B-origin quota cell in each stream is inspected, chosen before
reading its labels. Expanded proposals are counterfactual interventions, not
reported as actual deployed selector calls. They never enter model training.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from .experiment_protocol import create_output_directory, write_new_json
from .label_stability import candidate_pool, sustained_scenes
from .learning import TimedAnalyticEvaluator
from .role_coverage import collect_role_decisions, label_role_decision, checkpoint_fingerprint, sample_artifact
from .role_features import physical_features
from .run_role_coverage import SPEC, QUOTA, SOURCES as ROLE_SOURCES
from .runtime import actual_action_key


def expanded_sample(sample, scene):
    state = sample["checkpoint"].state
    tray = state.trays[sample["tray_id"]]
    pool, normal_keys, generation = candidate_pool(state, tray, SPEC, expanded_count=12)
    if tuple(sample["normal_keys"]) != normal_keys:
        raise ValueError("recreated normal pool differs from the actual decision")
    checkpoint = sample["checkpoint"].clone()
    checkpoint.cursor.pending_options = tuple(pool)
    visible = tuple(f for f in scene.forecasts if f.published_at <= state.now)
    evaluator = TimedAnalyticEvaluator(state.now + 20, visible)
    return {**sample, "checkpoint": checkpoint, "checkpoint_sha256": checkpoint_fingerprint(checkpoint),
            "pool": pool, "normal_keys": tuple(actual_action_key(state, p, route_mode="next_edge") for p in pool),
            "features": tuple(evaluator.features(state, p) for p in pool),
            "features_physical": tuple(physical_features(state, p, state.now + 20, visible) for p in pool),
            "generation": generation, "actual_decision_checkpoint_sha256": sample["checkpoint_sha256"],
            "actual_normal_keys": normal_keys,
            "expanded_scope": "hypothetical larger legal candidate set; continuation remains K4/timed"}


def run(labels, output):
    labels, output = Path(labels), create_output_directory(output)
    read_hashes = {}
    def read(name):
        raw = (labels / name).read_bytes()
        read_hashes[name] = sha256(raw).hexdigest()
        return json.loads(raw)
    prior = read("summary.json")
    if prior["failures"] or prior["source_changed_during_run"]:
        raise ValueError("need complete frozen R0 inputs")
    code = Path(__file__).parent
    sources = {name: (code / name).read_bytes() for name in ("run_role_candidate_coverage.py", *ROLE_SOURCES)}
    (output / "source_snapshot").mkdir()
    for name, raw in sources.items():
        (output / "source_snapshot" / name).write_bytes(raw)
    write_new_json(output / "protocol.json", {"scenes": [s.name for s in sustained_scenes()],
        "selection": "first real B-origin sampled cell in each stream, by time then identity; no label ranking",
        "declared_states": 4, "expanded_count": 12, "future_groups": 4, "futures_per_group": 8,
        "same_common_futures_as_R0": True, "horizon_ticks": 20,
        "training_use": "excluded", "scope": "bounded candidate coverage, not physical completeness oracle",
        "source_sha256": {n: sha256(v).hexdigest() for n, v in sources.items()}})
    rows, failed = [], []
    wall, cpu = perf_counter(), process_time()
    for scene in sustained_scenes():
        collection = collect_role_decisions(scene, SPEC, quota=QUOTA, source_group="R0_timed")
        choices = [s for s in collection.samples if s["source_node"] == "B" and s["role"] == "origin"]
        if not choices:
            failed.append({"scene": scene.name, "reason": "declared B decision absent"})
            continue
        sample = min(choices, key=lambda s: (s["time"], s["identity"]))
        record = next(r for r in prior["samples"] if r["identity"] == sample["identity"])
        original = read(record["stress_file"])
        saved_sample = read(record["sample_file"])
        replay_sample = json.loads(json.dumps(sample_artifact(sample)))
        # The exact checkpoint audit ID includes the generator's wall-clock
        # start and cache-dependent work counters. It is not a cross-run
        # semantic key. Check all saved decision evidence, excluding only this
        # audit ID and the explicitly non-semantic search-work measurement;
        # then independently reproduce every old paired continuation below.
        ignored = {"checkpoint_sha256", "search_work"}
        if ({k: v for k, v in replay_sample.items() if k not in ignored}
                != {k: v for k, v in saved_sample.items() if k not in ignored}):
            raise ValueError("saved physical/control decision evidence does not reproduce R0")
        expanded = expanded_sample(sample, scene)
        values = label_role_decision(expanded, scene.future_bags)
        write_new_json(output / (scene.name + "_sample.json"), sample_artifact(expanded))
        write_new_json(output / (scene.name + "_labels.json"), values)
        if values["failures"]:
            failed.extend(values["failures"])
            continue
        normal_indices = [values["actual_action_keys"].index(k) for k in original["actual_action_keys"]]
        costs = np.asarray(values["paired_costs"])
        if not np.array_equal(costs[:, normal_indices, :], np.asarray(original["paired_costs"])):
            raise ValueError("normal candidate common-future costs failed exact reproduction")
        means = costs.mean(axis=(0, 2))
        row = {"scene": scene.name, "identity": sample["identity"], "node": "B", "role": "origin",
               "normal_count": len(normal_indices), "expanded_count": len(expanded["pool"]),
               "branches": len(values["raw_branches"]), "all_cost_means": means.tolist(),
               "bounded_pool_coverage_loss": float(min(means[normal_indices]) - min(means)),
               "normal_costs_exactly_reproduced": True, "generation": expanded["generation"],
               "saved_decision_evidence_reproduced": True,
               "checkpoint_audit_id_matches": original["checkpoint_sha256"] == sample["checkpoint_sha256"],
               "checkpoint_id_caveat": "contains generator wall/cache internals; not a cross-run semantic key"}
        rows.append(row)
        print(row, flush=True)
    result = {"planned_states": 4, "completed_states": len(rows), "rows": rows, "failures": failed,
              "branch_count": sum(r["branches"] for r in rows), "input_sha256": read_hashes,
              "source_changed_during_run": any((code / n).read_bytes() != v for n, v in sources.items()),
              "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu,
              "limits": "first B-origin cells only; no C/G coverage claim, no training or model selection"}
    write_new_json(output / "summary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.labels, args.output)
    raise SystemExit(int(bool(result["failures"]) or result["source_changed_during_run"]))
