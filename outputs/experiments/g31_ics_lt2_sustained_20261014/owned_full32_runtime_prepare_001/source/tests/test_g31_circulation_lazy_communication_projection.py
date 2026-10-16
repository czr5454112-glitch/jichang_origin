import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import public_live_obligation_lazy_communication_projection as lazy


def fake(owner,*,mode='loaded',node=0,job='loaded',recovery=False):
    trace=[];reads=[]
    l={'tray_id':'L','node':node,'mode':mode,'job':job,'edge_to':-1,'available_at':0.,'generation':3,'traversal_id':4}
    e={'node':5,'mode':'empty'}
    state={'pending':None,'quiet':-1.,'started':set(),'pending_reply':None}
    value=SimpleNamespace(time=1.,activated_boundaries=set(),owner_state={owner:state},requests=[],
        demand_channel={owner:{'terminal':True,'captured':()}},trays={'L':l,'E':e},returns=0,
        return_pending=False,choice_jobs=set(),jobs={'reuse1':{'origin':7}},demand_inbox={owner:('reuse1',)},last_supply=None)
    value.waiting_signature=lambda owner:()
    value.exchange=lambda owner:trace.append(('exchange',owner))
    value.decide=lambda owner:trace.append(('decide',owner))
    def view(owner):
        reads.append(owner);return {'trays':[copy.deepcopy(l)]}
    value.world=SimpleNamespace(view=view)
    value.begin_collection=lambda owner,phase,tray:trace.append(('collection',owner,phase,copy.deepcopy(tray)))
    value.publish=lambda owner,phase:trace.append(('publish',owner,phase))
    def request(key,node,at):
        # Same relevant boundary as the actual source: E request construction
        # enqueues immutable future wire work and does not mutate L's row.
        trace.append(('request',key,node,at));e['new_request']=True
    value.request=request
    value.submit_preference=lambda *args:trace.append(('preference',args))
    if recovery:value.last_supply={'client_row':{'terminal':True,'ack':{'status':'rejected','delivered_at':0.}}}
    return value,trace,reads


@pytest.mark.parametrize('owner',['A','B'])
def test_idle_owner_skips_only_unused_full_view(owner):
    before,a,ar=fake(owner);after,b,br=fake(owner)
    lazy.original.Projection.activate(before,owner);lazy.Projection.activate(after,owner)
    assert a==b and ar==[owner] and br==[]


@pytest.mark.parametrize('owner,mode,node,job',[
    ('A','empty',6,None),('B','loaded',7,'reuse1')])
def test_actual_collection_trigger_row_identical(owner,mode,node,job):
    before,a,ar=fake(owner,mode=mode,node=node,job=job)
    after,b,br=fake(owner,mode=mode,node=node,job=job)
    lazy.original.Projection.activate(before,owner);lazy.Projection.activate(after,owner)
    assert a==b and ar==br==[owner] and a[-1][0]=='collection'


def test_recovery_before_lazy_read_does_not_change_L_trigger():
    before,a,ar=fake('B',mode='loaded',node=7,job='reuse1',recovery=True)
    after,b,br=fake('B',mode='loaded',node=7,job='reuse1',recovery=True)
    lazy.original.Projection.activate(before,'B');lazy.Projection.activate(after,'B')
    assert a==b and ar==br==['B']
    assert [v[0] for v in b][-2:]==['request','collection']


def test_preflight_publication_needs_no_trigger_view():
    before,a,ar=fake('B',mode='loading',node=7,job='reuse1')
    after,b,br=fake('B',mode='loading',node=7,job='reuse1')
    lazy.original.Projection.activate(before,'B');lazy.Projection.activate(after,'B')
    assert a==b and ar==['B'] and br==[] and b[-1]==('publish','B','preflight')


def test_quiet_guard_remains_before_view_and_actions():
    before,a,ar=fake('A',mode='empty',node=6,job=None)
    after,b,br=fake('A',mode='empty',node=6,job=None)
    before.owner_state['A']['quiet']=after.owner_state['A']['quiet']=2.
    lazy.original.Projection.activate(before,'A');lazy.Projection.activate(after,'A')
    assert a==b and ar==br==[] and not any(v[0]=='collection' for v in b)


def test_no_guard_capture_loop_or_entry_rewrite():
    assert lazy.Projection.collect is lazy.original.Projection.collect
    assert lazy.Projection.run is lazy.original.Projection.run
    assert lazy.Projection.protocol_event is lazy.original.Projection.protocol_event
    assert lazy.predict.__code__ is lazy.original.predict.__code__
    assert lazy.source_proof()['inverse_AST_exact'] is True
    assert lazy.source_proof()['new_numeric_expressions']==0
