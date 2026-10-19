"""Shared semantic candidate scores, trained offline without execution authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import statistics
import time

import numpy as np

from scripts.experiments.ics_circulation_v3.learning import RidgeValueModel
from . import foundation_learning_data as data


_MODELS = {}
MODEL_SCHEMA = 'g31.foundation.shared_candidate_ranker.v1'


def _training_rows(rows):
    converted = []
    for row in rows:
        target = row['labels']['cost_components']['delta_completion_sum_s']
        if row['labels']['evaluation_status'] != 'completed' or target is None:
            continue
        features = data.feature_vector(row['owner_observation'], row['candidate_semantics'])
        converted.append({'source_group': row['decision_id'], 'features': features,
            'is_baseline': row['candidate_index_for_join_only'] == 4,
            'cost_mean': data.number(target), 'delta_mean': data.number(target), 'timed_delta': 0.})
    data.require(bool(converted), 'no_known_training_labels')
    return converted


def _fit(rows, kind, version, seed, epochs, deadline):
    converted = _training_rows(rows)
    groups = sorted({row['source_group'] for row in rows})
    names = tuple(sorted(converted[0]['features']))
    started = time.perf_counter()
    payload = {'schema': MODEL_SCHEMA, 'model_version': version, 'kind': kind,
        'feature_schema': data.SCHEMA, 'feature_names': list(names), 'seed': seed,
        'trained_source_groups': groups, 'training_row_count': len(converted),
        'unknown_training_rows_excluded_from_loss': len(rows) - len(converted),
        'score_direction': 'higher_is_better_negative_predicted_delta', 'target': 'conditional_completion_sum_delta_vs04',
        'native_execution_authority': False, 'label_scope': 'causal_rollout_with_conditioned_peer_components',
        'uses_candidate_index_as_feature': False, 'validation_or_test_used_for_fit': False}
    if kind == 'linear':
        linear = RidgeValueModel.fit(converted, 'direct', alpha=1.)
        payload['parameters'] = linear.to_dict()
        predicted = [linear.predict_value(row['features']) for row in converted]
        payload['training_curve'] = [{'step': 1, 'mse': float(np.mean([(value - row['cost_mean']) ** 2
            for value, row in zip(predicted, converted, strict=True)]))}]
        payload['implementation'] = 'existing RidgeValueModel numerical fitter; no old simulator executed'
    elif kind == 'mlp':
        import torch
        torch.set_num_threads(1)
        torch.manual_seed(seed)
        matrix = np.asarray([[row['features'][name] for name in names] for row in converted], dtype=np.float64)
        target = np.asarray([row['cost_mean'] for row in converted], dtype=np.float64)
        center, scale = matrix.mean(axis=0), matrix.std(axis=0)
        scale[scale < 1e-9] = 1.
        target_center, target_scale = float(target.mean()), max(float(target.std()), 1e-9)
        inputs = torch.tensor((matrix - center) / scale, dtype=torch.float32)
        targets = torch.tensor((target - target_center) / target_scale, dtype=torch.float32).reshape(-1, 1)
        model = torch.nn.Sequential(torch.nn.Linear(len(names), 64), torch.nn.Tanh(),
            torch.nn.Linear(64, 64), torch.nn.Tanh(), torch.nn.Linear(64, 1))
        optimizer = torch.optim.Adam(model.parameters(), lr=.01, weight_decay=1e-4)
        curve = []
        for step in range(epochs + 1):
            data.require(time.perf_counter() <= deadline, 'training_wall_budget')
            prediction = model(inputs)
            loss = torch.mean((prediction - targets) ** 2)
            if step == 0 or step == epochs or step % 10 == 0:
                curve.append({'step': step, 'mse': float(loss.detach()) * target_scale ** 2})
            if step < epochs:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        payload['parameters'] = {'center': center.tolist(), 'scale': scale.tolist(),
            'target_center': target_center, 'target_scale': target_scale,
            'layers': [{'weight': layer.weight.detach().numpy().tolist(), 'bias': layer.bias.detach().numpy().tolist()}
                for layer in model if isinstance(layer, torch.nn.Linear)]}
        payload['training_curve'] = curve
        payload['implementation'] = 'torch CPU, two 64-unit tanh hidden layers; NumPy portable inference'
        payload['torch_version'] = torch.__version__
        payload['device'] = 'cpu'
        payload['torch_threads'] = 1
    else:
        raise ValueError('unknown_ranker_kind')
    payload['training_wall_seconds'] = time.perf_counter() - started
    data.require(time.perf_counter() <= deadline, 'training_wall_budget')
    return payload


def load_model(path):
    payload = json.loads(Path(path).read_bytes())
    data.require(payload.get('schema') == MODEL_SCHEMA and payload.get('feature_schema') == data.SCHEMA, 'model_schema')
    data.require(payload['kind'] in ('linear', 'mlp') and payload['score_direction'] == 'higher_is_better_negative_predicted_delta', 'model_kind')
    version = payload['model_version']
    data.require(version not in _MODELS or _MODELS[version] == payload, 'model_version_collision')
    _MODELS[version] = copy.deepcopy(payload)
    return version


def score_candidates(observation, candidates, model_version):
    if model_version not in _MODELS:
        model_version = load_model(model_version)
    payload = _MODELS[model_version]
    if not candidates:
        return []
    features = [data.feature_vector(observation, candidate) for candidate in candidates]
    names = payload['feature_names']
    data.require(all(set(row) == set(names) for row in features), 'model_feature_names')
    matrix = np.asarray([[row[name] for name in names] for row in features], dtype=np.float64)
    if payload['kind'] == 'linear':
        linear = RidgeValueModel.from_dict(payload['parameters'])
        predictions = np.asarray([linear.predict_value(row) for row in features])
    else:
        parameters = payload['parameters']
        center, scale = np.asarray(parameters['center']), np.asarray(parameters['scale'])
        data.require(center.shape == scale.shape == (len(names),) and np.isfinite(scale).all() and (scale > 0).all(), 'model_normalization')
        activation = (matrix - center) / scale
        for index, layer in enumerate(parameters['layers']):
            activation = activation @ np.asarray(layer['weight']).T + np.asarray(layer['bias'])
            if index < len(parameters['layers']) - 1:
                activation = np.tanh(activation)
        predictions = activation.reshape(-1) * parameters['target_scale'] + parameters['target_center']
    data.require(predictions.shape == (len(candidates),) and np.isfinite(predictions).all(), 'finite_scores')
    return (-predictions).tolist()


def rule_scores(observation, candidates):
    values = [data.candidate_features(observation, candidate) for candidate in candidates]
    return [-(row['candidate_empty_departure_delay_s'] + row['candidate_return_delay_s']
        + row['candidate_initial_prefer_2'] + row['candidate_later_prefer_8']) for row in values]


def evaluate_group(rows, scores, budget):
    data.require(len(rows) == len(scores) and 1 <= budget <= len(rows), 'evaluation_budget')
    baseline = next(index for index, row in enumerate(rows) if row['candidate_index_for_join_only'] == 4)
    ranked = sorted(range(len(rows)), key=lambda index: (-scores[index], index))
    retained = [baseline] + [index for index in ranked if index != baseline][:budget - 1]
    protected = [index for index, row in enumerate(rows) if row['labels']['conditional_protection_status'] == 'passed'
        and row['labels']['cost_components']['delta_completion_sum_s'] is not None]
    values = {index: rows[index]['labels']['cost_components']['delta_completion_sum_s'] for index in protected}
    optimal = min(values.values()) if values else None
    admissible = [index for index in retained if index in values]
    chosen = min(admissible, key=lambda index: (values[index], index)) if admissible else None
    return {'decision_id': rows[0]['decision_id'], 'budget_including_baseline': budget,
        'retained_candidate_indices': [rows[index]['candidate_index_for_join_only'] for index in retained],
        'retained_count': len(retained), 'conditional_optimal_cost_delta': optimal,
        'conditional_optimal_retained': any(values.get(index) == optimal for index in retained) if optimal is not None else None,
        'conditional_protected_regret_s': values[chosen] - optimal if chosen is not None else None,
        'conditional_selected_index': rows[chosen]['candidate_index_for_join_only'] if chosen is not None else None,
        'raw_top1_conditional_protection': rows[ranked[0]]['labels']['conditional_protection_status'],
        'native_protection_status': 'unknown', 'native_or_rollout_executions': 0,
        'measured_evaluation_savings': False,
        'scope': 'Saved-table top-K proxy only; protected selection uses causal teacher labels, not actor inputs or execution authority.'}


def _evaluate(rows, payloads):
    results = []
    for fold in payloads:
        held_out = [row for row in rows if row['source_group'] == fold['held_out_group']]
        data.require(not set(fold['training_groups']) & {row['source_group'] for row in held_out}, 'group_split_leakage')
        for decision in sorted({row['decision_id'] for row in held_out}):
            group = sorted([row for row in held_out if row['decision_id'] == decision], key=lambda row: row['candidate_index_for_join_only'])
            observation = group[0]['owner_observation']
            candidates = [row['candidate_semantics'] for row in group]
            for kind, path in [('rule', None)] + list(fold['models'].items()):
                started = time.perf_counter()
                scores = rule_scores(observation, candidates) if kind == 'rule' else score_candidates(observation, candidates, load_model(path))
                score_ms = (time.perf_counter() - started) * 1000.
                for budget in (4, 8):
                    result = evaluate_group(group, scores, budget)
                    results.append({**result, 'kind': kind, 'held_out_group': fold['held_out_group'],
                        'score_call_wall_ms_including_features': score_ms, 'scoring_device': 'cpu'})
    summary = {}
    for kind in ('rule', 'linear', 'mlp'):
        for budget in (4, 8):
            selected = [row for row in results if row['kind'] == kind and row['budget_including_baseline'] == budget]
            regrets = [row['conditional_protected_regret_s'] for row in selected if row['conditional_protected_regret_s'] is not None]
            summary[kind + '_K' + str(budget)] = {'owner_decision_count': len(selected),
                'scenario_group_count': len({row['held_out_group'] for row in selected}),
                'known_conditional_optimum_count': sum(row['conditional_optimal_retained'] is not None for row in selected),
                'optimal_retention_rate': statistics.mean(float(row['conditional_optimal_retained']) for row in selected
                    if row['conditional_optimal_retained'] is not None) if any(row['conditional_optimal_retained'] is not None for row in selected) else None,
                'mean_conditional_regret_s': statistics.mean(regrets) if regrets else None,
                'max_conditional_regret_s': max(regrets) if regrets else None,
                'raw_top1_not_conditionally_protected_count': sum(row['raw_top1_conditional_protection'] != 'passed' for row in selected)}
    return {'summary': summary, 'holdout_results': results,
        'generalization_established': False, 'native_execution_authorized': False,
        'scope': 'Leave-one-of-three-saved-scenarios-out L0 smoke; not independent airport generalization or RL.',
        'compute_savings_measured': False, 'complete_request_100ms_certified': False}


def train_rankers(dataset_path, output_dir, *, seed=17, epochs=80, max_wall_seconds=120):
    started = time.perf_counter()
    data.require(type(epochs) is int and 1 <= epochs <= 1000 and 0 < max_wall_seconds <= 7200, 'training_budget')
    output_dir = Path(output_dir).resolve()
    data.require(not output_dir.exists(), 'immutable_model_output')
    rows = data.read_dataset(dataset_path)
    groups = sorted({row['source_group'] for row in rows})
    data.require(len(groups) >= 3, 'group_holdout_requires_three_groups')
    output_dir.mkdir(parents=True)
    registration = {'seed': seed, 'epochs': epochs, 'max_wall_seconds': max_wall_seconds,
        'row_budget': 20000, 'dataset_path': str(Path(dataset_path).resolve()), 'dataset_sha256': data.file_sha(dataset_path),
        'source_groups': groups, 'validation_tuning': False, 'split': 'leave_one_source_group_out',
        'gpu_used': False, 'cpu_threads': 1, 'fixed_hyperparameters': {'ridge_alpha': 1., 'mlp_hidden': [64, 64], 'mlp_lr': .01}}
    run_identity = data.digest({'output_dir': str(output_dir), 'registration': registration})[:16]
    data.write(output_dir / 'registration.json', registration)
    folds = []
    for held_out in groups:
        training = [row for row in rows if row['source_group'] != held_out]
        fold = {'held_out_group': held_out, 'training_groups': [group for group in groups if group != held_out], 'models': {}}
        for kind in ('linear', 'mlp'):
            version = 'foundation_l0_' + kind + '_holdout_' + held_out + '_' + run_identity
            model = _fit(training, kind, version, seed, epochs, started + max_wall_seconds)
            path = output_dir / (kind + '_holdout_' + held_out + '.json')
            data.write(path, model)
            fold['models'][kind] = str(path)
        folds.append(fold)
    data.write(output_dir / 'folds.json', folds)
    evaluation = _evaluate(rows, folds)
    final_models = {}
    for kind in ('linear', 'mlp'):
        payload = _fit(rows, kind, 'foundation_l0_' + kind + '_all_smoke_' + run_identity,
            seed, epochs, started + max_wall_seconds)
        payload['holdout_evaluation_model'] = False
        payload['deployment_scope'] = 'Offline pre-rollout ranking integration smoke only; no native authorization.'
        path = output_dir / (kind + '_all_smoke.json')
        data.write(path, payload)
        final_models[kind] = str(path)
    report = {**evaluation, 'schema': 'g31.foundation.l0.rank_training.v1', 'candidate_rows': len(rows),
        'independent_source_groups': len(groups), 'owner_decision_groups': len({row['decision_id'] for row in rows}),
        'fold_models': folds, 'integration_models': final_models, 'actual_training_wall_seconds': time.perf_counter() - started,
        'native_or_causal_rollout_calls': 0, 'training_device': 'cpu', 'gpu_used': False,
        'source_module_sha256': data.file_sha(__file__), 'dataset_sha256': registration['dataset_sha256']}
    data.write(output_dir / 'training_report.json', report)
    return report


def evaluate_models(dataset_path, model_dir):
    model_dir = Path(model_dir)
    registration = json.loads((model_dir / 'registration.json').read_bytes())
    data.require(data.file_sha(dataset_path) == registration['dataset_sha256'], 'frozen_evaluation_dataset')
    return _evaluate(data.read_dataset(dataset_path), json.loads((model_dir / 'folds.json').read_bytes()))
