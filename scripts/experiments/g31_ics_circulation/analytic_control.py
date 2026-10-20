"""Same-information deterministic release prediction and tray matching.

This is a deliberately strong *baseline*, not a novelty claim and not a BPD/CWPD
replication. It never advances physics or owns inventory. Its only mutable data
are controller request identities; all supply is reconstructed from public,
already-delivered owner observations. Predictions are never export permissions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
from dataclasses import asdict, dataclass
import hashlib
import heapq
import math
import struct
import time
from typing import Any


@dataclass(frozen=True)
class ReleaseForecast:
    tray_id: str
    node: int
    earliest: float
    estimate: float
    ledger: str
    owner_id: str
    version: int
    dependency: str
    # No finite upper bound is certified under future congestion/faults.
    latest: float | None = None


_FORECAST_FIELDS = tuple(ReleaseForecast.__dataclass_fields__)
_SCALAR_TYPES = {str, int, float, bool, type(None)}


def _scalar_forecast_dict(forecast: ReleaseForecast) -> dict[str, Any]:
    # Native forecasts contain only immutable scalar fields. Each caller still
    # receives its own dictionary; unusual/subclass values retain asdict's
    # original recursive-copy behavior rather than acquiring shallow aliases.
    values = vars(forecast)
    if (type(forecast) is ReleaseForecast and tuple(values) == _FORECAST_FIELDS
            and all(type(value) in _SCALAR_TYPES for value in values.values())):
        return values.copy()
    return asdict(forecast)


class PublicTravel:
    """Static service-aware paths, with only notified closures removed."""

    def __init__(self, observation: dict[str, Any], *, _reuse_source_searches: bool = True):
        self.service = {int(r[0]): max(float(r[2]), .001)
                        for r in observation["node_records"]}
        self.adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
        self.edge_time = {(int(u), int(v)): max(float(length) / float(speed), .001)
                          for u, v, length, speed in observation["edge_records"]}
        now = observation["now"]
        closed = {(int(f["from"]), int(f["to"]))
                  for f in observation.get("known_faults", [])
                  if f.get("active", f.get("start", now) <= now < f.get("end", math.inf))}
        closed.update((int(e["from"]), int(e["to"]))
                      for e in observation.get("edge_contracts", []) if int(e["capacity"]) <= 0)
        for u, v, length, speed in observation["edge_records"]:
            if (int(u), int(v)) not in closed:
                self.adj[int(u)].append((int(v), max(float(length) / float(speed), .001)))
        self.cache: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}
        self._reuse_source_searches = _reuse_source_searches
        self._source_searches: dict[int, list] = {}

    def path(self, source: int, target: int) -> tuple[float, tuple[int, ...]]:
        key = source, target
        if key in self.cache:
            return self.cache[key]
        if self._reuse_source_searches:
            return self._continued_path(source, target)
        queue = [(0.0, (source,), source)]
        best = {source: 0.0}
        while queue:
            cost, path, node = heapq.heappop(queue)
            if cost > best[node]:
                continue
            if node == target:
                self.cache[key] = cost, path
                return cost, path
            for dest, travel in self.adj[node]:
                proposed = cost + self.service[node] + travel
                if proposed < best.get(dest, math.inf):
                    best[dest] = proposed
                    heapq.heappush(queue, (proposed, path + (dest,), dest))
        self.cache[key] = math.inf, ()
        return self.cache[key]

    def _continued_path(self, source: int, target: int) -> tuple[float, tuple[int, ...]]:
        # A positive-weight Dijkstra run has the same settled prefix for every
        # target. Resume its exact heap/strict-improvement arithmetic, including
        # the unexpanded previous target, instead of restarting for each pair.
        # This object belongs to one observation/candidate call only. Keep the
        # public pair cache limited to explicitly queried pairs as before.
        state = self._source_searches.get(source)
        if state is None:
            state = [[(0.0, (source,), source)], {source: 0.0}, {}, None]
            self._source_searches[source] = state
        queue, best, settled, pending = state
        if target not in settled:
            if pending is not None:
                cost, path, node = pending
                for dest, travel in self.adj[node]:
                    proposed = cost + self.service[node] + travel
                    if proposed < best.get(dest, math.inf):
                        best[dest] = proposed
                        heapq.heappush(queue, (proposed, path + (dest,), dest))
                state[3] = None
            while queue:
                cost, path, node = heapq.heappop(queue)
                if cost > best[node]:
                    continue
                settled[node] = cost, path
                if node == target:
                    state[3] = cost, path, node
                    break
                for dest, travel in self.adj[node]:
                    proposed = cost + self.service[node] + travel
                    if proposed < best.get(dest, math.inf):
                        best[dest] = proposed
                        heapq.heappush(queue, (proposed, path + (dest,), dest))
        self.cache[source, target] = settled.get(target, (math.inf, ()))
        return self.cache[source, target]

    def complete(self, source: int, target: int) -> float:
        return self.path(source, target)[0] + self.service[target]


def _jobs_by_id(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # The native projection, not this function, is the authorization boundary.
    jobs = {j["business_bag_id"]: j for j in observation.get("jobs", [])}
    if any(j["arrival"] > observation["now"] + 1e-9 for j in jobs.values()):
        raise ValueError("analytic_control:unpublished_future_job")
    return jobs


def _visible_demand(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    jobs = {key: dict(value, demand_observed_at=observation["now"])
            for key, value in _jobs_by_id(observation).items()}
    latest: dict[str, dict[str, Any]] = {}
    for message in observation.get("delivered_messages", []):
        if message.get("kind") != "demand":
            continue
        if message["delivered_at"] > observation["now"] + 1e-9:
            raise ValueError("analytic_control:undelivered_message")
        source = str(message["source_owner"])
        if source not in latest or message["observed_at"] > latest[source]["observed_at"]:
            latest[source] = message
    for message in latest.values():
        for job in message["jobs"]:
            if job["arrival"] > message["observed_at"] + 1e-9:
                raise ValueError("analytic_control:unpublished_future_demand")
            jobs.setdefault(job["business_bag_id"], dict(job, demand_observed_at=message["observed_at"]))
    return jobs


def demand_signature(rows: list[list[Any]]) -> dict[str, Any]:
    """Canonical local waiting identity digest, also used by the native port.

    This excludes owner versions, forecasts and remote messages, which must
    not trigger new demand publications. Legacy JSON controller states contain
    the full sorted rows and can be migrated without observing physical state.
    """
    payload = bytearray(b"g31.demand_signature.v1\n")
    payload.extend(struct.pack(">Q", len(rows)))
    for bag, origin, arrival, deadline in sorted(rows):
        encoded = bag.encode("utf-8")
        payload.extend(struct.pack(">Q", len(encoded)))
        payload.extend(encoded)
        payload.extend(struct.pack(">qdd", int(origin), 0. if arrival == 0 else arrival,
                                   0. if deadline == 0 else deadline))
    return {"schema": "g31.demand_signature.v1", "sha256": hashlib.sha256(payload).hexdigest(),
            "waiting_count": len(rows)}


def _compact_demand(observation: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter, dict[int, float], set[int]]:
    """Read exact queue counts with bounded FIFO identities, never expand them.

    The native port has already applied local-over-remote identity precedence
    and delivered-snapshot selection. Counts protect local work; identities
    only represent the equivalent assignment columns after incoming coverage.
    """
    projection = observation["control_projection"]
    if projection.get("schema") != "g31.analytic_control_projection.v1":
        raise ValueError("analytic_control:unsupported_control_projection")
    waiting, counts, observed = [], Counter(), {}
    for group in projection["waiting_groups"]:
        origin, count = int(group["origin"]), int(group["count"])
        if origin in counts or count < 0:
            raise ValueError("analytic_control:invalid_compact_queue")
        counts[origin] = count
        observed[origin] = float(group["demand_observed_at"])
        rows = group["jobs"]
        if len(rows) > count or [int(j["fifo_index"]) for j in rows] != list(range(len(rows))):
            raise ValueError("analytic_control:invalid_compact_fifo_prefix")
        for job in rows:
            if (int(job["origin"]) != origin or job["status"] not in ("waiting", "waiting_for_tray")
                    or job["arrival"] > job["demand_observed_at"] + 1e-9
                    or job["demand_observed_at"] > observation["now"] + 1e-9):
                raise ValueError("analytic_control:invalid_compact_demand")
        waiting.extend(rows)
    if sum(counts.values()) != int(projection["exact_waiting_count"]):
        raise ValueError("analytic_control:inconsistent_compact_waiting_count")
    waiting.sort(key=lambda j: (j["arrival"], j["business_bag_id"]))
    return waiting, counts, observed, {int(n) for n in projection["known_origin_nodes"]}


def _inflight_arrival(tray: dict[str, Any], now: float, travel: PublicTravel) -> float:
    if "edge_exit_at" in tray:
        return max(now, float(tray["edge_exit_at"]))
    return now + travel.edge_time[int(tray["edge_from"]), int(tray["edge_to"])]


def conditional_service_windows(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve exact delivered tombstones before evaluating forecast revisions.

    Delivery order is not a revision order. A withdrawal can reach the receiver
    before its original forecast, and withdrawing an old revision must not
    erase a newer revision. Withdrawing the latest revision must not resurrect
    a superseded older one. No inventory or physical transfer is changed here.
    """
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    withdrawn: set[tuple[str, str]] = set()
    ambiguous: set[tuple[str, str]] = set()
    for message in observation.get("delivered_messages", []):
        if message.get("kind") != "service_forecast":
            continue
        if message["delivered_at"] > observation["now"] + 1e-9:
            raise ValueError("analytic_control:undelivered_service_forecast")
        if message.get("status") == "withdrawn":
            if not message.get("supersedes"):
                raise ValueError("analytic_control:withdrawal_missing_exact_identity")
            withdrawn.add((message["source_owner"], message["supersedes"]))
            continue
        key = message["source_owner"], message["tray_id"]
        revision = lambda m: (m["observed_at"], m.get("generation", 0), m.get("publication_sequence", 0))
        if key not in latest or revision(message) > revision(latest[key]):
            latest[key] = message
            ambiguous.discard(key)
        elif revision(message) == revision(latest[key]) and message.get("message_id") != latest[key].get("message_id"):
            # Older schema without an ordered publication sequence cannot
            # resolve two same-epoch announcements by opaque ID or delivery.
            ambiguous.add(key)
    return [m for key, m in latest.items() if key not in ambiguous
            and m.get("status", "conditional") == "conditional"
            and (m["source_owner"], m["message_id"]) not in withdrawn
            and m["release_estimate"] > observation["now"]]


