"""Synthetic cut/control tests only; no actual input/model/native execution."""
import ast
import copy
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_future_later_fork as f
c=f.core


def cut(*, later='native_default', retry=0):
    e=c.Projection.__new__(c.Projection)
    e.time=8.69;e.action={'initial_action':'prefer_2','empty_departure':3.101,'return_delay':0.,'later_action':later}
    local={'tray_id':'L','node':7,'mode':'loaded','business_bag_id':'reuse1','edge_from':-1,'edge_to':-1,
        'reception_node':-1,'generation':2,'traversal_id':4,'committed_prefix':[7],'available_at':8.5}
    pending={'phase':'first_reuse_route','at':8.65,'deadline':8.73,'request_id':'r','root':'Bphase',
        'trigger_tray':copy.deepcopy(local),'peer_message':'peer','recollection_index':retry,'policy_quiet_since':8.65}
    s={'pending':pending,'quiet':0.};e.owner_state={'B':s}
    e.trays={'L':{**copy.deepcopy(local),'job':'reuse1','goal':6,'lease':None,'projection_prefix':0}}
    info={'status':'conditional_validated_later_v3_data','bundle':{'trays':{'L':{'service_ready_at':8.75}}}}
    view={'owner_id':'B','now':e.time,'trays':[local]};screen={'status':'not_admitted','reason':'no_failed_read'}
    row={'owner':'B','kind':'planning_snapshot_v3','request':{'request_id':'r'},'ack':{'status':'delivered'},'terminal':True}
    e.client_rows={'r':row};e.events=[(9.,6,2,'projected_message_ack',(row,))]
    e.collection_trace=[{'phase':'first_return','disposition':'final_decision_no_more_recollection'}]
    if retry:e.collection_trace.append({'phase':'first_reuse_route','disposition':'one_fresh_pair_requested'})
    e.choice_jobs=set();e.unknown_phases=[];e.commands=[];e.dispatches=[];e.operation_guards=[]
    e.serial=0;e.sequence=2;e.request_sequence=1;e.new_contract=True
    e.nodes={7:{'resource_owner':'B','capacity':1},8:{'resource_owner':'B','capacity':1}}
    e.world=c.lazy.original.captures.CaptureWorld.__new__(c.lazy.original.captures.CaptureWorld)
    e.world.e=e;e.world.entries={'L':{'observed':True}};e.collect_calls=1
    decision={'owner':'B','s':s,'p':pending,'info':info,'screen':screen,'view':view}
    frames={'pc':c.PC,'run':{'initialized':True,'count':42,'event':(e.time,100,1,'owner_activation',('B','ready')),
        'handler_pc':'owner_handler'},'tick':{'owners':('B',),'index':0},
        'activate':{'owner':'B','s':s},'decide':decision}
    return c.Continuation(e,frames,c.lazy.original.context.encoded(e.action))


def tail_only(branch):
    """Run the real post-collect statements in a tiny synthetic physical world."""
    def resume(state):
        c.validate(state,pc=c.PC);state._consumed=True
        d=state._frames['decide']
        c.PARTS['decide_tail'](state._engine,d['owner'],d['s'],d['p'],d['info'],d['screen'],d['view'])
        return state._engine
    facade=SimpleNamespace(**{**vars(c),'resume_same_action':resume})
    fn=FunctionType(f.resume_future_later.__code__,{**f.resume_future_later.__globals__,'core':facade},
        f.resume_future_later.__name__,f.resume_future_later.__defaults__,f.resume_future_later.__closure__)
    return fn(branch)


def test_source_inventory_proves_actual_live_and_dormant_reads():
    proof=f.source_proof()
    assert set(proof['effective_action_uses'])=={'run','decide'}
    assert proof['collect_before_live_read'] and proof['fresh_pair_returns_before_live_read']
    assert proof['obsolete_scheduler_effective_noop'] and proof['obsolete_event_producers']==[]
    assert proof['capture_does_not_read_action'] and proof['constructor_legacy_action_later_independent']
    assert not proof['native_authority'] and not proof['coverage_of_unknown_remote_states_certified']
    assert c.source_proof()['same_action_only']


