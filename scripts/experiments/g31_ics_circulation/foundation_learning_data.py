"""L0 saved-public features and separately stored conditional teacher labels."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
from pathlib import Path


SCHEMA = 'g31.foundation.owner_public_features.v2'
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
CASES = ('mechanism', 'no_overlap', 'insufficient_advance')
ACTION_FIELDS = ('initial_action', 'empty_departure', 'return_delay', 'later_action')
OWNER_FIELDS = {'A': ('initial_action', 'return_delay'), 'B': ('empty_departure', 'later_action')}


def require(condition, reason):
    if not condition:
        raise ValueError('foundation_learning_data:' + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_numeric_feature')
    return float(value)


def observation_features(observation):
    require(type(observation) is dict and set(observation) == {'command', 'own_request', 'received', 'view'},
        'public_observation_schema')
    view = observation['view']
    owner = view['owner_id']
    require(owner in OWNER_FIELDS, 'owner_role')
    now = number(view['now'])
    local_nodes = [node for node in view['node_contracts'] if node['resource_owner'] == owner]
    require(all(not any(field in node for field in ('occupancy', 'actual_available'))
        for node in view['node_contracts'] if node['resource_owner'] != owner), 'private_peer_node_fields')
    jobs, trays = view['jobs'], view['trays']
    require(all(number(job['arrival']) <= now for job in jobs), 'future_local_job')
    captures = []
    ages = []
    for message in observation['received']:
        require(message['kind'] == 'planning_snapshot', 'initial_delivered_planning_only')
        capture = message['capture']
        require(capture['source_owner'] != owner and capture['target_owner'] == owner, 'delivered_peer_scope')
        require(number(capture['captured_at']) <= number(message['delivered_at']) <= now, 'message_not_yet_delivered')
        require(capture['coverage']['future_arrivals_included'] is False, 'future_arrival_coverage')
        require(all(number(job['arrival']) <= capture['captured_at'] for job in capture['jobs']), 'future_peer_job')
        captures.append(capture)
        ages.append(now - number(capture['captured_at']))
    require(len(captures) <= 1, 'initial_single_peer_capture_scope')
    peer_jobs = [job for capture in captures for job in capture['jobs']]
    peer_nodes = [node for capture in captures for node in capture['nodes']]
    peer_trays = [tray for capture in captures for tray in capture['trays']]
    waiting = [job for job in jobs if job['status'] == 'waiting_for_tray']
    values = {
        'owner_is_A': float(owner == 'A'), 'owner_is_B': float(owner == 'B'), 'event_time_s': now,
        'own_tray_count': float(len(trays)),
        'own_available_empty_count': sum(number(node['actual_available']) for node in local_nodes),
        'own_loaded_count': float(sum(tray['mode'] == 'loaded' for tray in trays)),
        'own_loading_count': float(sum(tray['mode'] == 'loading' for tray in trays)),
        'own_inflight_count': float(sum(tray['edge_from'] >= 0 for tray in trays)),
        'own_occupancy': sum(number(node['occupancy']) for node in local_nodes),
        'own_capacity': sum(number(node['capacity']) for node in local_nodes),
        'own_waiting_jobs': float(len(waiting)),
        'own_oldest_wait_s': max((now - number(job['arrival']) for job in waiting), default=0.),
        'own_wait_sum_s': sum(now - number(job['arrival']) for job in waiting),
        'own_known_load_seconds': sum(number(job['load_seconds']) for job in jobs),
        'own_known_unload_seconds': sum(number(job['unload_seconds']) for job in jobs),
        'own_max_contract_storage_release_delay': max((max(0., number(job['storage_release_at']) - now) for job in jobs), default=0.),
        'own_min_deadline_margin': min((number(job['deadline']) - now for job in jobs), default=0.),
        'peer_capture_count': float(len(captures)), 'peer_information_age_s': max(ages, default=0.),
        'peer_capture_missing': float(not captures),
        'peer_declared_available_empty': sum(number(node['actual_available']) for node in peer_nodes),
        'peer_declared_occupancy': sum(number(node['occupancy']) for node in peer_nodes),
        'peer_declared_tray_count': float(len(peer_trays)),
        'peer_declared_waiting_jobs': float(sum(job['status'] == 'waiting_for_tray' for job in peer_jobs)),
        'peer_known_load_seconds': sum(number(job['load_seconds']) for job in peer_jobs),
        'peer_max_contract_storage_release_delay': max((max(0., number(job['storage_release_at']) - now) for job in peer_jobs), default=0.),
        'peer_known_ready_delay': max((max(0., number(tray['service_ready_at']) - now)
            for tray in peer_trays if tray['service_ready_known']), default=0.),
        'peer_ready_missing_count': float(sum(not tray['service_ready_known'] for tray in peer_trays)),
        'static_node_count': float(len(view['node_records'])), 'static_edge_count': float(len(view['edge_records'])),
        'static_edge_length_sum': sum(number(edge[2]) for edge in view['edge_records']),
        'actual_EBS_semantics_missing': 1., 'hard_receiver_reservation_missing': 1.}
    return {key: number(value) for key, value in values.items()}


def candidate_features(observation, action):
    require(type(action) is dict and set(action) == set(ACTION_FIELDS), 'semantic_candidate_schema')
    require(action['initial_action'] in ('native_default', 'prefer_2'), 'initial_action')
    require(action['later_action'] in ('native_default', 'prefer_8'), 'later_action')
    now = number(observation['view']['now'])
    departure, returned = number(action['empty_departure']), number(action['return_delay'])
    require(departure >= now and returned >= 0., 'negative_candidate_delay')
    initial = float(action['initial_action'] == 'prefer_2')
    later = float(action['later_action'] == 'prefer_8')
    delay = departure - now
    return {'candidate_initial_prefer_2': initial, 'candidate_initial_default': 1. - initial,
        'candidate_later_prefer_8': later, 'candidate_later_default': 1. - later,
        'candidate_empty_departure_delay_s': delay, 'candidate_return_delay_s': returned,
        'candidate_initial_later_interaction': initial * later,
        'candidate_departure_initial_interaction': delay * initial,
        'candidate_departure_later_interaction': delay * later,
        'candidate_return_initial_interaction': returned * initial}


def feature_vector(observation, action):
    return {**observation_features(observation), **candidate_features(observation, action)}


def known(completion):
    return type(completion) is dict and set(completion) == set(JOBS) and all(
        type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in completion.values())


def extract_raw(raw, source, scenario):
    require(raw['summary']['status'] == 'assessed', 'closed_saved_source_required')
    rows = []
    for owner in ('A', 'B'):
        initial = raw['initial_owners'][owner]
        observation = copy.deepcopy(initial['collection']['public'])
        observed_sha = digest(observation)
        require(observed_sha == initial['collection']['public_sha256'], 'public_digest')
        provider = initial['selection']['provider_evidence']
        require(provider['owner'] == owner and provider['initial_public_sha256'] == observed_sha, 'owner_label_origin')
        require(len(provider['rows']) == 32 and {row['candidate_index'] for row in provider['rows']} == set(range(32)), 'full32_domain')
        reference = next(row for row in provider['rows'] if row['candidate_index'] == 4)
        reference_cost = sum(reference['completion'].values()) if reference['status'] == 'conditional_forecast' and known(reference.get('completion')) else None
        for candidate in provider['rows']:
            completion = candidate.get('completion')
            complete = candidate['status'] == 'conditional_forecast' and known(completion)
            paired = complete and reference_cost is not None
            features = candidate_features(observation, candidate['action'])
            conditioned = {field: candidate['action'][field] for field in OWNER_FIELDS['B' if owner == 'A' else 'A']}
            index = candidate['candidate_index']
            rows.append({'episode_id': scenario + ':saved_incumbent', 'decision_id': scenario + ':' + owner + ':initial',
                'owner_id': owner, 'source_group': scenario, 'scenario_set_id': scenario,
                'observation_time_s': observation['view']['now'], 'observation_schema_version': SCHEMA,
                'information_scope': 'owner_local_delivered',
                'guard_information_scope': 'saved owned-provider full32 conditional forecast; not native execution authorization',
                'owner_observation': observation, 'observation_features': observation_features(observation),
                'observation_missing_mask': {'actual_EBS_semantics': True, 'hard_receiver_reservation': True,
                    'peer_capture': not observation['received']}, 'snapshot_version': observed_sha,
                'candidate_id': 'vector_' + str(index).zfill(2), 'candidate_index_for_join_only': index,
                'candidate_semantics': copy.deepcopy(candidate['action']), 'candidate_features': features,
                'proposal_mask': {'owned_fields': list(OWNER_FIELDS[owner]), 'full_joint_execution_authorized': False},
                'conditioned_peer_behavior': {'assumed_components': conditioned, 'peer_commitment_observed': False},
                'teacher_mode': 'causal_rollout', 'objective_version': 'sum_five_completion_delta_vs04.v1',
                'labels': {'evaluation_status': 'completed' if complete else 'unknown',
                    'conditional_protection_status': ('passed' if all(completion[job] <= reference['completion'][job] for job in JOBS)
                        else 'failed') if paired else 'unknown',
                    'protection_status': 'unknown', 'native_protection_certified': False,
                    'cost_components': {'completion_sum_s': sum(completion.values()) if complete else None,
                        'reference_completion_sum_s': reference_cost,
                        'delta_completion_sum_s': sum(completion.values()) - reference_cost if paired else None},
                    'per_job_outcomes': copy.deepcopy(completion) if complete else None,
                    'observed_native_outcomes': copy.deepcopy(raw['summary']['completion']) if index == 4 else None,
                    'observed_native_teacher_mode': 'realized_native' if index == 4 else None,
                    'model_status': candidate['status']},
                'evaluated_candidate_count': 32, 'source': source,
                'actor_input_has_no_candidate_index_or_labels': True})
    return rows


def export_saved_smoke(campaign_dir, output_dir):
    campaign_dir, output_dir = Path(campaign_dir).resolve(), Path(output_dir).resolve()
    require(not output_dir.exists(), 'immutable_output_directory')
    matrix = json.loads((campaign_dir / 'execution_matrix.json').read_bytes())
    rows, sources = [], {}
    for scenario in CASES:
        key = scenario + '/incumbent'
        cell = matrix[key]
        require(cell['status'] == 'assessed' and cell['process']['status'] == 'exited' and cell['process']['exitcode'] == 0,
            'source_process_closed')
        path = campaign_dir / (key + '.raw.json.gz')
        digest_value = file_sha(path)
        require(digest_value == cell['raw_artifact']['sha256'], 'source_raw_hash')
        raw = json.loads(gzip.decompress(path.read_bytes()))
        sources[str(path)] = digest_value
        rows.extend(extract_raw(raw, {'path': str(path), 'sha256': digest_value}, scenario))
    require(len(rows) <= 20000, 'row_budget')
    output_dir.mkdir(parents=True)
    dataset_path = output_dir / 'decision_rows.jsonl'
    dataset_path.write_text(''.join(canonical(row) + '\n' for row in rows), encoding='utf8')
    manifest = {'schema': 'g31.foundation.l0.saved_smoke_dataset.v1', 'dataset_path': str(dataset_path),
        'dataset_sha256': file_sha(dataset_path), 'candidate_rows': len(rows), 'independent_scenario_groups': len(CASES),
        'owner_decision_groups': len({row['decision_id'] for row in rows}), 'scenario_groups': list(CASES),
        'scope': 'Three saved scenes only; L0 pipeline smoke, not a generalization dataset or closed-loop RL.',
        'source_raw_sha256': sources, 'feature_schema': SCHEMA, 'feature_count': len(feature_vector(rows[0]['owner_observation'], rows[0]['candidate_semantics'])),
        'teacher_mode': 'causal_rollout', 'native_protection_certified': False, 'native_or_model_executions': 0,
        'future_labels_separate_from_actor_features': True, 'split_unit': 'source_group, never sibling candidates',
        'source_module_sha256': file_sha(__file__)}
    write(output_dir / 'manifest.json', manifest)
    return manifest


def read_dataset(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line.strip()]
    require(0 < len(rows) <= 20000, 'row_budget')
    return rows
