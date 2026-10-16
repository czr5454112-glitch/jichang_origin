"""Pure actual-client replay and adversarial ledger tests; no NativeSession."""
import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_outbox_trace as t


class NativeShapeSession:
    def __init__(self):self.physical_time=.11;self.acks={};self.fail=False;self.calls=[]
    def submit_protocol_command(self,payload):
        self.calls.append(('submit',copy.deepcopy(payload)))
        return {'status':'accepted','request_id':payload['request_id']}
    submit_protocol_transfer=submit_protocol_command
    def protocol_command(self,owner,identity):
        if self.fail:raise RuntimeError('injected actual query failure')
        self.calls.append(('query',owner,identity))
        return {'request_id':identity,'last_delivered_ack':copy.deepcopy(self.acks.get(identity,{}))}
    protocol_request=protocol_command


def fixture():
    session=NativeShapeSession();client=t.gate.original.public.LocalTransport(session)
    trace=t.OutboxTrace(client)
    client.activate('A',{'kind':'pure_fixture'})
    identity=client.submit('A','route','one',business_bag_id='loaded',tray_id='L')
    client.activate('B',{'kind':'pure_fixture'})
    peer=client.submit('B','transfer','two',tray_id='E')
    return session,client,trace,identity,peer


def compare(client,trace):
    data=trace.audit_copy();replayed=t.reconstruct(data,client.calls,client.creations)
    assert t.gate.ordered(replayed['rows'])==t.gate.ordered(client.rows)
    assert t.gate.ordered(replayed['ack_handling'])==t.gate.ordered(client.ack_handling)
    assert t.verify_refresh_inventory(data,client.calls,client.creations)['queries']==len(trace.reads)
    linear=t.Replay(data,client.calls,client.creations)
    for read in data['reads']:linear.advance(read['ordinal']+1,read['call_prefix'])
    linear.advance(len(data['reads']),len(client.calls))
    assert t.gate.ordered(linear.finish())==t.gate.ordered(replayed)


def test_private_refresh_keeps_original_client_type_and_full_rows():
    session,client,trace,identity,peer=fixture();original=type(client).refresh_owner
    t.refresh(client,'A');t.refresh(client,'B');compare(client,trace)
    assert type(client) is t.gate.original.public.LocalTransport and type(client).refresh_owner is original
    assert session.calls[-2:]==[('query','A',identity),('query','B',peer)]


def test_changed_and_repeated_actual_ACK_body_stored_once_without_skipping_reads():
    session,client,trace,identity,peer=fixture()
    session.acks[identity]={'status':'updated','delivered_at':.11,'payload':{'ordered':[1,2]}}
    t.refresh(client,'A');t.refresh(client,'A');t.refresh(client,'A')
    assert len(trace.reads)==3 and len(trace.bodies)==1 and [q['ack_changed'] for q in trace.reads]==[True,False,False]
    compare(client,trace)
    data=trace.audit_copy();data['ack_bodies'][0]['payload']['ordered'][0]=99
    assert trace.bodies[0]['payload']['ordered']==[1,2] and client.rows[identity]['ack']['payload']['ordered']==[1,2]


def test_pending_due_retry_exact_original_point_and_identity():
    session,client,trace,identity,peer=fixture();session.physical_time=.61
    t.refresh(client,'A');assert client.calls[-1]['retry'] is True and client.rows[identity]['next_retry']==1.1099999999999999
    compare(client,trace)
    # Terminal ACK closes the row; no later due retry is invented.
    session.physical_time=1.2;session.acks[identity]={'status':'updated','delivered_at':1.2}
    before=len(client.calls);t.refresh(client,'A');assert len(client.calls)==before;compare(client,trace)


def test_retry_false_preserves_due_original_row_without_retry():
    session,client,trace,identity,peer=fixture();session.physical_time=5.
    t.refresh(client,'A',retry=False);assert len(client.calls)==2;compare(client,trace)


def test_same_timestamp_send_query_sequence_reconstructs_reset_terminal_exactly():
    session,client,trace,identity,peer=fixture()
    session.acks[identity]={'status':'updated','delivered_at':.11};t.refresh(client,'A')
    # Deliberate pure stress of Transport.send's reset behavior; no claim that
    # the fixed actual policy would retry a terminal row.
    client.send(identity,retry=True);assert client.rows[identity]['terminal'] is False
    t.refresh(client,'A');assert client.rows[identity]['terminal'] is True
    assert len(trace.bodies)==1;compare(client,trace)


