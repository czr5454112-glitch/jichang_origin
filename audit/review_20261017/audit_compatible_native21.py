"""Combine separately closed native campaigns without manufacturing new raw."""
from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path
import statistics

import audit_compatible_native as first9


def audit(original, remaining):
    base = first9.audit(original)
    assert base['all9_execution_closed'] and base['all9_observed_componentwise_protected']
    first_matrix = first9.read(original / 'execution_matrix.json')
    assert all(first_matrix[key]['process']['status'] == 'exited'
        and first_matrix[key]['process']['exitcode'] == 0 for key in base['rows'])
    plan = first9.read(remaining / 'preregistered_protocol.json')
    assert plan['phase'] == 'remaining12' and len(plan['branch_order']) == 12
    assert plan['hard_cell_seconds'] == 60. and plan['hard_group_seconds'] == 780.
    assert first9.sha(remaining / 'preregistered_protocol.json') == first9.read(remaining / 'prepare_receipt.json')['plan_sha256']
    prior = plan['prior_first9']
    assert Path(prior['campaign_reference']['path']).resolve() == (original / 'preregistered_protocol.json').resolve()
    for path, digest in prior['evidence_sha256'].items():
        assert first9.sha(Path(path)) == digest, path
    original_plan = first9.read(original / 'preregistered_protocol.json')
    assert set(original_plan['source_sha256']) == set(plan['source_sha256'])
    changed_sources = [path for path, digest in original_plan['source_sha256'].items()
        if plan['source_sha256'][path] != digest]
    assert changed_sources == prior['source_change_allowlist']
    matrix = first9.read(remaining / 'execution_matrix.json')
    rows = copy.deepcopy(base['rows'])
    raw_references = dict(base['source']['raw_sha256'])
    unresolved = {}
    for key in plan['branch_order']:
        cell = matrix[key]
        if cell['status'] != 'assessed':
            unresolved[key] = {'status': cell['status'], 'process': cell.get('process')}
            continue
        assert cell['process']['status'] == 'exited' and cell['process']['exitcode'] == 0
        assert cell['process']['wall_seconds'] <= 60.
        assert cell['run_acceptance_status'] == 'closed_run_acceptance_passed'
        raw_path = remaining / (key + '.raw.json.gz')
        assert first9.sha(raw_path) == cell['raw_artifact']['sha256']
        raw_references[str(raw_path.resolve())] = first9.sha(raw_path)
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        actual = {job['business_bag_id']: job['completed_at'] for job in raw['result']['jobs']}
        assert set(actual) == set(first9.JOBS)
        assert actual == cell['summary']['completion'] == raw['summary']['completion']
        baseline = base['rows'][key.split('/')[0] + '/incumbent']['actual_completion']
        effective = raw['summary']['retrospective_effective_vector']
        owners = {}
        for owner in first9.OWNERS:
            initial = raw['initial_owners'][owner]
            selected = initial['selection']
            compatible = initial['compatibility']
            provider = selected['provider_evidence']
            binding = provider['source_binding']
            proof = binding['before_close']['proof_binding']
            forecasts = [row for row in provider['rows'] if row['action'] == effective]
            assert len(forecasts) == 1 and len(provider['rows']) == 32 and len(provider['groups']) == 16
            assert compatible['selected_index'] in selected['accounting']['query_indices']
            assert compatible['selected_action'] == initial['selected_action']
            owners[owner] = {'original_selection_index': selected['selected_index'],
                'compatible_selection_index': compatible['selected_index'],
                'original_proposal_rejected': compatible['original_proposal_rejected'],
                'selected_action': initial['selected_action'],
                'effective_vector_prediction': forecasts[0].get('completion'),
                'actual_minus_effective_prediction': first9.compare(actual, forecasts[0].get('completion') or {}),
                'provider_status': provider['status'], 'provider_counts': provider['counts'],
                'all_32_predictions_known': all(row.get('completion') is not None for row in provider['rows']),
                'proof_65_uses_verified': proof['cold_original_proof_calls'] == 1 and proof['proof_uses'] == 65,
                'binding_close_verified': binding['status'] == 'closed_complete65' and binding['close_completed'] is True,
                'logical_selector_query_count': selected['accounting']['queried_indices'],
                'logical_selector_query_indices': selected['accounting']['query_indices'],
                'provider_charged_candidates': selected['accounting']['provider_charged_candidate_denominator'],
                'provider_measured_through_seal_seconds': selected['accounting']['provider_measured_through_seal_seconds'],
                'initial_call_wall_ms': initial['call_wall_ms'],
                'initial_call_within_100ms': initial['call_wall_ms'] <= 100.,
                'initial_call_cost_scope': initial['cost_scope'],
                'filter_wall_ns': compatible['filter_wall_ns'],
                'admissibility_rows_examined': compatible['admissibility_rows_examined'],
                'diagnostic_rows_examined': compatible['diagnostic_rows_examined'],
                'additional_model_predictions': compatible['additional_model_predictions'],
                'additional_selector_queries': compatible['additional_selector_queries'],
                'protected_indices_excluded_by_contract': compatible['protected_indices_excluded_by_public_contract'],
                'native_request_id': initial['native_request_id'], 'native_default_no_command': initial['native_default_no_command']}
        stable = all(call['request'] == raw['outbox'][call['request']['request_id']]['request'] for call in raw['calls'])
        baseline_vector = base['rows'][key.split('/')[0] + '/incumbent']['effective_vector']
        physical = {request_id: {'kind': entry['kind'], 'request': entry['request'],
            'terminal': entry['terminal'], 'ack': entry.get('ack'), 'creation': raw['request_creations'].get(request_id)}
            for request_id, entry in raw['outbox'].items() if entry['kind'] in ('transfer', 'route')}
        rows[key] = {'actual_completion': actual, 'matched_native_incumbent_completion': baseline,
            'actual_vs_matched_incumbent': first9.compare(actual, baseline),
            'effective_vector': effective,
            'effective_vector_equals_B_witness': effective == raw['initial_owners']['B']['selected_action'],
            'A_incumbent_components_preserved': all(effective[field] == baseline_vector[field]
                for field in ('initial_action', 'return_delay')),
            'conditional_component_domain_verified': raw['summary']['conditional_component_domain_verified'],
            'owner_details': owners, 'physical_requests': physical,
            'all_same_id_retry_payloads_stable': stable,
            'all_outbox_requests_terminal': all(entry['terminal'] for entry in raw['outbox'].values()),
            'native_route_and_transfer_execution_verified': all(raw['summary'][field] for field in
                ('required_transfer_lineages_received', 'all_routes_updated', 'chosen_routes_match_executed_edges')),
            'process_wall_seconds': cell['process']['wall_seconds'], 'worker_observation_ms': cell['worker_observation_ms'],
            'branch_preexport_wall_ms': raw['branch_preexport_wall_ms'], 'complete_request_100ms_certified': False,
            'rolling_reestimation_executed': False, 'native_hard_reservation_granted': False}
    owner_rows = [owner for row in rows.values() for owner in row['owner_details'].values()]
    costs = [owner['initial_call_wall_ms'] for owner in owner_rows]
    complete = len(rows) == 21 and not unresolved
    return {'schema': 'g31.compatible_native.two_campaign21.raw_audit.v1',
        'scope': 'Two distinct actual campaigns, immutable raw references only; no manufactured/copy-filled native observations.',
        'first9_campaign': str(original.resolve()), 'remaining12_campaign': str(remaining.resolve()),
        'source_change_allowlist': changed_sources,
        'core_physics_provider_dispatcher_model_bytes_unchanged': True,
        'first9_receipt': first9.read(original / 'receipt.json'), 'remaining12_receipt': first9.read(remaining / 'receipt.json'),
        'source': {'audit_script_sha256': first9.sha(Path(__file__)),
            'first9_audit_library_sha256': first9.sha(Path(first9.__file__)), 'raw_sha256': raw_references},
        'registered_cell_denominator': 21, 'assessed_cell_count': len(rows), 'unresolved_remaining_cells': unresolved,
        'all21_execution_closed': complete,
        'all21_observed_componentwise_protected': complete and all(row['actual_vs_matched_incumbent']['strict_componentwise_not_worse'] for row in rows.values()),
        'all21_structural_witness_verified': complete and all(row['effective_vector_equals_B_witness']
            and row['A_incumbent_components_preserved'] and row['conditional_component_domain_verified'] for row in rows.values()),
        'all42_request_bindings_closed_complete65': complete and all(owner['binding_close_verified'] and owner['proof_65_uses_verified'] for owner in owner_rows),
        'all42_effective_predictions_exact_native_endpoints': complete and all(owner['actual_minus_effective_prediction']['all_exactly_equal'] for owner in owner_rows),
        'all_native_execution_lineages_verified': complete and all(row['native_route_and_transfer_execution_verified']
            and row['all_same_id_retry_payloads_stable'] for row in rows.values()),
        'initial_call_wall_ms': {'count': len(costs), 'minimum': min(costs), 'median': statistics.median(costs), 'maximum': max(costs),
            'within100ms_count': sum(cost <= 100. for cost in costs),
            'scope': 'Initial call only; enclosing request additionally includes publication, later ACKs/physical descendants, serialization and process/closure costs.'},
        'observations_are_not_general_protection_certification': True,
        'T2_fault_tapes_executed': False, 'full_joint_R1_R2_domain_restored': False,
        'complete_request_100ms_certified': False, 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--first9', type=Path, required=True)
    parser.add_argument('--remaining12', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'immutable_audit_output'
    result = audit(args.first9, args.remaining12)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'source')}, indent=2))
