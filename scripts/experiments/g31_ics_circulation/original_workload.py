"""Complete G31 Nanning source adapter and bounded, denominator-preserving runs.

This is input preparation, not a second physical simulator. The existing G31
flight projection/densification is reused verbatim; no job/edge is filtered.
The native host alone advances trays, Storage and transport. Unknown facility
contracts are explicitly finite research proxies, never field calibration.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict, dataclass
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback
from typing import Any

from czr005.io.legacy_tasks import parse_legacy_tasks
from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_g4irsf31_nanning_map as source_map
from scripts.eval import run_g4irsf31_nanning_workload as workload
from scripts.eval import run_g4irsf29_workload as densify
from .native_host import audit_result, load_native, prepare_input

ROOT = Path(__file__).absolute().parents[3]
DEFAULT_MAP = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_RAW = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ProxyContract:
    """Declared model, not inferred airport permission or equipment capacity.

    Extra load/unload is zero because source node service already handles it.
    A nonzero hold is a separate unavailable-empty interval after completion.
    """
    contract_id: str
    node_berths: int
    storage_berths: int
    trays_per_loader: int
    hold_seconds: float
    entry_headway_seconds: float
    deadline_lead_seconds: float
    waiting_contract: str

    def validate(self):
        if self.waiting_contract != "finite_berth_waiting_research_proxy":
            raise ValueError("unimplemented_waiting_contract; no-wait safety not certified")
        if not self.contract_id or any(type(x) is not int or x < 1 for x in
                (self.node_berths, self.storage_berths, self.trays_per_loader)):
            raise ValueError("explicit finite positive inventory and berth counts required")
        if self.trays_per_loader > self.node_berths:
            raise ValueError("initial tray inventory exceeds loader berths")
        for value in (self.hold_seconds, self.entry_headway_seconds,
                      self.deadline_lead_seconds):
            if not math.isfinite(value) or value < 0:
                raise ValueError("proxy times must be finite and nonnegative")


def verify_source_map(profile: dict, source_dir: Path) -> dict:
    """Read the untouched OOXML via the mature row-preserving parser."""
    files = [source_dir / name for _, name in source_map.WORKBOOK_NAMES]
    before = {str(p.absolute()): digest(p) for p in files}
    rebuilt = source_map.build_profile(source_dir)
    fields = ("nodes", "edges", "source_resolution", "business_roles")
    mismatch = [k for k in fields if rebuilt[k] != profile[k]]
    if mismatch:
        raise ValueError(f"source workbook/profile mismatch: {mismatch}")
    if any(digest(p) != before[str(p.absolute())] for p in files):
        raise ValueError("source workbook changed during read")
    return {"status": "exact_source_rows_match", "checked_fields": fields,
            "source_sha256": before, "node_count": len(profile["nodes"]),
            "edge_count": len(profile["edges"]), "source_files_edited": False}


def build_input(*, scale: int, contract: ProxyContract,
                raw_path: Path = DEFAULT_RAW, map_path: Path = DEFAULT_MAP,
                horizon: float = 86400., max_events: int = 100000,
                trace_limit: int = 0, scorer: str = "S4_queue_aware_rule_only"
                ) -> tuple[dict, dict, list[dict]]:
    contract.validate()
    if scale not in (1, 2):
        raise ValueError("only the existing frozen 1x/2x flight rule is supported")
    if not math.isfinite(horizon) or horizon <= 0 or max_events <= 0:
        raise ValueError("positive finite observation horizon/event budget required")
    if scorer not in ("S4_queue_aware_rule_only", "S3_shortest_potential_only"):
        raise ValueError("unsupported same-host scorer")
    source_hashes = {str(p.absolute()): digest(p) for p in (raw_path, map_path)}
    _, original = parse_legacy_tasks(raw_path)
    if len({t.task_id for t in original}) != len(original):
        raise ValueError("duplicate original business ID")
    profile = workload.load_map_profile(map_path)
    graph = map_adapter.load_map_profile(map_path)
    projection = workload.build_original_projection(original, profile)
    projected_original = workload._project_generated_tasks(
        original, original, projection, profile, inserted_id_offset=None)
    storage = workload.select_storage_pair(projected_original, profile)
    if scale == 2:
        generated, _, generation = densify.densify_flight_timetable(original)
        offset = int(generation["inserted_id_offset"])
        projected = workload._project_generated_tasks(
            original, generated, projection, profile, inserted_id_offset=offset)
    else:
        generated, projected, offset = original, projected_original, None
    if len(projected) != scale * len(original):
        raise ValueError("complete source denominator was not retained")
    source_by_id = {t.task_id: t for t in original}
    source_by_generated = dict(source_by_id)
    if offset is not None:
        source_by_generated.update({offset + rank: task for rank, task in enumerate(original)})
    jobs, crosswalk = [], []
    for row, generated_row in zip(projected, generated, strict=True):
        parent = source_by_generated[row.task_id]
        early = row.std - row.entry_time >= 4800.
        job = {"business_bag_id": f"projected:{scale}x:{row.task_id}",
               "origin": row.start, "destination": row.end,
               "arrival": row.entry_time, "deadline": row.std - contract.deadline_lead_seconds,
               "storage_node": storage["storage_in_goal"] if early else -1,
               "storage_release_at": row.std - 2700. if early else 0.,
               "storage_min_dwell": 0., "load_seconds": 0., "unload_seconds": 0.,
               "hold_seconds": contract.hold_seconds}
        jobs.append(job)
        crosswalk.append({"business_bag_id": job["business_bag_id"],
                          "original_task_id": parent.task_id,
                          "original_source_line": parent.source_line,
                          "original_od_namespace": "legacy_54_node_airport",
                          "original_start": parent.start, "original_goal": parent.end,
                          "raw_task_id": row.task_id, "projected_origin": row.start,
                          "projected_destination": row.end,
                          "synthetic_inserted": row.task_id != parent.task_id,
                          "time_shift_seconds": generated_row.entry_time-parent.entry_time,
                          "old_segment_ids": [f"{row.task_id}:{leg}" for leg in
                              (("storage_in", "storage_out") if early else ("direct",))]})
    loaders = sorted(set(j["origin"] for j in jobs))
    by_node = {n["location"]: n for n in profile["nodes"]}
    data = prepare_input({
        "schema": "g31.circulation.input.v1",
        "model_scope": "full Nanning graph; frozen G31 projected source; finite on-carrier research proxy",
        "model_contract": asdict(contract),
        "node_records": list(graph.node_records), "edge_records": list(graph.edge_records),
        "node_contracts": [{"node": n, "zone": row["system_key"],
                            "control_partition": f"partition:system_{row['system_key']}",
                            "resource_owner": f"owner:system_{row['system_key']}",
                            "capacity": contract.storage_berths if n == storage["storage_in_goal"] else contract.node_berths,
                            "export_min_stock": 0, "allow_export": True, "allow_receive": True}
                           for n, row in sorted(by_node.items())],
        "edge_contracts": [{"from": e["start"], "to": e["end"],
                            "capacity": e["pallet_capacity"],
                            "entry_headway": contract.entry_headway_seconds}
                           for e in profile["edges"]],
        "jobs": jobs,
        "trays": [{"tray_id": f"initial:{n}:{k}", "node": n}
                  for n in loaders for k in range(contract.trays_per_loader)],
        "transfers": [], "faults": [],
        "options": {"max_simulation_time": horizon, "max_events": max_events,
                    "trace_limit": trace_limit, "scorer_mode": scorer},
    })
    if any(digest(p) != source_hashes[str(p.absolute())] for p in (raw_path, map_path)):
        raise ValueError("source changed during adaptation")
    manifest = {"schema": "g31.circulation.original_workload.v1",
                "scale": scale, "input_sha256": json_digest(data),
                "source_sha256": source_hashes, "source_business_count": len(original),
                "offered_business_count": len(jobs), "source_group_count": 1,
                "independent_operating_days": "unknown; source is legacy simulated one-day stream",
                "early_storage_count": sum(j["storage_node"] >= 0 for j in jobs),
                "old_segment_count": sum(len(c["old_segment_ids"]) for c in crosswalk),
                "storage_pair": storage, "nodes": len(graph.node_records),
                "directed_edges": len(graph.edge_records),
                "closed_zero_capacity_edges": [[e["from"], e["to"]] for e in data["edge_contracts"] if e["capacity"] == 0],
                "inventory": len(data["trays"]), "proxy_contract": asdict(contract),
                "proxy_contract_sha256": json_digest(asdict(contract)),
                "owner_partition_contract": {"status": "derived_research_proxy",
                    "logistics_zone": "source workbook system_key",
                    "control_partition": "partition:system_<system_key>",
                    "resource_owner": "owner:system_<system_key>",
                    "shared_by_all_methods": True,
                    "field_owner_authority_confirmed": False},
                "original_source_and_projected_input_are_separate_factors": True,
                "crosswalk_sha256": json_digest(crosswalk),
                "deleted_business_jobs": 0, "created_graph_edges": 0,
                "changed_graph_directions": 0, "extra_load_unload_seconds": 0,
                "service_contract": "native source-table service retained; no duplicate extra load/unload; hold separate",
                "field_contract_unknowns": ["node berth capacity", "loaded/empty waiting permission",
                    "module port permissions and reserve stock", "actual EBS and off-carrier retrieval",
                    "deadline lead", "tray inventory", "entry headway", "hold duration"],
                "research_status": "input_engineering; no algorithmic innovation claim"}
    return data, manifest, crosswalk


def static_diagnostics(data: dict) -> dict:
    """Capacity-aware directed lower bounds; never filter infeasible demand."""
    n = len(data["node_records"])
    edges = {(e["from"], e["to"]): e for e in data["edge_contracts"]}
    services = {r[0]: max(.001, r[2]) for r in data["node_records"]}
    adj = [[] for _ in range(n)]
    for u, v, length, speed in data["edge_records"]:
        if edges[u, v]["capacity"] > 0:
            adj[u].append((v, max(.001, length/speed) + services[v]))
    costs = []
    for origin in range(n):
        dist = [math.inf] * n
        dist[origin] = services[origin]
        queue = [(dist[origin], origin)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != dist[node]:
                continue
            for target, weight in adj[node]:
                if cost+weight < dist[target]:
                    dist[target] = cost+weight
                    heapq.heappush(queue, (cost+weight, target))
        costs.append(dist)
    unreachable = deadline_impossible = 0
    unreachable_origins: Counter[int] = Counter()
    unreachable_destinations: Counter[int] = Counter()
    storage_min_work = 0.
    for j in data["jobs"]:
        arrival = j["arrival"]
        if j["storage_node"] < 0:
            earliest = arrival + costs[j["origin"]][j["destination"]]
        else:
            storage = j["storage_node"]
            enter = arrival + costs[j["origin"]][storage]
            earliest = max(enter, j["storage_release_at"]) + costs[storage][j["destination"]]
            # Only mandatory dwell, NOT arrival-to-release: late loading is possible.
            storage_min_work += j["storage_min_dwell"]
        if not math.isfinite(earliest):
            unreachable += 1
            unreachable_origins[j["origin"]] += 1
            unreachable_destinations[j["destination"]] += 1
        elif earliest > j["deadline"]:
            deadline_impossible += 1
    return {"offered": len(data["jobs"]), "capacity_positive_path_unreachable": unreachable,
            "topological_upper_bound_completed": len(data["jobs"])-unreachable,
            "unreachable_by_origin": dict(sorted(unreachable_origins.items())),
            "unreachable_by_destination": dict(sorted(unreachable_destinations.items())),
            "deadline_infeasible_even_without_queues": deadline_impossible,
            "mandatory_storage_dwell_work_seconds": storage_min_work,
            "arrival_to_release_is_not_a_valid_unconditional_occupancy_bound": True,
            "explanation": "directed source graph with zero capacity edges unavailable; native node service and declared release; finite tray/queue contention relaxed",
            "optimality": "unknown"}


def return_contract_diagnostics(data: dict) -> dict:
    """Directed return witnesses and fixed port scope; no inventory feasibility claim."""
    nodes = {n["node"]: n for n in data["node_contracts"]}
    adjacency = {n: [] for n in nodes}
    for e in data["edge_contracts"]:
        if e["capacity"] > 0:
            adjacency[e["from"]].append(e["to"])
    sources = sorted({j["origin"] for j in data["jobs"]})
    destinations = Counter(j["destination"] for j in data["jobs"])
    pairs, per_terminal = [], []
    for terminal, offered in sorted(destinations.items()):
        parents = {terminal: None}
        queue = deque([terminal])
        while queue:
            node = queue.popleft()
            for nxt in sorted(adjacency[node]):
                if nxt not in parents:
                    parents[nxt] = node
                    queue.append(nxt)
        counts = Counter()
        for source in sources:
            a, b = nodes[terminal], nodes[source]
            path = []
            if source in parents:
                cursor = source
                while cursor is not None:
                    path.append(cursor)
                    cursor = parents[cursor]
                path.reverse()
            if not path:
                status = "no_positive_capacity_directed_path"
            elif terminal == source:
                status = "local_reuse_at_same_node"
            elif a["zone"] == b["zone"]:
                status = "same_zone_requires_internal_module_not_central_transfer"
            elif not a.get("allow_export", True) or not b.get("allow_receive", True):
                status = "cross_zone_port_refused"
            else:
                status = "cross_zone_fixed_port_scope_candidate"
            counts[status] += 1
            pairs.append({"terminal": terminal, "loader": source,
                "terminal_zone": a["zone"], "loader_zone": b["zone"],
                "terminal_owner": a.get("resource_owner", a["zone"]),
                "loader_owner": b.get("resource_owner", b["zone"]),
                "status": status, "positive_capacity_path_witness": path})
        per_terminal.append({"terminal": terminal, "offered_ending_here": offered,
                             "return_pair_status_counts": dict(sorted(counts.items()))})
    unavailable = "no_positive_capacity_directed_path"
    cross = "cross_zone_fixed_port_scope_candidate"
    local = "local_reuse_at_same_node"
    internal = "same_zone_requires_internal_module_not_central_transfer"
    return {"offered": len(data["jobs"]), "source_loader_count": len(sources),
        "terminal_count": len(destinations), "pair_count": len(pairs),
        "pair_status_counts": dict(Counter(p["status"] for p in pairs)),
        "offered_with_no_directed_return_to_any_loader": sum(t["offered_ending_here"]
            for t in per_terminal if t["return_pair_status_counts"].get(unavailable, 0) == len(sources)),
        "offered_with_only_internal_module_return": sum(t["offered_ending_here"]
            for t in per_terminal if t["return_pair_status_counts"].get(internal, 0) and
            not t["return_pair_status_counts"].get(cross, 0) and not t["return_pair_status_counts"].get(local, 0)),
        "terminal_summary": per_terminal, "pairs": pairs,
        "same_zone_module_status": "not_implemented_in_current_circulation_port_contract",
        "authorization_boundary": "cross-zone endpoints only; crossing a zone along a same-zone return path does not authorize central export",
        "witness_boundary": "topology plus fixed port booleans only; live min stock, idle tray, acceptance berth, route resources and normal service still require native checks",
        "optimality": "unknown"}


def summarize_execution(data: dict, result: dict) -> dict:
    if len(result["jobs"]) != len(data["jobs"]):
        raise AssertionError("native output lost offered jobs")
    clock = result["physical_clock"]
    horizon = data["options"]["max_simulation_time"]
    # Event budgets may stop halfway through a timestamp; scheduled arrival
    # time <= clock alone is not proof that BAG_ARRIVAL has been executed.
    observed = sum(j["status"] != "unreleased" for j in result["jobs"])
    counts = Counter(j["status"] for j in result["jobs"])
    completed = [j for j in result["jobs"] if j["completed_at"] >= 0]
    # All jobs contribute until completion or the *same actual observed clock*.
    restricted_sojourn = sum(max(0., min(j["completed_at"] if j["completed_at"] >= 0 else clock, clock)
                                 - spec["arrival"])
                             for spec, j in zip(data["jobs"], result["jobs"], strict=True))
    loaded = sum(j["loaded_at"] >= 0 for j in result["jobs"])
    failed_reasons = Counter(r["reason"] for r in result.get("receipts", ())
                             if r["event"] == "LEG_FAILED")
    return {"offered": len(data["jobs"]), "observed": observed, "not_yet_observed": len(data["jobs"])-observed,
            "loaded": loaded, "completed": len(completed),
            "on_time": sum(j["deadline_met"] for j in completed),
            "uncompleted": len(data["jobs"])-len(completed), "job_status_counts": dict(counts),
            "unfinished_past_deadline": sum(j["completed_at"] < 0 and spec["deadline"] < clock
                for spec, j in zip(data["jobs"], result["jobs"], strict=True)),
            "tray_mode_counts": dict(Counter(t["mode"] for t in result["trays"])),
            "trays_with_receiving_lease": sum(t["reception_node"] >= 0 for t in result["trays"]),
            "physical_clock": clock, "declared_horizon": horizon,
            "horizon_reached": clock >= horizon,
            "event_budget_reached": result["native_summary"]["event_count"] >= data["options"]["max_events"],
            "leg_failure_reasons": dict(failed_reasons),
            "budget_finalization_censored_legs": failed_reasons["event_limit_reached"],
            "budget_failure_semantics": "event_limit_reached is computational censoring; native finalize quarantines active legs, not proof of physical impossibility",
            "restricted_sojourn_sum_seconds_at_actual_clock": restricted_sojourn,
            "warning": "different observed clocks are censored and must not be ranked by aggregate objective",
            "native_summary": result["native_summary"], "optimality": "unknown"}


def write_json(path: Path, value: Any):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--source-dir", type=Path, default=source_map.default_source_dir())
    parser.add_argument("--max-events", type=int, default=10000)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--node-berths", type=int, default=4)
    parser.add_argument("--storage-berths", type=int, default=64)
    parser.add_argument("--trays-per-loader", type=int, default=2)
    parser.add_argument("--trace-limit", type=int, default=0)
    parser.add_argument("--session", action="store_true", help="bounded live continuation without finalizing unfinished legs")
    parser.add_argument("--chunk-events", type=int, default=10000)
    parser.add_argument("--scorer", choices=("S4_queue_aware_rule_only", "S3_shortest_potential_only"), default="S4_queue_aware_rule_only")
    parser.add_argument("--retain-result", action="store_true", help="compressed full result; disabled by default to respect disk budget")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"command": sys.argv, "platform": platform.platform(), "status": "running",
               "adapter_sha256": digest(Path(__file__)), "protocol": "complete offered source, bounded execution, no-return reference"}
    write_json(args.output/"receipt.json", receipt)
    start = time.perf_counter()
    try:
        contract = ProxyContract(f"nanning-on-carrier-proxy-v1-n{args.node_berths}-s{args.storage_berths}-t{args.trays_per_loader}", args.node_berths,
            args.storage_berths, args.trays_per_loader, 1., 1., 0., "finite_berth_waiting_research_proxy")
        data, manifest, crosswalk = build_input(scale=args.scale, contract=contract,
            horizon=args.horizon, max_events=args.max_events, scorer=args.scorer,
            trace_limit=args.trace_limit)
        profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
        write_json(args.output/"source_workbooks.json", verify_source_map(profile, args.source_dir))
        write_json(args.output/"input_manifest.json", manifest)
        write_json(args.output/"static_diagnostics.json", static_diagnostics(data))
        write_json(args.output/"return_contract_diagnostics.json", return_contract_diagnostics(data))
        # Small gzip lineage retains every job without multi-MB duplicated JSON.
        with gzip.open(args.output/"business_crosswalk.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in crosswalk:
                stream.write(json.dumps(row, sort_keys=True)+"\n")
        if args.binary:
            receipt["binary_sha256"] = digest(args.binary)
            native = load_native(args.binary)
            compute = time.perf_counter()
            if args.session:
                if args.chunk_events <= 0:
                    raise ValueError("positive chunk budget required")
                session = native.NativeSession(data)
                consumed = 0
                with (args.output/"continuation_chunks.jsonl").open("w", encoding="utf-8") as stream:
                    while session.physical_time < args.horizon and consumed < args.max_events:
                        progress = session.advance_to(args.horizon,
                            max_events=min(args.chunk_events, args.max_events-consumed))
                        consumed += progress["processed_events"]
                        stream.write(json.dumps({"cumulative_events": consumed, **progress})+"\n")
                        stream.flush()
                        if progress["processed_events"] == 0:
                            break
                result = session.result_at(session.physical_time)
                receipt["continuation"] = "live session; no finalize or artificial quarantine at budget"
                receipt["requested_common_horizon"] = args.horizon
                receipt["offline_final_state_sha256"] = session.offline_state_sha256()
            else:
                result = native.run(data)
            receipt["native_wall_seconds"] = time.perf_counter()-compute
            write_json(args.output/"summary.json", summarize_execution(data, result))
            write_json(args.output/"event_audit.json", audit_result(data, result))
            with gzip.open(args.output/"business_results.jsonl.gz", "wt", encoding="utf-8") as stream:
                for spec, job in zip(data["jobs"], result["jobs"], strict=True):
                    stream.write(json.dumps({"business_bag_id": spec["business_bag_id"], **job})+"\n")
            with gzip.open(args.output/"physical_events.jsonl.gz", "wt", encoding="utf-8") as stream:
                for event in result["receipts"]:
                    stream.write(json.dumps(event)+"\n")
            if args.retain_result:
                with gzip.open(args.output/"result.json.gz", "wt", encoding="utf-8") as stream:
                    json.dump(result, stream)
            receipt["status"] = "executed_with_complete_offered_denominator"
        else:
            receipt["status"] = "prepared_not_executed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter()-start
    receipt["adapter_changed"] = digest(Path(__file__)) != receipt["adapter_sha256"]
    write_json(args.output/"receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return int(receipt["status"] == "failed" or receipt["adapter_changed"])


if __name__ == "__main__":
    raise SystemExit(main())
