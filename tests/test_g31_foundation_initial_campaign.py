"""Pure runner/receipt tests; no native process or rollout is executed."""
import copy
import gzip
import json
import math

import pytest

from scripts.experiments.g31_ics_circulation import foundation_initial_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_budgeted_provider as provider


def native_fixture(mode='incumbent', selected=4):
    actions = provider.teacher.future.core.lazy.original.physics.previous.actions()
    raw = {'kind': 'EvaluatorRecord', 'native027_acceptance': {'runtime_accepted': True},
        'specification': {'case': 'mechanism', 'method': 'incumbent', 'fault': None},
        'input': {'fixed': 'same scene'}, 'summary': {'status': 'assessed',
            'completion': {job: 10. for job in campaign.JOBS}},
        'initial_evaluator_advice': {}, 'later_transitions': [], 'initial_owners': {}, 'calls': [], 'outbox': {}}
    for owner in ('A', 'B'):
        queried = [4, 5, 12, 13] if mode == 'learned' and owner == 'B' else [4]
        chosen = selected if owner == 'B' and mode == 'learned' else 4
        k, p = len(queried), 2 if len(queried) == 4 else 1
        rows = [{'candidate_index': index, 'action': action,
            'status': 'conditional_forecast' if index in queried else 'not_requested',
            'completion': {job: 10. for job in campaign.JOBS} if index in queried else None}
            for index, action in enumerate(actions)]
        report = {'owner': owner, 'initial_public_sha256': 'current:' + owner, 'actual_collection_at': .11,
            'status': 'conditional_forecasts_complete', 'source_binding': {'close_completed': True,
                'before_close': {'proof_binding': {'proof_uses': 1 + 2 * k}}},
            'requested_indices': queried, 'allocation': {'candidate_budget': k, 'prefix_budget': p},
            'evaluated_candidate_count': k, 'evaluated_prefix_count': p,
            'counts': {'future_forks': k, 'future_resumes': k, 'context_constructions': p},
            'public_compatibility_filter': {'enabled': True}, 'rows': rows}
        initial = {'selection': {'selector_mode': mode, 'model_version': 'frozen' if mode == 'learned' else None,
            'selected_index': chosen, 'selected_action': copy.deepcopy(actions[chosen]), 'provider_evidence': report,
            'accounting': {'query_indices': list(queried)}, 'allowed_candidate_indices': [chosen]},
            'collection': {'owner': owner, 'public_sha256': 'current:' + owner, 'at': .11},
            'compatibility': {'selected_index': chosen}, 'selected_action': copy.deepcopy(actions[chosen]),
            'immediate_component': {'status': 'fresh_local_component_proposal', 'owner': owner,
                'public_sha256': 'current:' + owner}, 'continuation_policy_created': True,
            'native_request_id': None, 'native_default_no_command': owner == 'A'}
        if owner == 'B':
            identity = 'initial:B'
            request = {'request_id': identity, 'owner_id': 'B', 'tray_id': 'E', 'source': 5, 'destination': 1,
                'earliest_departure': actions[chosen]['empty_departure']}
            initial.update(native_request_id=identity, submission={'request': copy.deepcopy(request)})
            raw['calls'].append({'request': copy.deepcopy(request), 'retry': False})
            raw['outbox'][identity] = {'request': copy.deepcopy(request),
                'ack': {'status': 'rejected', 'reason': 'receiving_full', 'delivered_at': 2.69}}
        raw['initial_owners'][owner] = initial
    return raw


@pytest.fixture
def registered(tmp_path, monkeypatch):
    model = tmp_path / 'model.json'
    model.write_text('{}')
    monkeypatch.setattr(campaign, 'MODEL_SHA256', campaign.sha(model))
    plan = {'schema': campaign.SCHEMA, 'hard_process_seconds': 150, 'branches': copy.deepcopy(list(campaign.BRANCHES)),
        'automatic_retries': 0, 'scenario': 'mechanism', 'method': 'incumbent', 'horizon': 40.,
        'timing_mode': 'offline_sync', 'model': campaign.reference(model), 'model_copy': campaign.reference(model),
        'feature_count': 43, 'model_version': 'frozen', 'source_sha256': {}, 'source_archive': {}, 'runtime_references': []}
    campaign.write_new(tmp_path / 'plan.json', plan)
    monkeypatch.setattr(campaign, 'source_pins', lambda: {})
    return tmp_path, plan


def test_chain_verifies_actual_chosen_action_and_preserves_rejected_ACK():
    assessment = campaign.assess_branch(native_fixture('learned', 12), 'learned', 'frozen')
    assert assessment['owners']['B']['selected_index'] == 12
    assert assessment['owners']['B']['actual_K'] == 4
    assert assessment['owners']['B']['actual_P'] == 2
    assert assessment['owners']['B']['ACK']['status'] == 'rejected'
    assert assessment['owners']['A']['ACK'] is None
    assert assessment['owners']['A']['native_request_id'] is None
    assert assessment['native_protection_certified'] is False


