"""Independent native repeated-cycle controller; the old domain stays closed.

Original fixed initial action, first return/reuse, retry and recovery remain the
reference. New conditional advice is usable only through a new current owner
collection and the full per-job reference check. Native execution is event-clock
driven; real worker concurrency does not constitute real-time certification.
"""
from __future__ import annotations
import copy
import time
from . import foundation_repeated_domain as domain
from . import foundation_repeated_worker as worker
from . import foundation_repeated_value as learned_value
from . import foundation_later_control as control
from . import live_obligation_historical_adapter as historical
from . import research_live_obligation_initial_methods as online

physical = domain.legacy
bound = physical.bound
require, plain, digest = domain.require, domain.plain, domain.digest


def protected(prediction, reference):
    if (not reference or prediction.get('status') != 'conditional_prediction'
            or set(prediction.get('completion', {})) != set(reference['completion'])
            or not all(domain.finite(value) and value >= 0 for value in prediction['completion'].values())):
        return {'status': 'unknown', 'per_job_delta': None}
    delta = {key: value-reference['completion'][key] for key, value in prediction['completion'].items()}
    return {'status': 'passed' if all(value <= 0 for value in delta.values()) else 'rejected', 'per_job_delta': delta}


def visible_view(view):
    result = plain(view)
    result['jobs'] = [job for job in result['jobs'] if job['arrival'] <= result['now'] and job['status'] != 'unreleased']
    return result


class ContractLedger:
    """Learns contracts only from native own observations and delivered captures."""
    def __init__(self, session, owner):
        self.session, self.owner = session, owner
        self.contracts, self.sources, self.static, self.at = {}, [], None, 0.

    def ingest(self, view, received):
        require(view['owner_id'] == self.owner and view['now'] == self.session.physical_time, 'ledger_actual_owner_time')
        rows = [(job, 'own_observation') for job in visible_view(view)['jobs']]
        for envelope in received:
            local = envelope['capture']['capture_v2']['local_capture']
            require(local['target_owner'] == self.owner and envelope['delivered_at'] <= view['now'], 'ledger_delivered_scope')
            require(self.static in (None, local['static_contract_sha256']), 'ledger_static_contract_change')
            self.static = local['static_contract_sha256']
            rows += [(job, local['message_id']) for job in local['jobs']]
        for job, source in rows:
            require(job['arrival'] <= view['now'] and job['status'] != 'unreleased', 'ledger_future_contract')
            key = job['business_bag_id']
            contract = {field: job[field] for field in domain.old_guard.CONTRACT_FIELDS}
            require(key not in self.contracts or self.contracts[key] == contract, 'ledger_changed_contract')
            if key not in self.contracts:
                self.contracts[key] = contract; self.sources.append({'job': key, 'at': view['now'], 'source': source})
                self.at = view['now']

    def audit_copy(self):
        return {'owner': self.owner, 'contracts': plain(self.contracts), 'sources': plain(self.sources),
            'static_contract_sha256': self.static, 'retained_at': self.at}


def semantic(phase, action, now):
    if phase == 'cycle_return':
        return {'operation_kind': 'transfer', 'source': 6, 'destination': 7, 'tray_id': 'L',
            'earliest_departure': now + (.5 if action == 'return_delay_0_5' else 0.),
            'earliest_legal_arrival': max(now + .01, now + (.5 if action == 'return_delay_0_5' else 0.)) + .1 + 2. + .1}
    target = 8 if action == 'prefer_8' else 3 if action == 'prefer_3' else None
    return {'operation_kind': 'no_command' if target is None else 'route', 'source': 7,
        'destination': target, 'tray_id': 'L', 'earliest_legal_arrival': None,
        'native_default_does_not_clear_preference': True}


def current_route_local_mask(view, tray, service, action, owner):
    if not (domain.finite(service) and view['now'] + .01 < service and tray['node'] == 7
            and tray['mode'] == 'loaded' and tray['edge_to'] < 0):
        return False
    # Leaving the existing native policy unchanged issues no reservation. Its
    # predicted waiting still has to pass the independent complete-job guard.
    if action == 'native_default':
        return True
    target = 8 if action == 'prefer_8' else 3
    capacity = [row for row in view['node_contracts'] if row['node'] == target and row['resource_owner'] == owner]
    return len(capacity) == 1 and capacity[0]['occupancy'] < capacity[0]['capacity']


def score_enabled(model, binding, public, enabled):
    start = time.perf_counter_ns()
    audit = {'model_reference': plain(binding), 'used_as_authority': False,
        'candidate_ids': [row['action_id'] for row in enabled], 'scores': {}}
    if not enabled:
        audit.update(status='no_admissible_candidates', foreground_inference_wall_ms=0.)
        return audit
    try:
        scores = learned_value.predict(model, [public] * len(enabled), [row['semantic'] for row in enabled])
        audit.update(status='scored_current_guarded_candidates', scores=dict(zip(audit['candidate_ids'], scores, strict=True)),
            model_content_sha256=model['model_sha256'])
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        audit.update(status='unknown_model_scoring_original_rank_continues', reason=str(error))
    audit['foreground_inference_wall_ms'] = (time.perf_counter_ns()-start)/1e6
    return audit


