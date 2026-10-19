"""Pure detached public-data tests; no fitting, runtime, or native calls."""
from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_learning_public as public
from scripts.experiments.g31_ics_circulation import foundation_action_value as value


def observation():
    return {'schema': 'g31.owner_protocol_observation.v1', 'observation_scope': 'controller_policy',
        'owner_id': 'A', 'now': 10., 'node_records': [(0,1,.001,0,0,[2]), (1,1,.001,0,0,[2]), (2,1,.001,0,0,[])],
        'edge_records': [(0,2,2.,1.), (1,2,2.,1.)], 'edge_contracts': [{'from':0,'to':2,'capacity':4}, {'from':1,'to':2,'capacity':4}],
        'node_contracts': [{'node':0,'resource_owner':'A','actual_available':1}, {'node':1,'resource_owner':'A','actual_available':0},
                           {'node':2,'resource_owner':'B'}],
        'trays': [{'tray_id':'E','node':0,'mode':'empty','edge_to':-1,'generation':1,'available_at':0.,'business_bag_id':''},
                  {'tray_id':'H','node':1,'mode':'hold','edge_to':-1,'generation':2,'available_at':15.,'business_bag_id':'done'}],
        'jobs': [{'business_bag_id':'done','status':'completed','arrival':1.}], 'delivered_messages': [], 'known_faults': [],
        'client_transfer_ledger': [], 'transfers': [],
        'control_projection': {'schema':'g31.analytic_control_projection.v1', 'waiting_groups': [
            {'origin':2,'count':5,'demand_observed_at':8.,'jobs':[
                {'business_bag_id':'remote1','origin':2,'arrival':2.,'demand_observed_at':8.,'status':'waiting_for_tray'}]}]}}


def forecast():
    return {'schema':'g31.foundation.new_demand_forecast.v1', 'owner_scope':'A','forecast_origin':10.,
        'bin_edges_seconds':[0.,60.,300.,900.,1800.], 'remaining_support_until':1810.,
        'new_demand_mean_by_region':{'airport_node_2':[2.,3.,4.,5.]},
        'missing_mask_by_region':{'airport_node_2':False}, 'mapping_version':'fixture_public_mapping', 'context_sha256':'context',
        'information_cutoffs':{'training_labels_closed_at':5.,'model_frozen_at':6.,'plan_received_at':0.,'observed_arrivals_through':None}}


def record():
    return {'schema':'g31.foundation.airport_policy_observation.v1','readonly':True,'native_execution_authority':False,
        'candidate_conditional_labels':None,'owner_id':'A','now':10.,'sequence':1,'observation':observation(),
        'decision':{'intents':[{'owner_id':'A','tray_id':'E','source':0,'destination':2,'message_delay':1.,'earliest_departure':12.}]}}


def request(status='pending'):
    return {'request_id':'r','tray_id':'E','source':0,'destination':2,'issued_at':9.,'status':status,
            'status_scope':'own_payload_and_last_delivered_ack_only'}


def test_public_counts_masks_and_actual_model_features():
    row=record(); original=deepcopy(row); f=forecast(); copy_f=deepcopy(f)
    wrapped,audit=public.wrap_record(row,f,episode_id='real_clock_fixture',episode_end=59400.)
    action=public.proposal_actions(row)[0]
    features=value.features(wrapped,action['semantic'])
    assert row==original and f==copy_f
    assert features['source_current_free']==1. and features['destination_known_waiting']==5.
    assert features['destination_known_waiting_jobs_complete']==0.
    assert features['source_current_free_trays_complete']==1.
    assert features['source_demand_missing_60']==1. and features['source_estimated_deficit_missing']==1.
    assert features['remaining_episode_s']==59390.
    assert action['enabled'] is None and action['outcome_label'] is None
    assert audit['observed_counts_for_flight_model'] is None
    accounts=wrapped['circulation_accounts']
    assert accounts['loaded_release_forecast'][0]['available_at']==15.
    assert accounts['committed_inbound']==accounts['committed_outbound']==[]
    assert not any(v['complete']for v in accounts['coverage_by_account_region']['committed_inbound'].values())


@pytest.mark.parametrize('status',['pending','departed','dispatching'])
def test_own_outbound_claim_never_becomes_receiver_inbound_or_free(status):
    o=observation();o['client_transfer_ledger']=[request(status)];o['transfers']=deepcopy(o['client_transfer_ledger'])
    accounts,audit=public.adapt_accounts(o)
    assert accounts['current_free_trays']==[] and accounts['committed_inbound']==accounts['committed_outbound']==[]
    assert accounts['coverage_by_account_region']['current_free_trays']['airport_node_0']['complete'] is False
    assert len(accounts['unresolved_requests'])==(1 if status=='pending' else 0)
    assert audit['excluded_active_claim_trays']==['E']


def test_sensor_disagreement_is_unknown_not_inflated_lower_bound():
    o=observation();o['node_contracts'][0]['actual_available']=0
    accounts,_=public.adapt_accounts(o)
    assert accounts['current_free_trays']==[]
    assert accounts['coverage_by_account_region']['current_free_trays']['airport_node_0']['complete'] is False


