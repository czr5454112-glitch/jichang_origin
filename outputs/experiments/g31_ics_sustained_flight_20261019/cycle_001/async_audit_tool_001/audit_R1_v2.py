"""Artifact-only closed-run request timing audit; never imports native/controller code."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import audit_async as chain

STAGES = {'collect': ('collect_start', 'collect_end'), 'all_candidate_evaluate': ('evaluate_start', 'evaluate_end'),
    'mask': ('mask_start', 'mask_end'), 'public_observation': ('public_start', 'public_end'),
    'inference': ('inference_start', 'inference_end'), 'ranking': ('ranking_start', 'ranking_end'),
    'require_current': ('require_current_start', 'require_current_end'),
    'route_dispatch_envelope': ('route_dispatch_start', 'route_dispatch_end')}


def stats(values, population):
    present = [value for value in values if value is not None]
    chain.require(all(chain.finite(value) and value >= 0 for value in present), 'finite_nonnegative_timing')
    return {'population': population, 'measured': len(present), 'missing_or_not_applicable': population-len(present),
        'median_ms': median(present) if present else None, 'max_ms': max(present) if present else None}


def timing_audit(raw):
    timing = raw['path_timing']; roots = raw['owner_activation_admissions']
    by_root = {row['root_id']: row for row in roots}
    chain.require(len(by_root) == len(roots), 'unique_actual_activation_roots')
    recorded = set()
    for row in timing['owner_activations']:
        root = by_root[row['root_id']]
        chain.require(row['root_id'] not in recorded and row['owner'] == root['owner']
            and row['entry_wall_ns'] <= root['accepted_wall_ns'] <= row['exit_wall_ns']
            and row['entry_sim_s'] == root['accepted_at'] == row['exit_sim_s']
            and row['status'] == 'returned'
            and row['processing_wall_ms'] == (row['exit_wall_ns']-row['entry_wall_ns'])/1e6,
            'actual_activation_envelope')
        recorded.add(row['root_id'])
        if timing['schema'].endswith('.v2'):
            expected_phase = root['trigger'].get('kind', 'owner_policy_continuation')
            chain.require(row['phase'] == expected_phase, 'actual_initial_final_or_continuation_scope')
    missing = [row for row in roots if row['root_id'] not in recorded]
    missing_by_kind = Counter(row['trigger'].get('kind', 'other') for row in missing)
    if timing['schema'].endswith('.v1'):
        chain.require(missing_by_kind == {'initial_public_epoch': 2, 'fixed_original_initial_action': 2,
            'final_outbox_collection': 2}, 'v1_exact_known_unmeasured_roots')
    else:
        chain.require(not missing, 'v2_all_actual_roots_have_envelopes')
    calls, submits = raw['calls'], timing['native_submits']
    chain.require(len(calls) == len(submits), 'every_returned_submit_measured')
    for call, measured in zip(calls, submits):
        command = call['request']
        chain.require(command['request_id'] == measured['request_id'] and call['kind'] == measured['kind']
            and command['owner_id'] == measured['owner'] and call['retry'] == measured['retry']
            and call['at'] == measured['sim_s'] and measured['end_wall_ns'] >= measured['start_wall_ns'],
            'exact_real_submit_call_order')
    ack_keys = {(row['request_id'], row['owner'], row['ack']['sequence']) for row in raw['ack_handling']}
    read_keys = set()
    for row in timing['ack_read_envelopes']:
        key = (row['request_id'], row['owner'], row['sequence'])
        ack = chain.one([item['ack'] for item in raw['ack_handling'] if
            (item['request_id'], item['owner'], item['ack']['sequence']) == key], 'real_delivered_ack_read')
        chain.require(key not in read_keys and ack['status'] == row['status']
            and ack['delivered_at'] == row['delivered_sim_s']
            and row['read_start_wall_ns'] <= row['read_end_wall_ns'], 'ack_read_envelope_binding')
        chain.one([activation for activation in timing['owner_activations']
            if activation['owner'] == row['owner'] and activation['entry_wall_ns'] == row['read_start_wall_ns']
            and activation['exit_wall_ns'] == row['read_end_wall_ns']
            and row['delivered_sim_s'] <= activation['exit_sim_s']], 'ack_read_inside_actual_owner_work')
        read_keys.add(key)
    rows = []
    for row in timing['requests']:
        chain.require(row['request_id'] in raw['outbox'], 'actual_collection_request')
        creation = raw['request_creations'][row['request_id']]
        chain.require(creation['creating_root'] == row['root_id'] and row['owner'] == by_root[row['root_id']]['owner'],
            'logical_request_root')
        marks = row['milestones_ns']; ready = marks.get('ready_entry')
        for name, value in marks.items():
            chain.require(row['open_wall_ns'] <= value <= row['close_wall_ns'], 'milestone_inside_request')
        for name, (start, end) in STAGES.items():
            measured = (marks[end]-marks[start])/1e6 if start in marks and end in marks else None
            chain.require(row['stage_wall_ms'][name] == measured and (measured is None or measured >= 0),
                'exact_individual_stage_envelope')
        chain.require(row['open_to_controller_done_wall_ms'] == (row['close_wall_ns']-row['open_wall_ns'])/1e6,
            'full_controller_envelope')
        if ready is not None:
            chain.require(row['logical_wait_to_ready_wall_ms'] == (ready-row['open_wall_ns'])/1e6,
                'logical_wait_measured_separately')
        matches = [item for item in submits if item['request_id'] == row.get('command_id') and not item['retry']]
        if row.get('command_id'):
            call = chain.one(matches, 'one_actual_route_submit')
            chain.require(row['open_wall_ns'] <= call['start_wall_ns'] <= call['end_wall_ns'] <= row['close_wall_ns']
                and row['actual_native_submit_wall_ms'] == (call['end_wall_ns']-call['start_wall_ns'])/1e6
                and row['open_to_native_submit_return_wall_ms'] == (call['end_wall_ns']-row['open_wall_ns'])/1e6,
                'actual_full_request_submit_boundary')
        else:
            chain.require(not matches and row['actual_native_submit_wall_ms'] is None
                and row['open_to_native_submit_return_wall_ms'] is None, 'no_command_not_a_fast_submit')
        rows.append(row)
    metrics = ('logical_wait_to_ready_wall_ms', 'open_to_controller_done_wall_ms',
        'ready_to_controller_done_wall_ms', 'open_to_route_dispatch_return_wall_ms',
        'open_to_native_submit_return_wall_ms', 'actual_native_submit_wall_ms')
    groups = {}
    for name, population in [('all_logical_requests', rows), ('current_cycle_route', [r for r in rows if r['phase'] == 'cycle_route']),
            ('nonexecuting_preview', [r for r in rows if r['phase'] == 'preview_next_route'])]:
        groups[name] = {'count': len(population), 'status_counts': dict(Counter(r['status'] for r in population)),
            'submitted': sum(r.get('command_id') is not None for r in population),
            'metrics': {key: stats([r[key] for r in population], len(population)) for key in metrics},
            'stages': {key: stats([r['stage_wall_ms'][key] for r in population], len(population))
                for key in (rows[0]['stage_wall_ms'] if rows else {})}}
    return {'groups': groups, 'requests': rows,
        'owner_activations': stats([r['processing_wall_ms'] for r in timing['owner_activations']], len(roots)),
        'all_client_roots': len(roots), 'measured_owner_roots': len(recorded),
        'unmeasured_root_counts': dict(missing_by_kind), 'unmeasured_roots': missing,
        'all_owner_activations_timed_claim_validated': not missing,
        'actual_submit_calls': len(calls), 'actual_ack_reads': len(ack_keys), 'measured_ack_reads': len(read_keys),
        'unmeasured_ack_read_keys': sorted(ack_keys-read_keys),
        'exception_path_timing_persistence_validated_by_this_successful_run': False,
        'exception_path_note': ('v1 successful-run recorder retains statuses; campaign exception partial did not persist recorder, so failed-run denominator is censored.'
            if timing['schema'].endswith('.v1') else 'v2 exception persistence is checked by session_016 pure failure fixtures; this successful native branch does not exercise process failure.'),
        'overlapping_envelopes_must_not_be_summed': True, 'physical_effect_exact_wall_time_measured': False}


def audit(folder, comparison):
    folder, comparison = Path(folder).resolve(), Path(comparison).resolve()
    raw, report, receipt = chain.load_closed(folder)
    previous, _, _ = chain.load_closed(comparison)
    chain.require(raw['input'] == previous['input'], 'same_full_business_input_for_comparison')
    chain.require(raw['summary']['status'] == 'assessed' and raw['summary']['audit']['status'] == 'passed',
        'closed_native_physical_audit')
    baseline = raw['specification']['reference']['completion']; completion = raw['summary']['completion']
    chain.require(set(completion) == {r['business_bag_id'] for r in raw['input']['jobs']} == set(baseline)
        and all(completion[j] <= baseline[j] for j in completion), 'whole_business_actual_zero_tolerance')
    checked = []
    resident = chain.read(report['resident_audit']['path']) if report.get('resident_audit') else None
    if resident is not None:
        chain.require(chain.reference(report['resident_audit']['path']) == report['resident_audit'], 'resident_digest')
    for decision in raw['repeated_decisions']:
        if decision['current_admission']['execution_mode'] != 'protected_current':
            continue
        current = chain.current_chain(raw, decision)
        row = {key: value for key, value in current.items() if key != 'attempt'}
        row['old_collect_plus_evaluate_envelope_ms'] = current['attempt']['collection_and_guard_wall_ms']
        if resident is not None:
            row['worker'] = chain.async_chain(folder, raw, report, decision, current, resident)
        checked.append(row)
    timing = timing_audit(raw)
    for row in checked:
        request = chain.one([r for r in timing['requests'] if r.get('decision_id') == row['decision_id']], 'current_request_timing')
        edge_time = row['edge']['time']
        row['physical_latency_sim_s'] = edge_time-request['close_sim_s']
        row['physical_edge_possible_native_advance_envelopes'] = [r for r in raw['path_timing']['native_advance_envelopes']
            if r['before_sim_s'] <= edge_time <= r['after_sim_s']]
        row['physical_edge_exact_wall_ns'] = None
    return {'schema': 'g31.independent.R1_full_request_audit.v2', 'status': 'passed_with_explicit_timing_scope',
        'raw': chain.reference(folder/'raw.json.gz'), 'comparison_raw': chain.reference(comparison/'raw.json.gz'),
        'audit_script': chain.reference(__file__), 'chain_auditor': chain.reference(chain.__file__),
        'native_started_by_audit': False, 'source_mutated': False,
        'completion': completion, 'delta_from_original_fixed_rule': {j: completion[j]-baseline[j] for j in completion},
        'exact_completion_equal_to_pre_R1': completion == previous['summary']['completion'],
        'physical_summary': raw['summary'], 'current_chains': checked, 'timing': timing,
        'static_registry_initialization': raw['static_registry_initialization'],
        'resident_cold_start_shutdown': resident['timing'] if resident else None,
        'whole_bounded_process_wall_seconds': receipt['process']['wall_seconds'],
        'full_request_100ms_certified': False, 'realtime_async_certified': False,
        'limits': ['Two submitted current requests per arm do not establish a latency distribution or 100 ms guarantee.',
            'Report actual missing root and ACK counts; v1 excludes four initialization and two final client roots.',
            'Native advance envelopes bound possible edge processing; physical receipts have no exact wall timestamp.',
            'Current request begins at collection publication; process cold initialization and worker startup remain separate.',
            'The no-model inference stage is a measured bypass, not NN inference latency; preview evaluate stages are not worker projection latency.',
            'Prior runs have collect-plus-projection envelopes, not identical full-request instrumentation; do not claim paired full-path speedup.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('run'); parser.add_argument('comparison'); parser.add_argument('--output', required=True)
    args = parser.parse_args(); output = Path(args.output)
    chain.require(not output.exists(), 'fresh_audit_output')
    result = audit(args.run, args.comparison)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'status': result['status'], 'timing_groups': result['timing']['groups'],
        'owner_activations': result['timing']['owner_activations'], 'equal_pre_R1': result['exact_completion_equal_to_pre_R1']}))
