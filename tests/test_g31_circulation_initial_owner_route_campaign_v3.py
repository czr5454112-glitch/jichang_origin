"""Actual failed-endpoint representations plus failure paths; zero native/model."""
import ast
import copy
import gzip
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign_v3 as c
from scripts.experiments.g31_ics_circulation import initial_owner_route_json_v3 as n
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_campaign_v3 as v
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_campaign_v3 as launch
from scripts.experiments.g31_ics_circulation import native_preexisting_initial_adapter as initial
from tests import test_g31_circulation_initial_owner_route_campaign as prior_tests

FAILED = c.OUT/'initial_owner_route_campaign_prepare_002'


def actual_record():
    ledger=c.read(FAILED/'branch_ledger.json')
    key='normal/block0_load0/fixed_default'
    p=FAILED/'raw'/(key+'.json.gz')
    assert ledger[key]['raw']==c.reference(p)
    raw=json.loads(gzip.decompress(p.read_bytes()))
    return raw['initial_endpoint_records']['A'][0]


def reconstruct(*, binding_tuples):
    record=actual_record();e=copy.deepcopy(record['endpoints'])
    if binding_tuples:
        authority=c.read(c.OUT/'native027_accepted_contract_001.json')
        source=Path(authority['source_archive'])/'cpp/ics_core/bindings/circulation_session_binding.hpp'
        hashes={k.replace('\\','/'):h for k,h in c.read(authority['build_receipt'])['source_after'].items()}
        assert c.sha(source)==hashes['cpp/ics_core/bindings/circulation_session_binding.hpp']
        text=source.read_text()
        assert 'nodes.append(py::make_tuple(n.location,n.node_type,n.service_time,n.x,n.y,n.outgoing));' in text
        assert 'edges.append(py::make_tuple(e.from,e.to,physical.length,physical.speed));' in text
        # Explicit source-shaped reconstruction; saved JSON alone lost tuple type.
        e['view']['node_records']=[tuple(r) for r in e['view']['node_records']]
        e['view']['edge_records']=[tuple(r) for r in e['view']['edge_records']]
    value=initial.validate_pair(e['view'],e['command']['last_delivered_ack'],e['received'])
    assert value['status']=='conditional_validated_data' and value['native_delivery_verified'] is False
    return record,e,value


@pytest.mark.parametrize('binding_tuples',[False,True])
def test_real_saved_endpoints_reconstruct_both_failures_then_exact_wire(binding_tuples):
    record,e,value=reconstruct(binding_tuples=binding_tuples)
    assert all(type(k) is int for k in value['bundle']['resources'])
    assert type(value['bundle']['contract']['node_records'][0]) is (tuple if binding_tuples else list)
    with pytest.raises(ValueError,match='json_non_builtin' if binding_tuples else 'json_non_string_key'):
        c.image.encode(value['bundle'])
    safe=n.normalize(value)
    assert v.exact(safe['bundle'],record['information']['bundle'])
    assert safe['native_delivery_verified'] is False  # No capability minted.
    assert c.image.decode(c.image.encode(safe['bundle']))==safe['bundle']
    assert list(safe['bundle']['resources'])==[str(k) for k in value['bundle']['resources']]


def test_no_value_type_permission_order_or_authority_loss():
    _,_,value=reconstruct(binding_tuples=True)
    safe=n.normalize(value)
    assert json.dumps(value,separators=(',',':'),allow_nan=False)==json.dumps(safe,separators=(',',':'),allow_nan=False)
    assert safe['bundle']['jobs']['loaded']['allow_suffix_reroute'] is True
    safe['bundle']['jobs']['loaded']['allow_suffix_reroute']=False
    assert value['bundle']['jobs']['loaded']['allow_suffix_reroute'] is True
    assert n.normalize(safe)['bundle']['jobs']['loaded']['allow_suffix_reroute'] is False


