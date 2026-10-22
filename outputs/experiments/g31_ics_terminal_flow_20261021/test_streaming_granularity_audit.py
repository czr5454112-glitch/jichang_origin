"""Small synthetic fixtures only; never reads native run observations or ACKs."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

path=Path(__file__).with_name('streaming_granularity_audit_005.py')
spec=importlib.util.spec_from_file_location('stream_granularity_test',path)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
audit,_=driver.load_support()


def fake_replay():
    config=dict(fixed=True);observation=dict(now=0.,owner_id='a')
    candidates=[dict(action_id='a_noop',action_type='noop'),
        dict(action_id='a',action_type='transfer',source=1,destination=3,tray_id='A',nominal_arrival_time=40.),
        dict(action_id='b',action_type='transfer',source=2,destination=4,tray_id='B',nominal_arrival_time=50.),
        dict(action_id='c',action_type='transfer',source=2,destination=3,tray_id='B',nominal_arrival_time=50.)]
    catalog=dict(catalog_id='menu',candidates=candidates);prepared=object();seen=[]
    class Policy:
        def __init__(self,**kw):assert kw==dict(config=config,recompute_period_seconds=60.)
        def select(self,current,menu,projection,**kw):
            assert current is prepared and menu is catalog and kw['policy_state']=={}
            seen.append(kw['policy_state'])
            second=candidates[2] if projection.mode=='60' else candidates[3]
            return dict(action_id='a',flow_plan=dict(plan_id='ignored_'+projection.mode,chosen=[candidates[1],second]))
    def projection(obs,**kw):
        assert obs is observation and kw['prepared_current'] is prepared
        assert kw['horizon_seconds']==600. and kw['supply_mode']=='committed_only'
        return SimpleNamespace(now=0.,loaders=[3,4],mode=kw['forecast']['mode'])
    def mass(projection,node,left,right):
        return right/60. if right in (600.,1800.) else right/60.+(projection.mode!='60')
    h=dict(r0=SimpleNamespace(r0_priority_planner=lambda o:dict(intents=[])),
        opportunities=SimpleNamespace(prepare_current=lambda *a,**k:prepared,build_joint_catalog=lambda p:catalog),
        forecast=SimpleNamespace(bin_edges=lambda mode:mode,rebin_forecast=lambda f,**k:dict(mode=k['bin_edges_seconds'])),
        projection=SimpleNamespace(prepare_inventory_projection=projection,demand_mass=mass),
        control=SimpleNamespace(TransportPolicy=Policy))
    decision=dict(decision_id='d',owner_id='a',legal_catalog_ref='menu',
        selection=dict(flow_plan=dict(receiver_claims_deducted={},config=config)))
    plan=dict(parent=dict(parent_seed=2201),transport_config=config)
    return decision,observation,plan,h,seen


def test_same_quantity_changed_od_allocation_and_metadata_independence():
    d,o,p,h,seen=fake_replay();result=driver.stats()
    driver.replay(d,o,{},p,{},dict(a={}),h,result)
    report=driver.summary(result)
    assert len(seen)==4 and len({id(x) for x in seen})==4
    assert report['opportunities']['replayed_opportunities']==1
    for mode in driver.MODES[1:]:
        counts=report['modes'][mode]
        assert counts['first_action_changes_vs_60']==0
        assert counts['quantity_changes_vs_60']==counts['total_quantity_changes_vs_60']==0
        assert counts['quantity_allocation_changes_vs_60']==1
        assert report['eta_cumulative_demand_sensitivity'][mode]['count']==3
    assert report['common_horizon_mass_checks']==dict(known_equal_600=6,known_equal_1800=6)
    assert report['first_action_or_allocation_change_examples'][0]['quantity_allocation_changed']
    left=dict(flow_plan=dict(chosen=[dict(source=1,destination=3,plan_id='old')]))
    right=dict(flow_plan=dict(chosen=[dict(source=1,destination=3,plan_id='new')]))
    assert driver.allocation(left)==driver.allocation(right)


def test_nonzero_or_missing_receiver_claim_evidence_never_guessed_zero():
    d,o,p,h,_=fake_replay();d['selection']['flow_plan']['receiver_claims_deducted']={'3':1}
    result=driver.stats();driver.replay(d,o,{},p,{},None,{},result)
    assert result['opportunities']==dict(excluded_uncredited_claim_opportunities=1)
    d['selection']['flow_plan'].pop('receiver_claims_deducted')
    with pytest.raises(ValueError,match='receiver_claim_evidence_required'):
        driver.replay(d,o,{},p,{},None,{},driver.stats())


@pytest.mark.parametrize('bad',[float('nan'),-1,True])
def test_invalid_receiver_claim_evidence_rejected(bad):
    d,o,p,h,_=fake_replay();d['selection']['flow_plan']['receiver_claims_deducted']={'3':bad}
    with pytest.raises(ValueError,match='receiver_claim_counts_invalid'):
        driver.replay(d,o,{},p,{},None,{},driver.stats())


@pytest.mark.parametrize('bad',[None,11.])
def test_common_mass_and_knownness_changes_fail(bad):
    d,o,p,h,_=fake_replay();mass=h['projection'].demand_mass
    h['projection'].demand_mass=lambda p,n,a,b:bad if p.mode=='600' and b==600 else mass(p,n,a,b)
    with pytest.raises(ValueError,match='common_horizon_mass_knownness_changed|coarsening_changed_common_horizon_mass'):
        driver.replay(d,o,{},p,{},dict(a={}),h,driver.stats())


def test_priority_exclusion_and_saved_config_are_explicit():
    d,o,p,h,_=fake_replay();h['r0'].r0_priority_planner=lambda o:dict(intents=['priority'])
    result=driver.stats();driver.replay(d,o,{},p,{},None,h,result)
    assert result['opportunities']==dict(excluded_priority_not_exhausted=1)
    d['selection']['flow_plan']['config']={}
    with pytest.raises(ValueError,match='saved_optimizer_config_binding'):
        driver.replay(d,o,{},p,{},None,h,driver.stats())


def test_forecast_actor_identity_scope_and_availability():
    digest=lambda x:json.dumps(x,sort_keys=True)
    f=dict(bin_edges_seconds='60',forecast_origin=10.,owner_scope='a')
    binding=dict(forecast=f,forecast_sha256=digest(f),public_state_sha256='public',
        observed_at_epoch_seconds=1010.,actual_callback_consumption=True,forecast_provenance='actual_callback_received',
        training_labels_closed_at_epoch_seconds=800.,model_available_at_epoch_seconds=900.,plan_received_at_epoch_seconds=1000.,
        source_forecast_sha256='source',forecast_transform=dict(actor_forecast_sha256=digest(f),
            source_forecast_sha256='source',demand_model_sha256=None))
    d=dict(forecast_binding=binding,decision_time=10.,owner_id='a',public_observation_ref='public')
    p=dict(parent=dict(calendar_start_epoch_seconds=1000.))
    h=dict(forecast=SimpleNamespace(bin_edges=lambda mode:mode),digest=SimpleNamespace(digest=digest))
    assert driver.validate_forecast(d,p,h)==f
    for field,value,reason in [('forecast_sha256','wrong','exact_actor_forecast_digest'),
            ('model_available_at_epoch_seconds',1010.,'forecast_available_at_callback'),
            ('plan_received_at_epoch_seconds',1011.,'forecast_available_at_callback'),
            ('public_state_sha256','wrong','forecast_public_observation_binding'),
            ('actual_callback_consumption',False,'actual_callback_forecast_required')]:
        altered=copy.deepcopy(d);altered['forecast_binding'][field]=value
        with pytest.raises(ValueError,match=reason):driver.validate_forecast(altered,p,h)


def plan(parent=2201):
    return dict(task_id=f'fine_{parent}',parent=dict(parent_seed=parent,split='dev',synthetic=True,common_historical_template_sha256='template'),
        source_bundle=dict(path='source005',sha256='same'),method='TF-B1-60',activation=7200.,horizon=59400.,
        forecast_bin_edges_seconds='60',forecast_horizon_seconds=1800.,projection_horizon_seconds=600.,
        recompute_period_seconds=60.,supply_mode='committed_only',demand_model=None,model=None,
        controller=dict(control_period=60.,command_delay=2.),binary={},mapping={},transport_config={})


def test_only_uncalibrated_full_dev_fine_plans_allowed():
    p=plan();h=dict(campaign=SimpleNamespace(method_contract_errors=lambda p:[]),forecast=SimpleNamespace(bin_edges=lambda m:m))
    driver.validate_plan(p,p['source_bundle'],h)
    for key,value in [('method','TF-predictor'),('horizon',18000.),('forecast_bin_edges_seconds','300'),('demand_model',{})]:
        altered=copy.deepcopy(p);altered[key]=value
        with pytest.raises(ValueError):driver.validate_plan(altered,p['source_bundle'],h)
    altered=copy.deepcopy(p);altered['parent']['split']='test'
    with pytest.raises(ValueError,match='four_dev_parents_only'):driver.validate_plan(altered,p['source_bundle'],h)


def test_pending_bridge_and_incomplete_four_parent_execution_do_not_create_output(tmp_path):
    bridge=tmp_path/'bridge_all_005'/'block.json'
    a=SimpleNamespace(workflow_blocks=lambda *args:([bridge],{}))
    rows,status=driver.inspect_runs('workflow',{},a,{})
    assert not rows and status['status']=='pending' and status['expected_runs']==4
    with pytest.raises(ValueError,match='all_four_closed_before_execute'):
        driver.execute({},status,{},[],None,{},tmp_path/'result')
    assert not (tmp_path/'result').exists()


def test_changed_producer_blocks_execution_before_any_output(tmp_path):
    producer=tmp_path/'producer.py';producer.write_text('first',encoding='utf8')
    ref=driver.bind(producer);producer.write_text('changed',encoding='utf8')
    with pytest.raises(ValueError,match='granularity_producer_changed'):
        driver.execute({p:{} for p in driver.PARENTS},dict(status='ready'),{},[ref],audit,{},tmp_path/'result')
    assert not (tmp_path/'result').exists()


def test_streaming_summary_preserves_all_parent_counts_and_no_mass_arrays():
    total=driver.stats()
    for parent in driver.PARENTS:
        part=driver.stats();part['opportunities'].update(recorded_decisions=10,replayed_opportunities=7,
            excluded_uncredited_claim_opportunities=2,excluded_outside_registered_window=1)
        driver.add_mass(part['eta']['600'],1.);driver.add_mass(part['eta']['600'],3.)
        part['modes']['600']['quantity_allocation_changes_vs_60']=1
        driver.merge(total,part)
    result=driver.summary(total)
    assert result['opportunities']==dict(recorded_decisions=40,replayed_opportunities=28,
        excluded_uncredited_claim_opportunities=8,excluded_outside_registered_window=4)
    assert result['eta_cumulative_demand_sensitivity']['600']==dict(count=8,
        mean_absolute_mass_difference=2.,maximum_absolute_mass_difference=3.)
    assert result['modes']['600']['quantity_allocation_changes_vs_60']==4


def test_exact_four_closed_same_source_parent_matrix(tmp_path):
    bridge=tmp_path/'block.json';refs=[]
    for parent in driver.PARENTS:
        directory=tmp_path/str(parent);directory.mkdir()
        refs.append(audit.fresh(directory/'plan.json',plan(parent)))
        audit.fresh(directory/'receipt.json',dict(worker=dict(scientific_status='closed')))
    b=dict(phase='bridge',source_bundle=plan()['source_bundle'],methods=audit.PHASES['bridge'],
        parents=list(driver.PARENTS),task_plans=refs)
    audit.fresh(bridge,b)
    a=SimpleNamespace(workflow_blocks=lambda *args:([bridge],{}),bound_read=audit.bound_read,read=audit.read,PHASES=audit.PHASES)
    h=dict(campaign=SimpleNamespace(_validate_block_manifest=lambda b:None,method_contract_errors=lambda p:[]),
        forecast=SimpleNamespace(bin_edges=lambda mode:mode),flow=SimpleNamespace(closed_run=lambda p:None))
    rows,status=driver.inspect_runs('workflow',b['source_bundle'],a,h)
    assert set(rows)==set(driver.PARENTS) and status['status']=='ready'
    b['task_plans'].pop();bridge.write_text(json.dumps(b),encoding='utf8')
    with pytest.raises(ValueError,match='all_four_registered_fine_runs_required'):
        driver.inspect_runs('workflow',b['source_bundle'],a,h)


def test_streaming_run_binds_inputs_and_excludes_cutoff_without_loading_ack(tmp_path,monkeypatch):
    digest=lambda x:json.dumps(x,sort_keys=True)
    obs=[dict(now=t,owner_id='a') for t in (7200.,7260.)]
    rows=[dict(decision_id=str(i),owner_id='a',decision_time=o['now'],public_observation_ref=digest(o),
        legal_catalog_ref='menu',catalog=dict(catalog_id='menu'),requested_action=dict(kind='noop'),selection={}) for i,o in enumerate(obs)]
    for name in driver.EVIDENCE_FILES:audit.fresh(tmp_path/name,{})
    p=plan();events=[];original=driver.bind
    def binding(path):events.append(Path(path).name);return original(path)
    monkeypatch.setattr(driver,'bind',binding)
    def closed(path):
        assert events==list(driver.EVIDENCE_FILES)
        return p,{},dict(rows=rows)
    def stream(path):
        if path.name=='decisions.json.gz':yield from rows+[dict(decision_id='boundary',decision_time=59400.)]
        elif path.name=='observations.json.gz':yield from [dict(digest=digest(o),observation=o) for o in obs]
        else:raise AssertionError('unexpected read '+str(path))
    h=dict(flow=SimpleNamespace(closed_run=closed),stream=SimpleNamespace(iter_json_array_gz=stream),
        digest=SimpleNamespace(digest=digest))
    result,report=driver.audit_run(dict(directory=tmp_path,plan_binding=original(tmp_path/'plan.json')),audit,h)
    assert result['opportunities']==dict(recorded_decisions=3,validated_in_window_decisions=2,
        missing_consumed_forecast=2,excluded_outside_registered_window=1)
    assert set(report['evidence'])==set(driver.EVIDENCE_FILES) and report['observations_read']==2
    assert not any('ack' in name for name in events)


def test_streaming_loop_matches_frozen005_legacy_algorithm_on_synthetic_fixture(tmp_path):
    """Fresh Python imports only frozen actors; both algorithms see tiny fake files."""
    root=path.resolve().parents[3]
    code=r'''
import importlib.util,json,gzip,sys
from pathlib import Path
root,driver_path,temp=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('stream_granularity',driver_path)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
a,_=g.load_support()
source=root/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json'
frozen=a.verify_sources(g.bind(source));h=g.load_helpers(frozen,a)
sys.path.insert(0,str(root/'tests'))
from test_g31_airport_joint_interface import two_sources
from test_g31_foundation_airport_joint_projection import forecast
obs=two_sources();obs['observation_scope']='controller_policy'
baseline=h['r0'].r0_priority_planner(obs)
prepared=h['opportunities'].prepare_current(obs,baseline,message_delay=2.)
menu=h['opportunities'].build_joint_catalog(prepared)
fc=forecast(obs,{2:[3.,0.,1.]+[0.]*27});fc['native_execution_authority']=False
plan=dict(parent=dict(parent_seed=2201,split='dev'),horizon=100.,transport_config=h['campaign'].DEFAULT_CONFIG)
d=dict(decision_id='d',owner_id=obs['owner_id'],decision_time=obs['now'],public_observation_ref=h['digest'].digest(obs),
    legal_catalog_ref=menu['catalog_id'],forecast_binding=dict(forecast=fc),
    selection=dict(flow_plan=dict(receiver_claims_deducted={},config=plan['transport_config'])))
def write(name,obj):
    target=temp/name
    with (gzip.open(target,'wt',encoding='utf8') if name.endswith('.gz') else target.open('w',encoding='utf8')) as stream:json.dump(obj,stream)
write('plan.json',plan)
write('receipt.json',dict(plan_sha256=g.bind(temp/'plan.json')['sha256'],process=dict(exitcode=0),
    worker=dict(scientific_status='closed',process_status='completed',final_physical_time=100.)))
write('observations.json.gz',[dict(digest=h['digest'].digest(obs),observation=obs)])
write('arrival_support_contract.json',None);write('arrival_support_receipts.json',{obs['owner_id']:None})
for claims in ({},{'2':1}):
    d['selection']['flow_plan']['receiver_claims_deducted']=claims
    write('decisions.json.gz',[d])
    legacy=h['campaign'].offline_granularity([temp])
    result=g.stats();result['opportunities']['recorded_decisions']=1
    g.replay(d,obs,fc,plan,None,{obs['owner_id']:None},h,result);new=g.summary(result)
    assert new['opportunities']==legacy['opportunities'],(new,legacy)
    for mode,values in legacy['modes'].items():
        assert {k:new['modes'][mode][k] for k in values}==values,(mode,new,legacy)
    assert new['eta_cumulative_demand_sensitivity']==legacy['eta_cumulative_demand_sensitivity']
print(json.dumps(dict(parity=True,native_starts=0,synthetic_opportunities=2)))
'''
    result=subprocess.run([sys.executable,'-c',code,str(root),str(path.resolve()),str(tmp_path)],
        cwd=root,text=True,capture_output=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['parity'] is True
