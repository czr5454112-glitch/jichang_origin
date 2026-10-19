"""Saved-data and semantic tests; these do not certify native concurrency."""
import copy
import gzip
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_multirate as multirate
from scripts.experiments.g31_ics_circulation import foundation_multirate_probe as probe


@pytest.fixture(scope='module')
def saved_context():
    raw = json.loads(gzip.decompress((probe.comparison.BASELINE / 'raw.json.gz').read_bytes()))
    transition = next(row for row in raw['later_transitions'] if row['owner'] == 'B')
    failures = raw['later_collection_failures']['B']
    assert not failures
    # The original actual endpoint payload is retained in the decision record.
    decision = raw['decisions']['B'][0]
    evidence = {'schema': multirate.control.EVIDENCE_SCHEMA, 'owner': 'B',
        'phase': decision['phase'], 'at': decision['at'], 'collection': copy.deepcopy(decision['collection']),
        'information': copy.deepcopy(decision['information']), 'retained': copy.deepcopy(raw['retained_ledgers']['B']),
        'own_calls': [copy.deepcopy(row) for row in raw['calls'][:decision['predecision_call_prefix_count']]
                      if row['request']['owner_id'] == 'B'], 'own_outbox': {}}
    return evidence, transition['initial_reference']


@pytest.fixture
def context(saved_context):
    evidence, reference = copy.deepcopy(saved_context)
    advice = multirate.advice_from_evidence(evidence, reference)
    return advice, evidence['information']['raw_endpoints']['view']


def test_advice_preserves_source_age_and_original_reference(saved_context):
    evidence, reference = copy.deepcopy(saved_context)
    advice = multirate.advice_from_evidence(evidence, reference)
    assert advice['source_captured_at'] < advice['capture_sim_time']
    assert advice['source_collection_valid_through'] == advice['source_captured_at'] + .05
    assert advice['use_by'] == evidence['information']['bundle']['trays']['L']['service_ready_at'] - .01
    assert advice['original_reference'] == reference
    reference['completion']['loaded'] = -999
    evidence['at'] = -999
    assert advice['original_reference']['completion']['loaded'] > 0
    assert advice['capture_sim_time'] > 0
    assert advice['execution_authority'] is False and advice['current_capability_id'] is None


def test_before_deadline_still_requires_fresh_current_revalidation(context):
    advice, view = context
    result = multirate.screen_current(advice, view, {})
    assert result['status'] == 'requires_fresh_current_admission_and_full_revalidation'
    assert result['reasons'] == []
    assert result['execution_authority'] is False and not result['old_collection_capability_reusable']


def test_no_new_message_expiry_never_extends_point05_contract(context):
    advice, view = context
    view['now'] = advice['source_collection_valid_through'] + 1e-6
    assert view['now'] < advice['use_by']
    result = multirate.screen_current(advice, view, {})
    assert result['status'] == 'full_refresh_required'
    assert result['reasons'] == ['old_collection_expired_full_refresh_required']
    assert result['execution_authority'] is False


@pytest.mark.parametrize('offset', [0., .001, 10.])
def test_exact_or_late_action_deadline_refuses_without_action(context, offset):
    advice, view = context
    view['now'] = advice['use_by'] + offset
    result = multirate.screen_current(advice, view, {})
    assert result['status'] == 'rejected' and 'action_deadline_missed' in result['reasons']
    assert result['new_physical_commands'] == 0


@pytest.mark.parametrize('field,value,reason', [('generation', 999, 'tray_generation_changed'),
    ('committed_prefix', [7, 8], 'target_or_immutable_prefix_changed'),
    ('edge_to', 8, 'target_or_immutable_prefix_changed')])
def test_changed_current_target_refuses_even_before_deadline(context, field, value, reason):
    advice, view = context
    tray = next(row for row in view['trays'] if row['tray_id'] == 'L')
    tray[field] = value
    result = multirate.screen_current(advice, view, {})
    assert result['status'] == 'rejected' and reason in result['reasons']


