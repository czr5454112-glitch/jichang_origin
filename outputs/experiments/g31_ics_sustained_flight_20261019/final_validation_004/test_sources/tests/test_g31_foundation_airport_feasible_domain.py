"""Full deterministic business-contract and forecast checks, without native."""
import copy
from collections import Counter

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_campaign as legacy
from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as domain
from scripts.experiments.g31_ics_circulation import foundation_airport_flight as flight
from scripts.experiments.g31_ics_circulation.original_workload import DEFAULT_MAP, DEFAULT_RAW


@pytest.fixture(scope='module')
def full():
    return domain.build_full_input()


def test_complete_business_and_physics_are_preserved_except_exact_registered_od(full):
    new, _, crosswalk, audit = full
    old, _, old_crosswalk = legacy.build_full_input()
    assert len(new['jobs']) == len(crosswalk) == 28506
    assert {k: v for k, v in new.items() if k != 'jobs'} == {k: v for k, v in old.items() if k != 'jobs'}
    assert len(new['trays']) == 22 and sum(tray['node'] == 92 for tray in new['trays']) == 2
    assert next(row['capacity'] for row in new['edge_contracts'] if (row['from'], row['to']) == (97, 98)) == 0
    changes = Counter()
    for a, b in zip(old['jobs'], new['jobs'], strict=True):
        keys = {key for key in a if a[key] != b[key]}
        assert keys <= {'origin', 'destination'}
        changes.update(keys); changes['union'] += bool(keys)
    assert changes == {'origin': 3102, 'destination': 4001, 'union': 6673}
    assert domain.validate_projection(old, new, old_crosswalk, crosswalk, raw_path=DEFAULT_RAW) == audit
    assert domain.digest(audit) == domain.AUDIT_SHA
    assert domain.digest(crosswalk) == domain.CROSSWALK_SHA


def test_exact_ids_whole_parent_and_lane_partition(full):
    data, _, _, audit = full
    assert len(audit['exact_changed_jobs']) == 6673
    assert len({row['business_bag_id'] for row in audit['exact_changed_jobs']}) == 6673
    parents = audit['whole_parent_audit']
    assert len(parents) == 360 and sum(row['count'] for row in parents) == 28506
    assert sum(row['old_destination'] != row['destination'] for row in parents) == 48
    assert set(identity for row in parents for identity in row['business_bag_ids']) == {job['business_bag_id'] for job in data['jobs']}
    changed_lanes = [row for row in audit['whole_source_lane_audit'] if row['old_origin'] != row['origin']]
    assert [(row['source_lane'], row['count']) for row in changed_lanes] == [(['A1', 2], 392), (['B2', 2], 1848), (['D1', 3], 862)]
    assert all(row['origin'] == 95 for row in changed_lanes)
    assert audit['all_loaded_paths_reachable'] and audit['all_used_unloaders_return_to_all_used_loaders']
    assert not audit['native_execution_performed']


@pytest.mark.parametrize('mutation', [
    lambda data: data['jobs'][0].update(arrival=data['jobs'][0]['arrival'] + .01),
    lambda data: data['jobs'].pop(),
    lambda data: data['trays'][0].update(node=95),
    lambda data: data['edge_contracts'][0].update(capacity=1000),
])
def test_timing_deletion_initialization_and_capacity_changes_are_rejected(full, mutation):
    new, _, crosswalk, _ = full
    modified = copy.deepcopy(new); mutation(modified)
    old, _, old_crosswalk = legacy.build_full_input()
    with pytest.raises(ValueError, match='new_business_input_identity'):
        domain.validate_projection(old, modified, old_crosswalk, crosswalk, raw_path=DEFAULT_RAW)


def forecast():
    return {'schema': 'g31.foundation.new_demand_forecast.v1', 'forecast_origin': 60000., 'owner_scope': 'A',
        'mapping_version': 'B1-frozen-regions', 'bin_edges_seconds': [0, 60, 300],
        'new_demand_mean_by_region': {region: [8., 16.] for region in flight.REGIONS},
        'missing_mask_by_region': {region: False for region in flight.REGIONS},
        'uncertainty_by_region': {}, 'window_summaries_by_region': {},
        'information_cutoffs': {'training_labels_closed_at': 43200., 'model_frozen_at': 43200.,
            'plan_received_at': 0., 'observed_arrivals_through': None}, 'context_sha256': 'untouched'}


def test_public_prior_pushforward_keeps_mass_cutoffs_and_no_workload_labels():
    mapping = domain.static_mapping(legacy.read(DEFAULT_MAP)); f = forecast()
    before = copy.deepcopy(f)
    actual = domain.project_forecast(f, mapping, now=60000., owner='A')
    assert f == before
    assert 'airport_node_92' not in actual['new_demand_mean_by_region']
    assert actual['new_demand_mean_by_region']['airport_node_95'] == [12., 24.]
    assert actual['new_demand_mean_by_region']['airport_node_0'] == [6., 12.]
    assert actual['new_demand_mean_by_region']['airport_node_134'] == [8./3., 16./3.]
    assert actual['projection_audit']['mapped_known_mass_per_bin'] == [56., 112.]
    assert actual['information_cutoffs'] == before['information_cutoffs']
    assert actual['context_sha256'] == before['context_sha256']
    assert actual['mapping_version'] == domain.MAPPING_VERSION and actual['business_semantic_sha256'] == domain.BUSINESS_SHA
    assert not mapping['uses_balanced_assignment_or_whole_day_group_counts']
    old = flight.project_forecast(f, flight.static_mapping(legacy.read(DEFAULT_MAP)), now=60000., owner='A')
    assert old['new_demand_mean_by_region']['airport_node_92'] == [6., 12.]
    assert old['new_demand_mean_by_region']['airport_node_95'] == [6., 12.]


def test_missing_raw_region_remains_unknown_at_all_affected_new_nodes():
    mapping = domain.static_mapping(legacy.read(DEFAULT_MAP)); f = forecast()
    f['missing_mask_by_region']['legacy_start_0'] = True
    f['new_demand_mean_by_region']['legacy_start_0'] = [None, None]
    actual = domain.project_forecast(f, mapping, now=60000., owner='A')
    for node in domain.ACTIVE_STANDARD:
        assert actual['new_demand_mean_by_region'][f'airport_node_{node}'] == [None, None]
    assert not actual['missing_mask_by_region']['airport_node_134']


def test_old_or_tampered_mapping_cannot_be_consumed_by_new_domain():
    old = flight.static_mapping(legacy.read(DEFAULT_MAP))
    with pytest.raises(ValueError, match='mapping_identity'):
        domain.project_forecast(forecast(), old, now=60000., owner='A')
    mapping = domain.static_mapping(legacy.read(DEFAULT_MAP))
    mapping['regions']['legacy_start_0']['weights'][0] = 0.
    mapping['sha256'] = domain.digest({k: v for k, v in mapping.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='mapping_identity'):
        domain.validate_mapping(mapping)


def test_new_planner_uses_only_registered_injection_nodes_and_keeps_no_supply_shortcut(monkeypatch):
    captured = {}
    def seam(*args, **kwargs):
        captured.update(kwargs)
        return 'planner'
    monkeypatch.setattr(flight, 'make_rule_planner', seam)
    assert domain.make_rule_planner(lambda **kwargs: None, domain.static_mapping(legacy.read(DEFAULT_MAP))) == 'planner'
    assert captured['injection_nodes'] == domain.ACTIVE_LOADERS and 92 not in captured['injection_nodes']
    assert captured['forecast_projector'] is domain.project_forecast
    assert captured['mapping_validator'] is domain.validate_mapping
