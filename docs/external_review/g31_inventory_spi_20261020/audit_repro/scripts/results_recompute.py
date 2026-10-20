"""Independent offline recalculation; no project imports, training or native execution."""
import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

START, END, POPULATION = 7200.0, 59400.0, 28506


def read(path):
    with (gzip.open(path, 'rt', encoding='utf-8') if path.name.endswith('.gz')
          else path.open(encoding='utf-8')) as f:
        return json.load(f)


def metrics(cycle, spec):
    directory = cycle / spec['name']
    inp, result = read(directory / 'input.json'), read(directory / 'final_result.json.gz')
    jobs = {j['business_bag_id']: j for j in inp['jobs']}
    exported = {j['business_bag_id']: j for j in result['jobs']}
    assert len(jobs) == len(exported) == POPULATION and jobs.keys() == exported.keys()
    assert result['physical_clock'] == END
    assert result['advance']['status'] == 'reached' and result['advance']['horizon_complete']
    completion, loads, arrival = {}, {}, {}
    edge_times = []
    leg_failures = []
    for r in result['receipts']:
        ev = r['event']
        if ev in ('UNLOAD_COMPLETE', 'LOAD_START', 'BAG_ARRIVAL'):
            dest = {'UNLOAD_COMPLETE': completion, 'LOAD_START': loads, 'BAG_ARRIVAL': arrival}[ev]
            identity = r['business_bag_id']
            assert identity in jobs and identity not in dest
            dest[identity] = r['time']
        if ev == 'EDGE_EXIT':
            edge_times.append(r['time'])
        if ev == 'LEG_FAILED':
            leg_failures.append(r)
    for identity, j in jobs.items():
        assert (identity in arrival) == (j['arrival'] <= END)
        if identity in arrival:
            assert arrival[identity] == j['arrival']
        assert (identity in completion) == (exported[identity]['completed_at'] >= 0)
        if identity in completion:
            assert completion[identity] == exported[identity]['completed_at']
            assert j['arrival'] <= loads[identity] <= completion[identity] <= END
    J0 = math.fsum(max(0.0, END-max(j['arrival'], START)) for j in jobs.values())
    J = math.fsum(max(0.0, min(completion.get(k, math.inf), END)-max(j['arrival'], START))
                  for k, j in jobs.items())
    wait = math.fsum(max(0.0, min(loads.get(k, math.inf), END)-max(j['arrival'], START))
                     for k, j in jobs.items())
    relief = math.fsum(END-max(c, START) for c in completion.values())
    assert abs(J0-J-relief) < 1e-6
    arrived = len(arrival)
    m = dict(name=spec['name'], parent_seed=spec['parent_seed'], fleet=spec['fleet'],
        variant=spec['variant'], model_seed=spec.get('model_seed'), J=J,
        no_service_area_J0=J0, service_relief=relief,
        service_relief_percent_of_no_service=100*relief/J0,
        waiting_area=wait, loaded_area=J-wait, waiting_fraction=wait/J,
        arrived=arrived, not_yet_arrived=POPULATION-arrived,
        completed=len(completion), completion_percent_of_arrived=100*len(completion)/arrived,
        on_time=sum(c <= jobs[k]['deadline'] for k,c in completion.items()),
        overdue_unfinished=sum(k not in completion and j['arrival'] <= END and j['deadline'] < END
                                for k,j in jobs.items()),
        actual_leg_failed_receipts=len(leg_failures),
        last_edge_exit=max(edge_times) if edge_times else None,
        final_no_edge_exit_interval=END-max(edge_times) if edge_times else None,
        source_input_sha256=hashlib.sha256((directory/'input.json').read_bytes()).hexdigest(),
        source_result_sha256=hashlib.sha256((directory/'final_result.json.gz').read_bytes()).hexdigest())
    if spec.get('job_status_counts'):
        assert m['completed'] == spec['job_status_counts'].get('completed', 0)
    if 'leg_failed_receipts' in spec:
        assert m['actual_leg_failed_receipts'] == len(spec['leg_failed_receipts'])
    return m, {'jobs': jobs, 'completion': completion}


