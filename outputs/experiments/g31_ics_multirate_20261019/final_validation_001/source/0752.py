"""Synthetic sealing and query regressions; saved forecasts grant no authority."""
import copy
import ast
import hashlib
import inspect
import itertools
import textwrap
from types import MappingProxyType,SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_initial_candidate_provider as subject
from scripts.experiments.g31_ics_circulation import live_obligation_owned_initial_provider as owned
from scripts.experiments.g31_ics_circulation import live_obligation_same_information_search as search


def payload():
    fields=subject.domain.FIELDS
    actions=[dict(zip(fields,coordinates)) for coordinates in itertools.product(
        subject.domain.INITIAL,(.11,1.,2.,3.),subject.domain.RETURN,subject.domain.LATER)]
    shared={'completion':{job:20. for job in subject.JOBS},'events':[{'owners':['A','B']}]}
    return {'rows':[{'candidate_index':index,'action':action,'status':'conditional_forecast',
        'completion':shared['completion'],'prediction':shared} for index,action in enumerate(actions)],
        'groups':[{'candidate_indices':[0,1]}],'counts':{'logical_candidates':32,'future_resumes':32},
        'provider_preseal_seconds':1.,'owner':'A','initial_public_sha256':'synthetic_only'}


def batch(data=None,decision=None):
    result=subject.CandidateBatch(subject._TOKEN,payload() if data is None else data,decision)
    result._provider_elapsed=1.1
    return result


def test_32_queries_decode_and_hash_whole_batch_once_without_copying_whole_batch(monkeypatch):
    data=payload();raw=subject.encoding(data)
    original_loads=subject.json.loads;original_sha=subject.hashlib.sha256
    decodes=[];hashes=[]
    def loads(value,*args,**kwargs):
        if value==raw:decodes.append(value)
        return original_loads(value,*args,**kwargs)
    def sha(value,*args,**kwargs):
        if value==raw.encode():hashes.append(value)
        return original_sha(value,*args,**kwargs)
    monkeypatch.setattr(subject.json,'loads',loads)
    monkeypatch.setattr(subject.hashlib,'sha256',sha)
    value=batch(data);queries=value.claim('finite_MPC')
    original_copy=subject._copy_frozen;whole_copies=[]
    def copied(item):
        if item is value._data:whole_copies.append(item)
        return original_copy(item)
    monkeypatch.setattr(subject,'_copy_frozen',copied)
    assert queries.domain()==[row['action'] for row in data['rows']]
    assert [queries.query(index) for index in range(32)]==data['rows']
    counts=queries.accounting()
    assert counts['query_indices']==list(range(32)) and counts['queried_indices']==32
    assert counts['provider_charged_candidate_denominator']==32
    assert counts['model_budget_saved_by_queries'] is False
    assert len(decodes)==len(hashes)==1 and not whole_copies
    assert value._read()==data
    assert value.audit_copy()['rows']==data['rows']
    assert len(decodes)==len(hashes)==1 and len(whole_copies)==2


def test_inputs_queries_domain_accounting_and_audit_have_no_mutable_aliases():
    data=payload();expected=copy.deepcopy(data);value=batch(data);queries=value.claim('finite_MPC')
    data['rows'][0]['prediction']['events'][0]['owners'].clear()
    data['counts']['logical_candidates']=1
    row=queries.query(0)
    row['prediction']['events'][0]['owners'].append('intruder')
    row['completion']['loaded']=999.
    row['action']['initial_action']='changed'
    actions=queries.domain();actions[0]['return_delay']=99.
    counts=queries.accounting();counts['provider_counts']['future_resumes']=0
    counts['query_indices'].clear();queries.indices.clear()
    exported=value.audit_copy();exported['rows'][1]['prediction']['events'].clear()
    exported['groups'][0]['candidate_indices'].clear()
    assert queries.query(0)==expected['rows'][0]
    assert queries.query(1)==expected['rows'][1]
    assert value._read()==expected
    assert queries.indices==[0,1]
    assert queries.accounting()['provider_counts']==expected['counts']


