"""Data-path tests. Native execution and process overlap require their own runs."""
import copy
import gzip
import json
from types import SimpleNamespace
import time
import queue
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import foundation_repeated_domain as domain
from scripts.experiments.g31_ics_circulation import foundation_repeated_native as native
from scripts.experiments.g31_ics_circulation import foundation_successful_refresh_probe as fixture
from scripts.experiments.g31_ics_circulation import foundation_repeated_worker as worker
from scripts.experiments.g31_ics_circulation import foundation_repeated_campaign as campaign


@pytest.fixture
def evidence():
    raw = json.loads(gzip.decompress((fixture.BASELINE / 'raw.json.gz').read_bytes()))
    decision = raw['decisions']['B'][0]
    calls = [row for row in raw['calls'][:decision['predecision_call_prefix_count']] if row['request']['owner_id'] == 'B']
    ids = {row['request']['request_id'] for row in calls}
    value = {'schema': domain.EVIDENCE_SCHEMA, 'owner': 'B', 'phase': 'cycle_route', 'at': decision['at'],
        'collection': copy.deepcopy(decision['collection']), 'information': decision['information'],
        'retained': raw['retained_ledgers']['B'], 'own_calls': calls,
        'own_outbox': {key: row for key, row in raw['outbox'].items() if key in ids}}
    value['collection']['phase'] = 'cycle_route'
    return value


def test_finite_cases_change_only_one_arrival():
    physical = {domain.manifest(case)['physical_sha256'] for case in domain.CASES}
    assert len(physical) == 1
    original = domain.scene('legacy_mechanism')
    for case in set(domain.CASES) - set(domain.HOLD3_CASES):
        actual = domain.scene(case)
        actual['model_scope'] = original['model_scope']
        next(row for row in actual['jobs'] if row['business_bag_id'] == 'blocker')['arrival'] = 0.
        actual['jobs'] = [row for row in actual['jobs'] if row['business_bag_id'] not in ('reuse3', 'reuse4')]
        assert actual == original


def test_hold3_is_explicit_new_contract_on_identical_physics():
    original = domain.scene('three_reuse_blocker_11_1')
    original_blocker = next(row for row in original['jobs'] if row['business_bag_id'] == 'blocker')
    assert original_blocker['storage_node'] == 9
    for case, (arrival, release, split) in domain.HOLD3_CASES.items():
        value, declared = domain.scene(case), domain.manifest(case)
        blocker = next(row for row in value['jobs'] if row['business_bag_id'] == 'blocker')
        assert blocker['arrival'] == arrival and blocker['storage_node'] == 3 and blocker['storage_release_at'] == release
        assert declared['declared_split'] == split and declared['business_contract_version'].endswith('.v1')
        assert len(value['jobs']) == 6 and declared['physical_sha256'] == domain.manifest('legacy_mechanism')['physical_sha256']
        value['model_scope'] = original['model_scope']; blocker.update(original_blocker)
        assert value == original


def test_no_command_needs_no_new_receiving_slot_but_route_does():
    view = {'now': 20., 'node_contracts': [
        {'node': 3, 'resource_owner': 'B', 'occupancy': 1, 'capacity': 1},
        {'node': 8, 'resource_owner': 'B', 'occupancy': 0, 'capacity': 1}]}
    tray = {'node': 7, 'mode': 'loaded', 'edge_to': -1}
    assert native.current_route_local_mask(view, tray, 20.1, 'native_default', 'B')
    assert not native.current_route_local_mask(view, tray, 20.1, 'prefer_3', 'B')
    assert native.current_route_local_mask(view, tray, 20.1, 'prefer_8', 'B')
    assert not native.current_route_local_mask(view, tray, 20.005, 'native_default', 'B')


def test_current_route_parity_and_zero_tolerance(evidence):
    report = domain.evaluate(evidence, ('native_default', 'prefer_3', 'prefer_8'))
    assert report['status'] == 'conditional_current_seed'
    results = report['candidate_results']
    assert results['native_default']['completion'] == results['prefer_3']['completion']
    reference = {'completion': results['native_default']['completion']}
    rejected = native.control.protected(results['prefer_8'], reference)
    assert rejected['status'] == 'rejected' and rejected['per_job_delta']['reuse1'] > .89
    assert all(set(row['completion']) == set(native.control.JOBS) for row in results.values())


