"""One fresh information pair per phase; finite fixed actions, no predictor.

This changes the communication policy and may delay the first empty return.
Old normal-exchange predictions do not certify this policy. Native physics keeps
running; only new physical admissions are withheld while collecting. All final
endpoint, action-union, current-owner and conditional stability guards remain.
The supplied-data helpers below are not native authority or protection proofs.
"""
from __future__ import annotations

import copy
import math
from . import research_live_obligation_native_domain as prior
from . import live_obligation_recollection_adapter as adapter
from . import live_obligation_lifecycle_state_v2 as lifecycle

bound = prior.bound
PHYSICAL_KINDS = lifecycle.PHYSICAL_KINDS
TERMINAL_BY_KIND = lifecycle.TERMINAL_BY_KIND
TARGET_FIELDS = ('tray_id', 'node', 'mode', 'business_bag_id', 'generation',
                 'traversal_id', 'edge_from', 'edge_to', 'reception_node',
                 'committed_prefix', 'available_at')
DECIDING_PHASES = ('first_return', 'first_reuse_route')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def sequential_epochs(start):
    require(finite(start) and start >= 0, 'invalid_start')
    epochs = [start]
    for _ in range(5):
        epochs.append(epochs[-1] + .01)
    return dict(zip(('start', 'own_capture', 'invite_delivery', 'peer_capture',
                     'pair_delivery', 'physical_wire'), epochs))


def local_target(view, trigger, phase):
    rows = [t for t in view['trays'] if t['tray_id'] == 'L']
    require(len(rows) == 1, 'missing_or_duplicate_current_L')
    tray = rows[0]
    require(all(tray[f] == trigger[f] for f in TARGET_FIELDS), 'original_L_changed')
    require(all(type(tray[f]) is int and tray[f] >= 0 for f in ('generation', 'traversal_id')),
            'invalid_target_identity')
    require(tray['edge_from'] == tray['edge_to'] == tray['reception_node'] == -1,
            'L_already_committed')
    expected = (6, 'empty', '') if phase == 'first_return' else (7, 'loaded', 'reuse1')
    require((tray['node'], tray['mode'], tray['business_bag_id']) == expected,
            'L_not_in_original_phase')
    require(tray['committed_prefix'] == [tray['node']] and finite(tray['available_at'])
            and 0 <= tray['available_at'] <= view['now'], 'L_not_locally_available')
    return tray


def _captures(information, pending, owner):
    endpoints = information['raw_endpoints']
    ack = endpoints['command']['last_delivered_ack']
    own_envelope = ack['planning_snapshot_v3']
    own = own_envelope['capture']['capture_v2']['local_capture']
    selected = [e for e in endpoints['received'] if
                e['capture']['capture_v2']['local_capture']['message_id'] == pending['peer_message']]
    require(len(selected) == 1, 'missing_exact_old_peer')
    peer_envelope = selected[0]
    peer = peer_envelope['capture']['capture_v2']['local_capture']
    require(own['source_owner'] == owner and peer['source_owner'] != owner
            and own['target_owner'] == peer['source_owner'] and peer['target_owner'] == owner,
            'source_pair_owner')
    floor = min(own['captured_at'], peer['captured_at'])
    # This helper consumes only a sealed, already validated native read on the
    # policy path. Recheck exact identity here rather than minting it from flags.
    require(endpoints['command']['request_id'] == pending['request_id']
            and ack['status'] == 'delivered' and ack['result_id'] == own['message_id']
            and own['captured_at'] == ack['executed_at']
            and own_envelope['delivered_at'] == ack['completed_at']
            and ack['delivered_at'] <= endpoints['view']['now'], 'old_self_ack_binding')
    for envelope, local in ((own_envelope, own), (peer_envelope, peer)):
        extension = envelope['capture']['capture_v2']['extension']
        actions = extension['submitted_physical_actions']
        coverage = extension['action_coverage']
        require(coverage['submitted_request_ids'] == [a['request_id'] for a in actions]
                and len(actions) == len({a['request_id'] for a in actions})
                and coverage['complete_for_declared_scope'] is True
                and coverage['unresolved_request_ids'] == []
                and coverage['through'] == local['captured_at'], 'old_action_coverage')
        require(extension['source_owner'] == local['source_owner'], 'old_action_owner')
        for action in actions:
            a = action['last_delivered_ack']
            require(action['source_owner'] == local['source_owner']
                    and action['kind'] in PHYSICAL_KINDS
                    and type(a['sequence']) is int and a['sequence'] > 0
                    and a['status'] in TERMINAL_BY_KIND[action['kind']]
                    and finite(a['delivered_at']) and 0 <= a['delivered_at'] < floor,
                    'old_action_not_terminal_before_union')
    return own, peer, floor


