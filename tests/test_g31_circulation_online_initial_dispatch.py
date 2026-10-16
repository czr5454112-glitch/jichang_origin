"""Unexecuted synthetic dispatch-seam tests; no real model/native call."""
import copy
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_online_initial_dispatch as subject


def fixture(owner='A', *, collection_unknown=False, selection_unknown=False,
            guard_unknown=False, native_error=None, bad_lineage=False, native_default=False,
            actual_transport_failure=None, clock=None, broken_evidence=False):
    events=[]
    session=SimpleNamespace(physical_time=.11)
    class Decision:
        _digest='public';_at=.11;_ledger=object()
        def audit_copy(self):return {'owner':owner,'public_sha256':self._digest,'at':self._at}
    decision=Decision()
    action={'initial_action':'native_default' if native_default else 'prefer_2',
        'empty_departure':.2,'return_delay':0.,'later_action':'native_default'}
    component=({'kind':'no_command_native_default','actual_next_unknown':True} if native_default else
        {'kind':'route','tray_id':'L','business_bag_id':'loaded','from':0,'next':2,
         'expected_generation':1,'expected_traversal':2,'expiry':5.,'message_delay':.01}) if owner=='A' else {
        'kind':'transfer','tray_id':'E','source':5,'destination':1,
        'earliest_departure':.2,'expiry':39.,'message_delay':.01}
    class Client:
        def __init__(self):
            self.context={'owner':owner,'root_id':'current:'+owner}
            self.rows={}
            self.creations={'publication':{'creating_root':'publication:'+owner}}
        def submit(self, actual_owner, kind, label, *, causal, **payload):
            events.append('submit')
            assert actual_owner==owner and label=='online-initial'
            if native_error:raise native_error
            identity='submitted:'+owner
            request={'request_id':identity,'owner_id':owner,**payload}
            if kind!='transfer':request['kind']=kind
            self.rows[identity]={'kind':kind,'request':request,'reply':{'status':'accepted'}}
            self.creations[identity]={'creating_root':'wrong' if bad_lineage else self.context['root_id'],
                'kind':kind,'causal':copy.deepcopy(causal)}
            return identity
    client=Client()
    if actual_transport_failure:
        # Execute the actual two submit methods and base send with a synthetic
        # session. No native object/model is constructed or imported here.
        from scripts.experiments.g31_ics_circulation.research_native_preexisting_v3_bound import LocalTransport
        class Reply(dict):
            def __deepcopy__(self, memo):raise native_error
        class Session:
            physical_time=.11
            def __getattribute__(self,name):
                if name in ('submit_protocol_command','submit_protocol_transfer') and actual_transport_failure=='getter':
                    events.append('native_getter');raise native_error
                return object.__getattribute__(self,name)
            def submit_protocol_command(self,payload):
                events.append('native_call')
                if actual_transport_failure=='method':raise native_error
                return Reply(status='accepted')
            submit_protocol_transfer=submit_protocol_command
        session=Session()
        client=LocalTransport(session)
        client.context={'owner':owner,'root_id':'current:'+owner,'protocol_ids':[]}
        client.creations['publication']={'creating_root':'publication:'+owner}
    def collect(*args):
        events.append('collect')
        assert args[2:5]==(owner,'publication',client)
        return {'status':'unknown','reason':'unsupported'} if collection_unknown else decision
    def propose(actual,**kwargs):
        events.append('full32')
        assert actual is decision and kwargs['incumbent_index']==0
        return {'selected_action':None if selection_unknown else copy.deepcopy(action),
            'method':kwargs['method'],'restriction':kwargs['restriction']}
    def revalidate(actual, vector):
        events.append('recollect')
        assert actual is decision and vector==action
        return {'status':'unknown'} if guard_unknown else {'status':'fresh_local_component_proposal',
            'owner':owner,'public_sha256':'public','at':.11,'component':copy.deepcopy(component)}
    def current(actual):
        events.append('current')
        assert actual is decision
    ns={**subject.choose_and_submit.__globals__,
        'origin':SimpleNamespace(InitialDecision=Decision,collect_initial_decision=collect,
            revalidate_first_component=revalidate,require_current=current),
        'search':SimpleNamespace(propose_initial=propose)}
    if clock is not None:ns['time']=SimpleNamespace(perf_counter_ns=clock)
    if broken_evidence:
        def fail_evidence(*args):raise OSError('synthetic evidence export')
        ns['_failed_submission']=fail_evidence
    fn=FunctionType(subject.choose_and_submit.__code__,ns,subject.choose_and_submit.__name__,
        subject.choose_and_submit.__defaults__,subject.choose_and_submit.__closure__)
    fn.__kwdefaults__=subject.choose_and_submit.__kwdefaults__
    progress={}
    return lambda arm='finite_MPC':fn(object(),session,client,owner,'publication',object(),
        arm=arm,incumbent_index=0,progress=progress),events,progress,client,decision


@pytest.mark.parametrize('owner',('A','B'))
def test_own_collection_current_recheck_and_immutable_submission(owner):
    invoke,events,progress,client,decision=fixture(owner)
    result,ledger=invoke()
    assert events==['collect','full32','recollect','current','submit']
    assert result is progress and ledger is decision._ledger
    assert progress['native_request_id']=='submitted:'+owner
    assert progress['submission']['creation']['causal']['continuation_parent_roots']==['publication:'+owner]
    assert not progress['native_physical_execution_certified']
    assert not progress['complete_request_100ms_certified']
    assert progress['started_ns']<=progress['submission_started_ns']<=progress['submission_returned_ns']<=progress['finished_ns']