def test_empty_ACK_reset_and_new_later_ACK_keep_exact_original_change_test():
    session,client,trace,identity,peer=fixture()
    session.acks[identity]={'status':'departed','delivered_at':.11};t.refresh(client,'A')
    session.acks[identity]={};t.refresh(client,'A')
    session.acks[identity]={'status':'updated','delivered_at':.11};t.refresh(client,'A')
    assert [q['ack_ref'] for q in trace.reads]==[0,None,1];compare(client,trace)


@pytest.mark.parametrize('mutation',['missing_query','wrong_owner','wrong_method','call_cursor','body_cursor','body_extra','changed_flag','missing_refresh','retry_count'])
def test_saved_outbox_tamper_fails_closed(mutation):
    session,client,trace,identity,peer=fixture()
    session.acks[identity]={'status':'updated','delivered_at':.11};t.refresh(client,'A');t.refresh(client,'B')
    data=trace.audit_copy()
    if mutation=='missing_query':data['reads'].pop()
    if mutation=='wrong_owner':data['reads'][0]['owner']='B'
    if mutation=='wrong_method':data['reads'][0]['method']='protocol_request'
    if mutation=='call_cursor':data['reads'][0]['call_prefix']=0
    if mutation=='body_cursor':data['reads'][0]['ack_ref']=2
    if mutation=='body_extra':data['ack_bodies'].append({'status':'updated'})
    if mutation=='changed_flag':data['reads'][0]['ack_changed']=False
    if mutation=='missing_refresh':data['refreshes'].pop()
    if mutation=='retry_count':data['refreshes'][0]['after_call']+=1
    with pytest.raises((ValueError,KeyError,IndexError)):
        t.reconstruct(data,client.calls,client.creations);t.verify_refresh_inventory(data,client.calls,client.creations)


def test_query_exception_propagates_and_retains_exact_failed_prefix():
    session,client,trace,identity,peer=fixture();session.fail=True
    with pytest.raises(RuntimeError,match='injected'):t.refresh(client,'A')
    assert trace.invalid and trace.reads[0]['error'] and trace.refreshes[0]['error']
    with pytest.raises(ValueError,match='unclosed'):t.reconstruct(trace.audit_copy(),client.calls,client.creations)


def test_unknown_late_installation_and_unscoped_query_rejected():
    session,client,trace,identity,peer=fixture()
    with pytest.raises(ValueError,match='fresh'):t.OutboxTrace(client)
    with pytest.raises(ValueError,match='unscoped'):trace.query('protocol_command','A',identity)


def test_private_callsite_AST_preserves_original_method_globals():
    original=t.gate.request.InitialOwnerRequest.observe_after_boundary
    before=dict(original.__globals__);clone=t.redirect_refresh(original)
    assert clone._refresh_sites==1 and original.__globals__==before
    assert clone.__globals__ is not original.__globals__
    assert t.redirect_refresh(t.gate.original.run_continuation)._refresh_sites==2


def test_incremental_inventory_never_calls_quadratic_reference(monkeypatch):
    session,client,trace,identity,peer=fixture()
    session.acks[identity]={'status':'updated','delivered_at':.11,'payload':{'large':[1]*100}}
    for _ in range(50):t.refresh(client,'A')
    monkeypatch.setattr(t,'reconstruct',lambda *a,**k: (_ for _ in ()).throw(AssertionError('quadratic oracle used')))
    assert t.verify_refresh_inventory(trace.audit_copy(),client.calls,client.creations)['queries']==50
    replay=t.Replay(trace.audit_copy(),client.calls,client.creations).advance(50,len(client.calls))
    assert replay.rows[identity]['ack'] is replay.trace['ack_bodies'][0]


@pytest.mark.parametrize('field,value',[('started_ns',-1),('query_finished_ns',False),('at',float('nan'))])
def test_actual_query_clock_corruption_rejected(field,value):
    session,client,trace,identity,peer=fixture();t.refresh(client,'A')
    data=trace.audit_copy();data['reads'][0][field]=value
    with pytest.raises(ValueError):t.verify_refresh_inventory(data,client.calls,client.creations)
