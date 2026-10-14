"""All actual original-map decisions under one preserved nominal future tape.

This is an offline diagnostic, not online oracle control, sampled-future mean,
training data split, or new independent operating source.
"""
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter, process_time
import traceback

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.experiment_protocol import write_new_json as save
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot
from scripts.experiments.ics_circulation_v3.network_full_cycle import branch_full_cycle, compare_old_result
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    SPEC, SearchBudget, bind_accounting, observed_role, physical_prefix_signature)
from scripts.experiments.ics_circulation_v3.phase4_control import build_engine, digest
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import load_network, make_workload
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache, routing_cache_state
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key
from scripts.experiments.ics_circulation_v3.run_network_full_cycle import SOURCES

CODE = ROOT / "scripts/experiments/ics_circulation_v3"
PRIOR = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w3_network_role_labels_parallel_20261009"
SCENES = ("cross_cycle", "counterflow", "near_full")


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def dump_gzip(path, value):
    with gzip.open(path, "xt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def verify_protocol():
    protocol = read(OUT / "protocol.json")
    if file_sha(__file__) != protocol["script_sha256"]:
        raise ValueError("frozen diagnostic runner changed")
    for name, expected in protocol["source_sha256"].items():
        if file_sha(CODE / name) != expected or file_sha(OUT / "source_snapshot" / name) != expected:
            raise ValueError("frozen physical/control source changed: " + name)
    for name, expected in protocol["input_sha256"].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("frozen old original input changed: " + name)
    return protocol


def collect(name):
    started, cpu = perf_counter(), process_time()
    verify_protocol()
    old_folder = PRIOR / name
    old = read(old_folder / (name + "_collection.json"))
    network, provenance = load_network(old_folder / "original_profile.json")
    scene = make_workload(name, network, provenance, rounds=3)
    prior_input = read(old_folder / (name + "_input.json"))
    new_input = json.loads(json.dumps({"initial": asdict(scene.initial),
        "forecasts": [asdict(f) for f in scene.forecasts],
        "future_engine_only": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon}))
    if any(prior_input[k] != value for k, value in new_input.items()):
        raise ValueError("original nominal input mismatch")
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, SPEC)
    enable_replay_cache(engine)
    engine = CursorSimulation.from_base_checkpoint(engine.checkpoint(), contract=engine.control_contract)
    counter = bind_accounting(engine, SearchBudget())
    attempts, requests = [], []
    directory = OUT / "collections" / name
    directory.mkdir()

    def capture(current, tray, options):
        state = current.state
        index = len(attempts)
        bag = state.bags[tray.bag_id]
        identity = f"{name}:network_timed:d{index}:t{state.now}:{bag.bag_id}:{tray.node}"
        old_row = old["opportunities"][index]
        if identity != old_row["identity"]:
            raise ValueError("actual opportunity order changed")
        geometry = [tuple(leg.edge_id for leg in ExecutionValidator._safe_prefix(state, p).legs) for p in options]
        timed = [physical_prefix_signature(state, p) for p in options]
        keys = [actual_action_key(state, p, route_mode="next_edge") for p in options]
        checkpoint = current.checkpoint().clone()
        nominal = tuple(sorted((b for bags in checkpoint.base.pending_arrivals.values() for b in bags),
                               key=lambda b: (b.arrival, b.bag_id)))
        expected_future = tuple(b for b in scene.future_bags if b.arrival > state.now and b.bag_id not in state.bags)
        if sorted((asdict(b) for b in nominal), key=lambda b: b["bag_id"]) != sorted((asdict(b) for b in expected_future), key=lambda b: b["bag_id"]):
            raise ValueError("pending nominal tape mismatch")
        row = {"identity": identity, "scene": name, "decision_index": index,
            "time": state.now, "version": state.version, "source_node": tray.node,
            "role": observed_role(state, tray), "protected": bag.protected,
            "bag_id": tray.bag_id, "tray_id": tray.tray_id, "candidate_count": len(options),
            "original_role_sample": old_row["sampled"], "cursor": asdict(checkpoint.cursor),
            "next_slow_trigger_at": current.slow_controller.next_trigger_at,
            "prefix_geometries": geometry, "prefix_geometry_distinct": len(set(geometry)),
            "timed_prefix_distinct": len(set(timed)), "actual_action_distinct": len(set(keys)),
            "actual_action_keys": keys, "timed_prefix_keys": timed,
            "full_witness_geometry_distinct": len({tuple(l.edge_id for l in p.legs) for p in options}),
            "state_sha256": digest(asdict(state)), "state": asdict(state),
            "routing_cache": routing_cache_state(current), "candidates": [asdict(p) for p in options],
            "future_event_engine_only": [asdict(b) for b in nominal], "future_sha256": digest([asdict(b) for b in nominal])}
        for key in ("time", "version", "source_node", "role", "protected", "bag_id", "tray_id", "candidate_count", "cursor", "next_slow_trigger_at"):
            if json.loads(json.dumps(row[key])) != old_row[key]:
                raise ValueError("original opportunity field mismatch: " + key)
        if options:
            path = directory / f"d{index:04d}.pkl"
            with path.open("xb") as stream:
                pickle.dump({"checkpoint": checkpoint, "pool": options, "future": nominal}, stream, protocol=5)
            row.update(checkpoint_file=str(path.relative_to(OUT)), checkpoint_sha256=file_sha(path))
            for ordinal, action in enumerate(keys):
                requests.append({"request_key": f"{name}_d{index:04d}_c{ordinal}", "scene": name,
                    "decision_index": index, "sample": identity, "candidate": ordinal,
                    "actual_action_key": action, "future_sha256": row["future_sha256"],
                    "checkpoint_file": row["checkpoint_file"], "checkpoint_sha256": row["checkpoint_sha256"]})
        attempts.append(row)

    engine._decision_callback = capture
    while engine.state.now < scene.horizon:
        counter.check()
        engine.advance(engine.state.now + 1)
    result = engine.result()
    comparison = compare_old_result(old["result"], result)
    if not comparison["equal"] or counter.rows != old["metadata"]["searches"]:
        raise ValueError("full nominal result/search ledger mismatch")
    selections = iter(engine.route_selector.history)
    for row in attempts:
        if not row["candidate_count"]:
            row["actual_chosen_index"] = None
        else:
            history = next(selections)
            if (history["time"] != row["time"] or history["version"] != row["version"]
                    or history["candidates"] != row["candidates"]):
                raise ValueError("actual selector log mismatch")
            row["actual_chosen_index"] = row["candidates"].index(history["chosen"])
        save(directory / f"d{row['decision_index']:04d}.json", row)
    if next(selections, None) is not None:
        raise ValueError("unbound actual selector decisions")
    verify_protocol()
    record = {"scene": name, "attempts": [{k: v for k, v in row.items() if k not in {"state", "candidates", "routing_cache", "future_event_engine_only"}} for row in attempts],
        "requests": requests, "result": asdict(result), "old_nominal_comparison": comparison,
        "searches": counter.rows, "search_calls": len(counter.rows), "search_work": counter.work,
        "slow_trigger_times": engine.slow_controller.trigger_times,
        "source_and_inputs_unchanged": True, "cpu_seconds": process_time()-cpu,
        "wall_seconds": perf_counter()-started, "memory": memory_snapshot()}
    dump_gzip(directory / "collection.json.gz", record)
    return {"scene": name, "attempts": len(attempts), "nonempty": sum(bool(r["candidate_count"]) for r in attempts),
        "requests": len(requests), "spatial_branching": sum(r["prefix_geometry_distinct"] > 1 for r in attempts),
        "cpu_seconds": process_time()-cpu, "wall_seconds": perf_counter()-started,
        "file": str((directory / "collection.json.gz").relative_to(OUT)), "sha256": file_sha(directory / "collection.json.gz")}


