"""Read-only full original-map request/candidate/whole-tape diagnostics."""
import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def result_metrics(result, expected, initial_completed):
    state, completed = result["final_snapshot"], result["completed"]
    bags = state["bags"]
    assert set(bags) <= expected and set(completed) <= expected
    assert abs(result["total_cost"] - sum(WEIGHTS[k] * v for k, v in result["cost_components"].items())) < 1e-8
    protected = {k for k, b in bags.items() if b["protected"]}
    return {"total_cost": result["total_cost"], "cost_components": result["cost_components"],
        "expected_full_ledger_tasks": len(expected), "observed_tasks": len(bags),
        "unobserved_tasks": len(expected - bags.keys()), "completed_tasks": len(completed),
        "newly_completed_since_checkpoint": len(completed.keys() - initial_completed),
        "observed_uncompleted_tasks": len(bags.keys() - completed.keys()),
        "full_ledger_uncompleted_tasks": len(expected - completed.keys()),
        "on_time": sum(t <= bags[k]["deadline"] for k, t in completed.items()),
        "protected_observed": len(protected), "protected_completed": len(protected & completed.keys()),
        "protected_on_time": sum(completed[k] <= bags[k]["deadline"] for k in protected & completed.keys()),
        "protected_uncompleted": len(protected - completed.keys()),
        "protected_completed_late": sum(completed[k] > bags[k]["deadline"] for k in protected & completed.keys()),
        "completion_times": completed,
        "final_tray_positions": {k: t["node"] for k, t in state["trays"].items()},
        "empty_in_transit": sum(t["mode"] == "in_transit" and t["bag_id"] is None for t in state["trays"].values()),
        "loaded_in_transit": sum(t["mode"] == "in_transit" and t["bag_id"] is not None for t in state["trays"].values()),
        "holding_or_unloading_trays": sum(t["mode"] in ("holding", "unloading") for t in state["trays"].values())}


