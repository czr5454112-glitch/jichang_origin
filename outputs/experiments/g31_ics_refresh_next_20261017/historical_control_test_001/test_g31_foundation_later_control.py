"""Saved-data and API-double tests; only actual fresh native runs grant authority."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import FunctionType, MethodType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_later_control as control
from scripts.experiments.g31_ics_circulation import foundation_later_episode as episode

RAW = Path(__file__).resolve().parents[1] / 'outputs/experiments/g31_ics_foundation_learning_20261017/native_001/raw.json.gz'


@pytest.fixture(scope='module')
def saved():
    return json.loads(gzip.decompress(RAW.read_bytes()))


def evidence(raw, owner):
    decision = raw['decisions'][owner][0]
    return copy.deepcopy({'schema': control.EVIDENCE_SCHEMA, 'owner': owner, 'phase': decision['phase'],
        'at': decision['at'], 'collection': decision['collection'], 'information': decision['information'],
        'retained': raw['retained_ledgers'][owner], 'own_outbox': {},
        'own_calls': [row for row in raw['calls'][:decision['predecision_call_prefix_count']]
            if row['request']['owner_id'] == owner]})


def original_decide(policy, view):
    raise AssertionError('old fixed choice must not execute for supported phase')


def stub_controller(raw, owner='B', mode='guarded', prediction_status='conditional_prediction'):
    data = evidence(raw, owner)
    reference = control.initial_reference(raw['initial_owners'][owner])
    view = data['information']['raw_endpoints']['view']
    rows = {data['collection']['request_id']: {'ack': {'status': 'delivered'}}}
    client = SimpleNamespace(rows=rows, calls=[], context={'owner': owner, 'accepted_at': data['at']}, owned=lambda requested: rows)
    session = SimpleNamespace(physical_time=data['at'], observe_protocol=lambda requested: copy.deepcopy(view))
    adapter = control.historical.OwnerCollectionAdapter(client, session, owner)
    adapter.collect_native = lambda *args, **kwargs: data['information']
    adapter.is_native_attempt = lambda value: value is data['information']
    adapter.is_native_collected = lambda value: value is data['information']
    policy = SimpleNamespace(owner=owner, client=client, session=session, native=None, accepted=None,
        ledger=SimpleNamespace(audit_copy=lambda: copy.deepcopy(data['retained'])), pending=copy.deepcopy(data['collection']),
        peer_quiet_until=0., collection_attempts=[], decisions=[], submissions=[])
    policy.decide_pending = MethodType(FunctionType(original_decide.__code__, {'adapter': adapter}), policy)

    def submit_action(kind, selected):
        policy.submissions.append((kind, selected))
        return None if kind == 'route' and selected is None else 'unit-command'

    policy.route_tray = lambda actual, tray, following, causal: submit_action('route', following)
    policy.return_tray = lambda actual, tray, demand, delay, causal: submit_action('transfer', delay)

    def predict(seed, action):
        completion = copy.deepcopy(reference['completion'])
        if action in ('prefer_8', 'return_not_before_7_84'):
            completion['reuse1'] += 1.
        return {'status': prediction_status, 'completion': completion}

    model = SimpleNamespace(VERSION='unit_only_not_native_model', build_seed=lambda supplied: {'status': 'unit_seed'}, predict=predict)
    controller = control.LaterControl(policy, reference, model=model, mode=mode)
    controller.collect(view)
    return controller, data


@pytest.mark.parametrize('owner', ['A', 'B'])
def test_actor_is_detached_actual_delivered_v3_and_not_model_truth(saved, owner):
    source = evidence(saved, owner)
    observation = control.actor_observation(source)
    selected = [message for message in observation['delivered_v3']
        if message['message_id'] == observation['collection']['peer_message_id']]
    assert len(selected) == 1 and selected[0]['fresh'] is True
    assert selected[0]['status'] == 'conditional'
    assert observation['model_predictions_included'] is False
    assert 'model_report' not in observation and 'retained' not in observation
    observation['local_view']['now'] = -1
    assert source['information']['raw_endpoints']['view']['now'] > 0


@pytest.mark.parametrize('change', ['target', 'undelivered', 'owner_view'])
def test_actor_rejects_wrong_owner_or_undelivered(saved, change):
    source = evidence(saved, 'B')
    if change == 'owner_view':
        source['information']['raw_endpoints']['view']['owner_id'] = 'A'
    else:
        envelope = source['information']['raw_endpoints']['received'][0]
        if change == 'target':
            envelope['capture']['capture_v2']['local_capture']['target_owner'] = 'A'
        else:
            envelope['delivered_at'] = source['at'] + .1
    with pytest.raises(ValueError):
        control.actor_observation(source)


def test_freshness_is_not_status_relabel_or_delivery_invention(saved):
    source = evidence(saved, 'B')
    for envelope in source['information']['raw_endpoints']['received']:
        envelope['capture']['capture_v2']['local_capture']['valid_until'] = source['at']
    assert not any(message['fresh'] for message in control.actor_observation(source)['delivered_v3'])


@pytest.mark.parametrize('status', ['conditional_forecast', 'unknown', 'unknown_unfinished_projection', 'unknown_event_budget'])
def test_unknown_predictions_never_pass_despite_retained_completion(saved, status):
    reference = control.initial_reference(saved['initial_owners']['B'])
    assert control.protected({'status': status, 'completion': reference['completion']}, reference)['status'] == 'unknown'


def test_guard_rejects_one_ulp_and_never_refreshes_reference(saved):
    reference = control.initial_reference(saved['initial_owners']['B'])
    changed = copy.deepcopy(reference['completion'])
    changed['reuse1'] = math.nextafter(changed['reuse1'], math.inf)
    assert control.protected({'status': 'conditional_prediction', 'completion': changed}, reference)['status'] == 'rejected'
    assert reference == control.initial_reference(saved['initial_owners']['B'])


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1., True])
def test_nonfinite_or_invalid_completion_is_unknown(saved, bad):
    reference = control.initial_reference(saved['initial_owners']['B'])
    changed = copy.deepcopy(reference['completion'])
    changed['reuse1'] = bad
    assert control.protected({'status': 'conditional_prediction', 'completion': changed}, reference)['status'] == 'unknown'


def test_absolute_return_and_no_command_default_semantics():
    action = control.semantic_action('first_return', 'return_not_before_7_84', 7.34)
    assert action['absolute_earliest_departure'] == 7.84
    assert control.semantic_action('first_return', 'return_not_before_7_84', 8.)['absolute_earliest_departure'] == 8.
    default = control.semantic_action('first_reuse_route', 'native_default', 9.69)
    assert default['kind'] == 'no_command' and default['next'] is None
    assert default['default_does_not_clear_existing_preference'] is True


def test_collection_pauses_before_any_physical_submission(saved):
    controller, _ = stub_controller(saved)
    assert controller.policy.submissions == [] and controller.policy.pending is not None
    assert [candidate['enabled'] for candidate in controller.candidates()] == [True, False]
    assert controller.candidates()[1]['guard_status'] == 'rejected'
    assert controller.offer['model_report']['candidate_results']['prefer_8']['completion']
    assert 'model_report' not in controller.observation()
    public = controller.candidates()
    public[1]['enabled'] = True
    with pytest.raises(ValueError, match='disabled_or_stale'):
        controller.submit(public[1]['candidate_id'])
    assert controller.policy.submissions == []


def test_default_has_no_command_id_and_no_fabricated_ack(saved):
    controller, _ = stub_controller(saved)
    result = controller.submit(controller.candidates()[0]['candidate_id'])
    assert controller.policy.submissions == [('route', None)]
    assert result['command_id'] is None and result['command_ids'] == []
    assert result['ACK'] is None and result['ACK_status'] == 'not_applicable_no_command'
    assert result['truncated'] is True and result['terminated'] is False
    assert controller.policy.pending is None and controller.offer is None
    controller.update_ack()
    assert controller.transitions[0]['ACK'] is None
    assert result['collection_to_decision_record_wall_ms'] >= result['collection_through_offer_wall_ms']
    assert 'excludes earlier message collection' in result['request_timing_scope']


def test_fresh_batch_evaluation_keeps_guards_and_is_not_actor_input(saved):
    controller, data = stub_controller(saved)
    calls = []
    expected = copy.deepcopy(controller.offer['model_report'])

    def evaluate(supplied, actions):
        calls.append((copy.deepcopy(supplied), tuple(actions)))
        return {**copy.deepcopy(expected), 'evaluation': {'scope': 'unit_request_only'}}

    def forbidden(*args):
        raise AssertionError('legacy per-candidate path invoked despite explicit batch API')

    controller.model = SimpleNamespace(evaluate=evaluate, build_seed=forbidden, predict=forbidden)
    controller.offer = None
    controller.collect(data['information']['raw_endpoints']['view'])
    assert len(calls) == 1 and calls[0][1] == control.PHASE_ACTIONS[data['phase']]
    assert calls[0][0]['at'] == data['at']
    assert [candidate['guard_status'] for candidate in controller.candidates()] == ['passed', 'rejected']
    assert [candidate['enabled'] for candidate in controller.candidates()] == [True, False]
    assert 'evaluation' not in controller.observation()
    assert 'request_started_ns' not in controller.audit_copy()['current_offer']


@pytest.mark.parametrize('change', ['unsealed_copy', 'pending', 'time', 'view', 'outbox', 'reference'])
def test_submit_rechecks_current_authority_and_identity(saved, change):
    controller, _ = stub_controller(saved)
    candidate = controller.candidates()[0]['candidate_id']
    if change == 'unsealed_copy':
        controller.offer['handle'] = copy.deepcopy(controller.offer['handle'])
    elif change == 'pending':
        controller.policy.pending['request_id'] = 'changed'
    elif change == 'time':
        controller.policy.session.physical_time += .1
    elif change == 'view':
        controller.policy.session.observe_protocol = lambda owner: {'node_records': [], 'edge_records': []}
    elif change == 'outbox':
        controller.policy.client.rows['unexpected'] = {}
    else:
        controller.reference['completion']['reuse1'] += 1.
    with pytest.raises(ValueError):
        controller.submit(candidate)
    assert not controller.policy.submissions


def test_plain_saved_handle_has_no_real_native_authority(saved):
    information = evidence(saved, 'B')['information']
    assert control.historical.is_native_attempt(information) is False
    assert control.historical.is_native_collected(information) is False


def test_diagnostic_preserves_failed_business_guard_and_actual_ack(saved):
    controller, _ = stub_controller(saved, mode='diagnostic_intervention')
    candidate = controller.candidates()[1]
    assert candidate['enabled'] is True and candidate['guard_status'] == 'rejected'
    result = controller.submit(candidate['candidate_id'])
    assert result['command_id'] == 'unit-command'
    assert result['conditional_protection_status'] == 'rejected'
    assert result['behavior_mode'] == 'diagnostic_intervention'
    controller.policy.client.rows['unit-command'] = {'ack': {'status': 'updated', 'delivered_at': 99.}}
    controller.update_ack()
    assert controller.transitions[0]['ACK'] is None
    ack = {'status': 'updated', 'delivered_at': controller.policy.session.physical_time}
    controller.policy.client.rows['unit-command']['ack'] = ack
    controller.update_ack()
    assert controller.transitions[0]['ACK'] == ack
    first_observed_at = controller.transitions[0]['ACK_observed_at']
    controller.policy.session.physical_time += 1.
    controller.update_ack()
    assert controller.transitions[0]['ACK_observed_at'] == first_observed_at


def test_audit_preserves_offer_and_masks_but_not_collection_capability(saved):
    controller, _ = stub_controller(saved)
    audit = controller.audit_copy()
    assert 'handle' not in audit['current_offer']
    assert audit['current_offer']['actions'][1]['guard_status'] == 'rejected'
    audit['current_offer']['actions'][1]['enabled'] = True
    assert controller.candidates()[1]['enabled'] is False


def test_all_unknown_retains_complete_offer_without_default_fallback(saved):
    controller, _ = stub_controller(saved, prediction_status='unknown_event_budget')
    audit = controller.audit_copy()
    assert not any(candidate['enabled'] for candidate in audit['current_offer']['actions'])
    assert audit['collection_failures'][0]['reason'] == 'unknown_or_rejected_all_candidates'
    assert all(candidate['mask_reason'] == 'original_reference_unknown'
        for candidate in audit['collection_failures'][0]['actions'])
    assert audit['current_offer']['model_report']['candidate_results']
    assert controller.policy.submissions == []


@pytest.mark.parametrize('change', ['none', 'hash', 'clock'])
def test_new_actor_callback_records_and_enforces_state_and_clock_isolation(saved, change):
    controller, _ = stub_controller(saved)
    native = episode.environment.FoundationNativeEnvironment(None, None, 'mechanism/incumbent', None)
    native._session = controller.policy.session
    native._session.state = 'before'
    native._session.offline_state_sha256 = lambda: native._session.state
    native._pending, native._status, native._later_controls = ['B'], 'running', {'B': controller}

    def choose(observation, candidates):
        assert 'native_state_before' not in observation and observation['schema'] == control.ACTOR_SCHEMA
        observation['local_view']['now'] = -1
        if change == 'hash':
            native._session.state = 'after'
        elif change == 'clock':
            native._session.physical_time += .1
        return candidates[0]['candidate_id']

    if change == 'none':
        assert native.choose_later('B', choose) == controller.candidates()[0]['candidate_id']
        assert controller.observation()['local_view']['now'] > 0
    else:
        with pytest.raises(ValueError, match='changed_native_state_or_clock'):
            native.choose_later('B', choose)
    assert controller.audit_copy()['current_offer']['actor_state_unchanged'] is (change == 'none')
    assert controller.offer['actor_choose_wall_ms'] >= controller.offer['actor_inference_wall_ms'] >= 0.
    assert not controller.policy.submissions


def test_fixed_actor_refuses_silent_fallback(saved):
    controller, _ = stub_controller(saved)
    choose = episode.fixed_choice({'first_reuse_route': 'prefer_8'})
    with pytest.raises(ValueError, match='no_silent_fallback'):
        choose(controller.observation(), controller.candidates())


def test_offline_terminal_comparison_is_five_job_zero_tolerance(saved):
    changed = copy.deepcopy(saved)
    job = next(job for job in changed['result']['jobs'] if job['business_bag_id'] == 'reuse1')
    job['completed_at'] = math.nextafter(job['completed_at'], math.inf)
    changed['summary']['completion']['reuse1'] = job['completed_at']
    report = episode.compare_terminal(saved, changed)
    assert report['strict_protected'] is False and report['per_job_delta']['reuse1'] > 0
    assert len(report['per_job_delta']) == 5
