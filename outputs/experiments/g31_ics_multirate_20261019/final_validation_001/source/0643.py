"""Complete finite endpoint/physical verifier plus source-bound query replay.

No native/predictor execution. The old root first-hop/ACK/drain checks remain;
every omitted observation is additionally tied to the actual advance chain and
full original outbox mutation sequence, not supplied projected state alone.
"""
from __future__ import annotations
import bisect
import copy
from . import initial_owner_route_campaign_v3 as old_campaign
from . import verify_initial_owner_route_campaign_v3 as old
from . import initial_owner_route_gate_campaign as c
from . import initial_owner_route_gated_evidence as integration
from . import initial_owner_route_gate_adapter as gate
from . import initial_owner_route_outbox_trace as trace
from . import verify_initial_owner_route_gate_adapter as chain_verifier

require=c.require
exact=old.exact


def transport_lineage(raw):
    roots=raw['owner_activation_admissions'];creations=raw['request_creations']
    identities={};clocks=[];expected={};previous=-1
    for index,row in enumerate(roots):
        identity=f"activation:{index}:{row['owner']}"
        require(row['owner'] in ('A','B') and row['root_id']==identity
            and row['scope']=='owner_activation_proxy' and type(row['accepted_wall_ns']) is int
            and previous<=row['accepted_wall_ns'] and trace._logical(row['accepted_at']),
            'actual_admission_identity_clock')
        identities[identity]=row;expected[identity]=[];clocks.append(row['accepted_wall_ns'])
        previous=row['accepted_wall_ns']
    first=[]
    for call in raw['calls']:
        if call['retry']:continue
        identity=call['request']['request_id'];first.append(identity)
        require(identity in creations,'missing_creation_record')
        creation=creations[identity];owner=call['request']['owner_id'];root=creation['creating_root']
        require(root in identities and identities[root]['owner']==owner
            and identities[root]['accepted_at']==call['at'] and creation['kind']==call['kind'],
            'creation_actual_admission')
        expected[root].append(identity)
    require(first==list(creations),'complete_creation_order')
    for identity,row in identities.items():
        require(row['protocol_ids']==expected[identity],'actual_admission_protocol_ids')
    for read in raw['outbox_query_trace']['reads']:
        if 'error' in read:continue
        index=bisect.bisect_right(clocks,read['started_ns'])-1
        expected_root=roots[index]['root_id'] if index>=0 else None
        require(read['handling_root']==expected_root and (index<0 or
            roots[index]['accepted_at']<=read['at']),'query_handling_root_not_actual_context')
    return len(roots)


