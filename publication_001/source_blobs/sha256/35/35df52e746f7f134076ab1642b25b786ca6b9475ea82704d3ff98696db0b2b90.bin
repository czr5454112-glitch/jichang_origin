"""New full-flow research OD contract on the unchanged finite airport graph.

This changes the declared business projection before collection. It never
repairs an old C00/C10 outcome or grants runtime routing authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import copy
import hashlib
import json
import math
from pathlib import Path

from . import foundation_airport_campaign as legacy
from . import foundation_airport_flight as flight

VERSION = 'g31.foundation.airport_cyclic_od.v1'
AUDIT_SCHEMA = 'g31.foundation.airport_cyclic_od_audit.v1'
MAPPING_SCHEMA = 'g31.foundation.airport_role_mapping.v2'
MAPPING_VERSION = 'airport151_std8_pushforward92to95_gtc3_v2'
ORIGIN_MAP = {92: 95}
DESTINATION_MAP = {99: 114, 101: 116, 103: 118, 106: 120, 108: 122, 110: 124}
LEGACY_PROTOCOL_SHA = 'ffe8a52c4ad2b6a841e800e293baa3333b97cd128e6dc3157c9801f828a12589'
LEGACY_CROSSWALK_SHA = '1d2c93812a5551c90b77f4df4ecf4a20c7950748e095eb1ff9e026e37167b1c8'
PROTOCOL_INPUT_SHA = '5a99b213c855e60b94a423a816ea80a2f23acb04a651ae418a21f9056e59edcf'
BUSINESS_SHA = 'cedfdbfb91c029dbe6db6552be8c4d0aad67a3ad78492819de840e22788e5006'
NON_BUSINESS_SHA = '2a1bfb818e79362e0f14dbdd37934e99e64ba2f84ab75ddd3c2ce9128cc211ca'
AUDIT_SHA = '774492c3e25e3a7553a9c407c23e291a5d89a12ae561596cde69fe43a2547aab'
CROSSWALK_SHA = 'b2a1cf3a0d46ce0838e85d19abbb04f6a2007bf38101d356fd9d56e0d72cb03f'
RAW_SHA = '0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87'
ACTIVE_STANDARD = tuple(node for node in flight.STANDARD_LOADERS if node != 92)
ACTIVE_LOADERS = ACTIVE_STANDARD + flight.TRANSFER_LOADERS


def require(value, reason):
    if not value:
        raise ValueError('airport_feasible_domain:' + reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def contract():
    return {'schema': VERSION, 'legacy_protocol_input_sha256': LEGACY_PROTOCOL_SHA,
        'new_protocol_input_sha256': PROTOCOL_INPUT_SHA, 'new_business_semantic_sha256': BUSINESS_SHA,
        'unchanged_non_business_semantic_sha256': NON_BUSINESS_SHA,
        'origin_substitution': {str(k): v for k, v in ORIGIN_MAP.items()},
        'destination_substitution': {str(k): v for k, v in DESTINATION_MAP.items()},
        'source_business_count': 28506, 'whole_parent_count': 360,
        'changed_origins': 3102, 'changed_destinations': 4001, 'changed_union': 6673, 'changed_both': 430,
        'physical_contract': 'nanning-on-carrier-proxy-v1-n4-s4-t2',
        'scope': 'new versioned same-role research OD projection; old negative runs remain valid',
        'native_execution_authority': False, 'finite_buffer_feasibility_proven': False}


def _lineage(raw_path):
    raw_path = Path(raw_path)
    require(hashlib.sha256(raw_path.read_bytes()).hexdigest() == RAW_SHA, 'raw_source_identity')
    result = {}
    for line in raw_path.read_text(encoding='utf8').splitlines()[1:]:
        if not line.strip():
            continue
        identity, arrival, std, origin, destination, unloader, loader = line.split()
        parent = [float(std), int(destination), unloader]
        result[int(identity)] = {'parent_group': 'hg_' + digest(parent)[:24],
            'parent_key': parent, 'source_lane': [loader, int(origin)]}
    require(len(result) == 28506, 'raw_business_domain')
    return result


def validate_projection(original, projected, original_crosswalk, projected_crosswalk, *, raw_path):
    """Recompute the complete exact-ID audit from immutable old/new inputs."""
    require(digest(original) == LEGACY_PROTOCOL_SHA and digest(original_crosswalk) == LEGACY_CROSSWALK_SHA,
        'registered_legacy_input_and_crosswalk')
    require(digest(projected) == PROTOCOL_INPUT_SHA and digest(projected['jobs']) == BUSINESS_SHA,
        'new_business_input_identity')
    require({k: v for k, v in original.items() if k != 'jobs'} ==
        {k: v for k, v in projected.items() if k != 'jobs'}, 'non_business_mutation')
    require(digest({k: v for k, v in projected.items() if k != 'jobs'}) == NON_BUSINESS_SHA, 'physical_contract_identity')
    lineage = _lineage(raw_path)
    require(len(projected['jobs']) == len(projected_crosswalk) == 28506, 'complete_offered_domain')
    changed, parents, lanes = [], defaultdict(list), defaultdict(list)
    counts = Counter()
    for old, new, cross, new_cross in zip(original['jobs'], projected['jobs'], original_crosswalk, projected_crosswalk, strict=True):
        require(old['business_bag_id'] == new['business_bag_id'] == cross['business_bag_id'] == new_cross['business_bag_id'], 'business_order_and_identity')
        expected = copy.deepcopy(old)
        expected['origin'] = ORIGIN_MAP.get(old['origin'], old['origin'])
        expected['destination'] = DESTINATION_MAP.get(old['destination'], old['destination'])
        require(new == expected, 'only_registered_od_substitution')
        expected_cross = copy.deepcopy(cross)
        expected_cross.update(projected_origin=new['origin'], projected_destination=new['destination'])
        require(new_cross == expected_cross, 'crosswalk_exact_projection')
        source = lineage[cross['original_task_id']]
        row = {'business_bag_id': new['business_bag_id'], 'original_task_id': cross['original_task_id'],
            **source, 'old_origin': old['origin'], 'origin': new['origin'],
            'old_destination': old['destination'], 'destination': new['destination']}
        parents[source['parent_group']].append(row)
        if source['source_lane'][0] != 'T':
            lanes[tuple(source['source_lane'])].append(row)
        changed_origin, changed_destination = new['origin'] != old['origin'], new['destination'] != old['destination']
        counts['origin'] += changed_origin; counts['destination'] += changed_destination
        counts['both'] += changed_origin and changed_destination
        if changed_origin or changed_destination:
            changed.append(row)
    require(dict(counts) == {'origin': 3102, 'destination': 4001, 'both': 430} and len(changed) == 6673, 'exact_change_counts')
    require(len(parents) == 360 and len({row['business_bag_id'] for rows in parents.values() for row in rows}) == 28506,
        'whole_parent_partition')
    parent_audit = []
    for parent, rows in sorted(parents.items()):
        require(len({row['old_destination'] for row in rows}) == len({row['destination'] for row in rows}) == 1,
            'whole_parent_destination_split')
        parent_audit.append({'parent_group': parent, 'parent_key': rows[0]['parent_key'], 'count': len(rows),
            'old_destination': rows[0]['old_destination'], 'destination': rows[0]['destination'],
            'business_bag_ids': [row['business_bag_id'] for row in rows]})
    lane_audit = []
    for lane, rows in sorted(lanes.items()):
        require(len({row['old_origin'] for row in rows}) == len({row['origin'] for row in rows}) == 1, 'source_lane_split')
        lane_audit.append({'source_lane': list(lane), 'count': len(rows), 'old_origin': rows[0]['old_origin'],
            'origin': rows[0]['origin'], 'business_bag_ids': [row['business_bag_id'] for row in rows]})
    adjacent = defaultdict(list)
    for edge in projected['edge_contracts']:
        if edge['capacity'] > 0:
            adjacent[edge['from']].append(edge['to'])
    def reachable(start):
        found, pending = {start}, deque([start])
        while pending:
            for target in adjacent[pending.popleft()]:
                if target not in found:
                    found.add(target); pending.append(target)
        return found
    reach = {node: reachable(node) for node in {job['origin'] for job in projected['jobs']} |
        {job['destination'] for job in projected['jobs']} | {53}}
    for job in projected['jobs']:
        stages = [(job['origin'], job['destination'])] if job['storage_node'] < 0 else [
            (job['origin'], job['storage_node']), (job['storage_node'], job['destination'])]
        require(all(target in reach[start] for start, target in stages), 'business_leg_unreachable')
        require(set(ACTIVE_LOADERS) <= reach[job['destination']], 'empty_return_unreachable')
    return {'schema': AUDIT_SCHEMA, 'contract': contract(), 'exact_changed_jobs': changed,
        'exact_changed_ids_sha256': digest([row['business_bag_id'] for row in changed]),
        'whole_parent_audit': parent_audit, 'whole_source_lane_audit': lane_audit,
        'new_crosswalk_sha256': digest(projected_crosswalk), 'all_loaded_paths_reachable': True,
        'all_used_unloaders_return_to_all_used_loaders': True, 'native_execution_performed': False,
        'jobs_deleted': 0, 'non_od_job_fields_changed': 0, 'non_job_input_fields_changed': 0,
        'origin_counts': {str(key): value for key, value in sorted(Counter(job['origin'] for job in projected['jobs']).items())},
        'destination_counts': {str(key): value for key, value in sorted(Counter(job['destination'] for job in projected['jobs']).items())}}


def build_full_input():
    from .original_workload import DEFAULT_RAW
    original, manifest, crosswalk = legacy.build_full_input()
    projected, new_crosswalk = copy.deepcopy(original), copy.deepcopy(crosswalk)
    for job, cross in zip(projected['jobs'], new_crosswalk, strict=True):
        job['origin'] = ORIGIN_MAP.get(job['origin'], job['origin'])
        job['destination'] = DESTINATION_MAP.get(job['destination'], job['destination'])
        cross.update(projected_origin=job['origin'], projected_destination=job['destination'])
    audit = validate_projection(original, projected, crosswalk, new_crosswalk, raw_path=DEFAULT_RAW)
    require(digest(audit) == AUDIT_SHA and digest(new_crosswalk) == CROSSWALK_SHA, 'complete_frozen_lineage_audit')
    return projected, manifest, new_crosswalk, audit


def static_mapping(profile):
    old = flight.static_mapping(profile)
    rows = {}
    for region, old_row in old['regions'].items():
        weights = Counter(ORIGIN_MAP.get(node, node) for node in old_row['nodes'])
        rows[region] = {'nodes': sorted(weights), 'weights': [weights[node] / len(old_row['nodes']) for node in sorted(weights)],
            'rule': 'pushforward_of_frozen_v1_uniform_role_prior'}
    mapping = {'schema': MAPPING_SCHEMA, 'version': MAPPING_VERSION, 'business_contract_version': VERSION,
        'business_semantic_sha256': BUSINESS_SHA, 'source_regions': list(flight.REGIONS), 'regions': rows,
        'source_mapping_version': old['version'], 'source_mapping_sha256': old['sha256'],
        'origin_substitution': {'92': 95}, 'uses_balanced_assignment_or_whole_day_group_counts': False,
        'real_advance_loader_assignment_known': False, 'physical_workload_projection_changed': True,
        'basis': 'static same-role prior pushed through new registered OD substitution; no learned or historical group weights'}
    mapping['sha256'] = digest(mapping)
    return mapping


def validate_mapping(mapping):
    # Only public static role data are needed to reconstruct the exact mapping.
    expected = static_mapping({'nodes': list(range(151)), 'edges': list(range(227)), 'business_roles': {
        'standard_loader_nodes': list(flight.STANDARD_LOADERS), 'transfer_loader_nodes': list(flight.TRANSFER_LOADERS)}})
    require(mapping == expected, 'new_business_forecast_mapping_identity')


def project_forecast(forecast, mapping, *, now, owner):
    validate_mapping(mapping)
    require(forecast.get('schema') == 'g31.foundation.new_demand_forecast.v1'
        and forecast['forecast_origin'] == now and forecast['owner_scope'] == owner, 'current_owner_forecast')
    require(set(forecast['new_demand_mean_by_region']) == set(flight.REGIONS), 'complete_source_regions')
    bins = len(forecast['bin_edges_seconds']) - 1
    means = {f'airport_node_{node}': [0.] * bins for node in sorted(ACTIVE_LOADERS)}
    missing = dict.fromkeys(means, False); raw_totals = [0.] * bins
    for region in flight.REGIONS:
        row = forecast['new_demand_mean_by_region'][region]; absent = forecast['missing_mask_by_region'][region]
        require(len(row) == bins and type(absent) is bool, 'forecast_bins_and_mask')
        targets = mapping['regions'][region]
        for node in targets['nodes']:
            missing[f'airport_node_{node}'] |= absent
        if absent:
            continue
        require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in row), 'forecast_nonnegative_mass')
        for index, value in enumerate(row):
            raw_totals[index] += value
            for node, weight in zip(targets['nodes'], targets['weights'], strict=True):
                means[f'airport_node_{node}'][index] += value * weight
    totals = [math.fsum(row[index] for row in means.values()) for index in range(bins)]
    errors = [b-a for a, b in zip(raw_totals, totals, strict=True)]
    require(all(abs(error) <= 1e-12 * max(1., total) for error, total in zip(errors, raw_totals, strict=True)), 'forecast_mass_conservation')
    for key in means:
        if missing[key]:
            means[key] = [None] * bins
    result = copy.deepcopy(forecast)
    result.update(new_demand_mean_by_region=means, missing_mask_by_region=missing,
        uncertainty_by_region={key: None for key in means}, window_summaries_by_region={},
        source_regional_forecast_sha256=digest(forecast), airport_mapping_sha256=mapping['sha256'],
        source_mapping_version=forecast.get('mapping_version'), mapping_version=MAPPING_VERSION,
        airport_mapping_version=MAPPING_VERSION, business_contract_version=VERSION, business_semantic_sha256=BUSINESS_SHA,
        region_mapping_scope='static_role_prior_pushforward_under_new_business_contract',
        node_uncertainty_status='unknown_dependent_projection', projection_audit={
            'raw_known_mass_per_bin': raw_totals, 'mapped_known_mass_per_bin': totals,
            'floating_point_residual_per_bin': errors, 'mean_mass_conserved': True, 'missing_mass_imputed_as_zero': False})
    return result


def make_rule_planner(forecast_at, mapping, **kwargs):
    return flight.make_rule_planner(forecast_at, mapping, forecast_projector=project_forecast,
        mapping_validator=validate_mapping, injection_nodes=ACTIVE_LOADERS, **kwargs)
