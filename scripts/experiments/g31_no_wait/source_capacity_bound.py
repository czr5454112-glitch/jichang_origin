"""Optimistic FIFO single-egress capacity lower bound; no native simulation."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, ROUND_CEILING
import hashlib
import heapq
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "outputs/experiments/g31_nonstop_contract_20261024_draft001/contract_manifest.json"
FREQUENCY = 1000000


def ticks(value):
    exact = Decimal(str(value)) * FREQUENCY
    if not exact.is_finite() or exact < 0 or exact != exact.to_integral_value():
        raise ValueError("input is not on the nonnegative integer-microsecond grid")
    return int(exact)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fifo_recurrence(releases, gap=2000000):
    """Sorted lower bounds on first-edge entry; returns the earliest sequence."""
    result = []
    for release in releases:
        if release < 0 or (result and release < releases[len(result)-1]):
            raise ValueError("releases must be nonnegative and sorted")
        result.append(max(release, result[-1] + gap) if result else release)
    return result


def static_costs(profile, goal, speed=2):
    service = {int(n["location"]): ticks(n["service_time"]) for n in profile["nodes"]}
    reverse = {n: [] for n in service}
    for edge in profile["edges"]:
        u, v = int(edge["start"]), int(edge["end"])
        travel = ticks(Decimal(str(edge["length"])) / Decimal(str(speed)))
        reverse[v].append((u, service[u] + travel))
    distance = {goal: 0}
    pending = [(0, goal)]
    while pending:
        cost, node = heapq.heappop(pending)
        if cost != distance[node]:
            continue
        for before, duration in reverse[node]:
            candidate = cost + duration
            if before not in distance or candidate < distance[before]:
                distance[before] = candidate
                heapq.heappush(pending, (candidate, before))
    return distance


def single_egress_bound(rows, profile, source=53, horizon=98259, gap=2, release_quantum=1):
    rows = list(rows)
    node = next(n for n in profile["nodes"] if n["location"] == source)
    outgoing = [e for e in profile["edges"] if e["start"] == source]
    if len(outgoing) != 1 or ticks(node["service_time"]) != 0:
        raise ValueError("this bound requires a zero-service source with exactly one outgoing edge")
    indexed = [(i, r) for i, r in enumerate(rows) if r["start"] == source]
    if not indexed or any(r["leg"] != "storage_out" or r["goal"] == source for _, r in indexed):
        raise ValueError("all source tasks must be outbound legs that require the sole outgoing edge")
    if len({r["task_id"] for _, r in indexed}) != len(indexed):
        raise ValueError("each outbound segment must represent a distinct business")
    indexed.sort(key=lambda pair: Decimal(str(pair[1]["pass_time"])))
    quantum = Decimal(str(release_quantum))
    release = [ticks((Decimal(str(r["pass_time"])) / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum)
               for _, r in indexed]
    entries = fifo_recurrence(release, ticks(gap))
    distances = {goal: static_costs(profile, goal) for goal in {r["goal"] for _, r in indexed}}
    trace = []
    for (original_index, row), earliest, nominal in zip(indexed, entries, release):
        if source not in distances[row["goal"]]:
            raise ValueError("statically unreachable goal requires a separate infinity certificate")
        remaining = distances[row["goal"]][source]
        trace.append(dict(segment_id=row["segment_id"], task_id=row["task_id"], original_row=original_index,
                          goal=row["goal"], nominal_release_tick=nominal,
                          earliest_edge_entry_tick=earliest, static_remaining_tick=remaining,
                          goal_finish_lower_bound_tick=earliest + remaining))
    cutoff = ticks(horizon)
    miss = [r for r in trace if r["goal_finish_lower_bound_tick"] > cutoff]
    last_finish = max(trace, key=lambda r: r["goal_finish_lower_bound_tick"])
    # Closed form of the final FIFO entry lower bound, independent check.
    witnesses = [r + ticks(gap) * (len(release) - 1 - j) for j, r in enumerate(release)]
    witness_index = max(range(len(witnesses)), key=witnesses.__getitem__)
    assert witnesses[witness_index] == entries[-1]
    waits = [e-r for e, r in zip(entries, release)]
    return dict(
        schema="g31.optimistic_single_egress_lower_bound.v1", source=source,
        outgoing_edge=[source, outgoing[0]["end"]], source_service_seconds=0,
        headway_seconds=gap, speed_mps=2, release_quantum_seconds=release_quantum,
        horizon_seconds=horizon, source_tasks=len(trace), source_leg_counts=dict(Counter(r["leg"] for _, r in indexed)),
        canonical_business_count=len({r["task_id"] for r in rows}), canonical_segment_count=len(rows),
        formula={"order": "raw canonical pass_time ascending, stable original row order for ties",
                 "release": "r_i = ceil(pass_time_i / release_quantum) * release_quantum",
                 "edge_entry": "s_1=r_1; s_i=max(r_i,s_(i-1)+2 seconds)",
                 "freeflow": "H(v,g)=min_(v,w)(service(v)+travel(v,w)+H(w,g)); H(g,g)=0",
                 "finish": "L_i=s_i+H(source,goal_i); actual physical finish_i >= L_i",
                 "proof": "Induction: no source FIFO overtaking, no entry before nominal release, and the common directed edge requires two-second spacing. Removing other traffic and EBS precedence can only make this necessary bound earlier. Every continuation costs at least static H."},
        earliest_first_edge_entry_seconds=entries[0]/FREQUENCY,
        final_edge_entry_lower_bound_seconds=entries[-1]/FREQUENCY,
        all_outbound_delivered_time_lower_bound_seconds=last_finish["goal_finish_lower_bound_tick"]/FREQUENCY,
        final_resource_drain_time_not_computed=True,
        cannot_enter_edge_by_horizon_lower_bound=sum(t > cutoff for t in entries),
        cannot_finish_by_horizon_lower_bound=len(miss),
        unique_businesses_cannot_finish_lower_bound=len({r["task_id"] for r in miss}),
        ideal_source_wait_from_nominal_sum_seconds=sum(waits)/FREQUENCY,
        ideal_source_wait_from_nominal_mean_seconds=sum(waits)/FREQUENCY/len(waits),
        ideal_source_wait_from_nominal_max_seconds=max(waits)/FREQUENCY,
        final_entry_closed_form_witness=dict(index=witness_index,
            segment_id=trace[witness_index]["segment_id"], release_seconds=release[witness_index]/FREQUENCY,
            remaining_gap_count=len(trace)-1-witness_index,
            final_entry_seconds=witnesses[witness_index]/FREQUENCY),
        maximum_finish_witness=last_finish, first_five=trace[:5], last_five=trace[-5:],
        missed_examples=miss[:10], missed_ids_sha256=digest_json([r["segment_id"] for r in miss]),
        entire_ordered_trace_sha256=digest_json(trace),
        relaxation=["Ignore inbound completion and EBS causal gate.",
                    "Ignore other traffic at node49 and every downstream calendar conflict.",
                    "Allow each bag its own shortest continuation even when those continuations conflict.",
                    "Ignore algorithm budgets, real planning cost, and extra source retry delays."],
        interpretation="A necessary lower bound for the fixed canonical FIFO/physical contract, not an achievable full-network schedule. A zero missed count proves no positive obstruction from this relaxation alone; it does not prove that all observed misses are algorithmically avoidable. The maximum finish is a lower bound on delivery drain time, not on resource-ledger cleanup or a predicted actual finish."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cell = manifest["cells"]["nanning_2x"]
    canonical = Path(cell["canonical"]["path"])
    profile_path = Path(manifest["maps"]["nanning"]["draft_profile"]["path"])
    assert sha(canonical) == cell["canonical"]["sha256"]
    assert sha(profile_path) == manifest["maps"]["nanning"]["draft_profile"]["sha256"]
    rows = [json.loads(s) for s in canonical.read_text(encoding="utf-8").splitlines() if s]
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    result = single_egress_bound(rows, profile)
    other_path = Path(manifest["maps"]["map2"]["draft_profile"]["path"])
    other = json.loads(other_path.read_text(encoding="utf-8"))
    other_source = manifest["cells"]["map2_2x"]["storage_out_start"]
    other_edges = [[e["start"], e["end"]] for e in other["edges"] if e["start"] == other_source]
    result["map2_boundary"] = dict(source=other_source, outgoing_edges=other_edges,
        source_service_seconds=next(n["service_time"] for n in other["nodes"] if n["location"] == other_source),
        single_channel_half_bag_per_second_bound_applies=False,
        explanation="Two separate directed-edge entrance resources. Their combined ideal capacity upper bound is one bag/second; the common source-feed rule also permits at most one admission/second. Neither proves this rate is achievable for all destinations/downstream conflicts. Do not serialize all map2 outbound bags with a common two-second recurrence.")
    result["provenance"] = dict(canonical=str(canonical), canonical_sha256=sha(canonical),
                                physical_profile=str(profile_path), physical_profile_sha256=sha(profile_path),
                                map2_profile_sha256=sha(other_path), manifest_sha256=sha(MANIFEST),
                                script_sha256=sha(__file__), native_simulation_executed=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("source_tasks", "cannot_finish_by_horizon_lower_bound",
          "final_edge_entry_lower_bound_seconds", "all_outbound_delivered_time_lower_bound_seconds",
          "ideal_source_wait_from_nominal_mean_seconds")}))


if __name__ == "__main__":
    main()
