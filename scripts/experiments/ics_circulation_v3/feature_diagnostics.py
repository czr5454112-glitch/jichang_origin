"""Read-only feature/role diagnostics; no fitting, rollout or future oracle.

Empirical target differences for identical inputs can be Monte Carlo noise.
Nearest labelled rows at another state are references, never deployment labels.
"""
from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
from heapq import heappop, heappush
import json
import math

import numpy as np

from .model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from .runtime import ExecutionValidator


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def feature_vector(features, names):
    if set(features) != set(names):
        raise ValueError("Feature schema differs from the recorded old protocol")
    values = np.asarray([features[name] for name in names], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite feature")
    return values


def shortest_ticks(network, source, destination):
    distance, queue = {source: 0}, [(0, source)]
    while queue:
        tick, node = heappop(queue)
        if tick != distance[node]:
            continue
        if node == destination:
            return tick
        for edge in network.edges.values():
            if edge.source != node or edge.capacity <= 0:
                continue
            arrival = tick + edge.travel_time
            if arrival < distance.get(edge.target, math.inf):
                distance[edge.target] = arrival
                heappush(queue, (arrival, edge.target))
    return None


def decode_network(raw):
    return Network({key: Node(**value) for key, value in raw["nodes"].items()},
                   {key: Edge(**value) for key, value in raw["edges"].items()})


def infer_current_node(network, candidates, bag):
    sources = {network.edges[c["legs"][0]["edge_id"]].source for c in candidates if c["legs"]}
    if len(sources) > 1:
        raise ValueError("Candidates at one decision disagree on source node")
    # A validated zero-leg loaded route is possible only at its destination.
    return next(iter(sources)) if sources else bag["destination"]


def observable_context(network, bag, raw_candidate, *, now, current_node):
    """Use only the public graph, current task and validated candidate witness.

    The minimal Snapshot is used only by the owner's pure safe-prefix projector;
    it is not a reconstructed simulation or an authorization decision.
    """
    candidate = RouteCandidate(**{**raw_candidate, "legs": tuple(Leg(**leg) for leg in raw_candidate["legs"])})
    task = Bag(**bag)
    if task.bag_id != candidate.bag_id or task.arrival > now:
        raise ValueError("Task must be the candidate's already observed task")
    state = Snapshot(now, network, {candidate.tray_id: Tray(candidate.tray_id, current_node, "loaded", task.bag_id)},
                     {task.bag_id: task})
    prefix = ExecutionValidator._safe_prefix(state, candidate)
    end = network.edges[prefix.legs[-1].edge_id].target if prefix.legs else current_node
    current_distance = shortest_ticks(network, current_node, task.destination)
    end_distance = shortest_ticks(network, end, task.destination)
    role = ("at_destination" if current_node == task.destination else
            "at_origin" if current_node == task.origin else "in_transit_node")
    visits = [current_node, *(network.edges[leg.edge_id].target for leg in candidate.legs)]
    first_goal = visits.index(task.destination) if task.destination in visits else None
    return {"current_node": current_node, "origin": task.origin, "destination": task.destination,
        "task_od": task.origin + "->" + task.destination, "role": role,
        "at_destination": current_node == task.destination, "at_origin": current_node == task.origin,
        "prefix_end": end, "prefix_completes_delivery": not prefix.prefix_only and end == task.destination,
        "prefix_departure_delay": prefix.legs[0].depart - now if prefix.legs else 0,
        "prefix_travel_ticks": sum(leg.arrive - leg.depart for leg in prefix.legs),
        "current_shortest_ticks": current_distance, "prefix_end_shortest_ticks": end_distance,
        "prefix_shortest_progress": (current_distance - end_distance
                                      if current_distance is not None and end_distance is not None else None),
        "witness_repeated_node_count": len(visits) - len(set(visits)),
        "witness_visits_goal_before_terminal": first_goal is not None and first_goal < len(visits) - 1,
        "immediate_physical_prefix": {"legs": [asdict(leg) for leg in prefix.legs], "end": end,
            "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only}}


def collision_report(rows, names, *, paired=False):
    """Exact old feature tuples, not rounded near-collisions or causal claims."""
    baselines = {row["source_group"]: row for row in rows if row["is_baseline"]}
    groups = defaultdict(list)
    for row in rows:
        key = tuple(feature_vector(row["features"], names))
        if paired:
            key = (tuple(feature_vector(baselines[row["source_group"]]["features"], names)), key)
        groups[key].append(row)
    collisions = []
    for group in groups.values():
        if len(group) < 2:
            continue
        entries = []
        for row in group:
            deltas = np.asarray(row["paired_deltas"], dtype=float)
            if deltas.ndim != 1 or len(deltas) < 2 or not np.isfinite(deltas).all():
                raise ValueError("Need finite original paired deltas to describe Monte Carlo uncertainty")
            entries.append({"source_group": row["source_group"], "candidate_index": row["candidate_index"],
                "context": row["context"], "delta_mean": row["delta_mean"], "timed_delta": row["timed_delta"],
                "analytic_delta_error": row["delta_mean"] - row["timed_delta"],
                "paired_delta_mc_standard_error": float(deltas.std(ddof=1) / np.sqrt(len(deltas))),
                "mc_count": len(deltas)})
        comparisons = []
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                gap = a["delta_mean"] - b["delta_mean"]
                se = math.hypot(a["paired_delta_mc_standard_error"], b["paired_delta_mc_standard_error"])
                comparisons.append({"left": [a["source_group"], a["candidate_index"]],
                    "right": [b["source_group"], b["candidate_index"]], "mean_target_gap": gap,
                    "independent_mc_difference_se": se, "gap_over_mc_se": abs(gap) / se if se else None})
        collisions.append({"feature_sha256": digest(group[0]["features"]), "row_count": len(group),
            "distinct_nodes": sorted({row["context"]["current_node"] for row in group}),
            "distinct_roles": sorted({row["context"]["role"] for row in group}),
            "same_node": len({row["context"]["current_node"] for row in group}) == 1,
            "same_role": len({row["context"]["role"] for row in group}) == 1,
            "target_range": max(row["delta_mean"] for row in group) - min(row["delta_mean"] for row in group),
            "entries": entries, "comparisons": comparisons})
    return {"input_rows": len(rows), "unique_feature_keys": len(groups), "collision_groups": collisions,
        "paired_reference_and_candidate": paired,
        "interpretation": "Unequal finite-sample means are not proof of structural aliasing. MC SE describes only this declared synthetic law; no operational confidence claim."}


class FoldNeighbors:
    """Distance normalization comes only from the training streams of the fold."""
    def __init__(self, rows, held_out_stream, names):
        self.rows = [row for row in rows if row["stream"] != held_out_stream]
        if not self.rows or any(row["stream"] == held_out_stream for row in self.rows):
            raise ValueError("Empty or leaking training fold")
        self.names = tuple(names)
        values = np.stack([feature_vector(row["features"], names) for row in self.rows])
        self.center, self.scale = values.mean(axis=0), values.std(axis=0)
        self.scale[self.scale < 1e-9] = 1.
        self.normalized = (values - self.center) / self.scale

    def nearest(self, features, context, *, limit=3):
        query = (feature_vector(features, self.names) - self.center) / self.scale
        distances = np.sqrt(np.mean((self.normalized - query) ** 2, axis=1))
        order = sorted(range(len(self.rows)), key=lambda i: (distances[i], self.rows[i]["source_group"], self.rows[i]["candidate_index"]))
        def result(indices):
            return [{"source_group": self.rows[i]["source_group"], "candidate_index": self.rows[i]["candidate_index"],
                     "current_node": self.rows[i]["context"]["current_node"], "role": self.rows[i]["context"]["role"],
                     "task_od": self.rows[i]["context"]["task_od"], "normalized_rms_distance": float(distances[i]),
                     "label_delta_mean": self.rows[i]["delta_mean"], "analytic_delta_error":
                     self.rows[i]["delta_mean"] - self.rows[i]["timed_delta"]} for i in indices[:limit]]
        return {"nearest_training_rows": result(order),
                "nearest_same_node": result([i for i in order if self.rows[i]["context"]["current_node"] == context["current_node"]]),
                "nearest_same_role": result([i for i in order if self.rows[i]["context"]["role"] == context["role"]]),
                "nearest_same_task_od": result([i for i in order if self.rows[i]["context"]["task_od"] == context["task_od"]]),
                "deployment_label_inferred": False}
