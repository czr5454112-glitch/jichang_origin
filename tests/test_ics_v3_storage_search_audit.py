"""Independent bounded integer-time oracle for mandatory on-carrier storage.

The oracle does not import/call either routing implementation, resource view,
effective_reservations, candidate_reservations, or ExecutionValidator. Its
domain is explicitly finite: positive integer edge travel, integer calendars,
one loaded decision carrier, fixed public release, and a fixed finite horizon.
Waiting is a one-tick action and every edge traversal checks all occupied ticks.
Final stock is checked against every future calendar breakpoint, beyond the
search horizon. Other carriers' calendars are constructed alongside fixtures
from complete manually declared itineraries, never from the production helpers.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from heapq import heappop, heappush
from itertools import count, product

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Edge, FixedLocalModule, InFlight, Leg, Network, Node, Reservation, RouteCandidate, Tray,
)
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StorageProgress, StorageSnapshot, StorageWaypointContract,
)


FOREVER = 10**12
AUDIT_COUNTERS = defaultdict(int)


@dataclass
class Case:
    state: StorageSnapshot
    # Independent external occupancy declarations, resource/start/end/owner.
    calendar: list = field(default_factory=list)


def tiny(*, now=0, release=3, capacity=1, protected=False, deadline=30, hold=0, unload=1):
    nodes = {n: Node(n, "z", "p", capacity=capacity if n == "E" else 4)
             for n in ("A", "E", "D")}
    edges = {name: Edge(name, a, b, 1) for name, a, b in
             (("ae", "A", "E"), ("ed", "E", "D"), ("bypass", "A", "D"))}
    bag = StorageBag("b", "A", "D", 0, deadline, protected,
                     storage=StorageWaypointContract("E", release, 0))
    return Case(StorageSnapshot(now, Network(nodes, edges), {"t": Tray("t", "A", "loaded", "b")},
                                {"b": bag}, module=FixedLocalModule(unload, {"D": hold})))


def capacity(case, resource):
    kind, key = resource.split(":", 1)
    if kind == "node":
        return case.state.network.nodes[key].capacity
    if kind == "edge":
        return case.state.network.edges[key].capacity
    assert kind == "reception"
    return case.state.module.reception_capacity


def free(case, resource, start, end):
    """Independent exact half-open occupancy; duplicate owner descriptions merge."""
    if end <= start:
        return True
    ticks = {start}
    ticks.update(t for r, a, b, owner in case.calendar if r == resource
                 for t in (a, b) if start <= t < end)
    return all(len({owner for r, a, b, owner in case.calendar
                    if r == resource and a <= tick < b}) < capacity(case, resource)
               for tick in ticks)


def add_other_plan(case, owner, origin, legs):
    """Declare an empty carrier's complete physical plan and its manual calendar."""
    state = case.state
    state.trays[owner] = Tray(owner, origin)
    node, tick = origin, state.now
    slots = []
    for leg in legs:
        edge = state.network.edges[leg.edge_id]
        assert edge.source == node and leg.depart >= tick and leg.arrive == leg.depart + edge.travel_time
        if leg.depart > tick:
            assert state.network.nodes[node].can_wait
            slots.append(("node:" + node, tick, leg.depart, owner))
        slots.append(("edge:" + leg.edge_id, leg.depart, leg.arrive, owner))
        node, tick = edge.target, leg.arrive
    slots.append(("node:" + node, tick, FOREVER, owner))
    hold = state.module.hold_ticks(node)
    if hold:
        slots.append(("reception:" + node, tick, tick + hold, owner))
    state.plans[owner] = RouteCandidate(owner, None, owner, tuple(legs), tick, tick + hold,
                                         state.version, owner, True, node)
    state.reservations += tuple(Reservation(*slot) for slot in slots)
    case.calendar.extend(slots)


def storage_occupied(case, until, owner="occupant"):
    if until <= case.state.now:
        return
    state = case.state
    parking, edge_id = "P-" + owner, "leave-" + owner
    state.network.nodes[parking] = Node(parking, "z", "p", capacity=4)
    state.network.edges[edge_id] = Edge(edge_id, "E", parking, 1)
    add_other_plan(case, owner, "E", (Leg(edge_id, until, until + 1),))


def receiver_busy(case, until):
    if until <= case.state.now:
        return
    case.state.trays["receiver"] = Tray("receiver", "D", "holding", available_at=until)
    case.calendar.extend([("node:D", case.state.now, FOREVER, "receiver"),
                          ("reception:D", case.state.now, until, "receiver")])


