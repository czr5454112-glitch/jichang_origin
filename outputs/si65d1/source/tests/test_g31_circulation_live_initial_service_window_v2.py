"""Real saved endpoint schemas and fake native origin; no native/model run."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_initial_decision_adapter_v2 as a
from scripts.experiments.g31_ics_circulation import live_obligation_initial_recorded_adapter_v2 as r
from scripts.experiments.g31_ics_circulation import research_live_initial_six_seam_v2 as c

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_initial_six_seam_prepare_001'
RAW={
    'mechanism':'aa645b88027b51008b44a06ed214492edc928c947597fdd2ce88e50526b3b36e',
    'no_overlap':'ee976ca304c0828be97092ab99bf7777a81344332733b2a3991cfac111845308',
    'insufficient_advance':'24ba3530b3197796388edeaab53cc1647706bb190bf570107793ea875eff7e2d'}


@pytest.fixture(scope='session')
def actual_rows():
    result={}
    for case,digest in RAW.items():
        raw=(BASE/'raw'/case/'initial.json.gz').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
        result[case]=json.loads(gzip.decompress(raw))
    return result


def pair(actual_rows,case='mechanism'):
    row=actual_rows[case]['owners']['A']
    return copy.deepcopy(row['initial_decision']['public']),copy.deepcopy(row['supplied_context']['payload']['validated'])


@pytest.mark.parametrize('case',list(RAW))
def test_exact_actual_schema_uses_validated_bound_not_absent_sensor(actual_rows,case):
    public,_=pair(actual_rows,case)
    tray=next(t for t in public['view']['trays'] if t['tray_id']=='L')
    assert 'service_ready_known' not in tray and 'service_ready_at' not in tray
    before=a.history.payload_encoding(public)
    value=a.route_window_from_public(public)
    assert value['derived_earliest_source_service_end']==1.1
    assert value['current_loaded_at']==.1 and value['wire_seconds']==.01 and value['at']==.11
    assert value['exact_current_service_end_observed'] is False and value['native_authority'] is False
    assert a.history.payload_encoding(public)==before
    assert actual_rows[case]['owners']['A']['status']=='unknown_fresh_current_guard'


@pytest.mark.parametrize('mutation',[
    'missing_transition','duplicate_transition','wrong_source','wrong_current_generation','bool_generation',
    'wrong_traversal','already_committed','reception_reserved','wrong_prefix','wrong_job',
    'wrong_node','wrong_current_mode','wrong_loaded_at','wrong_job_status','future_load_completion',
    'unknown_load','wrong_ready_kind','mismatched_load_bound','wrong_transition_capture',
    'wrong_transition_epoch','wrong_transition_finish','wrong_transition_direction',
    'nonfinite_bound','bool_bound','nonfinite_service','bool_service'])
def test_typed_derivation_rejects_missing_changed_future_or_uncommitted_contract(actual_rows,mutation):
    public,v=pair(actual_rows);view=public['view'];t=next(x for x in view['trays'] if x['tray_id']=='L')
    j=next(x for x in view['jobs'] if x['business_bag_id']=='loaded')
    cap=v['envelopes']['A']['capture'];prior=next(x for x in cap['trays'] if x['tray_id']=='L')
    transition=v['conditional_projection'][0]
    if mutation=='missing_transition':v['conditional_projection']=[]
    elif mutation=='duplicate_transition':v['conditional_projection']*=2
    elif mutation=='wrong_source':transition['source']='B'
    elif mutation=='wrong_current_generation':t['generation']+=1
    elif mutation=='bool_generation':t['generation']=True
    elif mutation=='wrong_traversal':t['traversal_id']+=1
    elif mutation=='already_committed':t['edge_to']=2
    elif mutation=='reception_reserved':t['reception_node']=2
    elif mutation=='wrong_prefix':t['committed_prefix']=[0,2]
    elif mutation=='wrong_job':t['business_bag_id']='reuse1'
    elif mutation=='wrong_node':t['node']=2
    elif mutation=='wrong_current_mode':t['mode']='loading'
    elif mutation=='wrong_loaded_at':j['loaded_at']=.09
    elif mutation=='wrong_job_status':j['status']='completed'
    elif mutation=='future_load_completion':prior['load_complete_at']=.2
    elif mutation=='unknown_load':prior['service_ready_known']=False
    elif mutation=='wrong_ready_kind':prior['ready_kind']='committed_local_service_end'
    elif mutation=='mismatched_load_bound':prior['service_ready_at']=.09
    elif mutation=='wrong_transition_capture':transition['source_captured_at']=.05
    elif mutation=='wrong_transition_epoch':transition['projected_at']=.1
    elif mutation=='wrong_transition_finish':transition['source_known_load_complete_at']=.09
    elif mutation=='wrong_transition_direction':transition['from_mode']='empty'
    elif mutation=='nonfinite_bound':transition['first_possible_source_service_end']=float('nan')
    elif mutation=='bool_bound':transition['first_possible_source_service_end']=True
    elif mutation=='nonfinite_service':view['node_records'][0][2]=float('inf')
    elif mutation=='bool_service':view['node_records'][0][2]=True
    # Keep the supplied own selfcopy relation consistent when testing a deeper
    # typed failure. This helper still grants no source/native authority.
    v['own_delivered_ack']=copy.deepcopy(public['command']['last_delivered_ack'])
    v['own_delivered_ack']['planning_snapshot']=copy.deepcopy(v['envelopes']['A'])
    public['command']['last_delivered_ack']=copy.deepcopy(v['own_delivered_ack'])
    with pytest.raises((ValueError,KeyError,TypeError)):a.route_window_from_validated(public,v)


@pytest.mark.parametrize('offset,accepted',[(.019,False),(.12-.1,False),(.021,True)])
def test_strict_wire_boundary_without_epsilon(actual_rows,offset,accepted):
    public,v=pair(actual_rows);public['view']['node_records'][0][2]=offset
    v['conditional_projection'][0]['first_possible_source_service_end']=.1+offset
    if accepted:assert a.route_window_from_validated(public,v)['derived_earliest_source_service_end']>.12
    else:
        with pytest.raises(ValueError,match='strict_earliest'):a.route_window_from_validated(public,v)


@pytest.mark.parametrize('mutation',['changed_service','capture_digest','missing_own_ack','undelivered_own_ack','expired_capture'])
def test_full_old_data_guard_still_rejects_changed_public_contract(actual_rows,mutation):
    public,_=pair(actual_rows);ack=public['command']['last_delivered_ack']
    if mutation=='changed_service':public['view']['node_records'][0][2]=.021
    elif mutation=='capture_digest':ack['planning_snapshot']['payload_sha256']='0'*64
    elif mutation=='missing_own_ack':public['command']['last_delivered_ack']={}
    elif mutation=='undelivered_own_ack':ack['delivered_at']=.12
    elif mutation=='expired_capture':ack['planning_snapshot']['status']='expired'
    with pytest.raises(ValueError,match='full_fresh_initial_guard'):a.route_window_from_public(public)


@pytest.fixture
def fake_origin(monkeypatch,actual_rows):
    class Session:
        def __init__(self,data):
            self.case=data['fixture_case'];self.physical_time=0.;self.requests={};self.reads=[];self.view_counts={};self.fail=None
            self.problem=ValueError('actual-shaped getter failure')
        def advance_to(self,at):self.physical_time=at
        def submit_protocol_command(self,request):self.requests[request['request_id']]=copy.deepcopy(request);return {'status':'accepted'}
        def public(self,owner):return actual_rows[self.case]['owners'][owner]['initial_decision']['public']
        def observe_protocol(self,owner):
            self.reads.append(('view',owner));self.view_counts[owner]=self.view_counts.get(owner,0)+1
            if self.fail==(owner,self.view_counts[owner]):raise self.problem
            return copy.deepcopy(self.public(owner)['view'])
        def protocol_command(self,owner,key):
            self.reads.append(('command',owner,key))
            return copy.deepcopy(next(x for x in self.public(owner)['view']['client_commands'] if x['request_id']==key))
        def protocol_planning_snapshots(self,owner):
            self.reads.append(('received',owner));return copy.deepcopy(self.public(owner)['received'])
    monkeypatch.setattr(a.native_gate,'_valid_handle',lambda *args:True)
    monkeypatch.setattr(a.native_gate,'bind_native027',lambda *args,**kwargs:({'status':'fake_origin_actual_saved_schema'},object()))
    return SimpleNamespace(Session=Session,native=SimpleNamespace(NativeSession=Session,_g31_native_artifact_identity={'fake':True}))


@pytest.mark.parametrize('case',list(RAW))
def test_fake_origin_actual_schema_routes_through_new_guard_and_saved_verifier(fake_origin,case):
    spec=c.declaration()[case+'/initial'];accepted=SimpleNamespace(active_for=lambda k:True,branch_specification=lambda k:spec)
    raw=c.run_case(fake_origin.native,spec,{'fixture_case':case},{},accepted_run=accepted,branch_key=case+'/initial')
    assert raw['status']=='complete_six_scope_case'
    assert all(row['status']=='initial_seam_validated' for row in raw['owners'].values())
    assert len(raw['calls'])==4 and raw['physical_requests_submitted']==raw['model_predictions']==0
    assert c.verify_saved(c.data(raw),spec,{'fixture_case':case})['known_initial_domains']==2


@pytest.mark.parametrize('attempt',[1,2])
def test_actual_shaped_failed_endpoint_prefix_still_unknown(fake_origin,attempt):
    class Failed(fake_origin.Session):
        def __init__(self,data):super().__init__(data);self.fail=('A',attempt)
    native=SimpleNamespace(NativeSession=Failed,_g31_native_artifact_identity={'fake':True})
    spec=c.declaration()['mechanism/initial'];accepted=SimpleNamespace(active_for=lambda k:True,branch_specification=lambda k:spec)
    raw=c.run_case(native,spec,{'fixture_case':'mechanism'},{},accepted_run=accepted,branch_key='mechanism/initial')
    assert raw['owners']['A']['status'].startswith('unknown')
    assert raw['owners']['A']['journal']['records'][-1]['endpoints'][-1]['status']=='raised'
    assert c.verify_saved(c.data(raw),spec,{'fixture_case':'mechanism'})['unknown_initial_domains']==1


def test_exact_source_replacements_leave_old_modules_unchanged():
    old=a.previous.revalidate_first_component;old_globals=dict(old.__globals__)
    assert a.source_proof()['inverse_AST_one_guard_replacement']
    assert r.source_proof()['journal_code_and_endpoint_count_unchanged']
    assert c.source_proof()['old173_preserved']
    assert old.__globals__==old_globals
    assert c.worker.__code__ is c.previous.worker.__code__
    collect,refresh,_=r.make_functions(r.EndpointJournal())
    assert refresh.__code__ is a.revalidate_first_component.__code__
    assert refresh.__globals__['collect_initial_decision'] is collect


def test_source_transform_rejects_another_missing_field_use(monkeypatch):
    old=a.inspect.getsource
    def changed(fn):
        text=old(fn)
        if fn is a.previous.revalidate_first_component:text=text.replace("now+.01<tray['service_ready_at']","now+.02<tray['service_ready_at']")
        return text
    monkeypatch.setattr(a.inspect,'getsource',changed)
    with pytest.raises(ValueError,match='one_missing_field_guard'):a.refresh_code()


def test_prepare_final_fields_exist_at_first_write_before_verify_and_ready(tmp_path):
    from types import FunctionType
    output=tmp_path/'prepared';events=[];writes={};proof={'synthetic_integration':True}
    def hash_file(path):
        path=Path(path)
        if path.name=='tests.xml':return 'xml'
        if path.name=='receipt.json':return 'pure_receipt'
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'synthetic_pin'
    def reference(path):return {'path':str(path),'sha256':hash_file(path)}
    def read(path):
        path=Path(path)
        if path==c.DIAGNOSIS:return {'rows':[{'case':case,'raw':reference('synthetic_raw_'+case)} for case in c.CASES]}
        if path.name=='receipt.json':return {'status':'passed','tests':c.EXPECTED_TESTS,'source_changed':[],
            'source_sha256':{},'XML_sha256':'xml'}
        if path.name=='bounded_parent_receipt.json':return {'status':'passed','receipt_sha256':'pure_receipt'}
        if path.name=='external_application_wall.json':return {'exitcode':0,'external_application_seconds':1.}
        if path.name=='vector_16.json':return {'case':path.parent.name}
        return json.loads(path.read_bytes())
    def write(path,value):
        path=Path(path);events.append('write:'+path.name);writes[path.name]=copy.deepcopy(value)
        if path.name=='plan.json':
            assert value['integration_source_proof']==proof and 'frozen173' in value['references']
            assert all('actual_schema_'+case in value['references'] for case in c.CASES)
        path.write_text(json.dumps(value,allow_nan=False),encoding='utf8')
    def verify(path,plan):
        events.append('verify');assert path==output and read(path/'plan.json')==plan
        assert plan['integration_source_proof']==proof and events[-2]=='write:plan.json'
    hook_ns={**c._complete_plan.__globals__,'source_proof':lambda:proof,'reference':reference,'read':read}
    hook=FunctionType(c._complete_plan.__code__,hook_ns,c._complete_plan.__name__)
    namespace={**c._prepare.__globals__,'source_gate':lambda:{'binary':{},'native_contract_reference':{},'semantic_gate_reference':{}},
        'source_files':lambda:{},'read':read,'write':write,'sha':hash_file,'reference':reference,
        'ET':SimpleNamespace(parse=lambda p:SimpleNamespace(getroot=lambda:SimpleNamespace(findall=lambda x:[[] for _ in range(c.EXPECTED_TESTS)]))),
        'recorded':SimpleNamespace(source_proof=lambda:{'synthetic':True}),
        'declaration':lambda:{key:{'case':case} for key,case in zip(c.KEYS,c.CASES,strict=True)},
        'fixture':SimpleNamespace(native_scene=lambda case:{'case':case}),
        '_complete_plan':hook,'verify_plan':verify}
    fn=FunctionType(c._prepare.__code__,namespace,c._prepare.__name__)
    fn(output)
    assert events.count('write:plan.json')==1 and events[-2:]==['verify','write:ready.json']
    ready=writes['ready.json'];assert ready['execute_command'][2].endswith('.launch_live_initial_six_seam_v2')
    assert ready['plan']['sha256']==ready['execute_command'][-1]==hash_file(output/'plan.json')
