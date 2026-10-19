"""One already-budgeted fresh pair after a real captured unload crosses time.

This extends failed-read eligibility only. A scheduled unload end is never a
terminal receipt. The unchanged actual-client collector must authenticate the
fresh pair and all current/identity/action/occupancy/completion guards before a
physical preference is admitted. No old result is promoted.
"""
from __future__ import annotations
import copy
from . import live_obligation_historical_policy as old
from . import live_obligation_recollection_policy as original
from . import live_obligation_native_view_v2 as representation
from . import live_obligation_lifecycle_state_v2 as lifecycle
from . import planning_capture_v3_contract as capture_contract

adapter,bound=old.adapter,old.bound
PHYSICAL_KINDS,TERMINAL_BY_KIND=old.PHYSICAL_KINDS,old.TERMINAL_BY_KIND
PhaseReplyBudget,local_target,attempt_evidence=old.PhaseReplyBudget,old.local_target,old.attempt_evidence
require,finite=original.require,original.finite
VERSION='g31.observed_unloading_one_fresh_pair.v1'


def crossed_unloading(own,peer,information,pending,view,floor):
    """Supplied source facts only; the caller separately checks native origin."""
    ep=information['raw_endpoints'];now=view['now']
    own_envelope=ep['command']['last_delivered_ack']['planning_snapshot_v3']
    selected=[e for e in ep['received'] if
        e['capture']['capture_v2']['local_capture']['message_id']==pending['peer_message']]
    require(len(selected)==1,'unloading_selected_peer')
    for envelope,source in ((own_envelope,own),(selected[0],peer)):
        require(envelope['status']=='conditional'
            and capture_contract.capture_digest_v3(envelope['capture'])==envelope['payload_sha256']
            and source['static_contract_sha256']==own['static_contract_sha256']
            and source['known_faults']==[]
            and all(finite(v) for v in (source['captured_at'],envelope['delivered_at'],source['valid_until']))
            and pending['at']<=source['captured_at']<=envelope['delivered_at']<=now<source['valid_until']
            and now-source['captured_at']<=.05,'unloading_source_digest_age_or_delivery')
    require(own['source_owner']=='B' and peer['source_owner']=='A','unloading_source_owner')
    rows=[t for t in peer['trays'] if t['tray_id']=='E']
    jobs=[j for j in peer['jobs'] if j['business_bag_id']=='receiver']
    require(len(rows)==len(jobs)==1,'unloading_exact_receiver_identity')
    t,j=rows[0],jobs[0];end=t['service_ready_at']
    require(all(type(t[f]) is int and t[f]>=0 for f in ('generation','traversal_id')),
            'unloading_public_identity')
    require(t['mode']=='unloading' and t['business_bag_id']=='receiver' and t['node']==4
        and t['committed_prefix']==[4] and t['edge_from']==t['edge_to']==t['reception_node']==-1
        and t['service_ready_known'] is True and t['ready_kind']=='observed_unload_completion'
        and t['load_complete_at']==-1. and finite(end) and t['available_at']==end
        and j['status']=='unloading' and j['origin']==1 and j['destination']==4
        and j['unload_seconds']==.1 and finite(j['loaded_at']) and 0<=j['loaded_at']<=floor
        and floor<=peer['captured_at']<end<=now
        and lifecycle.latest_possible_start(end,j['unload_seconds'])<=floor,
        'no_actual_source_unloading_crossed_collection')
    # Native source capture has already bound exact tray/job/public versions.
    # This record preserves them; it never supplies a private receiver state.
    return {'tray_id':'E','business_bag_id':'receiver','source_owner':'A',
        'generation':t['generation'],'traversal_id':t['traversal_id'],
        'source_message_id':peer['message_id'],'source_payload_sha256':selected[0]['payload_sha256'],
        'source_captured_at':peer['captured_at'],'source_delivered_at':selected[0]['delivered_at'],
        'observed_unload_scheduled_end':end,'completion_inferred':False}


def retry_admission(information,pending,view,owned_rows):
    """Keep every old eligibility result, then add one exact first-read case."""
    previous=old.retry_admission(information,pending,view,owned_rows)
    if not (previous.get('reason')=='not_a_supported_recollection_reason'
            and information.get('reasons')==['unsupported_later_model_state']
            and information.get('bundle',{}).get('reasons')==['stable_observed_unloading']):
        return previous
    try:
        safe,equal=representation.equivalent_views(view,information['raw_endpoints']['view'])
        require(equal,'not_the_collected_current_view');view=safe
        owner,now=view['owner_id'],view['now'];phase=pending['phase']
        require(owner=='B' and phase=='first_reuse_route','wrong_deciding_phase')
        require(type(pending.get('recollection_index')) is int and pending['recollection_index']==0,
                'one_fresh_pair_already_used')
        require(information.get('status')=='unknown','not_a_failed_collection')
        require(finite(now) and finite(pending['at']) and 0<=pending['at']<=now,'invalid_current_time')
        own,peer,floor=original._captures(information,pending,owner)
        actions=information['raw_endpoints']['command']['last_delivered_ack'][
            'planning_snapshot_v3']['capture']['capture_v2']['extension']['submitted_physical_actions']
        require(sorted((key,row['kind']) for key,row in owned_rows.items() if row['kind'] in PHYSICAL_KINDS)
            ==sorted((a['request_id'],a['kind']) for a in actions),'current_physical_action_set_changed')
        current=local_target(view,pending['trigger_tray'],phase)
        own_l=[t for t in own['trays'] if t['tray_id']=='L']
        require(len(own_l)==1 and all(own_l[0][f]==current[f] for f in original.TARGET_FIELDS),
                'current_L_differs_from_source_capture')
        crossed=crossed_unloading(own,peer,information,pending,view,floor)
        for row in owned_rows.values():
            require(row['request']['owner_id']==owner,'foreign_owned_request')
            if row['kind'] not in PHYSICAL_KINDS:continue
            ack=row.get('ack',{})
            require(row['terminal'] is True and ack.get('status') in TERMINAL_BY_KIND[row['kind']]
                and finite(ack.get('delivered_at')) and 0<=ack['delivered_at']<=now,
                'current_owned_physical_action_pending')
        epochs=original.sequential_epochs(now);t=own_l[0];service_bound=t['service_ready_at']
        require(t['service_ready_known'] is True and t['ready_kind']=='committed_local_service_end'
            and finite(service_bound) and epochs['physical_wire']<service_bound,
            'insufficient_current_L_service_window')
        return {'status':'conditional_retry_admissible','reason':'observed_unloading_crossed_collection',
            'nominal_epochs':epochs,'original_target':copy.deepcopy(pending['trigger_tray']),
            'retained_own_service_bound':service_bound,'native_success_certified':False,
            'actual_pair_still_required':True,'crossed_source_fact':crossed,
            'unload_completion_still_requires_actual_delivered_receipt':True}
    except (KeyError,TypeError,ValueError,OverflowError) as error:
        return {'status':'not_admitted','reason':str(error),'native_success_certified':False}


class OwnerPolicy(old.OwnerPolicy):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        # Preserve the exact per-owner actual-client collector and capability
        # checks installed by the old constructor; replace only eligibility.
        source=self.decide_pending.__func__
        decision=old.clone(source,{**source.__globals__,'retry_admission':retry_admission})
        self.decide_pending=decision.__get__(self,type(self))
