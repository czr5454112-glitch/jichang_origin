"""Detached structural counterexamples; no native execution or fitting."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_evidence as evidence


def binding_fixture():
    proposal={'request_id':'proposal','tray_id':'T','source':0,'destination':1,'issued_at':43200.,
              'earliest_departure':43200.,'message_delay':2.,'expiry':44000.,'expected_version':10,
              'forecast_ledger':'actual_available','forecast_dependency':'T:empty'}
    observation={'owner_id':'A','now':43200.,'trays':[{'tray_id':'T','node':0,'generation':7,'mode':'empty','edge_to':-1}],
        'client_transfer_ledger':[],'node_contracts':[{'node':0,'resource_owner':'A'}]}
    supply={'tray_id':'T','node':0,'owner_id':'A','estimate':43200.,'ledger':'actual_available','dependency':'T:empty'}
    row={'schema':'g31.foundation.airport_policy_observation.v2','sequence':1,'owner_id':'A','now':43200.,'readonly':True,'candidate_conditional_labels':None,
         'observation':observation,'decision':{'intents':[proposal],'supplies':[supply],'forecasts':[deepcopy(supply)]}}
    residual=deepcopy(row);residual['sequence']=2;residual['decision']={'intents':[]}
    request=deepcopy(proposal);request.pop('expected_version');request.update(request_id='r',owner_id='A')
    call={'at':43200.,'kind':'transfer','retry':False,'request':request,'reply':{'status':'pending'}}
    group={'owner_id':'A','decision':deepcopy(row['decision']),'attempts':[{'request_id':'r','reply':deepcopy(call['reply'])}]}
    return [row,residual],group,[call]


def receipt(event,time,*,job='',leg='',reason='',source=-1,destination=-1,node=-1):
    return {'event':event,'time':time,'business_bag_id':job,'transport_leg_id':leg,'reason':reason,
            'tray_id':'T' if leg or reason=='r' else '', 'traversal_id':8,'from':source,'to':destination,'node':node}


def snapshot():
    leg='r:empty_return:4'
    return {'physical_clock':44000.,'advance':{'status':'reached','horizon_complete':True},
        'jobs':[{'business_bag_id':'old','status':'completed','completed_at':43300.},
                {'business_bag_id':'new','status':'waiting_for_tray','completed_at':-1.},
                {'business_bag_id':'future','status':'unreleased','completed_at':-1.}],
        'population':{'observed':2,'completed':1},'trays':[{'tray_id':'T'}],
        'transfers':[{'request_id':'r','tray':0,'departed_at':43202.001,'received_at':43600.}],
        'leg_identities':[{'runtime_id':4,'transport_leg_id':leg,'tray':0,'job':-1,'kind':'empty_return'}],
        'receipts':[receipt('BAG_ARRIVAL',43000.,job='old'),receipt('BAG_ARRIVAL',43300.,job='new'),
            receipt('UNLOAD_COMPLETE',43300.,job='old'),
            receipt('EXPORT_GRANTED',43202.,reason='r',source=0,destination=1),
            receipt('LEG_START',43202.,leg=leg,source=0,destination=1),
            receipt('EDGE_ENTER',43202.001,leg=leg,source=0,destination=2),
            receipt('EMPTY_RECEIVED',43600.,leg=leg,reason='r',node=1,destination=1)]}


def ack_view():
    return {'owner_id':'A','now':44000.,'delivered_transfer_acks':[
        {'request_id':'r','status':'dispatching','observed_at':43202.,'delivered_at':43202.2}]}


def bound():
    callbacks,group,calls=binding_fixture()
    return evidence.bind_submissions(callbacks,group,calls,at=43200.)[0]


def test_exact_residual_submit_join_is_not_itself_execution_label():
    callbacks,group,calls=binding_fixture()
    retry=deepcopy(calls[0]);retry['retry']=True;retry['at']=43260.
    rows=evidence.bind_submissions(callbacks,group,calls+[retry],at=43200.)
    assert len(rows)==1 and rows[0]['target_value'] is None
    assert rows[0]['actual_request']['request_id']=='r' and rows[0]['pre_submit_tray']['generation']==7


@pytest.mark.parametrize('mutation',['payload','owner','time','duplicate_first','missing_residual','preexisting','initial','submit_reply'])
def test_binding_tampering_fails_closed(mutation):
    callbacks,group,calls=binding_fixture()
    if mutation=='payload':calls[0]['request']['destination']=2
    elif mutation=='owner':calls[0]['request']['owner_id']='B'
    elif mutation=='time':calls[0]['at']+=1
    elif mutation=='duplicate_first':calls.append(deepcopy(calls[0]))
    elif mutation=='missing_residual':callbacks.pop()
    elif mutation=='preexisting':callbacks[0]['observation']['client_transfer_ledger']=[{'request_id':'r'}]
    elif mutation=='initial':group['decision']['intents'][0]['expiry']+=1
    else:calls[0]['reply']['status']='rejected'
    with pytest.raises(ValueError):evidence.bind_submissions(callbacks,group,calls,at=43200.)


def test_terminal_residual_proposal_is_not_another_action():
    callbacks,group,calls=binding_fixture()
    callbacks[-1]['decision']=deepcopy(callbacks[0]['decision'])
    assert len(evidence.bind_submissions(callbacks,group,calls,at=43200.))==1


def test_real_behavior_integral_counts_all_arrived_jobs_and_closes_only_window():
    index=evidence.snapshot_index(snapshot(),expected_population=3)
    label=evidence.realized_return(index,start=43200.)
    assert label['target_value']==-300. # old:100; new:200; unreleased:0
    assert label['label_end']==43500. and label['physical_population']==3
    assert label['counterfactual_label'] is False
    actual=evidence.execution_asof(bound(),index,ack_view(),label_end=43500.)
    assert actual['status']=='actual_execution_and_delivered_ack_bound'
    assert actual['received_within_label_window'] is False


@pytest.mark.parametrize('mutation',['future_ack','wrong_owner','duplicate_edge','wrong_tray','wrong_first_source','no_edge','rejected'])
def test_execution_evidence_not_inferred_from_availability(mutation):
    data=snapshot();acks=ack_view()
    if mutation=='future_ack':acks['delivered_transfer_acks'][0].update(observed_at=43510.,delivered_at=43511.)
    elif mutation=='wrong_owner':acks['owner_id']='B'
    elif mutation=='duplicate_edge':data['receipts'].append(deepcopy(data['receipts'][5]))
    elif mutation=='wrong_tray':data['trays'][0]['tray_id']='OTHER'
    elif mutation=='wrong_first_source':data['receipts'][5]['from']=99
    elif mutation=='no_edge':data['receipts']=[r for r in data['receipts'] if r['event']!='EDGE_ENTER']
    else:acks['delivered_transfer_acks'].append({'request_id':'r','status':'rejected','observed_at':43203.,'delivered_at':43203.2})
    index=evidence.snapshot_index(data,expected_population=3)
    if mutation in ('future_ack','no_edge'):
        result=evidence.execution_asof(bound(),index,acks,label_end=43500.)
        assert result['target_value'] is None and result['status']!='actual_execution_and_delivered_ack_bound'
    else:
        with pytest.raises(ValueError):evidence.execution_asof(bound(),index,acks,label_end=43500.)


@pytest.mark.parametrize('mutation',['missing_arrival','duplicate_job','completion_mismatch','partial_timestamp'])
def test_incomplete_population_or_timestamp_cannot_mint_reward(mutation):
    data=snapshot()
    if mutation=='missing_arrival':data['receipts'].pop(0)
    elif mutation=='duplicate_job':data['jobs'][1]=deepcopy(data['jobs'][0])
    elif mutation=='completion_mismatch':data['jobs'][0]['completed_at']+=1
    else:data['advance']['horizon_complete']=False
    with pytest.raises(ValueError):evidence.snapshot_index(data,expected_population=3)


def test_fixed_window_does_not_use_future_completion_or_future_ack():
    data=snapshot();data['receipts'][2]['time']=43600.;data['jobs'][0]['completed_at']=43600.
    label=evidence.realized_return(evidence.snapshot_index(data,expected_population=3),start=43200.)
    assert label['target_value']==-500.
    with pytest.raises(ValueError,match='registered_label_time_cutoffs'):
        evidence.realized_return({'clock':60000.},start=57301.)
    contract=evidence.training_contract('whole_day_1')
    assert contract['seeds']==[17,29,43] and contract['independent_development_or_test'] is False
    assert contract['earliest_model_use_sim_time']==57600.


def conditional_case():
    return json.loads((Path(__file__).parent/'fixtures/g31_airport_conditional_release_seq32.json').read_bytes())['callback_projection']


def test_actual_seq32_can_request_known_future_local_release_but_is_not_execution():
    row=conditional_case();request=row['decision']['intents'][0];tray=row['observation']['trays'][0]
    assert tray['node']==72 and request['source']==73
    result=evidence.pre_submit_source(row,request,tray)
    assert result['status']=='public_conditional_release_not_free_inventory'
    assert result['forecast_used_as_execution_authority'] is False


@pytest.mark.parametrize('mutation',['source','future_job','unreleased','duplicate_supply','dependency','unknown_job','source_owner','nonfinite_estimate'])
def test_conditional_release_does_not_admit_forged_or_unknown_source(mutation):
    row=conditional_case();request=row['decision']['intents'][0];tray=row['observation']['trays'][0]
    if mutation=='source':request['source']=72
    elif mutation=='future_job':row['observation']['jobs'][0]['arrival']=row['now']+1
    elif mutation=='unreleased':row['observation']['jobs'][0]['status']='unreleased'
    elif mutation=='duplicate_supply':row['decision']['supplies'].append(deepcopy(row['decision']['supplies'][0]))
    elif mutation=='dependency':request['forecast_dependency']='guessed'
    elif mutation=='unknown_job':row['observation']['jobs']=[]
    elif mutation=='source_owner':row['observation']['node_contracts'][0]['resource_owner']='peer'
    else:row['decision']['supplies'][0]['estimate']=float('nan')
    with pytest.raises(ValueError):evidence.pre_submit_source(row,request,tray)
