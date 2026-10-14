"""Legality and bounded-search semantics for the isolated regional planner."""
from dataclasses import replace

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Network, Node, Reservation, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, ExecutionValidator
from scripts.experiments.ics_circulation_v3.scenarios import pilot_scenes


def small_state(*, can_wait=True):
    network = Network({"A": Node("A", "z", "r0"),
                       "J": Node("J", "z", "r1", can_wait=can_wait),
                       "B": Node("B", "z", "r2")},
                      {edge.edge_id: edge for edge in (
                          Edge("A-J", "A", "J", 1), Edge("J-B", "J", "B", 2),
                          Edge("A-B", "A", "B", 5))})
    bag = Bag("bag", "A", "B", 0, 30)
    return Snapshot(0, network, {"tray": Tray("tray", "A", "loaded", "bag")}, {"bag": bag})


def test_all_pilot_initializations_match_reference_static_paths_and_are_legal():
    # Equal physical candidates on this tiny known fixture, not a completeness
    # claim for all graphs (the macro summaries retain one local witness).
    for scene in pilot_scenes():
        regional = RegionalCandidateGenerator(horizon=48, deadline_ms=None)
        proposals = regional.generate(scene.state, scene.target_bag_id, scene.target_tray_id)
        reference = CandidateGenerator(horizon=48).generate(scene.state, scene.target_bag_id, scene.target_tray_id)
        assert {tuple(leg.edge_id for leg in row.legs) for row in proposals} == {
            tuple(leg.edge_id for leg in row.legs) for row in reference}
        assert len(proposals) == 3
        assert all(ExecutionValidator().validate(scene.state, row).accepted for row in proposals)
        assert proposals[0].is_baseline and proposals[0].baseline_id == proposals[0].candidate_id
        assert len({row.candidate_id for row in proposals}) == len(proposals)


def test_no_wait_junction_retains_time_label_and_delays_at_upstream_portal():
    state = small_state(can_wait=False)
    state.trays["blocker"] = Tray("blocker", "B")
    state.reservations = (Reservation("edge:J-B", 0, 3, "blocker"),)
    proposals = RegionalCandidateGenerator(horizon=20, deadline_ms=None).generate(state, "bag", "tray", 2)
    via_j = next(row for row in proposals if len(row.legs) == 2)
    assert via_j.legs[0].depart == 2
    assert via_j.legs[0].arrive == via_j.legs[1].depart == 3
    assert ExecutionValidator().validate(state, via_j).accepted


def test_reception_window_moves_arrival_and_preserves_module_response():
    state = small_state()
    state.module = FixedLocalModule(unload_ticks=2, hold_by_node={"B": 4}, reception_capacity=1)
    state.trays["holding"] = Tray("holding", "B", "holding", available_at=8)
    proposals = RegionalCandidateGenerator(horizon=30, deadline_ms=None).generate(state, "bag", "tray", 1)
    assert len(proposals) == 1
    assert proposals[0].legs[-1].arrive >= 8
    assert proposals[0].unload_complete == proposals[0].legs[-1].arrive + 2
    assert proposals[0].usable_at == proposals[0].unload_complete + 4
    assert ExecutionValidator().validate(state, proposals[0]).accepted


def test_budget_and_bounded_failure_do_not_claim_physical_infeasibility():
    state = small_state()
    limited = RegionalCandidateGenerator(horizon=20, expansion_limit=1, deadline_ms=None)
    assert limited.generate(state, "bag", "tray") == ()
    assert limited.last_search_status == "expansion_budget_exhausted"
    blocked = state.clone()
    blocked.trays["resident"] = Tray("resident", "B")
    blocked.network.nodes["B"] = replace(blocked.network.nodes["B"], capacity=1)
    generator = RegionalCandidateGenerator(horizon=20, deadline_ms=None)
    assert generator.generate(blocked, "bag", "tray") == ()
    assert generator.last_search_status == "bounded_no_candidate"
    assert generator.last_diagnostics["missing_candidate_is_not_infeasibility"]


def test_deadline_is_a_hard_business_check_and_timing_budget_is_distinct():
    state = small_state()
    state.bags["bag"] = replace(state.bags["bag"], protected=True, deadline=3)
    planner = RegionalCandidateGenerator(horizon=20, deadline_ms=None)
    assert planner.generate(state, "bag", "tray") == ()
    assert planner.last_search_status == "bounded_no_candidate"
    budget = RegionalCandidateGenerator(horizon=20, deadline_ms=1e-12)
    assert budget.generate(state, "bag", "tray") == ()
    assert budget.last_search_status == "deadline_exhausted"


