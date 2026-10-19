"""Detached A return-choice domain; no native/controller execution authority.

Only return indices 1 and 2 (the second and third returns) are candidates.
The historical first-return absolute 7.84 contract is deliberately untouched.
Future B preference 8 is an explicit conditional peer continuation, not proof
that a later native collection or guard will succeed. Any native integration
must record and check that continuation and its full original-job protection.
"""
from __future__ import annotations

import copy

from . import foundation_repeated_domain as repeated
from . import foundation_later_seed as old_seed

VERSION = 'g31.foundation.return_choice_domain.v1'
EVIDENCE_SCHEMA = 'g31.foundation.return_choice_evidence.v1'
PEER_SCHEMA = 'g31.foundation.return_choice_peer_B.v1'
ACTIONS = ('return_now', 'return_delay_0_5')
require, finite, plain, digest = repeated.require, repeated.finite, repeated.plain, repeated.digest


def peer_policy_contract():
    """Shared preregistered policy contract; this function creates no authority."""
    result = {'schema': PEER_SCHEMA, 'owner': 'B',
        'initial_and_reuse1': 'unchanged_original_fixed_incumbent',
        'later_preference': 'prefer_8', 'route_source': 7, 'route_target': 8, 'route_tray': 'L',
        'route_message_delay': .01, 'route_lifetime': 5.,
        'E_supply_recovery': 'unchanged_immutable_retry_receiving_full_recovery',
        'E_transfer_source': 5, 'E_transfer_destination': 1,
        'actual_authority': 'fresh_owner_local_native_contract_and_full_original_per_job_guard',
        'guard_failure': 'original_fixed_fallback_preserved_and_prediction_continuation_not_verified',
        'projection_scope': 'conditional_on_future_B_prefer8_admissions; not_future_guard_certification',
        'actor_may_read_peer_private_outbox': False,
        'physical_contract_changes': [], 'strict_protection_tolerance': 0.}
    result['sha256'] = digest(result)
    return result


def validate_peer_contract(contract):
    require(contract == peer_policy_contract(), 'return_choice_frozen_peer_contract')


def action_contract(now, action_id, return_index):
    """R2 not-before times, never a retrospective change to an existing request."""
    require(type(return_index) is int and return_index in (1, 2), 'return_choice_second_or_third_only')
    require(finite(now) and 0 <= now < 39. and action_id in ACTIONS, 'return_choice_time_or_action')
    earliest = now + (.5 if action_id == 'return_delay_0_5' else 0.)
    require(max(now + .01, earliest) <= 39., 'return_choice_expiry')
    return {'schema': VERSION, 'owner': 'A', 'return_index': return_index, 'action_id': action_id,
        'semantic': {'operation_kind': 'transfer', 'source': 6, 'destination': 7, 'tray_id': 'L',
            'earliest_departure': earliest,
            'earliest_legal_arrival': max(now + .01, earliest) + .1 + 2. + .1},
        'request_fields': {'tray_id': 'L', 'source': 6, 'destination': 7,
            'earliest_departure': earliest, 'expiry': 39., 'message_delay': .01},
        'online_executable': False, 'native_execution_authority': False,
        'physical_delay_is_exactly_half_second': False}


