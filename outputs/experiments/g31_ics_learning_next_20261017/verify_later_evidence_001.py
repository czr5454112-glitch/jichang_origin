"""Read-only native evidence checks; no project imports, inference or simulation."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

JOBS = {'loaded', 'receiver', 'blocker', 'reuse1', 'reuse2'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def reference(path, root):
    return {'path': str(path.relative_to(root)).replace('\\', '/'), 'sha256': sha(path)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def inspect_branch(directory, root):
    receipt_path = directory / 'receipt.json'
    worker_path = directory / 'worker_report.json'
    native_path = directory / 'episode/native/receipt.json'
    raw_path = directory / 'episode/native/raw.json.gz'
    receipt, worker, native = read(receipt_path), read(worker_path), read(native_path)
    require(receipt['status'] == 'completed_later_episode' and receipt['process']['status'] == 'exited'
        and receipt['process']['exitcode'] == 0, 'outer_process_not_complete')
    require(receipt['worker_report']['sha256'] == sha(worker_path)
        and receipt['native_receipt']['sha256'] == sha(native_path), 'outer_reference_mismatch')
    require(worker['source_and_checkpoint_exit_pins_passed'] is True
        and worker['native_receipt']['sha256'] == sha(native_path), 'worker_binding')
    require(native['status'] == 'assessed' and native['run_acceptance_status'] == 'closed_run_acceptance_passed'
        and native['raw_artifact']['sha256'] == sha(raw_path), 'native_closure_or_raw_binding')
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    unloads = [row for row in raw['result']['receipts'] if row['event'] == 'UNLOAD_COMPLETE']
    completion = {row['business_bag_id']: row['time'] for row in unloads}
    require(len(unloads) == 5 and set(completion) == JOBS
        and all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in completion.values())
        and completion == raw['summary']['completion'], 'five_unique_actual_unloads')
    transitions = raw['later_transitions']
    require(len(transitions) == 2 and [row['owner'] for row in transitions] == ['A', 'B'], 'two_real_temporal_owner_points')
    report = []
    for index, transition in enumerate(transitions):
        observation = transition['observation']
        require(observation['schema'] == 'g31.foundation.later_actor.v1'
            and observation['model_predictions_included'] is False
            and observation['privileged_evaluator_state_included'] is False, 'actor_declared_scope')
        owner, now = transition['owner'], transition['selected_at']
        view = observation['local_view']
        require(view['owner_id'] == owner and view['now'] == now == observation['at'], 'current_owner_epoch')
        require(all(row['resource_owner'] == owner or not {'occupancy', 'actual_available'}.intersection(row)
            for row in view['node_contracts']), 'foreign_dynamic_node_state')
        require(all(row['request']['owner_id'] == owner for row in observation['own_outbox'].values()), 'foreign_outbox')
        messages = [message for message in observation['delivered_v3']
            if message['message_id'] == observation['collection']['peer_message_id']]
        require(len(messages) == 1, 'one_selected_delivered_v3')
        message = messages[0]
        require(message['status'] == 'conditional' and message['fresh'] is True
            and message['captured_at'] <= message['delivered_at'] <= now < message['valid_until']
            and message['target_owner'] == owner and message['source_owner'] != owner, 'actual_message_freshness')
        state = transition['actor_state_check']
        require(transition['actor_state_unchanged'] is True and state['native_state_before'] == state['native_state_after']
            and state['physical_time_before'] == state['physical_time_after'] == now, 'callback_native_isolation')
        following = transitions[index + 1]['observation'] if index + 1 < len(transitions) else None
        require(transition['next_observation'] == following and transition['terminated'] is (following is None)
            and transition['truncated'] is False, 'next_actual_observation_and_terminal_flags')
        expected_delta = (following['at'] if following else raw['result']['advance']['physical_time']) - now
        require(transition['delta_sim_time_s'] == expected_delta, 'actual_elapsed_sim_time')
        initial = transition['initial_reference']
        require(transition['initial_reference_sha256'] == hashlib.sha256(canonical(initial)).hexdigest()
            and initial['reference_refresh_allowed'] is False, 'original_reference_hash')
        original = next(row for row in raw['initial_owners'][owner]['selection']['provider_evidence']['rows']
            if row['candidate_index'] == 4)
        require(original['completion'] == initial['completion'], 'original_reference_not_refreshed')
        guard_deltas = {}
        for candidate in transition['candidate_mask']:
            prediction = transition['model_report']['candidate_results'][candidate['action_id']]
            require(prediction['status'] == 'conditional_prediction' and set(prediction['completion']) == JOBS, 'conditional_prediction_scope')
            delta = {job: prediction['completion'][job] - initial['completion'][job] for job in JOBS}
            require(candidate['guard_status'] == ('passed' if all(value <= 0 for value in delta.values()) else 'rejected'), 'zero_tolerance_guard')
            guard_deltas[candidate['action_id']] = delta
        selected = [row for row in transition['candidate_mask'] if row['candidate_id'] == transition['candidate_id']]
        require(len(selected) == 1 and selected[0]['enabled'] is True
            and selected[0]['action_id'] == transition['executed_action_id'] == transition['action_id'], 'actual_selected_binding')
        command = transition['command_id']
        if command is None:
            require(transition['action_id'] == 'native_default' and transition['command_ids'] == []
                and transition['ACK'] is None and transition['ACK_status'] == 'not_applicable_no_command', 'no_fabricated_command_or_ack')
            request = None
        else:
            outbox = raw['outbox'][command]
            request = outbox['request']
            require(outbox['ack'] == transition['ACK'] and request['owner_id'] == owner
                and transition['ACK']['delivered_at'] <= transition['ACK_observed_at'], 'actual_owned_delivered_ack')
            require(transition['ACK_status'] == ('received' if owner == 'A' else 'updated'), 'terminal_action_ack')
            if owner == 'A':
                require(request['earliest_departure'] == selected[0]['proposal']['absolute_earliest_departure'], 'absolute_transfer_time')
            else:
                require(request['from'] == 7 and request['next'] == 8 and request['business_bag_id'] == 'reuse1', 'route_command_semantics')
        enters = [row for row in raw['result']['receipts'] if row['event'] == 'EDGE_ENTER'
            and row['tray_id'] == 'L' and row['time'] >= now and row['from'] == (6 if owner == 'A' else 7)]
        require(bool(enters) and transition['actual_physical_effect']['next_edge_enter'] == enters[0], 'actual_next_edge_receipt')
        require(transition['terminal_completion'] == completion, 'actual_terminal_label')
        report.append({'owner': owner, 'at': now, 'action': transition['action_id'],
            'behavior_mode': transition['behavior_mode'], 'guard_status': transition['conditional_protection_status'],
            'command_id': command, 'request': request, 'ACK': transition['ACK'], 'ACK_status': transition['ACK_status'],
            'ACK_observed_at': transition.get('ACK_observed_at'), 'next_edge_enter': enters[0],
            'actor_state_check': state, 'guard_deltas': guard_deltas, 'next_observation_exact': True,
            'delta_sim_time_s': expected_delta, 'terminated': transition['terminated'], 'truncated': False,
            'selected_conditional_prediction_matches_actual_terminal':
                transition['model_report']['candidate_results'][transition['action_id']]['completion'] == completion})
    returns = [row for row in raw['result']['receipts'] if row['event'] == 'EMPTY_RECEIVED' and row['tray_id'] == 'L']
    loads = [row for row in raw['result']['receipts'] if row['event'] == 'LOAD_START' and row['business_bag_id'] in ('reuse1', 'reuse2')]
    require(len(returns) == len(loads) == 2 and all(row['tray_id'] == 'L' for row in loads)
        and all(returned['time'] <= loaded['time'] for returned, loaded in zip(returns, loads)), 'same_tray_two_reuses')
    return raw, {'references': {name: reference(path, root) for name, path in
        (('raw', raw_path), ('native_receipt', native_path), ('outer_receipt', receipt_path), ('worker_report', worker_path))},
        'process_wall_s': receipt['process']['wall_seconds'], 'completion_from_five_unload_receipts': completion,
        'transitions': report, 'same_tray_returns': returns, 'same_tray_reloads': loads,
        'status': 'passed_with_conditional_and_diagnostic_limitations'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--branch', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    require(not args.output.exists(), 'output_must_be_new')
    raw, reports = {}, {}
    for argument in args.branch:
        name, relative = argument.split('=', 1)
        require(name not in reports, 'unique_branch_name')
        raw[name], reports[name] = inspect_branch(root / relative, root)
    baseline_name = next(iter(raw))
    baseline = raw[baseline_name]
    comparisons = {}
    for name, candidate in raw.items():
        require(candidate['input'] == baseline['input'], 'same_physical_input')
        base_transitions, changed_transitions = baseline['later_transitions'], candidate['later_transitions']
        changed = [index for index, (left, right) in enumerate(zip(base_transitions, changed_transitions))
            if left['action_id'] != right['action_id']]
        at = base_transitions[changed[0]]['selected_at'] if changed else 40.
        prefix = lambda value: [row for row in value['result']['receipts'] if row['time'] <= at]
        delta = {job: candidate['summary']['completion'][job] - baseline['summary']['completion'][job] for job in JOBS}
        comparisons[name] = {'baseline': baseline_name, 'same_input': True, 'prefix_cutoff': at,
            'all_receipts_prefix_exact': prefix(candidate) == prefix(baseline), 'baseline_prefix_count': len(prefix(baseline)),
            'per_job_actual_delta': delta, 'strict_protected_zero_tolerance': all(value <= 0 for value in delta.values())}
    old_path = root / 'outputs/experiments/g31_ics_foundation_learning_20261017/native_001/raw.json.gz'
    old = json.loads(gzip.decompress(old_path.read_bytes()))
    report = {'schema': 'g31.independent_later_evidence_review.v1',
        'status': 'passed_with_conditional_and_diagnostic_limitations', 'branches': reports, 'comparisons': comparisons,
        'old_default_reference': reference(old_path, root),
        'old_default_parity': {'input': old['input'] == baseline['input'],
            **{field: old['result'][field] == baseline['result'][field] for field in ('receipts', 'jobs', 'trays')}},
        'independent_scene_count': len({record['specification']['case'] for record in raw.values()}),
        'scope': 'Saved actual receipt/identity/observation/guard arithmetic only; no model inference, retraining or new native run.',
        'limitations': ['Not a full re-audit of the native FIFO/capacity model or hidden state.',
            'Earlier conditional forecasts assume default future behavior; later diagnostic interventions can invalidate them.',
            'Diagnostic rejected actions are not protected deployment successes.',
            'Same-scene repeated episodes are not independent-scene generalization or protected multi-step RL.',
            'No 100ms or full R1/R2 authority certification.']}
    with args.output.open('x', encoding='utf8') as target:
        json.dump(report, target, indent=2, ensure_ascii=False, allow_nan=False)
        target.write('\n')
    print(json.dumps({'status': report['status'], 'branches': len(reports), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