def test_point05_never_extended(evidence):
    evidence['at'] += .051
    evidence['information']['raw_endpoints']['view']['now'] = evidence['at']
    assert domain.evaluate(evidence, ('native_default',))['status'] == 'unknown'


def test_unknown_future_job_never_omitted_from_full_guard(evidence):
    evidence['retained']['contracts'].pop('blocker')
    assert domain.evaluate(evidence, ('native_default',))['status'] == 'unknown'


def test_ledger_excludes_unreleased_owner_job():
    session = SimpleNamespace(physical_time=1.)
    ledger = native.ContractLedger(session, 'A')
    row = {**domain.scene('late_blocker_11_1')['jobs'][-1], 'status': 'unreleased'}
    ledger.ingest({'owner_id': 'A', 'now': 1., 'jobs': [row]}, [])
    assert ledger.contracts == {} and not native.visible_view({'now': 1., 'jobs': [row]})['jobs']


def test_opportunity_changes_with_actual_generation_and_cause():
    tray = {'tray_id': 'L', 'generation': 2, 'traversal_id': 4}
    a = domain.opportunity('episode', 'B', 'cycle_route', tray, 10., 'receipt1', service_ready_at=10.1)
    b = domain.opportunity('episode', 'B', 'cycle_route', {**tray, 'generation': 3}, 10., 'receipt1', service_ready_at=10.1)
    c = domain.opportunity('episode', 'B', 'cycle_route', tray, 10., 'receipt2', service_ready_at=10.1)
    assert len({row['opportunity_id'] for row in (a, b, c)}) == 3
    assert a['use_by'] == 10.1-.01 and a['execution_authority'] is False


def test_all_registered_populations_exact_and_no_removed_old_guard():
    for case in domain.CASES:
        data = domain.scene(case)
        jobs = {row['business_bag_id']: {**row, 'protected_service': True} for row in data['jobs']}
        assert domain.identify(domain.old_guard.supported_contract(later=True), jobs) == case
        assert len(jobs) == 3 + domain.REUSE_COUNTS.get(case, 2)
    assert domain.old_guard.model.JOBS == set(native.control.JOBS)


def test_six_or_seven_job_guard_never_drops_new_business():
    reference = {'completion': {str(index): 10. for index in range(7)}}
    prediction = {'status': 'conditional_prediction', 'completion': dict(reference['completion'])}
    assert native.protected(prediction, reference)['status'] == 'passed'
    prediction['completion']['6'] += .0000000001
    assert native.protected(prediction, reference)['status'] == 'rejected'
    prediction['completion'].pop('6')
    assert native.protected(prediction, reference)['status'] == 'unknown'


def test_detached_physics_continues_third_and_fourth_reuse(evidence):
    # Unit-only seed mutation exercises continuation, grants no collected
    # capability and does not claim that this synthetic fixture is admitted.
    seed = domain.build_seed(evidence)
    for index in (3, 4):
        seed['bundle']['jobs'][f'reuse{index}'] = {**seed['bundle']['jobs']['reuse2'],
            'business_bag_id': f'reuse{index}', 'arrival': .01*(index+1)}
    result = domain.Projection(seed, 'native_default').run()
    assert result['status'] == 'conditional_prediction' and len(result['completion']) == 7
    assert result['completion']['reuse2'] < result['completion']['reuse3'] < result['completion']['reuse4'] < 40.


def test_generic_assessment_agrees_with_old_real_complete_fixture():
    raw = json.loads(gzip.decompress((fixture.BASELINE/'raw.json.gz').read_bytes()))
    client = SimpleNamespace(rows=raw['outbox'], calls=raw['calls'])
    result = native.assess(raw['input'], raw['result'], client, raw['continuation'], native.online.protocol.incumbent_action())
    assert result['status'] == 'assessed' and result['completion'] == raw['summary']['completion']


