"""Synthetic whole-component wiring, not real model or performance evidence."""
from __future__ import annotations
import copy
import gzip
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import measure_initial_scoped_public_inputs_six as m


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding='utf8')


@pytest.fixture
def fixture(tmp_path):
    output=tmp_path/'run'; output.mkdir()
    prediction={'status':'conditional_model_prediction','completion':{'j':1.0},'projected_collections':[]}
    encoded=m.frozen.base.bytes_of(prediction); rows={}; targets=set()
    for key in m.ORDER:
        public=tmp_path/'inputs'/f'{key}.json'
        write(public,{'action':{'kind':'synthetic'},'initial_owners':{'A':{},'B':{}}})
        references={}
        for label in ('lazy','v2'):
            target=tmp_path/label/f'{key}.gz'; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.compress(encoded,mtime=0)); references[label]=m.ref(target)
            if label=='lazy':targets.add(target)
        rows[key]={'input':m.ref(public),'action':{'kind':'synthetic'},
            'comparison_only_saved_prediction':references['lazy'],
            'comparison_only_v2_prediction':references['v2'],'expected_collections':[]}
    plan={'declaration':m.frozen.declaration(),'maximum_model_calls':24,
        'hard_application_seconds':120.,'rows':rows}
    write(output/'plan.json',plan)
    return SimpleNamespace(output=output,plan=plan,prediction=prediction,targets=targets)


def fake_worker(fixture, *, fail_at=None, gc_enabled=True, fail_final_pins=False):
    calls=[]; reads=[]; pins=[]; clock=SimpleNamespace(value=100)
    def stamp():clock.value+=1;return clock.value
    def predict(arm):
        def call(public,action):
            assert set(public)=={'initial_owners','action'} and action is public['action']
            calls.append({'arm':arm,'public':public,'at':stamp()})
            if len(calls)-1==fail_at:raise ValueError('synthetic component failure')
            return copy.deepcopy(fixture.prediction)
        return call
    class TargetRead:
        def __init__(self,path):self.path=path
        def read_bytes(self):
            ledger=m.read(fixture.output/'ledger.json')
            pending=[item for item in ledger if item['status']=='returned_audit_pending']
            if pending:assert Path(pending[-1]['raw']['path']).exists()
            reads.append((str(self.path),len(calls)))
            return self.path.read_bytes()
    def path(value):
        value=Path(value);return TargetRead(value) if value in fixture.targets else value
    def pin(*args):
        pins.append(None)
        if fail_final_pins and len(pins)==3:return {'changed':True}
        return {}
    def forbidden(*args):raise AssertionError('outside-sample build_initial')
    original=m.worker_function(); fakebase=SimpleNamespace(**vars(m.frozen.base))
    fakebase.build_initial=forbidden;fakebase.loaded_sources=lambda *args:{}
    ns={**original.__globals__,'base':fakebase,'pins_now':pin,
        'lazy':SimpleNamespace(predict=predict('A')),'candidate':SimpleNamespace(predict=predict('B')),
        'gc':SimpleNamespace(isenabled=lambda:gc_enabled),'Path':path,
        'time':SimpleNamespace(perf_counter=lambda:stamp()/1e6,perf_counter_ns=stamp)}
    return FunctionType(original.__code__,ns,original.__name__,original.__defaults__,original.__closure__),calls,reads,pins


def execute(fixture,**kwargs):
    function,calls,reads,pins=fake_worker(fixture,**kwargs)
    function(fixture.output,m.sha(fixture.output/'plan.json'))
    return m.read(fixture.output/'report.json'),m.read(fixture.output/'ledger.json'),calls,reads,pins


def test_inverse_ast_complete_namespace_and_exact_component_bindings():
    proof=m.source_proof(); function=m.worker_function()
    assert proof['inverse_AST_only_outside_context_to_public_status_label_final_audit_and_receipt_counts']
    assert function.__globals__['lazy'].predict is m._reference
    assert function.__globals__['candidate'].predict is m._candidate
    assert function.__globals__['base'] is m.frozen.base
    assert function.__defaults__ is m.frozen.worker.__defaults__
    assert function.__closure__ is m.frozen.worker.__closure__


