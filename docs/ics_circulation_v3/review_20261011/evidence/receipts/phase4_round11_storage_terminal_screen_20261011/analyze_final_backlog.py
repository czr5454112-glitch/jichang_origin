"""One sealed-run offline diagnosis; no Simulation, candidate query or replay."""
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
from heapq import heappop, heappush
from pathlib import Path
import gzip
import json
import pickle
import sys
import time
import traceback

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
BASE=Path(__file__).resolve().parent
RUN=BASE.parent/'phase4_round11_validation_20261011/projected_h21600_screen_001'
ORIGINAL=BASE.parent/'phase4_round11_validation_20261011/original_h21600_001'
# No attempted read of still-open gzip evidence, even if invoked too early.
required=('results.json','after.json','final_checkpoint.pickle','final_result.json.gz')
if not all((RUN/name).is_file() for name in required):
    raise SystemExit('run is not sealed; analysis not started')
index=1
while (BASE/f'backlog_analysis_{index:03d}').exists(): index+=1
OUT=BASE/f'backlog_analysis_{index:03d}'
OUT.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
report=dict(status='running',physical_runs=0,standalone_routing_queries=0,
    offline_static_graph_traversals=0,rows=[],input_sha256={},
    qualification='Offline full44 evaluation ledger only. Nonexclusive necessary-condition evidence is not a joint impossibility or causal attribution proof.')
source_paths=[Path(__file__)]+[ROOT/'scripts/experiments/ics_circulation_v3'/name for name in
    ('model.py','runtime.py','storage_contracts.py','storage_terminal_screen.py')]
before={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in source_paths}
report['source_sha256_before']=before
for path in source_paths:
    target=OUT/'source_snapshot'/path.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(path.read_bytes())

def bind(path):
    raw=path.read_bytes()
    report['input_sha256'][path.relative_to(ROOT).as_posix()]=sha256(raw).hexdigest()
    return raw

def read(path):
    raw=bind(path)
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def normal(value):
    return json.loads(json.dumps(value))

def summary(rows):
    return dict(total=len(rows),completed=sum(r['completed_at'] is not None for r in rows),
        observed=sum(r['observed'] for r in rows),unobserved=sum(not r['observed'] for r in rows),
        unfinished=sum(r['completed_at'] is None for r in rows),
        unfinished_deadline_passed=sum(r['unfinished_deadline_passed'] for r in rows),
        protected=sum(r['protected'] for r in rows),
        completed_ontime=sum(r['completed_at'] is not None and r['completed_at']<=r['deadline'] for r in rows),
        completed_late=sum(r['completed_at'] is not None and r['completed_at']>r['deadline'] for r in rows),
        status_counts=dict(Counter(r['status'] for r in rows)),
        nonexclusive_evidence_counts=dict(Counter(tag for r in rows for tag in r['evidence_flags'])))