def oracle(case, horizon, *, distinct_edge_paths=False):
    """Enumerate exact-time states; K path retention is used only in tiny DAGs."""
    AUDIT_COUNTERS["oracle_calls"] += 1
    state = case.state
    tray, bag = state.trays["t"], state.bags["b"]
    if tray.node is None or tray.mode != "loaded" or tray.available_at > state.now or "t" in state.plans:
        return ()
    progress = state.storage_progress.get("b")
    passed = progress is not None and progress.arrived_at is not None
    if tray.node == "E" and not passed:
        return ()
    stop = state.now + horizon
    order = count()
    queue = [(state.now, next(order), tray.node, passed, ())]
    seen, goals = set(), []
    outgoing = defaultdict(list)
    for edge in state.network.edges.values():
        outgoing[edge.source].append(edge)
    while queue:
        tick, _, node, passed, legs = heappop(queue)
        arrival = legs[-1].arrive if legs else state.now
        key = (node, tick, passed, arrival if node == bag.destination else None,
               tuple(l.edge_id for l in legs) if distinct_edge_paths else ())
        if key in seen:
            continue
        seen.add(key)
        AUDIT_COUNTERS["oracle_exact_states"] += 1
        if node == bag.destination and passed and tick == arrival:
            unload = tick + state.module.unload_ticks
            usable = unload + state.module.hold_ticks(node)
            if (state.network.nodes[node].can_wait and (not bag.protected or unload <= bag.deadline)
                    and free(case, "node:" + node, tick, FOREVER)
                    and free(case, "reception:" + node, tick, usable)):
                goals.append((tick, legs))
                if not distinct_edge_paths:
                    return tuple(goals)
        if tick >= stop:
            continue
        if state.network.nodes[node].can_wait and free(case, "node:" + node, tick, tick + 1):
            heappush(queue, (tick + 1, next(order), node, passed, legs))
        if node == "E" and tick < bag.storage.release_at:
            continue
        for edge in outgoing[node]:
            arrive = tick + edge.travel_time
            if arrive <= stop and all(free(case, "edge:" + edge.edge_id, t, t + 1)
                                      for t in range(tick, arrive)):
                heappush(queue, (arrive, next(order), edge.target, passed or edge.target == "E",
                                legs + (Leg(edge.edge_id, tick, arrive),)))
    return tuple(goals)


def assert_witness(case, candidate, horizon):
    """Check independently of the shared owner validator."""
    state, bag = case.state, case.state.bags["b"]
    assert candidate.bag_id == "b" and candidate.tray_id == "t"
    assert candidate.dependency_version == state.version
    assert not candidate.prefix_only and candidate.destination_node == "D"
    progress = state.storage_progress.get("b")
    passed = progress is not None and progress.arrived_at is not None
    node, tick = state.trays["t"].node, state.now
    for leg in candidate.legs:
        edge = state.network.edges[leg.edge_id]
        assert edge.source == node and leg.depart >= tick
        assert leg.arrive == leg.depart + edge.travel_time
        assert leg.depart == tick or state.network.nodes[node].can_wait
        assert free(case, "node:" + node, tick, leg.depart)
        assert all(free(case, "edge:" + edge.edge_id, t, t + 1) for t in range(leg.depart, leg.arrive))
        if node == "E":
            assert passed and leg.depart >= bag.storage.release_at
        node, tick = edge.target, leg.arrive
        passed |= node == "E"
    assert node == "D" and passed and tick <= state.now + horizon
    assert candidate.unload_complete == tick + state.module.unload_ticks
    assert candidate.usable_at == candidate.unload_complete + state.module.hold_ticks(node)
    assert not bag.protected or candidate.unload_complete <= bag.deadline
    assert free(case, "node:D", tick, FOREVER)
    assert free(case, "reception:D", tick, candidate.usable_at)
    AUDIT_COUNTERS["independently_checked_witnesses"] += 1


def query(case, *, horizon=14, k=1, budget=50000):
    # Production imports intentionally confined to the subject-under-test path.
    from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
    from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
    before = asdict(case.state)
    planner = StorageCandidateGenerator(RegionalCandidateGenerator(
        horizon=horizon, expansion_limit=budget, deadline_ms=None, dynamic_local=True))
    candidates = planner.generate(case.state, "b", "t", k)
    AUDIT_COUNTERS["production_queries"] += 1
    assert asdict(case.state) == before
    assert planner.last_expansions <= budget
    for candidate in candidates:
        assert_witness(case, candidate, horizon)
    return candidates, planner