def test_internal_candidate_graph_is_recursively_immutable():
    value=batch()
    def immutable(item):
        assert type(item) not in (dict,list,set)
        if type(item) is MappingProxyType:
            for child in item.values():immutable(child)
        elif type(item) is tuple:
            for child in item:immutable(child)
    immutable(value._data)
    with pytest.raises(TypeError):value._data['rows'][0]['completion']['loaded']=1.
    with pytest.raises(TypeError):value._data['rows'][0]['prediction']['events'][0]['owners'][0]='X'


@pytest.mark.parametrize('field',('_token','_bytes','_digest','_data','_decision','_sealed','_claimed'))
def test_sealed_batch_fields_cannot_be_replaced_or_deleted(field):
    value=batch()
    with pytest.raises(ValueError,match='batch_fields_sealed'):setattr(value,field,object())
    with pytest.raises(ValueError,match='batch_fields_sealed'):delattr(value,field)
    assert value.audit_copy()['rows']==payload()['rows']


@pytest.mark.parametrize('field',('_token','_bytes','_digest','_data','_decision'))
@pytest.mark.parametrize('access',('query','domain','accounting','audit','claim'))
def test_forced_sealed_field_replacement_is_detected_before_access(field,access):
    value=batch();queries=value.claim('finite_MPC')
    object.__setattr__(value,field,object())
    invoke={'query':lambda:queries.query(0),'domain':queries.domain,'accounting':queries.accounting,
        'audit':value.audit_copy,'claim':lambda:value.claim('incumbent')}[access]
    with pytest.raises(ValueError,match='batch_integrity'):invoke()


def test_replacing_bytes_and_matching_digest_cannot_rebind_sealed_rows():
    value=batch();replacement=subject.encoding(payload())+' '
    object.__setattr__(value,'_bytes',replacement)
    object.__setattr__(value,'_digest',hashlib.sha256(replacement.encode()).hexdigest())
    with pytest.raises(ValueError,match='batch_integrity'):value.audit_copy()


@pytest.mark.parametrize('field',('_token','_batch','method','_indices','indices'))
def test_query_handle_fields_are_sealed(field):
    queries=batch().claim('finite_MPC')
    with pytest.raises(ValueError,match='query_fields_sealed'):setattr(queries,field,object())
    with pytest.raises(ValueError,match='query_fields_sealed'):delattr(queries,field)


def test_queries_keep_one_claim_and_unique_logical_indices():
    value=batch();queries=value.claim('finite_MPC')
    for index in (0,0,1,1):queries.query(index)
    assert queries.indices==[0,1]
    with pytest.raises(ValueError,match='one_search_per_charged_batch'):value.claim('incumbent')
    with pytest.raises(ValueError,match='batch_fields_sealed'):value._provider_elapsed=2.
    for index in (True,-1,32,1.):
        with pytest.raises(ValueError,match='declared_candidate_index'):queries.query(index)
    assert queries.indices==[0,1]


@pytest.mark.parametrize('provider',(subject,owned))
def test_frozen_forecasts_do_not_cache_or_bypass_origin_freshness(monkeypatch,provider):
    decision=object();value=batch(decision=decision);checks=[]
    def current(actual):
        assert actual is decision
        checks.append(actual)
        if len(checks)>1:raise ValueError('stale_origin')
    monkeypatch.setattr(provider.origin,'require_current',current)
    assert provider.require_current_batch_origin(value) is decision
    with pytest.raises(ValueError,match='stale_origin'):provider.require_current_batch_origin(value)
    assert len(checks)==2


def test_offline_batch_and_audit_copy_never_authorize_native_execution():
    value=batch();exported=value.audit_copy()
    assert exported['native_protection_certified'] is exported['dispatch_authorized'] is False
    assert exported['saved_copy_has_authority'] is False
    with pytest.raises(ValueError):subject.require_current_batch_origin(value)
    with pytest.raises(ValueError):subject.require_current_batch_origin(exported)
    with pytest.raises(ValueError,match='provider_factory_required'):
        subject.CandidateBatch(object(),payload(),None)


