"""A deterministic, in-process multi-owner protocol sharing the physical clock.

This is a synthetic distributed *mechanism*, not a network deployment. Planners
receive one PartitionObservation plus explicit anchor/vote messages. They never
receive a global Snapshot or a remote calendar. Public topology and fixed module
parameters are shared. Each resource owner votes against its own calendar and
short prepare leases. The physical arbiter alone has a global engine and performs
the final atomic ExecutionValidator operation. Its validation is not a planning
oracle: rejections expose a reason, never a remote calendar.

Integer ticks: observe/FIFO, refresh local views and expire leases, deliver due
messages in (delivery tick, sequence) order, timeouts, then advance physics one
tick. Zero-delay messages drain in that same order. Processing has zero synthetic
CPU duration; transport delays consume real simulation ticks. No wall-clock or
actual network performance claim is made. Full routes are committed so no-wait
cross-owner chains cannot be split by a message boundary.

Outages model unavailable owner message endpoints, with an explicitly simulated
failure-detector notice subject to the same transport faults/delay. Local sensing
is refreshed from that owner's partition only. This is data-flow isolation, not
an OS/process security sandbox. The simulator's global trace and physical facts
are offline diagnostics, never planner input. Unanswered resolve queries yield
``outcome_unknown`` even if the offline physical ledger records a real commit.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from heapq import heappop, heappush
import json

from .model import (Bag, FixedLocalModule, Leg, Network, Reservation,
                    RouteCandidate, SimulationCheckpoint, Snapshot)
from .partition_observation import PartitionObservation, observe_partition
from .request_service import RouteRequest, validate_committed_full_route
from .runtime import ExecutionValidator, INFINITY, Simulation, assert_invariants


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                            default=asdict).encode()).hexdigest()


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class ClockRequest:
    request_id: str
    coordinator: str
    bag_id: str | None
    tray_id: str
    intent: str = "new_route"
    max_attempts: int = 3
    # Relative to reception of the explicit owner anchor, not initial submit.
    departure_lead: int = 4
    timeout_ticks: int = 10
    avoid_edges: tuple[str, ...] = ()
    destination_node: str | None = None
    demand_id: str | None = None
    demand_expires_at: int | None = None

    def __post_init__(self):
        if self.intent not in {"new_route", "keep_valid", "update_suffix", "empty_transfer"}:
            raise ValueError("unknown request intent")
        for name in ("max_attempts", "timeout_ticks"):
            _integer(getattr(self, name), name, 1)
        _integer(self.departure_lead, "departure_lead")
        if self.demand_expires_at is not None:
            _integer(self.demand_expires_at, "demand expiry")
        if not all(isinstance(s, str) and s for s in
                   (self.request_id, self.coordinator, self.tray_id)):
            raise ValueError("request identities must be nonempty strings")
        if self.intent == "empty_transfer":
            if self.bag_id is not None or not isinstance(self.destination_node, str) or not self.destination_node:
                raise ValueError("empty_transfer requires bag_id=None and destination_node")
        elif not isinstance(self.bag_id, str) or not self.bag_id:
            raise ValueError("loaded request requires bag_id")


@dataclass(frozen=True)
class CancelUncommitted:
    request_id: str
    reason: str = "published_demand_cancelled_or_retargeted"


@dataclass(frozen=True)
class TransportFault:
    """One consumed matching send; copies use absolute extra delays from send."""
    kind: str
    request_id: str | None = None
    attempt: int | None = None
    destination: str | None = None
    delay: int | None = None
    drop: bool = False
    duplicate_delays: tuple[int, ...] = ()

    def __post_init__(self):
        if self.delay is not None:
            _integer(self.delay, "delay")
        for delay in self.duplicate_delays:
            _integer(delay, "duplicate delay")


@dataclass(frozen=True)
class OwnerOutage:
    owner: str
    start: int
    end: int

    def __post_init__(self):
        _integer(self.start, "outage start")
        _integer(self.end, "outage end", self.start + 1)


@dataclass(frozen=True)
class AnchorMessage:
    tray_id: str
    bag: Bag | None
    node: str
    at: int
    observed_version: int
    frozen_legs: tuple[Leg, ...] = ()
    old_plan_fingerprint: str | None = None
    destination_node: str | None = None

    @property
    def target(self):
        return self.bag.destination if self.bag is not None else self.destination_node


@dataclass(frozen=True)
class Proposal:
    request_id: str
    attempt: int
    anchor: AnchorMessage
    candidate: RouteCandidate
    slots: tuple[Reservation, ...]
    owners: tuple[str, ...]
    demand_id: str | None = None
    demand_expires_at: int | None = None


@dataclass(frozen=True)
class Lease:
    request_id: str
    attempt: int
    owner: str
    proposal_fingerprint: str
    expires: int
    observed_version: int
    dependency_fingerprint: str
    slots: tuple[Reservation, ...]
    demand_id: str | None = None


@dataclass(frozen=True)
class Vote:
    owner: str
    accepted: bool
    reason: str
    lease: Lease | None = None


@dataclass(order=True, frozen=True)
class Message:
    delivery: int
    sequence: int
    kind: str = field(compare=False)
    request_id: str = field(compare=False)
    attempt: int = field(compare=False)
    source: str = field(compare=False)
    destination: str = field(compare=False)
    payload: object = field(compare=False)


@dataclass
class RequestRecord:
    request: ClockRequest
    submitted_at: int
    attempt: int = 0
    deadline: int = 0
    phase: str = "new"
    outcome: str | None = None
    reason: str = ""
    finished_at: int | None = None
    owner_committed: bool = False
    acknowledged: bool = False
    committed_at: int | None = None
    failures: list[dict] = field(default_factory=list)
    proposal: Proposal | None = None
    votes: dict[str, Vote] = field(default_factory=dict)
    receipt_queries: int = 0
    # A rejected remote capacity proposal advances time, not private calendars.
    departure_floor: int = 0
    transport_failure: str = ""
    pending_failure: str = ""
    cancel_requested: bool = False


def owner_of(network: Network, resource: str):
    kind, _, key = resource.partition(":")
    node = network.edges[key].source if kind == "edge" else key
    if kind not in {"node", "edge", "reception"}:
        raise ValueError("unknown resource")
    return network.nodes[node].control_partition


def footprint(network, anchor, candidate):
    """Construct occupancy from public path/module timing, with no calendars."""
    node, tick, slots = anchor.node, anchor.at, []
    for leg in candidate.legs:
        if leg.depart > tick:
            slots.append(Reservation(f"node:{node}", tick, leg.depart, candidate.tray_id))
        slots.append(Reservation(f"edge:{leg.edge_id}", leg.depart, leg.arrive, candidate.tray_id))
        node, tick = network.edges[leg.edge_id].target, leg.arrive
    slots.append(Reservation(f"node:{node}", tick, INFINITY, candidate.tray_id))
    if candidate.usable_at > tick:
        slots.append(Reservation(f"reception:{node}", tick, candidate.usable_at, candidate.tray_id))
    return tuple(slots)


def _conflict(network, module, slots, now):
    """Local sweep, merging each physical tray's duplicate descriptions."""
    groups = defaultdict(list)
    for slot in slots:
        if slot.end > max(now, slot.start):
            groups[slot.resource, slot.tray_id].append((max(now, slot.start), slot.end))
    events = defaultdict(lambda: defaultdict(int))
    for (resource, _), intervals in groups.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        for start, end in merged:
            events[resource][start] += 1
            events[resource][end] -= 1
    for resource, times in sorted(events.items()):
        kind, _, key = resource.partition(":")
        capacity = (network.edges[key].capacity if kind == "edge" else
                    module.reception_capacity if kind == "reception" else network.nodes[key].capacity)
        count = 0
        for tick, change in sorted(times.items()):
            count += change
            if count > capacity:
                return f"local_capacity:{resource}@{tick}"
    return None


