from __future__ import annotations
import ast
import copy
import io
import json
import os
from pathlib import Path
import threading
import time
import pytest
from scripts.experiments.g31_ics_circulation import json_prediction_image as codec
from scripts.experiments.g31_ics_circulation import json_prediction_shard_image as image
from scripts.experiments.g31_ics_circulation import json_prediction_worker as old_worker
from scripts.experiments.g31_ics_circulation import json_prediction_shard_worker as worker
from scripts.experiments.g31_ics_circulation import json_prediction_client as original_client
from scripts.experiments.g31_ics_circulation import json_prediction_shard_client as client
from scripts.experiments.g31_ics_circulation import measure_json_prediction_shards as measure


def supplied():
    assert measure.sha(measure.INPUT)==measure.INPUT_SHA
    return [r['bundle'] for r in json.loads(measure.INPUT.read_bytes()) if r['owner']=='A']


@pytest.fixture(scope='module')
def engines():
    return old_worker.Engine('compiled'), worker.Engine('shard0',codec), worker.Engine('shard1',codec)


@pytest.mark.parametrize('index',range(6))
def test_exact_actual_six_complete_baseline_and_all32_labels(index,engines):
    reference,left,right=engines;snapshot=supplied()[index]
    expected=reference.predict(snapshot)
    parts=[left.predict(snapshot),right.predict(snapshot)]
    assert [p['candidate_queries'] for p in parts]==[16,16]
    assert [p['physical_baselines'] for p in parts]==[1,1]
    assert codec.encode(client.merge(parts,snapshot))==codec.encode(expected)
    assert set(left.__dict__)=={'mode','codec','context','proof'}
    assert set(right.__dict__)=={'mode','codec','context','proof'}


def test_changed_inputs_results_and_no_potential_label_cache(engines):
    _,left,right=engines;one,two=supplied()[0],supplied()[5]
    initial=codec.encode(client.merge([left.predict(one),right.predict(one)],one))
    parts=[left.predict(one),right.predict(one)];merged=client.merge(parts,one)
    merged['baseline']['completion'].clear();merged['predictions'][0].clear()
    assert parts[0]['baseline']['completion']
    left.predict(two);right.predict(two)
    assert codec.encode(client.merge([left.predict(one),right.predict(one)],one))==initial
    assert left.proof['guard_compilations']==right.proof['guard_compilations']==1


@pytest.mark.parametrize('defect',['pending','resource','generation','missing'])
def test_fresh_dynamic_guards_each_shard(defect,engines):
    reference,left,right=engines;value=copy.deepcopy(supplied()[0])
    if defect=='pending':value['owner_pending_tray_requests']=['pending']
    elif defect=='resource':value['resources']['0']['occupancy']+=1
    elif defect=='generation':value['trays']['L']['generation']=False
    else:value['jobs'].pop('receiver')
    baseline=reference.predict(value)
    for engine in (left,right):
        result=engine.predict(value)
        assert result['baseline']==baseline['baseline']
        assert result['actions']==result['ordinals']==result['predictions']==[]
    with pytest.raises(ValueError):client.merge([left.predict(value),right.predict(value)],value)


def parts():
    actions=[{'i':i} for i in range(32)]
    return [{'baseline':{'status':'conditional_prediction'},'actions':copy.deepcopy(actions),
        'predictions':[{'status':'conditional_prediction','i':i} for i in range(n*16,(n+1)*16)],
        'ordinals':list(range(n*16,(n+1)*16)),'snapshot_sha256':codec.sha_bytes(codec.encode({})),
        'action_domain_sha256':codec.sha_bytes(codec.encode(actions)),
        'physical_baselines':1,'candidate_queries':16} for n in range(2)]


@pytest.mark.parametrize('defect',['missing_shard','reversed_shards','ordinal_duplicate','ordinal_bool','missing_row',
    'baseline','domain_order','snapshot','hash','baseline_bool','candidate_count','extra_field'])
