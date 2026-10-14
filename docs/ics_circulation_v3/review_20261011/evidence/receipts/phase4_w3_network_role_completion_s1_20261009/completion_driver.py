"""Complete every missing original request in a new immutable budgeted batch.

No canonical source, primary result, candidate, future tape or completed value
is changed. The missing set is selected solely by completion status.
"""
from dataclasses import asdict
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter, process_time
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.experiment_protocol import create_output_directory, write_new_json
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot
from scripts.experiments.ics_circulation_v3.model import Bag
from scripts.experiments.ics_circulation_v3.network_role_labels import SearchBudget, collect_network_decisions, branch_network_decision
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import load_network, make_workload
from scripts.experiments.ics_circulation_v3.role_coverage import digest, sample_artifact


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def request_key(row):
    return digest([row["scene"], row["sample"], row["group"], row["candidate"], row["draw"], row["horizon_ticks"]])


def memo_key(row):
    return (row["sample"], row["candidate"], row["future_sha256"], row["horizon_ticks"])


def shard_requests(missing, shard_index, shard_count):
    """Assign each whole exact memo class once, without inspecting outcome values."""
    if not 1 <= shard_count <= 4 or not 0 <= shard_index < shard_count:
        raise ValueError("shard index/count outside predeclared one-to-four domain")
    keys = sorted({memo_key(row) for row in missing})
    assignment = {key: index % shard_count for index, key in enumerate(keys)}
    selected = [row for row in missing if assignment[memo_key(row)] == shard_index]
    manifest = [{"memo_key": list(key), "shard": assignment[key],
                 "requests": [row["request_key"] for row in missing if memo_key(row) == key]} for key in keys]
    return selected, manifest


def outcome_value(row, outcome, file):
    """Replace all previous partial result fields as one coherent result."""
    result = outcome["result"]
    return {**row, "status": outcome["status"], "file": str(file.resolve()), "artifact_sha256": sha(file),
        "cache_hit": False, "original_status": row["status"], "original_file": row.get("file"),
        "original_reason": row.get("reason"), "reason": outcome.get("budget_stop"),
        "budget_stop": outcome.get("budget_stop"), "failure": outcome.get("failure"),
        "total_cost": result.total_cost if outcome["status"] == "reached_horizon" else None,
        "cost_components": result.cost_components if result is not None else None,
        "completed_bags": len(result.completed) if result is not None else None,
        "uncompleted_bags": len(result.uncompleted_bag_ids) if result is not None else None,
        "result_is_partial": outcome["status"] != "reached_horizon",
        "cpu_seconds": outcome["cpu_seconds"], "wall_seconds": outcome["wall_seconds"],
        "search_calls": outcome["search_calls"], "search_work": outcome["search_work"]}


def not_executed_value(row, reason):
    return {**row, "status": "not_executed", "reason": reason, "file": None, "cache_hit": False,
        "original_status": row["status"], "original_file": row.get("file"), "original_reason": row.get("reason"),
        "total_cost": None, "cost_components": None, "completed_bags": None, "uncompleted_bags": None,
        "result_is_partial": False, "cpu_seconds": 0., "wall_seconds": 0., "search_calls": 0, "search_work": 0}