def preserves_source_prefixes(owner, network, available, exported, needs, times):
    """Current local same-zone unit matching, not a future service guarantee."""
    zone = network.nodes[exported.node].logistics_zone
    pool = [tray for tray in available if network.nodes[tray.node].logistics_zone == zone]
    regional = {unit: node for unit, node in needs.items() if network.nodes[node].logistics_zone == zone}
    def can_serve(tray, node):
        seen, pending = {tray.node}, [tray.node]
        while pending:
            current = pending.pop()
            if current == node:
                return True
            for edge in network.edges.values():
                target = network.nodes[edge.target]
                if (edge.source == current and edge.capacity > 0 and target.control_partition == owner
                        and target.logistics_zone == zone and edge.target not in seen):
                    seen.add(edge.target)
                    pending.append(edge.target)
        return False
    adjacency = {unit: [tray.tray_id for tray in pool if can_serve(tray, node)] for unit, node in regional.items()}
    def matching(units, exclude=None):
        occupied = {}
        def augment(unit, seen):
            for tray_id in adjacency[unit]:
                if tray_id == exclude or tray_id in seen:
                    continue
                seen.add(tray_id)
                if tray_id not in occupied or augment(occupied[tray_id], seen):
                    occupied[tray_id] = unit
                    return True
            return False
        return sum(augment(unit, set()) for unit in sorted(units))
    for cutoff in sorted({times[unit] for unit in regional}):
        prefix = [unit for unit in regional if times[unit] <= cutoff]
        if matching(prefix, exported.tray_id) < matching(prefix):
            return False
    return True


