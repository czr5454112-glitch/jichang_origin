"""Synthetic wiring only: no C load, real fixture decode, model or benchmark."""
import copy
import hashlib
from pathlib import Path
from types import FunctionType,SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import delivered_peer_c_encoder_probe as p
from scripts.experiments.g31_ics_circulation import measure_delivered_peer_c_encoder as m
from scripts.experiments.g31_ics_circulation import planning_v2_c_encoder_authority as authority


def private(function,**updates):
    clone=FunctionType(function.__code__,{**function.__globals__,**updates},function.__name__,function.__defaults__,function.__closure__)
    clone.__kwdefaults__=function.__kwdefaults__;return clone


def records():
    result=[];batches=[]
    for ordinal in (27212,27215):
        for batch,arm in enumerate(m.ARMS):
            begin=len(result)*10
            for repeat in range(4):
                start=len(result)*10+1
                result.append({'ordinal':ordinal,'batch':batch,'arm':arm,'repeat':repeat,'disposition':'absent',
                    'outcome_file':f'outcome_{ordinal}_{batch}_{repeat}.json','outcome_sha256':'a'*64,
                    'metrics':{'started_ns':start,'finished_ns':start+5,'validator_ns':5,
                    'digest_events':None if arm=='A' else [{'ordinal':0,'classification':'direct_C_bytes','returned':True,'sha256':'b'*64}]}})
            end=len(result)*10;batches.append({'ordinal':ordinal,'batch':batch,'arm':arm,'started_ns':begin,'finished_ns':end,'whole_batch_ns':end-begin})
    return result,batches


def test_private_full_globals_and_original_code():
    old=p.original._VALIDATOR;before=dict(old.__globals__);digest=object();bound=p.private_validator(digest)
    assert bound.__code__ is old.__code__ and bound.__defaults__ is old.__defaults__ and bound.__closure__ is old.__closure__
    assert set(bound.__globals__)==set(before)
    assert [k for k in before if bound.__globals__[k] is not before[k]]==['capture_digest_v2']
    assert all(old.__globals__[k] is v for k,v in before.items())
    assert p.source_proof()['expiry_order_unchanged']


def test_actual_bound_rejects_unverified_candidate():
    with pytest.raises(ValueError,match='verified_Candidate_required'):p.bound(SimpleNamespace())


def test_direct_digest_exact_bytes_hash_and_single_attempt():
    calls=[];verify=[]
    record=p.DigestRecord(lambda value:calls.append(value) or b'\x00\xfftyped',lambda:verify.append(1))
    body=object();assert record(body)==hashlib.sha256(b'\x00\xfftyped').hexdigest()
    assert calls==[body] and verify==[1] and record.events==[{'ordinal':0,'classification':'direct_C_bytes','returned':True,'sha256':hashlib.sha256(b'\x00\xfftyped').hexdigest()}]


def test_only_NotImplemented_falls_back_once(monkeypatch):
    calls=[];body=object();monkeypatch.setattr(p.encoder,'_ORIGINAL',lambda value:calls.append(('old',value)) or 'original')
    record=p.DigestRecord(lambda value:calls.append(('C',value)) or NotImplemented,lambda:None)
    assert record(body)=='original' and calls==[('C',body),('old',body)]
    assert record.events[0]['classification']=='original_fallback'


@pytest.mark.parametrize('error',(ValueError,KeyError,TypeError,MemoryError,RecursionError,RuntimeError,KeyboardInterrupt))
def test_raised_C_never_retries_original(monkeypatch,error):
    original=error('stop');called=[]
    monkeypatch.setattr(p.encoder,'_ORIGINAL',lambda _:pytest.fail('fallback not allowed'))
    def attempt(body):called.append(1);raise original
    record=p.DigestRecord(attempt,lambda:None)
    with pytest.raises(error) as caught:record({})
    assert caught.value is original and called==[1] and record.events[0]['returned'] is False


def test_wrong_C_return_type_is_failure_not_fallback(monkeypatch):
    monkeypatch.setattr(p.encoder,'_ORIGINAL',lambda _:pytest.fail('must not fallback'))
    record=p.DigestRecord(lambda _:bytearray(b'x'),lambda:None)
    with pytest.raises(ValueError,match='unexpected_extension_result'):record({})


def test_verification_error_prevents_C_attempt():
    exc=RuntimeError('identity')
    def verify():raise exc
    record=p.DigestRecord(lambda _:pytest.fail('must not attempt'),verify)
    with pytest.raises(RuntimeError) as caught:record({})
    assert caught.value is exc and record.events[0]['classification']=='entered'


