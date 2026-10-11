"""Independently verify one complete ledger without replacing frozen partial runs."""
from collections import Counter
import argparse
import gzip
import json
from pathlib import Path
from statistics import mean
import sys

# Re-running a saved audit must not add bytecode files to its frozen evidence.
sys.dont_write_bytecode = True

import audit as physical
import complete_missing as completion


def run(prior, histories, output):
    prior = Path(prior).resolve()
    histories = tuple(Path(path).resolve() for path in histories)
    protocol, samples, requests = completion.load_primary(prior)
    resolved, references = completion.resolve_history(prior, requests, histories)
    output = completion.create_output_directory(output)
    checks = []
    def check(name, accepted, **context):
        checks.append({"check": name, "passed": bool(accepted), **context})
    check("exact_original_full_request_domain", len(requests) == len(resolved) == 2176
          and set(resolved) == {r["request_key"] for r in requests})
    by_assignment = {}
    supplement_metrics = []
    for folder in histories:
        summary, declared = completion.read(folder / "summary.json"), completion.read(folder / "protocol.json")
        assignment = completion.read(folder / "missing_assignment.json")
        missing = completion.read(folder / "missing_request_manifest.json")
        index, count = declared["shard_index"], declared["shard_count"]
        assignment_key = declared["missing_assignment_sha256"]
        by_assignment.setdefault(assignment_key, []).append((index, count, summary, assignment))
        expected = {key for item in assignment if item["shard"] == index for key in item["requests"]}
        check("shard_selected_exact_assigned_request_domain", completion.digest(assignment) == assignment_key
              and {r["request_key"] for r in missing} == expected
              and {r["request_key"] for r in summary["request_outcomes"]} == expected
              and len(summary["request_outcomes"]) == len(expected), path=str(folder))
        non_reused_attempts = [r for r in summary["request_outcomes"]
                              if r["status"] != "not_executed" and not r["cache_hit"]]
        check("supplement_attempt_and_exact_reuse_accounting", len(non_reused_attempts) == summary["actual_new_branch_calls"]
              and sum(r["cache_hit"] for r in summary["request_outcomes"]) == summary["cache_reused_request_rows"], path=str(folder))
        check("supplement_setup_plus_compute_equals_invocation", abs(summary["invocation_cpu_seconds"]
              - summary["setup_cpu_seconds"] - summary["cpu_seconds"]) < .1, path=str(folder))
        supplement_metrics.append({"path": str(folder), "manifest_sha256": completion.sha(folder / "manifest.json"),
            **{key: summary[key] for key in ("actual_new_branch_calls", "cache_reused_request_rows",
                "setup_cpu_seconds", "cpu_seconds", "invocation_cpu_seconds", "invocation_wall_seconds",
                "recollection_cpu_seconds", "successful_physical_branch_cpu_seconds", "failed_physical_branch_cpu_seconds",
                "search_calls_including_recollection", "search_work_including_recollection",
                "attempted_branches_with_unknown_search_accounting", "source_unchanged")},
            "failure_count": len(summary["failures"]),
            "not_executed": sum(r["status"] == "not_executed" for r in summary["request_outcomes"]),
            "memory": summary["memory_after"]})
    for assignment_key, shards in by_assignment.items():
        counts = {row[1] for row in shards}
        check("parallel_shards_share_complete_assignment_and_are_disjoint", len(counts) == 1
            and {row[0] for row in shards} == set(range(next(iter(counts))))
            and len(shards) == next(iter(counts))
            and all(row[3] == shards[0][3] for row in shards), assignment_sha256=assignment_key)
    evidence = {}
    for key, row in resolved.items():
        file = Path(row["file"])
        if file not in evidence:
            full = json.loads(gzip.decompress(file.read_bytes()))
            original = full.get("original_request", full)
            result = full["result"]
            physical.assert_invariants(physical.snapshot(result["final_snapshot"]))
            evidence[file] = {"identity": tuple(original[name] for name in ("sample", "candidate", "future_sha256", "horizon_ticks")),
                "status": full["status"], "cache_before_digest": completion.digest(full["cache_before"]),
                "end": result["final_snapshot"]["now"], "total_cost": result["total_cost"],
                "cost_components": result["cost_components"], "completed_bags": len(result["completed"]),
                "uncompleted_bags": len(result["uncompleted_bag_ids"]), "sha256": completion.sha(file)}
        saved = evidence[file]
        sample = samples[row["sample"]]["saved"]
        weighted = sum(saved["cost_components"][name] * weight for name, weight in physical.COST_WEIGHTS.items())
        check("final_request_uses_same_action_full_future_and_complete_result", saved["identity"] == completion.memo_key(row)
            and row["status"] == saved["status"] == "reached_horizon"
            and saved["end"] == sample["time"] + 80
            and all(row[name] == saved[name] for name in ("total_cost", "cost_components", "completed_bags", "uncompleted_bags"))
            and abs(weighted - row["total_cost"]) < 1e-8
            and saved["cache_before_digest"] == completion.digest(sample["routing_cache"]), request_key=key)
        if "artifact_sha256" in row:
            check("supplement_result_artifact_checksum", row["artifact_sha256"] == saved["sha256"], request_key=key)
    values = []
    for identity, source in samples.items():
        sample, label = source["saved"], source["label"]
        k = label["candidate_count"]
        check("reserved_candidate_zero_is_baseline", not k or sample["proposals"][0]["is_baseline"], identity=identity)
        local = [resolved[completion.request_key(row)] for row in label["raw_branches"]
                 if completion.request_key(row) in resolved]
        full = bool(k) and len(local) == k * 32
        index = {(row["group"], row["candidate"], row["draw"]): row for row in local}
        costs = [[index[g, c, f]["total_cost"] for g in range(4) for f in range(8)] for c in range(k)] if full else []
        means = [mean(vector) for vector in costs]
        component_means = [{name: mean(index[g, c, f]["cost_components"][name] for g in range(4) for f in range(8))
                           for name in physical.COST_WEIGHTS} for c in range(k)] if full else []
        state = physical.snapshot(sample["state"])
        immediate = []
        for proposal in sample["proposals"]:
            prefix = physical.ExecutionValidator._safe_prefix(state, physical.candidate(proposal))
            immediate.append({"legs": [physical.asdict(leg) for leg in prefix.legs],
                "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only})
        values.append({"identity": identity, "scene": source["scene"], "node": sample["source_node"],
            "time": sample["time"], "role": sample["role"], "band": sample["band"], "candidate_count": k,
            "physical_prefix_count": len(set(sample["physical_prefix_signatures"])),
            "complete_paired_label": full, "requested": k * 32, "resolved": len(local),
            "distinct_full_future_tapes": len({row["future_sha256"] for row in local}),
            "candidate_mean_costs": means if full else None,
            "candidate_mean_cost_components": component_means if full else None,
            "candidate_mean_completed_bags": [mean(index[g, c, f]["completed_bags"] for g in range(4) for f in range(8)) for c in range(k)] if full else None,
            "immediate_physical_prefixes": immediate,
            "mean_value_range": max(means) - min(means) if full else None,
            "exact_empirical_cost_vector_classes": len({tuple(v) for v in costs}) if full else None,
            "cost_vector_classes_at_1e_9": len({tuple(round(v, 9) for v in vector) for vector in costs}) if full else None,
            "baseline_mean_regret": means[0] - min(means) if full else None,
            "candidate_zero_is_baseline": sample["proposals"][0]["is_baseline"] if k else None,
            "paired_costs": costs if full else None})
    primary_summary = completion.read(prior / "summary.json")
    resources = {"primary": {"worker_cpu_seconds_sum": primary_summary["worker_cpu_seconds_sum"],
            "parent_cpu_seconds_excluding_workers": primary_summary["parent_cpu_seconds_excluding_workers"],
            "wall_makespan_seconds": primary_summary["wall_makespan_seconds"],
            "worker_wall_seconds_sum_not_makespan": primary_summary["worker_wall_seconds_sum_not_makespan"],
            "actual_calls": primary_summary["actual_full_simulator_calls"],
            "cache_reused_requests": primary_summary["cache_reused_branches"],
            "status_counts": primary_summary["branch_status_counts"]},
        "supplements": supplement_metrics,
        "combined_actual_attempts": primary_summary["actual_full_simulator_calls"] + sum(r["actual_new_branch_calls"] for r in supplement_metrics),
        "combined_cpu_seconds": primary_summary["worker_cpu_seconds_sum"] + primary_summary["parent_cpu_seconds_excluding_workers"]
            + sum(r["invocation_cpu_seconds"] for r in supplement_metrics),
        "supplement_wall_seconds_sum_not_makespan": sum(r["invocation_wall_seconds"] for r in supplement_metrics),
        "unique_successful_evidence_files": len(evidence),
        "scope": "primary plus all supplemental invocation expenses, including primary truncation and duplicate recollection; pilot and stopped earlier serial attempt reported separately, never silently counted as zero"}
    prior_root = prior.parent
    pilot = completion.read(prior_root / "phase4_w3_network_role_pilot_20261009" / "summary.json")
    resources["prior_pilot"] = {"actual_calls": pilot["actual_full_simulator_calls"], "cpu_seconds": pilot["cpu_seconds"], "wall_seconds": pilot["wall_seconds"]}
    stopped = prior_root / "phase4_w3_network_role_labels_20261009"
    interrupted = completion.read(stopped / "interruption.json")
    resources["prior_stopped_serial_attempt"] = {"record": interrupted,
        "saved_branch_files": len(list(stopped.glob("*.json.gz"))),
        "complete_invocation_cpu_known": False, "excluded_from_numeric_cumulative_total": True}
    payload = {"schema": "ics_v3_original_network_labels_complete_ledger_audit_v1", "primary": str(prior),
        "primary_manifest_sha256": completion.sha(prior / "manifest.json"), "supplement_references": references,
        "original_requests": len(requests), "resolved_requests": len(resolved), "samples": len(samples),
        "checks": len(checks), "passed": sum(row["passed"] for row in checks),
        "failed_checks": [row for row in checks if not row["passed"]], "checks_detail": checks,
        "roles": dict(Counter(row["role"] for row in values)), "zero_candidate_cells": sum(row["candidate_count"] == 0 for row in values),
        "physical_and_empirical_value_classes": values, "resources": resources,
        "new_independent_source_count": 0,
        "limits": ["Old synthetic development streams on unmodified original topology; no real airport task history or calibrated module-permission claim.",
            "Absent arrival-at-destination selector calls remain absent; one actually zero-candidate origin cell remains zero.",
            "Finite h80 conditional cost vectors are not universal action equivalence or an evaluation of a newly learned deployment.",
            "All32 draw weights are retained even when full future tapes repeat; exact memo reuse is not additional independent evidence.",
            "All original requests selected without inspecting costs; completed results never replaced; original failures and cooperative truncation retained.",
            "Supplement shards duplicate collection expense; process memory peaks must not be summed as simultaneous aggregate memory."]}
    completion.write_new_json(output / "audit.json", payload)
    completion.write_new_json(output / "resolved_request_ledger.json", resolved)
    (output / "audit_source.py").write_bytes(Path(__file__).read_bytes())
    for helper in ("audit.py", "complete_missing.py"):
        (output / helper).write_bytes(Path(__file__).with_name(helper).read_bytes())
    completion.write_new_json(output / "manifest.json", {p.name: completion.sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps({key: payload[key] for key in ("original_requests", "resolved_requests", "samples", "checks", "passed", "roles", "zero_candidate_cells")}))
    return int(bool(payload["failed_checks"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--history", nargs="*", default=(), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.prior, args.history, args.output))