def test_resident_result_body_collected_before_close_and_pending_is_bounded(tmp_path, evidence):
    resident = worker.ResidentWorker('B', tmp_path / 'resident')
    resident.start()
    try:
        first = resident.submit(evidence, ('native_default',))
        replaced = resident.submit(evidence, ('native_default',))
        last = resident.submit(evidence, ('native_default',))
        assert resident.active['request_id'] == first and resident.pending['request_id'] == last
        obtained = []; deadline = time.monotonic()+15.
        while len(obtained) < 2 and time.monotonic() < deadline:
            value = resident.poll(evidence['at'])
            if value is not None:
                obtained.append(value)
            time.sleep(.01)
        assert [row['request_id'] for row in obtained] == [first, last]
        assert all(row['model_report']['status'] == 'conditional_current_seed' for row in obtained)
        assert replaced not in [row['request_id'] for row in obtained]
        assert 'after_native_shutdown_wall_ms' not in resident.timing
    finally:
        resident.close()


def test_preview_target_is_known_unrouted_and_projection_is_target_bound(evidence):
    evidence['phase'] = evidence['collection']['phase'] = 'preview_next_route'
    evidence['collection']['target_job'] = 'reuse2'
    seed = domain.build_seed(evidence)
    assert seed['preview_target_job'] == 'reuse2'
    default = domain.Projection(seed, 'native_default').run()
    alternative = domain.Projection(seed, 'prefer_8').run()
    assert default['completion']['reuse1'] == alternative['completion']['reuse1']
    assert default['completion']['reuse2'] != alternative['completion']['reuse2']
    evidence['collection']['target_job'] = 'not_actually_known'
    assert domain.evaluate(evidence, ('prefer_8',))['status'] == 'unknown'


def test_worker_body_rejects_late_job_and_wrong_projection_target():
    policy = object.__new__(native.OwnerPolicy)
    policy.owner, policy.session = 'B', SimpleNamespace(physical_time=20.)
    policy.ledger = SimpleNamespace(contracts={'reuse2': {}, 'reuse3': {}})
    policy.choices, policy.result_deliveries, policy.completed_advice = [{'job': 'reuse2'}], [], None
    result = {'request_id': 'B-1', 'owner': 'B', 'target_job': 'reuse2', 'source_at': 11.,
        'model_report': {'status': 'conditional_current_seed', 'seed': {'preview_target_job': 'reuse2'}}}
    policy.accept_worker_result(result)
    assert policy.result_deliveries[-1]['status'] == 'rejected_action_already_dispatched' and policy.completed_advice is None
    result['target_job'] = 'reuse3'
    policy.accept_worker_result(result)
    assert policy.result_deliveries[-1]['status'] == 'rejected_unknown_or_mismatched_target_prediction'
    result['model_report']['seed']['preview_target_job'] = 'reuse3'
    policy.accept_worker_result(result)
    assert policy.completed_advice is result


def test_model_consumes_only_enabled_semantics(monkeypatch):
    seen = []
    def predict(model, observations, actions):
        seen.extend(actions)
        return [7.]
    monkeypatch.setattr(native.learned_value, 'predict', predict)
    enabled = [{'action_id': 'native_default', 'semantic': native.semantic('cycle_route', 'native_default', 20.)}]
    audit = native.score_enabled({'model_sha256': 'content'}, {'path': 'frozen', 'sha256': 'bytes'}, {}, enabled)
    assert seen == [enabled[0]['semantic']] and audit['scores'] == {'native_default': 7.}
    assert audit['used_as_authority'] is False and audit['model_reference']['sha256'] == 'bytes'


def test_prefer8_then_default_is_declared_current_job_schedule():
    selection = 'prefer_8_then_default'
    assert selection in native.SELECTIONS
    assert native.preferred_current_action(selection, 'reuse2') == 'prefer_8'
    assert native.preferred_current_action(selection, 'reuse3') == 'native_default'
    assert native.preferred_current_action(selection, 'reuse4') == 'native_default'
    with pytest.raises(ValueError, match='scheduled_preference_repeated_job'):
        native.preferred_current_action(selection, 'reuse1')
    for unchanged in ('prefer_3', 'prefer_8', 'native_default'):
        assert native.preferred_current_action(unchanged, 'reuse3') == unchanged
    assert native.preferred_current_action('score', 'reuse3') is None


