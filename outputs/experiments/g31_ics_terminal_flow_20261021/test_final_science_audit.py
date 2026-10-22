"""Pure tests only. Never imports frozen actors or opens native result files."""
import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import pytest

path=Path(__file__).with_name('final_science_audit_004.py')
spec=importlib.util.spec_from_file_location('final_science_driver',path)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def test_workflow_resolves_only_four_full_dev_blocks_and_binds_source(tmp_path):
    root=tmp_path/'terminal_flow';directory=root/'workflow_005';directory.mkdir(parents=True)
    source=dict(path='frozen/source_manifest.json',sha256='frozenhash')
    stages=[dict(phase=p,name=p+'_all_005',parents=list(audit.PARENTS)) for p in audit.PHASES]
    stages.extend([dict(phase='export_gate',name='old_gate',parents=[2101]),dict(phase='train_demand',name='training',parents=[2101,2102])])
    registration=directory/'registration.json'
    registration.write_text(json.dumps(dict(schema='g31.terminal_flow.finite_development_workflow.v1',
        source_bundle=source,stages=stages,TEST_unlocked=False,R1_enabled=False)),encoding='utf8')
    paths,binding=audit.workflow_blocks(registration,source)
    assert len(paths)==4 and all('all_005' in str(p) for p in paths)
    assert binding==audit.bind(registration)
    with pytest.raises(ValueError,match='workflow_source_binding'):
        audit.workflow_blocks(registration,dict(source,sha256='wrong'))

def test_missing_blocks_are_pending_and_cannot_execute(tmp_path):
    rows,status=audit.inspect_blocks([tmp_path/f'{i}.json' for i in range(4)],{}, {})
    assert status['status']=='pending' and len(status['pending'])==4
    with pytest.raises(ValueError,match='pending_runs_prohibit'):
        audit.execute(rows,status,{}, {}, {},tmp_path/'science')
    assert not (tmp_path/'science').exists()


def test_exact_28_run_matrix_and_24_scientific_pairs_required(tmp_path):
    source=dict(path='frozen/source_manifest.json',sha256='source')
    paths=[]
    for phase,methods in audit.PHASES.items():
        block=tmp_path/phase/'block.json';block.parent.mkdir()
        refs=[]
        for parent in audit.PARENTS:
            for method in methods:
                directory=block.parent/f'{parent}_{method}';directory.mkdir()
                plan=dict(task_id=f'{parent}_{method}',method=method,source_bundle=source,horizon=59400.,activation=7200.,
                    parent=dict(parent_seed=parent,split='dev',synthetic=True,common_historical_template_sha256='template'))
                refs.append(audit.fresh(directory/'plan.json',plan))
                audit.fresh(directory/'receipt.json',dict(worker=dict(scientific_status='closed',policy_timing=dict(
                    count=1,total_seconds=1.,scope='callback',stages={},stage_scope=dict(excluded=['native']),
                    complete_request_100ms_certified=False))))
        audit.fresh(block,dict(phase=phase,source_bundle=source,parents=list(audit.PARENTS),methods=methods,task_plans=refs))
        paths.append(block)
    h=dict(campaign=SimpleNamespace(_validate_block_manifest=lambda b:None,method_contract_errors=lambda p:[],
        comparison_contract=lambda p:dict(parent=p['parent'],source=p['source_bundle'])),
        flow=SimpleNamespace(closed_run=lambda p:None))
    rows,status=audit.inspect_blocks(paths,source,h)
    assert status['status']=='ready' and len(rows)==status['registered_runs']==28
    assert len(status['pair_contracts'])==24
    assert {(r['reference_method'],r['candidate_method']) for r in status['pair_contracts']}==set(audit.PAIRS)
    last=audit.read(paths[-1]);last['task_plans'].pop()
    paths[-1].write_text(json.dumps(last),encoding='utf8')
    with pytest.raises(ValueError,match='all_28_registered_runs_required'):audit.inspect_blocks(paths,source,h)

def test_registered_axis_does_not_allow_source_or_allocator_change():
    a=dict(source='same',allocator='same',demand_information='current')
    b=dict(a,demand_information='forecast')
    assert set(audit.pair_contract(a,b,['demand_information'],dict)['observed_differences'])=={'demand_information'}
    with pytest.raises(ValueError,match='unregistered_pair_axis'):
        audit.pair_contract(a,dict(b,source='different'),['demand_information'],dict)