def compare(case, *, horizon=14, k=1):
    expected = oracle(case, horizon)
    actual, planner = query(case, horizon=horizon, k=k)
    assert bool(actual) == bool(expected), (planner.last_search_status, planner.last_diagnostics)
    if expected:
        assert actual[0].legs[-1].arrive == expected[0][0]
    return actual


@pytest.mark.parametrize("release,busy,slots,now", tuple(product((0, 3, 6), (0, 2, 7), (1, 2), (0, 3))))
def test_exact_integer_storage_calendar_matrix(release, busy, slots, now):
    case = tiny(now=now, release=release, capacity=slots)
    storage_occupied(case, busy)
    compare(case)


@pytest.mark.parametrize("hold,unload,reception_until,protected,deadline", tuple(product((0, 2), (0, 2), (0, 7), (False, True), (6, 12))))
def test_exact_service_and_protected_matrix(hold, unload, reception_until, protected, deadline):
    case = tiny(hold=hold, unload=unload, protected=protected, deadline=deadline)
    receiver_busy(case, reception_until)
    compare(case)


@pytest.mark.parametrize("length,upstream_wait,busy", tuple(product((1, 2, 3), (True, False), (2, 8))))
def test_no_wait_chain_retains_later_arrivals(length, upstream_wait, busy):
    case = tiny(release=3)
    state = case.state
    state.network.edges.pop("ae")
    state.network.nodes["A"] = replace(state.network.nodes["A"], can_wait=upstream_wait)
    source = "A"
    for i in range(length):
        target = "N" + str(i)
        state.network.nodes[target] = Node(target, "z", "p", can_wait=False)
        state.network.edges[source + target] = Edge(source + target, source, target, 1)
        source = target
    state.network.edges[source + "E"] = Edge(source + "E", source, "E", 1)
    storage_occupied(case, busy)
    compare(case)


def test_no_wait_chain_after_storage_projects_final_hold_calendar():
    case = tiny(release=2, hold=2)
    state = case.state
    state.network.edges.pop("ed")
    for node in ("B", "C"):
        state.network.nodes[node] = Node(node, "z", "p", can_wait=False)
    for a, b in (("E", "B"), ("B", "C"), ("C", "D")):
        state.network.edges[a + b] = Edge(a + b, a, b, 1)
    receiver_busy(case, 8)
    actual = compare(case)
    assert actual[0].legs[-1].arrive == 8


def test_final_stock_must_fit_beyond_search_horizon():
    case = tiny(release=0)
    state = case.state
    state.network.nodes["D"] = replace(state.network.nodes["D"], capacity=1)
    state.network.nodes["X"] = Node("X", "z", "p")
    state.network.edges["xd"] = Edge("xd", "X", "D", 1)
    add_other_plan(case, "future-stock", "X", (Leg("xd", 29, 30),))
    assert not compare(case, horizon=14)


def test_duplicate_calendar_owner_is_one_physical_unit():
    case = tiny(release=5, capacity=2)
    storage_occupied(case, 7)
    slot = Reservation("node:E", 2, 6, "occupant")
    case.state.reservations += (slot, slot)
    case.calendar.extend([(slot.resource, slot.start, slot.end, slot.tray_id)] * 2)
    assert compare(case)[0].legs[0].depart == 0


def test_multicapacity_release_requires_only_one_free_slot():
    case = tiny(release=6, capacity=2)
    storage_occupied(case, 4, "first")
    storage_occupied(case, 8, "second")
    candidate = compare(case)[0]
    assert candidate.legs[0].arrive == 4


def test_k_three_retains_equal_earliest_physical_path_families():
    case = tiny(release=3)
    state = case.state
    state.network.edges.pop("ae")
    state.network.nodes["A"] = replace(state.network.nodes["A"], can_wait=False)
    for n in ("L", "M", "R"):
        state.network.nodes[n] = Node(n, "z", "p", can_wait=False)
        state.network.edges["A" + n] = Edge("A" + n, "A", n, 1)
        state.network.edges[n + "E"] = Edge(n + "E", n, "E", 1)
    expected = oracle(case, 6, distinct_edge_paths=True)
    best = min(t for t, _ in expected)
    families = {tuple(leg.edge_id for leg in legs) for t, legs in expected if t == best}
    candidates, _ = query(case, horizon=6, k=3)
    assert len(families) == 3 and len(candidates) == 3
    assert {tuple(leg.edge_id for leg in c.legs) for c in candidates} == families
    assert all(c.legs[-1].arrive == best for c in candidates)


