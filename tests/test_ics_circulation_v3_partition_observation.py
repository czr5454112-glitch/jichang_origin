from dataclasses import asdict
import json
import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray, Reservation
from scripts.experiments.ics_circulation_v3.partition_observation import observe_partition, resource_owner


def fixture():
    return Snapshot(0, Network({'A': Node('A', 'z1', 'r1'), 'B': Node('B', 'z2', 'r2'),
                                'C': Node('C', 'z2', 'r2')},
                               {'AB': Edge('AB', 'A', 'B', 2), 'BC': Edge('BC', 'B', 'C', 1)}),
                    {'local': Tray('local', 'A'), 'private-remote-tray': Tray('private-remote-tray', 'C')},
                    {'private-remote-bag': Bag('private-remote-bag', 'C', 'B', 3, 10)},
                    reservations=(Reservation('edge:BC', 3, 4, 'private-remote-tray'),))


def test_remote_calendar_and_identities_are_not_in_local_observation():
    state = fixture()
    view = observe_partition(state, 'r1')
    text = json.dumps(asdict(view))
    assert 'private-remote' not in text
    assert all(resource_owner(state, s.resource) == 'r1' for s in view.local_calendars)
    assert 'BC' in view.public_topology.edges  # Topology is explicitly public.
    assert len(view.remote_summaries) == 1
    assert {r.resource for r in view.remote_summaries[0].boundary_occupancy} == {'node:B', 'reception:B'}


def test_observation_has_no_mutable_reference_to_owner_state():
    state = fixture()
    view = observe_partition(state, 'r1')
    view.public_topology.edges.clear()
    assert set(state.network.edges) == {'AB', 'BC'}


def test_unknown_partition_does_not_receive_global_snapshot():
    with pytest.raises(ValueError, match='unknown_control_partition'):
        observe_partition(fixture(), 'missing')


def test_boundary_now_counts_are_explicitly_not_future_reservations():
    state = fixture()
    state.trays['private-remote-tray'] = Tray('private-remote-tray', 'B')
    view = observe_partition(state, 'r1')
    node = next(s for s in view.remote_summaries[0].boundary_occupancy if s.resource == 'node:B')
    assert node.occupied_units_now == 1
    assert not hasattr(node, 'calendar')
    assert view.version_scope == 'global_conservative_watermark'
