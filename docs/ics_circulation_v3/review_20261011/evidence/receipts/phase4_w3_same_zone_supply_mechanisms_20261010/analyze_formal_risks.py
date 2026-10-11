"""All tradeoffs, not just net-cost harm: pure-file trace attribution."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time,perf_counter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
RUN=BASE/'phase4_w3_same_zone_supply_repaired_20261010'

def main():
    cpu,wall=process_time(),perf_counter();target=OUT/'formal_tradeoffs.json'
    if target.exists():raise FileExistsError(target)
    bound={};checks=[]
    def read(path):
        data=path.read_bytes();key=str(path.relative_to(ROOT));digest=sha256(data).hexdigest()
        if key in bound and bound[key]!=digest:raise ValueError(key)
        bound[key]=digest
        return json.loads((gzip.decompress(data)if path.suffix=='.gz'else data).decode('utf-8-sig'))
    analysis=read(OUT/'full/analysis.json');summary=read(RUN/'full/summary.json')
    manifest=read(RUN/'full/manifest.json');rows={r['case_id']:r for r in summary['rows']}
    pairs=[p for p in analysis['pairs']if p['new_case']['policy']=='same_zone32plus32']
    risks=[p for p in pairs if p['task_regressions']or any(v>1e-9 for v in p['delta_components'].values())]
    details=[]
    for pair in risks:
        scene=pair['new_case']['scene'];original=read(BASE/'phase4_w3_network_role_labels_parallel_20261009'/scene/(scene+'_input.json'))['initial']
        entry={'old_case':pair['old_case']['case_id'],'new_case':pair['new_case']['case_id'],
            'delta_cost':pair['delta_cost'],'delta_components':pair['delta_components'],
            'task_regressions':pair['task_regressions'],'all_changed_tasks':pair['changed_tasks'],
            'first_slow_action_divergence':pair['first_slow_action_divergence'],'physical':{}}
        for side in ('old','new'):
            key=entry[side+'_case'];row=rows[key];path=RUN/row['file'];raw=read(path)
            checks.append({'kind':'raw_binding','case':key,'okay':bound[str(path.relative_to(ROOT))]==row['sha256']==manifest[path.name]})
            carried={k:t['bag_id']for k,t in original['trays'].items()};empty=[];loads=[]
            for event in raw['result']['trace']:
                kind=event['event'];tray=event.get('tray_id')
                if kind=='load':carried[tray]=event['bag_id'];loads.append(event)
                elif kind=='unload_complete':carried[tray]=None
                elif kind=='depart'and carried[tray]is None:
                    empty.append({**event,'travel_time':original['network']['edges'][event['edge_id']]['travel_time']})
            checks.append({'kind':'empty_distance','case':key,
                'okay':sum(e['travel_time']for e in empty)==raw['metrics']['cost_components']['empty_distance']})
            wait=sum(t['load_time']-t['arrival']for t in raw['evaluation_ledger']if t['load_time']is not None)
            checks.append({'kind':'tray_wait','case':key,'okay':wait==raw['metrics']['cost_components']['tray_wait']})
            entry['physical'][side]={'loads':loads,'empty_departures':empty,
                'slow_commit_routes':[{'time':c['time'],'tray_id':p['tray_id'],'target':p['destination_node'],
                    'usable_at':p['usable_at'],'legs':p['legs'],
                    'travel_time':sum(l['arrive']-l['depart']for l in p['legs'])}for c in raw['slow_calls']for p in c['proposals']],
                'same_zone_commits':[{'time':c['time'],'details':d,'state_sha256':c['state_sha256'],
                    'published_forecasts':c['published_forecasts'],'known_supply':c['known_supply'],
                    'guard_proofs':c['diagnostics'].get('same_zone_guards',[])}
                    for c in raw['slow_calls']for d in c['diagnostics'].get('proposal_details',[])if d.get('domain')=='same_zone']}
            del raw
        details.append(entry)
    changed=[p for p,h in bound.items()if sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    payload={'schema':'ics_round6_formal_tradeoffs_v1','new_physical_simulations':0,
        'selection':'All27 same-zone vs old32 pairs; include every pair with a positive cost-component delta or later load/completion for any task, even when net J improves.',
        'total_pairs':len(pairs),'risk_pair_count':len(risks),'net_cost_harmed_pairs':sum(p['delta_cost']>1e-9 for p in pairs),
        'pair_outcomes':dict(Counter('better'if p['delta_cost']<-1e-9 else 'worse'if p['delta_cost']>1e-9 else 'tie'for p in pairs)),
        'task_regression_pair_count':sum(bool(p['task_regressions'])for p in pairs),
        'task_regression_count':sum(len(p['task_regressions'])for p in pairs),'details':details,
        'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),
        'failures':[c for c in checks if not c['okay']],'bound_file_sha256':bound,'changed_inputs':changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Pure-file load/hash/trace reconstruction through input verification; final serialization excluded.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items()if k not in ('details','bound_file_sha256')},ensure_ascii=False))
    if changed or payload['failed_checks']:raise SystemExit(1)

if __name__=='__main__':main()
