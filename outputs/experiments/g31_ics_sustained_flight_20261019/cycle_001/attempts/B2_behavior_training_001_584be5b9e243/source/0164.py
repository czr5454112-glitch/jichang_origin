"""Conservative public-only airport learning inputs, without outcome labels.

This module never loads native or reads private workload/result/crosswalk data.
It adapts an actual owner callback, preserving unknown account coverage. It is
not a native provenance authenticator, candidate guard, trainer, or controller.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

VERSION = 'g31.foundation.airport_learning_public.v1'
ACCOUNT_NAMES = ('current_free_trays', 'known_waiting_jobs', 'loaded_release_forecast',
                 'committed_inbound', 'committed_outbound', 'unresolved_requests')
TERMINAL = frozenset(('received', 'rejected', 'failed', 'expired', 'cancelled'))
COMMITTED = frozenset(('accepted', 'granted', 'dispatching', 'departed', 'in_transit'))


def require(value, reason):
    if not value:
        raise ValueError('airport_learning_public:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def region(node):
    require(type(node) is int and node >= 0, 'public_node_id')
    return 'airport_node_' + str(node)


def validate_public(observation):
    require(observation['schema'] == 'g31.owner_protocol_observation.v1'
            and observation.get('observation_scope') == 'controller_policy', 'actual_policy_payload_scope')
    require(not ({'offline_diagnostics', 'global_result', 'future_jobs', 'private_crosswalk'} & set(observation)), 'private_top_level_payload')
    now = number(observation['now']); owner = observation['owner_id']
    require(now >= 0 and type(owner) is str and owner, 'owner_time')
    nodes = {row['node']: row for row in observation['node_contracts']}
    require(len(nodes) == len(observation['node_contracts']) and nodes, 'unique_public_nodes')
    for node in nodes:
        region(node)
    trays = {}
    for tray in observation['trays']:
        require(tray['tray_id'] not in trays and nodes[tray['node']]['resource_owner'] == owner,
                'unique_locally_visible_physical_tray')
        require(type(tray['generation']) is int and tray['generation'] >= 0, 'tray_generation')
        trays[tray['tray_id']] = tray
    jobs = {}
    for job in observation['jobs']:
        require(job['business_bag_id'] not in jobs and job['status'] != 'unreleased'
                and 0 <= number(job['arrival']) <= now, 'released_unique_public_job')
        jobs[job['business_bag_id']] = job
    for message in observation.get('delivered_messages', []):
        require(0 <= number(message['observed_at']) <= number(message['delivered_at']) <= now, 'actually_delivered_message')
    ledger = observation['client_transfer_ledger']
    require(observation.get('transfers') == ledger, 'own_protocol_ledger_alias_values')
    seen = set()
    for request in ledger:
        require(request['request_id'] not in seen and request['status_scope'] == 'own_payload_and_last_delivered_ack_only'
                and nodes[request['source']]['resource_owner'] == owner and request['destination'] in nodes
                and 0 <= number(request['issued_at']) <= now, 'own_public_request_scope')
        seen.add(request['request_id'])
    return now, owner, nodes, trays, jobs


def adapt_accounts(observation):
    """Six account interface; inbound/outbound completeness stays unknown.

