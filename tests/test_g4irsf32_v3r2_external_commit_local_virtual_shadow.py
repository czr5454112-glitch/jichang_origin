from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any, Mapping
import pytest
from scripts.eval import run_g4irsf32_v3r2_external_commit_local_virtual_shadow as runner
def _case(flow: str='simultaneous_local_first') -> runner.V3R2Case:
    return runner.V3R2Case(1.0, 8, flow)
def _row(*, path: int=1) -> dict[str, Any]:
    direct = path == 1
    return {'observation_ordinal': 1, 'opportunity_id': 11, 'event_time': 1.0, 'event_seq': 5, 'node': 1, 'calendar_generation_before': 4, 'seam_kind_code': path, 'external_path_code': path, 'external_task_id': 90, 'external_runtime_bag_id': 9, 'external_upstream_node': 0, 'external_slot_start_seconds': 2.0, 'external_slot_end_seconds': 3.0, 'external_service_seconds': 1.0, 'external_projected_arrival': 2.0, 'has_direct_episode_identity': direct, 'external_direct_episode_event_seq': 5 if direct else 0, 'has_j2_identity': not direct, 'external_request_id': 0 if direct else 41, 'external_request_lineage': 0 if direct else 51, 'external_request_generation': 0 if direct else 2, 'external_junction_queue_generation': 0 if direct else 3, 'local_task_id': 70, 'local_runtime_bag_id': 7, 'local_service_seconds': 1.0, 'local_source_ready_count': 1, 'local_source_uncovered_service_work_seconds': 1.0, 'external_scheduled_incoming_count': 0, 'destination_pending_count': 0 if direct else 1, 'oldest_local_wait_age_seconds': 1.0, 'oldest_external_wait_age_seconds': 0.0, 'local_source_enqueued_at': 0.0, 'local_release': 0.0, 'local_deadline': 100.0, 'local_choose_bag_index': 0, 'local_escape_token_runtime_bag_id': -1, 'local_queue_nonempty': True, 'local_bag_exists': True, 'local_released_live': True, 'local_source_queue_at_node': True, 'local_distinct_from_external': True, 'local_service_required': True, 'local_guards_passed': True, 'L0': 1.5, 'service_calendar_next_free_seconds': 1.5, 'existing_calendar_wait_seconds': 0.5, 'L1': 3.0, 'X_insert': 1.5, 'H_gap': 1.0, 'overlap_seconds': 0.5, 'epsilon': 1e-09, 'selected_action_from_node': 0, 'selected_action_to_node': 1, 'selected_action_kind_code': path, 'local_origin_code': 1, 'external_origin_code': 2, 'action_changed': False, 'future_release_read_count': 0, 'global_scan_count': 0, 'calendar_mutation_count': 0}
def _external_commit_marker(
    row: Mapping[str, Any], *, seq: int, **overrides: Any
) -> dict[str, Any]:
    reason = (
        'one_step_reservation_committed'
        if row['external_path_code'] == 1
        else 'one_step_merge_grant_committed'
    )
    marker = {
        'seq': seq,
        'event': 'EDGE_ENTER',
        'runtime_bag_id': row['external_runtime_bag_id'],
        'task_id': row['external_task_id'],
        'node': row['external_upstream_node'],
        'from_node': row['external_upstream_node'],
        'to_node': row['node'],
        'time': row['event_time'],
        'reason': reason,
    }
    marker.update(overrides)
    return marker
def _payload(path: int=1) -> dict[str, Any]:
    row = _row(path=path)
    events = [_external_commit_marker(row, seq=6), {'seq': 7, 'event': 'EDGE_EXIT', 'runtime_bag_id': 9, 'task_id': 90, 'node': 1, 'from_node': 0, 'to_node': 1, 'time': 2.0, 'reason': 'edge_exit'}, {'seq': 20, 'event': 'JUNCTION_SERVICE_COMPLETE', 'runtime_bag_id': 9, 'task_id': 90, 'node': 1, 'from_node': 0, 'to_node': 1, 'time': 3.0, 'reason': 'junction_service_complete'}, {'seq': 30, 'event': 'JUNCTION_SERVICE_COMPLETE', 'runtime_bag_id': 7, 'task_id': 70, 'node': 1, 'from_node': -1, 'to_node': 1, 'time': 5.0, 'reason': 'junction_service_complete'}]
    decisions = [{'task_id': 90, 'current_node': 0, 'selected_next': 1, 'event_time': 1.0, 'metadata': {'trace_kind': 'committed_edge_action', 'arrive_event_seq': 5, 'runtime_bag_id': 9}}]
    lifecycle = []
    if path == 2:
        lifecycle = [{'state': 'COMMITTED', 'reason': 'exact_slot_committed', 'request_id': 41, 'lineage': 51, 'request_generation': 2, 'junction_queue_generation': 3, 'runtime_bag_id': 9, 'task_id': 90, 'upstream_node': 0, 'destination_node': 1, 'edge_from_node': 0, 'edge_to_node': 1, 'projected_arrival': 2.0, 'destination_service_seconds': 1.0, 'slot_start': 2.0, 'slot_end': 3.0, 'time': 1.0, 'observed_claimed_request_generation': 2, 'observed_claimed_junction_queue_generation': 3, 'observed_claimed_owner_runtime_bag_id': 9, 'observed_claimed_edge_from_node': 0, 'observed_claimed_edge_to_node': 1, 'observed_claimed_destination_node': 1, 'observed_exact_calendar_reservation_present': False, 'calendar_generation': 5, 'observed_claimed_calendar_generation': 5}]
    return {'trace_context': {'schema_id': runner.ORDINARY_TRACE_SCHEMA_ID, 'source_aware_destination_service_schema_id': runner.TRACE_SCHEMA_ID}, 'summary': {'event_trace_truncated': False, 'decision_trace_truncated': False, 'trace_shard_count': 1, 'trace_shard_index': 0, 'decision_trace_stored_count': len(decisions), 'hold_trace_stored_count': 0, 'event_limit_reached': False, 'time_limit_reached': False, runner.NS + 'mode': 'shadow', 'merge_grant_lifecycle_complete': True, 'merge_grant_lifecycle_dropped_count': 0}, 'bags': [{'runtime_bag_id': 9, 'task_id': 90}, {'runtime_bag_id': 7, 'task_id': 70}], 'events': events, 'decisions': decisions, 'hold_attempts': [], 'merge_grant_lifecycle': lifecycle, runner.ROW_KEY: [row]}
