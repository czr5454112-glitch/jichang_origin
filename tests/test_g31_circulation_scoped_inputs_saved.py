"""Synthetic saved-reader cases only. No model or real prediction is loaded."""
import copy
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import review_scoped_public_inputs_saved as r


def ledger():
    rows=[];clock=100
    for item in r.declaration():
        rows.append({**item,'status':'exact_full_prediction','started_ns':clock,'finished_ns':clock+10,
            'elapsed_ns':10,'export_ns':2,'raw':{'path':'synthetic','sha256':'0'*64}});clock+=20
    return rows


def sample_bytes(value):return json.dumps(value,allow_nan=False).encode()


def test_exact_statistics_ABBA24_twelve_per_arm_and_all_six_negative_kept():
    result=r.summarize(ledger())
    assert result['exact']==24 and result['unknown']==0
    assert result['summary_ms']['A']['count']==result['summary_ms']['B']['count']==12
    assert result['negative_or_equal_cases']==list(r.ORDER)
    assert len(result['paired_median_ms'])==6


@pytest.mark.parametrize('defect',['omit','duplicate','order','arm','position_bool','clock_bool','elapsed','overlap','export_negative','clock_partial','exact_missing_raw'])
def test_ledger_tamper_rejected(defect):
    rows=ledger()
    if defect=='omit':rows.pop()
    elif defect=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif defect=='order':rows.reverse()
    elif defect=='arm':rows[0]['arm']='B'
    elif defect=='position_bool':rows[0]['position']=False
    elif defect=='clock_bool':rows[0]['started_ns']=True
    elif defect=='elapsed':rows[0]['elapsed_ns']=9
    elif defect=='overlap':rows[1]['started_ns']=rows[0]['finished_ns']+1;rows[1]['elapsed_ns']=rows[1]['finished_ns']-rows[1]['started_ns']
    elif defect=='export_negative':rows[0]['export_ns']=-1
    elif defect=='clock_partial':del rows[0]['finished_ns']
    else:del rows[0]['raw']
    with pytest.raises(ValueError):r.summarize(rows)


@pytest.mark.parametrize('state',['unknown_unexecuted','unknown_setup_error','unknown_in_progress','unknown_error','returned_audit_pending'])
def test_unknowns_remain_denominator_and_no_partial_speed_summary(state):
    rows=ledger();rows[7]['status']=state
    result=r.summarize(rows)
    assert result['exact']==23 and result['unknown']==1 and result['summary_ms']=={}
    assert len(rows)==24


@pytest.mark.parametrize('a,b',[(1,1.),(False,0),(-0.,0.),({'a':1,'b':2},{'b':2,'a':1}),([1,2],[2,1])])
def test_complete_type_order_floathex_mismatch(a,b):
    x={'value':a,'projected_collections':[]};y={'value':b,'projected_collections':[]}
    with pytest.raises(ValueError,match='complete_prediction_changed'):
        r.compare_prediction(sample_bytes(x),sample_bytes(y),[])


def test_exact_full_bytes_and_chronology_no_output_projection():
    value={'completion':{'a':1.},'events':[{'at':-0.,'kind':'event'}],'projected_collections':[{'at':1.,'owner':'A'}]}
    raw=sample_bytes(value)
    assert all(r.compare_prediction(raw,raw,value['projected_collections']).values())
    with pytest.raises(ValueError,match='collection_chronology'):r.compare_prediction(raw,raw,[])
    with pytest.raises(ValueError,match='complete_prediction_changed'):r.compare_prediction(raw,raw+b' ',value['projected_collections'])


@pytest.mark.parametrize('value',[b'{"x":1,"x":2}',b'NaN',b'Infinity',b'1e999'])
def test_malformed_json_rejected(value):
    with pytest.raises(ValueError):r.loads(value)


def worker_source():
    return '''def worker(output,expected):
    for row in rows:
        try:
            function = lazy.predict
            try:
                prediction = function(context, public['action'])
            finally:
                end = clock()
            encoded = bytes_of(prediction)
            path.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))
            item.update(status='returned_audit_pending',raw=ref(path))
            write(output/'ledger.json',ledger)
            target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
            compare(encoded,target)
        except Exception:
            record_error()
'''


def test_source_proof_does_not_promote_saved_metadata_to_runtime_IO_journal():
    proof=r.source_order_proof(worker_source())
    assert proof['source_save_and_pending_write_before_target_read']
    assert proof['prediction_arguments_only_supplied_context_and_action']
    assert proof['independent_runtime_target_read_order_proved'] is False


@pytest.mark.parametrize('defect',['target_arg','early_target','no_save','no_pending'])
def test_source_order_and_model_input_regression(defect):
    source=worker_source()
    if defect=='target_arg':source=source.replace("function(context, public['action'])","function(context, target)")
    elif defect=='early_target':
        line="            target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())\n"
        source=source.replace(line,'').replace('            function = lazy.predict\n',line+'            function = lazy.predict\n')
    elif defect=='no_save':source=source.replace('path.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))','discard(encoded)')
    else:source=source.replace("status='returned_audit_pending'","status='exact_full_prediction'")
    with pytest.raises((ValueError,StopIteration)):r.source_order_proof(source)


