"""Runner tests use no native process or physical model execution."""
import copy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_later_campaign as campaign


@pytest.fixture
def registered(tmp_path, monkeypatch):
    plan = {'schema': campaign.SCHEMA, 'hard_process_seconds': 150, 'checkpoint': None,
        'branches': copy.deepcopy(list(campaign.BRANCHES)), 'scenario': 'mechanism', 'horizon': 40.,
        'method': 'incumbent', 'automatic_retries': 0, 'source_sha256': {}, 'runtime_references': []}
    campaign.write_new(tmp_path / 'plan.json', plan)
    monkeypatch.setattr(campaign, 'source_pins', lambda: {})
    return tmp_path, plan


def test_fixed_selection_matches_enabled_action_not_first_row():
    records = []
    choose = campaign.choose_fixed({'first_reuse_route': 'prefer_8'}, records)
    observation = {'owner': 'B', 'phase': 'first_reuse_route', 'at': 9.69}
    rows = [{'candidate_id': 'default', 'action_id': 'native_default', 'enabled': True},
            {'candidate_id': 'alternative', 'action_id': 'prefer_8', 'enabled': True}]
    assert choose(observation, rows) == 'alternative'
    rows[1]['enabled'] = False
    with pytest.raises(ValueError, match='disabled_no_fallback'):
        choose(observation, rows)
    assert len(records) == 1


def test_learned_selector_only_scores_enabled_legal_observation(tmp_path, monkeypatch):
    from scripts.experiments.g31_ics_circulation import foundation_later_learning as learning
    path = tmp_path / 'checkpoint.json'
    campaign.write_new(path, {'schema': learning.MODEL_SCHEMA})
    seen = []
    def predict(model, observation, action_id):
        seen.append((observation, action_id))
        return 2. if action_id == 'return_now' else 1.
    monkeypatch.setattr(learning, 'predict', predict)
    records = []
    choose = campaign.choose_learned(campaign.reference(path), records)
    observation = {'owner': 'A', 'phase': 'first_return', 'at': 7.34}
    rows = [{'candidate_id': 'now', 'action_id': 'return_now', 'enabled': True},
            {'candidate_id': 'later', 'action_id': 'return_not_before_7_84', 'enabled': False}]
    assert choose(observation, rows) == 'now'
    assert seen == [(observation, 'return_now')]
    assert records[0]['scores'][0]['value_s'] == 2.
    rows[1]['enabled'] = True
    assert choose(observation, rows) == 'later'


@pytest.mark.parametrize('field,value', [('hard_process_seconds', 151), ('scenario', 'other'),
                                       ('automatic_retries', 1), ('branches', [])])
def test_fixed_protocol_is_not_mutable(registered, field, value):
    _, plan = registered
    plan[field] = value
    with pytest.raises(ValueError):
        campaign.check_pins(plan)


def test_changed_source_set_fails_closed(registered, monkeypatch):
    _, plan = registered
    monkeypatch.setattr(campaign, 'source_pins', lambda: {'new_source.py': 'changed'})
    with pytest.raises(ValueError, match='source_set_or_bytes_changed'):
        campaign.check_pins(plan)


@pytest.mark.parametrize('process_status,exitcode,expected', [
    ('exited', 0, 'completed_later_episode'),
    ('hard_timeout', 0, 'unknown_incomplete_episode'),
    ('exited', 1, 'unknown_incomplete_episode')])
def test_parent_requires_process_success_and_native_receipt_binding(registered, monkeypatch, process_status, exitcode, expected):
    output, plan = registered
    branch = plan['branches'][0]
    def run(command, **kwargs):
        assert kwargs['timeout'] == 150
        assert command[command.index('--plan-sha256') + 1] == campaign.sha(output / 'plan.json')
        assert command[command.index('--admission') + 1] == kwargs['admission']
        receipt_path = output / branch['id'] / 'episode/native/receipt.json'
        campaign.write_new(receipt_path, {'status': 'assessed', 'run_acceptance_status': 'closed_run_acceptance_passed'})
        campaign.write_new(output / branch['id'] / 'worker_report.json', {
            'status': 'completed_later_episode', 'native_receipt': campaign.reference(receipt_path)})
        return {'status': process_status, 'exitcode': exitcode}
    monkeypatch.setattr(campaign.bounded_windows_job, 'run', run)
    result = campaign.launch_branch(output, branch, plan, campaign.sha(output / 'plan.json'))
    assert result['status'] == expected
    with pytest.raises(FileExistsError):
        campaign.launch_branch(output, branch, plan, campaign.sha(output / 'plan.json'))