def _population_identity_payload(
    *, path: int = 1
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {'bag_records': [
        ('external-segment', 90, 0.0, 100.0, 0, 3, 'external'),
        ('local-segment', 90, 0.0, 100.0, 1, 3, 'local'),
    ]}
    row = {
        **_row(path=path),
        'external_runtime_bag_id': 0,
        'local_runtime_bag_id': 1,
        'local_task_id': 90,
        'local_choose_bag_index': 0,
        'local_source_enqueued_at': 0.0,
    }
    bags = [
        {'runtime_bag_id': 0, 'segment_id': 'external-segment', 'task_id': 90, 'release_time': 0.0, 'deadline': 100.0, 'start': 0, 'goal': 3, 'source': 'external'},
        {'runtime_bag_id': 1, 'segment_id': 'local-segment', 'task_id': 90, 'release_time': 0.0, 'deadline': 100.0, 'start': 1, 'goal': 3, 'source': 'local'},
    ]
    enqueue = {'seq': 40, 'event': 'LOCAL_QUEUE_UPDATE', 'time': 0.0, 'runtime_bag_id': 1, 'task_id': 90, 'segment_id': 'local-segment', 'node': 1, 'reason': 'source_enqueue'}
    post_commit_dequeue = {'seq': 1, 'event': 'LOCAL_QUEUE_UPDATE', 'time': 1.0, 'runtime_bag_id': 1, 'task_id': 90, 'segment_id': 'local-segment', 'node': 1, 'reason': 'source_dequeue'}
    payload = {
        'bags': bags,
        'events': [
            enqueue,
            _external_commit_marker(row, seq=20),
            post_commit_dequeue,
        ],
        runner.ROW_KEY: [row],
    }
    return payload, request
def _repeat_ready_payload() -> dict[str, Any]:
    payload = _payload()
    for bag in payload['bags']: bag['goal'] = 3
    payload.update(junction_state=[{'node': 1, 'peak_local_state_accounted_bytes': 0}], hold_attempts=[])
    payload['summary'].update({'completed_count': 2, 'event_count': 4, 'cpp_internal_accounted_bytes': 0, 'internal_state_bytes': 0, **{runner.NS + key: 0 for key in ('external_commit_considered_count', 'direct_external_commit_count', 'j2_exact_commit_count', *runner.CENSUS_PARTS, *runner.SHADOW_ZERO, 'incremental_local_state_bytes', 'runtime_internal_accounted_bytes', 'trace_sidecar_accounted_bytes', 'total_accounted_bytes')}, runner.NS + 'external_commit_considered_count': 1, runner.NS + 'direct_external_commit_count': 1, runner.NS + 'observation_stored_count': 1})
    return payload
def test_population_task_identity_projection_and_protocol_hash_are_exact() -> None:
    manifest = runner.population_manifest()
    assert runner.SCHEMA.endswith('.v3r11')
    assert runner.SYNTHETIC_REVISION_ID == 'G4IRSF32_V3R11_DEEP_REPLAY_COMPATIBILITY_P0_20260829'
    assert runner.CAMPAIGN_REVISION_ID == 'G4IRSF32_V3R11_P0_CAMPAIGN_20260829'
    assert runner.OUTPUT_JSON.name == 'g4irsf32_v3r11_synthetic_stage01.json'
    assert runner.OUTPUT_MD.name == 'g4irsf32_v3r11_synthetic_stage01.md'
    assert manifest['case_count'] == 144
    assert manifest['task_bases'] == {
        'safety_regression': 32032000,
        'identification': 32032000 + 128 * 120,
    }
    assert manifest['cohorts']['safety_regression']['case_count'] == 120
    assert manifest['cohorts']['identification']['case_count'] == 24
    assert manifest['protocol_sha256'] == runner.PROTOCOL_SHA256
    assert manifest['native_row_schema_revision'] == 'V3R4_TELEMETRY_COMPLETENESS' and set(manifest['protocol_identities']) == {'measurement_protocol', 'execution_registration', 'preserved_v3r2_protocol', 'telemetry_completeness_addendum', 'commit_aligned_nanning_addendum', 'identification_addendum', 'stage0_metadata_parity_addendum', 'pair_binding_addendum', 'deep_replay_compatibility_addendum'}
    assert manifest['protocol_identities']['identification_addendum']['id'] == runner.IDENTIFICATION_ADDENDUM_ID
    assert manifest['protocol_identities']['stage0_metadata_parity_addendum']['id'] == runner.STAGE0_METADATA_PARITY_ADDENDUM_ID
    assert manifest['protocol_identities']['pair_binding_addendum']['id'] == runner.PAIR_BINDING_ADDENDUM_ID
    assert manifest['protocol_identities']['deep_replay_compatibility_addendum']['id'] == runner.SYNTHETIC_REVISION_ID
    first, last = (runner.registered_cases()[0], runner.registered_cases()[-1])
    assert len(runner.registered_cases()) == 120
    assert runner.build_bag_rows(first)[0]['task_id'] == 32032000
    assert runner.build_bag_rows(last)[-1]['task_id'] == 32032000 + 128 * 119 + 127
    request, _ = runner.build_request(_case(), mode='shadow')
    assert request['fault_windows'] == [] and request['storage_source_nodes'] == [0]
    assert request['source_aware_destination_service_mode'] == 'shadow'
    assert len(runner.profile_sha256(request)) == 64
    assert runner.LEDGER_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.REGISTRATION_PATH in runner.SOURCE_BUNDLE_PATHS and runner.V3R2_PROTOCOL_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.EVIDENCE_GAP_CLOSURE_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.HELDOUT_PREREGISTRATION_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.USER_CONTRACT_MANIFEST_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.TELEMETRY_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.ROOT / '.gitattributes' in runner.SOURCE_BUNDLE_PATHS
    assert runner.V3R5_COMMIT_ALIGNED_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.V3R6_BOUNDED_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.COMMIT_ALIGNED_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.IDENTIFICATION_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.STAGE0_METADATA_PARITY_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.file_sha256(runner.STAGE0_METADATA_PARITY_ADDENDUM_PATH) == runner.STAGE0_METADATA_PARITY_ADDENDUM_SHA256
    assert runner.PAIR_BINDING_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.file_sha256(runner.PAIR_BINDING_ADDENDUM_PATH) == runner.PAIR_BINDING_ADDENDUM_SHA256
    assert runner.DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.file_sha256(runner.DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH) == runner.DEEP_REPLAY_COMPATIBILITY_ADDENDUM_SHA256
    for relative in (
        'outputs/tables/g4irsf32_v3r8_synthetic_stage01.json',
        'outputs/reports/g4irsf32_v3r8_synthetic_stage01.md',
        'outputs/tables/g4irsf32_v3r8_p0_campaign.json',
        'outputs/reports/g4irsf32_v3r8_p0_campaign.md',
        'outputs/tables/g4irsf32_v3r9_synthetic_stage01.json',
        'outputs/reports/g4irsf32_v3r9_synthetic_stage01.md',
        'outputs/tables/g4irsf32_v3r9_p0_campaign.json',
        'outputs/reports/g4irsf32_v3r9_p0_campaign.md',
        'outputs/tables/g4irsf32_v3r10_synthetic_stage01.json',
        'outputs/reports/g4irsf32_v3r10_synthetic_stage01.md',
        'outputs/tables/g4irsf32_v3r10_p0_campaign.json',
        'outputs/reports/g4irsf32_v3r10_p0_campaign.md',
        'outputs/tables/g4irsf32_v3r11_synthetic_stage01.json',
        'outputs/reports/g4irsf32_v3r11_synthetic_stage01.md',
        'outputs/tables/g4irsf32_v3r11_p0_campaign.json',
        'outputs/reports/g4irsf32_v3r11_p0_campaign.md',
    ):
        assert relative in runner.IMPLEMENTATION_ALLOWED_PATHS
    assert not any(
        path.relative_to(runner.ROOT).as_posix().startswith('outputs/')
        for path in runner.SOURCE_BUNDLE_PATHS
    )
    assert runner.ROOT / 'scripts/eval/g4irsf31_map_adapter.py' in runner.SOURCE_BUNDLE_PATHS
    assert runner.ROOT / 'scripts/eval/run_g4irsf31_map2_native.py' in runner.SOURCE_BUNDLE_PATHS
    for path in (runner.NANNING_SELECTOR_PATH, runner.NANNING_SELECTOR_TEST_PATH, runner.NANNING_CONTROL_SELECTION_PATH):
        assert path.relative_to(runner.ROOT).as_posix() in runner.IMPLEMENTATION_ALLOWED_PATHS
    assert runner.NANNING_SELECTOR_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.NANNING_SELECTOR_TEST_PATH in runner.SOURCE_BUNDLE_PATHS
    assert runner.NANNING_CONTROL_SELECTION_PATH not in runner.SOURCE_BUNDLE_PATHS
    destination = runner.ROOT / 'cpp/tests/test_destination_merge_grant_real_map.cpp'
    assert destination in runner.SOURCE_BUNDLE_PATHS and destination.relative_to(runner.ROOT).as_posix() in runner.IMPLEMENTATION_ALLOWED_PATHS and not {'CMakeLists.txt', 'scripts/eval/g4irsf31_map_adapter.py', 'scripts/eval/run_g4irsf31_map2_native.py', 'data/processed/maps/map2.json'} & runner.IMPLEMENTATION_ALLOWED_PATHS
    assert any(row['path'] == destination.relative_to(runner.ROOT).as_posix() and len(row['sha256']) == 64 for row in runner.source_bundle_manifest()['files'])

def test_v3r8_identification_population_is_4_by_3_by_2_and_non_degenerate() -> None:
    cases = runner.identification_cases()
    assert len(cases) == 24
    assert {
        (case.service_seconds, case.bag_count, case.replica)
        for case in cases
    } == {
        (service, count, replica)
        for service in runner.SERVICE_SECONDS
        for count in runner.BAG_COUNTS
        for replica in (0, 1)
    }
    assert {
        case.flow_pattern for case in cases
    } == set(runner.IDENTIFICATION_FLOW_PATTERNS)

    by_stratum: dict[tuple[float, int], list[runner.IdentificationCase]] = {}
    for case in cases:
        by_stratum.setdefault((case.service_seconds, case.bag_count), []).append(case)
        manifest = runner.identification_case_manifest(case)
        expected_x = manifest['expected_x_insert_seconds']
        assert len(expected_x) == len(set(expected_x)) == 3
        assert len(manifest['bag_rows']) == case.bag_count

    for replicas in by_stratum.values():
        assert {case.replica for case in replicas} == {0, 1}
        requests = [
            runner.build_identification_request(case, mode='shadow')[0]
            for case in sorted(replicas, key=lambda value: value.replica)
        ]
        assert runner.request_sha256(requests[0]) != runner.request_sha256(requests[1])

def test_source_bundle_binds_the_user_supplied_markdown_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = runner.source_bundle_manifest()
    assert bundle['sha256'] == runner.canonical_sha256(bundle['files'])
    for path, expected_bytes, expected_sha256 in runner.USER_CONTRACT_FILES:
        assert path.stat().st_size == expected_bytes
        assert runner.file_sha256(path) == expected_sha256
        relative = path.relative_to(runner.ROOT).as_posix()
        attributes = subprocess.run(['git', 'check-attr', 'text', 'eol', '--', relative], cwd=runner.ROOT, capture_output=True, text=True, check=False)
        assert attributes.returncode == 0
        assert f'{relative}: text: set' in attributes.stdout
        assert f'{relative}: eol: lf' in attributes.stdout
    changed = tmp_path / 'changed-action-plan.md'
    changed.write_text('changed contract', encoding='utf-8')
    monkeypatch.setattr(runner, 'USER_CONTRACT_FILES', ((changed, 67791, runner.USER_CONTRACT_FILES[0][2]),))
    with pytest.raises(ValueError, match='identity changed'):
        runner.source_bundle_manifest()
def test_request_projection_rejects_every_unfrozen_backend_option() -> None:
    request, _ = runner.build_request(_case(), mode='shadow')
    request['legacy_observation_bias_max_seconds'] = 1.0
    with pytest.raises(ValueError, match='unexpected_request_keys'):
        runner.assert_request_projection(
            request,
            'shadow',
            [0],
            _case().scenario,
        )
def test_map2_frozen_profile_potential_and_first_eight_rows() -> None:
    request, hashes = runner.map2_fixture(mode='off')
    assert hashes == {'raw': runner.MAP2_RAW_SHA256, 'profile': runner.MAP2_PROFILE_SHA256, 'rows': runner.MAP2_ROWS_SHA256, 'potential': runner.MAP2_POTENTIAL_SHA256, 'segments': list(runner.MAP2_SEGMENTS), 'storage_source_nodes': [52]}
    assert request['storage_source_nodes'] == [52] and request['fault_windows'] == []
@pytest.mark.parametrize('path', [1, 2])
def test_namespaced_numeric_schema_and_strict_episode_builder(path: int) -> None:
    case, payload = (_case(), _payload(path))
    request = runner.build_request(case, mode='shadow')[0]
    rows = runner.extract_rows(payload, case_id=case.case_id, request=request)
    episodes = runner.build_service_episodes(case.case_id, payload, rows, request)
    joined = runner.join_v3r2_outcomes(rows, episodes)
    assert joined['status'] == runner.JOINED
    assert joined['pairs'][0]['Y_realized'] == 2.5
    if path == 2:
        assert next((ep for ep in episodes if ep['runtime_bag_id'] == 9))['request_lineage'] == 51
def test_episode_builder_rejects_ambiguous_direct_decision_and_wrong_schema() -> None:
    case, payload = (_case(), _payload())
    request = runner.build_request(case, mode='shadow')[0]
    rows = runner.extract_rows(payload, case_id=case.case_id, request=request)
    payload['decisions'].append(dict(payload['decisions'][0]))
    payload['summary']['decision_trace_stored_count'] = len(payload['decisions'])
    with pytest.raises(ValueError, match='exactly once'):
        runner.build_service_episodes(case.case_id, payload, rows, request)
    payload = _payload()
    payload['trace_context']['source_aware_destination_service_schema_id'] = 'wrong'
    with pytest.raises(ValueError, match='namespaced'):
        runner.extract_rows(payload, case_id=case.case_id, request=request)
def test_rows_freeze_epsilon_and_physical_commit_identity() -> None:
    case, payload = (_case(), _payload())
    request = runner.build_request(case, mode='shadow')[0]
    payload[runner.ROW_KEY][0]['epsilon'] = 1.0
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.extract_rows(payload, case_id=case.case_id, request=request)
    payload = _payload()
    duplicate = dict(payload[runner.ROW_KEY][0])
    duplicate.update(observation_ordinal=2, opportunity_id=12, external_slot_start_seconds=2.0 + 0.5e-9, external_slot_end_seconds=3.0 + 0.5e-9)
    payload[runner.ROW_KEY].append(duplicate)
    with pytest.raises(ValueError, match='physical commit identity'):
        runner.extract_rows(payload, case_id=case.case_id, request=request)
    first = _row()
    second = dict(first)
    second.update(opportunity_id=12, event_seq=6, external_direct_episode_event_seq=6, external_runtime_bag_id=10, external_task_id=91, local_runtime_bag_id=8, local_task_id=71)
    with pytest.raises(ValueError, match='observation ordinals'):
        runner.normalize_numeric_rows(case.case_id, [first, second], {1: 1.0})
    second.update(observation_ordinal=2, opportunity_id=first['opportunity_id'])
    rows = runner.normalize_numeric_rows(case.case_id, [first, second], {1: 1.0})
    assert len(rows) == 2 and rows[0]['opportunity_id'] == rows[1]['opportunity_id']
def test_rows_require_distinct_runtime_bags_not_distinct_raw_tasks() -> None:
    row = _row()
    row['local_task_id'] = row['external_task_id']
    assert runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})[0]['local_task_id'] == row['external_task_id']
    row['local_runtime_bag_id'] = row['external_runtime_bag_id']
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})
@pytest.mark.parametrize('pollution', ['L0_before_query', 'L1_still_overlaps_inserted_interval'])
def test_rows_reject_impossible_earliest_start_intervals(pollution: str) -> None:
    row = _row()
    if pollution == 'L0_before_query':
        row.update(external_slot_start_seconds=1.1, external_slot_end_seconds=2.1, L0=0.5, L1=2.1, X_insert=1.6, H_gap=1.0, overlap_seconds=0.4)
    else:
        row.update(L1=2.5, X_insert=1.0, H_gap=0.5)
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})

