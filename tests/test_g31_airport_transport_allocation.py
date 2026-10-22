"""Risk-targeted station-flow gates; no native sessions or future jobs."""
from collections import Counter
import itertools
import random

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_graph as graph_module
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_allocation as flow
from test_g31_airport_inventory_rule import observation, snapshot
from test_g31_foundation_airport_joint_projection import fixture, forecast, add_request


def prepare(obs, demand=None):
    obs["observation_scope"] = "controller_policy"
    obs.pop("control_projection", None)  # full current job list in these small fixtures
    current = joint.prepare_current(obs, r0.r0_priority_planner(obs), message_delay=2.)
    catalog = joint.build_joint_catalog(current)
    graph = graph_module.build_terminal_graph(current, catalog=catalog)
    offers = flow.build_supply_offers(current, catalog)
    projected = projection.prepare_inventory_projection(obs, forecast=demand, prepared_current=current)
    values = flow.build_marginal_values(projected, offers, graph["receiver_contract"])
    return graph, offers, values


def solve(obs, demand=None):
    return flow.solve_optional_transport(*prepare(obs, demand))


def test_optional_supply_has_hold_but_ordinary_returns_are_protected():
    optional = solve(observation(source=1, stock=3))
    assert optional["chosen"] == []
    assert optional["hold_quantity"] == 2
    ordinary = solve(observation(source=0, stock=2))
    assert len(ordinary["chosen"]) == 2
    assert all(row["source_category"] == "ordinary_return" for row in ordinary["chosen"])


def test_source_ceiling_preserves_loader_floor_across_joint_quantity():
    obs = fixture((0, 4, 0))
    result = solve(obs, forecast(obs, {2: [10.]+[0.]*29}))
    assert len(result["chosen"]) == 3
    assert len({row["tray_id"] for row in result["chosen"]}) == 3
    assert [row["submit_at"] for row in result["dispatch_profile"]] == [10., 70., 130.]
    assert [row["earliest_departure"] for row in result["dispatch_profile"]] == [12., 72., 132.]
    assert result["later_slots_require_replanning"]


def test_receiver_space_and_diminishing_benefit_limit_quantity():
    obs = fixture((0, 4, 0))
    obs["node_contracts"][2]["capacity"] = 1
    result = solve(obs, forecast(obs, {2: [10.]+[0.]*29}))
    assert len(result["chosen"]) == 1
    assert result["hold_quantity"] == 2
    obs["node_contracts"][2]["capacity"] = 10
    result = solve(obs, forecast(obs, {2: [.8]+[0.]*29}))
    assert len(result["chosen"]) == 1  # fractional bin mass is never rounded per-bin
    assert result["hold_quantity"] == 2


def test_source_opportunity_can_select_farther_source():
    obs = fixture((2, 2, 0))
    obs["edge_records"] = [(a, b, 1. if a == 0 else 10., 1.)
        for a in range(3) for b in range(3) if a != b]
    demand = forecast(obs, {0: [2.]+[0.]*29, 2: [1.]+[0.]*29})
    result = solve(obs, demand)
    assert [(row["source"], row["destination"]) for row in result["chosen"]] == [(1, 2)]
    assert result["hold_by_source"][0] == 1


def test_direction_closures_and_complete_service_are_not_duplicated():
    obs = observation()
    obs["node_records"] = [(0, 10, 2., 0, 0, [1]), (1, 10, 3., 0, 0, [2]), (2, 10, 4., 0, 0, [])]
    obs["edge_records"] = [(0, 1, 5., 1.), (1, 2, 7., 1.)]
    obs["edge_contracts"] = [{"from": 0, "to": 1, "capacity": 1}, {"from": 1, "to": 2, "capacity": 1}]
    graph, _, _ = prepare(obs)
    arcs = {(r["source_terminal"], r["destination_terminal"]): r for r in graph["arcs"]}
    assert (2, 0) not in arcs
    assert arcs[0, 2]["static_complete_seconds"] == 21.
    assert arcs[0, 2]["static_transport_seconds"] == 12.
    assert arcs[0, 2]["static_service_seconds"] == 9.
    old_version = graph["topology_version"]
    obs["edge_contracts"][1]["capacity"] = 0
    graph, _, _ = prepare(obs)
    assert old_version != graph["topology_version"]
    assert not any(r["destination_terminal"] == 2 for r in graph["arcs"])


