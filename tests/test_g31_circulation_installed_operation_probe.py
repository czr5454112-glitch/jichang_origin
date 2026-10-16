from copy import deepcopy
import json
import subprocess
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import probe_installed_operations as probe
from scripts.experiments.g31_ics_circulation import verify_installed_operations as verifier
from scripts.experiments.g31_ics_circulation.rolling_request_lineage import RequestLineage


def fixture():
    lineage=RequestLineage()
    lineage.accept('root',scope='business_task_update',owner='A',trigger_id='no_action:root',trigger_kind='predeclared_public_epoch',relation='independent_offer',
        completion_contract={'kind':'one_shot_update','goal_id':'finite','terminal_failure_allowed':True},jobs=('B1',),at=.11,wall_ns=110)
    lineage.observe('root',references=[],at=.11,wall_ns=120)
    lineage.seal('root',disposition='no_action',classification_complete=True,at=.11,wall_ns=130)
    lineage.drain('root',timestamp_complete=True,at=.11,wall_ns=140)
    lineage.output('root',at=.11,wall_ns=150)
    native_view={'owner_id':'A','now':.11,'jobs':[{'business_bag_id':'B1'}],'trays':[],'client_transfer_ledger':[]}
    view={**native_view,'transfers':[]}
    drain={'status':'reached','horizon_complete':True,'physical_time':.11,'wall_seconds':.0001}
    returned={'status':'returned','drain':drain,'output':json.dumps({'root':'root','disposition':'no_action','decisions':[]})}
    tape=[{'ordinal':1,'endpoint':'advance_to','args':[.11],'kwargs':{'max_events':100000},'start_ns':65,'end_ns':75,
        'physical_before':0.,'physical_after':.11,'result':drain},
        {'ordinal':2,'endpoint':'observe_protocol','args':['A'],'kwargs':{},'start_ns':122,'end_ns':124,
        'physical_before':.11,'physical_after':.11,'result':native_view},
        {'ordinal':3,'endpoint':'advance_to','args':[.11],'kwargs':{'max_events':100000},'start_ns':135,'end_ns':139,
        'physical_before':.11,'physical_after':.11,'result':drain}]
    return {'case':'no_action','roots':{'root':{'start_ns':100,'end_ns':160,'job':'B1','parents':[],
            'observation_call_ordinal':2,'drain_call_ordinal':3,'returned_output':json.dumps(returned)}},
        'setup_intervals':[{'start_ns':0,'end_ns':50},{'start_ns':60,'end_ns':90}],'ended_ns':170,
        'root_reports':{'root':{**lineage.summary('root'),'job_scope_verified':True}},'lineage':lineage.roots,
        'protocol_lineage':{},'outbox':{},'admission_views':{'root':view},
        'observations':{'root':{'view_sha256':probe._digest(view),'returned_at':.11,'returned_wall_ns':125}},
        'failures':[],'decisions':[],'service_tape':tape,'calls':[],'physical_time':.11,
        'timing':{'envelopes':[{'api_endpoint':r['endpoint'],'start_ns':r['start_ns'],'end_ns':r['end_ns']} for r in tape], 'errors':[]}}


def test_whole_lifetime_plus_shared_setup_is_not_divided_or_phase_subtracted():
    result=probe.analyze_case(fixture())
    assert result['status']=='complete_declared_operation_accounting'
    assert result['roots']['root']['complete_compute_upper_ns']==140
    assert result['within100ms_complete_count']==1
    assert result['physics_or_gc_subtracted_ns']==0
    assert result['original_business_request_100ms_certified'] is False


@pytest.mark.parametrize('defect',['missing_root','negative_clock','reversed_setup','overlapping_setup','premature_return',
    'native_call_after_return','native_call_in_diagnostic_setup','wrong_job','missing_drain','changed_view','faked_job_scope','extra_outbox'])