def pair(ref, candidate, all_metrics, all_indices):
    a,b = all_metrics[ref], all_metrics[candidate]
    x,y = all_indices[ref],all_indices[candidate]
    assert x['jobs'] == y['jobs']
    counts = Counter()
    exact_harm_delays = []
    censored_harm_bounds = []
    censored_improvement_bounds = []
    for identity,j in x['jobs'].items():
        first,second = x['completion'].get(identity),y['completion'].get(identity)
        if first is not None and second is not None:
            diff = second-first
            counts['exact_harmed' if diff>1e-6 else 'exact_improved' if diff < -1e-6 else 'exact_equal'] += 1
            if diff>1e-6:
                exact_harm_delays.append(diff)
        elif first is not None:
            counts['reference_only_finished_censored_harm'] += 1
            censored_harm_bounds.append(END-first)
        elif second is not None:
            counts['candidate_only_finished_censored_improvement'] += 1
            censored_improvement_bounds.append(END-second)
        else:
            counts['neither_finished_arrived' if j['arrival']<=END else 'neither_arrived_by_end'] += 1
    assert sum(counts.values()) == POPULATION
    old_unknown = sum(counts[k] for k in ('reference_only_finished_censored_harm',
        'candidate_only_finished_censored_improvement','neither_finished_arrived','neither_arrived_by_end'))
    gain = a['J']-b['J']
    assert abs((b['service_relief']-a['service_relief'])-gain) < 1e-6
    return dict(reference=ref,candidate=candidate,gain_bag_seconds=gain,
        relative_J_gain_percent=100*gain/a['J'],gain_seconds_per_arrived_bag=gain/a['arrived'],
        service_relief_relative_gain_percent=100*gain/a['service_relief'] if a['service_relief'] else None,
        completed_delta=b['completed']-a['completed'],on_time_delta=b['on_time']-a['on_time'],
        overdue_unfinished_delta=b['overdue_unfinished']-a['overdue_unfinished'],
        exact_and_censored_counts=dict(counts),legacy_unknown_incomplete=old_unknown,
        definitely_harmed_direction=counts['exact_harmed']+counts['reference_only_finished_censored_harm'],
        definitely_improved_direction=counts['exact_improved']+counts['candidate_only_finished_censored_improvement'],
        exact_harm_max_seconds=max(exact_harm_delays,default=0),
        exact_harm_sum_seconds=math.fsum(exact_harm_delays),
        censored_harm_lower_bound_sum_seconds=math.fsum(censored_harm_bounds),
        censored_harm_lower_bound_max_seconds=max(censored_harm_bounds,default=0),
        censored_improvement_lower_bound_sum_seconds=math.fsum(censored_improvement_bounds))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    cycle=args.root/'outputs/experiments/g31_ics_action_value_20261020/cycle_001'
    support=cycle/'report_support'
    protection=read(support/'final_protection_closed_runs_001.json')
    main_saved=read(support/'D_primary_closed_main_test_001.json')
    resource_saved=read(support/'final_resource_table_001.json')
    metrics_by_name,indices={},{}
    shared_parent_jobs={}
    for spec in protection['rows']:
        m,index=metrics(cycle,spec)
        if m['parent_seed'] in shared_parent_jobs:
            assert index['jobs']==shared_parent_jobs[m['parent_seed']]
            index['jobs']=shared_parent_jobs[m['parent_seed']]
        else:
            shared_parent_jobs[m['parent_seed']]=index['jobs']
        metrics_by_name[m['name']]=m
        indices[m['name']]=index
        print(m['name'],f"J={m['J']:.6f}",f"done={m['completed']}",flush=True)
    assert len(metrics_by_name)==34
    for row in main_saved['rows']:
        m=metrics_by_name[row['name']]
        expected=row['full_window_cost']
        assert abs(m['J']-expected['backlog_integral_bag_seconds'])<1e-6
        assert abs(m['waiting_area']-expected['waiting_for_tray_integral_bag_seconds'])<1e-6
        for k,old in [('completed','completed_by_end'),('on_time','on_time_by_end'),
                      ('arrived','arrived_by_end'),('overdue_unfinished','arrived_unfinished_past_deadline')]:
            assert m[k]==expected[old]
    for row in resource_saved['rows']:
        m=metrics_by_name[row['name']]
        for k in ('J','completed','on_time'):
            assert abs(m[k]-row[k])<1e-6
    formal_pairs=[]
    supplemental_pairs=[]
    for parent in (901,902):
        base=f'D_N22_C00_P{parent}_001'; forecast=f'D_N22_C10_P{parent}_001'
        formal_pairs.append(pair(base,forecast,metrics_by_name,indices))
        for seed in (17,29,43):
            noplan=f'D_N22_C01_S{seed}_P{parent}_001'; plan=f'D_N22_C11_S{seed}_P{parent}_001'
            formal_pairs.extend((pair(base,noplan,metrics_by_name,indices),
                                 pair(forecast,plan,metrics_by_name,indices)))
            supplemental_pairs.extend((pair(base,plan,metrics_by_name,indices),
                                       pair(noplan,plan,metrics_by_name,indices)))
        for fleet in (18,22,26):
            batch='D' if fleet==22 else 'G'
            ref=f'{batch}_N{fleet}_C10_P{parent}_001'; learned=f'G_N{fleet}_C11_S29_P{parent}_001'
            formal_pairs.append(pair(ref,learned,metrics_by_name,indices))
            supplemental_pairs.append(pair(f'{batch}_N{fleet}_C00_P{parent}_001',learned,metrics_by_name,indices))
    assert len(formal_pairs)==20
    primary=[p for p in formal_pairs if p['candidate'].startswith('D_N22_C11_')]
    primary_summary={
        'cell_count':len(primary),
        'mean_cell_relative_J_gain_percent':math.fsum(p['relative_J_gain_percent'] for p in primary)/6,
        'mean_cell_absolute_gain':math.fsum(p['gain_bag_seconds'] for p in primary)/6,
        'wins_vs_C10':sum(p['gain_bag_seconds']>0 for p in primary),
        'mean_cell_gain_seconds_per_arrived_bag':math.fsum(p['gain_seconds_per_arrived_bag'] for p in primary)/6,
        'mean_cell_relative_service_relief_gain_percent':math.fsum(p['service_relief_relative_gain_percent'] for p in primary)/6,
    }
    assert abs(primary_summary['mean_cell_relative_J_gain_percent']-0.089645688)<1e-8
    # Preserve the legacy definition; only add exact/censoring-aware categories.
    for saved in main_saved['comparisons']:
        p=pair(saved['reference'],saved['candidate'],metrics_by_name,indices)
        old=saved['per_job_comparison']
        assert p['legacy_unknown_incomplete']==old['unknown_incomplete']
        assert p['exact_and_censored_counts'].get('exact_harmed',0)==old.get('harmed',0)
        assert p['exact_and_censored_counts'].get('exact_improved',0)==old.get('improved',0)
        assert abs(p['exact_harm_max_seconds']-saved['maximum_known_delay_seconds'])<1e-6
    for saved in resource_saved['same_N_C11_vs_C10_comparisons']:
        parent,fleet=saved['parent_seed'],saved['fleet'];batch='D' if fleet==22 else 'G'
        p=pair(f'{batch}_N{fleet}_C10_P{parent}_001',f'G_N{fleet}_C11_S29_P{parent}_001',metrics_by_name,indices)
        old=saved['same_N_C10_per_job']['counts']
        assert p['legacy_unknown_incomplete']==old['unknown_incomplete']
        assert p['exact_and_censored_counts'].get('exact_harmed',0)==old.get('harmed',0)
        assert abs(p['exact_harm_max_seconds']-saved['same_N_C10_per_job']['maximum_known_delay_seconds'])<1e-6
    result=dict(schema='independent.g31.results_review.v1',fixed_commit='1d895da00644c9486568fe74b835e057aa93f8c8',
        scope='Saved full native final results and input jobs independently recalculated; no native or training rerun.',
        source_tree=str(args.root),primary_summary=primary_summary,
        all34_metrics=list(metrics_by_name.values()),formal20_comparisons=formal_pairs,
        supplemental_comparisons=supplemental_pairs,
        metric_note='J remains the preregistered objective. J0-J service relief is an algebraic explanatory diagnostic, not a retroactive success target.',
        censoring_note='Directional labels are only at the common closed horizon; exact delay remains unknown for single-sided completion. Legacy unknown counts are preserved.',
        native_runs=0,fits=0,project_imports=0)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(primary_summary,indent=2))


if __name__=='__main__':
    main()