def observation(policy, view, opportunity):
    now = view['now']
    delivered = policy.session.protocol_planning_snapshots_v3(policy.owner)
    return {'schema': domain.OBSERVATION_SCHEMA, 'owner': policy.owner, 'at': now,
        'remaining_horizon_s': 40. - now,
        'opportunity': plain(opportunity), 'local_view': visible_view(view),
        'delivered_v3': control.v3_messages(delivered, policy.owner, now),
        'known_contracts': policy.ledger.audit_copy(), 'own_outbox': plain(policy.client.owned(policy.owner)),
        'account_summary': {'actual_locally_available': sum(row.get('actual_available', 0)
            for row in view['node_contracts'] if row['resource_owner'] == policy.owner),
            'arrived_unfinished_locally_known': sum(job['status'] != 'completed' for job in visible_view(view)['jobs'])},
        'privileged_evaluator_state_included': False, 'reference_included': False,
        'timing_mode': 'event_clock_with_resident_process' if policy.resident else 'offline_sync'}


class OwnerPolicy(physical.OwnerPolicy):
    def __init__(self, *args, episode, mode, reference=None, resident=None, **kwargs):
        super().__init__(*args, **kwargs)
        require(mode in ('baseline', 'guarded', 'async'), 'repeated_mode')
        self.episode, self.mode, self.reference, self.resident = episode, mode, plain(reference), resident
        self.reference_sha = digest(reference)
        self.repeated_decisions, self.repeated_attempts = [], []
        self.preview_targets = set()
        self.completed_advice = None
        self.result_deliveries = []
        self._in_new_collection = False
        self.reuse_count = 2
        self.required_business_ids = set(control.JOBS)
        self.selection = 'score'
        self.learned_model, self.model_reference = None, None

    def decide_pending(self, view):
        pending = self.pending
        if not pending or view['now'] < self.peer_quiet_until:
            return
        own = self.client.rows[pending['request_id']].get('ack', {})
        ready = own.get('status') == 'delivered' and pending['peer_message'] is not None
        if not ready and view['now'] < pending['deadline']:
            return
        if pending['phase'] in ('cycle_route', 'preview_next_route'):
            return self.decide_current(view, ready)
        # Fixed original incumbent: reference continuation never asks the old
        # initial predictor to invent a contract that has not yet arrived.
        tray = next((row for row in view['trays'] if row['tray_id'] == 'L'), None)
        causal = {'relation': 'fixed_original_incumbent', 'continuation_parent_roots': [pending['root']],
            'predecessor_protocol_id': pending['request_id'], 'delivered_peer_message_id': pending['peer_message']}
        if pending['phase'] == 'first_return' and tray:
            demand = physical.v1.latest_demand(view, 'B')
            if demand:
                self.return_tray(view, tray, demand, 0., causal)
        elif pending['phase'] == 'first_reuse_route' and tray:
            self.route_tray(view, tray, None, causal)
        self.pending = None

    def exchange(self, view):
        # Reuse exact original replies/preflight for first opportunities.
        new_messages = []
        for envelope in self.session.protocol_planning_snapshots_v3(self.owner):
            local = envelope['capture']['capture_v2']['local_capture']
            if local['message_id'] in self.seen_messages:
                continue
            # Native message IDs do not transmit Python request labels. This
            # new invitation is defined by delivered lifecycle facts instead.
            # It is confined to B -> A after the original first reuse epoch.
            if self.owner == 'A' and local['source_owner'] == 'B' and local['captured_at'] > 10.:
                new_messages.append(envelope)
        for envelope in new_messages:
            local = envelope['capture']['capture_v2']['local_capture']
            identity = local['message_id']; self.seen_messages.add(identity)
            causal = {'relation': 'result_handling', 'continuation_parent_roots': [],
                'delivered_parent_message': {'message_id': identity, 'source_owner': local['source_owner'],
                    'captured_at': local['captured_at'], 'delivered_at': envelope['delivered_at']}}
            refresh = []
            for identity, row in self.client.owned(self.owner).items():
                if row['kind'] == 'transfer' and not row['terminal']:
                    self.client.send(identity, retry=True); refresh.append(identity)
            if refresh:
                self.pending_reply = {'phase': 'cycle_route', 'causal': causal, 'envelope': plain(envelope), 'waiting': refresh}
                self.exchanges.append({'at': view['now'], 'kind': 'repeated_immutable_ACK_refresh_before_reply',
                    'message': plain(envelope), 'request_ids': refresh, 'causal': plain(causal)})
            else:
                reply = self.publication('reply-repeated', causal)
                self.peer_quiet_until = max(self.peer_quiet_until, view['now'] + bound.COLLECTION_LIMIT)
                self.exchanges.append({'at': view['now'], 'kind': 'repeated_reply',
                    'message': plain(envelope), 'request_id': reply})
        super().exchange(view)

    def hold_new_admissions_after_reply(self, phase, identity, now):
        if phase == 'cycle_route':
            self.peer_quiet_until = max(self.peer_quiet_until, now + bound.COLLECTION_LIMIT)
        else:
            super().hold_new_admissions_after_reply(phase, identity, now)

    def activate(self, trigger):
        # Default fast policy, immutable retry and physical progress do not wait
        # on the worker. Body collection happens before any new default command.
        if self.resident:
            result = self.resident.poll(self.session.physical_time)
            if result is not None:
                self.accept_worker_result(result)
            # A speculative collection never holds up an actual loaded
            # opportunity while its worker or collection remains incomplete.
            if self.pending and self.pending['phase'] == 'preview_next_route':
                actual = self.session.observe_protocol(self.owner)
                if any(tray['business_bag_id'] == self.pending['target_job'] and tray['mode'] == 'loaded'
                        for tray in actual['trays']):
                    self.result_deliveries.append({'at': actual['now'], 'status': 'preview_cancelled_default_deadline',
                        'target_job': self.pending['target_job']})
                    self.pending = None
        super().activate(trigger)
        view = self.session.observe_protocol(self.owner)
        self.loading_preflight(view)
        prior_contracts = set(self.ledger.contracts)
        self.ledger.ingest(view, self.session.protocol_planning_snapshots_v3(self.owner))
        # Extra registered waves use the identical ordinary immediate return
        # and route3 continuation after the old first two cycles.
        if self.pending is None and view['now'] >= self.peer_quiet_until:
            if self.owner == 'A' and 2 <= len(self.returns) < self.reuse_count:
                tray = next((row for row in view['trays'] if row['tray_id'] == 'L' and row['node'] == 6
                    and row['mode'] == 'empty' and row['edge_to'] < 0 and row['available_at'] <= view['now']), None)
                demand = physical.v1.latest_demand(view, 'B')
                if tray and demand and any(job['origin'] == 7 for job in demand['jobs']) and self.client.rows[self.returns[-1]['request_id']]['terminal']:
                    self.return_tray(view, tray, demand, 0., {'relation': 'fixed_repeated_immediate_return',
                        'continuation_parent_roots': [], 'delivered_demand_id': demand['message_id']})
            if self.owner == 'B':
                for tray in view['trays']:
                    if (tray['tray_id'] == 'L' and tray['node'] == 7 and tray['mode'] == 'loaded' and tray['edge_to'] < 0
                            and tray['business_bag_id'].startswith('reuse') and tray['business_bag_id'] not in ('reuse1', 'reuse2')
                            and (tray['business_bag_id'], tray['generation'], tray['traversal_id']) not in self.route_keys):
                        self.route_tray(view, tray, 3, {'relation': 'fixed_repeated_loaded_route', 'continuation_parent_roots': []})
        if set(self.ledger.contracts) - prior_contracts and view['now'] > .11 and self.pending is None:
            self.publication('new-arrived-business', {'relation': 'locally_observed_new_business',
                'continuation_parent_roots': [], 'arrived_business_ids': sorted(set(self.ledger.contracts)-prior_contracts)})
        # A preview observes only already delivered business and does not use
        # evaluator future jobs. Its result is candidate ordering, never a gate.
        if (self.resident and self.owner == 'B' and self.pending is None
                and set(self.ledger.contracts) == self.required_business_ids and len(self.choices) >= 1
                and self.client.context['owner'] == self.owner):
            targets = [job['business_bag_id'] for job in visible_view(view)['jobs']
                if job['business_bag_id'].startswith('reuse') and job['business_bag_id'] != 'reuse1'
                and job['status'] == 'waiting_for_tray'
                and not self.route_already_decided(job['business_bag_id'])]
            trays = [tray for tray in view['trays'] if tray['tray_id'] == 'L']
            if targets and trays:
                target = min(targets, key=lambda job: (self.ledger.contracts[job]['arrival'], job))
                if target not in self.preview_targets:
                    self.preview_targets.add(target)
                    self.begin_new('preview_next_route', trays[0], self.client.context['root_id'])
                    self.pending['target_job'] = target

    def route_already_decided(self, target):
        return any(row['job'] == target for row in self.choices)

    def accept_worker_result(self, result):
        target, now = result.get('target_job'), self.session.physical_time
        status = 'available_for_fresh_current_collection'
        report = result.get('model_report', {})
        if target not in self.ledger.contracts or not isinstance(target, str) or not target.startswith('reuse'):
            status = 'rejected_unknown_target'
        elif self.route_already_decided(target):
            status = 'rejected_action_already_dispatched'
        elif result.get('owner') != self.owner or result.get('source_at', now + 1) > now:
            status = 'rejected_owner_or_time'
        elif report.get('status') != 'conditional_current_seed' or report.get('seed', {}).get('preview_target_job') != target:
            status = 'rejected_unknown_or_mismatched_target_prediction'
        if status == 'available_for_fresh_current_collection':
            self.completed_advice = result
        self.result_deliveries.append({'at': now, 'result': plain(result), 'status': status,
            'before_owner_default_admission': True})

    def loading_preflight(self, view):
        """Refresh the immutable return ACK during each real subsequent load.

This repeats the original reuse1 preflight. It does not wait for a forecast,
change the request payload, admit a route, or reuse the loading capture as the
later current-state collection.
"""
        if self.owner != 'B':
            return
        for tray in view['trays']:
            job = tray['business_bag_id']
            if (tray['tray_id'] != 'L' or tray['node'] != 7 or tray['mode'] != 'loading'
                    or tray['edge_to'] >= 0 or not job.startswith('reuse') or job == 'reuse1'):
                continue
            identity = f"repeated_loading_ack_refresh:{job}:{tray['generation']}:{tray['traversal_id']}"
            if identity in self.started:
                continue
            self.started.add(identity)
            request = self.publication('repeated-loading-preflight', {'relation': 'independent_offer',
                'continuation_parent_roots': [], 'local_trigger': {'phase': identity, 'tray': plain(tray)}})
            self.exchanges.append({'at': view['now'], 'kind': 'repeated_preflight_from_actual_local_loading',
                'request_id': request, 'local_tray': plain(tray), 'future_collection_required': True})

    def begin_new(self, phase, tray, root):
        self.begin(phase, tray, root)
        self.pending['policy_quiet_since'] = self.pending['at']

    def return_tray(self, view, tray, demand, delay, causal):
        before = self.before_observation(view, tray, 'cycle_return', causal)
        identity = (super().return_tray(view, tray, demand, delay, causal) if len(self.returns) < 2 else
            bound.OwnerPolicy.return_tray(self, view, tray, demand, delay, causal))
        self.record_default(view, tray, 'cycle_return', 'return_now', identity, causal,
            'fixed_original_return_continuation; delayed alternative requires full current support', before)
        return identity

    def route_tray(self, view, tray, next_node, causal):
        if (tray['business_bag_id'] != 'reuse1' and tray['business_bag_id'].startswith('reuse')
                and not self._in_new_collection and self.mode != 'baseline'):
            advice = (self.completed_advice or {}).get('model_report', {})
            can_start = self.mode == 'guarded' or (advice.get('status') == 'conditional_current_seed'
                and bool(advice.get('candidate_results'))
                and self.completed_advice.get('target_job') == tray['business_bag_id'])
            if can_start:
                self.begin_new('cycle_route', tray, self.client.context['root_id'])
                return None
        before = self.before_observation(view, tray, 'cycle_route', causal)
        identity = super().route_tray(view, tray, next_node, causal)
        self.record_default(view, tray, 'cycle_route', 'native_default' if next_node is None else f'prefer_{next_node}',
            identity, causal, 'fixed_original_route_continuation' if self.mode == 'baseline' else 'advice_unavailable_default_continues', before)
        return identity

    def before_observation(self, view, tray, phase, causal):
        opportunity = domain.opportunity(self.episode, self.owner, phase, tray, view['now'],
            causal.get('predecessor_protocol_id') or self.client.context['root_id'])
        return opportunity, observation(self, view, opportunity)

    def record_default(self, view, tray, phase, action, identity, causal, reason, before):
        opportunity, public = before
        self.repeated_decisions.append({'decision_id': opportunity['opportunity_id'], 'owner': self.owner,
            'selected_at': view['now'], 'opportunity': opportunity, 'observation': public,
            'candidate_mask': [{'action_id': action, 'semantic': semantic(phase, action, view['now']),
                'enabled': True, 'guard_status': 'original_fixed_rule', 'per_job_delta': None}],
            'selected_action_id': action, 'command_id': identity, 'reason': reason,
            'current_admission': {'owner_root': self.client.context['root_id'], 'at': view['now'],
                'fresh_collection': False, 'execution_mode': 'original_fixed_rule'}})

    def collect(self, view):
        pending = self.pending
        require(historical.endpoint._valid_handle(self.native, self.session, self.accepted), 'accepted_actual_native_handle')
        rows, publications, audit = historical.client_owned_snapshot(self.client, self.session, self.owner,
            self.client.owned(self.owner))
        endpoints = {'view': self.session.observe_protocol(self.owner),
            'command': self.session.protocol_command(self.owner, pending['request_id']),
            'received': self.session.protocol_planning_snapshots_v3(self.owner)}
        self.ledger.ingest(endpoints['view'], endpoints['received'])
        info = domain.validate_endpoints(**endpoints, retained=self.ledger.audit_copy(),
            own_actions=sorted((key, row['kind']) for key, row in rows.items() if row['kind'] in domain.old_guard.PHYSICAL_KINDS),
            phase=pending['phase'], own_request_id=pending['request_id'], peer_message_id=pending['peer_message'],
            collection_started_at=pending['at'], policy_quiet_since=pending['policy_quiet_since'],
            own_request=publications[pending['request_id']])
        info['raw_endpoints'] = plain(endpoints)
        evidence = {'schema': domain.EVIDENCE_SCHEMA, 'owner': self.owner, 'phase': pending['phase'], 'at': view['now'],
            'information': info, 'collection': plain(pending), 'retained': self.ledger.audit_copy(),
            'own_outbox': plain(rows), 'own_calls': [plain(row) for row in self.client.calls if row['request']['owner_id'] == self.owner]}
        require(self.session.physical_time == view['now'] and endpoints['view'] == view, 'actual_collection_unchanged')
        return evidence, audit

    def decide_current(self, view, ready):
        start = time.perf_counter_ns()
        pending = plain(self.pending)
        evidence, audit = self.collect(view)
        if pending['phase'] == 'preview_next_route':
            report = {'status': 'validated_detached_preview_input' if ready and evidence['information'].get('status')
                == 'conditional_validated_later_v3_data' else 'unknown', 'candidate_results': {}}
        else:
            report = domain.evaluate(evidence, domain.ACTIONS[pending['phase']]) if ready else {'status': 'unknown', 'candidate_results': {}}
        attempt = {'evidence': evidence, 'model_report': report, 'actual_client_read': audit,
            'collection_and_guard_wall_ms': (time.perf_counter_ns()-start)/1e6}
        self.repeated_attempts.append(attempt)
        if pending['phase'] == 'preview_next_route':
            if report['status'] == 'validated_detached_preview_input':
                # Worker receives detached actual evidence, not private native.
                attempt['worker_request_id'] = self.resident.submit(evidence, domain.ACTIONS[pending['phase']])
            self.pending = None
            return
        tray = next((row for row in view['trays'] if row['tray_id'] == 'L'), None)
        if not tray:
            self.pending = None; attempt['status'] = 'target_departed_default_continues'; return
        service = evidence['information'].get('bundle', {}).get('trays', {}).get('L', {}).get('service_ready_at')
        opportunity = domain.opportunity(self.episode, self.owner, 'cycle_route', tray, view['now'],
            pending['request_id'], service_ready_at=service)
        candidates = []
        for action in domain.ACTIONS['cycle_route']:
            prediction = report.get('candidate_results', {}).get(action, {})
            guard = protected(prediction, self.reference)
            target = 8 if action == 'prefer_8' else 3
            local = current_route_local_mask(view, tray, service, action, self.owner)
            proposal = semantic('cycle_route', action, view['now'])
            if domain.finite(service) and action != 'native_default':
                proposal['earliest_legal_arrival'] = service + (2.8 if target == 8 else 1.)
            candidates.append({'action_id': action, 'semantic': proposal, 'enabled': bool(local and guard['status'] == 'passed'),
                'guard_status': guard['status'], 'per_job_delta': guard['per_job_delta'],
                'mask_reason': None if local else 'current_window_target_capacity'})
        enabled = [row for row in candidates if row['enabled']]
        # Prediction only ranks candidates already authorized by the independent
        # current full-job guard. Existing original request remains fallback.
        advice = self.completed_advice if self.completed_advice and self.completed_advice.get('target_job') == tray['business_bag_id'] else None
        advice_results = (advice or {}).get('model_report', {}).get('candidate_results', {})
        advice_order = sorted(advice_results, key=lambda action: sum(advice_results[action].get('completion', {}).values()))
        public_before = observation(self, view, opportunity)
        model_audit = score_enabled(self.learned_model, self.model_reference, public_before, enabled) if self.learned_model is not None else None
        model_scores = model_audit['scores'] if model_audit else {}
        chosen = min(enabled, key=lambda row: (-model_scores.get(row['action_id'], 0.),
            row['action_id'] != self.selection if self.selection != 'score' else False,
            advice_order.index(row['action_id']) if self.mode == 'async' and row['action_id'] in advice_order else 0,
            sum(report['candidate_results'][row['action_id']]['completion'].values()),
            row['action_id'] != 'prefer_3', row['action_id'])) if enabled else None
        action = chosen['action_id'] if chosen else 'prefer_3'
        require(digest(self.reference) == self.reference_sha and historical.endpoint._valid_handle(self.native, self.session, self.accepted),
            'reference_and_native_origin_still_current')
        require(self.client.context['owner'] == self.owner and self.client.context['accepted_at'] == self.session.physical_time
            and self.session.observe_protocol(self.owner) == view and plain(self.client.owned(self.owner)) == evidence['own_outbox'],
            'new_current_admission_unchanged_before_submit')
        before = len(self.repeated_decisions)
        self._in_new_collection = True
        try:
            identity = self.route_tray(view, tray, None if action == 'native_default' else 8 if action == 'prefer_8' else 3,
                {'relation': 'current_guarded_result' if chosen else 'original_fallback',
                    'predecessor_protocol_id': pending['request_id'], 'continuation_parent_roots': [pending['root']]})
        finally:
            self._in_new_collection = False
        del self.repeated_decisions[before:]
        self.repeated_decisions.append({'decision_id': opportunity['opportunity_id'], 'owner': self.owner,
            'selected_at': view['now'], 'opportunity': opportunity, 'observation': public_before,
            'candidate_mask': candidates, 'selected_action_id': action, 'command_id': identity,
            'current_admission': {'owner_root': self.client.context['root_id'], 'at': view['now'],
                'fresh_collection': True, 'collection_request_id': pending['request_id'],
                'evidence_sha256': digest(evidence), 'reference_sha256': self.reference_sha,
                'execution_mode': 'protected_current' if chosen else 'original_fallback'},
            'old_advice_used_as_authority': False, 'worker_result_id': None if advice is None else advice['request_id'],
            'worker_target_job': None if advice is None else advice['target_job'], 'learned_ranking': model_audit,
            'worker_candidate_order': advice_order if self.mode == 'async' else [],
            'collection_and_guard_wall_ms': attempt['collection_and_guard_wall_ms']})
        if advice is not None:
            self.result_deliveries.append({'at': view['now'], 'status': 'consumed_once_after_current_guard',
                'request_id': advice['request_id'], 'target_job': advice['target_job'],
                'decision_id': opportunity['opportunity_id']})
            self.completed_advice = None
        self.pending = None