@pytest.mark.parametrize(('field', 'value'), [
    ('local_source_ready_count', 0),
    ('local_source_uncovered_service_work_seconds', 2.0),
    ('external_scheduled_incoming_count', -1),
    ('destination_pending_count', -1),
    ('oldest_local_wait_age_seconds', -0.1),
    ('oldest_external_wait_age_seconds', -0.1),
    ('service_calendar_next_free_seconds', 1.6),
    ('existing_calendar_wait_seconds', 0.6),
    ('selected_action_from_node', 2),
    ('selected_action_to_node', 2),
    ('selected_action_kind_code', 2),
    ('local_origin_code', 2),
    ('external_origin_code', 1),
])
def test_v3r4_telemetry_identity_and_nonnegative_contract(
    field: str, value: int | float
) -> None:
    row = _row()
    row[field] = value
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})

def test_v3r4_exact_schema_and_zero_pending_age_contract() -> None:
    row = _row()
    row.pop('local_source_ready_count')
    with pytest.raises(ValueError, match='keys differ from frozen schema'):
        runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})
    row = _row()
    row['oldest_external_wait_age_seconds'] = 0.1
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.normalize_numeric_rows(_case().case_id, [row], {1: 1.0})
def _legal_direct_safety_summary() -> dict[str, Any]:
    summary = {key: 0 for key in runner.SAFETY_ZERO_KEYS + runner.CLONE_SAFETY_ZERO_KEYS}
    summary.update(safe_execution_pass=True, max_edges_selected_per_bag_per_decision=1, event_limit_reached=False, time_limit_reached=False, artificial_batch_delay_seconds=0.0, merge_grant_conservation_holds=True, merge_grant_active_bijection_holds=True, merge_grant_protocol_integrity_pass=True, merge_grant_lifecycle_complete=True, merge_grant_lifecycle_dropped_count=0)
    return summary
@pytest.mark.parametrize(('field', 'bad'), [(key, 1) for key in runner.CLONE_SAFETY_ZERO_KEYS] + [('max_edges_selected_per_bag_per_decision', 2), ('event_limit_reached', True), ('time_limit_reached', True), ('artificial_batch_delay_seconds', 0.25)])
def test_safety_matches_clone_hard_gates_and_rejects_each_pollution(field: str, bad: Any) -> None:
    summary = _legal_direct_safety_summary()
    assert runner._safety(summary)
    summary[field] = bad
    assert not runner._safety(summary)
@pytest.mark.parametrize('field', list(runner.CLONE_SAFETY_ZERO_KEYS) + ['max_edges_selected_per_bag_per_decision', 'event_limit_reached', 'time_limit_reached', 'artificial_batch_delay_seconds'])
def test_safety_fails_closed_when_clone_gate_field_is_missing(field: str) -> None:
    summary = _legal_direct_safety_summary()
    summary.pop(field)
    assert not runner._safety(summary)
def test_global_service_calendar_audit_rebuilds_all_intervals_fail_closed() -> None:
    request = runner.build_request(_case(), mode='shadow')[0]
    request['node_records'] = [list(row) for row in request['node_records']]
    request['node_records'][1][2] = 0.0
    request['node_records'][1][1] = 2
    request['minimum_service_seconds'] = 0.25
    services = runner._services(request)
    episodes = runner._base_episodes('calendar', _payload(), services)[0]
    runtime_ids = {9: 0, 7: 1}
    episodes = [
        {**episode, 'runtime_bag_id': runtime_ids[episode['runtime_bag_id']]}
        for episode in episodes
    ]
    assert services[1] == 0.25 and episodes[0]['actual_L_service_start'] == 2.75
    state = [{'node': node, 'service_reservation_count': 2 if node == 1 else 0} for node in services]
    # A configured type-2 node may still serve a bag whose own goal is elsewhere.
    assert runner._global_service_calendar_audit(episodes, state, request)['pass']
    duplicate = episodes + [{**episodes[0], 'actual_L_service_start': 5.75, 'actual_L_service_complete': 6.0}]
    duplicate_state = [{**row, 'service_reservation_count': 3} if row['node'] == 1 else row for row in state]
    assert not runner._global_service_calendar_audit(duplicate, duplicate_state, request)['pass']
    overlap = copy.deepcopy(episodes)
    overlap[1].update(actual_L_service_start=2.9, actual_L_service_complete=3.15)
    assert not runner._global_service_calendar_audit(overlap, state, request)['pass']
    mismatch = [{**row, 'service_reservation_count': 1} if row['node'] == 1 else row for row in state]
    assert not runner._global_service_calendar_audit(episodes, mismatch, request)['pass']
    missing = copy.deepcopy(state); missing[1].pop('service_reservation_count')
    assert not runner._global_service_calendar_audit(episodes, missing, request)['pass']
    goal = episodes + [{**episodes[0], 'runtime_bag_id': 0, 'node': 3, 'actual_L_service_start': 6.0, 'actual_L_service_complete': 6.25}]
    goal_state = [{**row, 'service_reservation_count': 1} if row['node'] == 3 else row for row in state]
    assert not runner._global_service_calendar_audit(goal, goal_state, request)['pass']
def _v3r3_semantic_fixture(n: int=128) -> tuple[dict[str, Any], dict[str, Any]]:
    records, bags, events = ([], [], [])
    for index in range(n):
        source, wait = (('local' if index % 2 == 0 else 'external'), float(index))
        records.append((f'segment-{index}', 1000 + index, 0.0, 1000.0, 0, 2, source))
        bags.append({'runtime_bag_id': index, 'segment_id': f'segment-{index}', 'task_id': 1000 + index, 'release_time': 0.0, 'deadline': 1000.0, 'start': 0, 'goal': 2, 'source': source, 'completed': True, 'finish_time': float(index + 1), 'total_local_wait': wait, 'starved': wait > 120.0})
        events.append({'seq': index + 1, 'event': 'JUNCTION_SERVICE_COMPLETE', 'runtime_bag_id': index, 'task_id': 1000 + index, 'node': 1, 'from_node': 0, 'to_node': 1, 'time': float(index + 1), 'reason': 'junction_service_complete'})
    summary = {**_legal_direct_safety_summary(), 'event_trace_truncated': False, 'decision_trace_truncated': False, 'trace_shard_count': 1, 'trace_shard_index': 0, 'decision_trace_stored_count': 0, 'hold_trace_stored_count': 0, 'requested_count': n, 'completed_count': n, 'failed_count': 0, 'final_active_bag_count': 0, 'starvation_count': sum(bag['starved'] for bag in bags), 'merge_grant_peak_pending_requests': 0, 'merge_grant_peak_active_unconsumed': 0, 'merge_grant_request_count': 0, 'merge_grant_issued_count': 0, 'merge_grant_issued_transition_count': 0, 'merge_grant_prepared_count': 0, 'merge_grant_prepared_transition_count': 0, 'merge_grant_committed_count': 0, 'merge_grant_committed_transition_count': 0, 'merge_grant_consumed_count': 0, 'merge_grant_post_commit_revoked_count': 0, 'merge_grant_post_commit_expired_count': 0, 'merge_grant_post_commit_rollback_count': 0, 'merge_grant_expired_count': 0, 'merge_grant_revoked_count': 0, 'merge_grant_rolled_back_count': 0, 'merge_grant_lifecycle_transition_count': 0, 'merge_grant_lifecycle_stored_count': 0, 'merge_grant_terminal_request_count': 0, 'merge_grant_final_active_unconsumed': 0, 'merge_grant_outstanding_request_count': 0}
    junctions = [{'node': node, 'service_reservation_count': n if node == 1 else 0, 'final_source_queue_length': 0, 'final_junction_queue_length': 0, 'scheduled_incoming': 0} for node in range(3)]
    request = {'minimum_service_seconds': 0.001, 'complete_on_goal_arrival': True, 'node_records': [[0, 7, 0.0, 0, 0, [1]], [1, 1, 1.0, 1, 0, [2]], [2, 2, 0.0, 2, 0, []]], 'bag_records': records}
    payload = {'trace_context': {'schema_id': runner.ORDINARY_TRACE_SCHEMA_ID}, 'summary': summary, 'bags': bags, 'events': events, 'decisions': [], 'hold_attempts': [], 'junction_state': junctions, 'merge_grant_lifecycle': [], runner.ROW_KEY: []}
    return payload, request
