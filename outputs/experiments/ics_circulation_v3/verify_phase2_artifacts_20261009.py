"""Independently verify saved ICS V3 evidence, without importing/running experiments.

Run from any directory: python outputs/experiments/ics_circulation_v3/verify_phase2_artifacts_20261009.py
Only the verification JSON is written. Archived source, rather than the mutable
working tree, is the authority for each historical experiment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
from math import isclose
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
CONFIRM = BASE / "phase2_learning_confirmatory_20261009"
DISCOVERY = BASE / "phase2_learning_20261009"
ARCHIVE = BASE / "phase2_confirmed_source_20261009"
OUTPUT = BASE / "phase2_verification_20261009.json"
checks = []
input_hashes = {}


def rel(path):
    return path.relative_to(ROOT).as_posix()


def digest(path):
    value = sha256(path.read_bytes()).hexdigest()
    input_hashes[rel(path)] = value
    return value


def read_json(path):
    digest(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_rows(path):
    digest(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def record(name, okay, evidence):
    checks.append({"check": name, "status": "passed" if okay else "failed", "evidence": evidence})


def close(a, b):
    return isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def archived_hashes(name, mapping, archive):
    rows = []
    for original, expected in mapping.items():
        p = Path(original)
        candidate = archive / "tests" / p.name if p.parts[0] == "tests" else archive / p.name
        if not candidate.exists() and (archive / p.name).exists():
            candidate = archive / p.name
        actual = digest(candidate) if candidate.is_file() else None
        rows.append({"original": original, "archive": rel(candidate), "expected": expected,
                     "actual": actual, "matches": actual == expected})
    record(name, bool(rows) and all(r["matches"] for r in rows),
           {"file_count": len(rows), "matched_files": sum(r["matches"] for r in rows), "files": rows})


def verify_learning():
    manifest = read_json(CONFIRM / "split_manifest.json")
    old_manifest = read_json(DISCOVERY / "split_manifest.json")
    summary = read_json(CONFIRM / "summary.json")
    groups = manifest["groups"]
    expected_counts = {"train": 80, "validation": 20, "test": 40, "deployment": 40}
    counts = {split: len(ids) for split, ids in groups.items()}
    intersections = {f"{a}/{b}": sorted(set(groups[a]) & set(groups[b])) for a, b in combinations(groups, 2)}
    record("confirmed_split_counts_and_disjointness", counts == expected_counts
           and all(len(ids) == len(set(ids)) for ids in groups.values())
           and not any(intersections.values()), {"counts": counts, "cross_split_intersections": intersections})
    old_all = set().union(*map(set, old_manifest["groups"].values()))
    freshness = {split: sorted(set(groups[split]) & old_all) for split in ("test", "deployment")}
    record("fresh_confirmatory_test_and_deployment", not any(freshness.values())
           and all(groups[s] == old_manifest["groups"][s] for s in ("train", "validation")),
           {"old_source_intersections": freshness, "train_validation_groups_unchanged":
            {s: groups[s] == old_manifest["groups"][s] for s in ("train", "validation")},
            "evaluation_namespace": manifest.get("evaluation_namespace")})
    rows = read_rows(CONFIRM / "candidates.jsonl")
    branches = read_rows(CONFIRM / "branches.jsonl")
    deployment = read_rows(CONFIRM / "deployment.jsonl")
    sources = read_rows(CONFIRM / "sources.jsonl")
    record("confirmed_artifact_counts", (len(rows), len(branches), len(deployment), len(sources)) == (560, 1120, 240, 140)
           and (summary["candidate_rows"], summary["paired_branch_rollouts"], summary["deployment_runs"]) == (560, 1120, 240),
           {"candidate_rows": len(rows), "paired_branches": len(branches), "deployment_runs": len(deployment),
            "source_records": len(sources)})
    candidate_groups = defaultdict(list)
    for row in rows:
        candidate_groups[row["source_group"]].append(row)
    expected_label_groups = set().union(*(set(groups[s]) for s in ("train", "validation", "test")))
    record("four_candidates_per_label_source", set(candidate_groups) == expected_label_groups
           and all(sorted(r["candidate_index"] for r in items) == [0, 1, 2, 3] for items in candidate_groups.values())
           and all(row["source_group"] in groups[row["split"]] for row in rows),
           {"candidate_count_histogram": dict(Counter(len(items) for items in candidate_groups.values())),
            "source_groups": len(candidate_groups)})
    lookup = {(r["source_group"], r["candidate_index"], r["future_seed"]): r for r in branches}
    seeds = manifest["label_seeds"]
    expected_keys = {(r["source_group"], r["candidate_index"], seed) for r in rows for seed in seeds}
    record("paired_branch_key_coverage", len(lookup) == len(branches) and set(lookup) == expected_keys
           and seeds == [0, 1] and all(r["source_group"] in groups[r["split"]] for r in branches),
           {"branch_keys": len(lookup), "expected_keys": len(expected_keys), "future_seeds": seeds})
    mismatches = []
    baseline_errors = []
    for row in rows:
        key = (row["source_group"], row["candidate_index"])
        costs = [lookup[(*key, seed)]["total_cost"] for seed in seeds]
        baseline = [lookup[(key[0], 0, seed)]["total_cost"] for seed in seeds]
        deltas = [a - b for a, b in zip(costs, baseline)]
        okay = (len(row["costs"]) == len(costs) and len(row["paired_deltas"]) == len(deltas)
                and all(close(a, b) for a, b in zip(costs, row["costs"]))
                and all(close(a, b) for a, b in zip(deltas, row["paired_deltas"]))
                and close(sum(costs) / len(costs), row["cost_mean"])
                and close(sum(deltas) / len(deltas), row["delta_mean"]))
        if not okay:
            mismatches.append({"source_group": key[0], "candidate_index": key[1]})
        if row["is_baseline"]:
            if key[1] != 0 or any(value != 0 for value in row["paired_deltas"]
                                 + [row[field] for field in ("delta_mean", "analytic_delta", "timed_delta", "forecast_delta")]):
                baseline_errors.append(key)
    record("paired_cost_and_delta_arithmetic", not mismatches, {"rows_checked": len(rows), "mismatches": mismatches})
    record("baseline_deltas_exactly_zero", not baseline_errors and sum(r["is_baseline"] for r in rows) == 140,
           {"baseline_rows": sum(r["is_baseline"] for r in rows), "errors": baseline_errors,
            "fields": ["paired_deltas", "delta_mean", "analytic_delta", "timed_delta", "forecast_delta"]})
    policies = {"baseline", "analytic", "timed", "direct", "residual", "forecast_rollout"}
    deploy_keys = {(r["source_group"], r["policy"]) for r in deployment}
    record("independent_deployment_policy_coverage", len(deploy_keys) == 240
           and deploy_keys == {(g, p) for g in groups["deployment"] for p in policies},
           {"unique_source_policy_keys": len(deploy_keys), "policies": dict(Counter(r["policy"] for r in deployment)),
            "deployment_seed": manifest["deployment_seed"]})
    weight = {"tray_wait": 1.0, "nonprotected_tardiness": 1.0, "empty_distance": .1,
              "terminal_backlog": 10.0, "terminal_inflight": 2.0}
    invalid_costs = [{"row": i, "source_group": r["source_group"]} for i, r in enumerate(branches + deployment)
                     if not close(r["total_cost"], sum(weight[k] * v for k, v in r["cost_components"].items()))]
    record("shared_cost_weight_arithmetic", not invalid_costs,
           {"weights": weight, "rows_checked": len(branches) + len(deployment), "errors": invalid_costs})
    for kind in ("direct", "residual"):
        new_file, old_file = CONFIRM / f"{kind}_model.json", DISCOVERY / f"{kind}_model.json"
        new_hash, old_hash = digest(new_file), digest(old_file)
        record(f"{kind}_model_byte_identical_to_discovery", new_file.read_bytes() == old_file.read_bytes(),
               {"confirmed_sha256": new_hash, "discovery_sha256": old_hash, "bytes": new_file.stat().st_size})
    record("evaluation_source_stable_during_run", summary.get("source_changed_during_run") is False,
           {"source_changed_during_run": summary.get("source_changed_during_run")})
    archived_hashes("confirmatory_source_hashes_match_confirmed_archive", summary["source_sha256"], ARCHIVE)
    archived_hashes("confirmed_archive_manifest_matches_files", read_json(ARCHIVE / "source_manifest.json"), ARCHIVE)
    archived_hashes("discovery_source_hashes_match_historical_archive",
                    read_json(DISCOVERY / "summary.json")["source_sha256"], BASE / "phase2_discovery_source_20261009")
    archived_hashes("phase1_source_hashes_match_historical_archive",
                    read_json(BASE / "pilot_20261009/summary.json")["source_sha256"], BASE / "phase1_source_20261009")


def verify_routing():
    directory = BASE / "tiny_matched_routing_20261009"
    requests, pairs = read_rows(directory / "requests.jsonl"), read_rows(directory / "matched_pairs.jsonl")
    summary = read_json(directory / "summary.json")
    grouped = defaultdict(list)
    for row in requests:
        grouped[(row["repeat"], row["source_group"])].append(row)
    problems = []
    for key, items in grouped.items():
        planners = {r["planner"]: r for r in items}
        if len(items) != 2 or set(planners) != {"reference", "regional"}:
            problems.append({"key": key, "reason": "planner_coverage"})
            continue
        witness = lambda row: sorted(json.dumps(w, sort_keys=True) for w in row["candidate_witnesses"])
        if witness(planners["reference"]) != witness(planners["regional"]):
            problems.append({"key": key, "reason": "different_exact_timed_witnesses"})
        index = int(key[1].split(":")[-1])
        expected = ["reference", "regional"] if (key[0] + index) % 2 == 0 else ["regional", "reference"]
        if [r["planner"] for r in sorted(items, key=lambda r: r["execution_order_index"])] != expected:
            problems.append({"key": key, "reason": "nonalternating_order"})
    pair_keys = {(p["repeat"], p["source_group"]) for p in pairs}
    record("tiny_72_pairs_144_requests_exact_timed_parity", len(requests) == 144 and len(pairs) == 72
           and len(grouped) == 72 and len(pair_keys) == 72 and set(grouped) == pair_keys
           and not problems and all(p["same_timed_candidate_set"] for p in pairs)
           and all(r["all_valid"] and r["committed"] and r["candidate_count"] == 3 for r in requests)
           and summary["request_count"] == 144 and summary["pair_count"] == 72,
           {"requests": len(requests), "pairs": len(pairs), "independently_matched_pairs": len(grouped) - len(problems),
            "order_first_counts": dict(Counter(r["planner"] for r in requests if r["execution_order_index"] == 0)),
            "problems": problems})
    archived_hashes("tiny_source_hashes_match_confirmed_archive", summary["source_sha256"], ARCHIVE)
    directory = BASE / "nanning_routing_100od_20261009"
    rows, summary = read_rows(directory / "requests.jsonl"), read_json(directory / "summary.json")
    counts = Counter(r["partitions"] for r in rows)
    unique = {(r["partitions"], r["repeat"], r["od_index"]) for r in rows}
    good = sum(r["all_candidates_valid"] and r["committed"] and r["candidate_count"] > 0
               and r["status"] == "new_route_success" for r in rows)
    shortest = sum(r["static_shortest_match"] and r["best_candidate_arrival_ticks"] == r["static_dijkstra_reference_ticks"] for r in rows)
    record("nanning_300_valid_commits_and_shortest_reference", len(rows) == len(unique) == good == shortest == 300
           and counts == {4: 100, 8: 100, 16: 100} and summary["total_requests"] == 300,
           {"requests": len(rows), "unique_request_keys": len(unique), "valid_commits": good,
            "independent_stored_dijkstra_matches": shortest, "requests_by_partition": dict(counts),
            "full_k_coverage_by_partition": {p: sum(r["candidate_count"] == r["requested_candidates"] for r in rows if r["partitions"] == p)
                                             for p in (4, 8, 16)},
            "note": "Verifies recorded validation/commit outcomes and arithmetic; does not re-execute runtime."})
    archived_hashes("nanning_source_hashes_match_confirmed_archive", summary["source_sha256"], ARCHIVE)


def main():
    for name, function in (("learning_artifacts", verify_learning), ("routing_artifacts", verify_routing)):
        try:
            function()
        except Exception as exc:
            checks.append({"check": name, "status": "error", "evidence": {"exception": repr(exc)}})
    failures = [r["check"] for r in checks if r["status"] != "passed"]
    output = {"schema": "ics_v3_independent_artifact_verification_v1",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Read and hash saved evidence only; no experiment imports, simulations, fitting or timing runs",
              "verifier": rel(Path(__file__).resolve()), "verifier_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "passed": not failures, "check_count": len(checks), "failed_checks": failures,
              "checks": checks, "input_sha256": dict(sorted(input_hashes.items())),
              "limitations": ["Matching records proves artifact consistency, not independent operational correctness.",
                              "Hash comparisons use each experiment's archived source, not the current mutable working tree.",
                              "Source-ID disjointness does not imply a different topology family or real-world independence."]}
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": rel(OUTPUT), "passed": output["passed"], "check_count": len(checks),
                      "failed_checks": failures}, ensure_ascii=False))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
