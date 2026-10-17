"""Private construction and fake execution seams only; no real model/native."""
import ast
import copy
import inspect
from types import FunctionType,SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_owned_prefix_evaluator as e
from scripts.experiments.g31_ics_circulation import live_obligation_owned_initial_provider as p
from scripts.experiments.g31_ics_circulation import live_obligation_owned_same_information_search as s
from scripts.experiments.g31_ics_circulation import live_obligation_same_information_search as old_search
from scripts.experiments.g31_ics_circulation import live_obligation_initial_decision_adapter_v2 as v2
from test_g31_circulation_future_later_paired_driver import harness,action
from test_g31_circulation_live_initial_decision_seam import batch
from test_g31_circulation_future_later_fork import cut as synthetic_cut


def actions():return p.future.core.lazy.original.physics.previous.actions()
def groups():return p.domain.partition(actions())['groups']


def test_closed_AST_inverses_and_complete_globals():
    proof=e.source_proof()
    assert all(proof[k]['inverse_AST_exact'] for k in ('point','terminal','run','group'))
    assert proof['run']['exact_statement_count']==16 and proof['group']['exact_statement_count']==1
    assert proof['original_initial_and_cut_guards_retained'] and proof['same_whole_dynamic_graph_clone']
    assert not proof['source_inventory_memoization'] and not proof['initial_context_cache']
    assert not proof['arbitrary_tamper_resistance'] and not proof['100ms_certified']


@pytest.mark.parametrize('target',['point','terminal','run','group'])
def test_private_code_replacement_rejected(monkeypatch,target):
    function=getattr(e,'_'+target)
    monkeypatch.setattr(function,'__code__',(lambda *args:None).__code__)
    with pytest.raises(ValueError,match='private_code_identity'):e.source_proof()


@pytest.mark.parametrize('target',['point','run','group'])
def test_complete_global_drift_rejected(monkeypatch,target):
    function=getattr(e,'_'+target)
    monkeypatch.setitem(function.__globals__,'unexpected_live_dependency',object())
    with pytest.raises(ValueError,match='defining_globals'):e.source_proof()


def test_source_rewriter_rejects_missing_or_duplicate_statement():
    with pytest.raises(ValueError,match='one_exact_statement'):
        e._rewrite(e.previous.run_case,[('missing=1','missing=2')])
    with pytest.raises(ValueError,match='one_exact_statement'):
        e._rewrite(e.previous.run_case,[('row=1','row=2'),('row=1','row=3')])


def fake_run(model,future,save):
    # Closed synthetic substitution used only by this test. The public runtime
    # accepts no supplied factories/state callbacks; source_proof rejects them.
    ns={**e.previous.run_case.__globals__,'point_description':e.previous.point_description,
        'terminal_description':e.previous.terminal_description,'_OWNERSHIP':e.OWNERSHIP}
    function=FunctionType(e._RUN_CODE,ns,'synthetic_owned_run')
    return function('initial_only',action(),4,model,future,save)


@pytest.mark.parametrize('n',[2,4])
def test_fake_same_chronology_two_children_before_resume(harness,n):
    model,future,save,saved,_=harness(n)
    fork=future.fork_later_action;resume=future.resume_future_later;calls=[]
    def newfork(state,choice):calls.append(('fork',choice));return fork(state,choice)
    def newresume(branch):calls.append(('resume',branch._after['later_action']));return resume(branch)
    future.fork_later_action=newfork;future.resume_future_later=newresume
    result=fake_run(model,future,save)
    assert calls==[('fork',c) for c in e.domain.LATER]+[('resume',c) for c in e.domain.LATER]
    assert result['prefix']['parent_unconsumed'] and result['prefix']['isolation_basis']==e.OWNERSHIP
    assert all(row['status']=='returned' for row in result['suffixes'].values())
    assert (model.starts,model.advances,model.resumes,model.forks)==(1,1,n+1,2)
    assert tuple(saved)==e.domain.LATER


@pytest.mark.parametrize('kind',['bad_cut','unknown_B','early','extra','fail_prefix','fail_choice'])
def test_fake_failure_denominator_retained(harness,kind):
    kwargs={kind:'native_default' if kind=='fail_choice' else True}
    model,future,save,saved,_=harness(**kwargs)
    result=fake_run(model,future,save)
    assert tuple(result['suffixes'])==e.domain.LATER
    if kind=='fail_choice':
        assert result['suffixes']['native_default']['status']=='unknown_suffix_error'
        assert result['suffixes']['prefer_8']['status']=='returned'
    elif kind=='extra':assert all(row['status']=='unknown_unexpected_postB_cut' for row in result['suffixes'].values())
    else:assert all(row['status']=='unknown_unexecuted' for row in result['suffixes'].values()) and model.forks==0


