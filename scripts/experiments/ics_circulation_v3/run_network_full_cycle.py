"""Preserved original-map 18-cell/2176-request whole-tape continuation."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .model import Bag
from .network_full_cycle import branch_full_cycle
from .network_role_labels import SearchBudget, collect_network_decisions
from .phase4_network_workloads import file_sha, load_network, make_workload
from .role_coverage import digest, sample_artifact
from .run_network_role_labels import SOURCES as OLD_SOURCES, SCENES


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).parent
SOURCES = tuple(dict.fromkeys(("network_full_cycle.py", "run_network_full_cycle.py", *OLD_SOURCES)))
DEFAULT_PRIOR = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w3_network_role_complete_20261009"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_manifest(folder):
    folder = Path(folder)
    manifest = read(folder / "manifest.json")
    for name, expected in manifest.items():
        if file_sha(folder / name) != expected:
            raise ValueError("immutable input changed: " + str(folder / name))
    return manifest


def memo_key(row):
    return row["sample"], row["candidate"], row["future_sha256"]


def exact_decision(old, sample):
    actual = json.loads(json.dumps(sample_artifact(sample)))
    changed = [k for k in old.keys() | actual.keys()
               if k != "checkpoint_sha256" and old.get(k) != actual.get(k)]
    return {"equal": not changed, "different_fields": sorted(changed),
            "excluded": "wall-containing per-instance checkpoint_sha256 only"}


def load_inputs(prior):
    prior = Path(prior).resolve()
    check_manifest(prior)
    audit = read(prior / "audit.json")
    if audit["failed_checks"] or audit["resolved_requests"] != 2176:
        raise ValueError("complete audited original request ledger required")
    primary = Path(audit["primary"])
    if file_sha(primary / "manifest.json") != audit["primary_manifest_sha256"]:
        raise ValueError("primary manifest changed")
    primary_manifest = read(primary / "manifest.json")
    if any(file_sha(primary / (k + ".json")) != primary_manifest[k + "_sha256"] for k in ("summary", "protocol")):
        raise ValueError("primary root evidence changed")
    old_protocol = read(primary / "protocol.json")
    for name, expected in old_protocol["source_sha256"].items():
        if file_sha(SOURCE / name) != expected or file_sha(primary / "source_snapshot" / name) != expected:
            raise ValueError("original controller/physical source changed: " + name)
    for item in audit["supplement_references"]:
        folder = Path(item["path"])
        if file_sha(folder / "manifest.json") != item["manifest_sha256"]:
            raise ValueError("supplement manifest changed")
        check_manifest(folder)
    samples, original_rows = {}, {}
    for scene in SCENES:
        folder = primary / scene
        if file_sha(folder / "manifest.json") != primary_manifest["scene_manifest_sha256"][scene]:
            raise ValueError("primary scene manifest changed")
        check_manifest(folder)
        for entry in read(folder / "summary.json")["samples"]:
            label = read(folder / entry["labels"][0])
            if label["groups"] != 4 or label["futures_per_group"] != 8 or label["evaluation_horizon_ticks"] != 80:
                raise ValueError("original K4/4x8/h80 domain changed")
            samples[entry["identity"]] = {"scene": scene, "saved": read(folder / entry["file"]),
                "label": label, "entry": entry}
            for row in label["raw_branches"]:
                key = digest([row[k] for k in ("scene", "sample", "group", "candidate", "draw", "horizon_ticks")])
                original_rows[key] = row
    ledger = read(prior / "resolved_request_ledger.json")
    if len(samples) != 18 or len(ledger) != 2176 or set(ledger) != set(original_rows):
        raise ValueError("must preserve all18 cells/all2176 original request identities")
    for key, row in ledger.items():
        if row["request_key"] != key or row["status"] != "reached_horizon":
            raise ValueError("ledger must resolve each original h80 endpoint")
        if any(row[k] != original_rows[key][k] for k in ("scene", "sample", "candidate", "group", "draw", "horizon_ticks", "future_sha256")):
            raise ValueError("resolved request differs from original")
        raw = samples[row["sample"]]["label"]["future_groups_offline_only"][row["group"]]["tapes"][row["draw"]]
        if digest(raw) != row["future_sha256"]:
            raise ValueError("saved original tape hash differs")
    return primary, samples, list(ledger.values())


def selected_requests(samples, rows, mode):
    if mode == "full":
        return list(rows)
    if mode != "pilot":
        raise ValueError("mode must be pilot or full")
    selected = []
    for scene in SCENES:
        identity = next(k for k, s in samples.items() if s["scene"] == scene
                        and s["saved"]["role"] == "continuation" and s["saved"]["candidate_count"])
        selected.extend(r for r in rows if r["sample"] == identity and r["group"] == r["draw"] == 0)
    return selected


def summarize_rows(rows):
    return {"request_count": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
        "actual_branches": sum(r.get("physical_call", False) for r in rows),
        "cache_reused": sum(r.get("cache_hit", False) for r in rows),
        "old80_matches": sum(r.get("old80_equal") is True for r in rows),
        "task_complete": sum(r.get("task_complete") is True for r in rows),
        "transport_drained": sum(r.get("transport_drained") is True for r in rows)}


def shard_requests(rows, index, count):
    """Allocate entire sample/candidate/full-tape memo classes, outcome blind."""
    if type(count) is not int or type(index) is not int or count < 1 or not 0 <= index < count:
        raise ValueError("invalid deterministic shard index/count")
    keys = sorted({memo_key(r) for r in rows})
    assignment = {key: number % count for number, key in enumerate(keys)}
    return [r for r in rows if assignment[memo_key(r)] == index]


def _scene_worker(args):
    prior, output, scene_name, mode, cpu_limit, wall_limit = args
    return scene_name, run_scene(prior, output, scene_name, mode=mode,
                                cpu_limit=cpu_limit, wall_limit=wall_limit)


def _shard_worker(args):
    prior, output, index, count, cpu_limit, wall_limit = args
    start, cpu = perf_counter(), process_time()
    output = create_output_directory(output)
    summaries, failures = {}, []
    for scene in SCENES:
        try:
            summaries[scene] = run_scene(prior, output / scene, scene, mode="full",
                cpu_limit=max(0., cpu_limit - (process_time() - cpu)),
                wall_limit=max(0., wall_limit - (perf_counter() - start)),
                shard_index=index, shard_count=count)
        except Exception as exc:
            failures.append({"scene": scene, "type": type(exc).__name__, "message": str(exc),
                             "traceback": traceback.format_exc()})
    rows = [r for scene in SCENES for r in summaries.get(scene, {}).get("rows", [])]
    summary = {**summarize_rows(rows), "rows": rows, "shard_index": index, "shard_count": count,
        "scene_summaries": {k: {n: v for n, v in s.items() if n != "rows"} for k, s in summaries.items()},
        "failures": failures, "source_unchanged": all(s["source_unchanged"] for s in summaries.values()),
        "input_unchanged": all(s["input_unchanged"] for s in summaries.values()),
        "complete_resource_accounting": not failures,
        "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - start,
        "memory_after": memory_snapshot()}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "manifest.json", {p.relative_to(output).as_posix(): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return f"shard{index}", summary


def run_scene(prior, output, scene_name, *, mode="pilot", cpu_limit=14400., wall_limit=21600.,
              shard_index=0, shard_count=1):
    start, cpu, memory = perf_counter(), process_time(), memory_snapshot()
    primary, samples, original_rows = load_inputs(prior)
    selected = shard_requests(selected_requests(samples, original_rows, mode), shard_index, shard_count)
    rows = [r for r in selected if r["scene"] == scene_name]
    hashes = {n: file_sha(SOURCE / n) for n in SOURCES}
    output = create_output_directory(output)
    snapshots = output / "source_snapshot"
    snapshots.mkdir()
    for name in SOURCES:
        (snapshots / name).write_bytes((SOURCE / name).read_bytes())
    protocol = {"schema": "ics_v3_network_full_cycle_v1", "mode": mode, "scene": scene_name,
        "prior": str(Path(prior).resolve()), "prior_manifest_sha256": file_sha(Path(prior) / "manifest.json"),
        "source_sha256": hashes, "original_request_count": 2176, "selected_request_count": len(rows),
        "all_original_samples": [s["entry"] for s in samples.values()],
        "selection": "all2176 requests; pilot first actual continuation per scene, allK4 and saved g0/draw0",
        "controller": "unchanged exact original cursor/cache; timed planning180/K4/search3000/slow period2",
        "futures": "original4x8 saved tapes verbatim, evaluator only; no policy truth access",
        "old80": "exact all RolloutResult fields except policy_stats.*_ms; mismatch stops before longer evaluation",
        "termination": "entire initial+future ledger complete, no arrivals/plans/targets/nonempty trays/transport reservations/transit; valid idle current-node INFINITY stock occupancy retained separately; all forecast publications past original TTL; stable through full actual slow period and actual trigger",
        "tick_cap": "max(start+80,last tape arrival,last forecast publication+TTL+1)+720; unresolved is censored",
        "fixed_endpoints": "start+80, max(start+80,last arrival), latter+180/+360, final cap; save only actually reached endpoints",
        "branch_budget": asdict(SearchBudget(1000, 1000000, 180.)), "tail_cap": 720,
        "cpu_limit": cpu_limit, "wall_limit": wall_limit,
        "shard_index": shard_index, "shard_count": shard_count,
        "sharding": "sorted unique(sample,candidate,full future SHA) modulo count; all requests in one exact memo class stay together",
        "resource_scope": "per scene invocation includes setup/recollection/serialization; cooperative checks between branches/searches/ticks",
        "new_independent_source_count": 0}
    write_new_json(output / "protocol.json", protocol)
    write_new_json(output / "requested_rows.json", rows)
    outcomes, comparisons, failures = [], [], []
    collection = None
    memo = {}
    attempt_count = 0
    try:
        network, topology = load_network(primary / scene_name / "original_profile.json")
        scene = make_workload(scene_name, network, topology, rounds=3)
        saved_input = read(primary / scene_name / (scene_name + "_input.json"))
        current_input = json.loads(json.dumps({"initial": asdict(scene.initial), "forecasts": [asdict(f) for f in scene.forecasts],
            "future_engine_only": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon}))
        if any(current_input[k] != saved_input[k] for k in current_input):
            raise ValueError("original nominal physical/tape/publication inputs changed")
        collection = collect_network_decisions(scene)
        write_new_json(output / "collection.json", {"metadata": collection["metadata"],
            "opportunities": collection["opportunities"], "result": None if collection["result"] is None else asdict(collection["result"])})
        current = {s["identity"]: s for s in collection["samples"]}
        expected_samples = {k: s for k, s in samples.items() if s["scene"] == scene_name}
        if set(current) != set(expected_samples):
            raise ValueError("all original real/zero candidate cells must recollect")
        for index, (identity, old) in enumerate(expected_samples.items()):
            sample = current[identity]
            folder = output / f"s{index:02d}"
            folder.mkdir()
            comparison = exact_decision(old["saved"], sample)
            pending = [asdict(b) for group in sample["checkpoint"].base.pending_arrivals.values() for b in group]
            expected_pending = [b for b in saved_input["future_engine_only"]
                                if b["arrival"] > sample["time"] and b["bag_id"] not in sample["checkpoint"].state.bags]
            comparison["private_nominal_tape_equal"] = sorted(pending, key=lambda b: b["bag_id"]) == sorted(expected_pending, key=lambda b: b["bag_id"])
            comparison["equal"] &= comparison["private_nominal_tape_equal"]
            comparisons.append({"identity": identity, **comparison})
            write_new_json(folder / "sample.json", sample_artifact(sample))
            write_new_json(folder / "comparison.json", comparison)
            if not comparison["equal"]:
                raise ValueError("strict original decision recollection mismatch: " + identity)
            local_rows = [r for r in rows if r["sample"] == identity]
            for row in local_rows:
                clean = {k: row[k] for k in ("request_key", "scene", "sample", "candidate", "group", "draw", "future_sha256")}
                key = memo_key(row)
                if key in memo:
                    outcomes.append({**memo[key], **clean, "cache_hit": True, "physical_call": False,
                                     "cpu_seconds": 0., "wall_seconds": 0.})
                    continue
                if process_time() - cpu >= cpu_limit or perf_counter() - start >= wall_limit:
                    outcomes.append({**clean, "status": "not_executed", "reason": "scene_resource_cap",
                                     "physical_call": False, "cache_hit": False})
                    continue
                outcome = None
                physical_call_started = False
                attempt_start, attempt_cpu = perf_counter(), process_time()
                try:
                    with gzip.open(row["file"], "rt", encoding="utf-8") as stream:
                        old_result = json.load(stream)["result"]
                    raw_tape = old["label"]["future_groups_offline_only"][row["group"]]["tapes"][row["draw"]]
                    attempt_count += 1
                    physical_call_started = True
                    outcome = branch_full_cycle(sample["checkpoint"], sample["pool"][row["candidate"]],
                        tuple(Bag(**b) for b in raw_tape), old_result=old_result)
                    target = folder / f"b{attempt_count:04d}.json.gz"
                    with gzip.open(target, "xt", encoding="utf-8") as stream:
                        json.dump({"request": clean, "old80_file": row["file"], "old80_file_sha256": file_sha(row["file"]),
                            **outcome, "result": None if outcome["result"] is None else asdict(outcome["result"])},
                            stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    result = outcome["result"]
                    value = {**clean, "status": outcome["status"], "physical_call": True, "cache_hit": False,
                        "file": str(target.resolve()), "artifact_sha256": file_sha(target),
                        "physical_call_request_key": row["request_key"],
                        "old80_equal": outcome["old80_comparison"] is not None and outcome["old80_comparison"]["equal"],
                        "task_complete": outcome["last_cycle_state"]["task_complete"],
                        "transport_drained": outcome["last_cycle_state"]["transport_drained"],
                        "stopped_at": outcome["stopped_at"], "total_cost": None if result is None else result.total_cost,
                        "cost_components": None if result is None else result.cost_components,
                        "milestone_times": {k: v["time"] for k, v in outcome["milestones"].items()},
                        "cpu_seconds": process_time() - attempt_cpu, "wall_seconds": perf_counter() - attempt_start,
                        "search_calls": outcome["search_calls"], "search_work": outcome["search_work"]}
                    memo[key] = value
                    outcomes.append(value)
                except Exception as exc:
                    value = {**clean, "status": "attempt_failure", "physical_call": physical_call_started,
                        "cache_hit": False, "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(),
                        "physical_outcome": None if outcome is None else {**outcome, "result": None if outcome["result"] is None else asdict(outcome["result"])},
                        "cpu_seconds": process_time() - attempt_cpu, "wall_seconds": perf_counter() - attempt_start}
                    failures.append(value)
                    outcomes.append(value)
            write_new_json(folder / "rows.json", [r for r in outcomes if r["sample"] == identity])
            print(json.dumps({"scene": scene_name, "sample": identity, **summarize_rows(outcomes)}), flush=True)
    except Exception as exc:
        failures.append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        done = {r["request_key"] for r in outcomes}
        outcomes.extend({"request_key": r["request_key"], "sample": r["sample"], "scene": r["scene"],
            "status": "not_executed", "reason": "setup_or_recollection_failure"} for r in rows if r["request_key"] not in done)
    unchanged = hashes == {n: file_sha(SOURCE / n) for n in SOURCES}
    try:
        load_inputs(prior)
        input_unchanged, input_failure = True, None
    except Exception as exc:
        input_unchanged, input_failure = False, {"type": type(exc).__name__, "message": str(exc)}
    summary = {**summarize_rows(outcomes), "mode": mode, "scene": scene_name, "rows": outcomes,
        "recollection_comparisons": comparisons, "failures": failures, "source_unchanged": unchanged,
        "input_unchanged": input_unchanged, "input_failure": input_failure,
        "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - start,
        "memory_before": memory, "memory_after": memory_snapshot(),
        "collection_metadata": None if collection is None else collection["metadata"]}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "manifest.json", {p.relative_to(output).as_posix(): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def run(prior, output, *, mode="pilot", workers=3, cpu_limit=14400., wall_limit=21600., shards=6):
    if workers not in range(1, 9) or shards not in (6, 8) or any(not 0 < v < float("inf") for v in (cpu_limit, wall_limit)):
        raise ValueError("one-to-eight workers,6/8 formal shards and finite positive unit budgets required")
    started, cpu = perf_counter(), process_time()
    primary, samples, all_rows = load_inputs(prior)
    rows = selected_requests(samples, all_rows, mode)
    output = create_output_directory(output)
    hashes = {n: file_sha(SOURCE / n) for n in SOURCES}
    unit_count = 3 if mode == "pilot" else shards
    write_new_json(output / "protocol.json", {"mode": mode, "workers": workers, "original_cells": 18,
        "original_requests": 2176, "selected_request_count": len(rows), "source_sha256": hashes,
        "units": unit_count, "per_unit_cpu_limit": cpu_limit, "per_unit_wall_limit": wall_limit,
        "total_cpu_safeguard": unit_count * cpu_limit, "new_independent_source_count": 0,
        "allocation": "pilot3scenes; formal sorted unique(sample,candidate,full future SHA) modulo6/8 with each memo class intact",
        "prior_manifest_sha256": file_sha(Path(prior) / "manifest.json")})
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((SOURCE / name).read_bytes())
    tests = ("test_ics_circulation_v3_network_full_cycle.py", "test_ics_circulation_v3_network_full_cycle_audit.py")
    test_hashes = {name: file_sha(ROOT / "tests" / name) for name in tests}
    (output / "test_snapshot").mkdir()
    for name in tests:
        (output / "test_snapshot" / name).write_bytes((ROOT / "tests" / name).read_bytes())
    write_new_json(output / "test_manifest.json", test_hashes)
    if mode == "full":
        write_new_json(output / "assignment.json", [{"index": i,
            "request_keys": [r["request_key"] for r in shard_requests(rows, i, shards)],
            "unique_keys": [list(k) for k in sorted({memo_key(r) for r in shard_requests(rows, i, shards)})]}
            for i in range(shards)])
    summaries, failures = {}, []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = ({pool.submit(_scene_worker, (str(prior), str(output / scene), scene, mode, cpu_limit, wall_limit)): scene for scene in SCENES}
                if mode == "pilot" else
                {pool.submit(_shard_worker, (str(prior), str(output / f"u{i:02d}"), i, shards, cpu_limit, wall_limit)): f"shard{i}" for i in range(shards)})
        for task in as_completed(jobs):
            try:
                scene, summary = task.result()
                summaries[scene] = summary
            except Exception as exc:
                failures.append({"scene": jobs[task], "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    results = [r for key in sorted(summaries) for r in summaries[key]["rows"]]
    seen = {r["request_key"] for r in results}
    results.extend({"request_key": r["request_key"], "scene": r["scene"], "sample": r["sample"],
        "status": "not_executed", "reason": "worker_failure"} for r in rows if r["request_key"] not in seen)
    summary = {**summarize_rows(results), "rows": results, "worker_failures": failures,
        "scene_summaries": {k: {n: v for n, v in s.items() if n != "rows"} for k, s in summaries.items()},
        "source_unchanged": hashes == {n: file_sha(SOURCE / n) for n in SOURCES}
            and all(s["source_unchanged"] for s in summaries.values()),
        "input_unchanged": all(s["input_unchanged"] for s in summaries.values()),
        "tests_unchanged": test_hashes == {n: file_sha(ROOT / "tests" / n) for n in tests},
        "complete_resource_accounting": not failures and all(s.get("complete_resource_accounting", True) for s in summaries.values()),
        "worker_cpu_seconds_sum": sum(s["cpu_seconds"] for s in summaries.values()),
        "parent_cpu_seconds": process_time() - cpu, "wall_makespan_seconds": perf_counter() - started}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "manifest.json", {p.relative_to(output).as_posix(): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, default=DEFAULT_PRIOR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--scene", choices=SCENES)
    parser.add_argument("--cpu-limit", type=float, default=14400.)
    parser.add_argument("--wall-limit", type=float, default=21600.)
    args = parser.parse_args(argv)
    kwargs = {"mode": args.mode, "cpu_limit": args.cpu_limit, "wall_limit": args.wall_limit}
    result = (run_scene(args.prior, args.output, args.scene, **kwargs) if args.scene else
              run(args.prior, args.output, workers=args.workers, shards=args.shards, **kwargs))
    print(json.dumps({k: result[k] for k in ("request_count", "status_counts", "actual_branches", "cache_reused", "old80_matches", "source_unchanged")}), flush=True)
    return int(not result["source_unchanged"] or any(r["status"] != "controller_quiescent" for r in result["rows"]))


if __name__ == "__main__":
    raise SystemExit(main())