def retry_admission(information, pending, view, owned_rows):
    """Pure admissibility screen only; actual-origin seal is checked by policy."""
    try:
        phase = pending['phase']; owner = view['owner_id']; now = view['now']
        require(phase in DECIDING_PHASES and owner == ('A' if phase == 'first_return' else 'B'),
                'wrong_deciding_phase')
        require(type(pending.get('recollection_index')) is int and pending['recollection_index'] == 0,
                'one_fresh_pair_already_used')
        require(finite(now) and finite(pending['at']) and 0 <= pending['at'] <= now, 'invalid_current_time')
        require(information['raw_endpoints']['view'] == view, 'not_the_collected_current_view')
        require(information.get('status') == 'unknown', 'not_a_failed_collection')
        own, peer, floor = _captures(information, pending, owner)
        captured_actions = information['raw_endpoints']['command']['last_delivered_ack'][
            'planning_snapshot_v3']['capture']['capture_v2']['extension']['submitted_physical_actions']
        require(sorted((key, row['kind']) for key, row in owned_rows.items() if row['kind'] in PHYSICAL_KINDS)
                == sorted((a['request_id'], a['kind']) for a in captured_actions),
                'current_physical_action_set_changed')
        current = local_target(view, pending['trigger_tray'], phase)
        own_l = [t for t in own['trays'] if t['tray_id'] == 'L']
        require(len(own_l) == 1 and all(own_l[0][f] == current[f] for f in TARGET_FIELDS),
                'current_L_differs_from_source_capture')
        reasons = information.get('reasons')
        if reasons == ['owned_tray_changed_after_v3_capture']:
            trigger_reason = 'actual_owned_tray_changed_after_capture'
        else:
            require(reasons == ['unsupported_later_model_state']
                    and information.get('bundle', {}).get('reasons') == ['stable_committed_local_service'],
                    'not_a_supported_recollection_reason')
            crossed = []
            for source in (own, peer):
                for t in source['trays']:
                    expected = {'E': ('receiver', 4, [1, 3, 4]),
                                'P': ('blocker', 10, [9, 3, 10])}.get(t['tray_id'])
                    if expected is None: continue
                    if (t['business_bag_id'], t['node'], t['committed_prefix']) != expected: continue
                    if (t['mode'] == 'loaded' and t['edge_from'] == t['edge_to'] == -1
                            and t['service_ready_known'] is True
                            and t['ready_kind'] == 'committed_local_service_end'
                            and finite(t['service_ready_at']) and floor <= t['service_ready_at'] <= now):
                        crossed.append({'tray_id': t['tray_id'], 'source_owner': source['source_owner'],
                                        'old_service_bound': t['service_ready_at']})
            require(crossed, 'no_supported_deadline_crossed_collection')
            trigger_reason = 'known_stationary_service_crossed_collection'
        for row in owned_rows.values():
            require(row['request']['owner_id'] == owner, 'foreign_owned_request')
            if row['kind'] not in PHYSICAL_KINDS: continue
            a = row.get('ack', {})
            require(row['terminal'] is True and a.get('status') in TERMINAL_BY_KIND[row['kind']]
                    and finite(a.get('delivered_at')) and 0 <= a['delivered_at'] <= now,
                    'current_owned_physical_action_pending')
        epochs = sequential_epochs(now)
        service_bound = None
        if phase == 'first_reuse_route':
            t = own_l[0]; service_bound = t['service_ready_at']
            require(t['service_ready_known'] is True and t['ready_kind'] == 'committed_local_service_end'
                    and finite(service_bound) and epochs['physical_wire'] < service_bound,
                    'insufficient_current_L_service_window')
        else:
            require(epochs['physical_wire'] < 39., 'insufficient_transfer_expiry')
        return {'status': 'conditional_retry_admissible', 'reason': trigger_reason,
                'nominal_epochs': epochs, 'original_target': copy.deepcopy(pending['trigger_tray']),
                'retained_own_service_bound': service_bound, 'native_success_certified': False,
                'actual_pair_still_required': True}
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return {'status': 'not_admitted', 'reason': str(error), 'native_success_certified': False}


