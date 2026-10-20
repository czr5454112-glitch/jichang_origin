"""Read-only replay of the two saved native callbacks, never a native run.

Run from the repository root. Historical pins are verified, never rewritten.
The ordinary provenance consumer must reject those weights on changed source.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_action_value as value
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_consumer as consumer
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_training as training
from scripts.experiments.g31_ics_circulation import foundation_airport_learning_public as public
from scripts.experiments.g31_ics_circulation import foundation_airport_learning_audit as projection
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster_arrays as arrays

OUT = Path(__file__).resolve().parent
HISTORICAL = ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/B2_live_behavior_shadow_003'
TOLERANCE = {'rtol': 1e-12, 'atol': 1e-9}


def encoded(row):
    return json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def file_ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(name, row):
    path = OUT / name
    path.write_bytes(encoded(row) + b'\n')
    return file_ref(path)


def bound(ref):
    data = Path(ref['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == ref['sha256']
    return json.loads(data)


def historical_module(plan, filename, name):
    source = next(key for key in plan['source_archive'] if Path(key).name == filename)
    archive = HISTORICAL / plan['source_archive'][source]
    assert file_ref(archive)['sha256'] == plan['source_sha256'][source]
    spec = importlib.util.spec_from_file_location('scripts.experiments.g31_ics_circulation.' + name, archive)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, archive


def extract_callbacks(sequences):
    reference_path = HISTORICAL / 'C00/policy_observations.jsonl.gz'
    blobs_path = HISTORICAL / 'C00/policy_observations.blobs.jsonl.gz'
    receipt = json.loads((HISTORICAL / 'C00/policy_observation_receipt.json').read_bytes())
    assert file_ref(reference_path)['sha256'] == receipt['artifact']['sha256']
    assert file_ref(blobs_path)['sha256'] == receipt['blobs']['sha256']
    references = []
    with gzip.open(reference_path, 'rt', encoding='utf8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['sequence'] in sequences:
                references.append(row)
    needed = set()
    def collect(ref):
        if ref['kind'] == 'object':
            for field in ref['fields'].values():
                collect(field)
        elif ref['kind'] == 'list':
            needed.update(ref['chunks'])
        elif ref['kind'] == 'value':
            needed.add(ref['sha256'])
    for row in references:
        for field in ('observation', 'policy_options', 'decision'):
            collect(row[field])
    blobs = {}
    with gzip.open(blobs_path, 'rt', encoding='utf8') as stream:
        for line in stream:
            blob = json.loads(line)
            if blob['sha256'] in needed:
                actual = hashlib.sha256(json.dumps(blob['value'], separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                assert actual == blob['sha256'] and actual not in blobs
                blobs[actual] = blob['value']
    assert set(blobs) == needed
    def unpack(ref):
        if ref['kind'] == 'inline':
            return ref['value']
        if ref['kind'] == 'value':
            return copy.deepcopy(blobs[ref['sha256']])
        if ref['kind'] == 'list':
            result = [copy.deepcopy(item) for key in ref['chunks'] for item in blobs[key]]
            assert len(result) == ref['length']
            return result
        if ref['kind'] == 'object':
            return {key: unpack(item) for key, item in ref['fields'].items()}
        raise ValueError('unknown reference kind')
    for row in references:
        for field in ('observation', 'policy_options', 'decision'):
            row[field] = unpack(row[field])
    assert {row['sequence'] for row in references} == sequences
    return references, [file_ref(reference_path), file_ref(blobs_path)]


def main():
    plan = json.loads((HISTORICAL / 'plan.json').read_bytes())
    receipt = json.loads((HISTORICAL / 'C00/behavior_shadow_receipt.json').read_bytes())
    saved = {row['actual_sequence']: row['scorer'] for row in receipt['results']}
    old_value, old_value_path = historical_module(plan, 'foundation_action_value.py', 'historical_prepared_value')
    old_public, old_public_path = historical_module(plan, 'foundation_airport_learning_public.py', 'historical_prepared_public')
    records, raw_inputs = extract_callbacks(set(saved))
    resources = plan['behavior_shadow']
    descriptors = bound(resources['model_manifest'])['model_descriptors']
    context = bound(resources['flight_context'])
    forecast_checkpoint = bound(resources['forecast_checkpoint'])
    mapping = bound(plan['mapping'])
    models = []
    for descriptor in descriptors:
        model = bound(descriptor)
        training_receipt = bound(descriptor['training_receipt'])
        training_plan = bound(training_receipt['plan'])
        original_source = next(key for key in training_plan['source_sha256'] if Path(key).name == 'foundation_action_value.py')
        assert training_plan['source_sha256'][original_source] == file_ref(old_value_path)['sha256']
        matching = [row for row in training_receipt['models']
            if row['checkpoint'] == {'path': descriptor['path'], 'sha256': descriptor['sha256']}]
        assert len(matching) == 1 and matching[0]['content_sha256'] == value.digest(model)
        models.append(model)
    prepared_models = [value.prepare_model(model) for model in models]
    results = []
    for original in records:
        previous = saved[original['sequence']]
        assert value.digest(original) == previous['callback_record_sha256']
        count = len(original['decision']['intents'])
        input_ref = write(f'callback_{count}_complete_input.json', original)
        adapted, normalization = training.normalize_callback(original)
        public_context = copy.deepcopy(context)
        public_context['owner_scope'] = original['owner_id']
        forecast_start = time.perf_counter()
        regional = arrays.predict(public_context, forecast_checkpoint, now=original['now'],
            owner=original['owner_id'], observed_counts=None)
        mapped = projection.project(regional, mapping)
        forecast_seconds = time.perf_counter() - forecast_start
        assert value.digest(regional) == previous['regional_forecast_sha256']
        assert value.digest(mapped) == previous['mapped_forecast_sha256']
        kwargs = dict(episode_id=previous['episode_id'], episode_end=59400.)
        old_start = time.perf_counter()
        wrapped, audit = old_public.wrap_record(adapted, mapped, **kwargs)
        candidates = old_public.proposal_actions(adapted)
        actions = [candidate['semantic'] for candidate in candidates]
        old_features = [old_value.features(wrapped, action) for action in actions]
        old_scores = [old_value.predict(model, [wrapped] * len(actions), actions) for model in models]
        old_seconds = time.perf_counter() - old_start
        new_start = time.perf_counter()
        prepared, new_audit, new_candidates = public.prepare_record(adapted, mapped, **kwargs)
        matrix = value.prepare_feature_matrix(prepared, actions)
        new_scores = [value.predict_prepared(model, matrix, context=prepared) for model in prepared_models]
        new_features = matrix.feature_rows()
        new_seconds = time.perf_counter() - new_start
        assert prepared.to_observation() == wrapped
        assert value.digest(wrapped) == previous['model_observation_sha256']
        assert new_audit == audit and new_candidates == candidates
        assert encoded(new_features) == encoded(old_features) == encoded(previous['features'])
        assert all(np.allclose(a, b, **TOLERANCE) for a, b in zip(old_scores, new_scores, strict=True))
        assert all(np.allclose(a, b['scores'], **TOLERANCE) for a, b in zip(new_scores, previous['models'], strict=True))
        try:
            consumer.validate_behavior_checkpoint(wrapped, descriptors[0])
        except ValueError as error:
            source_gate = str(error)
            assert 'fixed_trained_feature_and_numerical_implementation' in source_gate
        else:
            raise AssertionError('Changed source must not silently accept historical weights')
        storage_start = time.perf_counter()
        detail_ref = write(f'callback_{count}_feature_and_score_comparison.json', {
            'features': new_features, 'features_sha256': value.digest(new_features),
            'historical_scores': old_scores, 'prepared_scores': new_scores,
            'saved_native_scores': [row['scores'] for row in previous['models']]})
        storage_seconds = time.perf_counter() - storage_start
        results.append({'sequence': original['sequence'], 'now': original['now'], 'candidate_count': count,
            'full_input': input_ref, 'detail': detail_ref,
            'feature_fields_equal': True, 'canonical_feature_bytes_equal': True,
            'historical_native_saved_features_equal': True, 'forward_tolerance': TOLERANCE,
            'maximum_forward_absolute_difference': float(np.max(np.abs(np.array(old_scores) - np.array(new_scores)))),
            'source_gate_retained': source_gate, 'current_context_build_count': 1, 'feature_matrix_build_count': 1,
            'historical_adapter_features_and_three_forwards_seconds': old_seconds,
            'prepared_adapter_features_and_three_forwards_seconds': new_seconds,
            'B1_and_mapping_replay_seconds': forecast_seconds, 'comparison_storage_seconds': storage_seconds,
            'timing_scope': 'detached saved-input replay; no native/controller/callback-capture measurement',
            'new_native_large_candidate_callback_verified': False, 'deployment_latency_certified': False})
    report = {'schema': 'g31.prepared_features_historical_equivalence.v1', 'status': 'passed',
        'raw_inputs': raw_inputs, 'historical_sources': [file_ref(old_value_path), file_ref(old_public_path)],
        'current_sources': [file_ref(module.__file__) for module in (value, consumer, public)],
        'models': descriptors, 'new_training_jobs': 0, 'new_native_jobs': 0,
        'historical_source_pins_modified': False, 'callback_results': results,
        'limits': ['Feature/forward replay equivalence is not model provenance rebinding.',
                   'Native callback including storage must be measured separately on a new actual session.',
                   'Historical behavior weights are not certified for the repaired circulation domain.']}
    write('equivalence_receipt.json', report)
    print(json.dumps({'status': 'passed', 'receipt': str(OUT / 'equivalence_receipt.json'),
        'callbacks': [{key: row[key] for key in ('candidate_count', 'maximum_forward_absolute_difference',
            'historical_adapter_features_and_three_forwards_seconds',
            'prepared_adapter_features_and_three_forwards_seconds')} for row in results]}, indent=2))


if __name__ == '__main__':
    main()