def test_exact_local_count_and_absent_group_do_not_attest_full_fifo_scope():
    o=observation()
    o['control_projection']['waiting_groups'].append(
        {'origin':0,'count':7,'demand_observed_at':10.,'jobs':[]})
    accounts,audit=public.adapt_accounts(o)
    coverage=accounts['coverage_by_account_region']['known_waiting_jobs']
    assert coverage['airport_node_0']=={'visible':True,'complete':False,'observed_at':10.}
    assert coverage['airport_node_1']=={'visible':True,'complete':False,'observed_at':10.}
    assert accounts['known_waiting_jobs'][-1]['count']==7
    assert 'not_attested' in audit['waiting_coverage_basis']


@pytest.mark.parametrize('mode,available_at',[('unloading',12.),('hold',15.)])
def test_release_estimate_adds_hold_only_for_unloading(mode,available_at):
    o=observation();o['trays'][1].update(mode=mode,available_at=available_at)
    o['jobs'][0]['hold_seconds']=3.
    accounts,_=public.adapt_accounts(o)
    release=accounts['loaded_release_forecast'][0]
    assert release['available_at']==15. and release['status']=='conditional'
    assert 'not_congestion_upper_bound_or_free_inventory' in release['estimate_scope']


def test_negative_unloading_hold_duration_is_rejected():
    o=observation();o['trays'][1]['mode']='unloading';o['jobs'][0]['hold_seconds']=-1.
    with pytest.raises(ValueError,match='nonnegative_observed_hold_duration'):
        public.adapt_accounts(o)


def test_unknown_count_keeps_representative_bound_not_fake_zero():
    row=record();row['observation']['control_projection']['waiting_groups'][0]['count']=None
    wrapped,_=public.wrap_record(row,forecast(),episode_id='e',episode_end=59400.)
    features=value.features(wrapped,public.proposal_actions(row)[0]['semantic'])
    assert features['destination_known_waiting']==1. and features['destination_known_waiting_count_missing']==1.


@pytest.mark.parametrize('mutation',['future_job','unreleased','future_message','future_group','wrong_owner','duplicate_tray','private'])
def test_public_boundaries_fail_closed(mutation):
    o=observation()
    if mutation=='future_job':o['jobs'][0]['arrival']=11.
    elif mutation=='unreleased':o['jobs'][0]['status']='unreleased'
    elif mutation=='future_message':o['delivered_messages']=[{'observed_at':9.,'delivered_at':11.}]
    elif mutation=='future_group':o['control_projection']['waiting_groups'][0]['demand_observed_at']=11.
    elif mutation=='wrong_owner':o['trays'][0]['node']=2
    elif mutation=='duplicate_tray':o['trays'].append(deepcopy(o['trays'][0]))
    else:o['private_crosswalk']={}
    with pytest.raises(ValueError):public.adapt_accounts(o)


def test_forecast_padding_preserves_source_and_cutoffs_but_never_zero_fills():
    f=forecast();padded=public.extend_forecast_with_unknown_nodes(f,observation())
    assert padded['information_cutoffs']==f['information_cutoffs']
    assert padded['source_forecast_sha256']==public.digest(f)
    assert padded['new_demand_mean_by_region']['airport_node_2']==[2.,3.,4.,5.]
    assert padded['new_demand_mean_by_region']['airport_node_0']==[None]*4
    assert padded['missing_mask_by_region']['airport_node_0'] is True
    assert padded['mapping_version']!=f['mapping_version']


def test_cannot_wrap_existing_outcome_labels_as_observation():
    row=record();row['candidate_conditional_labels']={'fake':0.}
    with pytest.raises(ValueError,match='without_labels'):
        public.wrap_record(row,forecast(),episode_id='e',episode_end=59400.)


def test_registered_projection_mass_unknown_and_mapping_binding():
    from scripts.experiments.g31_ics_circulation import foundation_airport_learning_audit as audit
    regions=['legacy_start_'+str(i)for i in (0,1,2,3,4,5,53)]
    mapping={'schema':'g31.foundation.airport_role_mapping.v2','version':'airport151_std8_pushforward92to95_gtc3_v2',
        'regions':{r:{'nodes':[134,136,138]if r.endswith('_53')else[0,24,26,49,57,95,149],
            'weights':[1/3]*3 if r.endswith('_53')else[1/8,1/8,1/8,1/8,1/8,2/8,1/8]}for r in regions}}
    mapping['sha256']=audit.digest(mapping)
    f=forecast();f['new_demand_mean_by_region']={r:[1.,2.,3.,4.]for r in regions}
    f['missing_mask_by_region']={r:False for r in regions}
    projected=audit.project(f,mapping)
    assert sum(row[0]for row in projected['new_demand_mean_by_region'].values())==pytest.approx(7.)
    assert projected['new_demand_mean_by_region']['airport_node_95'][0]==1.5
    assert projected['information_cutoffs']==f['information_cutoffs']
    f['missing_mask_by_region']['legacy_start_0']=True;f['new_demand_mean_by_region']['legacy_start_0']=[None]*4
    projected=audit.project(f,mapping)
    assert projected['new_demand_mean_by_region']['airport_node_95']==[None]*4
    assert projected['missing_mask_by_region']['airport_node_134'] is False
    mapping['regions']['legacy_start_1']['weights'][0]=0.
    with pytest.raises(ValueError,match='mapping_identity'):audit.project(f,mapping)
