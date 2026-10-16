"""Closed single-case scope, serial patch restoration and evidence negatives."""
from copy import deepcopy
import inspect
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import research_original_low_wip_cap_relay as r
from scripts.experiments.g31_ics_circulation import launch_original_low_wip_cap_relay as launch
from scripts.experiments.g31_ics_circulation import verify_original_low_wip_cap_relay as verify


def good_receipt():
    return {'schema': r.SCHEMA, 'status': 'completed_finite_campaign', 'campaign_sha256': 'expected',
        'cases': {'cap8': {'status': 'completed_saved_case', 'execution': {'exit_code': 0},
            'verification': {'exit_code': 0}}}, 'source_changed': [], 'new_same_policy_cap3_pair': False,
        'assessment': {'status': 'complete_cap8_with_bidirectional_cap_relay'}, 'wall_seconds': 100.}


def test_single_case_full_input_scope_and_distinct_prior_reference():
    with r.installed():
        scope = r.contract()
        assert r.reference.CAPS == {'cap8': 8} and scope['caps'] == {'cap8': 8}
        assert scope['horizon'] == 86400. and scope['offered'] == 28506 and scope['trays'] == 22
        assert scope['original_r1'] is False and r.reference.PARENT_SECONDS == launch.LIMIT == 2400.
        assert scope['cap_relay']['additional_publications_per_owner_maximum'] == 1
        assert 'not an execution of this new relay policy' in scope['prior_attempt_reference']['scope']


def test_original_worker_and_policy_loop_preserved_and_context_restores_on_error():
    before = {k: getattr(r.reference, k) for k in r._original}
    loop = r.reference.run_policy; worker = r.reference.base.worker
    with pytest.raises(RuntimeError, match='stop'):
        with r.installed():
            assert r.reference.RepeatOwner is r.candidate.RepeatOwner
            assert r.reference.run_policy is loop and r.reference.base.worker is worker
            with pytest.raises(ValueError, match='overlap'):
                with r.installed(): pass
            raise RuntimeError('stop')
    assert all(getattr(r.reference, k) is value for k, value in before.items())


def test_source_closure_contains_actual_candidate_launcher_verifier_and_tests():
    paths = r.source_paths(); names = {p.name for p in paths}
    assert len(paths) == len(set(paths)) and all(p.is_file() for p in paths)
    assert {'repeat_cap_barrier_relay.py', 'repeat_quiescent_cap.py',
        'research_original_low_wip_cap_relay.py', 'verify_original_low_wip_cap_relay.py',
        'launch_original_low_wip_cap_relay.py', 'test_g31_circulation_cap_barrier_relay.py',
        'test_g31_circulation_low_wip_cap_relay.py', 'bounded_windows_job.py'} <= names


def test_prepare_uses_only_cap8_and_restores_globals(monkeypatch, tmp_path):
    seen = []
    def prepare(path):
        seen.append((dict(r.reference.CAPS), r.reference.SCHEMA, r.reference.RepeatOwner))
        return {'path': str(path)}
    monkeypatch.setattr(r.reference, 'prepare', prepare)
    prior = r.reference.CAPS
    r.prepare(tmp_path / 'not_executed')
    assert seen == [({'cap8': 8}, r.SCHEMA, r.candidate.RepeatOwner)] and r.reference.CAPS is prior


def test_launcher_admits_only_complete_single_case_with_verified_relay():
    launch.validate_internal(good_receipt(), 'expected')


@pytest.mark.parametrize('change', ['cap3', 'missing_case', 'unknown_relay', 'source_drift',
    'same_pair', 'wrong_campaign', 'worker_failure', 'verifier_failure', 'case_unknown',
    'over_budget', 'bool_budget', 'nan_budget'])
def test_launcher_fails_closed(change):
    value = good_receipt()
    if change == 'cap3': value['cases']['cap3'] = deepcopy(value['cases']['cap8'])
    elif change == 'missing_case': value['cases'] = {}
    elif change == 'unknown_relay': value['assessment']['status'] = 'unknown_or_incomplete_cap_relay'
    elif change == 'source_drift': value['source_changed'] = ['changed']
    elif change == 'same_pair': value['new_same_policy_cap3_pair'] = True
    elif change == 'wrong_campaign': value['campaign_sha256'] = 'other'
    elif change == 'worker_failure': value['cases']['cap8']['execution']['exit_code'] = 1
    elif change == 'verifier_failure': value['cases']['cap8']['verification']['exit_code'] = 1
    elif change == 'case_unknown': value['cases']['cap8']['status'] = 'unknown'
    elif change == 'over_budget': value['wall_seconds'] = 2400.0001
    elif change == 'bool_budget': value['wall_seconds'] = True
    elif change == 'nan_budget': value['wall_seconds'] = float('nan')
    with pytest.raises(ValueError): launch.validate_internal(value, 'expected')


