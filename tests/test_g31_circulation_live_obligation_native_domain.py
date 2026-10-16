"""Fixed96 preparation guards only; no native or projection execution."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_domain_guard as guard
from scripts.experiments.g31_ics_circulation import research_live_obligation_native_domain as runner
from scripts.experiments.g31_ics_circulation import live_obligation_native_domain_contract as contract

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'

@pytest.mark.parametrize('case',runner.CASE_ORDER)
def test_exact_three_case_input_and_initial_contract(case):
    data=runner.native_scene(case);physical=runner.validate_runtime_input(data)
    assert physical==json.loads((OUT/'live_obligation_projection_prepare_003'/(case+'.input.json')).read_bytes())
    assert data['owner_notifications']=={'enabled':True}
    jobs,trays,resources=guard.construction.initial_facts(physical)
    public=guard.supported_contract(case=case)
    assert guard.identify_public_case(public,jobs)==case
    owners={r['node']:r['resource_owner'] for r in physical['node_contracts']}
    projected={o:{'jobs':[j for j in jobs.values() if owners[j['origin']]==o],
        'trays':[t for t in trays.values() if owners[t['node']]==o],
        'resources':[r for n,r in resources.items() if owners[n]==o]} for o in ('A','B')}
    assert guard.initial_bundle(public,projected,.11)['status']=='conditional_model_input'

@pytest.mark.parametrize('change',['release','edge','owner','capacity','job','notification','extra'])
def test_no_case_label_or_overlay_bypass(change):
    data=runner.native_scene('no_overlap')
    if change=='release':data['jobs'][-1]['storage_release_at']+=.001
    elif change=='edge':data['edge_records'][0][2]+=.001
    elif change=='owner':data['node_contracts'][0]['resource_owner']='B'
    elif change=='capacity':data['node_contracts'][0]['capacity']+=1
    elif change=='job':data['jobs'][0]['deadline']-=1
    elif change=='notification':data['owner_notifications']['enabled']=1
    elif change=='extra':data['case_override']='mechanism'
    with pytest.raises(ValueError):runner.validate_runtime_input(data)

def test_same_graph_different_public_job_release_disambiguates_cases():
    mechanism=guard.public_input('mechanism');negative=guard.public_input('no_overlap')
    assert guard.supported_contract(case='mechanism')==guard.supported_contract(case='no_overlap')
    assert mechanism['jobs']!=negative['jobs']
    jobs=guard.construction.initial_facts(negative)[0]
    assert guard.identify_public_case(guard.supported_contract(),jobs)=='no_overlap'
    jobs['blocker']['storage_release_at']+=.001
    with pytest.raises(ValueError):guard.identify_public_case(guard.supported_contract(),jobs)

@pytest.mark.parametrize('now',[0.,6.34,math.nextafter(7.84,-math.inf),7.84,math.nextafter(7.84,math.inf),8.1,39.])
def test_frozen_absolute_first_return_all_boundaries(now):
    assert runner.return_earliest(now,0.,0)==now
    assert runner.return_earliest(now,.5,0)==max(now,guard.construction.PROTOCOL['first_return_not_before'])
    assert runner.return_earliest(now,0.,1)==now

@pytest.mark.parametrize('args',[(6.34,.5,1),(True,0.,0),(6.34,True,0),(6.34,.25,0),(-1,0.,0),(float('nan'),0.,0),(6.34,0.,True),(6.34,0.,2)])
def test_reject_changed_second_action_or_untyped_time(args):
    with pytest.raises(ValueError):runner.return_earliest(*args)

def test_command_preserves_absolute_not_before_and_second_immediate():
    class Client:
        def __init__(self):self.calls=[]
        def submit(self,*args,**kwargs):self.calls.append((args,kwargs));return f'return:{len(self.calls)}'
    policy=object.__new__(runner.OwnerPolicy);policy.returns=[];policy.client=Client()
    view={'now':6.34};tray={'tray_id':'L','node':6};demand={'delivered_at':6.3}
    policy.return_tray(view,tray,demand,.5,{'cause':'fixed'})
    assert policy.client.calls[0][1]['earliest_departure']==7.84
    assert policy.client.calls[0][1]['earliest_departure']!=view['now']+.5
    policy.return_tray({'now':12.},tray,demand,0.,{})
    assert policy.client.calls[1][1]['earliest_departure']==12.
    assert [r['selected_delay'] for r in policy.returns]==[.5,0.]

def test_exact96_order_and_reference_domain():
    rows=runner.probe_rows();assert list(rows)==runner.ORDER==contract.ORDER and len(rows)==96
    contract.validate_rows(rows)
    for case in runner.CASE_ORDER:
        group=[r for r in rows.values() if r['case']==case]
        assert len(group)==32 and [r['vector'] for r in group]==guard.construction.actions()
        assert sum(r['vector']['initial_action']=='native_default' for r in group)==16
        assert sum(r['vector']['later_action']=='native_default' for r in group)==16
    assert runner.HARD_TIMEOUT==600. and runner.BRANCH_COUNT==96

@pytest.mark.parametrize('change',['missing','order','case','action'])
def test_domain_cannot_silently_skip_or_relabel(change):
    rows=runner.probe_rows();key=runner.ORDER[0]
    if change=='missing':rows.pop(key)
    elif change=='order':rows=dict(reversed(list(rows.items())))
    elif change=='case':rows[key]['case']='no_overlap'
    elif change=='action':rows[key]['vector']['return_delay']=.5
    with pytest.raises(ValueError):contract.validate_rows(rows)

def selections():return json.loads((OUT/'live_obligation_projection_prepare_003/comparisons.json').read_bytes())
def all_supplied_known():
    rows=runner.probe_rows()
    for row in rows.values():
        row.update(status='assessed',summary={'status':'assessed','business_complete':True,
            'all_required_inputs_verified':True,'selected_actions_executed':True,'completion':{j:1. for j in contract.JOB_ORDER}})
    return rows

def test_unknown_even_when_physically_complete_keeps_reference_unknown():
    rows=all_supplied_known();key='mechanism/vector_00';rows[key]['summary']['all_required_inputs_verified']=False
    compared=contract.compare(rows,selections());case=compared['cases']['mechanism']
    assert case['assessed']==31 and case['unknown']==1 and case['full32_finite_optimum'] is None
    assert all(r['status']=='unknown_incomplete_reference' and r['best_key'] is None for r in case['references'].values())
    assert case['rows_vs_incumbent'][key]['strict_protected'] is None

def test_strict_per_job_no_epsilon_and_frozen_same_budget_selections():
    rows=all_supplied_known();rows['mechanism/vector_25']['summary']['completion']['blocker']=math.nextafter(1.,math.inf)
    compared=contract.compare(rows,selections());case=compared['cases']['mechanism']
    assert case['rows_vs_incumbent']['mechanism/vector_25']['strict_protected'] is False
    assert all(v['selection']['budget']==32 for v in case['methods'].values())
    assert case['methods']['pair_repair']['selected_native_key']=='mechanism/vector_25'
    assert case['methods']['pair_repair']['native_outcome_vs_incumbent']['strict_protected'] is False
    assert compared['online_solver_executed'] is False

@pytest.mark.parametrize('vector',[12,24,25])
def test_same_mechanism_saved004_full_assessment_and_endpoint_replay(vector):
    directory=OUT/'live_obligation_native_probe_prepare_004';ledger=json.loads((directory/'branch_ledger.json').read_bytes())
    key=f'mechanism/vector_{vector:02}';artifact=ledger[key]['raw_artifact'];data=Path(artifact['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==artifact['sha256']
    raw=json.loads(gzip.decompress(data));runner.verify_saved_inputs(raw)
    rebuilt=runner.completed_summary(raw['input'],raw['result'],SimpleNamespace(rows=raw['outbox'],calls=raw['calls']),
        raw['continuation'],raw['specification']['vector'],raw['initial_owners'],raw['decisions'])
    assert rebuilt==raw['summary'] and rebuilt['status']=='assessed'

def test_saved_json_cannot_authorize_domain_choice():
    assert runner.fixed_choice({'status':'conditional_native_delivered_later_v3_model_input','native_delivery_verified':True},
        runner.probe_rows()[runner.ORDER[0]]['vector'])['selected_action'] is None
