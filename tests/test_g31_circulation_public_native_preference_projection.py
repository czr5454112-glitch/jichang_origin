"""Source-derived preference/dispatch tests; no saved native result or session."""
from copy import deepcopy
import pytest

from scripts.experiments.g31_ics_circulation import public_native_preference_projection as model


def data():
    case=model.contract.domain.cases()[4]
    bundle=model.contract.domain.make_bundle(case)
    static=model.contract.supported_contract();static.pop('native_semantics')
    bundle.update(status='conditional_model_input',model_version=model.contract.VERSION,contract=static)
    for key,tray in bundle['trays'].items():
        ready = 0. if key == 'E' else .1 if key == 'L' else case['blocker_load']
        tray.update(reception_node=-1,tray_id=key,generation=0 if key=='E' else 1,traversal_id=0,
            committed_prefix=[tray['node']],service_ready_known=True,service_ready_at=ready,
            ready_kind='empty_available_at' if key=='E' else 'observed_load_completion',
            load_complete_at=-1. if key=='E' else ready,available_at=ready if key=='P' else 0.)
    for key,job in bundle['jobs'].items():
        job.update(protected_service=True,storage_entered_at=-1.,storage_released_at=-1.)
    bundle['jobs']['loaded']['status']='in_transit'
    bundle['resources']={node['node']:{'node':node['node'],
        'occupancy':sum(t['node']==node['node'] for t in bundle['trays'].values()),
        'actual_available':int(node['node']==5)} for node in static['node_contracts']}
    action={'initial_action':'native_default','empty_departure':.11,'return_delay':0.,'later_action':'native_default'}
    return bundle,action


def engine():
    bundle,action=data();p=model.Projection(bundle,action)
    p.begin_leg('L',4,ready=1.1)
    return p


def test_boolean_action_delay_is_not_equal_to_declared_zero():
    b,a=data();a['return_delay']=False
    assert model.predict(b,a)['status']=='unknown_action'


@pytest.mark.parametrize('defect',['unavailable_empty','completed_blocker','wrong_occupancy','wrong_stock',
    'missing_resource','resource_bool','resource_alias','unknown_load','bad_ready_kind','wrong_ready',
    'wrong_load_complete','wrong_load_start','wrong_generation','changed_prefix','typed_job_bool'])
def test_full_initial_fact_gate_rejects_contradictions_even_with_valid_labels(defect):
    b,a=data()
    if defect=='unavailable_empty':b['trays']['E']['available_at']=99.
    elif defect=='completed_blocker':b['jobs']['blocker']['status']='completed'
    elif defect=='wrong_occupancy':b['resources'][0]['occupancy']=999
    elif defect=='wrong_stock':b['resources'][5]['actual_available']=0
    elif defect=='missing_resource':b['resources'].pop(9)
    elif defect=='resource_bool':b['resources'][0]['occupancy']=True
    elif defect=='resource_alias':b['resources']['0']=deepcopy(b['resources'][0])
    elif defect=='unknown_load':b['trays']['P']['service_ready_known']=False
    elif defect=='bad_ready_kind':b['trays']['P']['ready_kind']='empty_available_at'
    elif defect=='wrong_ready':b['trays']['P']['service_ready_at']+=.1
    elif defect=='wrong_load_complete':b['trays']['P']['load_complete_at']+=.1
    elif defect=='wrong_load_start':b['trays']['L']['service_ready_at']=.2
    elif defect=='wrong_generation':b['trays']['L']['generation']=False
    elif defect=='changed_prefix':b['trays']['L']['committed_prefix']=[0,1,0]
    else:b['jobs']['loaded']['arrival']=False
    assert model.predict(b,a)['status'].startswith('unknown')


def test_best_blocked_loaded_candidate_waits_instead_of_selecting_allowed_alternative():
    p=engine();p.time=1.1
    rows=p.candidate_rows('L')
    assert rows[0]['next']==1 and rows[0]['reason']=='receiving_full'
    assert next(r for r in rows if r['next']==2)['allowed'] is True
    p.try_depart('L')
    assert p.trays['L']['edge_to']==-1 and p.waits[-1]['to']==1


