"""Read-only post-run audit. Standard library only; never imports a controller or native binary.

This is an independent artifact, deliberately outside the frozen native source inventory.
Usage: python audit_async.py RUN_DIRECTORY --output NEW_REPORT.json
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

ACTIONS = ('native_default', 'prefer_3', 'prefer_8')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def load_closed(folder):
    folder = Path(folder).resolve()
    raw_path = folder/'raw.json.gz'
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    report, receipt, plan, accepted = (read(folder/name) for name in
        ('worker_report.json', 'receipt.json', 'plan.json', 'acceptance.json'))
    require(receipt['status'] == report['status'] == 'completed_native_branch'
        and receipt['worker_report'] == reference(folder/'worker_report.json')
        and report['raw'] == reference(raw_path) and report['source_exit_pins_passed'] is True,
        'closed_worker_raw_digest_binding')
    require(receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
        and receipt['process']['windows_job_kill_on_close'] is True
        and receipt['process']['child_released_only_after_job_assignment'] is True, 'bounded_actual_native_process')
    require(accepted['status'] == 'closed_run_acceptance_passed' and accepted['active'] is False
        and accepted['invalid'] == [] and accepted['run_reference'] == reference(folder/'plan.json'), 'closed_native_acceptance')
    key = one(plan['branch_order'], 'one_declared_branch')
    require(plan['rows'][key] == raw['specification'] and report['summary'] == raw['summary'], 'declared_raw_branch')
    input_path = folder/'inputs'/(key+'.json')
    require(read(input_path) == raw['input'] and reference(input_path)['sha256'] == plan['input_file_sha256'][key],
        'unchanged_complete_input')
    for source, relative in plan['source_archive'].items():
        archived = (folder/relative).resolve()
        require(archived.is_relative_to(folder)
            and reference(archived)['sha256'] == plan['source_sha256'][source]
            and accepted['evidence_sha256'][source] == plan['source_sha256'][source], 'historical_archived_source_binding')
    if plan.get('original_reference'):
        ref = plan['original_reference']
        require(reference(ref['path']) == ref, 'immutable_paired_reference_file')
        baseline = json.loads(gzip.decompress(Path(ref['path']).read_bytes()))
        require(baseline['input'] == raw['input']
            and baseline['summary']['completion'] == raw['specification']['reference']['completion'], 'paired_original_reference_values')
    return raw, report, receipt


def current_chain(raw, decision):
    now, owner = decision['selected_at'], decision['owner']
    admission, opportunity = decision['current_admission'], decision['opportunity']
    target = opportunity['target']; job = target['business_bag_id']
    require(admission['execution_mode'] == 'protected_current' and admission['fresh_collection'] is True,
        'current_full_guard_required')
    attempt = one([row for row in raw['repeated_attempts'][owner]
        if row['evidence']['collection']['request_id'] == admission['collection_request_id']], 'unique_current_attempt')
    evidence, prediction = attempt['evidence'], attempt['model_report']
    require(evidence['at'] == now and evidence['owner'] == owner and evidence['phase'] == 'cycle_route'
        and digest(evidence) == admission['evidence_sha256']
        and prediction['status'] == 'conditional_current_seed'
        and prediction['seed']['evidence_sha256'] == digest(evidence), 'current_evidence_source_binding')
    sources = prediction['seed']['bundle']['source_records']
    require(len(sources) == 2 and {row['owner'] for row in sources} == {'A', 'B'}
        and all(0 <= now-row['captured_at'] <= .05 and row['captured_at'] <= row['delivered_at'] <= now
            for row in sources), 'actual_current_point05_source_age')
    view = evidence['information']['raw_endpoints']['view']
    require(view['owner_id'] == owner and view['now'] == now
        and target == one([row for row in view['trays'] if row['tray_id'] == target['tray_id']], 'current_native_tray')
        and opportunity['generation'] == target['generation'] and opportunity['traversal_id'] == target['traversal_id'],
        'current_native_generation_traversal_binding')
    root = one([row for row in raw['owner_activation_admissions'] if row['root_id'] == admission['owner_root']],
        'unique_actual_owner_activation')
    require(root['owner'] == owner and root['accepted_at'] == now and admission['at'] == now,
        'current_owner_epoch_binding')
    public = decision['observation']; visible = dict(view)
    visible['jobs'] = [row for row in view['jobs'] if row['arrival'] <= now and row['status'] != 'unreleased']
    require(public['owner'] == owner and public['at'] == now and public['opportunity'] == opportunity
        and public['local_view'] == visible and public['own_outbox'] == evidence['own_outbox'], 'legal_pre_submit_observation')
    complete_ids = {row['business_bag_id'] for row in raw['input']['jobs']}
    baseline = raw['specification']['reference']['completion']
    require(set(baseline) == complete_ids and digest(raw['specification']['reference']) == admission['reference_sha256'],
        'immutable_full_job_reference')
    require(set(prediction['candidate_results']) == set(ACTIONS)
        and {row['action_id'] for row in decision['candidate_mask']} == set(ACTIONS), 'full_registered_candidate_evaluation')
    masks = {}
    for row in decision['candidate_mask']:
        action = row['action_id']; candidate = prediction['candidate_results'][action]
        completion = candidate['completion']
        require(candidate['status'] == 'conditional_prediction' and set(completion) == complete_ids
            and all(finite(value) and value >= 0 for value in completion.values()), 'complete_candidate_prediction')
        delta = {key: completion[key]-baseline[key] for key in complete_ids}
        status = 'passed' if all(value <= 0 for value in delta.values()) else 'rejected'
        require(row['guard_status'] == status and row['per_job_delta'] == delta, 'exact_zero_tolerance_candidate_guard')
        local = now + .01 < opportunity['service_ready_at'] and target['node'] == 7 and target['mode'] == 'loaded' and target['edge_to'] < 0
        if action != 'native_default':
            destination = 8 if action == 'prefer_8' else 3
            resource = one([node for node in view['node_contracts']
                if node['node'] == destination and node['resource_owner'] == owner], 'owned_receiving_resource')
            local = local and resource['occupancy'] < resource['capacity']
        require(row['enabled'] == bool(local and status == 'passed'), 'actual_candidate_mask')
        masks[action] = row
    action, identity = decision['selected_action_id'], decision['command_id']
    require(masks[action]['enabled'] and decision['old_advice_used_as_authority'] is False, 'selected_current_guard_authorized')
    receipts = raw['result']['receipts']
    load = one([row for row in receipts if row['event'] == 'LOAD_COMPLETE' and row['business_bag_id'] == job
        and row['tray_id'] == target['tray_id'] and row['node'] == target['node'] and row['time'] <= now], 'unique_same_job_load')
    leg = one([row for row in receipts if row['event'] == 'LEG_START' and row['business_bag_id'] == job
        and row['tray_id'] == target['tray_id'] and row['from'] == target['node'] and row['time'] <= now], 'unique_same_job_transport_leg')
    edge = one([row for row in receipts if row['event'] == 'EDGE_ENTER' and row['business_bag_id'] == job
        and row['tray_id'] == target['tray_id'] and row['from'] == target['node'] and row['time'] > now], 'unique_actual_route_edge')
    require(load['time'] == leg['time'] and load['traversal_id'] == leg['traversal_id']
        and leg['transport_leg_id'] == edge['transport_leg_id'] and leg['traversal_id'] < edge['traversal_id'],
        'native_loaded_leg_edge_identity')
    ack = None
    if identity is None:
        require(action == 'native_default' and decision['actual_ack'] is None, 'no_command_has_no_synthetic_ack')
    else:
        out = raw['outbox'][identity]; command, ack = out['request'], out['ack']
        call = one([row for row in raw['calls'] if row['request']['request_id'] == identity and not row['retry']], 'unique_real_submit')
        require(call['at'] == now and call['request'] == command and command['kind'] == 'route'
            and command['owner_id'] == owner and command['business_bag_id'] == job and command['tray_id'] == target['tray_id']
            and command['expected_generation'] == target['generation'] and command['expected_traversal'] == target['traversal_id']
            and command['next'] == edge['to'] == masks[action]['semantic']['destination'], 'actual_chosen_submit_identity')
        require(raw['request_creations'][identity]['creating_root'] == admission['owner_root']
            and identity not in public['own_outbox'], 'actual_submit_after_legal_observation_in_same_epoch')
        require(ack == decision['actual_ack'] and ack['result_id'] == identity and ack['status'] == 'updated'
            and now <= ack['executed_at'] <= ack['observed_at'] <= ack['delivered_at'] < edge['time'], 'actual_ack_before_unique_edge')
    return {'status': 'passed', 'decision_id': decision['decision_id'], 'target_job': job,
        'chosen': action, 'command_id': identity, 'ack': ack, 'edge': edge,
        'source_ages_sim_s': {row['owner']: now-row['captured_at'] for row in sources},
        'enabled_ids': [key for key, row in masks.items() if row['enabled']], 'attempt': attempt}


def wall_bracket(raw, decision, attempt):
    roots = sorted(raw['owner_activation_admissions'], key=lambda row: row['accepted_wall_ns'])
    by_id = {row['root_id']: row for row in roots}
    start = by_id[attempt['evidence']['collection']['root']]
    selected = by_id[decision['current_admission']['owner_root']]
    following = next((row for row in roots if row['accepted_wall_ns'] > selected['accepted_wall_ns']), None)
    inference = decision.get('learned_ranking')
    return {'unit': 'wall_ms',
        'current_collection_start_to_following_activation_enclosing_span_ms': None if following is None else
            (following['accepted_wall_ns']-start['accepted_wall_ns'])/1e6,
        'selected_activation_to_following_activation_enclosing_span_ms': None if following is None else
            (following['accepted_wall_ns']-selected['accepted_wall_ns'])/1e6,
        'bracket_caveat': 'Observed activation timestamps enclose processing plus interleaved scheduling/native IPC; these are not directly timed current-path latency.',
        'current_collect_plus_all_candidate_projection_envelope_ms': attempt['collection_and_guard_wall_ms'],
        'current_projection_only_ms': None, 'submit_only_ms': None,
        'inference_ms': inference.get('foreground_inference_wall_ms') if inference else None,
        'inference_status': inference.get('status') if inference else 'not_applicable_no_value_model',
        'current_path_exact_ms': None, 'full_request_100ms_certified': False,
        'missing_boundaries': ['current_path_start/end', 'current_projection_start/end', 'actual_submit_start/end']}


def async_chain(folder, raw, report, decision, current, resident):
    identity = decision.get('worker_result_id')
    require(type(identity) is str and re.fullmatch(r'[AB]-[0-9]{5}', identity), 'selected_decision_must_identify_worker_body')
    deliveries = raw['result_deliveries']
    delivered = one([row for row in deliveries if row.get('result', {}).get('request_id') == identity], 'unique_run_time_body_delivery')
    body = delivered['result']; target = current['target_job']; selected = decision['selected_at']
    source_attempt = one([row for row in raw['repeated_attempts'][decision['owner']]
        if row.get('worker_request_id') == identity], 'unique_actual_preview_submission')
    source = source_attempt['evidence']
    require(source['phase'] == source['collection']['phase'] == 'preview_next_route'
        and source_attempt['model_report']['status'] == 'validated_detached_preview_input', 'actual_detached_preview_phase')
    require(read(folder/('resident_'+decision['owner'])/(identity+'.json')) == body, 'complete_atomic_body_equals_consumed_raw')
    require(body['execution_authority'] is False and body['owner'] == decision['owner'] == source['owner']
        and body['source_sha256'] == digest(source) and body['source_at'] == source['at']
        and body['target_job'] == target == source['collection']['target_job'] == decision['worker_target_job'],
        'worker_owner_source_target_binding')
    require(body['status'] == 'completed_detached_prediction' and body['model_report']['status'] == 'conditional_current_seed'
        and body['model_report']['seed']['preview_target_job'] == target
        and body['model_report']['seed']['evidence_sha256'] == digest(source), 'bound_supported_detached_prediction')
    require(delivered['status'] == 'available_for_fresh_current_collection' and delivered['before_owner_default_admission'] is True
        and source['at'] <= delivered['at'] <= current['attempt']['evidence']['collection']['at'] <= selected,
        'body_precedes_fresh_current_collection')
    consumed = one([row for row in deliveries if row.get('request_id') == identity
        and row.get('status') == 'consumed_once_after_current_guard'], 'one_explicit_consumption')
    require(consumed['decision_id'] == decision['decision_id'] and consumed['target_job'] == target and consumed['at'] == selected,
        'consumption_same_actual_decision')
    require(sum(row.get('worker_result_id') == identity for row in raw['repeated_decisions']) == 1, 'body_never_reused_across_decisions')
    predictions = body['model_report']['candidate_results']
    order = sorted(predictions, key=lambda action: sum(predictions[action]['completion'].values()))
    require(set(predictions) == set(ACTIONS) and decision['worker_candidate_order'] == order, 'actual_worker_order_consumed')
    enabled = current['enabled_ids']; actual_predictions = current['attempt']['model_report']['candidate_results']
    scores = (decision.get('learned_ranking') or {}).get('scores', {})
    preference = decision.get('resolved_behavior_preference', raw['specification'].get('selection', 'score'))
    preference = None if preference == 'score' else preference
    prefix = lambda action: (-scores.get(action, 0.), action != preference if preference is not None else False)
    suffix = lambda action: (sum(actual_predictions[action]['completion'].values()), action != 'prefer_3', action)
    with_body = min(enabled, key=lambda action: (*prefix(action), order.index(action), *suffix(action)))
    without_body = min(enabled, key=lambda action: (*prefix(action), *suffix(action)))
    require(with_body == decision['selected_action_id'], 'recorded_selection_matches_worker_ranking')
    best_prefix = min(prefix(action) for action in enabled)
    rankable = [action for action in enabled if prefix(action) == best_prefix]
    require(len(rankable) >= 2, 'worker_ranking_must_compare_at_least_two_authorized_choices')
    records = resident['records']
    enqueued = one([row for row in records if row.get('request_id') == identity
        and row['kind'] in ('enqueued', 'pending', 'replaced_pending')], 'worker_request_enqueue_record')
    collected = one([row for row in records if row.get('request_id') == identity and row['kind'] == 'result_body_collected'],
        'foreground_complete_body_read_record')
    require(collected['sim_time'] == delivered['at'] and body['worker_started_ns'] <= body['worker_completed_ns'] <= collected['wall_ns'],
        'body_completed_before_poll_read')
    during = [row for row in raw['owner_activation_admissions']
        if body['worker_started_ns'] <= row['accepted_wall_ns'] <= body['worker_completed_ns']]
    progression = [row['accepted_at'] for row in during if row['accepted_at'] > source['at']]
    return {'status': 'passed_consumed_worker_ranking', 'worker_request_id': identity, 'target_job': target,
        'source_evidence_sha256': digest(source), 'body_file': reference(folder/('resident_'+decision['owner'])/(identity+'.json')),
        'rankable_authorized_ids': rankable, 'worker_candidate_order': order,
        'selected_with_worker_order': with_body, 'selection_without_worker_order': without_body,
        'worker_order_changes_choice': with_body != without_body,
        'native_progress_during_worker_observed': bool(progression), 'native_activations_during_worker': len(during),
        'progressed_sim_times_during_worker': progression,
        'sim_seconds': {'preview': source['at'], 'body_collected': delivered['at'],
            'fresh_collection_started': current['attempt']['evidence']['collection']['at'], 'selected': selected,
            'ack_delivered': current['ack']['delivered_at'] if current['ack'] else None, 'edge': current['edge']['time']},
        'wall_milliseconds': {'worker_projection_envelope': body['worker_wall_ms'], 'worker_cpu': body['worker_cpu_ms'],
            'enqueue_record_to_completed_body': (body['worker_completed_ns']-enqueued['wall_ns'])/1e6,
            'completed_body_to_foreground_poll': (collected['wall_ns']-body['worker_completed_ns'])/1e6,
            'enqueue_record_to_foreground_poll': (collected['wall_ns']-enqueued['wall_ns'])/1e6,
            'pack_and_enqueue': enqueued['foreground_pack_enqueue_wall_ms'],
            'nonblocking_poll_and_body_read': collected['poll_and_body_read_wall_ms']},
        'body_wait_caveat': 'Queue residence/completion/read interval is elapsed wall time, not a foreground blocking wait. Enqueue record is emitted after put_nowait.',
        'wall_and_sim_are_not_interchangeable': True}


def body_evidence(folder, raw, resident):
    """A delivered body can be real even when its later guard correctly refuses."""
    findings = []
    for delivered in raw['result_deliveries']:
        if 'result' not in delivered:
            continue
        body = delivered['result']; identity = body['request_id']
        finding = {'worker_request_id': identity, 'delivery_status': delivered['status']}
        try:
            require(re.fullmatch(r'[AB]-[0-9]{5}', identity), 'safe_worker_identity')
            source = one([attempt['evidence'] for attempt in raw['repeated_attempts'][body['owner']]
                if attempt.get('worker_request_id') == identity], 'unique_worker_source')
            path = folder/('resident_'+body['owner'])/(identity+'.json')
            require(read(path) == body and source['owner'] == body['owner']
                and source['at'] == body['source_at'] and digest(source) == body['source_sha256']
                and source['collection']['target_job'] == body['target_job']
                and body['execution_authority'] is False, 'complete_body_owner_source_target_binding')
            enqueue = one([row for row in resident['records'] if row.get('request_id') == identity
                and row['kind'] in ('enqueued', 'pending', 'replaced_pending')], 'unique_enqueue')
            collected = one([row for row in resident['records'] if row.get('request_id') == identity
                and row['kind'] == 'result_body_collected'], 'unique_body_read')
            require(collected['sim_time'] == delivered['at'] and body['worker_started_ns'] <= body['worker_completed_ns'] <= collected['wall_ns'],
                'completed_body_before_runtime_read')
            during = [row for row in raw['owner_activation_admissions']
                if body['worker_started_ns'] <= row['accepted_wall_ns'] <= body['worker_completed_ns']]
            progressed = [row['accepted_at'] for row in during if row['accepted_at'] > source['at']]
            decisions = [row for row in raw['repeated_decisions'] if row.get('worker_result_id') == identity]
            finding.update(status='bound_actual_complete_body_only_not_execution', body_file=reference(path),
                target_job=body['target_job'], source_sim_at=source['at'], collected_sim_at=delivered['at'],
                model_status=body.get('model_report', {}).get('status'),
                worker_candidate_order=sorted(body.get('model_report', {}).get('candidate_results', {}),
                    key=lambda key: sum(body['model_report']['candidate_results'][key].get('completion', {}).values())),
                native_activations_during_worker=len(during), native_progress_observed=bool(progressed),
                progressed_sim_range=None if not progressed else [min(progressed), max(progressed)],
                wall_ms={'worker_projection_envelope': body['worker_wall_ms'], 'worker_cpu': body['worker_cpu_ms'],
                    'pack_enqueue': enqueue['foreground_pack_enqueue_wall_ms'],
                    'enqueue_record_to_body_read': (collected['wall_ns']-enqueue['wall_ns'])/1e6,
                    'completed_body_to_body_read': (collected['wall_ns']-body['worker_completed_ns'])/1e6,
                    'poll_and_body_read': collected['poll_and_body_read_wall_ms']},
                downstream=[{'decision_id': row['decision_id'], 'at': row['selected_at'],
                    'execution_mode': row['current_admission']['execution_mode'],
                    'enabled_candidate_count': sum(candidate['enabled'] for candidate in row['candidate_mask']),
                    'selected': row['selected_action_id'], 'ack_status': (row.get('actual_ack') or {}).get('status')}
                    for row in decisions])
        except (KeyError, TypeError, ValueError) as error:
            finding.update(status='unknown_unbound_body', failure=str(error))
        findings.append(finding)
    return findings


def audit(folder):
    folder = Path(folder).resolve(); raw, report, receipt = load_closed(folder)
    resident = None
    if report.get('resident_audit'):
        require(reference(report['resident_audit']['path']) == report['resident_audit'], 'closed_resident_audit_digest')
        resident = read(report['resident_audit']['path'])
    rows = []
    for decision in raw['repeated_decisions']:
        if decision['current_admission']['execution_mode'] != 'protected_current' and not decision.get('worker_result_id'):
            continue
        row = {'decision_id': decision['decision_id'], 'target_job': decision['opportunity']['target']['business_bag_id']}
        try:
            current = current_chain(raw, decision)
            row['current'] = {key: value for key, value in current.items() if key != 'attempt'}
            row['current_timing'] = wall_bracket(raw, decision, current['attempt'])
            require(raw['specification']['mode'] == 'async' and resident is not None, 'not_a_resident_async_run')
            row['async'] = async_chain(folder, raw, report, decision, current, resident)
        except (KeyError, ValueError, TypeError, IndexError) as error:
            row['failure'] = str(error)
            attempts = [attempt for attempt in raw['repeated_attempts'][decision['owner']]
                if attempt['evidence']['collection']['request_id'] == decision['current_admission'].get('collection_request_id')]
            if len(attempts) == 1:
                row['current_timing'] = wall_bracket(raw, decision, attempts[0])
                row['actual_current_refusal'] = {key: value for key, value in attempts[0]['evidence']['information'].items()
                    if key in ('status', 'reasons', 'extension_check')}
        rows.append(row)
    accepted = [row for row in rows if row.get('async', {}).get('status') == 'passed_consumed_worker_ranking']
    submitted = [row for row in accepted if row['current']['command_id'] is not None]
    progress = [row for row in submitted if row['async']['native_progress_during_worker_observed']]
    complete = raw['summary']['status'] == 'assessed' and raw['summary']['audit']['status'] == 'passed'
    return {'schema': 'g31.independent.resident_async_consumption_audit.v1',
        'status': 'positive_async_consumption_and_progress_witness' if progress and complete else 'not_yet_positive_async_witness',
        'raw': reference(folder/'raw.json.gz'), 'audit_script': reference(__file__),
        'source_mutated': False, 'native_started_by_audit': False,
        'closed_current_chains': sum('current' in row for row in rows), 'consumed_ranked_bodies': len(accepted),
        'consumed_submitted_ack_edge_chains': len(submitted), 'with_native_progress_witness': len(progress),
        'decisions': rows, 'closed_physical_summary': raw['summary'], 'complete_successful_run': complete,
        'delivered_bodies': [] if resident is None else body_evidence(folder, raw, resident),
        'resident_cold_start_and_shutdown': None if resident is None else resident['timing'],
        'whole_bounded_process_wall_seconds': receipt['process']['wall_seconds'],
        'timing_conclusion': 'Current-path exact wall latency and submit latency are not instrumented; report measured envelopes and missing fields separately.',
        'full_request_100ms_certified': False, 'realtime_async_certified': False}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('run_directory', type=Path)
    parser.add_argument('--output', required=True, type=Path); args = parser.parse_args()
    require(not args.output.exists(), 'fresh_audit_output_required')
    result = audit(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = args.output.with_suffix('.audit.py')
    require(not snapshot.exists(), 'fresh_audit_source_snapshot_required')
    snapshot.write_bytes(Path(__file__).read_bytes())
    result['audit_script_snapshot'] = reference(snapshot)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({key: result[key] for key in ('status', 'closed_current_chains', 'consumed_ranked_bodies',
        'consumed_submitted_ack_edge_chains', 'with_native_progress_witness')}))


if __name__ == '__main__':
    main()
