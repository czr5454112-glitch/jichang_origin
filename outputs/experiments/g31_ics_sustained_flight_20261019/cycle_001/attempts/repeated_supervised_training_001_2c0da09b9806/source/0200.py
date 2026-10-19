"""Conditional historical-arrival bounds from the deciding owner's own ACK.

Pure supplied-data validation only. It cannot authenticate a native endpoint or
mint a collection capability. The current raw tray ready field is never changed.
The only supported consumer is B/first_reuse_route in the frozen three-case
finite domain. An old message is historical evidence, not a fresh observation.
"""
from __future__ import annotations
import copy
from . import live_obligation_domain_guard as base

SCHEMA = 'g31.conditional_historical_goal_service_bound.v1'
require,finite=base.require,base.finite


def local(envelope): return envelope['capture']['capture_v2']['local_capture']


def derive_goal_service_bounds(view, own_ack, received, *, retained, own_actions,
                              own_publication_requests, phase):
    """Return separate derived facts; all inputs still require the native adapter.

`own_publication_requests` is the caller's immutable owner-local command ledger,
not a list fabricated from message contents. A future native adapter must obtain
it from its actual ProtocolClient. Saved replay may bind it to actual call tape.
"""
    owner,now=view['owner_id'],view['now']
    require(owner=='B' and phase=='first_reuse_route','historical_deciding_owner_or_phase')
    require(type(own_publication_requests) is dict,'historical_immutable_publication_ledger')
    pair=[own_ack['planning_snapshot_v3'],*received]
    require(len(pair)==2 and {local(e)['source_owner'] for e in pair}=={'A','B'},'historical_current_pair')
    floor=min(local(e)['captured_at'] for e in pair)
    own_current=next(local(e) for e in pair if local(e)['source_owner']==owner)
    target=[t for t in own_current['trays'] if t['tray_id']=='L']
    require(len(target)==1 and target[0]['mode']=='loaded' and target[0]['business_bag_id']=='reuse1'
            and target[0]['node']==7 and target[0]['edge_from']==target[0]['edge_to']==-1
            and target[0]['service_ready_known'] is True
            and target[0]['ready_kind']=='committed_local_service_end'
            and finite(target[0]['service_ready_at']) and now+.01<target[0]['service_ready_at'],
            'historical_target_wire_outside_service_window')
    contract=base.model.public_contract(view)
    contract['native_semantics']=copy.deepcopy(base.model.SUPPORTED_NATIVE_SEMANTICS)
    base.identify_public_case(contract,retained['contracts'],later=True)
    for envelope in pair:
        capture=local(envelope)
        require(base.capture_digest_v3(envelope['capture'])==envelope['payload_sha256']
                and capture['static_contract_sha256']==retained['static_contract_sha256']
                and all(finite(v) for v in (capture['captured_at'],envelope['delivered_at'],capture['valid_until']))
                and 0<=capture['captured_at']<=envelope['delivered_at']<=now<capture['valid_until']
                and now-capture['captured_at']<=.05,'historical_current_pair_digest_or_age')
    owners={n['node']:n['resource_owner'] for n in contract['node_contracts']}
    service={n[0]:max(.001,n[2]) for n in contract['node_records']}
    candidates=[(local(e),t) for e in pair for t in local(e)['trays']
                if t['tray_id'] in ('E','P') and t['mode']=='loaded' and t['edge_to']==-1
                and t['node']==retained['contracts'][t['business_bag_id']]['destination']
                and t['service_ready_at']<=now]
    require(len(candidates)==1,'historical_exact_one_goal_epoch')
    current,tray=candidates[0]; name=tray['tray_id']; jid=tray['business_bag_id']
    require((name,jid,tray['node']) in (('E','receiver',4),('P','blocker',10)),'historical_goal_domain')
    require(current['source_owner']==owners[tray['node']] and current['static_contract_sha256']==retained['static_contract_sha256']
            and tray['service_ready_known'] is True and tray['ready_kind']=='committed_local_service_end'
            and finite(tray['service_ready_at']) and tray['service_ready_at']==current['captured_at']
            and tray['edge_from']==tray['edge_to']==tray['reception_node']==-1
            and tray['load_complete_at']==-1. and finite(tray['available_at']) and 0<=tray['available_at']<=floor,
            'historical_current_goal_state')
    require(all(type(tray[f]) is int and tray[f]>=0 for f in ('generation','traversal_id')),'historical_current_identity_type')
    matches=[]
    commands=view['client_commands']
    require(len({c['request_id'] for c in commands})==len(commands),'historical_duplicate_command_identity')
    for index,command in enumerate(commands):
        ack=command.get('last_delivered_ack',{});envelope=ack.get('planning_snapshot_v3')
        if envelope is None: continue
        body=envelope['capture'];capture=local(envelope)
        entries=[e for e in body['extension']['source_observed_inflight']
            if all(e.get(f)==tray[f] for f in ('tray_id','business_bag_id','generation','traversal_id'))
            and e.get('edge_to')==tray['node']]
        if not entries:continue
        require(len(entries)==1,'historical_duplicate_entry')
        entry=entries[0];request=own_publication_requests.get(command['request_id'])
        require(type(request) is dict and request.get('request_id')==command['request_id']
                and request.get('owner_id')==owner and request.get('target_owner')=='A'
                and request.get('kind')=='planning_snapshot_v3'
                and request.get('message_delay')==request.get('publication_delay')==.01
                and request.get('expiry')==capture['valid_until'],'historical_own_immutable_request_binding')
        require(command.get('kind')=='planning_snapshot_v3' and command.get('status')=='acknowledged'
                and type(command.get('attempt')) is int and command['attempt']>=1
                and ack.get('status')=='delivered' and type(ack.get('sequence')) is int and ack['sequence']>=1
                and type(ack.get('attempt')) is int and ack['attempt']>=1,
                'historical_terminal_self_ack')
        require(envelope.get('schema')=='g31.planning_snapshot.v3' and envelope.get('kind')=='planning_snapshot_v3'
                and envelope.get('digest_format')=='g31.planning_capture_digest.v3'
                and envelope.get('status')=='conditional' and body.get('schema')=='g31.planning_capture.v3'
                and base.capture_digest_v3(body)==envelope['payload_sha256'],'historical_payload_digest')
        require(capture['schema']=='g31.planning_capture.v1' and capture['source_owner']==owner and capture['target_owner']=='A'
                and type(capture['message_id']) is str and capture['message_id']
                and type(capture['publication_sequence']) is int and capture['publication_sequence']>0
                and capture['static_contract_sha256']==retained['static_contract_sha256']
                and capture['known_faults']==[] and capture['semantics']==current['semantics'],
                'historical_channel_contract')
        epochs=[capture['captured_at'],envelope['delivered_at'],ack.get('executed_at'),ack.get('completed_at'),
                ack.get('delivered_at'),capture['valid_until']]
        require(all(finite(v) for v in epochs)
                and 0<=capture['captured_at']==ack['executed_at']<=envelope['delivered_at']==ack['completed_at']
                <=ack['delivered_at']<floor<=now<capture['valid_until']
                and ack['result_id']==capture['message_id'],'historical_delivery_before_union')
        checked=base.validate_inflight(body,contract,now=ack['delivered_at'],delivered_at=envelope['delivered_at'])
        require(checked['status']=='conditional_inflight_extension_data','historical_entry_valid_when_available')
        extension=base.validate_extension(body['capture_v2']['extension'],source_owner=owner,
            captured_at=capture['captured_at'],node_owners=owners,retained_job_contracts=retained['contracts'],
            local_action_ledger=own_actions)
        require(extension['status']=='conditional_extension_data' and extension['unresolved_request_ids']==[],
                'historical_source_action_scope')
        old_trays=[t for t in capture['trays'] if t['tray_id']==name]
        require(len(old_trays)==1,'historical_tray_coverage');previous=old_trays[0]
        require(previous['mode']=='loaded' and previous['node']==entry['edge_from']
                and owners[previous['node']]==owner and entry['source_owner']==owner
                and all(previous[f]==entry[f] for f in ('tray_id','business_bag_id','generation','traversal_id','edge_from','edge_to'))
                and previous['committed_prefix']+[entry['edge_to']]==tray['committed_prefix'],
                'historical_continuous_final_edge_identity')
        arrival=entry['derived_edge_exit_at'];bound=arrival+service[tray['node']]
        require(finite(arrival) and finite(bound) and capture['captured_at']<arrival<=floor<=now<bound,
                'historical_goal_service_stable_interval')
        matches.append({'schema':SCHEMA,'deciding_owner':owner,'tray_id':name,'business_bag_id':jid,
            'generation':tray['generation'],'traversal_id':tray['traversal_id'],
            'current_source_owner':current['source_owner'],'current_message_id':current['message_id'],
            'current_captured_at':current['captured_at'],'raw_service_ready_at':tray['service_ready_at'],
            'historical_endpoint':f'view.client_commands[{index}].last_delivered_ack.planning_snapshot_v3',
            'own_request_id':command['request_id'],'historical_message_id':capture['message_id'],
            'payload_sha256':envelope['payload_sha256'],'static_contract_sha256':capture['static_contract_sha256'],
            'historical_captured_at':capture['captured_at'],'historical_delivered_at':envelope['delivered_at'],
            'self_ack_delivered_at':ack['delivered_at'],'valid_until':capture['valid_until'],
            'observed_entry':copy.deepcopy(entry),'derived_arrival_at':arrival,
            'public_goal_service_seconds':service[tray['node']],'derived_service_end':bound,
            'arithmetic':'derived_edge_exit_at + max(minimum_service_seconds, public_node_service_seconds)',
            'floor':floor,'now':now,'conditional_stability_only':True,'actual_terminal_receipt':False,
            'native_delivery_verified':False,'current_state_certified':False})
    require(len(matches)==1,'historical_missing_or_ambiguous_own_delivered_entry')
    return {name:matches[0]}