def run(experiment, output):
    started, cpu = perf_counter(), process_time()
    experiment, output = Path(experiment), Path(output)
    if output.exists():
        raise ValueError("analysis must use a fresh immutable output directory")
    complete = BASE / "phase4_w3_network_role_complete_20261009"
    protocol, summary = read(experiment / "protocol.json"), read(experiment / "summary.json")
    assert protocol["mode"] == "full" and protocol["original_requests"] == 2176
    assert protocol["prior_manifest_sha256"] == sha(complete / "manifest.json")
    primary = Path(read(complete / "audit.json")["primary"])
    old_ledger = read(complete / "resolved_request_ledger.json")
    new_ledger = {r["request_key"]: r for r in summary["rows"]}
    assert len(new_ledger) == len(summary["rows"]) == 2176 and set(new_ledger) == set(old_ledger)
    inputs = {str(p.resolve()): sha(p) for p in (experiment / "protocol.json", experiment / "summary.json",
        experiment / "manifest.json", complete / "manifest.json", complete / "resolved_request_ledger.json")}
    samples = {}
    for scene in ("cross_cycle", "counterflow", "near_full"):
        folder = primary / scene
        for entry in read(folder / "summary.json")["samples"]:
            path, label = folder / entry["file"], folder / entry["labels"][0]
            inputs[str(path.resolve())], inputs[str(label.resolve())] = sha(path), sha(label)
            samples[entry["identity"]] = {"scene": scene, "sample": read(path), "label": read(label), "entry": entry}
    assert len(samples) == 18
    files, metrics, rows = {}, {}, []
    sample_rows = defaultdict(list)
    for key, row in new_ledger.items():
        old = old_ledger[key]
        assert all(row[k] == old[k] for k in ("scene", "sample", "candidate", "group", "draw", "future_sha256"))
        entry = samples[row["sample"]]
        tape = entry["label"]["future_groups_offline_only"][row["group"]]["tapes"][row["draw"]]
        expected = set(entry["sample"]["state"]["bags"]) | {b["bag_id"] for b in tape}
        initial_completed = set(entry["sample"]["state"]["completed"])
        analyzed = {k: row[k] for k in ("request_key", "scene", "sample", "candidate", "group", "draw", "status")}
        if row.get("file"):
            path = Path(row["file"])
            physical = None
            if str(path) not in files:
                inputs[str(path.resolve())] = sha(path)
                assert row["artifact_sha256"] == sha(path)
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    physical = json.load(stream)
                files[str(path)] = sha(path)
            memo = (row["sample"], row["candidate"], row["future_sha256"])
            if memo not in metrics:
                assert physical is not None
                old80 = physical["endpoints"].get(str(physical["old80_at"]))
                metrics[memo] = {"old80": None if old80 is None else result_metrics(old80["result"], expected, initial_completed),
                    "full": None if physical["result"] is None else result_metrics(physical["result"], expected, initial_completed),
                    "status": physical["status"], "stopped_at": physical["stopped_at"],
                    "milestone_times": {k: v["time"] for k, v in physical["milestones"].items()},
                    "last_cycle_state": physical["last_cycle_state"],
                    "stationary_occupancy_count": len(physical["last_cycle_state"]["stationary_occupancy_reservations"]),
                    "protected_unadmitted_decisions": physical["last_cycle_state"]["protected_unadmitted_decisions"],
                    "physical_file": str(path), "search_calls": physical["search_calls"], "search_work": physical["search_work"],
                    "branch_cpu_seconds": physical["cpu_seconds"], "branch_wall_seconds": physical["wall_seconds"]}
            assert metrics[memo]["physical_file"] == str(path)
            analyzed.update(metrics[memo])
            analyzed["cache_hit"] = row["cache_hit"]
            analyzed["physical_call"] = row["physical_call"]
            if analyzed["old80"] is not None:
                assert analyzed["old80"]["total_cost"] == old["total_cost"]
                assert analyzed["old80"]["cost_components"] == old["cost_components"]
            if analyzed["status"] == "controller_quiescent":
                assert analyzed["full"]["full_ledger_uncompleted_tasks"] == 0
                assert analyzed["full"]["unobserved_tasks"] == 0
                assert analyzed["last_cycle_state"]["transport_drained"]
                assert analyzed["last_cycle_state"]["forecast_expired"]
                assert analyzed["full"]["cost_components"]["terminal_backlog"] == 0
                assert analyzed["full"]["cost_components"]["terminal_inflight"] == 0
        rows.append(analyzed)
        sample_rows[row["sample"]].append(analyzed)
    diagnostics = []
    for identity, entry in samples.items():
        sample, local = entry["sample"], sample_rows[identity]
        base = {"identity": identity, "scene": entry["scene"], "role": sample["role"],
            "time": sample["time"], "band": sample["band"], "source_node": sample["source_node"],
            "candidate_count": sample["candidate_count"], "requested": len(local),
            "prefix_classes": len(set(sample["physical_prefix_signatures"])),
            "zero_candidate_cell": sample["candidate_count"] == 0,
            "status_counts": dict(Counter(r["status"] for r in local))}
        if not local:
            assert sample["candidate_count"] == 0
            diagnostics.append(base)
            continue
        assert len(local) == 128
        complete_local = all(r["status"] == "controller_quiescent" for r in local)
        base["complete_for_full_value_comparison"] = complete_local
        by_candidate = {c: sorted((r for r in local if r["candidate"] == c), key=lambda r: (r["group"], r["draw"])) for c in range(4)}
        assert all(len(rs) == 32 for rs in by_candidate.values())
        baseline = next(i for i, p in enumerate(sample["proposals"]) if p["is_baseline"])
        base["baseline_ordinal"] = baseline
        for endpoint in ("old80", "full"):
            if endpoint == "full" and not complete_local:
                base[endpoint] = {"excluded_from_complete_ranking": True, "reason": "not all128 reached certified full-cycle endpoint"}
                continue
            if any(r.get(endpoint) is None for r in local):
                base[endpoint] = {"excluded_from_complete_ranking": True, "reason": "missing endpoint"}
                continue
            vectors = [[r[endpoint]["total_cost"] for r in by_candidate[c]] for c in range(4)]
            means = list(map(mean, vectors))
            best = min(means)
            base[endpoint] = {"candidate_means": means, "optset": [c for c, value in enumerate(means) if abs(value - best) <= 1e-9],
                "candidate_cost_vectors": vectors, "candidate_group_means": [[mean(v[g * 8:(g + 1) * 8]) for g in range(4)] for v in vectors],
                "candidate_component_means": [{k: mean(r[endpoint]["cost_components"][k] for r in by_candidate[c]) for k in WEIGHTS} for c in range(4)],
                "candidate_on_time_means": [mean(r[endpoint]["on_time"] for r in by_candidate[c]) for c in range(4)],
                "candidate_protected_late_means": [mean(r[endpoint]["protected_completed_late"] for r in by_candidate[c]) for c in range(4)],
                "all_candidate_vectors_identical": len({tuple(v) for v in vectors}) == 1,
                "baseline_mean_regret": means[baseline] - best}
            paired = []
            for c in range(4):
                delta = [a - b for a, b in zip(vectors[c], vectors[baseline])]
                paired.append({"candidate": c, "delta_vs_baseline": delta,
                    "mean": mean(delta), "min": min(delta), "max": max(delta),
                    "better": sum(d < -1e-9 for d in delta), "tie": sum(abs(d) <= 1e-9 for d in delta),
                    "worse": sum(d > 1e-9 for d in delta)})
            base[endpoint]["paired_candidate_vs_baseline"] = paired
        if complete_local and "optset" in base["old80"]:
            old_choice = min(base["old80"]["optset"])
            base.update(old80_choice_min_ordinal=old_choice,
                old80_choice_full_regret=base["full"]["candidate_means"][old_choice] - min(base["full"]["candidate_means"]),
                exact_optset_equal=base["old80"]["optset"] == base["full"]["optset"])
            base["candidate_first_task_complete_mean_times"] = [mean(r["milestone_times"]["task_complete"] for r in by_candidate[c]) for c in range(4)]
            base["candidate_first_transport_drained_mean_times"] = [mean(r["milestone_times"]["transport_drained"] for r in by_candidate[c]) for c in range(4)]
            base["candidate_controller_quiescent_mean_times"] = [mean(r["stopped_at"] for r in by_candidate[c]) for c in range(4)]
            base["full_same_future_completion_times_differ"] = any(
                len({digest(by_candidate[c][i]["full"]["completion_times"]) for c in range(4)}) > 1 for i in range(32))
            base["full_same_future_final_tray_positions_differ"] = any(
                len({digest(by_candidate[c][i]["full"]["final_tray_positions"]) for c in range(4)}) > 1 for i in range(32))
        diagnostics.append(base)
    totals = {}
    for endpoint in ("old80", "full"):
        local = [r[endpoint] for r in rows if r.get(endpoint) is not None]
        totals[endpoint] = {"request_weighted_endpoints": len(local), "physical_or_outcome_incomplete_requests": 2176 - len(local),
            "counting_scope": "correlated candidate/group/draw/owner request instances; not independent operational bags or days",
            "cost_components_sum": {k: sum(r["cost_components"][k] for r in local) for k in WEIGHTS}}
        for key in ("expected_full_ledger_tasks", "observed_tasks", "unobserved_tasks", "completed_tasks", "newly_completed_since_checkpoint",
                    "observed_uncompleted_tasks", "full_ledger_uncompleted_tasks", "on_time", "protected_observed", "protected_completed",
                    "protected_on_time", "protected_uncompleted", "protected_completed_late", "empty_in_transit", "loaded_in_transit", "holding_or_unloading_trays"):
            totals[endpoint][key] = sum(r[key] for r in local)
    nonempty = [d for d in diagnostics if not d["zero_candidate_cell"]]
    valid = [d for d in nonempty if d["complete_for_full_value_comparison"]]
    aggregate = {"schema": "ics_v3_network_whole_cycle_analysis_v1", "samples": len(diagnostics), "nonempty_samples": len(nonempty),
        "zero_candidate_samples": [d["identity"] for d in diagnostics if d["zero_candidate_cell"]],
        "requested": len(rows), "physical_files": len(files), "exact_memo_classes": len(metrics),
        "cache_hit_requests": sum(r.get("cache_hit", False) for r in rows), "status_counts": dict(Counter(r["status"] for r in rows)),
        "complete_value_samples": len(valid), "roles": dict(Counter(d["role"] for d in diagnostics)),
        "old80_flat_samples": sum(d.get("old80", {}).get("all_candidate_vectors_identical", False) for d in nonempty),
        "full_flat_samples": sum(d["full"]["all_candidate_vectors_identical"] for d in valid),
        "full_flat_continuation_samples": sum(d["role"] == "continuation" and d["full"]["all_candidate_vectors_identical"] for d in valid),
        "full_cost_flat_but_completion_times_differ_samples": sum(d["full"]["all_candidate_vectors_identical"] and d["full_same_future_completion_times_differ"] for d in valid),
        "full_cost_flat_but_final_tray_positions_differ_samples": sum(d["full"]["all_candidate_vectors_identical"] and d["full_same_future_final_tray_positions_differ"] for d in valid),
        "exact_optset_unchanged_samples": sum(d.get("exact_optset_equal", False) for d in valid),
        "positive_old80_choice_full_regret_samples": sum(d.get("old80_choice_full_regret", 0.) > 1e-9 for d in valid),
        "baseline_full_regret_positive_samples": sum(d["full"]["baseline_mean_regret"] > 1e-9 for d in valid),
        "old80_choice_full_regret_mean_over_complete_samples": mean([d["old80_choice_full_regret"] for d in valid]) if valid else None,
        "old80_choice_full_regret_max_over_complete_samples": max([d["old80_choice_full_regret"] for d in valid], default=None),
        "full_baseline_regret_mean_over_complete_samples": mean([d["full"]["baseline_mean_regret"] for d in valid]) if valid else None,
        "full_baseline_regret_max_over_complete_samples": max([d["full"]["baseline_mean_regret"] for d in valid], default=None),
        "request_weighted": totals,
        "unique_physical_search_calls": sum(x["search_calls"] for x in metrics.values()),
        "unique_physical_search_work": sum(x["search_work"] for x in metrics.values()),
        "unique_branch_cpu_seconds": sum(x["branch_cpu_seconds"] for x in metrics.values()),
        "unique_branch_wall_seconds_sum_not_makespan": sum(x["branch_wall_seconds"] for x in metrics.values()),
        "worker_invocation_cpu_seconds": summary["worker_cpu_seconds_sum"], "parent_cpu_seconds": summary["parent_cpu_seconds"],
        "parent_wall_makespan_seconds": summary["wall_makespan_seconds"],
        "resource_note": "branch timing is nested in invocation timing, never add again; requests.json repeats referenced physical-file timings on memo aliases, so sum unique physical files only; worker timings include duplicate recollection/setup; pilot and stopped pilot tracked separately",
        "new_independent_source_count": 0,
        "value_scope": "per-state single-intervention conditional means under fixed timed continuation; repeated checkpoints/shared futures are correlated; regrets across states are not additive deployable policy gains",
        "maximum_controller_quiescent_at": max((r["stopped_at"] for r in rows if r["status"] == "controller_quiescent"), default=None),
        "minimum_controller_quiescent_at": min((r["stopped_at"] for r in rows if r["status"] == "controller_quiescent"), default=None),
        "requests_task_done_before_transport": sum(r.get("milestone_times", {}).get("task_complete", 0) < r.get("milestone_times", {}).get("transport_drained", 0) for r in rows),
        "requests_with_stationary_occupancy_at_end": sum(r.get("stationary_occupancy_count", 0) > 0 for r in rows),
        "protected_unadmitted_decision_counter_request_sum": sum(r.get("protected_unadmitted_decisions", 0) for r in rows),
        "input_manifest_matches_start": None,
        "analysis_cpu_seconds": process_time() - cpu, "analysis_wall_seconds": perf_counter() - started}
    aggregate["by_scene"] = {}
    for scene in ("cross_cycle", "counterflow", "near_full"):
        selected = [r for r in rows if r["scene"] == scene]
        selected_samples = [d for d in valid if d["scene"] == scene]
        aggregate["by_scene"][scene] = {"requests": len(selected),
            "physical_memo_classes": len({(r["sample"], r["candidate"], r.get("physical_file")) for r in selected}),
            "status_counts": dict(Counter(r["status"] for r in selected)),
            "complete_value_samples": len(selected_samples),
            "full_flat_samples": sum(d["full"]["all_candidate_vectors_identical"] for d in selected_samples),
            "h80_requests_unobserved_tasks": sum((r.get("old80") or {}).get("unobserved_tasks", 0) > 0 for r in selected),
            "h80_requests_observed_uncompleted": sum((r.get("old80") or {}).get("observed_uncompleted_tasks", 0) > 0 for r in selected),
            "task_complete_before_transport_requests": sum(r.get("milestone_times", {}).get("task_complete", 0) < r.get("milestone_times", {}).get("transport_drained", 0) for r in selected),
            "full_expected_tasks_request_weighted": sum((r.get("full") or {}).get("expected_full_ledger_tasks", 0) for r in selected),
            "full_completed_tasks_request_weighted": sum((r.get("full") or {}).get("completed_tasks", 0) for r in selected),
            "full_on_time_tasks_request_weighted": sum((r.get("full") or {}).get("on_time", 0) for r in selected)}
    worker_summaries = list(summary["scene_summaries"].values())
    memories = [s["memory_after"] for s in worker_summaries if s.get("memory_after")]
    collections = [scene["collection_metadata"] for worker in worker_summaries
                   for scene in worker.get("scene_summaries", {}).values() if scene.get("collection_metadata")]
    aggregate["resources_detail"] = {
        "actual_recollection_invocations": len(collections),
        "recollection_cpu_seconds_nested_in_worker_total": sum(c["cpu_seconds"] for c in collections),
        "recollection_search_calls": sum(c["search_calls"] for c in collections),
        "recollection_search_work": sum(c["search_work"] for c in collections),
        "max_observed_single_worker_peak_working_set_bytes": max((m["peak_working_set_bytes"] for m in memories if m.get("peak_working_set_bytes") is not None), default=None),
        "max_observed_single_worker_peak_commit_bytes": max((m["peak_commit_bytes"] for m in memories if m.get("peak_commit_bytes") is not None), default=None),
        "memory_scope": "per-process lifetime peak including imports and earlier scene stages; never sum as simultaneous aggregate peak"}
    pilot_path = BASE / "phase4_w3_network_full_cycle_pilot_v2_20261010/summary.json"
    interrupted_path = BASE / "phase4_w3_network_full_cycle_pilot_20261010/interruption.json"
    pilot, interrupted = read(pilot_path), read(interrupted_path)
    inputs[str(pilot_path.resolve())], inputs[str(interrupted_path.resolve())] = sha(pilot_path), sha(interrupted_path)
    aggregate["additional_expense_not_in_formal_total"] = {
        "repaired_pilot_physical_calls": pilot["actual_branches"],
        "repaired_pilot_worker_cpu_seconds": pilot["worker_cpu_seconds_sum"],
        "repaired_pilot_parent_cpu_seconds": pilot["parent_cpu_seconds"],
        "repaired_pilot_wall_makespan_seconds": pilot["wall_makespan_seconds"],
        "interrupted_pilot_recorded_physical_calls_lower_bound": interrupted["recorded_branch_calls_lower_bound"],
        "interrupted_pilot_recorded_branch_cpu_seconds_lower_bound": interrupted["recorded_branch_cpu_seconds_lower_bound"],
        "interrupted_pilot_recorded_collection_cpu_seconds": interrupted["recorded_collection_cpu_seconds"],
        "interrupted_pilot_unrecorded_work_unknown": interrupted["interrupted_running_work_unknown"]}
    examples = []
    for criterion in ("nonflat_cost", "flat_cost_different_completion", "flat_cost_different_final_position"):
        eligible = [d for d in valid if (
            not d["full"]["all_candidate_vectors_identical"] if criterion == "nonflat_cost" else
            d["full"]["all_candidate_vectors_identical"] and d["full_same_future_completion_times_differ"]
            if criterion == "flat_cost_different_completion" else
            d["full"]["all_candidate_vectors_identical"] and d["full_same_future_final_tray_positions_differ"])]
        if not eligible:
            continue
        d = sorted(eligible, key=lambda d: d["identity"])[0]
        local = {(r["candidate"], r["group"], r["draw"]): r for r in sample_rows[d["identity"]]}
        candidates = []
        for c in range(4):
            if c == d["baseline_ordinal"]:
                continue
            for g in range(4):
                for draw in range(8):
                    base, other = local[d["baseline_ordinal"], g, draw], local[c, g, draw]
                    field = {"nonflat_cost": "total_cost", "flat_cost_different_completion": "completion_times",
                             "flat_cost_different_final_position": "final_tray_positions"}[criterion]
                    if base["full"][field] != other["full"][field]:
                        candidates.append((g, draw, c, base, other))
        if not candidates:
            continue
        g, draw, c, base, other = min(candidates, key=lambda x: x[:3])
        physicals = []
        for row in (base, other):
            with gzip.open(row["physical_file"], "rt", encoding="utf-8") as stream:
                physicals.append(json.load(stream))
        snapshots = [p["result"]["final_snapshot"] for p in physicals]
        examples.append({"criterion": criterion, "selection": "posthoc first identity, then lexicographic(group,draw,candidate); illustrative only",
            "sample": d["identity"], "group": g, "draw": draw, "baseline_candidate": d["baseline_ordinal"], "other_candidate": c,
            "files": [r["physical_file"] for r in (base, other)],
            "file_sha256": [sha(r["physical_file"]) for r in (base, other)],
            "old80_cost_delta": other["old80"]["total_cost"] - base["old80"]["total_cost"],
            "full_cost_delta": other["full"]["total_cost"] - base["full"]["total_cost"],
            "full_component_delta": {k: other["full"]["cost_components"][k] - base["full"]["cost_components"][k] for k in WEIGHTS},
            "different_load_times": {k: [s["load_times"].get(k) for s in snapshots] for k in snapshots[0]["bags"]
                                     if snapshots[0]["load_times"].get(k) != snapshots[1]["load_times"].get(k)},
            "different_completion_times": {k: [s["completed"].get(k) for s in snapshots] for k in snapshots[0]["bags"]
                                           if snapshots[0]["completed"].get(k) != snapshots[1]["completed"].get(k)},
            "final_tray_positions": [r["full"]["final_tray_positions"] for r in (base, other)]})
    aggregate["input_manifest_matches_start"] = all(sha(p) == expected for p, expected in inputs.items())
    aggregate["analysis_cpu_seconds"] = process_time() - cpu
    aggregate["analysis_wall_seconds"] = perf_counter() - started
    aggregate["analysis_timing_scope"] = "all reads/checks/analysis before output serialization"
    assert aggregate["input_manifest_matches_start"]
    output.mkdir(parents=True)
    write(output / "summary.json", aggregate)
    write(output / "samples.json", diagnostics)
    write(output / "requests.json", rows)
    write(output / "posthoc_examples.json", examples)
    write(output / "input_manifest.json", inputs)
    (output / "analysis_source.py").write_bytes(Path(__file__).read_bytes())
    lines = ["# Original-map complete saved-tape and controller-drain diagnostics", "",
        f"{len(diagnostics)} original cells ({len(valid)} complete nonempty value grids), {len(rows)} original requests, {len(files)} physical files.", "",
        "| Scene / role / time | h80 candidate mean costs | Whole-cycle candidate mean costs | h80-choice regret at drain |",
        "|---|---|---|---:|"]
    for d in diagnostics:
        label = f"{d['scene']} / {d['role']} / {d['time']}"
        if d["zero_candidate_cell"]:
            lines.append(f"| {label} | real zero-candidate cell | no fabricated branches | — |")
        else:
            old = ", ".join(f"{v:.6g}" for v in d.get("old80", {}).get("candidate_means", []))
            full = ", ".join(f"{v:.6g}" for v in d.get("full", {}).get("candidate_means", []))
            lines.append(f"| {label} | {old} | {full or 'censored'} | {d.get('old80_choice_full_regret', '—')} |")
    lines += ["", "All weights, original K4 candidates, 32 saved futures, planning horizon180 and timed continuation are unchanged.",
        "Task completion, transport drain and controller quiescence are separate times. Idle current-node INFINITY capacity stock remains in the physical ledger.",
        "Counts are correlated request-weighted instances from the same three development workloads; no new independent operational source is claimed.",
        "Per-state candidate regrets are conditional single-intervention diagnostics under timed continuation; summing them does not establish an achievable deployed-policy gain.",
        "Candidate cost vectors, per-group means, components and all flat samples are preserved in samples.json; raw per-request ledger is requests.json.",
        "The old 80-step result is a physical checkpoint comparison only; no RolloutResult was used as a resumable engine checkpoint."]
    (output / "ANALYSIS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write(output / "manifest.json", {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, default=BASE / "phase4_w3_network_full_cycle_20261010")
    parser.add_argument("--output", type=Path, default=BASE / "phase4_w3_network_full_cycle_analysis_20261010")
    args = parser.parse_args()
    run(args.experiment, args.output)
