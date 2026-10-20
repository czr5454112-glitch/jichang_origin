"""Saved-data replay for the one-recollection policy; never native authority."""
from __future__ import annotations
import copy, math
from types import SimpleNamespace
from . import research_live_obligation_native_domain as prior
from . import domain_guard_v2 as guard
from . import live_obligation_recollection_policy as policy

require, json_value = prior.require, prior.json_value


def verify_call_history(raw):
    """All immutable payloads and call times, including calls after decisions."""
    requests = {}; previous = -1.
    for call in raw['calls']:
        at = call['at']; request = call['request']; key = request['request_id']
        require(type(at) in (int, float) and math.isfinite(at) and previous <= at <= 40.,
                'whole_call_chronology')
        require(type(key) is str and bool(key) and request['owner_id'] in ('A', 'B'), 'whole_call_identity')
        require(key not in requests or requests[key] == (call['kind'], request), 'whole_immutable_request')
        requests[key] = (call['kind'], request); previous = at
    return {'calls': len(raw['calls']), 'immutable_requests': len(requests)}


def verify_terminal_receipts(raw):
    """Bind completion claims to actual native terminal receipts, exactly."""
    rows = raw['result']['jobs']; jobs = {r['business_bag_id']: r for r in rows}
    require(len(rows) == len(jobs) == 5 and set(jobs) == prior.model.JOBS, 'five_terminal_job_domain')
    require({r['business_bag_id'] for r in raw['input']['jobs']} == set(jobs)
            and len(raw['input']['jobs']) == 5, 'five_input_job_domain')
    times = {}
    for key, row in jobs.items():
        receipts = [r for r in raw['result']['receipts']
                    if r['event'] == 'UNLOAD_COMPLETE' and r['business_bag_id'] == key]
        if row['status'] == 'completed':
            at = row['completed_at']
            require(len(receipts) == 1 and type(at) in (int, float) and math.isfinite(at)
                    and 0 <= at == receipts[0]['time'] <= 40., 'actual_terminal_receipt:' + key)
            times[key] = at
        else:
            require(not receipts and row['completed_at'] < 0, 'unfinished_terminal_contradiction:' + key)
            times[key] = None
    return times


def prefix_requests(raw, owner, entry):
    count = entry['predecision_call_prefix_count']; calls = raw['calls']
    require(type(count) is int and 0 <= count <= len(calls), 'attempt_call_boundary')
    require(all(c['at'] <= entry['at'] for c in calls[:count]), 'attempt_future_prior_call')
    require(count == len(calls) or calls[count]['at'] >= entry['at'], 'attempt_past_next_call')
    rows = {}
    for call in calls[:count]:
        request = call['request']; key = request['request_id']
        if request['owner_id'] != owner: continue
        require(key not in rows or rows[key] == (call['kind'], request), 'changed_immutable_request')
        rows[key] = (call['kind'], request)
    return rows


def owned_at_view(requests, view):
    endpoints = {r['request_id']: r for r in view['client_requests'] + view['client_commands']}
    require(len(endpoints) == len(view['client_requests']) + len(view['client_commands']), 'duplicate_owned_endpoint')
    rows = {}
    for key, (kind, request) in requests.items():
        require(key in endpoints, 'missing_owned_request_endpoint')
        ack = copy.deepcopy(endpoints[key].get('last_delivered_ack', {}))
        rows[key] = {'request': request, 'kind': kind, 'ack': ack,
                     'terminal': ack.get('status') in policy.TERMINAL_BY_KIND.get(kind, ())}
    return rows


