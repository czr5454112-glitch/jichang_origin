"""Pure airport projection/planner tests; no native process is loaded."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_flight as flight


def mapping():
    return flight.static_mapping({'nodes': list(range(151)), 'edges': list(range(227)), 'business_roles': {
        'standard_loader_nodes': list(flight.STANDARD_LOADERS), 'transfer_loader_nodes': list(flight.TRANSFER_LOADERS)}})


def forecast(now=57600., owner='A'):
    return {'schema': 'g31.foundation.new_demand_forecast.v1', 'forecast_origin': now, 'owner_scope': owner,
        'bin_edges_seconds': [0., 60., 300.],
        'new_demand_mean_by_region': {region: [8., 16.] for region in flight.REGIONS},
        'missing_mask_by_region': dict.fromkeys(flight.REGIONS, False),
        'uncertainty_by_region': {}, 'window_summaries_by_region': {},
        'context_sha256': 'legal_context', 'remaining_support_until': now+300.}


def test_role_mapping_conserves_mass_without_using_whole_day_projection():
    original = forecast(); before = copy.deepcopy(original)
    projected = flight.project_forecast(original, mapping(), now=57600., owner='A')
    assert original == before
    assert len(projected['new_demand_mean_by_region']) == 11
    assert projected['new_demand_mean_by_region']['airport_node_0'] == [6., 12.]
    assert projected['new_demand_mean_by_region']['airport_node_134'] == [8./3., 16./3.]
    assert projected['projection_audit']['mapped_known_mass_per_bin'] == [56., 112.]
    assert projected['node_uncertainty_status'] == 'unknown_dependent_projection'
    assert not mapping()['uses_balanced_assignment_or_whole_day_group_counts']


def test_missing_region_contaminates_its_mapped_nodes_and_is_never_zero():
    value = forecast(); value['missing_mask_by_region']['legacy_start_0'] = True
    value['new_demand_mean_by_region']['legacy_start_0'] = [None, None]
    mapped = flight.project_forecast(value, mapping(), now=57600., owner='A')
    assert mapped['new_demand_mean_by_region']['airport_node_0'] == [None, None]
    assert mapped['missing_mask_by_region']['airport_node_134'] is False
    assert not mapped['projection_audit']['missing_mass_imputed_as_zero']


@pytest.mark.parametrize('field,value', [('forecast_origin', 57599.), ('owner_scope', 'B')])
def test_old_or_foreign_forecast_rejected(field, value):
    item = forecast(); item[field] = value
    with pytest.raises(ValueError, match='current_owner'):
        flight.project_forecast(item, mapping(), now=57600., owner='A')


def fixture(monkeypatch):
    observation = {'now': 57600., 'owner_id': 'A', 'version': 1, 'transfers': [], 'jobs': [],
        'node_contracts': [{'node': node, 'zone': 'B', 'resource_owner': 'B', 'capacity': 4,
                            'allow_receive': True} for node in flight.STANDARD_LOADERS + flight.TRANSFER_LOADERS]
        + [{'node': 16, 'zone': 'A', 'resource_owner': 'A', 'capacity': 4, 'allow_export': True}],
        'node_records': [[node, 0, .1] for node in (16, *flight.STANDARD_LOADERS, *flight.TRANSFER_LOADERS)],
        'edge_records': [[16, node, 10., 1.] for node in flight.STANDARD_LOADERS + flight.TRANSFER_LOADERS],
        'edge_contracts': []}
    supply = {'tray_id': 'free', 'node': 16, 'earliest': 57600., 'estimate': 57600.,
        'ledger': 'actual_available', 'owner_id': 'A', 'version': 1, 'dependency': 'free:empty', 'latest': None}
    base = {'intents': [], 'supplies': [supply], 'includes_wait': True}
    monkeypatch.setattr(flight, 'transfer_candidates', lambda *args, **kwargs: copy.deepcopy(base))
    return observation, base


def test_rule_proposes_only_an_actual_empty_transfer_never_fake_future_jobs(monkeypatch):
    obs, base = fixture(monkeypatch); before = copy.deepcopy(obs)
    planner = flight.make_rule_planner(lambda **kwargs: forecast(**kwargs), mapping())
    result = planner(obs, predictive=True, message_delay=2., respect_service_forecasts=False)
    assert obs == before and obs['jobs'] == [] and len(result['intents']) == 1
    assert result['intents'][0]['tray_id'] == 'free'
    assert result['intents'][0]['owner_id'] == 'A'
    assert result['intents'][0]['earliest_departure'] == 57602.
    assert result['flight_planning']['future_jobs_created'] == 0
    assert not result['flight_planning']['strict_nonharm_certified']
    base['supplies'][0]['ledger'] = 'firm_release'
    assert planner(obs, predictive=True)['intents'] == []


def test_existing_queue_intents_and_prefreeze_warmup_keep_old_behavior(monkeypatch):
    obs, base = fixture(monkeypatch)
    def forbidden(**kwargs):
        raise AssertionError('model cannot be read in warmup or displace known work')
    planner = flight.make_rule_planner(forbidden, mapping())
    obs['now'] = 0.
    assert planner(obs, predictive=True) == base
    obs['now'] = 57600.; base['intents'] = [{'existing': 'known_queue'}]
    assert planner(obs, predictive=True) == base


@pytest.mark.parametrize('supply_ledger', [None, 'firm_release', 'conditional_release', 'obligated_arrival'])
def test_no_actual_supply_skips_provider_and_preserves_unknown_demand(monkeypatch, supply_ledger):
    obs, base = fixture(monkeypatch)
    if supply_ledger is None:
        base['supplies'] = []
    else:
        base['supplies'][0]['ledger'] = supply_ledger
    before_obs, before_base = copy.deepcopy(obs), copy.deepcopy(base)
    calls = []
    def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError('no actual supply must not invoke the forecast provider')
    result = flight.make_rule_planner(forbidden, mapping())(obs, predictive=True)
    assert calls == [] and result['intents'] == []
    assert obs == before_obs and base == before_base
    assert {k: v for k, v in result.items() if k != 'flight_planning'} == before_base
    skipped = result['flight_planning']
    assert skipped['status'] == 'forecast_skipped'
    assert skipped['skip_reason'] == 'no_actual_available_supply'
    assert skipped['forecast'] is None and skipped['demand_inference'] == 'not_evaluated'
    assert skipped['forecast_provider_called'] is False and skipped['candidate_count'] == 0
    assert skipped['future_jobs_created'] == 0 and skipped['native_authority'] is False


@pytest.mark.parametrize('change', ['foreign_source', 'no_export', 'no_receive', 'all_inbound', 'service_blocked'])
def test_guards_retain_local_wait(monkeypatch, change):
    obs, base = fixture(monkeypatch)
    if change == 'foreign_source':
        obs['node_contracts'][-1]['resource_owner'] = 'B'
    elif change == 'no_export':
        obs['node_contracts'][-1]['allow_export'] = False
    elif change == 'no_receive':
        for row in obs['node_contracts']:
            row['allow_receive'] = False
    elif change == 'all_inbound':
        obs['transfers'] = [{'destination': node, 'status': 'pending'} for node in
            flight.STANDARD_LOADERS + flight.TRANSFER_LOADERS for _ in range(30)]
    else:
        monkeypatch.setattr(flight, 'departure_avoiding_published_windows', lambda *args:
            {'earliest_departure': obs['now'] + 500., 'conditional_dependencies': [], 'hard_guarantee': False})
    planner = flight.make_rule_planner(lambda **kwargs: forecast(**kwargs), mapping())
    assert planner(obs, predictive=True, respect_service_forecasts=True)['intents'] == []


def test_mapping_cannot_be_changed_to_actual_balanced_subset():
    item = mapping(); item['regions']['legacy_start_0']['nodes'] = [24, 49, 149]
    item['sha256'] = flight.digest({k: v for k, v in item.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='fixed_role_prior'):
        flight.validate_mapping(item)
