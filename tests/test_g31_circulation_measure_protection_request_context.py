from copy import deepcopy
import json
import gzip
import hashlib
import pickle
import pytest
from scripts.experiments.g31_ics_circulation import measure_preference_protection_request_context as m


def fixture():
    jobs=m.candidate.proof.original.contract.JOBS
    base={'status':'conditional_prediction','completion':{j:10. for j in sorted(jobs)}}
    full={'baseline':base,'actions':[{'n':n} for n in range(32)],'predictions':[deepcopy(base) for _ in range(32)]}
    actual=deepcopy(full); job=next(iter(base['completion']));full['predictions'][1]['completion'][job]=11.
    actual['predictions'][1]={'status':m.PARTIAL,'completion':{},'completion_sum':None,
        'witness':{'job':job,'candidate_completed_at':11.,'baseline_completed_at':10.,'cut_at':11.,
            'completed_prefix':{job:11.},'comparison':'strict >; no tolerance',
            'observed_point':'original unload assignment before its post-unload notification'},
        'supplied_snapshot_sha256':'a'*64,'baseline_action':{'n':0},'baseline_completion':deepcopy(base['completion']),
        'full_candidate_prediction':False,'suffix_status':'unknown_unexecuted','native_protection_certified':False,
        'native_execution_certified':False,'online_information_delivered':False,'complete_100ms_certified':False}
    return full,actual


def test_valid_partial_has_no_fabricated_complete_prediction():
    full,actual=fixture()
    assert m.check_outputs(full,actual,'a'*64)=={'full_exact':31,'strict_prefix_rejections':1,'unknown':0}


@pytest.mark.parametrize('defect', ['missing_candidate','reordered_action','baseline','full_value','unknown_baseline','unknown_candidate',
    'equal_not_strict','wrong_prefix','future_prefix','digest','complete_flag','suffix','native_flag','unexpected_witness'])
def test_tampered_partial_or_incomplete_domain_fails(defect):
    full,actual=fixture();part=actual['predictions'][1];w=part['witness'];job=w['job']
    if defect=='missing_candidate':actual['predictions'].pop()
    elif defect=='reordered_action':actual['actions'].reverse()
    elif defect=='baseline':actual['baseline']['completion'][job]=1.
    elif defect=='full_value':actual['predictions'][0]['completion'][job]=1.
    elif defect=='unknown_baseline':full['baseline']['status']=actual['baseline']['status']='unknown'
    elif defect=='unknown_candidate':full['predictions'][1]['status']='unknown'
    elif defect=='equal_not_strict':
        full['predictions'][1]['completion'][job]=10.;w['candidate_completed_at']=w['cut_at']=10.;w['completed_prefix'][job]=10.
    elif defect=='wrong_prefix':w['completed_prefix'][job]=9.
    elif defect=='future_prefix':w['completed_prefix'][next(k for k in full['baseline']['completion'] if k!=job)]=12.
    elif defect=='digest':part['supplied_snapshot_sha256']='b'*64
    elif defect=='complete_flag':part['full_candidate_prediction']=True
    elif defect=='suffix':part['suffix_status']='complete'
    elif defect=='native_flag':part['native_protection_certified']=True
    else:w['extra']='ignored?'
    with pytest.raises(ValueError):m.check_outputs(full,actual,'a'*64)


def test_ordered_float_output_difference_rejected():
    full,actual=fixture();full['predictions'][0]['zero']=-0.;actual['predictions'][0]['zero']=0.
    with pytest.raises(ValueError,match='full_prediction_not_exact'):m.check_outputs(full,actual,'a'*64)


def test_bool_cannot_impersonate_completion_time():
    full,actual=fixture();p=actual['predictions'][1];job=p['witness']['job']
    for v in (full['baseline'],actual['baseline']):v['completion'][job]=0.
    p['baseline_completion'][job]=0.;full['predictions'][1]['completion'][job]=1.
    p['witness'].update(candidate_completed_at=True,baseline_completed_at=0.,cut_at=1.,completed_prefix={job:1.})
    with pytest.raises(ValueError,match='invalid_partial'):m.check_outputs(full,actual,'a'*64)


def test_both_arms_charge_baseline_and_all32_including_baseline_query(monkeypatch):
    calls=[]
    class Ref:
        def __init__(self,bundle):calls.append(('context',bundle))
        def actions(self):calls.append(('actions',));return [{'n':n} for n in range(32)]
        def predict(self,action):calls.append(('predict',action['n']));return {'action':action['n']}
    class Cut(Ref):
        def __init__(self,bundle):super().__init__(bundle);self.saved=self.predict({'n':0})
        def baseline(self):calls.append(('baseline_copy',));return deepcopy(self.saved)
    monkeypatch.setattr(m.reference,'RequestContext',Ref);monkeypatch.setattr(m.candidate,'ProtectionRequestContext',Cut)
    a=m.batch({'x':1},'A');acalls=list(calls);calls.clear();b=m.batch({'x':1},'B')
    assert a==b
    assert [v[1] for v in acalls if v[0]=='predict']==[0]+list(range(32))
    assert [v[1] for v in calls if v[0]=='predict']==[0]+list(range(32))
    assert len(json.loads(a)['predictions'])==32


