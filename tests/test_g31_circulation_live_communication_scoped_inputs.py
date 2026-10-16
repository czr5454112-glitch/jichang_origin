"""Fake predictors only: early evidence, exact worker binding, all96 gates."""
import copy
import gc
import gzip
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import validate_live_communication_scoped_inputs as d


def value():
    return {'status':'conditional_prediction','completion':{'a':1.0,'b':-0.0},
        'projected_collections':[],'events':[['x',True,None,2,'😀']]}


def events(path):
    return [d.strict.loads(line) for line in (path/'early_prediction_events.jsonl').read_bytes().splitlines()]


def invoke(path,predict=lambda c,a:value()):
    saver=d.SaveBeforeReturn(path,predict)
    try:result=saver({'public':'only'},{'action':0})
    finally:saver.close()
    return saver,result


def test_saved_before_caller_target_and_owned_snapshot(tmp_path):
    prediction=value();action={'x':[1]};calls=[]
    def predict(context,received):
        assert context=={'public':'only'} and received is action
        calls.append('predict');return prediction
    saver=d.SaveBeforeReturn(tmp_path,predict)
    result=saver({'public':'only'},action)
    # This is the first point where the caller could read its target.
    calls.append('target_read')
    row=saver.records[0];saved=d.strict.loads(gzip.decompress(Path(row['prediction']['path']).read_bytes()))
    assert d.strict.exact(saved,prediction)
    assert row['prediction']==d.ref(row['prediction']['path'])
    assert row['full_json_sha256']==hashlib.sha256(json.dumps(prediction,allow_nan=False).encode()).hexdigest()
    assert events(tmp_path)[-1]['event']=='prediction_saved_before_return'
    result['events'][0][0]='caller mutation';action['x'].append(2)
    assert saved['events'][0][0]=='x' and row['input_action']=={'x':[1]}
    assert calls==['predict','target_read']
    saver.close();assert d.early_inventory(saver.records,events(tmp_path))==1


def test_only_original_two_arguments_no_target_or_key(tmp_path):
    calls=[]
    saver,_=invoke(tmp_path,lambda *args:(calls.append(args),value())[1])
    assert calls==[({'public':'only'},{'action':0})]
    assert 'key' not in saver.records[0] and 'branch' not in saver.records[0]
    assert tuple(inspect.signature(d.SaveBeforeReturn.__call__).parameters)==('self','context','action')


def test_later_target_failure_cannot_erase_saved_prediction(tmp_path):
    saver,result=invoke(tmp_path)
    with pytest.raises(RuntimeError,match='target'):
        assert result['status']=='conditional_prediction';raise RuntimeError('target read failed')
    assert d.ref(saver.records[0]['prediction']['path'])==saver.records[0]['prediction']
    assert d.early_inventory(saver.records,events(tmp_path))==1


def test_predictor_failure_keeps_ordinal_and_original_exception(tmp_path):
    error=RuntimeError('predictor failure')
    def predict(c,a):raise error
    saver=d.SaveBeforeReturn(tmp_path,predict)
    with pytest.raises(RuntimeError) as caught:saver({}, {})
    saver.close();assert caught.value is error
    assert saver.records[0]['status']=='unknown_prediction_or_export_error'
    assert list((tmp_path/'early_predictions').iterdir())==[]
    assert d.early_inventory(saver.records,events(tmp_path))==1


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),object(),'cycle'])
def test_nonjson_export_is_unknown_not_success(tmp_path,bad):
    if type(bad) is str and bad=='cycle':
        bad=[];bad.append(bad)
    saver=d.SaveBeforeReturn(tmp_path,lambda c,a:bad)
    with pytest.raises((ValueError,TypeError)):saver({}, {})
    saver.close()
    assert saver.records[0]['status']=='unknown_prediction_or_export_error'
    assert d.early_inventory(saver.records,events(tmp_path))==1


def test_prediction_file_collision_preserved(tmp_path):
    saver=d.SaveBeforeReturn(tmp_path,lambda c,a:value())
    target=tmp_path/'early_predictions/000.json.gz';target.write_bytes(b'old')
    with pytest.raises(FileExistsError):saver({}, {})
    saver.close();assert target.read_bytes()==b'old'
    assert saver.records[0]['status']=='unknown_prediction_or_export_error'


