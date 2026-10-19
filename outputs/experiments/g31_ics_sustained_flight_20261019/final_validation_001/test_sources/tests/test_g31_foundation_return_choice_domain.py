"""Detached return-domain contracts only. No native or training is started."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_return_choice_domain as choice
from scripts.experiments.g31_ics_circulation import research_live_obligation_native_domain as legacy


def action(identity, owner, status, at, kind='transfer'):
    return {'request_id': identity, 'kind': kind, 'source_owner': owner,
        'last_delivered_ack': {'sequence': 1, 'delivered_at': at, 'status': status}}


def bundle(index=1):
    sources = []
    for owner, rows in [('A', [action(f'A-return-{i}', 'A', 'received', 9. + i) for i in range(index)]),
                        ('B', [action('B-rejected', 'B', 'rejected', 2.),
                               action('B-received', 'B', 'received', 12.)])]:
        sources.append({'owner': owner, 'identity': 'delivered-' + owner, 'captured_at': 12.7,
            'known_faults': [], 'unresolved_tray_request_ids': [],
            'submitted_physical_request_ids': [r['request_id'] for r in rows], 'submitted_physical_actions': rows})
    return {'now': 12.8, 'case': 'hold3_11_65_release27_5', 'source_records': sources,
        'completed_prefix': {'loaded': 7., 'receiver': 5., **{f'reuse{i}': 11.+i for i in range(1, index+1)}},
        'trays': {'L': {'node': 6, 'mode': 'empty', 'business_bag_id': '', 'edge_to': -1,
            'reception_node': -1, 'available_at': 12.6, 'committed_prefix': [6]},
            'E': {'node': 1, 'mode': 'loading', 'business_bag_id': 'blocker'}}}


def evidence(index=1):
    own = {'q': {'kind': 'planning_snapshot_v3', 'request': {'request_id': 'q', 'owner_id': 'A'}}}
    for i in range(index):
        own[f'A-return-{i}'] = {'kind': 'transfer', 'request': {'request_id': f'A-return-{i}',
            'owner_id': 'A', 'tray_id': 'L', 'source': 6, 'destination': 7},
            'terminal': True, 'ack': {'status': 'received'}}
    return {'schema': choice.EVIDENCE_SCHEMA, 'owner': 'A', 'phase': 'cycle_return', 'at': 12.8,
        'information': {'raw_endpoints': {'view': {'owner_id': 'A', 'now': 12.8}, 'command': {}, 'received': []}},
        'collection': {'request_id': 'q', 'peer_message': 'delivered-B', 'at': 12.7, 'policy_quiet_since': 12.7},
        'retained': {}, 'own_outbox': own, 'own_calls': []}


@pytest.mark.parametrize('index', [1, 2])
def test_new_relative_delays_preserve_old_absolute_first_contract(index):
    immediate = choice.action_contract(12.8, 'return_now', index)
    delayed = choice.action_contract(12.8, 'return_delay_0_5', index)
    assert immediate['request_fields']['earliest_departure'] == 12.8
    assert delayed['request_fields']['earliest_departure'] == 13.3
    assert delayed['request_fields']['expiry'] == immediate['request_fields']['expiry'] == 39.
    assert delayed['request_fields']['message_delay'] == .01
    assert delayed['semantic']['earliest_legal_arrival'] - immediate['semantic']['earliest_legal_arrival'] == pytest.approx(.49)
    assert legacy.return_earliest(12.8, .5, 0) == 12.8  # Historical absolute 7.84 remains historical.
    with pytest.raises(ValueError, match='second_return_must_be_immediate'):
        legacy.return_earliest(12.8, .5, 1)


@pytest.mark.parametrize('index', [0, 3, -1, True, 1.0])
def test_no_first_or_unregistered_return_is_admitted(index):
    with pytest.raises(ValueError, match='second_or_third'):
        choice.action_contract(12.8, 'return_now', index)


def test_expiry_is_not_silently_extended():
    with pytest.raises(ValueError, match='expiry'):
        choice.action_contract(38.75, 'return_delay_0_5', 2)


def test_public_received_ACKs_prove_conservative_headway_without_private_payload():
    before = bundle(); frozen = copy.deepcopy(before)
    result = choice.verify_public_peer_history(before, 1, choice.peer_policy_contract())
    assert result['headway_expired_by'] == 12.5 < result['capture_floor']
    assert result['received_transfer_request_id'] == 'B-received'
    assert result['peer_private_outbox_read'] is False and before == frozen


@pytest.mark.parametrize('change,reason', [
    ('recent_ACK', 'headway_not_expired'), ('pending_ACK', 'terminal_delivered_actions'),
    ('missing_action', 'complete_source_actions'), ('unresolved', 'unresolved_source'),
    ('wrong_cycle', 'actual_completed_cycle'), ('unreleased_tray', 'released_L'),
    ('E_still_at_source', 'E_current_lifecycle')])
def test_public_history_and_current_cycle_fail_closed(change, reason):
    b = bundle(); peer = b['source_records'][1]
    if change == 'recent_ACK':
        peer['submitted_physical_actions'][-1]['last_delivered_ack']['delivered_at'] = 12.3
    elif change == 'pending_ACK':
        peer['submitted_physical_actions'][-1]['last_delivered_ack']['status'] = 'departed'
    elif change == 'missing_action':
        peer['submitted_physical_actions'].pop()
    elif change == 'unresolved':
        peer['unresolved_tray_request_ids'] = ['B-unresolved']
    elif change == 'wrong_cycle':
        b['completed_prefix']['reuse2'] = 12.1
    elif change == 'unreleased_tray':
        b['trays']['L']['available_at'] = 12.71
    else:
        b['trays']['E']['node'] = 5
    with pytest.raises(ValueError, match=reason):
        choice.verify_public_peer_history(b, 1, choice.peer_policy_contract())


def test_frozen_peer_cannot_be_silently_changed_to_route3():
    peer = choice.peer_policy_contract(); peer['later_preference'] = 'prefer_3'
    peer['sha256'] = choice.digest({k: v for k, v in peer.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='frozen_peer_contract'):
        choice.verify_public_peer_history(bundle(), 1, peer)


def test_A_seed_revalidates_fresh_endpoints_and_uses_only_owned_requests(monkeypatch):
    calls = []
    def checked(view, command, received, **kwargs):
        calls.append(kwargs)
        return {'status': 'conditional_validated_later_v3_data', 'bundle': bundle(), 'envelopes': {}}
    monkeypatch.setattr(choice.repeated, 'validate_endpoints', checked)
    e = evidence(); frozen = copy.deepcopy(e)
    seed = choice.build_seed(e, return_index=1, peer_policy_contract=choice.peer_policy_contract())
    assert calls[0]['phase'] == 'cycle_return' and calls[0]['own_actions'] == [('A-return-0', 'transfer')]
    assert seed['owner'] == 'A' and seed['schema'] == choice.VERSION and seed['retained_preferences'] == {}
    assert seed['online_executable'] is False and seed['native_protection_certified'] is False
    assert seed['retained_preference_derivation']['peer_private_outbox_read'] is False and e == frozen


@pytest.mark.parametrize('change,reason', [('foreign_owned', 'only_owned_requests'),
    ('private_outbox', 'peer_private_state_forbidden'), ('owner_B', 'A_current_evidence')])
def test_foreign_private_actor_state_is_rejected_before_endpoint_use(monkeypatch, change, reason):
    def forbidden(*args, **kwargs):
        raise AssertionError('private/foreign state must fail before endpoint validation')
    monkeypatch.setattr(choice.repeated, 'validate_endpoints', forbidden)
    e = evidence()
    if change == 'foreign_owned':
        e['own_outbox']['q']['request']['owner_id'] = 'B'
    elif change == 'private_outbox':
        e['B_private_outbox'] = {}
    else:
        e['owner'] = 'B'
    with pytest.raises(ValueError, match=reason):
        choice.build_seed(e, return_index=1, peer_policy_contract=choice.peer_policy_contract())


def test_fresh_endpoint_failure_cannot_be_promoted_to_prediction(monkeypatch):
    monkeypatch.setattr(choice.repeated, 'validate_endpoints', lambda *args, **kwargs:
        {'status': 'unknown', 'reasons': ['stale_capture']})
    result = choice.evaluate(evidence(), choice.ACTIONS, return_index=1,
        peer_policy_contract=choice.peer_policy_contract())
    assert result['status'] == 'unknown' and result['candidate_results'] == {}
    assert 'stale_capture' in result['reasons'][0] and result['execution_authority'] is False


def test_frozen_peer_hook_is_later_reuse_only():
    projection = object.__new__(choice.Projection)
    assert projection.peer_route_choice({'node': 7, 'mode': 'loaded', 'job': 'reuse2'}) == 8
    with pytest.raises(ValueError, match='peer_lifecycle'):
        projection.peer_route_choice({'node': 7, 'mode': 'loaded', 'job': 'reuse1'})
