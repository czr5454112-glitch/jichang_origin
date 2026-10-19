import copy
import time

import pytest

from scripts.experiments.g31_ics_circulation import foundation_action_value as value


def observation():
    now = 60000.
    forecast = {'schema': 'g31.foundation.new_demand_forecast.v1', 'forecast_origin': now,
        'owner_scope':'A', 'remaining_support_until':now+1800, 'context_sha256':'plan',
        'information_cutoffs': {'training_labels_closed_at':43200.,'model_frozen_at':43200.,'plan_received_at':0.,'observed_arrivals_through':None},
        'mapping_version':'test-regions-v1',
        'bin_edges_seconds':list(range(0,1801,60)),
        'new_demand_mean_by_region':{'left':[1.]*30,'right':[3.]*30},
        'missing_mask_by_region':{'left':False,'right':False}}
    accounts = {'current_free_trays':[{'tray_id':'t','generation':1,'region':'left','observed_at':now}],
        'known_waiting_jobs':[], 'loaded_release_forecast':[], 'committed_inbound':[],
        'committed_outbound':[], 'unresolved_requests':[],
        'coverage_by_account_region':{name:{region:{'visible':True,'complete':True,'observed_at':now}
            for region in ('left','right')} for name in value.ACCOUNT_NAMES}}
    return value.wrap_observation(episode_id='e',owner='A',decision_id='d',now=now,
        base_observation={'owner':'A','at':now},forecast=forecast,accounts=accounts,
        information_variant='static_plan',remaining_episode_seconds=5000,flight_context_sha256='plan',mapping_version='test-regions-v1')


def action(destination='right'):
    return {'kind':'transfer','source_region':'left','destination_region':destination,
            'earliest_legal_arrival':60300.}


def test_forecast_changes_candidate_differences():
    original = observation()
    before = [value.features(original,action(x))['destination_estimated_deficit_at_arrival'] for x in ('left','right')]
    changed = copy.deepcopy(original)
    changed['demand_forecast']['new_demand_mean_by_region']['left']=[6.]*30
    after = [value.features(changed,action(x))['destination_estimated_deficit_at_arrival'] for x in ('left','right')]
    assert before[0] < before[1] and after[0] > after[1]


def test_forecast_not_relabelled_at_later_time():
    row=observation();row['now']+=1
    with pytest.raises(ValueError,match='base_owner_time|current_time_projection'):
        value.features(row,action())


def test_conditional_release_never_current_free_and_outbound_not_double_pledged():
    row=observation(); accounts=row['circulation_accounts']
    accounts['loaded_release_forecast']=[{'tray_id':'u','generation':1,'region':'left','observed_at':60000.,'available_at':60200.,'status':'conditional'}]
    accounts['committed_outbound']=[{'tray_id':'u','generation':1,'region':'left','observed_at':60000.}]
    features=value.features(row,action())
    assert features['source_current_free']==1 and features['source_conditional_release_by_arrival']==0


def test_duplicate_future_supply_rejected():
    row=observation();row['circulation_accounts']['loaded_release_forecast']=[
        {'tray_id':'t','generation':1,'region':'left','observed_at':60000.,'available_at':60200.,'status':'conditional'}]
    with pytest.raises(ValueError,match='multiple_supply'):
        value.features(row,action())


@pytest.mark.parametrize('other_account', ['loaded_release_forecast', 'committed_outbound'])
def test_same_physical_tray_with_another_generation_cannot_double_count_or_evade_outbound(other_account):
    row = observation()
    row['circulation_accounts'][other_account] = [{'tray_id':'t','generation':2,'region':'left',
        'observed_at':60000.,'available_at':60200.,'status':'conditional'}]
    with pytest.raises(ValueError, match='conflicting_tray_generations'):
        value.features(row, action())


def test_unknown_demand_has_explicit_missing_feature():
    row=observation();row['demand_forecast']['new_demand_mean_by_region']['right']=[None]*30
    row['demand_forecast']['missing_mask_by_region']['right']=True
    f=value.features(row,action())
    assert f['destination_demand_missing_300']==1 and f['destination_new_demand_300']==0


def test_future_arrival_cannot_enter_known_waiting():
    row=observation();row['circulation_accounts']['known_waiting_jobs']=[
        {'kind':'job','origin':2,'business_bag_id':'future','region':'right','arrival_at':60001.,'observed_at':60000.}]
    with pytest.raises(ValueError,match='future_waiting'):
        value.features(row,action())


def test_arrival_after_asof_observation_rejected():
    row=observation();row['circulation_accounts']['known_waiting_jobs']=[
        {'kind':'job','origin':2,'business_bag_id':'future-asof','region':'right','arrival_at':59999.,'observed_at':59998.}]
    with pytest.raises(ValueError,match='future_waiting'):
        value.features(row,action())


