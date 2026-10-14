"""Independent bounded terminal-screen review; no author fixtures imported.

The earlier independent integer-calendar fixture is reused, not presented as a
new independent physical sample. The reachability oracle below does not call
routing, validators, or effective_reservations. All peer itineraries are hand
declared and tracked separately from production reservations.
"""
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import asdict, replace
from itertools import product

import pytest

from test_ics_v3_storage_search_audit import (
    FOREVER, add_other_plan, free, storage_occupied, tiny,
)
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, InFlight, Leg, Node, Reservation, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    ReplayRegionalFactory, capture_routing_cache, restore_routing_cache, routing_cache_state,
)
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.storage_contracts import StorageProgress
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
from scripts.experiments.ics_circulation_v3.storage_terminal_screen import (
    StorageTerminalScreenFactory, StorageTerminalScreenGenerator, install_storage_terminal_screen,
)

AUDIT_COUNTERS = defaultdict(int)


def fixture(mode="storage", capacity=1, *, release=2):
    case = tiny(release=release)
    case.state.network.nodes["D"] = replace(case.state.network.nodes["D"], capacity=capacity)
    if mode == "ordinary":
        bag = case.state.bags["b"]
        case.state.bags["b"] = Bag(bag.bag_id, bag.origin, bag.destination,
                                    bag.arrival, bag.deadline, bag.protected)
    elif mode == "empty":
        case.state.bags.clear()
        case.state.trays["t"] = Tray("t", "A")
    return case


def block_final(case, start, end=FOREVER, owner="other"):
    """Complete peer itinerary: arrive D, stay [start,end), then leave if finite."""
    state = case.state
    origin = "D" if start == 0 else "X-" + owner
    state.network.nodes["P-" + owner] = Node("P-" + owner, "z", "p")
    legs = []
    if start:
        state.network.nodes[origin] = Node(origin, "z", "p")
        state.network.edges["enter-" + owner] = Edge("enter-" + owner, origin, "D", 1)
        legs.append(Leg("enter-" + owner, start - 1, start))
    if end < FOREVER:
        state.network.edges["leave-" + owner] = Edge("leave-" + owner, "D", "P-" + owner, 1)
        legs.append(Leg("leave-" + owner, end, end + 1))
    add_other_plan(case, owner, origin, tuple(legs))


def exact_has_route(case, mode, horizon):
    """Exhaust one-tick waits and edge travel in an explicit finite domain."""
    AUDIT_COUNTERS["oracle_calls"] += 1
    state, visited = case.state, mode != "storage"
    progress = state.storage_progress.get("b")
    visited |= progress is not None and progress.arrived_at is not None
    start = state.trays["t"].node
    queue, seen = deque([(start, state.now, visited)]), set()
    bag = state.bags.get("b")
    while queue:
        node, tick, passed = queue.popleft()
        if (node, tick, passed) in seen:
            continue
        seen.add((node, tick, passed))
        AUDIT_COUNTERS["oracle_exact_states"] += 1
        if node == "D" and passed:
            unload = tick + (state.module.unload_ticks if bag else 0)
            usable = unload + state.module.hold_ticks("D")
            if (state.network.nodes[node].can_wait
                    and (bag is None or not bag.protected or unload <= bag.deadline)
                    and free(case, "node:D", tick, FOREVER)
                    and free(case, "reception:D", tick, usable)):
                return True
        if tick >= state.now + horizon:
            continue
        if state.network.nodes[node].can_wait and free(case, "node:" + node, tick, tick + 1):
            queue.append((node, tick + 1, passed))
        if mode == "storage" and node == "E" and tick < bag.storage.release_at:
            continue
        for edge in state.network.edges.values():
            if edge.source != node or edge.capacity <= 0:
                continue
            arrive = tick + edge.travel_time
            if arrive <= state.now + horizon and free(case, "edge:" + edge.edge_id, tick, arrive):
                queue.append((edge.target, arrive, passed or edge.target == "E"))
    return False


def planner(horizon=8, budget=10000):
    return StorageCandidateGenerator(RegionalCandidateGenerator(
        horizon=horizon, expansion_limit=budget, deadline_ms=None, dynamic_local=True,
        cache_contract="isolated_replay_v1"))


def call(generator, state, mode="storage", k=3):
    AUDIT_COUNTERS["production_queries"] += 1
    if mode == "empty":
        return generator.generate_empty(state, "t", "D", k)
    return generator.generate(state, "b", "t", k)


