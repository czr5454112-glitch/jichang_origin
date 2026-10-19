"""Training input/normalization gates only. No fitting or model execution."""
from copy import deepcopy
import json
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_training as training


def row():
    proposal={'request_id':'proposal','owner_id':'A','source':73,'destination':49,'tray_id':'T','expected_version':0,
        'issued_at':43320.,'message_delay':2.,'earliest_departure':43320.}
    callback={'schema':'g31.foundation.airport_policy_observation.v2','sequence':32,'owner_id':'A','now':43320.,
        'observation':{'owner_id':'A','now':43320.,'unknown':None,'count':17},'decision':{'intents':[proposal]}}
    request={key:value for key,value in proposal.items()if key!='expected_version'};request['request_id']='actual'
    return {'schema':'g31.foundation.airport_behavior_readiness.v1','split':'train','parent_group':'whole_trajectory',
        'native_execution_authority':False,'callback_record':callback,
        'submission':{'callback_sha256':training.digest(callback),'callback_sequence':32,'at':43320.,'owner':'A',
            'pre_submit_source_evidence':{'supports_training':True},'actual_request':request},
        'execution':{'status':'actual_execution_and_delivered_ack_bound','counterfactual_protection_certified':False,
            'first_edge':{'from':73,'tray_id':'T','time':43330.,'event':'EDGE_ENTER','transport_leg_id':'actual:empty_return:3'},
            'native_leg':{'runtime_id':3,'kind':'empty_return','job':-1,'transport_leg_id':'actual:empty_return:3'},
            'positive_ack':{'request_id':'actual','status':'dispatching','observed_at':43322.,'delivered_at':43322.2}},
        'behavior_label':{'label_start':43320.,'label_end':43620.,'horizon_seconds':300.,'discount':1.,
            'physical_population':28506,'counterfactual_label':False,'future_completion_imputed':False,'target_value':-200.},
        'target_value':-200.}


def test_v2_normalization_changes_only_schema_and_preserves_original_hash():
    original=row()['callback_record'];before=deepcopy(original)
    adapted,report=training.normalize_callback(original)
    assert original==before and report['original_record_sha256']==training.digest(original)
    assert adapted['schema']=='g31.foundation.airport_policy_observation.v1'
    assert adapted['observation']['unknown'] is None and adapted['observation']['count']==17
    assert report['only_changed_field']=='schema' and report['raw_modified'] is False
    adapted['observation']['count']=0
    assert original['observation']['count']==17


def test_realized_behavior_row_is_training_only_not_counterfactual():
    data=row();callback,request=training.validate_row(data,{'parent_group':'whole_trajectory'})
    assert callback is data['callback_record'] and request['request_id']=='actual'
    assert training.SEEDS==(17,29,43) and training.EPOCHS==100


@pytest.mark.parametrize('mutation',['split','parent','hash','time','cutoff','population','unknown','no_execution','counterfactual','payload','effect_source'])
def test_training_rejects_unbound_or_out_of_contract_rows(mutation):
    data=row()
    if mutation=='split':data['split']='development'
    elif mutation=='parent':data['parent_group']='another_flight'
    elif mutation=='hash':data['callback_record']['observation']['count']=18
    elif mutation=='time':data['submission']['at']+=1
    elif mutation=='cutoff':data['behavior_label']['label_end']=57601.
    elif mutation=='population':data['behavior_label']['physical_population']=28505
    elif mutation=='unknown':data['target_value']=None
    elif mutation=='no_execution':data['execution']['status']='no_physical_execution_in_label_window'
    elif mutation=='counterfactual':data['behavior_label']['counterfactual_label']=True
    elif mutation=='payload':data['submission']['actual_request']['destination']=95
    else:data['execution']['first_edge']['from']=72
    with pytest.raises(ValueError):training.validate_row(data,{'parent_group':'whole_trajectory'})


@pytest.mark.parametrize('mutation',['ack_missing','leg_missing','ack_request','ack_future','ack_negative','ack_reverse',
    'leg_request','leg_edge','leg_kind','edge_pre_submit','edge_pre_delivery','edge_future','not_edge','numeric_bool'])
def test_status_string_cannot_replace_actual_ack_and_physical_leg(mutation):
    data=row();execution=data['execution']
    if mutation=='ack_missing':del execution['positive_ack']
    elif mutation=='leg_missing':del execution['native_leg']
    elif mutation=='ack_request':execution['positive_ack']['request_id']='different'
    elif mutation=='ack_future':execution['positive_ack']['delivered_at']=43621.
    elif mutation=='ack_negative':execution['positive_ack']['status']='rejected'
    elif mutation=='ack_reverse':execution['positive_ack']['delivered_at']=43321.
    elif mutation=='leg_request':execution['native_leg']['transport_leg_id']='different:empty_return:3'
    elif mutation=='leg_edge':execution['first_edge']['transport_leg_id']='actual:empty_return:4'
    elif mutation=='leg_kind':execution['native_leg']['kind']='loaded'
    elif mutation=='edge_pre_submit':execution['first_edge']['time']=43319.
    elif mutation=='edge_pre_delivery':execution['first_edge']['time']=43321.
    elif mutation=='edge_future':execution['first_edge']['time']=43621.
    elif mutation=='not_edge':execution['first_edge']['event']='EXPORT_GRANTED'
    else:execution['positive_ack']['observed_at']=True
    with pytest.raises(ValueError):training.validate_row(data,{'parent_group':'whole_trajectory'})