def test_merge_fails_closed(defect):
    value=parts()
    if defect=='missing_shard':value.pop()
    elif defect=='reversed_shards':value.reverse()
    elif defect=='ordinal_duplicate':value[1]['ordinals'][0]=15
    elif defect=='ordinal_bool':value[0]['ordinals'][0]=False
    elif defect=='missing_row':value[0]['predictions'].pop()
    elif defect=='baseline':value[1]['baseline']['changed']=True
    elif defect=='domain_order':
        value[1]['actions'].reverse();value[1]['action_domain_sha256']=codec.sha_bytes(codec.encode(value[1]['actions']))
    elif defect=='snapshot':value[0]['snapshot_sha256']='0'*64
    elif defect=='hash':value[0]['action_domain_sha256']='0'*64
    elif defect=='baseline_bool':value[0]['physical_baselines']=True
    elif defect=='candidate_count':value[1]['candidate_queries']=15
    else:value[0]['cached_result']={}
    with pytest.raises((ValueError,KeyError)):client.merge(value,{})


def test_image_AST_only_version_entry_and_own_closure_change():
    old=ast.parse(Path(codec.__file__).read_text(encoding='utf-8-sig'))
    new=ast.parse(Path(image.__file__).read_text(encoding='utf-8-sig'))
    replacements={image.SCHEMA:codec.SCHEMA,image.ENTRY:codec.ENTRY,
        'scripts.experiments.g31_ics_circulation.json_prediction_shard_image':'scripts.experiments.g31_ics_circulation.json_prediction_image'}
    for node in ast.walk(new):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value in replacements:
            node.value=replacements[node.value]
    assert ast.dump(new,include_attributes=False)==ast.dump(old,include_attributes=False)
    for method in ('_reader','_next','predict','close','abort','_expire'):
        assert getattr(client.ShardClient,method) is getattr(original_client.Client,method)


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}\n',b'{"x":NaN}\n',b'{"x":Infinity}\n',b'{"x":1e999}\n',b'{}',b'{}\n{}\n'])
def test_new_wire_same_strict_JSON(raw):
    with pytest.raises(ValueError):image.decode(raw)


@pytest.mark.parametrize('defect',['subset','exec','old_version','sequence_bool','replay','close_extra'])
def test_old_closed_protocol_reused_without_new_exec_subset_channel(defect):
    class Fake:
        def predict(self,value):return {'safe':True}
    protocol=old_worker.Protocol('v',Fake(),image)
    request={'kind':'predict','version':'v','sequence':1,'request_id':'id','snapshot':{}}
    if defect=='subset':request['ordinals']=[0]
    elif defect=='exec':request['kind']='exec'
    elif defect=='old_version':request['version']='old'
    elif defect=='sequence_bool':request['sequence']=True
    elif defect=='replay':protocol.accept(request)
    else:request={'kind':'close','version':'v','sequence':1,'extra':0}
    with pytest.raises(ValueError):protocol.accept(request)


def fake_logical(clients):
    value=client.LogicalClient.__new__(client.LogicalClient)
    value.arm='split';value.started_ns=time.perf_counter_ns();value.clients=clients
    value.ledger=[];value.closed=False;value.cleanup_errors=[]
    return value


def test_first_shard_failure_aborts_other_and_entire_request_unknown():
    stopped=threading.Event()
    class Failed:
        def predict(self,*args):raise ValueError('injected_original')
        def abort(self):stopped.set()
    class Waiting:
        def predict(self,*args):
            assert stopped.wait(2)
            raise EOFError('owned_cleanup')
        def abort(self):stopped.set()
    value=fake_logical([Failed(),Waiting()])
    with pytest.raises(RuntimeError,match='unknown_shard_failure'):
        value.predict('id',{})
    assert value.closed and value.ledger==[] and stopped.is_set()
    with pytest.raises(ValueError,match='closed'):value.predict('again',{})


def test_cleanup_attempts_every_owned_child_preserves_primary_error():
    called=[]
    class Bad:
        def predict(self,*args):raise ValueError('primary')
        def abort(self):called.append('bad');raise OSError('cleanup')
    class Good:
        def predict(self,*args):raise ValueError('secondary')
        def abort(self):called.append('good')
    value=fake_logical([Bad(),Good()])
    with pytest.raises(RuntimeError,match='unknown_shard_failure'):value.predict('id',{})
    assert 'good' in called and value.cleanup_errors


