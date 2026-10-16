from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_original_cooperative_bridge as r
from scripts.experiments.g31_ics_circulation import verify_original_cooperative_bridge as v
from scripts.experiments.g31_ics_circulation import launch_original_cooperative_bridge as launch


def old_case():
    path=r.OUT/'original_low_wip_prepare_005'
    data=r.base.gzread(path/'input.json.gz');raw=r.base.gzread(path/'raw_final.json.gz');plan=r.base.read(path/'preregistered_protocol.json')
    for owner in raw['owners']:
        owner.update(operations=[],bridge_publications=[],consumed_completions=[],cap_observed=False,cap_relay=None)
    return data,raw,plan


def test_private_base_functions_preserve_code_and_do_not_modify_imported_globals():
    before=dict(vars(r.base));private=r.isolated_base()
    assert private.worker.__code__ is r.base.worker.__code__
    assert private.verify_saved.__code__ is r.base.verify_saved.__code__
    assert private.worker.__globals__ is private.verify_saved.__globals__
    assert private.worker.__globals__ is not vars(r.base)
    assert private.worker.__globals__['run_policy'] is r.policy.run_policy
    assert private.verify_saved.__globals__['run_policy'] is r.policy.run_policy
    assert private.HORIZON==86400 and r.base.HORIZON==22200
    assert vars(r.base)==before