def test_diagnostic_operations_are_not_called(harness,monkeypatch):
    model,future,save,_,_=harness()
    def forbidden(*args):raise AssertionError('diagnostic_called')
    for key in ('graph','mutable_ids','action_graph_only'):monkeypatch.setattr(e.previous,key,forbidden)
    monkeypatch.setattr(e.previous.previous,'mutate_finished_copy',forbidden)
    result=fake_run(model,future,save)
    assert all(row['status']=='returned' for row in result['suffixes'].values())


def minimal_point():
    pending={'phase':'first_reuse_route','recollection_index':0};owner={'pending':pending}
    event=(2.,5,7,'tick',());engine=SimpleNamespace(time=2.,events=[],sequence=7,owner_state={'B':owner})
    engine.world=SimpleNamespace(e=engine)
    state=SimpleNamespace(_engine=engine,_frames={'decide':{'owner':'B','p':pending,'s':owner,
        'info':{'status':'known'},'screen':{'status':'not_admitted'}},'run':{'event':event},'tick':{'owners':['A','B'],'index':1}},
        description=lambda:{'program_counter':'post_collect'})
    return state,SimpleNamespace(validate=lambda *args,**kw:None,PC='post_collect')


@pytest.mark.parametrize('failure',[None,'world','pending','event','recorder'])
def test_point_semantic_guards_retained_without_encoding(failure):
    state,model=minimal_point()
    if failure=='world':state._engine.world.e=None
    elif failure=='pending':state._frames['decide']['p']=copy.deepcopy(state._frames['decide']['p'])
    elif failure=='event':state._engine.events.append(state._frames['run']['event'])
    elif failure=='recorder':state._engine._phase_b_recorder=object()
    if failure is not None:
        with pytest.raises(ValueError):e._point(state,model)
    else:
        result=e._point(state,model)
        assert result['world_engine_alias'] and result['owner_pending_alias'] and 'graph_sha256' not in result


def test_original_factory_copies_full_graph_preserving_internal_alias(monkeypatch):
    core=e.future.core
    class Engine:pass
    monkeypatch.setattr(core,'Projection',Engine)
    engine=Engine();engine.action={'unchanged':1};engine.shared=[];engine.world=SimpleNamespace(e=engine)
    frames={'pc':'next_event','run':{'initialized':True,'count':4},'shared':engine.shared}
    parent=core.Continuation(engine,frames,core.lazy.original.context.encoded(engine.action))
    left,right=core.fork_conditional(parent),core.fork_conditional(parent)
    assert left._engine.world.e is left._engine and left._frames['shared'] is left._engine.shared
    left._engine.shared.append('mutated')
    assert parent._engine.shared==right._engine.shared==[]
    assert left._engine is not right._engine is not parent._engine


def test_all32_keep_original_cut_and_complete_graph_clone_calls():
    """Real guards/fork factory on synthetic cut graphs; no model advance."""
    core=e.future.core;calls={'cut':0,'deepcopy':0,'source':0,'suffix':0}
    def checked_cut(state):calls['cut']+=1;return e.future._cut(state)
    def clone(state):calls['deepcopy']+=1;return core.fork_conditional(state)
    def proof():calls['source']+=1;return e.future.source_proof()
    def finish(state):
        core.validate(state,pc=core.PC);state._consumed=True;calls['suffix']+=1
        return {'status':'conditional_prediction','completion':{j:1. for j in p.JOBS},
            'action':copy.deepcopy(state._engine.action),'unknown_information_phases':[]}
    model=SimpleNamespace(**{**vars(core),'fork_conditional':clone,'resume_same_action':finish})
    def start(context,fixed):
        assert context=='synthetic_cut_only';state=synthetic_cut()
        state._engine.action=copy.deepcopy(fixed);state._action_bytes=core.lazy.original.context.encoded(fixed)
        return state
    model.start_conditional=start;model.advance_to_collection_or_terminal=lambda state:state
    ns={**e.future.__dict__,'core':model,'_cut':checked_cut,'source_proof':proof}
    ff=SimpleNamespace(_cut=checked_cut)
    for name in ('fork_later_action','resume_future_later'):
        original=getattr(e.future,name);setattr(ff,name,FunctionType(original.__code__,ns,name))
    # The one entry proof plus two fork and two resume proofs per prefix.
    proof()
    for group in groups():
        saved={}
        def save(label,value):saved[label]=copy.deepcopy(value);return {'saved':label}
        result=e._run('synthetic_cut_only',group['representative_action'],4,model,ff,save)
        assert all(row['status']=='returned' for row in result['suffixes'].values())
        assert tuple(saved)==e.domain.LATER
    assert calls=={'cut':80,'deepcopy':32,'source':65,'suffix':32}