class PhaseReplyBudget:
    """Two actual monotone invitations per decision phase; preflight once."""
    def __init__(self): self.rows = {}

    def admit(self, phase, local):
        try:
            limit = 2 if phase in DECIDING_PHASES else 1 if phase == 'reuse1_loading_ack_refresh' else 0
            history = self.rows.get(phase, [])
            identity, at, sequence = local['message_id'], local['captured_at'], local['publication_sequence']
            require(type(identity) is str and identity and finite(at) and at >= 0
                    and type(sequence) is int and sequence > 0, 'invalid_invitation_identity')
            require(len(history) < limit and all(identity != r['message_id'] for r in history),
                    'invitation_budget_or_duplicate')
            require(not history or at > history[-1]['captured_at'] and sequence > history[-1]['publication_sequence'],
                    'nonmonotone_invitation')
            self.rows.setdefault(phase, []).append({'message_id': identity, 'captured_at': at,
                                                    'publication_sequence': sequence})
            return True
        except (KeyError, TypeError, ValueError): return False


def fixed_choice(information, vector):
    if not adapter.is_native_collected(information):
        return {'status': 'unknown_unverified_or_unsupported_input', 'selected_action': None}
    return {'status': 'predeclared_finite_counterfactual_action',
            'selected_action': {'return_delay': vector['return_delay'],
                               'reuse_next': 8 if vector['later_action'] == 'prefer_8' else None},
            'vector': copy.deepcopy(vector), 'predicted_protection': None,
            'native_model_protection_certified': False}


def attempt_evidence(policies):
    """Required new-runner success/exception export; no capability attributes."""
    return {owner: adapter.json_data(policy.collection_attempts)
            for owner, policy in policies.items()}