@pytest.mark.parametrize('text',["self.action.get('later_action')",'consume(self.action)',
    'self.action[field]','self.action = action'])
def test_unreviewed_action_escape_or_dynamic_access_rejected(text):
    with pytest.raises(ValueError):f.action_uses(ast.parse('def method(self,action,field):\n    '+text))


def test_earlier_live_read_is_rejected_by_source_scan():
    tree=c.tree_of(c.lazy.original.Projection.decide)
    tree.body[0].body.insert(0,ast.parse("unused=self.action['later_action']").body[0])
    with pytest.raises(ValueError,match='later_read_before_collection'):f.analyze_decide(tree)


@pytest.mark.parametrize('retry',[0,1])
def test_fork_changes_only_future_field_preserves_graph_prefix_and_parent(retry):
    parent=cut(retry=retry);branch=f.fork_later_action(parent,'prefer_8');child=branch._state
    assert parent._engine.action['later_action']=='native_default' and not parent._consumed
    assert child._engine.action=={**parent._engine.action,'later_action':'prefer_8'}
    assert parent._action_bytes!=child._action_bytes
    assert child._engine.world.e is child._engine
    assert child._frames['decide']['p'] is child._engine.owner_state['B']['pending']
    assert child._frames['decide']['s'] is child._frames['activate']['s'] is child._engine.owner_state['B']
    assert child._engine.events[0][4][0] is child._engine.client_rows['r']
    assert child._frames['run']==parent._frames['run'] and child._frames['tick']==parent._frames['tick']
    assert child._engine.collection_trace==parent._engine.collection_trace
    assert child._engine.collect_calls==parent._engine.collect_calls==1
    child._engine.client_rows['r']['terminal']=False
    assert parent._engine.client_rows['r']['terminal']
    assert branch.description()['changed_fields']==['later_action']


def test_same_choice_has_exact_old_action_identity_and_no_source_action_change():
    parent=cut();new=f.fork_later_action(parent,'native_default');old=c.fork_conditional(parent)
    assert new._state._action_bytes==old._action_bytes==parent._action_bytes
    assert new._state._frames['run']==old._frames['run']
    assert new.description()['changed_fields']==[]
    assert c.resume_same_action is f._CORE_FUNCTIONS['resume_same_action']


@pytest.mark.parametrize('choice,commands',[('native_default',0),('prefer_8',1)])
def test_new_contract_executes_real_decide_tail_once_without_collect(choice,commands):
    parent=cut();branch=f.fork_later_action(parent,choice);e=tail_only(branch)
    assert e.collect_calls==1 and len(e.collection_trace)==2
    assert len(e.operation_guards)==commands
    assert len([r for r in e.client_rows.values() if r['kind']=='route'])==commands
    if commands:
        row=next(r for r in e.client_rows.values() if r['kind']=='route')
        assert row['request']['next']==8 and row['request']['business_bag_id']=='reuse1'
        assert row['request']['expected_generation']==2 and row['request']['expected_traversal']==4
        assert e.events[0][0]==8.69+.01
    assert e.owner_state['B']['pending'] is None and e.choice_jobs=={'reuse1'}
    assert parent._engine.owner_state['B']['pending'] is not None and parent._engine.choice_jobs==set()
    with pytest.raises(ValueError,match='consumed'):f.resume_future_later(branch)


@pytest.mark.parametrize('mutation',['phase','owner','unknown','fresh_needed','deadline','quiet','clock',
    'wire_equal','wire_past','wire_bool','consumed','choice_used','previous_final','prior_route',
    'obsolete_event','committed','generation','past_action','wrong_pc'])
