"""Restricted stable lifecycle data extension; no native or prediction API.

Supplied snapshots remain conditional, source-authenticated only by the caller's
unchanged endpoint validator. No transition is projected across capture->now.
The three frozen inputs/actions and all original source/action/occupancy checks
remain unchanged. Extra completed E/P facts require delivered destination-owned
receipts; no job is completed by absence from a snapshot.
"""
import copy
from . import live_obligation_domain_guard as old

model=old.model
CONTRACT_FIELDS=old.CONTRACT_FIELDS
PHYSICAL_KINDS=old.PHYSICAL_KINDS
TERMINAL_BY_KIND=old.TERMINAL_BY_KIND
latest_possible_start=old.latest_possible_start
finite,require,unknown=old.finite,old.require,old.unknown
identify_public_case,public_input=old.identify_public_case,old.public_input
construction=old.construction
VERSION='g31.live_obligation.stable_lifecycle.v2'


def completed_prefix(jobs,receipts,records,owners,floor):
    require(type(receipts) is list,'terminal_rows_shape')
    completed={};identities=set()
    for row in receipts:
        jid=row['business_bag_id'];source=row['source_owner']
        require(jid in {'loaded','receiver','blocker'} and jid not in completed,
                'unsupported_or_duplicate_completed_prefix')
        require(row['status']=='completed' and jobs[jid]['status']=='completed'
                and source==owners[jobs[jid]['destination']] and source in records,
                'completed_prefix_destination_authority')
        require(type(row['identity']) is str and row['identity'] and row['identity'] not in identities,
                'completed_prefix_receipt_identity')
        require(finite(row['completed_at']) and 0<=row['completed_at']<=floor
                and row['captured_at']==records[source]['captured_at']
                and row['delivered_at']==records[source]['delivered_at']
                and row['capture_message_id']==records[source]['identity'],
                'completed_prefix_causal_binding')
        identities.add(row['identity']);completed[jid]=row['completed_at']
    require('loaded' in completed and
            {j for j,row in jobs.items() if row['status']=='completed'}==set(completed),
            'complete_delivered_prefix')
    return completed


def stable_stationary(name,t,jobs,completed,*,floor,now,phase,service):
    """Return the next committed deadline, or None for stable terminal empty.

    Every nonempty deadline is strictly future. An equal/past calendar endpoint
    is not a certificate that autonomous work stopped. Rounded inverse bounds
    are outward-conservative; there is no tolerance in business protection.
    """
    require(t['edge_from']==t['edge_to']==-1 and t['service_ready_known'] is True,
            'stationary_known_epoch')
    require(all(finite(t[f]) for f in ('available_at','service_ready_at','load_complete_at'))
            and t['available_at']>=0,'stationary_epoch_shape')
    mode=t['mode'];bound=t['service_ready_at']
    if name=='L':
        require(t['available_at']<=floor,'unsupported_tray_available_epoch')
        if phase=='first_return':
            require(t['ready_kind']=='empty_available_at' and
                    completed['loaded']<=t['available_at']==bound<=floor,
                    'L_available_release')
            return None
        require(t['ready_kind']=='committed_local_service_end' and bound>now
                and latest_possible_start(bound,service[7])<=floor
                and 0<=jobs['reuse1']['loaded_at']<=floor,'L_stable_local_service')
        return bound
    jid={'E':'receiver','P':'blocker'}[name];job=jobs[jid];goal=job['destination']
    require((mode=='empty' and t['business_bag_id']=='') or t['business_bag_id']==jid,
            'stationary_job_identity')
    if mode in ('hold','empty'):
        require(jid in completed and job['status']=='completed' and t['node']==goal
                and t['committed_prefix']==[goal] and t['load_complete_at']==-1.,
                'terminal_tray_completed_receipt_binding')
        expected=completed[jid]+job['hold_seconds']
        require(bound==t['available_at']==expected,'terminal_hold_bound')
        if mode=='hold':
            require(t['ready_kind']=='observed_hold_completion' and bound>now,
                    'terminal_hold_not_stable')
            return bound
        require(t['ready_kind']=='empty_available_at' and bound<=floor,
                'terminal_empty_not_stable')
        return None
    require(jid not in completed,'unfinished_tray_has_completed_receipt')
    if mode=='unloading':
        require(t['node']==goal and t['committed_prefix']==[goal] and job['status']=='unloading'
                and t['ready_kind']=='observed_unload_completion' and t['load_complete_at']==-1.
                and t['available_at']==bound>now and 0<=job['loaded_at']<=floor
                and latest_possible_start(bound,job['unload_seconds'])<=floor,
                'stable_observed_unloading')
        return bound
    if name=='E' and mode=='loading':
        require(t['node']==1 and t['committed_prefix']==[1] and job['status']=='loading'
                and job['loaded_at']==-1. and t['ready_kind']=='observed_load_completion'
                and t['available_at']==t['load_complete_at']==bound>now
                and latest_possible_start(bound,job['load_seconds'])<=floor,
                'E_stable_loading')
        return bound
    require(t['available_at']<=floor,'unsupported_tray_available_epoch')
    if name=='P' and mode=='storage':
        expected=max(job['storage_release_at'],job['storage_entered_at']+job['storage_min_dwell'])
        require(t['node']==9 and t['committed_prefix']==[9] and job['status']=='storage'
                and 0<=job['loaded_at']<=job['storage_entered_at']<=floor and job['storage_released_at']==-1.
                and t['load_complete_at']==-1. and t['ready_kind']=='observed_storage_release_bound'
                and bound==expected>now,'P_stable_storage')
        return bound
    prefixes=({1:[1],3:[1,3],4:[1,3,4]} if name=='E' else {9:[9],3:[9,3],10:[9,3,10]})
    require(mode=='loaded' and job['status']=='in_transit' and t['node'] in prefixes
            and t['committed_prefix']==prefixes[t['node']] and t['load_complete_at']==-1.
            and t['ready_kind']=='committed_local_service_end' and bound>now
            and 0<=job['loaded_at']<=floor
            and latest_possible_start(bound,service[t['node']])<=floor,
            'stable_committed_local_service')
    if name=='P':
        require(0<=job['loaded_at']<=job['storage_entered_at']<=job['storage_released_at']<=floor,
                'P_storage_release_history')
    return bound