def test_original_function_and_module_globals_untouched():
    before=dict(m.frozen.worker.__globals__); code=m.frozen.worker.__code__
    m.worker_function();m.source_proof()
    assert m.frozen.worker.__code__ is code
    assert set(before)==set(m.frozen.worker.__globals__)
    assert all(m.frozen.worker.__globals__[k] is v for k,v in before.items())


def test_full_fake24_order_denominator_output_and_setup_scope(fixture):
    report,ledger,calls,reads,pins=execute(fixture)
    assert report['exact']==24 and report['unknown']==0 and len(ledger)==24
    assert ''.join(c['arm'] for c in calls)=='ABBA'*6
    assert report['summary_ms']['A']['count']==report['summary_ms']['B']['count']==12
    assert len(reads)==48 and len(pins)==3
    assert all(row['status']=='public_input_loaded_only' for row in report['setup'])
    assert all(row['status']=='exact_v2_full_output' for row in report['v2_full_output_checks'])
    assert 'v1_full_output_checks' not in report
    assert report['comparison_with_previous_predict_only_ABBA_valid'] is False
    assert report['per_sample_cycle_cleanup_certified'] is False
    assert report['complete_request100ms_certified'] is False
    assert all(m.ref(row['raw']['path'])==row['raw'] for row in ledger)


def test_component_callback_is_inside_each_sample_clock(fixture):
    report,ledger,calls,*_=execute(fixture)
    assert all(row['started_ns']<call['at']<row['finished_ns'] for row,call in zip(ledger,calls))
    assert report['both_initial_context_constructions_and_fact_comparisons_inside_each_sample']


def test_A_wrapper_calls_complete_reference_with_same_public():
    public={'action':object()};seen=[];answer=object()
    callback=FunctionType(m._reference.__code__,{**m._reference.__globals__,
        'component':SimpleNamespace(reference=lambda p:seen.append(p) or answer)})
    assert callback(public,public['action']) is answer and seen[0] is public


def test_B_wrapper_calls_complete_candidate_with_same_public():
    public={'action':object()};seen=[];answer=object()
    callback=FunctionType(m._candidate.__code__,{**m._candidate.__globals__,
        'component':SimpleNamespace(predict=lambda p:seen.append(p) or answer)})
    assert callback(public,public['action']) is answer and seen[0] is public


@pytest.mark.parametrize('function',[m._reference,m._candidate])
def test_equal_but_other_action_object_rejected_before_component(function):
    with pytest.raises(ValueError,match='same_action_object'):function({'action':{}},{})


@pytest.mark.parametrize('failure_index',[0,1,12,23])
def test_initial_or_prediction_exception_keeps_all24_and_full_unknown(fixture,failure_index):
    report,ledger,calls,*_=execute(fixture,fail_at=failure_index)
    assert len(calls)==len(ledger)==24 and report['exact']==23 and report['unknown']==1
    assert ledger[failure_index]['status']=='unknown_error' and 'elapsed_ns' in ledger[failure_index]
    assert report['status']=='unknowns_preserved' and report['summary_ms']=={}


@pytest.mark.parametrize('change',['type','signed_zero','key_order','extra_field','list_order'])
def test_v2_comparator_full_fields_and_receipt_counts(fixture,change):
    value=copy.deepcopy(fixture.prediction)
    if change=='type':value['completion']['j']=1
    elif change=='signed_zero':value['completion']['j']=-0.0
    elif change=='key_order':value=dict(reversed(list(value.items())))
    elif change=='extra_field':value['extra']=None
    else:value['projected_collections']=[2,1]
    row=fixture.plan['rows'][m.ORDER[0]];target=Path(row['comparison_only_v2_prediction']['path'])
    target.write_bytes(gzip.compress(m.frozen.base.bytes_of(value),mtime=0))
    row['comparison_only_v2_prediction']=m.ref(target);write(fixture.output/'plan.json',fixture.plan)
    report,ledger,calls,*_=execute(fixture);receipt=m.read(fixture.output/'receipt.json')
    assert len(calls)==24 and report['exact']==receipt['exact']==20
    assert report['unknown']==receipt['unknown']==4 and report['summary_ms']=={}
    assert all(row['status']=='unknown_saved_v2_error' for row in report['v2_full_output_checks'][:4])
    assert all('raw' in row for row in ledger)