def test_v3r3_legacy_positive_is_diagnostic_while_permanent_starvation_is_zero() -> None:
    payload, request = _v3r3_semantic_fixture()
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert audit['pass'] and audit['legacy_wait_over_120']['recomputed_count'] == 7
    assert audit['permanent_starvation']['pass'] and audit['service_sequence']['pass']
    assert audit['service_sequence']['maximum_consecutive_origin_run'] == 1
    sequence = audit['service_sequence']['ordered_service_episodes']
    permanent = audit['permanent_starvation']
    assert sequence == sorted(sequence, key=lambda row: (row['start'], row['complete'], row['completion_event_seq'], row['runtime_bag_id']))
    assert audit['service_sequence']['sequence_sha256'] == runner.canonical_sha256(sequence)
    assert audit['service_sequence']['sequence_count'] <= audit['service_sequence']['evidence_vector_limit']
    assert [row['runtime_bag_id'] for row in permanent['bag_completion_vector']] == list(range(128))
    assert [row['node'] for row in permanent['junction_final_vector']] == [0, 1, 2]
    for name in ('bag_completion_vector', 'junction_final_vector', 'lifecycle_final_state_vector'):
        assert permanent[name + '_sha256'] == runner.canonical_sha256(permanent[name])
    assert permanent['recomputable_vector_count'] <= permanent['recomputable_vector_limit']
    assert runner._safety(payload['summary']) and json.dumps(audit, allow_nan=False)
def test_permanent_audit_requires_active_nodes_but_not_a_dormant_source() -> None:
    payload, request = _v3r3_semantic_fixture()
    request['node_records'].append([3, 7, 0.0, 0, 1, [1]])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert audit['pass']
    assert audit['permanent_starvation']['configured_junction_count'] == 4
    assert audit['permanent_starvation']['expected_junction_count'] == 3
    payload['junction_state'] = [row for row in payload['junction_state'] if row['node'] != 2]
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert not audit['pass']
    assert audit['permanent_starvation']['checks']['active_junction_state_exact'] is False

def test_permanent_audit_accepts_only_inert_configured_state_beyond_active_nodes() -> None:
    payload, request = _v3r3_semantic_fixture()
    request['node_records'].append([3, 7, 0.0, 0, 1, [1]])
    payload['junction_state'].append({'node': 3, 'service_reservation_count': 0, 'final_source_queue_length': 0, 'final_junction_queue_length': 0, 'scheduled_incoming': 0})
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert audit['pass']
    permanent = audit['permanent_starvation']
    assert permanent['junction_count'] == 4
    assert permanent['expected_junction_count'] == 3
    assert permanent['configured_junction_count'] == 4
    assert permanent['recomputable_vector_limit'] == 128 + 4

    queued, queued_request = _v3r3_semantic_fixture()
    queued_request['node_records'].append([3, 7, 0.0, 0, 1, [1]])
    queued['junction_state'].append({'node': 3, 'service_reservation_count': 0, 'final_source_queue_length': 1, 'final_junction_queue_length': 0, 'scheduled_incoming': 0})
    queued_audit = runner._service_audit('n128', 128, {'local', 'external'}, queued, queued_request, exact_node=1)
    assert not queued_audit['pass']
    assert queued_audit['permanent_starvation']['checks']['final_queues_empty'] is False

    serviced, serviced_request = _v3r3_semantic_fixture()
    serviced_request['node_records'].append([3, 7, 0.0, 0, 1, [1]])
    serviced['junction_state'].append({'node': 3, 'service_reservation_count': 1, 'final_source_queue_length': 0, 'final_junction_queue_length': 0, 'scheduled_incoming': 0})
    serviced_audit = runner._service_audit('n128', 128, {'local', 'external'}, serviced, serviced_request, exact_node=1)
    assert not serviced_audit['pass']
    assert serviced_audit['permanent_starvation']['checks']['active_junction_state_exact'] is False
    assert serviced_audit['checks']['global_service_calendar'] is False
@pytest.mark.parametrize(('kind', 'gate'), [('count', 'legacy_wait_native_consistent'), ('flag', 'legacy_wait_native_consistent'), ('queue', 'permanent_starvation_zero'), ('deadline', 'permanent_starvation_zero'), ('origin', 'permanent_starvation_zero')])
def test_v3r3_semantic_pollution_fails_closed(kind: str, gate: str) -> None:
    payload, request = _v3r3_semantic_fixture()
    if kind == 'count': payload['summary']['starvation_count'] += 1
    elif kind == 'flag': payload['bags'][121]['starved'] = False
    elif kind == 'queue': payload['junction_state'][1]['final_source_queue_length'] = 1
    elif kind == 'deadline': payload['bags'][-1]['finish_time'] = 1001.0
    else: payload['bags'][1]['source'] = 'local'
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert not audit['pass'] and audit['checks'][gate] is False
    json.dumps(audit, allow_nan=False)
def test_v3r3_legacy_off_shadow_exact_rejects_a_new_over_120_wait() -> None:
    off, _request = _v3r3_semantic_fixture(); shadow = copy.deepcopy(off)
    shadow['bags'][120].update(total_local_wait=121.0, starved=True); shadow['summary']['starvation_count'] += 1
    assert runner.legacy_wait_over_120(off)['pass'] and runner.legacy_wait_over_120(shadow)['pass']
    paired = runner.legacy_wait_pair(off, shadow)
    assert not paired['pass'] and not paired['checks']['count_exact'] and json.dumps(paired, allow_nan=False)
def _lifecycle_row(state: str, *, time: float, destination_node: int=1, grant_id: int=1, request_id: int=1) -> dict[str, Any]:
    return {'state': state, 'time': time, 'request_id': request_id, 'lineage': 1, 'request_generation': 1, 'junction_queue_generation': 1, 'destination_node': destination_node, 'grant_id': grant_id}
def _completed_lifecycle(*, destination_node: int, request_id: int, grant_id: int, base_time: float) -> list[dict[str, Any]]:
    return [
        _lifecycle_row('REQUESTED', time=base_time, destination_node=destination_node, request_id=request_id, grant_id=0),
        _lifecycle_row('ISSUED', time=base_time + 1.0, destination_node=destination_node, request_id=request_id, grant_id=grant_id),
        _lifecycle_row('PREPARED', time=base_time + 1.0, destination_node=destination_node, request_id=request_id, grant_id=grant_id),
        _lifecycle_row('COMMITTED', time=base_time + 1.0, destination_node=destination_node, request_id=request_id, grant_id=grant_id),
        _lifecycle_row('CONSUMED', time=base_time + 2.0, destination_node=destination_node, request_id=request_id, grant_id=grant_id),
    ]
