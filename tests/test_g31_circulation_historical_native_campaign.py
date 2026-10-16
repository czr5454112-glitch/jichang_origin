"""Saved native shapes and mock endpoint boundaries; no native or predictor.

Mock handle validation below tests adapter wiring only. It is not runtime
acceptance evidence. Original actual fixtures/results are never overwritten.
"""
import copy,gzip,json
from pathlib import Path
from types import FunctionType,SimpleNamespace
import pytest
import test_g31_circulation_live_obligation_recollection_campaign as previous
import test_g31_circulation_historical_goal_service as history_tests
from scripts.experiments.g31_ics_circulation import research_live_obligation_historical as c
from scripts.experiments.g31_ics_circulation import launch_live_obligation_historical as launch
from scripts.experiments.g31_ics_circulation import verify_live_obligation_historical as saved
from scripts.experiments.g31_ics_circulation import live_obligation_historical_adapter as adapter
from scripts.experiments.g31_ics_circulation import live_obligation_historical_policy as policy


def supplied_fixture():
    data=previous.supplied_fixture()
    for owner in ('A','B'):
        entry=data['collection_attempts'][owner][0]
        known,_,expected=saved.expected_information(data,owner,entry)
        assert known
        entry['information']=expected
        data['decisions'][owner][0]['information']=copy.deepcopy(expected)
    return data


# Preserve all39 accepted physical/action/failure/denominator checks using the
# new independent campaign and saved verifier. The fixture is explicitly pure.
_namespace={**vars(previous),'c':c,'launch':launch,'saved':saved,'supplied_fixture':supplied_fixture}
for _name in ('assessed_rows',*[n for n in vars(previous) if n.startswith('test_')]):
    _old=getattr(previous,_name)
    _new=FunctionType(_old.__code__,_namespace,_old.__name__,_old.__defaults__,_old.__closure__)
    _new.__kwdefaults__=_old.__kwdefaults__;_new.__dict__.update(_old.__dict__)
    _namespace[_name]=globals()[_name]=_new


def client_fixture(key='mechanism/vector_02',owner='B',index=-1):
    raw,entry,ep,kwargs=history_tests.arguments(key,owner,index)
    class EndpointFixture:
        def __init__(self):self.physical_time=entry['at'];self.reads=[];self.after_read=lambda:None
        def observe_protocol(self,who):
            assert who==owner;self.reads.append(('observe_protocol',who));return copy.deepcopy(ep['view'])
        def protocol_command(self,who,rid):
            assert who==owner and rid==entry['collection']['request_id']
            self.reads.append(('protocol_command',who,rid));return copy.deepcopy(ep['command'])
        def protocol_planning_snapshots_v3(self,who):
            assert who==owner;self.reads.append(('protocol_planning_snapshots_v3',who))
            self.after_read();return copy.deepcopy(ep['received'])
    session=EndpointFixture();client=adapter.fixture.LocalTransport(session)
    count=entry['predecision_call_prefix_count'];client.calls=copy.deepcopy(raw['calls'][:count])
    for call in client.calls:
        rid=call['request']['request_id'];client.rows[rid]=copy.deepcopy(raw['outbox'][rid])
        client.rows[rid]['request']=copy.deepcopy(call['request'])
    roots=[r for r in raw['owner_activation_admissions'] if r['owner']==owner and r['accepted_at']==entry['at']]
    assert len(roots)==1
    client.context=copy.deepcopy(roots[0]);client.roots=[client.context]
    native=SimpleNamespace(_g31_native_artifact_identity=copy.deepcopy(raw['retained_ledgers'][owner]['native_binary']))
    accepted=SimpleNamespace(_native=native,_session=session,audit_copy=lambda:copy.deepcopy(raw['native027_acceptance']))
    ledger=adapter.endpoint.previous.NativeJobLedger(adapter.endpoint.previous._LEDGER_TOKEN,
        session,owner,copy.deepcopy(raw['retained_ledgers'][owner]))
    return raw,entry,ep,client,native,accepted,ledger


def collect_fixture(monkeypatch,items):
    raw,entry,ep,client,native,accepted,ledger=items;session=client.session;owner=ep['view']['owner_id']
    monkeypatch.setattr(adapter.endpoint,'_valid_handle',lambda n,s,h:n is native and s is session and h is accepted)
    pending=entry['collection']
    result=adapter.collect_native(native,session,owner,pending['request_id'],client=client,
        accepted=accepted,ledger=ledger,owned_client_rows=client.owned(owner),phase=entry['phase'],
        peer_message_id=pending['peer_message'],collection_started_at=pending['at'],
        policy_quiet_since=pending['policy_quiet_since'])
    return result


