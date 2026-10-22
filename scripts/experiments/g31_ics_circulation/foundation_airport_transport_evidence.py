"""Read-only TRAIN opportunity and time-scale evidence for terminal transport.

This offline evaluator consumes closed historical runs. It never dispatches,
modifies a ledger, or passes future arrival labels to a policy. Missing samples
remain missing and observation-limited episodes retain their censoring flags.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

from .foundation_airport_json_stream import iter_json_array_gz
from .foundation_airport_inventory_projection import prepare_inventory_projection
from .foundation_airport_inventory_spi_campaign import read_bound

SCHEMA = "g31.foundation.airport_terminal_transport_evidence.v1"


def read(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def binding(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


def distribution(values):
    values = sorted(float(x) for x in values)
    if any(not math.isfinite(x) for x in values):
        raise ValueError("transport_evidence:nonfinite_value")
    def quantile(q):
        if not values:
            return None
        rank = (len(values) - 1) * q
        lo, hi = math.floor(rank), math.ceil(rank)
        return values[lo] + (values[hi] - values[lo]) * (rank - lo)
    return dict(count=len(values), minimum=min(values, default=None),
                p50=quantile(.5), p90=quantile(.9), p95=quantile(.95),
                maximum=max(values, default=None),
                mean=math.fsum(values) / len(values) if values else None)


def opportunity_summary(decisions):
    counts, candidates, sources, destinations, trays = Counter(), [], [], [], []
    examples = []
    for decision in decisions:
        catalog = decision["catalog"]
        moves = [x for x in catalog["candidates"] if x["kind"] == "transfer"]
        ns = len({x["source"] for x in moves})
        nd = len({x["destination"] for x in moves})
        nt = len({x["tray_id"] for x in moves})
        counts["post_priority_visits"] += 1
        candidates.append(len(moves)); sources.append(ns); destinations.append(nd); trays.append(nt)
        counts["legal_transfer_opportunities"] += bool(moves)
        counts["no_legal_transfer"] += not moves
        counts["multiple_sources"] += ns > 1
        counts["multiple_trays"] += nt > 1
        counts["multiple_destinations"] += nd > 1
        counts["multiple_sources_and_destinations"] += ns > 1 and nd > 1
        counts["one_tray_one_destination_degenerate"] += nt == 1 and nd == 1
        if nt > 1 and nd > 1 and len(examples) < 3:
            examples.append(dict(at=decision["decision_time"], owner_id=decision["owner_id"],
                public_observation_ref=decision["public_observation_ref"],
                legal_catalog_ref=decision["legal_catalog_ref"], source_count=ns,
                destination_count=nd, tray_count=nt, candidate_count=len(moves)))
    denominator = counts["legal_transfer_opportunities"]
    return dict(counts=dict(counts), ratios_among_legal_opportunities={key:
        counts[key] / denominator if denominator else None for key in
        ("multiple_sources", "multiple_trays", "multiple_destinations",
         "multiple_sources_and_destinations", "one_tray_one_destination_degenerate")},
        candidate_count=distribution(candidates), source_count=distribution(sources),
        destination_count=distribution(destinations), tray_count=distribution(trays),
        multi_tray_multi_destination_examples=examples,
        competition_interpretation="multiple legal alternatives; positive marginal demand competition is not established")


def arrival_count_distributions(jobs, terminals, *, start, end, widths=(60, 300, 600)):
    """Offline truth labels only, with a complete zero-bin denominator."""
    result = {}
    for width in widths:
        if width <= 0 or end <= start:
            raise ValueError("transport_evidence:invalid_window")
        n = math.ceil((end - start) / width)
        bins = {node: [0] * n for node in terminals}
        for job in jobs:
            if job["origin"] in bins and start <= job["arrival"] < end:
                bins[job["origin"]][min(n - 1, int((job["arrival"] - start) // width))] += 1
        result[str(width)] = {str(node): dict(distribution(values),
            zero_fraction=sum(x == 0 for x in values) / n,
            total_arrivals=sum(values), final_bin_seconds=(end - start) - (n - 1) * width)
            for node, values in bins.items()}
    return result


def observation_episodes(samples, *, max_gap_seconds=60.):
    """Intervals based on consecutive own-sensor samples; never bridge gaps.

    A shortage means known positive waiting with zero current empty stock.
    Stock depletion is an observed positive-stock to zero-stock transition.
    These are sampling bounds, not exact continuous native event durations.
    """
    episodes, depletions, gaps = [], [], 0
    active = None
    stocked_at = None
    previous = None
    for sample in sorted(samples, key=lambda x: x["at"]):
        at, stock, waiting = sample["at"], sample["stock"], sample["waiting"]
        continuous = previous is not None and 0 < at - previous["at"] <= max_gap_seconds
        if previous is not None and not continuous:
            gaps += 1
            if active:
                episodes.append(dict(active, end=previous["at"], right_censored=True))
                active = None
            stocked_at = None
        known = stock is not None and waiting is not None
        if not known:
            if active:
                episodes.append(dict(active, end=previous["at"], right_censored=True))
                active = None
            stocked_at = None
        else:
            if stock > 0 and stocked_at is None:
                stocked_at = at
            if stock == 0 and stocked_at is not None:
                depletions.append(at - stocked_at)
                stocked_at = None
            shortage = stock == 0 and waiting > 0
            if shortage and active is None:
                active = dict(start=at, left_censored=not continuous or
                              previous["stock"] is None or previous["waiting"] is None)
            if not shortage and active:
                episodes.append(dict(active, end=at, right_censored=False))
                active = None
        previous = sample
    if active:
        episodes.append(dict(active, end=previous["at"], right_censored=True))
    for row in episodes:
        row["observed_duration_seconds"] = row["end"] - row["start"]
    return dict(samples=len(samples), missing_samples=sum(x["stock"] is None or x["waiting"] is None for x in samples),
                gaps=gaps, shortage_episodes=episodes, observed_stock_to_zero_seconds=distribution(depletions))


def analyze_run(directory):
    directory = Path(directory)
    plan, receipt = read(directory / "plan.json"), read(directory / "receipt.json")
    if plan["parent"]["split"] != "train":
        raise ValueError("transport_evidence:train_only")
    if receipt["worker"].get("scientific_status") != "closed" or receipt["process"].get("exitcode") != 0:
        raise ValueError("transport_evidence:closed_run_required")
    trajectory = read(directory / "trajectory.json.gz")
    if trajectory["manifest"]["split"] != "train" or trajectory["scientific_status"] != "closed_finite_horizon":
        raise ValueError("transport_evidence:closed_train_trajectory_required")
    population = read_bound(plan["input"])
    terminal = read(directory / "terminal_evidence.json.gz")
    observation_path = directory / "observations.json.gz"
    observed, loaders = defaultdict(list), set()
    for row in iter_json_array_gz(observation_path):
        obs = row["observation"]
        current = prepare_inventory_projection(obs)
        loaders.update(obs["static_role_contract"]["loader_nodes"])
        for node in obs["static_role_contract"]["loader_nodes"]:
            state = current.nodes[node]
            if state["local"]:
                observed[node].append(dict(at=obs["now"],
                    stock=state["stock"] if state["inventory_known"] else None,
                    waiting=state["waiting"] if state["waiting_known"] else None))
    if not loaders:
        loaders.update(plan["parent"].get("static_layout_order", []))
    submitted = {}
    for call in iter_json_array_gz(directory / "calls.json.gz"):
        if call.get("kind") == "transfer" and not call.get("retry"):
            submitted[call["request"]["request_id"]] = call
    transfers = {x["request_id"]: x for x in terminal["transfers"]}
    latency, depart, receive, residual, estimated = [], [], [], [], []
    for row in trajectory["rows"]:
        action = row["requested_action"]
        if action["kind"] != "transfer":
            continue
        estimated.append(action["static_travel_time"])
        request = row.get("actual_submission")
        if request:
            latency.append(request["issued_at"] - row["decision_time"])
        transfer = transfers.get(row.get("request_id"))
        if transfer and transfer.get("received_at", -1) >= 0:
            residual.append(transfer["received_at"] - action["static_arrival_estimate"])
    for identity, call in submitted.items():
        transfer = transfers.get(identity)
        if not transfer:
            continue
        if transfer.get("departed_at", -1) >= 0:
            depart.append(transfer["departed_at"] - call["at"])
        if transfer.get("received_at", -1) >= 0:
            receive.append(transfer["received_at"] - call["at"])
    statuses = Counter(x["status"] for x in terminal["transfers"])
    return dict(schema=SCHEMA, task_id=plan["task_id"], parent_seed=plan["parent"]["parent_seed"],
        method=plan["method"], physical_window=[trajectory["manifest"]["physical_start"], plan["horizon"]],
        bindings={name: binding(directory / name) for name in ("plan.json", "receipt.json", "trajectory.json.gz",
            "observations.json.gz", "decisions.json.gz", "terminal_evidence.json.gz", "calls.json.gz")},
        opportunities=opportunity_summary(iter_json_array_gz(directory / "decisions.json.gz")),
        terminal_directory=dict(static_loader_nodes=sorted(loaders),
            business_origin_nodes=sorted({j["origin"] for j in population["jobs"]}),
            current_legal_sources_are_catalog_dependent=True),
        timing_seconds=dict(selected_static_transport=distribution(estimated),
            decision_to_submission=distribution(latency), submission_to_departure=distribution(depart),
            submission_to_received=distribution(receive), selected_arrival_residual=distribution(residual)),
        transfer_denominators=dict(submitted_requests=len(submitted), native_status_counts=dict(statuses),
            received=len(receive), received_fraction=len(receive) / len(submitted) if submitted else None),
        station_observation_episodes={str(node): observation_episodes(values) for node, values in observed.items()},
        arrival_counts=arrival_count_distributions(population["jobs"], sorted(loaders),
            start=trajectory["manifest"]["physical_start"], end=plan["horizon"]),
        existing_policy_timing=receipt["worker"].get("policy_timing"),
        limitations=["post-priority observations are not a complete physical station time series",
            "shortage/depletion intervals use own-sensor samples and are interval-censored",
            "no persisted forecast-start/feature/allocator/submission wall-time decomposition exists in old runs",
            "decision_to_submission is not multi-tick planned-order queue time; old selector had no quantity plan",
            "arrival counts read future population only in this offline evaluator; never actor inputs",
            "repeated methods within one parent are not independent arrival-count observations",
            "native TRAIN gates stop at 18000 seconds; no full-window service benefit follows"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("transport_evidence:output_must_be_new")
    result = dict(schema=SCHEMA, evaluation_scope="existing_closed_train_only", native_starts=0,
        independent_real_airport_days=0, future_truth_used_only_offline=True,
        runs=[analyze_run(path) for path in args.runs])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output.resolve()), runs=len(result["runs"]), native_starts=0)))


if __name__ == "__main__":
    main()