def verify_public_peer_history(bundle, return_index, peer_contract):
    """Only already-delivered source actions; never B's Python/private outbox.

    A received transfer ACK occurs after that transfer's last entry. Waiting a
    further .5 after delivery therefore conservatively expires the short 5→1
    edge headway. Complete source action coverage and the unchanged frozen E
    policy are required; unknown/pending transfers cannot be silently omitted.
    """
    validate_peer_contract(peer_contract)
    require(type(return_index) is int and return_index in (1, 2), 'return_choice_second_or_third_only')
    sources = bundle['source_records']
    require(len(sources) == 2 and {s['owner'] for s in sources} == {'A', 'B'}, 'return_choice_source_domain')
    floor = min(s['captured_at'] for s in sources)
    require(finite(floor) and 0 <= floor <= bundle['now'], 'return_choice_capture_floor')
    for source in sources:
        require(source['unresolved_tray_request_ids'] == [] and source['known_faults'] == [],
                'return_choice_unresolved_source')
        rows = source['submitted_physical_actions']
        require(source['submitted_physical_request_ids'] == [r['request_id'] for r in rows]
                and len({r['request_id'] for r in rows}) == len(rows), 'return_choice_complete_source_actions')
        for row in rows:
            ack = row['last_delivered_ack']
            require(row['source_owner'] == source['owner'] and row['kind'] in repeated.old_guard.PHYSICAL_KINDS
                and type(ack['sequence']) is int and ack['sequence'] > 0
                and ack['status'] in repeated.old_guard.TERMINAL_BY_KIND[row['kind']]
                and finite(ack['delivered_at']) and 0 <= ack['delivered_at'] < floor,
                'return_choice_terminal_delivered_actions')
    peer = next(s for s in sources if s['owner'] == 'B')
    transfers = [r for r in peer['submitted_physical_actions'] if r['kind'] == 'transfer']
    received = [r for r in transfers if r['last_delivered_ack']['status'] == 'received']
    require(transfers and len(received) == 1, 'return_choice_single_actual_E_receiving_history')
    for row in transfers:
        ack = row['last_delivered_ack']
        require(ack['status'] == 'rejected' or ack['status'] == 'received'
            and ack['delivered_at'] + .5 < floor, 'return_choice_E_headway_not_expired')
    tray = bundle['trays']['L']
    require((tray['node'], tray['mode'], tray['business_bag_id'], tray['edge_to'], tray['reception_node'])
            == (6, 'empty', '', -1, -1), 'return_choice_current_empty_L')
    require(tray['available_at'] <= floor and tray['committed_prefix'] == [6], 'return_choice_released_L')
    completed_reuse = {key for key in bundle['completed_prefix'] if key.startswith('reuse')}
    require(completed_reuse == {f'reuse{i}' for i in range(1, return_index + 1)},
            'return_choice_actual_completed_cycle')
    e = bundle['trays']['E']
    require(e['node'] != 5 and (e['business_bag_id'] == 'blocker'
        or 'blocker' in bundle['completed_prefix'] and e['node'] == 10 and e['mode'] == 'empty'),
        'return_choice_E_current_lifecycle')
    return {'schema': VERSION, 'peer_source_identity': peer['identity'], 'capture_floor': floor,
        'received_transfer_request_id': received[0]['request_id'],
        'headway_expired_by': received[0]['last_delivered_ack']['delivered_at'] + .5,
        'peer_private_outbox_read': False,
        'retained_preference_scope': 'L currently empty at6; future frozen B route8 overwrites at7'}


def build_seed(evidence, *, return_index, peer_policy_contract):
    validate_peer_contract(peer_policy_contract)
    require(type(evidence) is dict and evidence.get('schema') == EVIDENCE_SCHEMA
            and evidence.get('owner') == 'A' and evidence.get('phase') == 'cycle_return',
            'return_choice_A_current_evidence')
    require(not set(evidence).intersection({'peer_outbox', 'peer_calls', 'B_outbox', 'B_private_outbox'}),
            'return_choice_peer_private_state_forbidden')
    endpoints, pending = evidence['information']['raw_endpoints'], evidence['collection']
    require(endpoints['view']['owner_id'] == 'A' and endpoints['view']['now'] == evidence['at'],
            'return_choice_current_owner_epoch')
    require(all(row['request']['owner_id'] == 'A' for row in evidence['own_outbox'].values())
            and all(row['request']['owner_id'] == 'A' for row in evidence['own_calls']),
            'return_choice_only_owned_requests')
    checked = repeated.validate_endpoints(endpoints['view'], endpoints['command'], endpoints['received'],
        retained=evidence['retained'], own_actions=sorted((key, row['kind'])
            for key, row in evidence['own_outbox'].items() if row['kind'] in repeated.old_guard.PHYSICAL_KINDS),
        phase='cycle_return', own_request_id=pending['request_id'], peer_message_id=pending['peer_message'],
        collection_started_at=pending['at'], policy_quiet_since=pending['policy_quiet_since'],
        own_request=evidence['own_outbox'][pending['request_id']]['request'])
    require(checked['status'] == 'conditional_validated_later_v3_data',
            'return_choice_current_endpoints:' + str(checked.get('reasons')))
    bundle = plain(checked['bundle'])
    require(str(bundle['case']).startswith('hold3_'), 'return_choice_registered_hold3_only')
    history = verify_public_peer_history(bundle, return_index, peer_policy_contract)
    returns = [r for r in evidence['own_outbox'].values() if r['kind'] == 'transfer']
    require(len(returns) == return_index and all(r['request']['tray_id'] == 'L'
        and r['request']['source'] == 6 and r['request']['destination'] == 7
        and r['terminal'] and r['ack']['status'] == 'received' for r in returns),
        'return_choice_all_prior_own_returns_received')
    bundle.update(owner_pending_tray_requests=[], protocol=plain(old_seed.physics.previous.PROTOCOL))
    entries = [entry for envelope in checked['envelopes'].values()
               for entry in envelope['capture']['extension']['source_observed_inflight']]
    seed = {'schema': VERSION, 'status': 'conditional_current_seed', 'at': evidence['at'],
        'phase': 'cycle_return', 'owner': 'A', 'return_index': return_index,
        'bundle': bundle, 'entry_receipts': entries, 'retained_preferences': {},
        'retained_route_history': [], 'retained_preference_derivation': history,
        'peer_policy_contract': plain(peer_policy_contract), 'evidence_sha256': digest(evidence),
        'source_captured_at': history['capture_floor'], 'action_ids': list(ACTIONS),
        'online_executable': False, 'native_protection_certified': False}
    seed['seed_sha256'] = digest(seed)
    return seed


