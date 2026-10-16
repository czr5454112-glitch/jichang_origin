from copy import deepcopy
import hashlib
import json
from pathlib import Path
import weakref
import pytest
from test_g31_circulation_preference_request_context import bundle, ordered
from scripts.experiments.g31_ics_circulation import public_preference_protection_request_context as new
from scripts.experiments.g31_ics_circulation import public_preference_protection_cut as cut
from scripts.experiments.g31_ics_circulation import public_native_preference_search as search

ROWS=[]

@pytest.mark.parametrize('index',range(6))
def test_all32_match_reviewed_cut_and_nonpruned_strong_context(index):
    value=bundle(index); reference=new.base.RequestContext(value); actions=reference.actions()
    candidate=new.ProtectionRequestContext(value); old=cut.ProtectionContext(value,actions[0])
    assert ordered(candidate.baseline())==ordered(reference.predict(actions[0]))
    for action in actions:
        result=candidate.predict(action)
        assert ordered(result)==ordered(old.predict(action))
        if result['status']!='conditional_protection_rejected_prefix':
            assert ordered(result)==ordered(reference.predict(action))
    ROWS.append({'case':index,'counts':candidate.describe()['counts'],'same_as_reviewed_cut':True})

@pytest.mark.parametrize('defect',['status','pending','resource','generation','job','missing'])
def test_all_dynamic_input_guards_remain_per_request(defect):
    value=bundle(); action=new.base.RequestContext(value).actions()[0]
    if defect=='status': value['status']='unknown'
    elif defect=='pending': value['owner_pending_tray_requests']=['pending']
    elif defect=='resource': value['resources'][0]['occupancy']+=1
    elif defect=='generation': value['trays']['L']['generation']=False
    elif defect=='job': value['jobs']['loaded']['loaded_at']=.2
    else: value['jobs'].pop('receiver')
    reference=new.base.RequestContext(value); candidate=new.ProtectionRequestContext(value)
    assert candidate.describe()['cut_enabled'] is False
    assert ordered(candidate.predict(action))==ordered(reference.predict(action))

@pytest.mark.parametrize('defect',['bool','nan','missing','extra','window'])
def test_action_guards_retained_after_full_baseline(defect):
    value=bundle(); reference=new.base.RequestContext(value); action=reference.actions()[0]
    candidate=new.ProtectionRequestContext(value)
    if defect=='bool':action['return_delay']=False
    elif defect=='nan':action['empty_departure']=float('nan')
    elif defect=='missing':action.pop('later_action')
    elif defect=='extra':action['extra']=1
    else:action['empty_departure']+=.001
    assert ordered(candidate.predict(action))==ordered(reference.predict(action))
    assert candidate.describe()['counts']['candidate_prefix_rejections']==0

def test_context_guard_potential_once_and_no_extra_ast_compile(monkeypatch):
    counts={'guards':0,'potential':0};old=new.base.compile_guards;potential=new.base.original.service_aware_potential
    def compile_guards(): counts['guards']+=1;return old()
    def build(*args,**kwargs): counts['potential']+=1;return potential(*args,**kwargs)
    monkeypatch.setattr(new.base,'compile_guards',compile_guards)
    monkeypatch.setattr(new.base.original,'service_aware_potential',build)
    candidate=new.ProtectionRequestContext(bundle())
    for action in candidate.actions():candidate.predict(action)
    assert counts=={'guards':1,'potential':1}

def test_weak_monitor_does_not_retain_projection_or_create_cycle():
    class Projection: time=1.
    projection=Projection(); ref=weakref.ref(projection); ledger=new._ledger(projection,{'loaded':2.})
    projection.completed=ledger;ledger['loaded']=1.
    del projection
    assert ref() is None  # no forced GC/GC-disabling and the ledger still lives
    assert ledger=={'loaded':1.}

def test_mutation_isolation_including_rejected_prefix_and_baseline():
    value=bundle(); reference=new.base.RequestContext(value); candidate=new.ProtectionRequestContext(value)
    actions=candidate.actions(); expected=candidate.predict(actions[-1])
    value['jobs']['loaded']['destination']=99;candidate.snapshot()['resources'][0]['occupancy']=10
    candidate.baseline()['completion']['loaded']=-1
    first=candidate.predict(actions[-1]);first.setdefault('witness',{})['completed_prefix']={'loaded':-1}
    actions[0]['return_delay']=99
    assert ordered(candidate.predict(candidate.actions()[-1]))==ordered(expected)
    assert ordered(candidate.baseline())==ordered(reference.predict(reference.actions()[0]))

def test_source_hash_change_rejected_before_context(monkeypatch):
    monkeypatch.setattr(new,'EXPECTED_CUT','0'*64)
    with pytest.raises(ValueError,match='unreviewed_source'):new.ProtectionRequestContext(bundle())

def test_changed_completion_function_rejected_before_context(monkeypatch):
    monkeypatch.setattr(new.base.original.Projection,'run',lambda self: {})
    with pytest.raises(ValueError,match='changed_proof_function'):new.ProtectionRequestContext(bundle())

@pytest.mark.parametrize('index',range(6))
def test_same_four_methods_same_queries_and_selected_full_output(index):
    value=bundle(index); actions=new.base.RequestContext(value).actions()
    keys=((i,w,r,l) for i in range(2) for w in range(4) for r in range(2) for l in range(2))
    domain=dict(zip(keys,actions)); base=(0,0,0,0)
    for method in search.METHODS:
        reference=new.base.RequestContext(value);candidate=new.ProtectionRequestContext(value)
        baseline=reference.predict(domain[base]);old_calls=[];new_calls=[]
        def full(action):old_calls.append(deepcopy(action));return deepcopy(baseline) if action==domain[base] else reference.predict(action)
        def partial(action):new_calls.append(deepcopy(action));return candidate.baseline() if action==domain[base] else candidate.predict(action)
        old=search.search(domain,base,full,method=method,budget=32)
        result=search.search(domain,base,partial,method=method,budget=32)
        assert old_calls==new_calls
        for field in ('selected_action','selected_prediction','evaluations','stop_reason'):
            assert ordered(old[field])==ordered(result[field])
        assert candidate.describe()['counts']['candidate_queries']+1==result['evaluations']

def test_six_saved_actual_input_contexts_all32_vs_strong_reference():
    root=Path(__file__).resolve().parents[1]
    directory=root/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_static_context_pair_001/worker'
    path=directory/'supplied_inputs.json';plan=json.loads((directory/'plan.json').read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==plan['input_sha256']
    rows=[r for r in json.loads(path.read_bytes()) if r['owner']=='A'];assert len(rows)==6
    for row in rows:
        reference=new.base.RequestContext(row['bundle']); candidate=new.ProtectionRequestContext(row['bundle'])
        baseline=candidate.baseline()
        for action in reference.actions():
            full=reference.predict(action);result=candidate.predict(action)
            if result['status']=='conditional_protection_rejected_prefix':
                witness=result['witness'];job=witness['job']
                assert full['completion'][job]==witness['candidate_completed_at']>baseline['completion'][job]
            else:assert ordered(result)==ordered(full)