def test_scheduled_preference_ranks_only_current_guarded_set():
    rows = [{'action_id': action} for action in ('native_default', 'prefer_3', 'prefer_8')]
    report = {'candidate_results': {row['action_id']: {'completion': {'job': time}}
        for row, time in zip(rows, (30.5, 30.5, 26.121), strict=True)}}
    def choose(job, enabled, selection='prefer_8_then_default'):
        return native.choose_current_candidate(enabled,
            preferred=native.preferred_current_action(selection, job), report=report,
            advice_order=[], mode='guarded', model_scores={})
    assert choose('reuse2', rows)['action_id'] == 'prefer_8'
    assert choose('reuse3', rows)['action_id'] == 'native_default'
    assert choose('reuse2', rows[:2])['action_id'] == 'prefer_3'  # No disabled prefer8 admitted.
    assert choose('reuse3', rows[1:])['action_id'] == 'prefer_8'  # Missing preferred default grants nothing.
    assert choose('reuse3', []) is None
    assert choose('reuse3', rows, 'score')['action_id'] == 'prefer_8'
    assert choose('reuse3', rows, 'prefer_3')['action_id'] == 'prefer_3'


def test_preview_gate_waits_for_actual_terminal_ack_and_existing_headway_bound():
    row = {'kind': 'transfer', 'terminal': False,
        'request': {'tray_id': 'E', 'source': 5, 'destination': 1}, 'ack': None}
    assert native.preview_source_gate({'E-return': row}, 11.67)[1] == 'local_physical_action_not_delivered_terminal'
    row.update(terminal=True, ack={'status': 'received', 'delivered_at': 12.24})
    assert native.preview_source_gate({'E-return': row}, 12.74)[1] == 'owned_short_edge_headway_proof_not_mature'
    assert native.preview_source_gate({'E-return': row}, 12.76)[0] is True
    row['ack']['delivered_at'] = 13.
    assert native.preview_source_gate({'E-return': row}, 12.76)[0] is False


def preview_policy():
    policy = object.__new__(native.OwnerPolicy)
    policy.resident, policy.owner, policy.pending, policy.peer_quiet_until = object(), 'B', None, 0.
    policy.choices = [{'job': 'reuse1'}]
    policy.preview_targets, policy.preview_attempts, policy.preview_schedule = set(), {}, []
    policy.preview_last_deferral = None
    policy.required_business_ids = {'reuse1', 'reuse2', 'reuse3'}
    policy.ledger = SimpleNamespace(contracts={job: {} for job in policy.required_business_ids})
    policy.client = SimpleNamespace(context={'owner': 'B', 'root_id': 'actual-test-root'}, owned=lambda owner: {})
    def begin(phase, tray, root):
        policy.pending = {'phase': phase, 'trigger_tray': tray, 'root': root}
    policy.begin_new = begin
    return policy


def preview_view():
    return {'now': 12.76, 'jobs': [
        {'business_bag_id': 'reuse2', 'arrival': .03, 'status': 'waiting_for_tray'},
        {'business_bag_id': 'reuse3', 'arrival': .04, 'status': 'waiting_for_tray'}], 'trays': []}


def test_preview_does_not_require_or_invent_local_L_and_is_bounded_by_new_facts():
    policy, view = preview_policy(), preview_view()
    policy.maybe_preview(view)
    assert policy.pending['trigger_tray'] is None and policy.pending['target_job'] == 'reuse2'
    assert policy.pending['preview_attempt'] == 1 and policy.preview_targets == set()
    policy.pending = None
    view['now'] += .05
    policy.maybe_preview(view)
    assert policy.pending is None  # Elapsed time alone is not new physical evidence.
    view['jobs'][0]['status'] = 'loading'
    policy.maybe_preview(view)
    assert policy.pending['target_job'] == 'reuse2' and policy.pending['preview_attempt'] == 2
    policy.pending = None
    view['trays'] = [{'tray_id': 'L', 'generation': 8}]
    policy.maybe_preview(view)
    assert policy.pending is None and len(policy.preview_attempts['reuse2']) == 2


def test_preview_never_skips_loading_next_job_to_later_waiting_job():
    policy, view = preview_policy(), preview_view()
    view['jobs'][0]['status'] = 'loading'
    policy.preview_targets.add('reuse2')
    policy.maybe_preview(view)
    assert policy.pending is None and 'reuse3' not in policy.preview_attempts
    policy.choices.append({'job': 'reuse2'})
    policy.maybe_preview(view)
    assert policy.pending['target_job'] == 'reuse3'