class Projection(repeated.Projection):
    def __init__(self, seed, action_id):
        require(seed['schema'] == VERSION and seed['owner'] == 'A' and seed['phase'] == 'cycle_return',
                'return_choice_projection_seed')
        validate_peer_contract(seed['peer_policy_contract'])
        self.selected_return = action_contract(seed['at'], action_id, seed['return_index'])
        require(callable(getattr(repeated.Projection, 'peer_route_choice', None)),
                'return_choice_peer_hook_not_yet_available')
        super().__init__(seed, action_id)

    def peer_route_choice(self, tray):
        require(tray['node'] == 7 and tray['mode'] == 'loaded' and tray['job'].startswith('reuse')
                and tray['job'] != 'reuse1', 'return_choice_peer_lifecycle')
        return 8

    def seed_current(self):
        super().seed_current()
        requests = [r for r in self.requests if r['tray'] == 'L']
        require(len(requests) == 1 and requests[0]['earliest'] == self.selected_return['request_fields']['earliest_departure'],
                'return_choice_projected_R2_not_before')


def evaluate(evidence, action_ids, *, return_index, peer_policy_contract):
    """Two detached conditional predictions; callers retain strict guard/authority."""
    try:
        old_seed.physics.check_sources()
        require(type(action_ids) in (list, tuple) and 0 < len(action_ids) <= 2
            and len(set(action_ids)) == len(action_ids) and all(a in ACTIONS for a in action_ids),
            'return_choice_candidate_budget')
        seed = build_seed(evidence, return_index=return_index, peer_policy_contract=peer_policy_contract)
        before, results = digest(seed), {}
        for action in action_ids:
            engine = Projection(seed, action)
            result = engine.run()
            require(digest(seed) == before, 'return_choice_candidate_mutated_seed')
            require(result['status'] == 'conditional_prediction'
                and set(result['completion']) == set(seed['bundle']['jobs'])
                and all(finite(v) and v >= 0 for v in result['completion'].values()),
                'return_choice_full_job_prediction')
            results[action] = {**result, 'action_id': action, 'model_version': VERSION,
                'projected_commands': plain(engine.commands), 'projected_transfers': plain(engine.requests),
                'peer_policy_contract_sha256': peer_policy_contract['sha256'],
                'future_peer_guard_success_certified': False, 'online_executable': False,
                'native_protection_certified': False}
        return {'status': 'conditional_current_seed', 'seed': seed, 'candidate_results': results,
            'model_version': VERSION, 'execution_authority': False,
            'actual_peer_continuation_requires_native_audit': True}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return {'status': 'unknown', 'reasons': [str(error)], 'candidate_results': {},
            'model_version': VERSION, 'execution_authority': False}
