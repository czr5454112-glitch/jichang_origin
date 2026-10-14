"""Independent raw-row arithmetic audit of endpoint mechanism analysis."""
from pathlib import Path
from collections import Counter, defaultdict
from hashlib import sha256
import json

BASE=Path('outputs/experiments/ics_circulation_v3')
ROOT=BASE/'phase4_w3_horizon_repaired_20261009'
ANALYSIS=BASE/'phase4_w3_horizon_mechanisms_20261009'
OUTPUT=BASE/'phase4_w3_diagnostic_audit_20261009'
WEIGHTS={'tray_wait':1.,'nonprotected_tardiness':1.,'empty_distance':.1,'terminal_backlog':10.,'terminal_inflight':2.}

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return sha256(p.read_bytes()).hexdigest()
def close(a,b): return abs(a-b)<=1e-8
counts=Counter(); errors=[]
def check(test,key,detail=None):
    counts[key]+=1
    if not test: errors.append({'check':key,'detail':detail})

m=read(ANALYSIS/'manifest.json')
for name,hashvalue in m['files_sha256'].items(): check(sha(ANALYSIS/name)==hashvalue,'analysis_sha',name)
author=read(ANALYSIS/'mechanisms.json')
check(author['source_analysis_sha256']==sha(ROOT/'analysis/summary.json'),'source_analysis_sha')
check(author['input_manifest_sha256']==sha(ROOT/'input_manifest.json'),'input_manifest_sha')
indexed={r['identity']:r for r in author['records']}
check(len(indexed)==len(author['records'])==208,'record_denominator')
branch=defaultdict(Counter); records=[]
for entry in read(ROOT/'input_manifest.json')['selected']:
    r=indexed[entry['identity']]
    labelpath=ROOT/r['label']; label=read(labelpath)
    check(sha(labelpath)==author['labels_sha256'][r['label']],'raw_label_sha')
    points={}
    for horizon in (20,40,80):
        bycandidate=defaultdict(list)
        for row in label['raw_branches']:
            e=row['endpoints'][str(horizon)]; c=e['cost_components']
            free=sum(c[k]*w for k,w in WEIGHTS.items() if not k.startswith('terminal_'))
            terminal=sum(c[k]*w for k,w in WEIGHTS.items() if k.startswith('terminal_'))
            check(close(free+terminal,e['total_cost']),'raw_cost_identity')
            bycandidate[row['candidate']].append((e,free,terminal))
            b=branch[horizon]; b['requests']+=1
            b['any_uncompleted']+=bool(e['uncompleted']); b['uncompleted_bag_instances']+=len(e['uncompleted'])
            b['observed_bag_instances']+=e['observed_bags']; b['completed_bag_instances']+=len(e['completed'])
            b['on_time_bag_instances']+=e['on_time']; b['positive_terminal_cost']+=terminal>1e-9
        check(set(bycandidate)==set(range(4)) and all(len(values)==32 for values in bycandidate.values()),'candidate_future_weighting')
        full=[sum(v[0]['total_cost'] for v in bycandidate[c])/32 for c in range(4)]
        free=[sum(v[1] for v in bycandidate[c])/32 for c in range(4)]
        terminal=[sum(v[2] for v in bycandidate[c])/32 for c in range(4)]
        optimum=[c for c,v in enumerate(full) if abs(v-min(full))<=1e-9]
        optimum_free=[c for c,v in enumerate(free) if abs(v-min(free))<=1e-9]
        p=r['points'][str(horizon)]
        for field,expected in [('means',full),('terminal_free_means',free),('terminal_means',terminal)]:
            check(len(p[field])==4 and all(close(a,b) for a,b in zip(p[field],expected)),'point_'+field,r['identity'])
        check(p['optimal_indices']==optimum and p['terminal_free_optimal_indices']==optimum_free,'point_optima',r['identity'])
        check(p['unload_optimal']==(0 in optimum) and p['terminal_free_unload_optimal']==(0 in optimum_free),'point_reference',r['identity'])
        points[horizon]={'full':full,'free':free,'terminal':terminal,'optimum':optimum}
    i20,i40,i80=(min(points[h]['optimum']) for h in (20,40,80))
    check((r['choice20_first_index'],r['choice40_first_index'],r['choice80_first_index'])==(i20,i40,i80),'tie_min_index',r['identity'])
    for name,index in [('choice20_regret80',i20),('choice40_regret80',i40),('unload_regret80',0)]:
        check(close(r[name],points[80]['full'][index]-min(points[80]['full'])),'regret_'+name,r['identity'])
    check(r['optimal_set40_agrees80']==(points[40]['optimum']==points[80]['optimum']),'optimal_set40_agrees80',r['identity'])
    for h in (20,40,80):
        for field,source in [('total','full'),('terminal','terminal'),('nonterminal','free')]:
            check(close(r['old_choice_advantage_over_unload'][str(h)][field],points[h][source][0]-points[h][source][i20]),'same_choice_advantage',r['identity'])
    records.append({'identity':r['identity'],'owner':entry['owner'],'stream':entry['stream'],'node':label['source_node'],
        'old_detour':0 not in points[20]['optimum'],'unload80':0 in points[80]['optimum'],
        'same20_better80':points[80]['full'][0]-points[80]['full'][i20]>1e-9,
        'regret20':points[80]['full'][i20]-min(points[80]['full']),
        'regret40':points[80]['full'][i40]-min(points[80]['full']),
        'set40_equal80':points[40]['optimum']==points[80]['optimum']})