def replay_information(raw, owner, entry):
    info = entry['information']; endpoint = info['raw_endpoints']; read = info['native_read']
    pending = entry['collection']; requests = prefix_requests(raw, owner, entry)
    own_id = pending['request_id']
    require(own_id in requests and requests[own_id][0] == 'planning_snapshot_v3', 'attempt_own_publication')
    require(entry['phase'] == pending['phase'] and entry['actual_local_view'] == endpoint['view']
            and endpoint['view']['owner_id'] == owner and endpoint['view']['now'] == entry['at'], 'attempt_current_view')
    actual_read = {'owner': owner, 'own_request_id': own_id, 'at': entry['at'],
        'native_binary': raw['retained_ledgers'][owner]['native_binary'],
        'acceptance': raw['native027_acceptance'], 'selected_peer_message_id': pending['peer_message'],
        'collection_started_at': pending['at'],
        'actual_endpoints': ['observe_protocol', 'protocol_command', 'protocol_planning_snapshots_v3']}
    require(read == actual_read, 'attempt_actual_read_binding')
    actions = sorted((k, kind) for k, (kind, _) in requests.items() if kind in policy.PHYSICAL_KINDS)
    replay = guard.validate_collected_endpoints(endpoint['view'], endpoint['command'], endpoint['received'],
        retained=raw['retained_ledgers'][owner], own_actions=actions, phase=entry['phase'],
        own_request_id=own_id, peer_message_id=pending['peer_message'], collection_started_at=pending['at'],
        policy_quiet_since=pending['policy_quiet_since'], own_request=requests[own_id][1])
    expected = json_value(replay); known = replay['status'] == 'conditional_validated_later_v3_data'
    expected['native_read'] = actual_read
    if known:
        expected.update(status='conditional_native_delivered_later_v3_model_input',
            native_delivery_verified=True, online_information_delivered=True,
            conditional_stability_only=True, current_state_certified=False,
            native_protection_certified=False)
    require(info == expected, 'complete_attempt_endpoint_replay')
    return known, requests, owned_at_view(requests, endpoint['view'])


