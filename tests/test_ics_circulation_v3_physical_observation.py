from copy import deepcopy
from dataclasses import asdict

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_full_cycle import compare_old_result
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.physical_observation import (
    InstantPhysicalCursorSimulation, instant_physical_projection)
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.run_network_opportunities import physical_projection


def fixture():
    network = Network({n: Node(n, 'zone', 'owner', 3) for n in ('L', 'J', 'U')},
        {'LJ': Edge('LJ', 'L', 'J', 2), 'JU': Edge('JU', 'J', 'U', 2), 'UL': Edge('UL', 'U', 'L', 2)})
    state = Snapshot(0, network, {'tray': Tray('tray', 'L', 'loaded', 'seen')},
        {'seen': Bag('seen', 'L', 'U', 0, 30)})
    return build_engine(state, (), (Bag('later', 'L', 'U', 12, 40),),
                        ControlSpec(planning_horizon=20, predictive=True))


def test_detachment_prevents_future_updates_and_consumer_mutation_both_ways():
    state = fixture().state
    legacy = physical_projection(state)
    captured = instant_physical_projection(state)
    expected = deepcopy(captured)
    state.completed['new_completion'] = 99
    state.load_times['new_load'] = 98
    state.empty_targets['new_target'] = 'U'
    assert legacy['completed']['new_completion'] == 99  # Preserve the old defect as a regression witness.
    assert captured == expected
    captured['trays']['tray']['node'] = 'U'
    captured['completed']['consumer_only'] = 100
    assert state.trays['tray'].node == 'L'
    assert 'consumer_only' not in state.completed


def test_live_ticks_remain_instantaneous_and_do_not_change_execution():
    base = fixture()
    plain = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    observed = InstantPhysicalCursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    first = None
    for tick in range(1, 25):
        original, actual = plain.advance(tick), observed.advance(tick)
        assert compare_old_result(asdict(original), asdict(actual))['equal']
        assert observed.instant_physical_ticks[-1] == instant_physical_projection(plain.state)
        if first is None:
            first = deepcopy(observed.instant_physical_ticks[0])
    assert observed.instant_physical_ticks[0] == first
    assert not first['completed']
    assert observed.state.completed
    for row in observed.instant_physical_ticks:
        assert row['completed'] == {k: v for k, v in observed.state.completed.items() if v <= row['time']}
        # advance(t) prepares arrivals/unloads at t, but load decisions at t are
        # performed by the next advance(t+1); this is a real phase boundary.
        assert row['load_times'] == {k: v for k, v in observed.state.load_times.items() if v < row['time']}


def test_observer_history_does_not_follow_checkpoint_or_allow_skipped_ticks():
    base = fixture()
    observed = InstantPhysicalCursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    observed.advance(1)
    checkpoint = observed.checkpoint().clone()
    restored = InstantPhysicalCursorSimulation.from_checkpoint(checkpoint)
    assert not restored.instant_physical_ticks
    assert not hasattr(checkpoint.base, 'instant_physical_ticks')
    with pytest.raises(ValueError, match='one integer tick'):
        observed.advance(3)
    assert observed.state.now == 1
    assert len(observed.instant_physical_ticks) == 1
    assert compare_old_result(asdict(restored.advance(2)), asdict(observed.advance(2)))['equal']
