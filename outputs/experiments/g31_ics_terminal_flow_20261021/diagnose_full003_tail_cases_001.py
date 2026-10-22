"""One-shot, read-only source003 tail diagnosis; does not import native."""
import json
from collections import Counter
from pathlib import Path

from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_flow_audit import closed_run
from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_service_audit import physical_comparison_contract
from scripts.experiments.g31_ics_circulation.foundation_airport_transport_evidence import binding, read
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import read_bound
from scripts.experiments.g31_ics_circulation.foundation_airport_json_stream import iter_json_array_gz

ROOT = Path('outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs')
OUT = Path('outputs/experiments/g31_ics_terminal_flow_20261021/full003_tail_cases_001.json')
IDS = ('projected:1x:5', 'projected:1x:38')
PATHS = {m: ROOT / ('TF_bridge_P2201_003_'+m+'_P2201') for m in ('C00','C10')}
closed = {m: closed_run(p) for m,p in PATHS.items()}
contract = physical_comparison_contract(closed['C00'][0], closed['C10'][0])
assert contract['parent']['split'] == 'dev'
data = read_bound(contract['input'])
specs = {r['business_bag_id']: r for r in data['jobs']}
terms = {m: read(p/'terminal_evidence.json.gz') for m,p in PATHS.items()}
calls = {m: [r for r in iter_json_array_gz(p/'calls.json.gz') if r.get('kind')=='transfer' and not r.get('retry')]
         for m,p in PATHS.items()}

def public_physical(r):
    return {k:r[k] for k in ('time','event','business_bag_id','tray_id','node','from','to','reason')}

def prefix(a,b,normalize=lambda r:r):
    count=0
    for x,y in zip(a,b):
        if normalize(x)!=normalize(y): break
        count+=1
    return dict(common_prefix_records=count, last_shared=None if count==0 else a[count-1],
        reference_next=a[count:count+3], candidate_next=b[count:count+3],
        reference_exhausted=count==len(a),candidate_exhausted=count==len(b))

PHYSICAL_EVENTS={'BAG_ARRIVAL','LOAD_START','LOAD_COMPLETE','LEG_START','LEG_COMPLETE','EDGE_ENTER','EDGE_EXIT',
    'RESOURCE_WAIT','RESOURCE_WAKE','STORAGE_ENTER','STORAGE_RELEASE','UNLOAD_START','UNLOAD_COMPLETE',
    'HOLD_START','HOLD_COMPLETE','EMPTY_RECEIVED'}
physical={m:[r for r in t['receipts'] if r['event'] in PHYSICAL_EVENTS] for m,t in terms.items()}
global_difference=prefix(physical['C00'],physical['C10'],public_physical)
global_difference['comparison_fields']=list(public_physical(physical['C00'][0]))
global_difference['excluded_protocol_delivery_and_runtime_identifiers']=True

cases={}
for identity in IDS:
    record=dict(business_bag_id=identity,input_spec=specs[identity],runs={})
    timelines={}
    for m,t in terms.items():
        rows=[r for r in t['receipts'] if r['business_bag_id']==identity]
        timelines[m]=rows
        state=next(r for r in t['jobs'] if r['business_bag_id']==identity)
        major=[r for r in rows if r['event'] not in ('EDGE_ENTER','EDGE_EXIT','RESOURCE_WAIT','RESOURCE_WAKE')]
        edge_paths={phase:[[r['from'],r['to']] for r in rows if r['event']=='EDGE_ENTER'
                    and ':'+phase+':' in r['transport_leg_id']] for phase in ('storage_in','storage_out')}
        dwells=[]
        for i,r in enumerate(rows):
            if r['event']!='EDGE_EXIT': continue
            later=next((z for z in rows[i+1:] if z['event']=='EDGE_ENTER' and z['transport_leg_id']==r['transport_leg_id']),None)
            if later is None: continue
            dwell=later['time']-r['time']
            if dwell<=10: continue
            waits=[z for z in rows[i+1:] if z['event'] in ('RESOURCE_WAIT','RESOURCE_WAKE')
                and z['node']==r['node'] and r['time']<=z['time']<=later['time']]
            shared=[z for z in t['receipts'] if z['event']=='EDGE_ENTER' and z['business_bag_id']!=identity
                and (z['from'] in (112,53) or z['to'] in (112,53)) and r['time']<=z['time']<=later['time']]
            dwells.append(dict(node=r['node'],arrival=r['time'],departure=later['time'],next_node=later['to'],
                duration_seconds=dwell,wait_wake_events=waits,shared_112_53_edge_entries=shared,
                timing_overlap_does_not_identify_exact_blocker=True))
        loaded=state['loaded_at'] if state['loaded_at']>=0 else None
        done=state['completed_at'] if state['completed_at']>=0 else None
        record['runs'][m]=dict(final_state=state,events=rows,event_counts=dict(Counter(r['event'] for r in rows)),
            major_events=major,edge_paths=edge_paths,node_dwells_over_10_seconds=dwells,
            pre_load_wait_seconds=(loaded if loaded is not None else contract['horizon'])-specs[identity]['arrival'],
            pre_load_wait_is_lower_bound=loaded is None,
            loaded_to_storage_seconds=None if loaded is None else state['storage_entered_at']-loaded,
            storage_to_completion_seconds=None if done is None else done-state['storage_entered_at'],
            load_to_completion_seconds=None if done is None else done-loaded)
    record['bag_event_common_prefix']=prefix(timelines['C00'],timelines['C10'],public_physical)
    record['storage_in_same_edge_path']=record['runs']['C00']['edge_paths']['storage_in']==record['runs']['C10']['edge_paths']['storage_in']
    cases[identity]=record

