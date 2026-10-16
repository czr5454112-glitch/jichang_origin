import copy
import pytest
from scripts.experiments.g31_ics_circulation import measure_json_prediction_service as measure


def plan():
    return {'schema':measure.SCHEMA,'hard_timeout_seconds':120.,'native_calls':0,
        'worker_order':list(measure.ORDER),'candidate_queries_per_valid_request':32,'full_baselines':24,
        'requests':24,'candidate_queries':768,'cases':[{'case':c,'input':c+'.json'} for c in measure.CASES],
        'input':{'sha256':measure.INPUT_SHA},'source_sha256':{'scripts/a.py':'0'*64},'image':{'directory':'image'}}


@pytest.mark.parametrize('field,value',[('hard_timeout_seconds',121.),('native_calls',1),('worker_order',['compiled']),
    ('requests',23),('candidate_queries',767),('full_baselines',23),('candidate_queries_per_valid_request',31)])
def test_plan_denominators_fixed(field,value):
    value_plan=plan();value_plan[field]=value
    with pytest.raises(ValueError):measure.check_plan(value_plan)


def test_plan_exact_case_order_and_safe_archive_paths():
    value=plan();measure.check_plan(value)
    value['cases'].reverse()
    with pytest.raises(ValueError):measure.check_plan(value)
    value=plan();value['source_sha256']={'../a.py':'0'*64}
    with pytest.raises(ValueError):measure.check_plan(value)


def payload():
    return {'baseline':{'status':'conditional_prediction'},'actions':[{} for _ in range(32)],
            'predictions':[{'status':'conditional_prediction'} for _ in range(32)]}


@pytest.mark.parametrize('defect',['fewer_actions','fewer_predictions','unknown','partial_complete','unknown_baseline'])
def test_all32_and_original_partial_status_only(defect):
    value=payload()
    if defect=='fewer_actions':value['actions'].pop()
    elif defect=='fewer_predictions':value['predictions'].pop()
    elif defect=='unknown':value['predictions'][0]['status']='unknown'
    elif defect=='partial_complete':value['predictions'][0]['status']='complete_prefix'
    else:value['baseline']['status']='unknown'
    with pytest.raises(ValueError):measure.check_payload(value)


def sample():
    return {'request_id':'id','sequence':1,'caller_admitted_ns':100,'caller_decoded_ns':200,
        'caller_body_finished_ns':210,'caller_bookkeeping_ns':10,'caller_elapsed_ns':110,
        'cold_through_reply_ns':130,'outer_admitted_ns':90,'outer_returned_ns':220,'complete_caller_elapsed_ns':130,
        'request':{'kind':'predict','version':'v','sequence':1,'request_id':'id','snapshot':{}},
        'response':{'kind':'prediction','version':'v','sequence':1,'request_id':'id','payload':payload(),
                    'compute_wall_ns':90,'native_authority':False,'complete_100ms_certified':False}}


@pytest.mark.parametrize('defect',['bool_clock','wrong_elapsed','negative_compute','outside_compute','old_version','wrong_snapshot','replayed_id'])
def test_actual_RPC_identity_and_nested_clock_boundaries(defect):
    value=sample();measure.check_sample(value,{},'id',1,'v')
    if defect=='bool_clock':value['caller_admitted_ns']=True
    elif defect=='wrong_elapsed':value['caller_elapsed_ns']=99
    elif defect=='negative_compute':value['response']['compute_wall_ns']=-1
    elif defect=='outside_compute':value['response']['compute_wall_ns']=111
    elif defect=='old_version':value['response']['version']='old'
    elif defect=='wrong_snapshot':value['request']['snapshot']={'cached':'older'}
    else:value['response']['request_id']='older'
    with pytest.raises(ValueError):measure.check_sample(value,{},'id',1,'v')


@pytest.mark.parametrize('defect',['missing_tail','before_return','wrong_total','backward_body'])
def test_tail_and_outside_return_are_required(defect):
    value=sample()
    if defect=='missing_tail':value.pop('outer_returned_ns')
    elif defect=='before_return':value['outer_returned_ns']=205
    elif defect=='wrong_total':value['complete_caller_elapsed_ns']=110
    else:value['caller_body_finished_ns']=190
    with pytest.raises(ValueError):measure.check_sample(value,{},'id',1,'v')


def test_six_legal_wire_frames_use_separate_bounded_artifact_format(monkeypatch):
    codec=measure.codec
    frame={'snapshot':'字'*200000}
    assert len(codec.encode(frame))<codec.MAX_FRAME_BYTES
    record={'samples':[frame for _ in range(6)]}
    with pytest.raises(ValueError,match='frame_limit'):codec.encode(record)
    raw=codec.artifact_encode(record)
    assert len(raw)>codec.MAX_FRAME_BYTES
    assert codec.artifact_decode(raw)==record
    monkeypatch.setattr(codec,'MAX_ARTIFACT_BYTES',10)
    with pytest.raises(ValueError,match='artifact_limit'):codec.artifact_encode(record)
    with pytest.raises(ValueError,match='artifact_limit'):codec.artifact_decode(raw)


def test_pure_receipt_binds_actual_XML_and_exact_count(tmp_path):
    path=tmp_path/'tests.xml'
    path.write_text('<testsuite>'+''.join('<testcase name="t'+str(n)+'"/>' for n in range(measure.EXPECTED_PURE_TESTS))+'</testsuite>')
    receipt={'status':'passed','source_changed':[],'native_calls':0,'tests':measure.EXPECTED_PURE_TESTS,'XML_sha256':measure.sha(path)}
    measure.check_pure_gate(tmp_path,receipt)
    for field,value in [('tests',measure.EXPECTED_PURE_TESTS-1),('XML_sha256','0'*64),('source_changed',['x'])]:
        changed={**receipt,field:value}
        with pytest.raises(ValueError):measure.check_pure_gate(tmp_path,changed)
    path.write_text(path.read_text().replace('<testcase name="t0"/>','<testcase name="t0"><skipped/></testcase>'))
    receipt['XML_sha256']=measure.sha(path)
    with pytest.raises(ValueError):measure.check_pure_gate(tmp_path,receipt)


def test_source_closure_includes_client_worker_bootstrap_tests_and_src_backend():
    files=measure.closure()
    for name in ('src/czr005/cpp_backend.py', 'scripts/experiments/g31_ics_circulation/json_prediction_worker.py',
        'scripts/experiments/g31_ics_circulation/json_prediction_client.py',
        'scripts/experiments/g31_ics_circulation/json_prediction_image.py',*measure.TEST_NAMES):
        assert name in files


@pytest.mark.parametrize('defect',['remove_guard','remove_model','changed_proof'])
def test_READY_complete_loaded_closure_and_proof_not_subset(defect):
    gate={'loaded_sources':{'guard.py':'a','model.py':'b'},'proof':{'guard_compilations':1,'AST':'fixed'}}
    ready={'kind':'ready','version':'v','mode':'compiled','native_authority':False,
        'loaded_sources':dict(gate['loaded_sources']),'proof':dict(gate['proof']),'startup_post_import_wall_ns':10}
    measure.check_ready(ready,gate,'v','compiled')
    if defect=='remove_guard':ready['loaded_sources'].pop('guard.py')
    elif defect=='remove_model':ready['loaded_sources'].pop('model.py')
    else:ready['proof']['AST']='other'
    with pytest.raises(ValueError,match='closure_or_proof'):measure.check_ready(ready,gate,'v','compiled')