def test_selector_retains_unknowns_and_exact_per_job_protection():
    data=payload()
    data['rows'][2].update(status='unknown_projection',completion=None)
    data['rows'][3]['completion']={job:1. for job in subject.JOBS}
    data['rows'][3]['completion']['loaded']=20.000000000000004
    result=search.select(batch(data),method='finite_MPC',incumbent_index=4)
    assert result['selected_index']==0 and result['unknown_forecast_indices']==[2]
    assert result['candidate_rows'][3]['estimated_not_worse'] is False
    assert result['full_reference_known'] is False
    assert result['accounting']['queried_indices']==32
    assert result['dispatch_authorized'] is result['native_protection_certified'] is False


def test_explicit_bound_group_preserves_all_original_group_statements():
    original=ast.parse(textwrap.dedent(inspect.getsource(owned.execution.execute_group))).body[0]
    candidate=ast.parse(textwrap.dedent(inspect.getsource(owned.execution.execute_bound_group))).body[0]
    original.body=original.body[1:]
    candidate.body=[statement for statement in candidate.body[2:]
        if not isinstance(statement,ast.Try) and not (isinstance(statement,ast.Assign)
            and ast.unparse(statement.targets[0])=='binding_error')]
    candidate.body[-1].value.keys.pop();candidate.body[-1].value.values.pop()
    class OriginalName(ast.NodeTransformer):
        def visit_Name(self,node):
            if node.id=='actual_future':node.id='future'
            return node
    candidate=OriginalName().visit(candidate)
    assert ast.dump(ast.Module(body=original.body,type_ignores=[]),include_attributes=False)==ast.dump(
        ast.Module(body=candidate.body,type_ignores=[]),include_attributes=False)


@pytest.mark.parametrize('value',(None,{},SimpleNamespace(facade=object())))
def test_bound_group_rejects_plain_facade_or_saved_handle(value):
    with pytest.raises(ValueError,match='exact_v3_request_binding'):
        owned.execution.execute_bound_group(value,{},object())


def test_bound_group_uses_the_explicit_facade_and_retains_independent_saver(monkeypatch):
    evaluator=owned.execution;events=[]
    request=SimpleNamespace(check_integration=lambda:events.append('checked'))
    facade=SimpleNamespace(core=evaluator.future.core)
    def checked(actual):
        assert actual is request
        request.check_integration()
        return facade
    monkeypatch.setattr(evaluator,'_bound_future',checked)
    group=subject.domain.partition(evaluator.future.core.lazy.original.physics.previous.actions())['groups'][0]
    context=object()
    def execute(actual,make,save,*,model,future):
        assert actual is group and make(0,actual['representative_action']) is context
        assert model is facade.core and future is facade
        prediction={'events':[1.,-0.]}
        save('native_default',prediction);prediction['events'].append(99.)
        return {'rows':{f'vector_{index:02d}':{} for index in actual['candidate_indices']}}
    monkeypatch.setattr(evaluator,'_group',execute)
    result=evaluator.execute_bound_group(request,group,context)
    assert events==['checked','checked']
    assert result['predictions']['native_default']=={'events':[1.,-0.]}
    assert result['native_authority'] is False


