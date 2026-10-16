"""No study-cell projections in tests; declaration and fail-closed assessment."""
from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation import research_public_interaction_discovery as m


def test_complete_separate_discovery_validation_denominators():
    p = m.protocol()
    assert p['discovery_denominator'] == p['validation_denominator_reserved_unexecuted'] == 256
    assert len(p['cases']) == 16 and len({c['case_id'] for c in p['cases']}) == 16
    for c in m.parameters('discovery') + m.parameters('validation'):
        assert len(m.actions(c)) == 32
        assert len([a for k, a in m.actions(c).items() if k[0] == 0]) == 16
    assert {c['receiver_load'] for c in m.parameters('discovery')}.isdisjoint(
        {c['receiver_load'] for c in m.parameters('validation')})


def test_only_new_public_edge_length_and_receiver_load_change():
    a, b = m.parameters('discovery')[0:2]
    ba, bb = m.bundle(a), m.bundle(b)
    ea = next(e for e in ba['contract']['edge_records'] if e[:2] == [7, 8])
    eb = next(e for e in bb['contract']['edge_records'] if e[:2] == [7, 8])
    assert ea[2:] == [1.75, 1.] and eb[2:] == [2., 1.]
    assert ba['contract']['edge_contracts'] == bb['contract']['edge_contracts']
    assert ba['contract']['node_contracts'] == bb['contract']['node_contracts']
    assert 'heuristic_time' not in ba['contract'] and 'potential_contract' not in ba['contract']
    assert set(ba['jobs']) == m.JOBS and len(ba['trays']) == 3


@pytest.mark.parametrize('change', ['edge', 'capacity', 'job', 'status', 'source', 'arrival', 'available', 'case'])
def test_exact_hypothetical_template_rejects_changed_field(change):
    c = m.parameters('discovery')[0]; b = m.bundle(c); action = m.actions(c)[0, 0, 0, 0]
    if change == 'edge': b['contract']['edge_records'][0][2] += .1
    elif change == 'capacity': b['contract']['node_contracts'][0]['capacity'] += 1
    elif change == 'job': b['jobs'].pop('blocker')
    elif change == 'status': b['jobs']['blocker']['status'] = 'completed'
    elif change == 'source': b['trays']['E']['node'] = 0
    elif change == 'arrival': b['jobs']['receiver']['arrival'] += .01
    elif change == 'available': b['trays']['E']['available_at'] = 99.
    else: b['case']['later_extra_travel'] = 0.
    assert m.predict(c, b, action)['status'] == 'unknown_changed_hypothetical_contract'


def test_boolean_action_cannot_be_declared_zero():
    c = m.parameters('discovery')[0]; a = m.actions(c)[0, 0, 0, 0]
    a['return_delay'] = False
    assert m.predict(c, m.bundle(c), a)['status'] == 'unknown_undeclared_action'


def row(times, first=1, later=3, returned=5.):
    return {'prediction': {'status': 'conditional_prediction', 'completion': dict(zip(sorted(m.JOBS), times))},
            'evidence': {'status': 'conditional_projected_actions_and_chain',
                         'initial_edge': {'target': first}, 'first_reuse_edge': {'target': later},
                         'returns': [{'at': returned}]}}


def test_two_single_regressions_pair_protected_is_only_conditional_barrier():
    # sorted jobs: blocker, loaded, receiver, reuse1, reuse2
    values = {(0, 0): row([5., 10., 10., 10., 10.]),
              (1, 0): row([5., 9., 11., 9., 9.], first=2, returned=4.),
              (0, 1): row([5., 10., 9., 11., 11.], later=8),
              (1, 1): row([5., 9., 9., 9., 9.], first=2, later=8, returned=4.)}
    result = m.cube(values)
    assert result['barrier'] is True and result['projected_chain_candidate'] is True
    assert result['native_protection_certified'] is False
    values[0, 1]['prediction']['completion']['reuse1'] = 10.
    values[0, 1]['prediction']['completion']['reuse2'] = 10.
    assert m.cube(values)['barrier'] is False


def test_unknown_cube_and_positive_ulp_regression_fail_closed():
    values = {k: row([5., 10., 10., 10., 10.]) for k in ((0, 0), (1, 0), (0, 1), (1, 1))}
    values[1, 1]['prediction']['completion']['receiver'] = 10.000000000000002
    assert m.protected(values[1, 1], values[0, 0]) is False
    values[1, 0]['evidence']['status'] = 'unknown_projected_action_or_chain'
    assert m.cube(values)['status'] == 'unknown_incomplete_cube'


def test_rejected_preference_never_becomes_successful_default():
    action = {'initial_action': 'prefer_2', 'later_action': 'native_default'}
    p = {'status': 'conditional_prediction', 'completion': {j: 10. for j in m.JOBS},
         'projected_commands': [{'job': 'loaded', 'from': 0, 'next': 2, 'status': 'rejected',
                                 'ack_delivered_at': .14, 'reserves_receiving_capacity': False}]}
    result = m.physical_evidence(p, action)
    assert result['commands_updated'] is False
    assert result['status'] == 'unknown_projected_action_or_chain'


def test_incomplete_or_misbound_factorial_is_unknown():
    assert m.assess(m.parameters('discovery')[0], [])['status'] == 'unknown_incomplete_or_misbound_factorial'
