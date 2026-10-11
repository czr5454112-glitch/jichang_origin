from dataclasses import asdict

import pytest

from scripts.experiments.ics_circulation_v3.feature_diagnostics import (
    FoldNeighbors, collision_report, infer_current_node, observable_context)
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Leg, Network, Node, RouteCandidate
from scripts.experiments.ics_circulation_v3.run_feature_diagnostics import run


def test_observable_destination_role_and_safe_prefix_do_not_treat_return_loop_as_delivery():
    network = Network({n: Node(n, 'z', 'p', can_wait=n != 'X') for n in ('C', 'S', 'X', 'G')},
        {e.edge_id: e for e in (Edge('CS', 'C', 'S', 1), Edge('SX', 'S', 'X', 2),
                                 Edge('XG', 'X', 'G', 2), Edge('GC', 'G', 'C', 2))})
    bag = asdict(Bag('b', 'S', 'C', 0, 30))
    candidate = asdict(RouteCandidate('loop', 'b', 't', (Leg('CS', 5, 6), Leg('SX', 6, 8),
                            Leg('XG', 8, 10), Leg('GC', 10, 12)), 13, 13, 0, 'base'))
    c = observable_context(network, bag, candidate, now=5, current_node='C')
    assert c['role'] == 'at_destination'
    assert not c['prefix_completes_delivery']
    assert c['prefix_end'] == 'S'
    assert c['witness_visits_goal_before_terminal']
    assert c['prefix_shortest_progress'] < 0
    assert infer_current_node(network, [candidate], bag) == 'C'
    with pytest.raises(ValueError, match='already observed'):
        observable_context(network, {**bag, 'arrival': 9}, candidate, now=5, current_node='C')


def row(group, stream, value, delta, *, baseline=False, node='S', role='at_origin'):
    return {'source_group': group, 'stream': stream, 'candidate_index': 0 if baseline else 1,
            'is_baseline': baseline, 'features': {'x': value}, 'delta_mean': delta, 'timed_delta': 0.,
            'paired_deltas': [delta - 1, delta + 1], 'context': {'current_node': node, 'role': role, 'task_od': 'S->G'}}


def test_exact_collision_compares_noise_without_claiming_structural_aliasing():
    rows = [row('a', 'one', 1, 1, baseline=True), row('b', 'two', 1, 2, baseline=True)]
    result = collision_report(rows, ['x'])
    collision, = result['collision_groups']
    assert collision['target_range'] == 1
    assert collision['comparisons'][0]['independent_mc_difference_se'] > 1
    assert 'not proof' in result['interpretation']


def test_paired_collision_keeps_reference_context():
    rows = [row('a', 'one', 0, 0, baseline=True), row('a', 'one', 2, 1),
            row('b', 'two', 1, 0, baseline=True), row('b', 'two', 2, 2)]
    assert collision_report(rows, ['x'])['unique_feature_keys'] == 3
    assert collision_report(rows, ['x'], paired=True)['unique_feature_keys'] == 4


def test_neighbours_exclude_heldout_stream_and_do_not_infer_role_or_label():
    rows = [row('held', 'held', 0, 999, baseline=True, node='C', role='at_destination'),
            row('train', 'train', 2, 1, baseline=True)]
    index = FoldNeighbors(rows, 'held', ['x'])
    result = index.nearest({'x': 0}, {'current_node': 'C', 'role': 'at_destination', 'task_od': 'B->C'})
    assert result['nearest_training_rows'][0]['source_group'] == 'train'
    assert result['nearest_training_rows'][0]['normalized_rms_distance'] == 2
    assert not result['nearest_same_role']
    assert not result['deployment_label_inferred']


def test_diagnostic_refuses_existing_output_before_reading_inputs(tmp_path):
    (tmp_path / 'keep.txt').write_text('keep')
    with pytest.raises(ValueError, match='cannot be overwritten'):
        run(tmp_path, paired=tmp_path / 'absent', labels=tmp_path / 'also_absent')
