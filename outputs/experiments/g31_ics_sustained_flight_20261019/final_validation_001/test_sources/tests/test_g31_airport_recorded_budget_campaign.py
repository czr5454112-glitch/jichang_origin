"""Finite budget configuration and delegation only; no native execution."""
import copy
import subprocess
import sys

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_recorded_budget_campaign as campaign


def test_evidence_bound_budget_is_finite_and_preserves_prior_partial():
    basis = campaign.budget_basis()
    assert len(basis['references']) == 3
    assert basis['remaining_simulated_seconds'] == 59400 - 54240
    assert basis['projected_remaining_loop_wall_seconds'] == 91.5 * 5160 / 3600
    assert 554 < basis['projected_complete_loop_wall_seconds'] < 555
    assert 585 < basis['projected_total_with_allowance_seconds'] < 586
    assert not basis['old_partial_relabelled_or_removed']
    assert not basis['native_input_model_physics_policy_window_changed']
    assert basis['automatic_retries'] == 0
    assert (campaign.SOFT_SECONDS, campaign.HARD_SECONDS, campaign.OUTER_SECONDS) == (600, 660, 720)


def test_configuration_delegates_all_algorithm_functions_and_restores_test_globals(monkeypatch):
    base = campaign.delegate
    functions = {name:getattr(base,name) for name in ['prepare','worker','launch','check_pins',
        'apply_policy','registered_planner','execute_continuous','execute_bounded_continuous']}
    original_resource = copy.deepcopy(base.resource_contract())
    for name in ['MODULE','SCHEMA','SOFT_SECONDS','HARD_SECONDS','SOURCE_ROOTS','soft_checkpoint_contract']:
        monkeypatch.setattr(base,name,getattr(base,name))
    monkeypatch.setattr(campaign,'_configured',False)
    assert campaign.configure() is base and campaign.configure() is base
    assert all(getattr(base,name) is fn for name,fn in functions.items())
    assert base.resource_contract() == original_resource
    assert base.MODULE == campaign.MODULE and base.SCHEMA == campaign.SCHEMA
    assert base.SOURCE_ROOTS == (campaign.MODULE,*campaign._BASE_ROOTS)
    contract = base.soft_checkpoint_contract()
    assert contract['soft_seconds'] == 600 and contract['hard_seconds'] == 660
    assert contract['recommended_outer_hard_seconds'] == 720
    assert contract['previous_soft_seconds'] == 420 and contract['previous_hard_seconds'] == 480
    assert not contract['control_trace_changed_when_deadline_never_fires']
    assert contract['measured_wall_resource_basis']['native_input_model_physics_policy_window_changed'] is False


def test_basis_hash_change_is_rejected(monkeypatch):
    monkeypatch.setattr(campaign.delegate,'sha',lambda path:'0'*64)
    try:
        campaign.budget_basis()
    except ValueError as error:
        assert 'wall_resource_basis_hash' in str(error)
    else:
        raise AssertionError('changed original evidence accepted')


@pytest.mark.parametrize('arguments,stdin',[
    ([],''),
    (['--admission','expected-token'],''),
    (['--admission','expected-token'],'wrong-token\n'),
    (['--admission'],''),
])
def test_worker_rejects_absent_or_wrong_admission_before_delegate_import(tmp_path,arguments,stdin):
    destination=tmp_path/'must-not-be-created'
    result=subprocess.run([sys.executable,'-X','importtime','-m',campaign.MODULE,
        '--worker','--output',str(destination),*arguments],input=stdin,text=True,
        capture_output=True,timeout=15,cwd=campaign.delegate.ROOT)
    assert result.returncode != 0
    assert 'airport_recorded_budget:missing_parent_job_admission' in result.stderr
    assert 'foundation_airport_recorded_campaign' not in result.stderr
    assert not destination.exists()


def test_valid_admission_reaches_help_without_running_a_worker():
    result=subprocess.run([sys.executable,'-X','importtime','-m',campaign.MODULE,
        '--worker','--admission','expected-token','--help'],input='expected-token\n',
        text=True,capture_output=True,timeout=15,cwd=campaign.delegate.ROOT)
    assert result.returncode == 0
    assert 'foundation_airport_recorded_campaign' in result.stderr
    assert '--prepare' in result.stdout
