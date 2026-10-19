"""Pure protocol doubles only; these tests are not two native observations."""
import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_successful_refresh_probe as probe


def unit_offer(now=9.69, request_id='old-own', sequence=1):
    tray = {'tray_id': 'L', 'node': 7, 'mode': 'loaded', 'business_bag_id': 'reuse1',
        'generation': 5, 'traversal_id': 5, 'edge_from': -1, 'edge_to': -1, 'reception_node': -1,
        'committed_prefix': [7], 'available_at': 9.55}
    view = {'owner_id': 'B', 'now': now, 'trays': [tray]}
    pending = {'phase': 'first_reuse_route', 'at': now - .04, 'request_id': request_id,
        'peer_message': 'peer-' + str(sequence), 'root': 'original-root', 'trigger_tray': copy.deepcopy(tray),
        'recollection_index': 0, 'policy_quiet_since': 9.65, 'deadline': 9.73}

    def envelope(identity, captured_at):
        return {'capture': {'capture_v2': {'local_capture': {'message_id': identity,
            'publication_sequence': sequence, 'captured_at': captured_at}}}}

    own = {'transfer-id': {'kind': 'transfer', 'terminal': True, 'request': {'request_id': 'transfer-id'},
                          'ack': {'status': 'received'}}}
    handle = {'raw_endpoints': {'view': view, 'command': {'last_delivered_ack': {
        'planning_snapshot_v3': envelope('own-' + str(sequence), now - .03)}},
        'received': [envelope(pending['peer_message'], now - .01)]},
        'bundle': {'trays': {'L': {'service_ready_at': 9.75}}}}
    observation = {'owner': 'B', 'phase': pending['phase'], 'at': now}
    evidence = {'owner': 'B', 'at': now, 'collection': copy.deepcopy(pending),
        'information': copy.deepcopy(handle), 'own_outbox': copy.deepcopy(own)}
    return {'pending': pending, 'handle': handle, 'view': view, 'evidence': evidence,
        'observation': observation, 'model_report': {'status': 'conditional_current_seed', 'seed': {}, 'candidate_results': {}},
        'actions': [{'action_id': 'native_default', 'enabled': True, 'guard_status': 'passed', 'candidate_id': 'default'}],
        'actual_collection_supported': True, 'initial_reference': {'owner': 'B'},
        'model_and_guard_wall_ms': 1., 'collection_through_offer_wall_ms': 2.,
        'collection_segments': {'real_current_collection_wall_ms': .5}, 'attempt': {}}, own


@pytest.fixture
def unit_control(monkeypatch):
    current = object.__new__(probe.ProbeLaterControl)
    offer, own = unit_offer()
    session = SimpleNamespace(physical_time=9.69, observe_protocol=lambda owner: copy.deepcopy(offer['view']))
    client = SimpleNamespace(context={'owner': 'B', 'accepted_at': 9.69}, owned=lambda owner: own)
    publications = []

    def publish(label, causal):
        publications.append({'label': label, 'causal': copy.deepcopy(causal)})
        return 'new-own-request'

    current.policy = SimpleNamespace(owner='B', pending=copy.deepcopy(offer['pending']), session=session,
        client=client, publication=publish, quiet_periods=[])
    current.adapter = SimpleNamespace(is_native_collected=lambda handle: handle is current.offer['handle'])
    current.mode, current.phases = 'guarded', ('first_reuse_route',)
    current.offer = offer
    current.reference, current.reference_sha = {'owner': 'B'}, 'a' * 64
    current.episode_id = 'unit-only-not-native'
    current.successful_observations = []
    current.followup_request = current.refresh_result = None
    current.transitions, current.collection_failures = [], []
    monkeypatch.setattr(probe.control.representation, 'equivalent_views',
        lambda first, second: (first, probe.control.encoding(first) == probe.control.encoding(second)))
    return current, publications, own


def test_successful_first_offer_is_observation_not_failure_or_action(unit_control):
    current, publications, own = unit_control
    original = copy.deepcopy(own)
    old_offer = current.offer
    current.begin_successful_followup()
    assert current.offer is None and current.transitions == []
    assert len(current.successful_observations) == len(publications) == 1
    saved = current.successful_observations[0]
    assert saved['observation_only'] and not saved['action_or_transition_created']
    assert saved['model_report'] == old_offer['model_report']
    assert saved['initial_reference_sha256'] == current.reference_sha
    assert saved['collection_segments'] == old_offer['collection_segments']
    assert current.policy.pending['request_id'] == 'new-own-request'
    assert current.policy.pending['original_request_id'] == 'old-own'
    assert current.policy.pending['recollection_index'] == 1
    assert current.policy.pending['policy_quiet_since'] == 9.65
    assert current.policy.pending['deadline'] == 9.75
    assert current.policy.session.physical_time == 9.69 and own == original
    assert publications[0]['causal']['prior_collection_succeeded'] is True
    assert 'actual_failed_collection_reason' not in publications[0]['causal']
    assert current.followup_request['nominal_epochs']['physical_wire'] < 9.75
    assert current.policy.quiet_periods[0]['native_physics_paused'] is False
    old_offer['evidence']['at'] = -1
    assert saved['evidence']['at'] == 9.69
    with pytest.raises(ValueError, match='single_followup_budget'):
        current.begin_successful_followup()


