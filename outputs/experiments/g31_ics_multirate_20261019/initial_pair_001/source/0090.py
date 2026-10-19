"""Only two saved unknown rows and pinned public source; no trajectory/model."""
import gzip,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN=OUT/'live_obligation_historical_native_prepare_001';TARGET=OUT/'historical_unloading_gap_001.json'
AUDIT=OUT/'live_obligation_historical_native_saved_review_001.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,why):
    if not v:raise ValueError(why)
def local(e):return e['capture']['capture_v2']['local_capture']
def one(rows,why):need(len(rows)==1,why);return rows[0]

def main():
    need(not TARGET.exists(),'immutable_report')
    need(sha(AUDIT)=='3ea06f5867e916bca10936c28134003e91a8cd0b0cb1f41b3a93c1eaa3321728','audited_new96')
    audit=read(AUDIT);plan=read(RUN/'preregistered_protocol.json');contract=plan['native_contract_reference']
    need(sha(contract['path'])==contract['sha256'],'native_contract');authority=read(contract['path'])
    archive=Path(authority['source_archive']);sources={}
    for suffix in ('runtime/circulation_planning_snapshot_impl.hpp','runtime/circulation_runtime_impl.hpp','bindings/circulation_session_binding.hpp'):
        relative='cpp/ics_core/'+suffix;p=archive/relative
        keys=[k for k in authority['source_sha256'] if Path(k).as_posix()==relative]
        need(len(keys)==1 and sha(p)==authority['source_sha256'][keys[0]],'accepted_native_source:'+relative)
        sources[relative]=ref(p)
    for filename in ('live_obligation_historical_policy.py','live_obligation_recollection_policy.py',
        'live_obligation_lifecycle_state_v2.py','research_native_preexisting_v3_bound.py'):
        p=ROOT/'scripts/experiments/g31_ics_circulation'/filename
        need(sha(p)==plan['source_sha256'][str(p)],'frozen_policy:'+filename);sources[filename]=ref(p)
    rows={}
    for key in ('insufficient_advance/vector_16','insufficient_advance/vector_17'):
        p=RUN/(key+'.json.gz');need(sha(p)==audit['rows'][key]['raw']['sha256'],'raw_pin')
        raw=json.loads(gzip.decompress(p.read_bytes()));e=one(raw['collection_attempts']['B'],'B_one_attempt')
        need(raw['summary']['status']=='unknown_missing_input_or_unexecuted_counterfactual','preserved_unknown')
        ep=e['information']['raw_endpoints'];pending=e['collection'];now=e['at']
        peer=one([m for m in ep['received'] if local(m)['message_id']==pending['peer_message']],'selected_peer')
        own=ep['command']['last_delivered_ack']['planning_snapshot_v3']
        floor=min(local(own)['captured_at'],local(peer)['captured_at'])
        tray=one([t for t in local(peer)['trays'] if t['tray_id']=='E'],'captured_E')
        L=one([t for t in local(own)['trays'] if t['tray_id']=='L'],'captured_L')
        current=one([t for t in ep['view']['trays'] if t['tray_id']=='L'],'current_L')
        need(current==pending['trigger_tray'] and current['business_bag_id']=='reuse1'
            and current['edge_from']==current['edge_to']==-1 and pending['recollection_index']==0,'original_uncommitted_L_no_fresh_used')
        need(e['information']['bundle']['reasons']==['stable_observed_unloading']
            and tray['mode']=='unloading' and tray['ready_kind']=='observed_unload_completion'
            and tray['service_ready_known'] is True and tray['available_at']==tray['service_ready_at']
            and floor<=local(peer)['captured_at']<tray['service_ready_at']<now,'exact_crossed_unload_bound')
        # Only public envelopes actually available to B, not A's private reads.
        available=list(ep['received'])
        available.extend(c['last_delivered_ack']['planning_snapshot_v3'] for c in ep['view']['client_commands']
            if 'planning_snapshot_v3' in c.get('last_delivered_ack',{}))
        completed=[{'source':local(m)['source_owner'],'message_id':local(m)['message_id'],'receipt':r}
            for m in available for r in m['capture']['capture_v2']['extension']['terminal_receipts']
            if r['business_bag_id']=='receiver']
        need(not completed,'no_actual_delivered_receiver_completion')
        terminal=one([r for r in raw['result']['receipts'] if r['event']=='UNLOAD_COMPLETE'
            and r['business_bag_id']=='receiver' and r['tray_id']=='E'],'offline_actual_terminal')
        hold=one([r for r in raw['result']['receipts'] if r['event']=='HOLD_COMPLETE'
            and r['business_bag_id']=='receiver' and r['tray_id']=='E'],'offline_actual_hold')
        need(terminal['time']==tray['service_ready_at'] and terminal['time']+.1==hold['time'],'offline_schedule_not_policy_input')
        notices=[b['response'] for b in raw['native_batches'] if b['response']['physical_time']==terminal['time']]
        need(len(notices)==1 and set(notices[0]['notifications'])=={'A'},'terminal_notice_only_A')
        root=one([r for r in raw['owner_activation_admissions'] if r['root_id']==e['information']['actual_publication_ledger']['admission_root']],'B_actual_admission')
        epochs=[now]
        for _ in range(5):epochs.append(epochs[-1]+.01)
        labels=('issue','own_capture','invite_delivery','peer_capture','pair_delivery','physical_wire')
        nominal=dict(zip(labels,epochs,strict=True))
        need(nominal['physical_wire']<L['service_ready_at'],'nominal_wire_before_actual_L_bound')
        outgoing=[r for r in raw['result']['receipts'] if r['event']=='EDGE_ENTER'
            and r['business_bag_id']=='reuse1' and r['from']==7]
        need(len(outgoing)==1 and outgoing[0]['to']==3,'actual_default_edge_unknown_remains')
        rows[key]={'raw':ref(p),'actual_status':raw['summary']['status'],'phase':'B:first_reuse_route',
            'at':now,'capture_union_floor':floor,'peer_capture_at':local(peer)['captured_at'],
            'peer_message_id':local(peer)['message_id'],'peer_delivered_at':peer['delivered_at'],
            'known_unload_end_is_scheduled_fact_not_terminal_receipt':tray['service_ready_at'],
            'captured_E':tray,'current_L':current,'captured_L_service_bound':L['service_ready_at'],
            'original_collection_deadline':pending['deadline'],'actual_B_activation_trigger':root['trigger'],
            'actually_available_B_receiver_terminal_receipts':completed,
            'actual_B_other_messages':ep['view']['delivered_messages'],
            'offline_only_actual_UNLOAD_COMPLETE':terminal,'offline_only_actual_HOLD_COMPLETE':hold,
            'offline_only_source_A_notification':notices[0],
            'actual_retry_screen':e['retry_admission'],'actual_fresh_pairs_used_by_B':0,
            'nominal_one_existing_fresh_pair_epochs':nominal,
            'nominal_pair_before_original_collection_deadline':nominal['pair_delivery']<pending['deadline'],
            'nominal_wire_before_own_L_service':True,'nominal_wire_margin':L['service_ready_at']-nominal['physical_wire'],
            'physical_success_of_new_pair':'unknown_unexecuted','actual_reuse1_first_edge':outgoing[0],
            'native_status_not_promoted':True}
    value={'schema':'g31.historical_unloading_information_gap.v1','status':'two_saved_rows_source_diagnosis_only',
        'audit':ref(AUDIT),'plan':ref(RUN/'preregistered_protocol.json'),'sources':sources,'auditor':ref(__file__),'rows':rows,
        'conclusion':'B has a delivered pre-completion A snapshot and a known scheduled unload end, but no delivered destination-owned terminal receipt. The actual unload notification is A-local. Current B own ACKs/immutable ledger cannot turn that into a received A completion.',
        'minimal_candidate':'A new policy module can admit the already-budgeted single fresh pair for this exact crossed observed-unloading state, subject to all current original-L identity/commit/ACK/union/strict wire checks. A responds with a genuinely new v3 source capture, whose existing destination-owned completion extension can include the now-observed receiver terminal receipt. No C++ or v3 schema change is required by the inspected source.',
        'mandatory_guards':['First collection only; never a third pair.','Known exact unloading identity, destination, public unload duration, original captured start before union, and deadline crossed after capture.','Current L still the same uncommitted job/generation/traversal; sequential .01 message epochs plus actual route wire strictly before retained service bound.','No new physical admissions during collection, but physics and immutable retries continue.','The new pair must actually arrive and pass current full endpoint/history/occupancy/action-union/terminal-prefix validation; otherwise unknown.','A notification or a passed clock is never substituted for the new delivered terminal receipt.'],
        'limits':['The nominal five additions are source-derived feasibility arithmetic, not a native replay, prediction, guaranteed response or epsilon relaxation.','This is a new public message-policy amendment; all affected outcomes require a fresh bounded experiment before being assessed.','No source, wire delay, tray/FIFO/capacity, physical service window or existing result was changed.'],
        'native_executions':0,'model_evaluations':0}
    TARGET.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');print(json.dumps(ref(TARGET)))

if __name__=='__main__':main()