def test_failure_journal_does_not_mask_predictor_exception(tmp_path,monkeypatch):
    error=MemoryError('original')
    def predict(c,a):raise error
    saver=d.SaveBeforeReturn(tmp_path,predict);original=saver.append
    def append(event):
        if event['event']=='attempt_failed':raise OSError('second failure')
        return original(event)
    monkeypatch.setattr(saver,'append',append)
    with pytest.raises(MemoryError) as caught:saver({}, {})
    saver.close();assert caught.value is error and len(saver.journal_errors)==1
    with pytest.raises(ValueError,match='journal_binding'):d.early_inventory(saver.records,events(tmp_path))


def test_short_journal_write_is_failure(tmp_path):
    saver=d.SaveBeforeReturn(tmp_path,lambda c,a:pytest.fail('must not predict'))
    saver.journal.close()
    saver.journal=SimpleNamespace(write=lambda data:len(data)-1,flush=lambda:None,close=lambda:None)
    with pytest.raises(ValueError,match='journal_short_write'):saver({}, {})
    assert saver.records[0]['status']=='unknown_prediction_or_export_error' and saver.journal_errors


@pytest.mark.parametrize('answers',[(False,),(True,False)])
def test_gc_disabled_never_certifies(tmp_path,monkeypatch,answers):
    answers=iter(answers);monkeypatch.setattr(d.gc,'isenabled',lambda:next(answers))
    saver=d.SaveBeforeReturn(tmp_path,lambda c,a:value())
    with pytest.raises(ValueError,match='GC_disabled'):saver({}, {})
    saver.close();assert not saver.records or saver.records[0]['status']=='unknown_prediction_or_export_error'


def test_exact_max96_then_no_extra_callback(tmp_path):
    seen=[];saver=d.SaveBeforeReturn(tmp_path,lambda c,a:(seen.append(a),{'value':a})[1])
    for i in range(96):assert saver({},i)=={'value':i}
    with pytest.raises(ValueError,match='maximum_model_calls'):saver({},96)
    saver.close();assert seen==list(range(96))
    assert d.early_inventory(saver.records,events(tmp_path))==96


@pytest.mark.parametrize('mutation',[
    'ordinal','start_type','start_negative','predict_before_start','save_before_predict',
    'bytes_type','unfinished','journal_missing','journal_reorder','journal_extra'])
def test_early_inventory_rejects_tampering(tmp_path,mutation):
    saver,_=invoke(tmp_path);rows=copy.deepcopy(saver.records);journal=events(tmp_path)
    row=rows[0]
    if mutation=='ordinal':row['ordinal']=1
    elif mutation=='start_type':row['started_ns']=float(row['started_ns'])
    elif mutation=='start_negative':row['started_ns']=-2
    elif mutation=='predict_before_start':row['predict_returned_ns']=row['started_ns']-1
    elif mutation=='save_before_predict':row['saved_ns']=row['predict_returned_ns']-1
    elif mutation=='bytes_type':row['full_json_bytes']=True
    elif mutation=='unfinished':row['status']='unknown_in_progress'
    elif mutation=='journal_missing':journal.pop()
    elif mutation=='journal_reorder':journal.reverse()
    else:journal.append(journal[-1])
    with pytest.raises(ValueError):d.early_inventory(rows,journal)


def test_bind_worker_retains_all_real_checks_and_original_globals():
    before=dict(d.original.worker.__globals__);sentinel=lambda c,a:None
    bound=d.bind_worker(sentinel)
    assert bound.__code__ is d.original.worker.__code__
    assert bound.__closure__ is d.original.worker.__closure__
    assert bound.__defaults__ is d.original.worker.__defaults__
    assert bound.__kwdefaults__ is d.original.worker.__kwdefaults__
    assert set(bound.__globals__)==set(before)
    assert all(bound.__globals__[k] is v for k,v in before.items() if k!='model')
    assert bound.__globals__['model'].predict is sentinel
    assert bound.__globals__['model'].physics is d.original.model.physics
    assert all(d.original.worker.__globals__[k] is v for k,v in before.items())


def test_source_proof_does_not_construct_scope(monkeypatch):
    monkeypatch.setattr(d.candidate,'PublicInputScope',lambda:pytest.fail('no scope in source proof'))
    assert d.source_proof()['candidate_fresh_scope_each_call'] is True


def test_candidate_new_scope_every_call_without_actual_projection(monkeypatch):
    seen=[]
    class Fake:
        def __init__(self):seen.append(self)
        def predict(self,c,a):return (self,c,a)
    monkeypatch.setattr(d.candidate,'PublicInputScope',Fake)
    x=d.candidate.predict('c',0);y=d.candidate.predict('c',1)
    assert len(seen)==2 and x[0] is not y[0] and x[1:]==('c',0) and y[1:]==('c',1)


