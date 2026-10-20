"""Saved-only diagnosis of the sixteen residual rows; never runs a model/native."""
from __future__ import annotations
import gzip
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from .planning_capture_v3_contract import capture_digest_v3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN = OUT/'live_obligation_recollection_native_v2_prepare_001'
DEST = OUT/'live_obligation_recollection_v2_residual_001.json'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def ref(p): return {'path':str(Path(p).resolve()), 'sha256':sha(p)}
def need(x, reason):
    if not x: raise ValueError(reason)
def one(xs, reason):
    need(len(xs)==1,reason)
    return xs[0]
def local(e): return e['capture']['capture_v2']['local_capture']
def event_rows(raw, name, tray):
    return [e for e in raw['result']['receipts'] if e['event']==name and e['tray_id']==tray]
def slim(e):
    return {k:e[k] for k in ('time','event','tray_id','business_bag_id','from','to','node','reason') if k in e}

def final_pair(attempt):
    ep=attempt['information']['raw_endpoints']
    own=ep['command']['last_delivered_ack']['planning_snapshot_v3']
    peer=one([e for e in ep['received'] if local(e)['message_id']==attempt['collection']['peer_message']], 'exact_selected_peer')
    return own,peer

def self_history(ep, owner, now):
    """Only already delivered own ACKs in the actual deciding-owner endpoint."""
    rows=[]
    for index,command in enumerate(ep['view']['client_commands']):
        ack=command.get('last_delivered_ack',{})
        e=ack.get('planning_snapshot_v3')
        if e is None: continue
        b=local(e)
        need(b['source_owner']==owner and ack['status']=='delivered'
             and ack['result_id']==b['message_id'] and ack['executed_at']==b['captured_at']
             and ack['completed_at']==e['delivered_at'] and ack['delivered_at']<=now,
             'historical_self_ack_binding')
        need(capture_digest_v3(e['capture'])==e['payload_sha256'],'historical_capture_digest')
        rows.append({'endpoint_path':f'view.client_commands[{index}].last_delivered_ack.planning_snapshot_v3',
                     'command_request_id':command['request_id'],'ack':ack,'envelope':e})
    return rows

