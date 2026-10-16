import copy
import sys
from types import FunctionType
import pytest

from scripts.experiments.g31_ics_circulation import public_live_obligation_scoped_inputs as candidate
from scripts.experiments.g31_ics_circulation.profile_live_lazy_six import exact


def test_public_constructor_called_once_each_scope_and_not_at_import(monkeypatch):
    calls=[]; original=candidate.construction.inputs
    def counted(): calls.append(1); return original()
    monkeypatch.setattr(candidate.construction, 'inputs', counted)
    a=candidate.PublicInputScope(); assert len(calls)==1
    a.inputs(); a.inputs(); assert len(calls)==1 and a.input_reads==2
    b=candidate.PublicInputScope(); b.inputs(); assert len(calls)==2 and b.input_reads==1


def test_all_three_public_inputs_exact_with_independent_deepcopy_returns():
    expected=candidate.construction.inputs(); scope=candidate.PublicInputScope()
    first,second=scope.inputs(),scope.inputs()
    assert exact(first,expected) and exact(second,expected)
    assert first is not second and first['mechanism']['jobs'] is not second['mechanism']['jobs']
    first['mechanism']['jobs'][0]['load_seconds']=999
    first['no_overlap']['node_records'][0][5].append(999)
    assert exact(second,expected) and exact(scope.inputs(),expected)


def test_separate_scope_does_not_share_public_mutable_values():
    a,b=candidate.PublicInputScope(),candidate.PublicInputScope()
    before=b.inputs(); a._inputs['mechanism']['jobs'].clear()
    assert exact(before,b.inputs())


def test_all_guard_code_full_globals_and_context_identity_are_preserved():
    scope=candidate.PublicInputScope(); proof=scope.source_proof()
    assert len(proof['unchanged_functions'])>30
    assert scope.context.SuppliedContext is candidate.context.SuppliedContext
    for name in ('validate_later_pair','validate_collected_endpoints'):
        assert getattr(scope.v2,name).__code__ is getattr(candidate.v2,name).__code__
    assert not proof['global_cache'] and not proof['saved_prediction_or_future_observation_cache']


def test_original_module_namespaces_and_model_mro_remain_untouched():
    old=candidate.initial.construction; original=candidate.lazy.predict.__globals__['context']
    scope=candidate.PublicInputScope()
    assert candidate.initial.construction is old is candidate.construction
    assert candidate.lazy.predict.__globals__['context'] is original is candidate.context
    assert scope.Projection.__mro__[1] is candidate.lazy.Projection
    assert scope.Projection.activate is candidate.lazy.Projection.activate
    assert scope.Projection.run is candidate.lazy.Projection.run


@pytest.mark.parametrize('case',candidate.construction.construction.CASE_IDS)
def test_public_identity_original_all_case_guard_result(case):
    scope=candidate.PublicInputScope()
    data=scope.inputs()[case]
    jobs=candidate.construction.initial_facts(data)[0]
    contract=candidate.initial.supported_contract(case=case)
    assert candidate.initial.identify_public_case(contract,jobs)==scope.initial.identify_public_case(contract,jobs)==case
    assert exact(scope.initial.supported_contract(later=True,case=case),
        candidate.initial.supported_contract(later=True,case=case))


@pytest.mark.parametrize('defect',['job_duration','contract_edge','missing_job'])
def test_original_rejection_checks_not_bypassed(defect):
    scope=candidate.PublicInputScope()
    data=scope.inputs()['mechanism']; jobs=candidate.construction.initial_facts(data)[0]
    contract=candidate.initial.supported_contract(case='mechanism')
    if defect=='job_duration': jobs['loaded']['load_seconds']+=1
    elif defect=='contract_edge': contract['edge_records'][0][2]+=1
    else: del jobs['receiver']
    with pytest.raises(ValueError,match='unsupported_or_ambiguous_public_graph_and_jobs'):
        candidate.initial.identify_public_case(contract,jobs)
    with pytest.raises(ValueError,match='unsupported_or_ambiguous_public_graph_and_jobs'):
        scope.initial.identify_public_case(contract,jobs)


def test_invalid_context_stays_unknown_without_model_engine(monkeypatch):
    expected=candidate.lazy.predict(object(),{})
    assert exact(candidate.predict(object(),{}),expected)
    assert expected['status']=='unknown'


def test_later_historical_private_fallback_points_at_same_scoped_initial():
    scope=candidate.PublicInputScope()
    assert scope.historical.old.old is scope.initial
    assert scope.historical.lifecycle is scope.lifecycle
    assert scope.lifecycle.identify_public_case is scope.initial.identify_public_case
    assert scope.lifecycle.public_input is scope.initial.public_input
    assert scope.context.revalidate.__globals__['initial_context'] is scope.context.initial_context
    assert scope.context.revalidate.__globals__['later_context'] is scope.context.later_context
    assert scope.context.later_context.__globals__['later'] is scope.historical


def test_tampered_local_guard_code_rejected_by_proof():
    scope=candidate.PublicInputScope()
    def invalid(*args,**kwargs): return True
    scope._initial_namespace['identify_public_case']=invalid
    with pytest.raises(ValueError,match='changed_guard_or_helper_code'): scope.source_proof()


def test_bad_public_domain_never_silently_accepted(monkeypatch):
    monkeypatch.setattr(candidate.construction,'inputs',lambda:{})
    with pytest.raises(ValueError,match='fixed_public_domain'): candidate.PublicInputScope()


def test_data_only_candidate_does_not_load_native_or_C():
    candidate.PublicInputScope()
    assert '_g31_complete_tree_normalizer' not in sys.modules
    assert not any('czr005_circulation' in name for name in sys.modules)