def test_cached_original_solve_time_is_counted_once_and_mutation_fails():
    d=lambda pid,t:dict(selection=dict(flow_plan=dict(plan_id=pid,solve_seconds=t)))
    result=audit.unique_solve_cost([d('a',.1),d('a',.1),d('b',.2)])
    assert result['unique_plans']==2 and result['total_original_solve_seconds']==pytest.approx(.3)
    with pytest.raises(ValueError,match='same_plan_changed'):
        audit.unique_solve_cost([d('a',.1),d('a',.2)])

def test_average_gain_does_not_erase_tail_service_rejection():
    rows=[dict(parent=p,gain_bag_seconds=10.,completion_direction=dict(known_direction_harm=int(i==0)),
        known_lateness_harm=int(i==0),completed_delta=1,on_time_delta=-int(i==0),
        existing_observed_service_gate_passed=i!=0) for i,p in enumerate(audit.PARENTS)]
    r=audit.aggregate_pairs(rows)
    assert r['mean_gain_bag_seconds']==10 and r['any_parent_service_rejection']
    assert not r['all_parent_observed_service_gates_passed'] and not r['promotion_approved']
    assert r['known_completion_harm_parent_bag_cases']==1

def test_observation_join_validates_digest_time_owner_and_two_owner_order():
    def digest(x):return json.dumps(x,sort_keys=True)
    obs=[dict(now=t,owner_id=o) for t,o in [(0,'a'),(0,'b'),(60,'a'),(60,'b')]]
    def stream(path):
        for o in obs:yield dict(digest=digest(o),observation=o)
    h=dict(stream=SimpleNamespace(iter_json_array_gz=stream),digest=SimpleNamespace(digest=digest))
    join=audit.ObservationJoin(Path('.'),[],h,100)
    for o in obs:
        d=dict(public_observation_ref=digest(o),decision_time=o['now'],owner_id=o['owner_id'])
        assert join.get(d)==o
    with pytest.raises(ValueError,match='time_owner_mismatch'):
        join.get(dict(public_observation_ref=digest(obs[-1]),decision_time=60,owner_id='a'))
    def bad(path):yield dict(digest='tampered',observation=obs[0])
    h['stream']=SimpleNamespace(iter_json_array_gz=bad)
    with pytest.raises(ValueError,match='observation_digest_mismatch'):
        audit.ObservationJoin(Path('.'),[],h,100).next()

def test_failed_or_never_submitted_action_is_not_an_in_transit_censor():
    def row(identity,request):
        return dict(decision_id=identity,owner_id='a',decision_time=10.,request_id=request,
            requested_action=dict(kind='transfer',source=1,destination=2,tray_id=identity,
                source_category='loader_optional',nominal_arrival_time=20.),ack=None,
            actual_submission=None if request is None else dict(request_id=request))
    result=audit.selected_lifecycle(dict(rows=[row('failed','r'),row('not_submitted',None)],physical_clock=100.),
        dict(transfers=[dict(request_id='r',status='failed',received_at=-1.)]))
    assert len(result)==2 and result[0]['failed'] and result[1]['missing_execution']
    assert not any(r['right_censored'] for r in result)
    assert all(r['unreceived_eta_lateness_lower_bound_seconds'] is None for r in result)

def test_local_service_retains_both_unfinished_and_future_denominators():
    rows=[dict(business_bag_id='a',reference=dict(status='unfinished_overdue'),candidate=dict(status='unfinished_overdue'),
        category='both_arrived_unfinished',lateness_direction='unknown_censored'),
        dict(business_bag_id='b',reference=dict(status='not_yet_arrived'),candidate=dict(status='not_yet_arrived'),
        category='both_not_yet_arrived',lateness_direction='unknown_not_yet_arrived')]
    result=audit.local_service(rows,[dict(business_bag_id='a',origin=24),dict(business_bag_id='b',origin=24)])
    assert result['24']['population']==2 and result['24']['completion']['both_arrived_unfinished']==1
    assert result['24']['reference']['not_yet_arrived']==1

def test_gzip_outputs_are_deterministic_and_never_overwritten(tmp_path):
    a=tmp_path/'a.json.gz';b=tmp_path/'b.json.gz';data=dict(rows=[dict(value=1.)])
    audit.fresh(a,data);audit.fresh(b,data)
    assert a.read_bytes()==b.read_bytes() and audit.read(a)==data
    with pytest.raises(ValueError,match='fresh_output_required'):audit.fresh(a,data)