def test_actual_local_transport_ledger_preserves_order_and_owner_scope():
    _,_,_,client,_,_,_=client_fixture()
    owned=client.owned('B');rows,publications,audit=adapter.client_owned_snapshot(client,client.session,'B',owned)
    assert all(rows[k] is owned[k] for k in rows)
    assert audit['own_submitted_request_ids']==list(owned)
    assert audit['publication_request_ids']==list(publications)
    assert all(r['owner_id']=='B' for r in publications.values())
    assert audit['submission_call_count']==len(client.calls)
    assert audit['admission_root']==client.context['root_id']
    assert not adapter.is_native_attempt(audit)


@pytest.mark.parametrize('change',['generic_client','subclass','wrong_session','copied_rows','foreign_rows',
    'wrong_owner','missing_admission','copied_admission','old_admission','changed_call','missing_call',
    'reversed_rows','duplicate_first','retry_without_first','retry_bool','future_clock','bool_clock',
    'signed_zero','float_integer','custom_payload','tuple_payload','nonfinite'])
def test_actual_client_authority_and_lossless_history_negatives(change):
    _,_,_,client,_,_,_=client_fixture();session=client.session;owner='B';rows=client.owned(owner)
    rid=next(k for k,r in rows.items() if r['kind']=='planning_snapshot_v3')
    call=next(x for x in client.calls if x['request']['request_id']==rid)
    if change=='generic_client':client=SimpleNamespace(**client.__dict__)
    elif change=='subclass':
        class Foreign(adapter.fixture.LocalTransport):pass
        other=Foreign(session);other.__dict__.update(client.__dict__);client=other
    elif change=='wrong_session':session=SimpleNamespace(physical_time=session.physical_time)
    elif change=='copied_rows':rows=copy.deepcopy(rows)
    elif change=='foreign_rows':rows.update(client.owned('A'))
    elif change=='wrong_owner':owner='A'
    elif change=='missing_admission':client.context=None
    elif change=='copied_admission':client.context=copy.deepcopy(client.context)
    elif change=='old_admission':client.context['accepted_at']-=.01
    elif change=='changed_call':call['request']['expiry']+=1.
    elif change=='missing_call':client.calls=[x for x in client.calls if x['request']['request_id']!=rid]
    elif change=='reversed_rows':client.rows=dict(reversed(list(client.rows.items())));rows=client.owned(owner)
    elif change=='duplicate_first':client.calls.insert(client.calls.index(call)+1,copy.deepcopy(call))
    elif change=='retry_without_first':call['retry']=True
    elif change=='retry_bool':call['retry']=0
    elif change=='future_clock':call['at']=session.physical_time+1.
    elif change=='bool_clock':call['at']=True
    elif change=='signed_zero':call['request']['new_zero']=0.;rows[rid]['request']['new_zero']=-0.
    elif change=='float_integer':call['request']['new_integer']=1;rows[rid]['request']['new_integer']=1.
    elif change=='custom_payload':
        class Custom(dict):pass
        call['request']['other']=Custom(a=1)
    elif change=='tuple_payload':call['request']['other']=(1,2)
    else:call['request']['expiry']=float('nan')
    with pytest.raises((ValueError,KeyError,TypeError)):adapter.client_owned_snapshot(client,session,owner,rows)


def test_actual_tuple_endpoints_history_and_capability_seal(monkeypatch):
    items=client_fixture();raw,entry,ep,client,*_=items
    assert type(ep['view']['node_records'][0]) is tuple
    value=collect_fixture(monkeypatch,items)
    assert value['status']=='conditional_native_delivered_later_v3_model_input'
    assert adapter.is_native_attempt(value) and adapter.is_native_collected(value)
    assert 'derived_goal_service_bounds' in value['bundle']
    assert not adapter.is_native_attempt(adapter.json_data(value))
    assert not adapter.is_native_collected(dict(value))
    known,_,expected=saved.expected_information(raw,'B',entry)
    assert known and adapter.json_data(value)==expected
    assert client.session.reads==[('observe_protocol','B'),('protocol_command','B',entry['collection']['request_id']),
        ('protocol_planning_snapshots_v3','B')]
    value['actual_publication_ledger']['publication_request_ids'].reverse()
    assert not adapter.is_native_attempt(value)