try:
    from scripts.experiments.ics_circulation_v3.runtime import INFINITY,effective_reservations
    run=read(RUN/'results.json')
    assert run['success'] and not run['source_changed'],'run did not finish a valid sealed attempt'
    read(RUN/'after.json')
    protocol=read(RUN/'protocol.json')
    raw=read(RUN/'final_result.json.gz')
    checkpoint=pickle.loads(bind(RUN/'final_checkpoint.pickle'))
    state=checkpoint.state
    assert checkpoint.search_horizon==protocol['search_horizon']==21600
    assert checkpoint.route_mode==protocol['route_mode']=='whole_route'
    assert checkpoint.route_selector is None and protocol['actual_default_generator_request_k']==1
    assert normal(asdict(state))==raw['final_snapshot'],'checkpoint and raw public state differ'
    assert normal(checkpoint.trace)+[{'time':state.now,'event':'tick'}]==raw['trace'],'trace differs'
    assert {k:v for k,v in checkpoint.policy_stats.items() if not k.endswith('_ms')}==raw['policy_stats']
    tape=read(RUN/'environment_tape.json')
    source=read(ORIGINAL/'environment_tape.json')
    initial=read(RUN/'initial_snapshot.json')
    tasks={b['bag_id']:b for b in tape}
    originals={b['bag_id']:b for b in source}
    assert len(tape)==len(source)==len(tasks)==len(originals)==44
    assert all(isinstance(b.get('storage'),dict) for b in tape),'this diagnosis is for the all-storage44 tape'
    assert tasks.keys()==originals.keys()
    changed={bid for bid in tasks if tasks[bid]['destination']!=originals[bid]['destination']}
    assert len(changed)==16
    assert all({k:v for k,v in tasks[bid].items() if k!='destination'}==
               {k:v for k,v in originals[bid].items() if k!='destination'} for bid in tasks)
    pending=[b.bag_id for group in checkpoint.pending_arrivals.values() for b in group]
    assert len(pending)==len(set(pending)) and set(pending).isdisjoint(state.bags)
    assert set(pending)|set(state.bags)==set(tasks)
    assert set(state.completed)<=set(state.bags)
    assert all(normal(asdict(bag))==tasks[bid] for bid,bag in state.bags.items())
    assert set(state.trays)==checkpoint.initial_tray_ids==set(initial['trays']) and len(state.trays)==11
    assert raw['completed']==state.completed
    assert raw['final_trays']==normal({key:asdict(value) for key,value in state.trays.items()})
    report.update(stop_tick=state.now,stop_status=run['status'],tail_cap_tick=28500,
        run_parent_cpu_seconds_reference=run['cpu_seconds'],run_physics_cpu_seconds_reference=run.get('physics_cpu_seconds'),
        checkpoint_raw_state_equal=True,checkpoint_raw_trace_equal=True,checkpoint_raw_policy_counts_equal=True,
        search_horizon=checkpoint.search_horizon,actual_default_request_k=1,
        generator_type=type(checkpoint.generator).__name__,
        pending_arrival_ids=sorted(pending),cohort_expected={'changed_final':16,'unchanged_final':28})
    loads={}
    for event in raw['trace']:
        if event['event']=='load':
            assert event['bag_id'] not in loads
            loads[event['bag_id']]=event
    slots=effective_reservations(state)
    by_node=defaultdict(list)
    for slot in slots:
        if slot.resource.startswith('node:'):
            by_node[slot.resource[5:]].append(slot)
    current_by_bag={t.bag_id:t for t in state.trays.values() if t.bag_id is not None}
    query_counts=Counter()
    latest={}
    query_path=RUN/'queries.jsonl.gz'
    bind(query_path)
    with gzip.open(query_path,'rt',encoding='utf-8') as stream:
        for line in stream:
            query=json.loads(line)
            query_counts[query['status']]+=1
            if query['bag_id'] is not None:
                latest[query['bag_id']]={k:query[k] for k in ('query_id','now','status','candidate_count','expansions')}
    assert dict(query_counts)==run['search_status_counts']
    report['sealed_query_status_counts_reference']=dict(query_counts)
    reverse=defaultdict(list)
    for edge in state.network.edges.values():
        if edge.capacity>0:
            reverse[edge.target].append((edge.source,edge.travel_time))
    distances={}
    def distance(source,target):
        if target not in distances:
            report['offline_static_graph_traversals']+=1
            values={target:0}; queue=[(0,target)]
            while queue:
                cost,node=heappop(queue)
                if values[node]!=cost: continue
                for prior,travel in reverse[node]:
                    value=cost+travel
                    if value<values.get(prior,INFINITY):
                        values[prior]=value;heappush(queue,(value,prior))
            distances[target]=values
        return distances[target].get(source)
    def terminal_evidence(tray_id,destination):
        cutoff=state.now+checkpoint.search_horizon
        events=defaultdict(int)
        relevant=[]
        for slot in by_node[destination]:
            if slot.tray_id==tray_id: continue
            left,right=max(cutoff,slot.start),min(INFINITY,slot.end)
            if left<right:
                events[left]+=1;events[right]-=1;relevant.append(slot)
        capacity=state.network.nodes[destination].capacity
        occupancy=0
        for tick,delta in sorted(events.items()):
            occupancy+=delta
            if tick<INFINITY and occupancy>=capacity:
                return dict(certified=True,cutoff=cutoff,conflict_at=tick,capacity=capacity,
                    other_occupancy=occupancy,witness_slots=[asdict(s) for s in relevant if s.start<=tick<s.end],
                    scope='Current no-plan loaded-tray full-witness query domain only; not permanent or joint infeasibility')
        return dict(certified=capacity<=0,cutoff=cutoff,capacity=capacity)
    free=[t for t in state.trays.values() if t.mode=='empty' and t.bag_id is None and t.node is not None
          and t.available_at<=state.now and t.tray_id not in state.plans and t.tray_id not in state.empty_targets]
    for bid,bag in tasks.items():
        completion=state.completed.get(bid)
        tray=current_by_bag.get(bid)
        plan=state.plans.get(tray.tray_id) if tray else None
        progress=state.storage_progress.get(bid)
        observed=bid in state.bags
        load=loads.get(bid)
        status=('completed' if completion is not None else 'not_yet_observed' if not observed
                else 'waiting_unloaded' if load is None else 'loaded_with_committed_plan' if plan is not None
                else 'loaded_without_plan')
        origin_to_storage=distance(bag['origin'],bag['storage']['node_id'])
        storage_to_final=distance(bag['storage']['node_id'],bag['destination'])
        original_origin_to_storage=distance(bag['origin'],bag['storage']['node_id'])
        original_storage_to_final=distance(bag['storage']['node_id'],originals[bid]['destination'])
        static=origin_to_storage is not None and storage_to_final is not None
        flags=[];cert=None;earliest=None
        start=bag['origin'];start_at=max(state.now,bag['arrival'])
        if tray is not None and tray.node is not None:
            start=tray.node;start_at=max(state.now,tray.available_at)
        if tray is not None and tray.node is None:
            active=[leg for leg in (plan.legs if plan else ()) if leg.depart<=state.now<leg.arrive]
            active.extend(f for f in state.old_in_transit if f.tray_id==tray.tray_id and f.depart<=state.now<f.arrive)
            if len(active)==1:
                start=state.network.edges[active[0].edge_id].target;start_at=active[0].arrive
            else:
                start=None
        if start is not None:
            if progress is not None and progress.departed_at is not None:
                rest=distance(start,bag['destination'])
                if rest is not None: earliest=start_at+rest+state.module.unload_ticks
            else:
                first=distance(start,bag['storage']['node_id'])
                if first is not None and storage_to_final is not None:
                    earliest=max(start_at+first,bag['storage']['release_at'])+storage_to_final+state.module.unload_ticks
        if completion is None:
            if not static: flags.append('projected_task_waypoint_static_path_missing')
            if start is not None and earliest is None: flags.append('current_stage_static_path_missing')
            if bag['protected'] and earliest is not None and earliest>bag['deadline']:
                flags.append('protected_deadline_lower_bound_already_exceeds_deadline')
            if not observed: flags.append('arrival_not_reached_at_censor')
            if status=='waiting_unloaded' and not any(t.node==bag['origin'] for t in free):
                flags.append('no_current_eligible_empty_tray_at_origin')
            if plan is not None: flags.append('committed_plan_still_to_execute')
            if (progress is not None and progress.arrived_at is not None and progress.departed_at is None):
                flags.append('actual_on_carrier_storage_occupancy')
                if state.now<bag['storage']['release_at']: flags.append('announced_release_not_reached')
            if status=='loaded_without_plan' and tray is not None and tray.node is not None:
                cert=terminal_evidence(tray.tray_id,bag['destination'])
                if cert['certified']: flags.append('current_terminal_full_witness_capacity_certificate')
            flags.append('unfinished_at_'+run['status'])
        row=dict(bag_id=bid,final_changed=bid in changed,original_final=originals[bid]['destination'],
            projected_final=bag['destination'],origin=bag['origin'],arrival=bag['arrival'],
            release=bag['storage']['release_at'],storage_node=bag['storage']['node_id'],deadline=bag['deadline'],
            protected=bag['protected'],observed=observed,status=status,completed_at=completion,
            unfinished_deadline_passed=completion is None and state.now>bag['deadline'],
            loaded_at=load['time'] if load else None,load_tray_id=load['tray_id'] if load else None,
            current_tray=asdict(tray) if tray else None,storage_progress=asdict(progress) if progress else None,
            plan=asdict(plan) if plan else None,latest_observed_query=latest.get(bid),
            original_waypoint_static_reachable=original_origin_to_storage is not None and original_storage_to_final is not None,
            projected_waypoint_static_reachable=static,relaxed_current_unload_lower_bound=earliest if completion is None else None,
            terminal_evidence=cert,evidence_flags=flags)
        report['rows'].append(row)
    report['all44']=summary(report['rows'])
    report['cohorts']={name:summary([r for r in report['rows'] if r['final_changed']==changed_flag])
        for name,changed_flag in (('changed_final',True),('unchanged_final',False))}
    assert report['all44']['total']==44
    assert sum(report['all44']['status_counts'].values())==44
    concentration={}
    for name,values in (('original',source),('projected',tape)):
        counts=Counter(b['destination'] for b in values)
        ordered=sorted(counts.items(),key=lambda pair:(-pair[1],pair[0]))
        concentration[name]=dict(counts=dict(ordered),distinct_destinations=len(counts),
            largest_share=ordered[0][1]/44,top3_share=sum(n for _,n in ordered[:3])/44,
            hhi=sum((n/44)**2 for n in counts.values()))
    report['destination_concentration']=concentration
    physical_by_node=defaultdict(list)
    for tray in state.trays.values():
        if tray.node is not None: physical_by_node[tray.node].append(tray.tray_id)
    finals=[]
    for final in sorted({b['destination'] for b in tape}):
        rows=[r for r in report['rows'] if r['projected_final']==final]
        finals.append(dict(node=final,capacity=state.network.nodes[final].capacity,
            task_summary=summary(rows),physical_trays_now=physical_by_node[final],
            future_indefinite_slots=[asdict(s) for s in by_node[final] if s.end==INFINITY],
            finite_slots=[asdict(s) for s in by_node[final] if s.end<INFINITY]))
    report['by_projected_final']=finals
    origins=[]
    for origin in sorted({r['origin'] for r in report['rows'] if r['status']=='waiting_unloaded'}):
        origins.append(dict(origin=origin,waiting_ids=[r['bag_id'] for r in report['rows'] if r['origin']==origin and r['status']=='waiting_unloaded'],
            eligible_empty_ids=[t.tray_id for t in free if t.node==origin],
            empty_targets_inbound=[key for key,value in state.empty_targets.items() if value==origin]))
    report['origin_waiting']=origins
    report['carriers']=dict(initial_count=11,current_count=len(state.trays),mode_counts=dict(Counter(t.mode for t in state.trays.values())),
        available_empty_ids=[t.tray_id for t in free],plan_count=len(state.plans),
        empty_targets=dict(state.empty_targets),rows=[dict(**asdict(t),has_plan=t.tray_id in state.plans,
            service_bags=[r['bag_id'] for r in report['rows'] if r['load_tray_id']==t.tray_id]) for t in state.trays.values()])
    storage=[]
    for node in sorted({b['storage']['node_id'] for b in tape}):
        positive=[];zero=[];ongoing_at_arrival=[]
        for bid,progress in state.storage_progress.items():
            if progress.contract.node_id!=node or progress.arrived_at is None: continue
            end=state.now if progress.departed_at is None else progress.departed_at
            bucket=(positive if end>progress.arrived_at else ongoing_at_arrival if progress.departed_at is None else zero)
            bucket.append(dict(bag_id=bid,tray_id=progress.tray_id,
                start=progress.arrived_at,end=end,still_stored=progress.departed_at is None))
        storage.append(dict(node=node,capacity=state.network.nodes[node].capacity,physical_trays_now=physical_by_node[node],
            current_effective_slots=[asdict(s) for s in by_node[node]],actual_positive_dwell=positive,
            completed_zero_dwell=zero,ongoing_arrival_zero_elapsed=ongoing_at_arrival,
            qualification='Actual residence and public commitments, not proof that storage is the unique throughput bottleneck'))
    report['storage_nodes']=storage
    report['source_sha256_after']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in source_paths}
    assert before==report['source_sha256_after'],'source drift'
    for name,digest in report['input_sha256'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==digest,('sealed input changed',name)
    report['status']='passed'
except BaseException:
    report.update(status='failed',failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
        resource_scope='Read/source capture/import/unpickle/static distance traversals/reservation sweeps/whole sealed query log parse/aggregation/input rehash; no physics or candidate query; final report writes excluded')
    (OUT/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k in ('status','failure','stop_tick','stop_status','all44','cohorts','carriers','physical_runs','standalone_routing_queries','offline_static_graph_traversals','cpu_seconds','wall_seconds')},indent=2))
raise SystemExit(0 if report['status']=='passed' else 1)
