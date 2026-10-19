"""Explicit airport forecast projection and a conservative public R2 planner.

The historical workload projection is a common physical input factor. Its
whole-day balanced assignment and group sizes are never planner features.
This separate uniform role prior is a declared experiment, not field routing.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import math

from .analytic_control import (PublicTravel, ReleaseForecast, transfer_candidates,
                               departure_avoiding_published_windows)

MAPPING_SCHEMA = 'g31.foundation.airport_role_mapping.v1'
REGIONS = tuple('legacy_start_' + str(i) for i in (0, 1, 2, 3, 4, 5, 53))
STANDARD_LOADERS = (0, 24, 26, 49, 57, 92, 95, 149)
TRANSFER_LOADERS = (134, 136, 138)


def require(condition, reason):
    if not condition:
        raise ValueError('airport_flight:' + reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def static_mapping(profile):
    """Read registered node roles only; this function accepts no workload."""
    require(len(profile['nodes']) == 151 and len(profile['edges']) == 227, 'fixed_airport_graph')
    roles = profile['business_roles']
    require(tuple(roles['standard_loader_nodes']) == STANDARD_LOADERS
            and tuple(roles['transfer_loader_nodes']) == TRANSFER_LOADERS, 'frozen_loader_roles')
    result = {'schema': MAPPING_SCHEMA, 'version': 'airport151_std8_gtc3_role_uniform_v1',
        'source_regions': list(REGIONS), 'regions': {
            region: {'nodes': list(TRANSFER_LOADERS if region == 'legacy_start_53' else STANDARD_LOADERS),
                     'rule': 'uniform_expected_mass_only'} for region in REGIONS},
        'basis': 'explicit research role prior; legacy starts 0..5 standard, 53 transfer',
        'source_fields': ['business_roles.standard_loader_nodes', 'business_roles.transfer_loader_nodes'],
        'uses_balanced_assignment_or_whole_day_group_counts': False,
        'real_advance_loader_assignment_known': False, 'physical_workload_projection_changed': False}
    result['sha256'] = digest(result)
    return result


def validate_mapping(mapping):
    require(mapping['schema'] == MAPPING_SCHEMA and mapping['sha256'] == digest(
        {k: v for k, v in mapping.items() if k != 'sha256'}), 'mapping_binding')
    require(tuple(mapping['source_regions']) == REGIONS and set(mapping['regions']) == set(REGIONS), 'mapping_regions')
    for region, row in mapping['regions'].items():
        expected = TRANSFER_LOADERS if region == 'legacy_start_53' else STANDARD_LOADERS
        require(tuple(row['nodes']) == expected and row['rule'] == 'uniform_expected_mass_only', 'fixed_role_prior')


def project_forecast(forecast, mapping, *, now, owner):
    """Conserve expected new mass without converting it into inventory/jobs.

Regional uncertainty is retained as its original source artifact. Node-level
intervals are unknown: splitting a region creates dependent node demands and
does not justify adding its source interval as an independently calibrated CI.
"""
    validate_mapping(mapping)
    require(forecast.get('schema') == 'g31.foundation.new_demand_forecast.v1'
            and forecast['forecast_origin'] == now and forecast['owner_scope'] == owner,
            'current_owner_forecast_required')
    require(set(forecast['new_demand_mean_by_region']) == set(REGIONS), 'complete_region_domain')
    bins = len(forecast['bin_edges_seconds']) - 1
    nodes = sorted(set(STANDARD_LOADERS + TRANSFER_LOADERS))
    by_node = {f'airport_node_{node}': [0.] * bins for node in nodes}
    missing = dict.fromkeys(by_node, False)
    raw_totals = [0.] * bins
    for region in REGIONS:
        row = forecast['new_demand_mean_by_region'][region]
        require(len(row) == bins, 'bin_count')
        targets = mapping['regions'][region]['nodes']
        absent = forecast['missing_mask_by_region'][region]
        require(type(absent) is bool, 'region_missing_mask')
        for node in targets:
            missing[f'airport_node_{node}'] |= absent
        if absent:
            continue
        require(all(type(value) in (float, int) and math.isfinite(value) and value >= 0 for value in row), 'finite_nonnegative_mass')
        for i, value in enumerate(row):
            raw_totals[i] += value
            for node in targets:
                by_node[f'airport_node_{node}'][i] += value / len(targets)
    mapped_totals = [math.fsum(values[i] for values in by_node.values()) for i in range(bins)]
    errors = [b - a for a, b in zip(raw_totals, mapped_totals, strict=True)]
    require(all(abs(error) <= 1e-12 * max(1., abs(total)) for total, error in zip(raw_totals, errors)), 'mass_conservation')
    for key in by_node:
        if missing[key]:
            by_node[key] = [None] * bins
    result = copy.deepcopy(forecast)
    result.update(new_demand_mean_by_region=by_node, missing_mask_by_region=missing,
        uncertainty_by_region={key: None for key in by_node}, window_summaries_by_region={},
        source_regional_forecast_sha256=digest(forecast), airport_mapping_sha256=mapping['sha256'],
        source_mapping_version=forecast.get('mapping_version'), mapping_version=mapping['version'],
        airport_mapping_version=mapping['version'], region_mapping_scope='explicit_uniform_airport_role_prior',
        node_uncertainty_status='unknown_dependent_projection',
        projection_audit={'raw_known_mass_per_bin': raw_totals, 'mapped_known_mass_per_bin': mapped_totals,
            'floating_point_residual_per_bin': errors, 'mean_mass_conserved': True,
            'missing_mass_imputed_as_zero': False})
    return result


def _mass(forecast, node, seconds):
    key = f'airport_node_{node}'
    if forecast['missing_mask_by_region'].get(key, True):
        return None
    edges, values = forecast['bin_edges_seconds'], forecast['new_demand_mean_by_region'][key]
    return math.fsum(value * max(0., min(right, seconds) - left) / (right - left)
        for left, right, value in zip(edges[:-1], edges[1:], values, strict=True))


def make_rule_planner(forecast_at, mapping, *, activate_at=57600., horizon_seconds=300,
                      forecast_projector=project_forecast, mapping_validator=validate_mapping,
                      injection_nodes=None):
    """Return callback for the real ProtocolClient path; no actor-side session.

