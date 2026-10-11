from dataclasses import replace

from scripts.experiments.ics_circulation_v3.dependency_admission import execute_dependencies, plan_dependencies, propose_loaded_departures
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import Simulation


def cycle(size=3, capacity=1):
    nodes = {str(i): Node(str(i), str(i), str(i), capacity=capacity) for i in range(size)}
    edges = {str(i): Edge(str(i), str(i), str((i + 1) % size), 1) for i in range(size)}
    bags = {str(i): Bag(str(i), str(i), str((i + 1) % size), 0, 5) for i in range(size)}
    trays = {str(i): Tray(str(i), str(i), 'loaded', str(i)) for i in range(size)}
    return Snapshot(0, Network(nodes, edges), trays, bags)


def test_cycle_is_one_joint_component_and_all_physical_tasks_finish():
    engine = Simulation(cycle(), control_mode='external')
    observation = engine.observe()
    actions, logs = propose_loaded_departures(observation)
    plan = plan_dependencies(observation, actions)
    assert len(actions) == 3 and len(logs) == 3
    assert plan.diagnostics['joint_component_count'] == 1
    assert len(plan.bundles[0]) == 3
    assert engine.state == observation
    execute_dependencies(engine, plan)
    assert len(engine.advance(3).completed) == 3


def test_spare_node_capacity_needs_no_joint_component():
    state = cycle(capacity=2)
    actions, _ = propose_loaded_departures(state)
    plan = plan_dependencies(state, actions)
    assert plan.diagnostics['joint_component_count'] == 0
    assert plan.diagnostics['accepted_tray_count'] == 3


def test_unproposed_idle_blocker_cannot_be_erased_by_hypothetical_release():
    state = cycle()
    actions, _ = propose_loaded_departures(state)
    plan = plan_dependencies(state, actions[:2])
    assert not plan.bundles
    assert plan.diagnostics['uncommitted_trays'] == ['0', '1']


def test_joint_dependency_cycle_still_rejects_incompatible_departure_times():
    state = cycle()
    actions, _ = propose_loaded_departures(state)
    later = replace(actions[-1], legs=tuple(replace(l, depart=l.depart + 2, arrive=l.arrive + 2) for l in actions[-1].legs),
                    unload_complete=actions[-1].unload_complete + 2, usable_at=actions[-1].usable_at + 2)
    plan = plan_dependencies(state, actions[:-1] + (later,))
    assert not plan.bundles
    assert plan.diagnostics['rejected_components']
