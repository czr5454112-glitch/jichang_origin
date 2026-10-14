"""Reproduce the matched tiny-map routing comparison without rollout labels.

python -m scripts.experiments.ics_circulation_v3.run_routing_comparison --scene-count 24 --repeats 3

Both planners receive identical cloned initial states, K=3, horizon=48 and an
expansion budget of 2000. Every route witness (edge and time) must agree. The
request timer includes generation, full revalidation and first-route commit;
state cloning, static scenario construction and output I/O are outside it.
"""
from __future__ import annotations

from .experiment_protocol import check_output_directory, create_output_directory

import argparse
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

from .routing import RegionalCandidateGenerator, clear_static_cache
from .run_pilot import quantiles, write_json
from .runtime import CandidateGenerator, ExecutionValidator
from .scenarios import pilot_scenes

ROOT = Path(__file__).resolve().parents[3]


def witness(candidate):
    return {"legs": [[leg.edge_id, leg.depart, leg.arrive] for leg in candidate.legs],
            "unload_complete": candidate.unload_complete, "usable_at": candidate.usable_at}


def run(output: Path, *, scene_count=24, repeats=3, horizon=48, expansion_limit=2000, k=3):
    all_scenes = pilot_scenes()
    if not 1 <= scene_count <= len(all_scenes) or repeats < 1:
        raise ValueError("scene_count must be 1..24 and repeats must be positive")
    if min(horizon, expansion_limit, k) < 1:
        raise ValueError("horizon, expansion_limit and k must be positive")
    output = create_output_directory(output)
    rows, pairs = [], []
    clear_static_cache()
    for repeat in range(repeats):
        for scene_index, scene in enumerate(all_scenes[:scene_count]):
            observed = {}
            order = (("reference", "regional") if (repeat + scene_index) % 2 == 0 else ("regional", "reference"))
            for order_index, name in enumerate(order):
                state = scene.state.clone()
                planner = (CandidateGenerator(horizon=horizon, expansion_limit=expansion_limit)
                           if name == "reference" else
                           RegionalCandidateGenerator(horizon=horizon, expansion_limit=expansion_limit, deadline_ms=None))
                authority = ExecutionValidator()
                started = perf_counter()
                candidates = planner.generate(state, scene.target_bag_id, scene.target_tray_id, k)
                generation_ms = (perf_counter() - started) * 1000
                before = perf_counter()
                validations = [authority.validate(state, candidate) for candidate in candidates]
                validation_ms = (perf_counter() - before) * 1000
                before = perf_counter()
                committed = authority.commit(state, candidates[0]).accepted if candidates else False
                commit_ms = (perf_counter() - before) * 1000
                elapsed_ms = (perf_counter() - started) * 1000
                witnesses = sorted((witness(candidate) for candidate in candidates),
                                   key=lambda value: json.dumps(value, sort_keys=True))
                observed[name] = witnesses
                rows.append({"repeat": repeat, "source_group": scene.scene_id, "planner": name,
                             "execution_order_index": order_index, "candidate_count": len(candidates),
                             "all_valid": all(row.accepted for row in validations) if candidates else False,
                             "committed": committed, "generation_ms": generation_ms,
                             "validation_ms": validation_ms, "commit_ms": commit_ms,
                             "local_request_ms": elapsed_ms, "status": planner.last_search_status,
                             "expansions": planner.last_expansions, "candidate_witnesses": witnesses})
            pairs.append({"repeat": repeat, "source_group": scene.scene_id, "execution_order": order,
                          "same_timed_candidate_set": observed["reference"] == observed["regional"]})
    summary = {
        "schema": "ics_v3_matched_tiny_routing_comparison_v1",
        "scope": "same_synthetic_initializations_local_routing_not_real_map_or_distributed_speedup",
        "source_groups": scene_count, "repeats": repeats, "request_count": len(rows),
        "pair_count": len(pairs), "timed_candidate_set_matches": sum(pair["same_timed_candidate_set"] for pair in pairs),
        "same_timed_candidate_sets": all(pair["same_timed_candidate_set"] for pair in pairs),
        "all_requested_candidates_found": all(row["candidate_count"] == k for row in rows),
        "all_valid_and_committed": all(row["all_valid"] and row["committed"] for row in rows),
        "horizon": horizon, "expansion_limit": expansion_limit, "candidate_count": k,
        "wall_budget": None, "order": "reference_first_when_(repeat+scene_index)%2==0_else_regional_first",
        "time_scope": "generation_plus_full_revalidation_plus_first_candidate_commit_including_authority_checks",
        "excluded_from_time": ["initial_state_clone", "scenario_construction", "file_IO", "network_communication"],
        "cache_protocol": "clear_regional_static_cache_before_suite_then_retain_content_cache_across_queries",
        "timing_ms": {name: quantiles([row["local_request_ms"] for row in rows if row["planner"] == name])
                      for name in ("reference", "regional")},
        "phase_timing_ms": {name: {field: quantiles([row[field] for row in rows if row["planner"] == name])
                                   for field in ("generation_ms", "validation_ms", "commit_ms")}
                            for name in ("reference", "regional")},
        "limits": ["Repeated timing of the same 24 source initializations, not independent operating days",
                   "Exact timed candidate agreement is asserted for these fixtures, not for arbitrary maps",
                   "Regional abstraction intentionally retains bounded static local witnesses and may omit other routes"],
        "source_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                          for name in ("experiment_protocol.py", "routing.py", "runtime.py", "model.py", "scenarios.py", "run_routing_comparison.py")},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    write_json(output / "summary.json", summary)
    for filename, records in (("requests.jsonl", rows), ("matched_pairs.jsonl", pairs)):
        (output / filename).write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records), encoding="utf-8")
    if not summary["same_timed_candidate_sets"] or not summary["all_valid_and_committed"] or not summary["all_requested_candidates_found"]:
        raise RuntimeError("Matched comparison failed; inspect saved candidates and denominators")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-count", type=int, default=24)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/experiments/ics_circulation_v3/tiny_matched_routing_20261009")
    args = parser.parse_args()
    summary = run(args.output, scene_count=args.scene_count, repeats=args.repeats)
    print(json.dumps({key: summary[key] for key in ("request_count", "timed_candidate_set_matches", "all_valid_and_committed", "timing_ms")}, indent=2))


if __name__ == "__main__":
    main()
