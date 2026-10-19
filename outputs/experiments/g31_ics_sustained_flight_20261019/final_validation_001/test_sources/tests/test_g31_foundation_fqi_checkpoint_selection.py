"""Pure fixture regressions; no actual fit, native run, or held-out reads."""
import copy
import io
import json
from pathlib import Path
import sys

import pytest

from scripts.experiments.g31_ics_circulation import foundation_fqi_checkpoint_selection as selector


def observation(at):
    return {'owner': 'B', 'at': at, 'public_state': at, 'opportunity': {'id': 'opaque'}}


def candidate(action, identity='chosen'):
    return {'action_id': identity, 'semantic': action, 'enabled': True,
            'guard_status': 'original_fixed_rule', 'per_job_delta': None}


def row(source, decision, at, reward, action, *, next_row=None):
    return {'split': 'development', 'owner': 'B', 'peer_policy_id': 'fixed', 'source': {'sha256': source},
            'decision_id': decision, 'training_eligible': True, 'truncated': False, 'terminated': next_row is None,
            'gamma': 1., 'observation': observation(at), 'action': action, 'selected_action_id': 'chosen',
            'candidate_mask': [candidate(action)], 'reward': {'start': at, 'end': next_row['observation']['at'] if next_row else at+1, 'value': reward},
            'next_observation': None if next_row is None else next_row['observation'],
            'next_decision_id': None if next_row is None else next_row['decision_id'],
            'next_candidate_mask': [] if next_row is None else next_row['candidate_mask']}


def fixture():
    a, b, c = {'destination': 3}, {'destination': 8}, {'destination': None}
    terminal_a = row('one', 'two', 2, -2, a)
    terminal_b = row('other', 'two', 2, -5, b)
    start_a = row('one', 'one', 1, -1, c, next_row=terminal_a)
    start_b = row('other', 'one', 1, -1, c, next_row=terminal_b)
    mask = [candidate(a, 'a'), candidate(b, 'b')]
    terminal_a['candidate_mask'] = copy.deepcopy(mask); terminal_a['selected_action_id'] = 'a'
    terminal_b['candidate_mask'] = copy.deepcopy(mask); terminal_b['selected_action_id'] = 'b'
    start_a['next_candidate_mask'] = copy.deepcopy(mask)
    start_b['next_candidate_mask'] = copy.deepcopy(mask)
    return [start_a, terminal_a, start_b, terminal_b]


def graph(rows):
    return selector.supported_empirical_targets(rows, owner='B', peer_policy_id='fixed', gamma=1.)


def test_exact_supported_optimal_retains_original_row_weights():
    result = graph(fixture())
    assert [r['target_value'] for r in result['targets']] == [-3, -2, -3, -5]
    assert result['rows'] == 4 and result['unique_state_actions'] == 3
    assert result['global_optimality_claim'] is False


@pytest.mark.parametrize('field,value,error', [
    ('split', 'test', 'development_owner_peer_only'),
    ('owner', 'A', 'development_owner_peer_only'),
    ('peer_policy_id', 'changed', 'development_owner_peer_only'),
    ('truncated', True, 'closed_actual'),
    ('training_eligible', False, 'closed_actual'),
    ('gamma', .9, 'gamma_changed'),
    ('selected_action_id', 'unknown', 'chosen_not_legal')])
def test_invalid_transition_rejected(field, value, error):
    rows = fixture(); rows[0][field] = value
    with pytest.raises(ValueError, match=error): graph(rows)


def test_conflicting_same_state_action_reward_rejected():
    rows = fixture(); rows[2]['reward']['value'] = -4
    with pytest.raises(ValueError, match='nondeterministic'): graph(rows)


def test_missing_actual_successor_rejected():
    rows = fixture(); rows[0]['next_decision_id'] = 'missing'
    with pytest.raises(ValueError, match='actual_successor_missing'): graph(rows)


def test_successor_observation_not_equal_rejected():
    rows = fixture(); rows[0]['next_observation'] = observation(3)
    with pytest.raises(ValueError, match='actual_successor_not_bound'): graph(rows)


