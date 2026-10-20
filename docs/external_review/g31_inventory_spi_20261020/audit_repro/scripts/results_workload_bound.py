"""Optimistic tray-work necessary conditions from frozen physical inputs.

This is a relaxation, not a simulator, an actual fleet recommendation, or a
proof that a specified fleet can achieve the goal. No project modules imported.
"""
import argparse
import hashlib
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path


def analyze(path, horizon):
    raw=path.read_bytes();data=json.loads(raw)
    adjacency=defaultdict(list)
    capacities={(r['from'],r['to']):r['capacity'] for r in data['edge_contracts']}
    relaxed_zero_capacity_edges=[]
    for source,destination,length,speed in data['edge_records']:
        assert length>=0 and speed>0
        adjacency[source].append((destination,length/speed))
        if capacities.get((source,destination),0)<=0:
            relaxed_zero_capacity_edges.append([source,destination])
    distance={}
    for source in sorted({j['origin'] for j in data['jobs']}):
        best={source:0.};queue=[(0.,source)]
        while queue:
            value,node=heapq.heappop(queue)
            if value!=best[node]:continue
            for destination,travel in adjacency[node]:
                new=value+travel
                if new<best.get(destination,math.inf):
                    best[destination]=new;heapq.heappush(queue,(new,destination))
        distance[source]=best
    jobs=[j for j in data['jobs'] if j['arrival']<=horizon]
    for j in jobs:
        assert math.isfinite(distance[j['origin']].get(j['destination'],math.inf))
    def cohort(name,selected):
        assert selected
        first_arrival=min(j['arrival'] for j in selected)
        work=math.fsum(distance[j['origin']][j['destination']] for j in selected)
        span=horizon-first_arrival
        individual_window_impossible=sum(j['arrival']+distance[j['origin']][j['destination']]>horizon
                                         for j in selected)
        individual_deadline_impossible=sum(j['arrival']+distance[j['origin']][j['destination']]>j['deadline']
                                           for j in selected)
        return dict(name=name,count=len(selected),first_physical_arrival=first_arrival,
            common_completion_horizon=horizon,optimistic_available_seconds_per_tray=span,
            direct_loaded_travel_work_lower_bound_tray_seconds=work,
            mean_direct_loaded_travel_seconds=work/len(selected),
            continuous_fleet_work_lower_bound=work/span,
            integer_fleet_work_necessary_lower_bound=math.ceil(work/span),
            jobs_individually_impossible_by_horizon_even_at_relaxed_speed=individual_window_impossible,
            jobs_individually_impossible_by_deadline_even_at_relaxed_speed=individual_deadline_impossible,
            initial_fleet=len(data['trays']),initial_fleet_relaxed_work_budget=len(data['trays'])*span)
    cohorts=[cohort('all_arrived_by_H',jobs),
        cohort('arrived_deadline_strictly_before_H',[j for j in jobs if j['deadline']<horizon]),
        cohort('arrived_deadline_at_or_before_H',[j for j in jobs if j['deadline']<=horizon])]
    due=[j for j in jobs if j['deadline']<=horizon]
    first_arrival=min(j['arrival'] for j in due)
    prefix=[]
    for deadline in sorted({j['deadline'] for j in due}):
        selected=[j for j in due if j['deadline']<=deadline]
        work=math.fsum(distance[j['origin']][j['destination']] for j in selected)
        assert deadline>first_arrival
        prefix.append(dict(deadline=deadline,jobs=len(selected),work=work,
            span=deadline-first_arrival,necessary_fleet=work/(deadline-first_arrival)))
    strongest=max(prefix,key=lambda r:r['necessary_fleet'])
    return dict(input_path=str(path),input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_population=len(data['jobs']),not_yet_arrived=len(data['jobs'])-len(jobs),
        physical_initial_fleet=len(data['trays']),zero_capacity_edges_permitted_in_relaxation=relaxed_zero_capacity_edges,
        cohorts=cohorts,strongest_deadline_prefix_work_necessary_bound=strongest,
        integer_strongest_deadline_prefix_necessary_fleet=math.ceil(strongest['necessary_fleet']))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    cycle=args.root/'outputs/experiments/g31_ics_action_value_20261020/cycle_001'
    result=dict(schema='independent.g31.optimistic_workload_bound.v1',
        fixed_commit='1d895da00644c9486568fe74b835e057aa93f8c8',
        formula='p_j = shortest directed sum(length/speed) from origin to destination; N >= sum(p_j)/(H-min arrival), for every job in the specified cohort to finish by H.',
        assumptions=['one bag occupies one physical tray while traveling loaded',
            'all jobs in the selected cohort are required to finish by the stated common horizon',
            'deadline-prefix condition is an additional necessary condition for every job due by that prefix deadline to finish on time'],
        relaxations=['all 227 graph edges permitted even where actual capacity is zero',
            'ignore empty return travel and initial tray position',
            'ignore intermediate node service, loading, unloading and holding',
            'ignore mandatory storage detours and storage-release holding',
            'ignore edge/node contention, owner protocol, commitments and quarantines',
            'ignore all job-specific arrival times after the earliest arrival when aggregating available work'],
        limitations=['necessary lower bound only; not a sufficient fleet sizing recommendation',
            'all-arrived-by-H cohort can contain individually too-late arrivals, so no finite fleet necessarily closes it by H',
            'does not prove observed throughput around 1000 is optimal or excuse avoidable stalls',
            'does not modify the preregistered J or existing service acceptance target',
            'the 77/68-style numbers concern this frozen synthetic demand/graph/time window only'],
        parents={str(parent):analyze(cycle/f'D_N22_C00_P{parent}_001'/'input.json',59400.) for parent in (901,902)},
        native_starts=0,fit_calls=0)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