def test_expired_envelope_still_executes_original_digest_callsite():
    seen=[]
    def digest(body):seen.append(body);return 'sha'
    envelope={'schema':'g31.planning_snapshot.v2','kind':'planning_snapshot_v2','digest_format':'g31.planning_capture_digest.v2',
        'payload_sha256':'sha','status':'expired','delivered_at':2.,'capture':{'schema':'g31.planning_capture.v2',
        'local_capture':{'source_owner':'B','target_owner':'A','captured_at':1.,'valid_until':3.}}}
    result=p.original.invoke(p.private_validator(digest),([envelope],'A','B',4.,{}))
    assert result=={'status':'absent'} and seen==[envelope['capture']]


def test_predigest_rejection_keeps_all_envelopes():
    function=p.private_validator(lambda _:pytest.fail('duplicate check must be first'))
    result=p.original.invoke(function,([{},{}],'A','B',4.,{}))
    assert result['status']=='rejected' and 'unexpected_or_duplicate' in result['exception_text']


@pytest.mark.parametrize('error',(ValueError,KeyError,TypeError))
def test_ordinary_errors_remain_rejected(error):
    def function(*args):raise error('exact')
    result=p.invoke(function,())
    assert result=={'status':'rejected','exception_type':error.__name__,'exception_text':str(error('exact')),
        'exception_args_verified':True,'exception_args':{'type':'tuple','items':[{'type':'str','value':'exact'}]}}


@pytest.mark.parametrize('error',(MemoryError,RuntimeError,RecursionError))
def test_resource_errors_are_not_successful_rejections(error):
    def function(*args):raise error('resource')
    with pytest.raises(error):p.invoke(function,())


def test_A_empty_no_candidate_or_C_load():
    ticks=iter((10,20));attempt={}
    outcome,metrics=p.measure(([],'A','B',4.,{}),'A',None,lambda:next(ticks),attempt)
    assert outcome=={'status':'absent'} and metrics=={'started_ns':10,'finished_ns':20,'validator_ns':10,'digest_events':None}
    assert attempt=={'validator_started_ns':10,'digest_events':None}


@pytest.mark.parametrize('bad',(True,1.0,-1))
def test_measured_clock_type_or_order_rejected(bad):
    ticks=iter((bad,20))
    with pytest.raises(ValueError,match='typed_clock'):p.measure(([],'A','B',4.,{}),'A',None,lambda:next(ticks))


def test_complete32_and8_batch_gate():
    rows,batches=records();summary=m.audit_records(rows);m.audit_batches(batches,rows)
    assert summary['27212']['B']['direct_C_bytes']==8 and summary['27215']['A']['calls']==8


@pytest.mark.parametrize('field',('ordinal','batch','repeat'))
def test_bool_indices_rejected(field):
    rows,_=records();rows[0][field]=True
    with pytest.raises(ValueError):m.audit_records(rows)


@pytest.mark.parametrize('field',('started_ns','finished_ns','validator_ns'))
def test_bool_clock_rejected(field):
    rows,_=records();rows[0]['metrics'][field]=True
    with pytest.raises(ValueError):m.audit_records(rows)


@pytest.mark.parametrize('change',('missing','duplicate','swapped','extra_metric','mismatch_outcome','bad_SHA','two_digests','returned_int','unknown_class','resource_reclassified','wrong_file'))
def test_saved_record_tampering_rejected(change):
    rows,_=records()
    if change=='missing':rows.pop()
    elif change=='duplicate':rows.append(copy.deepcopy(rows[-1]))
    elif change=='swapped':rows[1],rows[2]=rows[2],rows[1]
    elif change=='extra_metric':rows[0]['metrics']['x']=1
    elif change=='mismatch_outcome':rows[0]['outcome_sha256']='b'*64
    elif change=='bad_SHA':rows[0]['outcome_sha256']='bad'
    elif change=='two_digests':rows[4]['metrics']['digest_events']*=2
    elif change=='returned_int':rows[4]['metrics']['digest_events'][0]['returned']=1
    elif change=='unknown_class':rows[4]['metrics']['digest_events'][0]['classification']='assumed'
    elif change=='resource_reclassified':rows[4]['disposition']='rejected';rows[4]['metrics']['digest_events']=[{'ordinal':0,'classification':'entered','returned':False,'error_type':'MemoryError','error_text':'x'}]
    elif change=='wrong_file':rows[0]['outcome_file']='other.json'
    with pytest.raises(ValueError):m.audit_records(rows)


