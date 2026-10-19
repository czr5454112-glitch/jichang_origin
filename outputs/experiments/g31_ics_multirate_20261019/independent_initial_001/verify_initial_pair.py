"""Standard-library-only audit of saved native bytes; never imports project code.

Run after both native branches and their acceptance/parent receipts close.
The report is new and immutable. It is not a native rerun or safety proof.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import traceback

JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def check_reference(item):
    require(sha(item['path']) == item['sha256'], 'reference_byte_mismatch:' + item['path'])
    return item


def audit_archive(plan, base):
    pins, mapping = plan['source_sha256'], plan['source_archive']
    require(set(pins) == set(mapping) and bool(pins), 'source_archive_missing_identity')
    checked = []
    for source, target in mapping.items():
        path = Path(target)
        if not path.is_absolute():
            path = base / path
        require(path.resolve().is_relative_to(base.resolve()), 'archive_outside_registered_output')
        require(sha(path) == pins[source], 'archived_source_byte_mismatch:' + source)
        checked.append({'source': source, 'archive': str(path.resolve()), 'sha256': pins[source]})
    require(len({row['archive'] for row in checked}) == len(checked), 'duplicate_source_archive_path')
    return {'status': 'all_registered_archived_source_bytes_match', 'file_count': len(checked),
        'source_index_sha256': hashlib.sha256(canonical(pins)).hexdigest(), 'checked_files': checked}


def one(rows, label):
    require(len(rows) == 1, 'expected_one_' + label + ':' + str(len(rows)))
    return rows[0]


def audit_branch(pair, branch):
    folder = pair / branch
    native = folder / 'native'
    receipt = read(native / 'receipt.json')
    require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'native_receipt_not_closed:' + branch)
    check_reference(receipt['raw_artifact'])
    raw = json.loads(gzip.decompress(Path(receipt['raw_artifact']['path']).read_bytes()))
    plan = read(native / 'preregistered_protocol.json')
    acceptance = read(native / 'acceptance.json')
    require(acceptance['status'] == 'closed_run_acceptance_passed' and acceptance['active'] is False
            and acceptance['invalid'] == [] and acceptance['branch_keys'] == ['mechanism/incumbent'],
            'actual_acceptance_not_closed:' + branch)
    require(acceptance['run_reference'] == reference(native / 'preregistered_protocol.json'),
            'acceptance_run_identity:' + branch)
    for name in ('contract_reference', 'semantic_reference'):
        check_reference(acceptance[name])
    evidence_count = 0
    for path, expected in acceptance['evidence_sha256'].items():
        require(sha(path) == expected, 'closed_acceptance_evidence_byte_mismatch:' + path)
        evidence_count += 1
    require(raw['native027_acceptance']['runtime_accepted'] is True
            and raw['native027_acceptance']['contract_reference'] == acceptance['contract_reference'],
            'raw_acceptance_contract_mismatch:' + branch)
    archive = audit_archive(plan, native)
    input_path = native / 'inputs/mechanism/incumbent.json'
    require(sha(input_path) == plan['input_file_sha256']['mechanism/incumbent'], 'input_file_digest:' + branch)
    require(canonical(read(input_path)) == canonical(raw['input']), 'actual_input_differs_from_registered:' + branch)
    for source in (raw['input'], raw['result']):
        require(len(source['jobs']) == 5 and len(source['trays']) == 3, 'five_jobs_three_trays:' + branch)
        require({job['business_bag_id'] for job in source['jobs']} == set(JOBS), 'job_identity:' + branch)
        require({tray['tray_id'] for tray in source['trays']} == {'L', 'E', 'P'}, 'tray_identity:' + branch)
    receipts = raw['result']['receipts']
    completion = {}
    for job in raw['result']['jobs']:
        name, at = job['business_bag_id'], job['completed_at']
        require(job['status'] == 'completed' and type(at) is float and math.isfinite(at) and at >= 0.,
                'actual_completed_job:' + name)
        event = one([event for event in receipts if event['event'] == 'UNLOAD_COMPLETE'
            and event['business_bag_id'] == name], 'unload_complete_' + name)
        require(event['time'] == at, 'job_completion_receipt_mismatch:' + name)
        completion[name] = at
    b = raw['initial_owners']['B']
    action, selected = b['selected_action'], b['selection']['selected_index']
    require(canonical(action) == canonical(b['selection']['selected_action'])
            and canonical(action) == canonical(b['selection']['provider_evidence']['rows'][selected]['action'])
            and b['compatibility']['selected_index'] == selected, 'selected_vector_binding:' + branch)
    require(selected in b['selection']['accounting']['query_indices'], 'selected_unqueried:' + branch)
    identity = b['native_request_id']
    calls = [call for call in raw['calls'] if call['request']['request_id'] == identity]
    original = one([call for call in calls if call['retry'] is False], 'actual_initial_B_call')
    request = original['request']
    require(request['earliest_departure'] == action['empty_departure'] and request['owner_id'] == 'B'
            and request['tray_id'] == 'E' and request['source'] == 5 and request['destination'] == 1,
            'actual_B_departure_or_owner_mismatch:' + branch)
    require(canonical(request) == canonical(b['submission']['request'])
            and all(canonical(call['request']) == canonical(request) for call in calls)
            and canonical(request) == canonical(raw['outbox'][identity]['request']), 'initial_command_identity:' + branch)
    initial_delivery = one([event for event in receipts if event['event'] == 'MODULE_REQUEST_DELIVERED'
        and event['tray_id'] == 'E' and event['reason'] == identity], 'initial_request_delivery')
    initial_ack = raw['outbox'][identity]['ack']
    require(initial_ack['status'] in ('received', 'rejected') and initial_ack['delivered_at'] <= 40.
            and initial_ack['delivered_at'] >= initial_delivery['time'], 'delivered_initial_ack:' + branch)
    a = raw['initial_owners']['A']
    require(a['selection']['selected_index'] == 4 and a['native_request_id'] is None
            and a['native_default_no_command'] is True, 'A04_default_has_no_command:' + branch)
    empty_enter = one([event for event in receipts if event['event'] == 'EDGE_ENTER' and event['tray_id'] == 'E'
        and event['from'] == 5 and event['to'] == 1 and event['business_bag_id'] == ''], 'E_empty_edge_enter')
    empty_exit = one([event for event in receipts if event['event'] == 'EDGE_EXIT' and event['tray_id'] == 'E'
        and event['traversal_id'] == empty_enter['traversal_id'] and event['transport_leg_id'] == empty_enter['transport_leg_id']],
        'E_empty_edge_exit')
    received = one([event for event in receipts if event['event'] == 'EMPTY_RECEIVED' and event['tray_id'] == 'E'
        and event['transport_leg_id'] == empty_enter['transport_leg_id']], 'E_empty_received')
    actual_transfer = received['reason']
    require(actual_transfer in raw['outbox'] and raw['outbox'][actual_transfer]['ack']['status'] == 'received',
            'physical_transfer_received_ACK:' + branch)
    load = one([event for event in receipts if event['event'] == 'LOAD_START' and event['business_bag_id'] == 'receiver'],
        'receiver_load_start')
    require(load['tray_id'] == 'E' and empty_enter['time'] < empty_exit['time'] <= received['time'] == load['time']
            and empty_enter['time'] >= raw['outbox'][actual_transfer]['request']['earliest_departure'],
            'physical_E_receiver_lineage:' + branch)
    closed_parent = read(folder / 'receipt.json')
    require(closed_parent['status'] == 'completed_initial_episode'
            and closed_parent['process']['status'] == 'exited' and closed_parent['process']['exitcode'] == 0
            and closed_parent['native_receipt'] == reference(native / 'receipt.json'), 'bounded_parent_not_closed:' + branch)
    return {'branch': branch, 'status': 'verified_from_saved_native_records',
        'raw_reference': receipt['raw_artifact'], 'native_receipt': reference(native / 'receipt.json'),
        'acceptance': {'reference': reference(native / 'acceptance.json'), 'status': acceptance['status'],
            'evidence_files_verified': evidence_count, 'pid': acceptance['pid']},
        'source_archive': archive, 'input_reference': reference(input_path),
        'input_semantic_sha256': hashlib.sha256(canonical(raw['input'])).hexdigest(),
        'job_count': 5, 'tray_count': 3, 'A_selected_index': 4, 'B_selected_index': selected,
        'B_selected_action': action, 'B_queried_indices': b['selection']['accounting']['query_indices'],
        'B_actual_initial_call': original, 'B_initial_request_delivery': initial_delivery,
        'B_initial_call_count_with_protocol_retries': len(calls), 'B_initial_ACK': initial_ack,
        'E_empty_edge_enter': empty_enter, 'E_empty_edge_exit': empty_exit,
        'E_empty_received': received, 'E_actual_transfer_request': raw['outbox'][actual_transfer]['request'],
        'E_actual_transfer_ACK': raw['outbox'][actual_transfer]['ack'], 'receiver_load_start': load,
        'receiver_completed_at': completion['receiver'], 'completion': completion,
        'initial_request_was_actual_received_transfer': actual_transfer == identity,
        'declared_offline_sync': plan['timing_mode'] == 'offline_sync'}


def audit(pair):
    plan = read(pair / 'plan.json')
    campaign_archive = audit_archive(plan, pair)
    for item in [plan['model'], plan['model_copy'], *plan['runtime_references']]:
        check_reference(item)
    branches = [audit_branch(pair, name) for name in ('bridge04', 'learned')]
    before, after = branches
    require(Path(before['input_reference']['path']).read_bytes() == Path(after['input_reference']['path']).read_bytes(),
            'paired_input_file_bytes_differ')
    require(before['input_semantic_sha256'] == after['input_semantic_sha256'], 'paired_actual_input_semantics_differ')
    require(before['source_archive']['source_index_sha256'] == after['source_archive']['source_index_sha256'],
            'paired_native_source_set_or_bytes_differ')
    delta = {job: after['completion'][job] - before['completion'][job] for job in JOBS}
    campaign = read(pair / 'receipt.json')
    require(campaign['status'] == 'completed_initial_selector_campaign', 'parent_campaign_not_closed')
    return {'status': 'passed', 'schema': 'g31.independent.initial_pair_audit.v1',
        'verification_method': 'Standard-library byte/hash and raw record checks; no project import, predictor, native run, or controller assessment reuse.',
        'campaign_plan': reference(pair / 'plan.json'), 'campaign_receipt': reference(pair / 'receipt.json'),
        'campaign_source_archive': campaign_archive, 'branches': branches,
        'paired_input_bytes_equal': True, 'paired_actual_input_semantics_equal': True,
        'paired_native_source_set_and_bytes_equal': True, 'actual_per_job_delta_s': delta,
        'actual_completion_sum_delta_s': sum(after['completion'].values()) - sum(before['completion'].values()),
        'observed_no_job_worse': all(value <= 0. for value in delta.values()),
        'observed_at_least_one_job_better': any(value < 0. for value in delta.values()),
        'comparison_tolerance_s': 0., 'independent_scene_count': 1,
        'universal_protection_proven': False, 'RL_generalization_proven': False,
        'real_async_or_100ms_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.pair.resolve())
    except Exception:
        result = {'status': 'failed_or_incomplete', 'exception': traceback.format_exc()}
    result['verifier'] = reference(__file__)
    with args.report.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key in
        ('status', 'actual_per_job_delta_s', 'observed_no_job_worse', 'exception')}, indent=2))
    raise SystemExit(0 if result['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