def test_ack_after_account_snapshot_rejected():
    row=observation();row['circulation_accounts']['committed_inbound']=[
        {'tray_id':'in','generation':1,'region':'right','observed_at':59998.,'available_at':60300.,
         'ack_status':'accepted','ack_observed_at':59999.,'request_id':'r'}]
    with pytest.raises(ValueError,match='future_ack'):
        value.features(row,action())


def test_opaque_ids_do_not_become_features():
    row=observation(); expected=value.features(row,action())
    row['episode_id']='other';row['decision_id']='other'
    assert value.features(row,action())==expected


def test_no_plan_rejects_plan_input():
    row=observation()
    with pytest.raises(ValueError,match='no_plan'):
        value.wrap_observation(episode_id='e',owner='A',decision_id='d',now=row['now'],
            base_observation=row['base_observation'],forecast=row['demand_forecast'],accounts=row['circulation_accounts'],
            information_variant='no_plan',remaining_episode_seconds=10,mapping_version='test-regions-v1')


@pytest.mark.parametrize('mutation,reason',[
    (lambda f:f.update(owner_scope='B'),'wrong_owner'),
    (lambda f:f['information_cutoffs'].update(model_frozen_at=60001.),'future_forecast')])
def test_forecast_owner_and_model_cutoff(mutation,reason):
    row=observation();mutation(row['demand_forecast'])
    with pytest.raises(ValueError,match=reason):
        value.wrap_observation(episode_id='e',owner='A',decision_id='d',now=row['now'],
            base_observation=row['base_observation'],forecast=row['demand_forecast'],accounts=row['circulation_accounts'],
            information_variant='static_plan',remaining_episode_seconds=10,flight_context_sha256='plan',mapping_version='test-regions-v1')


def test_undeclared_region_does_not_silently_become_missing():
    candidate=action();candidate['destination_region']='different_airport_node'
    with pytest.raises(ValueError,match='action_region_missing'):
        value.features(observation(),candidate)


def test_missing_cutoffs_rejected_on_saved_json():
    row=observation();row['demand_forecast']['information_cutoffs']={}
    with pytest.raises(ValueError,match='cutoff_schema'):
        value.features(row,action())


@pytest.mark.parametrize('name', value.ACCOUNT_NAMES)
def test_unknown_empty_account_is_masked_per_account_and_region(name):
    row = observation()
    known = value.features(row, action())
    row['circulation_accounts']['coverage_by_account_region'][name]['right'] = {
        'visible': False, 'complete': False, 'observed_at': None}
    unknown = value.features(row, action())
    assert known['destination_estimated_deficit_missing'] == 0
    assert unknown['destination_' + name + '_visible'] == 0
    assert unknown['destination_' + name + '_complete'] == 0
    assert unknown['destination_estimated_deficit_missing'] == 1
    assert unknown['destination_estimated_deficit_at_arrival'] == 0
    assert unknown['destination_deficit_after_transfer'] == 0
    assert unknown['destination_deficit_after_transfer_missing'] == 1
    assert unknown['source_estimated_deficit_missing'] == 0


def test_incomplete_supply_preserves_observed_records_but_does_not_invent_scarcity():
    row = observation()
    row['circulation_accounts']['coverage_by_account_region']['current_free_trays']['left']['complete'] = False
    result = value.features(row, action())
    assert result['source_current_free'] == 1
    assert result['source_current_free_trays_visible'] == 1
    assert result['source_current_free_trays_complete'] == 0
    assert result['source_estimated_deficit_missing'] == 1
    assert result['source_scarcity_after_transfer'] == result['transfer_x_source_scarcity'] == 0


def test_incomplete_waiting_keeps_actual_known_lower_bound():
    row = observation()
    row['circulation_accounts']['known_waiting_jobs'] = [{'kind':'job','origin':2,'business_bag_id':'known',
        'region':'right','arrival_at':59999.,'observed_at':60000.}]
    row['circulation_accounts']['coverage_by_account_region']['known_waiting_jobs']['right']['complete'] = False
    result = value.features(row, action())
    assert result['destination_known_waiting'] == 1
    assert result['destination_known_waiting_jobs_complete'] == 0
    assert result['destination_estimated_deficit_missing'] == 1


def compact_observation(count=7):
    row = observation()
    group = {'origin':2, 'count':count, 'demand_observed_at':60000., 'jobs':[{
        'business_bag_id':'representative', 'origin':2, 'status':'waiting_for_tray',
        'arrival':59990., 'demand_observed_at':60000.}]}
    row['base_observation']['control_projection'] = {'schema':'g31.analytic_control_projection.v1',
        'waiting_groups':[group]}
    row['circulation_accounts']['known_waiting_jobs'] = [{'kind':'waiting_group','origin':2,
        'region':'right','observed_at':60000.,'count':count,
        'provenance':{'kind':'public_control_projection_waiting_group','group_sha256':value.digest(group)}}]
    return row