def compare(case, mode="storage", *, horizon=8, k=3, max_records=200000):
    original = planner(horizon)
    screen = StorageTerminalScreenGenerator(planner(horizon), max_records=max_records)
    before = asdict(case.state)
    expected, actual = call(original, case.state, mode, k), call(screen, case.state, mode, k)
    assert actual == expected
    assert asdict(case.state) == before
    exact = exact_has_route(case, mode, horizon)
    assert bool(actual) == exact
    cert = screen.last_diagnostics["terminal_screen"]
    assert cert["screen_work"] == sum(cert.get("work_by_stage", {}).values())
    if cert["certified"]:
        assert not exact
        assert screen.last_expansions == 0
        assert not screen.inner.generator._owned_topology_cache.entries
        tick = cert["conflict_at"]
        assert tick >= case.state.now + horizon
        owners = {owner for resource, start, end, owner in case.calendar
                  if resource == "node:D" and start <= tick < end and owner != "t"}
        assert len(owners) == cert["other_occupancy"] >= case.state.network.nodes["D"].capacity
        assert {slot["tray_id"] for slot in cert["witness_slots"]} == owners
    else:
        assert screen.last_expansions == original.last_expansions
        assert screen.last_search_status == original.last_search_status
        assert screen.last_diagnostics["work_units_by_stage"] == original.last_diagnostics["work_units_by_stage"]
    return screen


@pytest.mark.parametrize("mode,capacity,interval", tuple(product(
    ("ordinary", "storage", "empty"), (1, 2),
    (None, (0, 7), (0, 8), (0, 9), (0, FOREVER), (7, 8), (8, 9), (12, FOREVER)))))
def test_full_witness_half_open_capacity_matrix(mode, capacity, interval):
    case = fixture(mode, capacity)
    if interval:
        block_final(case, *interval)
    screen = compare(case, mode)
    expected_certificate = bool(interval and capacity == 1 and interval[1] > 8)
    assert screen.last_diagnostics["terminal_screen"]["certified"] == expected_certificate


@pytest.mark.parametrize("overlap", (False, True))
def test_multi_capacity_distinct_owners_and_duplicate_descriptions(overlap):
    case = fixture(capacity=2)
    block_final(case, 0, 9, "first")
    block_final(case, 8 if overlap else 9, FOREVER, "second")
    # Duplicate published descriptions of one actual carrier do not create stock.
    case.state.reservations += tuple(case.state.reservations)
    screen = compare(case)
    assert screen.last_diagnostics["terminal_screen"]["certified"] is overlap


def test_query_carrier_terminal_presence_is_excluded():
    case = fixture()
    case.state.trays["t"] = Tray("t", "D", "loaded", "b")
    contract = case.state.bags["b"].storage
    case.state.bags["b"] = replace(case.state.bags["b"], storage=replace(contract, release_at=0))
    case.state.storage_progress["b"] = StorageProgress("t", case.state.bags["b"].storage, 0, 0)
    case.state.reservations = (Reservation("node:D", 0, FOREVER, "t"),)
    assert call(StorageTerminalScreenGenerator(planner()), case.state)


@pytest.mark.parametrize("release", (0, 3, 8, 9))
def test_full_storage_does_not_certify_destination_or_preclude_zero_dwell(release):
    case = fixture(capacity=2, release=release)
    storage_occupied(case, 12)
    case.state.network.nodes["A"] = replace(case.state.network.nodes["A"], can_wait=True)
    screen = compare(case, horizon=12)
    assert not screen.last_diagnostics["terminal_screen"]["certified"]
    assert screen.accounting.rows[-1]["options"]
    for candidate in screen.accounting.rows[-1]["options"]:
        enter = next(leg for leg in candidate.legs if case.state.network.edges[leg.edge_id].target == "E")
        leave = next(leg for leg in candidate.legs if case.state.network.edges[leg.edge_id].source == "E")
        assert enter.arrive == leave.depart >= release


@pytest.mark.parametrize("protected,deadline,hold", tuple(product((False, True), (3, 4), (0, 3))))
def test_reception_and_protection_still_belong_to_complete_delegate(protected, deadline, hold):
    case = fixture()
    case.state.bags["b"] = replace(case.state.bags["b"], protected=protected, deadline=deadline)
    case.state.module = replace(case.state.module, hold_by_node={"D": hold})
    compare(case)


def test_record_budget_unknown_delegates_unchanged_candidates():
    case = fixture()
    block_final(case, 0)
    screen = compare(case, max_records=1)
    assert screen.last_diagnostics["terminal_screen"]["status"] == "screen_record_budget_unknown_delegate"
    assert screen.last_expansions > 0


@pytest.mark.parametrize("mode", ("ordinary", "storage", "empty"))
def test_zero_final_capacity_is_a_direct_physical_impossibility(mode):
    assert compare(fixture(mode, capacity=0), mode).last_diagnostics["terminal_screen"]["certified"]


