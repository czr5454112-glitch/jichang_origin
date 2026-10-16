"""Checker/admission tests; saved outputs are test oracles, never policy inputs."""
from copy import deepcopy
import gzip
import hashlib
import json
import pickle
import pytest
from scripts.experiments.g31_ics_circulation import measure_preference_receiver_bound_context as m


def fixture():
    name=m.CASES[0];bundle=json.loads((m.ORACLE/(name+'.input.json')).read_bytes())
    full=m.oracle_case(name,bundle)
    reference=json.loads(gzip.decompress((m.ORACLE/(name+'.1.B.json.gz')).read_bytes()))
    digest=hashlib.sha256(pickle.dumps(bundle,protocol=5)).hexdigest();actual=deepcopy(reference)
    for i,action in enumerate(full['actions']):
        w=m.expected_bound(bundle,action,full['baseline']['completion'])
        if w['completion_lower_bound']>w['baseline_completed_at']:
            actual['predictions'][i]={'status':m.LOWER,'completion':{},'completion_sum':None,'witness':w,
                'supplied_snapshot_sha256':digest,'baseline_action':deepcopy(full['actions'][0]),
                'baseline_completion':deepcopy(full['baseline']['completion']),'full_candidate_prediction':False,
                'suffix_status':'unknown_unexecuted','native_protection_certified':False,
                'native_execution_certified':False,'online_information_delivered':False,'complete_100ms_certified':False}
    return bundle,full,reference,actual,digest


def test_actual_shaped_bound_checker_preserves_all32_and_suffix_unknown():
    bundle,full,reference,actual,digest=fixture()
    assert m.check_outputs(full,actual,digest,bundle,reference)=={
        'full_exact':4,'strict_prefix_rejections':12,'unknown':0,'strict_lower_bound_rejections':16}
    assert m.check_outputs(full,reference,digest,bundle)['strict_lower_bound_rejections']==0


@pytest.mark.parametrize('defect',['omitted','action_order','baseline','digest','path','bound','grant',
    'float_bool','fake_complete','native_true','suffix','extra','full_changed','prefix_changed','unknown_oracle'])
def test_bound_tamper_or_changed_nonbound_output_rejected(defect):
    bundle,full,reference,actual,digest=fixture();part=next(p for p in actual['predictions'] if p['status']==m.LOWER)
    if defect=='omitted':actual['predictions'].pop()
    elif defect=='action_order':actual['actions'].reverse()
    elif defect=='baseline':actual['baseline']['completion']['receiver']=0.
    elif defect=='digest':part['supplied_snapshot_sha256']='0'*64
    elif defect=='path':part['witness']['positive_capacity_paths']['loaded']=[1,9,4]
    elif defect=='bound':part['witness']['completion_lower_bound']+=.01
    elif defect=='grant':part['witness']['grant_lower_bound']-=.01
    elif defect=='float_bool':part['witness']['completion_lower_bound']=True
    elif defect=='fake_complete':part['full_candidate_prediction']=True
    elif defect=='native_true':part['native_execution_certified']=True
    elif defect=='suffix':part['suffix_status']='complete'
    elif defect=='extra':part['witness']['ignored']='no'
    elif defect=='full_changed':next(p for p in actual['predictions'] if p['status']=='conditional_prediction')['completion']['receiver']+=.01
    elif defect=='prefix_changed':next(p for p in actual['predictions'] if p['status']==m.PARTIAL)['witness']['cut_at']+=.01
    else:next(p for p,a in zip(full['predictions'],actual['predictions']) if a['status']==m.LOWER)['status']='unknown'
    with pytest.raises(ValueError):m.check_outputs(full,actual,digest,bundle,reference)


def test_both_batch_arms_construct_and_compute_baseline_plus32(monkeypatch):
    calls=[]
    class Context:
        def __init__(self,bundle):calls.append(('context',bundle));self.saved=self.predict({'n':0})
        def actions(self):calls.append(('actions',));return [{'n':n} for n in range(32)]
        def predict(self,action):calls.append(('predict',action['n']));return {'action':action['n']}
        def baseline(self):calls.append(('baseline_copy',));return deepcopy(self.saved)
    monkeypatch.setattr(m.reference,'ProtectionRequestContext',Context)
    monkeypatch.setattr(m.candidate,'ReceiverBoundRequestContext',Context)
    a=m.batch({'input_only':True},'A');acalls=list(calls);calls.clear();b=m.batch({'input_only':True},'B')
    assert a==b and acalls==calls
    assert [v[1] for v in calls if v[0]=='predict']==[0]+list(range(32))
    assert len([v for v in calls if v[0]=='baseline_copy'])==1


