"""Minimal two-variable resource-aware repair on the existing public model.

This is a small LNS-style adaptation, not a replication of TAPF-PC/SIPPS or a
novel algorithm. All four obligations stay in the predictor/protection test.
"""
from __future__ import annotations
import copy
import heapq
import math
from . import public_reuse_model as model

VERSION = "public-two-variable-repair-v1"
METHODS = ("coordinate_strict", "coordinate_plateau", "resource_pair_repair")


def key(action):
    return action["initial_next"], action["departure"], action["later_mode"]


def shortest_nodes(contract, source, target):
    service = {n[0]: max(.001, n[2]) for n in contract["node_records"]}
    graph = {n: [] for n in service}
    capacities = {(e["from"], e["to"]): e["capacity"] for e in contract["edge_contracts"]}
    for u, v, length, speed in contract["edge_records"]:
        if capacities[u, v] > 0: graph[u].append((v, service[u] + max(.001, length / speed)))
    todo, seen = [(0., (source,))], set()
    while todo:
        cost, path = heapq.heappop(todo)
        if path[-1] in seen: continue
        seen.add(path[-1])
        if path[-1] == target: return path
        for v, w in graph[path[-1]]:
            if v not in seen: heapq.heappush(todo, (cost + w, path + (v,)))
    return ()


def resource_neighborhood(bundle, actions):
    """Public operation-support overlap; no future/native occupancy queried."""
    c, jobs, trays = bundle["contract"], bundle["jobs"], bundle["trays"]
    loaded = jobs[trays["L"]["business_bag_id"]]
    stage = loaded["storage_node"] if loaded["storage_node"] >= 0 else loaded["destination"]
    route_support = set()
    for nxt in {a["initial_next"] for a in actions}:
        route_support.update(shortest_nodes(c, nxt, stage))
    receiver = jobs["receiver"]
    timing_support = set(shortest_nodes(c, trays["E"]["node"], receiver["origin"]))
    timing_support.update(shortest_nodes(c, receiver["origin"], receiver["destination"]))
    shared = sorted(route_support & timing_support)
    return {"status": "resource_linked" if shared else "no_public_resource_link",
        "route_variable_resource_support": sorted(route_support), "window_variable_resource_support": sorted(timing_support),
        "shared_nodes": shared, "destroy_variables": ["initial_next", "departure"] if shared else [],
        "obligation_closure": sorted(jobs), "exterior_frozen": [],
        "scope": "complete four-obligation closure; no assignment, exterior repair, or later-control optimization"}


def protected(prediction, baseline, expected):
    for p in (prediction, baseline):
        if p.get("status") != "conditional_prediction" or set(p.get("completion", {})) != expected:
            return None
        if any(not math.isfinite(t) or t < 0 for t in p["completion"].values()): return None
    return all(prediction["completion"][j] <= baseline["completion"][j] for j in expected)


def repair(bundle, actions, incumbent, *, method, evaluation_budget=35):
    if method not in METHODS: raise ValueError("repair:undeclared_method")
    if not isinstance(evaluation_budget, int) or evaluation_budget < 1: raise ValueError("repair:positive_evaluation_budget")
    if bundle["status"] != "conditional_model_input":
        return {"status": "unknown_input", "selected_action": None, "evaluations": 0, "native_protection_certified": False}
    domain = {key(a): copy.deepcopy(a) for a in actions}
    if len(domain) != len(actions) or key(incumbent) not in domain:
        raise ValueError("repair:duplicate_domain_or_missing_incumbent")
    if any(a["later_mode"] != incumbent["later_mode"] for a in actions):
        raise ValueError("repair:later_continuation_must_be_fixed")
    expected = set(bundle["jobs"])
    neighborhood = resource_neighborhood(bundle, actions)
    cache, steps = {}, []
    base_key = key(incumbent)
    def evaluate(action_key):
        if action_key in cache: return cache[action_key]
        if len(cache) >= evaluation_budget: return None
        prediction = model.predict(bundle, domain[action_key])
        cache[action_key] = {"action": copy.deepcopy(domain[action_key]), "prediction": prediction,
            "model_protected": protected(prediction, cache[base_key]["prediction"] if base_key in cache else prediction, expected)}
        return cache[action_key]
    baseline = evaluate(base_key)
    if baseline["model_protected"] is not True:
        return {"status": "unknown_incumbent_projection", "selected_action": None, "evaluations": 1,
                "native_protection_certified": False, "rows": [baseline]}
    score = lambda k: (cache[k]["prediction"]["completion_sum"], k)
    neighbors = lambda k: [x for x in sorted(domain) if sum(a != b for a, b in zip(x[:2], k[:2])) == 1]
    stop = "local_fixed_point"
    if method == "resource_pair_repair":
        if neighborhood["status"] != "resource_linked":
            stop = "unknown_no_resource_link"
        else:
            for candidate in sorted(domain):
                if evaluate(candidate) is None: stop = "evaluation_budget_exhausted"; break
            else: stop = "finite_resource_neighborhood_exhausted"
    elif method == "coordinate_strict":
        current = base_key
        while True:
            eligible = []
            for candidate in neighbors(current):
                row = evaluate(candidate)
                if row is None: stop = "evaluation_budget_exhausted"; break
                if row["model_protected"] is True and score(candidate)[0] < score(current)[0]: eligible.append(candidate)
            if not eligible: break
            chosen = min(eligible, key=score)
            steps.append({"from": domain[current], "to": domain[chosen], "kind": "strict_coordinate_improvement"})
            current = chosen
            if stop == "evaluation_budget_exhausted": break
    else:
        # Stronger coordinate diagnostic retains neutral plateaus; no lucky
        # variable-order move is required. Search paths never worsen their own
        # parent cost; the best protected incumbent is retained separately.
        pending, expanded, queued = [(score(base_key), base_key)], set(), {base_key}
        while pending:
            _, current = heapq.heappop(pending)
            if current in expanded: continue
            expanded.add(current)
            for candidate in neighbors(current):
                row = evaluate(candidate)
                if row is None: stop = "evaluation_budget_exhausted"; break
                if row["model_protected"] is True and score(candidate)[0] <= score(current)[0] and candidate not in queued:
                    queued.add(candidate); heapq.heappush(pending, (score(candidate), candidate))
                    steps.append({"from": domain[current], "to": domain[candidate], "kind": "nonworsening_coordinate_frontier"})
            if stop == "evaluation_budget_exhausted": break
        else: stop = "nonworsening_coordinate_component_exhausted"
    eligible = [k for k, row in cache.items() if row["model_protected"] is True]
    best = min(eligible, key=score)
    rows = [{**cache[k], "evaluation_status": "evaluated"} if k in cache else
            {"action": copy.deepcopy(domain[k]), "evaluation_status": "unknown_unexecuted", "model_protected": None}
            for k in sorted(domain)]
    return {"schema": "g31.lt2.resource_repair_proposal.v1", "version": VERSION,
        "status": "conditional_model_proposal", "method": method, "evaluation_budget": evaluation_budget,
        "evaluations": len(cache), "candidate_denominator": len(domain), "stop_reason": stop,
        "selected_action": copy.deepcopy(domain[best]), "selected_prediction": cache[best]["prediction"],
        "incumbent_prediction": baseline["prediction"], "model_gain": score(base_key)[0] - score(best)[0],
        "neighborhood": neighborhood, "search_steps": steps, "rows": rows,
        "capture_pair_sha256": bundle["capture_pair_sha256"], "native_protection_certified": False,
        "model_error_bound_certified": False, "rolling_solver_implemented": False, "online_executable": False}