class OwnerPolicy(prior.OwnerPolicy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reply_budget = PhaseReplyBudget()
        self.collection_attempts = []

    def begin(self, phase, tray, root):
        super().begin(phase, tray, root)
        self.pending['recollection_index'] = 0
        self.pending['policy_quiet_since'] = self.pending['at']

    def exchange(self, view):
        for envelope in self.session.protocol_planning_snapshots_v3(self.owner):
            local = envelope['capture']['capture_v2']['local_capture']; identity = local['message_id']
            if identity in self.seen_messages: continue
            self.seen_messages.add(identity)
            if self.pending:
                if local['captured_at'] >= self.pending['at']:
                    self.pending['peer_message'] = identity
                self.exchanges.append({'at': view['now'], 'kind': 'received_for_pending_collection',
                                       'message': copy.deepcopy(envelope)})
                continue
            phase = bound.invitation_phase(envelope, self.owner, view['now'])
            if not self.reply_budget.admit(phase, local):
                self.exchanges.append({'at': view['now'], 'kind': 'not_a_new_bounded_phase_invitation',
                                       'message': copy.deepcopy(envelope)})
                continue
            self.answered_phases.add(phase)
            causal = {'relation': 'result_handling', 'continuation_parent_roots': [],
                'delivered_parent_message': {'message_id': identity, 'source_owner': local['source_owner'],
                    'captured_at': local['captured_at'], 'delivered_at': envelope['delivered_at']},
                'cross_owner_creating_request_root': 'unknown_not_transmitted'}
            refresh = []
            if phase == 'reuse1_loading_ack_refresh' and self.owner == 'A':
                for request_id, row in self.client.owned('A').items():
                    request = row['request']
                    if (row['kind'] == 'transfer' and request.get('tray_id') == 'L'
                            and request.get('source') == 6 and request.get('destination') == 7
                            and not row['terminal']):
                        self.client.send(request_id, retry=True); refresh.append(request_id)
            if refresh:
                causal['continuation_parent_roots'] = [self.client.creations[i]['creating_root'] for i in refresh]
                causal['immutable_retry_request_ids'] = refresh
                self.pending_reply = {'phase': phase, 'causal': causal, 'envelope': copy.deepcopy(envelope),
                                      'waiting': refresh}
                self.exchanges.append({'at': view['now'], 'kind': 'immutable_ack_refresh_before_reply',
                    'message': copy.deepcopy(envelope), 'request_ids': refresh, 'causal': copy.deepcopy(causal)})
            else:
                reply = self.publication('reply', causal)
                self.hold_new_admissions_after_reply(phase, identity, view['now'])
                self.exchanges.append({'at': view['now'], 'kind': 'reply', 'message': copy.deepcopy(envelope),
                                       'request_id': reply})

    def _begin_recollection(self, pending, screen, information, view):
        require(pending.get('recollection_index', 0) == 0, 'recollection_budget')
        causal = {'relation': 'replacement_replan', 'continuation_parent_roots': [pending['root']],
            'predecessor_protocol_id': pending['request_id'], 'collection_phase': pending['phase'],
            'actual_failed_collection_reason': copy.deepcopy(information.get('reasons', [])),
            'same_original_target': copy.deepcopy(pending['trigger_tray']), 'fresh_pair_index': 1}
        identity = self.publication('recollect-' + pending['phase'], causal)
        deadline = view['now'] + bound.COLLECTION_LIMIT
        if screen['retained_own_service_bound'] is not None:
            deadline = min(deadline, screen['retained_own_service_bound'])
        self.pending = {**copy.deepcopy(pending), 'at': view['now'], 'deadline': deadline,
            'request_id': identity, 'peer_message': None, 'recollection_index': 1,
            'original_request_id': pending['request_id'], 'retry_admission': copy.deepcopy(screen)}
        self.quiet_periods.append({'at': view['now'], 'through': deadline,
            'reason': 'single_fresh_collection_pending', 'phase': pending['phase'],
            'native_physics_paused': False})

    def decide_pending(self, view):
        pending = self.pending
        if not pending or view['now'] < self.peer_quiet_until: return
        own = self.client.rows[pending['request_id']].get('ack', {})
        pair_ready = own.get('status') == 'delivered' and pending['peer_message'] is not None
        if not pair_ready and view['now'] < pending['deadline']: return
        information = adapter.collect_native(self.native, self.session, self.owner, pending['request_id'],
            accepted=self.accepted, ledger=self.ledger, owned_client_rows=self.client.owned(self.owner),
            phase=pending['phase'], peer_message_id=pending['peer_message'], collection_started_at=pending['at'],
            policy_quiet_since=pending['policy_quiet_since'])
        screen = {'status': 'not_admitted', 'reason': 'actual_failed_owner_read_required'}
        if adapter.is_native_attempt(information) and information.get('status') == 'unknown':
            screen = retry_admission(information, pending, view, self.client.owned(self.owner))
        attempt = {'at': view['now'], 'phase': pending['phase'], 'collection': copy.deepcopy(pending),
            'information': adapter.json_data(information), 'actual_local_view': copy.deepcopy(view),
            'predecision_call_prefix_count': len(self.client.calls), 'retry_admission': screen}
        self.collection_attempts.append(attempt)
        if screen['status'] == 'conditional_retry_admissible':
            self._begin_recollection(pending, screen, information, view)
            attempt['disposition'] = 'one_fresh_pair_requested'
            attempt['new_request_id'] = self.pending['request_id']
            return
        decision = fixed_choice(information, self.method)
        selected = decision.get('selected_action'); fallback = selected is None
        action = selected or {'reuse_next': None, 'return_delay': 0.}
        causal = {'relation': 'fallback' if fallback else 'result_handling',
            'continuation_parent_roots': [pending['root']], 'predecessor_protocol_id': pending['request_id'],
            'delivered_peer_message_id': pending['peer_message'], 'collection_started_at': pending['at'],
            'predeclared_counterfactual_vector': copy.deepcopy(self.method),
            'recollection_index': pending['recollection_index']}
        actual = None; local_stage = False; final_reason = None; demand = None
        try:
            tray = local_target(view, pending['trigger_tray'], pending['phase'])
            if pending['phase'] == 'first_return':
                earliest = prior.return_earliest(view['now'], action['return_delay'], 0)
                require(max(view['now'] + .01, earliest) < 39., 'final_transfer_expiry')
                demand = prior.v1.latest_demand(view, 'B')
                if demand and any(j['origin'] == 7 for j in demand['jobs']):
                    local_stage = True
            else:
                if not fallback:
                    bound_at = information['bundle']['trays']['L']['service_ready_at']
                    require(view['now'] + .01 < bound_at, 'final_route_wire_outside_service_window')
                local_stage = True
        except (KeyError, TypeError, ValueError) as error:
            final_reason = str(error)
        # Submission/runtime exceptions must reach the runner's partial-data
        # handler, not be disguised as an unsuccessful local predicate.
        if local_stage:
            if pending['phase'] == 'first_return':
                actual = self.return_tray(view, tray, demand, action['return_delay'], causal)
            else:
                actual = self.route_tray(view, tray, action['reuse_next'], causal)
        executed = (not fallback and local_stage and (actual is not None or
                    pending['phase'] == 'first_reuse_route' and action['reuse_next'] is None))
        self.decisions.append({'at': view['now'], 'phase': pending['phase'], 'collection': copy.deepcopy(pending),
            'information': information, 'decision': decision, 'fallback_used': fallback,
            'executed_first_action': action, 'native_request_id': actual, 'actual_local_view': copy.deepcopy(view),
            'predecision_call_prefix_count': attempt['predecision_call_prefix_count'],
            'selected_action_admitted': executed, 'final_local_guard_reason': final_reason,
            'future_proposal_component_executed_without_replan': False})
        attempt['disposition'] = 'final_decision_no_more_recollection'
        self.pending = None
