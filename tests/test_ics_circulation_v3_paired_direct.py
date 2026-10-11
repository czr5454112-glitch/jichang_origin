from copy import deepcopy

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.nonlinear_learning import FULL_FEATURE_NAMES, MLPConfig, MLPValueModel


def rows():
    result = []
    for group in range(3):
        for action in range(3):
            features = dict.fromkeys(FULL_FEATURE_NAMES, 0.)
            features['edge_count'] = float(action)
            features['known_waiting_count'] = float(group)
            result.append({'source_group': f'g{group}', 'split': 'train', 'is_baseline': action == 0,
                           'features': features, 'cost_mean': group * 1000 + action * 2,
                           'delta_mean': action * 2., 'timed_delta': 0.})
    return result


def test_paired_direct_uses_same_architecture_loss_and_steps_as_zero_analytic_residual():
    data = rows()
    config = MLPConfig(seed=17, epochs=30)
    direct = MLPValueModel.fit(data, 'paired_direct', config)
    residual = MLPValueModel.fit(data, 'residual', config)
    assert direct.parameter_count == residual.parameter_count
    assert np.array_equal(direct.center, residual.center)
    for name in direct.parameters:
        assert np.array_equal(direct.parameters[name], residual.parameters[name])
    assert direct.training_metadata['prediction_in_loss'] == 'f(x)-f(group_baseline)'
    assert direct.training_metadata['target'] == 'delta_mean'
    assert direct.training_metadata['history'] == residual.training_metadata['history']


def test_absolute_group_cost_offsets_cannot_change_paired_model_and_roundtrip():
    data, shifted = rows(), rows()
    for row in shifted:
        row['cost_mean'] += 10**12
    config = MLPConfig(seed=29, epochs=20)
    model = MLPValueModel.fit(data, 'paired_direct', config)
    other = MLPValueModel.fit(shifted, 'paired_direct', config)
    assert model.to_dict() == other.to_dict()
    restored = MLPValueModel.from_dict(model.to_dict())
    baseline, action = data[0]['features'], data[2]['features']
    assert restored.score_features(action, baseline) == model.score_features(action, baseline)
    assert model.score_features(baseline, baseline) == 0
    assert model.parameters['b2'][0] == 0


def test_paired_training_rejects_invalid_baseline_and_nontraining_rows():
    data = rows()
    data[0]['delta_mean'] = 1
    with pytest.raises(ValueError, match='Baseline paired deltas'):
        MLPValueModel.fit(data, 'paired_direct')
    data = rows()
    data[0]['split'] = 'test'
    with pytest.raises(ValueError, match='Only training rows'):
        MLPValueModel.fit(data, 'paired_direct')
