"""Measured design-only oracle checks, never calls ICS Simulation."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations, product
from pathlib import Path
import json
import pickle
import sys
import time
import traceback

BASE=Path(__file__).resolve().parent
ROOT=Path.cwd()
sys.path.insert(0,str(BASE))
index=1
while (BASE/f'prototype_{index:03d}').exists():
    index+=1
OUT=BASE/f'prototype_{index:03d}'
OUT.mkdir()
paths=[BASE/'headway_ledger_prototype.py',Path(__file__)]
paths += [ROOT/'scripts/experiments/ics_circulation_v3'/name for name in
          ('model.py','runtime.py','routing.py','routing_reference.py','storage_routing.py','storage_calendar.py',
           'joint_transactions.py','dependency_admission.py','distributed_clock.py','partition_observation.py','routing_cache_contract.py')]
before={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    target=OUT/'source_snapshot'/p.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(p.read_bytes())
cpu,wall=time.process_time(),time.perf_counter()
result=dict(status='running',checks=0,oracle_cases=0,physics_calls=0,standalone_routing_queries=0,
            rows=[],source_sha256_before=before)
def check(value, label):
    result['checks']+=1
    if not value:
        raise AssertionError(label)

def pair_gap_oracle(records, now=0):
    # Independent combinatorial formulation; does not call prototype canonical
    # or its sweep and does not group by tray. Headway is fixed per directed edge.
    unique={}
    for record in records:
        key=(record.tray_id,record.edge_id,record.original_depart)
        prior=unique.get(key)
        if prior and prior.headway!=record.headway:
            raise ValueError('inconsistent duplicate')
        unique[key]=record
    active=[r for r in unique.values() if r.original_depart+r.headway>now]
    return any(a.edge_id==b.edge_id and abs(a.original_depart-b.original_depart)<a.headway
               for a,b in combinations(active,2))

def edge_capacity(departs, travel, capacity):
    return all(sum(d<=tick<d+travel for d in departs)<=capacity
               for tick in range(min(departs,default=0),max(departs,default=0)+travel+1))

try:
    from headway_ledger_prototype import EntryEvent,canonical,conflicts,record_actual_entry,retain_for_replacement,self_tail_signature
    for headway in range(1,6):
        events=[EntryEvent(tray,edge,depart,headway) for tray,edge,depart in
                product(('t0','t1'),('e0','e1'),range(7))]
        for size in (0,1,2,3):
            for records in combinations(events,size):
                for now in (0,3,7):
                    actual=bool(conflicts(records,now=now))
                    expected=pair_gap_oracle(records,now)
                    check(actual==expected,('sweep_vs_pair',headway,size,now,[asdict(r) for r in records]))
                    result['oracle_cases']+=1
    examples=[('capacity_not_headway',10,3,3,(0,1),True,False),
              ('pipeline_not_capacity_one',10,3,3,(0,3,6),True,True),
              ('headway_not_capacity',10,2,3,(0,3,6),False,True),
              ('tail_after_arrival',2,3,5,(0,3),True,False),
              ('exact_boundary',2,3,5,(0,5),True,True)]
    for label,travel,capacity,headway,departs,want_edge,want_entry in examples:
        records=[EntryEvent(f't{i}','e',d,headway) for i,d in enumerate(departs)]
        edge_ok=edge_capacity(departs,travel,capacity)
        entry_ok=not conflicts(records)
        check(edge_ok==want_edge and entry_ok==want_entry,label)
        result['rows'].append(dict(case=label,travel=travel,capacity=capacity,headway=headway,
                                  departures=departs,edge_allowed=edge_ok,entry_allowed=entry_ok))
    first=EntryEvent('t','e',0,5)
    for fields in ({'headway':0},{'headway':-1},{'headway':True},{'headway':1.5},
                   {'original_depart':False},{'original_depart':-1},{'entered':1},{'edge_id':''}):
        try:
            replace(first,**fields)
        except ValueError:
            check(True,('invalid_entry_rejected',fields))
        else:
            check(False,('invalid_entry_accepted',fields))
    same_entered=replace(first,entered=True)
    repeated=canonical((first,same_entered,first))
    check(repeated==(same_entered,),'duplicate notifications idempotent and entered monotone')
    check(not conflicts(repeated),'same physical entry not doubled')
    second=EntryEvent('t','e',3,5)
    check(bool(conflicts((same_entered,second),now=2)),'same tray second event still conflicts')
    check(not conflicts((same_entered,EntryEvent('t','other',3,5)),now=2),'other directed edge independent')
    check(canonical((same_entered,),now=2)==(same_entered,),'arrival at2 does not expire tail5')
    check(not canonical((same_entered,),now=5),'half-open tail expires at5')
    try:
        canonical((first,replace(first,headway=4)))
    except ValueError:
        check(True,'inconsistent duplicate rejected')
    else:
        check(False,'inconsistent duplicate accepted')
    entered=record_actual_entry((first,),first.event_id,now=0)
    check(entered==(same_entered,),'physical callback marks entered')
    check(record_actual_entry(entered,first.event_id,now=2)==entered,'duplicate callback remains idempotent')
    for bad_clock in (True, False, -1, None, 1.0):
        for physical in (first, same_entered):
            try:
                record_actual_entry((physical,),physical.event_id,now=bad_clock)
            except ValueError:
                check(True,'strict actual-entry clock')
            else:
                check(False,'invalid actual-entry clock accepted')
    check(canonical((first,),now=2)[0].entered is False,'clock alone does not invent actual entry')
    for now in (1,2):
        try:
            record_actual_entry((first,),first.event_id,now=now)
        except ValueError:
            check(True,'late manufactured notification rejected')
        else:
            check(False,'late manufactured notification accepted')
    pending=EntryEvent('t','pending',6,5)
    frozen=EntryEvent('t','frozen',3,8)
    other=EntryEvent('q','e',8,5)
    records=(same_entered,pending,frozen,other)
    kept=retain_for_replacement(records,now=2,
                               authorized_suffix_ids=[r.event_id for r in records],
                               frozen_prefix_ids=[frozen.event_id,other.event_id])
    check(set(kept)=={same_entered,frozen,other},'historical and frozen tails retained, only permitted future cancelled')
    check(next(r for r in kept if r.event_id==frozen.event_id).end==11,'frozen tail crosses anchor7 uncut')
    # Two paths reach A at t=2. One used e at0 then returned; the other used a
    # different two-edge detour. The same suffix e@2 is legal only for the latter.
    left=self_tail_signature((same_entered,),tray_id='t',tick=2)
    right=self_tail_signature((),tray_id='t',tick=2)
    suffix=EntryEvent('t','e',2,5)
    check(left!=right,'node/time does not determine sufficient history')
    check(bool(conflicts((same_entered,suffix),now=2)) and not conflicts((suffix,),now=2),'different continuation feasibility')
    result['rows'].append(dict(case='same_node_tick_different_self_tail',node='A',tick=2,
        left_signature=left,right_signature=right,left_suffix_allowed=False,right_suffix_allowed=True))
    checkpoint=dict(events=list(kept),cursor=dict(phase='control',now=2,entered_ids={same_entered.event_id}))
    raw=pickle.dumps(checkpoint)
    (OUT/'checkpoint.pickle').write_bytes(raw)
    branch=pickle.loads(raw)
    sibling=pickle.loads(raw)
    branch['events'].append(EntryEvent('x','new',2,3))
    branch['cursor']['phase']='events'
    check(sibling==checkpoint,'restore siblings independent')
    check(checkpoint['events']==list(kept),'origin unchanged')
    check(pickle.loads(raw)==checkpoint,'full cursor and ledger exact restoration')
    check(bool(conflicts((*sibling['events'],second),now=2)),'restored actual tail still rejects reentry')
    result['checkpoint_sha256']=sha256(raw).hexdigest()
    after={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths}
    result['source_sha256_after']=after
    check(before==after,'production and prototype source stable')
    result['status']='passed'
except BaseException:
    result.update(status='failed',failure=traceback.format_exc())
finally:
    result.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
        scope='prototype imports, exhaustive pure ledger oracle checks, serialization; no ICS Simulation or route search',
        limitation='design-only ledger; authority, real motion, W2 transport, owner admission and production cache not implemented',
        unmetered_auxiliary=['source reading','web research','design/code editing','tool orchestration','source snapshot capture'])
    (OUT/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256_before','source_sha256_after','rows')},indent=2))
sys.exit(0 if result['status']=='passed' else 1)
