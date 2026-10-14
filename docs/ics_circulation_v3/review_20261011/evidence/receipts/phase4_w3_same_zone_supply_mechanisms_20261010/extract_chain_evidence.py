"""Reconstruct loaded/empty departures from existing complete event histories."""
from hashlib import sha256
import json
from pathlib import Path
from time import process_time,perf_counter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'

def main():
    cpu,wall=process_time(),perf_counter();target=OUT/'chain_evidence.json'
    if target.exists():raise FileExistsError(target)
    bound={}
    def read(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads(data.decode('utf-8-sig'))
    analyses={k:read(OUT/k/'analysis.json')for k in ('repaired_mechanism','nominal_pilot')}
    inputs={k:read(BASE/'phase4_w3_network_role_labels_parallel_20261009'/k/(k+'_input.json'))
            for k in ('cross_cycle','counterflow','near_full')}
    cases={};checks=[]
    for stage,analysis in analyses.items():
        meta={c['case']['case_id']:c for c in analysis['cases']if 'case'in c}
        for name,chain in analysis['chains'].items():
            scene=meta[name]['case']['scene'];initial=inputs[scene]['initial']
            carried={key:t['bag_id']for key,t in initial['trays'].items()}
            empty,loaded=[],[]
            for event in chain['events']:
                kind=event['event'];tray=event.get('tray_id')
                if kind=='load':carried[tray]=event['bag_id']
                elif kind=='unload_complete':
                    checks.append({'kind':'unload_identity','case':name,'time':event['time'],
                                   'okay':carried[tray]==event['bag_id']})
                    carried[tray]=None
                elif kind=='depart':
                    edge=initial['network']['edges'][event['edge_id']]
                    row={**event,'bag_id_at_depart':carried[tray],'travel_time':edge['travel_time']}
                    (empty if carried[tray]is None else loaded).append(row)
            components=meta[name]['metrics']['cost_components']
            checks.append({'kind':'empty_distance_from_departures','case':name,
                           'okay':sum(r['travel_time']for r in empty)==components['empty_distance']})
            wait=sum(r['load_time']-r['arrival']for r in chain['evaluation_ledger']if r['load_time']is not None)
            checks.append({'kind':'queue_wait_from_loads','case':name,'okay':wait==components['tray_wait']})
            cases[name]={'stage':stage,'scene':scene,'empty_departures':empty,'loaded_departures':loaded,
                'empty_distance_sum':sum(r['travel_time']for r in empty),'queue_wait_sum':wait,
                'initial_already_loaded_without_load_timestamp':[r['bag_id']for r in chain['evaluation_ledger']if r['load_time']is None],
                'observed_slow_commit_routes':[{'time':c['time'],'tray_id':p['tray_id'],
                    'destination':p['destination_node'],'first_depart':p['legs'][0]['depart']if p['legs']else c['time'],
                    'usable_at':p['usable_at'],'travel_time_sum':sum(l['arrive']-l['depart']for l in p['legs']),
                    'legs':p['legs']}for c in chain['slow_call_actions']for p in c['proposals']]}
    changed=[name for name,h in bound.items()if sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    result={'schema':'ics_round6_same_zone_chain_evidence_v1','new_physical_simulations':0,
        'cases':cases,'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),
        'failures':[c for c in checks if not c['okay']],'bound_file_sha256':bound,'changed_inputs':changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'scope':'Pure-file trace reconstruction through input verification; final serialization excluded.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('checks','failed_checks','failures','changed_inputs','cpu_seconds','wall_seconds')}))
    if result['failed_checks']or changed:raise SystemExit(1)

if __name__=='__main__':main()
