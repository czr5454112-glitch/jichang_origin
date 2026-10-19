"""Independent closed negative-baseline reference audit; no native/training."""
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('formal_baseline_helpers',HERE/'audit_formal.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
base=HERE.parent
folder=base/'A_eval_negative_baseline_001'
guard=audit.load_guard()
raw,worker,inner=guard.load_closed(folder)
require=audit.require;one=audit.one
require(raw['specification']['mode']=='baseline' and raw['specification'].get('model_reference') is None,
        'actual_original_unmodeled_baseline')
vector=audit.completion_vector(raw)
require(vector['complete'] and vector['physical_clock']==40. and raw['summary']['common_horizon_complete'] is True,
        'complete_common_horizon')
require(raw['summary']['audit']['status']=='passed' and raw['summary']['stock_preserved'] is True
        and raw['summary']['supply_recovery_valid'] is True
        and raw['summary']['all_original_and_new_returns_received'] is True,'closed_original_lifecycle')
require(raw['summary']['status']=='unknown_incomplete_or_unexecuted'
        and raw['summary']['all_routes_updated_and_match_edges'] is False,'preserved_original_negative_status')
events=raw['result']['receipts'];physical=[]
for identity,row in raw['outbox'].items():
    if row['kind'] not in ('route','transfer'):continue
    ack=row.get('ack');request=row['request']
    require(row['terminal'] is True and ack is not None
            and 0<=ack['observed_at']<=ack['delivered_at']<=40.,'every_physical_request_terminal_delivered')
    if row['kind']=='transfer':
        if ack['status']=='received':
            event=one([e for e in events if e['event']=='EMPTY_RECEIVED' and e['reason']==identity
                and e['tray_id']==request['tray_id'] and e['time']==ack['received_at']],'unique_actual_transfer_receipt')
            physical.append({'request_id':identity,'status':'received','received_event':event})
        else:
            require(ack['status']=='rejected' and ack['reason']=='receiving_full','expected_original_receiving_rejection')
            require(not any(e['event']=='EMPTY_RECEIVED' and e['reason']==identity for e in events),'rejected_not_received')
            physical.append({'request_id':identity,'status':'rejected','ack':ack})
routes=[]
for decision in raw['repeated_decisions']:
    require(decision['current_admission']['execution_mode']=='original_fixed_rule','unchanged_original_policy')
    if decision['opportunity']['phase']!='cycle_route':continue
    target=decision['opportunity']['target'];job=target['business_bag_id'];now=decision['selected_at'];identity=decision['command_id']
    load=one([e for e in events if e['event']=='LOAD_COMPLETE' and e['business_bag_id']==job
        and e['tray_id']==target['tray_id'] and e['time']<=now],'unique_actual_route_load')
    leg=one([e for e in events if e['event']=='LEG_START' and e['business_bag_id']==job
        and e['tray_id']==target['tray_id'] and e['time']==load['time']],'unique_actual_transport_leg')
    edge=one([e for e in events if e['event']=='EDGE_ENTER' and e['business_bag_id']==job
        and e['tray_id']==target['tray_id'] and e['from']==target['node'] and e['time']>now],'unique_actual_first_edge')
    require(edge['transport_leg_id']==leg['transport_leg_id'] and edge['traversal_id']>load['traversal_id'],'load_leg_edge_identity')
    status='default_no_command';ack=None;recovery_events=[]
    if identity is not None:
        out=raw['outbox'][identity];request=out['request'];ack=out['ack']
        require(out['kind']=='route' and request['business_bag_id']==job and request['tray_id']==target['tray_id']
            and request['from']==target['node'] and request['expected_generation']==target['generation']
            and request['expected_traversal']==target['traversal_id'],'route_target_binding')
        call=one([c for c in raw['calls'] if c['request']['request_id']==identity and not c['retry']],'unique_original_submit')
        require(call['at']==now and call['request']==request and ack==decision['actual_ack']
            and now<=ack['executed_at']<=ack['observed_at']<=ack['delivered_at']<edge['time'],'actual_submit_ack_time')
        intent=one([e for e in events if e['event']=='ROUTE_INTENT_'+ack['status'] and e['business_bag_id']==job
            and e['tray_id']==target['tray_id'] and e['time']==ack['executed_at']
            and e['from']==request['from'] and e['to']==request['next']],'actual_route_status_receipt')
        if ack['status']=='updated':
            require(edge['to']==request['next'],'executed_route_to_edge');status='updated_command_and_actual_edge'
        else:
            require(ack['status']=='rejected' and ack['reason']=='circulation:receiving_full','expected_route_rejection')
            require(not any(e['event']=='ROUTE_INTENT_updated' and e['business_bag_id']==job
                and now<=e['time']<edge['time'] for e in events),'no_fabricated_route_execution')
            require(not any(c['kind']=='route' and c['request']['business_bag_id']==job
                and now<c['at']<edge['time'] for c in raw['calls']),'no_posthoc_replacement_command')
            recovery_events=[e for e in events if e['business_bag_id']==job and e['transport_leg_id']==leg['transport_leg_id']
                and e['event'] in ('RESOURCE_WAIT','RESOURCE_WAKE') and ack['delivered_at']<=e['time']<=edge['time']]
            require(any(e['event']=='RESOURCE_WAIT' for e in recovery_events) and any(e['event']=='RESOURCE_WAKE' for e in recovery_events),
                    'actual_native_wait_and_wake')
            status='terminal_rejection_then_unchanged_native_continuation'
    else:require(decision['selected_action_id']=='native_default' and decision['actual_ack'] is None,'no_command_no_ack')
    routes.append({'job':job,'request_id':identity,'status':status,'ack':ack,'load':load,'leg':leg,'first_edge':edge,
                   'recovery_events':recovery_events,'rejected_command_claimed_executed':False})
recoveries=[]
for row in raw['continuation']['recovery_decisions']:
    old=raw['outbox'][row['predecessor_request_id']];new=raw['outbox'][row['request_id']]
    require(old['ack']==row['delivered_rejection'] and old['ack']['status']=='rejected'
        and old['ack']['delivered_at']<=row['at'] and new['ack']['status']=='received','original_supply_recovery_chain')
    demand=row['delivered_demand']
    require(demand['observed_at']<=demand['delivered_at']<=row['at']
        and all(j['arrival']<=demand['observed_at'] for j in demand['jobs']),'causal_original_recovery_demand')
    recoveries.append({'request_id':row['request_id'],'predecessor':row['predecessor_request_id'],'received_at':new['ack']['received_at']})
require(len(routes)==3 and sum(r['status']=='terminal_rejection_then_unchanged_native_continuation' for r in routes)==1,
        'explicit_one_rejected_route')
report={'schema':'g31.independent.original_baseline_reference_eligibility.v1',
    'status':'complete_original_baseline_reference_eligible_despite_terminal_route_rejection',
    'original_summary_preserved':raw['summary'],'completion':vector,'physical_transfers':physical,'route_chains':routes,
    'original_supply_recovery':recoveries,'raw':audit.reference(folder/'raw.json.gz'),
    'audit_script':audit.reference(__file__),'formal_audit_helper':audit.reference(HERE/'audit_formal.py'),
    'guard_snapshot':audit.reference(HERE/'guard_audit_snapshot.py'),'raw_mutated':False,'native_executed_by_audit':False,
    'fit_or_selection_performed':False,'rejected_command_claimed_executed':False,
    'eligibility_scope':'actual original-policy completion vector only; current candidate guard and model authority unchanged',
    'remaining_four_formal_branches':'not yet run at diagnosis; not counted as failures'}
print(json.dumps(report,indent=2,allow_nan=False))