def test_producer_entry_binding_rejects_changed_file_before_completion(tmp_path):
    producer=tmp_path/'producer.py';producer.write_text('version = 1\n',encoding='utf8')
    entry=audit.bind(producer)
    audit.verify_bindings([entry],'analysis_driver_changed_during_audit')
    producer.write_text('version = 2\n',encoding='utf8')
    with pytest.raises(ValueError,match='analysis_driver_changed_during_audit'):
        audit.verify_bindings([entry],'analysis_driver_changed_during_audit')
    with pytest.raises(ValueError,match='analysis_driver_changed_before_execution'):
        audit.execute({},dict(status='ready'),{}, {}, {},tmp_path/'science',producer_ref=entry)
    assert not (tmp_path/'science').exists()


def test_publication_limit_is_decimal_and_boundary_rejected(tmp_path,monkeypatch):
    assert audit.PUBLICATION_LIMIT_BYTES==95_000_000
    ref=audit.fresh(tmp_path/'a.json',dict(a=1))
    assert ref['publication_size_limit_bytes']==95_000_000
    monkeypatch.setattr(audit,'PUBLICATION_LIMIT_BYTES',ref['bytes'])
    with pytest.raises(ValueError,match='artifact_over_publication_limit'):
        audit.fresh(tmp_path/'b.json',dict(a=1))


def test_decision_join_rejects_duplicate_missing_and_cross_file_mismatch():
    def row(identity,at):
        return dict(decision_id=identity,owner_id='a',decision_time=at,public_observation_ref='obs'+identity,
            legal_catalog_ref='catalog',catalog=dict(catalog_id='catalog'),requested_action=dict(kind='noop'))
    a,b=row('a',0),row('b',60)
    join=audit.DecisionJoin([a,b],0,100)
    assert join.accept(a)
    with pytest.raises(ValueError,match='duplicate_selected_decision_id'):join.accept(a)
    with pytest.raises(ValueError,match='selected_trajectory_decision_missing'):join.finish()
    assert join.accept(b);join.finish()
    assert not join.accept(row('horizon',100))
    with pytest.raises(ValueError,match='in_window_decision_missing_from_trajectory'):join.accept(row('extra',90))
    for field,value in [('owner_id','b'),('decision_time',1),('public_observation_ref','other'),
                        ('legal_catalog_ref','other'),('requested_action',dict(kind='transfer'))]:
        with pytest.raises(ValueError,match='decision_trajectory_mismatch:'+field):
            audit.DecisionJoin([a,b],0,100).accept(dict(a,**{field:value}))
    with pytest.raises(ValueError,match='decision_catalog_binding_mismatch'):
        audit.DecisionJoin([a],0,100).accept(dict(a,catalog=dict(catalog_id='other')))
    with pytest.raises(ValueError,match='duplicate_trajectory_decision_id'):audit.DecisionJoin([a,a],0,100)
    with pytest.raises(ValueError,match='duplicate_trajectory_owner_time'):audit.DecisionJoin([a,row('other',0)],0,100)


def test_distinct_order_comparison_and_same_state_scope_are_not_plan_ids():
    a=dict(owner_id='a',at=60,public_state='same',catalog='same',action=['noop',None,None,None])
    b=dict(a,action=['transfer','t',1,2])
    c=dict(owner_id='a',selected_at=60,tray_id='t',source=1,destination=2,actual_submission=dict(request_id='r'))
    left=dict(decision_choices=[a],selected_transfer_lifecycle=[])
    right=dict(decision_choices=[b],selected_transfer_lifecycle=[c])
    result=audit.compare_choices(left,right)
    assert result['actual_action_changes']==result['same_state_action_changes']==1
    assert result['candidate_only_actual_selected_orders']==[c]
    changed=audit.compare_choices(left,dict(right,decision_choices=[dict(b,public_state='changed')]))
    assert changed['actual_action_changes']==1 and changed['same_state_action_changes']==0
    with pytest.raises(ValueError,match='duplicate_comparison_owner_time'):
        audit.compare_choices(left,dict(right,decision_choices=[b,b]))
    with pytest.raises(ValueError,match='duplicate_submitted_order_signature'):
        audit.compare_choices(left,dict(right,selected_transfer_lifecycle=[c,c]))


