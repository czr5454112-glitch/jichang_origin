"""Lossless public recording and bounded controller parity; no native imports."""
import copy
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_observations as old_recorder
from scripts.experiments.g31_ics_circulation import foundation_airport_observations_v2 as recorder
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol as old_protocol
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as protocol


def observation(now=43200.):
    ledger=[{'request_id':str(i),'value':i,'nested':{'nullable':None,'status':'received'}} for i in range(150)]
    return {'now':now,'owner_id':'A','node_records':[[i,1.,4] for i in range(151)],
        'trays':[],'client_transfer_ledger':ledger,'transfers':ledger,
        'control_projection':{'waiting_groups':[{'group_id':'g','count':73}]}}


def normalize(row):
    row=copy.deepcopy(row);row.pop('schema');return row


def test_lossless_old_format_parity_and_original_actor_objects(tmp_path):
    old=old_recorder.Recorder(tmp_path/'old.jsonl.gz',branch='C00',business_version='v')
    new=recorder.Recorder(tmp_path/'new.jsonl.gz',branch='C00',business_version='v')
    seen=[]
    def planner(obs,**options):
        seen.append((id(obs),options));return {'now':obs['now'],'intents':[],'supplies':[],'mixed':[True,1,1.,None]}
    for i in range(4):
        obs=observation(43200+i*60);obs['client_transfer_ledger'][65]['value']=i
        expected_id=id(obs);a=old.wrap(planner)(obs,predictive=True);b=new.wrap(planner)(obs,predictive=True)
        assert seen[-2][0]==seen[-1][0]==expected_id and a==b
    old.close();new.close()
    with gzip.open(old.path,'rt',encoding='utf-8') as f:before=[json.loads(line) for line in f]
    after=list(recorder.read_records(new.path))
    assert [normalize(x) for x in after]==[normalize(x) for x in before]
    assert new.summary()['record_count']==4
    assert new.summary()['uncompressed_blob_bytes']+new.summary()['uncompressed_reference_bytes'] < sum(len(json.dumps(x)) for x in before)
    assert [type(x) for x in after[0]['decision']['mixed']]==[bool,int,float,type(None)]


def test_snapshot_precedes_planner_mutation_and_numeric_types_do_not_alias(tmp_path):
    sink=recorder.Recorder(tmp_path/'rows.jsonl.gz',branch='C00',business_version='v')
    decisions=[]
    def mutating(obs,**options):
        obs['client_transfer_ledger'][0]['nested']['status']='mutated'
        answer={'now':obs['now'],'intents':[],'supplies':[]};decisions.append(answer);return answer
    for value in (1,True,1.):
        obs=observation();obs['client_transfer_ledger'][0]['value']=value
        assert sink.wrap(mutating)(obs) is decisions[-1]
    sink.close();rows=list(recorder.read_records(sink.path))
    assert [type(r['observation']['client_transfer_ledger'][0]['value']) for r in rows]==[int,bool,float]
    assert all(r['observation']['client_transfer_ledger'][0]['nested']['status']=='received' for r in rows)
    rows[0]['observation']['client_transfer_ledger'][1]['value']=-1
    assert list(recorder.read_records(sink.path))[0]['observation']['client_transfer_ledger'][1]['value']==1


def test_capture_window_does_not_create_records_or_modify_decision(tmp_path):
    sink=recorder.Recorder(tmp_path/'rows.jsonl.gz',branch='C00',business_version='v');answer={'same':True}
    for at in (43199.,59401.):assert sink.wrap(lambda obs,**kw:answer)(observation(at)) is answer
    sink.close();assert list(recorder.read_records(sink.path))==[] and sink.summary()['record_count']==0


def test_complete_member_partial_recovery_and_hash_rejection(tmp_path):
    sink=recorder.Recorder(tmp_path/'rows.jsonl.gz',branch='C00',business_version='v')
    for i in range(2):sink.wrap(lambda obs,**kw:{'now':obs['now']})(observation(43200+i))
    sink.close();members=list(recorder.members(sink.path));assert len(members)==2
    sink.path.write_bytes(gzip.compress(members[0],mtime=0)+gzip.compress(members[1],mtime=0)[:-5])
    assert len(list(recorder.read_records(sink.path,allow_partial=True)))==1
    with pytest.raises(ValueError,match='incomplete_gzip_member'):list(recorder.read_records(sink.path))
    blobs=list(recorder.members(sink.blobs_path));wrong=json.loads(blobs[0]);wrong['sha256']='0'*64
    sink.blobs_path.write_bytes(gzip.compress(recorder.encoded(wrong),mtime=0)+b''.join(gzip.compress(x,mtime=0) for x in blobs[1:]))
    with pytest.raises(ValueError,match='blob_hash_mismatch'):list(recorder.read_records(sink.path,allow_partial=True))


class Session:
    def __init__(self,budget_fail=False):self.physical_time=0.;self.trace=[];self.submitted=False;self.budget_fail=budget_fail
    def advance_to(self,time,max_events):
        self.trace.append(('advance',time,max_events));self.physical_time=time
        return {'status':'budget_exhausted' if self.budget_fail else 'reached','horizon_complete':not self.budget_fail,'processed_events':1}
    def protocol_demand_signature(self,owner):return 's'
    def result_at(self,horizon):
        assert horizon==self.physical_time;self.trace.append(('result',horizon))
        return {'physical_clock':horizon,'advance':{'status':'reached','horizon_complete':True}}