def test_missing_causal_or_interval_coverage_is_unknown(defect):
    raw=fixture()
    if defect=='missing_root':raw['roots']={}
    elif defect=='negative_clock':raw['roots']['root']['start_ns']=-1
    elif defect=='reversed_setup':raw['setup_intervals'][0]['end_ns']=-1
    elif defect=='overlapping_setup':raw['setup_intervals'][1]['start_ns']=40
    elif defect=='premature_return':raw['roots']['root']['end_ns']=149
    elif defect=='native_call_after_return':raw['timing']['envelopes'].append({'start_ns':161,'end_ns':165})
    elif defect=='native_call_in_diagnostic_setup':raw['timing']['envelopes'].append({'start_ns':51,'end_ns':55})
    elif defect=='wrong_job':raw['roots']['root']['job']='other'
    elif defect=='missing_drain':raw['lineage']['root']['mandatory_drain']=None
    elif defect=='changed_view':raw['admission_views']['root']['jobs']=[]
    elif defect=='faked_job_scope':raw['root_reports']['root']['job_scope_verified']=False
    else:raw['outbox']['unknown']={'kind':'route'}
    assert probe.analyze_case(raw)['status']=='unknown_invalid_or_incomplete_accounting'


def test_failures_and_open_roots_never_gain_complete_bounds():
    raw=fixture();raw['failures']=['captured failure']
    result=probe.analyze_case(raw)
    assert result['closed_count']==0 and result['roots']['root']['complete_compute_upper_ns'] is None


def test_declared_domain_keeps_retries_cancel_no_action_and_missing_ack():
    contract=probe.contract()
    assert contract['root_count']==9
    assert set(contract['cases'])==set(probe.CASES)
    assert 'ack_still_missing' in contract['cases'] and 'no_action' in contract['cases']
    assert contract['cases']['cancel_pending']==['root','cancel']


def test_route_candidate_uses_only_public_owned_job_and_tray():
    view={'now':.11,'jobs':[{'business_bag_id':'B1','storage_node':2,'storage_released_at':-1.,'destination':4}],
        'trays':[{'business_bag_id':'B1','mode':'loaded','edge_to':-1,'node':0,'tray_id':'T0','generation':1,'traversal_id':0}],
        'node_records':[[0,1,.05],[1,1,.05],[2,1,.05],[4,1,.05],[6,1,.05]],
        'edge_records':[[0,1,1.,1.],[0,6,1.2,1.],[1,2,1.,1.],[6,2,1.,1.],[2,4,1.,1.]]}
    original=deepcopy(view)
    payload,candidates=probe.route_candidate(view,'B1',wire=.01)
    assert payload['next']==1 and payload['business_bag_id']=='B1' and len(candidates)==2
    assert view==original
    view['trays'][0]['edge_to']=1
    assert probe.route_candidate(view,'B1',wire=.01)==(None,[])


@pytest.mark.parametrize('defect', ['deleted_call','reordered_call','unrecorded_submit','fake_drain','wrong_observation',
    'missing_sequence','negative_logical','mutated_final_disposition','wrong_envelope','false_output','foreign_trigger'])
def test_independent_tape_and_lineage_replay_fail_closed(defect):
    raw=fixture()
    if defect=='deleted_call':raw['service_tape'].pop()
    elif defect=='reordered_call':raw['service_tape'].reverse()
    elif defect=='unrecorded_submit':raw['calls'].append({'request':{}})
    elif defect=='fake_drain':raw['service_tape'][2]['result']={**raw['service_tape'][2]['result'],'horizon_complete':False}
    elif defect=='wrong_observation':raw['service_tape'][1]['result']['jobs']=[]
    elif defect=='missing_sequence':raw['lineage']['root']['accepted']['sequence']=9
    elif defect=='negative_logical':raw['lineage']['root']['accepted']['at']=-1.
    elif defect=='mutated_final_disposition':raw['lineage']['root']['decision_seal']['disposition']='fake'
    elif defect=='wrong_envelope':raw['timing']['envelopes'][1]['api_endpoint']='protocol_command'
    elif defect=='false_output':raw['roots']['root']['returned_output']=json.dumps({'status':'returned','drain':{},'output':'{}'})
    else:raw['lineage']['root']['trigger_id']='another'
    assert probe.analyze_case(raw)['status']=='unknown_invalid_or_incomplete_accounting'


def test_in_memory_and_persisted_tape_shapes_have_identical_assessment():
    raw=fixture()
    assert probe.analyze_case(raw)==probe.analyze_case(json.loads(json.dumps(raw)))