@pytest.mark.parametrize('change', ['advice_only', 'wrong_mode', 'old_observation', 'query_count', 'prefix_count',
    'unqueried_prediction', 'different_dispatch', 'different_transfer', 'no_ack', 'future_ack', 'harm', 'unclosed'])
def test_chain_rejects_missing_or_mismatched_execution_evidence(change):
    raw = native_fixture('learned', 12)
    initial = raw['initial_owners']['B']
    report = initial['selection']['provider_evidence']
    if change == 'advice_only':
        raw['initial_evaluator_advice'] = {'B': {'selected_index': 12}}
    elif change == 'wrong_mode':
        initial['selection']['selector_mode'] = 'incumbent'
    elif change == 'old_observation':
        report['actual_collection_at'] = .05
    elif change == 'query_count':
        report['counts']['future_resumes'] += 1
    elif change == 'prefix_count':
        report['counts']['context_constructions'] += 1
    elif change == 'unqueried_prediction':
        report['rows'][31]['prediction'] = {'forbidden': True}
    elif change == 'different_dispatch':
        initial['selected_action'] = copy.deepcopy(report['rows'][4]['action'])
    elif change == 'different_transfer':
        raw['calls'][0]['request']['earliest_departure'] += .1
    elif change == 'no_ack':
        raw['outbox']['initial:B']['ack'] = None
    elif change == 'future_ack':
        raw['outbox']['initial:B']['ack']['delivered_at'] = 40.01
    elif change == 'harm':
        report['rows'][12]['completion']['loaded'] = math.nextafter(10., math.inf)
    elif change == 'unclosed':
        report['source_binding']['close_completed'] = False
    with pytest.raises(ValueError):
        campaign.assess_branch(raw, 'learned', 'frozen')


def test_matched_pair_reports_one_ulp_harm_without_tolerance_or_failing_to_save_result():
    baseline, learned = native_fixture(), native_fixture('learned', 12)
    learned['summary']['completion']['receiver'] -= .119
    learned['summary']['completion']['loaded'] = math.nextafter(10., math.inf)
    result = campaign.compare_pair(baseline, learned)
    assert result['status'] == 'completed_matched_native_pair'
    assert result['per_job_delta_s']['loaded'] > 0
    assert result['observed_five_job_non_degradation'] is False
    assert result['observed_strict_improvement'] is False


def test_pair_requires_identical_input_and_all_five_real_completions():
    before, after = native_fixture(), native_fixture('learned')
    after['input'] = {'different': 'scene'}
    with pytest.raises(ValueError, match='input_mismatch'):
        campaign.compare_pair(before, after)
    after['input'] = before['input']
    after['summary']['completion']['receiver'] = -1.
    with pytest.raises(ValueError, match='five_completed'):
        campaign.compare_pair(before, after)


@pytest.mark.parametrize('field,value', [('hard_process_seconds', 151), ('automatic_retries', 1),
    ('branches', []), ('scenario', 'no_overlap'), ('timing_mode', 'realtime'), ('feature_count', 52)])
def test_fixed_plan_cannot_change_domain_model_budget_or_clock(registered, field, value):
    _, plan = registered
    plan[field] = value
    with pytest.raises(ValueError):
        campaign.check_pins(plan)


def test_changed_source_set_or_model_fails_closed(registered, monkeypatch):
    _, plan = registered
    monkeypatch.setattr(campaign, 'source_pins', lambda: {'new.py': 'unregistered'})
    with pytest.raises(ValueError, match='source_set_or_bytes_changed'):
        campaign.check_pins(plan)
    monkeypatch.setattr(campaign, 'source_pins', lambda: {})
    with open(plan['model']['path'], 'a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='pinned_artifact_changed'):
        campaign.check_pins(plan)


def save_native(output, branch):
    raw = native_fixture(branch['mode'], 12 if branch['mode'] == 'learned' else 4)
    path = output / branch['id'] / 'native/raw.json.gz'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(raw).encode()))
    receipt_path = path.parent / 'receipt.json'
    campaign.write_new(receipt_path, {'status': 'assessed', 'run_acceptance_status': 'closed_run_acceptance_passed',
        'raw_artifact': campaign.reference(path)})
    assessment = campaign.assess_branch(raw, branch['mode'], 'frozen')
    campaign.write_new(output / branch['id'] / 'worker_report.json', {'status': 'completed_initial_episode',
        'native_receipt': campaign.reference(receipt_path), 'assessment': assessment})
    return receipt_path