def test_prediction_saved_before_terminal_error_is_retained_unknown(harness):
    model,future,save,saved,_=harness()
    def failed_terminal(*args):raise ValueError('postsave_terminal_guard')
    ns={**e._RUN_GLOBALS,'point_description':e.previous.point_description,'terminal_description':failed_terminal}
    run=FunctionType(e._RUN_CODE,ns)
    result=run('initial_only',action(),4,model,future,save)
    assert tuple(saved)==e.domain.LATER
    assert all(row['status']=='unknown_suffix_error' and 'prediction' in row for row in result['suffixes'].values())


def test_public_execution_accepts_no_target_or_save_callback(monkeypatch):
    assert tuple(inspect.signature(e.execute_group).parameters)==('group','context')
    seen=[]
    def fake(group,make,save,*,model,future):
        seen.append(make(group['prefix_index'],group['representative_action']))
        value={'nested':{'all_events':[1.,-0.]}}
        artifact=save('native_default',value);value['nested']['all_events'].append(99.)
        return {'rows':{f'vector_{i:02d}':{} for i in group['candidate_indices']},'artifact':artifact}
    monkeypatch.setattr(e,'_group',fake)
    result=e.execute_group(groups()[0],'initial_only')
    assert seen==['initial_only'] and result['predictions']['native_default']['nested']['all_events']==[1.,-0.]
    assert not result['diagnostic_graphs_computed'] and not result['native_authority']


@pytest.mark.parametrize('change',['past','index','order'])
def test_public_group_requires_exact_cartesian_member(change):
    group=copy.deepcopy(groups()[0])
    if change=='past':group['representative_action']['return_delay']=99.
    elif change=='index':group['prefix_index']=True
    else:group['candidate_indices'].reverse()
    with pytest.raises(ValueError,match='fixed_prefix_group'):e.execute_group(group,None)


def fake_item(group,defect=None):
    predictions={c:{'status':'conditional_prediction','completion':{j:1. for j in p.JOBS},'unknown_information_phases':[]}
        for c in e.domain.LATER}
    suffixes={c:{'status':'returned','isolation_basis':e.OWNERSHIP} for c in e.domain.LATER}
    inner={'prefix':{'status':'supported_known_B_cut','isolation_basis':e.OWNERSHIP,
        'diagnostic_graphs_computed':False,'parent_unconsumed':True},'suffixes':suffixes,
        'counts':{'initial_engines':1,'initial_advances':1,'prefix_same_resumes':1,'future_forks':2,'future_resumes':2}}
    detail={'context_constructions':1,'detail':inner,'rows':{f'vector_{i:02d}':{'status':'unknown_prediction_returned_audit_pending'}
        for i in group['candidate_indices']}}
    if defect=='suffix_status':suffixes[e.domain.LATER[0]]['status']='unknown_suffix_error'
    elif defect=='group_error':detail['rows'][f'vector_{group["candidate_indices"][0]:02d}']['status']='unknown_group_error'
    elif defect=='ownership':inner['prefix']['isolation_basis']='fabricated'
    elif defect=='consumed':inner['prefix']['parent_unconsumed']=False
    elif defect=='missing':predictions[e.domain.LATER[0]]['completion'].pop('blocker')
    elif defect=='info':predictions[e.domain.LATER[0]]['unknown_information_phases']=['B']
    return {'detail':detail,'predictions':predictions}