def test_run_binds_inputs_before_reads_and_validates_noop_observations(tmp_path,monkeypatch):
    digest=lambda obj:json.dumps(obj,sort_keys=True)
    obs=[dict(now=t,owner_id=o) for t,o in [(0,'a'),(0,'b'),(60,'a'),(60,'b')]]
    rows=[dict(decision_id=str(i),owner_id=o['owner_id'],decision_time=o['now'],public_observation_ref=digest(o),
        legal_catalog_ref='catalog',catalog=dict(catalog_id='catalog'),requested_action=dict(kind='noop'),selection={})
        for i,o in enumerate(obs)]
    for name in audit.RUN_EVIDENCE_FILES:
        audit.fresh(tmp_path/name,dict(transfers=[]) if name=='terminal_evidence.json.gz' else {})
    events=[];original_bind=audit.bind
    def bind(path):events.append(Path(path).name);return original_bind(path)
    monkeypatch.setattr(audit,'bind',bind)
    def closed_run(path):
        assert events==list(audit.RUN_EVIDENCE_FILES)
        return (dict(task_id='run',method='C00',parent=dict(parent_seed=2201),activation=0.,horizon=100.),
            dict(worker=dict(policy_timing={},wall_seconds=1.,peak_memory_bytes=1)),dict(rows=rows,physical_clock=100.))
    def stream(path):
        if path.name=='decisions.json.gz':yield from rows
        elif path.name=='observations.json.gz':yield from [dict(digest=digest(o),observation=o) for o in obs]
        elif path.name!='calls.json.gz':raise AssertionError('unexpected input '+str(path))
    def coverage(stream,rows):return dict(decision_counts=dict(valid_decisions=len(list(stream))))
    h=dict(flow=SimpleNamespace(closed_run=closed_run,audit_records=lambda *a:dict(violations=[],plans=[])),
        stream=SimpleNamespace(iter_json_array_gz=stream),digest=SimpleNamespace(digest=digest),
        behavior=SimpleNamespace(decision_coverage=coverage,source_windows=lambda *a,**k:[],reverse_requests=lambda *a,**k:[]),
        timing=SimpleNamespace(_summary=lambda values:{}))
    result=audit.run_audit(dict(directory=tmp_path),h)
    assert result['timing']['validated_decision_observation_count']==4
    assert result['timing']['observations_read']==4 and result['evidence_bound_before_consumption']
    assert set(result['evidence'])==set(audit.RUN_EVIDENCE_FILES)
    assert 'delivered_ack_evidence.json.gz' not in events
    # All-HOLD/C00 decisions previously bypassed the observation join entirely.
    events.clear();obs[-1]=dict(obs[-1],owner_id='tampered')
    with pytest.raises(ValueError,match='bound_observation_missing'):
        audit.run_audit(dict(directory=tmp_path),h)

def test_current_only_null_forecast_and_pending_claim_exclusion():
    candidates=[dict(action_id=str(n),action_type='transfer',source_category='loader_optional',
        source=1,destination=n,tray_id='tray',nominal_arrival_time=10.,earliest_departure=2.,static_travel_time=8.) for n in (2,3)]
    plan=dict(receiver_claims_deducted={},station_table=[dict(node=n,receiver=dict(known=True,available_slots=1)) for n in (2,3)],
        config=dict(marginal_reference_available_offset_seconds=2.,transport_penalty_weight=.01,minimum_net_gain=0.),
        projection_horizon_seconds=600.,supply_mode='committed_only')
    d=dict(selection=dict(flow_plan=plan),flow_verification=dict(invalid=[]),requested_action=dict(kind='noop'),
        catalog=dict(candidates=candidates),forecast_binding=None,owner_id='a',decision_id='d',decision_time=0.,
        candidate_features={str(n):dict(features_current=dict(current_proxy_gain=2.)) for n in (2,3)})
    seen=[]
    def prepare(obs,**kw):seen.append(kw['forecast']);return SimpleNamespace(now=0.)
    h=dict(projection=SimpleNamespace(prepare_inventory_projection=prepare,project_action=lambda p,c:dict(proxy_gain=2.,known=True)),
        allocation=SimpleNamespace(transport_cost=lambda c,config:0.),
        timing=SimpleNamespace(_identity=lambda c:None if c is None else [c['source'],c['destination']]))
    stats=lambda:dict(counts=Counter(),invalid=Counter(),gain_gaps=[],examples=[])
    first=stats();audit.timing_decision(d,h,SimpleNamespace(get=lambda d:{}),{},dict(a={}),first)
    assert seen==[None] and first['counts']['known_multi_od_ranking_opportunities']==1
    plan['receiver_claims_deducted']={'2':1};second=stats()
    audit.timing_decision(d,{},None,None,None,second)
    assert second['counts']['excluded_pending_claims_no_counterfactual_reconstruction']==1
    assert second['counts']['known_multi_od_ranking_opportunities']==0


