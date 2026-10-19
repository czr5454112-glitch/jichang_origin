import ast, gzip, hashlib, json, math
from pathlib import Path
ROOT=Path.cwd()
P=ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/A3_fqi_training_001'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def near(a,b,tol=1e-9):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol*max(1,abs(b)),(a,b)
receipt=read(P/'receipt.json');episodes=read(P/'transitions.json');plan=read(P/'preregistered_plan.json')
assert digest(episodes)==receipt['gate']['episodes_sha256'] and receipt['gate']['status']=='passed'
attempts=list((P.parent/'attempts').glob('A3_fqi_training_001_*'))
assert len(attempts)==1
attempt=attempts[0];registration=read(attempt/'registration.json');outer=read(attempt/'receipt.json')
assert outer['status']=='completed' and outer['source_changed']==[] and outer['assessment']==receipt
assert outer['process']['exitcode']==0 and outer['process']['child_released_only_after_job_assignment']
archives={original:attempt/'source'/(f'{index:04d}'+Path(original).suffix)
          for index,original in enumerate(registration['source_pins'])}
assert all(sha(archives[p])==v for p,v in registration['source_pins'].items())
assert all(registration['source_pins'][p]==v for p,v in plan['sources'].items())
assert receipt['contract']==read(plan['contract']['path'])
assert sha(plan['contract']['path'])==plan['contract']['sha256']
allowed={'train':set(receipt['contract']['train_parent_groups']),'development':set(receipt['contract']['development_parent_groups'])}
assert all(e['split'] in allowed and e['parent_group'] in allowed[e['split']] for e in episodes)
assert set.union(*allowed.values()).isdisjoint(receipt['contract']['evaluation_plan']['held_out_parent_groups'])
assert all(sha(r['path'])==r['sha256'] for r in plan['references'])
assert receipt['contract']['gamma']==1 and set(e['split'] for e in episodes)=={'train','development'}
source=ROOT/'scripts/experiments/g31_ics_circulation/foundation_repeated_value.py'
source=archives[str(source)]
module=ast.parse(source.read_text(encoding='utf8'))
module.body=[n for n in module.body if not (isinstance(n,ast.Import) and any(a.name=='numpy' for a in n.names))
             and not (isinstance(n,ast.FunctionDef) and n.name in ('fit','predict'))]
namespace={'__name__':'pinned_public_features_stdlib'}
exec(compile(module,str(source),'exec'),namespace)
features=namespace['features']
def forward(model,obs,action):
    f=features(obs,action);p=model['parameters'];names=model['feature_names']
    assert sorted(f)==names
    x=[(f[n]-c)/s for n,c,s in zip(names,p['center'],p['scale'],strict=True)]
    for index,layer in enumerate(p['layers']):
        assert len(layer['weight'])==len(layer['bias'])==(64,64,1)[index]
        x=[math.fsum(a*b for a,b in zip(w,x,strict=True))+b for w,b in zip(layer['weight'],layer['bias'],strict=True)]
        if index<2:x=list(map(math.tanh,x))
    return x[0]*p['target_scale']+p['target_center']
def state(obs):return digest({k:v for k,v in obs.items() if k not in ('episode_id','decision_id','opportunity')})
def allowed(mask):
    return [c['semantic'] for c in mask if c['enabled'] and (c['guard_status']=='original_fixed_rule' or
           c['guard_status']=='passed' and c.get('per_job_delta') and all(v<=0 for v in c['per_job_delta'].values()))]
owner=receipt['contract']['owner']
rows={split:[r for e in episodes for r in e['transitions'] if r['owner']==owner and r['split']==split]
      for split in ('train','development')}
def rowkey(r):return r['source']['sha256'],r['decision_id']
def mc(rr):
    by={rowkey(r):r for r in rr}
    def rec(r,seen):
        assert rowkey(r) not in seen and r['training_eligible'] and not r['truncated']
        if r['terminated']:return r['reward']['value']
        nxt=by[(r['source']['sha256'],r['next_decision_id'])]
        assert nxt['observation']==r['next_observation'] and r['reward']['end']==nxt['reward']['start']
        return r['reward']['value']+r['gamma']*rec(nxt,seen|{rowkey(r)})
    return [rec(r,set()) for r in rr]
def supported(r,rr):
    if r['terminated']:return []
    visited={digest(x['action']) for x in rr if x['training_eligible'] and x['owner']==r['owner']
             and x['peer_policy_id']==r['peer_policy_id'] and state(x['observation'])==state(r['next_observation'])}
    return [a for a in allowed(r['next_candidate_mask']) if digest(a) in visited]
all_reward_checks=0
for e in episodes:
    native=json.loads(gzip.decompress(Path(e['origin']['path']).read_bytes()))
    assert sha(e['origin']['path'])==e['origin']['sha256']
    arrivals={j['business_bag_id']:j['arrival'] for j in native['input']['jobs']}
    completion={j['business_bag_id']:j['completed_at'] for j in native['result']['jobs']}
    for r in e['transitions']:
        assert r['gamma']==1 and r['training_eligible'] and not r['truncated']
        start,end=r['reward']['start'],r['reward']['end']
        expected=-math.fsum(max(0,min(end,completion[j])-max(start,a)) for j,a in arrivals.items())
        near(expected,r['reward']['value']);all_reward_checks+=1