def source_fixture(tmp_path):
    live=tmp_path/'source.py';live.write_text('x=1\n');archive=tmp_path/'archived.py';archive.write_bytes(live.read_bytes())
    evidence=tmp_path/'evidence.json';evidence.write_text('{}')
    plan={'source_sha256':{str(live):r.sha(live)},'source_archive':{str(live):archive.name},
        'evidence_sha256':{str(evidence):r.sha(evidence)}}
    entry={str(live):r.sha(live),str(archive):r.sha(archive),str(evidence):r.sha(evidence)}
    loaded={str(live):r.sha(live)}
    return plan,entry,loaded


def test_current_archive_evidence_and_loaded_identity_exact(tmp_path):
    plan,entry,loaded=source_fixture(tmp_path)
    result=r.check_saved_sources(tmp_path,plan,entry,copy.deepcopy(entry),loaded,copy.deepcopy(loaded))
    assert result=={'sources':1,'evidence_files':1,'loaded_entry':1,'loaded_exit':1}


@pytest.mark.parametrize('defect',['archive','entry_missing','exit_changed','loaded_unpinned','loaded_removed'])
def test_saved_source_and_runtime_tamper(tmp_path,defect):
    plan,entry,loaded=source_fixture(tmp_path);exit=copy.deepcopy(entry);loaded_exit=copy.deepcopy(loaded)
    if defect=='archive':(tmp_path/'archived.py').write_text('x=2\n')
    elif defect=='entry_missing':entry.pop(next(iter(entry)))
    elif defect=='exit_changed':exit[next(iter(exit))]='f'*64
    elif defect=='loaded_unpinned':loaded_exit['foreign.py']='f'*64
    else:loaded_exit.clear()
    with pytest.raises(ValueError):r.check_saved_sources(tmp_path,plan,entry,exit,loaded,loaded_exit)


def test_fixed_whole_budget_rejects_spent_or_nonfinite_time():
    assert r.remaining(10.)==109.
    for value in (True,-1.,float('nan'),119.,120.):
        with pytest.raises((ValueError,TimeoutError)):r.remaining(value)


def test_import_does_not_import_or_call_candidate_model():
    r.no_execution_modules()


def producer_metadata():
    plan={'order':list(r.ORDER),'declaration':r.declaration(),'maximum_model_calls':24,
        'hard_application_seconds':120.,'default_GC_required':True,
        'environment':{'python':'python.exe','sha256':'0'*64}}
    report={'status':'passed_fixed_six_ABBA24_complete_prediction','GC_enabled':True,'source_changed':[],
        'native_calls':0,'C_extension_loads':0,'complete_request100ms_certified':False,
        'all_method_setup_and_state_filtering_costed':False,'model_calls':24,'worker_seconds':10.,
        'setup':[{'key':k,'status':'initial_context_prepared','seconds':.1} for k in r.ORDER]}
    receipt={'status':report['status'],'source_changed':[]}
    process={'status':'exited','exitcode':0,'pid':1,'windows_job_kill_on_close':True,
        'child_released_only_after_job_assignment':True,'wall_seconds':11.,'hard_timeout_seconds':118.}
    command=['python.exe','-m','scripts.experiments.g31_ics_circulation.measure_scoped_public_inputs_six',
        '--worker','--output',str(r.PRODUCER),'--expected-plan',r.PLAN_SHA]
    bounded={'status':'completed','process':process,'whole_python_before_receipt_seconds':12.,'shared_limit_seconds':120.,'command':command}
    outer={'status':'application_exited_zero','exit_code':0,'error':None,'evidence_unchanged':True,
        'whole_python_within_120_seconds':True,'shared_owned_seconds':120,'plan_sha256':r.PLAN_SHA,
        'python_sha256':'0'*64,'fixed_inputs':6,'model_calls':24,'C_extension_loads':0,
        'native_simulation_calls':0,'complete_native_request_100ms_certified':False,'whole_python_application_seconds':13.}
    return plan,report,receipt,bounded,outer


def test_producer_complete_wall_and_scope_metadata():
    r.metadata_check(*producer_metadata())


@pytest.mark.parametrize('defect',['pid_bool','nan_wall','no_job','clock_order','GC_false','100ms_true','wrong_command','exit_bool'])
def test_metadata_cannot_promote_partial_or_scope_changed_producer(defect):
    p,rp,rc,b,o=producer_metadata()
    if defect=='pid_bool':b['process']['pid']=True
    elif defect=='nan_wall':b['process']['wall_seconds']=float('nan')
    elif defect=='no_job':b['process']['windows_job_kill_on_close']=False
    elif defect=='clock_order':o['whole_python_application_seconds']=9.
    elif defect=='GC_false':rp['GC_enabled']=False
    elif defect=='100ms_true':rp['complete_request100ms_certified']=True
    elif defect=='wrong_command':b['command'][-1]='f'*64
    else:o['exit_code']=False
    with pytest.raises(ValueError):r.metadata_check(p,rp,rc,b,o)
