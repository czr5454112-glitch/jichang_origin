"""Synthetic actual-origin stubs only; no native, model or saved raw decode."""
import copy
import hashlib
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_initial_recorded_adapter as r
from scripts.experiments.g31_ics_circulation import research_live_initial_six_seam as c


class Marker(ValueError):pass


@pytest.fixture
def synthetic(monkeypatch):
    gate=r.original.native_gate
    class Session:
        def __init__(self,data=None):
            self.physical_time=0.;self.requests={};self.reads=[];self.advances=[];self.fail=None;self.views={};self.active_error=Marker('getter failure')
        def advance_to(self,at):self.advances.append(at);self.physical_time=at
        def submit_protocol_command(self,request):
            self.requests[request['request_id']]=copy.deepcopy(request);return {'status':'accepted'}
        def observe_protocol(self,owner):
            self.reads.append(('view',owner));self.views[owner]=self.views.get(owner,0)+1
            if self.fail==('view',owner,self.views[owner]):raise self.active_error
            tray=({'tray_id':'L','node':0,'mode':'loaded','business_bag_id':'loaded','service_ready_known':True,
                   'service_ready_at':1.1,'generation':1,'traversal_id':0,'edge_to':-1,'edge_from':-1} if owner=='A' else
                  {'tray_id':'E','node':5,'mode':'empty','business_bag_id':'','available_at':0.,'edge_to':-1,'edge_from':-1})
            return {'owner_id':owner,'now':self.physical_time,'node_records':[(0,'R',1.,1.,1.,1)],
                'edge_records':[(0,2,1.,1.)],'trays':[tray],
                'node_contracts':[{'node':2,'resource_owner':'A','occupancy':0,'capacity':1}]}
        def protocol_command(self,owner,key):
            self.reads.append(('command',owner,key))
            if self.fail==('command',owner):raise self.active_error
            return {'request_id':key,'kind':self.requests.get(key,{}).get('kind','planning_snapshot'),
                'last_delivered_ack':{'status':'delivered'}}
        def protocol_planning_snapshots(self,owner):
            self.reads.append(('received',owner))
            if self.fail==('received',owner):raise self.active_error
            return []
    def context(**kwargs):
        value=object.__new__(r.original.supplied.SuppliedContext)
        value._payload=r.original.history.payload_encoding({'synthetic_fixture':True,'evidence':kwargs})
        value._digest=hashlib.sha256(value._payload.encode()).hexdigest();return value
    def valid(view,ack,received):
        jobs=[{**{f:0 for f in gate.previous.CONTRACT_FIELDS},'business_bag_id':j} for j in sorted(gate.guard.model.JOBS)]
        return {'status':'conditional_validated_data','own_delivered_ack':{'delivered_at':.09},
            'envelopes':{view['owner_id']:{'capture':{'jobs':jobs,'message_id':'synthetic',
                'static_contract_sha256':'synthetic','captured_at':.06},'payload_sha256':'synthetic','delivered_at':.07}}}
    monkeypatch.setattr(gate,'_valid_handle',lambda *args:True)
    monkeypatch.setattr(gate,'bind_native027',lambda *args,**kwargs:({'status':'synthetic_acceptance_only'},object()))
    monkeypatch.setattr(gate,'validate_pair',valid)
    monkeypatch.setattr(r.original.supplied,'initial_context',context)
    return SimpleNamespace(Session=Session,native=SimpleNamespace(NativeSession=Session,_g31_native_artifact_identity={'synthetic':True}))


def test_inverse_source_and_original_globals_untouched():
    collector=r.original.native_gate.collect_initial_ledger;before=dict(collector.__globals__)
    proof=r.source_proof();assert proof['inverse_AST_exact_three_passive_getter_wrappers']
    assert proof['actual_session_never_proxied'] and collector.__globals__==before


@pytest.mark.parametrize('label',['view','command','received'])
def test_real_shaped_getter_exception_identity_and_prefix_preserved(synthetic,label):
    session=synthetic.Session();session.physical_time=.11
    session.fail=('view','A',1) if label=='view' else (label,'A')
    journal=r.EndpointJournal();entry=journal.begin('initial','A','own')
    _,_,collector=r.make_functions(journal)
    with pytest.raises(Marker) as caught:collector(synthetic.native,session,'A','own',accepted=object())
    assert caught.value is session.active_error
    journal.finish(entry,error=caught.value)
    saved=journal.audit_copy();rows=saved['records'][0]['endpoints'];position=r.ORDER.index(label)
    assert [x['endpoint'] for x in rows]==list(r.ORDER[:position+1]) and rows[-1]['status']=='raised'
    assert all(x['status']=='returned' and 'value' in x for x in rows[:-1])
    assert len(session.reads)==position+1;c.verify_journal(saved)