mc_values={s:mc(rr) for s,rr in rows.items()}
def graph_targets(rr):
    grouped={}
    for r in rr:grouped.setdefault((state(r['observation']),digest(r['action'])),[]).append(r)
    q={};visiting=set();nondeterministic=[]
    def rec(key):
        if key in q:return q[key]
        assert key not in visiting
        visiting.add(key);group=grouped[key]
        signatures={(r['reward']['value'],r['terminated'],None if r['terminated'] else state(r['next_observation'])) for r in group}
        if len(signatures)!=1:nondeterministic.append(key)
        values=[]
        for r in group:
            actions=supported(r,rr)
            assert r['terminated'] or actions
            values.append(r['reward']['value']+(0 if r['terminated'] else r['gamma']*max(rec((state(r['next_observation']),digest(a))) for a in actions)))
        q[key]=math.fsum(values)/len(values);visiting.remove(key);return q[key]
    values=[rec((state(r['observation']),digest(r['action']))) for r in rr]
    return values,q,nondeterministic
optimal={s:graph_targets(rr) for s,rr in rows.items()}
assert not any(v[2] for v in optimal.values()),'empirical transition not deterministic'
summaries=[];checks=0
for hist in receipt['history']:
    seed,it=hist['seed'],hist['iteration']
    ref=hist['saved_intermediate']
    assert all(sha(v['path'])==v['sha256'] for v in ref.values())
    model,targets=read(ref['checkpoint']['path']),read(ref['targets']['path'])
    assert digest(model)==hist['model_sha256'] and digest(targets)==hist['targets_sha256']==model['training_rows_sha256']
    assert model['model_sha256']==digest({k:v for k,v in model.items() if k!='model_sha256'})
    assert model['seed']==seed and model['epochs']==100 and len(model['feature_names'])==123
    assert model['native_execution_authority'] is False and model['cpu_threads']==1
    assert len(targets)==len(rows['train'])==9
    assert [p['epoch'] for p in model['training_curve']]==list(range(0,101,10))
    if it:previous=read(P/'iterations'/f'seed_{seed}_iteration_{it-1}_checkpoint.json')
    for r,t,monte in zip(rows['train'],targets,mc_values['train'],strict=True):
        assert t['observation']==r['observation'] and t['action']==r['action'] and t['split']=='train'
        assert t['parent_group']==r['parent_group'] and t['source_decision_id']==r['decision_id']
        actions=supported(r,rows['train'])
        expected=monte if not it else r['reward']['value']+(0 if r['terminated'] else max(forward(previous,r['next_observation'],a) for a in actions))
        near(t['target_value'],expected);checks+=1
        if it:assert t['supported_next_action_count']==len(actions)
    vectors=[features(t['observation'],t['action']) for t in targets]
    for idx,name in enumerate(model['feature_names']):
        center=math.fsum(v[name] for v in vectors)/len(vectors)
        scale=math.sqrt(math.fsum((v[name]-center)**2 for v in vectors)/len(vectors))
        near(model['parameters']['center'][idx],center)
        near(model['parameters']['scale'][idx],1 if scale<1e-9 else scale)
    target_center=math.fsum(t['target_value'] for t in targets)/len(targets)
    target_scale=max(1,math.sqrt(math.fsum((t['target_value']-target_center)**2 for t in targets)/len(targets)))
    near(model['parameters']['target_center'],target_center);near(model['parameters']['target_scale'],target_scale)
    predictions={s:[forward(model,r['observation'],r['action']) for r in rr] for s,rr in rows.items()}
    mse=lambda x,y:math.fsum((a-b)**2 for a,b in zip(x,y,strict=True))/len(x)
    dev_mse=mse(predictions['development'],mc_values['development'])
    near(dev_mse,hist['development_behavior_return_mse'])
    train_mse=mse(predictions['train'],[t['target_value'] for t in targets])
    near(train_mse,model['training_curve'][-1]['mse'],tol=2e-4)
    # Diagnostic only: this is not a new checkpoint selection or model change.
    dev_optimal_mse=mse(predictions['development'],optimal['development'][0])
    dev_residual=[r['reward']['value']+(0 if r['terminated'] else max(forward(model,r['next_observation'],a) for a in supported(r,rows['development'])))
                  for r in rows['development']]
    summaries.append({'seed':seed,'iteration':it,'train_mse':train_mse,'dev_behavior_mse':dev_mse,
                      'diagnostic_dev_supported_empirical_optimal_mse':dev_optimal_mse,
                      'diagnostic_dev_bellman_residual_mse':mse(predictions['development'],dev_residual)})
for selected in receipt['models']:
    assert selected['selected_iteration']==0
    assert sha(selected['checkpoint']['path'])==selected['checkpoint']['sha256']==sha(P/'iterations'/f"seed_{selected['seed']}_iteration_0_checkpoint.json")
floors={}
for split,rr in rows.items():
    grouped={}
    for r,ret in zip(rr,mc_values[split],strict=True):
        key=digest(features(r['observation'],r['action']))
        grouped.setdefault(key,[]).append(ret)
    floor=math.fsum(math.fsum((v-math.fsum(g)/len(g))**2 for v in g) for g in grouped.values())/len(rr)
    floors[split]={'behavior_mc_mse_irreducible_floor_given_features':floor,
       'unique_feature_action_vectors':len(grouped),'conflicting_groups':[g for g in grouped.values() if max(g)-min(g)>1e-8],
       'actual_mc_returns':mc_values[split],'supported_empirical_optimal_targets':optimal[split][0]}
print(json.dumps({'status':'passed_stdlib_read_only','all_transition_reward_checks':all_reward_checks,
 'checkpoint_count':len(summaries),'training_target_checks':checks,'formal_test_read':False,'fits':0,
 'historical_training_archive_pins_verified':len(archives),'historical_outer_receipt_verified':True,
 'empirical_graph_deterministic':True,'floors_and_targets':floors,'metrics':summaries},indent=2))

