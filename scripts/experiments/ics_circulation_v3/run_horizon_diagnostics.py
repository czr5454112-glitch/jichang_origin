"""Fixed 20/40/80 endpoints for every saved R1 destination-role sample."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time
import traceback

from . import run_paired_recovery as recovery
from .experiment_protocol import create_output_directory
from .experiment_resources import memory_snapshot
from .horizon_diagnostics import audit_old_twenty, horizon_outcomes, outcome_metrics, same_saved_decision
from .label_stability import sustained_scenes
from .model import Bag
from .nonlinear_learning import MLPValueModel
from .phase4_control import PublishedRoutingSelector
from .role_coverage import collect_role_decisions, digest, sample_artifact


OFFSETS = (20, 40, 80)
CACHE_CONTRACT = "isolated_replay_v1"
SOURCES = tuple(dict.fromkeys((*recovery.SOURCES, "run_horizon_diagnostics.py", "horizon_diagnostics.py",
                              "routing_cache_contract.py", "experiment_resources.py")))
PROTOCOL = {
    "schema": "ics_v3_destination_horizon_diagnostic_v1",
    "source_scope": "all 208 prior R1 arrival_at_destination samples, preserving their 24 owners",
    "selection": "role only; include flat states and all prior seeds, never select by label outcome",
    "offsets": list(OFFSETS), "controller_planning_horizon": 20, "continuation": "fixed timed",
    "cache_contract": CACHE_CONTRACT, "candidate_pool": "unchanged normal K4 from actual saved decision",
    "future_tapes": "all saved four groups by eight future tapes, no resampling",
    "maximum_sample_count": 208, "maximum_candidate_future_requests": 26624,
    "maximum_endpoint_reads": 79872,
    "memo": "one sample/candidate/full future tape; no cross-sample or cross-owner reuse",
    "terminal_view": "arithmetic removal of terminal_backlog/inflight on same physical outcome, not optimized",
    "reproduction": "all sample physical/control evidence and every 20tick cost/component/completion must match",
    "owner_budget": {"cpu_seconds": 600, "wall_seconds": 1200, "checkpoints": "between physical branches"},
    "new_fit": False, "model_or_seed_selection": False, "fresh_confirmation": False,
    "limits": ["Owners and futures are correlated reused development data, not independent source groups.",
               "Reporting horizon changes the outcome target while fixed planning/controller remains unchanged.",
               "Terminal-free values omit unfinished service; they cannot alone certify improvement.",
               "Timings are descriptive on a shared workstation; peak memory is process-lifetime."]}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def frozen_stage(folder):
    manifest = read(folder / "stage_manifest.json")
    expected = manifest["files_sha256"]
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(expected) | {"stage_manifest.json"}:
        raise ValueError("historical frozen file set changed: " + str(folder))
    for name, value in expected.items():
        if sha(folder / name) != value:
            raise ValueError("historical frozen bytes changed: " + name)
    return read(folder / "summary.json")


def source_gate(output):
    protocol = read(output / "protocol.json")
    for name, value in protocol["source_sha256"].items():
        if sha(Path(__file__).parent / name) != value or sha(output / "source_snapshot" / name) != value:
            raise ValueError("horizon run source changed: " + name)
    return protocol


def freeze(folder, summary):
    save(folder / "summary.json", summary)
    save(folder / "stage_manifest.json", {"files_sha256": {
        p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}})


def initialize(prior, output):
    prior = prior.resolve()
    original = read(prior / "protocol.json")
    source_changes = []
    for name, value in original["source_sha256"].items():
        if sha(prior / "source_snapshot" / name) != value:
            raise ValueError("historical source snapshot changed")
        if sha(Path(__file__).parent / name) != value:
            source_changes.append(name)
    if set(source_changes) - {"routing.py", "role_coverage.py"}:
        raise ValueError("unexpected historical control change: " + repr(source_changes))
    r0, r1 = frozen_stage(prior / "r0"), frozen_stage(prior / "r1")
    if r0["failures"] or r1["failures"]:
        raise ValueError("need complete successful historical stages")
    selected, manifests = [], {}
    for owner in recovery.recovery_owners():
        folder = prior / "r1_units" / owner
        unit = frozen_stage(folder)
        manifests[owner] = sha(folder / "stage_manifest.json")
        for episode in unit["episodes"]:
            for index, record in enumerate(episode["labels"]):
                if record["role"] != "arrival_at_destination":
                    continue
                sample = folder / episode["stream"] / f"sample_{index:02d}.json"
                label = folder / episode["stream"] / f"label_{index:02d}.json"
                selected.append({"owner": owner, "stream": episode["stream"], "identity": record["identity"],
                    "sample": sample.relative_to(prior).as_posix(), "sample_sha256": sha(sample),
                    "label": label.relative_to(prior).as_posix(), "label_sha256": sha(label),
                    "planned_branches": record["requested_branches"]})
    if len(selected) != 208 or not {r["owner"] for r in selected} <= set(recovery.recovery_owners()):
        raise ValueError("historical destination sample denominator differs from predeclared 208/24")
    longest = max(len(str((output / "owners" / r["owner"] / r["stream"] / "destination_00" /
                           "branches" / "b0127.json.gz").resolve())) for r in selected)
    if os.name == "nt" and longest >= 259:
        raise ValueError("output directory is too deep for portable Windows evidence paths")
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    (output / "owners").mkdir()
    hashes = {}
    for name in SOURCES:
        data = (Path(__file__).parent / name).read_bytes()
        (output / "source_snapshot" / name).write_bytes(data)
        hashes[name] = sha256(data).hexdigest()
    save(output / "protocol.json", {**PROTOCOL, "prior_path": str(prior), "source_sha256": hashes,
        "historical_current_source_differences": source_changes})
    save(output / "input_manifest.json", {"selected": selected, "unit_manifest_sha256": manifests,
        "prior_protocol_sha256": sha(prior / "protocol.json"), "r0_manifest_sha256": sha(prior / "r0/stage_manifest.json"),
        "r1_manifest_sha256": sha(prior / "r1/stage_manifest.json"),
        "frozen_models_sha256": sha(prior / "r0/frozen_models.json"),
        "folds_bounds_sha256": sha(prior / "r0/folds_and_bounds.json"),
        "longest_planned_absolute_evidence_path_characters": longest})
    save(output / "runtime_environment.json", {"python_executable": sys.executable, "python": sys.version,
        "numpy": recovery.np.__version__, "platform": platform.platform(),
        "thread_environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "memory": memory_snapshot()})
    return output


def label_sample(sample, old, folder, scene, budget_check):
    if old["groups"] != 4 or old["futures_per_group"] != 8 or old["candidate_count"] != len(sample["pool"]):
        raise ValueError("saved destination label lacks complete K4 by 32 tape alignment")
    policy = PublishedRoutingSelector(recovery.SPEC, scene.forecasts)
    old_rows = {(r["group"], r["candidate"], r["future_index"]): r for r in old["raw_branches"]}
    rows, memo, failures, budget_stop = [], {}, [], None
    branch_folder = folder / "branches"
    branch_folder.mkdir()
    wall, cpu = perf_counter(), process_time()
    for g, group in enumerate(old["future_groups_offline_only"]):
        for c, candidate in enumerate(sample["pool"]):
            for f, raw_tape in enumerate(group["tapes"]):
                tape_sha = digest(raw_tape)
                key = (c, tape_sha)
                hit = key in memo
                if not hit:
                    try:
                        if budget_stop is None:
                            budget_check()
                    except TimeoutError as exc:
                        budget_stop = {"error": type(exc).__name__, "reason": str(exc)}
                    if budget_stop is None:
                        start, tick_cpu = perf_counter(), process_time()
                        result = {"physical_outcome_available": False}
                        try:
                            outcomes = horizon_outcomes(sample["checkpoint"], candidate, tuple(Bag(**b) for b in raw_tape),
                                OFFSETS, continuation_selector=policy)
                            metrics = {str(h): outcome_metrics(result) for h, result in outcomes.items()}
                            evidence = {str(h): asdict(result) for h, result in outcomes.items()}
                            # Full SHA remains in the row/memo key. A short,
                            # sample-local ordinal avoids Windows MAX_PATH;
                            # it never truncates a semantic cache identity.
                            name = f"b{len(memo):04d}.json.gz"
                            result = {"failed": False, "endpoints": metrics,
                                      "physical_outcome_available": True}
                            with gzip.open(branch_folder / name, "xt", encoding="utf-8") as stream:
                                json.dump(evidence, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                            result.update(evidence="branches/" + name, evidence_sha256=sha(branch_folder / name))
                        except Exception as exc:
                            result.update(failed=True, error=type(exc).__name__, reason=str(exc))
                        result.update(cpu_seconds=process_time() - tick_cpu, wall_seconds=perf_counter() - start,
                                      not_executed=False)
                        memo[key] = result
                original = old_rows[g, c, f]
                result = memo.get(key, {"failed": True, "not_executed": True, **(budget_stop or {}),
                                        "cpu_seconds": 0., "wall_seconds": 0.})
                matches = (original["future_sha256"] == tape_sha and not result["failed"]
                           and audit_old_twenty(original, result["endpoints"]["20"]))
                row = {"group": g, "candidate": c, "future_index": f, "future_sha256": tape_sha,
                       "cache_hit": hit, "twenty_matches_historical": matches, **result}
                rows.append(row)
                if row["failed"] or not matches:
                    failures.append({k: row[k] for k in ("group", "candidate", "future_index", "failed", "twenty_matches_historical")})
    return {"identity": sample["identity"], "source_node": sample["source_node"], "role": sample["role"],
        "groups": 4, "futures_per_group": 8, "candidate_count": len(sample["pool"]),
        "actual_action_keys": list(sample["normal_keys"]), "future_groups_offline_only": old["future_groups_offline_only"],
        "requested_branches": len(rows), "actual_branches": len(memo), "cache_reused": sum(r["cache_hit"] for r in rows),
        "not_executed_requests": sum(r["not_executed"] for r in rows),
        "endpoint_reads": 3 * sum(not r["failed"] for r in rows),
        "endpoint_reads_scope": "successful requested endpoints, including cache reuse",
        "actual_unique_endpoint_reads": sum(len(r.get("endpoints", {})) for r in memo.values()),
        "actual_unique_endpoint_reads_exact": all(r.get("physical_outcome_available") for r in memo.values()),
        "budget_stop": budget_stop, "raw_branches": rows, "failures": failures,
        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu}


def run_owner(output, owner):
    output = Path(output)
    protocol = source_gate(output)
    inputs, prior = read(output / "input_manifest.json"), Path(protocol["prior_path"])
    selected = [r for r in inputs["selected"] if r["owner"] == owner]
    if owner not in recovery.recovery_owners():
        raise ValueError("undeclared owner")
    folder = output / "owners" / owner
    if (folder / "stage_manifest.json").exists():
        return frozen_stage(folder)
    folder.mkdir()  # Incomplete units remain evidence; never silently overwrite.
    wall, cpu, memory = perf_counter(), process_time(), memory_snapshot()
    records, failures = [], []
    def budget_check():
        if process_time() - cpu > PROTOCOL["owner_budget"]["cpu_seconds"] or perf_counter() - wall > PROTOCOL["owner_budget"]["wall_seconds"]:
            raise TimeoutError("predeclared owner compute budget exhausted")
    try:
        for name, key in (("frozen_models.json", "frozen_models_sha256"), ("folds_and_bounds.json", "folds_bounds_sha256")):
            if sha(prior / "r0" / name) != inputs[key]:
                raise ValueError("historical model or bounds drift")
        models, meta = read(prior / "r0/frozen_models.json"), read(prior / "r0/folds_and_bounds.json")
        model = MLPValueModel.from_dict(models[owner])
        for scene in sustained_scenes():
            wanted = [r for r in selected if r["stream"] == scene.name]
            if not wanted:
                continue
            budget_check()
            policy = recovery.RecoverySelector(model, meta["bounds"][owner], scene.forecasts, schema="physical31")
            manifest = recovery.selector_manifest(model, meta["bounds"][owner], "physical31")
            collection = collect_role_decisions(scene, replace(recovery.SPEC, routing="external"),
                quota=recovery.quota(), route_selector=policy, selector_manifest=manifest, source_group=owner,
                cache_contract=CACHE_CONTRACT)
            scene_folder = folder / scene.name
            scene_folder.mkdir()
            save(scene_folder / "collection.json", {"contract": collection.contract, "metadata": collection.metadata,
                "opportunities": collection.opportunities, "result": asdict(collection.episode_result)})
            found = {s["identity"]: s for s in collection.samples}
            for index, entry in enumerate(wanted):
                for kind in ("sample", "label"):
                    if sha(prior / entry[kind]) != entry[kind + "_sha256"]:
                        raise ValueError("historical sample/label drift")
                target = scene_folder / f"destination_{index:02d}"
                target.mkdir()
                if entry["identity"] not in found:
                    failure = {"identity": entry["identity"], "reason": "saved decision absent after recollection"}
                    failures.append(failure)
                    save(target / "failure.json", failure)
                    continue
                sample = found[entry["identity"]]
                comparison = same_saved_decision(read(prior / entry["sample"]), sample)
                save(target / "recollection_comparison.json", comparison)
                save(target / "sample.json", sample_artifact(sample))
                if not comparison["equal"]:
                    failures.append({"identity": entry["identity"], "reason": "physical/control evidence mismatch",
                                     "differences": comparison["differences"]})
                    continue
                label = label_sample(sample, read(prior / entry["label"]), target, scene, budget_check)
                save(target / "labels.json", label)
                records.append({"identity": entry["identity"], "stream": scene.name,
                    "label_file": (target / "labels.json").relative_to(folder).as_posix(),
                    **{k: label[k] for k in ("requested_branches", "actual_branches", "cache_reused", "not_executed_requests", "endpoint_reads", "actual_unique_endpoint_reads", "actual_unique_endpoint_reads_exact", "cpu_seconds", "wall_seconds")}})
                failures.extend({"identity": entry["identity"], **r} for r in label["failures"])
    except Exception as exc:
        failure = {"error": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()}
        failures.append(failure)
        save(folder / "failure.json", failure)
    source_gate(output)
    processed = {r["identity"] for r in records}
    unexecuted = [r for r in selected if r["identity"] not in processed]
    summary = {"owner": owner, "planned_samples": len(selected), "completed_samples": len(records),
        "records": records, "failures": failures, "source_changed_during_run": False,
        "empty_historical_role_preserved": not selected,
        "unexecuted_samples": unexecuted,
        "planned_branches": sum(r["planned_branches"] for r in selected),
        "requested_branches": sum(r["requested_branches"] for r in records),
        "actual_branches": sum(r["actual_branches"] for r in records),
        "cache_reused": sum(r["cache_reused"] for r in records),
        "not_executed_requests": sum(r["not_executed_requests"] for r in records) + sum(r["planned_branches"] for r in unexecuted),
        "actual_unique_endpoint_reads": sum(r["actual_unique_endpoint_reads"] for r in records),
        "actual_unique_endpoint_reads_exact": all(r["actual_unique_endpoint_reads_exact"] for r in records),
        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu,
        "memory_before": memory, "memory_after": memory_snapshot()}
    freeze(folder, summary)
    return summary


def merge(output):
    protocol = source_gate(output)
    owners = [frozen_stage(output / "owners" / name) for name in recovery.recovery_owners()]
    folder = output / "analysis"
    folder.mkdir()
    decisions, failures = [], []
    for owner in owners:
        failures.extend({"owner": owner["owner"], **r} for r in owner["failures"])
        for record in owner["records"]:
            label = read(output / "owners" / owner["owner"] / record["label_file"])
            for h in OFFSETS:
                for metric in ("total_cost", "nonterminal_cost_same_trajectory"):
                    means = []
                    for c in range(label["candidate_count"]):
                        rows = [r for r in label["raw_branches"] if r["candidate"] == c]
                        means.append(None if any(r["failed"] for r in rows) else sum(r["endpoints"][str(h)][metric] for r in rows) / len(rows))
                    valid = all(v is not None for v in means)
                    best = [c for c, value in enumerate(means) if valid and abs(value - min(means)) <= 1e-9]
                    decisions.append({"owner": owner["owner"], "identity": label["identity"], "node": label["source_node"],
                        "horizon": h, "metric": metric, "means": means, "optimal_indices": best,
                        "reference_is_optimal": 0 in best, "range": max(means) - min(means) if valid else None})
    tables = []
    for h in OFFSETS:
        for metric in ("total_cost", "nonterminal_cost_same_trajectory"):
            rows = [r for r in decisions if r["horizon"] == h and r["metric"] == metric]
            valid = [r for r in rows if r["range"] is not None]
            tables.append({"horizon": h, "metric": metric, "states": len(rows), "valid_states": len(valid),
                "reference_optimal": sum(r["reference_is_optimal"] for r in valid),
                "strict_detour_better": sum(not r["reference_is_optimal"] for r in valid),
                "all_tied": sum(r["range"] <= 1e-9 for r in valid)})
    indexed = {(r["owner"], r["identity"], r["horizon"], r["metric"]): r for r in decisions}
    paired, paired_tables = [], []
    for row in decisions:
        if row["horizon"] != 20 or row["metric"] != "total_cost" or row["range"] is None:
            continue
        first_choice = min(row["optimal_indices"])
        for horizon, metric in ((40, "total_cost"), (80, "total_cost"), (20, "nonterminal_cost_same_trajectory"),
                                (40, "nonterminal_cost_same_trajectory"), (80, "nonterminal_cost_same_trajectory")):
            other = indexed[row["owner"], row["identity"], horizon, metric]
            if other["range"] is None:
                continue
            paired.append({"owner": row["owner"], "identity": row["identity"], "node": row["node"],
                "target_horizon": horizon, "target_metric": metric,
                "exact_optimal_set_agrees": row["optimal_indices"] == other["optimal_indices"],
                "old_twenty_first_index_optimum": first_choice,
                "old_choice_regret_in_target": other["means"][first_choice] - min(other["means"]),
                "detour_better_at_twenty": not row["reference_is_optimal"],
                "unload_optimal_in_target": other["reference_is_optimal"]})
    for horizon, metric in sorted({(r["target_horizon"], r["target_metric"]) for r in paired}):
        rows = [r for r in paired if r["target_horizon"] == horizon and r["target_metric"] == metric]
        paired_tables.append({"target_horizon": horizon, "target_metric": metric, "paired_states": len(rows),
            "exact_optimal_set_agrees": sum(r["exact_optimal_set_agrees"] for r in rows),
            "mean_old_choice_regret_in_target": sum(r["old_choice_regret_in_target"] for r in rows) / len(rows),
            "detour_twenty_to_unload_optimal": sum(r["detour_better_at_twenty"] and r["unload_optimal_in_target"] for r in rows)})
    summary = {"planned_samples": 208, "completed_samples": sum(r["completed_samples"] for r in owners),
        "owners": 24, "requested_branches": sum(r["requested_branches"] for r in owners),
        "actual_branches": sum(r["actual_branches"] for r in owners), "cache_reused": sum(r["cache_reused"] for r in owners),
        "not_executed_requests": sum(r["not_executed_requests"] for r in owners),
        "actual_unique_endpoint_reads": sum(r["actual_unique_endpoint_reads"] for r in owners),
        "actual_unique_endpoint_reads_exact": all(r["actual_unique_endpoint_reads_exact"] for r in owners),
        "failures": failures, "decisions": decisions, "tables": tables,
        "paired_endpoint_comparisons": paired, "paired_endpoint_tables": paired_tables,
        "worker_cpu_seconds": sum(r["cpu_seconds"] for r in owners),
        "worker_wall_seconds_sum_not_makespan": sum(r["wall_seconds"] for r in owners),
        "memory_worker_process_lifetime_peaks": [r["memory_after"] for r in owners],
        "limits": PROTOCOL["limits"], "source_changed_during_run": False}
    freeze(folder, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--stage", choices=("init", "owner", "run", "merge"), required=True)
    parser.add_argument("--owner")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=4)
    args = parser.parse_args()
    if args.stage == "init":
        if args.prior is None:
            parser.error("init needs --prior")
        initialize(args.prior, args.output)
        return 0
    if args.stage == "owner":
        result = run_owner(args.output, args.owner)
    elif args.stage == "merge":
        result = merge(args.output)
    else:
        source_gate(args.output)
        wall, cpu, memory = perf_counter(), process_time(), memory_snapshot()
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(run_owner, str(args.output.resolve()), name): name for name in recovery.recovery_owners()}
            for task in as_completed(jobs):
                value = task.result()
                print(json.dumps({k: value[k] for k in ("owner", "completed_samples", "actual_branches", "cpu_seconds", "failures")}), flush=True)
        save(args.output / "execution.json", {"workers": args.workers, "wall_seconds": perf_counter() - wall,
            "coordinator_cpu_seconds": process_time() - cpu, "memory_before": memory, "memory_after": memory_snapshot()})
        result = merge(args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in {"records", "decisions", "paired_endpoint_comparisons", "memory_worker_process_lifetime_peaks", "limits"}}), flush=True)
    return int(bool(result["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
