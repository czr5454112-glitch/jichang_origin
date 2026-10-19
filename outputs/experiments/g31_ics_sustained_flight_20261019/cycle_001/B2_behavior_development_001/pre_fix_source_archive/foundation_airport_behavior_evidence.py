"""Detached, fail-closed airport behavior-label checks. No native or fitting.

Artifact hashes and producer source archives must be verified by the caller.
This module checks data relations, not native authority. Offline receipt data
never becomes an actor observation. All samples from one physical trajectory
belong to one train-only parent, regardless of flight or time window.
"""
from __future__ import annotations

from collections import defaultdict
import copy
import hashlib
import json
import math

SCHEMA = 'g31.foundation.airport_behavior_evidence.v1'
WINDOW_SECONDS = 300.
FORECAST_FROZEN_AT = 43200.
LABELS_CLOSED_AT = 57600.
SEEDS = (17, 29, 43)
EPOCHS = 100
POSITIVE_ACKS = frozenset(('granted', 'accepted', 'dispatching', 'departed', 'in_transit', 'received'))
NEGATIVE_ACKS = frozenset(('rejected', 'failed', 'expired', 'cancelled'))


def require(ok, reason):
    if not ok:
        raise ValueError('airport_behavior_evidence:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def bind_submissions(callbacks, owner_decision, calls, *, at):
    """Join the actual residual callback chain to first submissions exactly.

The source controller calls again after EVERY pending submit, including the
last bounded iteration. Therefore the final residual can contain proposals
that were never submitted. Retry calls never represent another choice.
"""
    require(bool(callbacks), 'complete_callback_group_required')
    at = number(at); owner = owner_decision['owner_id']
    require(all(row['schema'] in ('g31.foundation.airport_policy_observation.v1','g31.foundation.airport_policy_observation.v2')
                and row['owner_id'] == owner and number(row['now']) == at
                and row['observation']['owner_id'] == owner and number(row['observation']['now']) == at
                and row['readonly'] is True and row['candidate_conditional_labels'] is None
                for row in callbacks), 'callback_owner_time_and_no_labels')
    require(all(a['sequence'] < b['sequence'] for a, b in zip(callbacks, callbacks[1:])), 'callback_sequence_order')
    require(callbacks[0]['decision'] == owner_decision['decision'], 'initial_decision_exact_bytes')
    attempts = owner_decision['attempts']; initial_limit = len(callbacks[0]['decision']['intents'])
    require(len(attempts) <= initial_limit and bool(attempts) == bool(initial_limit), 'bounded_attempt_count')
    expected_callbacks = len(attempts) + (not attempts or attempts[-1]['reply'].get('status') == 'pending')
    require(len(callbacks) == expected_callbacks, 'complete_residual_callback_chain')
    first_calls = defaultdict(list)
    for call in calls:
        if call['kind'] == 'transfer' and call['retry'] is False:
            first_calls[call['request']['request_id']].append(call)
    result = []; seen = set()
    for index, attempt in enumerate(attempts):
        row = callbacks[index]; identity = attempt['request_id']
        require(identity not in seen and row['decision']['intents'], 'unique_nonempty_chosen_attempt')
        seen.add(identity)
        require(index == 0 or attempts[index-1]['reply'].get('status') == 'pending', 'no_attempt_after_nonpending')
        require(len(first_calls[identity]) == 1, 'unique_first_nonretry_submission')
        call = first_calls[identity][0]
        require(number(call['at']) == at and call['reply'] == attempt['reply'], 'actual_submit_time_reply')
        proposed = row['decision']['intents'][0]
        expected = copy.deepcopy(proposed); expected.pop('expected_version', None)
        expected.update(request_id=identity, owner_id=owner)
        require(call['request'] == expected and number(expected['issued_at']) == at, 'exact_selected_payload_transformation')
        trays = [tray for tray in row['observation']['trays'] if tray['tray_id'] == expected['tray_id']]
        require(len(trays) == 1 and trays[0]['node'] == expected['source'], 'actual_pre_submit_tray_source')
        require(not any(r['request_id'] == identity for r in row['observation']['client_transfer_ledger']), 'request_absent_before_submit')
        result.append({'schema': SCHEMA, 'status': 'submitted_not_yet_execution_label', 'owner': owner,
            'at': at, 'callback_sequence': row['sequence'], 'callback_sha256': digest(row),
            'actual_request': copy.deepcopy(call['request']), 'submission_reply': copy.deepcopy(call['reply']),
            'pre_submit_tray': copy.deepcopy(trays[0]), 'call_sha256': digest(call),
            'attempt_sha256': digest(attempt), 'target_value': None, 'action_index': 0})
    if attempts and attempts[-1]['reply'].get('status') == 'pending' and len(attempts) < initial_limit:
        require(not callbacks[-1]['decision']['intents'], 'early_stop_requires_empty_residual')
    return result


def snapshot_index(result, *, expected_population=28506):
    """Index a full-population snapshot at a completed native timestamp."""
    clock = number(result['physical_clock'])
    require(result['advance']['status'] == 'reached' and result['advance']['horizon_complete'] is True,
            'closed_native_timestamp')
    jobs = {row['business_bag_id']: row for row in result['jobs']}
    require(len(jobs) == len(result['jobs']) == expected_population, 'complete_unique_physical_population')
    arrivals = {}; completions = {}; by_leg = defaultdict(list); by_request = defaultdict(list)
    for row in result['receipts']:
        event_time = number(row['time']); require(0 <= event_time <= clock, 'receipt_not_future_to_snapshot')
        if row['event'] == 'BAG_ARRIVAL':
            identity = row['business_bag_id']
            require(identity in jobs and identity not in arrivals, 'unique_actual_arrival_per_business')
            arrivals[identity] = event_time
        if row['event'] == 'UNLOAD_COMPLETE':
            identity = row['business_bag_id']
            require(identity in jobs and identity not in completions, 'unique_actual_completion_per_business')
            completions[identity] = event_time
        if row.get('transport_leg_id'):
            by_leg[row['transport_leg_id']].append(row)
        if row['event'] in ('EXPORT_GRANTED', 'EMPTY_RECEIVED', 'MODULE_REQUEST_DELIVERED'):
            by_request[row['reason']].append(row)
    for identity, row in jobs.items():
        require((identity in arrivals) == (row['status'] != 'unreleased'), 'arrival_receipt_matches_actual_job_status')
        completed_at = number(row['completed_at'])
        require((completed_at >= 0) == (identity in completions) == (row['status'] == 'completed'), 'completion_receipt_matches_status')
        if identity in completions:
            require(arrivals[identity] <= completions[identity] == completed_at <= clock, 'completion_clock_matches_receipt')
    require(result['population']['observed'] == len(arrivals)
            and result['population']['completed'] == len(completions), 'actual_population_receipt_counts')
    transfers = {row['request_id']: row for row in result['transfers']}
    require(len(transfers) == len(result['transfers']), 'unique_native_transfer')
    legs = defaultdict(list)
    for row in result['leg_identities']:
        if row['kind'] == 'empty_return':
            suffix = ':empty_return:' + str(row['runtime_id'])
            require(row['transport_leg_id'].endswith(suffix), 'native_empty_leg_identity_shape')
            legs[row['transport_leg_id'][:-len(suffix)]].append(row)
    return {'clock': clock, 'population': expected_population, 'jobs': jobs, 'arrivals': arrivals,
            'completions': completions, 'transfers': transfers, 'legs': legs,
            'receipts_by_leg': by_leg, 'receipts_by_request': by_request, 'trays': result['trays']}


def execution_asof(submission, index, owner_ack_view, *, label_end):
    """Require an actual empty-transfer departure and delivered positive ACK.

First EDGE_ENTER establishes execution. Receiving within the 300s window is
not required; choosing only transfers later received would condition on the
future. Later ACKs/receipts cannot make an earlier sample eligible.
"""
    start = number(submission['at']); end = number(label_end)
    require(start <= end <= index['clock'], 'execution_label_window_closed')
    request = submission['actual_request']; identity = request['request_id']
    require(owner_ack_view['owner_id'] == request['owner_id'] == submission['owner']
            and number(owner_ack_view['now']) >= end, 'owner_actual_ack_scope')
    acks = []
    for ack in owner_ack_view['delivered_transfer_acks']:
        if ack['request_id'] != identity:
            continue
        observed = number(ack['observed_at']); delivered = number(ack['delivered_at'])
        require(start <= observed <= delivered <= number(owner_ack_view['now']), 'ack_causal_time')
        if delivered <= end:
            acks.append(ack)
    transfer = index['transfers'].get(identity)
    legs = index['legs'].get(identity, [])
    require(len(legs) <= 1, 'unique_native_request_leg')
    receipts = index['receipts_by_leg'].get(legs[0]['transport_leg_id'], []) if legs else []
    edges = sorted((r for r in receipts if r['event'] == 'EDGE_ENTER' and start <= r['time'] <= end), key=lambda r:r['time'])
    if not edges:
        negative = [a for a in acks if a['status'] in NEGATIVE_ACKS]
        return {'status': 'acknowledged_not_executed_' + negative[-1]['status'] if negative else 'no_physical_execution_in_label_window',
                'target_value': None, 'positive_ack_count': sum(a['status'] in POSITIVE_ACKS for a in acks)}
    require(transfer is not None and len(legs) == 1, 'physical_execution_has_native_transfer')
    leg = legs[0]; first = edges[0]
    require(type(transfer['tray']) is int and 0 <= transfer['tray'] < len(index['trays'])
            and leg['tray'] == transfer['tray'] and leg['job'] == -1
            and index['trays'][transfer['tray']]['tray_id'] == request['tray_id'], 'native_transfer_leg_tray_identity')
    require(first['tray_id'] == request['tray_id'] and first['from'] == request['source']
            and len([r for r in edges if r['time'] == first['time']]) == 1
            and number(transfer['departed_at']) == first['time'], 'unique_actual_first_edge_departure')
    require(first['time'] >= max(start+number(request['message_delay']), number(request['earliest_departure'])), 'actual_edge_after_delivery_departure_bound')
    grants = [r for r in index['receipts_by_request'][identity] if r['event'] == 'EXPORT_GRANTED' and start <= r['time'] <= first['time']]
    starts = [r for r in receipts if r['event'] == 'LEG_START' and start <= r['time'] <= first['time']]
    require(len(grants) == len(starts) == 1 and all(r['tray_id'] == request['tray_id']
        and r['from'] == request['source'] and r['to'] == request['destination'] for r in grants+starts), 'unique_export_and_leg_start_payload')
    positive = [a for a in acks if a['status'] in POSITIVE_ACKS]
    if not positive:
        return {'status': 'physical_execution_without_delivered_positive_ack_in_label_window', 'target_value': None}
    require(not any(a['status'] in ('rejected','expired') for a in acks), 'executed_transfer_cannot_be_rejected_or_expired')
    received = [r for r in index['receipts_by_request'][identity] if r['event'] == 'EMPTY_RECEIVED' and r['time'] <= end]
    require(len(received) <= 1, 'unique_empty_receipt')
    if received:
        require(received[0]['tray_id'] == request['tray_id'] and received[0]['transport_leg_id'] == leg['transport_leg_id']
            and received[0]['node'] == request['destination'] and number(transfer['received_at']) == received[0]['time'], 'received_transfer_exact_payload')
    return {'status': 'actual_execution_and_delivered_ack_bound', 'first_edge': copy.deepcopy(first),
            'native_leg': copy.deepcopy(leg), 'positive_ack': copy.deepcopy(min(positive,key=lambda a:a['delivered_at'])),
            'received_within_label_window': bool(received), 'counterfactual_protection_certified': False,
            'receiver_inbound_actor_account_created': False}


def realized_return(index, *, start):
    """Negative full-population arrived-unfinished bag-seconds over [t,t+300]."""
    start = number(start); end = start + WINDOW_SECONDS
    require(FORECAST_FROZEN_AT <= start and end <= min(LABELS_CLOSED_AT, index['clock']), 'registered_label_time_cutoffs')
    contributions = []
    for identity, arrived in index['arrivals'].items():
        if arrived >= end:
            continue
        closed = min(end, index['completions'].get(identity, end))
        contributions.append(max(0., closed-max(start,arrived)))
    integral = math.fsum(contributions)
    require(math.isfinite(integral) and integral >= 0, 'finite_actual_integral')
    return {'target_value': -integral, 'label_start': start, 'label_end': end,
        'horizon_seconds': WINDOW_SECONDS, 'discount': 1., 'unit': 'negative_bag_seconds',
        'reward_kind': 'realized_behavior_continuation_full_arrived_unfinished_integral',
        'physical_population': index['population'], 'no_full_day_completion_claim': True,
        'future_completion_imputed': False, 'counterfactual_label': False}


def training_contract(trajectory_id):
    require(type(trajectory_id) is str and trajectory_id, 'single_trajectory_parent_identity')
    return {'schema': SCHEMA, 'split': 'train', 'parent_group': trajectory_id,
        'all_windows_and_flight_parents_same_split': True, 'independent_development_or_test': False,
        'seeds': list(SEEDS), 'epochs': EPOCHS, 'checkpoint_selection': 'fixed_last_epoch_no_development_selection',
        'objective': 'supervised_realized_300s_behavior_value_not_optimal_Q_or_RL',
        'earliest_model_use_sim_time': LABELS_CLOSED_AT, 'native_population_deleted': 0,
        'forecast_frozen_at': FORECAST_FROZEN_AT, 'labels_closed_at': LABELS_CLOSED_AT,
        'native_consumption_scope': 'same_trajectory_continuation_or_shadow_diagnostic_no_control_benefit_claim'}