@pytest.mark.parametrize('mutate',[
    lambda b:b['resources'].update({'0':copy.deepcopy(b['resources'][0])}),
    lambda b:b.update(resources={True:{'node':1}}),
    lambda b:b['resources'].update({1.5:{'node':1}}),
    lambda b:b['resources'].update({'00':{'node':0}}),
    lambda b:b['resources'].update({'١':{'node':1}}),
    lambda b:b['resources'][0].update(node=True),
    lambda b:b['resources'][0].update(node=1),
    lambda b:b.update(extra={0:'not_resources'}),
    lambda b:b.update(extra=float('nan')),
    lambda b:b.update(extra=float('inf')),
    lambda b:b.update(extra={1,2}),
])
def test_normalizer_closed_domain_rejects(mutate):
    _,_,value=reconstruct(binding_tuples=False);b=value['bundle'];mutate(b)
    with pytest.raises(ValueError):n.normalize(b)


def test_cycle_custom_hooks_and_limits_rejected():
    class Custom(dict):
        def items(self):raise AssertionError('custom hook called')
    for value in (Custom(),object()):
        with pytest.raises(ValueError,match='non_builtin'):n.normalize(value)
    cycle=[];cycle.append(cycle)
    with pytest.raises(ValueError,match='cycle'):n.normalize(cycle)
    deep=[];top=deep
    for _ in range(65):child=[];deep.append(child);deep=child
    with pytest.raises(ValueError,match='tree_limit'):n.normalize(top)


def test_native_collector_and_ledger_remain_real_objects(monkeypatch):
    record,e,value=reconstruct(binding_tuples=True)
    value['status']='conditional_native_delivered_model_input';value['native_delivery_verified']=True
    value['native_read']=record['information']['native_read']
    ledger=object()
    class Ledger:
        def audit_copy(self):return {'owner':'A'}
    ledger=Ledger()
    class Session:
        physical_time=.11
        def observe_protocol(self,o):return e['view']
        def protocol_command(self,o,i):return e['command']
        def protocol_planning_snapshots(self,o):return e['received']
    monkeypatch.setattr(c.request.adapter,'collect_initial_ledger',lambda *a,**k:(value,ledger))
    rows=[];safe,actual=c.captured_collection(rows,None,Session(),'A',e['request_id'])
    assert actual is ledger and safe is not value and safe['native_delivery_verified'] is True
    assert type(value['bundle']['contract']['node_records'][0]) is tuple
    assert v.endpoint_replay(rows[0])=='conditional_validated_data'


def test_failed_normalization_retains_captured_rows(monkeypatch):
    record,e,value=reconstruct(binding_tuples=True);value['bad']=float('nan')
    class Session:
        physical_time=.11
        def observe_protocol(self,o):return e['view']
        def protocol_command(self,o,i):return e['command']
        def protocol_planning_snapshots(self,o):return e['received']
    monkeypatch.setattr(c.request.adapter,'collect_initial_ledger',lambda *a,**k:(value,None))
    records=[]
    with pytest.raises(ValueError,match='nonfinite'):c.captured_collection(records,None,Session(),'A',e['request_id'])
    assert len(records)==1 and records[0]['endpoints']['request_id']==e['request_id']


def test_normalized_root_evidence_includes_actual_tuple_endpoints():
    record,e,value=reconstruct(binding_tuples=True)
    root=c.CapturedRequest.__new__(c.CapturedRequest)
    root.request_id='pure';root.started_ns=1;root.deadline_ns=100000001;root.cutoff_ns=60000001
    root.state='unknown_exception';root.choice=root.command_id=root.hop=None
    root.events=[{'stage':'saved_fixture','wall_ns':2,'at':.11,'value':value}]
    root.initial_endpoint_records=[{'information':value,'endpoints':e,'ledger':None}];root.B_endpoint_records=[]
    result=root.evidence()
    assert c.image.artifact_decode(result['encoded'])==result['evidence']
    assert result['body_finished_ns']>=root.started_ns


def test_failure_root_clock_and_typed_data_no_capability():
    root=SimpleNamespace(started_ns=2,events=[{'tuple':(1,2),'dict':{0:'a'}}],information=None,reply=None)
    f=c.failed_root_evidence(root,key='a/b',attempt_started=1,error='injected',endpoint_records={})
    raw={'key':'a/b','root_records':[],'failure':'injected','failed_root_admission':f}
    assert v.root_replay(raw)['closed'] is False
    altered=copy.deepcopy(raw);altered['failed_root_admission']['elapsed_ns']+=1
    with pytest.raises(ValueError,match='clock'):v.root_replay(altered)
    assert 'tuple' in json.dumps(f['typed_builtin_snapshot']) and 'int' in json.dumps(f['typed_builtin_snapshot'])