def plan():
    return {'schema':m.SCHEMA,'native_calls':0,'hard_timeout_seconds':120.,'candidate_domain':32,'batch_count':24,
        'full_baseline_per_batch':1,'input':{'sha256':m.INPUT_SHA},'source_sha256':{'example.py':'a'*64},
        'cases':[{'case':name,'input':name+'.input.json','order':['A','B','B','A']} for name in m.CASES]}


@pytest.mark.parametrize('field,value',[('native_calls',1),('batch_count',23),('candidate_domain',31),('hard_timeout_seconds',121),('full_baseline_per_batch',0)])
def test_fixed_denominators_and_budget(field,value):
    p=plan();m.check_plan(p);p[field]=value
    with pytest.raises(ValueError):m.check_plan(p)


def test_timeout_never_promoted_or_overwritten(monkeypatch,tmp_path):
    p=plan();m.write(tmp_path/'preregistered_protocol.json',p);digest=m.sha(tmp_path/'preregistered_protocol.json')
    monkeypatch.setattr(m,'verify_pins',lambda *args:None)
    monkeypatch.setattr(m.bounded_windows_job,'run',lambda *a,**k:{'status':'hard_timeout','exitcode':1,'windows_job_kill_on_close':True})
    assert m.launch(tmp_path,digest)==1
    assert json.loads((tmp_path/'external_process.json').read_bytes())['status']=='failed_or_unknown'
    assert not (tmp_path/'receipt.json').exists()
    with pytest.raises(FileExistsError):m.launch(tmp_path,digest)


def saved_fixture(path,monkeypatch):
    bundle,full,reference,actual,digest=fixture();m.write(path/'preregistered_protocol.json',plan());rows=[];pairs=[]
    for case in m.CASES:
        m.write(path/(case+'.input.json'),bundle)
        for n,arm in enumerate(['A','B','B','A']):
            value=reference if arm=='A' else actual;name=f'{case}.{n}.{arm}.json.gz'
            (path/name).write_bytes(gzip.compress(m.encoded(value).encode('utf8'),mtime=0))
            rows.append({'case':case,'sample':n,'arm':arm,'status':'completed','wall_ns':100,'cpu_ns':50,
                'raw':name,'raw_sha256':m.sha(path/name),'checks':m.check_outputs(full,value,digest,bundle,reference if arm=='B' else None)})
        pairs.append({'case':case,'median_A_ns':100.,'median_B_ns':100.})
    m.write(path/'ledger.json',rows)
    receipt={'status':'completed_pure_ABBA_with_validated_partial_suffixes','plan_sha256':m.sha(path/'preregistered_protocol.json'),
        'source_changed':[],'input_changed':[],'native_calls':0,'complete_100ms_certified':False,'candidate_queries':768,
        'full_baselines':24,'timing_samples':deepcopy(rows),'case_pairs':pairs,'median_A_ns':100.,'median_B_ns':100.,'worker_wall_seconds':1.}
    m.write(path/'receipt.json',receipt)
    m.write(path/'external_process.json',{'status':'worker_exited_zero','plan_sha256':receipt['plan_sha256'],'process':{'status':'exited','exitcode':0}})
    monkeypatch.setattr(m,'verify_pins',lambda *a:None);monkeypatch.setattr(m,'oracle_case',lambda *a:full)
    return rows,receipt


@pytest.mark.parametrize('defect',['none','omitted','clock_bool','negative_cpu','summary','process','raw'])
def test_saved_output_recheck_is_complete(monkeypatch,tmp_path,defect):
    rows,receipt=saved_fixture(tmp_path,monkeypatch)
    if defect=='none':assert m.verify_saved(tmp_path)['status']=='saved_24_batches_rechecked';return
    if defect=='omitted':rows.pop()
    elif defect=='clock_bool':rows[0]['wall_ns']=True
    elif defect=='negative_cpu':rows[0]['cpu_ns']=-1
    elif defect=='summary':receipt['median_A_ns']=5.
    elif defect=='process':m.write(tmp_path/'external_process.json',{'status':'failed'})
    else:(tmp_path/rows[0]['raw']).write_bytes(b'not raw')
    receipt['timing_samples']=deepcopy(rows);m.write(tmp_path/'ledger.json',rows);m.write(tmp_path/'receipt.json',receipt)
    with pytest.raises(ValueError):m.verify_saved(tmp_path)


def test_oracle_authority_cannot_be_replaced_by_edited_ledger(monkeypatch):
    monkeypatch.setattr(m,'ORACLE_LEDGER_SHA','0'*64)
    with pytest.raises(ValueError,match='unaccepted_oracle'):m.oracle_pins()
