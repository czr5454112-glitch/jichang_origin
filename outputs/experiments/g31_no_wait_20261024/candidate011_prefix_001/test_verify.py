"""Synthetic prefix/lifecycle regressions; no simulator or large evidence reads."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify as v


def reserve(order=1,time=2.0,launch=6.0,sid='a'):
    return dict(kind='source_reserve',ledger_order=order,time=time,segment_id=sid,
                old_generation=0,new_generation=1,current_index=-1,current_node=None,
                planned_admission=launch,goal_arrival=launch+5.0,resource_cleanup_epoch=launch+6.0,
                committed_route=[[0,launch,launch],[1,launch+1.0,launch+3.0],[2,launch+5.0,launch+5.0]],
                node_reservation_ids=[0,11,0],edge_reservation_ids=[12,13],removed_ids=[])


def launch(order=2,time=6.0,sid='a',reference=1):
    return dict(kind='source_launch',ledger_order=order,time=time,segment_id=sid,
                generation=1,index=0,node=0,reference_reservation_order=reference)


def arrival(order,time,index,node,sid='a',generation=1):
    return dict(kind='arrival',ledger_order=order,time=time,segment_id=sid,
                generation=generation,index=index,node=node)


def cleanup(order,time,sid='a',valid=True,generation=1,removed=None):
    return dict(kind='cleanup',ledger_order=order,time=time,segment_id=sid,valid=valid,
                event_generation=generation,current_generation=generation,
                removed_ids=([11,12,13] if valid else []) if removed is None else removed)


def bag():
    # An independently specified short observation: actual attempt at 0,
    # rights booked at 2 for launch 6, but observation ends at 3.
    return dict(segment_id='a',task_id=1,leg='direct',start=0,goal=2,
                activation_time=0.0,first_planning_attempt_time=0.0,
                admission=None,admitted=False,completed=False,actual_finish=None,
                finish=None,route=[],node_reservation_ids=[],edge_reservation_ids=[],
                actual_arrived_index=-1,route_generation=1,resource_cleanup_epoch=None,
                resource_cleanup_time=None,commit_time=None,planning_time=None,commit_order=None,
                future_reserved=True,future_pending=True,reservation_time=2.0,reservation_order=1,
                planned_admission=6.0,planned_finish=11.0,planned_resource_cleanup_epoch=12.0,
                reserved_route=[[0,6.0,6.0],[1,7.0,9.0],[2,11.0,11.0]],
                reserved_node_reservation_ids=[0,11,0],reserved_edge_reservation_ids=[12,13])


def launched_bag(*,completed=False):
    b=bag()
    b.update(admission=6.0,admitted=True,future_pending=False,finish=11.0,
             route=deepcopy(b['reserved_route']),node_reservation_ids=[0,11,0],edge_reservation_ids=[12,13],
             actual_arrived_index=2 if completed else 0,resource_cleanup_epoch=12.0,
             resource_cleanup_time=12.0,commit_time=6.0,planning_time=6.0,commit_order=1,
             completed=completed,actual_finish=11.0 if completed else None)
    return b


def state(*events):
    s=v.PrefixState()
    for e in events:s.apply(e)
    return s


def write_json(path,value):
    Path(path).write_text(json.dumps(value,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')


def write_lines(path,rows):
    Path(path).write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in rows),encoding='utf-8')


def test_pending_rights_survive_cutoff_without_actual_admission():
    s=state(reserve())
    assert s.compare_short_bag(bag(),3.0)==[]
    assert s.ids(s.states['a'])=={11,12,13}
    assert s.commit_counter==0
    assert v.compare_future_evidence(bag(),launched_bag(completed=True),3.0)==[]


@pytest.mark.parametrize('field,value',[('future_pending',False),('admission',6.0),('finish',11.0),
                                       ('actual_finish',11.0),('route',[[0,6.0,6.0]]),('commit_order',1)])
def test_pending_cannot_leak_actual_fields(field,value):
    b=bag();b[field]=value
    assert state(reserve()).compare_short_bag(b,3.0)


def test_launch_at_cutoff_is_included_without_rebooking():
    s=state(reserve(),launch())
    assert s.compare_short_bag(launched_bag(),6.0)==[]
    assert s.ids(s.states['a'])=={11,12,13}
    assert s.commit_counter==1
    assert v.compare_future_evidence(launched_bag(),launched_bag(completed=True),6.0)==[]


@pytest.mark.parametrize('changes',[{'time':5.999999},{'time':6.000001},
                                    {'reference_reservation_order':2},{'node_reservation_ids':[11]}])
def test_launch_must_consume_exact_certificate(changes):
    e=launch();e.update(changes)
    with pytest.raises(ValueError):state(reserve(),e)


def test_due_launch_cannot_be_silently_missing():
    assert 'missing_due_launch' in state(reserve()).compare_short_bag(bag(),6.0)


def test_pending_cannot_be_cleaned_but_stale_cleanup_does_not_remove_rights():
    with pytest.raises(ValueError):state(reserve(),cleanup(2,3.0))
    s=state(reserve(),cleanup(2,3.0,valid=False))
    assert s.compare_short_bag(bag(),3.0)==[]
    assert s.ids(s.states['a'])=={11,12,13}


def test_actual_goal_exactly_at_cutoff_is_complete_cleanup_can_be_later():
    s=state(reserve(),launch(),arrival(3,7.0,1,1),arrival(4,11.0,2,2))
    assert s.compare_short_bag(launched_bag(completed=True),11.0)==[]
    assert not s.states['a']['cleaned']
    assert 'missing_due_cleanup' in s.compare_short_bag(launched_bag(completed=True),12.0)
    s.apply(cleanup(5,12.0))
    assert s.compare_short_bag(launched_bag(completed=True),12.0)==[]


def test_source_equals_goal_finishes_at_launch_and_retains_two_second_right():
    r=reserve();r.update(committed_route=[[0,6.0,8.0]],node_reservation_ids=[11],edge_reservation_ids=[],
                         goal_arrival=6.0,resource_cleanup_epoch=8.0)
    s=state(r,launch())
    assert s.states['a']['actual_finish']==6.0
    assert not s.states['a']['cleaned']
    s.apply(cleanup(3,8.0,removed=[11]))
    assert s.states['a']['cleaned']


def test_later_rolling_route_does_not_replace_short_certificate(tmp_path):
    s=state(reserve(),launch())
    short=launched_bag()
    drained=launched_bag(completed=True)
    drained.update(route=[[0,6.0,6.0],[1,7.0,9.0],[3,9.5,9.5],[2,10.0,10.0]],
                   route_generation=2,finish=10.0,actual_finish=10.0,actual_arrived_index=3,
                   node_reservation_ids=[0,11,0,0],edge_reservation_ids=[12,21,22],
                   resource_cleanup_epoch=12.0,resource_cleanup_time=12.0,attempts=999)
    a=tmp_path/'short.jsonl';b=tmp_path/'drain.jsonl';write_lines(a,[short]);write_lines(b,[drained])
    assert v.stream_bags(a,b,6.0,s)['passed']
    # Importing that later suffix into the short artifact is specifically rejected.
    short['route']=drained['route'];write_lines(a,[short])
    assert not v.stream_bags(a,b,6.0,s)['passed']


def test_replacement_before_cutoff_preserves_initial_reserved_provenance():
    s=state(reserve(),launch(),arrival(3,7.0,1,1))
    replacement=dict(kind='replace_commit',ledger_order=4,time=7.0,segment_id='a',old_generation=1,
                     new_generation=2,current_index=1,committed_route=[[0,6.0,6.0],[1,7.0,9.0],[2,10.0,10.0]],
                     node_reservation_ids=[0,11,0],edge_reservation_ids=[12,21],removed_ids=[13],
                     resource_cleanup_epoch=11.0)
    s.apply(replacement)
    b=launched_bag();b.update(route=replacement['committed_route'],route_generation=2,actual_arrived_index=1,
                              finish=10.0,edge_reservation_ids=[12,21],resource_cleanup_epoch=11.0,resource_cleanup_time=11.0)
    assert s.compare_short_bag(b,7.0)==[]
    assert b['planned_finish']==11.0 and b['reserved_edge_reservation_ids']==[12,13]
    assert s.commit_counter==2 and b['commit_order']==1


def test_future_attempt_and_reservation_are_excluded_from_short_observation():
    old=bag();old.update(activation_time=None,first_planning_attempt_time=None,route_generation=0,actual_arrived_index=0,
                        future_reserved=False,future_pending=False)
    for k in v.FUTURE_CLOCKS+('reservation_order',):old[k]=None
    for k in v.FUTURE_ARRAYS:old[k]=[]
    new=bag();new.update(activation_time=4.0,first_planning_attempt_time=4.0,reservation_time=5.0)
    assert v.base.compare_bag_prefix(old,new,3.0)==[]
    assert v.compare_future_evidence(old,new,3.0)==[]
    assert state().compare_short_bag(old,3.0)==[]
    old['first_planning_attempt_time']=4.0
    assert v.base.compare_bag_prefix(old,new,3.0)


def test_initial_reservation_provenance_cannot_be_mutated_in_drain():
    new=launched_bag(completed=True);new['reserved_edge_reservation_ids']=[12,99]
    assert v.compare_future_evidence(bag(),new,3.0)


def test_same_time_global_order_and_future_right_bytes_are_exact(tmp_path):
    a=tmp_path/'a.jsonl';b=tmp_path/'b.jsonl'
    r=reserve();r2=reserve(2,2.0,8.0,'b');r2['node_reservation_ids']=[0,21,0];r2['edge_reservation_ids']=[22,23]
    write_lines(a,[r,r2]);write_lines(b,[r,r2,launch(3,6.0)])
    result,s=v.stream_ledger(a,b,2.0)
    assert result['passed'] and result['prefix_records']==2
    assert len(s.states)==2 and s.commit_counter==0
    modified=deepcopy(r2);modified['node_reservation_ids'][1]=31;write_lines(b,[r,modified,launch(3,6.0)])
    assert not v.stream_ledger(a,b,2.0)[0]['passed']
    r_rev=deepcopy(r2);r_rev['ledger_order']=1;r_next=deepcopy(r);r_next['ledger_order']=2
    write_lines(b,[r_rev,r_next,launch(3,6.0,reference=2)])
    assert not v.stream_ledger(a,b,2.0)[0]['passed']


def test_short_events_after_cutoff_and_gapped_order_rejected(tmp_path):
    a=tmp_path/'a.jsonl';b=tmp_path/'b.jsonl';write_lines(a,[reserve(),launch()]);write_lines(b,[reserve(),launch()])
    with pytest.raises(ValueError,match='beyond'):v.stream_ledger(a,b,3.0)
    with pytest.raises(ValueError,match='missing'):state(reserve(order=2))


def make_run(directory,end,rows,events):
    directory.mkdir();sources=directory/'standard_sources';sources.mkdir()
    controls=dict(end_time=end,enable_inroute_replanning=True,future_source_reservation_horizon_seconds=60)
    write_json(sources/'controls.json',controls);write_json(sources/'contract.json',dict(end_time=end,version='synthetic'))
    (sources/'auditor.py').write_text('# synthetic frozen identity only\n',encoding='utf-8')
    write_lines(directory/'bags.jsonl',rows);write_lines(directory/'rolling_events.jsonl',events)
    for name in v.AUDITS:write_json(directory/name,dict(passed=True,fixture_only=True))
    identity=dict(sha256='fixed-synthetic-identity')
    selection=dict(execution_model='continuous_motion',map='synthetic',scale='1x',business_denominator=1,segment_denominator=1,
                   effective_controls=controls,**{k:identity for k in ('binary','canonical','profile','build_receipt','native_source')})
    m=dict(schema='g31.continuous.run.v1',status='complete',audits_passed=True,
           full_population_performance_available=False,selection=selection,
           source_sha256={p.name:v.base.file_sha(p) for p in sources.iterdir()},bags_sha256=v.base.file_sha(directory/'bags.jsonl'))
    write_json(directory/'manifest.json',m)
    write_json(directory/'native_summary.json',dict(event_budget_exhausted=False,executed_horizon=end,tasks=1,rolling_ledger_records=len(events)))


def test_run_accepts_censored_actual_short_with_five_passed_gates(tmp_path):
    a=tmp_path/'short';b=tmp_path/'drain'
    make_run(a,3.0,[bag()],[reserve()])
    make_run(b,20.0,[launched_bag(completed=True)],[reserve(),launch(),arrival(3,7.0,1,1),arrival(4,11.0,2,2),cleanup(5,12.0)])
    result=v.run(a,b,3.0)
    assert result['passed'] and result['bags']['future_pending']==1
    assert result['bags']['admitted']==0 and result['prefix_state']['live_rights']==3
    write_json(a/'headway_audit.json',dict(passed=False))
    with pytest.raises(ValueError,match='audit did not pass'):v.run(a,b,3.0)


def test_run_rejects_missing_ledger_records_even_with_manifest_passed(tmp_path):
    a=tmp_path/'short';b=tmp_path/'drain'
    make_run(a,3.0,[bag()],[reserve()]);make_run(b,20.0,[launched_bag(completed=True)],[reserve(),launch()])
    summary=v.base.read(a/'native_summary.json');summary['rolling_ledger_records']=99;write_json(a/'native_summary.json',summary)
    with pytest.raises(ValueError,match='record count'):v.run(a,b,3.0)


def test_same_directory_cannot_be_called_independent_run(tmp_path):
    with pytest.raises(ValueError,match='distinct'):v.run(tmp_path,tmp_path,3.0)