@pytest.mark.parametrize('closed,fail',[(True,False),(False,True),(False,False)])
def test_cleanup_preserves_abort_and_close_failure(closed,fail):
    class Client:
        def __init__(self):self.closed=closed;self.ledger=[{'original':'retained'}];self.process=SimpleNamespace(poll=lambda:0);self.calls=[]
        def close(self):
            self.calls.append('close')
            if fail:raise ValueError('original_close_error')
            self.closed=True;return {'closed':True}
        def abort(self):self.calls.append('abort');self.closed=True
    p=Client();result=c.close_predictor(p)
    assert result['ledger']==p.ledger and result['cleanup_finished_ns']>=result['close_attempt_started_ns']
    if closed:assert p.calls==[] and result['status']=='unknown_already_aborted'
    elif fail:assert p.calls==['close','abort'] and 'original_close_error' in result['error']
    else:assert result['status']=='closed_protocol'


def life_fixture(status='closed_protocol'):
    ready={'version':'image','mode':'initial_A_two','proof':{'kept':True},'loaded_sources':{'x':'h'}}
    plan={'expected_READY':copy.deepcopy(ready),'image':{'version':'image'}}
    life={'status':status,'ready':ready,'worker_setup_started_ns':0,'construction_attempt_started_ns':0,
        'started_ns':1,'ready_ns':2,'close_attempt_started_ns':3,
        'cleanup_finished_ns':7,'process_exit_code':0,'ledger':[], 'closed_before_close':False,
        'close':{'reply':{'source_unchanged':True,'requests':0},'process_exit_code':0,
                 'close_admitted_ns':4,'close_finished_ns':6}}
    return life,plan


@pytest.mark.parametrize('status',['unknown_already_aborted','unknown_close_failure','unknown_cleanup_failure'])
def test_saved_failure_lifetime_remains_unknown(status):
    life,plan=life_fixture(status)
    if status=='unknown_already_aborted':life['closed_before_close']=True
    else:life['error']='real retained error'
    life.pop('close')
    assert v.predictor_lifetime(life,plan) is False


@pytest.mark.parametrize('mutation',[
    lambda life:life['close']['reply'].update(source_unchanged=False),
    lambda life:life['close']['reply'].update(requests=1),
    lambda life:life.update(process_exit_code=1),
    lambda life:life.update(cleanup_finished_ns=5),
    lambda life:life['ready']['loaded_sources'].clear(),
    lambda life:life.update(status='unknown_close_failure'),
])
def test_saved_lifetime_not_promoted(mutation):
    life,plan=life_fixture();mutation(life)
    with pytest.raises(ValueError):v.predictor_lifetime(life,plan)


def test_failed_predict_call_is_attempted_and_original_error_preserved():
    _,_,information=reconstruct(binding_tuples=True)
    class Predictor:
        sequence=0;closed=False
        def predict(self,*args):
            self.closed=True
            raise ValueError('injected_RPC_failure')
    root=c.CapturedRequest.__new__(c.CapturedRequest)
    root.state='collected';root.predictor=Predictor();root.information=n.normalize(information)
    root.request_id='injected';root.started_ns=1;root.cutoff_ns=60000001;root.deadline_ns=100000001
    root.events=[];root.session=SimpleNamespace(physical_time=.11)
    with pytest.raises(ValueError,match='injected_RPC_failure'):root.choose()
    assert len(root.events)==1 and root.events[0]['stage']=='RPC_attempt'
    a=root.events[0]['value']
    assert a['closed_after'] is True and a['sequence_after']==0 and 'injected_RPC_failure' in a['error']


def test_failure_verifier_binds_all_rows_and_raw_hashes_source():
    text=inspect.getsource(v.verify_saved)
    assert "list(ledger)==plan['row_order']" in text
    assert "row['raw']==c.reference(path)" in text
    assert 'used==set(samples)' in text
    assert "'open_or_unknown_roots':sum(not r['root']['closed']" in text