def test_zero_duration_self_loop_rejected():
    rows = fixture(); rows[0]['next_decision_id'] = 'one'; rows[0]['next_observation'] = rows[0]['observation']
    rows[0]['reward']['end'] = 1
    with pytest.raises(ValueError, match='actual_reward_clock'): graph(rows)


def test_candidate_unvisited_action_cannot_bootstrap():
    rows = fixture()
    for r in (rows[0], rows[2]): r['next_candidate_mask'] = [candidate({'destination': 99})]
    with pytest.raises(ValueError, match='actual_successor_candidate_mask_not_bound'): graph(rows)


def test_conflicting_legal_successor_support_rejected():
    rows = fixture(); rows[2]['next_candidate_mask'].pop(0); rows[3]['candidate_mask'].pop(0)
    with pytest.raises(ValueError, match='nondeterministic'): graph(rows)


@pytest.mark.parametrize('change', ['disabled', 'harmful', 'unknown'])
def test_chosen_must_be_currently_admissible(change):
    rows = fixture(); c = rows[0]['candidate_mask'][0]
    if change == 'disabled': c['enabled'] = False
    elif change == 'harmful': c.update(guard_status='passed', per_job_delta={'job': .1})
    else: c['guard_status'] = 'unknown'
    with pytest.raises(ValueError, match='chosen_not_legal'): graph(rows)


def test_semantic_alias_deduplicates_without_new_action():
    rows = fixture()
    rows[0]['next_candidate_mask'].append(candidate(rows[1]['action'], 'alias'))
    rows[1]['candidate_mask'].append(candidate(rows[1]['action'], 'alias'))
    result = graph(rows)
    assert result['targets'][0]['target_value'] == -3


def test_forged_next_masks_cannot_remove_actual_better_supported_action():
    rows = fixture()
    for row in (rows[0], rows[2]): row['next_candidate_mask'] = [candidate({'destination': 8}, 'b')]
    with pytest.raises(ValueError, match='actual_successor_candidate_mask_not_bound'): graph(rows)


def test_disabled_chosen_alias_not_enabled_by_other_alias():
    rows = fixture(); rows[0]['candidate_mask'][0]['enabled'] = False
    rows[0]['candidate_mask'].append(candidate(rows[0]['action'], 'enabled_alias'))
    with pytest.raises(ValueError, match='chosen_not_legal'): graph(rows)


def test_terminal_cannot_hide_successor():
    rows = fixture(); rows[0]['terminated'] = True
    with pytest.raises(ValueError, match='terminal_has_successor'): graph(rows)


def test_nonfinite_reward_rejected():
    rows = fixture(); rows[0]['reward']['value'] = float('nan')
    with pytest.raises(ValueError, match='finite_number'): graph(rows)


def test_duplicate_actual_decision_rejected():
    rows = fixture(); rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match='duplicate_actual'): graph(rows)


def test_duplicate_selected_candidate_identity_rejected():
    rows = fixture(); rows[0]['candidate_mask'].append(copy.deepcopy(rows[0]['candidate_mask'][0]))
    with pytest.raises(ValueError, match='unique_candidate_ids'): graph(rows)


def test_independent_forward_known_constant_and_nonfinite_rejection():
    names = [f'f{i:03d}' for i in range(123)]
    model = {'schema': 'g31.foundation.repeated_action_value.v1', 'native_execution_authority': False,
             'feature_names': names, 'parameters': {'center': [0.] * 123, 'scale': [1.] * 123,
             'target_scale': 2., 'target_center': -10., 'layers': [
                 {'weight': [[0.] * width for _ in range(out)], 'bias': [0.] * out}
                 for width, out in ((123, 64), (64, 64), (64, 1))]}}
    model['parameters']['layers'][-1]['bias'] = [.5]
    model['model_sha256'] = selector.digest(model)
    fn = lambda *_: {name: 1. for name in names}
    assert selector.forward(model, {}, {}, fn) == -9.
    model['parameters']['scale'][0] = 0.
    model['model_sha256'] = selector.digest({k:v for k,v in model.items() if k != 'model_sha256'})
    with pytest.raises(ValueError, match='positive_scale'): selector.forward(model, {}, {}, fn)