def test_actual005_complete_H20_prefix_replay_instantiates_BridgeOwner(tmp_path):
    old=r.OUT/'original_low_wip_prepare_005';plan=r.base.read(old/'preregistered_protocol.json')
    manifest=[json.loads(line) for line in (old/'api/manifest.jsonl').read_text().splitlines()]
    rows=[];directory=tmp_path/'api';directory.mkdir()
    for entry in manifest:
        raw=r.base.gzread(old/'api'/entry['path'])
        if raw['endpoint']=='advance_to' and raw['before']==20.:break
        shutil.copyfile(old/'api'/entry['path'],directory/entry['path']);rows.append(entry)
    assert raw['before']==20.
    (directory/'manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
    tape=r.base.ReplayTape(directory);calls=[]
    class Recorded(r.policy.BridgeOwner):
        def activate(self):calls.append((self.owner,self.session.physical_time));return super().activate()
    run=r.clone(r.policy.run_policy,{**r.policy.run_policy.__globals__,'BridgeOwner':Recorded,'HORIZON':20.,'MAX_TICKS':3})
    owners,status,tick=run(tape,plan)
    # Complete finite test prefix includes both final H20 owner activations.
    assert status=='horizon_complete' and tape.index==len(rows)
    assert all(isinstance(o,r.policy.BridgeOwner) for o in owners) and len(calls)==6
    assert r.base.Owner not in [type(o) for o in owners]


def test_private_worker_reaches_injected_policy_without_native(tmp_path):
    seen=[];exports={}
    fake=SimpleNamespace(physical_time=0.,result_at=lambda at:{'jobs':[],'trays':[],'receipts':[]},offline_state_sha256=lambda:'a'*64)
    def run(tape,plan,progress):seen.append(tape);return [],'unknown_test',0
    private=r.isolated_base(read=lambda path:{'binary':'unloaded'},verify_pins=lambda *a,**k:None,
        claim_worker=lambda *a:None,gzread=lambda p:{'transfers':[]},
        load_native=lambda path:SimpleNamespace(NativeSession=lambda data:fake),Tape=lambda raw,path:raw,
        run_policy=run,audit_result=lambda *a:{'status':'unknown_test'},sha=lambda p:'a'*64,
        gzwrite=lambda path,value:exports.update({path.name:value}),write=lambda *a:None,assess=lambda *a:{})
    private.worker(tmp_path)
    assert seen==[fake] and exports['raw_final.json.gz']['status']=='unknown_test'
    assert r.base.run_policy is not run


def test_actual005_outcomes_remain_exact_but_are_not_new_bridge_execution():
    data,raw,plan=old_case();result=v.physical_outcomes(data,raw,plan)
    assert result['offered']==28506 and result['total_tray_identities']==22
    assert result['completed']==['projected:1x:2'] and result['direct_supplies']==1 and result['bridges']==0
    assert len(result['actual_empty_arrivals'])==23 and len(result['noncirculating_parked_trays'])==21
    assert result['completion_witnesses'][0]['storage']['observed']
    assert r.assess(raw,plan)['full_horizon_without_policy_failure'] is False


@pytest.mark.parametrize('change',['missing_job','duplicate_tray','missing_storage','missing_hold','bad_empty','other_load','other_tray_move','retry_payload'])
def test_actual_receipt_mutations_fail_or_remain_incomplete(change):
    data,raw,plan=old_case();receipts=raw['result']['receipts']
    if change=='missing_job':raw['result']['jobs'].pop()
    elif change=='duplicate_tray':raw['result']['trays'][1]=deepcopy(raw['result']['trays'][0])
    elif change=='missing_storage':raw['result']['receipts']=[x for x in receipts if x['event']!='STORAGE_RELEASE']
    elif change=='missing_hold':
        raw['result']['receipts']=[x for x in receipts if x['event']!='HOLD_COMPLETE']
        result=v.physical_outcomes(data,raw,plan);assert result['all_selected_returned'] is False;return
    elif change=='bad_empty':next(x for x in receipts if x['event']=='EMPTY_RECEIVED')['node']+=1
    elif change=='other_load':next(x for x in receipts if x['event']=='LOAD_START')['tray_id']='other'
    elif change=='other_tray_move':
        p=next(x for x in plan['parking_plan']['parking'] if x['tray_id']!=plan['parking_plan']['token_tray_id'])
        receipts.append({'event':'EDGE_ENTER','tray_id':p['tray_id'],'time':raw['physical_time']})
    else:
        owner=raw['owners'][0];call=deepcopy(owner['calls'][0]);call['request']['expiry']+=1;call['retry']=True;owner['calls'].append(call)
    with pytest.raises((ValueError,KeyError)):v.physical_outcomes(data,raw,plan)


def test_single_cap_scope_keeps_original_standard_and_finite_unknown():
    contract=r.contract()
    assert contract['offered']==28506 and contract['total_tray_identities']==22
    assert (contract['max_actual_token_completions'],contract['max_postparking_empty_operations'],contract['max_physical_requests'])==(39,78,100)
    assert contract['horizon']==86400 and contract['shared_parent_seconds']==2400
    assert contract['native_workers_at_once']==contract['native_branches']==1
    assert contract['whole_day_business_success'] is False and contract['complete_100ms_certified'] is False


def clocks(tmp_path,change=None):
    rows=[{'scope':'complete_frozen_api_and_tape_write','ordinal':0,'endpoint':'protocol_request','start_ns':20,'end_ns':40},
        {'scope':'owner_activation_including_tape_clocks','owner':'A','logical_time':0.,'first_api':0,'after_api':1,'start_ns':10,'end_ns':50},
        {'scope':'complete_frozen_api_and_tape_write','ordinal':1,'endpoint':'advance_to','start_ns':60,'end_ns':90}]
    if change=='missing':rows.pop()
    elif change=='negative':rows[0]['start_ns']=-1
    elif change=='wrong_endpoint':rows[0]['endpoint']='protocol_command'
    elif change=='wrong_owner':rows[1]['owner']='B'
    elif change=='escape':rows[0]['start_ns']=5
    elif change=='bool':rows[1]['start_ns']=True
    path=tmp_path/'clock.jsonl';path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    return path,[{'endpoint':'protocol_request'},{'endpoint':'advance_to'}],[{'owner':'A','logical_time':0.,'first_api':0,'after_api':1}]


def test_nested_clock_scopes_are_not_added_or_divided(tmp_path):
    value=v.validate_clocks(*clocks(tmp_path));assert value['api_wall_ns']==50 and value['owner_wall_ns']==40
    assert 'never summed' in value['scope']


@pytest.mark.parametrize('change',['missing','negative','wrong_endpoint','wrong_owner','escape','bool'])
def test_complete_clock_coverage_is_bound_to_exact_api_and_owner_replay(tmp_path,change):
    with pytest.raises(ValueError):v.validate_clocks(*clocks(tmp_path,change))


def receipt():
    return {'schema':r.SCHEMA,'status':'completed_finite_campaign','campaign_sha256':'a'*64,'source_changed':[],
        'cases':{'bridge':{'status':'saved_replay_passed','execution':{'exit_code':0},'verification':{'exit_code':0}}},
        'offered':28506,'alloffered_business_success':False,'complete_100ms_certified':False,'wall_seconds':123.}


def test_launcher_accepts_only_complete_finite_case_not_business_success():launch.validate_internal(receipt(),'a'*64)


@pytest.mark.parametrize('change',['case_missing','verify_failed','source_changed','over_budget','nan','business_success'])
def test_launcher_failures_are_not_promoted(change):
    value=receipt()
    if change=='case_missing':value['cases']={}
    elif change=='verify_failed':value['cases']['bridge']['verification']['exit_code']=1
    elif change=='source_changed':value['source_changed']=['x']
    elif change=='over_budget':value['wall_seconds']=2400.0001
    elif change=='nan':value['wall_seconds']=float('nan')
    else:value['alloffered_business_success']=True
    with pytest.raises(ValueError):launch.validate_internal(value,'a'*64)


def test_source_closure_includes_exact_new_worker_verifier_launcher_and_absolute_imports():
    names={str(x.relative_to(r.ROOT)).replace('\\','/') for x in r.source_paths()}
    assert 'scripts/eval/run_g4irsf28_service_potential.py' in names
    assert all('scripts/experiments/g31_ics_circulation/'+name+'.py' in names for name in
        ('research_original_cooperative_bridge','verify_original_cooperative_bridge','launch_original_cooperative_bridge','cooperative_bridge_policy'))


def test_failed_worker_keeps_elapsed_and_duplicate_attempt_cannot_overwrite(tmp_path,monkeypatch):
    calls=[]
    def fail(output):calls.append(output);raise RuntimeError('injected_before_native')
    monkeypatch.setattr(r,'isolated_base',lambda **kwargs:SimpleNamespace(worker=fail))
    with pytest.raises(RuntimeError,match='injected_before_native'):r.worker(tmp_path)
    original=(tmp_path/'worker_elapsed.json').read_bytes()
    assert json.loads(original)['elapsed_ns']>=0 and len(calls)==1
    with pytest.raises(ValueError,match='measurement_exists'):r.worker(tmp_path)
    assert len(calls)==1 and (tmp_path/'worker_elapsed.json').read_bytes()==original


def test_interrupted_measurement_claim_rejects_new_attempt_without_export(tmp_path,monkeypatch):
    (tmp_path/'worker_measurement_claim.json').write_text('{}')
    monkeypatch.setattr(r,'isolated_base',lambda **kwargs:pytest.fail('duplicate reached worker'))
    with pytest.raises(FileExistsError):r.worker(tmp_path)
    assert not (tmp_path/'worker_elapsed.json').exists()


def test_timeout_artifact_retention_hashes_exact_incomplete_bytes(tmp_path):
    import hashlib
    path=tmp_path/'bridge/api';path.mkdir(parents=True)
    partial=b'{"ordinal":0}\n{"ordinal":'
    (path/'manifest.jsonl').write_bytes(partial)
    assert launch.retained_evidence(tmp_path)=={'bridge/api/manifest.jsonl':hashlib.sha256(partial).hexdigest()}
    assert (path/'manifest.jsonl').read_bytes()==partial


def observation_fixture():
    # Logical classifier fixture, not an actual original-map completion claim.
    return ({'full_horizon_without_policy_failure':True,'all_physical_received':True},
        {'noncirculating_parked_trays':list(range(21)),'all_selected_returned':True,'final_token_empty':True,
         'actual_empty_arrivals':{'p':{}},'physical_payloads':{'p':{}},'postparking_empty_requests':8,'completed':list(range(8))},
        {'status':'passed'})


def test_full_day_observation_does_not_require_hitting_completion_cap():
    assert v.classify_observation(*observation_fixture(),{})==(True,'not_reached_not_certified')


@pytest.mark.parametrize('proofs',[{}, {'A':{'status':'actual_fresh_cap_proof_and_delivered_relay'}},
    {'A':{'status':'actual_fresh_cap_proof_and_delivered_relay'},'B':{'status':'unknown'}}])
def test_hitting_cap_without_both_actual_relays_never_certifies_cap(proofs):
    a,o,audit=observation_fixture();o['postparking_empty_requests']=78
    assert v.classify_observation(a,o,audit,proofs)==(True,'unknown_missing_cap_proof_or_relay')


@pytest.mark.parametrize('failure',['horizon','ack','audit','parked','return','empty','arrival'])
def test_closed_cap_does_not_hide_incomplete_physical_observation(failure):
    a,o,audit=observation_fixture();o['postparking_empty_requests']=78
    if failure=='horizon':a['full_horizon_without_policy_failure']=False
    elif failure=='ack':a['all_physical_received']=False
    elif failure=='audit':audit['status']='unknown'
    elif failure=='parked':o['noncirculating_parked_trays'].pop()
    elif failure=='return':o['all_selected_returned']=False
    elif failure=='empty':o['final_token_empty']=False
    else:o['actual_empty_arrivals']={}
    proofs={k:{'status':'actual_fresh_cap_proof_and_delivered_relay'} for k in ('A','B')}
    assert v.classify_observation(a,o,audit,proofs)==(False,'complete_bidirectional_cap_relay')
