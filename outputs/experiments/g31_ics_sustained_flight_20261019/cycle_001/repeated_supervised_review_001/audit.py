"""Read-only checkpoint audit; standard-library forward pass, no fit/native."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def near(actual, expected, tolerance=1e-10):
    assert math.isfinite(actual) and math.isfinite(expected)
    assert abs(actual - expected) <= tolerance * max(1., abs(expected)), (actual, expected)


def forward(model, vector):
    parameters = model['parameters']
    x = [(vector[name] - center) / scale for name, center, scale in zip(model['feature_names'],
        parameters['center'], parameters['scale'], strict=True)]
    for index, layer in enumerate(parameters['layers']):
        x = [math.fsum(a * b for a, b in zip(x, weights, strict=True)) + bias
            for weights, bias in zip(layer['weight'], layer['bias'], strict=True)]
        if index < 2:
            x = [math.tanh(item) for item in x]
    return x[0] * parameters['target_scale'] + parameters['target_center']


def main():
    output = Path(__file__).resolve().parent
    cycle = output.parent
    directory = cycle / 'repeated_supervised_training_001'
    receipt, plan, evaluation, rows = (read(directory / name) for name in (
        'receipt.json', 'registered_plan.json', 'evaluation.json', 'conditional_supervision_rows.json'))
    assert receipt['status'] == 'completed_supervised_conditional_pretraining'
    assert receipt['plan_sha256'] == digest(plan) and plan == read(cycle / 'repeated_supervised_plan_001.json')
    assert receipt['native_executed'] is receipt['reinforcement_learning_performed'] is receipt['formal_test_read'] is False
    assert all(sha(directory / name) == expected for name, expected in receipt['artifacts'].items())
    assert all(sha(path) == expected for path, expected in receipt['source_sha256_pins'].items())
    manifest_task = read(cycle / 'manifest.json')['tasks']['repeated_supervised_training_001']
    attempt = Path(manifest_task['attempt']['output'])
    parent = read(attempt / 'receipt.json')
    registration = read(attempt / 'registration.json')
    assert manifest_task['status'] == parent['status'] == 'completed' and parent['source_changed'] == []
    assert parent['process']['exitcode'] == 0 and parent['process']['status'] == 'exited'
    assert parent['process']['windows_job_kill_on_close'] and parent['process']['child_released_only_after_job_assignment']
    assert parent['process']['hard_timeout_seconds'] == 180 and receipt['wall_seconds'] < 180
    assert all(sha(path) == expected for path, expected in registration['source_pins'].items())
    for index, (path, expected) in enumerate(registration['source_pins'].items()):
        assert sha(attempt / 'source' / (f'{index:04d}' + Path(path).suffix)) == expected
    # Reuse only the pinned public-observation feature extractor. Inference,
    # normalization, target construction and metric arithmetic are independent.
    from scripts.experiments.g31_ics_circulation import foundation_repeated_value as value
    vectors = [value.features(row['observation'], row['action']) for row in rows]
    training = [(row, vector) for row, vector in zip(rows, vectors, strict=True) if row['split'] == 'train']
    development = [(row, vector) for row, vector in zip(rows, vectors, strict=True) if row['split'] == 'development']
    assert len(training) == 6 and len(development) == 9
    assert {row['parent_group'] for row, _ in training} == {'three_reuse_blocker_11_1'}
    assert {row['parent_group'] for row, _ in development} == {'four_reuse_blocker_12_5'}
    for row in rows:
        assert row['actual_native_return_label'] is row['eligible_for_TD'] is row['native_execution_authority'] is False
        near(row['target_value'], -math.fsum(max(0., completed - row['observation']['at'])
            for completed in row['conditional_completion'].values()))
    summaries = []
    for declared in evaluation['seeds']:
        seed = declared['seed']
        checkpoint = directory / ('model_seed_' + str(seed) + '.json')
        model = read(checkpoint)
        assert model['model_sha256'] == declared['model_sha256'] == digest({key: item for key, item in model.items() if key != 'model_sha256'})
        assert model['seed'] == seed and model['epochs'] == 200 and model['cpu_threads'] == 1 and model['device'] == 'cpu'
        assert model['training_rows_sha256'] == digest([row for row, _ in training])
        assert model['native_execution_authority'] is model['td_readiness_certified_by_this_module'] is False
        names, params, curve = model['feature_names'], model['parameters'], model['training_curve']
        assert len(names) == 123 and names == sorted(vectors[0])
        assert [point['epoch'] for point in curve] == list(range(0, 201, 10))
        assert all(math.isfinite(point['mse']) and point['mse'] >= 0 for point in curve)
        assert curve[-1]['mse'] < curve[0]['mse']
        near(curve[-1]['mse'], declared['final_training_mse'])
        for index, name in enumerate(names):
            center = math.fsum(vector[name] for _, vector in training) / len(training)
            scale = math.sqrt(math.fsum((vector[name] - center) ** 2 for _, vector in training) / len(training))
            near(params['center'][index], center)
            near(params['scale'][index], 1. if scale < 1e-9 else scale)
        target_center = math.fsum(row['target_value'] for row, _ in training) / len(training)
        target_scale = max(1., math.sqrt(math.fsum((row['target_value'] - target_center) ** 2 for row, _ in training) / len(training)))
        near(params['target_center'], target_center)
        near(params['target_scale'], target_scale)
        count, previous = 0, 123
        for layer, width in zip(params['layers'], (64, 64, 1), strict=True):
            assert len(layer['weight']) == len(layer['bias']) == width
            assert all(len(weights) == previous for weights in layer['weight'])
            scalars = layer['bias'] + [number for weights in layer['weight'] for number in weights]
            assert all(math.isfinite(number) for number in scalars)
            count += len(scalars)
            previous = width
        assert count == 12161
        result = {'seed': seed, 'file_sha256': sha(checkpoint), 'model_content_sha256': model['model_sha256'],
            'parameter_count': count, 'initial_curve_mse': curve[0]['mse'], 'final_curve_mse': curve[-1]['mse']}
        for split, pairs in (('training', training), ('development', development)):
            predictions = [forward(model, vector) for _, vector in pairs]
            for actual, reported in zip(predictions, declared[split]['predictions'], strict=True):
                near(actual, reported)
            errors = [prediction - row['target_value'] for prediction, (row, _) in zip(predictions, pairs, strict=True)]
            mae = math.fsum(abs(error) for error in errors) / len(errors)
            rmse = math.sqrt(math.fsum(error ** 2 for error in errors) / len(errors))
            near(mae, declared[split]['MAE_to_conditional_teacher'])
            near(rmse, declared[split]['RMSE_to_conditional_teacher'])
            assert declared[split]['guard_admissible_teacher_differentiated_decisions'] == 0
            assert declared[split]['differentiated_teacher_best_match_fraction'] is None
            decisions = {}
            for prediction, (row, _) in zip(predictions, pairs, strict=True):
                if row['admissible_under_current_guard']:
                    decisions.setdefault(row['source_decision_id'], []).append((row, prediction))
            chosen = []
            for group in decisions.values():
                assert len(group) == 2
                assert len({row['target_value'] for row, _ in group}) == 1
                selected = max(group, key=lambda item: (item[1], item[0]['action_id']))[0]
                chosen.append({'at': selected['observation']['at'], 'action_id': selected['action_id']})
            result[split] = {'MAE': mae, 'RMSE': rmse, 'all_tied_admissible_decisions': len(decisions),
                'offline_model_ranking_only': chosen}
        summaries.append(result)
    assert [row['seed'] for row in summaries] == plan['protocol']['seeds'] == [1701, 1702, 1703]
    assert plan['protocol']['deployment_seed_if_needed'] == 1701
    assert len({read(directory / ('model_seed_' + str(seed) + '.json'))['parameters']['layers'][0]['weight'][0][0]
        for seed in (1701, 1702, 1703)}) == 3
    report = {'schema': 'g31.foundation.repeated_supervised_checkpoint_audit.v1', 'status': 'passed',
        'audit_script_sha256': sha(__file__), 'training_receipt_sha256': sha(directory / 'receipt.json'),
        'parent_receipt_sha256': sha(attempt / 'receipt.json'), 'source_and_archive_pin_count': len(registration['source_pins']),
        'feature_extractor_reused': str(Path(value.__file__).resolve()), 'forward_pass': 'independent_standard_library',
        'native_executed': False, 'fits_performed': 0, 'formal_test_read': False,
        'predeclared_deployment_seed': 1701, 'training_wall_seconds': receipt['wall_seconds'],
        'parent_wall_seconds': parent['process']['wall_seconds'], 'seeds': summaries,
        'conclusion': 'checkpoints_and_reported_metrics_verified; development_error_large; no_differentiated_safe_choice_or_RL_evidence'}
    with (output / 'report.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'seeds': 3, 'fits_performed': 0, 'formal_test_read': False}))


if __name__ == '__main__':
    main()
