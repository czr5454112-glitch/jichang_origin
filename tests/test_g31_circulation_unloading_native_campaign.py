"""Actual saved native shapes and mock authority boundaries; zero simulation."""
import copy,gzip,json
from pathlib import Path
from types import FunctionType,SimpleNamespace
import pytest
import test_g31_circulation_live_obligation_recollection_campaign as physical_tests
import test_g31_circulation_historical_native_campaign as historical_tests
from scripts.experiments.g31_ics_circulation import research_live_obligation_unloading as c
from scripts.experiments.g31_ics_circulation import launch_live_obligation_unloading as launch
from scripts.experiments.g31_ics_circulation import verify_live_obligation_unloading as saved
from scripts.experiments.g31_ics_circulation import live_obligation_unloading_policy as policy

adapter=policy.adapter
supplied_fixture=historical_tests.supplied_fixture
# Repeat the39 meaningful physical/action/partial/denominator tests with the
# new private campaign/verifier. No previous result is rewritten by the fixture.
_namespace={**vars(physical_tests),'c':c,'launch':launch,'saved':saved,'supplied_fixture':supplied_fixture}
for _name in ('assessed_rows',*[n for n in vars(physical_tests) if n.startswith('test_')]):
    _old=getattr(physical_tests,_name)
    _new=FunctionType(_old.__code__,_namespace,_old.__name__,_old.__defaults__,_old.__closure__)
    _new.__kwdefaults__=_old.__kwdefaults__;_new.__dict__.update(_old.__dict__)
    _namespace[_name]=globals()[_name]=_new


def fixture(key='insufficient_advance/vector_16'):
    plan=c.read(c.OLD_PLAN);ledger=c.read(c.OLD_PLAN.parent/'branch_ledger.json')
    ref=ledger[key]['raw_artifact'];assert c.sha(ref['path'])==ref['sha256']
    raw=json.loads(gzip.decompress(Path(ref['path']).read_bytes()))
    entry=raw['collection_attempts']['B'][0]
    info,pending,view=entry['information'],entry['collection'],entry['actual_local_view']
    known,requests,owned=saved.replay_information(raw,'B',entry)
    assert not known
    peer=next(m for m in info['raw_endpoints']['received'] if
        m['capture']['capture_v2']['local_capture']['message_id']==pending['peer_message'])
    own=info['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3']
    return raw,entry,info,pending,view,owned,own,peer


def local(envelope):return envelope['capture']['capture_v2']['local_capture']
def resign(envelope):envelope['payload_sha256']=policy.capture_contract.capture_digest_v3(envelope['capture'])


@pytest.mark.parametrize('key',['insufficient_advance/vector_16','insufficient_advance/vector_17'])
def test_two_real_crossed_unloading_shapes_admit_only_a_new_pair(key):
    raw,e,info,pending,view,owned,own,peer=fixture(key)
    screen=policy.retry_admission(info,pending,view,owned)
    assert screen['status']=='conditional_retry_admissible'
    assert screen['reason']=='observed_unloading_crossed_collection'
    assert screen['crossed_source_fact']['completion_inferred'] is False
    assert screen['unload_completion_still_requires_actual_delivered_receipt'] is True
    assert screen['native_success_certified'] is False
    assert screen['nominal_epochs']['physical_wire']<screen['retained_own_service_bound']
    assert not adapter.is_native_attempt(info) and not adapter.is_native_collected(info)
    assert info['status']=='unknown' and info['bundle']['reasons']==['stable_observed_unloading']
    assert raw['summary']['status']=='unknown_missing_input_or_unexecuted_counterfactual'


@pytest.mark.parametrize('change',['no_unloading','wrong_job','wrong_node','wrong_prefix','committed_edge',
    'missing_known','wrong_kind','future_end','end_at_capture','past_start_bound','wrong_duration',
    'missing_tray','missing_job','duplicate_tray','generation_bool','traversal_negative',
    'unresigned_generation','unresigned_traversal','future_delivery','expired_source','wrong_source',
    'wrong_target_job','wrong_target_generation','wrong_target_traversal','target_committed',
    'fresh_used','fresh_bool','missing_current_ack','pending_physical','changed_physical_set',
    'wire_equal','wire_after','own_known_missing','future_physical_ack'])