def test_public_compact_exact_count_is_seven_not_one_representative():
    result = value.features(compact_observation(), action())
    assert result['destination_known_waiting'] == 7
    assert result['destination_known_waiting_count_missing'] == 0
    assert result['destination_known_waiting_jobs_complete'] == 1
    assert result['destination_estimated_deficit_at_arrival'] == 22


def test_public_unknown_compact_count_retains_only_actual_lower_bound_and_masks():
    result = value.features(compact_observation(None), action())
    assert result['destination_known_waiting'] == 1
    assert result['destination_known_waiting_count_missing'] == 1
    assert result['destination_known_waiting_jobs_complete'] == 0
    assert result['destination_estimated_deficit_missing'] == 1
    assert result['destination_estimated_deficit_at_arrival'] == 0


@pytest.mark.parametrize('mutate,reason', [
    (lambda row: row['circulation_accounts']['known_waiting_jobs'][0].update(count=50), 'public_count'),
    (lambda row: row['circulation_accounts']['known_waiting_jobs'][0]['provenance'].update(group_sha256='unbound'), 'count_provenance'),
    (lambda row: row['base_observation'].pop('control_projection'), 'public_projection'),
    (lambda row: row['circulation_accounts']['known_waiting_jobs'].append({
        'kind':'job','origin':2,'business_bag_id':'another', 'region':'right','arrival_at':59999.,'observed_at':60000.}), 'individual_overlap'),
])
def test_compact_count_cannot_come_from_private_truth_or_double_count_group(mutate, reason):
    row = compact_observation()
    mutate(row)
    with pytest.raises(ValueError, match=reason):
        value.features(row, action())


def test_future_public_representative_is_rejected_even_with_updated_digest():
    row = compact_observation()
    group = row['base_observation']['control_projection']['waiting_groups'][0]
    group['jobs'][0]['arrival'] = 60001.
    row['circulation_accounts']['known_waiting_jobs'][0]['provenance']['group_sha256'] = value.digest(group)
    with pytest.raises(ValueError, match='future_waiting'):
        value.features(row, action())


def test_boolean_public_count_is_not_an_exact_integer_count():
    row = compact_observation(1)
    group = row['base_observation']['control_projection']['waiting_groups'][0]
    group['count'] = True
    row['circulation_accounts']['known_waiting_jobs'][0]['provenance']['group_sha256'] = value.digest(group)
    with pytest.raises(ValueError, match='public_count'):
        value.features(row, action())


def test_explicit_coverage_required_and_legacy_observations_not_relabelled():
    row = observation()
    del row['circulation_accounts']['coverage_by_account_region']
    with pytest.raises(ValueError, match='account_schema'):
        value.features(row, action())
    row = observation()
    row['schema'] = 'g31.foundation.flight_aware_observation.v1'
    with pytest.raises(ValueError, match='observation_schema'):
        value.features(row, action())


@pytest.mark.parametrize('mutate,reason', [
    (lambda row: row['circulation_accounts']['coverage_by_account_region']['committed_inbound'].pop('right'), 'coverage_regions'),
    (lambda row: row['circulation_accounts']['coverage_by_account_region']['known_waiting_jobs']['right'].update(observed_at=60001.), 'coverage_time'),
    (lambda row: row['circulation_accounts']['current_free_trays'][0].update(region='undeclared'), 'outside_forecast'),
    (lambda row: row['circulation_accounts']['coverage_by_account_region']['current_free_trays']['left'].update(
        visible=False,complete=False,observed_at=None), 'invisible_record'),
])
def test_account_coverage_and_observed_record_binding(mutate, reason):
    row = observation()
    mutate(row)
    with pytest.raises(ValueError, match=reason):
        value.features(row, action())


def test_unknown_forecast_also_masks_complete_account_deficit():
    row = observation()
    row['demand_forecast']['missing_mask_by_region']['right'] = True
    result = value.features(row, action())
    assert result['destination_estimated_deficit_missing'] == 1
    assert result['destination_deficit_after_transfer'] == 0