def test_verify_old_cap3_cannot_become_new_cap8_even_if_full_day():
    old = r.PRIOR / 'cap3'
    raw = r.reference.base.gzread(old / 'raw_final.json.gz')
    plan = r.reference.base.read(old / 'preregistered_protocol.json')
    result = verify.assess_relays(raw, plan, {}, {}, {})
    assert result['status'] == 'unknown_or_incomplete_cap_relay'
    assert result['physical_assessment']['actual_supplies'] == 3
    assert result['new_same_policy_cap3_pair'] is False


@pytest.mark.parametrize('change', ['omit', 'duplicate'])
def test_both_source_owner_denominator_is_required(change):
    old = r.PRIOR / 'cap3'; raw = r.reference.base.gzread(old / 'raw_final.json.gz')
    plan = r.reference.base.read(old / 'preregistered_protocol.json')
    raw['owners'] = raw['owners'][:1] if change == 'omit' else [raw['owners'][0], raw['owners'][0]]
    with pytest.raises(ValueError, match='owner_domain'): verify.assess_relays(raw, plan, {}, {}, {})


def test_no_second_full_replay_in_verifier():
    source = inspect.getsource(verify.verify_case)
    assert source.count('verify_case_corrected(directory)') == 1
    assert 'scan_api(' not in source and 'NativeSession' not in source
    assert 'all_job_states.json.gz' in source


def test_own_job_includes_worker_and_verifier_and_no_comparison_process():
    source = inspect.getsource(r.campaign_worker)
    assert "child(['--worker', 'cap8']" in source and "child(['--verify', 'cap8']" in source
    assert '--compare' not in source and 'LIMIT - (time.monotonic() - began)' in source
    assert launch.MODULE == r.MODULE and launch.LIMIT == r.LIMIT == 2400.


def evidence_binding_fixture(monkeypatch):
    # A native receipt shape reused only for unit-testing saved-verifier
    # bindings. This is deliberately NOT claimed as an actual new cap proof.
    from test_g31_circulation_cap_barrier_relay import actual, actual_delivered_summary
    owner = actual_delivered_summary(); who = owner['cap_barrier_relay']['source_owner']
    rid = owner['cap_barrier_relay']['request_id']; owner['owner'] = who
    proof = {'known_supply_count': 8, 'received_request_ids': ['synthetic_guard_fixture'], 'peer_message_id': 'fixture'}
    owner['cap_barrier_relay']['fresh_cap_proof'] = deepcopy(proof)
    owner['repeat_publications'] = [{'request_id': rid, 'reason': {'kind': 'terminal_cap_barrier_relay'}}]
    peer = {'owner': owner['cap_barrier_relay']['target_owner'], 'cap_observed': False}
    raw = {'owners': [owner, peer], 'physical_time': 86400., 'physical_audit': {'status': 'passed'}}
    plan = {'supply_cap': 8, 'parking_plan': {'owners': [who, peer['owner']]}}
    proofs = {who: {'at': 26020., 'after_api_ordinal': 18017, 'physical_barrier': proof}}
    submits = {rid: actual(18018)}; queries = {rid: [actual(18024)]}
    monkeypatch.setattr(r.reference, 'assess', lambda *_: {'status': 'complete_finite_policy_evidence',
        'actual_supplies': 8, 'completion_witnesses': [{}] * 8})
    return raw, plan, proofs, submits, queries, rid


def test_one_valid_historical_receipt_never_replaces_other_owner_proof(monkeypatch):
    raw, plan, proofs, submits, queries, rid = evidence_binding_fixture(monkeypatch)
    value = verify.assess_relays(raw, plan, proofs, submits, queries)
    assert value['status'] == 'unknown_or_incomplete_cap_relay'
    assert sum(x['status'] == 'actual_fresh_cap_proof_and_delivered_own_relay'
        for x in value['owner_proofs'].values()) == 1


@pytest.mark.parametrize('change', ['missing_submit', 'submit_order', 'proof_clock', 'query_missing',
    'query_before_ack', 'query_owner', 'digest_changed', 'duplicate_publication'])
def test_actual_cap_relay_evidence_cannot_be_relabelled_or_omitted(monkeypatch, change):
    raw, plan, proofs, submits, queries, rid = evidence_binding_fixture(monkeypatch)
    if change == 'missing_submit': submits.clear()
    elif change == 'submit_order': submits[rid]['ordinal'] += 1
    elif change == 'proof_clock': next(iter(proofs.values()))['at'] += 10
    elif change == 'query_missing': queries.clear()
    elif change == 'query_before_ack': queries[rid][0]['before'] = queries[rid][0]['after'] = 26024.
    elif change == 'query_owner': queries[rid][0]['args'][0] = 'different'
    elif change == 'digest_changed':
        ack = raw['owners'][0]['outbox']['outbox'][rid]['client_view']['last_delivered_ack']
        ack['planning_snapshot_v2']['payload_sha256'] = '0' * 64
        queries[rid][0]['result']['last_delivered_ack'] = deepcopy(ack)
    elif change == 'duplicate_publication': raw['owners'][0]['repeat_publications'] *= 2
    with pytest.raises(ValueError): verify.assess_relays(raw, plan, proofs, submits, queries)
