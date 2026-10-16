"""Synthetic ownership/guard parity; no real model, native or saved roots.

The original revalidate bytecode is executed with explicit fake initial/later
guard providers. Those fakes prove call topology and fresh-output ownership;
they are not endpoint acceptance or native evidence.
"""
import copy
import hashlib
import json
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import public_live_obligation_owned_bundle as m


def exact(value):
    if type(value) is dict: return ('dict', tuple((exact(k),exact(v)) for k,v in value.items()))
    if type(value) is list: return ('list', tuple(exact(v) for v in value))
    if type(value) is float: return ('float', value.hex())
    return (type(value).__name__, value)


def containers(value):
    result = set()
    if type(value) in (dict,list):
        result.add(id(value))
        for child in (value.values() if type(value) is dict else value): result.update(containers(child))
    return result


def bundle():
    return {'jobs': [{'id':'j','deadline':12.0,'flag':True}],
        'trays': {'P': {'load_complete_at':1.25,'nested':[1,-0.0]}},
        'resources': {'3': {'occupancy':1}, '8': {'occupancy':0}},
        'contract': {'a':[1,1.0,-0.0,False]}, 'now':0.11}


def wire(*, phase='initial', status='conditional_validated_data', mode='valid', copy_failure=None):
    payload = {'phase':phase, 'evidence':{'marker':'supplied'},
        'validated':{'status':status, 'bundle':bundle()}}
    supplied = object.__new__(m._SUPPLIED)
    supplied._payload = json.dumps(payload, separators=(',',':'),allow_nan=False)
    supplied._digest = hashlib.sha256(supplied._payload.encode()).hexdigest()
    calls=[]; copies=[]; protocol={'wire':0.08,'routes':[1,2]}
    def rebuild(**evidence):
        calls.append((phase,exact(evidence)))
        if mode == 'raise': raise ValueError('synthetic guard rejected')
        if mode == 'unknown': return {'status':'unknown'}
        rebuilt = object.__new__(m._SUPPLIED)
        rebuilt._payload = supplied._payload + (' ' if mode == 'changed' else '')
        rebuilt._digest = supplied._digest
        return rebuilt
    def counted_copy(value):
        label = 'validated' if type(value) is dict and 'status' in value else 'bundle' if type(value) is dict and 'jobs' in value else 'protocol'
        copies.append(label)
        if label == copy_failure: raise MemoryError('synthetic ' + label)
        return copy.deepcopy(value)
    namespace = {**m._GLOBALS, 'initial_context':rebuild, 'later_context':rebuild,
        'copy':SimpleNamespace(deepcopy=counted_copy),
        'initial':SimpleNamespace(construction=SimpleNamespace(PROTOCOL=protocol))}
    revalidate=FunctionType(m._REVALIDATE_CODE,namespace,m._REVALIDATE.__name__,m._REVALIDATE.__defaults__,m._REVALIDATE.__closure__)
    revalidate.__kwdefaults__=m._REVALIDATE.__kwdefaults__
    namespace['revalidate']=revalidate
    reference=FunctionType(m._PROJECTION_CODE,namespace,m._PROJECTION.__name__,m._PROJECTION.__defaults__,m._PROJECTION.__closure__)
    reference.__kwdefaults__=m._PROJECTION.__kwdefaults__
    namespace['initial_projection_bundle']=reference
    candidate=m._private_projection(reference)
    return supplied,reference,candidate,calls,copies,protocol,namespace


def test_static_source_proof_retains_full_revalidation():
    proof=m.source_proof()
    assert proof['inverse_AST_exact'] and proof['revalidate_full_guards_and_deepcopy_return_retained']
    assert proof['removed_copy_count_per_projection_bundle_call']==1
    assert not proof['allocation_failure_timing_equivalent']
    assert not proof['native_authority'] and not proof['complete_request100ms_certified']


def test_actual_scope_chain_retains_guards_and_changes_only_projection_facade():
    # Fixed public constructors and source proof only; predict is never called.
    scope=m.PublicInputScope(); proof=scope.source_proof()
    assert proof['actual_projection_binding_checked']
    assert scope.context.revalidate is scope._owned_original_context.revalidate
    assert scope.context.initial_context is scope._owned_original_context.initial_context
    assert scope.context.later_context is scope._owned_original_context.later_context
    assert scope.predict.__globals__['context'] is scope.context
    assert scope._context_namespace['initial_projection_bundle'].__code__ is m._PROJECTION_CODE
    assert m._CONTEXT.initial_projection_bundle is m._PROJECTION


def test_original_revalidate_and_complete_typed_output_parity():
    supplied,reference,candidate,calls,copies,protocol,namespace=wire()
    left=reference(supplied); reference_copies=list(copies); copies.clear()
    right=candidate(supplied)
    assert exact(left)==exact(right)
    assert reference_copies==['validated','bundle','protocol']
    assert copies==['validated','protocol']
    assert len(calls)==2 and calls[0]==calls[1]
    assert not containers(left)&containers(right)
    assert not containers(left)&containers(protocol) and not containers(right)&containers(protocol)
    assert tuple(right['resources'])==(3,8)
    assert right['trays']['P']['load_end']==1.25
    assert right['contract']['a'][2].hex()=='-0x0.0p+0'
    assert not right['online_information_delivered']