def test_preview_target_consumed_only_after_successful_worker_submission():
    policy, view = preview_policy(), preview_view()
    policy.repeated_attempts = []
    policy.resident = SimpleNamespace(submit=lambda evidence, actions: 'B-00001')
    policy.maybe_preview(view)
    evidence = {'information': {'status': 'unknown', 'reasons': ['source_not_ready']}}
    policy.collect = lambda current: (evidence, {})
    policy.decide_current(view, False)
    assert not policy.preview_targets and policy.preview_schedule[-1]['kind'] == 'collection_refused_target_not_consumed'
    view['jobs'][0]['status'] = 'loading'
    policy.maybe_preview(view)
    evidence['information']['status'] = 'conditional_validated_later_v3_data'
    policy.decide_current(view, True)
    assert policy.preview_targets == {'reuse2'} and policy.preview_schedule[-1]['kind'] == 'worker_enqueued'


def test_saved_async_failure_remains_unsubmitted_not_a_worker_timing_success():
    path = baseline_artifact().parent.parent/'A3_train_async_001'/'raw.json.gz'
    if not path.exists():
        pytest.skip('separately registered async failure not present')
    raw = json.loads(gzip.decompress(path.read_bytes()))
    first, second = raw['repeated_attempts']['B']
    assert first['evidence']['information']['extension_check']['reasons'] == ['unresolved_source_physical_action']
    assert second['evidence']['information']['reasons'] == ['invalid_v3_channel_contract_or_causal_age']
    assert raw['result_deliveries'] == [] and all('worker_request_id' not in row for row in (first, second))


def actual_async_reply_fixture(at=12.78):
    path = baseline_artifact().parent.parent/'A4_train_async_001'/'raw.json.gz'
    if not path.exists():
        pytest.skip('separately registered v2 async fixture not present')
    raw = json.loads(gzip.decompress(path.read_bytes()))
    exchange = next(row for row in raw['exchanges']['A'] if row['kind'] == 'repeated_reply'
        and abs(row['at']-at) < .0001)
    return raw, exchange, raw['outbox'][exchange['request_id']]['request']


@pytest.mark.parametrize('at,expected', [(11.69, .02), (12.78, .02), (15.19, .08), (15.26, .08), (16.2, .08)])
def test_reply_silence_uses_actual_delivered_L_state_and_grants_no_authority(at, expected):
    _, exchange, request = actual_async_reply_fixture(at)
    contract = native.reply_silence_contract('async', 'A', exchange['message'], request, exchange['at'])
    assert contract['silence_s'] == expected and contract['execution_authority'] is False
    if expected == .02:
        assert contract['silence_s'] == request['publication_delay'] + request['message_delay']
        assert not any(row['mode'] == 'loaded' and row['node'] == 7 for row in contract['actual_source_L'])
    else:
        assert contract['classification'] == 'actual_L_loaded_at7_current_reply_keeps_original_window'


@pytest.mark.parametrize('mode,owner', [('guarded', 'A'), ('baseline', 'A'), ('async', 'B')])
def test_short_preview_reply_does_not_change_other_policy_modes_or_owner(mode, owner):
    _, exchange, request = actual_async_reply_fixture()
    contract = native.reply_silence_contract(mode, owner, exchange['message'], request, exchange['at'])
    assert contract['silence_s'] == native.bound.COLLECTION_LIMIT == .08


@pytest.mark.parametrize('corruption', ['digest', 'future', 'incomplete', 'delay', 'expired'])
def test_unknown_or_unbound_preview_reply_keeps_original_silence(corruption):
    _, exchange, request = actual_async_reply_fixture()
    envelope = exchange['message']; now = exchange['at']
    if corruption == 'digest':
        envelope['payload_sha256'] = '0'*64
    elif corruption == 'delay':
        request['message_delay'] = .03
    elif corruption == 'expired':
        now += .06
    else:
        local = envelope['capture']['capture_v2']['local_capture']
        local['coverage']['future_arrivals_included' if corruption == 'future' else 'complete_for_declared_local_scope'] = corruption == 'future'
        envelope['payload_sha256'] = domain.old_guard.capture_digest_v3(envelope['capture'])
    result = native.reply_silence_contract('async', 'A', envelope, request, now)
    assert result['silence_s'] == .08 and result['execution_authority'] is False
    assert result.get('short_window_refused_reason')


