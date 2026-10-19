import copy
import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_shadow_planner import ShadowPlanner


def sample(now=57660.):
    return {'now':now,'owner_id':'A','nested':{'unknown':None,'count':91}}, {'now':now,'intents':[{'source':1,'destination':2,'tray_id':'E','issued_at':now}]}


def selected(sequence=0,residual=0,now=57660.):
    obs,decision=sample(now)
    return {'callback':{'owner_id':'A','now':now,'sequence':sequence,'residual_index':residual,
        'request_prefix':'protocol:1' if residual==0 else 'protocol:1:residual'}}


def test_original_objects_and_decision_are_preserved(tmp_path):
    obs,decision=sample();calls=[]
    def baseline(value,**kw):
        assert value is obs;return decision
    def scorer(record):
        calls.append(copy.deepcopy(record));assert record['decision'] is not decision
        assert record['observation'] is not obs;return {'status':'completed_public_shadow_scoring','scores':[1,2,3]}
    p=ShadowPlanner(baseline,scorer,selections=[selected()],branch='C00',business_version='v',path=tmp_path/'events')
    before=copy.deepcopy((obs,decision))
    assert p(obs,request_prefix='protocol:1') is decision
    assert (obs,decision)==before and len(calls)==1
    p.close();report=p.summary()
    assert report['actual_hits']==1 and report['all_shadow_scores_completed']
    assert report['results'][0]['callback_elapsed_before_return_seconds_including_storage']>=0
    assert not report['native_consumption_closed'] and not report['complete_request_100ms_certified']


def test_mutating_scorer_is_failed_but_cannot_mutate_baseline(tmp_path):
    obs,decision=sample();before=copy.deepcopy((obs,decision))
    def scorer(record):
        record['observation']['nested']['count']=0;record['decision']['intents'].clear()
        return {'status':'completed_public_shadow_scoring'}
    p=ShadowPlanner(lambda *_a,**_k:decision,scorer,selections=[selected()],branch='C00',business_version='v',path=tmp_path/'events')
    assert p(obs,request_prefix='protocol:1') is decision
    assert (obs,decision)==before
    p.close();assert p.summary()['results'][0]['status']=='failed'


def test_max_two_exact_callbacks_and_no_exception_retry(tmp_path):
    obs,decision=sample();calls=[]
    def scorer(record):calls.append(record['sequence']);raise RuntimeError('expected')
    p=ShadowPlanner(lambda *_a,**_k:decision,scorer,selections=[selected(),selected(1,1)],
        branch='C00',business_version='v',path=tmp_path/'events')
    for i in range(4):assert p(obs,request_prefix='protocol:1' if i==0 else 'protocol:1:residual') is decision
    p.close();assert calls==[0,1] and p.summary()['actual_hits']==2


def test_identity_mismatch_never_calls_scorer(tmp_path):
    obs,decision=sample();calls=[]
    p=ShadowPlanner(lambda *_a,**_k:decision,lambda record:calls.append(record),selections=[selected(5)],
        branch='C00',business_version='v',path=tmp_path/'events')
    assert p(obs,request_prefix='protocol:1') is decision
    p.close();assert not calls and p.summary()['results'][0]['status']=='failed'


def test_pre_capture_window_does_not_consume_record_sequence(tmp_path):
    obs,decision=sample();p=ShadowPlanner(lambda value,**kw:decision,lambda record:{'status':'completed_public_shadow_scoring'},
        selections=[selected()],branch='C00',business_version='v',path=tmp_path/'events')
    assert p({**obs,'now':0},request_prefix='protocol:0') is decision
    assert p(obs,request_prefix='protocol:1') is decision
    p.close();assert p.summary()['all_shadow_scores_completed']


def test_runtime_future_outcome_payload_and_more_than_two_targets_rejected(tmp_path):
    row=selected();row['first_positive_ack_delay_seconds']=10.
    with pytest.raises(ValueError,match='runtime_identity_only'):
        ShadowPlanner(None,None,selections=[row],branch='C00',business_version='v',path=tmp_path/'a')
    with pytest.raises(ValueError,match='one_or_two'):
        ShadowPlanner(None,None,selections=[selected()]*3,branch='C00',business_version='v',path=tmp_path/'b')