def run_branch(native, accepted_run, key, contract_reference, row, *, resident=None, progress=None, learned_model=None):
    progress = {} if progress is None else progress
    require(type(accepted_run) is physical.run_admission.RunAcceptance and accepted_run.active_for(key), 'active_accepted_branch')
    require(accepted_run.branch_specification(key) == row, 'declared_repeated_row')
    require((learned_model is None) == (row.get('model_reference') is None), 'declared_model_object_presence')
    if learned_model is not None:
        require(row['mode'] != 'baseline' and row.get('selection') == 'score' and row.get('model_used_as_authority') is False
            and learned_model.get('model_sha256') == row['model_content_sha256'], 'declared_model_object_binding')
        learned_value.predict(learned_model, [], [])
    data = domain.scene(row['case']); domain.validate_scene(data, row['domain'])
    progress.update(specification=row, input=data, stage='native_session_constructor')
    session = native.NativeSession(data)
    progress.update(session=session, stage='runtime_admission')
    admission, accepted = physical.adapter.bind_native027(native, session, contract_reference,
        accepted_run=accepted_run, branch_key=key)
    require(accepted is not None, 'actual_native_acceptance:' + str(admission))
    session.advance_to(.05)
    client = bound.LocalTransport(session)
    channels, policies, planning = {}, {}, {}
    progress.update(client=client, policies=policies, stage='initial_fixed_rule')
    for owner, peer in (('A', 'B'), ('B', 'A')):
        client.activate(owner, {'kind': 'initial_public_epoch', 'at': .05})
        channels[owner] = client.submit(owner, 'demand', 'seed-demand', target_owner=peer, message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, 'planning_snapshot', 'initial-planning', target_owner=peer,
            message_delay=.01, publication_delay=.01, expiry=.21)
    session.advance_to(physical.v1.START)
    vector = online.protocol.incumbent_action()
    for owner in ('A', 'B'):
        client.activate(owner, {'kind': 'fixed_original_initial_action', 'at': session.physical_time})
        client.refresh_owner(owner)
        ledger = ContractLedger(session, owner)
        ledger.ingest(session.observe_protocol(owner), session.protocol_planning_snapshots_v3(owner))
        supply = None
        if owner == 'B':
            supply = client.submit('B', 'transfer', 'initial-supply', tray_id='E', source=5, destination=1,
                earliest_departure=vector['empty_departure'], expiry=39., message_delay=.01)
        policies[owner] = OwnerPolicy(native, session, client, owner, ledger, channels[owner], vector, accepted, supply,
            episode=key, mode=row['mode'], reference=row.get('reference'), resident=resident if owner == 'B' else None)
        policies[owner].reuse_count = domain.REUSE_COUNTS.get(row['case'], 2)
        policies[owner].required_business_ids = set(row['domain']['business_ids'])
        policies[owner].selection = row.get('selection', 'score')
        policies[owner].learned_model = learned_model if owner == 'B' else None
        policies[owner].model_reference = row.get('model_reference')
    cursors = {'A': 0, 'B': 0}; tick = 0; activations = 0; batches = []
    progress.update(native_batches=batches, stage='owner_notification_continuation')
    while session.physical_time < 40. and activations < bound.MAX_ACTIVATIONS:
        deadline = min(40., physical.v1.START + tick * physical.v1.PERIOD,
            *(max(policy.pending['deadline'], policy.peer_quiet_until) for policy in policies.values() if policy.pending))
        require(deadline >= session.physical_time, 'repeated_no_missed_deadline')
        response = session.advance_until_owner_notification(['A', 'B'], cursors, deadline, max_events=100000)
        batches.append({'deadline': deadline, 'response': plain(response)})
        require(response['status'] in ('notified', 'horizon_reached') and response.get('timestamp_complete') is True,
            'complete_native_notification_boundary')
        now = session.physical_time; due_tick = now == physical.v1.START + tick * physical.v1.PERIOD
        if due_tick:
            tick += 1
        notices = response.get('notifications', {})
        due = {owner for owner, policy in policies.items() if due_tick or owner in notices
            or policy.pending and now >= policy.pending['deadline']}
        for owner, notice in notices.items():
            cursors[owner] = notice['sequence']
        for owner in sorted(due):
            policies[owner].activate({'native_notification': plain(notices.get(owner)), 'periodic_tick': due_tick})
            activations += 1
    require(session.physical_time == 40. and activations < bound.MAX_ACTIVATIONS, 'complete_native_horizon')
    for owner in policies:
        client.activate(owner, {'kind': 'final_outbox_collection', 'at': 40.}); client.refresh_owner(owner, retry=False)
    result = session.result_at(40.)
    progress.update(result=result, stage='complete_assessment')
    continuation = {'status': 'finished', 'route_choices': policies['B'].choices, 'returns': policies['A'].returns,
        'supply_lineage': policies['B'].supplies, 'recovery_decisions': policies['B'].recovery}
    summary = assess(data, result, client, continuation, vector)
    # assess_cell expects the old second-route3. Report actual route and ACK
    # evidence separately for a legal changed second route; never rewrite input.
    decisions = sorted([item for policy in policies.values() for item in policy.repeated_decisions],
        key=lambda item: (item['selected_at'], item['owner']))
    for decision in decisions:
        decision['actual_ack'] = plain(client.rows[decision['command_id']].get('ack')) if decision['command_id'] else None
        decision['actual_effects'] = actual_effects(decision, result['receipts'], client.rows)
    return {'schema': 'g31.foundation.repeated_native.v1', 'input': data, 'specification': row,
        'result': result, 'summary': summary, 'calls': client.calls, 'outbox': client.rows,
        'request_creations': client.creations, 'owner_activation_admissions': client.roots,
        'ack_handling': client.ack_handling, 'continuation': continuation, 'native_batches': batches,
        'exchanges': {owner: policy.exchanges for owner, policy in policies.items()},
        'collection_policy_intervals': {owner: policy.quiet_periods for owner, policy in policies.items()},
        'repeated_decisions': decisions, 'repeated_attempts': {owner: policy.repeated_attempts for owner, policy in policies.items()},
        'retained_ledgers': {owner: policy.ledger.audit_copy() for owner, policy in policies.items()},
        'result_deliveries': policies['B'].result_deliveries,
        'native027_acceptance': accepted.audit_copy(), 'full_request_100ms_certified': False, 'realtime_async': False}