def verify_attempts(raw, *, partial=False):
    attempts = raw.get('collection_attempts')
    require(type(attempts) is dict and set(attempts) == {'A', 'B'}, 'complete_attempt_owner_domain')
    totals = {'attempts': 0, 'fresh_pairs': 0, 'final_decisions': 0, 'verified_final_inputs': 0}
    for owner in ('A', 'B'):
        sequence = attempts[owner]; decisions = raw.get('decisions', {}).get(owner, [])
        require(type(sequence) is list and len(sequence) <= 2 and len(decisions) <= 1, 'bounded_phase_attempts')
        phase = 'first_return' if owner == 'A' else 'first_reuse_route'
        for index, entry in enumerate(sequence):
            totals['attempts'] += 1
            pending = entry['collection']
            require(entry['phase'] == phase and pending['recollection_index'] == index
                    and type(pending['recollection_index']) is int, 'attempt_phase_order')
            require(pending['policy_quiet_since'] == sequence[0]['collection']['at'], 'original_quiet_start')
            if index:
                previous = sequence[index - 1]; original = previous['collection']
                require(previous.get('disposition') == 'one_fresh_pair_requested'
                        and pending['request_id'] == previous['new_request_id']
                        and pending['original_request_id'] == original['request_id']
                        and pending['at'] == previous['at'] and entry['at'] >= pending['at']
                        and pending['trigger_tray'] == original['trigger_tray'] and pending['root'] == original['root'],
                        'new_pair_original_intent_binding')
                bound = previous['retry_admission']['retained_own_service_bound']
                deadline = previous['at'] + policy.bound.COLLECTION_LIMIT
                if bound is not None: deadline = min(deadline, bound)
                require(pending['deadline'] == deadline and pending['retry_admission'] == previous['retry_admission'],
                        'new_pair_deadline_binding')
            known, requests, owned = replay_information(raw, owner, entry)
            screen = {'status': 'not_admitted', 'reason': 'actual_failed_owner_read_required'}
            if not known:
                screen = policy.retry_admission(entry['information'], pending, entry['actual_local_view'], owned)
            require(entry['retry_admission'] == screen, 'retry_screen_replay')
            disposition = entry.get('disposition')
            if disposition == 'one_fresh_pair_requested':
                require(index == 0 and not known and screen['status'] == 'conditional_retry_admissible', 'retry_not_admitted')
                key = entry['new_request_id']; count = entry['predecision_call_prefix_count']
                require(key != pending['request_id'] and key not in requests and count < len(raw['calls']), 'fresh_request_identity')
                call = raw['calls'][count]; request = call['request']
                require(call['at'] == entry['at'] and call['retry'] is False and call['kind'] == 'planning_snapshot_v3'
                        and request['request_id'] == key and request['owner_id'] == owner
                        and request['target_owner'] == ('B' if owner == 'A' else 'A')
                        and request['message_delay'] == request['publication_delay'] == .01
                        and request['expiry'] == entry['at'] + policy.bound.CAPTURE_VALIDITY, 'fresh_pair_actual_submission')
                cause = raw['request_creations'][key]['causal']
                require(cause == {'relation': 'replacement_replan', 'continuation_parent_roots': [pending['root']],
                    'predecessor_protocol_id': pending['request_id'], 'collection_phase': phase,
                    'actual_failed_collection_reason': entry['information'].get('reasons', []),
                    'same_original_target': pending['trigger_tray'], 'fresh_pair_index': 1}, 'fresh_pair_causal_parent')
                totals['fresh_pairs'] += 1
                if not partial: require(index + 1 < len(sequence), 'fresh_pair_missing_final_attempt')
            elif disposition == 'final_decision_no_more_recollection':
                require(index == len(sequence) - 1 and len(decisions) == 1, 'final_attempt_decision_binding')
                decision = decisions[0]
                for field in ('at', 'phase', 'collection', 'information', 'actual_local_view', 'predecision_call_prefix_count'):
                    require(decision[field] == entry[field], 'final_attempt_changed:' + field)
                require(decision['fallback_used'] is (not known), 'final_fallback_status')
                selected = decision['decision'].get('selected_action')
                expected = {'return_delay': raw['specification']['vector']['return_delay'],
                    'reuse_next': 8 if raw['specification']['vector']['later_action'] == 'prefer_8' else None}
                require(selected == (expected if known else None), 'fixed_final_action')
                if decision['selected_action_admitted'] is True:
                    require(known and decision['final_local_guard_reason'] is None, 'unverified_final_action')
                    policy.local_target(entry['actual_local_view'], pending['trigger_tray'], phase)
                    if owner == 'B':
                        require(entry['at'] + .01 < entry['information']['bundle']['trays']['L']['service_ready_at'],
                                'final_wire_outside_own_service')
                    else:
                        require(max(entry['at'] + .01, prior.return_earliest(entry['at'], expected['return_delay'], 0)) < 39.,
                                'final_transfer_expiry')
                request_id = decision['native_request_id']; count = entry['predecision_call_prefix_count']
                if request_id is not None:
                    require(count < len(raw['calls']) and raw['calls'][count]['request']['request_id'] == request_id
                            and raw['calls'][count]['at'] == entry['at'], 'final_action_call_boundary')
                totals['final_decisions'] += 1; totals['verified_final_inputs'] += int(known)
            else:
                require(partial and disposition is None, 'unknown_attempt_disposition')
        if not partial:
            require(len(sequence) >= 1 and len(decisions) == 1, 'missing_required_phase')
    return totals


def verify_saved(raw):
    # Initial-stage validation byte-for-byte through the original helper.
    initial = dict(raw); initial['decisions'] = {}
    prior.verify_saved_inputs(initial)
    if 'continuation' not in raw:
        require(raw['summary']['status'] == 'unknown_initial_asymmetry_or_missing_ledger'
                and raw['summary']['business_metrics'] is None
                and raw.get('collection_attempts') == {'A': [], 'B': []}, 'initial_unknown_no_later_claim')
        return {'status': 'initial_unknown_preserved', 'physical_protection': 'unknown'}
    report = verify_attempts(raw)
    report['whole_call_history'] = verify_call_history(raw)
    report['actual_terminal_times'] = verify_terminal_receipts(raw)
    report['bounded_reply_replay'] = verify_replies(raw)
    rebuilt = prior.completed_summary(raw['input'], raw['result'],
        SimpleNamespace(rows=raw['outbox'], calls=raw['calls']), raw['continuation'],
        raw['specification']['vector'], raw['initial_owners'], raw['decisions'])
    require(rebuilt == raw['summary'], 'full_physical_action_assessment')
    # The ordinary assessor always checks H40, every job/tray, all required
    # transfer ACKs, actual EDGE_ENTER and mandatory Storage. Unknown stays so.
    report['physical_audit'] = rebuilt.get('audit', {})
    report['common_horizon_complete'] = rebuilt['common_horizon_complete']
    report['five_jobs_physically_complete'] = rebuilt['business_complete']
    return report