Known FIFO/terminal-clear intents retain precedence. Extra preposition uses
only spare *currently idle* owner trays. All transfers remain conditional on
native source/receiver authorization at delivery; this is no nonharm proof.
"""
    mapping_validator(mapping)
    injection_nodes = STANDARD_LOADERS + TRANSFER_LOADERS if injection_nodes is None else tuple(injection_nodes)
    require(injection_nodes and len(set(injection_nodes)) == len(injection_nodes)
        and set(injection_nodes) <= set(STANDARD_LOADERS + TRANSFER_LOADERS), 'declared_injection_nodes')
    require(callable(forecast_at) and math.isfinite(activate_at) and activate_at >= 0
            and 0 < horizon_seconds <= 1800, 'planner_configuration')
    frozen_mapping = copy.deepcopy(mapping)

    def planner(observation, **options):
        baseline = transfer_candidates(observation, **options)
        now, owner = observation['now'], observation['owner_id']
        if now < activate_at or baseline['intents']:
            return baseline
        spare = [row for row in baseline['supplies'] if row['ledger'] == 'actual_available']
        if not spare:
            # A forecast cannot create a currently idle tray. Keep demand
            # unknown and record the skipped computation instead of a zero.
            baseline['flight_planning'] = {'forecast': None, 'status': 'forecast_skipped',
                'skip_reason': 'no_actual_available_supply', 'forecast_provider_called': False,
                'demand_inference': 'not_evaluated', 'native_authority': False,
                'strict_nonharm_certified': False, 'future_jobs_created': 0, 'candidate_count': 0}
            return baseline
        forecast = forecast_projector(forecast_at(now=now, owner=owner), frozen_mapping, now=now, owner=owner)
        baseline['flight_planning'] = {'forecast': forecast, 'status': 'local_wait',
            'forecast_provider_called': True,
            'native_authority': False, 'strict_nonharm_certified': False,
            'future_jobs_created': 0, 'candidate_count': 0}
        contracts = {int(row['node']): row for row in observation['node_contracts']}
        spare_counts = Counter(row['node'] for row in spare)
        active = [row for row in observation.get('transfers', []) if row['status'] in
            ('pending', 'granted', 'in_transit', 'requested', 'delivered', 'undelivered', 'dispatching', 'departed')]
        incoming = Counter(int(row['destination']) for row in active)
        travel, candidates = PublicTravel(observation), []
        for supply in spare:
            source = int(supply['node'])
            contract = contracts[source]
            if contract.get('resource_owner', contract['zone']) != owner or not contract.get('allow_export', True):
                continue
            own_mass = _mass(forecast, source, horizon_seconds)
            # Non-loader terminal nodes have no forecast injection demand;
            # known local obligations were already retained by the baseline.
            if source in injection_nodes and own_mass is None:
                continue
            if spare_counts[source] - 1 < math.ceil(own_mass or 0.):
                continue
            for destination in injection_nodes:
                other = contracts[destination]
                demand = _mass(forecast, destination, horizon_seconds)
                if demand is None or demand <= incoming[destination] or other['zone'] == contract['zone'] or not other.get('allow_receive', True):
                    continue
                duration = travel.complete(source, destination)
                if not math.isfinite(duration) or duration > horizon_seconds:
                    continue
                window = (departure_avoiding_published_windows(observation, ReleaseForecast(**supply),
                    destination, travel, options.get('message_delay', 0.))
                    if options.get('respect_service_forecasts', False) else None)
                departure = max(now + options.get('message_delay', 0.),
                                window['earliest_departure'] if window else now)
                eta = departure + duration
                if eta > now + horizon_seconds:
                    continue
                candidates.append((-(demand - incoming[destination]) / (1. + duration), source,
                    destination, supply['tray_id'], eta, supply, departure, window))
        baseline['flight_planning']['candidate_count'] = len(candidates)
        if not candidates:
            return baseline
        _, source, destination, tray, eta, supply, departure, window = min(candidates, key=lambda row: row[:5])
        baseline['intents'] = [{'tray_id': tray, 'source': source, 'destination': destination,
            'issued_at': now, 'message_delay': options.get('message_delay', 0.), 'earliest_departure': departure,
            'expiry': eta + 60., 'forecast_dependency': supply['dependency'], 'forecast_ledger': supply['ledger'],
            'control_reason': 'flight_expected_demand_preposition', 'owner_id': owner,
            'service_window': window}]
        baseline['flight_planning'].update(status='conditional_preposition_proposal',
            selected_semantic_action={'kind': 'transfer', 'source_region': f'airport_node_{source}',
                'destination_region': f'airport_node_{destination}', 'earliest_legal_arrival': eta},
            guard_scope='visible local FIFO reserve and current spare only; receiver revalidates in native')
        return baseline

    return planner