class ResourceParticipant:
    """Has only an owner view, public parameters, and protocol-local leases."""
    def __init__(self, observation: PartitionObservation, module: FixedLocalModule, source_guard_horizon=None):
        self.observation = deepcopy(observation)
        self.module = deepcopy(module)
        self.leases: dict[tuple[str, int], Lease] = {}
        self.accepted_demands: dict[str, dict] = {}
        self.seen_loaded_bags = {tray.bag_id for tray in observation.local_trays if tray.bag_id is not None}
        # A bag visible in an origin ledger is not necessarily waiting: it may
        # already be carried on an old remote edge. Queue facts arrive explicitly.
        self.waiting_units: dict[str, str] = {}
        self.task_facts_tick = -1
        self.demand_publications = {}
        self.demand_versions = {}
        self.source_guard_horizon = source_guard_horizon

    def demand_publication(self, publication):
        key = publication.revision, publication.published_at
        old_key = self.demand_versions.get(publication.unit_id)
        if old_key is None or key > old_key:
            self.demand_versions[publication.unit_id] = key
            self.demand_publications[publication.unit_id] = deepcopy(publication)
        elif key == old_key and self.demand_publications.get(publication.unit_id) != publication:
            # Ambiguous publications cannot release an accepted demand claim.
            self.demand_publications[publication.unit_id] = None

    def task_state(self, facts):
        if facts["observed_tick"] > self.task_facts_tick:
            self.task_facts_tick = facts["observed_tick"]
            self.seen_loaded_bags.update(facts["loaded_units"])
            self.waiting_units = {unit: node for unit, node in facts["waiting_units"].items()
                                  if unit not in self.seen_loaded_bags}

    def refresh(self, observation):
        if observation.owner != self.observation.owner:
            raise ValueError("cross-owner observation")
        self.observation = deepcopy(observation)
        self.seen_loaded_bags.update(tray.bag_id for tray in observation.local_trays if tray.bag_id is not None)
        self.leases = {key: lease for key, lease in self.leases.items()
                       if lease.expires > observation.observed_tick}
        local_trays = {tray.tray_id: tray for tray in observation.local_trays}
        for unit, claim in list(self.accepted_demands.items()):
            tray = local_trays.get(claim["tray_id"])
            publication = self.demand_publications.get(unit)
            demand_ended = publication is not None and (publication.cancelled
                or publication.expires_at <= observation.observed_tick or publication.node != claim["destination_node"])
            demand_ended = demand_ended or (claim.get("expires_at") is not None and claim["expires_at"] <= observation.observed_tick)
            if unit in self.waiting_units and unit not in self.seen_loaded_bags:
                demand_ended = False  # Observed real work supersedes a prediction TTL/cancellation.
            if (unit in self.seen_loaded_bags or (observation.observed_tick >= claim["usable_at"]
                    and (demand_ended or (tray is not None and tray.bag_id is not None and tray.bag_id != unit)))):
                self.accepted_demands.pop(unit)

    def _check(self, proposal, *, ignore_key=None):
        view = self.observation
        own = tuple(slot for slot in proposal.slots
                    if owner_of(view.public_topology, slot.resource) == view.owner)
        if not own:
            return "proposal_has_no_owned_resources", own
        tray_id = proposal.candidate.tray_id
        if proposal.candidate.bag_id is None and view.public_topology.nodes[proposal.anchor.node].control_partition == view.owner:
            source_reason = self._source_guard(proposal, ignore_key=ignore_key)
            if source_reason:
                return source_reason, own
        if (proposal.demand_expires_at is not None and proposal.demand_expires_at <= view.observed_tick
                and proposal.demand_id not in self.waiting_units):
            return "demand_prediction_expired", own
        if proposal.candidate.bag_id is None and any(claim["tray_id"] == tray_id for claim in self.accepted_demands.values()):
            return "tray_reserved_for_accepted_demand", own
        if proposal.demand_id is not None and proposal.demand_id in self.seen_loaded_bags:
            return "demand_already_loaded", own
        if proposal.demand_id in self.accepted_demands:
            return "demand_already_has_accepted_transfer", own
        others = [slot for slot in view.local_calendars if slot.tray_id != tray_id]
        for key, lease in self.leases.items():
            if key != ignore_key:
                if proposal.demand_id is not None and lease.demand_id == proposal.demand_id:
                    return "demand_already_prepared", own
                if any(slot.tray_id == tray_id for slot in lease.slots):
                    return "tray_already_prepared", own
                others.extend(lease.slots)
        return _conflict(view.public_topology, self.module, tuple(others) + own,
                         view.observed_tick), own

    def _source_guard(self, proposal, *, ignore_key):
        if self.source_guard_horizon is None:
            return None
        view, now = self.observation, self.observation.observed_tick
        # Only this owner's delivered forecasts/task facts are read. A future
        # publication or a message still in transport cannot revoke a proposal.
        needs = {}
        times = {}
        for unit, publication in self.demand_publications.items():
            if unit in self.seen_loaded_bags or unit in self.waiting_units:
                continue
            if publication is None:
                return "source_forecast_version_conflict"
            if (not publication.cancelled and publication.expires_at > now and publication.at <= now + self.source_guard_horizon
                    and view.public_topology.nodes[publication.node].control_partition == view.owner):
                needs[unit], times[unit] = publication.node, max(now, publication.at)
        for unit, node in self.waiting_units.items():
            if unit not in self.seen_loaded_bags:
                needs[unit], times[unit] = node, now
        busy = {slot.tray_id for slot in view.local_calendars if slot.resource.startswith("edge:") and slot.end > now}
        busy.update(claim["tray_id"] for claim in self.accepted_demands.values())
        for key, lease in self.leases.items():
            if key != ignore_key:
                busy.update(slot.tray_id for slot in lease.slots)
        pool = [tray for tray in view.local_trays if tray.mode == "empty" and tray.available_at <= now and tray.tray_id not in busy]
        tray = next((tray for tray in pool if tray.tray_id == proposal.candidate.tray_id), None)
        if tray is None:
            return "source_stock_no_longer_available"
        return None if preserves_source_prefixes(view.owner, view.public_topology, pool, tray, needs, times) else "source_prefix_protection_changed"

    def prepare(self, proposal, ttl):
        key = proposal.request_id, proposal.attempt
        existing = self.leases.get(key)
        if existing:
            return Vote(self.observation.owner, existing.proposal_fingerprint == digest(proposal),
                        "duplicate_prepare", existing)
        conflict, own = self._check(proposal)
        if conflict:
            return Vote(self.observation.owner, False, conflict)
        view = self.observation
        resources = {slot.resource for slot in own}
        dependencies = tuple(slot for slot in view.local_calendars if slot.resource in resources)
        lease = Lease(*key, view.owner, digest(proposal), view.observed_tick + ttl,
                      view.version, digest(dependencies), own, proposal.demand_id)
        self.leases[key] = lease
        return Vote(view.owner, True, "local_lease_prepared", lease)

    def authorize(self, proposal, supplied_lease):
        key = proposal.request_id, proposal.attempt
        lease = self.leases.get(key)
        if lease is None or lease != supplied_lease or lease.expires <= self.observation.observed_tick:
            return "lease_missing_expired_or_modified"
        if lease.proposal_fingerprint != digest(proposal):
            return "proposal_modified"
        # The watermark is allowed to advance as physics moves. Current LOCAL
        # calendars are swept again; a forecast is never upgraded into a lease.
        return self._check(proposal, ignore_key=key)[0]