def test_wire_rejection_is_not_a_preference_or_reservation():
    p=engine();p.submit_preference('L',1)
    record=next(e[-1][0] for e in p.events if e[-2]=='command')
    p.time=.12;p.execute_preference(record)
    assert p.commands[-1]['status']=='rejected' and p.commands[-1]['reason']=='receiving_full'
    assert p.trays['L']['preference'] is None


def test_updated_preference_reserves_nothing_and_is_shielded_again_at_dispatch():
    p=engine();p.submit_preference('L',2)
    record=next(e[-1][0] for e in p.events if e[-2]=='command')
    p.time=.12;p.execute_preference(record)
    assert p.commands[-1]['status']=='updated' and p.occupancy(2)==0
    # Public hypothetical state change: a competitor now occupies the preferred
    # receiver. Latest preference is retained but receives no score bonus.
    p.trays['P']['node']=2;p.time=1.1
    assert p.choose_next('L')==1
    assert p.trays['L']['preference']['next']==2


def test_stale_prefix_command_is_rejected():
    p=engine();p.submit_preference('L',2)
    record=next(e[-1][0] for e in p.events if e[-2]=='command')
    p.trays['L']['projection_prefix']+=1;p.time=.12;p.execute_preference(record)
    assert p.commands[-1]['reason']=='stale_executed_prefix'


def test_native_default_accounts_for_scheduled_incoming_without_route_command():
    p=engine();p.trays['L'].update(node=7,goal=6,job='reuse1',ready=8.)
    p.trays['E'].update(node=1,edge_from=1,edge_to=3,goal=4,mode='loaded',scheduled_incoming_node=3)
    p.time=8.;assert p.choose_next('L')==8
    assert p.commands==[]


def test_s4_hidden_merge_calendar_does_not_add_a_visible_score_penalty():
    p=engine();p.trays['L'].update(node=7,goal=6,job='reuse1',ready=8.)
    p.time=8.;p.calendars[3]=[(9.,10.)]
    row=next(x for x in p.candidate_rows('L') if x['next']==3)
    assert row['target_calendar_start']==9. and row['score']==2.7
    assert row['allowed'] is False and row['reason']=='service_calendar'


def test_static_dead_end_stays_in_s4_ranking_but_is_not_a_legal_route_command():
    p=engine();p.trays['L'].update(node=1,goal=4)
    rows=p.candidate_rows('L')
    assert [r['next'] for r in rows]==[3,9]
    assert rows[1]['score']>rows[0]['score']
    p.submit_preference('L',9)
    record=next(e[-1][0] for e in p.events if e[-2]=='command')
    p.time=.12;p.execute_preference(record)
    assert p.commands[-1]['reason']=='no_static_legal_suffix'


@pytest.mark.parametrize('mutation',['allow_export','capacity','minimum_service','missing_tray','moving','bad_load','unknown_jobs'])
def test_unsupported_public_contract_or_lifecycle_fails_closed(mutation):
    bundle,action=data()
    if mutation=='allow_export':bundle['contract']['node_contracts'][5]['allow_export']=False
    elif mutation=='capacity':bundle['contract']['node_contracts'][3]['capacity']=2
    elif mutation=='minimum_service':bundle['contract']['protocol']['native_dispatch_quantum']=.01
    elif mutation=='missing_tray':bundle['trays'].pop('P')
    elif mutation=='moving':bundle['trays']['E']['edge_to']=1
    elif mutation=='bad_load':bundle['trays']['P']['load_end']=True
    else:bundle['jobs'].pop('receiver')
    assert model.predict(bundle,action)['status'].startswith('unknown')


def test_noop_is_not_renamed_to_a_forced_edge_and_prediction_is_not_protection():
    bundle,action=data();result=model.predict(bundle,action)
    assert result['status']=='conditional_prediction'
    assert all(c['job']!='loaded' and c['job']!='reuse1' for c in result['projected_commands'])
    assert result['native_protection_certified'] is False and result['online_information_delivered'] is False