def test_old_inflight_other_carrier_allows_only_zero_dwell_storage_passage():
    case = tiny(release=5, capacity=1)
    state = case.state
    state.network.nodes["X"] = Node("X", "z", "other")
    state.network.edges["xe"] = Edge("xe", "X", "E", 3)
    state.trays["old"] = Tray("old", None, "in_transit")
    state.old_in_transit = (InFlight("old", "xe", -1, 2),)
    case.calendar.extend([("edge:xe", -1, 2, "old"), ("node:E", 2, FOREVER, "old")])
    candidates = compare(case)
    assert candidates[0].legs[0].arrive == candidates[0].legs[1].depart == 5


def test_own_inflight_cannot_be_replanned_from_a_future_arrival():
    case = tiny(release=5)
    case.state.trays["t"] = Tray("t", None, "in_transit", "b")
    case.state.old_in_transit = (InFlight("t", "ae", 0, 1),)
    assert not compare(case)


@pytest.mark.parametrize("now,release,departed", [(3, 6, False), (6, 6, False), (7, 2, False), (8, 2, True)])
def test_actual_storage_progress_controls_search_stage(now, release, departed):
    case = tiny(now=now, release=release)
    state = case.state
    state.storage_progress["b"] = StorageProgress("t", state.bags["b"].storage, 1, 2 if departed else None)
    if not departed:
        state.trays["t"] = replace(state.trays["t"], node="E")
    compare(case)


@pytest.mark.parametrize("mode", ["whole_route", "next_edge"])
def test_checkpoint_restore_preserves_search_calendar_and_candidates(mode):
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    case = tiny(release=5, hold=2)
    storage_occupied(case, 4)
    AUDIT_COUNTERS["physical_runs"] += 1
    engine = Simulation(case.state, control_mode="external", route_mode=mode)
    engine.observe()
    AUDIT_COUNTERS["physical_runs"] += 1
    restored = Simulation.from_checkpoint(engine.checkpoint())
    for current in (engine, restored):
        current.advance(2)
    left = Case(engine.observe(), deepcopy(case.calendar))
    right = Case(restored.observe(), deepcopy(case.calendar))
    l, r = compare(left), compare(right)
    assert asdict(left.state) == asdict(right.state)
    assert [asdict(c) for c in l] == [asdict(c) for c in r]


def test_busy_storage_with_return_loop_has_legal_late_witness_with_original_budget():
    case = tiny(release=100)
    case.state.network.edges["ea"] = Edge("ea", "E", "A", 1)
    storage_occupied(case, 110)
    expected = oracle(case, 120)
    assert expected and expected[0][0] == 101
    candidates, planner = query(case, horizon=120, budget=500, k=1)
    assert candidates, (planner.last_search_status, planner.last_diagnostics)
    assert candidates[0].legs[-1].arrive == 101


@pytest.mark.parametrize("edge_capacity,release,duplicate", tuple(product((1, 2), (0, 3, 6), (False, True))))
def test_egress_requires_entire_travel_interval_with_multicapacity(edge_capacity, release, duplicate):
    case = tiny(release=release, capacity=2)
    state = case.state
    state.network.edges["ed"] = replace(state.network.edges["ed"], travel_time=4, capacity=edge_capacity)
    add_other_plan(case, "on-egress", "E", (Leg("ed", 1, 5),))
    if duplicate:
        redundant = Reservation("edge:ed", 2, 4, "on-egress")
        state.reservations += (redundant,)
        case.calendar.append((redundant.resource, redundant.start, redundant.end, redundant.tray_id))
    compare(case)


@pytest.mark.parametrize("edge_capacity", [2, 3])
def test_egress_capacity_threshold_counts_simultaneous_distinct_carriers(edge_capacity):
    case = tiny(release=3, capacity=3)
    state = case.state
    state.network.edges["ed"] = replace(state.network.edges["ed"], travel_time=4, capacity=edge_capacity)
    add_other_plan(case, "egress-one", "E", (Leg("ed", 1, 5),))
    add_other_plan(case, "egress-two", "E", (Leg("ed", 2, 6),))
    candidates = compare(case)
    assert candidates[0].legs[-1].depart == (5 if edge_capacity == 2 else 3)