def inbound_observation(status='departed', kind='received_peer_ack'):
    row = observation()
    native_ack = {'sequence':7,'attempt':7,'observed_at':59995.,'delivered_at':59996.,
        'status':status,'reason':'','received_at':-1.}
    evidence = {'schema':'g31.foundation.public_inbound_ack.v1','kind':kind,
        'source_owner':'B' if kind == 'received_peer_ack' else 'A','target_owner':'A',
        'request_id':'incoming-1','tray_id':'inbound','generation':2,'region':'right',
        'captured_at':59997.,'available_to_owner_at':59998.,'native_ack':copy.deepcopy(native_ack)}
    row['base_observation']['inbound_ack_evidence'] = [evidence]
    row['circulation_accounts']['committed_inbound'] = [{'tray_id':'inbound','generation':2,
        'region':'right','observed_at':60000.,'available_at':60200.,'request_id':'incoming-1',
        'ack_status':status,'ack_observed_at':59995.,'native_ack':native_ack,
        'ack_provenance':{'kind':'public_inbound_ack_evidence','evidence_sha256':value.digest(evidence)}}]
    return row


@pytest.mark.parametrize('kind', ['received_peer_ack', 'own_public_outbox', 'native_receiving_lease'])
def test_actual_departed_native_ack_preserved_as_future_inbound_not_free_stock(kind):
    row = inbound_observation(kind=kind)
    before = copy.deepcopy(row)
    result = value.features(row, action())
    assert result['destination_committed_inbound_by_arrival'] == 1
    assert result['destination_current_free'] == 0
    assert row == before
    assert row['circulation_accounts']['committed_inbound'][0]['native_ack']['status'] == 'departed'


def test_accepted_commitment_is_not_relabelled_as_departed():
    row = inbound_observation(status='accepted')
    assert value.features(row, action())['destination_committed_inbound_by_arrival'] == 1
    row['circulation_accounts']['committed_inbound'][0]['ack_status'] = 'departed'
    with pytest.raises(ValueError, match='must_not_be_normalized'):
        value.features(row, action())


@pytest.mark.parametrize('mutate,reason', [
    (lambda row: row['base_observation'].pop('inbound_ack_evidence'), 'current_public_inbound'),
    (lambda row: row['circulation_accounts']['committed_inbound'][0]['ack_provenance'].update(evidence_sha256='fake'), 'original_provenance'),
    (lambda row: row['base_observation']['inbound_ack_evidence'][0].update(target_owner='B'), 'receiver_entity_scope'),
    (lambda row: row['base_observation']['inbound_ack_evidence'][0].update(kind='own_public_outbox'), 'sender_outbox'),
    (lambda row: row['circulation_accounts']['committed_inbound'][0]['native_ack'].update(status='accepted'), 'original_provenance'),
    (lambda row: row['base_observation']['inbound_ack_evidence'].append(copy.deepcopy(row['base_observation']['inbound_ack_evidence'][0])), 'current_public_inbound'),
])
def test_departed_claim_requires_original_ack_and_actual_receiver_public_scope(mutate, reason):
    row = inbound_observation()
    mutate(row)
    with pytest.raises(ValueError, match=reason):
        value.features(row, action())


@pytest.mark.parametrize('status', ['pending', 'rejected', 'received', 'unknown'])
def test_unresolved_rejected_or_received_ack_is_not_future_inbound(status):
    with pytest.raises(ValueError, match='not_future_inbound'):
        value.features(inbound_observation(status), action())


def test_future_receiver_delivery_rejected_despite_rebound_provenance():
    row = inbound_observation()
    evidence = row['base_observation']['inbound_ack_evidence'][0]
    evidence['available_to_owner_at'] = 60001.
    row['circulation_accounts']['committed_inbound'][0]['ack_provenance']['evidence_sha256'] = value.digest(evidence)
    with pytest.raises(ValueError, match='actual_delivery_order'):
        value.features(row, action())


def test_supervised_fit_has_real_weights_and_portable_scores():
    rows=[]
    for index in range(4):
        obs=observation(); obs['demand_forecast']['new_demand_mean_by_region']['right']=[float(index+1)]*30
        for target in ('left','right'):
            candidate=action(target)
            rows.append({'observation':obs,'action':candidate,'target_value':float(index if target=='right' else -index),
                         'split':'train','parent_group':'synthetic-contract-test'})
    model=value.fit(rows,information_variant='static_plan',seed=17,epochs=10,deadline=time.monotonic()+30,
                    objective='synthetic numerical contract test only')
    assert len(model['parameters']['layers'])==3 and len(model['parameters']['layers'][0]['weight'])==64
    assert model['training_curve'][-1]['mse']<model['training_curve'][0]['mse']
    assert len(value.predict(model,[r['observation'] for r in rows],[r['action'] for r in rows]))==len(rows)
    bad=copy.deepcopy(model);bad['parameters']['layers'][0]['bias']=[0]
    with pytest.raises(ValueError,match='layer_shape'):
        value.predict(bad,[rows[0]['observation']],[rows[0]['action']])
