"""Functional/fake-clock harness guards; never execute the256-call ABBA here."""
from copy import deepcopy
import inspect
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import measure_bridge_copy_scopes as m
from scripts.experiments.g31_ics_circulation import launch_bridge_copy_scopes as launch


def record_fixture():
    records=[];batches=[];t=100
    input_hashes={family:'a'*64 for family in m.FAMILIES};result_hashes={family:'b'*64 for family in m.FAMILIES}
    for family in m.FAMILIES:
        for batch,arm in enumerate(m.ARMS):
            start=t;t+=1
            for index in range(m.PER_BATCH):
                records.append(dict(family=family,batch=batch,arm=arm,index=index,started_ns=t,
                    fixture_finished_ns=t+1,isolated_started_ns=t+2,isolated_finished_ns=t+3,checked_ns=t+4,
                    isolated_ns=1,cpu_ns=1,input_sha256=input_hashes[family],result_sha256=result_hashes[family],guards_and_aliases_passed=True))
                t+=5
            batches.append(dict(family=family,batch=batch,arm=arm,started_ns=start,finished_ns=t,whole_ns=t-start));t+=1
    return records,batches,input_hashes,result_hashes


def test_original_seed_ast_source_and_serial_submit_no_old_ack_mutation():
    proof=m.source_review();assert proof['synthetic_seed_AST_exact']
    assert len(proof['readonly_dependency_sources'])==8
    case=m.f.make_case('temporary_own_capture');session=m.f.QuerySession({})
    client=m.f.c.protocol.ProtocolClient(session,retry_period=60.,state=dict(
        schema='g31.protocol_client_state.v1',retry_period=60.,rejection_cooldown=.2,forecast_validity=120.,sequences={},outbox=case['box']))
    own=m.f.c._BORROWED_OWN(client.state['outbox'],'A','B',10.,case['nodes']);before=m.encoded(own)
    value=SimpleNamespace(client=client,owner='A',peer='B',publications=16,next_publication=10.,bridge_publications=[],failure=None)
    rid=m.f.c.policy.BridgeOwner.publish(value,10.,{'kind':'synthetic_alias_probe'})
    assert rid in client.state['outbox'] and m.encoded(own)==before
    assert own['ack'] is client.state['outbox']['snapshot:15']['client_view']['last_delivered_ack']
    assert len(client.calls)==1 and client.calls[0]['request']['request_id']==rid


@pytest.mark.parametrize('family',m.FAMILIES)
def test_exact64jobs16revisions_fresh_per_invocation_and_A_B_equivalence(family):
    cases=[m.f.make_case(family) for _ in range(2)];payloads=[]
    assert m.tree(m.inputs(cases[0])).isdisjoint(m.tree(m.inputs(cases[1])))
    for arm,case in zip(('A','B'),cases):
        assert len([r for r in case['box'].values() if r['kind']=='planning_snapshot_v2'])==16
        assert len(case['peer']['capture']['local_capture']['jobs'])==64
        if family=='temporary_own_capture':
            assert all(len(r['client_view']['last_delivered_ack']['planning_snapshot_v2']['capture']['local_capture']['jobs'])==64
                for r in case['box'].values() if r['kind']=='planning_snapshot_v2')
        before=m.encoded(m.inputs(case));result=m.f.invoke(case,arm)
        payloads.append(m.checked_result(case,arm,result,before))
    assert m.exact(*payloads)


@pytest.mark.parametrize('defect',['query_order','input_mutation','client_alias','unexpected_submit'])
def test_refresh_comparison_rejects_changed_behavior(defect):
    case=m.f.make_case('discard_refresh');before=m.encoded(m.inputs(case));result=m.f.invoke(case,'B')
    if defect=='query_order':case['session'].calls.reverse()
    elif defect=='input_mutation':case['peer']['status']='changed'
    elif defect=='client_alias':case['client'].state['outbox']['snapshot:00']['client_view']=case['session'].responses['snapshot:00']
    else:case['client'].calls.append({'unexpected':'retry'})
    with pytest.raises(ValueError):m.checked_result(case,'B',result,before)


@pytest.mark.parametrize('defect',['borrow_identity','selected_value','consumer_alias','wrong_choice'])
def test_selector_full_value_and_alias_guards(defect):
    case=m.f.make_case('temporary_own_capture');before=m.encoded(m.inputs(case));own,barrier,choice=m.f.invoke(case,'B')
    if defect=='borrow_identity':own=deepcopy(own)
    elif defect=='selected_value':own={**own,'request_id':'snapshot:00'}
    elif defect=='consumer_alias':barrier['bad_alias']=case['view']['trays']
    else:choice['selected_current_job']['business_bag_id']='peer:001'
    with pytest.raises(ValueError):m.checked_result(case,'B',(own,barrier,choice),before)