def _apply_lifecycle_summary(summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    states = {name: sum(row['state'] == name for row in rows) for name in ('REQUESTED', 'ISSUED', 'PREPARED', 'COMMITTED', 'CONSUMED')}
    final: dict[tuple[int, int, int, int, int], str] = {}
    histories: dict[tuple[int, int, int, int, int], list[str]] = {}
    for row in rows:
        identity = tuple(row[key] for key in ('request_id', 'lineage', 'request_generation', 'junction_queue_generation', 'destination_node'))
        final[identity] = row['state']
        histories.setdefault(identity, []).append(row['state'])
    terminals = {'EXPIRED', 'REVOKED_FAULT', 'REVOKED_STALE_STATE', 'REVOKED_REPLAN_CURRENT_EDGE', 'ROLLED_BACK'}
    post_commit = [history[-1] for history in histories.values() if 'COMMITTED' in history and history[-1] in terminals]
    committed_current = sum(state in {'COMMITTED', 'CONSUMED'} for state in final.values())
    summary.update(
        merge_grant_request_count=states['REQUESTED'],
        merge_grant_issued_count=committed_current,
        merge_grant_issued_transition_count=states['ISSUED'],
        merge_grant_prepared_count=committed_current,
        merge_grant_prepared_transition_count=states['PREPARED'],
        merge_grant_committed_count=committed_current,
        merge_grant_committed_transition_count=states['COMMITTED'],
        merge_grant_consumed_count=states['CONSUMED'],
        merge_grant_post_commit_revoked_count=sum(state.startswith('REVOKED_') for state in post_commit),
        merge_grant_post_commit_expired_count=post_commit.count('EXPIRED'),
        merge_grant_post_commit_rollback_count=post_commit.count('ROLLED_BACK'),
        merge_grant_expired_count=sum(state == 'EXPIRED' for state in final.values()),
        merge_grant_revoked_count=sum(state.startswith('REVOKED_') for state in final.values()),
        merge_grant_rolled_back_count=sum(state == 'ROLLED_BACK' for state in final.values()),
        merge_grant_lifecycle_transition_count=len(rows),
        merge_grant_lifecycle_stored_count=len(rows),
        merge_grant_lifecycle_dropped_count=0,
        merge_grant_terminal_request_count=sum(state in terminals for state in final.values()),
        merge_grant_outstanding_request_count=sum(state == 'REQUESTED' for state in final.values()),
        merge_grant_final_active_unconsumed=sum(state == 'COMMITTED' for state in final.values()),
    )
def test_v3r3_merge_history_uses_last_state_and_recomputes_final_live_summary() -> None:
    payload, request = _v3r3_semantic_fixture()
    payload['merge_grant_lifecycle'] = [_lifecycle_row('REQUESTED', time=0.0, grant_id=0), _lifecycle_row('ISSUED', time=1.0), _lifecycle_row('PREPARED', time=1.0), _lifecycle_row('COMMITTED', time=1.0), _lifecycle_row('CONSUMED', time=2.0)]
    summary = payload['summary']; _apply_lifecycle_summary(summary, payload['merge_grant_lifecycle'])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    permanent = audit['permanent_starvation']
    assert audit['pass'] and permanent['historical_last_lifecycle_state_counts'] == {'CONSUMED': 1}
    assert permanent['lifecycle_final_state_vector'] == [{'request_id': 1, 'lineage': 1, 'request_generation': 1, 'junction_queue_generation': 1, 'destination_node': 1, 'state': 'CONSUMED'}]
    assert permanent['checks']['final_merge_pending_zero'] and permanent['checks']['merge_active_unconsumed_zero']
@pytest.mark.parametrize(
    ('request_time_drift', 'expected_pass'),
    [(0.5 * runner.EPSILON, True), (2.0 * runner.EPSILON, False)],
)
def test_v3r3_lifecycle_canonicalizes_only_subepsilon_telemetry_order_jitter(
    request_time_drift: float, expected_pass: bool
) -> None:
    payload, request = _v3r3_semantic_fixture()
    rows = _completed_lifecycle(
        destination_node=1, request_id=1, grant_id=7, base_time=0.0
    )
    requested = {**rows[0], 'time': rows[1]['time'] + request_time_drift}
    payload['merge_grant_lifecycle'] = [
        rows[1],
        rows[2],
        rows[3],
        requested,
        rows[4],
    ]
    _apply_lifecycle_summary(payload['summary'], payload['merge_grant_lifecycle'])
    audit = runner._service_audit(
        'n128', 128, {'local', 'external'}, payload, request, exact_node=1
    )
    assert audit['permanent_starvation']['checks']['lifecycle_chains_valid'] \
        is expected_pass
    assert audit['pass'] is expected_pass
def test_v3r3_lifecycle_subepsilon_raw_order_uses_logical_final_state() -> None:
    payload, _request = _v3r3_semantic_fixture()
    logical = _completed_lifecycle(
        destination_node=1, request_id=1, grant_id=7, base_time=0.0
    )[:4]
    _apply_lifecycle_summary(payload['summary'], logical)
    requested = {
        **logical[0],
        'time': logical[1]['time'] + 0.5 * runner.EPSILON,
    }
    raw = [logical[1], logical[2], logical[3], requested]
    audit = runner._merge_lifecycle_chain_audit(raw, payload['summary'])
    identity = (1, 1, 1, 1, 1)
    assert audit['ordered'] and audit['chains_valid'] and audit['counts_exact']
    assert audit['final_states'][identity] == 'COMMITTED'
@pytest.mark.parametrize(
    'pollution',
    [
        'only_consumed',
        'missing_committed',
        'duplicate_requested',
        'request_grant',
        'grant_drift',
        'terminal_grant_drift',
        'issue_time_drift',
        'terminal_time_reversal',
    ],
)
def test_v3r3_lifecycle_rejects_incomplete_or_inconsistent_chains(pollution: str) -> None:
    payload, request = _v3r3_semantic_fixture()
    rows = _completed_lifecycle(destination_node=1, request_id=1, grant_id=7, base_time=0.0)
    if pollution == 'only_consumed':
        rows = [rows[-1]]
    elif pollution == 'missing_committed':
        rows.pop(3)
    elif pollution == 'duplicate_requested':
        rows.insert(1, dict(rows[0]))
    elif pollution == 'request_grant':
        rows[0] = {**rows[0], 'grant_id': 7}
    elif pollution == 'grant_drift':
        rows[2] = {**rows[2], 'grant_id': 8}
    elif pollution == 'terminal_grant_drift':
        rows[-1] = {**rows[-1], 'grant_id': 8}
    elif pollution == 'issue_time_drift':
        rows[2] = {**rows[2], 'time': rows[2]['time'] + 0.25}
    else:
        rows[-1] = {
            **rows[-1],
            'time': rows[3]['time'] - 2.0 * runner.EPSILON,
        }
    payload['merge_grant_lifecycle'] = rows
    _apply_lifecycle_summary(payload['summary'], rows)
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert not audit['pass']
    assert audit['permanent_starvation']['checks']['lifecycle_chains_valid'] is False
def test_v3r3_lifecycle_summary_counts_are_recomputed() -> None:
    payload, request = _v3r3_semantic_fixture()
    rows = _completed_lifecycle(destination_node=1, request_id=1, grant_id=7, base_time=0.0)
    payload['merge_grant_lifecycle'] = rows
    _apply_lifecycle_summary(payload['summary'], rows)
    payload['summary']['merge_grant_lifecycle_stored_count'] -= 1
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert not audit['pass']
    assert audit['permanent_starvation']['checks']['lifecycle_counts_exact'] is False
@pytest.mark.parametrize('state', ['REQUESTED', 'ISSUED', 'PREPARED', 'COMMITTED'])
def test_v3r3_nonterminal_last_lifecycle_state_fails_closed(state: str) -> None:
    payload, request = _v3r3_semantic_fixture()
    payload['merge_grant_lifecycle'] = [_lifecycle_row(state, time=0.0, grant_id=0 if state == 'REQUESTED' else 1)]
    summary = payload['summary']
    _apply_lifecycle_summary(summary, payload['merge_grant_lifecycle'])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert not audit['pass']
    permanent = audit['permanent_starvation']
    if state in {'ISSUED', 'PREPARED'}:
        assert not permanent['checks']['lifecycle_final_state_complete']
    elif state == 'REQUESTED':
        assert not permanent['checks']['final_merge_pending_zero']
    else:
        assert not permanent['checks']['merge_active_unconsumed_zero']
def test_v3r3_terminal_last_lifecycle_state_matches_terminal_summary() -> None:
    payload, request = _v3r3_semantic_fixture()
    payload['merge_grant_lifecycle'] = [_lifecycle_row('REQUESTED', time=0.0, grant_id=0), _lifecycle_row('EXPIRED', time=1.0, grant_id=0)]
    _apply_lifecycle_summary(payload['summary'], payload['merge_grant_lifecycle'])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    permanent = audit['permanent_starvation']
    assert audit['pass'] and permanent['historical_last_lifecycle_state_counts'] == {'EXPIRED': 1}
    assert permanent['checks']['lifecycle_terminal_exact'] and permanent['merge_request_accounting']['final_terminal_count'] == 1
def test_v3r3_post_commit_rollback_uses_historical_transition_conservation() -> None:
    payload, request = _v3r3_semantic_fixture()
    rows = _completed_lifecycle(destination_node=1, request_id=1, grant_id=7, base_time=0.0)[:-1]
    rows.append(_lifecycle_row('ROLLED_BACK', time=2.0, grant_id=7))
    payload['merge_grant_lifecycle'] = rows
    _apply_lifecycle_summary(payload['summary'], rows)
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    counts = audit['permanent_starvation']['merge_request_accounting']
    assert audit['pass']
    assert counts['committed_count'] == 0 and counts['terminal_count'] == 1
def test_v3r3_lifecycle_identity_includes_destination_and_order_is_fail_closed() -> None:
    payload, request = _v3r3_semantic_fixture()
    payload['merge_grant_lifecycle'] = [_lifecycle_row('CONSUMED', time=2.0), _lifecycle_row('REQUESTED', time=0.0, destination_node=2, grant_id=0)]
    _apply_lifecycle_summary(payload['summary'], payload['merge_grant_lifecycle'])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    permanent = audit['permanent_starvation']
    assert not audit['pass'] and len(permanent['lifecycle_final_state_vector']) == 2
    assert not permanent['checks']['lifecycle_ordered'] and not permanent['checks']['lifecycle_final_state_complete']
@pytest.mark.parametrize(('second_destination', 'second_request_id', 'expected'), [(2, 1, True), (1, 2, False)])
def test_v3r3_committed_request_and_grant_ids_are_controller_local(second_destination: int, second_request_id: int, expected: bool) -> None:
    payload, request = _v3r3_semantic_fixture()
    payload['merge_grant_lifecycle'] = [
        *_completed_lifecycle(destination_node=1, request_id=1, grant_id=7, base_time=0.0),
        *_completed_lifecycle(destination_node=second_destination, request_id=second_request_id, grant_id=7, base_time=3.0),
    ]
    _apply_lifecycle_summary(payload['summary'], payload['merge_grant_lifecycle'])
    audit = runner._service_audit('n128', 128, {'local', 'external'}, payload, request, exact_node=1)
    assert audit['checks']['no_overlap_or_duplicate'] is expected
    assert audit['pass'] is expected
@pytest.mark.parametrize(('field', 'delta'), [('decision_trace_stored_count', 1), ('hold_trace_stored_count', 1)])
def test_ordinary_health_recomputes_stored_trace_counts(field: str, delta: int) -> None:
    payload = _payload()
    payload['summary'][field] += delta
    with pytest.raises(ValueError, match='ordinary payload is incomplete'):
        runner._ordinary_health(payload)
def test_resources_use_frozen_zero_denominator_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = {'resources': {'off': {}, 'shadow': {}}}
    for name in ('events_per_completed', 'junction_local_accounted_bytes', 'runtime_internal_accounted_bytes', 'total_accounted_bytes'):
        base['resources']['off'][name] = base['resources']['shadow'][name] = 0.0
    assert runner.evaluate_resources([base])['pass']
    base['resources']['shadow']['total_accounted_bytes'] = 1.0
    result = runner.evaluate_resources([base])
    assert not result['pass']
    total = next((gate for gate in result['gates'] if gate['name'] == 'resource_total_accounted_bytes'))
    assert total['evidence']['non_finite'] == 1
    payload = {'summary': {'completed_count': 2, 'event_count': 4, 'cpp_internal_accounted_bytes': 13, 'internal_state_bytes': 13, runner.NS + 'incremental_local_state_bytes': 0, runner.NS + 'runtime_internal_accounted_bytes': 10, runner.NS + 'trace_sidecar_accounted_bytes': 3, runner.NS + 'total_accounted_bytes': 13}, 'junction_state': [{'peak_local_state_accounted_bytes': 7}]}
    assert runner._resource_values(payload, shadow=True) == {'events_per_completed': 2.0, 'junction_local_accounted_bytes': 7.0, 'runtime_internal_accounted_bytes': 10.0, 'trace_sidecar_accounted_bytes': 3.0, 'total_accounted_bytes': 13.0}
    forged = json.loads(json.dumps(payload)); forged['summary'][runner.NS + 'total_accounted_bytes'] = 1
    with pytest.raises(ValueError, match='exact decomposition'):
        runner._resource_values(forged, shadow=True)
    forged = json.loads(json.dumps(payload))
    forged['summary'][runner.NS + 'incremental_local_state_bytes'] = -1
    with pytest.raises(ValueError, match='exact decomposition'):
        runner._resource_values(forged, shadow=True)
    payload['summary']['completed_count'] = 0
    with pytest.raises(ValueError, match='resource accounting'):
        runner._resource_values(payload, shadow=True)
    case, raw_row, raw_pair = (_case(), {'case_id': _case().case_id, 'observation_ordinal': 1}, {'case_id': _case().case_id, 'primary': False})
    monkeypatch.setattr(runner, 'registered_cases', lambda: (case,)); monkeypatch.setattr(runner, 'run_case', lambda *_args, **_kwargs: {'rows': [raw_row], 'join': {}}); monkeypatch.setattr(runner, 'merge_joined_pairs', lambda *_args: [raw_pair])
    monkeypatch.setattr(runner, 'identification_cases', lambda: ())
    monkeypatch.setattr(runner, 'summarize_case', lambda *_args, **_kwargs: runner._resource_values(payload, shadow=True))
    stage1 = runner.run_stage1(executor=lambda **_request: {}, g32_binary=tmp_path / 'unused.pyd', expected_binary_sha256='a' * 64, draws=1)
    evidence = {'status': runner.NO_GO, 'decision': runner.NO_GO, 'stage0': None, 'stage1': stage1, 'issue_remediation_ledger': []}
    json_path, md_path = (tmp_path / 'zero.json', tmp_path / 'zero.md'); runner.write_evidence(evidence, json_path=json_path, markdown_path=md_path)
    assert not stage1['pass']
    assert stage1['status'] == 'NO_GO_V3R11_STAGE1_CONTRACT'
    assert stage1['safety_regression']['observations'] == [raw_row]
    assert stage1['safety_regression']['pairs'] == [raw_pair]
    assert stage1['identification']['observations'] == []
    assert stage1['identification']['pairs'] == []
    assert json.loads(json_path.read_text(encoding='utf-8'))['decision'] == runner.NO_GO
    json.dumps(evidence, allow_nan=False)
def test_output_bags_bind_exactly_to_request_manifest_and_shadow_rows() -> None:
    payload, request = _population_identity_payload()
    assert runner._bag_population_identity(payload, request)['pass']
    forged = json.loads(json.dumps(payload)); forged['bags'][1]['segment_id'] = 'external-segment'; assert not runner._bag_population_identity(forged, request)['pass']
    forged = json.loads(json.dumps(payload)); forged[runner.ROW_KEY][0]['local_task_id'] = 999; assert not runner._bag_population_identity(forged, request)['pass']
    forged = json.loads(json.dumps(payload)); forged[runner.ROW_KEY][0]['local_choose_bag_index'] = 1; assert not runner._bag_population_identity(forged, request)['pass']
    swapped = copy.deepcopy(payload)
    swapped_request = copy.deepcopy(request)
    swapped['bags'][0]['source'] = 'local'
    swapped_request['bag_records'][0] = (*swapped_request['bag_records'][0][:-1], 'local')
    swapped['bags'][1]['source'] = 'external'
    swapped_request['bag_records'][1] = (*swapped_request['bag_records'][1][:-1], 'external')
    assert not runner._bag_population_identity(swapped, swapped_request)['pass']
    forged = copy.deepcopy(payload); forged['events'][0]['segment_id'] = 'wrong-segment'; assert not runner._bag_population_identity(forged, request)['pass']
@pytest.mark.parametrize('path', [1, 2])
def test_source_queue_replay_uses_raw_execution_order_and_commit_reason(
    path: int,
) -> None:
    payload, request = _population_identity_payload(path=path)

    assert payload['events'][0]['seq'] > payload[runner.ROW_KEY][0]['event_seq']
    assert payload['events'][2]['seq'] < payload[runner.ROW_KEY][0]['event_seq']
    assert runner._bag_population_identity(payload, request)['pass']

    wrong_reason = copy.deepcopy(payload)
    wrong_reason['events'][1]['reason'] = (
        'one_step_merge_grant_committed'
        if path == 1
        else 'one_step_reservation_committed'
    )
    assert not runner._bag_population_identity(wrong_reason, request)['pass']
@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('runtime_bag_id', 99),
        ('task_id', 91),
        ('from_node', 4),
        ('to_node', 2),
        ('time', 1.25),
    ],
)
def test_source_queue_replay_rejects_missing_or_mismatched_commit_marker(
    field: str, value: Any
) -> None:
    payload, request = _population_identity_payload()
    payload['events'][1][field] = value

    assert not runner._bag_population_identity(payload, request)['pass']