def test_native_default_is_no_command_and_no_claimed_physical_success():
    invoke,events,progress,client,decision=fixture(native_default=True)
    _,ledger=invoke()
    assert events==['collect','full32','recollect','current'] and not client.rows
    assert progress['status']=='selected_native_default_no_command'
    assert progress['native_default_no_command'] and progress['native_request_id'] is None
    assert ledger is decision._ledger and progress['selected_action']['initial_action']=='native_default'


@pytest.mark.parametrize(('option','status','events'),(
    ('collection_unknown','unknown_initial_collection',['collect']),
    ('selection_unknown','unknown_no_admissible_estimate',['collect','full32']),
    ('guard_unknown','unknown_final_local_guard',['collect','full32','recollect'])))
def test_unknowns_remain_no_submission(option,status,events):
    invoke,actual,progress,client,_=fixture(**{option:True})
    invoke()
    assert actual==events and progress['status']==status and not client.rows
    assert progress['finished_ns']>=progress['started_ns']


def test_native_exception_propagates_exact_object_with_progress():
    error=RuntimeError('synthetic native submit failure')
    invoke,events,progress,_,_=fixture(native_error=error)
    with pytest.raises(RuntimeError) as caught:invoke()
    assert caught.value is error and events.count('submit')==1
    assert progress['stage']=='immediate_dispatch' and progress['error_type']=='RuntimeError'
    assert progress['selected_action'] is not None and progress['finished_ns']>=progress['started_ns']


def test_post_submission_lineage_failure_keeps_actual_identity_and_no_retry():
    invoke,events,progress,client,_=fixture(bad_lineage=True)
    with pytest.raises(ValueError,match='actual_creation_lineage'):invoke()
    assert progress['native_request_id']=='submitted:A' and events.count('submit')==1
    assert 'submitted:A' in client.rows
    assert progress['status']=='unknown_raised_dispatch_outcome_unconfirmed'


@pytest.mark.parametrize('arm',tuple(subject.ARMS))
def test_all_seven_arms_use_same_full32_seam(arm):
    invoke,events,progress,_,_=fixture()
    invoke(arm)
    assert events.count('full32')==1
    assert (progress['selection']['method'],progress['selection']['restriction'])==subject.ARMS[arm]
    assert progress['online_rolling_reestimation'] is False


@pytest.mark.parametrize('owner',('A','B'))
@pytest.mark.parametrize('boundary',('getter','method','reply_copy'))
def test_actual_transport_row_survives_failure_before_local_submit_returns(owner,boundary):
    error=RuntimeError('synthetic transport boundary')
    invoke,events,progress,client,_=fixture(owner,native_error=error,actual_transport_failure=boundary)
    with pytest.raises(RuntimeError) as caught:invoke()
    identity=f'live:1:{owner}:online-initial'
    assert caught.value is error and progress['native_request_id']==identity
    assert progress['new_own_request_ids_after_error']==[identity]
    assert progress['partial_submission']['local_row']['request']==client.rows[identity]['request']
    assert not progress['partial_submission']['creation_present']
    assert not progress['partial_submission']['reply_present']
    assert not progress['partial_submission']['physical_execution_certified']
    assert progress['dispatch_outcome']=='unknown_no_inference_from_missing_reply'
    assert identity not in client.creations and client.calls==[]
    assert events.count('native_call')==(0 if boundary=='getter' else 1)
    assert events.count('native_getter')==(1 if boundary=='getter' else 0)
    assert progress['intended_creation']['causal']['continuation_parent_roots']==['publication:'+owner]


@pytest.mark.parametrize('with_native_error',(False,True))
def test_final_clock_failure_preserves_primary_or_raises_clock(with_native_error):
    native_error=RuntimeError('native primary') if with_native_error else None
    clock_error=OSError('final clock')
    calls=[]
    def clock():
        calls.append(None)
        if len(calls)==(3 if with_native_error else 4):raise clock_error
        return len(calls)*100
    invoke,events,progress,client,_=fixture(native_error=native_error,clock=clock)
    with pytest.raises(BaseException) as caught:invoke()
    assert caught.value is (native_error or clock_error)
    assert events.count('submit')==1 and progress['call_wall_ms'] is None
    assert progress['status']=='unknown_incomplete_instrumentation'
    assert progress['instrumentation_complete'] is False
    assert progress['instrumentation_errors']==[{'phase':'final_clock','error_type':'OSError'}]
    if not with_native_error:assert progress['native_request_id']=='submitted:A'


def test_failed_evidence_copy_preserves_primary_error_and_sticky_unknown():
    error=RuntimeError('native primary')
    invoke,events,progress,_,_=fixture(native_error=error,broken_evidence=True)
    with pytest.raises(RuntimeError) as caught:invoke()
    assert caught.value is error and events.count('submit')==1
    assert progress['instrumentation_complete'] is False
    assert progress['instrumentation_errors']==[{'phase':'failed_submission_evidence','error_type':'OSError'}]
