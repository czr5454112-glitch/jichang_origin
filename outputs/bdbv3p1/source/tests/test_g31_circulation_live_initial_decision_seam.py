"""Focused synthetic boundary fixtures only; not native/model acceptance.

Authority primitives are stubbed only in the adapter unit fixture. No actual
extension, future projection, saved native result or performance experiment is
loaded. Separate tests reject ordinary JSON and changed exact-client identity.
"""
import copy
import itertools
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_initial_decision_adapter as a
from scripts.experiments.g31_ics_circulation import live_obligation_initial_candidate_provider as p
from scripts.experiments.g31_ics_circulation import live_obligation_same_information_search as s
from scripts.experiments.g31_ics_circulation import live_obligation_full32_suffix_partition as domain


def actions():return [dict(zip(domain.FIELDS,row)) for row in itertools.product(domain.INITIAL,(.11,1.,2.,3.),domain.RETURN,domain.LATER)]


@pytest.fixture
def native_stub(monkeypatch):
    # Fake runtime is never advertised as native acceptance; this fixture
    # replaces the authenticity primitive to exercise the independent seam.
    session=SimpleNamespace(physical_time=.11);native=object();accepted=object()
    client=a.history.fixture.LocalTransport(session);client.activate('A',{'kind':'synthetic_initial_test'})
    request={'owner_id':'A','request_id':'opaque:one','kind':'planning_snapshot','target_owner':'B',
        'message_delay':.01,'publication_delay':.01,'expiry':.21}
    client.rows[request['request_id']]={'kind':'planning_snapshot','request':copy.deepcopy(request),'terminal':True,'ack':{'status':'delivered'}}
    client.calls.append({'at':.05,'kind':'planning_snapshot','retry':False,'request':copy.deepcopy(request),'reply':{}})
    monkeypatch.setattr(a.native_gate,'_valid_handle',lambda n,se,h:n is native and se is session and h is accepted)
    def context(**kwargs):return object.__new__(a.supplied.SuppliedContext)
    monkeypatch.setattr(a.supplied,'initial_context',context)
    view={'owner_id':'A','now':.11,'node_records':[(0,'R',1.,1.,1.,1)],'edge_records':[(0,2,1.,1.)],
        'trays':[{'tray_id':'L','mode':'loaded','business_bag_id':'loaded','node':0,'edge_to':-1,'edge_from':-1,
            'service_ready_known':True,'service_ready_at':1.1,'generation':1,'traversal_id':0}],
        'node_contracts':[{'node':2,'resource_owner':'A','occupancy':0,'capacity':1}]}
    observed=[]
    def collect(n,se,owner,key,*,accepted):
        observed.extend([('view',owner),('command',owner,key),('received',owner)])
        ledger=a.native_gate.previous.NativeJobLedger(a.native_gate.previous._LEDGER_TOKEN,se,owner,{})
        return {'status':'conditional_native_delivered_model_input','native_delivery_verified':True,
            'raw_endpoints':{'view':copy.deepcopy(view),'command':{'request_id':key,'kind':'planning_snapshot'},'received':[]},
            'native_read':{'owner':owner,'own_request_id':key,'at':se.physical_time}},ledger
    monkeypatch.setattr(a.native_gate,'collect_initial_ledger',collect)
    return SimpleNamespace(session=session,native=native,client=client,accepted=accepted,key=request['request_id'],view=view,reads=observed)


def collect(f):return a.collect_initial_decision(f.native,f.session,'A',f.key,f.client,f.accepted)


def test_actual_origin_seam_binds_only_own_triplet_and_real_row(native_stub):
    f=native_stub;d=collect(f)
    assert type(d) is a.InitialDecision and len(f.reads)==3 and all(r[1]=='A' for r in f.reads)
    assert a.require_current(d) is d and type(a.supplied_snapshot(d)) is a.supplied.SuppliedContext
    copied=d.audit_copy();assert copied['saved_copy_has_authority'] is False
    with pytest.raises(ValueError):a.require_current(copied)


@pytest.mark.parametrize('mutation',['clock','admission','request','row_ack','new_call','owner','digest'])
def test_current_capability_rejects_changed_authority_or_payload(native_stub,mutation):
    f=native_stub;d=collect(f)
    if mutation=='clock':f.session.physical_time=.12
    elif mutation=='admission':f.client.activate('A',{'kind':'next'})
    elif mutation=='request':f.client.rows[f.key]['request']['expiry']=.22
    elif mutation=='row_ack':f.client.rows[f.key]['ack']['status']='expired'
    elif mutation=='new_call':f.client.calls.append(copy.deepcopy(f.client.calls[0]))
    elif mutation=='owner':f.client.context['owner']='B'
    else:d._public_bytes+=' '
    with pytest.raises(ValueError):a.require_current(d)


