"""Focused composition checks; full codec and entry contracts have their own gates."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_codec_integration as i
from test_g31_circulation_initial_owner_route_entry_integration import root_fixture


def prepared_root():
    root=root_fixture();root.started_ns=1;root.deadline_ns=100_000_001;root.cutoff_ns=60_000_001
    root.initial_endpoint_records=[];root.B_endpoint_records=[]
    root.evidence=i.EVIDENCE.__get__(root)
    return root


def test_proof_retains_live_observation_and_authority():
    proof=i.integration_proof()
    assert proof['original_accepted_native_and_exact_transport_authority_unchanged']
    assert proof['actual_entry_marker_and_complete_query_proof_encoded']
    assert not proof['native_or_predictor_dispatched']
    assert i.CapturedRequest.collect is i.entry.CapturedRequest.collect
    assert i.CapturedRequest.final_revalidate_and_submit is i.entry.CapturedRequest.final_revalidate_and_submit
    assert i.FixedDefaultRequest.choose is i.entry.FixedDefaultRequest.choose
    assert i.run_continuation.__globals__['ActualAdvanceChain'] is i.entry.ActualAdvanceChain
    assert i.TracedContinuationOwner is i.entry.TracedContinuationOwner


def test_full_evidence_exactly_matches_entry_tree_at_same_body_clock():
    root=prepared_root();clock=SimpleNamespace(perf_counter_ns=lambda:123456)
    root.events.append({'stage':'pure_types','value':{'a':-0.0,'b':1,'c':1.0,'d':'\U0001f642'}})
    old=i.private(i.entry.EVIDENCE,{'time':clock})(root)
    new=i.private(i.EVIDENCE,{'time':clock})(root)
    assert old.pop('encoded')==new.pop('encoded')
    assert i.codec.single.exact_tree(old,new)
    assert new['evidence']['runtime_query_proof']['first_hop_observation_contract']==i.entry.MARKER


def test_output_is_fresh_and_later_input_or_output_mutations_do_not_cross():
    root=prepared_root();root.events.append({'stage':'nested','value':{'ordered':[1,2]}})
    result=i.finish_root(root)
    evidence=result['value']['evidence'];saved=deepcopy(evidence)
    root.events[0]['value']['ordered'].append(3)
    assert i.codec.single.exact_tree(saved,evidence)
    evidence['runtime_query_proof']['first_hop_observation_contract']['source_prefix'].append(9)
    assert i.entry.MARKER['source_prefix']==[0]
    assert result['ledger']['bytes']>0


def test_strict_codec_failure_cannot_escape_through_finisher():
    root=prepared_root()
    def fail(encoded):raise ValueError('injected_strict_readback_failure')
    root.evidence=i.private(i.EVIDENCE,{'_codec_check':fail}).__get__(root)
    with pytest.raises(ValueError,match='injected_strict_readback_failure'):i.finish_root(root)


def test_unknown_data_never_bypasses_original_normalizer():
    root=prepared_root();root.events.append({'stage':'unknown','value':object()})
    with pytest.raises((ValueError,TypeError)):i.finish_root(root)


def test_exact_native_authority_still_rejects_synthetic_root():
    root=prepared_root();root.native=object();root.accepted={}
    with pytest.raises(ValueError,match='accepted_session'):
        i.ActualAdvanceChain(root.session,root.client,root,{})
    assert root.session.calls==[]


def test_original_modules_and_classes_still_have_their_original_bindings():
    assert i.entry.CapturedRequest.evidence is i.entry.EVIDENCE
    assert i.entry.finish_root.__globals__['evidence'] is i.entry.EVIDENCE
    assert i.entry.run_continuation.__globals__['publish_root'] is i.entry.publish_root
    assert i.codec.EVIDENCE.__globals__['root_runtime_proof'] is i.codec.frozen.root_runtime_proof
    assert i.codec.finish_root.__globals__['evidence'] is i.codec.EVIDENCE