def test_reply_silence_binds_real_publication_cause_and_never_shortens_existing_hold():
    raw, exchange, request = actual_async_reply_fixture()
    policy = object.__new__(native.OwnerPolicy)
    policy.mode, policy.owner, policy.quiet_periods = 'async', 'A', []
    policy.client = SimpleNamespace(rows=raw['outbox'], creations=raw['request_creations'])
    policy.peer_quiet_until = exchange['at']+.07
    policy.apply_reply_silence(exchange['message'], exchange['request_id'], exchange['at'])
    assert policy.peer_quiet_until == exchange['at']+.07
    audit = policy.quiet_periods[-1]
    assert audit['source_reply_identity_bound'] and audit['reply_silence_contract']['silence_s'] == .02
    assert audit['incremental_policy_silence_s'] == 0
    assert audit['native_physics_paused'] is audit['worker_waited_for'] is False
    policy.peer_quiet_until = 0.
    policy.apply_reply_silence(exchange['message'], exchange['request_id'], exchange['at'], expected_source_message='wrong-source')
    assert policy.peer_quiet_until == exchange['at']+.08 and not policy.quiet_periods[-1]['source_reply_identity_bound']


def test_deferred_reply_uses_the_actual_latest_publication_and_pending_source():
    raw, exchange, request = actual_async_reply_fixture()
    policy = object.__new__(native.OwnerPolicy)
    policy.mode, policy.owner, policy.quiet_periods, policy.peer_quiet_until = 'async', 'A', [], 0.
    call = next(row for row in raw['calls'] if row['request']['request_id'] == request['request_id'])
    policy.client = SimpleNamespace(rows=raw['outbox'], creations=raw['request_creations'], calls=[call])
    policy.pending_reply = {'envelope': exchange['message']}
    identity = exchange['message']['capture']['capture_v2']['local_capture']['message_id']
    policy.hold_new_admissions_after_reply('cycle_route', identity, exchange['at'])
    assert policy.peer_quiet_until == exchange['at']+.02
    assert policy.quiet_periods[-1]['reply_request_id'] == request['request_id']
    policy.client.calls = []
    policy.peer_quiet_until = 0.
    policy.hold_new_admissions_after_reply('cycle_route', identity, exchange['at'])
    assert policy.peer_quiet_until == exchange['at']+.08


def test_real_fixed_seed_model_scores_legal_current_candidates():
    root = baseline_artifact().parent.parent
    path = root/'repeated_supervised_training_001'/'model_seed_1701.json'
    raw_path = root/'A1_three_prefer3_002'/'raw.json.gz'
    if not path.exists() or not raw_path.exists():
        pytest.skip('separately trained closed fixture not present')
    model = json.loads(path.read_text())
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    decision = next(row for row in raw['repeated_decisions'] if row['current_admission']['execution_mode'] == 'protected_current')
    enabled = [row for row in decision['candidate_mask'] if row['enabled']]
    audit = native.score_enabled(model, campaign.campaign.reference(path), decision['observation'], enabled)
    assert audit['status'] == 'scored_current_guarded_candidates'
    assert set(audit['scores']) == {row['action_id'] for row in enabled} and 'prefer_8' not in audit['scores']


def test_shutdown_full_task_queue_is_bounded_and_recorded():
    resident = object.__new__(worker.ResidentWorker)
    def full(_):
        raise queue.Full
    resident.tasks = SimpleNamespace(put_nowait=full, close=lambda: None, cancel_join_thread=lambda: None)
    resident.results = SimpleNamespace(close=lambda: None, cancel_join_thread=lambda: None)
    calls = []
    resident.process = SimpleNamespace(terminate=lambda: calls.append('terminate'),
        join=lambda timeout: calls.append(('join', timeout)), is_alive=lambda: False)
    resident.pending, resident.timing = {}, {}
    resident.close()
    assert calls == ['terminate', ('join', 5)] and resident.pending is None
    assert resident.timing['shutdown_with_unconsumed_active_request'] is True


def baseline_artifact():
    path = Path('outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/A1_three_baseline_001/raw.json.gz')
    if not path.exists():
        pytest.skip('separately registered native fixture not present')
    return path