support={}
for m,t in terms.items():
    reqs={r['request_id']:r for r in t['transfers']}
    related=[c for c in calls[m] if 24 in (c['request']['source'],c['request']['destination'])
        or (c['request']['tray_id'] in ('initial:138:0','initial:136:0','initial:24:1') and c['at']<=25000)]
    joined=[dict(call=c,native_terminal=reqs[c['request']['request_id']]) for c in related]
    node24=[r for r in t['receipts'] if r['node']==24 and r['event'] in ('BAG_ARRIVAL','LOAD_START','EMPTY_RECEIVED')]
    node95=[r for r in t['receipts'] if r['node']==95 and r['event'] in ('LOAD_START','EMPTY_RECEIVED') and r['time']<25000]
    tray_histories={tray:[r for r in t['receipts'] if r['tray_id']==tray and r['time']<=25000
        and (r['event'] in ('LEG_START','LEG_COMPLETE','EMPTY_RECEIVED','LOAD_START','UNLOAD_COMPLETE')
             or (r['event'] in ('EDGE_ENTER','EDGE_EXIT','RESOURCE_WAIT','RESOURCE_WAKE') and
                 (r['node'] in (112,53,137,139) or r['from'] in (112,53,137,139) or r['to'] in (112,53,137,139))))]
        for tray in ('initial:138:0','initial:136:0','initial:24:1')}
    diag=read(PATHS[m]/'offline_diagnostics.json.gz'); graph=read(PATHS[m]/'wait_graph.json.gz')
    source24_ids={r['business_bag_id'] for r in node24 if r['event']=='BAG_ARRIVAL'}
    status24=Counter(r['status'] for r in t['jobs'] if r['business_bag_id'] in source24_ids)
    support[m]=dict(related_requests=joined,node24_events=node24,node95_early_supply_and_load=node95,
        selected_tray_shared_bottleneck_timelines=tray_histories,
        node24_arrived_status_counts=dict(status24),node24_arrived_count=len(source24_ids),
        terminal_junctions=[r for r in diag['junctions'] if r['node'] in (24,95,112,53,137,139)],
        terminal_wait_graph_summary={k:graph[k] for k in ('at','actual_resource_waits','edges','witnessed_hold_wait_cycles')},
        terminal_wait_graph_is_not_historical_snapshot=True)

case38=cases['projected:1x:38']['runs']
load_delta=case38['C10']['pre_load_wait_seconds']-case38['C00']['pre_load_wait_seconds']
transport_delta=case38['C10']['load_to_completion_seconds']-case38['C00']['load_to_completion_seconds']
complete_delta=case38['C10']['final_state']['completed_at']-case38['C00']['final_state']['completed_at']
assert abs(load_delta+transport_delta-complete_delta)<1e-6
fifo95={m:[r['business_bag_id'] for r in support[m]['node95_early_supply_and_load'] if r['event']=='LOAD_START'][:9] for m in terms}
assert fifo95['C00']==fifo95['C10'] and fifo95['C00'][-1]=='projected:1x:38'
assert cases['projected:1x:5']['runs']['C10']['event_counts']=={'BAG_ARRIVAL':1}
assert not [r for r in support['C10']['node24_events'] if r['event']=='EMPTY_RECEIVED']

result=dict(schema='g31.terminal_flow.source003_tail_mechanism_audit.v1',physical_contract=contract,
    native_starts=0,full_owner_ack_export_opened=False,test_data_read=False,
    global_first_physical_difference=global_difference,cases=cases,support=support,
    case38_decomposition=dict(pre_load_delay=load_delta,post_load_duration_delta=transport_delta,
        completion_delay=complete_delta,first_nine_node95_load_identity_order=fifo95['C00'],same_first_nine_order=True),
    limits=['Observed native event chains establish where delay accumulated, not marginal causality of an isolated choice.',
        'C00 and C10 are closed-loop runs: later public states, trays and upstream decisions differ.',
        'No targeted intervention was performed; predictor differences are not alone a physical causal explanation.',
        'Terminal wait graph has no historical resource-owner snapshots; overlapping events do not prove a unique blocker.',
        'A waiting_for_tray bag can have zero loaded-leg resource waits; absent wait graph edges do not certify service.'],
    evidence={m:{name:binding(p/name) for name in ('plan.json','receipt.json','terminal_evidence.json.gz',
        'trajectory.json.gz','calls.json.gz','offline_diagnostics.json.gz','wait_graph.json.gz')} for m,p in PATHS.items()},
    analysis_source=binding(Path(__file__)))
assert not OUT.exists()
with OUT.open('x',encoding='utf8') as f:
    json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
print(json.dumps(dict(output=str(OUT),case38=result['case38_decomposition'],
    node24={m:support[m]['node24_arrived_status_counts'] for m in terms},
    first_physical_prefix=global_difference['common_prefix_records']),ensure_ascii=False))