def test_bound_group_retains_first_failure_and_saved_prediction_when_postcheck_fails(monkeypatch):
    evaluator=owned.execution
    def invalidated():raise ValueError('closed_or_invalidated_future_request')
    request=SimpleNamespace(check_integration=invalidated)
    monkeypatch.setattr(evaluator,'_bound_future',lambda actual:evaluator.future)
    group=subject.domain.partition(evaluator.future.core.lazy.original.physics.previous.actions())['groups'][0]
    def execute(actual,make,save,*,model,future):
        save('native_default',{'partial':'retained'})
        return {'error':'first_dependency_label','rows':{f'vector_{index:02d}':{} for index in actual['candidate_indices']}}
    monkeypatch.setattr(evaluator,'_group',execute)
    result=evaluator.execute_bound_group(request,group,object())
    assert result['detail']['error']=='first_dependency_label'
    assert result['predictions']=={'native_default':{'partial':'retained'}}
    assert 'closed_or_invalidated_future_request' in result['binding_error']
    assert result['native_authority'] is False


def test_copy_metadata_preparation_only_materializes_three_canonical_empty_lists(monkeypatch):
    before={cls:dict(vars(cls)) for cls in owned._COPY_CLASSES}
    for cls in owned._COPY_CLASSES:
        if '__slotnames__' in vars(cls):monkeypatch.delattr(cls,'__slotnames__')
    result=owned._prepare_copy_metadata()
    assert len(result['classes'])==3 and all(row['materialized'] for row in result['classes'])
    for cls in owned._COPY_CLASSES:
        assert type(vars(cls)['__slotnames__']) is list and vars(cls)['__slotnames__']==[]
        assert {name:id(value) for name,value in vars(cls).items() if name!='__slotnames__'}=={
            name:id(value) for name,value in before[cls].items() if name!='__slotnames__'}
        cache=vars(cls)['__slotnames__'];keys=tuple(vars(cls))
        copied=copy.deepcopy(object.__new__(cls))
        assert type(copied) is cls and vars(cls)['__slotnames__'] is cache and tuple(vars(cls))==keys
    assert not any(row['materialized'] for row in owned._prepare_copy_metadata()['classes'])


@pytest.mark.parametrize('value',(None,(),['invented_field'],{'invented_field':True}))
def test_copy_metadata_preparation_rejects_noncanonical_existing_cache(monkeypatch,value):
    monkeypatch.setattr(owned._COPY_CLASSES[0],'__slotnames__',value,raising=False)
    with pytest.raises(ValueError,match='unexpected_existing_copy_slotnames'):
        owned._prepare_copy_metadata()


def test_copy_metadata_preparation_rejects_replaced_standard_library_function(monkeypatch):
    monkeypatch.setattr(owned.copyreg,'_slotnames',lambda cls:[])
    with pytest.raises(ValueError,match='canonical_copy_slotnames_function'):
        owned._prepare_copy_metadata()


@pytest.mark.parametrize('change',('replace','append','class_field'))
def test_materialized_copy_metadata_remains_fully_sealed(monkeypatch,change):
    owned._prepare_copy_metadata();cls=owned._COPY_CLASSES[0]
    seal=owned.binding.binding.DependencySeal({'projection_class':vars(cls)},project_prefixes=owned.binding.original.PROJECT)
    if change=='replace':monkeypatch.setattr(cls,'__slotnames__',[])
    elif change=='class_field':monkeypatch.setattr(cls,'unexpected_runtime_field',1,raising=False)
    else:vars(cls)['__slotnames__'].append('invented_field')
    try:
        with pytest.raises(ValueError,match='dependency_changed'):
            seal.check()
    finally:
        if change=='append':vars(cls)['__slotnames__'].clear()