def test_unloading_eligibility_rejects_missing_changed_future_stale_and_exhausted(change):
    _,e,info,pending,view,owned,own,peer=fixture()
    t=next(t for t in local(peer)['trays'] if t['tray_id']=='E')
    j=next(j for j in local(peer)['jobs'] if j['business_bag_id']=='receiver')
    lt=next(t for t in local(own)['trays'] if t['tray_id']=='L')
    current=next(t for t in view['trays'] if t['tray_id']=='L')
    end=t['service_ready_at'];do_resign=True
    if change=='no_unloading':t['mode']='loaded'
    elif change=='wrong_job':t['business_bag_id']='blocker'
    elif change=='wrong_node':t['node']=3
    elif change=='wrong_prefix':t['committed_prefix']=[1,3,4]
    elif change=='committed_edge':t['edge_from']=3;t['edge_to']=4
    elif change=='missing_known':t['service_ready_known']=False
    elif change=='wrong_kind':t['ready_kind']='committed_local_service_end'
    elif change=='future_end':t['service_ready_at']=t['available_at']=view['now']+.01
    elif change=='end_at_capture':t['service_ready_at']=t['available_at']=local(peer)['captured_at']
    elif change=='past_start_bound':j['unload_seconds']=.001
    elif change=='wrong_duration':j['unload_seconds']=.2
    elif change=='missing_tray':local(peer)['trays'].remove(t)
    elif change=='missing_job':local(peer)['jobs'].remove(j)
    elif change=='duplicate_tray':local(peer)['trays'].append(copy.deepcopy(t))
    elif change=='generation_bool':t['generation']=True
    elif change=='traversal_negative':t['traversal_id']=-1
    elif change=='unresigned_generation':t['generation']+=1;do_resign=False
    elif change=='unresigned_traversal':t['traversal_id']+=1;do_resign=False
    elif change=='future_delivery':peer['delivered_at']=view['now']+.01
    elif change=='expired_source':local(peer)['valid_until']=view['now']
    elif change=='wrong_source':local(peer)['source_owner']='B'
    elif change.startswith('wrong_target_'):
        field={'job':'business_bag_id','generation':'generation','traversal':'traversal_id'}[change.removeprefix('wrong_target_')]
        current[field]='reuse2' if field=='business_bag_id' else current[field]+1
        info['raw_endpoints']['view']=copy.deepcopy(view)
    elif change=='target_committed':current['edge_from']=7;current['edge_to']=3;info['raw_endpoints']['view']=copy.deepcopy(view)
    elif change=='fresh_used':pending['recollection_index']=1
    elif change=='fresh_bool':pending['recollection_index']=False
    elif change=='missing_current_ack':info['raw_endpoints']['command'].pop('last_delivered_ack')
    elif change=='pending_physical':next(r for r in owned.values() if r['kind'] in policy.PHYSICAL_KINDS)['terminal']=False
    elif change=='changed_physical_set':owned.pop(next(k for k,r in owned.items() if r['kind'] in policy.PHYSICAL_KINDS))
    elif change in ('wire_equal','wire_after'):
        wire=policy.original.sequential_epochs(view['now'])['physical_wire'];lt['service_ready_at']=wire if change=='wire_equal' else wire-.001
    elif change=='own_known_missing':lt['service_ready_known']=False
    else:next(r for r in owned.values() if r['kind'] in policy.PHYSICAL_KINDS)['ack']['delivered_at']=view['now']+.001
    if do_resign:resign(peer);resign(own)
    assert policy.retry_admission(info,pending,view,owned)['status']=='not_admitted'


def test_all224_old_screens_preserved_except_exact_two_new_eligibilities():
    ledger=c.read(c.OLD_PLAN.parent/'branch_ledger.json');count=0;changes=[]
    for key in c.ORDER:
        ref=ledger[key]['raw_artifact'];assert c.sha(ref['path'])==ref['sha256']
        raw=json.loads(gzip.decompress(Path(ref['path']).read_bytes()))
        for owner,entries in raw['collection_attempts'].items():
            for entry in entries:
                known,requests,owned=saved.replay_information(raw,owner,entry);count+=1
                if known:continue
                args=(entry['information'],entry['collection'],entry['actual_local_view'],owned)
                previous=policy.old.retry_admission(*args);assert previous==entry['retry_admission']
                candidate=policy.retry_admission(*args)
                if candidate!=previous:
                    assert candidate['status']=='conditional_retry_admissible'
                    changes.append((key,owner,entry['collection']['recollection_index']))
    assert count==224
    assert changes==[(f'insufficient_advance/vector_{n}','B',0) for n in ('16','17')]


