"""Current collection capabilities stay here; actors receive detached data only."""
from __future__ import annotations

import hashlib
import json
import math
import time

from . import live_obligation_historical_adapter as historical
from . import live_obligation_recollection_policy_v2 as policy_guards
from . import research_live_obligation_native_domain as physical
from . import live_obligation_native_view_v2 as representation


ACTOR_SCHEMA = 'g31.foundation.later_actor.v1'
EVIDENCE_SCHEMA = 'g31.foundation.later_evidence.v1'
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
PHASE_ACTIONS = {'first_return': ('return_now', 'return_not_before_7_84'),
    'first_reuse_route': ('native_default', 'prefer_8')}


def require(condition, reason):
    if not condition:
        raise ValueError('foundation_later:' + reason)


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def encoding(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoding(value).encode()).hexdigest()


def known(completion):
    return type(completion) is dict and set(completion) == set(JOBS) and all(
        type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in completion.values())


def initial_reference(record):
    provider = record['selection']['provider_evidence']
    rows = [row for row in provider['rows'] if row['candidate_index'] == 4]
    require(len(rows) == 1 and rows[0]['status'] == 'conditional_forecast' and known(rows[0]['completion']),
        'known_original_incumbent_reference')
    require(provider['owner'] == record['owner']
        and provider['initial_public_sha256'] == record['collection']['public_sha256'], 'initial_reference_origin')
    return {'owner': record['owner'], 'completion': plain(rows[0]['completion']),
        'initial_public_sha256': provider['initial_public_sha256'], 'candidate_index': 4,
        'scope': 'Original initial conditional forecast, not an actual service commitment or native future truth.',
        'native_protection_certified': False, 'reference_refresh_allowed': False}


def v3_messages(received, owner, now):
    result = []
    for envelope in received:
        local = envelope['capture']['capture_v2']['local_capture']
        require(local['target_owner'] == owner and local['source_owner'] != owner
            and envelope['delivered_at'] <= now, 'v3_wrong_owner_or_undelivered')
        result.append({'envelope': plain(envelope), 'message_id': local['message_id'],
            'source_owner': local['source_owner'], 'target_owner': local['target_owner'],
            'status': envelope['status'], 'captured_at': local['captured_at'],
            'delivered_at': envelope['delivered_at'], 'valid_until': local['valid_until'],
            'fresh': envelope['status'] == 'conditional' and local['captured_at'] <= now < local['valid_until']})
    return result


def actor_observation(evidence):
    information = evidence['information']
    endpoints = information['raw_endpoints']
    pending = evidence['collection']
    owner, now = evidence['owner'], evidence['at']
    require(endpoints['view']['owner_id'] == owner and endpoints['view']['now'] == now, 'actor_view_owner_time')
    return {'schema': ACTOR_SCHEMA, 'owner': owner, 'phase': evidence['phase'], 'at': now,
        'timing_mode': 'offline_sync', 'collection': {'request_id': pending['request_id'],
            'peer_message_id': pending['peer_message'], 'started_at': pending['at'], 'collected_at': now},
        'local_view': plain(endpoints['view']),
        'delivered_v3': v3_messages(endpoints['received'], owner, now),
        'own_outbox': plain(evidence['own_outbox']), 'collection_status': information['status'],
        'actor_information_scope': 'current own endpoint, actually delivered v3 data and own immutable requests/ACKs',
        'model_predictions_included': False, 'privileged_evaluator_state_included': False}


def semantic_action(phase, action_id, now):
    require(action_id in PHASE_ACTIONS[phase], 'action_not_in_phase')
    if phase == 'first_return':
        delay = 0. if action_id == 'return_now' else .5
        return {'kind': 'transfer', 'return_delay_label': delay,
            'absolute_earliest_departure': physical.return_earliest(now, delay, 0),
            'source': 6, 'destination': 7, 'tray_id': 'L'}
    return {'kind': 'no_command' if action_id == 'native_default' else 'route',
        'next': None if action_id == 'native_default' else 8, 'from': 7, 'tray_id': 'L',
        'default_does_not_clear_existing_preference': True}


def protected(prediction, reference):
    if prediction.get('status') != 'conditional_prediction' or not known(prediction.get('completion')):
        return {'status': 'unknown', 'per_job_delta': None}
    delta = {job: prediction['completion'][job] - reference['completion'][job] for job in JOBS}
    return {'status': 'passed' if all(value <= 0 for value in delta.values()) else 'rejected', 'per_job_delta': delta}


