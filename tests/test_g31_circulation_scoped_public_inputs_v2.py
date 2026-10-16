"""Private data-read boundaries; no predictor/model/native executions."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import public_live_obligation_scoped_inputs_v2 as c

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_unloading_native_prepare_001/no_overlap/vector_00.json.gz'
RAW_SHA='c493cb3045ff8c5b3160e2693203bce808991a49312893fcb9f827b88fffe346'


def exact(a,b):
    if type(a) is not type(b):return False
    if type(a) is dict:return list(a)==list(b) and all(exact(a[k],b[k]) for k in a)
    if type(a) in (tuple,list):return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    if type(a) is float:return a.hex()==b.hex()
    assert type(a) in (str,int,bool,type(None))
    return a==b


def mutable_ids(value):
    result=set();pending=[value]
    while pending:
        item=pending.pop()
        if type(item) not in (dict,list,tuple):continue
        if type(item) is not tuple:result.add(id(item))
        pending.extend(item.values() if type(item) is dict else item)
    return result


def error(function,*args):
    try:function(*args)
    except Exception as exc:return type(exc),exc.args
    pytest.fail('expected failure')


def test_source_proof_and_unchanged_model_context_identity():
    s=c.PublicInputScope();p=s.source_proof()
    assert len(p['unchanged_functions'])>30 and p['inverse_AST_exact']
    assert p['borrowed_values_only_consumed_by_original_readonly_digest']
    assert s.context.SuppliedContext is c.prior.context.SuppliedContext
    assert s.predict.__code__ is c.prior.lazy.predict.__code__
    assert s.Projection.activate is c.prior.lazy.Projection.activate
    assert s.Projection.run is c.prior.lazy.Projection.run


def test_generic_inputs_still_three_case_full_fresh_deepcopy():
    s=c.PublicInputScope();a=s.inputs();b=s.inputs()
    assert exact(a,b) and tuple(a)==c.prior.construction.construction.CASE_IDS
    assert not mutable_ids(a)&mutable_ids(b)
    assert not mutable_ids(a)&mutable_ids(s._inputs)
    a['no_overlap']['jobs'].clear()
    assert exact(s.inputs(),b) and s.input_reads==3


@pytest.mark.parametrize('case',c.prior.construction.construction.CASE_IDS)
def test_public_case_exact_fresh_and_copies_only_requested_case(monkeypatch,case):
    s=c.PublicInputScope();expected=c.prior.initial.public_input(case);calls=[]
    original=copy.deepcopy
    def duplicate(value):calls.append(value);return original(value)
    monkeypatch.setattr(c,'copy',SimpleNamespace(deepcopy=duplicate))
    first=s.initial.public_input(case);second=s.initial.public_input(case)
    assert exact(first,expected) and exact(second,expected)
    assert calls==[s._inputs[case],s._inputs[case]] and all(v is s._inputs[case] for v in calls)
    assert not mutable_ids(first)&mutable_ids(second)
    assert not mutable_ids(first)&mutable_ids(s._inputs)
    first['jobs'][0]['load_seconds']=999.
    assert exact(second,expected) and exact(s.initial.public_input(case),expected)
    assert s.input_reads==0 and s.public_case_reads==3


@pytest.mark.parametrize('case',['missing',None,0,[],{}])
def test_original_case_validation_and_error_preserved(case):
    s=c.PublicInputScope()
    assert error(s.initial.public_input,case)==error(c.prior.initial.public_input,case)
    assert s.public_case_reads==s.input_reads==0


def test_scope_calls_original_builder_once_each(monkeypatch):
    original=c.prior.construction.inputs;calls=[]
    def counted():calls.append(1);return original()
    monkeypatch.setattr(c.prior.construction,'inputs',counted)
    a=c.PublicInputScope();a.initial.public_input('mechanism');a.inputs()
    b=c.PublicInputScope();b.initial.public_input('no_overlap')
    assert len(calls)==2


def test_private_tables_and_returned_cases_cross_scope_isolated():
    a,b=c.PublicInputScope(),c.PublicInputScope();before=b.inputs()
    assert not mutable_ids(a._inputs)&mutable_ids(b._inputs)
    a._inputs['mechanism']['jobs'].clear()
    assert exact(before,b.inputs())


def test_identify_borrows_only_for_readonly_digest_and_returns_name():
    s=c.PublicInputScope();before=copy.deepcopy(s._inputs)
    for name in c.prior.construction.construction.CASE_IDS:
        data=s.initial.public_input(name)
        returned=s.construction.identify(data)
        assert type(returned) is str and returned==c.prior.construction.identify(data)==name
    assert s.identify_table_reads==3 and s.input_reads==0 and exact(before,s._inputs)
    assert s.construction.identify.__code__ is c._IDENTIFY.__code__
    assert s.construction.initial_facts.__globals__['identify'] is s.construction.identify


@pytest.mark.parametrize('defect',['duration','edge','job_missing'])
def test_all_identity_comparisons_still_reject_changed_input(defect):
    s=c.PublicInputScope();data=s.initial.public_input('mechanism')
    if defect=='duration':data['jobs'][0]['load_seconds']+=1
    elif defect=='edge':data['edge_records'][0][2]+=1
    else:data['jobs'].pop()
    assert error(s.construction.identify,data)==error(c.prior.construction.identify,data)


@pytest.mark.parametrize('case',c.prior.construction.construction.CASE_IDS)
def test_complete_original_guard_and_public_contract_outputs(case):
    s=c.PublicInputScope();data=s.initial.public_input(case)
    jobs=s.construction.initial_facts(data)[0]
    for later in (False,True):
        expected=c.prior.initial.supported_contract(later=later,case=case)
        assert exact(s.initial.supported_contract(later=later,case=case),expected)
        assert s.initial.identify_public_case(expected,jobs,later=later)==case


def test_all_private_aliases_include_historical_helper():
    s=c.PublicInputScope()
    assert s.lifecycle.public_input is s.initial.public_input is s.v2.public_input
    assert s.v2._private['public_input'] is s.initial.public_input
    assert s.lifecycle.identify_public_case is s.initial.identify_public_case
    assert s.historical.old.old is s.initial is s.history.base
    assert s.historical.validate_collected_endpoints.__globals__['history'] is s.history
    assert s.history.derive_goal_service_bounds.__globals__['base'] is s.initial
    assert s.context.later_context.__globals__['later'] is s.historical
    assert s.context.revalidate.__globals__['initial_context'] is s.context.initial_context
    assert s.context.revalidate.__globals__['later_context'] is s.context.later_context
    assert s.Projection.collect.__globals__['guard'] is s.historical


@pytest.mark.parametrize('alias',['history_base','lifecycle_case','v2_private_case','identify_inputs',
    'copy_case','context_initial'])
def test_source_proof_rejects_broken_private_alias(alias):
    s=c.PublicInputScope()
    if alias=='history_base':s.history.base=c.prior.initial
    elif alias=='lifecycle_case':s.lifecycle.public_input=c.prior.initial.public_input
    elif alias=='v2_private_case':s.v2._private['public_input']=c.prior.initial.public_input
    elif alias=='identify_inputs':s._identify_namespace['inputs']=s.inputs
    elif alias=='copy_case':s._public_case_namespace['_copy_public_case']=s.inputs
    else:s.context.initial=c.prior.initial
    with pytest.raises(ValueError):s.source_proof()


def test_no_old_global_mutation():
    modules=(c.prior.construction,c.prior.initial,c.prior.lifecycle,c.prior.historical,c._HISTORY,c.prior.context)
    before=[dict(vars(module)) for module in modules]
    s=c.PublicInputScope();s.source_proof();s.construction.identify(s.initial.public_input('mechanism'))
    assert all(set(vars(module))==set(saved) and all(vars(module)[key] is value for key,value in saved.items())
        for module,saved in zip(modules,before))


def test_copy_failure_is_not_retried_or_misreported(monkeypatch):
    s=c.PublicInputScope();calls=[];failure=MemoryError('controlled allocation failure')
    def fail(value):calls.append(value);raise failure
    monkeypatch.setattr(c,'copy',SimpleNamespace(deepcopy=fail))
    with pytest.raises(MemoryError) as caught:s.initial.public_input('mechanism')
    assert caught.value is failure and len(calls)==1 and calls[0] is s._inputs['mechanism']


def test_no_prediction_for_invalid_context():
    s=c.PublicInputScope()
    assert exact(s.predict(object(),{}),c.prior.lazy.predict(object(),{}))


@pytest.fixture(scope='module')
def saved_arguments():
    compressed=RAW.read_bytes();assert hashlib.sha256(compressed).hexdigest()==RAW_SHA
    raw=json.loads(gzip.decompress(compressed))
    row=raw['collection_attempts']['B'][-1];ep=copy.deepcopy(row['information']['raw_endpoints']);pending=row['collection']
    # Only the actual deciding owner's immutable call prefix and endpoints are
    # passed. No final result/outcome or source branch key enters the guard.
    return dict(**ep,retained=raw['retained_ledgers']['B'],
        own_calls=[call for call in raw['calls'][:row['predecision_call_prefix_count']] if call['request']['owner_id']=='B'],
        phase=row['phase'],own_request_id=pending['request_id'],peer_message_id=pending['peer_message'],
        collection_started_at=pending['at'],policy_quiet_since=pending['policy_quiet_since'])


def test_saved_real_historical_fallback_retains_all_output_without_reconstruction(saved_arguments,monkeypatch):
    args=copy.deepcopy(saved_arguments);before=copy.deepcopy(args)
    reference=c.prior.context.later_context(**args)
    assert type(reference) is c.prior.context.SuppliedContext
    s=c.PublicInputScope()
    def fail():pytest.fail('historical path escaped scope to original fixed constructor')
    monkeypatch.setattr(c.prior.construction,'inputs',fail)
    current=s.context.later_context(**args)
    assert type(current) is c.prior.context.SuppliedContext
    assert current._payload==reference._payload and current._digest==reference._digest
    result=json.loads(current._payload)['validated']
    assert result['bundle']['derived_goal_service_bounds']
    assert result['historical_service_scope']=='conditional_supplied_data_only_no_new_native_or_policy_execution'
    assert exact(args,before) and s.public_case_reads>0 and s.identify_table_reads>0


@pytest.mark.parametrize('defect',['owner','history','request','bound','pending'])
def test_saved_historical_and_current_guards_reject_same_defects(saved_arguments,defect):
    args=copy.deepcopy(saved_arguments)
    if defect=='owner':args['view']['owner_id']='A'
    elif defect=='history':args['view']['client_commands']=[]
    elif defect=='request':args['own_calls']=[]
    elif defect=='bound':args['policy_quiet_since']=args['view']['now']+1
    else:args['own_calls'].append({'request':{'owner_id':'A'}})
    previous=c.prior.context.later_context(**args)
    current=c.PublicInputScope().context.later_context(**args)
    assert type(previous) is dict and previous['status']=='unknown'
    assert exact(current,previous)


def test_source_scope_limits_explicit():
    p=c.PublicInputScope().source_proof()
    assert not p['cached_observation_or_result_or_validation'] and not p['global_cache']
    assert not p['initial_context_caller_optimization_included']
    assert not p['removed_allocation_failure_timing_equivalence']
    assert not p['per_sample_cycle_cleanup_certified'] and not p['native_authority']