@pytest.mark.parametrize('change',('missing','clock_bool','formula','outside_call','reorder'))
def test_batch_clock_and_membership_tampering(change):
    rows,batches=records()
    if change=='missing':batches.pop()
    elif change=='clock_bool':batches[0]['started_ns']=False
    elif change=='formula':batches[0]['whole_batch_ns']+=1
    elif change=='outside_call':batches[0]['finished_ns']=10;batches[0]['whole_batch_ns']=10
    else:batches[0],batches[1]=batches[1],batches[0]
    with pytest.raises(ValueError):m.audit_batches(batches,rows)


def test_source_union_conflict_rejected_and_extra_exact_members_retained():
    assert authority.merged_sources({'source_sha256':{'a':'1'}},{'b':'2'})['source_sha256']=={'a':'1','b':'2'}
    with pytest.raises(ValueError,match='source_union_conflict'):authority.merged_sources({'source_sha256':{'a':'1'}},{'a':'2'})


def test_stage_capacity_is_bounded(tmp_path):
    journal=m.Journal(tmp_path/'stages')
    try:
        for _ in range(64):journal.mark('test','complete')
        with pytest.raises(ValueError,match='stage_journal_capacity'):journal.mark('extra','unknown')
    finally:journal.close()
    assert len((tmp_path/'stages').read_bytes().splitlines())==64


def test_prepare_then_execute_then_pure_real_file_open_domains(tmp_path):
    calls=[]
    def job(command,**kwargs):
        calls.append(command);kwargs['stdout'].write(command[0].encode());return {'status':'exited','exitcode':0}
    function=private(m.run_child,bounded_windows_job=SimpleNamespace(run=job))
    for flag in ('--prepare-worker','--worker','--pure-worker'):function(tmp_path,[flag],'token')
    for label,flag in (('prepare','--prepare-worker'),('execute','--worker'),('pure','--pure-worker')):
        assert (tmp_path/(label+'_stdout.log')).read_bytes()==flag.encode()
    with pytest.raises(FileExistsError):function(tmp_path,['--worker'],'token')
    assert len(calls)==3


def test_ambiguous_stage_cannot_launch(tmp_path):
    with pytest.raises(ValueError,match='one_child_stage'):m.run_child(tmp_path,['--worker','--pure-worker'],'token')


def authority_fixture():
    value={'schema':'g31.planning_v2.C_encoder.functional_external_application_wall.v1',
        'exit_code':0,'source_changed':[],'outer_timeout':False,'exception':None,'elapsed_ticks':100,
        'tick_frequency':10,'whole_python_seconds':10.,'command':['exact'],
        'plan':{'path':str(authority.PLAN),'sha256':authority.PLAN_SHA}}
    receipt={'status':'functional_passed_synthetic_full_bytes','identity_verified_on_exit':True,
        'test_count':159,'pytest_exit_code':0,'bad_tests':[],'direct_support':{
            'direct_supported_count':126,'fallback_count':10,'fallback_is_not_direct_C_support':True}}
    return value,receipt,{'status':'exited','exitcode':0},{'command':['exact']}


def test_functional_external_synthetic_positive():
    authority.external_functional(*authority_fixture())


@pytest.mark.parametrize('change',('ticks_bool','frequency_float','wall_bool','wall_limit','formula','exit_bool',
                                  'test_float','direct_float','fallback_float','command'))
def test_functional_authority_bad_typed_evidence(change):
    value,receipt,bounded,review=authority_fixture()
    if change=='ticks_bool':value['elapsed_ticks']=True
    elif change=='frequency_float':value['tick_frequency']=10.
    elif change=='wall_bool':value['whole_python_seconds']=True
    elif change=='wall_limit':value['whole_python_seconds']=121.
    elif change=='formula':value['elapsed_ticks']=101
    elif change=='exit_bool':value['exit_code']=False
    elif change=='test_float':receipt['test_count']=159.
    elif change=='direct_float':receipt['direct_support']['direct_supported_count']=126.
    elif change=='fallback_float':receipt['direct_support']['fallback_count']=10.
    elif change=='command':value['command']=['other']
    with pytest.raises(ValueError):authority.external_functional(value,receipt,bounded,review)


def test_exception_args_preserve_same_text_different_tuple():
    # Same str is not proof of equal args: int versus bool, and signed zero.
    a=p.exception_args((1,True,0.,-0.,b'x',['x'],('x',)))
    assert [x['type'] for x in a['items']]==['int','bool','float64','float64','bytes','list','tuple']
    assert a['items'][2]['hex']=='0000000000000000' and a['items'][3]['hex']=='8000000000000000'


def test_custom_exception_arg_hooks_never_called():
    calls=[]
    class Custom:
        def __str__(self):calls.append('str');return 'x'
        def __repr__(self):calls.append('repr');return 'x'
    error=ValueError(Custom())
    def function():raise error
    with pytest.raises(p.UnsafeExceptionEvidence):p.invoke(function,())
    assert calls==[]


