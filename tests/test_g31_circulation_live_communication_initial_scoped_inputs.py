"""Fake96 scope/early-save wiring only, no actual model or raw/native input."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from scripts.experiments.g31_ics_circulation import validate_live_communication_initial_scoped_inputs as d


def test_inline_inverse_ast_and_original_future_guard_boundary():
    proof=d.source_proof();inner=d.bind_worker(object())
    assert proof['inline_inverse_AST'] and proof['same_scope_initial_and_predict']
    assert inner.__globals__['future_context'] is d.original.future_context
    assert inner.__globals__['context'] is d.original.context
    assert d.original.future_context.__globals__['context'] is d.original.context


def test_no_original_function_or_global_mutation():
    before=dict(d.original.worker.__globals__);old=d.original.worker.__code__
    d.source_proof();d.worker_function()
    assert d.original.worker.__code__ is old and set(before)==set(d.original.worker.__globals__)
    assert all(d.original.worker.__globals__[k] is v for k,v in before.items())


def test_outer_original_single_saver_and_all_check_functions_retained():
    function=d.worker_function();allowed={'candidate','run_original','SCHEMA','source_proof','pure_gate'}
    assert function.__code__ is d.frozen.worker.__code__
    assert set(function.__globals__)==set(d.frozen.worker.__globals__)
    assert all(function.__globals__[k] is v for k,v in d.frozen.worker.__globals__.items() if k not in allowed)
    for name in ('SaveBeforeReturn','early_inventory','mapping_allowed','exact_predictions','loaded_sources'):
        assert function.__globals__[name] is getattr(d.frozen,name)


def test_cleanup_primary_exception_and_original_scope_unchanged():
    assert d.run_original.__code__ is d.frozen.run_original.__code__
    assert d.run_original.__closure__ is d.frozen.run_original.__closure__
    assert d.run_original.__defaults__ is d.frozen.run_original.__defaults__
    assert all(d.run_original.__globals__[k] is v for k,v in d.frozen.run_original.__globals__.items() if k!='bind_worker')


def test_source_proof_rejects_changed_scope_before_constructing(monkeypatch):
    monkeypatch.setattr(d.scoped,'PublicInputScope',lambda:pytest.fail('must not instantiate'))
    with pytest.raises(ValueError,match='identity'):d.source_proof()


@pytest.mark.parametrize('bad',[None,({},{}),SimpleNamespace(scope=None,supplied=None)])
def test_untrusted_carriers_never_predict(bad):
    with pytest.raises(ValueError,match='private_scope_input'):d._predict(bad,{})


def test_wrong_validated_context_type_rejected():
    class S:pass
    class Scope:
        context=SimpleNamespace(SuppliedContext=S)
        def predict(self,*args):pytest.fail('no predictor')
    function=d.private(d._predict,{'_SCOPE':Scope})
    with pytest.raises(ValueError,match='validated_initial_type'):function(d._ScopeInput(Scope(),{}),{})


def test_carrier_passes_exact_context_action_to_same_scope_once():
    calls=[]
    class S:pass
    class Scope:
        context=SimpleNamespace(SuppliedContext=S)
        def predict(self,c,a):calls.append((self,c,a));return answer
    scope=Scope();supplied=S();action={};answer={}
    function=d.private(d._predict,{'_SCOPE':Scope})
    assert function(d._ScopeInput(scope,supplied),action) is answer
    assert calls==[(scope,supplied,action)] and calls[0][2] is action


@pytest.fixture
def synthetic(tmp_path):
    output=tmp_path/'run';output.mkdir();inputs=tmp_path/'inputs';inputs.mkdir()
    value={'status':'conditional_prediction',
        'completion':{k:float(i+1) for i,k in enumerate(('loaded','receiver','reuse1','reuse2','blocker'))},
        'projected_collections':[]}
    old=tmp_path/'target.gz';old.write_bytes(gzip.compress(json.dumps(value,allow_nan=False).encode(),mtime=0))
    rows={}
    for i,key in enumerate(d.ORDER):
        attempts={o:[{'at':0.1,'information':{'native_delivery_verified':True}}] for o in ('A','B')}
        if i<34:attempts['B'].append({'at':0.2,'information':{'native_delivery_verified':False}})
        raw={'index':i,'summary':{'completion':value['completion']},'collection_attempts':attempts}
        path=inputs/f'{i:03d}.gz';path.write_bytes(gzip.compress(json.dumps(raw).encode(),mtime=0))
        rows[key]={'action':{'ordinal':i%32},'actual_raw':d.ref(path),'status':'unknown_unexecuted'}
    plan={'schema':d.SCHEMA,'order':d.ORDER,'rows':rows,'hard_timeout_seconds':360.,'maximum_model_evaluations':96,
        'source_proof':d.source_proof(),'environment':{'python':sys.executable,'sha256':d.sha(sys.executable)},
        'source_sha256':{},'fixed_evidence_sha256':{},'source_archive':{},
        'old96_predictions':{key:d.ref(old) for key in d.ORDER}}
    d.write(output/'plan.json',plan);d.write(output/'rows.json',copy.deepcopy(rows))
    return SimpleNamespace(output=output,plan=plan,value=value,scopes=[],future=[],guards=[],models=[])


def fake_inner(f, *, initial_failure=None, model_failure=None, allocation_failure=None):
    class Supplied:
        def __init__(self,owner,index):self.owner=owner;self.index=index
    class Scope:
        def __init__(self):
            self.index=len(f.scopes);f.scopes.append(self)
            if self.index==allocation_failure:raise MemoryError('synthetic scope allocation')
            self.context=SimpleNamespace(SuppliedContext=Supplied,initial_context=self.initial,
                initial_projection_bundle=self.bundle,encoded=lambda value:json.dumps(value,allow_nan=False).encode())
        def initial(self,owner,index):
            f.guards.append((self.index,owner,index))
            if initial_failure==(self.index,owner):return None
            return Supplied(owner,index)
        def bundle(self,supplied):
            facts={'jobs':[1],'trays':[2],'contract':{'v':1},'now':0.1}
            if initial_failure==(self.index,'facts') and supplied.owner=='B':facts['now']=0.2
            return facts
        def predict(self,supplied,action):
            assert supplied.index==self.index and supplied.owner=='A'
            assert action=={'ordinal':self.index%32}
            f.models.append(self.index)
            if self.index==model_failure:raise RuntimeError('synthetic prediction failure')
            return copy.deepcopy(f.value)
    predict=d.private(d._predict,{'_SCOPE':Scope})
    saver=d.SaveBeforeReturn(f.output,predict)
    def future(raw,owner,attempt):
        # The old worker's first future-data guard occurs only AFTER full save.
        assert saver.records[-1]['status']=='complete_prediction_saved_before_return'
        assert Path(saver.records[-1]['prediction']['path']).exists()
        f.future.append((raw['index'],owner,attempt['at']))
        return Supplied(owner,raw['index']) if attempt['information']['native_delivery_verified'] else None
    inner=d.bind_worker(saver)
    facade=SimpleNamespace(physics=SimpleNamespace(previous=SimpleNamespace(actions=lambda:[{'ordinal':i} for i in range(32)])),predict=saver)
    function=d.private(inner,{'_new_scope':Scope,'context':SimpleNamespace(SuppliedContext=Supplied,encoded=lambda v:json.dumps(v).encode()),
        'model':facade,'pure_gate':lambda:None,'public_initial':lambda raw,owner:{'owner':owner,'index':raw['index']},
        'future_context':future,'projected_collection_rows':lambda value:[],'actual_collection_rows':lambda raw:[]})
    runner=d.private(d.frozen.run_original,{'bind_worker':lambda s:function})
    return saver,runner


def run_inner(f,**kwargs):
    saver,runner=fake_inner(f,**kwargs);runner(saver,f.output,d.sha(f.output/'plan.json'))
    return saver,d.read(f.output/'receipt.json'),d.read(f.output/'rows.json')


def test_actual_inner_code_fake96_one_scope_one_saver_and_226_checks(synthetic):
    saver,receipt,rows=run_inner(synthetic)
    assert len(synthetic.scopes)==len({id(v) for v in synthetic.scopes})==96
    assert synthetic.models==list(range(96)) and len(synthetic.guards)==192
    assert synthetic.guards==[(i,o,i) for i in range(96) for o in ('A','B')]
    assert len(saver.records)==96 and [r['ordinal'] for r in saver.records]==list(range(96))
    assert len(synthetic.future)==226 and receipt['actual_known_collection_data']==192
    assert receipt['status']=='exact_all96_conformance' and list(rows)==d.ORDER
    assert all('branch' not in r and 'key' not in r for r in saver.records)
    events=[d.frozen.strict.loads(line) for line in (synthetic.output/'early_prediction_events.jsonl').read_bytes().splitlines()]
    assert d.frozen.early_inventory(saver.records,events)==96
    assert d.frozen.mapping_allowed(receipt,rows,saver.records)


@pytest.mark.parametrize('owner',['A','B','facts'])
def test_initial_failure_preserves_guard_order_next_fresh_scope_and_all_rows(synthetic,owner):
    saver,receipt,rows=run_inner(synthetic,initial_failure=(2,owner))
    assert len(synthetic.scopes)==96 and len(rows)==96 and len(saver.records)==95
    assert synthetic.models==[i for i in range(96) if i!=2]
    assert (2,'A',2) in synthetic.guards and (2,'B',2) in synthetic.guards
    assert rows[d.ORDER[2]]['status']=='unknown_error' and receipt['status']!='exact_all96_conformance'
    assert not d.frozen.mapping_allowed(receipt,rows,saver.records)


@pytest.mark.parametrize('index',[0,95])
def test_prediction_failure_consumes_ordinal_but_never_fabricates_saved_output(synthetic,index):
    saver,receipt,rows=run_inner(synthetic,model_failure=index)
    assert len(saver.records)==96 and saver.records[index]['status']=='unknown_prediction_or_export_error'
    assert 'prediction' not in saver.records[index] and rows[d.ORDER[index]]['status']=='unknown_error'
    assert receipt['model_evaluations']==95 and not d.frozen.mapping_allowed(receipt,rows,saver.records)


def test_allocation_failure_keeps_full_unknown_denominator_without_reusing_prior_scope(synthetic):
    saver,receipt,rows=run_inner(synthetic,allocation_failure=3)
    assert len(synthetic.scopes)==96 and len(saver.records)==95
    assert rows[d.ORDER[3]]['status']=='unknown_error' and 'MemoryError' in rows[d.ORDER[3]]['error']
    assert (4,'A',4) in synthetic.guards and receipt['status']!='exact_all96_conformance'


def test_original_future_context_and_source_input_projection_are_not_privately_rebound():
    inner=d.bind_worker(None)
    for name in ('future_context','public_initial','actual_collection_rows','exact_completion'):
        assert inner.__globals__[name] is getattr(d.original,name)


def test_full_original_outer_verifies_fake96_outputs_and_mapping(synthetic):
    saver,runner=fake_inner(synthetic)
    original_scope=d.worker_function()
    # Outer still owns exactly this single saver. Fakes are explicitly confined
    # to this test; the production source proof rejects such global replacements.
    function=d.private(original_scope,{'pure_gate':lambda:None,'loaded_sources':lambda p:{},
        'SaveBeforeReturn':lambda output,predict:saver,'run_original':runner})
    function(synthetic.output,d.sha(synthetic.output/'plan.json'))
    final=d.read(synthetic.output/'final_receipt.json')
    assert final['full_output_exact']==96 and final['unknown_or_difference']==0
    assert final['early_invocations']==96 and final['early_ordinal_mapping_certified']
    assert final['actual_collection_data_checks']==226 and final['actual_known_collection_data']==192
    assert not final['complete_request_100ms_certified'] and not final['sample_cleanup_certified']


@pytest.mark.parametrize('status',['completed_unknowns_or_differences_preserved','unknown_worker_failure','invented'])
def test_final_status_gate_rejects_unknown_not_merely_exit0(tmp_path,monkeypatch,status):
    d.write(tmp_path/'final_receipt.json',{'status':status})
    monkeypatch.setattr(d,'worker_function',lambda:lambda *args:None)
    with pytest.raises(ValueError,match='initial_complete_gate'):d.worker(tmp_path,'x')
    assert d.read(tmp_path/'final_receipt.json')['status']==status


@pytest.mark.parametrize('change',[
    {'actual_collection_data_checks':225},{'actual_known_collection_data':191},
    {'model_evaluations':95},{'complete_actual_collection_conformance':False}])
def test_all_predictions_cannot_override_original_guard_missing_counts(synthetic,change):
    saver,receipt,rows=run_inner(synthetic);receipt.update(change)
    assert not d.frozen.mapping_allowed(receipt,rows,saver.records)


def test_budget_and_cleanup_are_original_shared360():
    assert d.LIMIT==d.previous.LIMIT==d.frozen.LIMIT==360.
    assert d.main.__code__ is d.previous.main.__code__
    assert d.main.__globals__['BOOT'] is d.BOOT and d.main.__globals__['worker'] is d.worker
    assert d.main.__globals__['__file__']==d.__file__


def test_disabled_gc_still_refuses_before_predictor(tmp_path,monkeypatch):
    monkeypatch.setattr(d.frozen.gc,'isenabled',lambda:False)
    saver=d.SaveBeforeReturn(tmp_path,lambda *a:pytest.fail('no predictor'))
    try:
        with pytest.raises(ValueError,match='GC_disabled'):saver(None,{})
    finally:saver.close()
    assert saver.records==[]


def test_successful_final_status_gate(tmp_path,monkeypatch):
    d.write(tmp_path/'final_receipt.json',{'status':'exact_all96_original_checks_and_full_outputs'})
    monkeypatch.setattr(d,'worker_function',lambda:lambda *args:None)
    d.worker(tmp_path,'x')