def test_mandatory_egress_floor_considers_nonshortest_static_exit():
    case = tiny(release=3, capacity=6)
    state = case.state
    state.network.edges.pop("ed")
    state.network.nodes["X"] = Node("X", "z", "p", capacity=6)
    state.network.nodes["Y"] = Node("Y", "z", "p", can_wait=False)
    for name, a, b, travel in [("ex", "E", "X", 1), ("xd", "X", "D", 1),
                                ("ey", "E", "Y", 2), ("yd", "Y", "D", 2)]:
        state.network.edges[name] = Edge(name, a, b, travel)
    for i, depart in enumerate(range(3, 8)):
        add_other_plan(case, "fast-exit-" + str(i), "E", (Leg("ex", depart, depart + 1),))
    candidates = compare(case)
    assert candidates[0].legs[-1].arrive == 7
    assert tuple(leg.edge_id for leg in candidates[0].legs) == ("ae", "ey", "yd")


def test_actual_old_flight_occupies_entire_egress_before_late_acquire():
    case = tiny(release=1, capacity=2)
    state = case.state
    state.network.edges["ed"] = replace(state.network.edges["ed"], travel_time=4)
    state.trays["old-egress"] = Tray("old-egress", None, "in_transit")
    state.old_in_transit = (InFlight("old-egress", "ed", -1, 3),)
    case.calendar.extend([("edge:ed", -1, 3, "old-egress"), ("node:D", 3, FOREVER, "old-egress")])
    candidates = compare(case)
    assert candidates[0].legs[-1].depart == 3 and candidates[0].legs[-1].arrive == 7


@pytest.mark.parametrize("budget", [1, 2, 4, 8, 16, 32])
def test_interval_and_projection_exhaustion_keeps_original_request_budget(budget):
    case = tiny(release=8, capacity=2)
    storage_occupied(case, 10)
    receiver_busy(case, 12)
    candidates, planner = query(case, budget=budget)
    assert planner.last_diagnostics["preprocessing_budget_included"]
    assert planner.last_diagnostics["missing_candidate_is_not_infeasibility"]
    if planner.last_search_status == "expansion_budget_exhausted":
        assert planner.last_expansions == budget


@pytest.mark.parametrize("storage_busy_until,protected", tuple(product((0, 6), (False, True))))
def test_downstream_no_wait_blockage_projects_departure_back_to_full_storage(storage_busy_until, protected):
    case = tiny(release=3, capacity=1, protected=protected, deadline=10)
    state = case.state
    state.network.edges.pop("ed")
    state.network.nodes["B"] = Node("B", "z", "q", can_wait=False)
    state.network.nodes["C"] = Node("C", "z", "q", capacity=4, can_wait=False)
    state.network.nodes["Q"] = Node("Q", "z", "q")
    for name, source, target, travel in [("eb", "E", "B", 1), ("bc", "B", "C", 2),
                                         ("cd", "C", "D", 1), ("cq", "C", "Q", 1)]:
        state.network.edges[name] = Edge(name, source, target, travel)
    # The other tray waits at a real upstream node, then crosses B without
    # waiting, occupies bc[4,6), crosses C immediately and parks at Q.
    state.network.nodes["X"] = Node("X", "z", "q")
    state.network.edges["xb"] = Edge("xb", "X", "B", 1)
    add_other_plan(case, "downstream", "X", (Leg("xb", 3, 4), Leg("bc", 4, 6), Leg("cq", 6, 7)))
    storage_occupied(case, storage_busy_until)
    expected = oracle(case, 14)
    assert expected[0][0] == 9
    candidates, planner = query(case)
    assert candidates, (planner.last_search_status, planner.last_diagnostics)
    assert candidates[0].legs[-1].arrive == 9


@pytest.mark.parametrize("mode,protected,accepted", [("whole_route", False, True),
                                                    ("next_edge", True, True),
                                                    ("next_edge", False, False)])
def test_manual_zero_dwell_witness_at_full_storage_obeys_commit_mode(mode, protected, accepted):
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    case = tiny(release=3, protected=protected)
    storage_occupied(case, 7)
    arrival, legs = oracle(case, 14)[0]
    assert arrival == 4
    AUDIT_COUNTERS["physical_runs"] += 1
    engine = Simulation(case.state, control_mode="external", route_mode=mode)
    observed = engine.observe()
    candidate = RouteCandidate("manual", "b", "t", legs, arrival + 1, arrival + 1,
                               observed.version, "manual", True, "D")
    assert_witness(Case(observed, case.calendar), candidate, 14)
    before = asdict(engine.state)
    outcome = engine.intervene(candidate)
    assert outcome.accepted is accepted
    if accepted:
        final = engine.advance(5).final_snapshot
        assert final.completed["b"] == 5
        assert final.storage_progress["b"].arrived_at == final.storage_progress["b"].departed_at == 3
        assert final.trays["occupant"].node == "E"
    else:
        assert outcome.reason.startswith("prefix_capacity:")
        assert asdict(engine.state) == before