def verify_replies(raw):
    counts = {}
    for owner, exchanges in raw['exchanges'].items():
        budget = policy.PhaseReplyBudget(); deferred = {}; times = []
        for exchange in exchanges:
            times.append(exchange['at']); kind = exchange['kind']
            if kind not in ('reply', 'immutable_ack_refresh_before_reply',
                            'not_a_new_bounded_phase_invitation', 'reply_after_delivered_received_ack'):
                continue
            envelope = exchange['message']; body = envelope['capture']; local = body['capture_v2']['local_capture']
            require(guard.old.capture_digest_v3(body) == envelope['payload_sha256'], 'reply_capture_digest')
            phase = policy.bound.invitation_phase(envelope, owner, exchange['at'])
            if kind == 'reply_after_delivered_received_ack':
                require(local['message_id'] in deferred, 'unrequested_deferred_reply')
                waiting = deferred.pop(local['message_id']); cause = exchange['causal']
                require(cause['immutable_retry_request_ids'] == waiting
                        and set(cause['delivered_terminal_acknowledgements']) == set(waiting), 'deferred_reply_scope')
                require(all(a['status'] == 'received' and a['delivered_at'] <= exchange['at']
                            for a in cause['delivered_terminal_acknowledgements'].values()), 'deferred_reply_before_ack')
                continue
            admitted = budget.admit(phase, local)
            if kind == 'not_a_new_bounded_phase_invitation':
                require(not admitted, 'unjustified_ignored_invitation'); continue
            require(admitted, 'reply_budget_exceeded')
            if kind == 'immutable_ack_refresh_before_reply':
                require(phase == 'reuse1_loading_ack_refresh' and owner == 'A', 'preflight_owner')
                deferred[local['message_id']] = exchange['request_ids']
            else:
                key = exchange['request_id']; cause = raw['request_creations'][key]['causal']
                require(cause['delivered_parent_message'] == {'message_id': local['message_id'],
                    'source_owner': local['source_owner'], 'captured_at': local['captured_at'],
                    'delivered_at': envelope['delivered_at']}, 'reply_actual_parent')
        require(times == sorted(times), 'exchange_chronology')
        counts[owner] = {phase: len(rows) for phase, rows in budget.rows.items()}
    return counts


def verify_partial(raw):
    require(raw.get('partial') is True and raw.get('summary', {}).get('status') == 'unknown_failed_partial',
            'partial_status')
    require(raw['summary'].get('business_metrics') is None and raw['summary'].get('strict_protected') is None,
            'partial_no_protection')
    require(raw.get('result_capture_rule') == 'only_preexisting_result; result_at_not_called_after_exception',
            'partial_no_advance')
    if 'input' in raw: prior.validate_runtime_input(raw['input'])
    require(type(raw.get('collection_attempts')) is dict and set(raw['collection_attempts']) == {'A', 'B'},
            'partial_attempt_export')
    if 'physical_time_after_diagnostics' in raw:
        require(raw['physical_time_after_diagnostics'] == raw['physical_time'], 'partial_diagnostic_advanced')
    can_replay = ('retained_ledgers' in raw and 'native027_acceptance' in raw
                  and set(raw.get('initial_owners', {})) == {'A', 'B'})
    if can_replay:
        initial = dict(raw); initial['decisions'] = {}; prior.verify_saved_inputs(initial)
        verify_attempts(raw, partial=True)
    return {'status': 'available_prefix_checked_not_complete', 'attempts_replayed': can_replay,
            'physical_protection': 'unknown'}