@pytest.mark.parametrize('change,reason', [('budget', 'unused_first_reuse_collection_budget'),
    ('window', 'insufficient_actual_service_window'), ('outbox', 'owned_outbox_changed'),
    ('pending', 'pending_identity_changed'), ('admission', 'current_B_admission_required'),
    ('unprotected', 'protected_default_required'), ('unknown', 'known_current_seed_required')])
def test_invalid_followup_never_publishes(unit_control, change, reason):
    current, publications, own = unit_control
    if change == 'budget':
        current.offer['pending']['recollection_index'] = 1
    elif change == 'window':
        current.offer['handle']['bundle']['trays']['L']['service_ready_at'] = probe.collection.sequential_epochs(9.69)['physical_wire']
    elif change == 'outbox':
        own['another'] = {'kind': 'transfer'}
    elif change == 'pending':
        current.policy.pending['request_id'] = 'different'
    elif change == 'admission':
        current.policy.client.context['owner'] = 'A'
    elif change == 'unprotected':
        current.offer['actions'][0]['enabled'] = False
    else:
        current.offer['model_report']['status'] = 'unknown'
    with pytest.raises(ValueError, match=reason):
        current.begin_successful_followup()
    assert publications == []
    assert current.successful_observations == []


def second_offer(current):
    offer, _ = unit_offer(now=9.73, request_id='new-own-request', sequence=2)
    offer['pending'].update(successful_followup_probe=True, recollection_index=1)
    offer['evidence']['collection'] = copy.deepcopy(offer['pending'])
    current.offer = offer
    return offer


def test_second_success_keeps_offer_for_one_actual_action_and_defers_refresh_audit(unit_control, monkeypatch):
    current, _, _ = unit_control
    current.begin_successful_followup()
    second = second_offer(current)

    def forbid_audit(*args, **kwargs):
        raise AssertionError('refresh audit belongs after native episode')

    monkeypatch.setattr(probe.refresh, 'refresh_audit', forbid_audit)
    current.finish_successful_followup()
    assert current.offer is second
    assert len(current.successful_observations) == 2
    assert current.transitions == [] and current.refresh_result is None
    assert second['attempt']['successful_followup_observation_index'] == 1
    with pytest.raises(ValueError, match='exactly_one_prior'):
        current.finish_successful_followup()


@pytest.mark.parametrize('change', ['old_time', 'old_own', 'old_peer', 'wrong_request'])
def test_second_snapshot_requires_new_real_identity_data(unit_control, change):
    current, _, _ = unit_control
    current.begin_successful_followup()
    second = second_offer(current)
    if change == 'old_time':
        second['observation']['at'] = 9.69
    elif change == 'wrong_request':
        second['evidence']['collection']['request_id'] = 'old-own'
    elif change == 'old_own':
        second['evidence']['information']['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3'][
            'capture']['capture_v2']['local_capture']['publication_sequence'] = 1
    else:
        second['evidence']['information']['raw_endpoints']['received'][0]['capture']['capture_v2'][
            'local_capture']['publication_sequence'] = 1
    with pytest.raises(ValueError):
        current.finish_successful_followup()
    assert len(current.successful_observations) == 1


def test_collect_hook_consumes_first_offer_before_environment_can_make_transition(unit_control, monkeypatch):
    current, _, _ = unit_control
    monkeypatch.setattr(probe.control.LaterControl, 'collect', lambda self, view: None)
    current.collect(current.offer['view'])
    assert current.offer is None
    assert not current.transitions


def test_factory_is_opt_in_and_default_environment_keeps_original_controller():
    default = probe.environment.FoundationNativeEnvironment(None, None, 'mechanism/incumbent', None)
    assert default._later_control_factory is probe.control.LaterControl
    custom = lambda *args, **kwargs: None
    explicit = probe.environment.FoundationNativeEnvironment(None, None, 'mechanism/incumbent', None, later_control_factory=custom)
    assert explicit._later_control_factory is custom
    with pytest.raises(ValueError, match='explicit_later_control_factory'):
        probe.environment.FoundationNativeEnvironment(None, None, 'mechanism/incumbent', None, later_control_factory=False)


def test_worker_dependency_modules_are_imported_before_native_archive():
    sources = {Path(path).resolve() for path in probe.environment.online.old.bound.imported_sources()}
    for module in (probe, probe.refresh, probe.model, probe.episode, probe.campaign, probe.control, probe.collection):
        assert Path(module.__file__).resolve() in sources
    assert 'import ' not in inspect.getsource(probe.worker)


