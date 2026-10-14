"""Frozen 2/8/32 nested common-future labels, with exact physical memo billing."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from time import perf_counter, process_time

from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .model import Bag
from .network_full_cycle import compare_old_result
from .phase4_network_workloads import file_sha
from .role_coverage import digest
from .run_same_zone_labels import (DEFAULT_OUTPUT as PRIOR, load_payload, failure_detail,
    verify as verify_prior)
from .run_same_zone_supply import ROOT, SOURCE, BASE, read, write_gzip, exact_json_value
from .same_zone_labels import comparison_passes, restore_matching_continuation
from .same_zone_stability import (SCENE_SEEDS, BLOCKS, SIZES, EVALUATION_CONTRACT,
    select_strata, conditional_support, block_seed, sample_conditional_futures,
    tape_sha, memo_key, run_sampled_branch)


DEFAULT_OUTPUT = BASE / "phase4_w3_same_zone_stability_20261010"
WORKERS = 6
PRIOR_REVIEW = BASE / "phase4_w3_round7_independent_review_20261010"


def bind_prior(path, manifest):
    key = str(Path(path).relative_to(PRIOR))
    if file_sha(path) != manifest[key]:
        raise ValueError("prior artifact differs from its frozen manifest: " + key)


def prepare(output):
    started, cpu = perf_counter(), process_time()
    prior_protocol = verify_prior(PRIOR)
    collected_manifest = read(PRIOR / "collection_run/manifest.json")
    full_manifest = read(PRIOR / "full/manifest.json")
    collections, input_paths = {}, [PRIOR / p for p in ("protocol.json", "preparation_manifest.json",
        "collection_run/manifest.json", "collection_run/summary.json", "full/manifest.json", "full/summary.json")]
    for stage, manifest in (("collection_run", collected_manifest), ("full", full_manifest)):
        bind_prior(PRIOR / stage / "summary.json", manifest)
    for scene in SCENE_SEEDS:
        path = PRIOR / "collections" / scene / "collection.json.gz"
        bind_prior(path, collected_manifest)
        collection = read(path)
        if collection["status"] != "controller_quiescent" or not comparison_passes(collection["replication"]):
            raise ValueError("source collection is incomplete or not exact")
        collections[scene] = collection["attempts"]
        input_paths.append(path)
    inventory = select_strata(collections)
    # Selection is complete before pending tapes are loaded or enumerated.
    output = create_output_directory(output)
    write_new_json(output / "inventory.json", inventory)
    requests, uniques, bridges, selected_details = [], {}, [], []
    for row in inventory["selected"]:
        for key in ("checkpoint_file", "metadata_file"):
            path = PRIOR / row[key]
            bind_prior(path, collected_manifest)
            input_paths.append(path)
        payload, metadata = load_payload(PRIOR, row)
        engine = restore_matching_continuation(payload, metadata)
        blocks = []
        for block in range(BLOCKS):
            seed = block_seed(row["scene"], row["decision_index"], block)
            tapes = sample_conditional_futures(engine.state, payload["future"], seed, max(SIZES))
            blocks.append({"block": block, "seed": seed, "tapes": [
                {"index": i, "sha256": tape_sha(tape), "bags": [asdict(b) for b in tape]} for i, tape in enumerate(tapes)]})
        future_path = output / "futures" / (row["state_key"] + ".json")
        future_record = {"state": row, "now": engine.state.now, "original_future_sha256": metadata["future_sha256"],
            "original_future": [asdict(b) for b in payload["future"]],
            "conditional_support": {b.bag_id: conditional_support(b, engine.state.now) for b in payload["future"]},
            "blocks": blocks}
        write_new_json(future_path, future_record)
        binding = {**row, "future_file": str(future_path.relative_to(output)), "future_file_sha256": file_sha(future_path)}
        distinct = set()
        for block in blocks:
            for future in block["tapes"]:
                distinct.add(future["sha256"])
                tape = tuple(Bag(**b) for b in future["bags"])
                for candidate, key in enumerate(metadata["candidate_keys"]):
                    memo = memo_key(row["checkpoint_sha256"], candidate, key, tape, row["continuation_sha256"])
                    request = {**binding, "block": block["block"], "future_index": future["index"],
                        "sampled_future_sha256": future["sha256"], "candidate": candidate, "candidate_key": key,
                        "request_key": f"{row['state_key']}_b{block['block']}_f{future['index']:02d}_c{candidate}",
                        "memo_key": memo, "physical_key": "p_" + memo,
                        "minimum_observation_at": row["time"] + EVALUATION_CONTRACT["minimum_offset"]}
                    requests.append(request)
                    uniques.setdefault(memo, request)
        selected_details.append({**binding, "distinct_tapes": len(distinct),
            "logical_requests": row["candidate_count"] * BLOCKS * max(SIZES),
            "unique_physical_requests": row["candidate_count"] * len(distinct),
            "pending_count": len(payload["future"]), "pending_protected": sum(b.protected for b in payload["future"])})
        if row["candidate_count"]:
            candidate = row["actual_chosen_index"]
            reference = PRIOR / "full" / f"{row['state_key']}_c{candidate}.json.gz"
            bind_prior(reference, full_manifest)
            input_paths.append(reference)
            # The endpoint belongs to the already frozen source branch, not a
            # newly observed sampled outcome.
            original = read(reference)
            bridges.append({**binding, "candidate": candidate, "bridge": True,
                "physical_key": row["state_key"] + "_original_bridge", "request_key": row["state_key"] + "_original_bridge",
                "reference_file": str(reference), "reference_sha256": file_sha(reference),
                "minimum_observation_at": original["stopped_at"]})
    input_paths += [Path(p) for p in prior_protocol["input_sha256"]]
    frozen_path = PRIOR_REVIEW / "full_validation_terminal/before.json"
    inherited_manifest = read(PRIOR_REVIEW / "manifest.json")["files_sha256"]
    if file_sha(frozen_path) != inherited_manifest[str(frozen_path.relative_to(PRIOR_REVIEW)).replace("\\", "/")]:
        raise ValueError("prior final regression source manifest changed")
    inherited = read(frozen_path)
    for path, expected in inherited.items():
        if file_sha(ROOT / path) != expected:
            raise ValueError("prior frozen source/test changed: " + path)
    source_names = {Path(p).name for p in inherited if p.startswith("scripts/")} | {
        "same_zone_stability.py", "run_same_zone_stability.py"}
    test_names = {Path(p).name for p in inherited if p.startswith("tests/")} | {
        "test_ics_circulation_v3_same_zone_stability.py", "test_ics_circulation_v3_same_zone_stability_audit.py"}
    sources = {name: file_sha(SOURCE / name) for name in sorted(source_names)}
    tests = {name: file_sha(ROOT / "tests" / name) for name in sorted(test_names)}
    input_paths += [frozen_path, PRIOR_REVIEW / "manifest.json"]
    inputs = {str(p.resolve()): file_sha(p) for p in input_paths}
    for kind, items, directory in (("source", sources, SOURCE), ("test", tests, ROOT / "tests")):
        folder = output / (kind + "_snapshot")
        folder.mkdir()
        for name in items:
            (folder / name).write_bytes((directory / name).read_bytes())
    pilot_states = {min((r for r in inventory["selected"] if r["scene"] == scene and r["candidate_count"]),
                        key=lambda r: (r["time"], r["decision_index"]))["state_key"] for scene in SCENE_SEEDS}
    pilot = [r for r in requests if r["state_key"] in pilot_states and r["block"] == 0 and r["future_index"] < 2]
    protocol = {"schema": "ics_v3_same_zone_common_future_stability_v1", "source": str(PRIOR),
        "source_sha256": sources, "test_sha256": tests, "input_sha256": inputs,
        "selection": "first actual attempt in each scene x origin/continuation x [0,40)/[40,80)/[80,infinity); zero never replaced; all zero attempts retained",
        "counts": inventory["counts"], "blocks": BLOCKS, "nested_sizes": SIZES,
        "scene_seeds": SCENE_SEEDS, "seed_formula": "scene_seed + 1000003*block + 101*decision_index; block=0,1",
        "sampling": "independent fixed PRNG blocks; per soft pending task prior cancel=3/24, each jitter=-2,0,+2 mass7/24; condition on cancel OR arrival+j>now; normalize 3+7*m; no clipping/rejection draws; protected exact, consumes no draw",
        "sampling_scope": "synthetic prior conditioned on task absence, not calibrated posterior; observed tasks fixed; original pending<=now or observed identity rejected",
        "information": "sampled tape goes only to restored cloned event queue and evaluation ledger; original forecast publication gates, active controller, cursor, private cache and actual slow clock unchanged",
        "evaluation": EVALUATION_CONTRACT, "workers": WORKERS,
        "censoring": "all finite limits yield censored evidence, not infeasibility; failure/censor remains all logical denominators and cannot be complete ranking evidence",
        "memo": "same original checkpoint SHA + candidate index and actionkey + canonical complete tape SHA + active continuation SHA + evaluation contract only; no cross-state/action reuse; unique physical resources once; duplicated future weights kept in nested estimates; censored aliases retain same censor",
        "bridge": "all selected nonempty actual choices under original tape, at original branch stopping time, full non-ms result/ledger/search/cache/events/selector/slow strict replication; separately billed",
        "pilot": "earliest selected nonempty in each scene, all candidates, block0 prefix2; independent repeated pilot, never subtracted from formal",
        "planned_logical_requests": len(requests), "planned_unique_physical": len(uniques),
        "planned_bridge_calls": len(bridges), "planned_pilot_logical": len(pilot),
        "source_scope": "three reused synthetic original-map development streams; no new independent operational data",
        "statistics_scope": "statewise paired CRN differences, nested tie-aware optimal sets, cross-block validation; scenarios are stochastic simulation draws, not independent deployment episodes; state regrets not additive gains",
        "resource_scope": "case invocation includes restore/physics/raw serialization but ends before final receipt write; nested cycle CPU not added; process imports/startup/initializer verification before timers unknown; parent final summary/manifest writes outside timer; single-worker lifetime peak is not aggregate concurrent peak",
        "preparation_cpu_seconds": process_time() - cpu, "preparation_wall_seconds": perf_counter() - started}
    for name, value in (("protocol.json", protocol), ("selected_details.json", selected_details),
        ("requested_rows.json", requests), ("unique_rows.json", list(uniques.values())),
        ("bridge_rows.json", bridges), ("pilot_rows.json", pilot)):
        write_new_json(output / name, value)
    write_new_json(output / "preparation_manifest.json", {str(p.relative_to(output)): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return protocol


def verify(output):
    output = Path(output)
    protocol = read(output / "protocol.json")
    for name, expected in read(output / "preparation_manifest.json").items():
        if file_sha(output / name) != expected:
            raise ValueError("frozen preparation changed: " + name)
    for key, root in (("source_sha256", SOURCE), ("test_sha256", ROOT / "tests")):
        for name, expected in protocol[key].items():
            if file_sha(root / name) != expected:
                raise ValueError("frozen source/test changed: " + name)
    for path, expected in protocol["input_sha256"].items():
        if file_sha(path) != expected:
            raise ValueError("frozen input changed: " + path)
    return protocol


def compare_bridge(reference, outcome):
    def nonelapsed(value):
        if isinstance(value, dict):
            return {k: nonelapsed(v) for k, v in value.items() if k != "elapsed_ms"}
        if isinstance(value, (list, tuple)):
            return [nonelapsed(v) for v in value]
        return value
    fields = ("evaluation_ledger", "cache_before", "cache_after", "searches", "search_calls", "search_work",
        "stopped_at", "event_trace_suffix", "selector_history_suffix", "actual_slow_trigger_times",
        "slow_history_suffix", "physical_tick_trace", "forced_intervention")
    return {"result": compare_old_result(reference["result"], outcome["result"]),
        **{key: exact_json_value(nonelapsed(reference[key]), nonelapsed(outcome[key])) for key in fields}}


def evaluate(output, stage, row):
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    target = output / stage / (row["physical_key"] + ".json.gz")
    outcome, binding, comparison, physical_started = None, None, None, False
    try:
        payload, binding = load_payload(PRIOR, row)
        if row.get("bridge"):
            tape = payload["future"]
        else:
            path = output / row["future_file"]
            if file_sha(path) != row["future_file_sha256"]:
                raise ValueError("saved sampled tape file changed")
            entry = read(path)["blocks"][row["block"]]["tapes"][row["future_index"]]
            tape = tuple(Bag(**b) for b in entry["bags"])
            if tape_sha(tape) != row["sampled_future_sha256"] or entry["sha256"] != row["sampled_future_sha256"]:
                raise ValueError("saved sampled tape identity mismatch")
            expected = memo_key(row["checkpoint_sha256"], row["candidate"], binding["candidate_keys"][row["candidate"]],
                tape, binding["active_continuation"]["sha256"])
            if expected != row["memo_key"]:
                raise ValueError("memo identity mismatch")
        physical_started = True  # before the branch entry; exceptions never erase physical-call uncertainty
        outcome = run_sampled_branch(payload, binding, tape, candidate_index=row["candidate"],
            minimum_observation_at=row["minimum_observation_at"])
        if row.get("bridge") and outcome["result"] is not None:
            if file_sha(row["reference_file"]) != row["reference_sha256"]:
                raise ValueError("bridge reference changed")
            comparison = compare_bridge(read(row["reference_file"]), outcome)
        write_gzip(target, {"request": row, "checkpoint_metadata": binding, "replication": comparison, **outcome})
        result, ledger = outcome["result"], outcome["evaluation_ledger"]
        receipt = {**row, "status": outcome["status"] if comparison is None or comparison_passes(comparison) else "replication_mismatch",
            "replication": comparison, "actual_physical_call": True, "file": str(target.relative_to(output)), "sha256": file_sha(target),
            "total_cost": None if result is None else result["total_cost"],
            "cost_components": None if result is None else result["cost_components"], "stopped_at": outcome["stopped_at"],
            "milestones": outcome["milestones"], "task_count": len(ledger), "observed": sum(r["observed"] for r in ledger),
            "completed": sum(r["completed_at"] is not None for r in ledger), "protected_expected": sum(r["protected"] for r in ledger),
            "protected_on_time": sum(r["protected"] and r["completed_at"] is not None and r["completed_at"] <= r["deadline"] for r in ledger),
            "search_calls": outcome["search_calls"], "search_work": outcome["search_work"],
            "nested_cycle_cpu_seconds": outcome["cpu_seconds"],
            "invocation_cpu_seconds": process_time() - cpu, "invocation_wall_seconds": perf_counter() - started,
            "memory": memory_snapshot()}
    except Exception as error:
        receipt = {**row, "status": "invocation_failure", "failure": failure_detail(error),
            "actual_physical_call": physical_started, "retained_raw_file": str(target.relative_to(output)) if target.exists() else None,
            "physical_result_status": None if outcome is None else outcome["status"], "memory": memory_snapshot()}
        if outcome is not None:
            try:
                recovery = target.with_suffix(".recovery.json")
                write_new_json(recovery, {"request": row, "checkpoint_metadata": binding, "replication": comparison,
                    "outcome": outcome, "failure": receipt["failure"]})
                receipt["recovered_outcome_file"] = str(recovery.relative_to(output))
            except Exception as recovery_error:
                receipt["recovery_error"] = failure_detail(recovery_error)
        receipt.update(invocation_cpu_seconds=process_time() - cpu, invocation_wall_seconds=perf_counter() - started)
    try:
        write_new_json(target.with_suffix(".receipt.json"), receipt)
    except Exception as receipt_error:
        # The parent still receives all already known resource/outcome evidence,
        # even if a full or partial disk write prevents a per-case receipt.
        receipt["physical_result_status"] = receipt["status"]
        receipt["status"] = "receipt_failure"
        receipt["receipt_write_failure"] = failure_detail(receipt_error)
        try:
            write_new_json(target.with_suffix(".receipt-recovery.json"), receipt)
        except Exception as recovery_error:
            receipt["receipt_recovery_failure"] = failure_detail(recovery_error)
    return receipt


def run(output, stage):
    started, cpu = perf_counter(), process_time()
    output = Path(output).resolve()
    protocol = verify(output)
    if stage == "full":
        for required in ("bridge", "pilot"):
            manifest = read(output / required / "manifest.json")
            summary_path = output / required / "summary.json"
            if file_sha(summary_path) != manifest[str(summary_path.relative_to(output))]:
                raise ValueError("required stage summary changed")
            summary = read(summary_path)
            if (len(summary["rows"]) != summary["planned_unique_physical"] or
                    not summary["source_input_test_unchanged"] or
                    any(r["status"] != "controller_quiescent" for r in summary["rows"])):
                raise ValueError("formal stage requires complete exact bridge and pilot")
    directory = create_output_directory(output / stage)
    logical = read(output / {"bridge": "bridge_rows.json", "pilot": "pilot_rows.json", "full": "requested_rows.json"}[stage])
    unique = list({r["physical_key"]: r for r in reversed(logical)}.values())
    unique.reverse()
    write_new_json(directory / "requested_rows.json", logical)
    write_new_json(directory / "unique_rows.json", unique)
    results = []
    with ProcessPoolExecutor(max_workers=protocol["workers"], initializer=verify, initargs=(output,)) as pool:
        jobs = {pool.submit(evaluate, output, stage, row): row for row in unique}
        for job in as_completed(jobs):
            row = jobs[job]
            try:
                value = job.result()
            except Exception as error:
                value = {**row, "status": "worker_failure", "actual_physical_call": None,
                    "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "failure": failure_detail(error), "resource_scope": "worker resource unknown, never imputed zero"}
                write_new_json(directory / (row["physical_key"] + ".worker_failure.json"), value)
            results.append(value)
            if len(results) % 12 == 0 or len(results) == len(unique):
                print({"stage": stage, "physical_recorded": len(results), "physical_planned": len(unique),
                    "status_counts": dict(Counter(r["status"] for r in results))}, flush=True)
    immutable_error = None
    try:
        verify(output)
    except Exception as error:
        immutable_error = failure_detail(error)
    by_key = {r["physical_key"]: r for r in results}
    resolved = [{**r, "physical_status": by_key[r["physical_key"]]["status"],
        "physical_file": by_key[r["physical_key"]].get("file"), "physical_sha256": by_key[r["physical_key"]].get("sha256"),
        "memo_alias": r["request_key"] != by_key[r["physical_key"]]["request_key"]} for r in logical]
    write_new_json(directory / "resolved_requests.json", resolved)
    summary = {"stage": stage, "planned_logical_requests": len(logical), "planned_unique_physical": len(unique),
        "rows": results, "status_counts": dict(Counter(r["status"] for r in results)),
        "logical_status_counts": dict(Counter(r["physical_status"] for r in resolved)),
        "memo_aliases": len(logical) - len(unique),
        "actual_physical_calls_recorded": sum(r["actual_physical_call"] is True for r in results),
        "unknown_physical_call_statuses": sum(r["actual_physical_call"] is None for r in results),
        "case_invocation_cpu_seconds_recorded": sum(r["invocation_cpu_seconds"] or 0 for r in results),
        "case_wall_seconds_sum_not_makespan": sum(r["invocation_wall_seconds"] or 0 for r in results),
        "complete_resource_accounting": all(r["invocation_cpu_seconds"] is not None for r in results),
        "parent_cpu_seconds": process_time() - cpu, "wall_makespan_seconds": perf_counter() - started,
        "source_input_test_unchanged": immutable_error is None, "immutable_error": immutable_error}
    write_new_json(directory / "summary.json", summary)
    write_new_json(directory / "manifest.json", {str(p.relative_to(output)): file_sha(p)
        for p in sorted(directory.rglob("*")) if p.is_file()})
    return int(immutable_error is not None or any(r["status"] != "controller_quiescent" for r in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", required=True, choices=("prepare", "bridge", "pilot", "full"))
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.output)
    else:
        raise SystemExit(run(args.output, args.stage))