@pytest.mark.parametrize('family',m.FAMILIES)
def test_inputs_rebuilt_after_failure_no_shared_history(family):
    a=m.f.make_case(family);a['peer']['capture']['local_capture']['jobs'].clear()
    b=m.f.make_case(family);assert len(b['peer']['capture']['local_capture']['jobs'])==64
    assert m.tree(m.inputs(a)).isdisjoint(m.tree(m.inputs(b)))


@pytest.mark.parametrize('a,b',[(1,1.),(True,1),(0.,-0.),({'a':1,'b':2},{'b':2,'a':1})])
def test_order_and_scalar_type_are_not_Python_equal(a,b):
    assert not m.exact(a,b)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),{1:'bad'},(1,),object()])
def test_nonclosed_domain_rejected(value):
    with pytest.raises(ValueError):m.encoded(value)


def test_cycle_and_duplicate_key_and_artifact_limit():
    cycle=[];cycle.append(cycle)
    with pytest.raises(ValueError,match='cycle'):m.encoded(cycle)
    with pytest.raises(ValueError,match='duplicate_key'):m.loads(b'{"a":1,"a":2}')
    with pytest.raises(ValueError,match='artifact_size'):m.encoded('x'*m.MAX_BYTES)


def test_256_full_records_and8_batches_strict_fake_clock_accounting():
    args=record_fixture();summary=m.check_records(*args)
    assert len(args[0])==256 and len(args[1])==8
    assert summary['discard_refresh']['A']['median_isolated_batch_ms']==.000032
    assert summary['temporary_own_capture']['B']['median_whole_batch_ms']==.000161


@pytest.mark.parametrize('defect',['missing','extra','reorder','clock_bool','index_bool','clock_formula','clock_overlap',
    'hash','alias_flag','extra_field','batch_missing','batch_bool','batch_excludes_fixture','batch_formula'])
def test_saved_record_counterexamples(defect):
    records,batches,ih,rh=record_fixture()
    if defect=='missing':records.pop()
    elif defect=='extra':records.append(deepcopy(records[-1]))
    elif defect=='reorder':records[1],records[2]=records[2],records[1]
    elif defect=='clock_bool':records[0]['started_ns']=True
    elif defect=='index_bool':records[0]['index']=False
    elif defect=='clock_formula':records[0]['isolated_ns']=2
    elif defect=='clock_overlap':records[1]['started_ns']=records[0]['started_ns']
    elif defect=='hash':records[0]['result_sha256']='c'*64
    elif defect=='alias_flag':records[0]['guards_and_aliases_passed']=1
    elif defect=='extra_field':records[0]['failed_but_skipped']=True
    elif defect=='batch_missing':batches.pop()
    elif defect=='batch_bool':batches[0]['whole_ns']=True
    elif defect=='batch_excludes_fixture':batches[0]['started_ns']=records[0]['fixture_finished_ns']
    else:batches[0]['whole_ns']-=1
    with pytest.raises(ValueError):m.check_records(records,batches,ih,rh)


@pytest.mark.parametrize('defect',['counts','order','limit'])
def test_fixed_plan_rejects_retuning(defect):
    p={'schema':m.SCHEMA,'counts':deepcopy(m.COUNTS),'arms':list(m.ARMS),'families':list(m.FAMILIES),'shared_seconds':m.LIMIT}
    if defect=='counts':p['counts']['measured_invocations']=128
    elif defect=='order':p['arms'].reverse();p['arms'][0]='B'
    else:p['shared_seconds']=121.
    with pytest.raises(ValueError,match='plan_scope'):m.validate_plan(p)


def test_outer_job_owns_whole_campaign_and_verification_not_only_timed_calls():
    text=inspect.getsource(launch.main)
    assert launch.MODULE==m.MODULE and launch.LIMIT==m.LIMIT==120.
    assert "'--campaign-child'" in text and 'bounded_windows_job.run' in text
    assert 'time.perf_counter()-BOOT' in text and 'outer_claim.json' in text
    assert m.LAUNCHER.endswith('.launch_bridge_copy_scopes')
    assert "saved_check(output,plan,expected)" in inspect.getsource(m.worker)
    assert 'verify_pins(output,plan,runtime=True)' in inspect.getsource(m.saved_check)