def complete_query_replay(raw):
    data=raw['outbox_query_trace']
    if data['invalid'] is not None:
        require(raw['failure'],'invalid_trace_without_failure')
        return {'status':'unknown_failed_actual_query_trace','closed_scope':False,
            'error':data['invalid'],'queries':len(data['reads'])}
    inventory=trace.verify_refresh_inventory(data,raw['calls'],raw['request_creations'])
    admissions=transport_lineage(raw)
    replay=trace.Replay(data,raw['calls'],raw['request_creations'])
    records=raw['root_records']
    checkpoints=0
    if records:
        root=records[0]['value']['evidence'];proof=root['runtime_query_proof'];cursor=proof['checkpoint']
        require(proof['schema']=='g31.initial_root.complete_runtime_query_proof.v1'
            and proof['saved_data_grants_native_authority'] is False and cursor['invalid'] is None,
            'runtime_proof_scope')
        for event in root['events']:
            if event['stage'] not in ('root_observation_gate','root_observation_gate_completion'):continue
            mark=event['value']['outbox_checkpoint']
            require(mark['invalid'] is None,'invalid_gate_outbox_checkpoint')
            replay.advance(mark['query_prefix'],mark['call_prefix'])
            require(mark['ack_handling_prefix']==len(replay.handling),'gate_ACK_handling_prefix')
            if event['stage']=='root_observation_gate':
                inputs=event['value']['inputs']
                require(inputs['protocol_call_count']==mark['call_prefix'] and
                    exact(inputs['outbox'],gate.project_outbox(replay.rows)),
                    'gate_not_full_outbox_reconstruction')
            else:
                require(event['value']['protocol_call_count_after']==mark['call_prefix'],
                        'completion_actual_send_prefix')
            if mark['query_prefix']:
                require(data['reads'][mark['query_prefix']-1]['query_finished_ns']<=event['wall_ns'],
                        'gate_uses_future_query')
            checkpoints+=1
        replay.advance(cursor['query_prefix'],cursor['call_prefix'])
        require(cursor['ack_handling_prefix']==proof['ack_handling_count']==len(replay.handling)
            and exact(proof['outbox'],replay.rows),'encoded_root_complete_outbox')
        require(exact(proof['calls'],raw['calls'][:cursor['call_prefix']])
            and list(proof['creations'])==list(replay.rows)
            and all(exact(value,raw['request_creations'][key]) for key,value in proof['creations'].items()),
            'encoded_root_call_creation_prefix')
        t=proof['trace'];full=data
        require(t['schema']==full['schema'] and t['invalid'] is None
            and exact(t['reads'],full['reads'][:cursor['query_prefix']])
            and exact(t['ack_bodies'],full['ack_bodies'][:replay.body])
            and exact(t['refreshes'],full['refreshes'][:len(t['refreshes'])])
            and (not t['refreshes'] or t['refreshes'][-1]['after_query']==cursor['query_prefix']),
            'encoded_root_actual_query_prefix')
        body_end=records[0]['value']['body_finished_ns']
        require(proof['admission_count']==bisect.bisect_right(
            [row['accepted_wall_ns'] for row in raw['owner_activation_admissions']],body_end)
            and cursor['query_prefix']==bisect.bisect_right(
                [row['query_finished_ns'] for row in data['reads']],body_end),
            'encoded_root_admission_or_query_prefix')
        audit=raw['observation_gate_audit']
        require(exact(proof['advance_calls'],audit['calls'][:len(proof['advance_calls'])]) if audit
            else proof['advance_calls']==[],'encoded_root_advance_prefix')
    replay.advance(len(data['reads']),len(raw['calls']));state=replay.finish()
    require(exact(state['rows'],raw['outbox']) and exact(state['ack_handling'],raw['ack_handling']),
            'complete_actual_outbox_or_ACK_handling')
    return {**inventory,'status':'passed_complete_actual_refresh_outbox_replay',
        'gate_checkpoints':checkpoints,'admissions':admissions,
        'all_internal_native_query_replay_claimed':False}


def verify_branch(raw,row,key):
    report=_original_verify_branch(raw,row,key)
    report['query_replay']=complete_query_replay(raw)
    audit=raw['observation_gate_audit']
    if audit is not None:
        events=raw['root_records'][0]['value']['evidence']['events'] if raw['root_records'] else []
        if raw['failure'] is None:
            report['observation_gate']=chain_verifier.verify(events,raw['native_batches'],audit,
                raw['owner_activation_admissions'],raw['calls'],key.replace('/',':'))
            report['observation_gate']['policy_outbox_replay_still_required']=False
            report['observation_gate']['outbox_complete_replay']=True
            report['observation_gate']['background_policy_basis']='Pinned unchanged fixed owner source; original decision/endpoint/physical checks, not every internal query replay.'
        else:
            report['observation_gate']={'status':'unknown_failed_branch','native_calls':len(audit['calls'])}
    else:
        require(raw['failure'],'missing_actual_chain_without_failure')
        report['observation_gate']={'status':'unknown_unbound_actual_chain'}
    return report


# Preserve exact v3 verification functions in an independent closed namespace.
_namespace={**vars(old),'c':c,'verify_branch':verify_branch}
for _name in ('root_replay','endpoint_replay','immutable_calls','rpc_replay','pair_comparison',
              'predictor_lifetime','branch_attempt','verify_saved'):
    _namespace[_name]=globals()[_name]=integration.private(getattr(old,_name),_namespace)
_original_verify_branch=integration.private(old.verify_branch,_namespace)