def plan():
    return {'schema':m.SCHEMA,'native_calls':0,'hard_timeout_seconds':120.,'candidate_domain':32,'batch_count':24,
        'full_baseline_per_batch':1,'input':{'sha256':m.INPUT_SHA},'source_sha256':{'example.py':'a'*64},
        'cases':[{'case':name,'input':name+'.input.json','order':['A','B','B','A']} for name in m.CASES]}


@pytest.mark.parametrize('field,value',[('native_calls',1),('batch_count',23),('candidate_domain',31),('hard_timeout_seconds',121),('full_baseline_per_batch',0)])
def test_plan_cannot_lower_denominator_or_raise_budget(field,value):
    value_plan=plan();m.check_plan(value_plan);value_plan[field]=value
    with pytest.raises(ValueError):m.check_plan(value_plan)


def test_plan_cannot_reorder_discard_warmup_or_escape_archive():
    value=plan();value['cases'][0]['order']=['A','B']
    with pytest.raises(ValueError):m.check_plan(value)
    value=plan();value['source_sha256']={'../escape.py':'a'*64}
    with pytest.raises(ValueError):m.check_plan(value)


def test_nonzero_or_timeout_cannot_promote_without_worker(monkeypatch,tmp_path):
    value=plan();m.write(tmp_path/'preregistered_protocol.json',value);digest=m.sha(tmp_path/'preregistered_protocol.json')
    monkeypatch.setattr(m,'verify_pins',lambda *args:None)
    monkeypatch.setattr(m.bounded_windows_job,'run',lambda *args,**kwargs:{'status':'hard_timeout','exitcode':1,'windows_job_kill_on_close':True})
    assert m.launch(tmp_path,digest)==1
    receipt=json.loads((tmp_path/'external_process.json').read_bytes())
    assert receipt['status']=='failed_or_unknown' and not (tmp_path/'receipt.json').exists()
    with pytest.raises(FileExistsError):m.launch(tmp_path,digest)


def saved_fixture(path):
    value_plan=plan();m.write(path/'preregistered_protocol.json',value_plan)
    full,partial=fixture();bundle={'synthetic_guard_only':True}
    partial['predictions'][1]['supplied_snapshot_sha256']=hashlib.sha256(pickle.dumps(bundle,protocol=5)).hexdigest()
    ledger=[];pairs=[]
    for case in m.CASES:
        m.write(path/(case+'.input.json'),bundle)
        for n,arm in enumerate(['A','B','B','A']):
            value=full if arm=='A' else partial;name=f'{case}.{n}.{arm}.json.gz'
            (path/name).write_bytes(gzip.compress(m.encoded(value).encode('utf8'),mtime=0))
            ledger.append({'case':case,'sample':n,'arm':arm,'status':'completed','wall_ns':100,'cpu_ns':50,
                'raw':name,'raw_sha256':m.sha(path/name),'checks':m.check_outputs(full,value,partial['predictions'][1]['supplied_snapshot_sha256'])})
        pairs.append({'case':case,'median_A_ns':100.,'median_B_ns':100.})
    m.write(path/'ledger.json',ledger)
    receipt={'status':'completed_pure_ABBA_with_validated_partial_suffixes','plan_sha256':m.sha(path/'preregistered_protocol.json'),
        'source_changed':[],'input_changed':[],'native_calls':0,'complete_100ms_certified':False,'candidate_queries':768,
        'full_baselines':24,'timing_samples':deepcopy(ledger),'case_pairs':pairs,'median_A_ns':100.,'median_B_ns':100.,'worker_wall_seconds':1.}
    m.write(path/'receipt.json',receipt)
    m.write(path/'external_process.json',{'status':'worker_exited_zero','plan_sha256':receipt['plan_sha256'],'process':{'status':'exited','exitcode':0}})
    return ledger,receipt


@pytest.mark.parametrize('defect',['none','omitted','reorder','clock_bool','clock_negative','cost_summary','process_failed','altered_raw'])
def test_saved_raw_recheck_rejects_missing_or_tampered_measurements(monkeypatch,tmp_path,defect):
    ledger,receipt=saved_fixture(tmp_path);monkeypatch.setattr(m,'verify_pins',lambda *args:None)
    if defect=='none':assert m.verify_saved(tmp_path)['status']=='saved_24_batches_rechecked';return
    if defect=='omitted':ledger.pop()
    elif defect=='reorder':ledger.reverse()
    elif defect=='clock_bool':ledger[0]['wall_ns']=True
    elif defect=='clock_negative':ledger[0]['cpu_ns']=-1
    elif defect=='cost_summary':receipt['median_A_ns']=1.
    elif defect=='process_failed':m.write(tmp_path/'external_process.json',{'status':'failed_or_unknown'})
    else:(tmp_path/ledger[0]['raw']).write_bytes(b'not raw')
    receipt['timing_samples']=deepcopy(ledger);m.write(tmp_path/'ledger.json',ledger);m.write(tmp_path/'receipt.json',receipt)
    with pytest.raises(ValueError):m.verify_saved(tmp_path)