def ranking_fixture(*,ods=((1,10),(2,20)),common=(3.,2.),exact=(1.,4.),costs=None,claims=False):
    """Synthetic scoring only; distinct immutable ETAs identify reconstruction calls."""
    candidates=[dict(action_id=str(i),action_type='transfer',source_category='loader_optional',
        source=od[0],destination=od[1],tray_id='tray'+str(i),nominal_arrival_time=10.125+10.25*i,
        earliest_departure=2.,static_travel_time=8.125+10.25*i) for i,od in enumerate(ods)]
    plan=dict(receiver_claims_deducted={'10':1} if claims else {},
        station_table=[dict(node=n,receiver=dict(known=True,available_slots=1)) for n in {r[1] for r in ods}],
        config=dict(marginal_reference_available_offset_seconds=2.,transport_penalty_weight=.01,minimum_net_gain=0.),
        projection_horizon_seconds=600.,supply_mode='committed_only')
    d=dict(selection=dict(flow_plan=plan),flow_verification=dict(invalid=[]),requested_action=dict(kind='noop'),
        catalog=dict(catalog_id='synthetic-catalog',candidates=candidates),forecast_binding=None,
        public_observation_ref='synthetic-observation',owner_id='owner:synthetic',decision_id='d',decision_time=0.,
        candidate_features={str(i):dict(features_current=dict(current_proxy_gain=v)) for i,v in enumerate(exact)})
    def project(p,c):
        values=common if c['nominal_arrival_time']==2. else exact
        value=values[int(c['action_id'])]
        return dict(proxy_gain=value,known=value is not None)
    h=dict(projection=SimpleNamespace(prepare_inventory_projection=lambda *a,**k:SimpleNamespace(now=0.),project_action=project),
        allocation=SimpleNamespace(transport_cost=lambda c,config:0. if costs is None else costs[int(c['action_id'])]),
        timing=SimpleNamespace(_identity=lambda c:None if c is None else [c['source'],c['destination']]))
    return d,h,SimpleNamespace(get=lambda d:{}),{}, {'owner:synthetic':{}},dict(counts=Counter(),invalid=Counter(),gain_gaps=[],examples=[])


@pytest.mark.parametrize('changed',[False,True])
def test_complete_ranking_rows_include_unchanged_and_exceed_example_limit(changed):
    args=ranking_fixture(exact=(1.,4.) if changed else (3.,2.))
    d,*_,stats=args
    if not changed:d['requested_action']=dict(d['catalog']['candidates'][0],kind='transfer')
    for i in range(35):
        d['decision_id']=str(i);d['decision_time']=i*60.
        audit.timing_decision(*args)
    assert len(stats['ranking_rows'])==stats['counts']['known_multi_od_ranking_opportunities']==35
    assert len(stats['examples'])==(30 if changed else 0)
    assert sum(r['eta_only_changes']['source_changed'] for r in stats['ranking_rows'])==(35 if changed else 0)
    row=stats['ranking_rows'][0]
    assert row['known_scored_candidates']==len(row['candidates'])==2
    assert row['candidates'][0]['nominal_arrival_time']==10.125
    assert row['candidates'][1]['static_travel_time']==18.375
    assert row['candidates'][1]['tray_id']=='tray1' and row['candidates'][1]['owner_id']=='owner:synthetic'
    assert {'common_time_score','exact_same_cost_score','exact_actual_cost_score'}<=row['candidates'][0].keys()
    assert row['public_observation_ref']=='synthetic-observation'
    assert (row['selected'] is None) is changed