def test_closed_original_reference_and_native_leg_identity():
    raw, _ = campaign.validate_original_reference(baseline_artifact(), 'three_reuse_blocker_11_1')
    for decision in raw['repeated_decisions']:
        bound = native.actual_effects(decision, raw['result']['receipts'], raw['outbox'])
        assert bound['status'].startswith('bound_actual_')
    second = next(row for row in raw['repeated_decisions'] if row['owner'] == 'B'
        and row['opportunity']['target']['business_bag_id'] == 'reuse2')
    bound = native.actual_effects(second, raw['result']['receipts'], raw['outbox'])
    assert bound['loaded_segment'][0]['traversal_id'] + 1 != bound['receipts'][0]['traversal_id']
    corrupted = copy.deepcopy(raw['result']['receipts'])
    next(row for row in corrupted if row['event'] == 'LEG_START' and row['business_bag_id'] == 'reuse2')['transport_leg_id'] += '-wrong'
    assert native.actual_effects(second, corrupted, raw['outbox'])['status'] == 'unknown_unbound'


def test_reference_raw_sha_mismatch_refused(monkeypatch):
    read = campaign.campaign.read
    def corrupt(path):
        value = read(path)
        if Path(path).name == 'worker_report.json':
            value['raw']['sha256'] = '0'*64
        return value
    monkeypatch.setattr(campaign.campaign, 'read', corrupt)
    with pytest.raises(ValueError, match='closed_original_baseline_origin'):
        campaign.validate_original_reference(baseline_artifact(), 'three_reuse_blocker_11_1')


def negative_baseline_artifact():
    path = baseline_artifact().parent.parent/'A_eval_negative_baseline_001'/'raw.json.gz'
    if not path.exists():
        pytest.skip('separately registered closed negative baseline not present')
    return path


def test_reference_accepts_closed_original_default_after_capacity_refusal_without_rewriting():
    raw, _ = campaign.validate_original_reference(negative_baseline_artifact(), 'hold3_11_69_release27_7')
    before = domain.digest(raw)
    eligibility = campaign.original_reference_eligibility(raw)
    assert eligibility['status'] == 'eligible_complete_actual_original_baseline'
    assert raw['summary']['status'] == eligibility['historical_summary_status'] == 'unknown_incomplete_or_unexecuted'
    refused = eligibility['rejected_route_default_continuations']
    assert len(refused) == 1 and refused[0]['job'] == 'reuse3'
    assert refused[0]['ack']['status'] == 'rejected' and refused[0]['rejected_command_executed'] is False
    assert refused[0]['default_edge']['to'] == 3 and refused[0]['default_edge']['time'] == 27.8
    assert domain.digest(raw) == before and eligibility['current_protection_gate_modified'] is False


@pytest.mark.parametrize('failure', ['wrong_mode', 'unfinished', 'missing_edge', 'wrong_leg',
    'wrong_generation', 'wrong_traversal', 'other_rejection', 'ack_not_delivered', 'ack_after_edge', 'ack_before_submit'])
def test_reference_capacity_refusal_exception_rejects_unbound_or_incomplete_evidence(failure):
    raw = json.loads(gzip.decompress(negative_baseline_artifact().read_bytes()))
    identity = 'live:1:B:later-route-2'; output = raw['outbox'][identity]
    if failure == 'wrong_mode':
        raw['specification']['mode'] = 'guarded'
    elif failure == 'unfinished':
        next(row for row in raw['result']['jobs'] if row['business_bag_id'] == 'reuse3')['status'] = 'loaded'
    elif failure in ('missing_edge', 'wrong_leg'):
        edge = next(row for row in raw['result']['receipts'] if row['event'] == 'EDGE_ENTER'
            and row['business_bag_id'] == 'reuse3' and row['from'] == 7)
        if failure == 'missing_edge':
            raw['result']['receipts'].remove(edge)
        else:
            edge['transport_leg_id'] += '-wrong'
    elif failure in ('wrong_generation', 'wrong_traversal'):
        field = 'expected_generation' if failure == 'wrong_generation' else 'expected_traversal'
        output['request'][field] += 1
        for call in raw['calls']:
            if call['request']['request_id'] == identity:
                call['request'][field] = output['request'][field]
    elif failure == 'other_rejection':
        output['ack']['reason'] = 'stale_generation'
    elif failure == 'ack_not_delivered':
        output['ack'].pop('delivered_at')
    elif failure == 'ack_after_edge':
        output['ack']['delivered_at'] = 27.81
    else:
        output['ack']['executed_at'] = 20.
    with pytest.raises(ValueError, match='reference_eligibility_'):
        campaign.original_reference_eligibility(raw)