def test_import_closure_pins_actual_controller_capture_abi_and_independent_verifier():
    names={p.name for p in probe.source_paths()}
    assert {'protocol_control.py','native_host.py','native025_request_timing.py','native025_timing_gate.py',
        'capture_native025_request_timing.py','native_request_timing.py','capture_native_request_timing.py',
        'business_update_outbox.py','rolling_request_lineage.py','probe_installed_operations.py',
        'verify_installed_operations.py','analytic_control.py','regional_control.py',
        'run_g4irsf28_service_potential.py','__init__.py'} <= names
    paths=probe.source_paths()
    assert len(set(paths))==len(paths) and all(path.is_relative_to(probe.ROOT) for path in paths)
    assert any('scripts/eval/' in path.relative_to(probe.ROOT).as_posix() for path in paths)


@pytest.mark.parametrize('outcome', ['nonzero','timeout','launch_error'])
def test_process_failures_are_persisted_and_cannot_be_success(tmp_path,outcome):
    def runner(command,**kwargs):
        if outcome=='timeout':raise subprocess.TimeoutExpired(command,kwargs['timeout'])
        if outcome=='launch_error':raise OSError('failed')
        return subprocess.CompletedProcess(command,7)
    result=probe.execute_arm(tmp_path,'plain',runner=runner,timeout=.1)
    saved=json.loads((tmp_path/'plain.process.json').read_text())
    assert saved==result and result['exit_code']!=0 and result['status']!='process_exited'
    assert result['wall_seconds']>=0


def test_missing_worker_or_raw_keeps_declared_denominator_unknown(tmp_path):
    result=verifier.verify_or_unknown(tmp_path)
    assert result['status']=='unknown_invalid_or_incomplete_probe'
    assert result['root_denominator']==9 and set(result['declared_roots'])==set(probe.CASES)
    assert result['original_business_request_100ms_certified'] is False


def test_missing_ack_case_cannot_be_relabelled_no_action_success():
    raw=fixture();raw['case']='ack_still_missing'
    with pytest.raises(ValueError,match='declared_operation_scenario_not_executed'):
        verifier.case_coverage(raw)


def route_fixture():
    raw=fixture();raw['case']='route_installed'
    lineage=RequestLineage()
    lineage.accept('root',scope='business_task_update',owner='A',trigger_id='route_installed:root',trigger_kind='predeclared_public_epoch',relation='independent_offer',
        completion_contract={'kind':'one_shot_update','goal_id':'install_operation_or_explicit_failure','terminal_failure_allowed':True},jobs=('B1',),at=.11,wall_ns=110)
    lineage.observe('root',references=[],at=.11,wall_ns=120)
    identity='route1';payload={'request_id':identity,'owner_id':'A','kind':'route','business_bag_id':'B1'}
    lineage.submit('root',identity,payload,required_terminal_statuses=('updated',),at=.11,wall_ns=126)
    ack={'request_id':identity,'sequence':1,'status':'updated','reason':'','delivered_at':.11}
    lineage.handle_ack(identity,ack,at=.11,wall_ns=131)
    lineage.seal('root',disposition='completed',classification_complete=True,at=.11,wall_ns=132)
    lineage.drain('root',timestamp_complete=True,at=.11,wall_ns=140);lineage.output('root',at=.11,wall_ns=150)
    delivered={k:v for k,v in ack.items() if k!='request_id'};reply={'status':'queued'}
    query={'request_id':identity,'last_delivered_ack':delivered}
    raw.update(lineage=lineage.roots,protocol_lineage=lineage.protocol,
        root_reports={'root':{**lineage.summary('root'),'job_scope_verified':True}},
        outbox={identity:{'kind':'route','payload':payload,'client_view':query}},
        calls=[{'at':.11,'retry':False,'kind':'route','request':payload,'reply':reply,'submit_compute_ms':.1}])
    raw['service_tape'][2:2]=[
        {'ordinal':3,'endpoint':'submit_protocol_command','args':[payload],'kwargs':{},'start_ns':127,'end_ns':128,'physical_before':.11,'physical_after':.11,'result':reply},
        {'ordinal':4,'endpoint':'protocol_command','args':['A',identity],'kwargs':{},'start_ns':129,'end_ns':130,'physical_before':.11,'physical_after':.11,'result':query}]
    raw['service_tape'][-1]['ordinal']=5;raw['roots']['root']['drain_call_ordinal']=5
    returned=json.loads(raw['roots']['root']['returned_output']);returned['output']=json.dumps({'root':'root','disposition':'completed','decisions':[]})
    raw['roots']['root']['returned_output']=json.dumps(returned)
    raw['timing']['envelopes']=[{'api_endpoint':r['endpoint'],'start_ns':r['start_ns'],'end_ns':r['end_ns'],
        **({'protocol_request_id':identity} if r['endpoint'] in {'submit_protocol_command','protocol_command'} else {})} for r in raw['service_tape']]
    return raw


