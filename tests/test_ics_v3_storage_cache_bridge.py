"""Storage/ordinary cache interaction at observable budget and replay boundaries."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Reservation, Tray
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, clear_static_cache
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    ReplayRegionalFactory, capture_routing_cache, restore_routing_cache, routing_cache_state,
)
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StorageSnapshot, StorageWaypointContract,
)
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator


def state():
    nodes = {n: Node(n, "zone", "owner", capacity=3) for n in ("A", "S", "N", "D")}
    edges = {e.edge_id: e for e in (Edge("AS", "A", "S", 1), Edge("SD", "S", "D", 1),
             Edge("SN", "S", "N", 1), Edge("ND", "N", "D", 1), Edge("DA", "D", "A", 1))}
    bag = StorageBag("b", "A", "D", 0, 20, True, StorageWaypointContract("S", 4, 0))
    return StorageSnapshot(0, Network(nodes, edges), {"t": Tray("t", "A", "loaded", "b")}, {"b": bag})


def planner(budget=10000):
    return StorageCandidateGenerator(RegionalCandidateGenerator(
        horizon=20, expansion_limit=budget, deadline_ms=None, dynamic_local=True,
        cache_contract="isolated_replay_v1"))


def query(generator, snapshot, mode="storage", k=2):
    value = deepcopy(snapshot)
    if mode == "ordinary":
        b = value.bags["b"]
        value.bags["b"] = Bag(b.bag_id, b.origin, b.destination, b.arrival, b.deadline, b.protected)
    if mode == "empty":
        value.bags.clear()
        value.trays["t"] = Tray("t", "A")
        candidates = generator.generate_empty(value, "t", "D", k)
    else:
        candidates = generator.generate(value, "b", "t", k)
    assert all(ExecutionValidator().validate(value, c).accepted for c in candidates)
    return {"candidates": tuple(asdict(c) for c in candidates),
            "status": generator.last_search_status, "work": generator.last_expansions,
            "stages": deepcopy(generator.last_diagnostics["work_units_by_stage"])}


@pytest.mark.parametrize("warm_mode", ["ordinary", "empty", "storage"])
def test_mixed_query_warmth_preserves_every_storage_budget_cutoff(warm_mode):
    snapshot = state()
    warm = planner()
    query(warm, snapshot, warm_mode)
    full = query(warm, snapshot)
    assert len(full["candidates"]) == 2
    for budget in range(1, full["work"] + 2):
        warm.generator.expansion_limit = budget
        assert query(warm, snapshot) == query(planner(budget), snapshot), (warm_mode, budget)
    accounting = warm.last_diagnostics["cache_accounting"]
    assert sum(accounting["reused_preprocessing_work"].values()) > 0
    assert not accounting["actual_preprocessing_work"]


@pytest.mark.parametrize("mode", ["ordinary", "empty"])
def test_storage_warmth_preserves_every_delegate_budget_cutoff(mode):
    snapshot = state()
    warm = planner()
    query(warm, snapshot)
    full = query(warm, snapshot, mode)
    assert full["candidates"]
    for budget in range(1, full["work"] + 2):
        warm.generator.expansion_limit = budget
        assert query(warm, snapshot, mode) == query(planner(budget), snapshot, mode), (mode, budget)


def test_static_unreachable_is_not_reused_after_graph_change():
    snapshot = state()
    snapshot.network.edges["AS"] = replace(snapshot.network.edges["AS"], capacity=0)
    warm = planner()
    impossible = query(warm, snapshot)
    assert impossible["status"] == "static_unreachable" and not impossible["candidates"]
    assert query(warm, snapshot) == impossible
    assert warm.last_diagnostics["cache_accounting"]["reused_preprocessing_work"]
    snapshot.network.edges["AS"] = replace(snapshot.network.edges["AS"], capacity=1)
    possible = query(warm, snapshot)
    assert possible["candidates"] and possible == query(planner(), snapshot)


def test_calendars_release_and_budget_unknown_never_become_static_cached_verdicts():
    snapshot = state()
    warm = planner(1)
    assert query(warm, snapshot)["status"] == "expansion_budget_exhausted"
    assert not warm.generator._owned_topology_cache.entries
    warm.generator.expansion_limit = 10000
    first = query(warm, snapshot)
    assert first["candidates"]
    snapshot.bags["b"] = replace(snapshot.bags["b"], storage=StorageWaypointContract("S", 9, 0))
    changed = query(warm, snapshot)
    assert changed == query(planner(), snapshot) and changed["candidates"] != first["candidates"]
    snapshot.network.nodes["X"] = Node("X", "zone", "owner")
    snapshot.trays["blocker"] = Tray("blocker", "X")
    snapshot.reservations = [Reservation("edge:SD", 0, 14, "blocker")]
    occupied = query(warm, snapshot)
    assert occupied == query(planner(), snapshot)
    snapshot.reservations.clear()
    assert query(warm, snapshot) == query(planner(), snapshot)


def test_storage_cache_is_visible_in_engine_checkpoint_and_explicit_restore():
    factory = ReplayRegionalFactory(horizon=20, expansion_limit=10000, static_path_limit=12,
                                    dynamic_local=True, local_label_limit=3)
    engine = Simulation(state(), generator_factory=factory, reactive_empty_dispatch=False)
    expected = query(engine._generator, engine.state)
    warm = routing_cache_state(engine)
    assert warm["fast_cache"]["entries_lru_oldest_first"]
    goals = {row["goal"] for entry in warm["fast_cache"]["entries_lru_oldest_first"] for row in entry["lower"]}
    assert goals >= {"S", "D"}
    checkpoint = engine.checkpoint()
    explicit = capture_routing_cache(engine)
    branch = Simulation.from_checkpoint(checkpoint)
    sibling = Simulation.from_checkpoint(checkpoint)
    engine._generator.generator._owned_topology_cache.entries.clear()
    assert routing_cache_state(branch) == routing_cache_state(sibling) == warm
    assert query(branch._generator, branch.state) == expected
    branch._generator.generator._owned_topology_cache.entries.clear()
    clear_static_cache()
    assert routing_cache_state(sibling) == warm
    restore_routing_cache(engine, explicit)
    assert routing_cache_state(engine) == warm
    engine._generator.generator._owned_topology_cache.entries.clear()
    restore_routing_cache(engine, explicit)
    assert routing_cache_state(engine) == warm
    assert not factory()._owned_topology_cache.entries


def test_storage_cache_rejects_runtime_wall_deadline_mutation():
    warm = planner()
    query(warm, state())
    warm.generator.deadline_ms = 1
    with pytest.raises(ValueError, match="deadline_ms=None"):
        query(warm, state())