def observation():
    return {'information_variant':'static_plan','flight_context_sha256':'legal_context',
        'demand_forecast':{'new_demand_mean_by_region':{'known':[1.,2.],'unknown':[None,None]},
            'missing_mask_by_region':{'known':False,'unknown':True},'context_sha256':'legal_context',
            'uncertainty_by_region':{'known':[1.,2.],'unknown':None},'window_summaries_by_region':{'known':3.}}}


def test_diagnostic_masks_values_without_false_no_plan_or_unknown_zero():
    original=observation();before=deepcopy(original);variants=training.diagnostic_variants(original)
    assert original==before
    for changed in variants.values():
        assert changed['information_variant']=='static_plan' and changed['flight_context_sha256']=='legal_context'
        assert changed['demand_forecast']['new_demand_mean_by_region']['unknown']==[None,None]
        assert changed['demand_forecast']['missing_mask_by_region']['unknown'] is True
    masked=variants['forecast_values_masked']['demand_forecast'];zero=variants['zero_new_demand']['demand_forecast']
    assert masked['new_demand_mean_by_region']['known']==[None,None] and masked['missing_mask_by_region']['known'] is True
    assert zero['new_demand_mean_by_region']['known']==[0.,0.] and zero['missing_mask_by_region']['known'] is False
    assert masked['window_summaries_by_region']==zero['window_summaries_by_region']=={}


def test_diagnostic_pair_uses_real_distinct_semantics_not_ids():
    callback=row()['callback_record'];wrapped=observation()
    candidates=[{'semantic':{'destination_region':'one'},'source_proposal_sha256':'a'},
        {'semantic':{'destination_region':'one'},'source_proposal_sha256':'b'}]
    assert training.diagnostic_pair(callback,wrapped,candidates) is None
    candidates.append({'semantic':{'destination_region':'two'},'source_proposal_sha256':'c'})
    pair=training.diagnostic_pair(callback,wrapped,candidates)
    assert pair['proposal_sha256']==['a','c'] and pair['chosen_index']==0


def test_diagnostic_reports_absent_nonadditivity_honestly():
    pair={'observation':observation(),'callback_sequence':1,'actions':[{},{}]}
    def additive(model,observations,actions):
        values=observations[0]['demand_forecast']['new_demand_mean_by_region']['known']
        baseline=sum(v or 0 for v in values)
        return [baseline+2.,baseline+1.]
    result=training.score_diagnostic({},pair,additive)
    assert result['numerical_nonadditivity_at_1e_minus_8'] is False
    assert result['physical_control_benefit_established'] is False and result['no_plan_product_evaluated'] is False


def archive_fixture(tmp_path):
    readiness=tmp_path/'actual_readiness';readiness.mkdir()
    source=str((tmp_path/'no_longer_current_source.py').resolve())
    attempt=tmp_path/'attempt';(attempt/'source').mkdir(parents=True)
    archived=attempt/'source/0000.py';archived.write_text('historical_exact_readiness_source')
    rplan={'source_sha256':{source:training.sha(archived)}}
    training.write(readiness/'plan.json',rplan)
    assessment={'status':'completed_behavior_readiness','plan':training.ref(readiness/'plan.json'),
        'eligible_rows':{'path':'actual_eligible_rows','sha256':'exact_executed_rows'}}
    training.write(readiness/'receipt.json',assessment)
    registration={'task_id':readiness.name,'native_branches':0,
        'module':'scripts.experiments.g31_ics_circulation.foundation_airport_behavior_readiness',
        'args':['--run','--output',str(readiness.resolve())],
        'assessment':{'path':str(readiness.resolve()/'receipt.json'),'allowed_statuses':['completed_behavior_readiness']},
        'source_pins':{source:training.sha(archived),str(readiness.resolve()/'plan.json'):training.sha(readiness/'plan.json')}}
    training.write(attempt/'registration.json',registration)
    training.write(attempt/'receipt.json',{'status':'completed','process':{'status':'exited','exitcode':0},'source_changed':[],
        'assessment':assessment})
    return readiness,rplan,attempt,archived,registration


def test_actual_readiness_sources_use_executed_archive_not_current_workspace(tmp_path):
    readiness,rplan,attempt,archived,_=archive_fixture(tmp_path)
    sources,inputs=training.readiness_archives(attempt/'registration.json',readiness,rplan)
    assert list(sources.values())==[training.ref(archived)]
    assert inputs['readiness_outer_receipt']==training.ref(attempt/'receipt.json')


@pytest.mark.parametrize('mutation',['archive_bytes','missing_source','plan_pin','assessment_path','changed_source','nonzero_exit',
    'missing_assessment','wrong_assessment'])
def test_readiness_provenance_requires_closed_exact_executed_sources(tmp_path,mutation):
    readiness,rplan,attempt,archived,registration=archive_fixture(tmp_path)
    if mutation=='archive_bytes':archived.write_text('different_source')
    elif mutation in ('missing_source','plan_pin','assessment_path'):
        if mutation=='missing_source':del registration['source_pins'][next(iter(rplan['source_sha256']))]
        elif mutation=='plan_pin':registration['source_pins'][str(readiness.resolve()/'plan.json')]='wrong'
        else:registration['assessment']['path']='different_result.json'
        (attempt/'registration.json').write_text(json.dumps(registration))
    else:
        receipt=training.read(attempt/'receipt.json')
        if mutation=='changed_source':receipt['source_changed']=['changed.py']
        elif mutation=='nonzero_exit':receipt['process']['exitcode']=1
        elif mutation=='missing_assessment':del receipt['assessment']
        else:receipt['assessment']['eligible_rows']['sha256']='posthoc_altered_rows'
        (attempt/'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):training.readiness_archives(attempt/'registration.json',readiness,rplan)