def actual_effects(decision, receipts, outbox):
    """Bind local command identities to a distinct native receipt namespace."""
    identity, opportunity = decision['command_id'], decision['opportunity']
    tray, selected = opportunity['target'], decision['selected_at']
    result = {'local_generation': tray['generation'], 'local_traversal_id': tray['traversal_id'],
        'native_receipt_traversal_is_distinct_namespace': True, 'receipts': [], 'status': 'unknown_unbound'}
    if opportunity['operation_kind'] == 'transfer':
        matches = [row for row in receipts if row['event'] == 'EMPTY_RECEIVED' and row['reason'] == identity
            and row['tray_id'] == tray['tray_id'] and row['time'] > selected]
        result.update(receipts=plain(matches), status='bound_actual_transfer_receipt' if len(matches) == 1 else 'unknown_unbound')
        return result
    job = tray['business_bag_id']
    loads = [row for row in receipts if row['event'] == 'LOAD_COMPLETE' and row['business_bag_id'] == job
        and row['tray_id'] == tray['tray_id'] and row['node'] == tray['node'] and row['time'] <= selected]
    edges = [row for row in receipts if row['event'] == 'EDGE_ENTER' and row['business_bag_id'] == job
        and row['tray_id'] == tray['tray_id'] and row['from'] == tray['node'] and row['time'] > selected]
    legs = [row for row in receipts if row['event'] == 'LEG_START' and row['business_bag_id'] == job
        and row['tray_id'] == tray['tray_id'] and row['from'] == tray['node'] and row['time'] <= selected]
    binding = (len(loads) == len(legs) == len(edges) == 1
        and loads[0]['time'] == legs[0]['time'] and loads[0]['traversal_id'] == legs[0]['traversal_id']
        and legs[0]['transport_leg_id'] == edges[0]['transport_leg_id']
        and legs[0]['traversal_id'] < edges[0]['traversal_id'])
    if identity:
        command, ack = outbox[identity]['request'], outbox[identity].get('ack', {})
        binding = (binding and command['expected_generation'] == tray['generation']
            and command['expected_traversal'] == tray['traversal_id'] and ack.get('status') == 'updated'
            and selected <= ack.get('executed_at', -1) < edges[0]['time'] and command['next'] == edges[0]['to'])
    result.update(receipts=plain(edges), loaded_segment=plain(loads), transport_leg=plain(legs),
        status='bound_actual_route_receipt' if binding else 'unknown_unbound')
    return result