def complete():
    return ({'status':'exact_all96_conformance','model_evaluations':96,
        'actual_collection_data_checks':226,'actual_known_collection_data':192,
        'complete_actual_collection_conformance':True},
        {k:{'status':'exact_conformance'} for k in d.ORDER},
        [{'ordinal':i,'status':'complete_prediction_saved_before_return'} for i in range(96)])


def test_mapping_only_after_complete_original96():
    assert d.mapping_allowed(*complete())


@pytest.mark.parametrize('mutation',['status','count','contexts','known','complete','rows_order',
    'rows_missing','row_unknown','records_missing','record_unknown'])
def test_partial_or_unknown_ordinals_never_get_branch_keys(mutation):
    receipt,rows,records=complete()
    if mutation=='status':receipt['status']='completed_conformance_failed_unknowns_preserved'
    elif mutation=='count':receipt['model_evaluations']=95
    elif mutation=='contexts':receipt['actual_collection_data_checks']=225
    elif mutation=='known':receipt['actual_known_collection_data']=191
    elif mutation=='complete':receipt['complete_actual_collection_conformance']=False
    elif mutation=='rows_order':rows=dict(reversed(list(rows.items())))
    elif mutation=='rows_missing':rows.pop(d.ORDER[-1])
    elif mutation=='row_unknown':rows[d.ORDER[3]]['status']='unknown_error'
    elif mutation=='records_missing':records.pop()
    else:records[3]['status']='unknown_prediction_or_export_error'
    assert not d.mapping_allowed(receipt,rows,records)


def zipped(value):return gzip.compress(json.dumps(value,allow_nan=False).encode(),mtime=0)


def test_full_output_exact_accepts_compression_difference_only():
    encoded=json.dumps(value(),allow_nan=False).encode()
    assert d.exact_predictions(gzip.compress(encoded,mtime=1),gzip.compress(encoded,mtime=2))==encoded


@pytest.mark.parametrize('first,second',[
    ({'x':1},{'x':1.0}),({'x':0.0},{'x':-0.0}),({'x':True},{'x':1}),
    ({'a':1,'b':2},{'b':2,'a':1}),({'a':[1,2]},{'a':[2,1]}),
    ({'a':None},{}),({'events':[['x',1.0]]},{'events':[['x',1.0000000000000002]]})])
def test_complete_output_all_fields_order_types_floathex(first,second):
    with pytest.raises(ValueError,match='full_prediction'):d.exact_predictions(zipped(first),zipped(second))


@pytest.mark.parametrize('primary,close_error',[(True,True),(True,False),(False,True)])
def test_original_failure_primary_and_cleanup_evidence(tmp_path,monkeypatch,primary,close_error):
    error=RuntimeError('original-worker');closing=OSError('close')
    def run(output,expected):
        if primary:raise error
    monkeypatch.setattr(d,'bind_worker',lambda s:run)
    def close():
        if close_error:raise closing
    saver=SimpleNamespace(records=[],journal_errors=[],close=close)
    with pytest.raises((RuntimeError,OSError)) as caught:d.run_original(saver,tmp_path,'x')
    assert caught.value is (error if primary else closing)
    evidence=json.loads((tmp_path/'early_prediction_inventory.json').read_bytes())
    assert bool(evidence['journal_errors']) is close_error


def test_inventory_export_failure_keeps_original_error(tmp_path,monkeypatch):
    error=RuntimeError('original-worker')
    def run(o,e):raise error
    def write(*args):raise OSError('inventory')
    monkeypatch.setattr(d,'bind_worker',lambda s:run);monkeypatch.setattr(d,'write',write)
    saver=SimpleNamespace(records=[],journal_errors=[],close=lambda:None)
    with pytest.raises(RuntimeError) as caught:d.run_original(saver,tmp_path,'x')
    assert caught.value is error


@pytest.mark.parametrize('name',['czr005_circulation_fake','_g31_complete_tree_normalizer_fake'])
def test_execution_extension_rejected(monkeypatch,name):
    monkeypatch.setitem(d.sys.modules,name,SimpleNamespace())
    with pytest.raises(ValueError,match='forbidden_extension'):d.no_execution_extensions()


def test_original_source_only_future_target_read_after_predict():
    source=inspect.getsource(d.original.worker)
    assert source.index('prediction=model.predict(')<source.index("actual=raw['summary']['completion']")
    assert source.index('prediction=model.predict(')<source.index('supplied=future_context(')
    # Actual raw has already been decoded by the offline verifier. It is not
    # passed to the predictor; this is a call-boundary claim, not data erasure.
    assert 'model.predict(contexts[\'A\'],action)' in source