def departure_avoiding_published_windows(observation: dict[str, Any], supply: ReleaseForecast,
                                        destination: int, travel: PublicTravel, message_delay: float,
                                        *, _windows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Ordinary point-estimate time-window baseline; never a hard certificate.

    Only transit-node occupancy windows are shifted. Terminal/remote receiving
    leases still rely on the native port; this does not introduce free leases.
    A later route change or forecast error can invalidate the point estimate.
    """
    path = travel.path(supply.node, destination)[1]
    offsets = []
    elapsed = 0.0
    for u, v in zip(path, path[1:]):
        entered = elapsed + travel.service[u]
        arrived = entered + travel.edge_time[u, v]
        if v != destination:
            offsets.append((v, entered, arrived + travel.service[v]))
        elapsed = arrived
    windows = conditional_service_windows(observation) if _windows is None else _windows
    relevant = [(window, start, end) for node, start, end in offsets for window in windows
                if window["next"] == node and window["tray_id"] != supply.tray_id]
    if not relevant:
        return {"earliest_departure": observation["now"], "conditional_dependencies": [], "hard_guarantee": False}
    departure = max(observation["now"] + message_delay, supply.estimate)
    dependencies = set()
    # Every strict increase passes at least one fixed interval end. No physical
    # state is advanced or reserved by this arithmetic.
    for _ in range(len(relevant) + 1):
        updated = departure
        for message, start, end in relevant:
            if departure + start < message["release_estimate"] - 1e-9 and departure + end > message["entry_estimate"] + 1e-9:
                updated = max(updated, message["release_estimate"] - start)
                dependencies.add(message.get("message_id", f"{message['source_owner']}:{message['tray_id']}:{message['generation']}"))
        if updated <= departure + 1e-9:
            break
        departure = updated
    return {"earliest_departure": departure, "conditional_dependencies": sorted(dependencies), "hard_guarantee": False}


def release_forecasts(observation: dict[str, Any], *, include_future: bool = True,
                      travel: PublicTravel | None = None) -> list[ReleaseForecast]:
    """One next availability per physical tray; no multi-cycle double pledge.

    Travel times are a capacity-relaxed point estimate, not a feasible rollout.
    In-flight residuals use a public entry receipt when available; otherwise a
    full edge time is a conservative estimate but not a certified upper bound.
    """
    now = float(observation["now"])
    jobs = _jobs_by_id(observation)
    result: list[ReleaseForecast] = []
    seen: set[str] = set()
    owner = str(observation.get("owner_id", ""))
    version = int(observation.get("version", 0))
    for tray in observation.get("trays", []):
        tid = tray["tray_id"]
        if tid in seen:
            raise ValueError("analytic_control:duplicate_tray_projection")
        seen.add(tid)
        mode = tray["mode"]
        node = int(tray["node"])
        if not include_future and mode != "empty":
            continue
        if mode == "quarantined":
            continue
        if mode == "empty" and tray.get("edge_to", -1) < 0:
            result.append(ReleaseForecast(tid, node, now, now, "actual_available",
                                          owner, version, f"{tid}:empty"))
            continue
        job_id = tray.get("business_bag_id", "")
        job = jobs.get(job_id) or tray.get("job_contract")
        if mode == "hold":
            available = max(now, float(tray["available_at"]))
            result.append(ReleaseForecast(tid, node, available, available, "firm_release",
                                          owner, version, f"{tid}:{job_id}:hold"))
            continue
        if mode == "empty_transit":
            # A hard receiving obligation still is not a present empty tray.
            target = int(tray["reception_node"])
            if target < 0:
                continue
            if travel is None:
                travel = PublicTravel(observation)
            location = int(tray.get("edge_to", -1))
            eta = now
            if location >= 0:
                eta = _inflight_arrival(tray, now, travel)
            else:
                location = node
            eta += travel.complete(location, target)
            if math.isfinite(eta):
                result.append(ReleaseForecast(tid, target, now, eta, "obligated_arrival",
                                              owner, version, f"{tid}:receiving:{target}"))
            continue
        if not job:
            # Missing lawful job information is unknown, not a fabricated ETA.
            continue
        destination = int(job["destination"])
        unload = float(job.get("unload_seconds", 0))
        hold = float(job.get("hold_seconds", 0))
        if mode == "unloading":
            estimate = max(now, float(tray.get("available_at", now + unload))) + hold
        else:
            if travel is None:
                travel = PublicTravel(observation)
            estimate = now
            if mode == "loading":
                estimate = max(now, float(tray.get("available_at", now + job.get("load_seconds", 0))))
            location = int(tray.get("edge_to", -1))
            if location >= 0:
                estimate = max(estimate, _inflight_arrival(tray, now, travel))
            else:
                location = node
            storage = int(job.get("storage_node", -1))
            if storage >= 0 and float(job.get("storage_released_at", -1)) < 0:
                entered = float(job.get("storage_entered_at", -1))
                if entered < 0:
                    entered = estimate + travel.complete(location, storage)
                estimate = max(estimate, float(job.get("storage_release_at", 0)),
                               entered + float(job.get("storage_min_dwell", 0)))
                location = storage
            estimate += travel.complete(location, destination) + unload + hold
        if math.isfinite(estimate):
            result.append(ReleaseForecast(tid, destination, now, estimate, "conditional_release",
                                          owner, version, f"{tid}:{job_id}:{mode}"))
    return result


def _min_cost_matching(costs: list[list[float]]) -> list[tuple[int, int]]:
    """Maximum-cardinality, minimum-cost bipartite matching; no greedy shortcut.

    Successive shortest augmenting paths in a residual network. Bellman-Ford
    handles reverse negative costs. This solves the declared assignment only,
    not coupled physical routing/receiving feasibility.
    """
    n, m = len(costs), len(costs[0]) if costs else 0
    source, sink = n + m, n + m + 1
    graph: list[list[list[Any]]] = [[] for _ in range(sink + 1)]

    def add(u: int, v: int, cost: float):
        graph[u].append([v, len(graph[v]), 1, cost])
        graph[v].append([u, len(graph[u]) - 1, 0, -cost])

    for i in range(n):
        add(source, i, 0)
        for j, cost in enumerate(costs[i]):
            if math.isfinite(cost):
                add(i, n + j, cost)
    for j in range(m):
        add(n + j, sink, 0)
    while True:
        distance = [math.inf] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distance[source] = 0
        for _ in range(len(graph) - 1):
            changed = False
            for u, edges in enumerate(graph):
                for index, (v, _, capacity, cost) in enumerate(edges):
                    if capacity and distance[u] + cost < distance[v] - 1e-12:
                        distance[v] = distance[u] + cost
                        previous[v] = u, index
                        changed = True
            if not changed:
                break
        if previous[sink] is None:
            break
        v = sink
        while v != source:
            u, index = previous[v]  # type: ignore[misc]
            edge = graph[u][index]
            edge[2] -= 1
            graph[v][edge[1]][2] += 1
            v = u
    return [(i, edge[0] - n) for i in range(n) for edge in graph[i]
            if n <= edge[0] < n + m and edge[2] == 0]


def _assignment_representatives(demand: list[dict[str, Any]], supply_count: int) -> list[tuple[int, dict[str, Any]]]:
    """Exact equivalent-column compression for this declared ETA objective.

    At most K supplies can serve K demands. For equal (origin, clearing_source,
    demand_kind), all supplies have identical feasibility and assignment costs
    across those columns. Retaining the first K FIFO columns preserves maximum
    cardinality and minimum cost; every assignment to a later column can be
    injectively exchanged with an unused retained column in its group.
    Deadlines/arrival weighting are NOT in this assignment objective. Adding
    either later requires expanding the equivalence key or disabling this.
    Full demand identities remain in the returned decision and offered cohort.
    """
    counts: Counter = Counter()
    retained = []
    for index, job in enumerate(demand):
        key = (int(job["origin"]), job.get("clearing_source"), job["demand_kind"])
        if counts[key] < supply_count:
            retained.append((index, job))
            counts[key] += 1
    return retained


def public_transfer_scope(observation: dict[str, Any], source: int, destination: int,
                          *, actual_available: bool, contracts=None):
    """Static scope eligibility only; native still owns current admission.

    Missing role contract retains the historical cross-zone-only behaviour.
    Same-zone return cannot reserve a merely forecast future release.
    """
    contracts = contracts if contracts is not None else {
        int(row["node"]): row for row in observation["node_contracts"]}
    if source == destination:
        return None
    origin, target = contracts[source], contracts[destination]
    if origin["zone"] != target["zone"]:
        return "cross_zone_transfer"
    roles = observation.get("static_role_contract")
    if roles is None:
        return None
    if (roles.get("schema") != "g31.static_node_roles.v1"
            or not isinstance(roles.get("loader_nodes"), list)
            or any(type(node) is not int or node not in contracts for node in roles["loader_nodes"])
            or len(set(roles["loader_nodes"])) != len(roles["loader_nodes"])):
        raise ValueError("analytic_control:invalid_static_role_contract")
    if (actual_available and destination in roles["loader_nodes"]
            and origin.get("resource_owner", origin["zone"])
            == target.get("resource_owner", target["zone"])):
        return "local_empty_return"
    return None


def transfer_candidates(observation: dict[str, Any], *, predictive: bool,
                        message_delay: float = 0, expiry_slack: float = 60,
                        request_prefix: str = "analytic", terminal_clearing: bool = True,
                        respect_service_forecasts: bool = False,
                        compress_equivalent_demands: bool = True,
                        _reuse_observation_work: bool = True) -> dict[str, Any]:
    """Build a common feasible-intent pool and solve its analytical assignment.

    Local FIFO demand is protected before cross-zone export. Existing pending
    transfers count once and block duplicate promises. Final export/receive
    authority remains in the native owner. Stale observations can be rejected.
    """
    now = float(observation["now"])
    if message_delay < 0 or expiry_slack <= 0:
        raise ValueError("analytic_control:invalid_timing")
    compact = "control_projection" in observation
    if compact:
        if not compress_equivalent_demands:
            raise ValueError("analytic_control:compact_projection_requires_equivalent_columns")
        waiting, local_demand, demand_time, known_ports = _compact_demand(observation)
    else:
        jobs = _visible_demand(observation)
        waiting = sorted((j for j in jobs.values() if j["status"] in ("waiting", "waiting_for_tray")),
                         key=lambda j: (j["arrival"], j["business_bag_id"]))
        local_demand = Counter(int(j["origin"]) for j in waiting)
        demand_time = {int(j["origin"]): j["demand_observed_at"] for j in waiting}
        known_ports = {int(j["origin"]) for j in jobs.values()}
    contracts = {int(n["node"]): n for n in observation["node_contracts"]}
    needs_future_travel = predictive and any(t["mode"] in ("loading", "loaded", "storage", "empty_transit")
                                             for t in observation.get("trays", []))
    travel = PublicTravel(observation, _reuse_source_searches=_reuse_observation_work) if needs_future_travel else None
    all_forecasts = release_forecasts(observation, include_future=predictive, travel=travel)
    active = [t for t in observation.get("transfers", [])
              if t["status"] in ("pending", "granted", "in_transit", "requested", "delivered",
                                  "undelivered", "dispatching", "departed")]
    pledged = {t["tray_id"] for t in active}
    incoming = Counter(int(t["destination"]) for t in active)
    # A completed delivery newer than the latest destination queue snapshot
    # already covers that old request. Do not ship another tray merely because
    # the receiver's clearing message is still in flight.
    for transfer in observation.get("transfers", []):
        dest = int(transfer["destination"])
        if transfer["status"] == "received" and transfer.get("received_at", -1) >= demand_time.get(dest, math.inf):
            incoming[dest] += 1
    grouped: dict[int, list[ReleaseForecast]] = defaultdict(list)
    for forecast in all_forecasts:
        source_owner = contracts[forecast.node].get("resource_owner", contracts[forecast.node]["zone"])
        if source_owner != observation.get("owner_id"):
            continue  # A future remote release is not this controller's export authority.
        if forecast.tray_id not in pledged and (predictive or forecast.ledger == "actual_available"):
            grouped[forecast.node].append(forecast)
    supplies: list[ReleaseForecast] = []
    covered = incoming.copy()
    for node, rows in grouped.items():
        rows.sort(key=lambda f: (f.estimate, f.tray_id))
        demand_reserve = max(0, local_demand[node] - incoming[node])
        covered[node] += min(demand_reserve, len(rows))
        retained = demand_reserve + int(contracts[node].get("export_min_stock", 0))
        if contracts[node].get("allow_export", True):
            supplies.extend(rows[retained:])
    demand: list[dict[str, Any]] = []
    exact_demand_count = sum(max(0, count-covered[node]) for node, count in local_demand.items()
                             if contracts[node].get("allow_receive", True))
    if compact:
        projection = observation["control_projection"]
        if len(supplies) > int(projection["candidate_limit"]):
            raise ValueError("analytic_control:compact_supply_bound_exceeded")
        for group in projection["waiting_groups"]:
            node, count = int(group["origin"]), int(group["count"])
            required = min(len(supplies), max(0, count-covered[node]))
            represented = max(0, len(group["jobs"])-covered[node])
            if contracts[node].get("allow_receive", True) and represented < required:
                raise ValueError("analytic_control:insufficient_compact_fifo_coverage")
    for job in waiting:
        node = int(job["origin"])
        if compact and int(job["fifo_index"]) < covered[node]:
            continue
        if not compact and covered[node]:
            covered[node] -= 1
        elif contracts[node].get("allow_receive", True):
            demand.append(dict(job, demand_kind="observed_source_queue"))
    if supplies and travel is None:
        travel = PublicTravel(observation, _reuse_source_searches=_reuse_observation_work)
    clearing_pressure_without_supply = 0
    if terminal_clearing:
        # A reasonable reactive baseline must also free a full terminal for a
        # visible loaded arrival. This is ordinary expelling/receiving control,
        # shared by both policies; it is not counted as predictive innovation.
        approaching = Counter()
        local_jobs = _jobs_by_id(observation)
        for tray in observation.get("trays", []):
            job = local_jobs.get(tray.get("business_bag_id", ""))
            if not job or tray["mode"] not in ("loading", "loaded", "storage"):
                continue
            target = int(job["destination"])
            if tray["node"] != target and tray.get("edge_to", -1) != target:
                approaching[target] += 1
        outgoing = Counter(int(t["source"]) for t in active if "source" in t)
        # Only actual observed business origins are offered as return ports;
        # arbitrary conveyor nodes are not invented as parking destinations.
        supply_sources = {s.node for s in supplies}
        for source, arrivals in sorted(approaching.items()):
            contract = contracts[source]
            required = max(0, int(contract.get("occupancy", 0)) + arrivals - int(contract["capacity"]) - outgoing[source])
            if not required:
                continue
            if source not in supply_sources:
                clearing_pressure_without_supply += required
                continue
            destinations = [port for port in known_ports if public_transfer_scope(
                                observation, source, port, actual_available=True, contracts=contracts)
                            and contracts[port].get("allow_receive", True)
                            and math.isfinite(travel.complete(source, port))]
            if not destinations or not required:
                continue
            destination = min(destinations, key=lambda port: (travel.complete(source, port), port))
            exact_demand_count += required
            for slot in range(required):
                demand.append({"business_bag_id": f"port-clear:{source}:{slot}", "origin": destination,
                               "arrival": now, "demand_kind": "terminal_receiving_pressure",
                               "clearing_source": source})
    costs: list[list[float]] = []
    pool: list[dict[str, Any]] = []
    representatives = (_assignment_representatives(demand, len(supplies)) if compress_equivalent_demands
                       else list(enumerate(demand)))
    windows = None
    for i, supply in enumerate(supplies):
        row = []
        for j, job in representatives:
            destination = int(job["origin"])
            eta = max(now + message_delay, supply.estimate) + travel.complete(supply.node, destination)
            if respect_service_forecasts and _reuse_observation_work and windows is None:
                # Validate/select revisions only if a pair is evaluated, just
                # as the original lazy path. No snapshot survives this call.
                windows = conditional_service_windows(observation)
            window = departure_avoiding_published_windows(observation, supply, destination, travel,
                message_delay, _windows=windows) if respect_service_forecasts else None
            if window:
                eta = max(eta, window["earliest_departure"] + travel.complete(supply.node, destination))
            scope = public_transfer_scope(observation, supply.node, destination,
                actual_available=supply.ledger == "actual_available", contracts=contracts)
            wrong_clear_source = job.get("clearing_source", supply.node) != supply.node
            # For a fixed served count, minimizing total restricted queue area
            # (including unserved jobs at the common horizon) minimizes ETA.
            # Minimizing only served-job waiting would favor younger jobs by
            # dropping the older unserved population from the objective.
            cost = math.inf if scope is None or wrong_clear_source else eta - now
            row.append(cost)
            if math.isfinite(cost):
                candidate = {"supply": i, "demand": j, "predicted_arrival": eta,
                             "assignment_cost": cost, "predicted_wait": eta - float(job["arrival"]),
                             "path": list(travel.path(supply.node, destination)[1]), "service_window": window}
                if scope == "local_empty_return":
                    candidate["transfer_scope"] = scope
                pool.append(candidate)
        costs.append(row)
    chosen = _min_cost_matching(costs)
    intents = []
    for i, j in chosen:
        original_index, job = representatives[j]
        supply = supplies[i]
        choice = next(c for c in pool if c["supply"] == i and c["demand"] == original_index)
        eta = choice["predicted_arrival"]
        live_prefix = request_prefix if request_prefix.startswith("live:") else "live:" + request_prefix
        intents.append({"request_id": f"{live_prefix}:{observation.get('version', 0)}:{supply.tray_id}:{job['business_bag_id']}",
                        "tray_id": supply.tray_id, "source": supply.node,
                        "destination": int(job["origin"]), "issued_at": now,
                        "message_delay": message_delay, "earliest_departure": choice["service_window"]["earliest_departure"] if choice["service_window"] else now,
                        "expiry": eta + expiry_slack,
                        "forecast_dependency": supply.dependency,
                        "forecast_ledger": supply.ledger,
                        "control_reason": job["demand_kind"],
                        "service_window": choice["service_window"],
                        "owner_id": contracts[supply.node].get("resource_owner", contracts[supply.node]["zone"]),
                        "expected_version": observation.get("version", 0)})
        if choice.get("transfer_scope") == "local_empty_return":
            intents[-1]["transfer_scope"] = choice["transfer_scope"]
    serialize_forecast = _scalar_forecast_dict if _reuse_observation_work else asdict
    return {"policy": "analytic_predictive_matching" if predictive else "reactive_matching",
            "now": now, "version": observation.get("version", 0),
            "forecasts": [serialize_forecast(f) for f in all_forecasts], "pool": pool,
            "supplies": [serialize_forecast(s) for s in supplies], "demands": demand,
            "exact_waiting_count": sum(local_demand.values()), "exact_demand_count": exact_demand_count,
            "demand_identity_scope": "bounded_fifo_representatives" if compact else "all_visible_uncovered",
            "assignment_demand_count": len(representatives),
            "equivalent_column_compression": compress_equivalent_demands,
            "clearing_pressure_without_available_source": clearing_pressure_without_supply,
            "intents": intents, "includes_wait": True,
            "optimality": "minimum_cost_maximum_cardinality_in_declared_assignment_only",
            "physical_optimality": "unknown"}


def run_online_matching(session: Any, owners: list[str], *, horizon: float,
                        predictive: bool, control_period: float = .5,
                        message_delay: float = 0, demand_delay: float = 0,
                        publish: bool = True, controller_state: dict[str, Any] | None = None,
                        respect_service_forecasts: bool = False,
                        compact_projection: bool = False) -> dict[str, Any]:
    """Drive a persistent native session; never restart or mutate input tape.

    The observation/control period is a declared policy parameter shared by
    reactive and predictive comparisons. Delays are logical native message
    delays; wall-clock compute is measured separately and never advertised as
    physical evolution while Python is running. Full records include no-action
    and rejected requests, not only successful exports.
    """
    if control_period <= 0 or not math.isfinite(control_period) or not math.isfinite(horizon):
        raise ValueError("analytic_control:invalid_control_schedule")
    records, submitted, publication_records = [], [], []
    config = {"owners": list(owners), "predictive": predictive, "control_period": control_period,
              "message_delay": message_delay, "demand_delay": demand_delay, "publish": publish,
              "respect_service_forecasts": respect_service_forecasts}
    state = controller_state if controller_state is not None else {
        "schema": "g31.analytic_controller_state.v1", "config": config,
        "start": float(session.physical_time), "next_tick": 0, "published": {}}
    if state["config"] != config:
        raise ValueError("analytic_control:continuation_configuration_changed")
    published = state["published"]
    # Representation is not a policy parameter. A saved legacy publication
    # cache migrates exactly, so full/compact siblings publish the same events.
    signature_port = getattr(session, "demand_signature", None)
    if signature_port is not None:
        for owner, previous in list(published.items()):
            if isinstance(previous, list):
                published[owner] = demand_signature(previous)
    observe = session.observe_control if compact_projection else session.observe
    start, tick = float(state["start"]), int(state["next_tick"])
    if start + tick * control_period < session.physical_time - 1e-9:
        raise ValueError("analytic_control:missed_control_boundary")
    censored = False
    while start + tick * control_period <= horizon + 1e-9:
        target = min(horizon, start + tick * control_period)
        advance = session.advance_to(target)
        if advance.get("status") == "budget_exhausted":
            censored = True
            break
        if publish:
            publication_started = time.perf_counter()
            publication_owners = []
            for owner in owners:
                owner_publication_started = time.perf_counter()
                if signature_port is not None:
                    signature = signature_port(owner)
                else:
                    local = session.observe(owner)
                    signature = sorted([j["business_bag_id"], j["origin"], j["arrival"], j.get("deadline", -1)]
                                             for j in local.get("jobs", [])
                                             if j["status"] in ("waiting", "waiting_for_tray"))
                if published.get(owner) != signature:
                    for recipient in owners:
                        if recipient != owner:
                            session.publish_demand(owner, recipient, demand_delay)
                    published[owner] = signature
                publication_owners.append({"owner_id": owner, "compute_ms": 1000*(time.perf_counter()-owner_publication_started)})
            # Deliver zero-delay messages through the native event phase.
            advance = session.advance_to(target)
            publication_records.append({"tick": tick, "target": target,
                "owner_computations": publication_owners,
                "signature_and_publish_ms": sum(r["compute_ms"] for r in publication_owners),
                "including_due_native_delivery_ms": 1000*(time.perf_counter()-publication_started),
                "scope": "all local demand signatures, changed-snapshot serialization/submission, and due native events; logical delay separate"})
            if advance.get("status") == "budget_exhausted":
                censored = True
                break
        for owner in owners:
            compute_start = time.perf_counter()
            observed = observe(owner)
            observed_at = time.perf_counter()
            decision = transfer_candidates(observed, predictive=predictive,
                                           message_delay=message_delay,
                                           respect_service_forecasts=respect_service_forecasts,
                                           request_prefix=f"{'predictive' if predictive else 'reactive'}:{owner}:{tick}")
            planned_at = time.perf_counter()
            submit_seconds, residual_seconds = 0., 0.
            replies, replans = [], []
            # A submit changes the owner's message/accounting version. Re-read
            # and solve the residual assignment rather than stamping later
            # requests with an unchecked or knowingly stale original version.
            current = decision
            for attempt in range(len(decision["intents"])):
                if not current["intents"]:
                    break
                request = current["intents"][0]
                stage_started = time.perf_counter()
                reply = session.submit_transfer_intent(request)
                submit_seconds += time.perf_counter() - stage_started
                replies.append(reply)
                submitted.append({"request": request, "reply": reply})
                if reply.get("status") in ("rejected", "timeout_unknown", "failed_no_safe_continuation"):
                    break
                if attempt + 1 < len(decision["intents"]):
                    stage_started = time.perf_counter()
                    observed = observe(owner)
                    current = transfer_candidates(observed, predictive=predictive,
                                                  message_delay=message_delay,
                                                  respect_service_forecasts=respect_service_forecasts,
                                                  request_prefix=f"{'predictive' if predictive else 'reactive'}:{owner}:{tick}:{attempt+1}")
                    replans.append(current)
                    residual_seconds += time.perf_counter() - stage_started
            compute_ms = 1000 * (time.perf_counter() - compute_start)
            records.append({"owner_id": owner, "decision": decision, "replans": replans, "replies": replies,
                            "compute_ms": compute_ms, "compute_parts_ms": {
                                "observe": 1000*(observed_at-compute_start),
                                "initial_prediction_and_assignment": 1000*(planned_at-observed_at),
                                "submit": 1000*submit_seconds, "residual_observe_and_replan": 1000*residual_seconds}})
        if target == horizon:
            state["next_tick"] = tick + 1
            break
        tick += 1
        state["next_tick"] = tick
    result = session.result_at(session.physical_time if censored else horizon)
    censored = censored or result.get("advance", {}).get("status") == "budget_exhausted"
    # Keep censoring on the raw result as well as the controller envelope: an
    # offline continuation wrapper may intentionally return only run["result"].
    # result_at(current_clock) reporting a reached *prefix* cannot erase the
    # original requested horizon or promote an exhausted branch to complete.
    result["control_continuation"] = {"status": "budget_exhausted" if censored else "reached",
                                     "requested_horizon": horizon, "physical_time": session.physical_time}
    return {"status": "budget_exhausted" if censored else "reached", "result": result, "control_records": records,
            "publication_records": publication_records,
            "submitted": submitted, "controller": "analytic_predictive_matching" if predictive else "reactive_matching",
            "control_period": control_period, "command_delay": message_delay,
            "observation_representation": "compact_exact_fifo" if compact_projection else "full",
            "demand_delay": demand_delay,
            "controller_state": copy.deepcopy(state),
            "timing_scope": "observation+prediction+assignment+submit-call; serial owner calls; logical delay separate",
            "complete_100ms_evidence": False,
            "unmeasured_request_components": ["demand-publication serialization", "native owner revalidation at message delivery",
                                               "confirmation processing", "multi-process transport"]}