def test_all_eighteen_failures_remain_declared_and_no_restart():
    assert c.declarations()==c.base.declarations() and len(c.declarations())==18
    text=inspect.getsource(c.worker)
    assert text.count('InitialOwnerClient(')==1
    assert text.index('for key in plan')<text.index('life.update(close_predictor')
    assert "rows[key]['attempt_finished_ns']" in text
    assert launch.LIMIT==600 and launch.MODULE.endswith('initial_owner_route_campaign_v3')


def test_scheduler_and_domain_exact_old_bytecode():
    for name in ('run_continuation','scene','declarations','full_outcome','finish_root','publish_root'):
        assert getattr(c,name).__code__ is getattr(c.base,name).__code__
    assert c.request is c.base.request and c.InitialOwnerClient is c.base.InitialOwnerClient
    assert c.FixedDefaultRequest.choose is c.base.FixedDefaultRequest.choose
    assert v.verify_branch.__code__ is v.old.verify_branch.__code__
    assert v.rpc_replay.__code__ is v.old.rpc_replay.__code__


def test_old124_sources_and_image_remain_exact():
    plan=c.read(FAILED/'campaign.json')
    assert len(plan['source_sha256'])==124
    for path,digest in plan['source_sha256'].items():
        assert c.sha(path)==digest and c.sha(FAILED/plan['source_archive'][path])==digest
    c.image.verify_image(plan['image']['path'],plan['image']['version'])


def test_both_fixes_from_prior_attempt_preserved(monkeypatch):
    text=inspect.getsource(c.run_branch)
    assert "if failure is None and status == 'finished' and session.physical_time == contract.HORIZON:" in text
    assert text.index('session.result_at')>text.index('if failure is None')
    prior_tests.test_final_validation_replays_pre_submit_choice_before_overrun(monkeypatch)


@pytest.mark.parametrize('resources',[
    {0:{'node':0},'1':{'node':1}},
    {'0':{'node':0},1:{'node':1}},
    {0:{'node':0},'0':{'node':0}},
])
def test_all_mixed_resource_key_types_rejected_even_without_alias(resources):
    with pytest.raises(ValueError,match='mixed_resource_keys'):
        n.normalize({'status':'conditional_model_input','contract':{},'resources':resources})


@pytest.mark.parametrize('resources',[
    {0:{'node':0},1:{'node':1}},
    {'0':{'node':0},'1':{'node':1}},
])
def test_homogeneous_resource_keys_normalize_idempotently(resources):
    result=n.normalize({'status':'conditional_model_input','contract':{},'resources':resources})
    assert list(result['resources'])==['0','1'] and n.normalize(result)==result


@pytest.mark.parametrize('field,value',[
    ('node',(0,)), ('mode',('loaded',)), ('generation',(1,)),
    ('service_ready_known',(True,)),
])
def test_tuple_conversion_cannot_bypass_original_dynamic_guard(field,value):
    # Execute only the exact input guard, never Projection.run or a prediction.
    from scripts.experiments.g31_ics_circulation import public_preference_request_context as context
    _,_,information=reconstruct(binding_tuples=True)
    bundle=information['bundle'];bundle['trays']['L'][field]=value
    normalized=n.normalize(bundle)
    assert type(normalized['trays']['L'][field]) is list
    validate,_,_=context.compile_guards()
    try:
        verdict=validate(normalized)
    except (ValueError,TypeError,KeyError,AttributeError):
        return
    assert type(verdict) is dict and verdict['status'].startswith('unknown_')


@pytest.mark.parametrize('key',[
    'worker_setup_started_ns','construction_attempt_started_ns','started_ns','ready_ns',
    'close_attempt_started_ns','cleanup_finished_ns','close.close_admitted_ns','close.close_finished_ns',
])
@pytest.mark.parametrize('value',[True,1.0,-1])
def test_every_predictor_lifetime_clock_is_exact_nonnegative_int(key,value):
    life,plan=life_fixture()
    target=life
    if key.startswith('close.'):
        target=life['close'];key=key.split('.')[1]
    target[key]=value
    with pytest.raises(ValueError,match='clock'):v.predictor_lifetime(life,plan)