@pytest.mark.parametrize('key',['insufficient_advance/vector_16','insufficient_advance/vector_17'])
def test_unloading_unknown_keeps_raw_endpoint_attempt_not_physical_authority(monkeypatch,key):
    items=client_fixture(key);value=collect_fixture(monkeypatch,items)
    assert value['status']=='unknown' and value['bundle']['reasons']==['stable_observed_unloading']
    assert adapter.is_native_attempt(value) and not adapter.is_native_collected(value)
    assert set(value['raw_endpoints'])=={'view','command','received'}
    assert len(items[3].session.reads)==3 and 'actual_publication_ledger' in value
    items[3].session.physical_time+=.001
    assert not adapter.is_native_attempt(value)


@pytest.mark.parametrize('change',['clock','admission','ledger_scalar_type','missing_endpoint'])
def test_mid_collection_change_keeps_partial_raw_unknown(monkeypatch,change):
    items=client_fixture();client=items[3];session=client.session
    if change=='clock':session.after_read=lambda:setattr(session,'physical_time',session.physical_time+.001)
    elif change=='admission':session.after_read=lambda:client.activate('A',{'changed':'unit'})
    elif change=='ledger_scalar_type':
        def mutate():
            for call in client.calls:
                if call['request']['owner_id']=='B' and call['kind']=='planning_snapshot_v3':
                    call['request']['unit_value']=1.;client.rows[call['request']['request_id']]['request']['unit_value']=1.
        # Before/after lossless encoding must detect consistent history edits too.
        for call in client.calls:
            if call['request']['owner_id']=='B' and call['kind']=='planning_snapshot_v3':
                call['request']['unit_value']=1;client.rows[call['request']['request_id']]['request']['unit_value']=1
        session.after_read=mutate
    else:
        original=adapter.guard.validate_collected_endpoints
        def incomplete(*args,**kw):
            result=original(*args,**kw);del result['raw_endpoints']['command'];return result
        monkeypatch.setattr(adapter.guard,'validate_collected_endpoints',incomplete)
    value=collect_fixture(monkeypatch,items)
    assert value['status']=='unknown' and not adapter.is_native_attempt(value)
    assert 'partial_information' in value and 'raw_endpoints' in value['partial_information']
    assert 'actual_publication_ledger' in value


def test_unaccepted_handle_never_reads_endpoints_or_client(monkeypatch):
    monkeypatch.setattr(adapter.endpoint,'_valid_handle',lambda *a:False)
    value=adapter.collect_native(object(),object(),'B','id',client=object(),accepted=object(),ledger=object(),
        owned_client_rows={},phase='first_reuse_route',peer_message_id='peer',collection_started_at=1.,policy_quiet_since=1.)
    assert value['reasons']==['missing_session_bound_native027_acceptance']


def test_private_policy_only_changes_collector_and_retains_one_fresh_budget():
    instance=policy.OwnerPolicy.__new__(policy.OwnerPolicy)
    # Constructor needs no native methods; the original only retains references.
    client=adapter.fixture.LocalTransport(SimpleNamespace(physical_time=1.))
    policy.OwnerPolicy.__init__(instance,object(),client.session,client,'B',object(),None,{},object())
    assert instance.decide_pending.__code__ is policy.old.OwnerPolicy.decide_pending.__code__
    scoped=instance.decide_pending.__globals__['adapter']
    assert type(scoped) is adapter.OwnerCollectionAdapter and scoped._client is client
    assert instance.decide_pending.__globals__['retry_admission'] is policy.old.retry_admission
    assert policy.old.OwnerPolicy.decide_pending.__globals__['adapter'] is not scoped
    for name in ('begin','exchange','_begin_recollection','activate','return_tray','route_tray'):
        assert getattr(policy.OwnerPolicy,name) is getattr(policy.old.OwnerPolicy,name)
    assert scoped.collect_native(object(),object(),'B','id')['reasons']==['wrong_bound_owner_collection_adapter']
    assert scoped.collect_native(object(),client.session,'A','id')['reasons']==['wrong_bound_owner_collection_adapter']