def execute_request(row, sample, raw_tape, branch_budget, file):
    """Attempt once; failed execution/evidence writing can never become not-executed."""
    started, cpu = perf_counter(), process_time()
    outcome = None
    try:
        outcome = branch_network_decision(sample["checkpoint"], sample["pool"][row["candidate"]],
            tuple(Bag(**b) for b in raw_tape), horizon_ticks=80, budget=branch_budget)
        with gzip.open(file, "xt", encoding="utf-8") as stream:
            json.dump({"original_request": row, **outcome,
                "result": None if outcome["result"] is None else asdict(outcome["result"])},
                stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        value = outcome_value(row, outcome, file)
        failure = None if outcome["status"] == "reached_horizon" else {
            "request_key": row["request_key"], "status": outcome["status"],
            "budget_stop": outcome["budget_stop"], "failure": outcome["failure"]}
        return value, outcome, failure
    except Exception as exc:
        failure = {"request_key": row["request_key"],
            "status": "execution_failure" if outcome is None else "evidence_write_failure",
            "type": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()}
        result = outcome["result"] if outcome is not None else None
        value = {**row, **failure, "file": None, "cache_hit": False,
            "original_status": row["status"], "original_file": row.get("file"),
            "original_reason": row.get("reason"),
            "physical_status": None if outcome is None else outcome["status"],
            "total_cost": None, "physical_result": None if result is None else asdict(result),
            "cost_components": None if result is None else result.cost_components,
            "completed_bags": None if result is None else len(result.completed),
            "uncompleted_bags": None if result is None else len(result.uncompleted_bag_ids),
            "result_is_partial": outcome is None or outcome["status"] != "reached_horizon",
            "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - started,
            "search_calls": None if outcome is None else outcome["search_calls"],
            "search_work": None if outcome is None else outcome["search_work"]}
        return value, outcome, failure


def exact_decision_comparison(old, live):
    live = json.loads(json.dumps(sample_artifact(live)))
    # All saved observable decision fields and complete cache state are exact.
    # Only the documented per-instance fingerprint contains wall internals.
    differences = [name for name in old if name != "checkpoint_sha256" and old[name] != live.get(name)]
    differences.extend("unexpected_new_field:" + name for name in live.keys() - old.keys())
    return {"equal": not differences, "differences": differences,
            "ignored_instance_fingerprint": {"old": old["checkpoint_sha256"], "new": live["checkpoint_sha256"]}}


def check_files(folder, manifest):
    for name, expected in manifest.items():
        if sha(folder / name) != expected:
            raise ValueError("immutable evidence changed: " + str(folder / name))


def load_primary(prior):
    top, protocol, frozen = read(prior / "summary.json"), read(prior / "protocol.json"), read(prior / "manifest.json")
    if sha(prior / "summary.json") != frozen["summary_sha256"] or sha(prior / "protocol.json") != frozen["protocol_sha256"]:
        raise ValueError("primary root manifest mismatch")
    if top["scene_summaries_received"] != 3 or top["worker_failures"] or not top["complete_resource_accounting"]:
        raise ValueError("incomplete primary worker must be diagnosed before supplement planning")
    if top.get("source_changed_during_run") is not False or top.get("profile_changed_during_run") is not False:
        raise ValueError("primary reported source/profile drift during execution")
    source = ROOT / "scripts/experiments/ics_circulation_v3"
    for name, expected in protocol["source_sha256"].items():
        if sha(source / name) != expected or sha(prior / "source_snapshot" / name) != expected:
            raise ValueError("supplement requires unchanged primary physical/controller implementation")
    samples, requests = {}, []
    for scene in protocol["workloads"]:
        folder = prior / scene
        manifest = read(folder / "manifest.json")
        if sha(folder / "manifest.json") != frozen["scene_manifest_sha256"][scene]:
            raise ValueError("primary scene manifest differs")
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        if actual != set(manifest) | {"manifest.json"}:
            raise ValueError("primary scene frozen file set differs")
        check_files(folder, manifest)
        summary = read(folder / "summary.json")
        for entry in summary["samples"]:
            saved = read(folder / entry["file"])
            label = read(folder / entry["labels"][0])
            if label["groups"] != 4 or label["futures_per_group"] != 8 or label["evaluation_horizon_ticks"] != 80:
                raise ValueError("primary label grid/horizon changed")
            samples[entry["identity"]] = {"scene": scene, "saved": saved, "label": label,
                "sample_sha256": sha(folder / entry["file"]), "label_sha256": sha(folder / entry["labels"][0])}
            for row in label["raw_branches"]:
                requests.append({**row, "request_key": request_key(row),
                    "file": str((folder / row["file"]).resolve()) if "file" in row else None})
    if len(requests) != len({r["request_key"] for r in requests}) or len(requests) != 2176:
        raise ValueError("primary complete2176 request ledger is required")
    return protocol, samples, requests


def resolve_history(prior, requests, history):
    original = {r["request_key"]: r for r in requests}
    expected_source = read(prior / "protocol.json")["source_sha256"]
    resolved = {r["request_key"]: {**r, "source": "primary"} for r in requests if r["status"] == "reached_horizon"}
    references = []
    for folder in history:
        manifest, summary = read(folder / "manifest.json"), read(folder / "summary.json")
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        if actual != set(manifest) | {"manifest.json"}:
            raise ValueError("supplement frozen file set changed")
        check_files(folder, manifest)
        protocol = read(folder / "protocol.json")
        if protocol["primary_manifest_sha256"] != sha(prior / "manifest.json"):
            raise ValueError("supplement refers to another primary experiment")
        if summary.get("source_unchanged") is not True or protocol.get("source_sha256") != expected_source:
            raise ValueError("supplement was not executed under unchanged original source")
        if any(sha(folder / "source_snapshot" / name) != expected for name, expected in expected_source.items()):
            raise ValueError("supplement source snapshot differs from primary")
        references.append({"path": str(folder.resolve()), "manifest_sha256": sha(folder / "manifest.json")})
        for row in summary["request_outcomes"]:
            if row["request_key"] not in original or any(row[name] != original[row["request_key"]][name]
                    for name in ("sample", "scene", "group", "candidate", "draw", "horizon_ticks", "future_sha256")):
                raise ValueError("supplement changed original request identity or future")
            if row["status"] == "reached_horizon":
                if row["request_key"] in resolved:
                    raise ValueError("completed original request was rerun/replaced")
                resolved[row["request_key"]] = {**row, "source": str(folder.resolve())}
    return resolved, references


def run(prior, output, *, history=(), cpu_seconds=2400., wall_seconds=3600.,
        branch_calls=100, branch_work=100000, branch_wall=60., shard_index=0, shard_count=1):
    invocation_started, invocation_cpu = perf_counter(), process_time()
    prior, history = Path(prior).resolve(), tuple(Path(p).resolve() for p in history)
    protocol, samples, requests = load_primary(prior)
    resolved, references = resolve_history(prior, requests, history)
    all_missing = [r for r in requests if r["request_key"] not in resolved]
    if not all_missing:
        raise ValueError("no missing requests; do not create a fake additional batch")
    missing, assignment = shard_requests(all_missing, shard_index, shard_count)
    if not missing:
        raise ValueError("empty shard; do not create a fake additional batch")
    if any(not 0 < v < float("inf") for v in (cpu_seconds, wall_seconds)):
        raise ValueError("finite positive batch safeguards required")
    branch_budget = SearchBudget(branch_calls, branch_work, branch_wall)
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    for name, expected in protocol["source_sha256"].items():
        (output / "source_snapshot" / name).write_bytes((prior / "source_snapshot" / name).read_bytes())
    (output / "completion_driver.py").write_bytes(Path(__file__).read_bytes())
    write_new_json(output / "protocol.json", {"schema": "ics_v3_network_role_exact_completion_v1",
        "primary": str(prior), "primary_manifest_sha256": sha(prior / "manifest.json"), "history": references,
        "source_sha256": protocol["source_sha256"], "driver_sha256": sha(Path(__file__)),
        "selection": "ALL original requests without a reached_horizon result, by status only; never inspect cost to select",
        "original_request_count": 2176, "already_resolved_requests": len(resolved), "all_missing_requests": len(all_missing),
        "selected_missing_requests": len(missing), "shard_index": shard_index, "shard_count": shard_count,
        "sharding": "sorted unique(sample,candidate,full future SHA,h80) modulo count; all requests in a memo class assigned together; no cost-based selection",
        "missing_assignment_sha256": digest(assignment),
        "cpu_seconds": cpu_seconds, "wall_seconds": wall_seconds, "branch_budget": asdict(branch_budget),
        "sum_shard_compute_cpu_safeguards": cpu_seconds * shard_count,
        "sum_shard_compute_wall_safeguards_not_makespan": wall_seconds * shard_count,
        "safeguard_scope": "each shard compute phase; setup validation is additionally measured, and each shard's duplicate recollection remains in cumulative expense",
        "per_query_algorithm_budget": "unchanged original3000, K4, planning180 and evaluation80; any larger batch or perbranch resource cap only permits additional continuation, never new candidates",
        "recollection": "exact all saved decision fields/cache/contract/module/private continuation evidence; exclude only wall-containing per-instance checkpoint fingerprint",
        "futures": "read original saved4x8 tapes verbatim; no resampling", "new_independent_source_count": 0,
        "partial_policy": "cooperative caps; every remaining request retained as not_executed; each new batch immutable; successful existing results never overwritten"})
    write_new_json(output / "missing_assignment.json", assignment)
    write_new_json(output / "missing_request_manifest.json", missing)
    started, cpu, memory_before = perf_counter(), process_time(), memory_snapshot()
    outcomes, collections, failed = [], [], []
    actual = reused = search_calls = search_work = unknown_search_calls = 0
    memo = {}
    def budget_stop():
        if process_time() - cpu >= cpu_seconds:
            return "batch_cpu_safeguard"
        if perf_counter() - started >= wall_seconds:
            return "batch_wall_safeguard"
        return None
    for scene_name in protocol["workloads"]:
        local_requests = [r for r in missing if r["scene"] == scene_name]
        if not local_requests:
            continue
        scene_output = output / scene_name
        scene_output.mkdir()
        if budget_stop():
            outcomes.extend(not_executed_value(r, budget_stop()) for r in local_requests)
            continue
        try:
            network, topology = load_network(prior / scene_name / "original_profile.json")
            scene = make_workload(scene_name, network, topology, rounds=3)
            original_input = read(prior / scene_name / (scene_name + "_input.json"))
            current_input = json.loads(json.dumps({"initial": asdict(scene.initial),
                "forecasts": [asdict(f) for f in scene.forecasts], "future_engine_only": [asdict(b) for b in scene.future_bags],
                "horizon": scene.horizon}))
            if any(current_input[key] != original_input[key] for key in current_input):
                raise ValueError("recollected scene changed original physical inputs or publication/nominal tape")
            collection = collect_network_decisions(scene)
            collections.append(collection["metadata"])
            search_calls += collection["metadata"]["search_calls"]
            search_work += collection["metadata"]["search_work"]
            write_new_json(scene_output / "collection.json", {"metadata": collection["metadata"],
                "opportunities": collection["opportunities"], "result": None if collection["result"] is None else asdict(collection["result"])})
            current = {s["identity"]: s for s in collection["samples"]}
            for sample_index, identity in enumerate(dict.fromkeys(r["sample"] for r in local_requests)):
                wanted = [r for r in local_requests if r["sample"] == identity]
                sample_output = scene_output / f"s{sample_index:02d}"
                sample_output.mkdir()
                if identity not in current:
                    raise ValueError("original actual decision absent after identical recollection: " + identity)
                sample = current[identity]
                comparison = exact_decision_comparison(samples[identity]["saved"], sample)
                pending = [asdict(b) for tasks in sample["checkpoint"].base.pending_arrivals.values() for b in tasks]
                expected_pending = [b for b in original_input["future_engine_only"]
                    if b["arrival"] > sample["time"] and b["bag_id"] not in sample["checkpoint"].state.bags]
                comparison["private_remaining_nominal_tape_matches_original_input"] = sorted(pending, key=lambda b: b["bag_id"]) == sorted(expected_pending, key=lambda b: b["bag_id"])
                comparison["equal"] &= comparison["private_remaining_nominal_tape_matches_original_input"]
                write_new_json(sample_output / "comparison.json", comparison)
                write_new_json(sample_output / "sample.json", sample_artifact(sample))
                if not comparison["equal"]:
                    raise ValueError("original physical/cache/control evidence differs: " + repr(comparison["differences"]))
                for row in wanted:
                    label = samples[identity]["label"]
                    raw_tape = label["future_groups_offline_only"][row["group"]]["tapes"][row["draw"]]
                    if digest(raw_tape) != row["future_sha256"]:
                        raise ValueError("saved original future tape does not match request")
                    key = memo_key(row)
                    if key in memo:
                        reused += 1
                        previous = memo[key]
                        outcomes.append({**previous, **{k: row[k] for k in ("request_key", "group", "draw")},
                            "cache_hit": True, "physical_call_request_key": previous["request_key"],
                            "original_status": row["status"], "original_file": row.get("file"),
                            "original_reason": row.get("reason"),
                            "cpu_seconds": 0., "wall_seconds": 0., "search_calls": 0, "search_work": 0})
                        continue
                    stopped = budget_stop()
                    if stopped:
                        outcomes.append(not_executed_value(row, stopped))
                        continue
                    actual += 1
                    file = sample_output / f"b{actual:05d}.json.gz"
                    value, outcome, failure = execute_request(row, sample, raw_tape, branch_budget, file)
                    if outcome is not None:
                        search_calls += outcome["search_calls"]
                        search_work += outcome["search_work"]
                    else:
                        unknown_search_calls += 1
                    outcomes.append(value)
                    if value["status"] == "reached_horizon":
                        memo[key] = value
                    if failure is not None:
                        failed.append(failure)
                print(json.dumps({"scene": scene_name, "sample": identity, "actual_calls": actual,
                    "successful_request_rows": sum(r["status"] == "reached_horizon" for r in outcomes)}), flush=True)
        except Exception as exc:
            failure = {"scene": scene_name, "type": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()}
            failed.append(failure)
            done = {r["request_key"] for r in outcomes}
            outcomes.extend(not_executed_value(r, "recollection_exception")
                for r in local_requests if r["request_key"] not in done)
            write_new_json(scene_output / "failure.json", failure)
    if len(outcomes) != len(missing) or len({r["request_key"] for r in outcomes}) != len(missing):
        raise ValueError("supplement lost or duplicated original requests")
    for row in outcomes:
        if row["status"] == "reached_horizon":
            resolved[row["request_key"]] = {**row, "source": str(output.resolve())}
    unchanged = all(sha(ROOT / "scripts/experiments/ics_circulation_v3" / name) == expected
                    for name, expected in protocol["source_sha256"].items())
    summary = {"original_request_count": 2176, "all_missing_at_start": len(all_missing),
        "missing_at_start": len(missing), "request_outcomes": outcomes,
        "resolved_requests_after": len(resolved), "remaining_requests": [r for r in requests if r["request_key"] not in resolved],
        "selected_remaining_requests": [r for r in missing if r["request_key"] not in resolved],
        "shard_index": shard_index, "shard_count": shard_count, "missing_assignment_sha256": digest(assignment),
        "actual_new_branch_calls": actual, "cache_reused_request_rows": reused, "failures": failed,
        "search_calls_including_recollection": search_calls, "search_work_including_recollection": search_work,
        "attempted_branches_with_unknown_search_accounting": unknown_search_calls,
        "collections": collections, "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - started,
        "recollection_cpu_seconds": sum(c["cpu_seconds"] for c in collections),
        "recollection_wall_seconds": sum(c["wall_seconds"] for c in collections),
        "successful_physical_branch_cpu_seconds": sum(r["cpu_seconds"] for r in outcomes if r["status"] == "reached_horizon" and not r["cache_hit"]),
        "failed_physical_branch_cpu_seconds": sum(r["cpu_seconds"] for r in outcomes if r["status"] not in {"not_executed", "reached_horizon"} and not r["cache_hit"]),
        "branch_cpu_accounting_scope": "known per-attempt measurement; invocation minus setup and attempts also contains repeated collection, snapshot gzip I/O and bookkeeping",
        "setup_cpu_seconds": cpu - invocation_cpu, "setup_wall_seconds": started - invocation_started,
        "invocation_cpu_seconds": process_time() - invocation_cpu, "invocation_wall_seconds": perf_counter() - invocation_started,
        "timing_scope": "invocation includes immutable validation/history/setup; compute safeguard and cpu_seconds begin after protocol; final JSON/manifest serialization excluded",
        "memory_before": memory_before, "memory_after": memory_snapshot(), "source_unchanged": unchanged,
        "new_independent_source_count": 0}
    write_new_json(output / "summary.json", summary)
    write_new_json(output / "resolved_request_ledger.json", {key: value for key, value in resolved.items()})
    write_new_json(output / "manifest.json", {p.relative_to(output).as_posix(): sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    print(json.dumps({k: summary[k] for k in ("missing_at_start", "resolved_requests_after", "actual_new_branch_calls",
        "cache_reused_request_rows", "cpu_seconds", "wall_seconds", "source_unchanged")}))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=Path, nargs="*", default=())
    parser.add_argument("--cpu-seconds", type=float, default=2400.)
    parser.add_argument("--wall-seconds", type=float, default=3600.)
    parser.add_argument("--branch-calls", type=int, default=100)
    parser.add_argument("--branch-work", type=int, default=100000)
    parser.add_argument("--branch-wall", type=float, default=60.)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    summary = run(args.prior, args.output, history=args.history, cpu_seconds=args.cpu_seconds,
        wall_seconds=args.wall_seconds, branch_calls=args.branch_calls, branch_work=args.branch_work, branch_wall=args.branch_wall,
        shard_index=args.shard_index, shard_count=args.shard_count)
    raise SystemExit(int(bool(summary["selected_remaining_requests"] or summary["failures"] or not summary["source_unchanged"])))