def test_unknown_or_expired_receiver_never_becomes_zero_inventory():
    obs = observation(source=1, stock=2, remote=True)
    obs["planning_snapshots"] = [snapshot(expiry=10.)]
    graph, offers, values = prepare(obs)
    assert not graph["receiver_contract"][2]["known"]
    assert graph["receiver_contract"][2]["current_space"] is None
    assert graph["receiver_contract"][2]["available_slots"] == 0
    assert values["receiver_known"][2] is False
    assert flow.solve_optional_transport(graph, offers, values)["hold_quantity"] == 1


def test_received_commitment_is_not_subtracted_twice_from_space():
    obs = fixture((0, 2, 1))
    add_request(obs, identity="T2-0", status="received", received_at=8.)
    graph, _, _ = prepare(obs)
    assert graph["receiver_contract"][2]["unrepresented_committed_or_pending"] == 0
    assert graph["receiver_contract"][2]["available_slots"] == 9


def test_conditional_future_release_is_not_current_supply():
    obs = observation(source=1, stock=3)
    obs["trays"][2].update(mode="unloading", available_at=250., business_bag_id="inflight")
    obs["node_contracts"][1]["actual_available"] = 2
    _, offers, _ = prepare(obs)
    assert "E2" not in offers["trays"]
    assert offers["total_source_cap"] == 1


def test_protected_returns_precede_optional_dispatch_and_share_receiver_space():
    obs = fixture((1, 3, 0))
    obs["static_role_contract"]["loader_nodes"] = [1, 2]
    obs["node_contracts"][2]["capacity"] = 1
    result = solve(obs, forecast(obs, {2: [5.]+[0.]*29}))
    assert result["chosen"][0]["source"] == 0
    assert sum(row["destination"] == 2 for row in result["chosen"]) == 1
    assert result["hold_quantity"] == 2


def test_conservative_monotone_approximation_reports_error():
    costs, costs_audit = flow._monotone([2., 1., 3.], increasing=True)
    gains, gains_audit = flow._monotone([4., 5., 2.], increasing=False)
    assert costs == [2., 2., 3.] and gains == [4., 4., 2.]
    assert costs_audit["absolute_error_sum"] == gains_audit["absolute_error_sum"] == 1.


def test_residual_reverse_arcs_reassign_an_earlier_good_match():
    # A -> X costs -10, A -> Y costs -9; B -> X costs -8. Greedy
    # A -> X strands B. The second residual augment must reroute A to Y.
    network = flow._ResidualFlow()
    start, a, b, x, y, end = [network.node() for _ in range(6)]
    for target in (a, b):
        network.edge(start, target, 1, 0.)
        network.edge(target, end, 1, 0.)
    ax = network.edge(a, x, 1, -10.)
    ay = network.edge(a, y, 1, -9.)
    bx = network.edge(b, x, 1, -8.)
    for source in (x, y):
        network.edge(source, end, 1, 0.)
    sent, cost = network.solve(start, end, 2)
    assert sent == 2 and cost == -17.
    assert ax[2] == 1 and ay[2] == bx[2] == 0


def test_per_tray_destination_eligibility_survives_station_aggregation():
    obs = observation(source=0, stock=2)
    graph, offers, values = prepare(obs)
    offers["trays"]["E0"]["legal_actions"] = [r for r in offers["trays"]["E0"]["legal_actions"] if r["destination"] == 1]
    offers["trays"]["E1"]["legal_actions"] = [r for r in offers["trays"]["E1"]["legal_actions"] if r["destination"] == 2]
    graph["receiver_contract"][1]["available_slots"] = 1
    graph["receiver_contract"][2]["available_slots"] = 1
    result = flow.solve_optional_transport(graph, offers, values)
    assert {(r["tray_id"], r["destination"]) for r in result["chosen"]} == {("E0", 1), ("E1", 2)}