def row_diagnosis(key, raw):
    attempt=raw['collection_attempts']['B'][-1]
    need(attempt['information']['status']=='unknown','expected_final_B_unknown')
    now=attempt['at']; ep=attempt['information']['raw_endpoints']; pair=final_pair(attempt)
    floor=min(local(e)['captured_at'] for e in pair)
    captured=[(local(e),t) for e in pair for t in local(e)['trays']]
    L=one([t for b,t in captured if t['tray_id']=='L'],'one_L')
    bad=one([(b,t) for b,t in captured if t['tray_id']!='L' and t['mode'] in ('loaded','unloading')
             and t['edge_to']==-1 and t['service_ready_at']<=now],'one_bad_stationary_bound')
    b,t=bad; name=t['tray_id']; job=one([j for j in b['jobs'] if j['business_bag_id']==t['business_bag_id']],'bad_job')
    need(t['node']==job['destination'] and t['service_ready_known'] is True,'goal_known_row')
    own_current=one([t for t in attempt['actual_local_view']['trays'] if t['tray_id']=='L'],'actual_local_L')
    need(own_current==attempt['collection']['trigger_tray'] and own_current['edge_from']==own_current['edge_to']==-1,
         'same_current_uncommitted_target')
    need(now+.01<min(L['service_ready_at'],attempt['collection']['deadline']),'direct_wire_still_before_L_deadline')
    entry=one([e for e in event_rows(raw,'EDGE_ENTER',name) if e['to']==job['destination']],'actual_goal_entry')
    exit_=one([e for e in event_rows(raw,'EDGE_EXIT',name) if e['to']==job['destination']],'actual_goal_exit')
    unload_start=one(event_rows(raw,'UNLOAD_START',name),'actual_unload_start')
    unload_end=one(event_rows(raw,'UNLOAD_COMPLETE',name),'actual_unload_end')
    hold_end=one(event_rows(raw,'HOLD_COMPLETE',name),'actual_hold_end')
    target_enter=one([e for e in event_rows(raw,'EDGE_ENTER','L') if e['business_bag_id']=='reuse1' and e['from']==7], 'actual_L_first_reuse_departure')
    service=max(.001,next(row[2] for row in ep['view']['node_records'] if row[0]==t['node']))
    need(exit_['time']+service==unload_start['time'] and unload_start['time']+job['unload_seconds']==unload_end['time'],
         'source_expression_matches_offline_receipts')
    histories=self_history(ep,'B',now)
    matching=[]
    for history in histories:
        envelope=history['envelope']; source=local(envelope)
        for receipt in envelope['capture']['extension']['source_observed_inflight']:
            if all(receipt[f]==t[f] for f in ('tray_id','business_bag_id','generation','traversal_id')) and receipt['edge_to']==t['node']:
                need(receipt['entered_at']==entry['time'] and receipt['derived_edge_exit_at']==exit_['time'], 'historical_entry_matches_offline_event')
                need(receipt['derived_edge_exit_at']==receipt['entered_at']+receipt['static_edge_travel_seconds'], 'entry_float_expression')
                need(source['valid_until']>now and history['ack']['delivered_at']<=floor,'historical_fact_delivered_before_floor_still_unexpired')
                matching.append({'endpoint_path':history['endpoint_path'],'command_request_id':history['command_request_id'],
                    'message_id':source['message_id'],'captured_at':source['captured_at'],
                    'recipient_delivered_at':envelope['delivered_at'],'own_ack_delivered_at':history['ack']['delivered_at'],
                    'valid_until':source['valid_until'],'payload_sha256':envelope['payload_sha256'],'entry':receipt,
                    'derived_goal_service_end':receipt['derived_edge_exit_at']+service})
    physical_requests=[{'request_id':rid,'request':item['request'],'ack':item['ack']} for rid,item in raw['outbox'].items()
        if item['request'].get('kind')=='route' and item['request'].get('business_bag_id')=='reuse1']
    # Scope statement is backed by the actual raw policy decision, not inferred
    # from absence of a route command alone (default is a legitimate action).
    decision=one([d for d in raw['decisions']['B'] if d['phase']=='first_reuse_route'],'one_final_B_decision')
    if t['mode']=='loaded':
        need(t['service_ready_at']==b['captured_at'] and len(matching)==1,'clamped_goal_epoch_and_exact_retained_entry')
        need(unload_start['time']>now and matching[0]['derived_goal_service_end']==unload_start['time'],'real_goal_service_not_finished')
        category='goal_service_calendar_observation_clamped_to_capture'
    else:
        need(b['captured_at']<t['service_ready_at']==unload_end['time']<=now<hold_end['time'],'real_unload_transition_during_collection')
        need(matching==[],'no_same_generation_historical_entry_for_unloading')
        category='actual_unload_completion_crossed_collection'
    return {'raw':ref(RUN/(key+'.json.gz')),'status_unchanged':raw['summary']['status'],
        'phase':'first_reuse_route','owner':'B','now':now,'floor':floor,
        'final_attempt_index':attempt['collection']['recollection_index'],
        'attempt_count_by_owner':{o:len(v) for o,v in raw['collection_attempts'].items()},
        'attempts':[{'owner':o,'phase':a['phase'],'at':a['at'],'index':a['collection']['recollection_index'],
                    'status':a['information']['status'],'reasons':a['information'].get('reasons',[]),
                    'bundle_reasons':a['information'].get('bundle',{}).get('reasons',[]),
                    'retry_admission':a['retry_admission'],'new_request_id':a.get('new_request_id')}
                    for o,values in raw['collection_attempts'].items() for a in values],
        'cause':category,'bad_source':b['source_owner'],'bad_capture_at':b['captured_at'],
        'bad_capture_message_id':b['message_id'],'bad_tray':t,'bad_job':job,
        'target_L':{'current_view':own_current,'captured':L,'service_deadline':L['service_ready_at'],
                    'collection_deadline':attempt['collection']['deadline'],
                    'hypothetical_immediate_wire_execution':now+.01,'wire_strictly_before_deadline':True,
                    'remaining_window':L['service_ready_at']-now,
                    'actual_first_reuse_edge':slim(target_enter),'actual_route_requests':physical_requests},
        'retained_own_delivered_history':matching,
        'offline_events_not_policy_inputs':list(map(slim,(entry,exit_,unload_start,unload_end,hold_end))),
        'actual_next':raw['summary']['first_reuse_actual_next'],
        'selected_later_action':raw['specification']['vector']['later_action'],
        'final_policy_decision':{k:v for k,v in decision.items() if k not in ('information','collection')},
        'all_five_completion':raw['summary']['completion'],'information_status_not_promoted':True}

