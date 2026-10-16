"""LT2 original-map static candidate census and native R1 execution witness.

Static selection precedes every rollout. All eligible and excluded mother jobs
remain in the census. The local action domain is enumerated from a delivered
owner projection; native forks and final receipts are offline validation only.
This is an R1 interface/mechanism gate, not a policy benefit or joint solver.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import heapq
import json
import math
from pathlib import Path
import sys
import time
import traceback

from .native_host import audit_result, load_native
from .original_workload import (ProxyContract, build_input, digest, json_digest,
                                research_r1_authorized, write_json)
from .regional_control import RoutePacket, decode_route, encode_route


def positive_graph(data: dict) -> dict[int, list[tuple[int, float]]]:
    services = {n[0]: max(.001, n[2]) for n in data["node_records"]}
    closed = {(e["from"], e["to"]) for e in data["edge_contracts"] if e["capacity"] <= 0}
    closed.update((f["from"], f["to"]) for f in data.get("known_faults", []) if f["active"])
    graph = {n: [] for n in services}
    for u, v, length, speed in data["edge_records"]:
        if (u, v) not in closed:
            graph[u].append((v, services[u] + max(.001, length / speed)))
    return {n: sorted(edges) for n, edges in graph.items()}


def shortest_path(graph: dict, source: int, goal: int, forbidden=()) -> tuple[int, ...]:
    forbidden = set(forbidden)
    if source in forbidden or goal in forbidden:
        return ()
    pending = [(0., (source,))]
    best = {source: 0.}
    while pending:
        cost, path = heapq.heappop(pending)
        node = path[-1]
        if cost != best[node]:
            continue
        if node == goal:
            return path
        for nxt, weight in graph[node]:
            new = cost + weight
            if nxt not in forbidden and new < best.get(nxt, math.inf):
                best[nxt] = new
                heapq.heappush(pending, (new, path + (nxt,)))
    return ()


def suffix_choices(graph: dict, source: int, goal: int, prefix=()) -> list[tuple[int, ...]]:
    """One shortest simple continuation per legal next hop, without prefix loops."""
    if source == goal:
        return []
    excluded = set(prefix) | {source}
    result = []
    for nxt, _ in graph[source]:
        path = shortest_path(graph, nxt, goal, excluded)
        if path:
            result.append((source,) + path)
    return result


def stage_census(graph: dict, source: int, goal: int) -> dict:
    path = shortest_path(graph, source, goal)
    choices = []
    for index, node in enumerate(path[:-1]):
        routes = suffix_choices(graph, node, goal, path[:index])
        if len(routes) >= 2:
            choices.append({"node": node, "prefix": list(path[:index + 1]),
                            "suffixes": [list(r) for r in routes]})
    return {"source": source, "goal": goal, "canonical_path": list(path),
            "status": "unreachable" if not path else "choice" if choices else "no_route_choice",
            "choice_points": choices}


def candidate_census(data: dict) -> dict:
    graph = positive_graph(data)
    cache, rows = {}, []
    for job in sorted(data["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        storage = job["storage_node"]
        pairs = ([(job["origin"], storage), (storage, job["destination"])] if storage >= 0
                 else [(job["origin"], job["destination"])])
        stages = []
        for pair in pairs:
            if pair not in cache:
                cache[pair] = stage_census(graph, *pair)
            stages.append(cache[pair])
        statuses = {s["status"] for s in stages}
        status = ("unreachable_required_stage" if "unreachable" in statuses else
                  "eligible_static_alternative" if "choice" in statuses else "no_route_choice")
        rows.append({"business_bag_id": job["business_bag_id"], "arrival": job["arrival"],
                     "origin": job["origin"], "destination": job["destination"],
                     "storage_node": storage, "status": status,
                     "stage_keys": [f"{u}:{v}" for u, v in pairs]})
    return {"schema": "g31.lt2.r1_candidate_census.v1", "mother_offered": len(rows),
            "selection_rule": "chronological arrival then business ID; all required stages reachable; at least two simple positive-capacity suffixes at some canonical stage node",
            "selection_uses_outcomes": False, "counts": dict(Counter(r["status"] for r in rows)),
            "stages": {f"{u}:{v}": v0 for (u, v), v0 in sorted(cache.items())}, "rows": rows,
            "unknowns": ["native reachability under live arbitration", "normal-service protection", "R2 coupling"],
            "excluded_jobs_removed_from_formal_full_flow": False}


def find_context(session, owners: list[str], horizon: float, *, max_activations: int = 1000,
                 stage_filter: str = "any"):
    sequences = {o: 0 for o in owners}
    for _ in range(max_activations):
        reply = session.advance_until_owner_notification(owners, sequences, horizon, max_events=100000)
        if not reply.get("timestamp_complete"):
            return None, "unknown_native_budget"
        for owner, notice in sorted(reply.get("notifications", {}).items()):
            sequences[owner] = notice["sequence"]
            view = session.observe_protocol(owner)
            jobs = {j["business_bag_id"]: j for j in view["jobs"]}
            graph = positive_graph(view)
            for tray in view["trays"]:
                if tray["mode"] != "loaded" or tray["edge_to"] >= 0:
                    continue
                job = jobs[tray["business_bag_id"]]
                storage = job["storage_node"]
                before = storage >= 0 and job["storage_released_at"] < 0
                if before and stage_filter == "post_storage_or_direct":
                    continue
                goal = storage if before else job["destination"]
                paths = suffix_choices(graph, tray["node"], goal, tray["committed_prefix"])
                if len(paths) >= 2:
                    return {"view": view, "tray": tray, "goal": goal, "paths": paths,
                            "stage": "storage_in" if before else "storage_out_or_direct",
                            "notification": notice}, "context_found"
        if session.physical_time == horizon:
            return None, "no_runtime_choice_before_horizon"
    return None, "unknown_activation_budget"


def branch_request(context: dict, path: tuple, *, message_delay: float, expiry: float) -> tuple[dict, str]:
    view, tray = context["view"], context["tray"]
    packet = RoutePacket("g31.route_intent.v1", tray["business_bag_id"], tray["tray_id"], view["owner_id"],
                         tray["generation"], tray["traversal_id"], context["stage"], context["goal"],
                         tuple(tray["committed_prefix"]), tuple(path), view["now"])
    encoded = encode_route(packet)
    decoded = decode_route(encoded)
    return {"request_id": f"live:{len(view['owner_id'].encode('utf-8'))}:{view['owner_id']}:route:r1-{path[1]}",
            "owner_id": view["owner_id"], "kind": "route", "business_bag_id": decoded.business_bag_id,
            "tray_id": decoded.tray_id, "from": path[0], "next": path[1],
            "expected_generation": decoded.generation, "expected_traversal": decoded.traversal_id,
            "expiry": view["now"] + expiry, "message_delay": message_delay}, encoded


def run_witness(native, data: dict, *, message_delay: float = .01,
                stage_filter: str = "any") -> tuple[dict, dict]:
    horizon = data["options"]["max_simulation_time"]
    parent = native.NativeSession(data)
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    context, status = find_context(parent, owners, horizon, stage_filter=stage_filter)
    if context is None:
        return {"status": status, "r1_physical_witness": False}, {}
    frozen_identity = parent.offline_state_sha256()
    raw, rows = {}, {}
    for label, path in [("control", None)] + [(f"next_{p[1]}", p) for p in context["paths"]]:
        branch = parent.fork()
        assert branch.offline_state_sha256() == frozen_identity
        request = encoded = reply = ack = None
        started = time.perf_counter()
        if path is not None:
            request, encoded = branch_request(context, path, message_delay=message_delay, expiry=120.)
            reply = branch.submit_protocol_command(request)
        result = branch.result_at(horizon)
        horizon_complete = (result["advance"]["status"] == "reached" and
                            result["advance"]["horizon_complete"])
        if request:
            ack = branch.protocol_command(request["owner_id"], request["request_id"]).get("last_delivered_ack")
        audit = audit_result(data, result)
        edges = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER"
                 and r["business_bag_id"] == context["tray"]["business_bag_id"]]
        future = [r for r in edges if r["time"] >= context["view"]["now"]]
        pre = [r for r in edges if r["time"] < context["view"]["now"]]
        rows[label] = {"ack": ack, "first_downstream_edge": [future[0]["from"], future[0]["to"]] if future else None,
                       "executed_prefix": [[r["from"], r["to"]] for r in pre],
                       "executed_edges": [[r["from"], r["to"]] for r in edges],
                       "completed": sum(j["completed_at"] >= 0 for j in result["jobs"]),
                       "jobs": result["jobs"], "wall_seconds": time.perf_counter() - started,
                       "horizon_complete": horizon_complete,
                       "event_audit": audit, "requested_next": path[1] if path else None}
        raw[label] = {"request": request, "encoded_route": encoded, "submission_reply": reply, "result": result}
    control = rows["control"]
    for label, row in rows.items():
        row["prefix_preserved_vs_control"] = row["executed_prefix"] == control["executed_prefix"]
        row["traversal_changed_vs_control"] = row["first_downstream_edge"] != control["first_downstream_edge"]
        row["request_physically_followed"] = (row["requested_next"] is not None and
            row["first_downstream_edge"] == [context["tray"]["node"], row["requested_next"]])
    witness = any(row["ack"] and row["ack"]["status"] == "updated" and row["request_physically_followed"]
                  and row["traversal_changed_vs_control"] and row["prefix_preserved_vs_control"]
                  and row["completed"] == len(data["jobs"]) and row["horizon_complete"]
                  and control["horizon_complete"] and control["completed"] == len(data["jobs"])
                  for row in rows.values())
    return {"status": "executed", "r1_physical_witness": witness,
            "checkpoint_identity": frozen_identity, "context_at": context["view"]["now"],
            "owner_id": context["view"]["owner_id"], "choice_node": context["tray"]["node"],
            "stage": context["stage"], "stage_goal": context["goal"], "branches": rows,
            "same_permission_control": True, "R2_status": "not_exercised", "joint_status": "unknown",
            "complete_100ms_requirement_certified": False}, {"context": context, "branches": raw}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contexts", type=int, default=1)
    parser.add_argument("--message-delay", type=float, default=.01)
    parser.add_argument("--stage-filter", choices=("any", "post_storage_or_direct"), default="any")
    args = parser.parse_args()
    if args.contexts < 1 or not math.isfinite(args.message_delay) or args.message_delay < 0:
        parser.error("positive context budget and nonnegative finite message delay required")
    args.output.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), Path(__file__).with_name("original_workload.py"),
                    Path(__file__).with_name("regional_control.py"), Path(__file__).with_name("native_host.py")]
    receipt = {"schema": "g31.lt2.r1_receipt.v1", "status": "running", "command": sys.argv,
               "source_before": {str(p): digest(p) for p in source_paths}, "contexts": []}
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in source_paths:
        (archive / path.name).write_bytes(path.read_bytes())
    write_json(args.output / "receipt.json", receipt)
    try:
        actual = digest(args.binary)
        if actual != args.expected_binary_sha256:
            raise ValueError("research_r1:binary_identity_mismatch")
        receipt["binary_sha256"] = actual
        source, manifest, _ = build_input(scale=1,
            contract=ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2, 1., 1., 0.,
                                   "finite_berth_waiting_research_proxy"), horizon=86400., max_events=100000)
        census = candidate_census(source)
        with gzip.open(args.output / "candidate_census.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(census, stream, allow_nan=False)
        write_json(args.output / "mother_manifest.json", manifest)
        selected = [r["business_bag_id"] for r in census["rows"] if r["status"] == "eligible_static_alternative"
                    and (args.stage_filter == "any" or census["stages"][r["stage_keys"][-1]]["status"] == "choice")][:args.contexts]
        write_json(args.output / "preregistered_selection.json", {
            "selected_business_ids": selected, "census_counts": census["counts"],
            "mother_offered": census["mother_offered"], "selected_before_native_load": True,
            "stage_filter": args.stage_filter,
            "context_factor": "one original job and one existing tray at its origin per independent witness",
            "graph_capacity_fifo_business_fields_changed": False,
            "scope": "mechanism development subset; not full-flow or normal-service protection"})
        native = load_native(args.binary)
        jobs = {j["business_bag_id"]: j for j in source["jobs"]}
        for index, business_id in enumerate(selected):
            case = args.output / f"context_{index:03d}"
            case.mkdir()
            data = copy.deepcopy(source)
            data["jobs"] = [copy.deepcopy(jobs[business_id])]
            data["trays"] = [copy.deepcopy(next(t for t in source["trays"] if t["node"] == jobs[business_id]["origin"]))]
            data, contract = research_r1_authorized(data)
            data["owner_protocol"] = {"enabled": True, "timeout": 5., "ack_delay": .2}
            data["owner_notifications"] = {"enabled": True}
            write_json(case / "input.json", data)
            write_json(case / "contract.json", contract)
            summary, raw = run_witness(native, data, message_delay=args.message_delay, stage_filter=args.stage_filter)
            write_json(case / "summary.json", summary)
            with gzip.open(case / "native_witness.json.gz", "wt", encoding="utf-8") as stream:
                json.dump(raw, stream, allow_nan=False)
            receipt["contexts"].append({"business_bag_id": business_id, "input_sha256": json_digest(data),
                "status": summary["status"], "r1_physical_witness": summary["r1_physical_witness"], "path": str(case)})
            write_json(args.output / "receipt.json", receipt)
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_changed"] = [str(p) for p in source_paths if digest(p) != receipt["source_before"][str(p)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["complete_100ms_requirement_certified"] = False
    receipt["claim"] = "original-map R1 native integration witness; no method, R2, joint, full-flow or field certification"
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return int(receipt["status"] == "failed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
