"""Frozen real-checkpoint collection and complete-cycle same-zone labels."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
import pickle
from time import perf_counter, process_time
import traceback

from .experiment_protocol import create_output_directory, write_new_json
from .experiment_resources import memory_snapshot
from .network_full_cycle import compare_old_result
from .network_role_labels import SPEC, bind_accounting, observed_role
from .phase4_control import build_engine
from .phase4_network_workloads import file_sha
from .role_coverage import CursorSimulation, digest
from .routing_cache_contract import enable_replay_cache, routing_cache_state
from .run_same_zone_supply import (ROOT, SOURCE, BASE, PRIMARY, NOMINAL, SCENES, read,
    write_gzip, exact_original_scene, exact_json_value, verify as verify_supply)
from .same_zone_experiment import install_supply_policy
from .same_zone_labels import (METHOD, LABEL_BUDGET, COLLECTION_BUDGET, TAIL_CAP,
    active_continuation_binding, checkpoint_metadata, validate_checkpoint_binding, pending_future, run_cycle,
    run_label_branch, compare_collection, compare_normal_resume, comparison_passes)


REFERENCE = BASE / "phase4_w3_same_zone_supply_repaired_20261010"
DEFAULT_OUTPUT = BASE / "phase4_w3_same_zone_labels_20261010"
OLD12 = (19, 20, 21, 22, 23, 40, 41, 42, 43, 46, 48, 50)


def reference_path(scene):
    return REFERENCE / "full" / f"{scene}__nominal__{METHOD}.json.gz"


def failure_detail(error):
    return {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}


def prepare(output):
    started, cpu = perf_counter(), process_time()
    verify_supply(REFERENCE)
    output = create_output_directory(output)
    for stage, filenames in (("full", ["summary.json", *(reference_path(scene).name for scene in SCENES)]),
                            ("mechanism", ["summary.json", *(f"counterflow_d0040_c{i}__{METHOD}.json.gz" for i in (0, 1))])):
        manifest = read(REFERENCE / stage / "manifest.json")
        for name in filenames:
            if file_sha(REFERENCE / stage / name) != manifest[name]:
                raise ValueError("prior audited raw/summary manifest binding failed: " + name)
    prior = read(REFERENCE / "protocol.json")
    source_names = set(prior["source_sha256"]) | {"same_zone_labels.py", "run_same_zone_labels.py", "same_zone_query_probe.py"}
    test_names = set(prior["test_sha256"]) | {"test_ics_circulation_v3_same_zone_labels.py",
        "test_ics_circulation_v3_same_zone_labels_audit.py", "test_ics_circulation_v3_same_zone_query_probe.py"}
    source = {name: file_sha(SOURCE / name) for name in sorted(source_names)}
    tests = {name: file_sha(ROOT / "tests" / name) for name in sorted(test_names)}
    paths = [REFERENCE / "protocol.json", REFERENCE / "preparation_manifest.json",
        REFERENCE / "full/summary.json", REFERENCE / "full/manifest.json",
        REFERENCE / "mechanism/summary.json", REFERENCE / "mechanism/manifest.json",
        NOMINAL / "collection_reuse_manifest.json", ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp"]
    paths += [reference_path(scene) for scene in SCENES]
    paths += [REFERENCE / "mechanism" / f"counterflow_d0040_c{i}__{METHOD}.json.gz" for i in (0, 1)]
    paths += [NOMINAL / "collections/counterflow" / f"d{index:04d}.{suffix}" for index in OLD12 for suffix in ("json", "pkl")]
    # Include every original source bound by the prior preparation, independently
    # of recursively reading its manifest during the later immutable checks.
    paths += [Path(p) for p in read(REFERENCE / "protocol.json")["input_sha256"]]
    inputs = {str(path.resolve()): file_sha(path) for path in paths}
    reference_counts = {}
    for scene in SCENES:
        raw = read(reference_path(scene))
        opportunities = raw["opportunities"]
        reference_counts[scene] = {"attempts": len(opportunities),
            "zero": sum(r["candidate_count"] == 0 for r in opportunities),
            "nonempty": sum(r["candidate_count"] > 0 for r in opportunities),
            "candidates": sum(r["candidate_count"] for r in opportunities)}
    for kind, items, directory in (("source", source, SOURCE), ("test", tests, ROOT / "tests")):
        folder = output / (kind + "_snapshot")
        folder.mkdir()
        for name in items:
            (folder / name).write_bytes((directory / name).read_bytes())
    protocol = {"schema": "ics_v3_same_zone_exact_labels_v1", "method": METHOD,
        "source_sha256": source, "test_sha256": tests, "input_sha256": inputs,
        "reference": str(REFERENCE), "reference_counts_observed_not_hardcoded": reference_counts,
        "scene_names": list(SCENES), "spec": asdict(SPEC), "collection_workers": 3, "label_workers": 6,
        "collection_budget": asdict(COLLECTION_BUDGET), "label_budget": asdict(LABEL_BUDGET), "tail_cap": TAIL_CAP,
        "collection_contract": "reconstruct exact original nominal initial/forecasts/future; install frozen new supply policy; every actual loaded generation callback clones full checkpoint immediately; private replay cache and cursor retained; zero attempts retained",
        "collection_replication": "original absolute endpoint; every result field except measured policy_stats *_ms, all search rows/private cache/loaded opportunities/physical tick and event traces/selector history/actual slow clocks match prior formal nominal",
        "query_probe": "complete actual query public Snapshot (including slow scratch), parameters, raw options, diagnostics and cache; authorization callback pool is a possibly strict subset of raw pool; observer is stripped by deepcopy/pickle and cannot receive future tape",
        "pilot_selection": "first nonempty actual attempt of each scene plus first counterflow continuation not already chosen; all its original candidates; outcome blind",
        "normal_resume_selection": "same pilot checkpoints plus first zero attempt in each scene, if any; no forced choice; common absolute prior collection stopped_at; strict suffix replication",
        "full_selection": "every original candidate from every newly collected nonempty attempt; all zeros remain attempts denominator; no sample, successful-run filter or cross-method memo",
        "historical_selection": {"scene": "counterflow", "decision_indices": list(OLD12),
            "scope": "all twelve previously audited nonoptimal old-policy states; explicitly posthoc historical subgroup, not new-policy on-policy coverage or training",
            "intervention": "same old state/cursor/privatecache/pool; replace only future inner slow policy; original clock/publications remain; all original candidates"},
        "evaluation": "all initial observed and exact pending nominal bags must arrive and complete; transport drain then all original forecast publication TTLs expired plus full actual slow period/trigger; earliest milestones separate from min endpoint checkpoint+80",
        "censoring": "finite call/work/wall/tick cap is censored, never mathematical infeasibility; unrun requests remain explicit denominator",
        "information": "future only event engine and evaluation ledger; unchanged original publication gates",
        "source_scope": "three reused synthetic original-graph development streams, zero new independent operational sources; conditional regrets across states are not additive deployment gains",
        "resource_scope": "worker invocation includes setup, physical loop and serialization; loop CPU nested; pilot/formal repeated separately; no physical memo",
        "preparation_cpu_seconds": process_time() - cpu, "preparation_wall_seconds": perf_counter() - started}
    write_new_json(output / "protocol.json", protocol)
    write_new_json(output / "input_manifest.json", inputs)
    write_new_json(output / "preparation_manifest.json", {str(p.relative_to(output)): file_sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return protocol


def verify(output):
    output = Path(output)
    protocol = read(output / "protocol.json")
    for name, expected in read(output / "preparation_manifest.json").items():
        if file_sha(output / name) != expected:
            raise ValueError("frozen preparation changed: " + name)
    for key, directory in (("source_sha256", SOURCE), ("test_sha256", ROOT / "tests")):
        for name, expected in protocol[key].items():
            if file_sha(directory / name) != expected:
                raise ValueError("frozen source/test changed: " + name)
    for path, expected in protocol["input_sha256"].items():
        if file_sha(path) != expected:
            raise ValueError("frozen input changed: " + path)
    return protocol


def freeze_checkpoint(output, scene, index, checkpoint, *, extra=None):
    """Trusted local pickle bound by SHA, plus independently readable bindings."""
    folder = Path(output) / "collections" / scene
    folder.mkdir(parents=True, exist_ok=True)
    metadata = checkpoint_metadata(checkpoint)
    engine = CursorSimulation.from_checkpoint(checkpoint)
    future = pending_future(engine)
    payload = {"checkpoint": checkpoint, "pool": tuple(checkpoint.cursor.pending_options), "future": future}
    path = folder / f"d{index:04d}.pkl"
    with path.open("xb") as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
    metadata.update({"scene": scene, "decision_index": index,
        "checkpoint_file": str(path.relative_to(output)), "checkpoint_sha256": file_sha(path), **(extra or {})})
    meta_path = folder / f"d{index:04d}.json"
    write_new_json(meta_path, metadata)
    return metadata, str(meta_path.relative_to(output)), file_sha(meta_path)


def collect_scene(output, scene_name):
    from .same_zone_query_probe import install_query_probe
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    folder = output / "collections" / scene_name
    folder.mkdir(parents=True, exist_ok=True)
    outcome, physical_started, attempts = None, False, []
    query_index, query_rows, active_binding = [], [], None

    def save_queries():
        queries = folder / "queries"
        queries.mkdir(exist_ok=True)
        for index in range(len(query_index), len(query_rows)):
            path = queries / f"q{index:05d}.pkl"
            with path.open("xb") as stream:
                pickle.dump(query_rows[index], stream, protocol=pickle.HIGHEST_PROTOCOL)
            query_index.append({"ordinal": index, "file": str(path.relative_to(output)), "sha256": file_sha(path),
                "public_snapshot_sha256": query_rows[index].get("public_snapshot_sha256"),
                "active_continuation_sha256": None if active_binding is None else active_binding["sha256"]})
    try:
        verify(output)
        scene = exact_original_scene(scene_name)
        base = build_engine(scene.initial, scene.forecasts, scene.future_bags, SPEC)
        enable_replay_cache(base)
        engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
        install_supply_policy(engine, METHOD)
        active_binding = active_continuation_binding(engine)
        owner = bind_accounting(engine, COLLECTION_BUDGET)
        install_query_probe(engine, query_rows)

        def capture(current, tray, options, row, accounting):
            # Probe wrappers drop their observer in deepcopy. This clones the
            # underlying Budget owner/cache graph with one shared deepcopy memo.
            index = len(attempts)
            attempt = {"scene": scene_name, "decision_index": index,
                "identity": f"{scene_name}:{METHOD}:d{index}:t{row['time']}:{row['bag_id']}:{row['node']}",
                **{k: row[k] for k in ("time", "version", "node", "bag_id", "tray_id", "protected", "candidate_count")},
                "role": observed_role(current.state, tray), "capture_status": "entered"}
            attempts.append(attempt)
            checkpoint = current.checkpoint().clone()
            metadata, path, sha = freeze_checkpoint(output, scene_name, index, checkpoint,
                extra={"search_prefix_count": len(accounting.rows),
                    "selector_prefix_count": len(current.route_selector.history),
                    "trace_prefix_count": len(current._trace),
                    "query_prefix_count": len(query_rows), "loaded_query_ordinal": len(query_rows) - 1})
            attempt.update({"capture_status": "saved", "metadata_file": path, "metadata_sha256": sha,
                "checkpoint_file": metadata["checkpoint_file"], "checkpoint_sha256": metadata["checkpoint_sha256"],
                "candidate_keys": metadata["candidate_keys"], "future_sha256": metadata["future_sha256"],
                "continuation_sha256": metadata["active_continuation"]["sha256"]})

        physical_started = True
        outcome = run_cycle(engine, {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}},
            minimum_observation_at=scene.horizon, budget=COLLECTION_BUDGET, owner=owner,
            capture=capture, retain_physical_ticks=True)
        save_queries()
        comparison = None if outcome["result"] is None else compare_collection(read(reference_path(scene_name)), outcome)
        selections = iter(outcome["selector_history_suffix"])
        for attempt, opportunity in zip(attempts, outcome["opportunities"]):
            if attempt["candidate_count"]:
                selected = next(selections)
                if not exact_json_value(selected["candidates"], opportunity["candidates"]):
                    raise ValueError("actual selector pool differs from captured attempt")
                attempt["actual_chosen_index"] = next(i for i, value in enumerate(opportunity["candidates"])
                                                       if exact_json_value(value, selected["chosen"]))
            else:
                attempt["actual_chosen_index"] = None
        if next(selections, None) is not None:
            raise ValueError("uncaptured selector opportunity")
        write_gzip(folder / "collection.json.gz", {"scene": scene_name, "attempts": attempts,
            "active_continuation": active_binding, "query_index": query_index, "replication": comparison, **outcome})
        verify(output)
        return {"scene": scene_name, "status": outcome["status"] if comparison is None or comparison_passes(comparison) else "replication_mismatch",
            "replication": comparison, "attempts": len(attempts), "zero": sum(r["candidate_count"] == 0 for r in attempts),
            "nonempty": sum(r["candidate_count"] > 0 for r in attempts), "candidates": sum(r["candidate_count"] for r in attempts),
            "query_records": len(query_rows), "actual_physical_call": physical_started,
            "search_calls": outcome["search_calls"], "search_work": outcome["search_work"],
            "file": str((folder / "collection.json.gz").relative_to(output)),
            "sha256": file_sha(folder / "collection.json.gz"), "invocation_cpu_seconds": process_time() - cpu,
            "invocation_wall_seconds": perf_counter() - started, "memory": memory_snapshot()}
    except Exception as error:
        failure = {"scene": scene_name, "status": "invocation_failure", "failure": failure_detail(error),
            "actual_physical_call": physical_started, "attempts_retained": len(attempts), "query_records": len(query_rows),
            "memory": memory_snapshot()}
        # A failed query serializer may have left qNNNNN.pkl partial. Never
        # retry the same exclusive path; independently retain the entire live
        # query list and physical outcome before attempting a failure receipt.
        recovery_errors = []
        try:
            write_new_json(folder / "recovery.json", {"outcome": outcome, "attempts": attempts,
                "query_index": query_index, "failure": failure["failure"]})
            failure["recovered_outcome_file"] = str((folder / "recovery.json").relative_to(output))
        except Exception as recovery:
            recovery_errors.append({"kind": "outcome", **failure_detail(recovery)})
        try:
            with (folder / "queries.recovery.pkl").open("xb") as stream:
                pickle.dump(query_rows, stream, protocol=pickle.HIGHEST_PROTOCOL)
            failure["recovered_queries_file"] = str((folder / "queries.recovery.pkl").relative_to(output))
        except Exception as recovery:
            recovery_errors.append({"kind": "queries", **failure_detail(recovery)})
        failure.update(recovery_errors=recovery_errors,
            invocation_cpu_seconds=process_time() - cpu, invocation_wall_seconds=perf_counter() - started)
        write_new_json(folder / "failure.json", failure)
        return failure


def load_payload(output, row):
    output = Path(output)
    path, metadata_path = output / row["checkpoint_file"], output / row["metadata_file"]
    if file_sha(path) != row["checkpoint_sha256"] or file_sha(metadata_path) != row["metadata_sha256"]:
        raise ValueError("trusted local checkpoint/metadata changed")
    metadata = read(metadata_path)
    with path.open("rb") as stream:
        payload = pickle.load(stream)
    validate_checkpoint_binding(payload["checkpoint"], metadata)
    return payload, metadata


def prepare_historical(output):
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    verify(output)
    rows = []
    reuse = read(NOMINAL / "collection_reuse_manifest.json")
    for index in OLD12:
        old_meta = read(NOMINAL / "collections/counterflow" / f"d{index:04d}.json")
        path = NOMINAL / old_meta["checkpoint_file"]
        if file_sha(path) != old_meta["checkpoint_sha256"] or file_sha(path) != reuse["files"][old_meta["checkpoint_file"]]:
            raise ValueError("historical source checkpoint changed")
        with path.open("rb") as stream:
            payload = pickle.load(stream)
        engine = CursorSimulation.from_checkpoint(payload["checkpoint"])
        before = {"state": digest(asdict(engine.state)), "cursor": asdict(engine._cursor),
                  "clock": engine.slow_controller.next_trigger_at, "cache": routing_cache_state(engine)}
        if before["state"] != old_meta["state_sha256"] or not exact_json_value(before["cache"], old_meta["routing_cache"]):
            raise ValueError("historical state/cache source binding failed")
        install_supply_policy(engine, METHOD)
        after = {"state": digest(asdict(engine.state)), "cursor": asdict(engine._cursor),
                 "clock": engine.slow_controller.next_trigger_at, "cache": routing_cache_state(engine)}
        if not exact_json_value(before, after):
            raise ValueError("controller replacement changed physical checkpoint")
        meta, meta_path, meta_sha = freeze_checkpoint(output, "historical_counterflow", index, engine.checkpoint().clone(),
            extra={"historical_source_file": str(path), "historical_source_sha256": file_sha(path),
                   "historical_scope": "posthoc old-policy subgroup with explicit slow continuation replacement"})
        for candidate in range(len(meta["candidates"])):
            rows.append({"request_key": f"historical_counterflow_d{index:04d}_c{candidate}", "scene": "counterflow",
                "decision_index": index, "candidate": candidate, "mode": "forced", "cohort": "historical_old12",
                "metadata_file": meta_path, "metadata_sha256": meta_sha,
                "checkpoint_file": meta["checkpoint_file"], "checkpoint_sha256": meta["checkpoint_sha256"],
                "future_sha256": meta["future_sha256"], "continuation_sha256": meta["active_continuation"]["sha256"]})
    write_new_json(output / "historical_requested_rows.json", rows)
    verify(output)
    write_new_json(output / "historical_preparation.json", {"rows": len(rows), "checkpoints": len(OLD12),
        "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - started,
        "actual_physical_calls": 0, "source_input_test_unchanged": True,
        "files": {str(p.relative_to(output)): file_sha(p)
                  for p in sorted((output / "collections/historical_counterflow").glob("*")) if p.is_file()}})
    return rows


def requested_rows(output, stage):
    output = Path(output)
    if stage == "old12":
        return read(output / "historical_requested_rows.json")
    rows = []
    for scene in SCENES:
        collection = read(output / "collections" / scene / "collection.json.gz")
        if collection["status"] != "controller_quiescent" or not comparison_passes(collection["replication"]):
            raise ValueError("cannot label a failed/mismatching collection")
        attempts = collection["attempts"]
        selected = {next(r["decision_index"] for r in attempts if r["candidate_count"])}
        if scene == "counterflow":
            selected.add(next(r["decision_index"] for r in attempts if r["candidate_count"] and r["role"] == "continuation"))
        if stage == "normal_resume":
            zero = next((r["decision_index"] for r in attempts if r["candidate_count"] == 0), None)
            if zero is not None:
                selected.add(zero)
        for attempt in attempts:
            if stage != "full" and attempt["decision_index"] not in selected:
                continue
            choices = (None,) if stage == "normal_resume" else range(attempt["candidate_count"])
            for candidate in choices:
                rows.append({**attempt, "candidate": candidate, "mode": "normal" if candidate is None else "forced",
                    "cohort": "new_policy_onpolicy", "request_key": f"{scene}_d{attempt['decision_index']:04d}_" +
                        ("normal" if candidate is None else f"c{candidate}"),
                    "minimum_observation_at": collection["stopped_at"] if candidate is None else attempt["time"] + 80})
    return rows


def evaluate(output, stage, row):
    started, cpu = perf_counter(), process_time()
    output = Path(output)
    target = output / stage / (row["request_key"] + ".json.gz")
    physical_started, outcome, metadata, comparison = False, None, None, None
    try:
        verify(output)
        payload, metadata = load_payload(output, row)
        physical_started = True
        outcome = run_label_branch(payload, metadata, forced_index=row["candidate"],
                                  minimum_observation_at=row.get("minimum_observation_at"))
        if row["mode"] == "normal" and outcome["result"] is not None:
            comparison = compare_normal_resume(read(reference_path(row["scene"])), outcome, metadata)
        elif row["cohort"] == "historical_old12" and row["decision_index"] == 40 and row["candidate"] in (0, 1) and outcome["result"] is not None:
            prior = read(REFERENCE / "mechanism" / f"counterflow_d0040_c{row['candidate']}__{METHOD}.json.gz")
            comparison = {"result": compare_old_result(prior["result"], outcome["result"]),
                "searches": exact_json_value(prior["searches"], outcome["searches"]),
                "cache_before": exact_json_value(prior["cache_before"], outcome["cache_before"]),
                "cache_after": exact_json_value(prior["cache_after"], outcome["cache_after"]),
                "stopped_at": prior["stopped_at"] == outcome["stopped_at"],
                "h80": compare_old_result(prior["original_endpoint"]["result"], outcome["original_endpoint"]["result"])}
        write_gzip(target, {"request": row, "checkpoint_metadata": metadata, "replication": comparison, **outcome})
        verify(output)
        result, ledger = outcome["result"], outcome["evaluation_ledger"]
        return {**row, "status": outcome["status"] if comparison is None or comparison_passes(comparison) else "replication_mismatch",
            "replication": comparison, "actual_physical_call": physical_started,
            "file": str(target.relative_to(output)), "sha256": file_sha(target),
            "total_cost": None if result is None else result["total_cost"],
            "cost_components": None if result is None else result["cost_components"], "stopped_at": outcome["stopped_at"],
            "task_count": len(ledger), "observed": sum(r["observed"] for r in ledger),
            "completed": sum(r["completed_at"] is not None for r in ledger),
            "protected_expected": sum(r["protected"] for r in ledger),
            "protected_on_time": sum(r["protected"] and r["completed_at"] is not None and r["completed_at"] <= r["deadline"] for r in ledger),
            "search_calls": outcome["search_calls"], "search_work": outcome["search_work"],
            "invocation_cpu_seconds": process_time() - cpu, "invocation_wall_seconds": perf_counter() - started,
            "memory": memory_snapshot()}
    except Exception as error:
        failure = {**row, "status": "invocation_failure", "failure": failure_detail(error),
            "actual_physical_call": physical_started, "retained_raw_file": str(target.relative_to(output)) if target.exists() else None,
            "physical_result_status": None if outcome is None else outcome["status"],
            "memory": memory_snapshot()}
        if outcome is not None:
            try:
                write_new_json(target.with_suffix(".recovery.json"), {"request": row, "checkpoint_metadata": metadata,
                    "replication": comparison, "outcome": outcome, "failure": failure["failure"]})
                failure["recovered_outcome_file"] = str(target.with_suffix(".recovery.json").relative_to(output))
            except Exception as recovery:
                failure["recovery_error"] = failure_detail(recovery)
        failure.update(invocation_cpu_seconds=process_time() - cpu, invocation_wall_seconds=perf_counter() - started)
        write_new_json(target.with_suffix(".failure.json"), failure)
        return failure


def run(output, stage):
    started, cpu = perf_counter(), process_time()
    output = Path(output).resolve()
    protocol = verify(output)
    directory = create_output_directory(output / ("collection_run" if stage == "collect" else stage))
    rows = [{"scene": scene} for scene in SCENES] if stage == "collect" else requested_rows(output, stage)
    write_new_json(directory / "requested_rows.json", rows)
    results = []
    workers = protocol["collection_workers"] if stage == "collect" else protocol["label_workers"]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(collect_scene, output, row["scene"]) if stage == "collect" else
                pool.submit(evaluate, output, stage, row): row for row in rows}
        for job in as_completed(jobs):
            row = jobs[job]
            try:
                value = job.result()
            except Exception as error:
                value = {**row, "status": "worker_failure", "actual_physical_call": None,
                    "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "failure": failure_detail(error), "resource_scope": "worker resource unknown, never imputed zero"}
                write_new_json(directory / ((row.get("request_key") or row["scene"]) + ".worker_failure.json"), value)
            results.append(value)
            print({"stage": stage, "recorded": len(results), "planned": len(rows), "status": value["status"]}, flush=True)
    immutable_error = None
    try:
        verify(output)
    except Exception as error:
        immutable_error = failure_detail(error)
    summary = {"stage": stage, "planned_requests": len(rows), "rows": results,
        "status_counts": dict(Counter(r["status"] for r in results)),
        "actual_physical_calls_recorded": sum(r["actual_physical_call"] is True for r in results),
        "unknown_physical_call_statuses": sum(r["actual_physical_call"] is None for r in results),
        "case_invocation_cpu_seconds_recorded": sum(r["invocation_cpu_seconds"] or 0 for r in results),
        "case_wall_seconds_sum_not_makespan": sum(r["invocation_wall_seconds"] or 0 for r in results),
        "complete_resource_accounting": all(r["invocation_cpu_seconds"] is not None for r in results),
        "parent_cpu_seconds": process_time() - cpu, "wall_makespan_seconds": perf_counter() - started,
        "source_input_test_unchanged": immutable_error is None, "immutable_error": immutable_error}
    write_new_json(directory / "summary.json", summary)
    roots = [directory, output / "collections"] if stage == "collect" else [directory]
    write_new_json(directory / "manifest.json", {str(p.relative_to(output)): file_sha(p)
        for root in roots for p in sorted(root.rglob("*")) if p.is_file()})
    return int(immutable_error is not None or any(r["status"] != "controller_quiescent" for r in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", required=True,
        choices=("prepare", "collect", "historical_prepare", "normal_resume", "pilot", "full", "old12"))
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.output)
    elif args.stage == "historical_prepare":
        prepare_historical(args.output)
    else:
        raise SystemExit(run(args.output, args.stage))
