"""Independent raw-file SAA audit: public information, physical ledger and budgets."""
from collections import Counter
import argparse
import json
from pathlib import Path
from time import perf_counter,process_time
from audit_round5_full_cycle import Audit,ROOT,read,digest,file_hash,physical
from audit_round5_empty import public_proxy,action_key


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    folder=args.run.resolve()
    wall,cpu=perf_counter(),process_time()
    audit=Audit()
    audit.manifest(folder)
    protocol,inputs,summary=[read(folder/n) for n in ('protocol.json','inputs.json','summary.json')]
    for name,expected in protocol['source_sha256'].items():
        audit.bind(folder/'source_snapshot'/name,expected)
        audit.bind(ROOT/'scripts/experiments/ics_circulation_v3'/name,expected)
    source={(i['si'],i['ti']):i for i in inputs}
    expected={f"s{i['si']}_t{i['ti']}_{p}" for i in inputs for p in protocol['policies']}
    rows=summary['rows']
    audit.check(len(rows)==len(expected)==protocol['planned_episodes']==summary['planned_episodes'],folder,'episode denominator differs')
    audit.check({r['identity'] for r in rows}==expected,folder,'planned episode grid differs')
    audit.check(summary['statuses']==dict(Counter(r['status'] for r in rows)),folder,'statuses differ')
    audit.check(summary['case_cpu_seconds_recorded']==sum(r['invocation_cpu_seconds'] or 0 for r in rows),folder,'recorded CPU lower bound differs')
    audit.check(summary['cases_unknown_resources']==sum(r['invocation_cpu_seconds'] is None for r in rows),folder,'unknown resource denominator differs')
    reference=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_empty_factorial_complete_20261010'
    audit.bind(reference/'summary.json')
    refs={r['identity']:r for r in read(reference/'summary.json')['rows']}
    counts=Counter()
    for row in rows:
        where=row['identity']
        si,ti=[int(s[1:]) for s in where.split('_')[:2]]
        inp=source[si,ti]
        if row['status']=='worker_failure':
            audit.check(row['invocation_cpu_seconds'] is None and 'final' not in row,where,'worker failure invented resources/metrics')
            continue
        path=folder/'cases'/row['file']
        audit.bind(path,row['sha256'])
        body=read(path)
        audit.check(all(body[k]==row[k] for k in ('identity','scene','tape','policy')),where,'case identity differs')
        if row['status']=='execution_failure':
            audit.check('failure' in body and 'final' not in row,where,'execution failure invents metrics')
            continue
        counts['successful_cases']+=1
        ledger=dict(inp['initial']['bags'])
        ledger.update((b['bag_id'],b) for b in inp['actual_tasks_event_engine_only'])
        forecasts=inp['forecasts']
        expiry=max((f['published_at']+61 for f in forecasts),default=inp['initial']['now'])
        for name,end in body['endpoints'].items():
            result,metrics=end['result'],end['metrics']
            audit.result(result,ledger,where+':'+name)
            complete=result['completed']
            audit.check(row[name]==metrics==body['metrics'][name],where,'endpoint metrics differ from summary')
            audit.check(metrics['scheduled']==len(ledger) and metrics['completed']==len(complete),where,'whole task ledger denominator differs')
            audit.check(metrics['on_time']==sum(k in complete and complete[k]<=b['deadline'] for k,b in ledger.items()),where,'true on-time numerator differs')
            audit.check(set(metrics['unfinished'])==set(ledger)-set(complete),where,'unarrived/unfinished task omitted')
            observed=result['final_snapshot']['bags']
            audit.check(end['cycle']['protected_observed']==sum(b['protected'] for b in observed.values()),where,'protected observed count differs')
            audit.check(end['cycle']['protected_completed']==sum(b['protected'] and k in complete for k,b in observed.items()),where,'protected completed count differs')
            audit.check(end['cycle']['protected_late']==sum(b['protected'] and complete.get(k,result['final_snapshot']['now'])>b['deadline'] for k,b in observed.items()),where,'protected late count differs')
        if row['status']=='controller_quiescent':
            marker={'time':row['stopped_at'],'quiet_since':body['quiet_since'],
                'actual_slow_triggers_since':body['final_slow_trigger_count']-body['quiet_start_slow_trigger_count']}
            adapted={'result':body['endpoints']['final']['result'],'last_cycle_state':body['endpoints']['final']['cycle'],
                'stopped_at':row['stopped_at'],'milestones':{'controller_quiescent':marker}}
            audit.drained(adapted,ledger,expiry,where)
            audit.check(body['final_slow_trigger_count']==len(body['slow_history']),where,'actual slow-trigger count differs from history')
            audit.check(any(h['trigger_time']>=body['quiet_since'] for h in body['slow_history'][body['quiet_start_slow_trigger_count']:]),where,'no actual slow trigger during quiet window')
        totals=Counter()
        for entry in body['slow_history']:
            now,diag=entry['trigger_time'],entry['diagnostics']
            settings=diag['settings']
            counts['slow_decisions']+=1
            audit.check(diag['published_forecasts']==[f for f in forecasts if f['published_at']<=now],where,'future publication or missing public forecast')
            audit.check(diag['next_slow_trigger_at']==now+protocol['spec']['slow_period'],where,'public slow clock differs')
            expected_stage=4 if protocol['spec']['coordination_order']=='route_then_prebalance' else 2
            audit.check(diag['cursor']['stage_index']==expected_stage and diag['cursor']['pending_options'] is None,where,'post-slow public cursor differs')
            scored=diag['scored_actions']
            totals['internal_query_calls']+=diag['greedy_diagnostics']['search_calls']+diag['proposal_search_calls']
            totals['internal_query_work']+=diag['greedy_diagnostics']['search_expansions']+diag['proposal_search_work']
            if diag['status']=='identical_no_demand_action':
                audit.check(not scored and diag['rollout_calls']==0 and diag['selected_proxy_cost'] is None and not entry['proposals'],where,'no-demand omission invents projection')
                continue
            observed={k for k,b in ledger.items() if b['arrival']<=now}
            proxy=public_proxy(forecasts,observed,now,now+settings['score_horizon'])
            audit.check(diag['proxy_bags']==proxy and digest(proxy)==diag['proxy_sha256'],where,'proxy does not follow only visible public inputs')
            audit.check(all(b['arrival']>now and b['bag_id'] not in observed for b in proxy),where,'observed task inserted into future proxy')
            audit.check(2<=len(scored)==diag['rollout_calls']<=settings['max_rollouts'],where,'action budget/mandatory alternatives differ')
            audit.check(scored[0]['kind']=='greedy_incumbent' and scored[1]['kind']=='no_transfer' and not scored[1]['proposals'],where,'missing mandatory baseline/no-action')
            best=0
            for j,c in enumerate(scored[1:],1):
                if scored[0]['status']!='complete' or c['status']!='complete':
                    continue
                current=scored[best]
                if c['proxy_cost']<current['proxy_cost']-1e-9 or (abs(c['proxy_cost']-current['proxy_cost'])<=1e-9 and (len(c['proposals']),action_key(c['proposals']),j)<(len(current['proposals']),action_key(current['proposals']),best)):
                    best=j
            audit.check(diag['selected_action_index']==best and entry['proposals']==scored[best]['proposals'],where,'selection/tie/fallback differs')
            audit.check(diag['fallback_to_greedy']==(scored[0]['status']!='complete'),where,'failed incumbent not retained')
            common=None
            for candidate in scored:
                counts['scored_actions']+=1
                totals['action_evaluations']+=1
                branches=candidate.get('physical_scenarios',[candidate])
                totals['physical_proxy_calls']+=len(branches)
                totals['requested_scenarios']+=candidate.get('requested_scenarios',1)
                totals['duplicate_reuses']+=candidate.get('exact_duplicate_reuses',0)
                if 'scenarios' in candidate:
                    req=candidate['scenarios']
                    keys=[r['future_sha256'] for r in req]
                    audit.check(common is None or common==keys,where,'current alternatives received different sampled futures')
                    common=keys
                    audit.check(len(req)==candidate['requested_scenarios']==8 and len(branches)==len(set(keys))==candidate['physical_proxy_calls'],where,'scenario/memo denominator differs')
                    audit.check(candidate['exact_duplicate_reuses']==len(req)-len(branches),where,'duplicate count differs')
                    seen=set()
                    for request in req:
                        physical_row=branches[request['physical_index']]
                        audit.check(request['future_sha256']==physical_row['public_scenario_sha256']==digest(physical_row['public_scenario_tape']),where,'scenario raw tape/memo binding differs')
                        audit.check(request['status']==physical_row['status'] and request['proxy_cost']==physical_row['proxy_cost'],where,'aliased projection status/value differs')
                        audit.check(request['cache_hit']==(request['future_sha256'] in seen),where,'reuse flag differs')
                        seen.add(request['future_sha256'])
                    complete=all(b['status']=='complete' for b in branches)
                    audit.check((candidate['status']=='complete')==complete,where,'partially evaluated scenario mean treated as complete')
                    audit.check(candidate['proxy_cost']==(sum(r['proxy_cost'] for r in req)/len(req) if complete else None),where,'scenario multiplicity mean differs')
                    for metric in ('search_calls','search_work','ticks','wall_seconds','cpu_seconds'):
                        audit.check(candidate[metric]==sum(b[metric] for b in branches),where,'scenario physical resource sum differs:'+metric)
                for b in branches:
                    counts['physical_proxy_rows']+=1
                    totals['internal_query_calls']+=b['search_calls']
                    totals['internal_query_work']+=b['search_work']
                    totals['status:'+b['status']]+=1
                    audit.check(b['search_calls']==len(b['searches'])<=settings['branch_search_calls'],where,'per-scenario query budget differs')
                    audit.check(b['search_work']==sum(q['work'] for q in b['searches']),where,'per-scenario query work ledger differs')
                    audit.check(b['search_work']-(b['searches'][-1]['work'] if b['searches'] else 0)<settings['branch_search_work'],where,'per-scenario work cap not checked between queries')
                    audit.check(b['status']=='complete' or b['proxy_cost'] is None,where,'incomplete physical projection assigned finite selection cost')
        for metric in ('action_evaluations','requested_scenarios','physical_proxy_calls','duplicate_reuses','internal_query_calls','internal_query_work'):
            audit.check(row[metric]==totals[metric],where,'episode resource aggregation differs:'+metric)
        audit.check(row['proxy_statuses']=={k[7:]:v for k,v in totals.items() if k.startswith('status:')},where,'episode proxy statuses differ')
        if row['policy']=='point':
            ref=refs[f's{si}_t{ti}_timed_greedy__fewest_physical']
            audit.bind(reference/'cases'/ref['file'],ref['sha256'])
            old=read(reference/'cases'/ref['file'])
            for end in ('h80','final'):
                audit.check(physical(old['endpoints'][end]['result'])==physical(body['endpoints'][end]['result']),where,'point baseline differs from corresponding factorial physical endpoint')
            audit.check(old['route_history']==body['route_history'],where,'point routing history differs from factorial')
            audit.check([(h['trigger_time'],h['proposals']) for h in old['slow_history']]==[(h['trigger_time'],h['proposals']) for h in body['slow_history']],where,'point slow actions differ from factorial')
            counts['point_reproductions']+=1
    changed=[p for p,h in audit.files.items() if file_hash(p)!=h]
    audit.check(not changed,folder,'bound bytes changed during independent audit')
    result={'schema':'ics_v3_empty_scenarios_independent_physical_public_audit_v1','run':str(folder),
        'checks':audit.count,'failed_checks':len(audit.errors),'errors':audit.errors,'counts':dict(counts),
        'bound_files':len(audit.files),'all_bound_files_unchanged':not changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,'script_sha256':file_hash(__file__),
        'helper_sha256':{name:file_hash(Path(__file__).with_name(name)) for name in ('audit_round5_full_cycle.py','audit_round5_empty.py')},
        'scope':'Independent pure raw-file ledger/physical drain/public-information/common-draw/mean/memo/budget/selection/point-reproduction checks; no new simulation, calibration or statistical confirmation claim.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('checks','failed_checks','counts','bound_files','wall_seconds')}))
    return bool(audit.errors)

if __name__=='__main__':
    raise SystemExit(main())
