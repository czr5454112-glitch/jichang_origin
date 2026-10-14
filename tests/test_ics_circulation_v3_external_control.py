"""The externally coordinated clock retains the same physical event kernel."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, Simulation


def scene():
    nodes = {n: Node(n, n, n, capacity=2) for n in ('A', 'B')}
    network = Network(nodes, {'AB': Edge('AB', 'A', 'B', 4), 'BA': Edge('BA', 'B', 'A', 4)})
    return Snapshot(0, network, {'t': Tray('t', 'A')}, {'b': Bag('b', 'A', 'B', 0, 12)})


def test_external_no_action_does_not_route_or_delete_loaded_task():
    engine = Simulation(scene(), control_mode='external')
    result = engine.advance(3)
    assert result.final_snapshot.trays['t'].bag_id == 'b'
    assert not result.final_snapshot.plans
    assert result.uncompleted_bag_ids == ('b',)
    assert result.policy_stats['generation_calls'] == 0
    assert result.policy_stats['route_commits'] == 0


def test_external_commit_has_same_motion_cost_and_completion_as_automatic():
    external = Simulation(scene(), control_mode='external')
    observation = external.observe()
    action = CandidateGenerator().generate(observation, 'b', 't', 1)[0]
    assert external.intervene(action).accepted
    in_motion = external.advance(2).final_snapshot
    assert in_motion.trays['t'].node is None
    restored = Simulation.from_checkpoint(external.checkpoint())
    assert restored.control_mode == 'external'
    expected = Simulation(scene()).advance(7)
    actual = restored.advance(7)
    assert actual.completed == expected.completed
    assert actual.cost_components == expected.cost_components
    assert actual.final_snapshot == expected.final_snapshot
    assert actual == external.advance(7)


def test_external_wait_accumulates_real_unloaded_queue_cost_and_events():
    state = scene()
    state.trays['t'] = replace(state.trays['t'], node='B')
    future = Bag('later', 'A', 'B', 2, 10)
    engine = Simulation(state, (future,), control_mode='external')
    result = engine.advance(4)
    assert result.cost_components['tray_wait'] == 6
    assert set(result.uncompleted_bag_ids) == {'b', 'later'}
    assert any(row['event'] == 'bag_arrival' and row['time'] == 2 for row in result.trace)


def test_invalid_mode_and_mixed_automatic_callback_are_rejected():
    with pytest.raises(ValueError, match='control_mode'):
        Simulation(scene(), control_mode='pause_physics')
    with pytest.raises(ValueError, match='automatic policy'):
        Simulation(scene(), control_mode='external', slow_controller=lambda state: ())