def fixed_plan():
    return {'schema':measure.SCHEMA,'round_order':list(measure.ORDER),'logical_requests':24,
        'physical_worker_processes':6,'physical_RPC_requests':36,'physical_full_baselines':36,
        'candidate_queries':768,'candidate_queries_per_logical_request':32,'hard_timeout_seconds':120.,'native_calls':0,
        'shards':{'shard0':list(range(16)),'shard1':list(range(16,32))},
        'input':{'sha256':measure.INPUT_SHA},'cases':[{'case':c,'input':c+'.json'} for c in measure.CASES],
        'source_sha256':{'scripts/a.py':'0'*64},'images':{'single':{'directory':'image_single'},'split':{'directory':'image_split'}}}


def test_campaign_real_path_plan_reaches_first_constructor_without_prediction(tmp_path,monkeypatch):
    plan=fixed_plan()
    for key in ('single','split'):
        plan['images'][key]['version']='fixed-'+key
    measure.check_plan(plan)
    measure.write(tmp_path/'preregistered_protocol.json',plan)
    checked=[]
    monkeypatch.setattr(measure,'verify_pins',lambda output,value: checked.append((output,value)))
    calls=[]
    class ReachedFirstClient(RuntimeError):
        pass
    def stop_before_process(arm,images,*,timeout,stderrs,startup_attempts):
        calls.append((arm,images))
        assert arm=='single' and len(stderrs)==1 and startup_attempts==[] and timeout>0
        assert images=={key:{'path':tmp_path/('image_'+key),'version':'fixed-'+key}
                       for key in ('single','split')}
        raise ReachedFirstClient('intentional_no_worker_no_prediction')
    monkeypatch.setattr(measure,'LogicalClient',stop_before_process)
    with pytest.raises(ReachedFirstClient,match='intentional_no_worker_no_prediction'):
        measure.campaign(tmp_path,measure.sha(tmp_path/'preregistered_protocol.json'))
    assert checked==[(tmp_path,plan)] and len(calls)==1
    assert measure.read(tmp_path/'ledger.json')==[
        {'round':i,'arm':arm,'status':'unknown_failed' if i==0 else 'unknown_unexecuted'}
        for i,arm in enumerate(measure.ORDER)]
    prefix=measure.read(tmp_path/'0.failed_prefix.json')
    assert prefix['samples']==prefix['partial_worker_samples']==prefix['startup_attempts']==[]
    assert not list(tmp_path.glob('*.json.gz'))


@pytest.mark.parametrize('field,value',[('logical_requests',23),('physical_worker_processes',4),('physical_RPC_requests',24),
    ('physical_full_baselines',24),('candidate_queries',767),('hard_timeout_seconds',121.),('round_order',['single','split']),
    ('candidate_queries_per_logical_request',31)])
def test_fixed_denominators_including_duplicated_baselines(field,value):
    plan=fixed_plan();measure.check_plan(plan);plan[field]=value
    with pytest.raises(ValueError):measure.check_plan(plan)


def sample():
    workers=[];halves=parts()
    for i,part in enumerate(halves):
        workers.append({'request_id':'id:'+str(i),'sequence':1,'caller_admitted_ns':110+i,
            'caller_decoded_ns':190,'caller_body_finished_ns':200,'caller_elapsed_ns':90-i,
            'caller_bookkeeping_ns':10,'cold_through_reply_ns':150,
            'request':{'kind':'predict','version':'b','sequence':1,'request_id':'id:'+str(i),'snapshot':{}},
            'response':{'kind':'prediction','version':'b','sequence':1,'request_id':'id:'+str(i),
                'payload':part,'compute_wall_ns':80,'native_authority':False,'complete_100ms_certified':False}})
    return {'request_id':'id','arm':'split','outer_admitted_ns':90,'caller_admitted_ns':100,'all_replies_ns':210,
        'caller_body_finished_ns':220,'outer_returned_ns':230,'caller_elapsed_ns':120,'complete_caller_elapsed_ns':140,
        'snapshot':{},'worker_samples':workers,'merged_payload':client.merge(halves,{}),
        'physical_baselines':2,'candidate_queries':32,'sum_worker_compute_ns':160}


