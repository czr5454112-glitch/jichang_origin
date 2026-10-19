"""Read-only finite baseline diagnosis; neither changes the gate nor runs native."""
import json
from pathlib import Path
from audit_async import load_closed, one, require, finite, reference

HERE = Path(__file__).resolve().parent
folder = HERE.parent/'A_eval_negative_baseline_001'
raw, _, _ = load_closed(folder)
require(raw['specification']['mode'] == 'baseline' and raw['specification'].get('model_reference') is None, 'original_baseline_only')
receipts = raw['result']['receipts']; summary = raw['summary']
require(raw['result']['physical_clock'] == raw['result']['advance']['physical_time'] == 40.
    and raw['result']['advance']['status'] == 'reached' and raw['result']['advance']['horizon_complete'] is True,
    'actual_complete_horizon')
flags = ['business_complete', 'common_horizon_complete', 'supply_recovery_valid', 'all_original_and_new_returns_received',
    'same_L_all_reuse_loads', 'stock_preserved', 'all_input_business_in_evaluator']
require(all(summary[key] is True for key in flags) and summary['audit']['status'] == 'passed'
    and summary['audit']['open_traversals'] == 0, 'all_nonroute_closure_conditions')
business = {}
for job in raw['input']['jobs']:
    identity = job['business_bag_id']
    outcome = one([row for row in raw['result']['jobs'] if row['business_bag_id'] == identity], 'one_actual_job')
    arrival = one([row for row in receipts if row['event'] == 'BAG_ARRIVAL' and row['business_bag_id'] == identity], 'one_actual_arrival')
    complete = one([row for row in receipts if row['event'] == 'UNLOAD_COMPLETE' and row['business_bag_id'] == identity], 'one_actual_completion')
    require(arrival['time'] == job['arrival'] and outcome['status'] == 'completed'
        and finite(complete['time']) and job['arrival'] <= complete['time'] <= 40.
        and complete['time'] == outcome['completed_at'] == summary['completion'][identity], 'full_original_job_actual_completion')
    business[identity] = complete
require(set(business) == set(summary['completion']) and len(raw['result']['jobs']) == len(business), 'no_omitted_population')
proofs = []
for call in raw['calls']:
    if call['kind'] != 'route' or call['retry']:
        continue
    request = call['request']; identity = request['request_id']; output = raw['outbox'][identity]; ack = output['ack']
    require(request['owner_id'] == 'B' and request['tray_id'] == 'L' and request['from'] == 7 and request['next'] == 3,
        'original_fixed_default_route_only')
    decision = one([row for row in raw['repeated_decisions'] if row['command_id'] == identity], 'one_original_route_decision')
    target = decision['opportunity']['target']
    require(decision['current_admission']['execution_mode'] == 'original_fixed_rule'
        and decision['selected_at'] == call['at'] and target['business_bag_id'] == request['business_bag_id']
        and request['expected_generation'] == target['generation'] and request['expected_traversal'] == target['traversal_id'],
        'actual_original_decision_identity')
    job = request['business_bag_id']
    load = one([row for row in receipts if row['event'] == 'LOAD_COMPLETE' and row['business_bag_id'] == job and row['tray_id'] == 'L'], 'same_job_load')
    leg = one([row for row in receipts if row['event'] == 'LEG_START' and row['business_bag_id'] == job and row['tray_id'] == 'L' and row['from'] == 7], 'same_job_leg')
    edge = one([row for row in receipts if row['event'] == 'EDGE_ENTER' and row['business_bag_id'] == job and row['tray_id'] == 'L' and row['from'] == 7], 'same_job_default_edge')
    require(output['terminal'] is True and output['request'] == request and ack['result_id'] == identity
        and (ack['status'] == 'updated' or (ack['status'] == 'rejected' and ack['reason'] == 'circulation:receiving_full'))
        and call['at'] <= ack['executed_at'] <= ack['observed_at'] <= ack['delivered_at'] < edge['time'] <= 40.,
        'actual_terminal_updated_or_capacity_refused_before_default_execution')
    require(load['time'] == leg['time'] <= call['at'] and load['traversal_id'] == leg['traversal_id']
        and leg['transport_leg_id'] == edge['transport_leg_id'] and leg['traversal_id'] < edge['traversal_id']
        and edge['to'] == 3 and edge['time'] < business[job]['time'], 'physical_default_continuation_after_same_load')
    proofs.append({'request': request, 'at': call['at'], 'ack': ack, 'load': load, 'leg': leg, 'edge': edge,
        'completion': business[job], 'claims_rejected_request_took_effect': False})
result = {'schema': 'g31.independent.original_baseline_capacity_refusal_diagnosis.v1',
    'status': 'all_original_jobs_closed_default_continues_after_capacity_refusal', 'raw': reference(folder/'raw.json.gz'),
    'script': reference(__file__), 'physical_clock': 40., 'raw_summary_preserved': summary, 'actual_job_completions': business,
    'route_proofs': proofs, 'rejected_route_count': sum(row['ack']['status'] == 'rejected' for row in proofs),
    'original_reference_gate_changed': False, 'native_started': False,
    'interpretation': 'An original route request rejected for capacity has no command effect; the native fixed default later executes its own same-job edge. Complete original business outcomes remain legitimate finite baseline values. A separate reference-only check is needed; protected refresh guards remain unchanged.'}
out = HERE/'negative_baseline_reference_diagnosis_001.json'
require(not out.exists(), 'fresh_output')
out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
print(json.dumps({'status': result['status'], 'rejected_routes': result['rejected_route_count'], 'sum': summary['completion_sum']}))