def test_event_classifier_keeps_transfer_and_route_effects_and_only_skips_communication_acks():
    rows = [{'event': 'RESOURCE_WAIT'}, {'event': 'PROTOCOL_ACK_DELIVERED'},
            {'event': probe.COMMAND_ACK_EVENT, 'reason': 'route-id:1'},
            {'event': probe.COMMAND_ACK_EVENT, 'reason': 'planning-id:1'}]
    raw = {'result': {'receipts': rows}, 'outbox': {'route-id': {'kind': 'route'}, 'planning-id': {'kind': 'planning_snapshot_v3'}}}
    assert probe.physical_receipts(raw) == rows[:3]
    raw['result']['receipts'].append({'event': 'NEW_PHYSICAL_KIND'})
    with pytest.raises(ValueError, match='unclassified_native_event'):
        probe.physical_receipts(raw)
    raw['result']['receipts'].pop()
    raw['outbox']['planning-id']['kind'] = 'new_unknown_kind'
    with pytest.raises(ValueError, match='unclassified_command_ACK_kind'):
        probe.physical_receipts(raw)


@pytest.fixture
def registered(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    monkeypatch.setattr(probe.campaign, 'source_pins', lambda: {})
    output = tmp_path / 'probe'
    output.mkdir()
    plan = {'schema': probe.SCHEMA, 'status': 'prepared_unexecuted', 'hard_seconds': 150,
        'native_branches': 1, 'automatic_retries': 0, 'case': 'mechanism', 'method': 'incumbent',
        'horizon': 40., 'probe_owner': 'B', 'extra_successful_pairs': 1,
        'source_pins': {}, 'baseline': {}, 'runtime_references': []}
    probe.campaign.write_new(output / 'plan.json', plan)
    return output, plan


@pytest.mark.parametrize('field,value', [('hard_seconds', 151), ('extra_successful_pairs', 2),
    ('automatic_retries', 1), ('native_branches', 2), ('probe_owner', 'A')])
def test_fixed_protocol_rejects_expansion(registered, field, value):
    _, plan = registered
    plan[field] = value
    with pytest.raises(ValueError, match='fixed_probe_protocol'):
        probe.check_plan(plan)


@pytest.mark.parametrize('status,exitcode,passed', [('exited', 0, True), ('hard_timeout', 0, False), ('exited', 1, False)])
def test_launch_requires_actual_process_success_even_after_complete_report(registered, monkeypatch, status, exitcode, passed):
    output, _ = registered

    def fake_run(command, **kwargs):
        assert kwargs['timeout'] == 150
        assert command[command.index('--admission') + 1] == kwargs['admission']
        raw_path = output / 'native/raw.json.gz'
        probe.campaign.write_new(raw_path, {'unit_artifact': True})
        raw = probe.campaign.reference(raw_path)
        native_path = output / 'native/receipt.json'
        probe.campaign.write_new(native_path, {'status': 'assessed', 'run_acceptance_status': 'closed_run_acceptance_passed', 'raw_artifact': raw})
        for name in ('probe_observations.json', 'refresh_audit.json'):
            probe.campaign.write_new(output / name, {})
        probe.campaign.write_new(output / 'worker_report.json', {'status': 'completed_successful_refresh_probe',
            'source_and_reference_exit_pins_passed': True, 'native_raw': raw,
            'native_receipt': probe.campaign.reference(native_path),
            'probe_observations': probe.campaign.reference(output / 'probe_observations.json'),
            'refresh_audit': probe.campaign.reference(output / 'refresh_audit.json')})
        return {'status': status, 'exitcode': exitcode}

    monkeypatch.setattr(probe.bounded_windows_job, 'run', fake_run)
    result = probe.launch(output)
    assert (result['status'] == 'completed_successful_refresh_probe') is passed
    with pytest.raises(FileExistsError):
        probe.launch(output)


def test_prepare_declares_zero_native_runs_and_cannot_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    contract = tmp_path / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    binary = tmp_path / 'unit-binary'
    binary.write_bytes(b'unit')
    probe.campaign.write_new(contract, {'binary': str(binary)})
    probe.campaign.write_new(contract.parent / 'native027_semantic_native_002/receipt.json', {})
    monkeypatch.setattr(probe, 'baseline_references', lambda: {})
    monkeypatch.setattr(probe.campaign, 'source_pins', lambda: {})
    output = tmp_path / 'fresh'
    result = probe.prepare(output)
    assert result['status'] == 'prepared_unexecuted' and result['automatic_retries'] == 0
    assert result['hard_seconds'] == 150 and not (output / 'native').exists()
    with pytest.raises(ValueError, match='fresh_workspace_output'):
        probe.prepare(output)