@pytest.mark.parametrize('defect',['clock_bool','caller_tail','nested_cost','sumcost','wrong_id','wrong_version','one_worker','merge_change'])
def test_saved_cost_merge_and_RPC_binding(defect):
    value=sample();measure.check_sample(value,{},'id',1,'split',{'single':'a','split':'b'})
    if defect=='clock_bool':value['all_replies_ns']=True
    elif defect=='caller_tail':value['outer_returned_ns']=215
    elif defect=='nested_cost':value['worker_samples'][0]['response']['compute_wall_ns']=91
    elif defect=='sumcost':value['sum_worker_compute_ns']=80
    elif defect=='wrong_id':value['worker_samples'][1]['response']['request_id']='old'
    elif defect=='wrong_version':value['worker_samples'][1]['request']['version']='old'
    elif defect=='one_worker':value['worker_samples'].pop()
    else:value['merged_payload']['predictions'][0]['i']=1
    with pytest.raises(ValueError):measure.check_sample(value,{},'id',1,'split',{'single':'a','split':'b'})


@pytest.fixture(scope='module')
def images(tmp_path_factory):
    root=tmp_path_factory.mktemp('si')
    return {key:{'path':root/key,'version':module.build_image(measure.ROOT,root/key)}
        for key,module in (('single',codec),('split',image))}


@pytest.mark.parametrize('mode',['compiled','shard0','shard1'])
def test_actual_functional_startup_complete_loaded_source_proof_and_close(mode,images,tmp_path):
    key='single' if mode=='compiled' else 'split'
    cls=original_client.Client if key=='single' else client.ShardClient
    with (tmp_path/'stderr.log').open('w') as stderr:
        value=cls(images[key]['path'],images[key]['version'],mode,timeout=30,stderr=stderr)
        ready=copy.deepcopy(value.ready);shutdown=value.close()
    assert ready['proof']['guard_compilations']==1 and shutdown['reply']['requests']==0
    assert ready['loaded_sources'] and shutdown['reply']['source_unchanged']
    target=os.environ.get('G31_SHARD_FUNCTIONAL_OUTPUT')
    if target:
        measure.write(Path(target)/('startup_'+mode+'.json'),{'schema':'g31.json_shards_functional_startup.v1',
            'mode':mode,'version':images[key]['version'],'loaded_sources':ready['loaded_sources'],
            'proof':ready['proof'],'source_unchanged':True,'closed_requests':0})


def test_actual_two_process_RPC_A_B_A_exact_isolated_and_cleanup(images,tmp_path,engines):
    expected=engines[0];snapshots=[supplied()[0],supplied()[5],supplied()[0]]
    with (tmp_path/'s0.log').open('w') as a,(tmp_path/'s1.log').open('w') as b:
        value=client.LogicalClient('split',images,timeout=40,stderrs=[a,b])
        for n,snapshot in enumerate(snapshots):
            got=value.predict('functional-'+str(n),snapshot)
            assert codec.encode(got['payload'])==codec.encode(expected.predict(snapshot))
            got['payload']['baseline'].clear()
            assert value.ledger[-1]['merged_payload']['baseline']
        shutdown=value.close()
    assert len(value.ledger)==3 and all(c.process.poll()==0 for c in value.clients)
    assert all(c.shutdown['reply']['requests']==3 for c in value.clients)
    assert shutdown['closed_and_reclaimed_ns']>=shutdown['close_admitted_ns']


def test_bounded_artifact_retains_duplicated_worker_payloads():
    record={'samples':[sample() for _ in range(6)]}
    assert codec.artifact_decode(codec.artifact_encode(record))==record


def test_new_closure_keeps_old_and_new_entry_model_client_and_tests():
    files=measure.closure()
    for name in ('json_prediction_worker.py','json_prediction_client.py','json_prediction_image.py',
                 'json_prediction_shard_worker.py','json_prediction_shard_client.py','json_prediction_shard_image.py'):
        assert 'scripts/experiments/g31_ics_circulation/'+name in files
    assert 'src/czr005/cpp_backend.py' in files
    assert measure.TEST_NAMES[0] in files