@pytest.fixture
def provider_fake(monkeypatch):
    seen=[];decision=SimpleNamespace(audit_copy=lambda:{'owner':'A','public_sha256':'fake','at':.11})
    monkeypatch.setattr(p.origin,'require_current',lambda d:seen.append('guard') or d)
    monkeypatch.setattr(p.origin,'supplied_snapshot',lambda d:seen.append('context') or 'initial_only')
    request=SimpleNamespace(uses=0)
    request.description=lambda:{'proof_binding':{'proof_uses':request.uses}}
    request.close=lambda:seen.append('close')
    monkeypatch.setattr(p.binding,'bind_request',lambda:seen.append('bind') or request)
    def proof(actual):
        assert actual is request
        request.uses+=1;seen.append('proof')
    monkeypatch.setattr(p,'source_proof',proof)
    def setup(defect=None):
        def execute(actual,group,context):
            assert actual is request and context=='initial_only';seen.append(group['prefix_index'])
            if defect=='raise' and group['prefix_index']==0:raise ValueError('synthetic_group_error')
            request.uses+=4
            return fake_item(group,defect if group['prefix_index']==0 else None)
        monkeypatch.setattr(p.execution,'execute_bound_group',execute)
        return decision,seen
    return setup


def test_provider_all16_constructions_full32_order_and_cost(provider_fake):
    decision,seen=provider_fake();value=p.evaluate_declared32(decision).audit_copy()
    assert value['status']=='conditional_forecasts_complete'
    assert seen.count('context')==16 and seen.count('guard')==2 and seen.count('proof')==1
    assert [r['candidate_index'] for r in value['rows']]==list(range(32))
    assert value['counts']['future_forks']==value['counts']['future_resumes']==32
    assert value['counts']['initial_engines']==value['counts']['context_constructions']==16
    assert value['complete_request_100ms_certified'] is False
    assert seen.count('bind')==seen.count('close')==1
    assert value['source_binding']['status']=='closed_complete65'


@pytest.mark.parametrize('defect',['suffix_status','group_error','ownership','consumed','missing','info','raise'])
def test_saved_prediction_does_not_override_postsave_failure(provider_fake,defect):
    decision,seen=provider_fake(defect);value=p.evaluate_declared32(decision).audit_copy()
    assert len(value['rows'])==32 and seen.count('context')==16
    assert value['rows'][0]['status']=='unknown_projection' and value['rows'][0]['completion'] is None
    assert value['rows'][2]['status']=='conditional_forecast'
    if defect=='raise':assert value['rows'][1]['status']=='unknown_projection'


def test_origin_changed_after_calculation_invalidates_every_estimate(provider_fake,monkeypatch):
    decision,_=provider_fake();count=[0]
    def current(d):
        count[0]+=1
        if count[0]>1:raise ValueError('changed_native_admission')
        return d
    monkeypatch.setattr(p.origin,'require_current',current)
    value=p.evaluate_declared32(decision).audit_copy()
    assert all(r['status']=='unknown_origin_or_provider_failure' and r['completion'] is None for r in value['rows'])


def test_search_full_original_code_v2_origin_and_provider_binding():
    proof=s.source_proof()
    assert proof['v2_final_current_revalidation'] and not proof['100ms_certified']
    assert s.propose_initial.__code__ is old_search.propose_initial.__code__
    assert s.propose_initial.__globals__['origin'] is v2
    assert s.propose_initial.__globals__['provider'] is p
    assert s.select.__globals__['_known'] is s._known


def test_propose_calls_v2_final_fresh_guard(monkeypatch):
    decision=object();seen=[]
    monkeypatch.setattr(p,'evaluate_declared32',lambda d:batch({0:[10.]*5}))
    monkeypatch.setattr(p,'require_current_batch_origin',lambda b:decision)
    monkeypatch.setattr(v2,'revalidate_first_component',lambda d,a:seen.append((d,a)) or {'status':'v2_revalidated'})
    result=s.propose_initial(decision,method='incumbent',incumbent_index=0)
    assert len(seen)==1 and seen[0][0] is decision and result['local_component']['status']=='v2_revalidated'
    assert result['complete_request_100ms_certified'] is False


@pytest.mark.parametrize('method',s.METHODS)
def test_every_strong_method_same_complete_charged_provider(method):
    result=s.select(batch({0:[10.]*5,17:[9.]*5}),method=method,incumbent_index=0)
    assert result['accounting']['provider_charged_candidate_denominator']==32
    assert result['selection_budget']==32 and len(result['candidate_rows'])==32
    assert not result['accounting']['model_budget_saved_by_queries']


def test_unknown_family_and_single_ulp_regression_not_safe():
    result=s.select(batch({0:[10.]*5,1:[10.000000000000002,1.,1.,1.,1.]},unknown=[3]),
        method='finite_MPC',incumbent_index=0)
    assert result['selected_index']==0 and not result['full_reference_known']
    assert result['candidate_rows'][1]['estimated_not_worse'] is False and result['unknown_forecast_indices']==[3]