@pytest.mark.parametrize('ack', [None, {'status': 'received'}, {'status': 'received', 'delivered_at': 100.}])
def test_ack_unknown_never_promotes_inventory(context, ack):
    advice, view = context
    owned = {'transfer': {'kind': 'transfer', 'terminal': True, 'ack': ack or {}}}
    result = multirate.screen_current(advice, view, owned)
    assert result['status'] == 'rejected' and 'physical_ACK_unknown_or_pending' in result['reasons']
    assert result['unresolved_physical_requests'] == ['transfer']
    assert result['predicted_inventory_promoted_to_actual'] is False


def test_poll_without_ready_never_waits_for_model_or_reads_current_view(context):
    advice, view = context
    def forbidden(*args, **kwargs):
        raise AssertionError('fast path must not wait or collect before result readiness')
    current = object.__new__(probe.MultirateLaterControl)
    current.policy = SimpleNamespace(session=SimpleNamespace(physical_time=view['now'], observe_protocol=forbidden))
    current.predictor = SimpleNamespace(started=SimpleNamespace(is_set=lambda: True),
        done=SimpleNamespace(is_set=lambda: False), finish=forbidden)
    current.advice, current.samples, current.poll_wall_ms = advice, [], []
    current.expiry_event = current.result_delivery = None
    current.poll()
    assert current.samples[0]['worker_started'] and not current.samples[0]['worker_done']
    assert current.result_delivery is None and len(current.poll_wall_ms) == 1


def test_real_prediction_remains_detached_and_retains_all_five_jobs(saved_context):
    evidence, reference = copy.deepcopy(saved_context)
    before = multirate.control.encoding(evidence)
    report = multirate.model.evaluate(evidence, ('native_default', 'prefer_8'))
    assert report['status'] == 'conditional_current_seed'
    assert probe.known_prediction(report)
    assert multirate.control.encoding(evidence) == before
    assert set(report['candidate_results']) == {'native_default', 'prefer_8'}
    for result in report['candidate_results'].values():
        assert set(result['completion']) == set(reference['completion']) == set(multirate.control.JOBS)
        assert result['online_executable'] is False and result['native_protection_certified'] is False


@pytest.mark.parametrize('mutation', [
    lambda report: report['candidate_results'].pop('prefer_8'),
    lambda report: report['candidate_results']['prefer_8'].update(status='unknown'),
    lambda report: report['candidate_results']['prefer_8'].update(completion=None),
    lambda report: report['candidate_results']['native_default']['completion'].pop('receiver'),
    lambda report: report['candidate_results']['native_default']['completion'].update(receiver=float('nan')),
    lambda report: report['candidate_results']['native_default']['completion'].update(receiver=-1.),
    lambda report: report['candidate_results']['native_default'].update(online_executable=True),
    lambda report: report['evaluation'].update(source_exit_pins_passed=False),
])
def test_seed_success_cannot_hide_unknown_or_unbound_predictions(mutation):
    report = {'status': 'conditional_current_seed',
        'evaluation': {'source_exit_pins_passed': True, 'native_execution_authority': False},
        'candidate_results': {action: {'status': 'conditional_prediction', 'online_executable': False,
            'native_protection_certified': False, 'completion': dict.fromkeys(multirate.control.JOBS, 10.)}
            for action in ('native_default', 'prefer_8')}}
    assert probe.known_prediction(report)
    mutation(report)
    assert not probe.known_prediction(report)


def test_protocol_traffic_is_not_evidence_of_physical_progress():
    receipts = [{'event': event, 'time': 10., 'tray_id': 'L'} for event in
        ('PROTOCOL_ACK_DELIVERED', 'MODULE_REQUEST_DELIVERED', 'ROUTE_INTENT_updated', 'RESOURCE_WAKE')]
    assert probe.physical_progress(receipts, 9., 11.) == []
    motion = {'event': 'EDGE_ENTER', 'time': 10.5, 'tray_id': 'L'}
    assert probe.physical_progress(receipts + [motion], 9., 11.) == [motion]
    assert probe.physical_progress([motion], 10.5, 11.) == []
