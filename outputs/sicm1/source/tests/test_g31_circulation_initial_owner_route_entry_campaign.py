"""Actual campaign/verifier wiring and saved synthetic root endpoint tests."""
from copy import deepcopy
import hashlib,time
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_campaign as c
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_integration as i
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_entry_campaign as v
from test_g31_circulation_initial_owner_route_entry_hop import fixture


def test_campaign_uses_exact_new_types_scheduler_and_verifier():
    assert c.run_branch.__globals__['CapturedRequest'] is i.CapturedRequest
    assert c.run_branch.__globals__['FixedDefaultRequest'] is i.FixedDefaultRequest
    assert c.run_branch.__globals__['run_continuation'] is i.run_continuation
    assert c.worker.__globals__['run_branch'] is c.run_branch
    assert c.worker.__globals__['verify_plan'] is c.verify_plan
    assert 'verify_initial_owner_route_entry_campaign' in c.worker.__code__.co_names
    assert c.main.__globals__['worker'] is c.worker
    assert c.scene is c.previous.scene and c.declarations()==c.previous.declarations()
    assert c.contract.BUDGET_NS==100_000_000 and c.LIMIT==600.
    assert v._original_verify_branch.__code__ is v.previous._original_verify_branch.__code__
    assert v._original_verify_branch.__globals__['root_replay'] is v.root_replay
    assert v.verify_branch.__globals__['_original_verify_branch'] is v._original_verify_branch
    assert v.verify_saved.__globals__['verify_branch'] is v.verify_branch
    assert v.root_replay.__globals__['old'].root_replay is v._root_original
    assert v._root_original.__globals__['c'].contract is i.contract
    assert v.previous.old.old.root_replay.__globals__['c'].contract is i.entry.old


def synthetic_root():
    view,source=fixture();hop=i.contract.observed_first_hop(view,source)
    verdict=i.contract.closure('native_default',hop,None,queried_owner='A',request_id=None,
                               now=view['now'],timestamp_complete=True)
    # Source revalidation is exercised separately by its unchanged code. This
    # targeted fixture supplies a source through a private replay-only stub.
    start=time.perf_counter_ns();events=[
        {'stage':'predeclared_default_control','wall_ns':start+1,'at':.11,'value':{}},
        {'stage':'final_local_and_receiver_check','wall_ns':start+2,'at':.11,
         'value':{'view':{'owner_id':'A','now':.11},'verdict':{'status':'fresh_local_precondition_checked','source':source}}},
        {'stage':'continuation','wall_ns':start+3,'at':view['now'],
         'value':{'view':view,'command_query_owner':'A','command_query_id':None,'command':None,'hop':hop}},
        {'stage':'mandatory_drain','wall_ns':start+4,'at':view['now'],
         'value':{'status':'reached','physical_time':view['now'],'horizon_complete':True}},
        {'stage':'post_drain_observation','wall_ns':start+5,'at':view['now'],
         'value':{'view':view,'command_query_owner':'A','command_query_id':None,'command':None,'verdict':verdict}},
    ]
    root={'root_id':'normal:synthetic:fixed_default','owner':'A','root_started_ns':start,
          'decision_cutoff_ns':start+60_000_000,'root_deadline_ns':start+100_000_000,
          'choice':'native_default','command_id':None,'hop':hop,'events':events,'state':verdict['status']}
    encoded=c.image.artifact_encode(root)
    ledger={'evidence_sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded)}
    record={'value':{'evidence':root,'body_finished_ns':start+6},'outside_return_ns':start+7,
            'warm_caller_elapsed_ns':7,'ledger':ledger,'return_codec':c.image.artifact_encode(ledger).decode(),
            'closed':True}
    raw={'key':'normal/synthetic/fixed_default','root_records':[record],
         'initial_endpoint_records':{'A':[{'information':{'bundle':{}}}]},
         'specification':{'method':'fixed_default'},'outbox':{}}
    root['initial_endpoint_records']=raw['initial_endpoint_records']
    def rehash():
        encoded=c.image.artifact_encode(root);ledger.update(evidence_sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded))
        record['return_codec']=c.image.artifact_encode(ledger).decode()
    rehash();return raw,source,rehash


def replay_fixture(raw,source,new=True):
    from types import SimpleNamespace
    # No live request path accepts this facade; it exists only for this exact
    # root-replay test to isolate the changed hop/unchanged drain decisions.
    contract=SimpleNamespace(**vars(i.contract))
    contract.validate_final_local=lambda *args:{'status':'fresh_local_precondition_checked','source':deepcopy(source)}
    if not new:contract.observed_first_hop=i.entry.old.observed_first_hop
    campaign=SimpleNamespace(**vars(c));campaign.contract=contract
    return v.shared(v._root_original,{**v._root_original.__globals__,'c':campaign})(raw)


def test_saved_entry_positive_requires_new_predicate_old_replay_rejects():
    raw,source,_=synthetic_root()
    assert replay_fixture(raw,source)['closed']
    with pytest.raises(ValueError,match='physical_proof_not_observed'):replay_fixture(raw,source,False)


@pytest.mark.parametrize('mutation',['missing_entry','bad_generation','drain_incomplete','drain_absent','changed_hop'])
def test_saved_root_tampering_not_accepted_by_entry_replay(mutation):
    raw,source,rehash=synthetic_root();root=raw['root_records'][0]['value']['evidence']
    if mutation=='missing_entry':root['events'][2]['value']['view']['trays'][0].pop('edge_exit_at')
    elif mutation=='bad_generation':root['events'][2]['value']['view']['trays'][0]['generation']+=1
    elif mutation=='drain_incomplete':root['events'][3]['value']['horizon_complete']=False
    elif mutation=='drain_absent':root['events'][3]['stage']='not_a_drain'
    else:root['hop']['to']=2
    rehash()
    with pytest.raises(ValueError):replay_fixture(raw,source)


def test_marker_addition_does_not_bypass_old_complete_query_audit():
    from test_g31_circulation_initial_owner_route_gate_campaign_v2 import actual_client_fixture
    _,_,_,raw=actual_client_fixture()
    assert v.complete_query_replay(raw)['status']=='passed_complete_actual_refresh_outbox_replay'
    raw['ack_handling'].clear()
    with pytest.raises(ValueError,match='complete_actual_outbox'):v.complete_query_replay(raw)


def test_launcher_keeps_owned_tree_and_separate_target():
    from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_entry_campaign as launch
    assert launch.main.__code__ is launch.old.main.__code__
    assert launch.main.__globals__['MODULE'].endswith('.initial_owner_route_entry_campaign')
    assert launch.LIMIT==600.