@pytest.mark.parametrize('ods,exact,expected',[
    (((1,10),(2,10)),(1.,4.),(True,False,False)),
    (((1,10),(1,20)),(1.,4.),(False,True,False)),
    (((1,10),(2,20)),(-1.,-2.),(False,False,True)),
])
def test_source_destination_and_hold_changes_have_separate_denominators(ods,exact,expected):
    args=ranking_fixture(ods=ods,exact=exact);audit.timing_decision(*args)
    row=args[-1]['ranking_rows'][0];changes=row['eta_only_changes']
    assert tuple(changes[k] for k in ('source_changed','destination_changed','hold_changed'))==expected
    assert changes['both_moves'] is (not expected[-1])
    assert len(row['candidates'])==2  # Even negative candidates remain in the complete score table.


def test_cost_model_change_is_not_mislabeled_as_eta_change():
    args=ranking_fixture(common=(5.,4.),exact=(5.,4.),costs=(4.,0.));audit.timing_decision(*args)
    row=args[-1]['ranking_rows'][0]
    assert row['common_time_best']['tray_id']==row['exact_same_cost_best']['tray_id']=='tray1'
    assert row['exact_actual_cost_best']['tray_id']=='tray0'
    assert not any(row['eta_only_changes'][k] for k in ('source_changed','destination_changed','hold_changed'))
    assert row['cost_model_changes_at_exact_eta']['source_changed']
    assert args[-1]['counts']['eta_only_best_first_changes_including_hold']==0


def test_claim_exclusion_never_fabricates_a_ranking_score_or_reads_observation():
    args=list(ranking_fixture(claims=True));args[1]={};args[2]=None
    audit.timing_decision(*args)
    assert args[-1]['ranking_rows']==[]
    assert args[-1]['counts']==Counter(valid_flow_decisions=1,excluded_pending_claims_no_counterfactual_reconstruction=1)
    assert args[-1]['examples']==[] and args[-1]['gain_gaps']==[]


def test_unknown_candidate_is_not_scored_as_zero_but_known_candidate_population_is_complete():
    args=ranking_fixture(ods=((1,10),(2,20),(3,30)),common=(3.,2.,None),exact=(1.,4.,None))
    audit.timing_decision(*args)
    row=args[-1]['ranking_rows'][0]
    assert row['eligible_candidate_checks']==3 and row['known_scored_candidates']==2
    assert [r['action_id'] for r in row['candidates']]==['0','1']
    assert args[-1]['counts']['reconstructed_candidate_checks']==3


def test_historical_counts_and_examples_are_identical_to_preserved_producer():
    old_path=path.parent/'final_science_timing_rows_history_001'/'final_science_audit_004.py'
    old_spec=importlib.util.spec_from_file_location('final_science_before_ranking_rows',old_path)
    old=importlib.util.module_from_spec(old_spec);old_spec.loader.exec_module(old)
    for updates in ({},{'exact':(3.,2.)},{'exact':(-1.,-2.)},{'claims':True},
                    {'common':(5.,4.),'exact':(5.,4.),'costs':(4.,0.)}):
        current=ranking_fixture(**updates);prior=ranking_fixture(**updates)
        audit.timing_decision(*current);old.timing_decision(*prior)
        for key in ('counts','invalid','gain_gaps','examples'):assert current[-1][key]==prior[-1][key]


@pytest.mark.parametrize('location',['candidate','selected'])
def test_explicit_conflicting_candidate_or_selected_owner_is_not_overwritten(location):
    args=ranking_fixture();d=args[0]
    if location=='candidate':d['catalog']['candidates'][0]['owner_id']='owner:other'
    else:d['requested_action']=dict(d['catalog']['candidates'][0],kind='transfer',owner_id='owner:other')
    with pytest.raises(ValueError,match='ranking_action_owner_mismatch'):audit.timing_decision(*args)
    assert args[-1]['ranking_rows']==[]


def test_absent_owner_inherits_bound_decision_but_explicit_null_does_not():
    action=ranking_fixture()[0]['catalog']['candidates'][0]
    assert audit.ranking_identity(action,'owner:synthetic')['owner_id']=='owner:synthetic'
    assert audit.ranking_identity(dict(action,owner_id='owner:synthetic'),'owner:synthetic')['owner_id']=='owner:synthetic'
    with pytest.raises(ValueError,match='ranking_action_owner_mismatch'):
        audit.ranking_identity(dict(action,owner_id=None),'owner:synthetic')
