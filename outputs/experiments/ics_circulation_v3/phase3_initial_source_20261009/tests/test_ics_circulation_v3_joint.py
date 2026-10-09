"""Owner safety and two sequential joint-control orders."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.joint_control import build_engine, policies
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.phase2_scenarios import make_scene
from scripts.experiments.ics_circulation_v3.run_joint_control import run
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, ExecutionValidator, Simulation


def fixture(*, protected=False):
    nodes = {name: Node(name, name, name, 4) for name in ("A", "J", "B", "C")}
    edges = (Edge("A-J", "A", "J", 1), Edge("J-B", "J", "B", 2),
             Edge("C-J", "C", "J", 1), Edge("J-A", "J", "A", 2))
    bag = Bag("P", "A", "B", 0, 4, protected=protected)
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {"P": Tray("P", "A", "loaded", "P"), "E": Tray("E", "C")}, {"P": bag})


@pytest.mark.parametrize("order,present", [("route_then_prebalance", True), ("prebalance_then_route", False)])
def test_coordination_order_follows_fifo_loading_and_calls_slow_once(order, present):
    state = fixture()
    state.trays["P"] = Tray("P", "A")
    calls = []

    def slow(snapshot):
        calls.append(snapshot.now)
        if snapshot.now == 0:
            assert snapshot.trays["P"].mode == "loaded"
            assert ("P" in snapshot.plans) == present
        return ()

    simulation = Simulation(state, slow_controller=slow, coordination_order=order)
    simulation.advance(3)
    assert calls == [0, 1, 2]
    assert simulation.policy_stats["slow_calls"] == 3


@pytest.mark.parametrize("order", ["route_then_prebalance", "prebalance_then_route"])
def test_order_and_controller_state_survive_checkpoint(order):
    scene = make_scene(0, "joint")
    policy = next(p for p in policies() if p.predictive and p.routing == "timed" and p.coordination_order == order)
    whole = build_engine(scene, scene.future(991), policy).advance(scene.horizon)
    paused = build_engine(scene, scene.future(991), policy)
    paused.advance(7)
    restored = Simulation.from_checkpoint(paused.checkpoint())
    assert restored.coordination_order == order
    assert restored.advance(scene.horizon) == whole


@pytest.mark.parametrize("order", ["route_then_prebalance", "prebalance_then_route"])
def test_protected_full_witness_prevents_later_empty_transfer_stealing_deadline_slot(order):
    state = fixture(protected=True)

    def slow(snapshot):
        if snapshot.now:
            return ()
        plan = snapshot.plans["P"]
        assert not plan.prefix_only
        assert len(plan.legs) == 2
        proposal = CandidateGenerator(horizon=12).generate_empty(snapshot, "E", "B")[0]
        # J-B [1,3) belongs to P. The empty tray must wait until that slot ends.
        assert proposal.legs[-1].depart >= 3
        assert ExecutionValidator().commit(snapshot, proposal).accepted
        return (proposal,)

    simulation = Simulation(state, route_mode="next_edge", slow_controller=slow, coordination_order=order)
    result = simulation.advance(6)
    assert result.completed["P"] == 4
    assert not [event for event in result.trace if event["event"] == "prefix_arrive" and event["tray_id"] == "P"]
    assert result.policy_stats["protected_commits"] == 1
    assert result.policy_stats["protected_unadmitted_decisions"] == 0


def test_existing_empty_destination_obligation_cannot_be_rewritten_at_safe_stop():
    state = fixture()
    state.bags = {}
    state.trays = {"E": Tray("E", "C")}
    simulation = Simulation(state, route_mode="next_edge", reactive_empty_dispatch=False)
    candidate = CandidateGenerator().generate_empty(simulation.observe(), "E", "B")[0]
    assert simulation.intervene(candidate).accepted
    simulation.advance(1)
    assert simulation.state.empty_targets == {"E": "B"}
    wrong = CandidateGenerator().generate_empty(simulation.observe(), "E", "A")
    assert wrong == ()
    good = CandidateGenerator().generate_empty(simulation.observe(), "E", "B")[0]
    forged = replace(good, destination_node="A")
    assert ExecutionValidator().validate(simulation.state, forged).reason == "empty_destination_obligation"
    assert simulation.advance(5).final_trays["E"].node == "B"


def test_joint_runner_retains_all_six_policy_denominators_and_matching_inputs(tmp_path):
    summary = run(tmp_path, groups=1)
    assert summary["run_count"] == summary["policy_count"] == 6
    assert summary["failed_run_count"] == 0
    assert summary["all_input_pairs_equal"]
    assert summary["all_finite_tray_ids_preserved"]
    assert summary["all_arrived_bag_ids_preserved"]
    assert len({row["all_bags_denominator"] for row in summary["by_policy"].values()}) == 1
    assert len(list(tmp_path.glob("group_000__*.json"))) == 6


def test_invalid_coordination_order_is_rejected():
    with pytest.raises(ValueError, match="coordination_order"):
        Simulation(fixture(), coordination_order="mutate_rules")
