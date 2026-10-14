"""Reject malformed physical numbers before advancing the circulation host."""
from copy import deepcopy
import math
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle


@pytest.fixture(scope='module')
def native():
    configured = os.environ.get('G31_CIRCULATION_BINARY')
    if configured:
        return load_native(configured)
    folder = Path(__file__).resolve().parents[1] / 'build_g31_circulation' / 'python'
    binaries = [*folder.glob('czr005_circulation*.pyd'), *folder.glob('czr005_circulation*.so')]
    assert len(binaries) == 1, 'Build czr005_circulation or set G31_CIRCULATION_BINARY'
    return load_native(binaries[0])


@pytest.mark.parametrize('service', [-1.0, float('nan'), float('inf')])
def test_invalid_node_service_is_not_silently_clamped(native, service):
    data = tiny_cycle()
    row = list(data['node_records'][0]); row[2] = service
    data['node_records'][0] = row
    with pytest.raises(ValueError, match='^circulation:invalid_node_service$'):
        native.run(data)


@pytest.mark.parametrize('length,speed', [(-1.0, 1.0), (float('nan'), 1.0),
    (float('inf'), 1.0), (1.0, 0.0), (1.0, -1.0), (1.0, float('nan')), (1.0, float('inf'))])
def test_invalid_edge_geometry_is_not_silently_clamped_or_scored_infinite(native, length, speed):
    data = tiny_cycle()
    data['edge_records'][0] = (0, 1, length, speed)
    with pytest.raises(ValueError, match='^circulation:invalid_edge_geometry$'):
        native.run(data)


def test_finite_edge_components_cannot_overflow_travel_time(native):
    data = tiny_cycle()
    data['edge_records'][0] = (0, 1, 1e308, 1e-308)
    with pytest.raises(ValueError, match='^circulation:invalid_edge_travel$'):
        native.run(data)


@pytest.mark.parametrize('component', ['message', 'load', 'unload_hold', 'fault_notification'])
def test_finite_times_cannot_overflow_derived_events(native, component):
    data = tiny_cycle()
    data['options']['max_simulation_time'] = -1
    if component == 'message':
        data['transfers'][0].update(issued_at=1e308, message_delay=1e308)
    elif component == 'load':
        data['jobs'][0].update(arrival=1e308, load_seconds=1e308)
    elif component == 'unload_hold':
        data['jobs'][0].update(unload_seconds=1e308, hold_seconds=1e308)
    else:
        data['faults'] = [dict(**{'from': 0, 'to': 1}, start=1e308,
                              end=1e308, message_delay=1e308)]
    with pytest.raises(ValueError, match='^circulation:nonfinite_derived_time$'):
        native.run(data)


@pytest.mark.parametrize('shape', ['few_rows', 'few_columns', 'extra_columns'])
def test_heuristic_shape_is_rejected_at_binding_boundary(native, shape):
    data = tiny_cycle()
    if shape == 'few_rows':
        data['heuristic_time'] = [[0.0]]
    elif shape == 'few_columns':
        data['heuristic_time'][0].pop()
    else:
        data['heuristic_time'][0].append(0.0)
    with pytest.raises(ValueError, match='^circulation:invalid_heuristic_shape$'):
        native.run(data)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1.0])
def test_unqueried_heuristic_values_also_obey_the_physical_input_contract(native, value):
    data = tiny_cycle()
    # The old implementation never queried this cell and accepted NaN here.
    data['heuristic_time'][0][2] = value
    with pytest.raises(ValueError, match='^circulation:invalid_heuristic_value$'):
        native.run(data)


@pytest.mark.parametrize('kind', ['node', 'edge'])
def test_duplicate_graph_rows_cannot_be_silently_ignored(native, kind):
    data = tiny_cycle()
    data[kind+'_records'].append(deepcopy(data[kind+'_records'][0]))
    with pytest.raises(ValueError, match='^circulation:invalid_graph_'+kind+'_record$'):
        native.run(data)


@pytest.mark.parametrize('kind', ['node', 'edge'])
def test_malformed_graph_record_lengths_have_explicit_boundary_reason(native, kind):
    data = tiny_cycle()
    data[kind+'_records'][0] = list(data[kind+'_records'][0])[:-1]
    with pytest.raises(ValueError, match='^circulation:invalid_graph_'+kind+'_record$'):
        native.run(data)


def test_zero_service_and_zero_length_retain_native_minimum_service_contract(native):
    data = tiny_cycle()
    row = list(data['node_records'][0]); row[2] = 0.0
    data['node_records'][0] = row
    data['edge_records'][0] = (0, 1, 0.0, 1.0)
    result = native.run(data)
    audit_result(data, result)
    assert all(job['status'] == 'completed' for job in result['jobs'])
    assert math.isfinite(result['physical_clock'])
    entries = {e['traversal_id']: e for e in result['receipts'] if e['event'] == 'EDGE_ENTER'}
    used = 0
    for event in result['receipts']:
        if event['event'] == 'EDGE_EXIT' and (event['from'], event['to']) == (0, 1):
            assert event['time']-entries[event['traversal_id']]['time'] == pytest.approx(0.001)
            used += 1
    assert used == 2