def test_exception_subclass_str_is_not_called():
    calls=[]
    class Custom(ValueError):
        def __str__(self):calls.append(1);return 'hidden'
    def function():raise Custom('safe args')
    with pytest.raises(p.UnsafeExceptionEvidence):p.invoke(function,())
    assert calls==[]


@pytest.mark.parametrize('shape',('alias','cycle'))
def test_exception_graph_unknown(shape):
    shared=[]
    if shape=='alias':args=(shared,shared)
    else:shared.append(shared);args=(shared,)
    with pytest.raises(p.UnsafeExceptionEvidence):p.exception_args(args)


def test_failed_digest_does_not_invoke_custom_error_rendering():
    calls=[]
    class Custom:
        def __str__(self):calls.append(1);return 'bad'
        def __repr__(self):calls.append(2);return 'bad'
    error=TypeError(Custom())
    def attempt(_):raise error
    record=p.DigestRecord(attempt,lambda:None)
    with pytest.raises(TypeError) as caught:record({})
    assert caught.value is error and calls==[] and record.events[0]['error']['exception_args_verified'] is False


def test_accepted_original_identity_is_still_required():
    env={};args=([env],)
    assert p.invoke(lambda rows:rows[0],args)['envelope'] is env
    with pytest.raises(ValueError,match='return_identity'):p.invoke(lambda rows:{},args)


def test_pure_external_positive():
    value={'schema':'g31.delivered_peer.C_encoder.pure_external.v1','command':['exact'],'runner':{'path':'x','sha256':'a'},
        'exit_code':0,'source_changed':[],'outer_timeout':False,'exception':None,'elapsed_ticks':100,
        'tick_frequency':10,'whole_python_seconds':10.,'output_sha256':{'receipt':'b'}}
    m.check_pure_external(value,['exact'],{'receipt':'b'},{'path':'x','sha256':'a'})


def test_pure_external_exact_tick_budget_not_rounded_wall():
    frequency=10**12
    value={'schema':'g31.delivered_peer.C_encoder.pure_external.v1','command':['exact'],'runner':{},
        'exit_code':0,'source_changed':[],'outer_timeout':False,'exception':None,'elapsed_ticks':120*frequency,
        'tick_frequency':frequency,'whole_python_seconds':120.,'output_sha256':{}}
    m.check_pure_external(value,['exact'],{},{})
    value['elapsed_ticks']+=1  # Below the old 1e-9 formula tolerance, but over the exact budget.
    with pytest.raises(ValueError,match='pure_external_clock'):m.check_pure_external(value,['exact'],{},{})


@pytest.mark.parametrize('change',('tick_bool','wall_bool','overbudget','command','outputs','status'))
def test_pure_external_bad(change):
    value={'schema':'g31.delivered_peer.C_encoder.pure_external.v1','command':['exact'],'runner':{},
        'exit_code':0,'source_changed':[],'outer_timeout':False,'exception':None,'elapsed_ticks':100,
        'tick_frequency':10,'whole_python_seconds':10.,'output_sha256':{}}
    if change=='tick_bool':value['elapsed_ticks']=True
    elif change=='wall_bool':value['whole_python_seconds']=True
    elif change=='overbudget':value['elapsed_ticks']=1210;value['whole_python_seconds']=121.
    elif change=='command':value['command']=['other']
    elif change=='outputs':value['output_sha256']={'other':'x'}
    else:value['exit_code']=False
    with pytest.raises(ValueError):m.check_pure_external(value,['exact'],{},{})


def archive_function(tmp_path):
    root=tmp_path/'repo';root.mkdir();out=root/'out';out.mkdir()
    function=private(m.archive_targets,ROOT=root,OUT=out)
    return function,root,out


def test_archive_precheck_is_canonical_distinct_and_short(tmp_path):
    function,root,out=archive_function(tmp_path);destination=out/'pure';destination.mkdir()
    target=function(destination,{'source.py':b'x'},True)['source.py']
    assert target==destination/'source/source.py' and target!=root/'source.py'


@pytest.mark.parametrize('change',('escape','long','live_alias','existing'))
def test_archive_precheck_rejects_bad_target(tmp_path,change):
    function,root,out=archive_function(tmp_path);destination=out/'pure';destination.mkdir();name='source.py'
    if change=='escape':name='../escape.py'
    elif change=='long':name='x'*260+'.py'
    elif change=='live_alias':destination=root
    else:(destination/'source').mkdir();(destination/'source/source.py').write_bytes(b'old')
    with pytest.raises(ValueError):function(destination,{name:b'x'},True)