No generation is invented for a departed request whose original generation
was not carried in this public ledger. Active own claims conservatively exclude
the same physical tray from reusable supply, without minting an inbound row.
"""
    now, owner, nodes, trays, jobs = validate_public(observation)
    regions = {region(node) for node in nodes}
    accounts = {name: [] for name in ACCOUNT_NAMES}
    coverage = {name: {key: {'visible': False, 'complete': False, 'observed_at': None} for key in regions}
                for name in ACCOUNT_NAMES}
    accounts['coverage_by_account_region'] = coverage
    local = {node for node, contract in nodes.items() if contract['resource_owner'] == owner}
    for name in ('current_free_trays', 'known_waiting_jobs', 'loaded_release_forecast', 'committed_outbound', 'unresolved_requests'):
        for node in local:
            coverage[name][region(node)] = {'visible': True, 'complete': False, 'observed_at': now}
    active = [row for row in observation['client_transfer_ledger'] if row['status'] not in TERMINAL]
    claimed = {row['tray_id'] for row in active}
    raw_free = {node: 0 for node in local}
    for tray in trays.values():
        key = region(tray['node'])
        common = {'tray_id': tray['tray_id'], 'generation': tray['generation'], 'region': key, 'observed_at': now,
                  'provenance': {'kind': 'current_owner_tray_sensor', 'tray_sha256': digest(tray)}}
        if tray['mode'] == 'empty' and tray['edge_to'] < 0 and number(tray['available_at']) <= now:
            raw_free[tray['node']] += 1
            if tray['tray_id'] not in claimed:
                accounts['current_free_trays'].append(common)
        elif tray['mode'] in ('hold', 'unloading') and tray['tray_id'] not in claimed:
            # Only the local observed deterministic operation is included.
            # Moving/loading tray travel and congestion remain unknown here.
            job = jobs.get(tray.get('business_bag_id'))
            if tray['mode'] == 'hold' or job is not None:
                estimate = max(now, number(tray['available_at']))
                if tray['mode'] == 'unloading':
                    # Public unloading available_at is UNLOAD_START + unload;
                    # a hold tray already carries unload_complete + hold.
                    hold = number(job['hold_seconds'])
                    require(hold >= 0, 'nonnegative_observed_hold_duration')
                    estimate += hold
                accounts['loaded_release_forecast'].append({**common, 'available_at': estimate, 'status': 'conditional',
                    'estimate_scope': 'conditional_local_duration_not_congestion_upper_bound_or_free_inventory'})
    for node in local:
        sensor = nodes[node].get('actual_available')
        if type(sensor) is not int or sensor != raw_free[node]:
            # The public tray shape lacks active_leg. A sensor disagreement
            # cannot be repaired with a guessed identity or an inflated bound.
            accounts['current_free_trays'] = [row for row in accounts['current_free_trays'] if row['region'] != region(node)]
        counted = sum(row['region'] == region(node) for row in accounts['current_free_trays'])
        coverage['current_free_trays'][region(node)]['complete'] = (
            type(sensor) is int and sensor == raw_free[node] == counted)
    projection = observation['control_projection']
    require(projection['schema'] == 'g31.analytic_control_projection.v1', 'public_waiting_projection')
    grouped = set()
    for group in projection['waiting_groups']:
        origin = group['origin']; key = region(origin)
        require(origin in nodes and origin not in grouped, 'one_waiting_group_per_public_origin')
        grouped.add(origin)
        observed = number(group['demand_observed_at'])
        require(0 <= observed <= now, 'waiting_capture_cutoff')
        count = group.get('count')
        require(count is None or type(count) is int and count >= len(group['jobs']), 'waiting_count_not_representative_length')
        ids = set()
        for job in group['jobs']:
            require(job['business_bag_id'] not in ids and job['origin'] == origin
                    and job['status'] in ('waiting', 'waiting_for_tray')
                    and 0 <= number(job['arrival']) <= number(job['demand_observed_at']) <= observed, 'public_waiting_representative_cutoff')
            ids.add(job['business_bag_id'])
        # An exact captured group count is still not proof that this generic
        # callback carries every local origin. A future producer-bound scope
        # contract may establish completeness; a schema name cannot do so.
        coverage['known_waiting_jobs'][key] = {'visible': True, 'complete': False,
                                             'observed_at': observed}
        accounts['known_waiting_jobs'].append({'kind': 'waiting_group', 'origin': origin, 'region': key,
            'observed_at': observed, 'count': count,
            'provenance': {'kind': 'public_control_projection_waiting_group', 'group_sha256': digest(group)}})
    for request in active:
        if request['status'] not in COMMITTED:
            accounts['unresolved_requests'].append({'request_id': request['request_id'], 'region': region(request['source']),
                'observed_at': now, 'native_status': request['status'],
                'provenance': {'kind': 'own_public_ledger', 'request_sha256': digest(request)}})
    # The callback lacks receiver-public transfer payload+ACK and original
    # submission generation. Empty rows in these accounts remain masked.
    audit = {'schema': VERSION, 'observation_sha256': digest(observation), 'owner': owner, 'now': now,
        'unknown_inbound_not_zero': True, 'unknown_outbound_generation_not_inferred': True,
        'excluded_active_claim_trays': sorted(claimed), 'observed_counts_for_flight_model': None,
        'waiting_coverage_basis': 'captured_group_counts_only_complete_native_origin_scope_not_attested',
        'private_lookup_used': False, 'native_execution_authority': False,
        'label_status': 'no_outcome_labels_created', 'coverage_source': 'caller_must_bind_actual_native_callback_artifact'}
    return accounts, audit


def extend_forecast_with_unknown_nodes(forecast, observation):
    """Support terminal-source actions without fabricating zero demand there."""
    now, owner, nodes, _, _ = validate_public(observation)
    require(forecast['schema'] == 'g31.foundation.new_demand_forecast.v1'
            and forecast['owner_scope'] == owner and number(forecast['forecast_origin']) == now, 'current_owner_forecast')
    result = copy.deepcopy(forecast)
    available = set(result['new_demand_mean_by_region'])
    require(available <= {region(node) for node in nodes}, 'forecast_in_public_node_domain')
    bins = len(result['bin_edges_seconds']) - 1
    require(bins > 0, 'nonempty_forecast_bins')
    for node in nodes:
        key = region(node)
        if key not in available:
            result['new_demand_mean_by_region'][key] = [None] * bins
            result['missing_mask_by_region'][key] = True
            result.setdefault('uncertainty_by_region', {})[key] = None
    result['source_forecast_sha256'] = digest(forecast)
    result['source_mapping_version_before_public_adapter'] = forecast['mapping_version']
    result['mapping_version'] = forecast['mapping_version'] + '+' + VERSION
    result['nonforecast_public_nodes'] = 'unknown_not_assumed_structural_zero'
    return result


def wrap_record(record, forecast, *, episode_id, episode_end):
    """Produce inputs consumed by the existing action-conditioned NN API."""
    from . import foundation_action_value as value
    require(record['schema'] == 'g31.foundation.airport_policy_observation.v1'
            and record['readonly'] is True and record['native_execution_authority'] is False
            and record['candidate_conditional_labels'] is None, 'actual_callback_record_without_labels')
    observation = record['observation']
    require(record['owner_id'] == observation['owner_id'] and record['now'] == observation['now'], 'record_owner_time')
    accounts, audit = adapt_accounts(observation)
    expanded = extend_forecast_with_unknown_nodes(forecast, observation)
    wrapped = value.wrap_observation(episode_id=episode_id, owner=record['owner_id'], decision_id=str(record['sequence']),
        now=record['now'], base_observation=observation, forecast=expanded, accounts=accounts,
        information_variant='static_plan' if expanded.get('context_sha256') is not None else 'no_plan',
        remaining_episode_seconds=number(episode_end)-record['now'], mapping_version=expanded['mapping_version'],
        flight_context_sha256=expanded.get('context_sha256'))
    return wrapped, audit


def proposal_actions(record):
    """Recorded proposals are features only; neither chosen nor executed labels."""
    from .analytic_control import PublicTravel
    observation = record['observation']; now, owner, nodes, trays, _ = validate_public(observation)
    travel = PublicTravel(observation); result = []
    for index, proposal in enumerate(record['decision']['intents']):
        source, destination = proposal['source'], proposal['destination']
        require(proposal['owner_id'] == owner and nodes[source]['resource_owner'] == owner
                and proposal['tray_id'] in trays and destination in nodes, 'proposal_public_entity_scope')
        departure = max(now + number(proposal['message_delay']), number(proposal['earliest_departure']))
        arrival = departure + travel.complete(source, destination)
        require(math.isfinite(arrival) and arrival >= now, 'reachable_public_freeflow_estimate')
        result.append({'action_id': 'recorded_proposal_' + str(index), 'semantic': {'kind': 'transfer',
            'source_region': region(source), 'destination_region': region(destination), 'earliest_legal_arrival': arrival},
            'source_proposal_sha256': digest(proposal), 'arrival_scope': 'public_static_capacity_relaxed_estimate',
            'enabled': None, 'outcome_label': None, 'status': 'proposal_only_requires_current_native_guard_and_execution_binding'})
    return result