def test_sequential_failure_stops_before_next_episode_and_no_manifest(registered, monkeypatch):
    output, _ = registered
    attempted = []
    def launch_branch(output, branch, plan, plan_sha):
        attempted.append(branch['id'])
        return {'status': 'completed_later_episode' if len(attempted) == 1 else 'unknown_incomplete_episode'}
    monkeypatch.setattr(campaign, 'launch_branch', launch_branch)
    result = campaign.launch(output)
    assert attempted == ['guarded_default', 'diagnostic_prefer8']
    assert result['attempted_count'] == 2
    assert result['status'] == 'unknown_incomplete_campaign'
    assert not (output / 'episode_manifest.json').exists()
    with pytest.raises(FileExistsError):
        campaign.launch(output)


def test_all_three_successes_write_only_actual_receipt_manifest(registered, monkeypatch):
    output, _ = registered
    def launch_branch(output, branch, plan, plan_sha):
        path = output / branch['id'] / 'episode/native/receipt.json'
        campaign.write_new(path, {'status': 'assessed', 'run_acceptance_status': 'closed_run_acceptance_passed'})
        return {'status': 'completed_later_episode', 'native_receipt': campaign.reference(path)}
    monkeypatch.setattr(campaign, 'launch_branch', launch_branch)
    result = campaign.launch(output)
    manifest = campaign.read(output / 'episode_manifest.json')
    assert result['status'] == 'completed_later_campaign'
    assert manifest['schema'] == 'g31.foundation.later_episode_manifest.v1'
    assert len(manifest['episodes']) == 3
    assert manifest['independent_scene_count'] == 1
    assert all(campaign.sha(row['receipt_path']) == row['receipt_sha256'] for row in manifest['episodes'])


def test_plan_byte_change_cannot_pass_campaign_even_when_json_equivalent(registered, monkeypatch):
    output, _ = registered
    def launch_branch(output, branch, plan, plan_sha):
        if branch['id'] == 'guarded_default':
            with (output / 'plan.json').open('a') as stream:
                stream.write(' ')
        return {'status': 'unknown_incomplete_episode'}
    monkeypatch.setattr(campaign, 'launch_branch', launch_branch)
    result = campaign.launch(output)
    assert result['plan_bytes_unchanged'] is False
    assert result['status'] == 'unknown_incomplete_campaign'


def test_worker_refuses_wrong_plan_hash_before_native_import(registered):
    output, plan = registered
    branch = plan['branches'][0]['id']
    result = campaign.worker(output, branch, 'wrong-plan-hash')
    assert result['status'] == 'unknown_source_or_checkpoint_changed'
    assert result['native_execution_attempted'] is False


def test_prepare_evaluation_registers_checkpoint_and_only_one_fresh_episode(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    monkeypatch.setattr(campaign, 'source_pins', lambda: {})
    binary = tmp_path / 'native.pyd'
    binary.write_bytes(b'non-native-unit-fixture')
    contract = tmp_path / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    campaign.write_new(contract, {'binary': str(binary)})
    checkpoint = tmp_path / 'checkpoint.json'
    campaign.write_new(checkpoint, {'schema': 'g31.foundation.later_value_model.v1'})
    output = tmp_path / 'new_evaluation'
    plan = campaign.prepare(output, evaluate_checkpoint=checkpoint)
    assert plan['checkpoint'] == campaign.reference(checkpoint)
    assert plan['branches'] == [{'id': 'guarded_learned_value', 'mode': 'guarded', 'actions': None}]
    assert plan['hard_process_seconds'] == 150
    assert not (output / 'launch.json').exists()
    with pytest.raises(ValueError, match='fresh_output_required'):
        campaign.prepare(output, evaluate_checkpoint=checkpoint)
    checkpoint.write_text(json.dumps({'schema': 'changed'}))
    with pytest.raises(ValueError, match='checkpoint_changed'):
        campaign.check_pins(plan)


def test_prepare_only_registered_branch_keeps_exact_spec_and_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    monkeypatch.setattr(campaign, 'source_pins', lambda: {})
    binary = tmp_path / 'native.pyd'
    binary.write_bytes(b'non-native-unit-fixture')
    contract = tmp_path / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    campaign.write_new(contract, {'binary': str(binary)})
    plan = campaign.prepare(tmp_path / 'only_third', only_branch='diagnostic_absolute_return')
    assert plan['only_branch'] == 'diagnostic_absolute_return'
    assert plan['branches'] == [campaign.BRANCHES[2]]
    assert plan['hard_process_seconds'] == 150
    assert plan['automatic_retries'] == 0
    plan['branches'][0]['actions']['first_return'] = 'return_now'
    with pytest.raises(ValueError, match='fixed_episode_plan_required'):
        campaign.check_pins(plan)


def test_checkpoint_and_only_branch_cannot_be_combined(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='checkpoint_and_only_branch_are_exclusive'):
        campaign.prepare(tmp_path / 'invalid', evaluate_checkpoint=tmp_path / 'checkpoint.json',
                         only_branch='diagnostic_absolute_return')
    assert not (tmp_path / 'invalid').exists()
