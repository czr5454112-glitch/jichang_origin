"""Synthetic scheduler/retention audit fixtures only; no actual model runs."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import validate_future_later_paired_suffix as d


def action(later='native_default'):
    return {'initial_action':'native_default','empty_departure':.11,'return_delay':0.,'later_action':later}


def expected(n):
    rows=[]
    for i in range(n):
        owner='A' if i<(n//2) else 'B';retry=i%(n//2);known=n==2 or retry==1
        rows.append({'owner':owner,'at':float(i+1),'phase':'first_return' if owner=='A' else 'first_reuse_route',
            'recollection_index':retry,'information_status':'conditional_validated_later_v3_data' if known else 'unknown',
            'retry_admission':{'status':'not_admitted' if known else 'conditional_retry_admissible'}})
    return rows


def domain():
    return {key:{'maximum_prefix_cuts':n,'original_action':action(),'counterpart_action':action('prefer_8'),
        'suffixes':{v:{'status':'unknown_unexecuted'} for v in d.CHOICES}} for key,n in zip(d.ORDER,d.CUT_COUNTS,strict=True)}


@pytest.fixture
def harness(monkeypatch,tmp_path):
    class State:
        def __init__(self,engine,frames):self._engine,self._frames,self._consumed=engine,frames,False
    def make(n=2,*,bad_cut=False,early=False,unknown_B=False,extra=False,fail_prefix=False,fail_choice=None,alias=False):
        model=SimpleNamespace(Continuation=State,starts=0,advances=0,resumes=0,forks=0)
        timeline=expected(n)
        if unknown_B:
            timeline[-1]['information_status']='unknown';timeline[-1]['retry_admission']['status']='not_admitted'
        def start(context,fixed_action):
            assert context=='initial_only';model.starts+=1
            return State({'action':copy.deepcopy(fixed_action),'log':['initialized_once']},{'index':-1})
        def advance(state):
            model.advances+=1;state._consumed=True
            if early:return {'status':'unknown_early'}
            state._frames['index']=0;return State(state._engine,state._frames)
        def resume(state):
            model.resumes+=1;state._consumed=True;i=state._frames['index']
            if fail_prefix and i==0:raise RuntimeError('deliberate_prefix_failure')
            choice=state._engine['action']['later_action']
            if i==n-1 and choice==fail_choice:raise RuntimeError('deliberate_suffix_failure')
            state._engine['log'].extend([('before',i),('action',i,choice if i==n-1 else 'unchanged'),('after',i)])
            state._frames['index']+=1
            if state._frames['index']<n or extra and i==n-1:return State(state._engine,state._frames)
            return {'status':'conditional_prediction','all_events':copy.deepcopy(state._engine['log']),
                'action':copy.deepcopy(state._engine['action']),'completion':{str(i):float(i) for i in range(5)}}
        def cut(state):
            if bad_cut:raise ValueError('expired_route_wire_window')
            return {'at':n}
        def fork(state,choice):
            model.forks+=1;new=state if alias else copy.deepcopy(state)
            new._engine['action']['later_action']=choice
            return SimpleNamespace(_state=new,_after=copy.deepcopy(new._engine['action']),_consumed=False)
        def resume_future(branch):branch._consumed=True;return resume(branch._state)
        future=SimpleNamespace(_cut=cut,fork_later_action=fork,resume_future_later=resume_future)
        model.start_conditional,model.advance_to_collection_or_terminal,model.resume_same_action=start,advance,resume
        def point(state,_):
            e=timeline[min(state._frames['index'],n-1)]
            return {**{k:v for k,v in e.items() if k!='retry_admission'},'retry_status':e['retry_admission']['status']}
        monkeypatch.setattr(d,'point_description',point)
        monkeypatch.setattr(d,'graph',lambda state,_:d.bytes_of([state._engine,state._frames]))
        def graph_change(before,after,old,new):
            left=json.loads(before);left[0]['action']['later_action']=new
            assert d.bytes_of(left)==after
        monkeypatch.setattr(d,'action_graph_only',graph_change)
        monkeypatch.setattr(d,'mutable_ids',lambda state,_:{id(state._engine),id(state._frames),id(state._engine['log'])})
        monkeypatch.setattr(d,'terminal_description',lambda state,_:{'index':state._frames['index'],'consumed':state._consumed})
        monkeypatch.setattr(d.previous,'mutate_finished_copy',lambda state:state._engine.update(mutated=True))
        saved={}
        def save(label,prediction):
            path=tmp_path/(str(len(saved))+'_'+label+'.json.gz');path.write_bytes(gzip.compress(d.bytes_of(prediction)))
            saved[label]=d.ref(path);return saved[label]
        return model,future,save,saved,timeline
    return make


def test_fixed_six_two_choice_denominator():d.check_domain(domain())


@pytest.mark.parametrize('keys',[d.ORDER[:-1],tuple(reversed(d.ORDER))])
def test_missing_or_reordered_case_rejected(keys):
    rows=domain()
    with pytest.raises(ValueError,match='six_ordered_rows'):d.check_domain({k:rows[k] for k in keys})


@pytest.mark.parametrize('choices',[('native_default',),('prefer_8','native_default')])
def test_missing_or_reordered_choice_rejected(choices):
    rows=domain();rows[d.ORDER[0]]['suffixes']={v:{} for v in choices}
    with pytest.raises(ValueError,match='two_later_denominator'):d.check_domain(rows)


def test_budget_setup_counts_and_invalid_values():
    assert d.remaining(10.)==109.
    with pytest.raises(TimeoutError):d.remaining(119.)
    for v in (True,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):d.remaining(v)


def tiny_graph(later):
    class Engine:pass
    e=Engine();e.action=action(later);e.other={'x':1.};frames={'alias':e.other}
    return d.previous.graph_bytes((e,frames),(Engine,))


def test_complete_alias_graph_accepts_only_later_scalar_change():
    d.action_graph_only(tiny_graph('native_default'),tiny_graph('prefer_8'),'native_default','prefer_8')


@pytest.mark.parametrize('change',['past_action','float_bits'])
def test_complete_graph_other_changes_reject(change):
    before=tiny_graph('native_default');after=json.loads(tiny_graph('prefer_8'))
    for node in after['nodes']:
        if node[0]=='dict':
            for pair in node[1]:
                if change=='past_action' and pair[0]==['str','return_delay']:pair[1]=['float',(1.).hex()]
                if change=='float_bits' and pair[0]==['str','x']:pair[1]=['float',(-0.).hex()]
    with pytest.raises(ValueError,match='unexpected_graph'):d.action_graph_only(before,d.bytes_of(after),'native_default','prefer_8')


def test_json_type_bits_order_are_not_normalized():
    assert d.json_signature({'x':0})!=d.json_signature({'x':0.})
    assert d.json_signature({'x':-0.})!=d.json_signature({'x':0.})
    assert d.json_signature({'a':1,'b':2})!=d.json_signature({'b':2,'a':1})
    with pytest.raises(ValueError):d.json_signature({'x':float('nan')})


@pytest.mark.parametrize('n',[2,4])
def test_two_suffixes_share_single_prefix_without_reinitialize(harness,n):
    model,future,save,saved,exp=harness(n)
    result=d.run_case('initial_only',action(),n,model,future,save)
    targets={v:gzip.decompress(Path(saved[v]['path']).read_bytes()) for v in d.CHOICES}
    d.audit_case(result,exp,targets)
    assert result['status']=='exact_paired_future_suffixes'
    assert (model.starts,model.advances,model.resumes,model.forks)==(1,1,n+1,2)
    assert tuple(saved)==d.CHOICES


def test_first_known_cut_invalid_does_not_seek_more_favorable_cut(harness):
    model,future,save,saved,_=harness(4,bad_cut=True)
    result=d.run_case('initial_only',action(),4,model,future,save)
    assert result['prefix']['status']=='unknown_prefix_or_fork_error' and model.forks==0
    assert model.resumes==3 and tuple(result['suffixes'])==d.CHOICES and not saved


def test_unknown_B_without_real_fresh_permission_stays_unknown(harness):
    model,future,save,_,_=harness(unknown_B=True)
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert 'unknown_B_without_declared_fresh_pair' in result['prefix']['error'] and model.resumes==1 and model.forks==0


def test_early_terminal_saved_without_inventing_cut(harness):
    model,future,save,saved,_=harness(early=True)
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert result['prefix']['status']=='unknown_no_supported_B_cut' and 'prefix_terminal' in saved
    assert all(r['status']=='unknown_unexecuted' for r in result['suffixes'].values())


def test_unexpected_post_B_cut_not_auto_resumed(harness):
    model,future,save,saved,_=harness(extra=True)
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert all(r['status']=='unknown_unexpected_postB_cut' for r in result['suffixes'].values())
    assert model.resumes==3 and not saved


def test_alias_fork_rejected_before_suffix(harness):
    model,future,save,_,_=harness(alias=True)
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert result['prefix']['status']=='unknown_prefix_or_fork_error' and result['counts']['future_resumes']==0


def test_saved_prediction_modification_fails_hash(harness):
    model,future,save,saved,exp=harness();result=d.run_case('initial_only',action(),2,model,future,save)
    targets={v:gzip.decompress(Path(saved[v]['path']).read_bytes()) for v in d.CHOICES}
    Path(saved['native_default']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='saved_prediction_changed'):d.audit_case(result,exp,targets)


def test_both_terminal_outputs_exist_before_target_audit_failure(harness):
    model,future,save,saved,exp=harness();result=d.run_case('initial_only',action(),2,model,future,save)
    assert tuple(saved)==d.CHOICES and all(Path(r['path']).is_file() for r in saved.values())
    with pytest.raises(ValueError,match='full_prediction_bytes'):d.audit_case(result,exp,{v:b'{}' for v in d.CHOICES})


def test_suffix_exception_keeps_other_returned_and_both_denominator(harness):
    model,future,save,saved,_=harness(fail_choice='native_default')
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert result['suffixes']['native_default']['status']=='unknown_suffix_error'
    assert result['suffixes']['prefer_8']['status']=='returned' and tuple(saved)==('prefer_8',)


def test_prefix_exception_never_starts_suffix(harness):
    model,future,save,saved,_=harness(fail_prefix=True)
    result=d.run_case('initial_only',action(),2,model,future,save)
    assert result['prefix']['status']=='unknown_prefix_or_fork_error' and not saved and model.forks==0


def test_fewer_calculations_cannot_certify_exact(harness):
    model,future,save,saved,exp=harness();result=d.run_case('initial_only',action(),2,model,future,save)
    result['counts']['future_resumes']=1
    with pytest.raises(ValueError,match='complete_execution_counts'):d.audit_case(result,exp,{v:b'{}' for v in d.CHOICES})