@pytest.mark.parametrize("k", (0, -1, True))
def test_invalid_k_keeps_original_full_result_and_diagnosis(k):
    case = fixture()
    block_final(case, 0)
    original, screen = planner(), StorageTerminalScreenGenerator(planner())
    assert call(screen, case.state, k=k) == call(original, case.state, k=k)
    assert screen.last_search_status == original.last_search_status
    assert screen.last_diagnostics["terminal_screen"]["status"] == "invalid_request_delegate"


def test_implicit_k_preserves_storage_delegate_default():
    case = fixture(capacity=3)
    for i in range(3):
        node = "N" + str(i)
        case.state.network.nodes[node] = Node(node, "z", "p")
        case.state.network.edges["en" + str(i)] = Edge("en" + str(i), "E", node, 1)
        case.state.network.edges["nd" + str(i)] = Edge("nd" + str(i), node, "D", 1)
    original, screened = planner(), StorageTerminalScreenGenerator(planner())
    AUDIT_COUNTERS["production_queries"] += 3
    assert len(original.generate(case.state, "b", "t", 4)) == 4
    expected = original.generate(case.state, "b", "t")
    assert len(expected) == 3
    assert screened.generate(case.state, "b", "t") == expected


@pytest.mark.parametrize("mutation", ("unknown_tray", "future_bag", "completed", "unavailable", "old_flight",
    "bad_policy", "bad_time", "unknown_storage", "progress_owner", "future_progress", "missing_ingress"))
def test_invalid_requests_keep_original_diagnosis_even_if_final_is_full(mutation):
    case = fixture()
    state = case.state
    block_final(case, 0)
    if mutation == "unknown_tray":
        state.trays.pop("t")
    elif mutation == "future_bag":
        state.bags["b"] = replace(state.bags["b"], arrival=1)
    elif mutation == "completed":
        state.completed["b"] = 0
    elif mutation == "unavailable":
        state.trays["t"] = replace(state.trays["t"], available_at=1)
    elif mutation == "old_flight":
        state.old_in_transit = (InFlight("t", "ae", 0, 1),)
    elif mutation in ("bad_policy", "bad_time", "unknown_storage"):
        field, value = {"bad_policy": ("carrier_policy", "off_carrier"),
                        "bad_time": ("release_at", True), "unknown_storage": ("node_id", "missing")}[mutation]
        state.bags["b"] = replace(state.bags["b"], storage=replace(state.bags["b"].storage, **{field: value}))
    elif mutation == "missing_ingress":
        state.trays["t"] = replace(state.trays["t"], node="E")
    else:
        state.storage_progress["b"] = StorageProgress("other" if mutation == "progress_owner" else "t",
                                                     state.bags["b"].storage, 1 if mutation == "future_progress" else 0)
    a, b = planner(), StorageTerminalScreenGenerator(planner())
    assert call(a, state) == call(b, state) == ()
    assert b.last_search_status == a.last_search_status
    assert b.last_diagnostics["terminal_screen"]["status"] == "invalid_request_delegate"


def test_old_peer_inflight_terminal_commitment_matches_manual_calendar():
    case = fixture()
    state = case.state
    state.network.nodes["X"] = Node("X", "z", "p")
    state.network.edges["xd"] = Edge("xd", "X", "D", 9)
    state.trays["peer"] = Tray("peer", None)
    state.old_in_transit = (InFlight("peer", "xd", 0, 9),)
    case.calendar.extend((("edge:xd", 0, 9, "peer"), ("node:D", 9, FOREVER, "peer")))
    assert compare(case).last_diagnostics["terminal_screen"]["certified"]


def test_skipped_cache_is_cold_then_calendar_and_graph_changes_requery():
    case = fixture()
    blocked = deepcopy(case)
    block_final(blocked, 0)
    screen = StorageTerminalScreenGenerator(planner())
    assert not call(screen, blocked.state)
    assert not screen.generator._owned_topology_cache.entries
    expected = call(planner(), case.state)
    assert call(screen, case.state) == expected
    full_work = screen.last_expansions
    for budget in range(1, full_work + 2):
        screen.generator.expansion_limit = budget
        cold = planner(budget=budget)
        assert call(screen, case.state) == call(cold, case.state)
        assert screen.last_expansions == cold.last_expansions
        assert screen.last_search_status == cold.last_search_status
    screen.generator.expansion_limit = 10000
    case.state.network.edges["ae"] = replace(case.state.network.edges["ae"], capacity=0)
    assert call(screen, case.state) == call(planner(), case.state) == ()
    case.state.network.edges["ae"] = replace(case.state.network.edges["ae"], capacity=1)
    assert call(screen, case.state) == expected


