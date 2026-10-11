from dataclasses import replace

from scripts.experiments.ics_circulation_v3.joint_transactions import commit_joint, commit_joint_actions, validate_joint
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation


def swap_scene():
    network = Network({n: Node(n, n, n, capacity=1) for n in ('A', 'B')},
                      {'AB': Edge('AB', 'A', 'B', 2), 'BA': Edge('BA', 'B', 'A', 2)})
    trays = {'a': Tray('a', 'A', 'loaded', 'ba'), 'b': Tray('b', 'B', 'loaded', 'bb')}
    bags = {'ba': Bag('ba', 'A', 'B', 0, 6), 'bb': Bag('bb', 'B', 'A', 0, 6)}
    state = Snapshot(0, network, trays, bags)
    actions = tuple(RouteCandidate(t, 'b' + t, t, (Leg(edge, 0, 2),), 3, 3, 0, t, True, target)
                    for t, edge, target in (('a', 'AB', 'B'), ('b', 'BA', 'A')))
    return state, actions


def test_capacity_one_swap_requires_atomic_admission_and_moves_legally():
    state, actions = swap_scene()
    assert all(not ExecutionValidator().validate(state, p).accepted for p in actions)
    before = state.clone()
    assert validate_joint(state, actions).accepted
    assert state == before
    engine = Simulation(state, control_mode='external')
    assert commit_joint_actions(engine, actions).accepted
    moving = engine.advance(1)
    assert all(t.node is None for t in moving.final_trays.values())
    completed = engine.advance(4)
    assert completed.completed == {'ba': 3, 'bb': 3}
    assert completed.final_snapshot.trays['a'].node == 'B'
    assert completed.final_snapshot.trays['b'].node == 'A'


def test_one_invalid_member_rolls_back_every_resource_and_version():
    state, actions = swap_scene()
    before = state.clone()
    bad = replace(actions[1], legs=(Leg('BA', 0, 1),))
    verdict = commit_joint(state, (actions[0], bad))
    assert not verdict.accepted
    assert state == before


def test_atomic_bundle_cannot_bypass_same_resource_capacity_or_stale_version():
    state, actions = swap_scene()
    assert not commit_joint(state, (actions[0], replace(actions[1], dependency_version=1))).accepted
    assert not commit_joint(state, (actions[0], actions[0])).accepted
    delayed = replace(actions[1], legs=(Leg('BA', 3, 5),), unload_complete=6, usable_at=6)
    assert not commit_joint(state, (actions[0], delayed)).accepted


def test_all_empty_exports_jointly_respect_source_stock_floor():
    state, actions = swap_scene()
    state.network.nodes['A'] = replace(state.network.nodes['A'], capacity=2)
    state.network.nodes['B'] = replace(state.network.nodes['B'], capacity=2)
    state.bags.clear()
    state.trays = {'a': Tray('a', 'A'), 'b': Tray('b', 'A')}
    state.module = FixedLocalModule(export_min_stock=1)
    transfers = tuple(replace(actions[0], candidate_id=t, tray_id=t, bag_id=None,
                              legs=(Leg('AB', i * 2, i * 2 + 2),), unload_complete=i * 2 + 2,
                              usable_at=i * 2 + 2) for i, t in enumerate(('a', 'b')))
    assert ExecutionValidator().validate(state, transfers[0]).accepted
    before = state.clone()
    assert not commit_joint(state, transfers).accepted
    assert state == before


def test_atomic_admission_does_not_replace_an_old_commitment():
    state, actions = swap_scene()
    state.network.nodes['B'] = replace(state.network.nodes['B'], capacity=2)
    assert ExecutionValidator().commit(state, actions[0]).accepted
    before = state.clone()
    assert not commit_joint(state, (replace(actions[0], dependency_version=state.version),)).accepted
    assert state == before


def test_engine_adapter_rejects_unknown_identity_without_partial_publication():
    state, actions = swap_scene()
    engine = Simulation(state, control_mode='external')
    before = engine.observe()
    verdict = commit_joint_actions(engine, (replace(actions[0], tray_id='missing'),))
    assert not verdict.accepted and verdict.reason == 'joint_unknown_tray'
    assert engine.state == before
