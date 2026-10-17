"""Read-only, standard-library checks for the relocated G31 L0 evidence bundle."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


L0 = Path('outputs/experiments/g31_ics_foundation_learning_20261017/l0_002')
OLD = Path('outputs/experiments/g31_ics_lt2_sustained_20261014/compatible_initial_native_20261017_004')
CASES = ('mechanism', 'no_overlap', 'insufficient_advance')
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
OWNER_FIELDS = {'A': ('initial_action', 'return_delay'), 'B': ('empty_departure', 'later_action')}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def known(completion):
    return type(completion) is dict and set(completion) == set(JOBS) and all(
        finite(value) and value >= 0 for value in completion.values())


def path_mapper(root, manifest):
    suffix = (L0 / 'collect/decision_rows.jsonl').as_posix()
    saved = manifest['dataset_path'].replace('\\', '/')
    require(saved.endswith('/' + suffix), 'unexpected_original_dataset_path')
    original_prefix = saved[:-len(suffix)]

    def mapped(value):
        normalized = str(value).replace('\\', '/')
        require(normalized.startswith(original_prefix), 'reference_outside_original_root:' + normalized)
        relative = normalized[len(original_prefix):]
        require(relative and all(part not in ('', '.', '..') for part in relative.split('/')),
            'unsafe_relative_reference')
        target = (root / relative).resolve()
        require(target.is_relative_to(root), 'reference_escapes_bundle_root')
        return target

    return mapped


def check_observation(public, owner):
    require(type(public) is dict and set(public) == {'command', 'own_request', 'received', 'view'}, 'observation_schema')
    view = public['view']
    now = view['now']
    require(view['owner_id'] == owner and finite(now), 'owner_or_time')
    require(all(finite(job['arrival']) and job['arrival'] <= now for job in view['jobs']), 'future_local_job')
    require(all(not any(field in node for field in ('occupancy', 'actual_available'))
        for node in view['node_contracts'] if node['resource_owner'] != owner), 'undelivered_private_peer_node')
    require(len(public['received']) <= 1, 'initial_capture_scope')
    for message in public['received']:
        capture = message['capture']
        require(message['kind'] == 'planning_snapshot' and capture['source_owner'] != owner
            and capture['target_owner'] == owner, 'delivered_peer_scope')
        require(finite(capture['captured_at']) and finite(message['delivered_at'])
            and capture['captured_at'] <= message['delivered_at'] <= now, 'future_message')
        require(capture['coverage']['future_arrivals_included'] is False, 'future_arrival_coverage')
        require(all(finite(job['arrival']) and job['arrival'] <= capture['captured_at']
            for job in capture['jobs']), 'future_peer_job')


def check_rows(root, rows, manifest, mapped):
    require(len(rows) == 192 and manifest['candidate_rows'] == 192, 'expected_192_candidate_rows')
    expected_sources = {root / OLD / case / 'incumbent.raw.json.gz' for case in CASES}
    actual_sources = {mapped(value) for value in manifest['source_raw_sha256']}
    require(actual_sources == expected_sources, 'expected_three_original_incumbent_raws')
    source_reports = []
    for saved_path, expected_sha in manifest['source_raw_sha256'].items():
        path = mapped(saved_path)
        require(sha(path) == expected_sha, 'raw_hash:' + str(path))
        raw = json.loads(gzip.decompress(path.read_bytes()))
        require(raw['summary']['status'] == 'assessed', 'source_not_assessed')
        matrix = read(root / OLD / 'execution_matrix.json')
        case = path.parent.name
        cell = matrix[case + '/incumbent']
        require(cell['status'] == 'assessed' and cell['process']['status'] == 'exited'
            and cell['process']['exitcode'] == 0 and cell['raw_artifact']['sha256'] == expected_sha,
            'source_execution_not_closed')
        selected = [row for row in rows if row['source']['path'] == saved_path]
        require(len(selected) == 64 and Counter(row['owner_id'] for row in selected) == {'A': 32, 'B': 32},
            'source_owner_candidate_counts')
        for owner in ('A', 'B'):
            initial = raw['initial_owners'][owner]
            public = initial['collection']['public']
            check_observation(public, owner)
            provider = initial['selection']['provider_evidence']
            public_sha = canonical_sha(public)
            require(initial['collection']['public_sha256'] == provider['initial_public_sha256'] == public_sha
                and provider['owner'] == owner, 'public_or_provider_origin_hash')
            candidates = {item['candidate_index']: item for item in provider['rows']}
            require(len(provider['rows']) == 32 and set(candidates) == set(range(32)), 'original_full32_domain')
            reference = candidates[4]
            reference_known = reference['status'] == 'conditional_forecast' and known(reference.get('completion'))
            reference_cost = sum(reference['completion'].values()) if reference_known else None
            owner_rows = [row for row in selected if row['owner_id'] == owner]
            require({row['candidate_index_for_join_only'] for row in owner_rows} == set(range(32)), 'export_full32_domain')
            for row in owner_rows:
                index = row['candidate_index_for_join_only']
                candidate = candidates[index]
                complete = candidate['status'] == 'conditional_forecast' and known(candidate.get('completion'))
                completion = candidate.get('completion')
                paired = complete and reference_known
                labels = row['labels']
                require(row['source']['sha256'] == expected_sha, 'row_source_hash')
                require(row['owner_observation'] == public and row['snapshot_version'] == public_sha, 'observation_exact')
                require(row['candidate_semantics'] == candidate['action'], 'candidate_action_exact')
                require(row['source_group'] == row['scenario_set_id'] == case
                    and row['decision_id'] == case + ':' + owner + ':initial', 'scenario_group_identity')
                require(row['teacher_mode'] == 'causal_rollout' and row['information_scope'] == 'owner_local_delivered', 'teacher_scope')
                require(labels['evaluation_status'] == ('completed' if complete else 'unknown')
                    and labels['model_status'] == candidate['status'], 'unknown_label_not_promoted')
                expected_protection = ('passed' if all(completion[job] <= reference['completion'][job] for job in JOBS)
                    else 'failed') if paired else 'unknown'
                require(labels['conditional_protection_status'] == expected_protection, 'conditional_protection_exact')
                require(labels['protection_status'] == 'unknown' and labels['native_protection_certified'] is False,
                    'conditional_teacher_not_native_authority')
                require(labels['per_job_outcomes'] == (completion if complete else None), 'completion_exact')
                require(labels['cost_components'] == {'completion_sum_s': sum(completion.values()) if complete else None,
                    'reference_completion_sum_s': reference_cost,
                    'delta_completion_sum_s': sum(completion.values()) - reference_cost if paired else None}, 'cost_targets_exact')
                require(labels['observed_native_outcomes'] == (raw['summary']['completion'] if index == 4 else None)
                    and labels['observed_native_teacher_mode'] == ('realized_native' if index == 4 else None), 'native_label_scope')
                peer = 'B' if owner == 'A' else 'A'
                require(row['conditioned_peer_behavior'] == {'assumed_components': {
                    field: candidate['action'][field] for field in OWNER_FIELDS[peer]}, 'peer_commitment_observed': False},
                    'peer_conditioning_preserved')
                require(row['proposal_mask'] == {'owned_fields': list(OWNER_FIELDS[owner]),
                    'full_joint_execution_authorized': False}, 'owner_authority_scope')
        source_reports.append({'path': str(path.relative_to(root)), 'sha256': expected_sha, 'verified_rows': len(selected)})
    return source_reports


def verify(root):
    root = Path(root).resolve()
    manifest = read(root / L0 / 'collect/manifest.json')
    mapped = path_mapper(root, manifest)
    dataset = root / L0 / 'collect/decision_rows.jsonl'
    dataset_sha = sha(dataset)
    require(dataset_sha == manifest['dataset_sha256'], 'dataset_hash')
    rows = [json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines() if line.strip()]
    sources = check_rows(root, rows, manifest, mapped)
    report = read(root / L0 / 'models/training_report.json')
    replay = read(root / L0 / 'heldout_replay.json')
    registration = read(root / L0 / 'models/registration.json')
    folds = read(root / L0 / 'models/folds.json')
    require(report['dataset_sha256'] == registration['dataset_sha256'] == dataset_sha, 'training_dataset_hash')
    require(mapped(registration['dataset_path']) == dataset and registration['source_groups'] == sorted(CASES)
        and registration['split'] == 'leave_one_source_group_out' and registration['validation_tuning'] is False,
        'training_split_registration')
    require(len(folds) == 3 and {fold['held_out_group'] for fold in folds} == set(CASES)
        and report['fold_models'] == folds, 'three_scene_folds')
    model_reports = []
    for fold in folds:
        held_out = fold['held_out_group']
        expected_training = sorted(set(CASES) - {held_out})
        require(fold['training_groups'] == expected_training and set(fold['models']) == {'linear', 'mlp'}, 'fold_group_leakage')
        for kind, saved_model in fold['models'].items():
            path = mapped(saved_model)
            require(path == root / L0 / 'models' / (kind + '_holdout_' + held_out + '.json'), 'fold_model_path')
            model = read(path)
            require(model['kind'] == kind and model['trained_source_groups'] == expected_training
                and model['training_row_count'] == 128 and model['validation_or_test_used_for_fit'] is False,
                'fold_model_training_leakage')
            require(model['feature_schema'] == manifest['feature_schema'] and len(model['feature_names']) == 43
                and model['uses_candidate_index_as_feature'] is False and model['native_execution_authority'] is False,
                'model_feature_or_authority_scope')
            model_reports.append({'path': str(path.relative_to(root)), 'sha256': sha(path), 'held_out_group': held_out,
                'training_groups': expected_training, 'kind': kind})
    require(report['summary'] == replay['summary'], 'heldout_summary_exact')
    require(len(report['holdout_results']) == len(replay['holdout_results']) == 36, 'holdout_result_count')
    ignored = {'score_call_wall_ms_including_features'}
    for recorded, repeated in zip(report['holdout_results'], replay['holdout_results'], strict=True):
        require({key: value for key, value in recorded.items() if key not in ignored}
            == {key: value for key, value in repeated.items() if key not in ignored}, 'heldout_replay_exact_except_timing')
    for filename, expected_sha in [('foundation_learning_data.py', manifest['source_module_sha256']),
            ('foundation_ranker.py', report['source_module_sha256'])]:
        require(sha(root / 'scripts/experiments/g31_ics_circulation' / filename) == expected_sha, 'learning_source_hash:' + filename)
    return {'status': 'passed', 'root': str(root), 'dataset_sha256': dataset_sha, 'candidate_rows_verified': len(rows),
        'independent_scenario_groups': 3, 'owner_decision_groups': 6, 'source_raws': sources,
        'group_fold_models_verified': model_reports, 'heldout_replay_summaries_exact': True,
        'heldout_result_records_exact_except_score_timing': True,
        'native_or_model_training_executions': 0, 'model_inference_executions': 0,
        'scope': 'Artifact hashes, saved observation legality, exact raw-derived targets, declared whole-scene splits and saved replay consistency only. No retraining, native replay, independent recomputation of model scores, generalization or 100ms certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Repository checkout or extracted ZIP repo directory.')
    parser.add_argument('--output', type=Path, help='Optional new JSON result file; existing files are never overwritten.')
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        print(json.dumps({'status': 'failed', 'error': 'output_already_exists', 'path': str(args.output)}))
        return 2
    try:
        result = verify(args.root)
        status = 0
    except Exception as error:
        result = {'status': 'failed', 'error_type': type(error).__name__, 'error': str(error),
            'native_or_model_training_executions': 0, 'model_inference_executions': 0}
        status = 1
    encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf8') as handle:
            handle.write(encoded)
    print(encoded, end='')
    return status


if __name__ == '__main__':
    sys.exit(main())