def test_actual_shaped_all_three_returns_once(synthetic):
    session=synthetic.Session();session.physical_time=.11
    journal=r.EndpointJournal();entry=journal.begin('initial','B','own');_,_,collector=r.make_functions(journal)
    result=collector(synthetic.native,session,'B','own',accepted=object());journal.finish(entry,result=result)
    assert result[0]['status']=='conditional_native_delivered_model_input'
    assert type(result[1]) is r.original.native_gate.previous.NativeJobLedger
    assert [x[0] for x in session.reads]==list(r.ORDER)
    assert type(journal.audit_copy()['records'][0]['endpoints'][0]['value']['node_records'][0]) is list


def test_invalid_runtime_admission_does_not_call_endpoint(synthetic,monkeypatch):
    monkeypatch.setattr(r.original.native_gate,'_valid_handle',lambda *args:False)
    session=synthetic.Session();journal=r.EndpointJournal();entry=journal.begin('initial','A','own')
    _,_,collector=r.make_functions(journal);result=collector(synthetic.native,session,'A','own',accepted=None)
    journal.finish(entry,result=result);assert session.reads==[] and result[1] is None


@pytest.mark.parametrize('value',[float('nan'),('unexpected',),{1:'badkey'}])
def test_recording_export_error_never_changes_return_object(value):
    journal=r.EndpointJournal();entry=journal.begin('initial','A','id')
    view={'node_records':[],'edge_records':[],'bad':value}
    assert journal.call('view',lambda:view) is view
    journal.finish(entry,result=object());saved=journal.audit_copy()
    assert saved['records'][0]['endpoints'][0]['evidence_status']=='unknown_export_error'
    c.verify_journal(saved)


def test_recording_noncloneable_capability_attributes_not_copied():
    class Bad(dict):
        def __deepcopy__(self,memo):raise AssertionError('no capability copy')
    value=Bad(node_records=[],edge_records=[]);value.native=object()
    journal=r.EndpointJournal();entry=journal.begin('initial','A','id')
    assert journal.call('view',lambda:value) is value
    journal.finish(entry,result=object());assert 'unknown_export_error' in str(journal.audit_copy())


@pytest.mark.parametrize('case',c.CASES)
def test_complete_fake_case_has_two_independent_immediate_collections_and_no_actions(synthetic,case):
    spec=c.declaration()[case+'/initial']
    accepted=SimpleNamespace(active_for=lambda key:True,branch_specification=lambda key:copy.deepcopy(spec))
    raw=c.run_case(synthetic.native,spec,{'synthetic_case':case},{},accepted_run=accepted,branch_key=case+'/initial')
    assert raw['status']=='complete_six_scope_case'
    assert list(raw['owners'])==['A','B'] and raw['physical_time']==.11
    assert len(raw['calls'])==4 and {x['kind'] for x in raw['calls']}=={'demand','planning_snapshot'}
    assert all(len(row['journal']['records'])==2 for row in raw['owners'].values())
    assert c.verify_saved(c.data(raw),spec,{'synthetic_case':case})['known_initial_domains']==2


@pytest.mark.parametrize('owner,attempt',[('A',1),('A',2),('B',1),('B',2)])
def test_failed_current_or_initial_getter_keeps_other_owner_and_saved_prefix(synthetic,owner,attempt):
    class Failing(synthetic.Session):
        def __init__(self,data=None):super().__init__(data);self.fail=('view',owner,attempt)
    native=SimpleNamespace(NativeSession=Failing,_g31_native_artifact_identity={'synthetic':True})
    spec=c.declaration()['mechanism/initial'];accepted=SimpleNamespace(active_for=lambda key:True,branch_specification=lambda key:spec)
    raw=c.run_case(native,spec,{}, {},accepted_run=accepted,branch_key='mechanism/initial')
    row=raw['owners'][owner];records=row['journal']['records']
    assert row['status'].startswith('unknown') and len(records)==attempt
    assert records[-1]['endpoints'][-1]['status']=='raised'
    assert raw['owners'][{'A':'B','B':'A'}[owner]]['status']=='initial_seam_validated'
    assert c.verify_saved(c.data(raw),spec,{})['unknown_initial_domains']==1


def valid_journal():
    journal=r.EndpointJournal();entry=journal.begin('initial','A','id')
    for label,value in zip(r.ORDER,({'node_records':[],'edge_records':[]},{},[]),strict=True):journal.call(label,lambda v=value:v)
    journal.finish(entry,result=None);return journal.audit_copy()


@pytest.mark.parametrize('mutation',['order','extra','bool_clock','negative_clock','unknown_endpoint','unfinished','raised_nonterminal','extra_collection'])
def test_saved_prefix_refuses_malformed_sequence_clock_and_missing_terminal(mutation):
    value=valid_journal();entry=value['records'][0];rows=entry['endpoints']
    if mutation=='order':rows.reverse()
    elif mutation=='extra':rows.append(copy.deepcopy(rows[-1]))
    elif mutation=='bool_clock':entry['started_ns']=True
    elif mutation=='negative_clock':entry['started_ns']=-1
    elif mutation=='unknown_endpoint':rows[0]['endpoint']='other_owner'
    elif mutation=='unfinished':rows[-1]['status']='in_progress'
    elif mutation=='raised_nonterminal':rows[0].update(status='raised',error_type='Marker')
    else:value['records']*=3
    with pytest.raises(ValueError):c.verify_journal(value)