def test_every_call_revalidates_and_mutations_cannot_reach_next_result_or_context():
    supplied,reference,candidate,calls,copies,protocol,namespace=wire()
    before=(supplied._payload,supplied._digest,copy.deepcopy(protocol))
    first=candidate(supplied); second=candidate(supplied)
    assert len(calls)==2 and not containers(first)&containers(second)
    first['jobs'][0]['id']='changed'; first['resources'][3]['occupancy']=100
    first['trays']['P']['nested'].append('changed'); first['protocol']['routes'].clear()
    third=candidate(supplied)
    assert exact(second)==exact(third) and len(calls)==3
    assert before==(supplied._payload,supplied._digest,protocol)


@pytest.mark.parametrize('phase', ['initial','first_return','first_reuse_route'])
def test_all_rebuild_branches_execute_original_code(phase):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire(phase=phase)
    assert exact(reference(supplied))==exact(candidate(supplied))
    assert len(calls)==2 and all(row[0]==phase for row in calls)


@pytest.mark.parametrize('mode', ['raise','unknown','changed'])
def test_rebuild_failure_and_original_unknown_result(mode):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire(mode=mode)
    assert exact(reference(supplied))==exact(candidate(supplied))
    assert len(calls)==2 and copies==[]
    assert candidate(supplied)['status']=='unknown'


@pytest.mark.parametrize('defect', ['wrong_type','changed_digest','invalid_json','missing_validated'])
def test_original_integrity_failure_order_no_guard_bypass(defect):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire()
    if defect=='wrong_type': supplied={}
    elif defect=='changed_digest': supplied._digest='bad'
    else:
        supplied._payload='{' if defect=='invalid_json' else json.dumps({'phase':'initial','evidence':{'marker':'supplied'}})
        supplied._digest=hashlib.sha256(supplied._payload.encode()).hexdigest()
    assert exact(reference(supplied))==exact(candidate(supplied))
    assert copies==[]
    assert len(calls)==(2 if defect=='missing_validated' else 0)


@pytest.mark.parametrize('status', ['unknown','conditional_validated_later_v3_data',None])
def test_noninitial_result_stays_unknown_without_bundle_access(status):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire(status=status)
    assert exact(reference(supplied))==exact(candidate(supplied))
    assert copies==['validated','validated'] and len(calls)==2


@pytest.mark.parametrize('stage',['validated','protocol'])
def test_retained_copy_allocation_failure_propagates_without_retry(stage):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire(copy_failure=stage)
    for function in (reference,candidate):
        with pytest.raises(MemoryError,match='synthetic '+stage): function(supplied)
    assert len(calls)==2


def test_removed_allocation_error_is_explicit_scope_limitation():
    supplied,reference,candidate,calls,copies,protocol,namespace=wire(copy_failure='bundle')
    with pytest.raises(MemoryError,match='synthetic bundle'): reference(supplied)
    assert candidate(supplied)['jobs'][0]['id']=='j'
    assert not m.source_proof()['allocation_failure_timing_equivalent']


@pytest.mark.parametrize('defect',['revalidate_code','namespace_lost','wrong_context_type'])
def test_private_binding_rejects_unproved_ownership(defect):
    supplied,reference,candidate,calls,copies,protocol,namespace=wire()
    if defect=='revalidate_code': namespace['revalidate']=lambda value: {'status':'conditional_validated_data','bundle':bundle()}
    elif defect=='namespace_lost': namespace.pop('PHYSICAL_KINDS')
    else: namespace['SuppliedContext']=object
    with pytest.raises(ValueError,match='complete_scope_context_namespace'): m._private_projection(reference)


def test_unmodified_code_alone_with_foreign_namespace_is_not_ownership_proof():
    supplied,reference,candidate,calls,copies,protocol,namespace=wire()
    namespace['revalidate']=FunctionType(m._REVALIDATE_CODE,dict(namespace))
    with pytest.raises(ValueError,match='complete_scope_context_namespace'): m._private_projection(reference)


def test_complete_original_build_runs_two_owners_and_same_scope_predict(monkeypatch):
    calls=[]; scopes=[]
    class Supplied:
        def __init__(self,owner): self.owner=owner
    class Scope:
        def __init__(self):
            calls.append('scope'); scopes.append(self)
            def initial_context(**args): calls.append(('initial',args['owner'])); return Supplied(args['owner'])
            def projection(value): calls.append(('projection',value.owner)); return bundle()
            self.context=SimpleNamespace(initial_context=initial_context,initial_projection_bundle=projection,
                SuppliedContext=Supplied,encoded=lambda value:json.dumps(value))
        def predict(self,supplied,action): calls.append(('predict',supplied.owner)); return copy.deepcopy(action)
    monkeypatch.setattr(m,'PublicInputScope',Scope)
    value={'initial_owners':{'A':{'owner':'A'},'B':{'owner':'B'}},'action':{'choice':2}}
    assert m.predict(value)=={'choice':2}
    assert calls==['scope',('initial','A'),('initial','B'),('projection','A'),('projection','B'),('predict','A')]
    m.predict(value); assert len(scopes)==2 and scopes[0] is not scopes[1]


def test_source_proof_rejects_changed_original_context_function(monkeypatch):
    monkeypatch.setattr(m,'_REVALIDATE_CODE',(lambda value:value).__code__)
    with pytest.raises(ValueError,match='original_context_functions_changed'): m.source_proof()