def test_source_queue_replay_rejects_duplicate_marker_or_event_identity() -> None:
    payload, request = _population_identity_payload()
    duplicate = copy.deepcopy(payload)
    duplicate_marker = copy.deepcopy(duplicate['events'][1])
    duplicate_marker['seq'] = 21
    duplicate['events'].insert(2, duplicate_marker)
    assert not runner._bag_population_identity(duplicate, request)['pass']

    missing = copy.deepcopy(payload)
    missing['events'].pop(1)
    assert not runner._bag_population_identity(missing, request)['pass']

    duplicate_sequence = copy.deepcopy(payload)
    duplicate_sequence['events'][1]['seq'] = duplicate_sequence['events'][0]['seq']
    assert not runner._bag_population_identity(duplicate_sequence, request)['pass']
def test_zero_row_population_still_requires_positive_unique_event_identities() -> None:
    payload, request = _population_identity_payload()
    payload[runner.ROW_KEY] = []
    assert runner._bag_population_identity(payload, request)['pass']

    duplicate = copy.deepcopy(payload)
    duplicate['events'][1]['seq'] = duplicate['events'][0]['seq']
    assert not runner._bag_population_identity(duplicate, request)['pass']

    nonpositive = copy.deepcopy(payload)
    nonpositive['events'][0]['seq'] = 0
    assert not runner._bag_population_identity(nonpositive, request)['pass']
def test_source_queue_winner_replay_uses_the_exact_escape_token_then_fifo() -> None:
    request = {'bag_records': [
        ('external', 90, 0.0, 100.0, 0, 3, 'external'),
        ('local-fifo', 71, 0.0, 100.0, 1, 3, 'local'),
        ('local-token', 72, 0.0, 100.0, 1, 3, 'local'),
    ]}
    bags = [
        {'runtime_bag_id': 0, 'segment_id': 'external', 'task_id': 90, 'release_time': 0.0, 'deadline': 100.0, 'start': 0, 'goal': 3, 'source': 'external'},
        {'runtime_bag_id': 1, 'segment_id': 'local-fifo', 'task_id': 71, 'release_time': 0.0, 'deadline': 100.0, 'start': 1, 'goal': 3, 'source': 'local'},
        {'runtime_bag_id': 2, 'segment_id': 'local-token', 'task_id': 72, 'release_time': 0.0, 'deadline': 100.0, 'start': 1, 'goal': 3, 'source': 'local'},
    ]
    token_row = {**_row(), 'external_runtime_bag_id': 0, 'local_runtime_bag_id': 2, 'local_task_id': 72, 'local_source_ready_count': 2, 'local_source_uncovered_service_work_seconds': 2.0, 'local_choose_bag_index': 1, 'local_escape_token_runtime_bag_id': 2, 'local_source_enqueued_at': 0.25}
    events = [
        {'seq': 40, 'event': 'LOCAL_QUEUE_UPDATE', 'time': 0.0, 'runtime_bag_id': 1, 'task_id': 71, 'segment_id': 'local-fifo', 'node': 1, 'reason': 'source_enqueue'},
        {'seq': 30, 'event': 'LOCAL_QUEUE_UPDATE', 'time': 0.25, 'runtime_bag_id': 2, 'task_id': 72, 'segment_id': 'local-token', 'node': 1, 'reason': 'source_enqueue'},
        _external_commit_marker(token_row, seq=20),
        {'seq': 1, 'event': 'LOCAL_QUEUE_UPDATE', 'time': 1.0, 'runtime_bag_id': 1, 'task_id': 71, 'segment_id': 'local-fifo', 'node': 1, 'reason': 'source_dequeue'},
    ]
    payload = {'bags': bags, 'events': events, runner.ROW_KEY: [token_row]}
    assert runner._bag_population_identity(payload, request)['pass']

    wrong_winner = copy.deepcopy(payload)
    wrong_winner[runner.ROW_KEY][0].update(local_runtime_bag_id=1, local_task_id=71, local_choose_bag_index=0, local_source_enqueued_at=0.0)
    assert not runner._bag_population_identity(wrong_winner, request)['pass']

    absent_token_falls_back_to_fifo = copy.deepcopy(wrong_winner)
    absent_token_falls_back_to_fifo[runner.ROW_KEY][0]['local_escape_token_runtime_bag_id'] = 99
    assert runner._bag_population_identity(absent_token_falls_back_to_fifo, request)['pass']

    wrong_count = copy.deepcopy(payload)
    wrong_count[runner.ROW_KEY][0]['local_source_ready_count'] = 1
    assert not runner._bag_population_identity(wrong_count, request)['pass']
    wrong_age = copy.deepcopy(payload)
    wrong_age[runner.ROW_KEY][0]['oldest_local_wait_age_seconds'] = 0.5
    assert not runner._bag_population_identity(wrong_age, request)['pass']

    invalid_token = _row()
    invalid_token['local_escape_token_runtime_bag_id'] = -2
    with pytest.raises(ValueError, match='frozen V3R4 invariants'):
        runner.normalize_numeric_rows(_case().case_id, [invalid_token], {1: 1.0})
def test_sparse_distant_fixture_potential_uses_frozen_node_ids(tmp_path: Path) -> None:
    binary = tmp_path / 'unused.pyd'
    binary.write_bytes(b'fixture')
    request = runner._distant_request(_case(), binary)
    assert [row[0] for row in request['node_records'][-3:]] == [10, 11, 12]
    assert request['storage_source_nodes'] == [0, 10]
    assert len(request['heuristic_time']) == 13
def test_distant_prefix_ignores_only_global_identity_not_behavior() -> None:
    left = {'decisions': [{'decision_id': 1, 'scenario': 'base', 'event_time': 1.0, 'current_node': 1, 'selected_next': 2, 'metadata': {'scenario': 'base', 'arrive_event_seq': 8, 'decision_ordinal': 3, 'priority_enqueue_sequence': 4, 'kept': 4}}], 'hold_attempts': [{'decision_id': 'base:1', 'event_time': 1.0, 'current_node': 0, 'candidate_next_nodes': [1], 'candidate_records': [{'next_node': 1, 'shield_reason': 'busy'}], 'rule_reason': 'busy', 'metadata': {'scenario': 'base', 'arrive_event_seq': 8, 'decision_ordinal': 3, 'priority_enqueue_sequence': 4, 'kept': 5}}], 'events': [{'seq': 9, 'time': 1.0, 'node': 1, 'event': 'X'}], runner.ROW_KEY: []}
    right = {'decisions': [{'decision_id': 99, 'scenario': 'distant', 'event_time': 1.0, 'current_node': 1, 'selected_next': 2, 'metadata': {'scenario': 'distant', 'arrive_event_seq': 80, 'decision_ordinal': 30, 'priority_enqueue_sequence': 40, 'kept': 4}}], 'hold_attempts': [{'decision_id': 'distant:9', 'event_time': 1.0, 'current_node': 0, 'candidate_next_nodes': [1], 'candidate_records': [{'next_node': 1, 'shield_reason': 'busy'}], 'rule_reason': 'busy', 'metadata': {'scenario': 'distant', 'arrive_event_seq': 80, 'decision_ordinal': 30, 'priority_enqueue_sequence': 40, 'kept': 5}}], 'events': [{'seq': 90, 'time': 1.0, 'node': 1, 'event': 'X'}], runner.ROW_KEY: []}
    assert runner._prefix(left, 50.0, node=1, semantic=True) == runner._prefix(right, 50.0, node=1, semantic=True)
    right['decisions'][0]['selected_next'] = 3
    assert runner._prefix(left, 50.0, node=1, semantic=True) != runner._prefix(right, 50.0, node=1, semantic=True)
    right['decisions'][0]['selected_next'] = 2
    right['hold_attempts'][0]['rule_reason'] = 'changed'
    assert runner._prefix(left, 50.0, node=1, semantic=True) != runner._prefix(right, 50.0, node=1, semantic=True)
