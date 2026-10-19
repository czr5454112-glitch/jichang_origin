"""Independent stdlib post-selection audit; no training/native/test imports."""
import ast
import hashlib
import json
import math
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
SELECTED = BASE/'A3_fqi_selection_002'
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def close(a, b):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b) <= 1e-9 * max(1., abs(b)), (a,b)
receipt = read(SELECTED/'receipt.json'); plan = read(SELECTED/'selection_plan.json')
assert receipt['status'] == 'completed_selection_only' and receipt['plan_sha256'] == digest(plan)
attempts = list((BASE/'attempts').glob('A3_fqi_selection_002_*'))
assert len(attempts) == 1
attempt = attempts[0]; registration = read(attempt/'registration.json'); outer = read(attempt/'receipt.json')
assert outer['status'] == 'completed' and not outer['source_changed'] and outer['assessment'] == receipt
assert outer['process']['exitcode'] == 0 and outer['process']['child_released_only_after_job_assignment']
archives = {p: attempt/'source'/(f'{i:04d}'+Path(p).suffix) for i,p in enumerate(registration['source_pins'])}
assert all(sha(archives[p]) == expected for p,expected in registration['source_pins'].items())
assert all(registration['source_pins'][p] == expected for p,expected in plan['sources'].items())
assert all(sha(r['path']) == r['sha256'] for r in plan['references'])
selector_source = next(p for p in archives if Path(p).name == 'foundation_fqi_checkpoint_selection.py')
assert sha(archives[selector_source]) == 'dd3cd6091ec9ab92e04f951234ed3c898e7e3a0fb85e50de772d9d0b93e7ddcf'
# Confirm the actually supplied directory was the registered training output.
train_registration = read(plan['training_registration'])
expected_training = Path(train_registration['args'][train_registration['args'].index('--output')+1]).resolve()
assert Path(plan['training_directory']).resolve() == expected_training == (BASE/'A3_fqi_training_001').resolve()
assert Path(train_registration['assessment']['path']).resolve() == expected_training/'receipt.json'
training = read(expected_training/'receipt.json'); episodes = read(expected_training/'transitions.json')
contract = training['contract']
assert training['gate']['episodes_sha256'] == digest(episodes)
allowed = {'train':set(contract['train_parent_groups']), 'development':set(contract['development_parent_groups'])}
assert all(e['split'] in allowed and e['parent_group'] in allowed[e['split']] for e in episodes)
assert set.union(*allowed.values()).isdisjoint(contract['evaluation_plan']['held_out_parent_groups'])
rows = [r for e in episodes if e['split']=='development' for r in e['transitions'] if r['owner']==contract['owner']]
by_id = {(r['source']['sha256'],r['decision_id']):r for r in rows}
def state(o):
    return digest({k:v for k,v in o.items() if k not in ('episode_id','decision_id','opportunity')})
def legal(mask):
    return {digest(c['semantic']) for c in mask if c['enabled'] and
            (c['guard_status']=='original_fixed_rule' or c['guard_status']=='passed' and c['per_job_delta']
             and all(isinstance(v,(int,float)) and math.isfinite(v) and v<=0 for v in c['per_job_delta'].values()))}
groups = {}
for row in rows:
    assert row['training_eligible'] and not row['truncated'] and row['gamma']==1.
    if not row['terminated']:
        nxt=by_id[(row['source']['sha256'],row['next_decision_id'])]
        assert nxt['observation']==row['next_observation'] and nxt['candidate_mask']==row['next_candidate_mask']
        assert row['observation']['at']==row['reward']['start']<row['reward']['end']==nxt['observation']['at']
    groups.setdefault((state(row['observation']),digest(row['action'])),[]).append(row)
values={};visiting=set()
def solve(key):
    if key in values:return values[key]
    assert key not in visiting
    visiting.add(key); outcomes=[]
    signatures=set()
    for row in groups[key]:
        next_state=None if row['terminated'] else state(row['next_observation'])
        support=[] if row['terminated'] else sorted(a for s,a in groups if s==next_state and a in legal(row['next_candidate_mask']))
        assert row['terminated'] or support
        signatures.add((row['reward']['value'],row['terminated'],next_state,tuple(support)))
        outcomes.append(row['reward']['value']+(0 if row['terminated'] else max(solve((next_state,a)) for a in support)))
    assert len(signatures)==1 and len(set(outcomes))==1
    visiting.remove(key);values[key]=outcomes[0];return values[key]
