"""Regression for a real omitted-global failure, no native or large raw reads."""
from types import FunctionType,SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_entry_campaign_v2 as v


def test_original_defect_is_reproduced_and_new_verifier_reaches_plan_guard(tmp_path):
    with pytest.raises(NameError,match='Path'):
        v.frozen.verify_saved(tmp_path,'not-a-plan')
    observed=[]
    def plan(path,expected):
        observed.append((path,expected));raise ValueError('sentinel_plan_guard')
    namespace={**v.verify_saved.__globals__,'c':SimpleNamespace(verify_plan=plan)}
    check=FunctionType(v.verify_saved.__code__,namespace)
    with pytest.raises(ValueError,match='sentinel_plan_guard'):check(tmp_path,'not-a-plan')
    assert observed==[(tmp_path.resolve(),'not-a-plan')]


def test_recursive_comprehension_global_inventory_catches_missing_modules():
    def sample(values):return [missing_global_helper(x) for x in values]
    assert v.missing_globals(sample)==['missing_global_helper']
    fixed=FunctionType(sample.__code__,{**sample.__globals__,'missing_global_helper':lambda x:x})
    assert v.missing_globals(fixed)==[] and fixed([1,2])==[1,2]


def test_all_original_checks_and_two_level_entry_binding_are_retained():
    proof=v.source_proof()
    assert 'Path' in proof['old_missing_globals']['verify_saved']
    assert all(not missing for missing in proof['new_missing_globals'].values())
    assert proof['producer_status']=='failed_preserved'
    assert v.verify_saved.__globals__['verify_branch'] is v.verify_branch
    assert v.verify_branch.__globals__['_original_verify_branch'] is v._original_verify_branch
    assert v._original_verify_branch.__globals__['root_replay'] is v.root_replay
    assert v.root_replay.__globals__['old'].root_replay.__globals__['c'] is v.c
    assert v.root_replay.__globals__['old'].root_replay.__globals__['c'].contract is v.c.integrated.contract


@pytest.mark.parametrize('name',v.NAMES)
def test_frozen_function_namespaces_not_mutated_and_all_code_retained(name):
    previous=getattr(v.frozen,name);current=getattr(v,name)
    assert current.__code__ is previous.__code__
    assert current.__defaults__==previous.__defaults__
    assert current.__kwdefaults__==previous.__kwdefaults__
    assert current.__closure__==previous.__closure__
    assert current.__globals__ is v._namespace
    assert current.__globals__ is not previous.__globals__
    assert 'Path' not in v.frozen.verify_saved.__globals__