def bound_provider_fixture(monkeypatch,failure=None):
    events=[];contexts=[];request=SimpleNamespace(uses=0)
    decision=SimpleNamespace(audit_copy=lambda:{'owner':'A','public_sha256':'synthetic','at':.11})
    def current(actual):
        assert actual is decision
        events.append('fresh')
        if failure=='freshness' and events.count('fresh')==2:raise ValueError('changed_native_admission')
    def context(actual):
        assert actual is decision
        value=object();contexts.append(value)
        return value
    def bind():
        events.append('cold')
        if failure=='cold':raise ValueError('cold_failure')
        return request
    def proof(actual):
        assert actual is request
        events.append('warm_setup');request.uses+=1
        if failure in ('setup','setup_and_close'):raise ValueError('setup_failure')
    def description():
        events.append('description')
        if failure=='description':raise ValueError('description_failure')
        return {'proof_binding':{'proof_uses':request.uses-(1 if failure=='missing_use' else 0)}}
    def close():
        events.append('close')
        if failure in ('close','setup_and_close'):raise ValueError('close_failure')
    request.description=description;request.close=close
    def execute(actual,group,snapshot):
        assert actual is request and snapshot is contexts[-1]
        events.append('group');request.uses+=4
        predictions={choice:{'status':'conditional_prediction','completion':{job:20. for job in subject.JOBS},
            'unknown_information_phases':[]} for choice in subject.domain.LATER}
        inner={'prefix':{'status':'supported_known_B_cut','isolation_basis':owned.execution.OWNERSHIP,
            'diagnostic_graphs_computed':False,'parent_unconsumed':True},
            'suffixes':{choice:{'status':'returned','isolation_basis':owned.execution.OWNERSHIP}
                for choice in subject.domain.LATER},
            'counts':{'initial_engines':1,'initial_advances':1,'prefix_same_resumes':1,
                'future_forks':2,'future_resumes':2}}
        return {'predictions':predictions,'binding_error':'first_group_binding_failure' if failure=='group_binding' else None,
            'detail':{'context_constructions':1,'detail':inner,
            'rows':{f'vector_{index:02d}':{'status':'unknown_prediction_returned_audit_pending'}
                for index in group['candidate_indices']}}}
    monkeypatch.setattr(owned.origin,'require_current',current)
    monkeypatch.setattr(owned.origin,'supplied_snapshot',context)
    monkeypatch.setattr(owned.binding,'bind_request',bind)
    monkeypatch.setattr(owned,'source_proof',proof)
    monkeypatch.setattr(owned.execution,'execute_bound_group',execute)
    return decision,request,events,contexts


def test_bound_provider_one_cold_65_checked_uses_16_fresh_contexts_and_final_close(monkeypatch):
    decision,request,events,contexts=bound_provider_fixture(monkeypatch)
    result=owned.evaluate_declared32(decision).audit_copy()
    assert result['status']=='conditional_forecasts_complete'
    assert events.count('cold')==events.count('warm_setup')==events.count('close')==1
    assert events.count('group')==len(contexts)==len({id(context) for context in contexts})==16
    assert events.count('fresh')==2 and request.uses==65 and events[-1]=='close'
    assert result['source_binding']['status']=='closed_complete65'
    assert result['source_binding']['close_completed'] is True
    assert result['counts']['future_forks']==result['counts']['future_resumes']==32
    assert result['dispatch_authorized'] is result['native_protection_certified'] is False


@pytest.mark.parametrize('failure',('cold','setup','close','description','missing_use','freshness','setup_and_close','group_binding'))
def test_bound_provider_failure_retains_full_unknown_denominator_and_primary_cause(monkeypatch,failure):
    decision,request,events,contexts=bound_provider_fixture(monkeypatch,failure)
    result=owned.evaluate_declared32(decision).audit_copy()
    assert result['status']=='unknown_initial_origin_or_provider' and len(result['rows'])==32
    assert all(row['completion'] is None and row['status']=='unknown_origin_or_provider_failure'
        for row in result['rows'])
    assert events.count('cold')==1 and events.count('close')==(0 if failure=='cold' else 1)
    if failure not in ('cold','setup','setup_and_close'):
        assert len(contexts)==16 and all(row['prediction']['completion'] for row in result['rows'])
    if failure=='setup_and_close':
        assert result['error']=='setup_failure'
        assert 'close_failure' in result['source_binding']['close_error']
    if failure=='group_binding':
        assert result['error']=='first_group_binding_failure'
        assert all(group['binding_error']=='first_group_binding_failure' for group in result['groups'])
    assert result['dispatch_authorized'] is result['native_protection_certified'] is False
