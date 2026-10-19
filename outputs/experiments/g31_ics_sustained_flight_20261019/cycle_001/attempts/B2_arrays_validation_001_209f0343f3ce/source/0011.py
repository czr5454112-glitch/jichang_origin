"""Action-conditioned local values consuming explicit flight/baseline forecasts.

Only detached observations enter this module. Scores confer no native authority.
The old 43/52-dimensional checkpoints and feature definitions are untouched.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

OBSERVATION_SCHEMA = 'g31.foundation.flight_aware_observation.v2'
MODEL_SCHEMA = 'g31.foundation.action_conditioned_value.v2'
FEATURE_SCHEMA = 'g31.foundation.action_conditioned_features.v2'
WINDOWS = (60, 300, 900, 1800)
ACCOUNT_NAMES = ('current_free_trays', 'known_waiting_jobs', 'loaded_release_forecast',
                 'committed_inbound', 'committed_outbound', 'unresolved_requests')


def require(condition, reason):
    if not condition:
        raise ValueError('action_value:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def detached(value):
    return json.loads(json.dumps(value, allow_nan=False))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _identity(row):
    require(type(row['tray_id']) is str and type(row['generation']) is int and row['generation'] >= 0, 'tray_generation')
    return row['tray_id'], row['generation']


def _waiting_count(row, base_observation, now):
    """A compact public count is not the number of representative job rows."""
    require(row['kind'] in ('job', 'waiting_group') and type(row['origin']) is int, 'waiting_row_kind_origin')
    if row['kind'] == 'job':
        require(type(row['business_bag_id']) is str and bool(row['business_bag_id'])
            and 0 <= number(row['arrival_at']) <= number(row['observed_at']) <= now,
            'duplicate_or_future_waiting_job')
        return 1., False, {row['business_bag_id']}
    projection = base_observation.get('control_projection', {})
    require(projection.get('schema') == 'g31.analytic_control_projection.v1'
        and type(projection.get('waiting_groups')) is list, 'waiting_group_public_projection_required')
    matches = [group for group in projection['waiting_groups'] if group['origin'] == row['origin']]
    require(len(matches) == 1, 'waiting_group_unique_public_origin')
    group = matches[0]
    require(row['provenance'] == {'kind': 'public_control_projection_waiting_group', 'group_sha256': digest(group)}
        and number(group['demand_observed_at']) == number(row['observed_at']) <= now,
        'waiting_group_count_provenance')
    require(type(group['origin']) is int and type(row['count']) is type(group.get('count'))
        and row['count'] == group.get('count') and (row['count'] is None
        or type(row['count']) is int and row['count'] >= 0), 'waiting_group_public_count')
    require(type(group['jobs']) is list, 'waiting_group_public_representatives')
    identities = set()
    for job in group['jobs']:
        identity = job['business_bag_id']
        require(type(identity) is str and identity and identity not in identities
            and job['origin'] == row['origin'] and job['status'] in ('waiting', 'waiting_for_tray')
            and 0 <= number(job['arrival']) <= number(job['demand_observed_at'])
            <= number(group['demand_observed_at']), 'duplicate_or_future_waiting_job')
        identities.add(identity)
    require(row['count'] is None or row['count'] >= len(identities), 'waiting_count_below_observed_lower_bound')
    return float(len(identities) if row['count'] is None else row['count']), row['count'] is None, identities


def _inbound_ack(row, base_observation, now):
    """Keep native ACK bytes and bind the receiver's public evidence scope.

    The future C adapter must produce this detached public evidence from its
    authorized input. A sender's private outbox is never a peer receiver input.
    This validator does not fetch an endpoint or certify native provenance.
    """
    owner = base_observation.get('owner_id', base_observation.get('owner'))
    public = base_observation.get('inbound_ack_evidence', [])
    require(type(public) is list, 'public_inbound_ack_evidence')
    matches = [item for item in public if item.get('request_id') == row['request_id']]
    require(len(matches) == 1, 'one_current_public_inbound_ack')
    evidence = matches[0]
    require(evidence['schema'] == 'g31.foundation.public_inbound_ack.v1'
        and evidence['kind'] in ('own_public_outbox', 'received_peer_ack', 'native_receiving_lease')
        and evidence['target_owner'] == owner and evidence['region'] == row['region']
        and evidence['tray_id'] == row['tray_id'] and evidence['generation'] == row['generation'],
        'inbound_ack_receiver_entity_scope')
    require((evidence['kind'] == 'received_peer_ack' and evidence['source_owner'] != owner)
        or (evidence['kind'] != 'received_peer_ack' and evidence['source_owner'] == owner),
        'sender_outbox_is_not_peer_receiver_evidence')
    require(row['ack_provenance'] == {'kind': 'public_inbound_ack_evidence', 'evidence_sha256': digest(evidence)}
        and row['native_ack'] == evidence['native_ack'], 'inbound_ack_original_provenance')
    ack = row['native_ack']
    require(row['ack_status'] == ack['status'] and row['ack_observed_at'] == ack['observed_at']
        and ack['status'] in ('accepted', 'in_transit', 'departed'), 'native_ack_status_must_not_be_normalized')
    require(0 <= number(ack['observed_at']) <= number(ack['delivered_at'])
        <= number(evidence['captured_at']) <= number(evidence['available_to_owner_at'])
        <= number(row['observed_at']) <= now, 'inbound_ack_actual_delivery_order')
    # Native027's departed ACK may retain received_at=-1. Do not invent a
    # departed_at timestamp or recast this as an already received free tray.
    require(ack.get('received_at', -1.) == -1., 'received_ack_is_not_future_inbound')


def validate_accounts(accounts, now, regions, base_observation):
    require(type(accounts) is dict and set(accounts) == set(ACCOUNT_NAMES) | {'coverage_by_account_region'}, 'account_schema')
    require(all(type(accounts[name]) is list for name in ACCOUNT_NAMES), 'account_lists')
    coverage = accounts['coverage_by_account_region']
    require(type(coverage) is dict and set(coverage) == set(ACCOUNT_NAMES), 'account_coverage_names')
    require(regions and all(type(region) is str and region for region in regions), 'forecast_regions')
    for name in ACCOUNT_NAMES:
        require(type(coverage[name]) is dict and set(coverage[name]) == set(regions), 'account_coverage_regions')
        for status in coverage[name].values():
            require(type(status) is dict and set(status) == {'visible', 'complete', 'observed_at'}
                and type(status['visible']) is bool and type(status['complete']) is bool, 'account_coverage_status')
            require((status['visible'] and 0 <= number(status['observed_at']) <= now)
                or (not status['visible'] and not status['complete'] and status['observed_at'] is None),
                'account_coverage_time_or_unknown')
        for row in accounts[name]:
            require(row['region'] in regions, 'account_region_outside_forecast_mapping')
            status = coverage[name][row['region']]
            require(status['visible'] and 0 <= number(row['observed_at']) <= number(status['observed_at']) <= now,
                'future_account_observation_or_invisible_record')
    seen_trays, jobs, requests, generations = set(), set(), set(), {}
    def bind_generation(identity):
        tray, generation = identity
        require(tray not in generations or generations[tray] == generation, 'conflicting_tray_generations')
        generations[tray] = generation
    for name in ('current_free_trays', 'loaded_release_forecast', 'committed_inbound'):
        for row in accounts[name]:
            identity = _identity(row)
            bind_generation(identity)
            require(identity not in seen_trays, 'tray_counted_in_multiple_supply_accounts')
            seen_trays.add(identity)
            require(type(row['region']) is str, 'region')
            require(0 <= number(row['observed_at']) <= now, 'future_account_observation')
            if name != 'current_free_trays':
                require(number(row['available_at']) >= now, 'future_supply_before_now')
            if name == 'loaded_release_forecast':
                require(row['status'] == 'conditional', 'release_is_not_actual_inventory')
            if name == 'committed_inbound':
                require(row['ack_status'] in ('accepted', 'in_transit', 'departed'), 'unresolved_or_received_is_not_future_inbound')
                require(0 <= number(row['ack_observed_at']) <= number(row['observed_at']), 'future_ack')
                require(row['request_id'] not in requests, 'duplicate_inbound_request')
                _inbound_ack(row, base_observation, now)
                requests.add(row['request_id'])
    group_origins, job_origins = set(), set()
    for row in accounts['known_waiting_jobs']:
        _, _, identities = _waiting_count(row, base_observation, now)
        require(not jobs & identities, 'duplicate_or_future_waiting_job')
        jobs.update(identities)
        if row['kind'] == 'waiting_group':
            require(row['origin'] not in group_origins | job_origins, 'waiting_group_individual_overlap')
            group_origins.add(row['origin'])
        else:
            require(row['origin'] not in group_origins, 'waiting_group_individual_overlap')
            job_origins.add(row['origin'])
    outbound = set()
    for row in accounts['committed_outbound']:
        identity = _identity(row)
        bind_generation(identity)
        require(identity not in outbound and number(row['observed_at']) <= now, 'duplicate_or_future_outbound')
        outbound.add(identity)
    unresolved = [row['request_id'] for row in accounts['unresolved_requests']]
    require(len(unresolved) == len(set(unresolved)) and not set(unresolved) & requests, 'unresolved_request_counted_as_inbound')
    return accounts


def wrap_observation(*, episode_id, owner, decision_id, now, base_observation, forecast,
                     accounts, information_variant, remaining_episode_seconds, mapping_version,
                     flight_context_sha256=None):
    now = number(now)
    require(information_variant in ('no_plan', 'static_plan'), 'information_variant')
    require(type(base_observation) is dict and type(forecast) is dict, 'detached_observation_and_forecast')
    require(forecast.get('schema') == 'g31.foundation.new_demand_forecast.v1', 'forecast_schema')
    require(forecast.get('owner_scope') == owner, 'forecast_wrong_owner')
    cutoffs = forecast['information_cutoffs']
    require(set(cutoffs) == {'training_labels_closed_at', 'model_frozen_at', 'plan_received_at',
                             'observed_arrivals_through'}, 'forecast_cutoff_schema')
    require(all(value is None or number(value) <= now for value in cutoffs.values()), 'future_forecast_information')
    require(number(cutoffs['training_labels_closed_at']) <= number(cutoffs['model_frozen_at']) <= now,
            'training_label_closure_order')
    require(type(mapping_version) is str and mapping_version and forecast.get('mapping_version') == mapping_version,
            'forecast_account_mapping_version')
    base_owner = base_observation.get('owner_id', base_observation.get('owner'))
    base_time = base_observation.get('now', base_observation.get('at'))
    require(base_owner == owner and number(base_time) == now, 'base_owner_time')
    # A cached vector cannot be silently relabelled at a later time. The cheap
    # forecaster must re-integrate its CDF at the actual decision time.
    require(number(forecast['forecast_origin']) == now, 'forecast_requires_current_time_projection')
    require(number(forecast['remaining_support_until']) >= now, 'forecast_support_expired')
    if information_variant == 'no_plan':
        require(forecast.get('context_sha256') is None and flight_context_sha256 is None, 'no_plan_must_not_consume_plan')
    else:
        require(forecast.get('context_sha256') == flight_context_sha256, 'context_forecast_binding')
    validate_accounts(accounts, now, set(forecast['new_demand_mean_by_region']), base_observation)
    result = {'schema': OBSERVATION_SCHEMA, 'episode_id': str(episode_id), 'owner_id': str(owner),
        'decision_id': str(decision_id), 'now': now, 'base_observation': detached(base_observation),
        'demand_forecast': detached(forecast), 'circulation_accounts': detached(accounts),
        'flight_context_sha256': flight_context_sha256, 'information_variant': information_variant,
        'mapping_version': mapping_version,
        'remaining_episode_seconds': number(remaining_episode_seconds),
        'native_execution_authority': False}
    require(result['remaining_episode_seconds'] >= 0, 'negative_remaining_episode')
    return result


def _mass(forecast, region, elapsed):
    values = forecast['new_demand_mean_by_region'].get(region)
    missing = forecast['missing_mask_by_region'].get(region, True)
    if values is None or missing is True or (isinstance(missing, list) and any(missing)):
        return 0., True
    edges = forecast['bin_edges_seconds']
    require(len(edges) == len(values) + 1 and number(edges[0]) == 0, 'relative_forecast_bin_edges')
    total = 0.
    for left, right, mass in zip(edges[:-1], edges[1:], values, strict=True):
        left, right, mass = number(left), number(right), number(mass)
        require(right > left and mass >= 0, 'forecast_bins_and_mass')
        # Feature aggregation only: partial bins use a declared uniform-bin
        # approximation. No physical inventory or demand event is created.
        total += mass * max(0., min(right, elapsed) - left) / (right - left)
    return total, elapsed > number(edges[-1])


def _account_counts(accounts, region, at, now, base_observation):
    outbound = {_identity(row) for row in accounts['committed_outbound']}
    free = sum(row['region'] == region and _identity(row) not in outbound for row in accounts['current_free_trays'])
    waiting_rows = [_waiting_count(row, base_observation, now) for row in accounts['known_waiting_jobs'] if row['region'] == region]
    waiting = sum(count for count, _, _ in waiting_rows)
    release = sum(row['region'] == region and row['available_at'] <= at and _identity(row) not in outbound
                  for row in accounts['loaded_release_forecast'])
    inbound = sum(row['region'] == region and row['available_at'] <= at and _identity(row) not in outbound
                  for row in accounts['committed_inbound'])
    counts = dict(zip(ACCOUNT_NAMES[:4], map(float, (free, waiting, release, inbound)), strict=True))
    counts.update(committed_outbound=float(sum(row['region'] == region for row in accounts['committed_outbound'])),
        unresolved_requests=float(sum(row['region'] == region for row in accounts['unresolved_requests'])))
    complete = {name: accounts['coverage_by_account_region'][name][region]['complete'] for name in ACCOUNT_NAMES}
    # Even a declared complete scope cannot turn an unknown compact count into
    # an exact total. Retain representative identities only as an observed bound.
    complete['known_waiting_jobs'] &= not any(missing for _, missing, _ in waiting_rows)
    return counts, complete, any(missing for _, missing, _ in waiting_rows)


def features(observation, action):
    require(observation['schema'] == OBSERVATION_SCHEMA, 'observation_schema')
    # Revalidate stored JSON as well as freshly wrapped observations.
    wrap_observation(episode_id=observation['episode_id'],owner=observation['owner_id'],
        decision_id=observation['decision_id'],now=observation['now'],base_observation=observation['base_observation'],
        forecast=observation['demand_forecast'],accounts=observation['circulation_accounts'],
        information_variant=observation['information_variant'],remaining_episode_seconds=observation['remaining_episode_seconds'],
        mapping_version=observation['mapping_version'],flight_context_sha256=observation['flight_context_sha256'])
    now = number(observation['now'])
    accounts = observation['circulation_accounts']  # Already validated by wrap_observation above.
    forecast = observation['demand_forecast']
    require(number(forecast['forecast_origin']) == now, 'stale_forecast_vector')
    require(action['kind'] in ('transfer', 'route', 'no_command'), 'action_kind')
    source, destination = action['source_region'], action['destination_region']
    require(type(source) is str and type(destination) is str, 'semantic_regions')
    require({source,destination} <= set(forecast['new_demand_mean_by_region']), 'action_region_missing_from_declared_mapping')
    arrival = number(action['earliest_legal_arrival'])
    require(arrival >= now, 'candidate_arrival_in_past')
    delay = arrival - now
    moved = 1. if action['kind'] == 'transfer' else 0.
    result = {'candidate_transfer': moved, 'candidate_route': float(action['kind'] == 'route'),
        'candidate_no_command': float(action['kind'] == 'no_command'), 'arrival_delay_s': delay,
        'remaining_episode_s': number(observation['remaining_episode_seconds']),
        'unresolved_request_observed_count': float(len(accounts['unresolved_requests'])),
        'unresolved_request_total_missing': float(not all(status['complete']
            for status in accounts['coverage_by_account_region']['unresolved_requests'].values()))}
    for role, region in (('source', source), ('destination', destination)):
        counts, complete, waiting_count_missing = _account_counts(accounts, region, arrival, now, observation['base_observation'])
        free, waiting, release, inbound = (counts[name] for name in ACCOUNT_NAMES[:4])
        for name in ACCOUNT_NAMES:
            status = accounts['coverage_by_account_region'][name][region]
            result.update({role + '_' + name + '_visible': float(status['visible']),
                role + '_' + name + '_complete': float(complete[name]),
                role + '_' + name + '_observation_age_s': 0. if not status['visible'] else now - status['observed_at']})
        result.update({role + '_current_free': free, role + '_known_waiting': waiting,
            role + '_conditional_release_by_arrival': release, role + '_committed_inbound_by_arrival': inbound,
            role + '_known_waiting_count_missing': float(waiting_count_missing),
            role + '_observed_committed_outbound': counts['committed_outbound'],
            role + '_observed_unresolved_requests': counts['unresolved_requests']})
        for window in WINDOWS:
            mass, missing = _mass(forecast, region, window)
            result[f'{role}_new_demand_{window}'] = mass
            result[f'{role}_demand_missing_{window}'] = float(missing)
        mass, missing = _mass(forecast, region, delay)
        result[role + '_forecast_before_arrival'] = mass
        result[role + '_forecast_arrival_missing'] = float(missing)
        # Explicitly action-conditioned estimates, never claimed as available
        # stock. Planned outbound entities are excluded from all supply terms.
        deficit_known = not missing and all(complete.values())
        result[role + '_estimated_deficit_missing'] = float(not deficit_known)
        result[role + '_estimated_deficit_at_arrival'] = waiting + mass - free - release - inbound if deficit_known else 0.
    result['source_scarcity_after_transfer'] = (result['source_estimated_deficit_at_arrival'] + moved
        if not result['source_estimated_deficit_missing'] else 0.)
    result['destination_deficit_after_transfer'] = (result['destination_estimated_deficit_at_arrival'] - moved
        if not result['destination_estimated_deficit_missing'] else 0.)
    result['source_scarcity_after_transfer_missing'] = result['source_estimated_deficit_missing']
    result['destination_deficit_after_transfer_missing'] = result['destination_estimated_deficit_missing']
    result['transfer_x_receiver_demand_300'] = moved * result['destination_new_demand_300']
    result['delay_x_receiver_demand_300'] = delay * result['destination_new_demand_300']
    result['transfer_x_source_scarcity'] = moved * result['source_scarcity_after_transfer']
    require(all(math.isfinite(value) for value in result.values()), 'nonfinite_features')
    return result


def predict(model, observations, actions):
    require(model['schema'] == MODEL_SCHEMA and model['feature_schema'] == FEATURE_SCHEMA, 'model_schema')
    require(len(observations) == len(actions), 'score_batch_length')
    require(all(row['information_variant'] == model['information_variant'] for row in observations), 'model_information_variant')
    require(all(row['mapping_version'] == model['mapping_version'] for row in observations), 'model_mapping_version')
    vectors = [features(row, action) for row, action in zip(observations, actions, strict=True)]
    names = model['feature_names']
    require(all(sorted(vector) == names for vector in vectors), 'feature_names')
    if not vectors:
        return []
    x = np.array([[vector[name] for name in names] for vector in vectors], dtype=np.float64)
    p = model['parameters']
    center, scale = np.array(p['center']), np.array(p['scale'])
    require(center.shape == scale.shape == (len(names),) and np.isfinite(center).all()
            and np.isfinite(scale).all() and (scale > 0).all(), 'normalization')
    x = (x - center) / scale
    for index, layer in enumerate(p['layers']):
        weight, bias = np.array(layer['weight']), np.array(layer['bias'])
        require(weight.ndim == 2 and weight.shape[1] == x.shape[1] and bias.shape == (weight.shape[0],)
                and np.isfinite(weight).all() and np.isfinite(bias).all(), 'layer_shape')
        x = x @ weight.T + bias
        if index < len(p['layers']) - 1:
            x = np.tanh(x)
    require(x.shape == (len(vectors), 1), 'scalar_value_output')
    value = x[:, 0] * number(p['target_scale']) + number(p['target_center'])
    require(np.isfinite(value).all(), 'finite_values')
    return value.tolist()


def fit(rows, *, information_variant, seed, epochs, deadline, objective, initial=None):
    """Fit a new 64x64 network on caller-validated native/conditional labels.

    This numerical fitter does not certify label provenance or RL readiness;
    the collection exporter and multistep gate must do that separately.
    """
    import torch
    require(bool(rows) and type(epochs) is int and 1 <= epochs <= 1000, 'training_rows_and_epochs')
    require(all(row['observation']['information_variant'] == information_variant for row in rows), 'training_information_variant')
    require(all(row['split'] == 'train' for row in rows), 'training_split_only')
    require(len({row['observation']['mapping_version'] for row in rows}) == 1, 'mixed_training_mappings')
    vectors = [features(row['observation'], row['action']) for row in rows]
    names = sorted(vectors[0])
    require(all(sorted(v) == names for v in vectors), 'training_feature_schema')
    x = np.array([[v[name] for name in names] for v in vectors])
    target = np.array([number(row['target_value']) for row in rows])
    center, scale = x.mean(0), x.std(0)
    scale[scale < 1e-9] = 1.
    target_center, target_scale = float(target.mean()), max(float(target.std()), 1.)
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    inputs = torch.tensor((x-center)/scale, dtype=torch.float32)
    targets = torch.tensor((target-target_center)/target_scale, dtype=torch.float32).reshape(-1, 1)
    network = torch.nn.Sequential(torch.nn.Linear(len(names),64),torch.nn.Tanh(),
        torch.nn.Linear(64,64),torch.nn.Tanh(),torch.nn.Linear(64,1))
    # Each Bellman iteration fits fresh with frozen targets. Explicitly reject
    # silently mixing normalizers from an unrelated old checkpoint.
    require(initial is None, 'fresh_target_fit_only')
    optimizer = torch.optim.Adam(network.parameters(), lr=.01, weight_decay=1e-4)
    curve = []
    for epoch in range(epochs+1):
        require(time.monotonic() <= deadline, 'training_wall_budget')
        loss = torch.mean((network(inputs)-targets)**2)
        if epoch % 10 == 0 or epoch == epochs:
            curve.append({'epoch':epoch, 'mse':float(loss.detach())*target_scale**2})
        if epoch < epochs:
            optimizer.zero_grad(); loss.backward(); optimizer.step()
    parameters = {'center':center.tolist(),'scale':scale.tolist(),'target_center':target_center,'target_scale':target_scale,
        'layers':[{'weight':layer.weight.detach().numpy().tolist(),'bias':layer.bias.detach().numpy().tolist()}
                  for layer in network if isinstance(layer,torch.nn.Linear)]}
    model = {'schema':MODEL_SCHEMA,'feature_schema':FEATURE_SCHEMA,'information_variant':information_variant,
        'mapping_version':rows[0]['observation']['mapping_version'],
        'feature_names':names,'parameters':parameters,'seed':seed,'epochs':epochs,'training_curve':curve,
        'objective':objective,'training_row_count':len(rows),'training_parent_groups':sorted({row['parent_group'] for row in rows}),
        'training_rows_sha256':digest(rows),'device':'cpu','cpu_threads':1,'torch_version':torch.__version__,
        'score_direction':'higher_is_better_return','native_execution_authority':False,
        'partial_bin_feature_aggregation':'uniform within fixed absolute-time forecast bins; current-origin CDF reprojection required'}
    require(np.isfinite(predict(model,[r['observation'] for r in rows],[r['action'] for r in rows])).all(), 'trained_predictions_finite')
    return model