def test_actual_query_ack_and_submission_replay_are_required():
    assert probe.analyze_case(route_fixture())['closed_count']==1


@pytest.mark.parametrize('defect',['payload','query_ack','missing_attempt','fake_retry','wrong_native_id','required_status','ack_after_seal'])
def test_actual_operation_lineage_cannot_be_relabelled(defect):
    raw=deepcopy(route_fixture())
    if defect=='payload':raw['outbox']['route1']['payload']['business_bag_id']='B2'
    elif defect=='query_ack':raw['service_tape'][3]['result']={'request_id':'route1','last_delivered_ack':{}}
    elif defect=='missing_attempt':raw['protocol_lineage']['route1']['attempts']=[]
    elif defect=='fake_retry':raw['calls'][0]['retry']=True
    elif defect=='wrong_native_id':raw['timing']['envelopes'][2]['protocol_request_id']='other'
    elif defect=='required_status':raw['protocol_lineage']['route1']['required_terminal_statuses']=['received']
    else:raw['protocol_lineage']['route1']['handling_events'][0]['sequence']=6
    assert probe.analyze_case(raw)['status']=='unknown_invalid_or_incomplete_accounting'


def test_service_tape_copies_actual_inputs_outputs_without_alias_mutation():
    class Fake:
        physical_time=0.
        def observe_protocol(self,owner):return {'owner':owner,'nested':[]}
    tape=probe.ServiceTape(Fake());returned=tape.observe_protocol('A');returned['nested'].append('changed')
    assert tape.rows[0]['args']==['A'] and tape.rows[0]['result']['nested']==[]
    assert tape.rows[0]['start_ns']<=tape.rows[0]['end_ns']
    with pytest.raises(ValueError,match='unclassified_endpoint'):tape.offline_diagnostics()


def test_returned_decision_payload_cannot_omit_actual_selection():
    raw=fixture();raw['decisions']=[{'root':'root','selected':None}]
    assert probe.analyze_case(raw)['status']=='unknown_invalid_or_incomplete_accounting'


def test_real_probe_no_action_pipeline_with_test_double_roundtrips_complete_evidence():
    class Session:
        def __init__(self,data):self.data=data;self.physical_time=0.
        def advance_to(self,horizon,max_events):
            self.physical_time=horizon
            return {'status':'reached','horizon_complete':True,'physical_time':horizon,'wall_seconds':.00001}
        def observe_protocol(self,owner):
            job={**self.data['jobs'][0],'storage_released_at':-1.}
            return {'owner_id':owner,'now':self.physical_time,'jobs':[job],
                'trays':[{'business_bag_id':'B1','mode':'loaded','edge_to':-1,'node':0,'tray_id':'T0','generation':1,'traversal_id':0}],
                'client_transfer_ledger':[],'node_records':self.data['node_records'],'edge_records':self.data['edge_records']}
        def offline_state_sha256(self):return 'a'*64
    native=SimpleNamespace(NativeSession=Session,_g31_native_artifact_identity={'sha256':'b'*64})
    raw=probe.run_case(native,'no_action',{},timed=False,identity=1)
    stored=json.loads(json.dumps(raw))
    assert probe.analyze_case(raw)==probe.analyze_case(stored)
    assert probe.analyze_case(stored)['closed_count']==1
    assert verifier.case_coverage(stored)['status']=='declared_scenario_exercised'
