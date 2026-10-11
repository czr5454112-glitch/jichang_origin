"""Outcome-blind finite-carrier development cases for announced storage.

These are hand-sized mechanism experiments, not observed airport workloads.
The unchanged FIFO loader and reactive empty dispatcher own all live actions.
"""
from dataclasses import asdict, replace

from .model import Bag, Edge, FixedLocalModule, Network, Node, Tray
from .routing import RegionalCandidateGenerator
from .runtime import Simulation
from .storage_contracts import StorageBag, StorageSnapshot, StorageWaypointContract


CASE_NAMES = ("reuse", "two_carriers", "tight_storage", "zero_dwell",
              "late_ingress", "long_release", "deadline_before_release",
              "closed_ingress", "closed_return", "initial_storage")


def mechanism(case, mode="whole_route"):
    if case not in CASE_NAMES:
        raise ValueError("unknown storage mechanism")
    nodes = {n: Node(n, "zone", "owner", 1 if n == "S" else 4)
             for n in ("A", "S", "D")}
    edges = {e.edge_id: e for e in (
        Edge("AS", "A", "S", 2), Edge("SD", "S", "D", 2),
        Edge("AD", "A", "D", 1), Edge("DA", "D", "A", 2))}
    count = 2 if case in ("two_carriers", "tight_storage") else 1
    if case == "two_carriers":
        nodes["S"] = replace(nodes["S"], capacity=2)
    if case == "closed_ingress":
        edges["AS"] = replace(edges["AS"], capacity=0)
    if case == "closed_return":
        edges["DA"] = replace(edges["DA"], capacity=0)
    release = {"zero_dwell": 2, "late_ingress": 1, "long_release": 100}.get(case, 6)
    initial_storage = case == "initial_storage"
    first = StorageBag("early1", "S" if initial_storage else "A", "D", 0,
        5 if case == "deadline_before_release" else 140, True,
        StorageWaypointContract("S", release, 0))
    second = StorageBag("early2", "A", "D", 1, 160, True,
                        StorageWaypointContract("S", 15, 1))
    direct = Bag("direct", "A", "D", 2, 180, True)
    trays = {f"t{i}": Tray(f"t{i}", "S" if initial_storage else "A")
             for i in range(count)}
    state = StorageSnapshot(0, Network(nodes, edges), trays, {},
                            module=FixedLocalModule(1, {"D": 2}, 0, 1))
    return Simulation(state, [first, second, direct], route_mode=mode,
        generator_factory=RegionalCandidateGenerator(horizon=80, expansion_limit=100000,
                                                    cache_scope="isolated_replay_v1"))


def lifecycle_report(engine, expected):
    """Derive business milestones from actual identity-bound runtime events."""
    result = engine.result()
    loads = [event for event in result.trace if event["event"] == "load"]
    by_bag = {}
    for bag_id in expected:
        bag = engine.state.bags.get(bag_id)
        progress = engine.state.storage_progress.get(bag_id)
        occurrences = [event for event in loads if event["bag_id"] == bag_id]
        assert len(occurrences) <= 1, "business task loaded twice"
        by_bag[bag_id] = {
            "observed": bag is not None,
            "arrival": bag.arrival if bag else None,
            "deadline": bag.deadline if bag else None,
            "loaded_at": occurrences[0]["time"] if occurrences else None,
            "tray_id": occurrences[0]["tray_id"] if occurrences else None,
            "storage": asdict(progress) if progress else None,
            "completed_at": engine.state.completed.get(bag_id),
            "uncompleted": bag_id not in engine.state.completed,
        }
        if progress:
            assert occurrences and progress.tray_id == occurrences[0]["tray_id"]
            if bag_id in engine.state.completed:
                assert progress.departed_at is not None
                assert progress.departed_at >= max(progress.arrived_at, progress.contract.release_at)
                assert engine.state.completed[bag_id] >= progress.departed_at
    carriers = {tray_id: [event["bag_id"] for event in loads if event["tray_id"] == tray_id]
                for tray_id in engine.state.trays}
    assert set(carriers) == engine._tray_ids
    assert len(engine.state.completed) + sum(row["uncompleted"] for row in by_bag.values()) == len(expected)
    drained = (not engine._arrivals and len(engine.state.completed) == len(expected)
               and not engine.state.plans and not engine.state.empty_targets
               and all(t.mode == "empty" and t.bag_id is None for t in engine.state.trays.values()))
    return {"at": engine.state.now, "expected_business_tasks": len(expected),
            "task_rows": by_bag, "carrier_service_order": carriers,
            "carrier_reuses": sum(max(0, len(ids)-1) for ids in carriers.values()),
            "transport_drained": drained,
            "status": "transport_drained" if drained else "fixed_tick_cap_censored",
            "cost_components": result.cost_components, "total_cost": result.total_cost,
            "policy_stats": result.policy_stats, "invariant_checks": result.invariant_checks}
