"""Exact existing-path oracle, causal invalidation and bounded retention."""
import copy
import random
import pytest
from scripts.experiments.g31_ics_circulation.analytic_control import PublicTravel
from scripts.experiments.g31_ics_circulation.public_travel_pool import PublicTravelPool


def observation():
    return {"owner_id": "A", "now": 0., "node_records": [[i, 0, .1 + i / 10] for i in range(8)],
            "edge_records": [[i, (i + 1) % 8, 1., 2.] for i in range(8)] + [[0, 4, 2., 2.], [4, 0, 2., 2.]],
            "edge_contracts": [], "known_faults": []}


def compare_all(pool, data, seed):
    cached = pool.checkout(data)
    pairs = [(i, j) for i in range(8) for j in range(8)]
    random.Random(seed).shuffle(pairs)
    # A fresh object for every pair tests independence from all preceding
    # queries, including query order retained across earlier checkouts.
    for a, b in pairs:
        oracle = PublicTravel(data)
        assert cached.path(a, b) == oracle.path(a, b)
        assert cached.complete(a, b) == oracle.complete(a, b)


def test_all_pairs_exact_across_permuted_query_orders_and_public_updates():
    pool, data = PublicTravelPool(3), observation()
    for seed in range(12):
        data["owner_id"] = str(seed % 2)
        compare_all(pool, data, seed)
        data["now"] += 3.
        data["jobs"] = [{"arrival": data["now"], "id": str(seed)}]
    assert pool.misses == 2 and pool.hits == 10
    assert len(pool._graphs) == 2


def test_identical_owner_graphs_never_share_search_or_pair_state():
    pool, data = PublicTravelPool(), observation()
    first = pool.checkout(data)
    first.path(0, 5)
    a_graph = next(iter(pool._graphs.values()))
    data["owner_id"] = "B"
    pool.checkout(data)
    b_graph = next(reversed(pool._graphs.values()))
    assert a_graph is not b_graph
    assert a_graph.cache and not b_graph.cache and not b_graph._source_searches
    data["owner_id"] = "A"
    assert pool.checkout(data).path(0, 5) == first.path(0, 5)
    assert pool.hits == 1 and pool.misses == 2


@pytest.mark.parametrize("owner", [None, "", 0, False, []])
def test_missing_or_invalid_owner_cannot_enter_shared_cache(owner):
    pool, data = PublicTravelPool(), observation()
    data["owner_id"] = owner
    with pytest.raises(ValueError, match="declared_owner_required"):
        pool.checkout(data)
    assert not pool._graphs and pool.hits == pool.misses == 0


@pytest.mark.parametrize("change", ["service", "length", "speed", "zero_capacity", "negative_capacity", "fault", "edge_order"])
def test_every_consumed_graph_change_invalidates_and_preserves_oracle(change):
    pool, data = PublicTravelPool(), observation()
    compare_all(pool, data, 1)
    if change == "service": data["node_records"][2][2] += 20
    elif change == "length": data["edge_records"][1][2] += 20
    elif change == "speed": data["edge_records"][1][3] = .01
    elif change in ("zero_capacity", "negative_capacity"):
        data["edge_contracts"] = [{"from": 0, "to": 1, "capacity": 0 if change == "zero_capacity" else -1}]
    elif change == "fault": data["known_faults"] = [{"from": 0, "to": 1, "active": True}]
    else: data["edge_records"].reverse()
    compare_all(pool, data, 2)
    assert pool.misses == 2


def test_fault_time_boundaries_and_explicit_active_override_are_exact():
    pool, data = PublicTravelPool(), observation()
    data["known_faults"] = [{"from": 0, "to": 1, "start": 2., "end": 4.}]
    for at in (0., 2., 3., 4., 2., 4.):
        data["now"] = at
        compare_all(pool, data, int(at))
    assert pool.misses == 2
    data["known_faults"][0]["active"] = True
    data["now"] = 100.
    compare_all(pool, data, 7)
    assert pool.misses == 2


def test_caller_cannot_corrupt_another_checkout_or_input():
    pool, data = PublicTravelPool(), observation()
    before = copy.deepcopy(data)
    one = pool.checkout(data)
    one.service[1] = 1000.
    one.edge_time[0, 1] = 1000.
    two = pool.checkout(data)
    assert two.service == PublicTravel(data).service
    assert two.edge_time == PublicTravel(data).edge_time
    assert data == before


def test_lru_bounds_graph_count_and_eviction_does_not_change_old_views():
    pool, data = PublicTravelPool(2), observation()
    old = pool.checkout(data)
    expected = old.path(0, 5)
    for i in range(20):
        data["node_records"][0][2] += .1
        compare_all(pool, data, i)
        assert len(pool._graphs) <= 2
    assert old.path(0, 5) == expected


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_capacity_fails_closed(capacity):
    with pytest.raises(ValueError, match="positive_integer"):
        PublicTravelPool(capacity)


@pytest.mark.parametrize("pair", [(0, 999), (999, 0)])
def test_undeclared_queries_cannot_grow_cached_state(pair):
    pool = PublicTravelPool()
    view = pool.checkout(observation())
    with pytest.raises(ValueError, match="undeclared_node"):
        view.path(*pair)
