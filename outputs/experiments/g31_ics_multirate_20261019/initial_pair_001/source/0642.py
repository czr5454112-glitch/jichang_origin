"""Data-only independent chain replay; saved JSON never grants runtime authority.

A future campaign must also replay its exact policy/outbox against native API
responses and bind source/binary pins. This validator proves the smaller claim:
logged skips follow the actual recorded all-owner advance/drain chain, complete
notification batches, original admissions and unchanged protocol-call prefix.
It does not authenticate invented native responses or projected outbox rows.
"""
from __future__ import annotations
import copy
import math
from . import initial_owner_route_gate_adapter as adapter
from .initial_owner_route_observation_gate import RootObservationGate


def verify(events, batches, audit, roots, protocol_calls, root_id):
    require=adapter.require
    require(type(audit) is dict and audit.get('schema')=='g31.initial_root.actual_advance_chain.v1'
            and audit.get('runtime_authority_from_saved_json') is False,'chain_schema')
    calls=audit['calls'];require(type(calls) is list,'chain_calls')
    boundaries=[]
    previous_time=previous_wall=None
    for ordinal,row in enumerate(calls):
        require(row['ordinal']==ordinal,'chain_ordinal')
        require(all(type(row[k]) in (int,float) and math.isfinite(row[k]) and row[k]>=0
                    for k in ('before','after')) and row['before']<=row['after'],'chain_physical_clock')
        require(all(type(row[k]) is int and row[k]>=0 for k in ('started_ns','finished_ns'))
                and row['started_ns']<=row['finished_ns'],'chain_wall_clock')
        if previous_time is not None:
            require(previous_time==row['before'] and previous_wall<=row['started_ns'],'chain_gap')
        previous_time,previous_wall=row['after'],row['finished_ns']
        if row['role']=='scheduler':
            require(row['method']=='advance_until_owner_notification' and len(row['args'])==3
                and row['args'][0]==['A','B'] and row['kwargs']=={'max_events':100000},'scheduler_call')
            if 'error' not in row:boundaries.append({'deadline':row['args'][2],'response':row['response']})
        elif row['role']=='scheduler_final_drain':
            require(row['method']=='advance_to' and len(row['args'])==1
                    and row['kwargs']=={'max_events':100000},'final_call')
            if 'error' not in row:boundaries.append({'deadline':row['args'][0],
                'response':row['response'],'kind':'final_drain'})
        else:
            require(row['role']=='root_same_timestamp_drain' and row['method']=='advance_to'
                and len(row['args'])==1 and row['args'][0]==row['before']
                and row['kwargs']=={'max_events':100000},'root_drain_call')
    require(adapter.ordered(boundaries)==adapter.ordered(batches),'all_native_batches')
    gate=RootObservationGate();next_call=0;pending=None;steps=skips=0
    for position,event in enumerate(events):
        if event['stage']=='root_observation_gate':
            require(pending is None,'uncompleted_gate')
            saved=event['value'];notification=saved['notification_call']
            ordinal=notification['ordinal']
            require(0<=ordinal<len(calls) and adapter.ordered(notification)==adapter.ordered(calls[ordinal]),
                    'notification_not_in_trace')
            require(notification['role']=='scheduler','notification_role')
            inputs=copy.deepcopy(saved['inputs'])
            # Recompute the adapter's continuity Boolean, never accept its log.
            continuous=(ordinal==next_call and 'error' not in notification
                and notification['args'][0]==['A','B']
                and notification['after']==event['at']
                and adapter.ordered(notification.get('response'))==adapter.ordered(inputs['response']))
            require(inputs['before']==notification['before'] and inputs['now']==notification['after']
                and inputs['horizon']==notification['args'][2]
                and inputs['cursor_before']==notification['args'][1]
                and type(inputs['protocol_call_count']) is int
                and 0<=inputs['protocol_call_count']<=len(protocol_calls),'bound_gate_inputs')
            inputs['all_native_advances_observed']=continuous
            proof=gate.decide(**inputs)
            require(adapter.ordered(proof)==adapter.ordered(saved['decision']),'recomputed_gate_decision')
            pending=(position,ordinal,proof,inputs);steps+=1;skips+=int(proof['skip'])
        elif event['stage']=='root_observation_gate_completion':
            require(pending is not None,'completion_without_gate')
            start,ordinal,proof,inputs=pending;value=event['value'];pending=None
            require(value['skipped'] is proof['skip'],'skip_flag')
            before=value['admissions_before'];after=value['admissions_after']
            require(type(before) is int and type(after) is int and 0<=before<after<=len(roots),
                    'admission_range')
            require(adapter.ordered(value['admission'])==adapter.ordered(roots[after-1]),'actual_admission')
            retained=adapter.admission_matches(roots[:after],before,root_id,event['at'])
            count=value['protocol_call_count_after']
            require(type(count) is int and inputs['protocol_call_count']<=count<=len(protocol_calls),
                    'protocol_prefix_count')
            tail=[e for e in events[start+1:position] if e['stage'] in ('mandatory_drain','post_drain_observation')]
            drain=value['actual_drain_call'];full=False
            if proof['skip']:
                require(drain is None and not tail,'skipped_native_or_view_work')
                next_call=ordinal+1
            elif drain is not None:
                require(drain['ordinal']==ordinal+1 and drain['ordinal']<len(calls)
                    and adapter.ordered(drain)==adapter.ordered(calls[ordinal+1]),'actual_root_drain')
                full=(drain['role']=='root_same_timestamp_drain' and 'error' not in drain
                    and drain['before']==drain['after']==event['at']
                    and [e['stage'] for e in tail]==['mandatory_drain','post_drain_observation']
                    and adapter.ordered(tail[0]['value'])==adapter.ordered(drain['response'])
                    and adapter.request.native_boundary_complete(drain['response'],event['at'])
                    and tail[1]['value']['view']['now']==event['at'])
                next_call=ordinal+2
            else:next_call=ordinal+1
            completion=gate.after_step(now=event['at'],protocol_call_count=count,
                original_admission_retained=retained,full_root_observation_and_drain_completed=full)
            require(adapter.ordered(completion)==adapter.ordered(value['completion']),'recomputed_completion')
    require(pending is None,'incomplete_final_gate')
    return {'status':'passed_source_bound_chain_data','steps':steps,'skips':skips,
            'native_calls':len(calls),'native_authenticity_certified':False,
            'policy_outbox_replay_still_required':True,'complete_100ms_certified':False}