def test_preferences_are_real_commands_without_an_outcome_input():
    bundle,action=data();action.update(initial_action='prefer_2',later_action='prefer_8')
    result=model.predict(bundle,action)
    assert [(c['job'],c['next'],c['status']) for c in result['projected_commands']]==[
        ('loaded',2,'updated'),('reuse1',8,'updated'),('reuse2',3,'updated')]
    assert result['projected_commands'][0]['expiry']==5.
    assert set(result['completion'])==model.contract.JOBS


def test_physical_notification_activates_only_notified_owner_after_timestamp_drain():
    p=engine();p.time=3.2
    p.trays['L'].update(node=2,edge_from=2,edge_to=3)
    p.record('EDGE_ENTER','L',source=2,target=3)
    boundaries=[event for event in p.events if event[-2]=='owner_activation']
    assert {(event[0],event[1],event[-1][0]) for event in boundaries}=={(3.2,99,'A'),(3.2,99,'B')}
    p.record('EDGE_ENTER','L',source=2,target=3)
    assert len([event for event in p.events if event[-2]=='owner_activation'])==2


def test_recovery_runs_on_a_causal_owner_notification_without_waiting_for_periodic_tick():
    p=engine();p.time=1.;p.request('E',1,1.)
    request=p.last_supply
    request.update(terminal=True,ack='rejected',ack_at=1.02)
    p.time=1.53;p.tick('A')
    assert len(p.requests)==1
    p.tick('B')
    assert len(p.requests)==2 and p.last_supply['earliest']==1.53


def test_resource_wait_receipt_does_not_fabricate_owner_notification():
    p=engine();p.record('RESOURCE_WAIT','L',source=0,target=1)
    assert not any(event[-2]=='owner_activation' for event in p.events)


def test_non_goal_merge_commits_after_source_arbitrations_and_wake_uses_quantum():
    p=engine();p.time=3.801
    p.trays['E'].update(node=1,goal=4,job='receiver',mode='loaded',ready=p.time,queued=True)
    p.trays['P'].update(node=9,goal=None,job=None,mode='empty')
    p.try_depart('E')
    assert p.trays['E']['edge_to']==-1 and p.trays['E']['dispatch_pending']
    p.try_depart('L')
    assert p.wait_targets['L']==(1,'receiving_full')
    p.commit('E',3);p.beacon(1)
    assert p.phase_trace[-1]['next_arbitration']==p.time+p.minimum
    assert p.ready_at['L']==3.802


def test_goal_bypass_commits_in_source_phase_without_a_destination_grant_event():
    p=engine();p.time=3.1
    p.trays['P'].update(node=1,goal=9,job='blocker',mode='loaded',ready=p.time,queued=True)
    p.try_depart('P')
    assert p.trays['P']['edge_to']==9
    assert not any(e[-2]=='merge_commit' and e[-1][0]=='P' for e in p.events)


def test_scheduled_incoming_counts_a_tray_during_target_service_after_edge_exit():
    p=engine();p.time=8.75
    p.trays['L'].update(node=7,goal=6,job='reuse1',ready=p.time,queued=True)
    p.trays['E'].update(node=3,edge_from=-1,edge_to=-1,goal=4,job='receiver',mode='loaded',
                       ready=8.801,queued=False,scheduled_incoming_node=3)
    rows=p.candidate_rows('L')
    assert next(r for r in rows if r['next']==3)['incoming']==1
    assert rows[0]['next']==8


def test_planning_exchange_preserves_each_wire_and_publication_addition():
    start=5.299999999999999
    actual_exchange=((start+.01)+.01)+.01+.01
    assert model.planning_decision_epoch(start)==actual_exchange
    assert model.planning_decision_epoch(start)!=start+.04


def test_jit_merge_ready_keeps_public_slot_inverse_arithmetic():
    p=engine();p.time=7.271
    p.trays['L'].update(node=1,goal=4,job='loaded',ready=p.time,queued=True)
    p.trays['P'].update(node=9,goal=None,job=None,mode='empty')
    p.try_depart('L')
    grant=next(e for e in p.events if e[-2]=='merge_commit')
    assert grant[0]==max(p.time,(p.time+p.travel[1,3])-p.travel[1,3])
    assert grant[0]>p.time  # Native expression, not an injected delay/tolerance.