def later_bundle(contract,jobs,trays,resources,*,now,phase,source_records,terminal_receipts,
                 owner_pending_tray_requests,entry_receipts,collection_contract):
    try:
        case=identify_public_case(contract,jobs,later=True)
        require(phase in ("first_return","first_reuse_route") and finite(now),"unsupported_phase_or_time")
        require(set(jobs)==model.JOBS and set(trays)=={"L","E","P"},"population")
        # Native's documented default protected_service is True when omitted
        # from the fixed input; the initial public contract ledger records it.
        expected=construction.initial_facts(public_input(case))[0]
        require(all(all(jobs[k][f]==expected[k][f] for f in CONTRACT_FIELDS) for k in jobs),"changed_job_contract")
        require(len(source_records)==2 and {r["owner"] for r in source_records}=={"A","B"},"source_domain")
        floor=min(r["captured_at"] for r in source_records)
        require(finite(floor) and 0<=floor<=now and all(j["arrival"]<=floor for j in jobs.values()),"future_uncaptured_population")
        require(all(finite(j[f]) and (j[f]==-1 or 0<=j[f]<=floor) for j in jobs.values()
            for f in ("loaded_at","storage_entered_at","storage_released_at")),"future_observed_job_epoch")
        require(collection_contract=={"schema":"g31.conditional_collection_quiescence.v1","physical_admissions_quiesced_from":floor,"through":now,"future_python_actions_certified_by_native":False},"quiet_contract")
        require(owner_pending_tray_requests==[],"current_owned_pending_action")
        owners={n["node"]:n["resource_owner"] for n in contract["node_contracts"]}; records={r["owner"]:r for r in source_records}
        require(set(resources)==set(owners),"full_resource_coverage")
        for r in source_records:
            require(r["known_faults"]==[] and r["unresolved_tray_request_ids"]==[],"unresolved_source_action_or_fault")
            actions=r["submitted_physical_actions"];ids=r["submitted_physical_request_ids"]
            require(ids==[a["request_id"] for a in actions] and len(ids)==len(set(ids)) and all(isinstance(i,str) and i for i in ids),"complete_action_ids")
            require([(a["request_id"],a["kind"]) for a in actions]==sorted((a["request_id"],a["kind"]) for a in actions),"action_order")
            for action in actions:
                ack=action.get("last_delivered_ack",{})
                require(action["source_owner"]==r["owner"] and action["kind"] in PHYSICAL_KINDS and type(ack.get("sequence")) is int and ack["sequence"]>0
                    and ack.get("status") in TERMINAL_BY_KIND[action["kind"]] and finite(ack.get("delivered_at")) and 0<=ack["delivered_at"]<floor,"physical_action_not_delivered_terminal_before_capture_union")
            require(set(r["node_ids"])=={n for n,o in owners.items() if o==r["owner"]},"owner_node_coverage")
        completed=completed_prefix(jobs,terminal_receipts,records,owners,floor)
        require(jobs["loaded"]["status"]=="completed" and jobs["reuse2"]["status"]=="waiting_for_tray","lifecycle_scope")
        lt=trays["L"]
        require((lt["node"],lt["mode"],lt["business_bag_id"])==((6,"empty","") if phase=="first_return" else (7,"loaded","reuse1")),"current_L_phase")
        require(jobs["reuse1"]["status"]==("waiting_for_tray" if phase=="first_return" else "in_transit"),"reuse_job_phase")
        require(all(type(t[f]) is int and t[f]>=0 for t in trays.values() for f in ("generation","traversal_id")),"public_tray_identity")
        require(all(t["reception_node"]==-1 for t in trays.values()),"unsupported_additional_lease")
        moving={k:t for k,t in trays.items() if t["edge_to"]>=0};entries={e["tray_id"]:e for e in entry_receipts}
        require(set(entries)==set(moving) and len(entries)==len(entry_receipts),"observed_entry_coverage")
        travel={(u,v):max(.001,length/speed) for u,v,length,speed in contract["edge_records"]};service={n[0]:max(.001,n[2]) for n in contract["node_records"]}
        stability=[]
        for name,t in trays.items():
            source=owners[t["node"]];bound=None
            require(finite(t["available_at"]) and 0<=t["available_at"],"unsupported_tray_available_epoch")
            if name in moving:require(t["available_at"]<=floor,"unsupported_tray_available_epoch")
            if name in moving:
                e=entries[name];edge=t["edge_from"],t["edge_to"];job={"E":"receiver","P":"blocker"}.get(name)
                require(job and edge in ({(1,3),(3,4)} if name=="E" else {(9,3),(3,10)}) and t["node"]==edge[0] and t["mode"]=="loaded" and t["business_bag_id"]==job and jobs[job]["status"]=="in_transit","unsupported_moving_state")
                require(e["source_owner"]==source and e["receipt_event"]=="EDGE_ENTER" and all(e[f]==t[f] for f in ("tray_id","business_bag_id","generation","traversal_id","edge_from","edge_to")),"entry_identity")
                require(all(finite(e[f]) for f in ("entered_at","derived_edge_exit_at","static_edge_travel_seconds")) and 0<=jobs[job]["loaded_at"]<=e["entered_at"]<=floor and e["static_edge_travel_seconds"]==travel[edge] and e["derived_edge_exit_at"]==e["entered_at"]+travel[edge] and now<e["derived_edge_exit_at"],"entry_interval")
                require(t["committed_prefix"]==(([1] if edge==(1,3) else [1,3]) if name=="E" else ([9] if edge==(9,3) else [9,3])),"current_leg_prefix")
                if name=="P":require(0<=jobs[job]["storage_entered_at"]<=jobs[job]["storage_released_at"]<=e["entered_at"],"P_storage_release_history")
                bound=e["derived_edge_exit_at"]
            else:
                bound=stable_stationary(name,t,jobs,completed,floor=floor,now=now,phase=phase,service=service)
            stability.append({"tray_id":name,"source_owner":source,"floor":floor,"now":now,"next_bound":bound})
        for node,r in resources.items():
            occupants=[k for k,t in trays.items() if (t["edge_to"] if t["edge_to"]>=0 else t["node"])==node]
            local=sum(owners[trays[k]["node"]]==owners[node] for k in occupants)
            available=sum(t["node"]==node and t["edge_to"]<0 and t["mode"]=="empty" and t["available_at"]<=now for t in trays.values())
            require(all(type(r[f]) is int for f in ("occupancy","actual_available","unrepresented_occupancy")) and r["occupancy"]==len(occupants) and r["actual_available"]==available and r["unrepresented_occupancy"]==len(occupants)-local,"OR_receiving_occupancy")
        for owner,r in records.items():require(r["unrepresented_occupancy"]==sum(resources[n]["unrepresented_occupancy"] for n,o in owners.items() if o==owner),"source_occupancy_coverage")
        return {"status":"conditional_model_input","phase":phase,"now":now,"jobs":copy.deepcopy(jobs),"trays":copy.deepcopy(trays),"resources":copy.deepcopy(resources),"source_records":copy.deepcopy(source_records),"terminal_receipts":copy.deepcopy(terminal_receipts),"stability":stability,"lifecycle_version":VERSION,"completed_prefix":copy.deepcopy(completed),"conditional_stability_only":True,"current_state_certified":False,"online_information_delivered":False,"native_protection_certified":False}
    except (KeyError,TypeError,ValueError,OverflowError) as e:return unknown(str(e))