def test_no_ready_setup_failure_is_unknown_and_still_checks_available_clocks():
    life={'status':'unknown_predictor_construction','ledger':[], 'worker_setup_started_ns':1,
        'construction_attempt_started_ns':2,'cleanup_finished_ns':3,'worker_setup_or_loop_failure':'real constructor failure'}
    assert v.predictor_lifetime(life,{}) is False
    for k in ('worker_setup_started_ns','construction_attempt_started_ns','cleanup_finished_ns'):
        bad=copy.deepcopy(life);bad[k]=True
        with pytest.raises(ValueError,match='clock'):v.predictor_lifetime(bad,{})


def missing_raw_fixture(monkeypatch):
    life,plan=life_fixture()
    life['close_attempt_started_ns']=1000
    life['cleanup_finished_ns']=1004
    life['close'].update(close_admitted_ns=1001,close_finished_ns=1003)
    rows=c.declarations()
    plan.update(rows=rows,row_order=list(rows))
    ledger={k:{**row,'status':'unknown_failed','exception':'retained before raw error',
        'attempt_started_ns':10+i*10,'attempt_finished_ns':15+i*10} for i,(k,row) in enumerate(rows.items())}
    reference={'path':'synthetic/campaign.json','sha256':'fixture'}
    accepted={'status':'closed_run_acceptance_passed','active':False,'invalid':[],
        'branch_keys':sorted(rows),'run_reference':reference,'evidence_sha256':{}}
    files={'branch_ledger.json':ledger,'predictor_lifetime.json':life,'run_acceptance.json':accepted}
    monkeypatch.setattr(c,'verify_plan',lambda *a:plan)
    monkeypatch.setattr(c,'read',lambda p:files[Path(p).name])
    monkeypatch.setattr(c,'reference',lambda p:reference)
    return ledger,life


def test_all_eighteen_missing_raw_failures_retain_branch_time_not_root_time(monkeypatch,tmp_path):
    ledger,_=missing_raw_fixture(monkeypatch)
    report=v.verify_saved(tmp_path,'fixture')
    assert report['branches']==report['open_or_unknown_roots']==18 and report['closed_roots']==0
    for key,row in report['rows'].items():
        assert row['root']['warm_ms'] is None
        assert row['branch_attempt']['elapsed_ms']==5/1e6
        assert row['branch_attempt']['started_ns']==ledger[key]['attempt_started_ns']


@pytest.mark.parametrize('mutation',[
    lambda r:r.pop('attempt_started_ns'),
    lambda r:r.pop('attempt_finished_ns'),
    lambda r:r.update(attempt_started_ns=True),
    lambda r:r.update(attempt_finished_ns=15.0),
    lambda r:r.update(attempt_started_ns=-1),
    lambda r:r.update(attempt_started_ns=16),
    lambda r:r.update(attempt_finished_ns=1001),
])
def test_missing_raw_attempt_clock_malformed_rejected_by_full_saved_path(monkeypatch,tmp_path,mutation):
    ledger,_=missing_raw_fixture(monkeypatch)
    mutation(next(iter(ledger.values())))
    with pytest.raises(ValueError,match='branch_attempt_clock'):v.verify_saved(tmp_path,'fixture')


def test_branch_attempt_order_and_unexecuted_differ(monkeypatch,tmp_path):
    ledger,life=missing_raw_fixture(monkeypatch)
    second=ledger[list(ledger)[1]];second['attempt_started_ns']=14
    with pytest.raises(ValueError,match='branch_attempt_order'):v.verify_saved(tmp_path,'fixture')
    assert v.branch_attempt({'status':'unknown_unexecuted'},life)['elapsed_ms'] is None
    with pytest.raises(ValueError,match='unexecuted_has_attempt_clock'):
        v.branch_attempt({'status':'unknown_unexecuted','attempt_started_ns':3},life)


def test_frozen_v2_sources_preserved():
    directory=c.OUT/'initial_owner_route_campaign_v2_prepare_001'
    plan=c.read(directory/'campaign.json')
    assert len(plan['source_sha256'])==129
    for path,digest in plan['source_sha256'].items():
        assert c.sha(path)==digest and c.sha(directory/plan['source_archive'][path])==digest