def assess(data, result, client, continuation, vector):
    receipts = result['receipts']; expected = {row['business_bag_id'] for row in data['jobs']}
    completion = {row['business_bag_id']: row['completed_at'] for row in result['jobs']}
    complete = (result['advance']['status'] == 'reached' and result['advance']['horizon_complete'] is True
        and result['advance']['physical_time'] == 40. and set(completion) == expected
        and all(domain.finite(value) and 0 <= value <= 40. for value in completion.values()))
    def ack_ok(identity, status):
        ack = client.rows[identity].get('ack', {})
        return ack.get('status') == status and domain.finite(ack.get('delivered_at')) and ack['delivered_at'] <= 40.
    supplies = continuation['supply_lineage']; returns = continuation['returns']; choices = continuation['route_choices']
    required_returns = len([key for key in expected if key.startswith('reuse')])
    recovery = continuation['recovery_decisions']
    supply_ok = (1 <= len(supplies) <= physical.v2.SUPPLY_ATTEMPT_LIMIT and ack_ok(supplies[-1], 'received')
        and all(ack_ok(identity, 'rejected') and client.rows[identity]['ack']['reason'] == 'receiving_full' for identity in supplies[:-1])
        and len(recovery) == len(supplies)-1)
    for index, record in enumerate(recovery):
        prior = client.rows[supplies[index]]['ack']
        supply_ok = supply_ok and (record['predecessor_request_id'] == supplies[index]
            and record['request_id'] == supplies[index+1] and record['delivered_rejection'] == prior
            and record['at'] >= prior['delivered_at'] + physical.v2.REJECTION_COOLDOWN
            and record['delivered_demand']['delivered_at'] <= record['at'])
    transfer_ids = {key for key, row in client.rows.items() if row['kind'] == 'transfer'}
    returns_ok = (len(returns) == required_returns and all(ack_ok(row['request_id'], 'received') for row in returns)
        and transfer_ids == set(supplies) | {row['request_id'] for row in returns}
        and all(row['selected_delay'] == 0. and client.rows[row['request_id']]['request']['earliest_departure'] == row['at'] for row in returns))
    reuse_jobs = {key for key in expected if key.startswith('reuse')}
    actual_loads = [row for row in receipts if row['event'] == 'LOAD_START' and row['business_bag_id'] in reuse_jobs]
    same_tray = len(actual_loads) == required_returns and all(row['tray_id'] == 'L' for row in actual_loads)
    route_ok = len(choices) == required_returns and {row['job'] for row in choices} == reuse_jobs
    for choice in choices:
        edges = [row for row in receipts if row['event'] == 'EDGE_ENTER' and row['business_bag_id'] == choice['job']
                 and row['tray_id'] == 'L' and row['from'] == 7]
        route_ok = route_ok and len(edges) == 1 and (choice['next'] is None or edges[0]['to'] == choice['next'])
        if choice['request_id']:
            route_ok = route_ok and ack_ok(choice['request_id'], 'updated')
    replay = plain(data)
    replay['transfers'] = [{**call['request'], 'issued_at': call['at']} for call in client.calls
        if call['kind'] == 'transfer' and not call['retry']]
    try:
        audit = physical.native_host.audit_result(replay, result)
    except (KeyError, ValueError, AssertionError) as error:
        audit = {'status': 'failed', 'reason': str(error)}
    stock = len(result['trays']) == 3 and {row['tray_id'] for row in result['trays']} == {'L', 'E', 'P'}
    valid = complete and supply_ok and returns_ok and same_tray and route_ok and stock and audit['status'] == 'passed'
    return {'status': 'assessed' if valid else 'unknown_incomplete_or_unexecuted', 'completion': completion,
        'business_complete': complete, 'common_horizon_complete': complete, 'completion_sum': sum(completion.values()) if complete else None,
        'supply_recovery_valid': supply_ok, 'all_original_and_new_returns_received': returns_ok,
        'same_L_all_reuse_loads': same_tray, 'all_routes_updated_and_match_edges': route_ok,
        'stock_preserved': stock, 'audit': audit, 'all_input_business_in_evaluator': True,
        'native_model_protection_certified': False}