def main():
    start=time.perf_counter();need(not DEST.exists(),'immutable_new_report')
    prior=OUT/'live_obligation_recollection_native_v2_saved_review_001.json'
    need(sha(prior)=='c21c9e90c92fb12ccf846fe2072f81c7b43531e969aa3ff031a8ea0d733e88af','independent_full96_review_pin')
    acceptance=read(OUT/'native027_accepted_contract_001.json');build=read(acceptance['build_receipt'])
    archive=Path(acceptance['source_archive']); sources={}
    for path,expected in build['source_after'].items():
        if Path(path).name in ('circulation_planning_snapshot_impl.hpp','circulation_runtime_impl.hpp','event_driven_junction.hpp'):
            file=archive/path;need(sha(file)==expected,'compiled_archive_source_pin');sources[path]=ref(file)
    need(len(sources)==3,'source_explanation_closure')
    ledger=read(RUN/'branch_ledger.json');unknown=[k for k,v in ledger.items() if v['summary']['status']!='assessed']
    need(len(unknown)==16 and len(ledger)==96,'full_denominator_and_residual_count')
    rows={}
    for key in unknown:
        path=RUN/(key+'.json.gz');raw=json.loads(gzip.decompress(path.read_bytes()))
        rows[key]=row_diagnosis(key,raw)
    counts=Counter((r['cause'],r['bad_source'],r['bad_tray']['tray_id'],r['bad_tray']['mode']) for r in rows.values())
    result={'schema':'g31.recollection_v2_residual_saved_diagnosis.v1',
      'status':'saved_source_bound_diagnosis_unknowns_preserved','prior_independent_review':ref(prior),
      'plan':ref(RUN/'preregistered_protocol.json'),'receipt':ref(RUN/'receipt.json'),
      'ledger':ref(RUN/'branch_ledger.json'),'accepted_native_contract':ref(OUT/'native027_accepted_contract_001.json'),
      'compiled_build':ref(acceptance['build_receipt']),'compiled_source_pins':sources,
      'diagnostic_source':ref(__file__),'counts':[{'cause':a,'source_owner':b,'tray':c,'mode':d,'count':n} for (a,b,c,d),n in counts.items()],
      'all16_target_wire_windows_still_open':True,'rows':rows,
      'source_findings':[
        'R3 uses_destination_calendar returns node != goal (event_driven_junction.hpp:5031). Goal service is nevertheless scheduled from event.service_end (15541), computed as (reservation time + travel) + destination service (14976-14977).',
        'task_service_end initializes end=now and returns max of matching intervals (1958). Planning loaded-kInService unconditionally marks this result known committed_local_service_end (planning_snapshot_impl:94-97). For a goal without an interval this is not the actual pending goal-service event epoch.',
        'All fourteen clamped rows have a still-valid actual B self-ACK containing the exact final inbound observed entry. Current goal capture has the same tray/job/generation/public traversal. The retained derived arrival plus exact public node service equals the offline service completion, with no rounding or epsilon.',
        'The other two are real unloading-to-hold transitions after peer capture and before decision. Their known observed unload deadline is exact; a stable-state guard must not accept the stale mode. No delivered completion receipt is manufactured from this diagnostic.'
      ],
      'possible_next_contract_not_implemented':[
        'Fourteen rows: narrowly authenticate retained own delivered planning ACK, immutable observed entry, same leg generation/public traversal/current goal prefix, static digest, no unresolved relevant actions/faults, exact owner occupancy and finite-population conditional stability. Derive an independent historical-arrival service deadline; do not reinterpret clamped service_ready_at as a future bound. A new native binding is not yet necessary for these actual retained records.',
        'Two rows: an observed unload bound and hold constant could describe a conditional autonomous transition, but the existing completed-prefix contract requires an actual source-owned completion receipt. Either prove and explicitly version conditional transition/occupancy semantics, or require a new delivered fact. Do not silently add a retry, infer completion from absence, or certify a missing actual receipt.',
        'Keep all fourteen/two unknown in this run and all incomplete16/32 families unknown. Any revised information consumer must be tested independently before a same96 run; strong coordinate/MPC/pair/enumeration references receive identical facts, actions and32/4 budgets. Saved native outcomes remain offline comparands, never policy inputs.'
      ],
      'limits':['Source and saved-event diagnosis, not a new native execution or model prediction. No hypothetical direct route is certified executable merely by an open local time window.',
        'Offline receipt times are used to diagnose metadata and validate derivations, never to grant an online capability or fill a missing delivered message.',
        'No all-family optimum, protection, joint-method necessity or100ms claim. Existing80assessed/16unknown and all six incomplete reference families remain unchanged.'],
      'native_executions':0,'model_evaluations':0,'wall_seconds':time.perf_counter()-start}
    for r in rows.values():need(sha(r['raw']['path'])==r['raw']['sha256'],'raw_stability')
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':ref(DEST),'counts':result['counts'],'wall_seconds':result['wall_seconds']},ensure_ascii=False))

if __name__=='__main__':main()
