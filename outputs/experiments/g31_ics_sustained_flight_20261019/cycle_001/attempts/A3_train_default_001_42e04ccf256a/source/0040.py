"""Small-domain action-conditioned values over detached legal observations.

This pure numerical consumer imports no native/controller/domain modules. IDs
bind observations but never become features. The exporter owns reward/TD
provenance certification; fitting this network does not certify RL readiness.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

import numpy as np

OBSERVATION_SCHEMA = 'g31.foundation.repeated_observation.v1'
FEATURE_SCHEMA = 'g31.foundation.repeated_semantic_features.v1'
MODEL_SCHEMA = 'g31.foundation.repeated_action_value.v1'
FIELDS = {'schema', 'owner', 'at', 'opportunity', 'local_view', 'delivered_v3',
    'known_contracts', 'own_outbox', 'account_summary', 'privileged_evaluator_state_included',
    'reference_included', 'timing_mode', 'remaining_horizon_s'}
CONTRACT_FIELDS = {'business_bag_id', 'origin', 'destination', 'arrival', 'deadline', 'storage_node',
    'storage_release_at', 'storage_min_dwell', 'load_seconds', 'unload_seconds', 'hold_seconds',
    'protected_service', 'allow_suffix_reroute'}
JOB_STATES = ('waiting_for_tray', 'loading', 'in_transit', 'storage', 'unloading', 'completed', 'handed_off')
TRAY_MODES = ('empty', 'loading', 'loaded', 'storage', 'unloading', 'hold', 'empty_transit')


def require(value, reason):
    if not value:
        raise ValueError('repeated_value:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def plain(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError('repeated_value:detached_finite_JSON_required') from error


def _jobs(jobs, at):
    require(type(jobs) is list, 'job_list')
    ids = set()
    for job in jobs:
        require(job['business_bag_id'] not in ids, 'duplicate_job_identity')
        ids.add(job['business_bag_id'])
        require(0 <= number(job['arrival']) <= at and job['status'] in JOB_STATES, 'unreleased_or_future_actor_job')
        for field in ('loaded_at', 'completed_at', 'storage_entered_at', 'storage_released_at'):
            if field in job:
                stamp = number(job[field])
                require(stamp == -1 or 0 <= stamp <= at, 'future_observed_job_event')
        for field in ('load_seconds', 'unload_seconds', 'hold_seconds', 'storage_min_dwell'):
            if field in job:
                require(number(job[field]) >= 0, 'nonnegative_service_contract')
        number(job['deadline'])


def _trays(trays):
    require(type(trays) is list, 'tray_list')
    ids = set()
    for tray in trays:
        require(tray['tray_id'] not in ids and tray['mode'] in TRAY_MODES, 'duplicate_or_unsupported_tray')
        ids.add(tray['tray_id'])
        require(number(tray['available_at']) >= 0 and type(tray['committed_prefix']) is list, 'tray_availability')


def actor_parts(observation):
    require(type(observation) is dict and set(observation) == FIELDS
        and observation['schema'] == OBSERVATION_SCHEMA, 'observation_schema')
    plain(observation)  # Reject hidden live objects/non-finite values in metadata.
    require(observation['privileged_evaluator_state_included'] is False
        and observation['reference_included'] is False, 'privileged_actor_information')
    require(observation['timing_mode'] in ('offline_sync', 'event_clock_with_resident_process'), 'declared_clock')
    owner, now = observation['owner'], number(observation['at'])
    require(type(owner) is str and owner and now >= 0 and number(observation['remaining_horizon_s']) >= 0,
        'owner_and_remaining_horizon')
    local, opportunity = observation['local_view'], observation['opportunity']
    require(local['owner_id'] == owner and number(local['now']) == now, 'local_owner_epoch')
    require(opportunity['owner'] == owner and number(opportunity['observed_at']) == now
        and opportunity['phase'] in ('cycle_return', 'cycle_route', 'preview_next_route')
        and opportunity['execution_authority'] is False and opportunity['unexecuted_suffix_only'] is True,
        'current_semantic_opportunity')
    _jobs(local['jobs'], now)
    _trays(local['trays'])
    targets = [tray for tray in local['trays'] if tray['tray_id'] == opportunity['target']['tray_id']]
    require(len(targets) == 1 and targets[0] == opportunity['target'], 'target_actual_local_observation')
    nodes = {node['node']: node for node in local['node_contracts']}
    require(len(nodes) == len(local['node_contracts']), 'unique_static_node_contract')
    for node in nodes.values():
        require(number(node['capacity']) >= 0, 'static_capacity')
        require(node['resource_owner'] == owner or not {'occupancy', 'actual_available'}.intersection(node),
            'private_peer_inventory')
        if node['resource_owner'] == owner:
            require(0 <= number(node['actual_available']) <= number(node['occupancy']) <= node['capacity'],
                'actual_owned_capacity')
    own_nodes = [node for node in nodes.values() if node['resource_owner'] == owner]
    summary = observation['account_summary']
    require(summary['actual_locally_available'] == sum(node['actual_available'] for node in own_nodes)
        and summary['arrived_unfinished_locally_known'] == sum(job['status'] != 'completed' for job in local['jobs']),
        'actual_account_summary_binding')
    latest, messages, message_ids = {}, observation['delivered_v3'], set()
    require(type(messages) is list, 'delivered_message_list')
    for message in messages:
        source, identity = message['source_owner'], message['message_id']
        capture = message['envelope']['capture']['capture_v2']['local_capture']
        require(identity not in message_ids, 'duplicate_message_identity')
        message_ids.add(identity)
        require(message['target_owner'] == owner and source != owner and capture['source_owner'] == source
            and capture['target_owner'] == owner, 'delivered_owner_scope')
        require(all(message[field] == capture[field] for field in ('message_id', 'captured_at', 'valid_until')),
            'message_capture_binding')
        require(0 <= number(message['captured_at']) <= number(message['delivered_at']) <= now
            and number(message['valid_until']) >= message['captured_at'], 'causal_message_time')
        envelope = message['envelope']
        require(('delivered_at' not in envelope or envelope['delivered_at'] == message['delivered_at'])
            and ('status' not in envelope or envelope['status'] == message['status']), 'message_envelope_binding')
        require(capture['coverage']['future_arrivals_included'] is False, 'future_arrival_capture')
        _jobs(capture['jobs'], message['captured_at'])
        _trays(capture['trays'])
        fresh = message['status'] == 'conditional' and now < message['valid_until']
        require(type(message['fresh']) is bool and message['fresh'] == fresh, 'message_freshness_binding')
        prior = latest.get(source)
        if prior is None or (message['captured_at'], message['delivered_at']) > (prior['captured_at'], prior['delivered_at']):
            latest[source] = message
    # An expired newest capture cannot be replaced by an older fresh capture.
    fresh_messages = [message for message in latest.values() if message['fresh']]
    peer_nodes, peer_jobs, peer_trays = {}, [], []
    for message in fresh_messages:
        capture = message['envelope']['capture']['capture_v2']['local_capture']
        peer_jobs.extend(capture['jobs'])
        peer_trays.extend(capture['trays'])
        for node in capture['nodes']:
            identity = node['node']
            require(identity in nodes and nodes[identity]['resource_owner'] == message['source_owner']
                and identity not in peer_nodes, 'peer_resource_source_scope')
            require(0 <= number(node['actual_available']) <= number(node['occupancy']) <= nodes[identity]['capacity'],
                'captured_peer_capacity')
            peer_nodes[identity] = node
    ledger = observation['known_contracts']
    require(ledger['owner'] == owner and 0 <= number(ledger['retained_at']) <= now, 'known_contract_owner_epoch')
    contracts, sources = ledger['contracts'], ledger['sources']
    require(type(contracts) is dict and type(sources) is list, 'known_contract_ledger')
    discoveries = {}
    for source in sources:
        require(source['job'] not in discoveries and source['job'] in contracts
            and 0 <= number(source['at']) <= ledger['retained_at'], 'unique_causal_contract_discovery')
        discoveries[source['job']] = source['at']
    require(set(discoveries) == set(contracts), 'all_known_contracts_have_observed_sources')
    for identity, job in contracts.items():
        require(set(job) == CONTRACT_FIELDS and job['business_bag_id'] == identity
            and 0 <= number(job['arrival']) <= discoveries[identity], 'known_contract_not_future_truth')
        for field in ('load_seconds', 'unload_seconds', 'hold_seconds', 'storage_min_dwell'):
            require(number(job[field]) >= 0, 'known_service_contract')
        number(job['deadline'])
        number(job['storage_release_at'])
    outbox = observation['own_outbox']
    require(type(outbox) is dict, 'owner_outbox_snapshot')
    for identity, row in outbox.items():
        request = row['request']
        require(request['owner_id'] == owner and request['request_id'] == identity
            and type(row['terminal']) is bool, 'own_immutable_request_identity')
        ack = row.get('ack', {})
        if ack:
            require(0 <= number(ack['observed_at']) <= number(ack['delivered_at']) <= now, 'future_or_undelivered_ack')
    return local, nodes, own_nodes, peer_nodes, peer_jobs, peer_trays, latest, fresh_messages, ledger, outbox


def _view_features(jobs, trays, nodes, now, prefix):
    result = {prefix + 'job_count': float(len(jobs)), prefix + 'tray_count': float(len(trays)),
        prefix + 'available_empty': float(sum(node['actual_available'] for node in nodes)),
        prefix + 'occupancy': float(sum(node['occupancy'] for node in nodes)),
        prefix + 'inflight': float(sum(tray['edge_to'] >= 0 or tray['mode'] == 'empty_transit' for tray in trays)),
        prefix + 'deadline_slack_s': sum(max(0., number(job['deadline']) - now) for job in jobs),
        prefix + 'overdue_jobs': float(sum(job['deadline'] < now and job['status'] != 'completed' for job in jobs)),
        prefix + 'load_seconds': sum(number(job['load_seconds']) for job in jobs),
        prefix + 'unload_seconds': sum(number(job['unload_seconds']) for job in jobs),
        prefix + 'availability_delay_s': sum(max(0., number(tray['available_at']) - now) for tray in trays),
        prefix + 'committed_prefix_length': float(sum(len(tray['committed_prefix']) for tray in trays))}
    result.update({prefix + 'jobs_' + status: float(sum(job['status'] == status for job in jobs)) for status in JOB_STATES})
    result.update({prefix + 'trays_' + mode: float(sum(tray['mode'] == mode for tray in trays)) for mode in TRAY_MODES})
    return result


def features(observation, action):
    local, nodes, own_nodes, peer_nodes, peer_jobs, peer_trays, latest, fresh, ledger, outbox = actor_parts(observation)
    require(type(action) is dict, 'semantic_action_object')
    plain(action)
    require(set(action) <= {'operation_kind', 'source', 'destination', 'tray_id', 'earliest_departure',
        'earliest_legal_arrival', 'native_default_does_not_clear_preference'}, 'semantic_action_fields')
    kind, source, destination = action['operation_kind'], action['source'], action['destination']
    require(kind in ('transfer', 'route', 'no_command') and source in nodes
        and (destination in nodes or kind == 'no_command' and destination is None), 'supported_semantic_action')
    require(kind != 'transfer' or source != destination, 'transfer_distinct_endpoints')
    owner, now = observation['owner'], number(observation['at'])
    opportunity, target = observation['opportunity'], observation['opportunity']['target']
    require(action['tray_id'] == target['tray_id'] and source == target['node'], 'action_current_target_binding')
    require((kind == 'transfer') == (opportunity['phase'] == 'cycle_return'), 'action_opportunity_kind')
    arrival = action['earliest_legal_arrival']
    require(kind != 'transfer' or arrival is not None, 'transfer_requires_arrival_bound')
    require(arrival is None or number(arrival) >= now, 'arrival_bound_in_past')
    delay = 0. if arrival is None else float(arrival) - now
    departure = action.get('earliest_departure')
    require(kind != 'transfer' or departure is not None, 'transfer_requires_departure_bound')
    require(departure is None or now <= number(departure) <= arrival, 'departure_arrival_order')
    result = {'remaining_horizon_s': number(observation['remaining_horizon_s']),
        'candidate_transfer': float(kind == 'transfer'), 'candidate_route': float(kind == 'route'),
        'candidate_no_command': float(kind == 'no_command'), 'candidate_destination_missing': float(destination is None),
        'arrival_delay_s': delay, 'arrival_bound_missing': float(arrival is None),
        'departure_delay_s': 0. if departure is None else departure - now,
        'phase_return': float(opportunity['phase'] == 'cycle_return'),
        'phase_preview': float(opportunity['phase'] == 'preview_next_route'),
        'known_contract_count': float(len(ledger['contracts'])),
        'known_contract_retained_age_s': now - ledger['retained_at'],
        'known_contract_load_seconds': sum(job['load_seconds'] for job in ledger['contracts'].values()),
        'known_contract_unload_seconds': sum(job['unload_seconds'] for job in ledger['contracts'].values()),
        'known_contract_deadline_slack_s': sum(max(0., job['deadline'] - now) for job in ledger['contracts'].values()),
        'peer_source_count': float(len(latest)), 'fresh_peer_source_count': float(len(fresh)),
        'peer_state_missing': float(not fresh), 'retained_message_count': float(len(observation['delivered_v3'])),
        'latest_peer_max_age_s': max([now - message['captured_at'] for message in latest.values()] or [0.]),
        'latest_peer_max_delivery_lag_s': max([message['delivered_at'] - message['captured_at'] for message in latest.values()] or [0.]),
        'fresh_peer_min_remaining_valid_s': min([message['valid_until'] - now for message in fresh] or [0.]),
        'target_available_delay_s': max(0., target['available_at'] - now),
        'target_inflight': float(target['edge_to'] >= 0 or target['mode'] == 'empty_transit'),
        'target_committed_prefix_length': float(len(target['committed_prefix']))}
    for mode in TRAY_MODES:
        result['target_mode_' + mode] = float(target['mode'] == mode)
    service = opportunity['service_ready_at']
    result.update(target_service_bound_missing=float(service is None),
        target_service_delay_s=0. if service is None else max(0., number(service) - now))
    result.update(_view_features(local['jobs'], local['trays'], own_nodes, now, 'own_'))
    result.update(_view_features(peer_jobs, peer_trays, list(peer_nodes.values()), now, 'captured_peer_'))
    active = [row for row in outbox.values() if not row['terminal']]
    result['own_outbox_pending'] = float(len(active))
    result['own_outbox_terminal'] = float(len(outbox) - len(active))
    result['own_outbox_ack_missing'] = float(sum(not row.get('ack') for row in active))
    for status in ('accepted', 'in_transit', 'received', 'updated', 'delivered', 'rejected'):
        result['own_outbox_ack_' + status] = float(sum(row.get('ack', {}).get('status') == status for row in outbox.values()))
    for operation in ('transfer', 'route_preference', 'planning_snapshot_v3', 'demand'):
        result['own_outbox_pending_' + operation] = float(sum(row['kind'] == operation for row in active))
    visible_jobs = local['jobs'] + peer_jobs
    for role, node_id in (('source', source), ('destination', destination)):
        static = nodes.get(node_id)
        current = None if static is None else static if static['resource_owner'] == owner else peer_nodes.get(node_id)
        result.update({role + '_capacity': 0. if static is None else float(static['capacity']),
            role + '_owned': float(static is not None and static['resource_owner'] == owner),
            role + '_resource_missing': float(current is None),
            role + '_occupancy': 0. if current is None else float(current['occupancy']),
            role + '_available_empty': 0. if current is None else float(current['actual_available']),
            role + '_waiting_jobs': float(sum(job['origin'] == node_id and job['status'] == 'waiting_for_tray' for job in visible_jobs)),
            role + '_known_arrival_contracts': float(sum(job['origin'] == node_id for job in ledger['contracts'].values())),
            role + '_known_destination_contracts': float(sum(job['destination'] == node_id for job in ledger['contracts'].values())),
            role + '_active_destination_jobs': float(sum(job['destination'] == node_id and job['status'] != 'completed' for job in visible_jobs))})
    edges = [edge for edge in local.get('edge_contracts', []) if edge['from'] == source and edge['to'] == destination]
    require(len(edges) <= 1, 'unique_candidate_static_edge')
    result.update(candidate_direct_edge_missing=float(not edges),
        candidate_direct_edge_capacity=0. if not edges else number(edges[0]['capacity']),
        candidate_direct_edge_headway_s=0. if not edges else number(edges[0]['entry_headway']))
    result['transfer_x_destination_waiting'] = result['candidate_transfer'] * result['destination_waiting_jobs']
    result['transfer_x_source_available'] = result['candidate_transfer'] * result['source_available_empty']
    result['route_x_destination_occupancy'] = result['candidate_route'] * result['destination_occupancy']
    result['delay_x_destination_waiting'] = delay * result['destination_waiting_jobs']
    # Views may retain handed-off records also represented in a peer capture;
    # this is a record-count interaction, never a global physical job count.
    result['delay_x_observed_job_records'] = delay * (result['own_job_count'] + result['captured_peer_job_count'])
    require(all(math.isfinite(value) for value in result.values()), 'finite_semantic_features')
    return result


def predict(model, observations, actions):
    require(model['schema'] == MODEL_SCHEMA and model['feature_schema'] == FEATURE_SCHEMA
        and model['native_execution_authority'] is False, 'value_model_schema')
    require(model.get('model_sha256') == digest({key: value for key, value in model.items() if key != 'model_sha256'}),
        'value_model_content_binding')
    require(len(observations) == len(actions), 'score_batch_length')
    vectors = [features(observation, action) for observation, action in zip(observations, actions, strict=True)]
    if not vectors:
        return []
    names = model['feature_names']
    require(all(sorted(vector) == names for vector in vectors), 'semantic_feature_names')
    x = np.asarray([[vector[name] for name in names] for vector in vectors], dtype=np.float64)
    params = model['parameters']
    center, scale = np.asarray(params['center']), np.asarray(params['scale'])
    require(center.shape == scale.shape == (len(names),) and np.isfinite(center).all()
        and np.isfinite(scale).all() and (scale > 0).all(), 'train_normalization')
    x = (x - center) / scale
    require(len(params['layers']) == 3, 'registered_three_linear_layers')
    for index, width in enumerate((64, 64, 1)):
        layer = params['layers'][index]
        weight, bias = np.asarray(layer['weight']), np.asarray(layer['bias'])
        require(weight.shape == (width, x.shape[1]) and bias.shape == (width,)
            and np.isfinite(weight).all() and np.isfinite(bias).all(), 'registered_64x64_layer_shape')
        x = x @ weight.T + bias
        if index < 2:
            x = np.tanh(x)
    require(number(params['target_scale']) > 0, 'positive_target_scale')
    result = x[:, 0] * params['target_scale'] + number(params['target_center'])
    require(np.isfinite(result).all(), 'finite_predicted_return')
    return result.tolist()


def fit(rows, *, seed, epochs, deadline, objective):
    """Fit CPU 64x64 NN; caller must independently certify native reward/TD rows."""
    require(type(rows) is list and rows and type(seed) is int and 0 <= seed < 2 ** 32
        and type(epochs) is int and 1 <= epochs <= 1000, 'registered_training_budget')
    require(type(objective) is str and objective and time.monotonic() <= number(deadline), 'training_deadline_objective')
    require(all(row['split'] == 'train' and type(row['parent_group']) is str and row['parent_group'] for row in rows),
        'train_only_parent_rows')
    vectors = [features(row['observation'], row['action']) for row in rows]
    names = sorted(vectors[0])
    require(all(sorted(vector) == names for vector in vectors), 'training_feature_names')
    x = np.asarray([[vector[name] for name in names] for vector in vectors], dtype=np.float64)
    target = np.asarray([number(row['target_value']) for row in rows], dtype=np.float64)
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-9] = 1.
    target_center, target_scale = float(target.mean()), max(float(target.std()), 1.)
    import torch
    require(time.monotonic() <= deadline, 'training_wall_budget')
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    inputs = torch.tensor((x - center) / scale, dtype=torch.float32)
    targets = torch.tensor((target - target_center) / target_scale, dtype=torch.float32).reshape(-1, 1)
    network = torch.nn.Sequential(torch.nn.Linear(len(names), 64), torch.nn.Tanh(),
        torch.nn.Linear(64, 64), torch.nn.Tanh(), torch.nn.Linear(64, 1))
    optimizer = torch.optim.Adam(network.parameters(), lr=.01, weight_decay=1e-4)
    curve = []
    for epoch in range(epochs + 1):
        require(time.monotonic() <= deadline, 'training_wall_budget')
        loss = torch.mean((network(inputs) - targets) ** 2)
        require(bool(torch.isfinite(loss)), 'finite_training_loss')
        if epoch % 10 == 0 or epoch == epochs:
            curve.append({'epoch': epoch, 'mse': float(loss.detach()) * target_scale ** 2})
        if epoch < epochs:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    parameters = {'center': center.tolist(), 'scale': scale.tolist(), 'target_center': target_center,
        'target_scale': target_scale, 'layers': [{'weight': layer.weight.detach().numpy().tolist(),
            'bias': layer.bias.detach().numpy().tolist()} for layer in network if isinstance(layer, torch.nn.Linear)]}
    model = {'schema': MODEL_SCHEMA, 'feature_schema': FEATURE_SCHEMA, 'feature_names': names,
        'parameters': parameters, 'seed': seed, 'epochs': epochs, 'training_curve': curve, 'objective': objective,
        'training_row_count': len(rows), 'training_parent_groups': sorted({row['parent_group'] for row in rows}),
        'training_rows_sha256': digest(rows), 'device': 'cpu', 'cpu_threads': 1, 'torch_version': torch.__version__,
        'score_direction': 'higher_is_better_return', 'native_execution_authority': False,
        'label_provenance_certified_by_this_module': False, 'td_readiness_certified_by_this_module': False,
        'feature_scope': 'released local views, received captures, retained arrived contracts, own requests and semantic actions',
        'opaque_identifiers_are_features': False, 'flight_minute_windows_used': False}
    model['model_sha256'] = digest(model)
    predict(model, [row['observation'] for row in rows], [row['action'] for row in rows])
    return model