def test_unsupported_or_consumed_cut_rejected_without_prefix_mutation(mutation):
    state=cut();e=state._engine;d=state._frames['decide'];p=d['p']
    if mutation=='phase':p['phase']='first_return'
    elif mutation=='owner':d['view']['owner_id']='A'
    elif mutation=='unknown':d['info']['status']='unknown'
    elif mutation=='fresh_needed':d['screen']['status']='conditional_retry_admissible'
    elif mutation=='deadline':p['deadline']=e.time
    elif mutation=='quiet':d['s']['quiet']=e.time+.01
    elif mutation=='clock':d['view']['now']=e.time-.01
    elif mutation.startswith('wire_'):
        d['info']['bundle']['trays']['L']['service_ready_at']={'wire_equal':e.time+.01,'wire_past':e.time,'wire_bool':True}[mutation]
    elif mutation=='consumed':state._consumed=True
    elif mutation=='choice_used':e.choice_jobs.add('reuse1')
    elif mutation=='previous_final':e.collection_trace.append({'phase':'first_reuse_route','disposition':'final_decision_no_more_recollection'})
    elif mutation=='prior_route':e.client_rows['old']={'kind':'route','request':{'business_bag_id':'reuse1'}}
    elif mutation=='obsolete_event':e.events.append((e.time+.01,99,3,'later_decision',()))
    elif mutation=='committed':e.trays['L']['edge_to']=3
    elif mutation=='generation':e.trays['L']['generation']+=1
    elif mutation=='past_action':e.action['return_delay']=.5
    elif mutation=='wrong_pc':state._frames['pc']='next_event'
    old_count=state._frames['run']['count'];old_events=len(e.events)
    with pytest.raises((ValueError,KeyError)):f.fork_later_action(state,'prefer_8')
    assert state._frames['run']['count']==old_count and len(e.events)==old_events
    assert e.collect_calls==1


@pytest.mark.parametrize('choice',[None,True,8,{'later_action':'prefer_8','return_delay':.5},'prefer_3'])
def test_only_declared_string_future_choice_is_accepted(choice):
    with pytest.raises(ValueError,match='undeclared_future_action'):f.fork_later_action(cut(),choice)


def test_old_same_action_guard_still_rejects_manual_future_change():
    state=cut();state._engine.action['later_action']='prefer_8'
    with pytest.raises(ValueError,match='changed_action'):c.resume_same_action(state)


def test_changed_child_or_factory_forgery_rejected():
    with pytest.raises(ValueError,match='factory_only'):f.FutureLaterFork(None,None,None,None,object())
    branch=f.fork_later_action(cut(),'prefer_8');branch._state._engine.action['empty_departure']=4.201
    with pytest.raises(ValueError,match='changed_action'):f.resume_future_later(branch)


def test_source_method_rebinding_fails_closed(monkeypatch):
    monkeypatch.setitem(c.PARTS,'decide_tail',lambda *_:None)
    with pytest.raises(ValueError,match='loaded_source_binding_changed'):f.source_proof()


@pytest.mark.parametrize('kind',['dynamic_action','obsolete_scheduler'])
def test_new_effective_consumers_and_obsolete_event_producers_rejected(monkeypatch,kind):
    def new_action(self,field):return self.action[field]
    def new_schedule(self):return self.schedule(self.time,'later_decision')
    monkeypatch.setattr(c.Projection,'unreviewed_method',
        new_action if kind=='dynamic_action' else new_schedule,raising=False)
    with pytest.raises(ValueError,match='loaded_source_binding_changed'):f.source_proof()


def test_existing_method_code_replacement_rejected(monkeypatch):
    method=c.Projection.notify_local_lifecycle
    def changed(self,key):return self.action.get('later_action')
    monkeypatch.setattr(method,'__code__',changed.__code__)
    with pytest.raises(ValueError,match='loaded_source_binding_changed'):f.source_proof()


def test_obsolete_return_event_rejected_at_the_actual_cut():
    state=cut();state._engine.events.append((8.7,99,3,'return_decision',()))
    with pytest.raises(ValueError,match='obsolete_action_event'):f.fork_later_action(state,'prefer_8')


def test_proposed_fixed_six_pairs_only_flip_final_action_dimension():
    plan=f.proposed_six_pair_plan()
    assert len(plan['order'])==len(plan['counterpart_order'])==plan['prefix_runs']==6
    assert len(set(plan['order']))==6 and plan['paired_suffix_budget']==12
    for left,right in zip(plan['order'],plan['counterpart_order'],strict=True):
        a,x=left.split('/vector_');b,y=right.split('/vector_')
        assert a==b and int(x)^1==int(y)
    assert plan['fixed_earlier_fields']==['initial_action','empty_departure','return_delay']
    assert plan['native_calls']==0 and plan['retrospective_comparands_not_heldout']