def test_native_proof_is_parsed_only_from_executed_stdout_and_binds_sources(tmp_path: Path) -> None:
    executable, nested, binary = (tmp_path / 'proof.exe', tmp_path / 'nested.exe', tmp_path / 'g32.pyd')
    executable.write_bytes(b'exe'); nested.write_bytes(b'nested'); binary.write_bytes(b'pyd')
    build_head = 'b' * 40
    proof = {'schema_id': runner.NATIVE_PROOF_SCHEMA, 'test_id': runner.NATIVE_PROOF_TEST_ID, 'build_head': build_head, **{key: True for key in runner.NATIVE_PROOF_ASSERTIONS}}
    nested_proof = {'schema_id': runner.NESTED_PROOF_SCHEMA, 'test_id': runner.NESTED_PROOF_TEST_ID, 'build_head': build_head, runner.NESTED_PROOF_ASSERTION: True}
    def fake_process(command: list[str], **_kwargs: Any) -> Any:
        value, prefix = (nested_proof, runner.NESTED_PROOF_PREFIX) if Path(command[0]) == nested else (proof, runner.NATIVE_PROOF_PREFIX)
        return SimpleNamespace(returncode=0, stdout='noise\n' + prefix + json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n', stderr='')
    result = runner.run_native_proof(executable, binary, nested_executable=nested, process_runner=fake_process, expected_executable=executable, expected_nested_executable=nested, build_head_reader=lambda _path: build_head)
    assert result['pass'] and result['executable_sha256'] == hashlib.sha256(b'exe').hexdigest()
    assert result['nested_executable_sha256'] == hashlib.sha256(b'nested').hexdigest() and result['nested_exit_code'] == 0
    assert result['g32_binary_sha256'] == hashlib.sha256(b'pyd').hexdigest()
    assert result['build_head'] == result['proof_build_head'] == result['nested_proof_build_head'] == build_head and result['nested_proof'] == nested_proof
    assert result['source_bundle']['files']
    assert any((row['path'] == 'cpp/tests/test_event_driven_junction.cpp' for row in result['source_bundle']['files']))
    def drifting_process(command: list[str], **_kwargs: Any) -> Any:
        value, prefix = (nested_proof, runner.NESTED_PROOF_PREFIX) if Path(command[0]) == nested else (proof, runner.NATIVE_PROOF_PREFIX)
        if Path(command[0]) == executable:
            executable.write_bytes(b'replaced-after-execution')
        return SimpleNamespace(returncode=0, stdout=prefix + json.dumps(value) + '\n', stderr='')
    drifted = runner.run_native_proof(executable, binary, nested_executable=nested, process_runner=drifting_process, expected_executable=executable, expected_nested_executable=nested, build_head_reader=lambda _path: build_head)
    assert not drifted['pass']
    assert next(gate for gate in drifted['gates'] if gate['name'] == 'native_proof_executable_unchanged')['pass'] is False
@pytest.mark.parametrize(
    'payload,match',
    [
        ('{"schema_id":"one","schema_id":"two"}', 'duplicate JSON object key'),
        ('{"value":NaN}', 'non-finite JSON constant'),
    ],
)
def test_native_proof_stdout_requires_strict_json(payload: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        runner._parse_prefixed_stdout(runner.NATIVE_PROOF_PREFIX + payload, runner.NATIVE_PROOF_PREFIX)
def test_native_proof_rejects_unregistered_path_before_process_start(tmp_path: Path) -> None:
    executable, registered, nested, binary = (tmp_path / 'wrong.exe', tmp_path / 'registered.exe', tmp_path / 'nested.exe', tmp_path / 'g32.pyd')
    for path in (executable, registered, nested, binary):
        path.write_bytes(path.name.encode('ascii'))
    called = False
    def must_not_run(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError('process must not start')
    with pytest.raises(ValueError, match='registered paths'):
        runner.run_native_proof(executable, binary, nested_executable=nested, process_runner=must_not_run, expected_executable=registered, expected_nested_executable=nested)
    assert called is False
def test_cross_binary_off_uses_four_isolated_binary_workers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    g31, g32 = (tmp_path / 'g31.pyd', tmp_path / 'g32.pyd')
    g31.write_bytes(b'g31')
    g32.write_bytes(b'g32')
    monkeypatch.setattr(runner, 'G31_BINARY_SHA256', hashlib.sha256(b'g31').hexdigest())
    calls = []
    def worker(request: Any, binary: Path) -> dict[str, Any]:
        calls.append(binary)
        return {'ordinary_request_sha256': runner.ordinary_request_sha256(request), 'ordinary': {'same': 'hash'}, 'accounting': {'same': 'accounting'}, 'binary_sha256': runner.file_sha256(binary), 'extension_absent': True}
    result = runner.evaluate_cross_binary_off(runner.build_request(_case(), mode='off')[0], g32, g31_binary=g31, worker=worker, expected_g31_binary=g31)
    assert result['pass'] and calls == [g31, g32, g32, g32]
def test_cross_binary_off_rejects_hidden_g32_extension_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    g31, g32 = (tmp_path / 'g31.pyd', tmp_path / 'g32.pyd')
    g31.write_bytes(b'g31')
    g32.write_bytes(b'g32')
    monkeypatch.setattr(
        runner,
        'G31_BINARY_SHA256',
        hashlib.sha256(b'g31').hexdigest(),
    )
    calls = 0
    def worker(request: Any, binary: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            'ordinary_request_sha256': runner.ordinary_request_sha256(request),
            'ordinary': {'same': 'hash'},
            'accounting': {'same': 'accounting'},
            'binary_sha256': runner.file_sha256(binary),
            'extension_absent': calls != 4,
        }
    result = runner.evaluate_cross_binary_off(
        runner.build_request(_case(), mode='off')[0],
        g32,
        g31_binary=g31,
        worker=worker,
        expected_g31_binary=g31,
    )
    absence = next(
        gate
        for gate in result['gates']
        if gate['name'] == 'cross_binary_exact_off_extension_absent'
    )
    assert result['pass'] is False and absence['pass'] is False
def test_ordinary_projection_covers_independent_deterministic_telemetry() -> None:
    payload = _payload()
    payload.update(hold_attempts=[], junction_state=[], credit_events=[])
    baseline = runner.ordinary_payload_hashes(payload)
    changed = json.loads(json.dumps(payload))
    changed['credit_events'].append({'credit_id': 1})
    assert runner.ordinary_payload_hashes(changed) != baseline
    changed = json.loads(json.dumps(payload))
    changed['summary']['runtime_seconds'] = 999.0
    assert runner.ordinary_payload_hashes(changed) == baseline
    changed = json.loads(json.dumps(payload))
    changed['summary']['completed_count'] = 99
    assert runner.ordinary_payload_hashes(changed) != baseline
def _identification_primary_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases, pairs = ([], [])
    for case in runner.identification_cases():
        manifest = runner.identification_case_manifest(case)
        cases.append({
            **{key: manifest[key] for key in ('case_id', 'service_seconds', 'bag_count', 'flow_pattern', 'replica')},
            'join_status': runner.JOINED,
            'census_partition_pass': True,
        })
        for pair_index, value in enumerate(manifest['expected_x_insert_seconds']):
            pairs.append({
                'case_id': case.case_id,
                'primary': True,
                'status': runner.JOINED,
                'X_insert': value,
                'Y_realized': value,
                'local_runtime_bag_id': 2 * pair_index,
                'external_runtime_bag_id': 2 * pair_index + 1,
            })
    return cases, pairs
def _gate_map(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {gate['name']: gate for gate in result['gates']}
def test_frozen_statistics_ties_bootstrap_percentile_and_wilson() -> None:
    assert runner.spearman([1.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == pytest.approx(0.8660254037844387)
    assert runner.percentile([0.0, 10.0], 0.25) == pytest.approx(2.5)
    assert runner.case_block_bootstrap({'a': -1.0, 'b': 1.0, 'c': 2.0}, draws=32) == {'point': 2.0 / 3.0, 'lower_2p5': -1.0 / 3.0, 'seed': runner.BOOTSTRAP_SEED, 'draws': 32}
    assert runner.wilson_interval(18, 24) == pytest.approx((0.55100555994846, 0.8800063377140499))
def test_identification_primary_accepts_exact_24_rho_one_cases_and_rejects_unknown_pair() -> None:
    cases, pairs = _identification_primary_fixture()
    baseline = runner.evaluate_identification_primary(pairs, cases, draws=32)
    assert baseline['pass'] is True
    assert baseline['primary_pair_count'] == 72
    assert baseline['unique_primary_bag_count'] == 144
    assert len(baseline['directional_cases']) == 24
    assert all(row['rho'] == pytest.approx(1.0) for row in baseline['directional_cases'])
    assert all(row['distinct_x'] == row['distinct_y'] == 3 for row in baseline['case_diagnostics'])

    unknown = [*pairs, {**pairs[0], 'case_id': 'unknown-identification-case'}]
    rejected = runner.evaluate_identification_primary(unknown, cases, draws=32)
    population_gate = _gate_map(rejected)['primary_pair_case_population']
    assert rejected['pass'] is False
    assert population_gate == {
        'name': 'primary_pair_case_population',
        'pass': False,
        'evidence': ['unknown-identification-case'],
    }
def test_synthetic_formal_runner_and_cli_use_registered_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert runner.FORMAL_EXECUTION_BLOCKED_REASON == ''
    binary = tmp_path / 'g32.pyd'
    binary.write_bytes(b'g32')
    stage0_calls: list[dict[str, Any]] = []
    def stopped_stage0(**kwargs: Any) -> dict[str, Any]:
        stage0_calls.append(kwargs)
        return {'pass': False, 'status': runner.STAGE0_NO_GO, 'gates': []}
    monkeypatch.setattr(runner, 'run_stage0', stopped_stage0)
    monkeypatch.setattr(runner, 'run_stage1', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('Stage1 must remain gated by Stage0')))
    result = runner.run_campaign(
        executor=lambda **_request: {},
        g32_binary=binary,
        identity_runner=lambda: {'pass': True, 'head': 'a' * 40, 'gates': []},
    )
    assert result['decision'] == runner.NO_GO
    assert len(stage0_calls) == 1
    assert stage0_calls[0]['g32_binary'] == binary.resolve()
    assert stage0_calls[0]['expected_binary_sha256'] == runner.file_sha256(binary)

    cli_calls: list[dict[str, Any]] = []
    writes: list[tuple[Path, Path]] = []
    monkeypatch.setattr(runner, '_default_g32_binary', lambda: binary)
    monkeypatch.setattr(runner, 'run_campaign', lambda **kwargs: cli_calls.append(kwargs) or {'decision': runner.NO_GO})
    monkeypatch.setattr(runner, 'write_evidence', lambda _result, *, json_path, markdown_path: writes.append((json_path, markdown_path)))
    json_path, markdown_path = (tmp_path / 'synthetic.json', tmp_path / 'synthetic.md')
    exit_code = runner.main(['--output-json', str(json_path), '--output-md', str(markdown_path)])
    assert exit_code == 2
    assert len(cli_calls) == 1
    assert cli_calls[0]['executor'] is runner.cpp_executor
    assert cli_calls[0]['g32_binary'] == binary
    assert writes == [(json_path, markdown_path)]
def test_stage0_failure_strictly_prevents_stage1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / 'g32.pyd'
    binary.write_bytes(b'g32')
    monkeypatch.setattr(runner, 'run_stage0', lambda **_kwargs: {'pass': False, 'status': runner.STAGE0_NO_GO, 'gates': []})
    monkeypatch.setattr(runner, 'run_stage1', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('must not run')))
    clean = lambda: {'pass': True, 'head': 'a' * 40, 'gates': []}
    result = runner.run_campaign(executor=lambda **_request: {}, g32_binary=binary, identity_runner=clean, _test_only=True)
    assert result['stage1'] is None and result['decision'] == runner.NO_GO
def test_synthetic_success_is_nanning_pending_and_never_authorizes_p1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / 'g32.pyd'; binary.write_bytes(b'g32')
    monkeypatch.setattr(runner, 'run_stage0', lambda **_kwargs: {'pass': True, 'status': runner.STAGE0_PASS, 'gates': []})
    monkeypatch.setattr(runner, 'run_stage1', lambda **_kwargs: {'pass': True, 'status': 'V3R11_STAGE1_PASS', 'gates': []})
    result = runner.run_campaign(executor=lambda **_request: {}, g32_binary=binary, identity_runner=lambda: {'pass': True, 'head': 'a' * 40, 'gates': []}, _test_only=True)
    assert result['decision'] == runner.SYNTHETIC_PASS != runner.FINAL_GO
    assert result['p1_review_authorized'] is False and result['nanning_p0_status'] == 'PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER'
    assert 'final_go_label' not in result and 'final_go_label' not in runner.evidence_skeleton()
    json.dumps(result, allow_nan=False)
def test_stage1_status_tracks_post_checkpoint_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / 'g32.pyd'; binary.write_bytes(b'A')
    monkeypatch.setattr(runner, 'run_stage0', lambda **_kwargs: {'pass': True, 'status': runner.STAGE0_PASS, 'gates': []})
    def drift_after_stage1(**_kwargs: Any) -> dict[str, Any]:
        binary.write_bytes(b'B')
        return {'pass': True, 'status': 'V3R11_STAGE1_PASS', 'gates': []}
    monkeypatch.setattr(runner, 'run_stage1', drift_after_stage1)
    result = runner.run_campaign(executor=lambda **_request: {}, g32_binary=binary, identity_runner=lambda: {'pass': True, 'head': 'a' * 40, 'gates': []}, _test_only=True)
    assert not result['stage1']['pass'] and result['stage1']['status'] == 'NO_GO_V3R11_STAGE1_CONTRACT'
    assert result['decision'] == runner.NO_GO
def test_campaign_freezes_binary_before_stage0_and_blocks_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / 'g32.pyd'; binary.write_bytes(b'A')
    frozen = hashlib.sha256(b'A').hexdigest()
    def drift(**kwargs: Any) -> dict[str, Any]: assert kwargs['expected_binary_sha256'] == frozen; binary.write_bytes(b'B'); return {'pass': True, 'status': runner.STAGE0_PASS, 'gates': []}
    monkeypatch.setattr(runner, 'run_stage0', drift)
    monkeypatch.setattr(runner, 'run_stage1', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('must not run')))
    result = runner.run_campaign(executor=lambda **_request: {}, g32_binary=binary, identity_runner=lambda: {'pass': True, 'head': 'a' * 40, 'gates': []}, _test_only=True)
    assert result['stage1'] is None and result['decision'] == runner.NO_GO and result['g32_binary_sha256'] == frozen
    assert not next(item for item in result['stage0']['gates'] if item['name'] == 'g32_binary_unchanged_through_stage0')['pass']
    json.dumps(result, allow_nan=False)
@pytest.mark.parametrize(('field', 'value', 'expected'), [(None, None, True), (runner.NS + 'observation_stored_count', 2, False), (runner.NS + 'trace_sidecar_accounted_bytes', 1, False)])
def test_stage0_repeat_binds_all_namespaced_state_and_reaudits(field: str | None, value: Any, expected: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / 'g32.pyd'; binary.write_bytes(b'g32'); digest = runner.file_sha256(binary)
    baseline, repeated, row, joined = (_repeat_ready_payload(), _repeat_ready_payload(), _row(), {'status': runner.JOINED, 'pairs': []})
    if field is not None: repeated['summary'][field] = value
    def fake_case(_case: Any, *, j2: bool=False, **_kwargs: Any) -> dict[str, Any]: return {'rows': [_row(path=2 if j2 else 1)], 'off': baseline, 'shadow': baseline, 'join': joined}
    def fake_summary(case: Any, _result: Any) -> dict[str, Any]: return {'hard_gate_pass': True, 'negative_control': case.flow_pattern in runner.NEGATIVE_CONTROLS, 'admitted_row_count': 0 if case.flow_pattern in runner.NEGATIVE_CONTROLS else 1, 'loaded_cpp_binary_sha256': digest}
    repeat_metadata: list[dict[str, Any]] = []
    def fake_extract(*_args: Any, metadata: Mapping[str, Any] | None=None, **_kwargs: Any) -> list[dict[str, Any]]:
        repeat_metadata.append(dict(metadata or {}))
        return [row]
    runs = {'g31_parent': {'binary_sha256': runner.G31_BINARY_SHA256}, **{key: {'binary_sha256': digest} for key in ('g32_omitted', 'g32_explicit', 'g32_repeated')}}
    fixture = {'pass': True, 'rows': [], 'pairs': [], 'off_ordinary_hashes': {}, 'shadow_ordinary_hashes': {}}
    patches = {'run_case': fake_case, 'summarize_case': fake_summary, 'evaluate_cross_binary_off': lambda *_args, **_kwargs: {'pass': True, 'gates': [], 'runs': runs}, 'extract_rows': fake_extract, 'build_service_episodes': lambda *_args, **_kwargs: [], 'join_v3r2_outcomes': lambda *_args, **_kwargs: joined, '_probe_audit': lambda *_args, **_kwargs: fixture, '_map2_stage0': lambda *_args, **_kwargs: {**fixture, 'gates': []}}
    for name, replacement in patches.items(): monkeypatch.setattr(runner, name, replacement)
    proof = lambda *_args, **_kwargs: {'pass': True, 'gates': [], 'g32_binary_sha256': digest, 'build_head': 'a' * 40}
    result = runner.run_stage0(executor=lambda **_request: repeated, g32_binary=binary, expected_binary_sha256=digest, proof_runner=proof)
    repeat_gates = [item for item in result['gates'] if item['name'] == 'shadow_repeat_exact']; assert repeat_gates, result
    repeat_gate = repeat_gates[0]
    assert repeat_gate['pass'] is expected and result['pass'] is expected and result['status'] == (runner.STAGE0_PASS if expected else runner.STAGE0_NO_GO); json.dumps(result, allow_nan=False)
    assert repeat_metadata == [{'cohort': 'safety_regression', 'replica': None, 'service_seconds': 1.0, 'bag_count': 8, 'flow_pattern': 'simultaneous_local_first'}]
    assert result['fixtures']['direct']['rows'] and result['fixtures']['map2']['pairs'] == [] and set(result['fixtures']) == {'direct', 'j2', 'external_only', 'local_only', 'repeated_shadow', 'future_a', 'future_b', 'distant', 'map2'}
    assert all({'rows', 'pairs', 'off_ordinary_hashes', 'shadow_ordinary_hashes'} <= set(value) for value in result['fixtures'].values())
    if expected:
        monkeypatch.setattr(runner, '_future_request', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('late fixture failure')))
        partial = runner.run_stage0(executor=lambda **_request: repeated, g32_binary=binary, expected_binary_sha256=digest, proof_runner=proof)
        assert not partial['pass'] and partial['cases'] and partial['fixtures']['direct']['rows'] and partial['fixtures']['j2']['pairs'] == []; json.dumps(partial, allow_nan=False)
        assert repeat_metadata[-1] == repeat_metadata[0]
@pytest.mark.parametrize(('diff_path', 'status', 'flags'), [('scripts/eval/run_g4irsf32_v3r2_external_commit_local_virtual_shadow.py', ' M scripts/eval/run_g4irsf32_v3r2_external_commit_local_virtual_shadow.py\n', (False, True)), ('scripts/eval/g4irsf31_map_adapter.py', '', (True, False))])
def test_implementation_identity_fails_closed_on_dirty_or_old_adapter_only_diff(diff_path: str, status: str, flags: tuple[bool, bool]) -> None:
    calls = 0
    def fake(command: list[str], **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if command[1:3] == ['rev-parse', 'HEAD']:
            return SimpleNamespace(returncode=0, stdout='a' * 40 + '\n', stderr='')
        if command[1:3] == ['merge-base', '--is-ancestor']:
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if command[1:3] == ['diff', '--name-only']:
            return SimpleNamespace(returncode=0, stdout=diff_path + '\n', stderr='')
        return SimpleNamespace(returncode=0, stdout=status, stderr='')
    result = runner.implementation_identity(command_runner=fake)
    assert calls == 4 and (not result['pass'])
    assert (bool(result['unexpected_changed_paths']), bool(result['dirty_source_paths'])) == flags and result['head'] == 'a' * 40
def test_atomic_evidence_and_unexecuted_report_never_claim_go(tmp_path: Path) -> None:
    skeleton = runner.evidence_skeleton()
    json_path, md_path = (tmp_path / 'evidence.json', tmp_path / 'evidence.md')
    runner.write_evidence(skeleton, json_path=json_path, markdown_path=md_path)
    json_before, md_before = json_path.read_bytes(), md_path.read_bytes()
    assert json.loads(json_path.read_text(encoding='utf-8'))['decision'] is None
    assert 'V3R11_NOT_EXECUTED' in md_path.read_text(encoding='utf-8')
    with pytest.raises(FileExistsError, match='append-only evidence path'):
        runner.write_evidence({'status': 'replacement'}, json_path=json_path, markdown_path=md_path)
    assert json_path.read_bytes() == json_before
    assert md_path.read_bytes() == md_before