def test_real_failed_shape_can_request_only_one_fresh_pair_with_actual_attempt_seal(monkeypatch):
    items=client_fixture('insufficient_advance/vector_16','A',0)
    raw,entry,ep,client,native,accepted,ledger=items
    value=collect_fixture(monkeypatch,items)
    assert value['status']=='unknown' and value['reasons']==['owned_tray_changed_after_v3_capture']
    assert adapter.is_native_attempt(value) and not adapter.is_native_collected(value)
    requests=saved.prefix_requests(raw,'A',entry)
    for key,row in saved.owned_at_view(requests,ep['view']).items():
        client.rows[key]['ack']=row['ack'];client.rows[key]['terminal']=row['terminal']
    # This is a mock submission sink, not native execution or a delivered ACK.
    client.session.submit_protocol_command=lambda request:{'status':'submitted','request_id':request['request_id']}
    instance=policy.OwnerPolicy(native,client.session,client,'A',ledger,None,raw['specification']['vector'],accepted)
    instance.pending=copy.deepcopy(entry['collection']);instance.serial=100
    before=len(client.calls)
    instance.decide_pending(ep['view'])
    assert len(client.calls)==before+1 and len(instance.collection_attempts)==1 and not instance.decisions
    attempt=instance.collection_attempts[0]
    assert attempt['disposition']=='one_fresh_pair_requested' and instance.pending['recollection_index']==1
    assert client.calls[-1]['retry'] is False and client.calls[-1]['kind']=='planning_snapshot_v3'
    assert client.calls[-1]['request']['request_id']!=entry['collection']['request_id']
    screen=policy.retry_admission(value,instance.pending,ep['view'],client.owned('A'))
    assert screen['status']=='not_admitted' and screen['reason']=='one_fresh_pair_already_used'
    instance.decide_pending(ep['view'])
    assert len(client.calls)==before+1


def test_all238_actual_saved_prefixes_bind_unique_admission_and_immutable_order():
    ledger=c.read(c.OLD_PLAN.parent/'branch_ledger.json');count=0
    for row in ledger.values():
        ref=row['raw_artifact'];assert c.sha(ref['path'])==ref['sha256']
        raw=json.loads(gzip.decompress(Path(ref['path']).read_bytes()))
        saved.verify_call_history(raw)
        for owner,entries in raw['collection_attempts'].items():
            for entry in entries:
                requests=saved.prefix_requests(raw,owner,entry)
                calls=raw['calls'][:entry['predecision_call_prefix_count']]
                assert list(adapter.submission_history(calls,owner,entry['at']))==list(requests)
                roots=[r for r in raw['owner_activation_admissions'] if r['owner']==owner and r['accepted_at']==entry['at']]
                assert len(roots)==1
                count+=1
    assert count==238


@pytest.mark.parametrize('change',['ledger_missing','ledger_order','ledger_clock_bool','ledger_request',
    'admission_missing','admission_duplicate','admission_identity','call_retry_type'])
def test_saved_new_actual_ledger_boundary_cannot_be_forged(change):
    raw=supplied_fixture();entry=raw['collection_attempts']['B'][0]
    ledger=entry['information']['actual_publication_ledger']
    if change=='ledger_missing':del entry['information']['actual_publication_ledger']
    elif change=='ledger_order':ledger['own_submitted_request_ids'].reverse()
    elif change=='ledger_clock_bool':ledger['at']=True
    elif change=='ledger_request':next(iter(ledger['publication_requests'].values()))['expiry']+=1.
    elif change=='admission_missing':raw['owner_activation_admissions']=[r for r in raw['owner_activation_admissions'] if r['root_id']!=ledger['admission_root']]
    elif change=='admission_duplicate':raw['owner_activation_admissions'].append(copy.deepcopy(next(r for r in raw['owner_activation_admissions'] if r['root_id']==ledger['admission_root'])))
    elif change=='admission_identity':ledger['admission_root']='other'
    else:next(x for x in raw['calls'] if x['request']['owner_id']=='B')['retry']=0
    with pytest.raises((ValueError,KeyError)):saved.replay_information(raw,'B',entry)


def test_old85_and_history_source_archives_remain_exact():
    assert c.sha(c.OLD_PLAN)==c.OLD_PLAN_SHA and c.sha(c.HISTORY_PREP)==c.HISTORY_PREP_SHA
    plan=c.read(c.OLD_PLAN);assert len(plan['source_sha256'])==85
    for path,digest in plan['source_sha256'].items():assert c.sha(path)==c.sha(c.OLD_PLAN.parent/plan['source_archive'][path])==digest
    for path,item in c.read(c.HISTORY_PREP)['source_archive'].items():
        assert c.sha(path)==c.sha(item['archive']['path'])==item['sha256']