class LaterControl:
    def __init__(self, policy, reference, *, model=None, mode='guarded', phases=tuple(PHASE_ACTIONS)):
        require(mode in ('guarded', 'diagnostic_intervention'), 'declared_later_mode')
        require(set(phases) <= set(PHASE_ACTIONS), 'declared_later_phases')
        original = policy.decide_pending
        adapter = original.__func__.__globals__['adapter']
        require(type(adapter) is historical.OwnerCollectionAdapter and adapter._client is policy.client
            and adapter._session is policy.session and adapter._owner == policy.owner, 'actual_owner_bound_adapter')
        require(reference['owner'] == policy.owner and known(reference['completion'])
            and reference['native_protection_certified'] is False and reference['reference_refresh_allowed'] is False,
            'original_conditional_reference')
        self.policy, self.adapter, self.original = policy, adapter, original
        self.model, self.mode, self.phases = model, mode, tuple(phases)
        self.reference = plain(reference)
        self.reference_sha = digest(self.reference)
        self.offer = None
        self.transitions = []
        self.collection_failures = []
        policy.decide_pending = self.collect

    def collect(self, view):
        policy = self.policy
        pending = policy.pending
        if not pending or pending['phase'] not in self.phases:
            return self.original(view)
        require(self.offer is None, 'unconsumed_later_offer')
        if view['now'] < policy.peer_quiet_until:
            return
        own = policy.client.rows[pending['request_id']].get('ack', {})
        pair_ready = own.get('status') == 'delivered' and pending['peer_message'] is not None
        if not pair_ready and view['now'] < pending['deadline']:
            return
        started = time.perf_counter_ns()
        information = self.adapter.collect_native(policy.native, policy.session, policy.owner, pending['request_id'],
            accepted=policy.accepted, ledger=policy.ledger, owned_client_rows=policy.client.owned(policy.owner),
            phase=pending['phase'], peer_message_id=pending['peer_message'], collection_started_at=pending['at'],
            policy_quiet_since=pending['policy_quiet_since'])
        screen = {'status': 'not_admitted', 'reason': 'actual_failed_owner_read_required'}
        if self.adapter.is_native_attempt(information) and information.get('status') == 'unknown':
            screen = policy_guards.retry_admission(information, pending, view, policy.client.owned(policy.owner))
        attempt = {'at': view['now'], 'phase': pending['phase'], 'collection': plain(pending),
            'information': self.adapter.json_data(information), 'actual_local_view': plain(view),
            'predecision_call_prefix_count': len(policy.client.calls), 'retry_admission': screen}
        policy.collection_attempts.append(attempt)
        if screen['status'] == 'conditional_retry_admissible':
            policy._begin_recollection(pending, screen, information, view)
            attempt.update(disposition='one_fresh_pair_requested', new_request_id=policy.pending['request_id'])
            return
        require(self.adapter.is_native_attempt(information), 'missing_real_current_collection_attempt')
        evidence = {'schema': EVIDENCE_SCHEMA, 'owner': policy.owner, 'phase': pending['phase'], 'at': view['now'],
            'collection': plain(pending), 'information': self.adapter.json_data(information),
            'retained': policy.ledger.audit_copy(), 'own_outbox': plain(policy.client.owned(policy.owner)),
            'own_calls': [plain(call) for call in policy.client.calls if call['request']['owner_id'] == policy.owner]}
        attempt['later_evidence'] = plain(evidence)
        public = actor_observation(evidence)
        actual = self.adapter.is_native_collected(information)
        model_started = time.perf_counter_ns()
        model_report = {'status': 'unknown_no_current_state_model', 'candidate_results': {}}
        if actual and self.model is not None:
            evaluate = getattr(self.model, 'evaluate', None)
            if callable(evaluate):
                model_report = plain(evaluate(plain(evidence), PHASE_ACTIONS[pending['phase']]))
            else:
                seed = self.model.build_seed(plain(evidence))
                predictions = {action: self.model.predict(seed, action) for action in PHASE_ACTIONS[pending['phase']]}
                model_report = {'status': seed['status'], 'seed': plain(seed), 'candidate_results': plain(predictions)}
        actions = []
        for action_id in PHASE_ACTIONS[pending['phase']]:
            proposal = semantic_action(pending['phase'], action_id, view['now'])
            local_ok, local_reason = self._local_guard(view, pending, information, action_id) if actual else (False, 'collection_not_supported_current')
            guard = protected(model_report['candidate_results'].get(action_id, {}), self.reference)
            allowed = actual and local_ok and (guard['status'] == 'passed' or self.mode == 'diagnostic_intervention')
            identity = digest({'collection': pending['request_id'], 'peer': pending['peer_message'],
                'owner': policy.owner, 'at': view['now'], 'action': action_id})
            actions.append({'candidate_id': identity, 'action_id': action_id, 'proposal': proposal,
                'enabled': allowed, 'guard_status': guard['status'],
                'mask_reason': local_reason if not local_ok else None if allowed else 'original_reference_' + guard['status'],
                'execution_mode': self.mode, 'native_protection_certified': False})
        self.offer = {'handle': information, 'pending': plain(pending), 'view': plain(view), 'evidence': evidence,
            'observation': public, 'actions': actions, 'model_report': model_report,
            'actual_collection_supported': actual, 'attempt': attempt,
            'request_started_ns': started,
            'initial_reference': plain(self.reference), 'initial_reference_sha256': self.reference_sha,
            'model_and_guard_wall_ms': (time.perf_counter_ns() - model_started) / 1e6,
            'collection_through_offer_wall_ms': (time.perf_counter_ns() - started) / 1e6}
        attempt['disposition'] = 'awaiting_detached_actor_choice' if any(row['enabled'] for row in actions) else 'unknown_or_rejected_all_candidates'
        if not any(row['enabled'] for row in actions):
            self.collection_failures.append({'observation': plain(public), 'actions': plain(actions),
                'model_report': plain(model_report), 'reason': attempt['disposition']})

    def _local_guard(self, view, pending, information, action_id):
        try:
            tray = policy_guards.local_target(view, pending['trigger_tray'], pending['phase'])
            if pending['phase'] == 'first_return':
                action = semantic_action(pending['phase'], action_id, view['now'])
                require(max(view['now'] + .01, action['absolute_earliest_departure']) < 39., 'transfer_expiry')
                demand = physical.v1.latest_demand(view, 'B')
                require(demand and any(job['origin'] == 7 for job in demand['jobs']), 'delivered_B_demand_required')
            else:
                require(view['now'] + .01 < information['bundle']['trays']['L']['service_ready_at'], 'route_service_window')
                if action_id == 'prefer_8':
                    target = [node for node in view['node_contracts'] if node['node'] == 8 and node['resource_owner'] == self.policy.owner]
                    require(len(target) == 1 and target[0]['occupancy'] < target[0]['capacity'], 'local_receive_capacity')
            return True, None
        except (KeyError, TypeError, ValueError) as error:
            return False, str(error)

    def observation(self):
        require(self.offer is not None, 'no_current_later_offer')
        return plain(self.offer['observation'])

    def candidates(self):
        require(self.offer is not None, 'no_current_later_offer')
        return plain(self.offer['actions'])

    def submit(self, candidate_id):
        started = time.perf_counter_ns()
        policy, offer = self.policy, self.offer
        require(offer is not None and digest(self.reference) == self.reference_sha, 'current_offer_and_original_reference')
        matches = [row for row in offer['actions'] if row['candidate_id'] == candidate_id]
        require(len(matches) == 1 and matches[0]['enabled'] is True, 'candidate_disabled_or_stale')
        candidate = matches[0]
        require(self.adapter.is_native_collected(offer['handle']), 'genuine_still_current_collection_required')
        require(encoding(policy.pending) == encoding(offer['pending']), 'collection_identity_changed')
        require(policy.client.context['owner'] == policy.owner
            and policy.client.context['accepted_at'] == policy.session.physical_time, 'current_own_admission')
        view = policy.session.observe_protocol(policy.owner)
        _, same = representation.equivalent_views(view, offer['handle']['raw_endpoints']['view'])
        require(same, 'current_view_changed_since_collection')
        require(encoding(plain(policy.client.owned(policy.owner))) == encoding(offer['evidence']['own_outbox']), 'owned_actions_changed')
        allowed, reason = self._local_guard(view, offer['pending'], offer['handle'], candidate['action_id'])
        require(allowed, 'final_local_guard:' + str(reason))
        pending = offer['pending']
        tray = policy_guards.local_target(view, pending['trigger_tray'], pending['phase'])
        causal = {'relation': 'result_handling', 'continuation_parent_roots': [pending['root']],
            'predecessor_protocol_id': pending['request_id'], 'delivered_peer_message_id': pending['peer_message'],
            'collection_started_at': pending['at'], 'foundation_later_candidate_id': candidate_id,
            'foundation_later_mode': self.mode}
        if pending['phase'] == 'first_return':
            delay = candidate['proposal']['return_delay_label']
            command_id = policy.return_tray(view, tray, physical.v1.latest_demand(view, 'B'), delay, causal)
            action = {'reuse_next': None, 'return_delay': delay}
        else:
            following = candidate['proposal']['next']
            command_id = policy.route_tray(view, tray, following, causal)
            action = {'reuse_next': following, 'return_delay': 0.}
            require(following is None or command_id is not None, 'nondefault_route_not_submitted')
        no_command = candidate['action_id'] == 'native_default'
        require((command_id is None) == no_command, 'command_identity_semantics')
        decision = {'at': view['now'], 'phase': pending['phase'], 'collection': plain(pending),
            'information': offer['handle'], 'decision': {'status': 'new_current_later_choice',
                'selected_action': action, 'candidate_id': candidate_id, 'action_id': candidate['action_id']},
            'fallback_used': False, 'executed_first_action': action, 'native_request_id': command_id,
            'actual_local_view': plain(view), 'predecision_call_prefix_count': offer['attempt']['predecision_call_prefix_count'],
            'selected_action_admitted': True, 'final_local_guard_reason': None,
            'future_proposal_component_executed_without_replan': False}
        policy.decisions.append(decision)
        transition = {'schema': 'g31.foundation.later_transition.v1', 'owner': policy.owner,
            'phase': pending['phase'], 'observation': plain(offer['observation']), 'candidate_mask': plain(offer['actions']),
            'proposal': plain(candidate), 'guarded_action': plain(candidate), 'actual_action': plain(action),
            'action_id': candidate['action_id'], 'executed_action_id': candidate['action_id'],
            'behavior_mode': self.mode, 'candidate_id': candidate_id, 'command_id': command_id,
            'command_ids': [] if no_command else [command_id], 'no_command': no_command,
            'ACK': None, 'ACK_status': 'not_applicable_no_command' if no_command else 'pending_delivered_ACK',
            'collection_started_at': pending['at'], 'selected_at': view['now'], 'submitted_at': None if no_command else view['now'],
            'model_report': plain(offer['model_report']), 'initial_reference': plain(self.reference),
            'initial_reference_sha256': self.reference_sha, 'execution_mode': self.mode,
            'conditional_protection_status': candidate['guard_status'], 'native_protection_certified': False,
            'next_observation': None, 'delta_sim_time_s': None, 'actual_per_job_delta': None,
            'terminated': False, 'truncated': True,
            'model_version': getattr(self.model, 'VERSION', None),
            'actual_physical_effect': None, 'timing_mode': 'offline_sync',
            'actor_choose_wall_ms': offer.get('actor_choose_wall_ms'),
            'actor_inference_wall_ms': offer.get('actor_inference_wall_ms'),
            'actor_state_unchanged': offer.get('actor_state_unchanged'),
            'actor_state_check': plain(offer.get('actor_state_check')),
            'collection_through_offer_wall_ms': offer['collection_through_offer_wall_ms'],
            'model_and_guard_wall_ms': offer['model_and_guard_wall_ms'],
            'submission_and_local_guard_wall_ms': (time.perf_counter_ns() - started) / 1e6}
        self.transitions.append(transition)
        offer['attempt']['disposition'] = 'new_current_later_choice_submitted' if not no_command else 'new_current_later_default_no_command'
        policy.pending = None
        self.offer = None
        transition['collection_to_decision_record_wall_ms'] = (time.perf_counter_ns() - offer['request_started_ns']) / 1e6
        transition['request_timing_scope'] = 'From collect_native entry through decision record; includes actor/wrapper gaps, excludes earlier message collection, startup, return serialization and later ACK.'
        return plain(transition)

    def audit_copy(self):
        offer = None if self.offer is None else {key: value for key, value in self.offer.items()
                                               if key not in ('handle', 'request_started_ns')}
        return plain({'owner': self.policy.owner, 'mode': self.mode, 'phases': list(self.phases),
            'current_offer': offer, 'transitions': self.transitions, 'collection_failures': self.collection_failures,
            'initial_reference': self.reference, 'initial_reference_sha256': self.reference_sha,
            'scope': 'detached audit data; no collection execution capability'})

    def update_ack(self):
        for transition in self.transitions:
            command_id = transition['command_id']
            if command_id is None:
                continue
            row = self.policy.client.owned(self.policy.owner)[command_id]
            ack = row.get('ack')
            if ack and ack != transition['ACK'] and ack.get('delivered_at', math.inf) <= self.policy.session.physical_time:
                transition['ACK'] = plain(ack)
                transition['ACK_status'] = ack.get('status')
                transition['ACK_observed_at'] = self.policy.session.physical_time