def test_static_unreachable_is_separate_and_graph_cache_follows_changed_content():
    state = small_state()
    planner = RegionalCandidateGenerator(horizon=20, deadline_ms=None)
    assert planner.generate(state, "bag", "tray", 1)[0].legs[-1].arrive == 3
    state.network.edges["J-B"] = replace(state.network.edges["J-B"], travel_time=20)
    assert planner.generate(state, "bag", "tray", 1)[0].legs[-1].arrive == 5
    state.network.edges.clear()
    assert planner.generate(state, "bag", "tray") == ()
    assert planner.last_search_status == "static_unreachable"


def test_empty_api_and_commit_still_use_original_authority():
    state = small_state()
    state.trays["tray"] = Tray("tray", "A")
    state.bags.clear()
    planner = RegionalCandidateGenerator(horizon=20, deadline_ms=None)
    proposals = planner.generate_empty(state, "tray", "B")
    assert len(proposals) == 1 and proposals[0].bag_id is None
    authority = ExecutionValidator()
    assert authority.commit(state, proposals[0]).accepted
    assert authority.commit(state, proposals[0]).reason == "stale_version"


def test_same_partition_can_collapse_a_long_chain_with_static_witness():
    nodes = {str(index): Node(str(index), "z", "one_region") for index in range(20)}
    edges = {str(index): Edge(str(index), str(index), str(index + 1), 1) for index in range(19)}
    bag = Bag("bag", "0", "19", 0, 30)
    state = Snapshot(0, Network(nodes, edges), {"tray": Tray("tray", "0", "loaded", "bag")}, {"bag": bag})
    planner = RegionalCandidateGenerator(horizon=30, deadline_ms=None)
    proposals = planner.generate(state, "bag", "tray", 1)
    assert len(proposals[0].legs) == 19
    assert planner.last_diagnostics["portal_count"] == 0
    assert planner.last_diagnostics["macro_arc_count"] == 1
    assert planner.last_diagnostics["static_lower_bound"] == 19


def test_fixed_static_candidate_limit_is_explicitly_incomplete():
    scene = pilot_scenes()[0]
    planner = RegionalCandidateGenerator(horizon=48, static_path_limit=1, deadline_ms=None)
    proposals = planner.generate(scene.state, scene.target_bag_id, scene.target_tray_id, 3)
    assert len(proposals) == 1
    assert planner.last_search_status == "partial_candidate_set"
    assert planner.last_diagnostics["static_paths_examined"] == 1


def test_routing_profile_closes_zero_capacity_and_reports_od_coverage(tmp_path):
    import json
    from scripts.experiments.ics_circulation_v3.nanning_routing_benchmark import load_routing_proxy

    source = tmp_path / "profile.json"
    source.write_text(json.dumps({
        "nodes": [{"location": index, "node_type": role, "system_key": "source_system"}
                  for index, role in ((0, 1), (1, 4), (2, 2), (3, 1), (4, 2))],
        "edges": [{"start": start, "end": end, "length": 2.5, "speed": 2, "capacity": cap}
                  for start, end, cap in ((0, 1, 2), (1, 2, 0), (3, 4, 3))],
    }), encoding="utf-8")
    original_bytes = source.read_bytes()
    network, pairs, metadata = load_routing_proxy(source, 2)
    assert source.read_bytes() == original_bytes
    assert "1->2" not in network.edges
    assert network.edges["0->1"].capacity == 2
    assert network.edges["0->1"].travel_time == 2
    assert metadata["reachable_od_before_zero_closure"] == 2
    assert metadata["reachable_od_after_zero_closure"] == 1
    assert metadata["lost_reachable_od_pairs"] == [("0", "2")]
    assert pairs == [("3", "4", 2)]
    assert metadata["proxy_flags"]["partition_is_field_control_boundary"] is False


def test_synthetic_partition_assignment_is_deterministic_topology_only():
    from scripts.experiments.ics_circulation_v3.nanning_routing_benchmark import synthetic_partitions

    nodes = [str(index) for index in range(12)]
    edges = [(str(index), str(index + 1), 1) for index in range(11)]
    first = synthetic_partitions(nodes, edges, 4)
    second = synthetic_partitions(list(reversed(nodes)), list(reversed(edges)), 4)
    assert first == second
    assert len(set(first.values())) == 4
    assert set(first) == set(nodes)