def initialize():
    started, cpu = perf_counter(), process_time()
    if (OUT / "protocol.json").exists():
        raise ValueError("existing protocol cannot be replaced")
    names = sorted(set(SOURCES))
    sources = {n: file_sha(CODE / n) for n in names}
    inputs = {str((PRIOR / scene / name).relative_to(ROOT)): file_sha(PRIOR / scene / name)
        for scene in SCENES for name in (scene+"_collection.json", scene+"_input.json", "original_profile.json", "manifest.json")}
    protocol = {"schema": "ics_v3_all_actual_nominal_full_cycle_v1", "scenes": SCENES,
        "spec": asdict(SPEC), "source_sha256": sources, "input_sha256": inputs,
        "script_sha256": file_sha(__file__), "planned_attempts": 180, "planned_nonempty": 174,
        "planned_requests": 696, "selection": "all actual original nominal attempts including six zero candidates, all normal K4; no result filtering",
        "pilot": "first actual multiple-spatial-prefix opportunity per scene, allK4, twelve additional physical branches; full run repeats pilot requests",
        "memo_key": "same actual decision checkpoint and actual_action_key and complete nominal future SHA; no cross-decision reuse",
        "continuation": "original timed/private-cache/planning180/K4/search3000/slow2/next_edge",
        "branch_budget": asdict(SearchBudget(1000,1000000,180.)), "tail_cap": 720,
        "workers": 6, "future_information": "complete original unobserved nominal tape for OFFLINE event engine only",
        "scope": "one reused nominal outcome per actual decision; no sampled-future mean, new independent source, online oracle or learning claim"}
    (OUT / "source_snapshot").mkdir()
    (OUT / "collections").mkdir()
    for name in names:
        (OUT / "source_snapshot" / name).write_bytes((CODE / name).read_bytes())
    save(OUT / "protocol.json", protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        cases = list(pool.map(collect, SCENES))
    if (sum(c["attempts"] for c in cases),sum(c["nonempty"] for c in cases),sum(c["requests"] for c in cases)) != (180,174,696):
        raise ValueError("predeclared original all-opportunity denominator changed")
    save(OUT / "collection_summary.json", {"cases": cases, "cpu_seconds_parent": process_time()-cpu,
        "wall_seconds": perf_counter()-started, "worker_cpu_seconds": sum(c["cpu_seconds"] for c in cases)})
    print(json.dumps(cases),flush=True)


def evaluate(row, stage):
    wall, cpu = perf_counter(), process_time()
    verify_protocol()
    path = OUT / row["checkpoint_file"]
    if file_sha(path) != row["checkpoint_sha256"]:
        raise ValueError("locally generated checkpoint changed")
    # The pickle is created by initialize() in this run, then SHA-bound in the
    # immutable collection; never load a user-provided or external pickle.
    with path.open("rb") as stream:
        data = pickle.load(stream)
    if digest([asdict(b) for b in data["future"]]) != row["future_sha256"]:
        raise ValueError("bound full nominal tape changed")
    outcome = branch_full_cycle(data["checkpoint"], data["pool"][row["candidate"]], data["future"])
    result = outcome["result"]
    target = OUT / stage / (row["request_key"] + ".json.gz")
    dump_gzip(target, {"request": row, **outcome, "result": None if result is None else asdict(result)})
    verify_protocol()
    return {**row, "status": outcome["status"], "actual_physical_call": True, "cache_hit": False,
        "file": str(target.relative_to(OUT)), "sha256": file_sha(target), "stopped_at": outcome["stopped_at"],
        "total_cost": None if result is None else result.total_cost,
        "cost_components": None if result is None else result.cost_components,
        "completed": None if result is None else len(result.completed),
        "search_calls": outcome["search_calls"], "search_work": outcome["search_work"],
        "invocation_cpu_seconds": process_time()-cpu, "invocation_wall_seconds": perf_counter()-wall,
        "memory": memory_snapshot()}


def run(stage):
    started, cpu = perf_counter(), process_time()
    verify_protocol()
    rows = []
    for scene in SCENES:
        collection = read(OUT / "collections" / scene / "collection.json.gz")
        chosen = next(r["identity"] for r in collection["attempts"] if r["prefix_geometry_distinct"] > 1)
        rows.extend(r for r in collection["requests"] if stage == "full" or r["sample"] == chosen)
    (OUT / stage).mkdir()
    save(OUT / stage / "requested_rows.json", rows)
    representatives, aliases = {}, defaultdict(list)
    for row in rows:
        key = row["checkpoint_sha256"],row["actual_action_key"],row["future_sha256"]
        representatives.setdefault(key,row)
        aliases[key].append(row)
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(evaluate,row,stage): key for key,row in representatives.items()}
        for job in as_completed(jobs):
            key = jobs[job]
            representative = representatives[key]
            try:
                value = job.result()
            except Exception as error:
                target = OUT / stage / (representative["request_key"] + ".json.gz")
                value = {**representative, "status": "worker_failure", "actual_physical_call": None,
                    "cache_hit": False, "invocation_cpu_seconds": None, "invocation_wall_seconds": None,
                    "resource_accounting": "unknown after worker exception, never imputed zero",
                    "retained_physical_file": str(target.relative_to(OUT)) if target.exists() else None,
                    "failure": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}}
                save(OUT / stage / (representative["request_key"] + ".failure.json"),value)
            results.append(value)
            for alias in aliases[key][1:]:
                results.append({**value, **alias, "cache_hit": True, "actual_physical_call": False,
                    "memo_owner_request": representative["request_key"], "invocation_cpu_seconds": 0., "invocation_wall_seconds": 0.})
            if len(results) % 24 == 0 or len(results) == len(rows):
                print(json.dumps({"stage":stage,"recorded":len(results),"planned":len(rows),
                    "statuses":dict(Counter(r["status"] for r in results))}),flush=True)
    verify_protocol()
    summary = {"stage": stage, "planned_requests": len(rows), "unique_requested":len(representatives),
        "rows": sorted(results,key=lambda r:r["request_key"]), "status_counts":dict(Counter(r["status"] for r in results)),
        "actual_physical_calls_recorded":sum(r["actual_physical_call"] is True for r in results),
        "unknown_physical_call_statuses":sum(r["actual_physical_call"] is None for r in results),
        "cache_hits":sum(r["cache_hit"] for r in results),
        "case_cpu_seconds_recorded":sum(r["invocation_cpu_seconds"] or 0 for r in results),
        "case_wall_seconds_recorded":sum(r["invocation_wall_seconds"] or 0 for r in results),
        "unknown_resource_cases":sum(r["invocation_cpu_seconds"] is None for r in results),
        "parent_cpu_seconds":process_time()-cpu,"wall_makespan_seconds":perf_counter()-started,
        "sources_and_inputs_unchanged":True}
    save(OUT / stage / "summary.json",summary)
    save(OUT / stage / "manifest.json",{str(p.relative_to(OUT / stage)):file_sha(p) for p in (OUT / stage).rglob("*") if p.is_file()})
    print(json.dumps({k:summary[k] for k in ("stage","planned_requests","status_counts","case_cpu_seconds_recorded","wall_makespan_seconds")}),flush=True)
    return int(any(r["status"] != "controller_quiescent" for r in results))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("init","pilot","full"), required=True)
    stage=parser.parse_args().stage
    if stage=="init":
        initialize()
    else:
        raise SystemExit(run(stage))