def test_preparation_pins_independent_reference_eligibility(tmp_path):
    plan = campaign.prepare(tmp_path/'reference_clarification', 'hold3_11_69_release27_7', 'guarded', negative_baseline_artifact())
    eligibility = plan['original_reference_eligibility']
    assert eligibility['historical_summary_status'] == 'unknown_incomplete_or_unexecuted'
    assert eligibility['rejected_route_default_continuations'][0]['rejected_command_executed'] is False
    assert plan['rows']['hold3_11_69_release27_7/guarded']['reference']['completion']['reuse3'] == 30.700000000000006
    campaign.verify(plan)


def test_imported_sources_ignores_inherited_module_proxy_filename(monkeypatch):
    import sys
    from types import ModuleType
    from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3_bound as bound

    class Proxy(ModuleType):
        __file__ = '_g31_inherited_proxy_only.py'

    class VirtualProxy(ModuleType):
        def __getattr__(self, name):
            if name == '__file__':
                return '_g31_virtual_proxy_only.py'
            raise AttributeError(name)

    proxy = Proxy('g31_source_proxy_fixture')
    virtual = VirtualProxy('g31_source_virtual_proxy_fixture')
    assert '__file__' not in vars(proxy)
    assert '__file__' not in vars(virtual)
    monkeypatch.setitem(sys.modules, proxy.__name__, proxy)
    monkeypatch.setitem(sys.modules, virtual.__name__, virtual)
    assert Path(proxy.__file__).resolve() not in bound.imported_sources()
    assert Path(virtual.__file__).resolve() not in bound.imported_sources()


def test_imported_sources_keeps_missing_real_project_source_fail_closed(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3_bound as bound
    from scripts.experiments.g31_ics_circulation import foundation_native_environment as environment

    missing = tmp_path / 'actual_source_fixture.py'
    assert missing.is_relative_to(environment.ROOT)
    missing.write_text('SOURCE_FIXTURE = True\n')
    module = ModuleType('g31_missing_actual_source_fixture')
    module.__file__ = str(missing)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert missing in bound.imported_sources()
    missing.unlink()
    assert missing in bound.imported_sources()
    with pytest.raises(FileNotFoundError):
        environment.archive_sources(tmp_path / 'missing_source_archive', [missing])


def test_repeated_loading_preflight_is_actual_stage_and_once_per_identity():
    policy = object.__new__(native.OwnerPolicy)
    policy.owner, policy.started, policy.exchanges = 'B', set(), []
    emitted = []
    policy.publication = lambda label, cause: emitted.append((label, cause)) or f'actual-publication-{len(emitted)}'
    tray = {'tray_id': 'L', 'node': 7, 'mode': 'loading', 'edge_to': -1, 'business_bag_id': 'reuse2',
        'generation': 8, 'traversal_id': 9}
    view = {'now': 15.011, 'trays': [tray]}
    policy.loading_preflight(view); policy.loading_preflight(view)
    assert len(emitted) == 1 and policy.exchanges[0]['at'] == view['now']
    assert policy.exchanges[0]['local_tray'] == tray and policy.exchanges[0]['future_collection_required'] is True
    policy.loading_preflight({'now': 15.111, 'trays': [{**tray, 'mode': 'loaded'}]})
    assert len(emitted) == 1
    policy.loading_preflight({'now': 20.421, 'trays': [{**tray, 'business_bag_id': 'reuse3', 'generation': 11}]})
    assert len(emitted) == 2


def test_real_failed_collection_preserves_point05_and_ack_causality():
    path = baseline_artifact().parent.parent/'A1_three_prefer3_001'/'raw.json.gz'
    if not path.exists():
        pytest.skip('registered failure fixture not present')
    raw = json.loads(gzip.decompress(path.read_bytes()))
    evidence = raw['repeated_attempts']['B'][0]['evidence']
    local = evidence['information']['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3']['capture']['capture_v2']['local_capture']
    assert evidence['at'] - local['captured_at'] > .05
    report = domain.evaluate(evidence, ('prefer_3',))
    assert report['status'] == 'unknown' and 'invalid_v3_channel_contract_or_causal_age' in report['reasons'][0]