class Client:
    def __init__(self,session,**options):self.session=session;self.state=copy.deepcopy(options.get('state')) or {'outbox':{}};self.calls=[]
    def refresh(self):self.session.trace.append(('refresh',self.session.physical_time));return []
    def _policy_view(self,owner,compact):return {'now':self.session.physical_time,'owner_id':owner,'has_supply':not self.session.submitted}
    def submit(self,owner,kind,payload):
        self.session.trace.append(('submit',owner,kind,copy.deepcopy(payload)));self.session.submitted=True
        row={'owner':owner,'kind':kind,'request':payload};self.calls.append(row)
        return 'r',{'status':'pending'}


def planner(obs,**options):return {'now':obs['now'],'intents':[{'tray_id':'E'}] if obs['has_supply'] else []}


@pytest.fixture
def mock_client(monkeypatch):
    for module in (old_protocol,protocol):
        monkeypatch.setattr(module,'ProtocolClient',Client)
        monkeypatch.setattr(module,'_publish_services',lambda *a,**kw:[])


def test_controller_endpoint_order_is_identical_without_soft_stop(mock_client):
    a,b=Session(),Session()
    options={'horizon':180.,'control_period':60.,'planner':planner,'planner_identity':'identical'}
    old=old_protocol.run_airport_protocol_control(a,['A'],**options)
    new=protocol.run_airport_bounded_protocol_control(b,['A'],soft_deadline=1000.,soft_clock=lambda:0.,**options)
    assert a.trace==b.trace and old['client_calls']==new['client_calls']
    assert old['controller_state']==new['controller_state']
    old_result,new_result=copy.deepcopy(old['result']),copy.deepcopy(new['result'])
    new_result['control_continuation'].pop('timestamp_complete')
    new_result['control_continuation'].pop('next_control_tick_pending')
    assert old_result==new_result
    assert old['status']==new['status']=='reached'


def test_soft_stop_is_before_control_tick_and_snapshots_only_actual_time(mock_client):
    session=Session();times=iter((0.,10.))
    result=protocol.run_airport_bounded_protocol_control(session,['A'],horizon=3600.,control_period=60.,
        planner=planner,planner_identity='same',soft_deadline=5.,soft_clock=lambda:next(times))
    assert result['status']=='soft_deadline_reached' and result['result']['physical_clock']==60.
    assert result['controller_state']['next_tick']==1 and result['controller_state']['control_boundary_complete']
    assert result['control_continuation']['timestamp_complete'] and result['control_continuation']['next_control_tick_pending']
    assert ('result',60.) in session.trace and ('result',3600.) not in session.trace
    assert ('refresh',60.) not in session.trace


def test_native_budget_stop_is_never_repaired_by_result_at(mock_client):
    session=Session(budget_fail=True)
    result=protocol.run_airport_bounded_protocol_control(session,['A'],horizon=60.,planner=planner,planner_identity='same',
        soft_deadline=0.,soft_clock=lambda:10.)
    assert result['status']=='budget_exhausted' and result['result'] is None
    assert not any(row[0]=='result' for row in session.trace)


def test_campaign_soft_partial_is_saved_with_actual_snapshot(monkeypatch,tmp_path):
    from scripts.experiments.g31_ics_circulation import foundation_airport_recorded_campaign as campaign
    from scripts.experiments.g31_ics_circulation import original_workload,run_original_protocol
    monkeypatch.setattr(campaign.legacy,'segment_targets',lambda:[0.,3600.])
    monkeypatch.setattr(original_workload,'summarize_execution',lambda data,result:{'physical_clock':result['physical_clock']})
    monkeypatch.setattr(run_original_protocol,'request_ledger',lambda calls,views:{'request_count':0})
    class PartialSession:
        physical_time=0.
        def observe_protocol(self,owner):return {'owner_id':owner,'now':self.physical_time}
    session=PartialSession();data={'node_contracts':[{'resource_owner':'A'}],'jobs':[{},{}]}
    def controller(session,owners,**options):
        assert options['soft_deadline']==240 and options['event_budget']==100000
        session.physical_time=0. if options['horizon']==0 else 60.
        return {'status':'reached' if options['horizon']==0 else 'soft_deadline_reached',
            'result':{'physical_clock':session.physical_time,'jobs':[{},{}]},'client_calls':[],'controller_state':{}}
    raw=campaign.execute_bounded_continuous(session,data,{'soft_stop_seconds':240,'controller':{},
        'protocol_input_semantic_sha256':'same'},tmp_path,controller=controller,clock=lambda:0.)
    assert raw['status']=='censored_before_requested_window_end' and raw['last_snapshot_is_actual_stop']
    assert raw['last_complete_snapshot_time']==raw['final_physical_time']==60.
    assert raw['session_instance_count']==1 and raw['physical_reset_count']==0 and raw['offered_count']==2
    records=[json.loads(line) for line in (tmp_path/'progress.jsonl').read_text().splitlines()]
    assert records[-1]['status']=='soft_deadline_reached' and records[-1]['target']==3600.
    assert records[-1]['actual_clock']==60. and (tmp_path/'segment_01.json.gz').exists()


def test_new_recording_campaign_preserves_native_input_and_resource_contract():
    from scripts.experiments.g31_ics_circulation import foundation_airport_recorded_campaign as campaign
    from scripts.experiments.g31_ics_circulation import foundation_airport_event_budget_campaign as prior
    from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as domain
    data=domain.build_full_input()[0]
    assert campaign.apply_policy(data)==prior.apply_policy(data)
    assert campaign.resource_contract()==prior.resource_contract()
    assert campaign.policy_contract()==prior.policy_contract()
    assert campaign.legacy.CONTROLLER==prior.legacy.CONTROLLER
    assert campaign.legacy.BOUNDARIES==prior.legacy.BOUNDARIES
    assert campaign.soft_checkpoint_contract()['control_trace_changed_when_deadline_never_fires'] is False
