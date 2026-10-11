from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import NetworkWorkload
from scripts.experiments.ics_circulation_v3.run_network_opportunities import digest, physical_prefix, run, run_case
from scripts.experiments.ics_circulation_v3.run_workload_diagnostics import DiagnosticBudget
from scripts.experiments.ics_circulation_v3.runtime import actual_action_key


def test_physical_signature_does_not_inflate_conditional_route_choices():
    nodes = {n: Node(n, 'z', 'owner') for n in ('A', 'J', 'K', 'B')}
    edges = [Edge('AJ', 'A', 'J', 1), Edge('JB', 'J', 'B', 1), Edge('JK', 'J', 'K', 1), Edge('KB', 'K', 'B', 1)]
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), {'t': Tray('t', 'A', 'loaded', 'b')},
                     {'b': Bag('b', 'A', 'B', 0, 20)})
    a = RouteCandidate('a', 'b', 't', (Leg('AJ', 0, 1), Leg('JB', 1, 2)), 3, 3, 0, 'a', True)
    b = replace(a, candidate_id='b', legs=(Leg('AJ', 0, 1), Leg('JK', 1, 2), Leg('KB', 2, 3)),
                unload_complete=4, usable_at=4)
    assert actual_action_key(state, a) != actual_action_key(state, b)
    assert digest(physical_prefix(state, a)) == digest(physical_prefix(state, b))


def small_scene():
    scene = feedback_scene(shared_travel=2)
    return NetworkWorkload(scene.name, scene.initial, scene.forecasts, scene.future_bags, 25, scene.factors)


def test_actual_selector_opportunities_include_later_reachable_states():
    result = run_case(small_scene(), 'timed', DiagnosticBudget(max_search_work=100000, max_wall_seconds=10))
    metrics = result['metrics']
    assert metrics['status'] == 'completed_all'
    assert metrics['noninitial_selector_calls'] > 0
    assert metrics['source_bag_count_with_selector'] == 2
    assert metrics['actual_selector_calls'] == len(result['selector_calls'])
    assert metrics['loaded_search_calls'] >= metrics['actual_selector_calls']
    assert all(r['physical_prefix_distinct'] <= r['actual_action_distinct'] <= r['candidate_count']
               for r in result['selector_calls'])
    assert all('network' not in r['observable_state_without_static_network'] for r in result['selector_calls'])
    assert len(result['routing_boundaries']) == small_scene().horizon


def test_budget_stop_keeps_full_future_bag_and_query_denominators():
    result = run_case(small_scene(), 'baseline', DiagnosticBudget(max_search_calls=1, max_wall_seconds=10))
    metrics = result['metrics']
    assert metrics['status'] == 'budget_exhausted'
    assert metrics['scheduled_bags'] == 2
    assert metrics['future_unobserved'] == 1
    assert metrics['uncompleted_including_unobserved'] == 2
    assert metrics['total_cost'] is None
    assert metrics['search_calls'] == 1


def test_nonempty_output_refused_before_profile_read(tmp_path):
    (tmp_path / 'keep.txt').write_text('preserve')
    with pytest.raises(ValueError, match='cannot be overwritten'):
        run(tmp_path, profile=tmp_path / 'absent.json')
    assert (tmp_path / 'keep.txt').read_text() == 'preserve'