def test_fixed_six_declaration_no_case_or_action_filter():
    rows=c.declaration();assert list(rows)==list(c.KEYS) and len(c.DOMAIN)==6
    assert all(row['vector']==rows[c.KEYS[0]]['vector'] for row in rows.values())
    assert c.LIMIT==120. and all(r['fault'] is None and r['method']=='initial_seam_only' for r in rows.values())


def test_source_ast_rejects_added_getter_consumption(monkeypatch):
    real=r.inspect.getsource
    def changed(function):
        value=real(function)
        if function is r.original.native_gate.collect_initial_ledger:value=value.replace('view=session.observe_protocol(owner);',
            'extra=session.observe_protocol(owner);view=session.observe_protocol(owner);')
        return value
    monkeypatch.setattr(r.inspect,'getsource',changed)
    with pytest.raises(ValueError,match='exact_three'):r.collector_code()


def test_returned_mutable_native_value_is_not_mutated_by_journal():
    value={'node_records':[(1,'R',.1,1.,1.,1)],'edge_records':[(1,2,1.,1.)]};before=copy.deepcopy(value)
    journal=r.EndpointJournal();entry=journal.begin('initial','A','id');assert journal.call('view',lambda:value) is value
    journal.finish(entry,result=None);value['node_records'].append((2,'R',.1,1.,1.,1))
    assert len(journal.audit_copy()['records'][0]['endpoints'][0]['value']['node_records'])==len(before['node_records'])


@pytest.mark.parametrize('failing_clock_call',[3,4])
def test_monitor_finalization_failure_preserves_exact_original_exception(monkeypatch,failing_clock_call):
    counter=[0]
    def clock():
        counter[0]+=1
        if counter[0]==failing_clock_call:raise RuntimeError('monitor clock failed')
        return counter[0]
    monkeypatch.setattr(r.time,'perf_counter_ns',clock)
    journal=r.EndpointJournal();original=Marker('original native failure')
    def getter():raise original
    with pytest.raises(Marker) as caught:r._invoke(journal,'initial','A','id',lambda:journal.call('view',getter))
    assert caught.value is original and journal.monitor_failed is True
    c.verify_journal(journal.audit_copy())


@pytest.mark.parametrize('failing_clock_call',[3,4])
def test_successful_getter_monitor_failure_cannot_return_successful_authority(monkeypatch,failing_clock_call):
    counter=[0]
    def clock():
        counter[0]+=1
        if counter[0]==failing_clock_call:raise RuntimeError('monitor clock failed')
        return counter[0]
    monkeypatch.setattr(r.time,'perf_counter_ns',clock)
    journal=r.EndpointJournal();value={'node_records':[],'edge_records':[]}
    result=r._invoke(journal,'initial','A','id',lambda:journal.call('view',lambda:value))
    assert result['status']=='unknown' and result['reason']=='endpoint_recording_failed'
    assert journal.monitor_failed;c.verify_journal(journal.audit_copy())


def test_exception_text_failure_cannot_replace_native_exception():
    class BadText(Marker):
        def __str__(self):raise RuntimeError('bad text monitor')
    original=BadText();journal=r.EndpointJournal()
    def getter():raise original
    with pytest.raises(BadText) as caught:r._invoke(journal,'initial','A','id',lambda:journal.call('view',getter))
    assert caught.value is original and journal.monitor_failed;c.verify_journal(journal.audit_copy())


@pytest.mark.parametrize('returned_status',['unknown','conditional_success'])
def test_caught_getter_exception_must_not_be_reported_as_valid_return(returned_status):
    value=valid_journal();entry=value['records'][0];entry['returned_status']=returned_status
    entry['endpoints'][-1].update(status='raised',error_type='Marker')
    entry['endpoints'][-1].pop('value')
    if returned_status=='unknown':c.verify_journal(value)
    else:
        with pytest.raises(ValueError,match='captured_exception'):c.verify_journal(value)


def test_monitor_failure_cannot_be_forged_as_successful_saved_owner(synthetic):
    spec=c.declaration()['mechanism/initial'];accepted=SimpleNamespace(active_for=lambda key:True,branch_specification=lambda key:spec)
    raw=c.run_case(synthetic.native,spec,{}, {},accepted_run=accepted,branch_key='mechanism/initial')
    raw['owners']['A']['journal']['monitor_failed']=True
    with pytest.raises(ValueError,match='recording_failed_not_success'):c.verify_saved(raw,spec,{})