@pytest.mark.parametrize('status,exitcode,complete', [('exited', 0, True), ('hard_timeout', 0, False), ('exited', 1, False)])
def test_process_status_and_raw_chain_required_even_if_child_claims_success(registered, monkeypatch, status, exitcode, complete):
    output, plan = registered
    branch = plan['branches'][0]
    def run(command, **kwargs):
        assert kwargs['timeout'] == 150
        assert command[command.index('--admission') + 1] == kwargs['admission']
        assert command[command.index('--plan-sha256') + 1] == campaign.sha(output / 'plan.json')
        save_native(output, branch)
        return {'status': status, 'exitcode': exitcode}
    monkeypatch.setattr(campaign.bounded_windows_job, 'run', run)
    result = campaign.launch_branch(output, branch, plan, campaign.sha(output / 'plan.json'))
    assert (result['status'] == 'completed_initial_episode') is complete
    with pytest.raises(FileExistsError):
        campaign.launch_branch(output, branch, plan, campaign.sha(output / 'plan.json'))


def test_parent_recomputes_raw_chain_instead_of_trusting_child_assessment(registered, monkeypatch):
    output, plan = registered
    branch = plan['branches'][0]
    def run(*args, **kwargs):
        receipt_path = save_native(output, branch)
        child_path = output / branch['id'] / 'worker_report.json'
        child = campaign.read(child_path)
        child['assessment']['owners']['B']['selected_index'] = 12
        child_path.write_text(json.dumps(child))
        return {'status': 'exited', 'exitcode': 0}
    monkeypatch.setattr(campaign.bounded_windows_job, 'run', run)
    result = campaign.launch_branch(output, branch, plan, campaign.sha(output / 'plan.json'))
    assert result['status'] == 'unknown_incomplete_episode'
    assert 'recomputed_chain_assessment' in result['exception']


def test_pair_stops_after_failure_and_cannot_retry(registered, monkeypatch):
    output, _ = registered
    attempted = []
    def branch(*args):
        attempted.append(args[1]['id'])
        return {'status': 'unknown_incomplete_episode'}
    monkeypatch.setattr(campaign, 'launch_branch', branch)
    result = campaign.launch(output)
    assert attempted == ['bridge04']
    assert result['status'] == 'unknown_incomplete_campaign'
    assert result['attempted_count'] == 1
    assert 'pair' not in result
    with pytest.raises(FileExistsError):
        campaign.launch(output)


def test_successful_two_branch_pair_is_saved_without_claiming_gain(registered, monkeypatch):
    output, _ = registered
    def branch(output, specification, plan, plan_sha):
        path = save_native(output, specification)
        return {'status': 'completed_initial_episode', 'native_receipt': campaign.reference(path)}
    monkeypatch.setattr(campaign, 'launch_branch', branch)
    result = campaign.launch(output)
    assert result['status'] == 'completed_initial_selector_campaign'
    assert result['pair']['observed_five_job_non_degradation'] is True
    assert result['pair']['observed_strict_improvement'] is False
    assert result['pair']['multistep_RL_established'] is False


def test_worker_refuses_wrong_plan_hash_before_native_execution(registered):
    output, _ = registered
    result = campaign.worker(output, 'bridge04', 'wrong_hash')
    assert result['status'] == 'unknown_source_or_model_changed'
    assert result['native_execution_attempted'] is False


def test_preparation_archives_sources_and_exact_preexisting_model_without_native(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    model = tmp_path / 'models/model.json'
    campaign.write_new(model, {'model_version': 'frozen', 'feature_schema': 'features43'})
    campaign.write_new(model.parent / 'folds.json', [])
    campaign.write_new(model.parent / 'registration.json', {})
    monkeypatch.setattr(campaign, 'MODEL_SHA256', campaign.sha(model))
    monkeypatch.setattr(campaign, 'validate_model', lambda path: campaign.read(path))
    source = tmp_path / 'source.py'
    source.write_text('VALUE = 1\n')
    monkeypatch.setattr(campaign, 'source_pins', lambda: {str(source): campaign.sha(source)})
    binary = tmp_path / 'native.pyd'
    binary.write_bytes(b'not-a-native-test')
    directory = tmp_path / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
    campaign.write_new(directory / 'native027_accepted_contract_001.json', {'binary': str(binary)})
    campaign.write_new(directory / 'native027_semantic_native_002/receipt.json', {})
    output = tmp_path / 'prepared'
    plan = campaign.prepare(output, model=model)
    assert plan['model']['sha256'] == plan['model_copy']['sha256']
    assert plan['source_archive'][str(source)] == str(output / 'source/0000.py')
    assert (output / 'source/0000.py').read_bytes() == source.read_bytes()
    assert plan['native_episode_budget'] == 2
    assert plan['branches'] == list(campaign.BRANCHES)
    assert not (output / 'launch.json').exists()
    with pytest.raises(ValueError, match='fresh_output_required'):
        campaign.prepare(output, model=model)
