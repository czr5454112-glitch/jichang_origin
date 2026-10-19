"""Pure replay-source and completed-validation gate checks; no actual replay."""
import ast
import copy
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_learning_audit_arrays as new


def fixtures(monkeypatch):
    monkeypatch.setattr(new, 'sha', lambda path:'frozen-source')
    inputs = {key:{'path':key,'sha256':key} for key in ('checkpoint','public_plan','trace','mapping','array_validation_plan')}
    validation = {'schema':'g31.flight_arrays_exact_saved_parity.v1', 'expected_saved_forecasts':402,
        'B2_sequences':[0,473,945], 'native_branches':0,'fit_calls':0,'cross_call_cache':False,
        'inputs':copy.deepcopy(inputs), 'sources':{str(Path(module.__file__).resolve()):'frozen-source'
            for module in (new.arrays,new.frozen_forecaster,new.original)}}
    receipt = {'status':new.PARITY_STATUS,'completed_saved_forecasts':402,'saved_parity_by_method':copy.deepcopy(new.METHOD_COUNTS),
        'AST_exact_except_array_materialization':True,'source_exit_pins_passed':True,
        'native_branches':0,'fit_calls':0,'new_training_labels':0,'no_training_or_test_selection':True,
        'cross_call_cache':False,'native_execution_authority':False,'plan':inputs['array_validation_plan'],
        'B2_rows':[{'sequence':seq,'exact_forecast_and_features_bytes':True} for seq in (0,473,945)]}
    return receipt,validation,inputs


def test_entire_replay_ast_exact_except_predictor_import_and_original_validator():
    def run_ast(module):
        return next(node for node in ast.parse(Path(module.__file__).read_text()).body
            if isinstance(node,ast.FunctionDef) and node.name=='run')
    class Normalize(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            for name in node.names:
                if name.name=='foundation_flight_forecaster_arrays':name.name='foundation_flight_forecaster'
            return node
        def visit_Name(self,node):
            if node.id=='frozen_forecaster':node.id='forecaster'
            return node
    assert ast.dump(run_ast(new.original))==ast.dump(Normalize().visit(run_ast(new)))
    assert new.project is new.original.project


def test_complete_actual_validation_is_required_and_accepted(monkeypatch):
    receipt,validation,inputs=fixtures(monkeypatch)
    before=copy.deepcopy((receipt,validation,inputs))
    new.validate_parity(receipt,validation,inputs)
    assert (receipt,validation,inputs)==before


@pytest.mark.parametrize('field,value',[
    ('status','failed_exact_saved_forecast_and_B2_parity'),('completed_saved_forecasts',401),
    ('AST_exact_except_array_materialization',False),('source_exit_pins_passed',False),
    ('native_branches',1),('fit_calls',1),('new_training_labels',1),
    ('no_training_or_test_selection',False),('cross_call_cache',True),('native_execution_authority',True)])
def test_incomplete_or_wrong_scope_validation_is_refused(monkeypatch,field,value):
    receipt,validation,inputs=fixtures(monkeypatch);receipt[field]=value
    with pytest.raises(ValueError,match='completed_exact_array_validation'):
        new.validate_parity(receipt,validation,inputs)


@pytest.mark.parametrize('failure',['missing_method','missing_row','wrong_sequence','row_failed','wrong_plan',
    'checkpoint','public_plan','trace','mapping','runtime_changed'])
def test_partial_parity_or_different_bound_input_is_refused(monkeypatch,failure):
    receipt,validation,inputs=fixtures(monkeypatch)
    if failure=='missing_method':receipt['saved_parity_by_method'].pop('flight_synthetic_observed_counts')
    elif failure=='missing_row':receipt['B2_rows'].pop()
    elif failure=='wrong_sequence':receipt['B2_rows'][1]['sequence']=472
    elif failure=='row_failed':receipt['B2_rows'][1]['exact_forecast_and_features_bytes']=False
    elif failure=='wrong_plan':receipt['plan']={'path':'other','sha256':'other'}
    elif failure=='runtime_changed':validation['sources'][str(Path(new.arrays.__file__).resolve())]='different'
    else:validation['inputs'][failure]['sha256']='different'
    with pytest.raises(ValueError):new.validate_parity(receipt,validation,inputs)


@pytest.mark.parametrize('field,value',[('expected_saved_forecasts',401),('B2_sequences',[0,1,2]),
    ('native_branches',1),('fit_calls',1),('cross_call_cache',True)])
def test_validation_contract_must_match_closed_receipt(monkeypatch,field,value):
    receipt,validation,inputs=fixtures(monkeypatch);validation[field]=value
    with pytest.raises(ValueError,match='exact_validation_scope'):new.validate_parity(receipt,validation,inputs)


@pytest.mark.parametrize('field,value',[('expected_record_count',945),('soft_wall_seconds',241),
    ('native_branches',1),('fit_calls',1),('outcome_labels_created',1),('observed_counts',{}),('episode_end',60000.)])
def test_original_population_budget_and_public_only_rules_still_refuse(field,value):
    plan={'schema':new.original.SCHEMA,'native_branches':0,'fit_calls':0,'outcome_labels_created':0,
        'expected_record_count':946,'soft_wall_seconds':240,'observed_counts':None,'episode_end':59400.,
        'source_sha256':{},'historical_collection_sources':{},'inputs':{}}
    plan[field]=value
    with pytest.raises(ValueError,match='fixed_public_only_audit'):new.original.validate_plan(plan)