def factory():
    return ReplayRegionalFactory(12, 10000, 12, True, 3)


def test_checkpoint_factory_and_explicit_cache_preserve_screen_and_sibling_isolation():
    case = fixture(capacity=2)
    engine = Simulation(case.state, generator_factory=factory(), search_horizon=12,
                        reactive_empty_dispatch=False)
    ledger = install_storage_terminal_screen(engine)
    call(engine._generator, engine.state)
    before = routing_cache_state(engine)
    checkpoint, cache = engine.checkpoint(), capture_routing_cache(engine)
    branch, sibling = Simulation.from_checkpoint(checkpoint), Simulation.from_checkpoint(checkpoint)
    assert type(branch._generator) is type(branch._make_generator()) is StorageTerminalScreenGenerator
    assert branch._generator.generator is branch._generator.inner.generator
    assert branch._generator.accounting is not sibling._generator.accounting is not ledger
    call(branch._generator, branch.state)
    assert len(branch._generator.accounting.rows) == 2
    assert len(sibling._generator.accounting.rows) == len(ledger.rows) == 1
    branch._generator.generator._owned_topology_cache.entries.clear()
    assert routing_cache_state(sibling) == before
    restore_routing_cache(branch, cache)
    assert routing_cache_state(branch) == before
    a, b = branch.generator_factory(), branch.generator_factory()
    assert a.accounting is not b.accounting and not a.accounting.rows and not b.accounting.rows
    assert not a.generator._owned_topology_cache.entries and not b.generator._owned_topology_cache.entries
    AUDIT_COUNTERS["physical_runs"] += 2
    actual, restored = engine.advance(10), sibling.advance(10)
    def physical(result):
        value = asdict(result)
        value["policy_stats"] = {name: count for name, count in value["policy_stats"].items()
                                 if not name.endswith("_ms")}
        return value
    assert physical(actual) == physical(restored)
    assert actual.completed == {"b": 4}


@pytest.mark.parametrize("mutation", ("slow", "unknown_factory", "unknown_generator", "repeat"))
def test_installation_rejects_unsupported_without_half_install(mutation):
    engine = Simulation(fixture().state, generator_factory=factory())
    if mutation == "slow":
        engine.slow_controller = object()
    elif mutation == "unknown_factory":
        engine.generator_factory = lambda horizon=None: factory()(horizon)
    elif mutation == "unknown_generator":
        engine._generator = planner().generator
    else:
        install_storage_terminal_screen(engine)
    generator, saved_factory = engine._generator, engine.generator_factory
    with pytest.raises(ValueError):
        install_storage_terminal_screen(engine)
    assert engine._generator is generator and engine.generator_factory is saved_factory


@pytest.mark.parametrize("mutation", ("deadline", "cache", "alias", "limit"))
def test_live_configuration_guard_is_rechecked(mutation):
    screen = StorageTerminalScreenGenerator(planner())
    if mutation == "deadline":
        screen.generator.deadline_ms = 1
    elif mutation == "cache":
        screen.generator.cache_contract = None
    elif mutation == "alias":
        screen.generator = planner().generator
    else:
        screen.max_records = 0
    with pytest.raises(ValueError):
        call(screen, fixture().state)
    assert not screen.accounting.rows


def test_factory_rejects_unknown_or_nested_factory():
    with pytest.raises(ValueError):
        StorageTerminalScreenFactory(lambda horizon=None: factory()(horizon))
    with pytest.raises(ValueError):
        StorageTerminalScreenFactory(StorageTerminalScreenFactory(factory()))


def test_streaming_rows_does_not_reset_cumulative_extra_work():
    case = fixture()
    block_final(case, 0)
    screen = StorageTerminalScreenGenerator(planner())
    call(screen, case.state)
    work = screen.accounting.screen_work
    cpu = screen.accounting.screen_cpu_seconds
    observation = screen.accounting.observation_cpu_seconds
    assert work > 0
    screen.accounting.rows.clear()
    call(screen, case.state)
    assert len(screen.accounting.rows) == 1
    assert screen.accounting.screen_work == 2 * work
    assert screen.accounting.screen_cpu_seconds >= cpu
    assert screen.accounting.observation_cpu_seconds >= observation


def test_base_snapshot_installer_is_explicitly_unsupported():
    source = fixture().state
    ordinary = Snapshot(source.now, source.network, {"t": Tray("t", "A")}, {})
    engine = Simulation(ordinary, generator_factory=factory())
    before = engine._generator, engine.generator_factory
    with pytest.raises(ValueError, match="central storage"):
        install_storage_terminal_screen(engine)
    assert (engine._generator, engine.generator_factory) == before
