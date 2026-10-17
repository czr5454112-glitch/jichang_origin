"""Read-only audit of actual first-nine native evidence, without model calls."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
OWNERS = ('A', 'B')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(actual, baseline):
    known = all(type(actual.get(job)) in (float, int)
        and type(baseline.get(job)) in (float, int) for job in JOBS)
    return {'all_five_known': known,
        'per_job_delta': {job: actual[job] - baseline[job] for job in JOBS} if known else None,
        'strict_componentwise_not_worse': all(actual[job] <= baseline[job] for job in JOBS) if known else None,
        'strictly_better_jobs': [job for job in JOBS if actual[job] < baseline[job]] if known else [],
        'strictly_worse_jobs': [job for job in JOBS if actual[job] > baseline[job]] if known else [],
        'all_exactly_equal': all(actual[job] == baseline[job] for job in JOBS) if known else None,
        'tolerance': 0}


def audit(campaign):
    plan = read(campaign / 'preregistered_protocol.json')
    matrix = read(campaign / 'execution_matrix.json')
    receipt = read(campaign / 'receipt.json')
    assert sha(campaign / 'preregistered_protocol.json') == read(campaign / 'prepare_receipt.json')['plan_sha256']
    loaded = {}
    pins = {}
    unresolved = {}
    for key in plan['branch_order']:
        cell = matrix[key]
        if cell['status'] != 'assessed':
            unresolved[key] = {'status': cell['status'], 'process': cell.get('process'),
                'native_session_attempted': cell.get('native_session_attempted'),
                'business_protection': None}
            continue
        assert cell['run_acceptance_status'] == 'closed_run_acceptance_passed'
        path = campaign / (key + '.raw.json.gz')
        assert sha(path) == cell['raw_artifact']['sha256']
        pins[str(path.resolve())] = sha(path)
        raw = json.loads(gzip.decompress(path.read_bytes()))
        endpoints = {job['business_bag_id']: job['completed_at'] for job in raw['result']['jobs']}
        assert set(endpoints) == set(JOBS)
        assert endpoints == raw['summary']['completion'] == cell['summary']['completion']
        loaded[key] = (cell, raw, endpoints)
    rows = {}
    for key, (cell, raw, actual) in loaded.items():
        baseline = loaded[key.split('/')[0] + '/incumbent'][2]
        effective = raw['summary']['retrospective_effective_vector']
        owner_rows = {}
        for owner in OWNERS:
            initial = raw['initial_owners'][owner]
            selection = initial['selection']
            compatible = initial['compatibility']
            provider = selection['provider_evidence']
            binding = provider['source_binding']
            proof = binding.get('before_close', {}).get('proof_binding', {})
            matching = [row for row in provider['rows'] if row['action'] == effective]
            assert len(matching) == 1
            forecast = matching[0]
            prediction = forecast.get('completion') or {}
            assert compatible['selected_index'] in selection['accounting']['query_indices']
            assert compatible['selected_action'] == initial['selected_action']
            assert len(provider['rows']) == 32
            assert len({row['candidate_index'] for row in provider['rows']}) == 32
            assert len(provider['groups']) == 16
            close_verified = binding['status'] == 'closed_complete65' and binding['close_completed'] is True
            exact_proof_uses = proof.get('cold_original_proof_calls') == 1 and proof.get('proof_uses') == 65
            owner_rows[owner] = {
                'original_selection_index': selection['selected_index'],
                'compatible_selection_index': compatible['selected_index'],
                'original_proposal_rejected': compatible['original_proposal_rejected'],
                'selected_action': initial['selected_action'],
                'effective_vector_prediction_index': forecast['candidate_index'],
                'effective_vector_prediction_status': forecast['status'],
                'effective_vector_prediction': prediction,
                'actual_minus_effective_prediction': compare(actual, prediction),
                'provider_status': provider['status'],
                'all_32_predictions_known': all(row.get('completion') is not None for row in provider['rows']),
                'provider_counts': provider['counts'],
                'proof_65_uses_verified': exact_proof_uses,
                'binding_close_verified': close_verified,
                'copy_metadata_preparation': binding.get('copy_metadata_preparation'),
                'logical_selector_query_count': selection['accounting']['queried_indices'],
                'logical_selector_query_indices': selection['accounting']['query_indices'],
                'provider_charged_candidates': selection['accounting']['provider_charged_candidate_denominator'],
                'provider_measured_through_seal_seconds': selection['accounting']['provider_measured_through_seal_seconds'],
                'initial_call_wall_ms': initial['call_wall_ms'],
                'initial_call_within_100ms': initial['call_wall_ms'] <= 100.,
                'initial_call_cost_scope': initial['cost_scope'],
                'filter_wall_ns': compatible['filter_wall_ns'],
                'admissibility_rows_examined': compatible['admissibility_rows_examined'],
                'diagnostic_rows_examined': compatible['diagnostic_rows_examined'],
                'additional_model_predictions': compatible['additional_model_predictions'],
                'additional_selector_queries': compatible['additional_selector_queries'],
                'protected_indices_excluded_by_contract': compatible['protected_indices_excluded_by_public_contract'],
                'native_request_id': initial['native_request_id'],
                'native_default_no_command': initial['native_default_no_command']}
        physical = {}
        retry_payloads_stable = True
        for request_id, entry in raw['outbox'].items():
            calls = [call for call in raw['calls'] if call['request']['request_id'] == request_id]
            retry_payloads_stable = retry_payloads_stable and all(call['request'] == entry['request'] for call in calls)
            if entry['kind'] in ('transfer', 'route'):
                physical[request_id] = {'kind': entry['kind'], 'request': entry['request'],
                    'terminal': entry['terminal'], 'ack': entry.get('ack'),
                    'call_count': len(calls), 'call_at': [call['at'] for call in calls],
                    'creation': raw['request_creations'].get(request_id)}
        vector_matches_B = effective == raw['initial_owners']['B']['selected_action']
        incumbent_vector = loaded[key.split('/')[0] + '/incumbent'][1]['summary']['retrospective_effective_vector']
        A_components_preserved = all(effective[field] == incumbent_vector[field]
            for field in ('initial_action', 'return_delay'))
        rows[key] = {'actual_completion': actual, 'matched_native_incumbent_completion': baseline,
            'actual_vs_matched_incumbent': compare(actual, baseline),
            'effective_vector': effective, 'effective_vector_equals_B_witness': vector_matches_B,
            'A_incumbent_components_preserved': A_components_preserved,
            'conditional_component_domain_verified': raw['summary']['conditional_component_domain_verified'],
            'owner_details': owner_rows, 'physical_requests': physical,
            'all_same_id_retry_payloads_stable': retry_payloads_stable,
            'all_outbox_requests_terminal': all(entry['terminal'] for entry in raw['outbox'].values()),
            'native_route_and_transfer_execution_verified': all(raw['summary'][field] for field in
                ('required_transfer_lineages_received', 'all_routes_updated', 'chosen_routes_match_executed_edges')),
            'process_wall_seconds': cell['process']['wall_seconds'],
            'worker_observation_ms': cell['worker_observation_ms'],
            'branch_preexport_wall_ms': raw['branch_preexport_wall_ms'],
            'complete_request_100ms_certified': False,
            'rolling_reestimation_executed': False,
            'native_hard_reservation_granted': False}
    return {'schema': 'g31.compatible_native.first9.raw_audit.v1',
        'scope': 'Retrospective evidence audit only; no model call, live query, dispatch, or admission authority.',
        'campaign': str(campaign.resolve()), 'receipt': receipt,
        'source': {'audit_script_sha256': sha(Path(__file__)), 'raw_sha256': pins},
        'all9_execution_closed': len(rows) == 9,
        'assessed_cell_count': len(rows), 'unresolved_first9_cells': unresolved,
        'all9_observed_componentwise_protected': len(rows) == 9 and all(row['actual_vs_matched_incumbent']['strict_componentwise_not_worse'] for row in rows.values()),
        'all9_structural_witness_verified': len(rows) == 9 and all(row['effective_vector_equals_B_witness']
            and row['A_incumbent_components_preserved'] and row['conditional_component_domain_verified'] for row in rows.values()),
        'all18_request_bindings_closed_complete65': len(rows) == 9 and all(owner['binding_close_verified'] and owner['proof_65_uses_verified']
            for row in rows.values() for owner in row['owner_details'].values()),
        'all18_effective_predictions_exact_native_endpoints': len(rows) == 9 and all(owner['actual_minus_effective_prediction']['all_exactly_equal']
            for row in rows.values() for owner in row['owner_details'].values()),
        'all_native_execution_lineages_verified': len(rows) == 9 and all(row['native_route_and_transfer_execution_verified']
            and row['all_same_id_retry_payloads_stable'] for row in rows.values()),
        'observations_are_not_general_protection_certification': True,
        'T2_fault_tapes_executed': False, 'T4_remaining12_executed': False,
        'full_joint_R1_R2_domain_restored': False, 'complete_request_100ms_certified': False,
        'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'immutable_audit_output'
    result = audit(args.campaign)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'source')}, indent=2))