class LocalRoutePlanner:
    """Bounded public-topology path enumeration; only own calendar is read.

    Schedules contiguous traversal after waiting at the safe source anchor.
    Remote votes, not remote lookahead, determine remote acceptance. This is
    deliberately incomplete for routes requiring internal waiting.
    """
    def __init__(self, horizon=80, expansion_limit=1000, path_limit=32):
        for name, value in (("horizon", horizon), ("expansion_limit", expansion_limit), ("path_limit", path_limit)):
            _integer(value, name, 1)
        self.horizon, self.expansion_limit, self.path_limit = horizon, expansion_limit, path_limit

    def plan(self, view, module, request, anchor, attempt, departure_floor=0):
        network = view.public_topology
        adjacency = defaultdict(list)
        for edge in sorted(network.edges.values(), key=lambda e: e.edge_id):
            if edge.capacity > 0 and edge.edge_id not in request.avoid_edges:
                adjacency[edge.source].append(edge)
        # Static reachability is a sound proof for this requested public graph.
        reachable, frontier = {anchor.node}, [anchor.node]
        while frontier:
            for edge in adjacency[frontier.pop()]:
                if edge.target not in reachable:
                    reachable.add(edge.target)
                    frontier.append(edge.target)
        if anchor.target not in reachable:
            return None, "proven_infeasible_static_no_path"
        queue, paths, expansions = [(0, (), anchor.node, (anchor.node,))], [], 0
        while queue and expansions < self.expansion_limit and len(paths) < self.path_limit:
            distance, ids, node, visited = heappop(queue)
            expansions += 1
            if node == anchor.target:
                paths.append(ids)
                continue
            for edge in adjacency[node]:
                if edge.target not in visited:
                    heappush(queue, (distance + edge.travel_time, ids + (edge.edge_id,),
                                     edge.target, visited + (edge.target,)))
        first = max(anchor.at, view.observed_tick + request.departure_lead, departure_floor)
        for depart in range(first, view.observed_tick + self.horizon + 1):
            for path in paths:
                tick, legs = depart, []
                for edge_id in path:
                    edge = network.edges[edge_id]
                    legs.append(Leg(edge_id, tick, tick + edge.travel_time))
                    tick += edge.travel_time
                unload = tick + (module.unload_ticks if anchor.bag is not None else 0)
                if anchor.bag is not None and anchor.bag.protected and unload > anchor.bag.deadline:
                    continue
                candidate = RouteCandidate(f"{request.request_id}:{attempt}", request.bag_id,
                    request.tray_id, tuple(legs), unload, unload + module.hold_ticks(anchor.target),
                    view.version, "local_static_fifo", destination_node=anchor.target)
                slots = footprint(network, anchor, candidate)
                own = tuple(s for s in slots if owner_of(network, s.resource) == view.owner)
                others = tuple(s for s in view.local_calendars if s.tray_id != request.tray_id)
                if _conflict(network, module, others + own, view.observed_tick) is None:
                    owners = tuple(sorted({owner_of(network, s.resource) for s in slots}))
                    return Proposal(request.request_id, attempt, anchor, candidate, slots, owners,
                                    request.demand_id, request.demand_expires_at), "candidate"
        return None, "search_exhausted_bounded_contiguous_paths"


@dataclass
class DistributedCheckpoint:
    simulation: SimulationCheckpoint
    protocol: dict

    def clone(self):
        return deepcopy(self)


@dataclass(frozen=True)
class DistributedResult:
    physical: object
    requests: dict[str, RequestRecord]
    outcome_counts: dict[str, int]
    trace: tuple[dict, ...]
    pending_messages: tuple[Message, ...]


