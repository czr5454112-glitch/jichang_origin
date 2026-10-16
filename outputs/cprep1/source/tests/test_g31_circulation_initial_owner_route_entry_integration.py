"""Synthetic closed wiring and failure tests; no live capability is forged."""
from copy import deepcopy
from types import SimpleNamespace
import time
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_integration as i
from test_g31_circulation_initial_owner_route_entry_hop import fixture


class Session:
    def __init__(self, view, command=None, complete=True):
        self.view, self.command, self.complete = view, command, complete
        self.physical_time = view['now']; self.calls = []
    def observe_protocol(self, owner):
        self.calls.append(('observe', owner)); return deepcopy(self.view)
    def protocol_command(self, owner, identity):
        self.calls.append(('command', owner, identity)); return deepcopy(self.command)
    def advance_to(self, now, **kwargs):
        self.calls.append(('drain', now))
        return {'status':'reached','physical_time':now,'horizon_complete':self.complete}


def root_fixture(choice='native_default', command=None, complete=True):
    view, source = fixture(); session = Session(view, command, complete)
    client = i.make_client(session)
    class Root:
        _record = i.previous.request.InitialOwnerRequest._record
        observe_after_boundary = i.TRACED_OBSERVE
        # Fixture-only untracked drain substitution cannot enter ActualAdvanceChain.
        drain_and_finish_if_closed = i.private(i.TRACKED_DRAIN,
            {'_actual_root_drain':lambda root, now, **kw: root.session.advance_to(now, **kw)})
    root = Root(); root.session, root.client = session, client
    root.source, root.hop, root.choice = source, None, choice
    root.state, root.events = 'pending_first_hop_and_ack', []
    root.request_id, root.command_id = 'pure-entry-root', ('route1' if choice=='prefer_2' else None)
    root.last_boundary = None
    return root


def test_complete_source_proof_and_old_global_isolation():
    proof=i.integration_proof()
    assert proof['native_or_predictor_dispatched'] is False
    assert proof['original_closure_and_ACK_code_unchanged']
    assert proof['scheduler']['firsthop_detector_changed']
    assert not proof['scheduler']['resulting_admission_or_ID_equality_claimed']
    assert i.previous.CapturedRequest.observe_after_boundary is i.previous.TRACED_OBSERVE
    assert i.previous.CapturedRequest.drain_and_finish_if_closed is i.previous.TRACKED_DRAIN
    assert i.previous.TRACED_OBSERVE.__globals__['contract'] is i.entry.old
    assert i.previous.TRACKED_DRAIN.__globals__['contract'] is i.entry.old
    assert i.TRACED_OBSERVE.__globals__['contract'] is i.TRACKED_DRAIN.__globals__['contract']
    assert i.contract.closure is i.entry.old.closure
    assert i.CapturedRequest.collect is i.previous.CapturedRequest.collect
    assert i.CapturedRequest.final_revalidate_and_submit is i.previous.CapturedRequest.final_revalidate_and_submit


def test_live_chain_rejects_data_fixture_before_any_native_call():
    root=root_fixture();root.native=object();root.accepted={}
    with pytest.raises(ValueError,match='accepted_session'):
        i.ActualAdvanceChain(root.session,root.client,root,{})
    assert root.session.calls==[]


@pytest.mark.parametrize('choice',['native_default','prefer_2'])
def test_observe_uses_entry_but_only_complete_actual_drain_closes(choice):
    command={'request_id':'route1','kind':'route','last_delivered_ack':{'status':'updated','delivered_at':4.0}}
    root=root_fixture(choice,command)
    response={'status':'reached','physical_time':root.session.physical_time,'horizon_complete':True}
    verdict=root.observe_after_boundary(response)
    assert not verdict['closed'] and root.state=='pending_first_hop_and_ack'
    assert root.hop['observed_at']==4.171 and root.hop['tray']['committed_prefix']==[0]
    assert not any(c[0]=='drain' for c in root.session.calls)
    verdict=root.drain_and_finish_if_closed()
    assert verdict['closed'] and root.state==verdict['status']
    assert root.session.calls[-(3 if choice=='prefer_2' else 2)][0]=='drain'
    assert [e['stage'] for e in root.events][-2:]==['mandatory_drain','post_drain_observation']
    if choice=='prefer_2':assert verdict['requested_hop_executed'] is False


@pytest.mark.parametrize('defect',['missing_ack','future_ack','wrong_request','wrong_kind','incomplete_drain',
    'reservation_only','wrong_generation','wrong_owner'])
def test_actual_entry_never_bypasses_original_guards(defect):
    command={'request_id':'route1','kind':'route','last_delivered_ack':{'status':'updated','delivered_at':4.0}}
    root=root_fixture('prefer_2',command)
    if defect=='missing_ack':root.session.command['last_delivered_ack']={}
    elif defect=='future_ack':root.session.command['last_delivered_ack']['delivered_at']=5.
    elif defect=='wrong_request':root.session.command['request_id']='other'
    elif defect=='wrong_kind':root.session.command['kind']='transfer'
    elif defect=='incomplete_drain':root.session.complete=False
    elif defect=='reservation_only':root.session.view['trays'][0].pop('edge_exit_at')
    elif defect=='wrong_generation':root.session.view['trays'][0]['generation']+=1
    else:root.session.view['owner_id']='B'
    assert not root.drain_and_finish_if_closed()['closed']
    assert root.state=='pending_first_hop_and_ack'


def test_first_post_drain_entry_is_captured_without_prior_sticky_hop():
    root=root_fixture()
    assert root.hop is None
    verdict=root.drain_and_finish_if_closed()
    assert verdict['closed'] and root.hop['observed_at']==4.171


def test_evidence_is_complete_owned_and_marker_is_charged_before_body_stamp():
    root=root_fixture();root.started_ns=time.perf_counter_ns()
    root.deadline_ns=root.started_ns+100_000_000;root.cutoff_ns=root.started_ns+60_000_000
    root.initial_endpoint_records=[];root.B_endpoint_records=[]
    root.evidence=i.EVIDENCE.__get__(root)
    finished=i.finish_root(root)
    evidence=finished['value']['evidence']
    assert evidence['runtime_query_proof']['first_hop_observation_contract']==i.MARKER
    assert evidence['events']==root.events and evidence['events'] is not root.events
    assert finished['value']['body_finished_ns']>=finished['finalization_started_ns']
    evidence['runtime_query_proof']['first_hop_observation_contract']['source_prefix'].append(99)
    assert i.MARKER['source_prefix']==[0]
    assert i.previous.finish_root.__globals__['evidence'] is i.previous.EVIDENCE


def test_scheduler_and_publisher_keep_original_code_but_bind_new_exact_chain():
    assert i.run_continuation.__code__ is i.previous.run_continuation.__code__
    assert i.run_continuation.__globals__['ActualAdvanceChain'] is i.ActualAdvanceChain
    assert i.run_continuation.__globals__['publish_root'] is i.publish_root
    assert i.finish_root.__globals__['evidence'] is i.EVIDENCE
    assert i.ActualAdvanceChain.__init__.__globals__['TRACKED_DRAIN'] is i.TRACKED_DRAIN
    assert i.ActualAdvanceChain.__init__.__globals__['CapturedRequest'] is i.CapturedRequest
    assert i.TracedContinuationOwner is i.previous.TracedContinuationOwner