def test_actual_adapter_seal_retained_and_unloading_cannot_be_promoted(monkeypatch):
    items=historical_tests.client_fixture('insufficient_advance/vector_16','B',0)
    raw,entry,ep,client,native,accepted,ledger=items
    value=historical_tests.collect_fixture(monkeypatch,items)
    assert adapter.is_native_attempt(value) and not adapter.is_native_collected(value)
    requests=saved.prefix_requests(raw,'B',entry)
    for key,row in saved.owned_at_view(requests,ep['view']).items():
        client.rows[key]['ack']=row['ack'];client.rows[key]['terminal']=row['terminal']
    client.session.submit_protocol_command=lambda request:{'status':'submitted','request_id':request['request_id']}
    instance=policy.OwnerPolicy(native,client.session,client,'B',ledger,None,raw['specification']['vector'],accepted)
    instance.pending=copy.deepcopy(entry['collection']);instance.serial=100
    scoped=instance.decide_pending.__globals__['adapter']
    assert type(scoped) is adapter.OwnerCollectionAdapter and scoped._client is client
    assert instance.decide_pending.__globals__['retry_admission'] is policy.retry_admission
    assert instance.decide_pending.__code__ is policy.original.OwnerPolicy.decide_pending.__code__
    before=len(client.calls);instance.decide_pending(ep['view'])
    assert len(client.calls)==before+1 and not instance.decisions
    assert instance.pending['recollection_index']==1
    assert client.calls[-1]['kind']=='planning_snapshot_v3' and client.calls[-1]['retry'] is False
    assert instance.collection_attempts[0]['information']['status']=='unknown'
    assert instance.collection_attempts[0]['disposition']=='one_fresh_pair_requested'
    assert policy.retry_admission(value,instance.pending,ep['view'],client.owned('B'))['status']=='not_admitted'
    # A real dict-shaped attempt is not a capability; no source generation or
    # traversal mutation can be legalized by recomputing a supplied digest.
    source=value['raw_endpoints']['received'][0]['capture']['capture_v2']['local_capture']
    next(t for t in source['trays'] if t['tray_id']=='E')['generation']+=1
    assert not adapter.is_native_attempt(value)
    assert not adapter.is_native_collected(adapter.json_data(value))


def test_fresh_read_still_unloading_or_missing_terminal_never_has_physical_authority(monkeypatch):
    items=historical_tests.client_fixture('insufficient_advance/vector_16','B',0)
    value=historical_tests.collect_fixture(monkeypatch,items)
    assert value['status']=='unknown' and value['bundle']['reasons']==['stable_observed_unloading']
    pending=copy.deepcopy(items[1]['collection']);pending['recollection_index']=1
    rows=saved.owned_at_view(saved.prefix_requests(items[0],'B',items[1]),items[2]['view'])
    assert policy.retry_admission(value,pending,items[2]['view'],rows)['status']=='not_admitted'
    assert not adapter.is_native_collected(value)
    for env in value['raw_endpoints']['received']:
        assert not any(r['business_bag_id']=='receiver' for r in env['capture']['capture_v2']['extension']['terminal_receipts'])
    assert not adapter.is_native_collected(dict(value))


def test_old91_source_and_history_archives_immutable_and_policy_scope_only():
    assert c.sha(c.OLD_PLAN)==c.OLD_PLAN_SHA
    plan=c.read(c.OLD_PLAN);assert len(plan['source_sha256'])==91
    for p,d in plan['source_sha256'].items():assert c.sha(p)==c.sha(c.OLD_PLAN.parent/plan['source_archive'][p])==d
    for name in ('begin','exchange','_begin_recollection','activate','return_tray','route_tray'):
        assert getattr(policy.OwnerPolicy,name) is getattr(policy.old.OwnerPolicy,name)
    assert policy.PhaseReplyBudget is policy.old.PhaseReplyBudget
    assert policy.old.retry_admission is not policy.retry_admission