targets=[solve((state(r['observation']),digest(r['action']))) for r in rows]
graph=read(SELECTED/'development_graph.json')
assert targets==[r['target_value'] for r in graph['targets']]
source=Path(plan['feature_source']).read_bytes()
assert hashlib.sha256(source).hexdigest()=='4b4ff7a0aa74c47302c0da9e0a67770af99c0239bb44a3120c09193c757abc9d'
module=ast.parse(source.decode('utf8'))
module.body=[n for n in module.body if not(isinstance(n,ast.Import) and any(a.name=='numpy' for a in n.names))
             and not(isinstance(n,ast.FunctionDef) and n.name in ('fit','predict'))]
namespace={'__name__':'independent_public_features'};exec(compile(module,'pinned_public_features','exec'),namespace)
def forward(model,row):
    f=namespace['features'](row['observation'],row['action']);p=model['parameters']
    x=[(f[n]-c)/s for n,c,s in zip(model['feature_names'],p['center'],p['scale'],strict=True)]
    for i,layer in enumerate(p['layers']):
        x=[math.fsum(a*b for a,b in zip(w,x,strict=True))+bias for w,bias in zip(layer['weight'],layer['bias'],strict=True)]
        if i<2:x=list(map(math.tanh,x))
    return x[0]*p['target_scale']+p['target_center']
metrics=read(SELECTED/'metrics.json')
assert len(metrics)==18 and {(m['seed'],m['iteration']) for m in metrics}=={(s,i) for s in (17,29,43) for i in range(6)}
for metric in metrics:
    history=next(h for h in training['history'] if (h['seed'],h['iteration'])==(metric['seed'],metric['iteration']))
    assert metric['checkpoint']==history['saved_intermediate']['checkpoint']
    model=read(metric['checkpoint']['path'])
    assert digest(model)==history['model_sha256'] and sha(metric['checkpoint']['path'])==metric['checkpoint']['sha256']
    predicted=[forward(model,r) for r in rows]
    for actual,stored in zip(predicted,metric['predictions'],strict=True):close(actual,stored)
    close(math.fsum((a-b)**2 for a,b in zip(predicted,targets,strict=True))/len(rows),metric['development_supported_empirical_optimal_mse'])
selected=[]
for chosen in receipt['models']:
    best=min((m for m in metrics if m['seed']==chosen['seed']),key=lambda m:(m['development_supported_empirical_optimal_mse'],m['iteration']))
    assert chosen['selected_iteration']==best['iteration']
    assert chosen['original_checkpoint']==best['checkpoint']
    original=Path(best['checkpoint']['path']);copied=Path(chosen['checkpoint']['path'])
    assert original.read_bytes()==copied.read_bytes() and sha(copied)==best['checkpoint']['sha256']==chosen['checkpoint']['sha256']
    close(chosen['development_mse'],best['development_supported_empirical_optimal_mse'])
    selected.append({'seed':chosen['seed'],'iteration':chosen['selected_iteration'],'mse':chosen['development_mse'],
                     'copied_sha256':sha(copied),'original_bytes_equal':True})
assert {r['seed'] for r in selected}=={17,29,43}
assert all(m['selected_iteration']==0 and sha(m['checkpoint']['path'])==m['checkpoint']['sha256'] for m in training['models'])
for key in ('plan','development_graph','metrics'):
    assert sha(receipt[key]['path'])==receipt[key]['sha256']
print(json.dumps({'status':'passed_independent_selection_audit','models':selected,'all_checkpoint_forwards_verified':18,
    'development_rows':len(rows),'development_unique_state_actions':len(groups),'actual_training_directory_was_registered':True,
    'original_mc_selection_unchanged':True,'selection_source_archived_sha256':sha(archives[selector_source]),
    'outer_wall_seconds':outer['process']['wall_seconds'],'selection_archive_pins_verified':len(archives),
    'reference_files_verified':len(plan['references']),'fits':0,'native_executed':False,'heldout_read':False,
    'later_api_hardening_changes_criterion_or_weights':False},indent=2))

