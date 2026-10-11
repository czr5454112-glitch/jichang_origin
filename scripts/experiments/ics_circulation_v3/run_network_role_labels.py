"""Original-map development label feasibility, then explicitly budgeted labels.

Pilot does 3 actual continuation states x K4 x two evaluation windows x one
common future. Formal labels require an explicit evaluation window and budgets.
Neither mode trains a model or claims a new held-out operational source.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .audit_nanning import DEFAULT_PROFILE
from .experiment_protocol import check_output_directory, create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .network_role_labels import (BANDS, ROLES, SPEC, SearchBudget, branch_network_decision,
                                  collect_network_decisions, network_futures)
from .phase4_network_workloads import file_sha, load_network, make_workload
from .role_coverage import digest, sample_artifact
from .run_role_coverage import SOURCES as ROLE_SOURCES
from .run_workload_diagnostics import SOURCES as NETWORK_SOURCES


SCENES = ("cross_cycle", "counterflow", "near_full")
SOURCES = tuple(dict.fromkeys(("run_network_role_labels.py", "network_role_labels.py",
    "routing_cache_contract.py", "experiment_resources.py", *ROLE_SOURCES, *NETWORK_SOURCES)))


def serializable_branch(branch):
    result = branch["result"]
    return {**branch, "result": None if result is None else asdict(result)}


def run(output, *, profile=DEFAULT_PROFILE, mode="pilot", evaluation_horizon=None,
        total_cpu_seconds=300., total_wall_seconds=600., max_branch_calls=None, names=SCENES):
    if mode not in {"pilot", "labels"}:
        raise ValueError("mode must be pilot or labels")
    if mode == "labels" and (type(evaluation_horizon) is not int or evaluation_horizon < 1):
        raise ValueError("formal labels require an explicit evaluation horizon")
    if mode == "pilot" and evaluation_horizon is not None:
        raise ValueError("pilot predeclares both h20 and h40")
    if any(not 0 < v < float("inf") for v in (total_cpu_seconds, total_wall_seconds)):
        raise ValueError("finite positive total resource safeguards required")
    max_branch_calls = (24 if mode == "pilot" else 2304) if max_branch_calls is None else max_branch_calls
    if type(max_branch_calls) is not int or max_branch_calls < 1:
        raise ValueError("positive explicit full-simulator-call cap required")
    if not names or len(set(names)) != len(names) or not set(names) <= set(SCENES):
        raise ValueError("choose a nonempty distinct subset of declared original-map workloads")
    output = check_output_directory(output)
    start, cpu, memory_before = perf_counter(), process_time(), memory_snapshot()
    source = Path(__file__).parent
    # Complete inputs and dependencies must exist before creating the directory.
    source_hashes = {name: file_sha(source / name) for name in SOURCES}
    profile = Path(profile)
    profile_hash = file_sha(profile)
    network, topology = load_network(profile)
    scenes = [make_workload(name, network, topology, rounds=3) for name in names]
    setup_wall, setup_cpu = perf_counter() - start, process_time() - cpu
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((source / name).read_bytes())
    (output / "original_profile.json").write_bytes(profile.read_bytes())
    horizons = (20, 40) if mode == "pilot" else (evaluation_horizon,)
    groups, draws = (1, 1) if mode == "pilot" else (4, 8)
    collection_budget, branch_budget = SearchBudget(), SearchBudget(100, 100000, 60.)
    protocol = {"schema": "ics_v3_network_role_labels_v1", "mode": mode,
        "source_sha256": source_hashes, "profile_sha256": profile_hash,
        "all_declared_workloads": SCENES, "workloads": names, "rounds": 3, "new_independent_source_count": 0,
        "source_scope": "reused original Nanning topology with old declared synthetic workload/inventory/service assumptions; development, not operating history or held-out confirmation",
        "spec": asdict(SPEC), "cache_contract": "isolated_replay_v1",
        "role_bands": {"roles": ROLES, "bands": BANDS, "first_attempt_per_cell": True,
                       "max_per_workload": 6, "minimum_checkpoint_target_per_workload": 3},
        "pilot_selection": "first sampled actual continuation per workload; zero is retained and never replaced" if mode == "pilot" else None,
        "evaluation_horizons": horizons, "planning_horizon": 180,
        "evaluation_scope": "finite-window accrued and terminal proxy cost, not full-flow J; continuation generation and published forecasts retain original planning horizon180",
        "stress_groups": groups, "futures_per_group": draws,
        "future_law": "offline unobserved tasks only: cancellation1/8, arrival jitter{-2,0,2} clipped to now+1, deadline shifted identically preserving slack; OD/ID/protected unchanged; positive-capacity directed witness required; forecasts/publication schedule unchanged",
        "pairing": "each sample/group/draw tape shared by every action and pilot horizon; no action-dependent sampling",
        "memoization": "successful full branch outcomes only; per-sample candidate ordinal + full future tape SHA + evaluation horizon, never cross-sample/action/owner; requests and actual calls remain separate",
        "collection_budget": asdict(collection_budget), "branch_budget": asdict(branch_budget),
        "max_full_simulator_calls": max_branch_calls, "total_cpu_seconds": total_cpu_seconds,
        "total_wall_seconds": total_wall_seconds,
        "simulator_call_cap_scope": "offline branch calls only; three collection episodes and three one-tick physical burn-in episodes reported separately",
        "setup_budget": "existing make_workload executes one burn-in search per scene under its unchanged 30000-expansion bound; included in total CPU/wall, not instrumented collection/branch expansion sums",
        "work_budget_boundary": "hard search-call cap; total work checked between queries and may overshoot by one original per-query3000 budget; no per-query limit shrink or wall cutoff within search",
        "checkpoint": "live loaded-decision cursor including earlier same-tick admissions, slow phase, private remaining tape and opt-in owned replay cache; only offline branch changes future tape",
        "branch_accounting": "fresh computation cap per branch; counters are instrumentation, not persistent physical policy state; existing inner generator/cache is never rebuilt",
        "branch_evidence": "one exclusive gzip JSON file per executed branch containing full RolloutResult, search records and cache evidence; summary costs only for reached_horizon branches",
        "denominators": "all actual attempts incl zero and absent role cells; every requested candidate/group/draw/window has completed/budget/failure/not-executed row; no failed rollout cost used as a complete label",
        "training": "none; pilot resource results determine a later declared label horizon/budget before reading full labels"}
    write_new_json(output / "protocol.json", protocol)
    write_new_json(output / "topology_audit.json", topology)
    episode_rows, sample_rows, branch_rows, failures, shortfalls = [], [], [], [], []
    actual_calls = total_searches = total_work = 0

    def global_stop():
        if process_time() - cpu >= total_cpu_seconds:
            return "total_process_cpu_safeguard"
        if perf_counter() - start >= total_wall_seconds:
            return "total_wall_safeguard"
        return None

    for scene in scenes:
        write_new_json(output / (scene.name + "_input.json"), {"initial": asdict(scene.initial),
            "forecasts": [asdict(f) for f in scene.forecasts], "future_engine_only": [asdict(b) for b in scene.future_bags],
            "horizon": scene.horizon, "provenance": scene.provenance})
        stopped = global_stop()
        if stopped:
            episode_rows.append({"scene": scene.name, "status": "not_executed", "reason": stopped})
            shortfalls.append({"scene": scene.name, "reason": "collection_not_executed", "minimum_target": 3, "sampled": 0})
            continue
        try:
            collection = collect_network_decisions(scene, budget=collection_budget)
        except Exception as exc:
            failure = {"scene": scene.name, "stage": "collection_setup", "type": type(exc).__name__,
                       "message": str(exc), "traceback": traceback.format_exc()}
            failures.append(failure)
            episode_rows.append({"scene": scene.name, "status": "execution_failure", "failure": failure})
            shortfalls.append({"scene": scene.name, "reason": "collection_setup_failure", "minimum_target": 3, "sampled": 0})
            write_new_json(output / (scene.name + "_collection_failure.json"), failure)
            continue
        total_searches += collection["metadata"]["search_calls"]
        total_work += collection["metadata"]["search_work"]
        episode_rows.append(collection["metadata"])
        write_new_json(output / (scene.name + "_collection.json"), {"metadata": collection["metadata"],
            "opportunities": collection["opportunities"],
            "result": None if collection["result"] is None else asdict(collection["result"])})
        if collection["metadata"]["failure"]:
            failures.append({"scene": scene.name, "stage": "collection", **collection["metadata"]["failure"]})
        selected = collection["samples"]
        if mode == "pilot":
            selected = [s for s in selected if s["role"] == "continuation"][:1]
        if len(collection["samples"]) < 3 or (mode == "pilot" and not selected):
            shortfalls.append({"scene": scene.name, "reason": "insufficient_actual_checkpoints_or_missing_pilot_continuation",
                               "minimum_target": 3, "sampled": len(collection["samples"]),
                               "selected_for_labels": len(selected)})
        selected_ids = {s["identity"] for s in selected}
        for number, sample in enumerate(collection["samples"]):
            stem = f"{scene.name}_sample_{number:02d}"
            write_new_json(output / (stem + ".json"), sample_artifact(sample))
            sample_row = {key: sample[key] for key in ("identity", "time", "source_node", "role", "band", "candidate_count")}
            sample_row.update(scene=scene.name, file=stem + ".json", selected_for_labels=sample["identity"] in selected_ids)
            sample_rows.append(sample_row)
            if sample["identity"] not in selected_ids:
                continue
            futures, memo = [], {}
            for group in range(groups):
                seed = int(digest([sample["identity"], "network_valid_future_v1", group])[:16], 16)
                tapes = network_futures(scene.future_bags, sample["checkpoint"].state, count=draws, seed=seed)
                futures.append({"seed": seed, "tapes": [[asdict(b) for b in tape] for tape in tapes]})
                for draw, tape in enumerate(tapes):
                    for horizon in horizons:
                        for candidate_index, candidate in enumerate(sample["pool"]):
                            row = {"sample": sample["identity"], "scene": scene.name, "group": group,
                                "draw": draw, "candidate": candidate_index, "horizon_ticks": horizon,
                                "future_sha256": digest([asdict(b) for b in tape])}
                            memo_key = (candidate_index, row["future_sha256"], horizon)
                            if memo_key in memo:
                                previous = memo[memo_key]
                                branch_rows.append({**previous, **row, "cache_hit": True,
                                    "evidence_original_request": {k: previous[k] for k in ("group", "draw", "candidate", "horizon_ticks")},
                                    "search_calls": 0, "search_work": 0, "wall_seconds": 0., "cpu_seconds": 0.})
                                continue
                            stopped = global_stop() or ("full_simulator_call_cap" if actual_calls >= max_branch_calls else None)
                            if stopped:
                                branch_rows.append({**row, "status": "not_executed", "reason": stopped, "cache_hit": False})
                                continue
                            actual_calls += 1
                            branch_wall, branch_cpu = perf_counter(), process_time()
                            try:
                                outcome = branch_network_decision(sample["checkpoint"], candidate, tape,
                                    horizon_ticks=horizon, budget=branch_budget)
                            except Exception as exc:
                                outcome = {"status": "execution_failure", "result": None,
                                    "failure": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
                                    "search_calls": 0, "search_work": 0, "failure_before_instrumented_continuation": True,
                                    "wall_seconds": perf_counter() - branch_wall, "cpu_seconds": process_time() - branch_cpu}
                            total_searches += outcome["search_calls"]
                            total_work += outcome["search_work"]
                            filename = f"{stem}_g{group}_f{draw}_h{horizon}_c{candidate_index}.json.gz"
                            with gzip.open(output / filename, "xt", encoding="utf-8") as stream:
                                json.dump({**row, **serializable_branch(outcome)}, stream,
                                          ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                            result = outcome["result"]
                            branch_rows.append({**row, "status": outcome["status"], "file": filename, "cache_hit": False,
                                "total_cost": result.total_cost if result is not None and outcome["status"] == "reached_horizon" else None,
                                "cost_components": result.cost_components if result is not None else None,
                                "completed_bags": len(result.completed) if result is not None else None,
                                "uncompleted_bags": len(result.uncompleted_bag_ids) if result is not None else None,
                                "search_calls": outcome["search_calls"], "search_work": outcome["search_work"],
                                "wall_seconds": outcome["wall_seconds"], "cpu_seconds": outcome["cpu_seconds"]})
                            if outcome["status"] == "reached_horizon":
                                memo[memo_key] = branch_rows[-1]
                            if outcome["failure"]:
                                failures.append({**row, **outcome["failure"]})
            write_new_json(output / (stem + "_future_groups_offline.json"), futures)
            sample_row["labels"] = []
            for horizon in horizons:
                local = [r for r in branch_rows if r["sample"] == sample["identity"] and r["horizon_ticks"] == horizon]
                index = {(r["group"], r["candidate"], r["draw"]): r for r in local}
                expected = groups * len(sample["pool"]) * draws
                if len(local) != len(index) or len(local) != expected:
                    raise ValueError("requested paired network label denominator mismatch")
                paired = [[[index[g, c, f].get("total_cost") for f in range(draws)]
                            for c in range(len(sample["pool"]))] for g in range(groups)]
                filename = f"{stem}_h{horizon}_label.json"
                label = {"schema": "ics_v3_network_role_label_v1", "identity": sample["identity"],
                    "source_node": sample["source_node"], "role": sample["role"], "band": sample["band"],
                    "planning_horizon": 180, "evaluation_horizon_ticks": horizon,
                    "groups": groups, "futures_per_group": draws, "candidate_count": len(sample["pool"]),
                    "actual_action_keys": sample.get("normal_keys", ()),
                    "physical_prefix_signatures": sample.get("physical_prefix_signatures", ()),
                    "checkpoint_sha256": sample.get("checkpoint_sha256"), "sample_file": stem + ".json",
                    "future_groups_offline_only": futures, "paired_costs": paired, "raw_branches": local,
                    "requested_branches": expected, "zero_candidate_preserved": not sample["pool"],
                    "actual_branches": sum(not r["cache_hit"] and r["status"] != "not_executed" for r in local),
                    "cache_reused_branches": sum(r["cache_hit"] for r in local),
                    "status_counts": dict(Counter(r["status"] for r in local)),
                    "complete_paired_label": bool(sample["pool"]) and all(r["status"] == "reached_horizon" for r in local),
                    "source_scope": protocol["source_scope"], "new_independent_source_count": 0}
                write_new_json(output / filename, label)
                sample_row["labels"].append(filename)
        print(json.dumps({"scene": scene.name, "collection_status": collection["metadata"]["status"],
            "sampled": len(collection["samples"]), "selected": len(selected), "actual_branch_calls": actual_calls}), flush=True)
    summary = {"mode": mode, "new_independent_source_count": 0, "episodes": episode_rows,
        "samples": sample_rows, "requested_branch_rows": len(branch_rows), "actual_full_simulator_calls": actual_calls,
        "cache_reused_branches": sum(r["cache_hit"] for r in branch_rows),
        "full_simulator_calls_scope": "offline branch calls; collection and burn-in episodes counted separately below",
        "collection_episodes_attempted": sum(e["status"] != "not_executed" for e in episode_rows),
        "collection_episodes_reached_horizon": sum(e["status"] == "reached_horizon" for e in episode_rows),
        "burnin_episodes_executed": len(scenes), "setup_wall_seconds": setup_wall, "setup_cpu_seconds": setup_cpu,
        "branch_status_counts": dict(Counter(r["status"] for r in branch_rows)), "branches": branch_rows,
        "failures": failures, "sampling_shortfalls": shortfalls, "search_calls_collection_and_branches": total_searches,
        "search_work_collection_and_branches": total_work,
        "source_changed_during_run": source_hashes != {name: file_sha(source / name) for name in SOURCES},
        "profile_changed_during_run": file_sha(profile) != profile_hash,
        "wall_seconds": perf_counter() - start, "cpu_seconds": process_time() - cpu,
        "memory_before": memory_before, "memory_after": memory_snapshot()}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "manifest.json", {p.relative_to(output).as_posix(): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def _scene_worker(arguments):
    name, output, profile, horizon, cpu, wall = arguments
    return name, run(output, profile=profile, mode="labels", evaluation_horizon=horizon,
                     total_cpu_seconds=cpu, total_wall_seconds=wall, max_branch_calls=768, names=(name,))


def run_parallel(output, *, profile=DEFAULT_PROFILE, evaluation_horizon=80, workers=3,
                 scene_cpu_seconds=2400., scene_wall_seconds=3600.):
    """All three source groups, each with its own recorded computation budget."""
    if type(workers) is not int or not 1 <= workers <= 3:
        raise ValueError("worker count must be in 1..3")
    if type(evaluation_horizon) is not int or evaluation_horizon < 1:
        raise ValueError("positive evaluation horizon required")
    if any(not 0 < v < float("inf") for v in (scene_cpu_seconds, scene_wall_seconds)):
        raise ValueError("positive finite per-scene safeguards required")
    output = check_output_directory(output)
    source, profile = Path(__file__).parent, Path(profile).resolve()
    hashes = {name: file_sha(source / name) for name in SOURCES}
    profile_hash = file_sha(profile)
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((source / name).read_bytes())
    longest = max(len(str((output / scene / f"{scene}_sample_05_g3_f7_h{evaluation_horizon}_c3.json.gz").resolve()))
                  for scene in SCENES)
    # Exercise the actual gzip API at the planned longest filename shape.
    # Keep this preflight artifact; it is not a simulator result.
    probe = output / ("gzip_path_probe_" + "x" * 55 + ".json.gz")
    with gzip.open(probe, "xt", encoding="utf-8") as stream:
        json.dump({"purpose": "gzip_write_preflight_only", "longest_planned_absolute_path_chars": longest}, stream)
    protocol = {"schema": "ics_v3_network_role_labels_parallel_v1", "source_sha256": hashes,
        "profile_sha256": profile_hash, "workloads": SCENES, "workers": workers,
        "evaluation_horizon_ticks": evaluation_horizon, "planning_horizon_ticks": 180,
        "maximum_selected_checkpoints": 18, "minimum_checkpoint_target_per_scene": 3,
        "normal_candidate_count": 4, "groups": 4, "draws_per_group": 8,
        "maximum_requested_branches": 2304, "maximum_actual_branches": 2304,
        "expected_requests_from_pilot_cells_not_a_runtime_filter": 2176,
        "scene_cpu_seconds": scene_cpu_seconds, "scene_wall_seconds": scene_wall_seconds,
        "sum_scene_cpu_safeguards": 3 * scene_cpu_seconds, "sum_scene_wall_safeguards_not_makespan": 3 * scene_wall_seconds,
        "resource_boundary": "work/checkpoint limits unchanged; per-scene CPU/wall checked cooperatively between branches; no outcome-dependent shortening; every worker retains full requested/failed/unexecuted denominator",
        "cache": "same sample/candidate/full future/horizon successful-result memo only; no cross-scene worker sharing",
        "source_scope": "same three reused synthetic workloads on original Nanning topology; development, no new independent source or field operations claim",
        "new_independent_source_count": 0,
        "path_preflight": {"longest_planned_absolute_path_chars": longest, "actual_probe_absolute_path_chars": len(str(probe.resolve())),
                           "gzip_write_success": True, "probe_file": probe.name},
        "memory_scope": "each worker reports process-lifetime peak; worker peaks are never summed as simultaneous aggregate memory"}
    write_new_json(output / "protocol.json", protocol)
    started, parent_cpu, memory_before = perf_counter(), process_time(), memory_snapshot()
    summaries, failures = {}, []
    arguments = [(name, str(output / name), str(profile), evaluation_horizon, scene_cpu_seconds, scene_wall_seconds) for name in SCENES]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_scene_worker, args): args[0] for args in arguments}
        for future in as_completed(jobs):
            name = jobs[future]
            try:
                _, summaries[name] = future.result()
            except Exception as exc:
                failures.append({"scene": name, "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    rows = [{**r, **({"file": name + "/" + r["file"]} if "file" in r else {})}
            for name in SCENES if name in summaries for r in summaries[name]["branches"]]
    result = {"schema": protocol["schema"], "scene_count_planned": 3, "scene_summaries_received": len(summaries),
        "worker_failures": failures, "new_independent_source_count": 0,
        "complete_resource_accounting": not failures, "scene_summaries": {name: {k: v for k, v in s.items() if k != "branches"} for name, s in summaries.items()},
        "requested_branch_rows": len(rows), "actual_full_simulator_calls": sum(s["actual_full_simulator_calls"] for s in summaries.values()),
        "cache_reused_branches": sum(s["cache_reused_branches"] for s in summaries.values()),
        "branch_status_counts": dict(Counter(r["status"] for r in rows)), "branches": rows,
        "failures": failures + [f for s in summaries.values() for f in s["failures"]],
        "sampling_shortfalls": [f for s in summaries.values() for f in s["sampling_shortfalls"]],
        "source_changed_during_run": hashes != {name: file_sha(source / name) for name in SOURCES}
            or any(s["source_changed_during_run"] for s in summaries.values()),
        "profile_changed_during_run": file_sha(profile) != profile_hash,
        "worker_cpu_seconds_sum": sum(s["cpu_seconds"] for s in summaries.values()),
        "worker_wall_seconds_sum_not_makespan": sum(s["wall_seconds"] for s in summaries.values()),
        "parent_cpu_seconds_excluding_workers": process_time() - parent_cpu,
        "wall_makespan_seconds": perf_counter() - started,
        "parent_memory_before": memory_before, "parent_memory_after": memory_snapshot()}
    write_new_json(output / "summary.json", result)
    write_new_json(output / "manifest.json", {"source_sha256": hashes, "summary_sha256": file_sha(output / "summary.json"),
        "protocol_sha256": file_sha(output / "protocol.json"),
        "scene_manifest_sha256": {name: file_sha(output / name / "manifest.json") for name in summaries}})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--mode", choices=("pilot", "labels"), default="pilot")
    parser.add_argument("--evaluation-horizon", type=int)
    parser.add_argument("--total-cpu-seconds", type=float, default=300.)
    parser.add_argument("--total-wall-seconds", type=float, default=600.)
    parser.add_argument("--max-branch-calls", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers != 1:
        if args.mode != "labels" or args.max_branch_calls not in (None, 2304):
            parser.error("parallel mode requires labels and the full2304 maximum-call budget")
        result = run_parallel(args.output, profile=args.profile, evaluation_horizon=args.evaluation_horizon,
            workers=args.workers, scene_cpu_seconds=args.total_cpu_seconds / 3,
            scene_wall_seconds=args.total_wall_seconds / 3)
    else:
        result = run(args.output, profile=args.profile, mode=args.mode, evaluation_horizon=args.evaluation_horizon,
                     total_cpu_seconds=args.total_cpu_seconds, total_wall_seconds=args.total_wall_seconds,
                     max_branch_calls=args.max_branch_calls)
    print(json.dumps({key: result[key] for key in ("requested_branch_rows", "actual_full_simulator_calls",
        "branch_status_counts", "source_changed_during_run")}, indent=2))
    return int(bool(result["failures"] or result["sampling_shortfalls"] or result["source_changed_during_run"] or result["profile_changed_during_run"]
                    or any(e["status"] != "reached_horizon" for e in result.get("episodes", ()))
                    or any(e["status"] != "reached_horizon" for s in result.get("scene_summaries", {}).values() for e in s["episodes"])
                    or any(r["status"] != "reached_horizon" for r in result["branches"])))


if __name__ == "__main__":
    raise SystemExit(main())