@pytest.mark.parametrize('kind',['json_client','subclass','wrong_session','foreign_publication','physical_action'])
def test_collection_rejects_client_or_request_scope(native_stub,kind):
    f=native_stub
    if kind=='json_client':f.client={}
    elif kind=='subclass':
        class Other(a.history.fixture.LocalTransport):pass
        alternate=Other(f.session);alternate.__dict__.update(f.client.__dict__);f.client=alternate
    elif kind=='wrong_session':f.client.session=SimpleNamespace(physical_time=.11)
    elif kind=='foreign_publication':f.key='other-owner-id'
    else:f.client.rows[f.key]['kind']='route'
    assert collect(f)['status']=='unknown' and not f.reads


def test_new_local_revalidation_keeps_noop_distinct_from_route(native_stub,monkeypatch):
    f=native_stub;d=collect(f)
    from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as vocabulary
    monkeypatch.setattr(vocabulary,'actions',actions)
    result=a.revalidate_first_component(d,actions()[0])
    assert result['component']['kind']=='no_command_native_default' and result['component']['actual_next_unknown']
    assert result['native_request_submitted'] is False and result['dispatch_authorized'] is False
    result=a.revalidate_first_component(d,actions()[16])
    assert result['component']['next']==2 and result['component']['expected_generation']==1
    assert len(f.reads)==9


@pytest.mark.parametrize('kind',['capture_changed','wire_equal','committed','receiver_full'])
def test_current_action_guard_rejects_changed_live_state(native_stub,monkeypatch,kind):
    f=native_stub;d=collect(f)
    from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as vocabulary
    monkeypatch.setattr(vocabulary,'actions',actions)
    if kind=='capture_changed':f.view['trays'][0]['generation']=2
    elif kind=='wire_equal':f.view['trays'][0]['service_ready_at']=.12
    elif kind=='committed':f.view['trays'][0]['edge_to']=2
    else:f.view['node_contracts'][0]['occupancy']=1
    assert a.revalidate_first_component(d,actions()[16])['status']=='unknown'


def batch(values=None,unknown=()):
    values={} if values is None else values
    rows=[]
    for i,action in enumerate(actions()):
        completion={j:v for j,v in zip(p.JOBS,values.get(i,[20.]*5),strict=True)}
        rows.append({'candidate_index':i,'action':action,'status':'unknown_projection' if i in unknown else 'conditional_forecast',
            'completion':None if i in unknown else completion,'prediction':{'completion':completion}})
    result=p.CandidateBatch(p._TOKEN,{'rows':rows,'counts':{'logical_candidates':32},'provider_preseal_seconds':1.,
        'owner':'A','initial_public_sha256':'synthetic_only'},None)
    result._provider_elapsed=1.1;return result


def test_selector_can_cross_unprotected_internal_proposal():
    result=s.select(batch({0:[10.]*5,1:[11.,8.,10.,10.,10.],17:[9.,9.,10.,10.,10.]}),method='coordinate_strict',incumbent_index=0)
    assert result['selected_index']==17 and 1 in result['internal_unprotected_visited_indices']
    assert all(d<=0 for d in result['estimated_per_job_delta'].values())
    assert result['native_protection_certified'] is result['dispatch_authorized'] is False


@pytest.mark.parametrize('method',s.METHODS)
def test_every_method_pays_full32_even_when_querying_fewer(method):
    result=s.select(batch({0:[10.]*5}),method=method,incumbent_index=0)
    assert result['accounting']['provider_charged_candidate_denominator']==32
    assert result['accounting']['model_budget_saved_by_queries'] is False and len(result['candidate_rows'])==32


def test_all_unknown_incumbent_never_implies_safe():
    result=s.select(batch({17:[1.]*5},unknown=[0]),method='finite_MPC',incumbent_index=0)
    assert result['selected_index'] is None and result['full_reference_known'] is False
    assert 0 in result['unknown_forecast_indices']


def test_complete_family_required_for_reference_optimum():
    result=s.select(batch({0:[10.]*5,12:[9.]*5},unknown=[2]),method='finite_MPC',incumbent_index=0,restriction='fixed_initial')
    assert result['selected_index']==12 and result['reference_optimum_index'] is None
    assert len(result['allowed_candidate_indices'])==16 and result['full_reference_known'] is False


def test_later_default_reference_keeps_all_four_windows():
    result=s.select(batch({0:[10.]*5}),method='finite_MPC',incumbent_index=0,restriction='later_default')
    assert result['allowed_candidate_indices']==list(range(0,32,2)) and result['full_reference_known'] is True


def test_exact_per_job_guard_rejects_small_regression_even_total_improves():
    result=s.select(batch({0:[10.]*5,1:[10.000000000000002,1.,1.,1.,1.]}),method='finite_MPC',incumbent_index=0)
    assert result['selected_index']==0 and result['candidate_rows'][1]['estimated_not_worse'] is False


def test_ties_use_original_cartesian_index():
    result=s.select(batch({0:[10.]*5,7:[9.]*5,5:[9.]*5}),method='finite_MPC',incumbent_index=0)
    assert result['selected_index']==5


def test_no_cross_method_free_batch_reuse():
    value=batch({0:[10.]*5});s.select(value,method='incumbent',incumbent_index=0)
    with pytest.raises(ValueError,match='one_search'):s.select(value,method='finite_MPC',incumbent_index=0)