for h,b in branch.items(): check(dict(b)==author['request_weighted_branch_completion'][str(h)],'branch_completion',h)
computed=[]
for field in ('all','stream','owner','node'):
    groups=defaultdict(list)
    for r in records:groups['all' if field=='all' else r[field]].append(r)
    for name,group in sorted(groups.items()):
        g={'grouping':field,'group':name,'states':len(group),
           'detour_better_at_twenty':sum(r['old_detour'] for r in group),
           'old_detour_to_unload80':sum(r['old_detour'] and r['unload80'] for r in group),
           'old_detour_state_has_detour_better80':sum(r['old_detour'] and not r['unload80'] for r in group),
           'same_choice20_still_beats_unload80':sum(r['old_detour'] and r['same20_better80'] for r in group),
           'unload20_to_detour80':sum(not r['old_detour'] and not r['unload80'] for r in group),
           'unload_optimal80':sum(r['unload80'] for r in group),
           'choice20_regret80_positive':sum(r['regret20']>1e-9 for r in group),
           'choice20_regret80_mean':sum(r['regret20'] for r in group)/len(group),
           'choice20_regret80_max':max(r['regret20'] for r in group),
           'choice40_regret80_mean':sum(r['regret40'] for r in group)/len(group),
           'choice40_regret80_positive':sum(r['regret40']>1e-9 for r in group),
           'optimal_set40_agrees80':sum(r['set40_equal80'] for r in group)}
        found=[v for v in author['grouped'] if v['grouping']==field and v['group']==name]
        check(len(found)==1 and all(close(found[0][k],v) if isinstance(v,(int,float)) else found[0][k]==v for k,v in g.items()),'grouped_arithmetic',(field,name))
        computed.append(g)
result={'schema':'independent_horizon_mechanisms_audit_v1','checks':sum(counts.values()),'checks_by_kind':dict(counts),
        'errors':errors,'all':computed[0],'branch_completion':dict(branch),'grouped':computed,
        'analysis_manifest_sha256':sha(ANALYSIS/'manifest.json'),'verifier_sha256':sha(Path(__file__)),
        'scope':'artifact-only weighted arithmetic; no simulation, refit or outcome-based selection'}
with (OUTPUT/'mechanisms_audit_final.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
with (OUTPUT/'read_only_mechanisms_verifier.py').open('xb') as f:f.write(Path(__file__).read_bytes())
print(json.dumps({'checks':result['checks'],'errors':errors,'all':computed[0]}))
raise SystemExit(bool(errors))
