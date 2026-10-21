"""Pure campaign registration, calendar, actor wiring and admission gates."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_parents as parents
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_calendar as calendar
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as opportunities
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_control as control
from scripts.experiments.g31_ics_circulation import protocol_control as protocol
from test_g31_airport_inventory_rule import observation, PublicSession
from test_g31_airport_joint_interface import two_sources


@pytest.fixture
def registered(tmp_path):
    plan = tmp_path / 'external_plan.md'; plan.write_text('registered proposal', encoding='utf8')
    cycle = tmp_path / 'cycle'
    budget.register(cycle, plan, 'frozen-anchor')
    return cycle


def task(identity='T1', **changes):
    return dict(task_id=identity, batch='gates', hard_seconds=30., plan_sha256='p'*64,
        binary={'sha256': 'b'*64}, source_bundle={'sha256': 's'*64},
        parent={'split': 'train'}, **changes)


def open_runner(cycle):
    budget.append(cycle, 'runner_open', runner_id='runner1')


def test_admission_needs_owned_interval_and_retains_failed_start(registered):
    with pytest.raises(ValueError, match='owned_active_runner_required'):
        budget.admit(registered, task())
    open_runner(registered); budget.admit(registered, task())
    with pytest.raises(ValueError, match='unfinished_native_attempt'):
        budget.admit(registered, task('T2'))
    budget.append(registered, 'native_finish', task_id='T1', process_status='failed', scientific_status='unknown')
    with pytest.raises(ValueError, match='no_silent_task_relaunch'):
        budget.admit(registered, task())
    assert budget.status(registered)['native_starts'] == 1
    budget.append(registered, 'runner_close', runner_id='runner1')
    assert budget.status(registered)['active_seconds'] > 0


def test_duplicate_runner_and_live_recovery_are_rejected(registered):
    open_runner(registered)
    with pytest.raises(ValueError, match='recover_existing_runner'):
        budget.append(registered, 'runner_open', runner_id='racer')
    with pytest.raises(ValueError, match='cannot_recover_live_runner'):
        budget.recover_runner(registered, 'runner1', reason='must not close live work')
    assert budget.status(registered)['open_runners'] == ['runner1']


def test_os_lock_blocks_second_admission_even_in_same_process(registered):
    with budget._locked(registered):
        with pytest.raises(ValueError, match='admission_locked'):
            budget.status(registered)


@pytest.mark.parametrize('change,reason', [
    ({'hard_seconds': float('nan')}, 'invalid_task_admission'),
    ({'hard_seconds': 172800.}, 'active_time_exhausted'),
    ({'batch': 'unknown'}, 'invalid_task_admission'),
    ({'parent': {'split': 'test'}}, 'formal_locked'),
    ({'estimated_evidence_bytes': 40*1024**3}, 'disk_boundary')])
def test_rejected_admission_never_consumes_start(registered, change, reason):
    open_runner(registered)
    with pytest.raises(ValueError, match=reason):
        budget.admit(registered, {**task(), **change})
    assert budget.status(registered)['native_starts'] == 0


def test_batch_allocation_and_low_free_space_are_real_boundaries(registered, monkeypatch):
    open_runner(registered)
    definition = budget.read(registered/'campaign_budget.json')
    definition['allocations']['gates'] = 0
    (registered/'campaign_budget.json').write_text(json.dumps(definition), encoding='utf8')
    with pytest.raises(ValueError, match='native_allocation_exhausted'):
        budget.admit(registered, task())
    definition['allocations']['gates'] = 8
    (registered/'campaign_budget.json').write_text(json.dumps(definition), encoding='utf8')
    old = budget.shutil.disk_usage(registered)
    monkeypatch.setattr(budget.shutil, 'disk_usage', lambda path: old._replace(free=30*1024**3-1))
    with pytest.raises(ValueError, match='disk_boundary'):
        budget.admit(registered, task())
    assert budget.status(registered)['native_starts'] == 0


def test_dead_recovery_charges_entire_interval_and_keeps_unknown_attempt(registered, monkeypatch):
    began = datetime.now(timezone.utc) - timedelta(seconds=120)
    with budget._locked(registered):
        budget._append(registered, 'runner_open', runner_id='dead', pid=99999999,
            process_created_at=1.)
        budget._append(registered, 'native_start', task_id='interrupted', batch='gates', runner_id='dead')
    rows = budget.events(registered); rows[0]['at'] = began.isoformat()
    (registered/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf8')
    monkeypatch.setattr(budget, '_live', lambda identity: False)
    budget.recover_attempt(registered, 'interrupted', reason='verified parent process exited')
    state = budget.recover_runner(registered, 'dead', reason='verified parent process exited')
    assert state['active_seconds'] >= 120.
    assert state['native_starts'] == 1 and not state['unfinished_native_tasks']
    assert any(row.get('scientific_status') == 'unknown_unclosed_attempt' for row in budget.events(registered))


def test_registration_never_resets_a_lost_or_partial_ledger(registered, tmp_path):
    path = tmp_path/'external_plan.md'
    (registered/'ledger.jsonl').write_text('{"event":', encoding='utf8')
    with pytest.raises(ValueError, match='incomplete_ledger_requires_audit'):
        budget.register(registered, path, 'frozen-anchor')


def test_new_whole_parent_roster_calendar_and_template_limits():
    assert set(parents.SEEDS) == set(range(2101, 2109)) | set(range(2201, 2205)) | set(range(2301, 2309))
    records = [parents._expected_registration(seed, 0) for seed in parents.SEEDS]
    assert len({row['parent_group'] for row in records}) == 20
    assert all(row['synthetic'] and row['plan_family_id'] == 'joint_group_shift_plan_v1' for row in records)
    assert max(row['calendar_start_epoch_seconds'] for row in records if row['split']=='train') < min(
        row['calendar_start_epoch_seconds'] for row in records if row['split']=='dev')
    assert parents.registry()['independent_real_airport_days'] == 0
    for seed in range(2101, 2109):
        first, later = parents._expected_registration(seed, 0), parents._expected_registration(seed, 1)
        assert first['plan_group_shifts_sha256'] == later['plan_group_shifts_sha256']
        assert later['calendar_start_epoch_seconds'] - first['calendar_start_epoch_seconds'] == 20*86400


def test_unfrozen_test_parent_rejects_before_private_tape_generation():
    with pytest.raises(ValueError, match='test_locked_until_champions_freeze'):
        parents.make_parent(2301)


def test_new_calendar_inverse_preserves_frozen_B1_and_has_no_future_arrivals():
    first = calendar.load_calendar_binding(parents._expected_registration(2101, 0))
    later = calendar.load_calendar_binding(parents._expected_registration(2101, 1))
    calendar._validate_binding(first); calendar._validate_binding(later)
    assert first['checkpoint']['parameters'] == later['checkpoint']['parameters']
    assert first['producer_manifest']['source_model_id'] == calendar.SOURCE_MODEL_ID
    assert first['producer_manifest']['new_fit_performed'] is False
    assert first['producer_manifest']['synthetic_common_template_limits']['target_actual_arrivals_or_future_counts_used'] is False
    changed = deepcopy(first)
    changed['absolute_plan_template']['entries'][0]['scheduled_event_at'] += 60.
    changed['producer_manifest']['target_plan_template_sha256'] = calendar.digest(changed['absolute_plan_template'])
    changed['binding_sha256'] = calendar.digest({key:value for key,value in changed.items() if key!='binding_sha256'})
    with pytest.raises(ValueError, match='inverse_binding_must_recover_frozen_public_plan'):
        calendar._validate_binding(changed)


def test_predecision_evaluator_runs_before_joint_policy_state_or_submit():
    session = PublicSession(); client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {'next_tick': 1}; seen = []
    def before(**kwargs):
        assert kwargs['decision']['intents'] == []
        assert 'joint_post_priority' not in kwargs['controller_state']
        assert not session.transfer_calls
        seen.append('predecision')
    def actor(prepared, catalog, **kwargs):
        assert seen == ['predecision']
        assert 'session' not in kwargs and 'controller_state' not in kwargs
        return control.select_joint_bridge(prepared, catalog)
    result = protocol._post_inventory_return(client, 'A', state, compact=True, command_delay=0.,
        priority_error=False, stock_return_selector=control.JointPostPrioritySelector(actor),
        stock_return_selector_identity='test', pre_stock_return_observer=before)
    assert result['new_submissions'] == 1 and len(session.transfer_calls) == 1


def test_C00_recording_policy_uses_actual_joint_catalog_and_never_calls_forecast():
    obs = two_sources(); obs['observation_scope'] = 'controller_policy'
    obs['control_projection'] = {'schema':'g31.analytic_control_projection.v1','waiting_groups':[],
        'exact_waiting_count':0,'candidate_limit':22,'known_origin_nodes':[]}
    prepared = opportunities.prepare_current(obs, r0.r0_priority_planner(obs))
    catalog = opportunities.build_joint_catalog(prepared)
    def forbidden(**kwargs): raise AssertionError('C00 forecast leak')
    plan = dict(method='C00', projection_horizon_seconds=600., transport_penalty=.01, minimum_gain=0.,
        task_id='pure', policy_version='pure-policy', parent={'calendar_start_epoch_seconds':1800000000.})
    decisions, observations = [], []
    actor = campaign.RecordingPolicy(plan, forbidden, decisions, observations)
    choice = actor(prepared, catalog, policy_state={}, decision_context={'tick':1})
    assert choice['action_id'] in {row['action_id'] for row in catalog['candidates']}
    assert len(decisions) == len(observations) == len(actor.rows) == 1
    assert actor.rows[0]['reference_candidate_id'] == choice['action_id']


def test_worker_rejects_changed_plan_before_native_constructor(tmp_path, monkeypatch):
    from scripts.experiments.g31_ics_circulation import native_host
    output = tmp_path/'run'; output.mkdir()
    plan_path = output/'plan.json'
    campaign.common.write(plan_path, {'output':str(output),'task_id':'pure-invalid'})
    def forbidden(*args, **kwargs): raise AssertionError('native loader called')
    monkeypatch.setattr(native_host, 'load_native', forbidden)
    report = campaign.worker(plan_path, 'wrong-sha')
    assert report['native_constructor_attempts'] == 0
    assert report['process_status'] == 'failed' and report['scientific_status'] == 'unknown_error'
    assert 'cost' not in report


def test_registered_long_window_and_resource_limits_cannot_drift(tmp_path):
    from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound
    path=tmp_path/'calibration.json'
    limits=dict(horizon=59400.,soft_seconds=2280.,hard_seconds=2400.,estimated_evidence_bytes=512*1024**2)
    campaign.common.write(path,dict(limits,before_training=True))
    plan=dict(limits,batch='initial',calibration=bound(path))
    campaign.verify_calibration(plan)
    for key in limits:
        with pytest.raises(ValueError,match='calibration_limits_binding'):
            campaign.verify_calibration(dict(plan,**{key:limits[key]+1}))
    with pytest.raises(ValueError,match='pretraining_calibration_required'):
        campaign.verify_calibration(dict(plan,calibration=None))