@pytest.mark.parametrize('mutation',['remove','reverse','arm'])
def test_final_extra_audit_rejects_denominator_tamper(fixture,mutation):
    ledger=[{**d,'status':'unknown_unexecuted'} for d in m.frozen.declaration()]
    if mutation=='remove':ledger.pop()
    elif mutation=='reverse':ledger.reverse()
    else:ledger[0]['arm']='B'
    with pytest.raises(ValueError,match='full_ledger'):m._extend_report(fixture.output,fixture.plan,ledger,{})


def test_disabled_gc_rejects_before_callback(fixture):
    function,calls,*_=fake_worker(fixture,gc_enabled=False)
    with pytest.raises(ValueError,match='fixed_scope'):function(fixture.output,m.sha(fixture.output/'plan.json'))
    assert not calls


def test_changed_plan_rejects_before_callback(fixture):
    function,calls,*_=fake_worker(fixture)
    with pytest.raises(ValueError,match='plan'):function(fixture.output,'0'*64)
    assert not calls


def test_failed_export_retains24_unknown_without_fake_raw(fixture):
    function,calls,*_=fake_worker(fixture)
    class FailedGzip:
        @staticmethod
        def compress(*args,**kwargs):raise OSError('synthetic export failure')
    FunctionType(function.__code__,{**function.__globals__,'gzip':FailedGzip})(fixture.output,m.sha(fixture.output/'plan.json'))
    report=m.read(fixture.output/'report.json')
    assert len(calls)==24 and report['unknown']==24 and report['exact']==0
    assert all('raw' not in row for row in m.read(fixture.output/'ledger.json'))


def test_input_load_error_retains_four_unexecuted_components(fixture):
    Path(fixture.plan['rows'][m.ORDER[0]]['input']['path']).write_text('{broken',encoding='utf8')
    report,ledger,calls,*_=execute(fixture)
    assert len(calls)==20 and report['unknown']==4
    assert all(row['status']=='unknown_setup_error' for row in ledger[:4])


def test_action_precheck_failure_remains_outside_sample_but_in_whole(fixture):
    path=Path(fixture.plan['rows'][m.ORDER[0]]['input']['path']);value=m.read(path)
    value['action']['kind']='different';write(path,value)
    report,ledger,calls,*_=execute(fixture)
    assert len(calls)==20 and report['unknown']==4
    assert all(row['status']=='unknown_setup_error' for row in ledger[:4])


def test_extra_audit_is_followed_by_source_exit_pin_check(fixture):
    function,calls,_,pins=fake_worker(fixture,fail_final_pins=True)
    with pytest.raises(ValueError,match='post_extra_audit_pins'):
        function(fixture.output,m.sha(fixture.output/'plan.json'))
    assert len(calls)==24 and len(pins)==3 and not (fixture.output/'receipt.json').exists()


def test_all_unexecuted_rows_stay_unknown(fixture):
    ledger=[{**d,'status':'unknown_unexecuted'} for d in m.frozen.declaration()]
    report=m._extend_report(fixture.output,fixture.plan,ledger,{'exact':24,'unknown':0})
    assert report['exact']==0 and report['unknown']==24 and report['summary_ms']=={}


@pytest.mark.parametrize('elapsed',[-1,120.])
def test_original_owned_budget_rejects_invalid_or_exhausted(elapsed):
    with pytest.raises((ValueError,TimeoutError)):m.frozen.base.remaining(elapsed)


def test_all_loading_export_extraaudit_and_cleanup_share_original120():
    assert m.LIMIT==m.frozen.LIMIT==m.frozen.base.LIMIT==120.
    assert m.frozen.base.remaining(0)==119.