def test_shared_witness_bottleneck_is_diagnostic_not_independent_capacity():
    obs = observation(source=0, stock=2)
    result = solve(obs)
    assert any(r["planned_crossings"] == 2 for r in result["shared_witness_edges"])
    assert result["native_execution_authority"] is False


def test_config_is_explicit_and_rejects_hidden_or_inconsistent_parameters():
    with pytest.raises(ValueError, match="unknown_config"):
        flow.allocation_config({"hidden_weight": 1.})
    graph, offers, values = prepare(observation())
    with pytest.raises(ValueError, match="marginal_config_mismatch"):
        flow.solve_optional_transport(graph, offers, values, {"command_delay_seconds": 3.})


def test_small_integer_solver_matches_exhaustive_eligible_allocations():
    rng = random.Random(3121)
    config = flow.allocation_config()
    for case in range(30):
        common = {"public_state_digest": "test", "catalog_id": "test", "now": 10.}
        offers = {**common, "sources": {}, "trays": {}, "total_source_cap": 0}
        graph = {**common, "receiver_contract": {}, "arcs": []}
        values = {**common, "source_marginals": {}, "receiver_marginals": {},
            "source_known": {0: True, 1: True}, "receiver_known": {2: True, 3: True}, "config": config}
        for destination in (2, 3):
            cap = rng.randint(1, 3)
            graph["receiver_contract"][destination] = {"available_slots": cap}
            values["receiver_marginals"][destination] = sorted([rng.random()*10 for _ in range(cap)], reverse=True)
        for source in (0, 1):
            cap = rng.randint(1, 2)
            offers["sources"][source] = {"source_cap": cap, "source_category": "loader_optional", "tray_ids": []}
            offers["total_source_cap"] += cap
            values["source_marginals"][source] = sorted([rng.random()*4 for _ in range(cap)])
            for destination in (2, 3):
                graph["arcs"].append({"source_terminal": source, "destination_terminal": destination,
                    "physical_edges": [[source, destination]]})
            for index in range(2):
                tray_id = f"{source}-{index}"
                actions = []
                for destination in (2, 3):
                    if rng.random() < .25:
                        continue
                    actions.append({"action_id": f"{case}:{tray_id}:{destination}", "tray_id": tray_id,
                        "source": source, "destination": destination, "owner_id": "A",
                        "source_category": "loader_optional", "earliest_departure": 12.,
                        "static_travel_time": rng.random()*150.})
                offers["trays"][tray_id] = {"legal_actions": actions}
                offers["sources"][source]["tray_ids"].append(tray_id)
        optimum = 0.
        for combination in itertools.product(*[[None]+r["legal_actions"] for r in offers["trays"].values()]):
            chosen = [r for r in combination if r is not None]
            sources, destinations = Counter(r["source"] for r in chosen), Counter(r["destination"] for r in chosen)
            if any(n > offers["sources"][s]["source_cap"] for s, n in sources.items()):
                continue
            if any(n > graph["receiver_contract"][d]["available_slots"] for d, n in destinations.items()):
                continue
            cost = sum(sum(values["source_marginals"][s][:n]) for s, n in sources.items())
            cost -= sum(sum(values["receiver_marginals"][d][:n]) for d, n in destinations.items())
            cost += sum(flow.transport_cost(r) for r in chosen)
            optimum = min(optimum, cost)
        actual = flow.solve_optional_transport(graph, offers, values)
        assert actual["objective"]["optional_cost"] == pytest.approx(optimum)
        assert actual["hold_quantity"]+len(actual["chosen"]) == offers["total_source_cap"]