class DistributedClock:
    """Single-thread deterministic transport + separate private physical arbiter.

    Protocol concurrency is interleaved message delivery, not OS concurrency.
    A lease prevents competing protocol admissions but is not a physical route
    commitment. Old routes remain reserved and move throughout an update.
    """
    def __init__(self, snapshot: Snapshot, future_bags=(), *, message_delay=1,
                 prepare_ttl=8, faults=(), outages=(), planner=None, controllers=None, publications=(), status_period=2):
        from .storage_contracts import reject_unsupported_storage
        future_bags = tuple(future_bags)
        # Check the environment tape as well as initial visible state; an
        # unsupported storage bag arriving later must not enter a live W2 run.
        reject_unsupported_storage(snapshot, future_bags, 'distributed_clock')
        _integer(message_delay, "message_delay")
        _integer(prepare_ttl, "prepare_ttl", 1)
        _integer(status_period, "status_period", 1)
        self._simulation = Simulation(snapshot, future_bags, control_mode="external", route_mode="whole_route")
        state = self._simulation.observe()
        self.module = deepcopy(state.module)
        self.participants = {owner: ResourceParticipant(observe_partition(state, owner), self.module,
                                getattr((controllers or {}).get(owner), "forecast_horizon", None))
                             for owner in sorted({n.control_partition for n in state.network.nodes.values()})}
        if len(self.participants) < 2:
            raise ValueError("distributed harness requires at least two owners")
        self.message_delay, self.prepare_ttl = message_delay, prepare_ttl
        self.faults, self.outages = tuple(faults), tuple(outages)
        self.consumed_faults: set[int] = set()
        self.planner = deepcopy(planner) if planner else LocalRoutePlanner()
        self.records: dict[str, RequestRecord] = {}
        self._queue: list[Message] = []
        self._sequence = 0
        self._trace: list[dict] = []
        # Idempotent authenticated receipts live with the arbiter, independent
        # of ACK delivery and independent of whether the bag later completes.
        self._receipts: dict[str, dict] = {}
        self._contexts: dict[tuple[str, int], object] = {}
        self._anchors: dict[tuple[str, int], AnchorMessage] = {}
        self._fenced_attempts: set[tuple[str, int]] = set()
        self._active_trays: dict[str, tuple[str, int]] = {}
        self._physical_trace_cursor = 0
        self.controllers = deepcopy(controllers or {})
        if set(self.controllers) - set(self.participants):
            raise ValueError("unknown controller owner")
        self.publications = tuple(deepcopy(publications))
        self._published_indices = set()
        self.status_period = status_period
        self._last_status_tick = None

    @property
    def now(self):
        return self._simulation.state.now

    def _event(self, event, **details):
        self._trace.append({"time": self.now, "event": event, **deepcopy(details)})

    def _down(self, owner):
        return any(o.owner == owner and o.start <= self.now < o.end for o in self.outages)

    def _refresh(self):
        state = self._simulation.observe()
        self._sync_physical_events()
        for owner, participant in self.participants.items():
            before = set(participant.leases)
            participant.refresh(observe_partition(state, owner))
            for request_id, attempt in sorted(before - set(participant.leases)):
                self._event("lease_expired", owner=owner, request_id=request_id, attempt=attempt)

    def _sync_physical_events(self):
        # result() appends a non-mutating preview marker, which is excluded.
        physical_events = self._simulation.result().trace[:-1]
        for item in physical_events[self._physical_trace_cursor:]:
            self._trace.append({"time": item["time"], "event": "physical_event", "detail": deepcopy(item)})
        self._physical_trace_cursor = len(physical_events)

    def submit(self, request: ClockRequest):
        if request.coordinator not in self.participants:
            raise ValueError("unknown coordinator")
        if request.request_id in self.records:
            if self.records[request.request_id].request != request:
                raise ValueError("request_id_identity_conflict")
            return deepcopy(self.records[request.request_id])
        self._refresh()
        record = RequestRecord(request, self.now)
        self.records[request.request_id] = record
        self._event("request_submitted", request_id=request.request_id, intent=request.intent)
        self._start(record)
        return deepcopy(record)

    def _send(self, kind, record, source, destination, payload=None, *, attempt=None):
        attempt = record.attempt if attempt is None else attempt
        self._send_raw(kind, record.request.request_id, attempt, source, destination, payload)

    def _send_raw(self, kind, request_id, attempt, source, destination, payload):
        delay, copies, drop = self.message_delay, (), False
        for index, fault in enumerate(self.faults):
            if (index not in self.consumed_faults and fault.kind == kind
                    and fault.request_id in (None, request_id)
                    and fault.attempt in (None, attempt) and fault.destination in (None, destination)):
                self.consumed_faults.add(index)
                delay = delay if fault.delay is None else fault.delay
                copies, drop = fault.duplicate_delays, fault.drop
                break
        self._event("message_sent", kind=kind, request_id=request_id,
                    attempt=attempt, source=source, destination=destination, delay=delay, dropped=drop)
        for offset in (() if drop else (delay,)) + copies:
            self._sequence += 1
            heappush(self._queue, Message(self.now + offset, self._sequence, kind,
                request_id, attempt, source, destination, deepcopy(payload)))

    def _start(self, record):
        record.attempt += 1
        record.phase, record.proposal, record.votes = "opening", None, {}
        record.deadline = self.now + record.request.timeout_ticks
        record.transport_failure = ""
        record.pending_failure = ""
        self._send("OPEN", record, record.request.coordinator, "arbiter")

    def _release(self, request_id, attempt):
        # Best-effort ABORT is explicitly messaged; lost/down messages leave a
        # lease until expiry. Atomic accepted finalization is handled separately.
        record = self.records[request_id]
        for owner in self.participants:
            self._send("ABORT", record, record.request.coordinator, owner, attempt=attempt)

    def _finish(self, record, outcome, reason, *, acknowledged=False):
        record.outcome, record.reason, record.finished_at = outcome, reason, self.now
        record.phase, record.acknowledged = "terminal", acknowledged
        self._event("request_finished", request_id=record.request.request_id, outcome=outcome,
                    reason=reason, owner_committed=record.owner_committed, acknowledged=acknowledged)
        controller = self.controllers.get(record.request.coordinator)
        if controller is not None:
            controller.on_outcome(record.request, outcome, self.now)

    def _failure(self, record, reason):
        # Resolve is a transmitted request-level fence, not a shared-memory
        # read of the physical commit flag. A negative response certifies that
        # a delayed COMMIT for this attempt can no longer be accepted.
        if record.phase == "querying":
            return
        if "timeout" in reason and record.transport_failure:
            reason = record.transport_failure + ":" + reason
        record.pending_failure = reason
        record.phase = "querying"
        record.deadline = self.now + record.request.timeout_ticks
        record.receipt_queries += 1
        self._send("QUERY", record, record.request.coordinator, "arbiter")

    def _resolved_failure(self, record, reason, *, old_valid):
        record.failures.append({"time": self.now, "attempt": record.attempt, "reason": reason})
        self._event("attempt_failed", request_id=record.request.request_id, attempt=record.attempt, reason=reason)
        self._release(record.request.request_id, record.attempt)
        if record.cancel_requested:
            self._finish(record, "cancelled_before_commit", reason)
            return
        if record.attempt < record.request.max_attempts:
            record.departure_floor = self.now + record.request.departure_lead + record.attempt
            self._start(record)
        else:
            if record.request.intent == "update_suffix" and old_valid:
                outcome = "suffix_update_failed_old_route_kept"
            elif reason.startswith("proven_infeasible"):
                outcome = "proven_infeasible"
            elif reason.startswith("search_exhausted"):
                outcome = "search_exhausted"
            elif "owner_unavailable" in reason:
                outcome = "owner_failure"
            elif "timeout" in reason:
                outcome = "communication_failure"
            else:
                outcome = "commit_failure"
            self._finish(record, outcome, reason)

    def _old_valid(self, record):
        req = record.request
        if req.bag_id is None:
            return False
        return validate_committed_full_route(self._simulation.state,
                  RouteRequest(req.request_id, req.bag_id, req.tray_id)).accepted

    def _open(self, record, attempt):
        request, state = record.request, self._simulation.state
        def reply(kind, payload):
            self._send(kind, record, "arbiter", request.coordinator, payload, attempt=attempt)
        if request.request_id in self._receipts:
            reply("ACK", self._receipts[request.request_id])
            return
        if (request.request_id, attempt) in self._fenced_attempts:
            reply("REJECT", "attempt_already_fenced")
            return
        # Synthetic authority: the immutable task-origin partition controls
        # suffix changes, in addition to explicit runtime tray permission.
        if request.intent in {"update_suffix", "keep_valid"} and not self._origin_authorized(record):
            reply("REJECT", "coordinator_not_task_control_owner")
            return
        if request.intent == "keep_valid":
            if self._old_valid(record):
                receipt = {"request_id": request.request_id, "outcome": "still_valid_old_route", "time": self.now, "committed": False}
                self._receipts[request.request_id] = receipt
                reply("ACK", receipt)
            else:
                reply("REJECT", "no_valid_full_old_route")
            return
        existing_anchor = self._anchors.get((request.request_id, attempt))
        if existing_anchor is not None:
            reply("ANCHOR", existing_anchor)
            return
        # Same-tray overlapping operations are disallowed at the owner boundary.
        if self._active_trays.get(request.tray_id) not in (None, (request.request_id, attempt)):
            reply("REJECT", "tray_request_already_active")
            return
        try:
            tray = state.trays[request.tray_id]
            bag = state.bags[request.bag_id] if request.bag_id is not None else None
            if tray.bag_id != request.bag_id:
                raise ValueError("request_identity_mismatch")
            if request.intent == "update_suffix":
                context = ExecutionValidator().prepare_replacement(state, request.tray_id)
                self._contexts[request.request_id, attempt] = context
                anchor = AnchorMessage(request.tray_id, bag, context.anchor_node, context.anchor_time,
                                       state.version, context.frozen_legs, digest(state.plans[request.tray_id]))
            else:
                expected_mode = "empty" if request.intent == "empty_transfer" else "loaded"
                if (tray.node is None or tray.mode != expected_mode or request.tray_id in state.plans
                        or request.tray_id in state.empty_targets or tray.available_at > self.now):
                    raise ValueError("new_route_requires_available_uncommitted_stationary_tray")
                if state.network.nodes[tray.node].control_partition != request.coordinator:
                    raise ValueError("new_request_outside_coordinator_partition")
                if request.intent == "empty_transfer" and request.destination_node not in state.network.nodes:
                    raise ValueError("unknown_empty_destination")
                anchor = AnchorMessage(request.tray_id, bag, tray.node, self.now, state.version,
                                       destination_node=request.destination_node)
            self._anchors[request.request_id, attempt] = anchor
            self._active_trays[request.tray_id] = request.request_id, attempt
            reply("ANCHOR", anchor)
        except (KeyError, ValueError) as error:
            reply("REJECT", str(error))

    def _origin_authorized(self, record):
        state, req = self._simulation.state, record.request
        bag = state.bags.get(req.bag_id)
        return bag is not None and state.network.nodes[bag.origin].control_partition == req.coordinator

    def _atomic_authorize(self, record, attempt, packet):
        """Explicit arbiter stage. Planning never receives this global state."""
        request = record.request
        proposal, transmitted_votes = packet
        def reply(kind, payload):
            self._send(kind, record, "arbiter", request.coordinator, payload, attempt=attempt)
        if request.request_id in self._receipts:
            reply("ACK", self._receipts[request.request_id])
            return
        if (request.request_id, attempt) in self._fenced_attempts:
            self._event("fenced_commit_rejected", request_id=request.request_id, attempt=attempt)
            reply("REJECT", "attempt_already_fenced")
            return
        if self._proposal_contract(record, proposal, attempt=attempt):
            reply("REJECT", "proposal_identity_modified")
            return
        if request.intent == "empty_transfer" and request.demand_id in self._simulation.state.bags:
            state = self._simulation.state
            actual = state.bags[request.demand_id]
            if actual.origin != request.destination_node:
                reply("REJECT", "observed_demand_origin_differs")
                return
            if (request.demand_id in state.load_times or request.demand_id in state.completed
                    or any(tray.bag_id == request.demand_id for tray in state.trays.values())):
                reply("REJECT", "demand_already_loaded")
                return
        if not proposal.candidate.legs and request.intent != "update_suffix":
            service_tick = proposal.candidate.unload_complete - (self.module.unload_ticks if request.bag_id is not None else 0)
            if self.now < service_tick:
                # A zero-edge service has no departure leg on which runtime can
                # encode waiting. Keep the received commit at the arbiter until
                # its declared service tick, then recheck every lease and fence.
                self._sequence += 1
                heappush(self._queue, Message(service_tick, self._sequence, "COMMIT", request.request_id,
                                             attempt, "arbiter_timer", "arbiter", deepcopy(packet)))
                self._event("commit_deferred_to_service_tick", request_id=request.request_id, service_tick=service_tick)
                return
        self._refresh()
        votes = {vote.owner: vote for vote in transmitted_votes}
        for owner in proposal.owners:
            vote = votes.get(owner)
            reason = "owner_unavailable:" + owner if self._down(owner) else (
                "missing_owner_vote" if not vote or not vote.accepted else
                self.participants[owner].authorize(proposal, vote.lease))
            self._event("owner_revalidation", request_id=request.request_id, owner=owner,
                        accepted=reason is None, reason=reason)
            if reason:
                reply("REJECT", reason)
                return
        state, candidate, validator = self._simulation.state, proposal.candidate, ExecutionValidator()
        # Only the arbiter rebases the global watermark after all owners recheck
        # live local calendars. No planner receives a refreshed global snapshot.
        candidate = replace(candidate, dependency_version=state.version)
        if request.intent == "update_suffix":
            try:
                if digest(state.plans.get(request.tray_id)) != proposal.anchor.old_plan_fingerprint:
                    raise ValueError("old_commitment_changed")
                context = validator.prepare_replacement(state, request.tray_id)
                if (context.anchor_node != proposal.anchor.node or context.frozen_legs != proposal.anchor.frozen_legs
                        or (candidate.legs and candidate.legs[0].depart < context.anchor_time)):
                    raise ValueError("physical_anchor_advanced")
                result = validator.replace_suffix(state, context, candidate, route_mode="whole_route")
            except ValueError as error:
                reply("REJECT", str(error))
                return
        else:
            result = self._simulation.intervene(candidate)
        if not result.accepted:
            reply("REJECT", "physical_" + result.reason)
            return
        assert_invariants(state)
        record.owner_committed, record.committed_at = True, self.now
        outcome = ("updated_route_success" if request.intent == "update_suffix" else
                   "empty_transfer_success" if request.intent == "empty_transfer" else "new_route_success")
        receipt = {"request_id": request.request_id, "outcome": outcome, "time": self.now, "committed": True,
                   "proposal_fingerprint": digest(proposal), "usable_at": candidate.usable_at,
                   "destination_node": proposal.anchor.target, "tray_id": request.tray_id,
                   "demand_id": request.demand_id}
        self._receipts[request.request_id] = receipt
        if request.demand_id is not None and request.intent == "empty_transfer":
            destination_owner = state.network.nodes[request.destination_node].control_partition
            self.participants[destination_owner].accepted_demands[request.demand_id] = {
                "tray_id": request.tray_id, "destination_node": request.destination_node,
                "usable_at": candidate.usable_at, "request_id": request.request_id,
                "expires_at": request.demand_expires_at}
        self._active_trays.pop(request.tray_id, None)
        # Atomic finalization and local calendar publication: never a gap where
        # neither lease nor physical reservation protects the accepted path.
        for participant in self.participants.values():
            participant.leases.pop((request.request_id, attempt), None)
        self._refresh()
        self._event("physical_commit", request_id=request.request_id, intent=request.intent,
                    candidate=asdict(candidate), owners=proposal.owners)
        reply("ACK", receipt)

    def _proposal_contract(self, record, proposal, *, attempt=None, received_anchor=None):
        """A malicious/buggy planner cannot omit an owner's authorization."""
        request = record.request
        attempt = record.attempt if attempt is None else attempt
        if not isinstance(proposal, Proposal):
            return "invalid_proposal_type"
        if (proposal.request_id, proposal.attempt, proposal.candidate.tray_id, proposal.candidate.bag_id) != (
                request.request_id, attempt, request.tray_id, request.bag_id):
            return "proposal_identity_modified"
        if (proposal.demand_id != request.demand_id or proposal.demand_expires_at != request.demand_expires_at
                or (request.intent == "empty_transfer" and
                proposal.candidate.destination_node != request.destination_node)):
            return "empty_destination_or_demand_modified"
        expected_anchor = received_anchor if received_anchor is not None else self._anchors.get((request.request_id, attempt))
        if proposal.anchor != expected_anchor:
            return "anchor_modified"
        network = self.participants[request.coordinator].observation.public_topology
        try:
            expected = footprint(network, proposal.anchor, proposal.candidate)
            owners = tuple(sorted({owner_of(network, slot.resource) for slot in expected}))
            if proposal.slots != expected or proposal.owners != owners:
                return "owner_footprint_modified"
        except (KeyError, ValueError):
            return "invalid_public_path"
        return None

    def _deliver(self, message):
        self._event("message_delivered", kind=message.kind, request_id=message.request_id,
                    attempt=message.attempt, sequence=message.sequence, source=message.source,
                    destination=message.destination, payload=message.payload)
        if message.kind == "TASK_STATE":
            if not self._down(message.destination):
                self.participants[message.destination].task_state(message.payload)
                if message.destination in self.controllers:
                    self.controllers[message.destination].receive(message.kind, deepcopy(message.payload), self.now)
            return
        if message.kind in {"OWNER_STATUS", "DEMAND_FORECAST"}:
            if not self._down(message.destination) and message.destination in self.controllers:
                if message.kind == "DEMAND_FORECAST":
                    self.participants[message.destination].demand_publication(message.payload)
                self.controllers[message.destination].receive(message.kind, deepcopy(message.payload), self.now)
            return
        record = self.records[message.request_id]
        if message.destination in self.participants and self._down(message.destination):
            self._event("owner_unavailable", owner=message.destination, request_id=message.request_id)
            # The harness has an explicit fault detector with message latency.
            # The coordinator learns this only if that notice is delivered.
            if message.kind not in {"OWNER_UNAVAILABLE", "ABORT"}:
                self._send("OWNER_UNAVAILABLE", record, "synthetic_failure_detector",
                           record.request.coordinator, message.destination, attempt=message.attempt)
            return
        if message.kind == "ABORT":
            self.participants[message.destination].leases.pop((message.request_id, message.attempt), None)
            return
        # Resource-owner/arbiter handlers use received attempts and their OWN
        # state, not the coordinator's instantaneous phase/attempt/outcome.
        if message.kind == "OPEN":
            self._open(record, message.attempt)
            return
        if message.kind == "PREPARE":
            vote = self.participants[message.destination].prepare(message.payload, self.prepare_ttl)
            self._event("owner_vote", request_id=message.request_id, vote=asdict(vote))
            self._send("VOTE", record, message.destination, record.request.coordinator, vote,
                       attempt=message.attempt)
            return
        if message.kind == "COMMIT":
            self._atomic_authorize(record, message.attempt, message.payload)
            return
        if message.kind == "QUERY":
            receipt = self._receipts.get(message.request_id)
            if receipt is None:
                self._fenced_attempts.add((message.request_id, message.attempt))
                if self._active_trays.get(record.request.tray_id) == (message.request_id, message.attempt):
                    self._active_trays.pop(record.request.tray_id)
                self._event("attempt_fenced", request_id=message.request_id, attempt=message.attempt)
            response = {"receipt": receipt, "fenced": receipt is None,
                        "observed_tick": self.now,
                        "old_route_valid": self._origin_authorized(record) and self._old_valid(record)}
            self._send("RECEIPT", record, "arbiter", record.request.coordinator, response,
                       attempt=message.attempt)
            return
        if record.outcome is not None or message.attempt != record.attempt:
            self._event("late_or_duplicate_ignored", request_id=message.request_id, kind=message.kind)
            return
        if message.kind == "ANCHOR":
            if record.phase != "opening":
                return
            participant = self.participants[record.request.coordinator]
            try:
                proposal, reason = self.planner.plan(deepcopy(participant.observation), deepcopy(self.module),
                    record.request, message.payload, record.attempt, record.departure_floor)
            except Exception as error:
                self._finish(record, "local_processing_failure", type(error).__name__)
                return
            if proposal is None:
                self._failure(record, reason)
                return
            contract_error = self._proposal_contract(record, proposal, received_anchor=message.payload)
            if contract_error:
                self._finish(record, "local_processing_failure", contract_error)
                return
            record.proposal, record.phase = proposal, "preparing"
            self._event("local_proposal", request_id=message.request_id, proposal=asdict(proposal),
                        planner_owner=participant.observation.owner,
                        visible_local_resources=sorted({s.resource for s in participant.observation.local_calendars}))
            for owner in proposal.owners:
                self._send("PREPARE", record, record.request.coordinator, owner, proposal)
        elif message.kind == "VOTE":
            if record.phase != "preparing":
                return
            vote = message.payload
            if not vote.accepted:
                self._failure(record, vote.reason)
                return
            record.votes[vote.owner] = vote
            if set(record.votes) == set(record.proposal.owners):
                record.phase = "committing"
                self._send("COMMIT", record, record.request.coordinator, "arbiter",
                           (record.proposal, tuple(record.votes.values())))
        elif message.kind == "REJECT":
            self._failure(record, message.payload)
        elif message.kind == "OWNER_UNAVAILABLE":
            record.transport_failure = "owner_unavailable:" + message.payload
            self._failure(record, record.transport_failure)
        elif message.kind == "ACK":
            receipt = message.payload
            if record.request.coordinator in self.controllers:
                self.controllers[record.request.coordinator].receive("RECEIPT", deepcopy(receipt), self.now)
            self._finish(record, receipt["outcome"], "authenticated_receipt", acknowledged=True)
        elif message.kind == "RECEIPT":
            if message.payload["receipt"] is not None:
                if record.request.coordinator in self.controllers:
                    self.controllers[record.request.coordinator].receive("RECEIPT", deepcopy(message.payload["receipt"]), self.now)
                self._finish(record, message.payload["receipt"]["outcome"], "receipt_recovered", acknowledged=True)
            else:
                assert message.payload["fenced"]
                self._resolved_failure(record, record.pending_failure or "timeout_without_receipt",
                                       old_valid=message.payload["old_route_valid"])

    def _tick(self):
        self._refresh()
        self._publish_control_messages()
        self._event("physical_observed", physical_version=self._simulation.state.version,
                    tray_positions={key: {"node": tray.node, "mode": tray.mode}
                                    for key, tray in sorted(self._simulation.state.trays.items())})
        while self._queue and self._queue[0].delivery <= self.now:
            self._deliver(heappop(self._queue))
        for owner, controller in sorted(self.controllers.items()):
            if not self._down(owner):
                proposals = controller.step(deepcopy(self.participants[owner].observation), deepcopy(self.module))
                for request in proposals:
                    if isinstance(request, CancelUncommitted):
                        record = self.records[request.request_id]
                        if record.request.coordinator != owner:
                            raise ValueError("controller attempted another owner's cancellation")
                        if record.outcome is None:
                            record.cancel_requested = True
                            self._failure(record, request.reason)
                        continue
                    if request.coordinator != owner:
                        raise ValueError("controller attempted another owner's request")
                    self.submit(request)
        for record in self.records.values():
            if record.outcome is not None or self.now < record.deadline:
                continue
            if record.phase == "querying":
                # Without a delivered fence/receipt the coordinator cannot
                # distinguish a lost commit from a lost acknowledgment.
                self._finish(record, "outcome_unknown", "resolve_response_timeout")
            else:
                self._failure(record, "communication_timeout")
        while self._queue and self._queue[0].delivery <= self.now:
            self._deliver(heappop(self._queue))

    def _publish_control_messages(self):
        for index, publication in enumerate(self.publications):
            if index not in self._published_indices and publication.published_at <= self.now:
                self._published_indices.add(index)
                for owner in sorted(self.controllers):
                    self._send_raw("DEMAND_FORECAST", "@forecast", 0, "published_forecast_source", owner, publication)
        if self.now % self.status_period or self._last_status_tick == self.now:
            return
        self._last_status_tick = self.now
        # Explicit origin-owner identity facts. No remote calendar/position or
        # future tape is sent. Carried initial/old transit and completed bags
        # remain loaded facts even when no local tray is visible at the origin.
        state = self._simulation.state
        carried = {tray.bag_id for tray in state.trays.values() if tray.bag_id is not None}
        for owner, participant in sorted(self.participants.items()):
            if self._down(owner):
                continue
            view = participant.observation
            own_bags = {bag.bag_id: bag for bag in state.bags.values()
                        if state.network.nodes[bag.origin].control_partition == owner}
            loaded = set(own_bags) & (carried | set(state.load_times) | set(state.completed))
            task_facts = {"observed_tick": self.now, "loaded_units": tuple(sorted(loaded)),
                          "waiting_units": {unit: bag.origin for unit, bag in own_bags.items() if unit not in loaded}}
            self._send_raw("TASK_STATE", "@task:" + owner, 0, "physical_identity_owner", owner, task_facts)
            busy = {slot.tray_id for slot in view.local_calendars if slot.resource.startswith("edge:") and slot.end > self.now}
            busy.update(slot.tray_id for lease in participant.leases.values() for slot in lease.slots)
            busy.update(claim["tray_id"] for claim in participant.accepted_demands.values())
            empty_counts = Counter(tray.node for tray in view.local_trays if tray.mode == "empty"
                                  and tray.available_at <= self.now and tray.tray_id not in busy)
            status = {"owner": owner, "observed_tick": self.now, "available_empty": dict(empty_counts),
                      "waiting_units": {unit: node for unit, node in participant.waiting_units.items()
                                        if unit not in participant.seen_loaded_bags},
                      "loaded_units": tuple(sorted(participant.seen_loaded_bags)),
                      "accepted_demands": deepcopy(participant.accepted_demands),
                      "prepared_demands": tuple(sorted({lease.demand_id for lease in participant.leases.values()
                                                         if lease.demand_id is not None}))}
            for destination in sorted(self.controllers):
                self._send_raw("OWNER_STATUS", "@status:" + owner, 0, owner, destination, status)

    def advance(self, horizon):
        _integer(horizon, "horizon", self.now)
        while self.now < horizon:
            self._tick()
            self._simulation.advance(self.now + 1)
            self._sync_physical_events()
        self._refresh()
        return self.result()

    def result(self):
        outcomes = Counter(r.outcome or "pending" for r in self.records.values())
        return DistributedResult(self._simulation.result(), deepcopy(self.records), dict(sorted(outcomes.items())),
                                 tuple(deepcopy(self._trace)), tuple(sorted(deepcopy(self._queue))))

    def checkpoint(self):
        protocol = {key: deepcopy(value) for key, value in self.__dict__.items() if key != "_simulation"}
        return DistributedCheckpoint(self._simulation.checkpoint(), protocol)

    @classmethod
    def from_checkpoint(cls, checkpoint):
        from .storage_contracts import reject_unsupported_storage
        clone = checkpoint.clone()
        future = tuple(bag for bags in clone.simulation.pending_arrivals.values() for bag in bags)
        reject_unsupported_storage(clone.simulation.state, future, 'distributed_clock_checkpoint')
        instance = cls.__new__(cls)
        instance.__dict__.update(clone.protocol)
        instance._simulation = Simulation.from_checkpoint(clone.simulation)
        return instance