class Meter:
    def __init__(self):
        self.work = defaultdict(int)

    def _consume(self, stage):
        self.work[stage] += 1


@pytest.mark.parametrize("storage_capacity,permanent", [(1, False), (2, False), (2, True)])
def test_capacity_interval_summary_matches_independent_tick_occupancy(storage_capacity, permanent):
    from scripts.experiments.ics_circulation_v3.storage_calendar import CapacityCalendarView
    case = tiny(capacity=storage_capacity)
    if permanent:
        for owner in ("idle-one", "idle-two"):
            case.state.trays[owner] = Tray(owner, "E")
            case.calendar.append(("node:E", 0, FOREVER, owner))
    else:
        storage_occupied(case, 5, "one")
        if storage_capacity == 2:
            storage_occupied(case, 8, "two")
        redundant = Reservation("node:E", 2, 4, "one")
        case.state.reservations += (redundant,)
        case.calendar.append((redundant.resource, redundant.start, redundant.end, redundant.tray_id))
    receiver_busy(case, 7)
    meter = Meter()
    view = CapacityCalendarView(meter, case.state, "t")
    for resource in ("node:E", "node:D", "reception:D", "edge:ae"):
        for start, duration in product(range(11), range(6)):
            AUDIT_COUNTERS["calendar_oracle_comparisons"] += 1
            assert view.available(resource, start, start + duration) == free(case, resource, start, start + duration)
            expected = next((t for t in range(start, 20) if free(case, resource, t, t + duration)), FOREVER)
            assert view.earliest_available(resource, start, duration) == expected
    assert meter.work["storage_calendar_reservations"] > 0
    assert meter.work["storage_calendar_endpoints"] > 0


def relaxed_integer_oracle(case, start, horizon=30):
    """Independent time expansion of the declared edge-only waiting relaxation."""
    reachable = {(start, "E")}
    for tick in range(start, horizon + 1):
        nodes = {node for t, node in reachable if t == tick}
        if "D" in nodes:
            return tick
        for node in nodes:
            reachable.add((tick + 1, node))  # All nodes may wait in this relaxation.
            for edge in case.state.network.edges.values():
                if edge.source == node and all(free(case, "edge:" + edge.edge_id, t, t + 1)
                                               for t in range(tick, tick + edge.travel_time)):
                    reachable.add((tick + edge.travel_time, edge.target))
    return FOREVER


def test_fifo_relaxed_suffix_floor_matches_separate_integer_time_expansion():
    from scripts.experiments.ics_circulation_v3.storage_calendar import CapacityCalendarView, StorageCompletionLowerBound
    from scripts.experiments.ics_circulation_v3.routing import _StaticTopology, network_signature
    case = tiny(release=3, capacity=2)
    state = case.state
    state.network.edges.pop("ed")
    state.network.nodes["B"] = Node("B", "z", "q", can_wait=False)
    state.network.nodes["X"] = Node("X", "z", "q")
    state.network.edges.update({"eb": Edge("eb", "E", "B", 1),
                                "bd": Edge("bd", "B", "D", 3),
                                "xb": Edge("xb", "X", "B", 1)})
    add_other_plan(case, "blocking-edge", "X", (Leg("xb", 1, 2), Leg("bd", 2, 5)))
    storage_occupied(case, 12)
    receiver_busy(case, 16)
    meter = Meter()
    topology = _StaticTopology(network_signature(state.network), meter._consume)
    view = CapacityCalendarView(meter, state, "t")
    bound = StorageCompletionLowerBound(meter, topology, view, "E", "D", 3)
    values = []
    for start in range(11):
        expected = relaxed_integer_oracle(case, max(start, 3))
        actual = bound.earliest_final(start)
        assert actual == expected
        values.append(actual)
        AUDIT_COUNTERS["relaxed_lower_bound_oracle_comparisons"] += 1
    assert values == sorted(values)
    assert meter.work["storage_relaxed_time_labels"] and meter.work["storage_relaxed_edge_scans"]
