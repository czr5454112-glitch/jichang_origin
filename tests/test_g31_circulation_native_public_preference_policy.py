from copy import deepcopy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import native_public_preference_policy as policy
from scripts.experiments.g31_ics_circulation import research_native_public_preference as runner


def test_plain_saved_bundle_and_truth_flags_cannot_choose_an_online_later_action():
    fake={'status':'conditional_native_delivered_later_v3_model_input','native_delivery_verified':True,
          'online_information_delivered':True,'bundle':{}}
    result=policy.later(fake,'coordinate_strict')
    assert result['selected_action'] is None and result['status'].startswith('unknown')


def test_full_six_case_ten_method_denominator_and_four_fixed_windows_share_inputs():
    plan=runner.protocol('business')
    assert len(plan['rows'])==60 and plan['native_branch_budget']==60
    assert (plan['initial_budget'],plan['later_budget'])==(32,4)
    assert plan['hard_timeout_seconds']==180.
    for case in runner.domain.cases():
        rows=[r for r in plan['rows'].values() if r['case']==case]
        assert {r['method'] for r in rows}==set(policy.METHODS)
        assert {plan['row_configuration_sha256'][case['case_id']+'/'+r['method']] for r in rows}=={plan['configuration_sha256'][case['case_id']]}
    assert policy.method_parameters('pair_repair_later_default')=={'method':'resource_pair_repair','later_default_only':True}
    assert policy.method_parameters('fixed_window_3',later=True)=={'method':'resource_pair_repair'}


def test_delivery_gate_remains_exact_six_normal_and_three_negative_initial_captures():
    rows=runner.protocol('delivery_gate')['rows']
    assert len(rows)==9 and sum(r['fault'] is None for r in rows.values())==6
    assert {r['fault'] for r in rows.values() if r['fault']}=={'missing_peer','expired_capture','lost_self_ack'}


def test_unexecuted_or_missing_families_do_not_become_zero_gain_or_protection():
    rows=deepcopy(runner.protocol('business')['rows'])
    result=runner.assess(rows,'business')
    for case in result.values():
        assert case['complete_fixed_family'] is False
        assert all(r['gain_vs_incumbent'] is None and r['strict_protected_vs_incumbent'] is None for r in case['methods'].values())
    rows.pop(next(iter(rows)))
    assert runner.assess(rows,'business')['status'].startswith('unknown_incomplete')


def test_launch_puts_preflight_native_and_final_validation_inside_same_owned180_job(tmp_path,monkeypatch):
    calls=[]
    def fake(command,**kwargs):
        calls.append((command,kwargs))
        return {'status':'hard_timeout','pid':123,'exitcode':1,'windows_job_kill_on_close':True}
    monkeypatch.setattr(runner.bounded_windows_job,'run',fake)
    args=SimpleNamespace(output=tmp_path,phase='business',expected_plan_sha256='plan',binary='binary',
        expected_binary_sha256='binaryhash',native_contract='contract',expected_native_contract_sha256='contracthash',
        semantic_gate='semantic',expected_semantic_gate_sha256='semantichash',delivery_gate='delivery')
    result=runner.launch(args)
    command,kwargs=calls[0]
    assert kwargs['timeout']==180. and '--worker' in command and '--parent-admission' in command
    assert command[command.index('--parent-admission')+1]==kwargs['admission']
    assert command[command.index('--delivery-gate')+1]=='delivery'
    assert result['evidence_status']=='unassessed_actual_process_outcome_only'
    assert result['all_unfinished_branches_retained_unknown'] is True


def test_worker_rejects_changed_prepared_plan_before_loading_any_native(tmp_path,monkeypatch):
    (tmp_path/'preregistered_protocol.json').write_text('{}')
    monkeypatch.setattr(runner,'load_native',lambda *args:pytest.fail('native load must not occur'))
    with pytest.raises(ValueError,match='frozen_plan_changed'):
        runner.worker(SimpleNamespace(output=tmp_path,expected_plan_sha256='wrong'))