def test_audit_copy_mutation_cannot_modify_provider():
    value=batch({0:[10.]*5});copy_=value.audit_copy();copy_['rows'][0]['completion']['loaded']=999.
    result=s.select(value,method='incumbent',incumbent_index=0)
    assert result['selected_completion']['loaded']==10.


@pytest.mark.parametrize('budget',[31,33,True])
def test_candidate_budget_never_silently_changes(budget):
    with pytest.raises(ValueError):s.select(batch(),method='finite_MPC',incumbent_index=0,budget=budget)


@pytest.mark.parametrize('kind',['missing','bool','int','nan','unknown_info','status'])
def test_incomplete_or_untyped_prediction_is_unknown(kind):
    value={'status':'conditional_prediction','completion':{j:1. for j in p.JOBS},'unknown_information_phases':[]}
    if kind=='missing':value['completion'].pop('loaded')
    elif kind=='bool':value['completion']['loaded']=True
    elif kind=='int':value['completion']['loaded']=1
    elif kind=='nan':value['completion']['loaded']=float('nan')
    elif kind=='unknown_info':value['unknown_information_phases']=['B']
    else:value['status']='unknown_event_budget'
    assert p.known_completion(value) is None


def test_closed_five_endpoints_remain_conditional_estimates():
    value={'status':'conditional_prediction','completion':{j:1. for j in p.JOBS},'unknown_information_phases':[]}
    assert p.known_completion(value)==value['completion']


@pytest.mark.parametrize('bound',[.12,.119])
def test_same_observed_view_still_needs_strict_wire_deadline(native_stub,monkeypatch,bound):
    f=native_stub;f.view['trays'][0]['service_ready_at']=bound;d=collect(f)
    from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as vocabulary
    monkeypatch.setattr(vocabulary,'actions',actions)
    result=a.revalidate_first_component(d,actions()[16])
    assert result['status']=='unknown' and 'strict_actual_route_wire_window' in result['reason']


@pytest.mark.parametrize('postsave_failure',[None,'suffix_status','execution_row'])
def test_provider_runs_fixed16_factories_and_retains32_without_target(monkeypatch,postsave_failure):
    seen=[];decision=SimpleNamespace(audit_copy=lambda:{'owner':'A','public_sha256':'synthetic','at':.11})
    monkeypatch.setattr(p.origin,'require_current',lambda value:value)
    monkeypatch.setattr(p.origin,'supplied_snapshot',lambda value:seen.append(value) or 'initial_only')
    monkeypatch.setattr(p.future,'source_proof',lambda:{'synthetic_test':True})
    monkeypatch.setattr(p.future.core.lazy.original.physics.previous,'actions',actions)
    def execute(group,factory,save,*,model,future):
        assert factory(group['prefix_index'],group['representative_action'])=='initial_only'
        suffixes={}
        for i,choice in zip(group['candidate_indices'],domain.LATER,strict=True):
            value={'status':'conditional_prediction','completion':{j:float(i+1) for j in p.JOBS},'unknown_information_phases':[]}
            suffixes[choice]={'status':'returned','prediction':save(choice,value),'parent_and_unconsumed_sibling_isolated':True}
        rows={f'vector_{i:02d}':{'status':'unknown_prediction_returned_audit_pending'} for i in group['candidate_indices']}
        if group['prefix_index']==0 and postsave_failure=='suffix_status':suffixes['native_default']['status']='unknown_suffix_error'
        if group['prefix_index']==0 and postsave_failure=='execution_row':rows['vector_00']['status']='unknown_group_error'
        return {'context_constructions':1,'detail':{'prefix':{'status':'supported_known_B_cut',
            'complete_graph_only_future_action_changed':True,'three_mutable_graphs_disjoint':True,'parent_unconsumed':True},
            'suffixes':suffixes,'counts':{'initial_engines':1,'initial_advances':1,'prefix_same_resumes':1,'future_forks':2,'future_resumes':2}},
            'rows':rows}
    monkeypatch.setattr(p.evaluator,'execute_group',execute)
    value=p.evaluate_declared32(decision);data=value.audit_copy()
    assert len(seen)==16 and len(data['rows'])==32 and data['counts']['future_resumes']==32
    if postsave_failure is None:assert all(row['status']=='conditional_forecast' for row in data['rows'])
    else:
        assert data['rows'][0]['status']=='unknown_projection' and data['rows'][0]['completion'] is None
        assert data['rows'][0]['prediction']['completion'] is not None  # preserved, never promoted
        assert all(row['status']=='conditional_forecast' for row in data['rows'][1:])
    assert data['native_protection_certified'] is False and value._provider_elapsed>=data['provider_preseal_seconds']


def test_provider_stale_origin_keeps_all32_unknown_without_a_model(monkeypatch):
    monkeypatch.setattr(p.future.core.lazy.original.physics.previous,'actions',actions)
    def reject(value):raise ValueError('stale_origin')
    monkeypatch.setattr(p.origin,'require_current',reject)
    value=p.evaluate_declared32(object()).audit_copy()
    assert len(value['rows'])==32 and value['counts']['initial_engines']==0
    assert all(row['completion'] is None and row['status']=='unknown_origin_or_provider_failure' for row in value['rows'])
