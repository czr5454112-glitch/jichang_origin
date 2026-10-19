"""One exact API replay plus independent original-map lifecycle/clock audit.

No NativeSession is constructed. Peer action identifiers remain opaque in
policy replay. Offline receipts separately establish what actually happened.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
from . import research_original_cooperative_bridge as r

base,policy=r.base,r.policy
require=base.require


def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
def ordered(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def semantic_api(row):
    row=deepcopy(row)
    if row['endpoint']=='advance_to':
        wall=row['result'].pop('wall_seconds')
        require(finite(wall),'bridge_native_wall');
    return ordered(row)


def physical_outcomes(data,raw,plan):
    jobs={j['business_bag_id']:j for j in data['jobs']};actual={j['business_bag_id']:j for j in raw['result']['jobs']}
    require(len(jobs)==len(data['jobs'])==len(actual)==len(raw['result']['jobs'])==28506 and jobs.keys()==actual.keys(),'bridge_alloffered')
    require(len({(j['origin'],j['arrival']) for j in jobs.values()})==28506,'bridge_unproved_equal_arrival_order')
    initial={t['tray_id']:t for t in data['trays']};trays={t['tray_id']:t for t in raw['result']['trays']}
    require(len(initial)==len(data['trays'])==len(trays)==len(raw['result']['trays'])==22 and initial.keys()==trays.keys(),'bridge_alltrays')
    parking=plan['parking_plan']['parking'];parks={p['request_id']:p for p in parking};token=plan['parking_plan']['token_tray_id']
    require(len(parks)==22 and {p['tray_id'] for p in parking}==initial.keys(),'bridge_parking_domain')
    actions=r.operations(raw);selected=[x for x in actions if x['kind']=='direct_supply'];bridges=[x for x in actions if x['kind']=='bridge_empty']
    ids=[x['request_id'] for x in actions];selected_ids=[x['job']['business_bag_id'] for x in selected]
    require(len(ids)==len(set(ids))<=policy.MAX_EMPTY_OPERATIONS and len(selected_ids)==len(set(selected_ids))<=39,'bridge_action_bound')
    require(all(x['kind'] in ('direct_supply','bridge_empty') for x in actions),'bridge_action_kind')
    physical={};calls={}
    for owner in raw['owners']:
        require(len(owner['bridge_publications'])<=policy.MAX_PUBLICATIONS and len(owner['consumed_completions'])==len(set(owner['consumed_completions'])),'bridge_publication_receipt_bound')
        for call in owner['calls']:
            require(finite(call['submit_compute_ms']),'bridge_submit_clock')
            p=call['request'];rid=p['request_id'];require(p['owner_id']==owner['owner'],'bridge_call_owner')
            if rid in calls:require(ordered(calls[rid])==ordered(p) and call['retry'] is True,'bridge_mutable_retry')
            else:require(call['retry'] is False,'bridge_missing_original_submit');calls[rid]=p
            if call['kind']=='transfer':physical[rid]=p
    require(set(physical)==set(parks)|set(ids) and len(physical)<=policy.MAX_PHYSICAL,'bridge_physical_inventory')
    for rid,p in physical.items():
        if rid in parks:require(all(p[k]==parks[rid][k] for k in ('tray_id','source','destination')),'bridge_parking_changed')
        else:require(p['tray_id']==token,'bridge_other_carrier')
    receipts=raw['result']['receipts'];empty={};witnesses=[]
    for rid,p in physical.items():
        rows=[x for x in receipts if x['event']=='EMPTY_RECEIVED' and x['reason']==rid]
        require(len(rows)<=1,'bridge_duplicate_receive')
        if rows:
            row=rows[0];require(row['tray_id']==p['tray_id'] and row['node']==p['destination'] and finite(row['time']) and row['time']<=raw['physical_time'],'bridge_actual_arrival')
            empty[rid]=row
    for selected_action in selected:
        jid=selected_action['job']['business_bag_id'];require(jid in jobs and selected_action['job']['origin']==jobs[jid]['origin'],'bridge_job_contract')
        rows={event:[x for x in receipts if x['event']==event and x['business_bag_id']==jid]
            for event in ('LOAD_START','LOAD_COMPLETE','UNLOAD_COMPLETE','HOLD_COMPLETE')}
        require(all(len(v)<=1 for v in rows.values()),'bridge_duplicate_job_event')
        require(all(x['tray_id']==token for group in rows.values() for x in group),'bridge_job_token')
        if not all(rows.values()):continue
        load,loaded,unload,hold=(rows[e][0] for e in rows)
        job=jobs[jid];received=empty.get(selected_action['request_id'])
        require(received is not None and all(finite(x['time']) for x in (load,loaded,unload,hold))
            and selected_action['at']<=received['time']<=load['time']<=loaded['time']<=unload['time']<=hold['time']<=raw['physical_time']
            and load['node']==loaded['node']==job['origin'] and unload['node']==hold['node']==job['destination']
            and actual[jid]['status']=='completed' and actual[jid]['completed_at']==unload['time'],'bridge_job_lifecycle')
        earlier=[j for j in jobs.values() if j['origin']==job['origin'] and (j['arrival'],j['business_bag_id'])<(job['arrival'],jid) and j['arrival']<=load['time']]
        prior_loads={x['business_bag_id']:x['time'] for x in receipts if x['event']=='LOAD_START' and x['time']<load['time']}
        require(all(j['business_bag_id'] in prior_loads for j in earlier),'bridge_skipped_original_fifo')
        storage={'required':job['storage_node']>=0,'observed':False}
        if job['storage_node']>=0:
            entry=[x for x in receipts if x['business_bag_id']==jid and x['event']=='STORAGE_ENTER']
            release=[x for x in receipts if x['business_bag_id']==jid and x['event']=='STORAGE_RELEASE']
            # Frozen runtime names are checked below against existing actual005.
            require(len(entry)==len(release)==1 and entry[0]['node']==release[0]['node']==job['storage_node']
                and loaded['time']<=entry[0]['time']<=release[0]['time']<=unload['time']
                and release[0]['time']>=max(job['storage_release_at'],entry[0]['time']+job['storage_min_dwell']),'bridge_mandatory_storage')
            storage.update(observed=True,entry=entry[0],release=release[0])
        witnesses.append({'job':jid,'request_id':selected_action['request_id'],'load':load,'loaded':loaded,'unload':unload,'hold':hold,'storage':storage})
    actual_loads=[x for x in receipts if x['event']=='LOAD_START'];unloaded=[x for x in receipts if x['event']=='UNLOAD_COMPLETE']
    require(all(x['tray_id']==token and x['business_bag_id'] in selected_ids for x in actual_loads)
        and len({x['business_bag_id'] for x in actual_loads})==len(actual_loads),'bridge_unselected_load')
    completed=[jid for jid,j in actual.items() if j['status']=='completed']
    require(set(completed)=={x['business_bag_id'] for x in unloaded} and set(completed)<=set(selected_ids),'bridge_completion_scope')
    by_supply={w['request_id']:w for w in witnesses};seen_completion=set()
    for index,action in enumerate(actions):
        if index==0:require(action['first'] and action['kind']=='direct_supply','bridge_first_supply')
        else:
            previous=actions[index-1]
            if previous['kind']=='direct_supply':
                require(previous['request_id'] in by_supply and by_supply[previous['request_id']]['hold']['time']<=action['at'],'bridge_before_return_hold')
            else:require(action['kind']=='direct_supply' and previous['request_id'] in empty and empty[previous['request_id']]['time']<=action['at'],'bridge_chain_or_before_empty_arrival')
            decision=action['decision'];permit=decision['possession_permit'];current=permit['current_token']
            require(current['tray_id']==token and current['node']==action['source'] and current['mode']=='empty'
                and current['edge_to']<0 and current['reception_node']<0 and current['available_at']<=action['at'],'bridge_possession_receipt')
            if action['kind']=='bridge_empty':
                proof=decision['choice']['completion_permit'];rid=proof['receipt_id']
                require(rid not in seen_completion,'bridge_completion_reuse');seen_completion.add(rid)
                matches=[w for w in witnesses if w['job']==proof['business_bag_id']]
                require(len(matches)==1 and matches[0]['unload']['time']==proof['completed_at']
                    and matches[0]['hold']['time']<=current['available_at']<=action['at'],'bridge_completion_not_actual_return')
    stationary=[]
    for p in parking:
        if p['tray_id']==token:continue
        t=trays[p['tray_id']]
        if p['request_id'] in empty:
            require(not any(x['tray_id']==p['tray_id'] and x['event'] in ('EDGE_ENTER','EDGE_EXIT','LOAD_START')
                and x['time']>empty[p['request_id']]['time'] for x in receipts),'bridge_parked_tray_moved_after_arrival')
        if p['request_id'] in empty and t['node']==p['destination'] and t['mode']=='empty' and t['job']==-1 and t['edge_to']<0 and t.get('reception_node',-1)<0:
            stationary.append(p['tray_id'])
    final=trays[token];empty_token=(final['mode']=='empty' and final['job']==-1 and final['edge_to']<0 and final.get('reception_node',-1)<0 and finite(final['available_at']) and final['available_at']<=raw['physical_time'])
    return {'offered':28506,'arrived':sum(j['arrival']<=raw['physical_time'] for j in jobs.values()),
        'completed':completed,'unfinished_offered':28506-len(completed),'status_counts':dict(Counter(j['status'] for j in actual.values())),
        'total_tray_identities':22,'startup_parking_requests':22,'noncirculating_parked_trays':stationary,
        'same_token':token,'postparking_empty_requests':len(actions),'direct_supplies':len(selected),'bridges':len(bridges),
        'physical_payloads':physical,'actual_empty_arrivals':empty,'completion_witnesses':witnesses,
        'all_selected_returned':len(witnesses)==len(selected),'final_token':final,'final_token_empty':empty_token}


def validate_clocks(path,manifest,owner_calls):
    api=[];owners=[];last=0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line);a,b=row['start_ns'],row['end_ns']
            require(type(a) is int and type(b) is int and 0<=a<=b and b>=last,'bridge_clock_order');last=b
            if row['scope']=='complete_frozen_api_and_tape_write':
                require(row['ordinal']==len(api) and len(api)<len(manifest)
                    and row['endpoint']==manifest[len(api)]['endpoint'],'bridge_api_clock_scope');api.append(row)
            else:
                require(row['scope']=='owner_activation_including_tape_clocks' and finite(row['logical_time'])
                    and type(row['first_api']) is int and type(row['after_api']) is int
                    and 0<=row['first_api']<=row['after_api']<=len(api),'bridge_owner_clock_scope')
                require(all(a<=x['start_ns']<=x['end_ns']<=b for x in api[row['first_api']:row['after_api']]),'bridge_nested_clock')
                owners.append(row)
    require(len(api)==len(manifest),'bridge_missing_api_clock')
    require([{k:x[k] for k in ('owner','logical_time','first_api','after_api')} for x in owners]==owner_calls,'bridge_owner_clock_replay')
    return {'api_intervals':len(api),'owner_activations':len(owners),'api_wall_ns':sum(x['end_ns']-x['start_ns'] for x in api),
        'owner_wall_ns':sum(x['end_ns']-x['start_ns'] for x in owners),
        'scope':'Nested diagnostic scopes; never summed together or divided by requests. Full child/parent elapsed is authority; no production per-job timing certificate.'}


def classify_observation(assessment,outcomes,audit,relay_evidence):
    complete=(assessment['full_horizon_without_policy_failure'] and assessment['all_physical_received']
        and audit['status']=='passed' and len(outcomes['noncirculating_parked_trays'])==21
        and outcomes['all_selected_returned'] and outcomes['final_token_empty']
        and len(outcomes['actual_empty_arrivals'])==len(outcomes['physical_payloads']))
    cap_reached=outcomes['postparking_empty_requests']>=policy.MAX_EMPTY_OPERATIONS or len(outcomes['completed'])>=policy.MAX_TOKEN_COMPLETIONS
    cap_closed=(cap_reached and len(relay_evidence)==2 and all(x['status']=='actual_fresh_cap_proof_and_delivered_relay' for x in relay_evidence.values()))
    return complete,('complete_bidirectional_cap_relay' if cap_closed else ('unknown_missing_cap_proof_or_relay' if cap_reached else 'not_reached_not_certified'))


def verify_case(directory):
    plan=base.read(directory/'preregistered_protocol.json');r.verify_pins(directory,plan)
    raw=base.gzread(directory/'raw_final.json.gz');data=base.gzread(directory/'input.json.gz')
    relay_ids={o['cap_relay']['request_id'] for o in raw['owners'] if o.get('cap_relay') and o['cap_relay']['request_id']}
    cap_proofs={};submits={};queries={};frames={};latest={};owner_calls=[];old=Path(plan['bootstrap_reference'])
    oldraw=base.gzread(old/'raw_final.json.gz');first=next(o['supply'] for o in oldraw['owners'] if o['supply'])
    oldmanifest=[json.loads(line) for line in (old/'api/manifest.jsonl').read_text().splitlines()]
    compared=0;prefix_closed=False
    class ObservedTape(base.ReplayTape):
        def __getattr__(self,name):
            method=super().__getattr__(name)
            def call(*args,**kwargs):
                nonlocal compared,prefix_closed
                at,ordinal=self.physical_time,self.index;value=method(*args,**kwargs)
                row={'ordinal':ordinal,'endpoint':name,'args':base.canonical(args),'kwargs':base.canonical(kwargs),'before':at,'result':deepcopy(value),'after':self.physical_time}
                if not prefix_closed:
                    require(ordinal<len(oldmanifest),'bridge_bootstrap_missing')
                    oldpath=old/'api'/oldmanifest[ordinal]['path'];require(base.sha(oldpath)==oldmanifest[ordinal]['sha256'],'bridge_old_tape_changed')
                    require(semantic_api(row)==semantic_api(base.gzread(oldpath)),'bridge_startup_api_difference');compared+=1
                    if name=='advance_to' and at==first['at'] and self.physical_time>at:prefix_closed=True
                if name in ('observe_protocol_control_policy_recent','protocol_planning_snapshots_v2'):latest[(name,args[0])]=row
                if name=='submit_protocol_transfer' and args[0]['request_id'] not in submits:
                    rid=args[0]['request_id'];submits[rid]=row
                    frames[rid]={k[0]:deepcopy(v) for k,v in latest.items() if k[1]==args[0]['owner_id']}
                elif name=='submit_protocol_command' and args[0]['request_id'] in relay_ids:submits.setdefault(args[0]['request_id'],row)
                elif name=='protocol_command' and args[1] in relay_ids:queries.setdefault(args[1],[]).append(row)
                return value
            return call
    class ObservedOwner(policy.BridgeOwner):
        def activate(self):
            before=self.session.index;was=self.cap_observed
            try:super().activate()
            finally:owner_calls.append({'owner':self.owner,'logical_time':self.session.physical_time,'first_api':before,'after_api':self.session.index})
            if not was and self.cap_observed:
                require(self.owner not in cap_proofs,'bridge_duplicate_cap_transition')
                cap_proofs[self.owner]={'before_api':before,'after_api':self.session.index,'relay':deepcopy(self.cap_relay)}
    replay_run=r.clone(policy.run_policy,{**policy.run_policy.__globals__,'BridgeOwner':ObservedOwner})
    private=r.isolated_base(ReplayTape=ObservedTape,run_policy=replay_run)
    replay=private.verify_saved(directory)
    require(prefix_closed,'bridge_incomplete_bootstrap_prefix')
    outcomes=physical_outcomes(data,raw,plan)
    for action in r.operations(raw):
        rid=action['request_id'];actual=submits.get(rid);require(actual is not None and actual['before']==action['at'],'bridge_actual_submit_missing')
        require(actual['args'][0]==outcomes['physical_payloads'][rid],'bridge_actual_payload')
        if not action['first']:
            frame=frames[rid];view=frame['observe_protocol_control_policy_recent'];peer=frame['protocol_planning_snapshots_v2']
            require(view['before']==peer['before']==action['at'] and view['ordinal']<peer['ordinal']<actual['ordinal'],'bridge_current_api_order')
            permit=action['decision']['possession_permit'];token=next(t for t in view['result']['trays'] if t['tray_id']==outcomes['same_token'])
            require(token==permit['current_token'] and permit['delivered_peer'] in peer['result'],'bridge_actual_possession_frame')
    relay_evidence={}
    for owner in raw['owners']:
        who=owner['owner'];historical=policy.cap_relay_evidence(owner,plan['parking_plan'],plan['public_contract'])
        proof=cap_proofs.get(who);row={'historical':historical,'status':'unknown'};relay_evidence[who]=row
        if proof is None or historical['status']!='historical_delivered_cap_relay':continue
        relay=owner['cap_relay'];rid=relay['request_id'];submission=submits.get(rid)
        require(proof['relay']==relay and submission is not None and proof['before_api']<=submission['ordinal']<proof['after_api']
            and submission['before']==submission['after']==relay['at'] and submission['args'][0]==owner['outbox']['outbox'][rid]['payload'],'bridge_cap_actual_submit')
        ack=owner['outbox']['outbox'][rid]['client_view']['last_delivered_ack']
        matches=[q for q in queries.get(rid,[]) if q['result'].get('last_delivered_ack')==ack]
        require(matches and all(q['args']==[who,rid] and q['before']==q['after']>=ack['delivered_at'] for q in matches),'bridge_cap_actual_query')
        pubs=[x for x in owner['bridge_publications'] if x['reason']['kind']=='terminal_cap_barrier_relay']
        require(len(pubs)==1 and pubs[0]['request_id']==rid,'bridge_cap_once')
        row.update(status='actual_fresh_cap_proof_and_delivered_relay',proof=proof,submit_ordinal=submission['ordinal'],ack_query_ordinals=[q['ordinal'] for q in matches])
    manifest=[json.loads(line) for line in (directory/'api/manifest.jsonl').read_text().splitlines()]
    clocks=validate_clocks(directory/'service_clocks.jsonl',manifest,owner_calls)
    assessment=r.assess(raw,plan)
    complete,assessment['cap_certificate']=classify_observation(assessment,outcomes,raw['physical_audit'],relay_evidence)
    require(type(raw['native_state_sha256']) is str and len(raw['native_state_sha256'])==64 and all(c in '0123456789abcdef' for c in raw['native_state_sha256']),'bridge_native_seal')
    target=directory/'all_job_states.json.gz';require(not target.exists(),'bridge_job_states_exists')
    base.gzwrite(target,{'offered':28506,'horizon':raw['physical_time'],'jobs':raw['result']['jobs']})
    r.verify_pins(directory,plan,runtime=True)
    result={'schema':r.SCHEMA,'status':'complete_finite_bridge_observation' if complete else 'passed_saved_replay_with_unknown_completion',
        'assessment':assessment,'replay':replay,'physical_outcomes':outcomes,'cap_proofs_and_deliveries':relay_evidence,
        'startup_exact':{'rows':compared,'through':first['at']+base.PERIOD,'only_exclusion':'advance_to.result.wall_seconds finite nonnegative'},
        'clock_scope':clocks,'all_offered':28506,'trays':22,'native_state_sha256':raw['native_state_sha256'],
        'saved_full_api_replays':1,'native_executions':0,'strict_protection':'unknown_unfinished_offered_jobs',
        'alloffered_business_success':False,'complete_100ms_certified':False}
    result['evidence_sha256']={str(directory/name):base.sha(directory/name) for name in
        ('preregistered_protocol.json','input.json.gz','raw_final.json.gz','assessment.json','api/manifest.jsonl','service_clocks.jsonl','all_job_states.json.gz')}
    return result
