"""Same-data objective comparison: ownership, complete folds and freeze gates."""
from copy import deepcopy

import pytest

from scripts.experiments.ics_circulation_v3 import run_shared_recovery as shared
from scripts.experiments.ics_circulation_v3.nonlinear_learning import FULL_FEATURE_NAMES, MLPConfig, PHYSICAL_FEATURE_NAMES


def corpus():
    r0 = []
    for stream in shared.STREAMS:
        for action in (0, 1):
            base = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
            base.update(remaining_route_ticks=float(action), timed_analytic_absolute=float(action))
            physical = {**dict.fromkeys(PHYSICAL_FEATURE_NAMES, 0.), **base}
            physical['prefix_completes_delivery'] = float(action)
            r0.append({'stream': stream, 'owner': None, 'source_group': stream + ':R0',
                       'normal_ordinal': action, 'is_baseline': action == 0, 'actual_action_key': str(action),
                       'features23': base, 'features31': physical, 'cost_mean': 3. - action,
                       'delta_mean': -float(action), 'timed_delta': float(action), 'source_node': 'S', 'role': 'origin'})
    held = shared.STREAMS[-1]
    by_owner = {owner: [dict(deepcopy(r), owner=owner, source_group=owner + ':' + r['stream'])
                       for r in r0 if r['stream'] != held] for owner in shared.fold_owners(held)}
    return r0, held, by_owner


def test_six_real_owners_share_identical_corpus_and_bounds_across_objectives():
    r0, held, by_owner = corpus()
    before = deepcopy(by_owner)
    training = shared.shared_training_rows(r0, by_owner, held)
    assert len(training) == 6 + 6 * 6
    assert by_owner == before
    assert {r['owner'] for r in training if r['owner'] is not None} == set(shared.fold_owners(held))
    fits = [shared.fit_shared_model(training, held, kind, seed,
            config=MLPConfig(epochs=2, learning_rate=.01, l2=.001, seed=seed))
            for kind in shared.KINDS for seed in shared.SEEDS]
    assert len({fold['training_rows_sha256'] for _, _, fold in fits}) == 1
    assert len({fold['training_bounds_sha256'] for _, _, fold in fits}) == 1
    assert all(fold['training_rows'] == 42 and fold['recovered_rows'] == 36 for _, _, fold in fits)
    assert all(len(fold['rows_by_original_owner']) == 7 for _, _, fold in fits)
    assert all(model.score_features(training[0]['features31'], training[0]['features31']) == 0. for model, _, _ in fits)


def test_held_out_labels_and_extreme_features_cannot_change_union_fit():
    r0, held, by_owner = corpus()
    changed = deepcopy(r0)
    for row in changed:
        if row['stream'] == held:
            row['cost_mean'] = -1e20
            row['delta_mean'] = 1e20
            row['features31']['remaining_route_ticks'] = 1e20
    left = shared.shared_training_rows(r0, by_owner, held)
    right = shared.shared_training_rows(changed, by_owner, held)
    assert left == right
    config = MLPConfig(epochs=2, seed=17)
    a, bounds_a, meta_a = shared.fit_shared_model(left, held, 'paired_direct', 17, config=config)
    b, bounds_b, meta_b = shared.fit_shared_model(right, held, 'paired_direct', 17, config=config)
    assert a.to_dict() == b.to_dict() and bounds_a == bounds_b and meta_a == meta_b


@pytest.mark.parametrize('error', ['missing_owner', 'extra_owner', 'wrong_owner', 'held_out_row', 'ordinal_duplicate', 'source_group_relabel'])
def test_incomplete_or_relabelled_owner_union_is_rejected(error):
    r0, held, by_owner = corpus()
    owners = list(by_owner)
    if error == 'missing_owner':
        by_owner.pop(owners[0])
    elif error == 'extra_owner':
        by_owner['foreign'] = []
    elif error == 'wrong_owner':
        by_owner[owners[0]][0]['owner'] = owners[1]
    elif error == 'held_out_row':
        by_owner[owners[0]][0]['stream'] = held
    elif error == 'ordinal_duplicate':
        by_owner[owners[0]].append(deepcopy(by_owner[owners[0]][0]))
    else:
        # Merely rewriting owner would make this look like a complete set;
        # retained checkpoint groups expose the relabeled duplicated owner.
        by_owner[owners[1]] = [dict(deepcopy(r), owner=owners[1]) for r in by_owner[owners[0]]]
    with pytest.raises(ValueError):
        shared.shared_training_rows(r0, by_owner, held)


def test_duplicate_feature_values_from_different_owner_trajectories_are_not_deduplicated():
    r0, held, by_owner = corpus()
    training = shared.shared_training_rows(r0, by_owner, held)
    groups = {r['source_group'] for r in training}
    assert len(groups) == 21
    assert len({tuple(r['features31'].items()) for r in training}) == 2
    assert len(training) == 42


def test_no_fit_or_output_is_allowed_before_original_R1_stage_is_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(shared.recovery, 'check_stage', lambda output, stage: (
        {'fits': 48, 'failures': []} if stage == 'r0' else (_ for _ in ()).throw(ValueError('Stage incomplete: r1'))))
    monkeypatch.setattr(shared.MLPValueModel, 'fit', lambda *args, **kwargs: pytest.fail('must not fit'))
    output = tmp_path / 'shared'
    with pytest.raises(ValueError, match='incomplete'):
        shared.run_fit(output, tmp_path / 'master')
    assert not output.exists()


def test_deployment_does_not_start_before_all_shared_models_are_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, 'check_shared_stage', lambda output, stage: {'fits': 23, 'failures': []})
    monkeypatch.setattr(shared.recovery, 'deployment', lambda *args, **kwargs: pytest.fail('must not deploy'))
    with pytest.raises(ValueError, match='24 shared models'):
        shared.run_evaluation(tmp_path)
    assert not (tmp_path / 'evaluation').exists()


def test_declared_supplement_has_fixed_24_models_288_episodes_and_no_new_labels():
    assert shared.PROTOCOL['fits'] == 4 * 2 * 3 == 24
    assert shared.PROTOCOL['deployment']['total_episodes'] == 4 * 9 * 8 == 288
    assert shared.PROTOCOL['deployment']['learned_episodes'] == 216
    assert shared.PROTOCOL['deployment']['control_episodes'] == 72
    assert shared.PROTOCOL['new_labels'] == 0