def test_checkpoint_complete_grid_and_exact_tie():
    values = [{'seed': s, 'iteration': i, 'development_supported_empirical_optimal_mse': 1.} for s in (17,29,43) for i in range(6)]
    assert [v['iteration'] for v in selector.choose(values, [17,29,43], list(range(6)))] == [0,0,0]
    values[4]['development_supported_empirical_optimal_mse'] = .5
    assert selector.choose(values, [17,29,43], list(range(6)))[0]['iteration'] == 4
    with pytest.raises(ValueError, match='missing_duplicate'): selector.choose(values[:-1], [17,29,43], list(range(6)))
    values[-1] = values[0]
    with pytest.raises(ValueError, match='missing_duplicate'): selector.choose(values, [17,29,43], list(range(6)))


def test_unapproved_feature_source_not_executed():
    with pytest.raises(ValueError, match='unapproved_feature_source'):
        selector.feature_function(b'raise RuntimeError("should not execute")')


def test_changed_model_fails_before_feature_extraction():
    def forbidden(*args): raise AssertionError('feature extraction must not happen')
    model = {'schema':'g31.foundation.repeated_action_value.v1','native_execution_authority':False,'model_sha256':'wrong'}
    with pytest.raises(ValueError, match='model_content_hash'): selector.forward(model, {}, {}, forbidden)


def test_admission_precedes_read(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['selector', '--plan', 'formal-test.json', '--output', 'never'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO('no\n'))
    monkeypatch.setattr(selector, 'read', lambda *a: pytest.fail('must not read before admission'))
    with pytest.raises(ValueError, match='bounded_parent_admission'): selector.main()


def test_plan_disallowed_split_rejected_before_collection_read(tmp_path):
    contract = {'checkpoint_selection': selector.OLD_CRITERION, 'train_parent_groups':['train'],
                'development_parent_groups':['dev'], 'evaluation_plan':{'held_out_parent_groups':['test']},
                'training_seeds':[17,29,43], 'iterations':5}
    directory = tmp_path/'training'; directory.mkdir()
    (directory/'receipt.json').write_text(json.dumps({'contract':contract}))
    (directory/'preregistered_plan.json').write_text(json.dumps({'episodes':[{'split':'test','parent_group':'test','directory':'must-not-read'}]}))
    addendum = {'schema':selector.ADDENDUM_SCHEMA,'criterion':selector.CRITERION,'prior_criterion':selector.OLD_CRITERION,
                'development_already_inspected':True,'formal_holdout_accessed':False,'selection_only':True,'fit_count':0,
                'native_branches':0,'maximum_revisions':1,'training_seeds':[17,29,43],'allowed_iterations':list(range(6)),
                'row_weighting':'original_development_rows_equal','collection_contract_sha256':selector.digest(contract),
                'training_receipt_sha256':selector.sha(directory/'receipt.json')}
    addendum_path=tmp_path/'addendum.json';addendum_path.write_text(json.dumps(addendum))
    registration_path=tmp_path/'registration.json'
    registration_path.write_text(json.dumps({'args':['--plan','irrelevant','--output',str(directory)],
                                            'assessment':{'path':str(directory/'receipt.json')}}))
    with pytest.raises(ValueError, match='training_plan_contains_nonallowed_split'):
        selector.make_plan(directory, registration_path, addendum_path)


def test_wrong_training_directory_rejected_before_any_result_read(monkeypatch, tmp_path):
    registration_path = tmp_path/'registration.json'
    legal = tmp_path/'training'; wrong = tmp_path/'formal-heldout'
    calls = []
    def only_registration(path):
        calls.append(Path(path))
        assert Path(path) == registration_path, 'must not read results before validating requested output'
        return {'args':['--plan','frozen-train-plan','--output',str(legal)],
                'assessment':{'path':str(legal/'receipt.json')}}
    monkeypatch.setattr(selector, 'read', only_registration)
    with pytest.raises(ValueError, match='training_attempt_directory_binding'):
        selector.make_plan(wrong, registration_path, tmp_path/'addendum.json')
    assert calls == [registration_path]


def test_source_imports_are_standard_library_only():
    import ast
    source = ast.parse(Path(selector.__file__).read_text())
    imports = {a.name.split('.')[0] for n in ast.walk(source) if isinstance(n, ast.Import) for a in n.names}
    assert imports <= {'argparse','ast','hashlib','json','math','sys','time'}

