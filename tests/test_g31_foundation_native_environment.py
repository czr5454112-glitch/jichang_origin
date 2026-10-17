"""API scheduling/isolation tests only; mocks are not physical evidence."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_native_environment as foundation


class SessionStub:
    physical_time = .11

    def __init__(self):
        self.reads = []

    def observe_protocol(self, owner):
        self.reads.append(('view', owner))
        return {'owner_id': owner, 'trays': [{'tray_id': owner, 'node': 0, 'business_bag_id': ''}],
                'now': self.physical_time, 'jobs': [], 'node_contracts': [{'node': 0, 'resource_owner': owner}]}

    def protocol_planning_snapshots(self, owner):
        self.reads.append(('delivered', owner))
        return [{'capture': {'target_owner': owner}, 'delivered_at': .1, 'message_id': 'delivered-to-' + owner}]

    def offline_state_sha256(self):
        return 'constant-unit-stub-not-native-evidence'

    def advance_until_owner_notification(self, owners, cursors, deadline, max_events):
        self.physical_time = deadline
        return {'status': 'horizon_reached', 'timestamp_complete': True, 'notifications': {}}


def environment_stub():
    environment = foundation.FoundationNativeEnvironment(None, None, 'mechanism/incumbent', None)
    environment._session = SessionStub()
    environment._client = SimpleNamespace(calls=[], owned=lambda owner: {'owned': {'owner_id': owner}})
    environment._row = {'method': 'coordinate_strict'}
    environment._status = 'running'
    environment._phase = 'retained'
    environment._pending = ['A', 'B']
    environment._policies = {owner: SimpleNamespace(pending=None) for owner in foundation.OWNERS}
    environment._batches = []
    environment._cursors = {'A': 0, 'B': 0}
    environment._tick = 0
    environment._activations = 0
    return environment


def test_observe_only_calls_requested_owner_endpoints():
    environment = environment_stub()
    observation = environment.observe('A')
    assert environment._session.reads == [('view', 'A'), ('delivered', 'A')]
    assert observation['own_outbox'] == {'owned': {'owner_id': 'A'}}
    assert observation['privileged_evaluator_state_included'] is False
    assert 'result' not in observation


def test_observation_is_detached_data():
    environment = environment_stub()
    first = environment.observe('A')
    first['own_outbox']['owned']['owner_id'] = 'B'
    assert environment.observe('A')['own_outbox']['owned']['owner_id'] == 'A'


def test_shadow_consumes_neither_owner_nor_activation():
    environment = environment_stub()
    candidate = environment.candidates('A')['actions'][0]
    before = copy.deepcopy(environment._pending)
    report = environment.submit('A', candidate['candidate_id'], shadow=True)
    assert report['authority'] is False
    assert report['native_state_before'] == report['native_state_after']
    assert environment._pending == before
    assert environment._activations == 0
    assert environment._audit == []
    assert environment._client.calls == []


@pytest.mark.parametrize('owner,candidate', [('B', '0:B:activate_retained_policy'), ('A', '99:A:activate_retained_policy'), ('A', '0:B:activate_retained_policy')])
def test_wrong_owner_and_stale_identity_rejected(owner, candidate):
    environment = environment_stub()
    with pytest.raises(ValueError):
        environment.submit(owner, candidate)
    assert not environment._client.calls


def test_advance_does_not_skip_unhandled_owner():
    environment = environment_stub()
    with pytest.raises(ValueError, match='consume_current'):
        environment.advance_to_next_decision()
    assert environment._session.physical_time == .11


def test_actual_step_calls_retained_policy_once():
    environment = environment_stub()
    triggers = []
    environment._triggers = {'A': {'periodic_tick': True}}
    environment._policies['A'].activate = triggers.append
    candidate = environment.candidates('A')['actions'][0]
    report = environment.submit('A', candidate['candidate_id'])
    assert triggers == [{'periodic_tick': True}]
    assert report['submitted_is_not_physical_success'] is True
    assert environment._activations == 1
    assert environment._pending == ['B']
    with pytest.raises(ValueError):
        environment.submit('A', candidate['candidate_id'])


def test_time_advancement_comes_from_native_endpoint():
    environment = environment_stub()
    environment._pending = []
    environment._tick = 1
    boundary = environment.advance_to_next_decision()
    assert boundary['event_time_s'] == .11 + .05
    assert boundary['delta_sim_time_s'] == pytest.approx(.05)
    assert boundary['due_owners'] == ['A', 'B']
    assert boundary['decision_epoch'] == 1


def test_early_outcome_and_reset_rejected():
    environment = environment_stub()
    with pytest.raises(ValueError, match='terminal_evaluator_only'):
        environment.outcome()
    with pytest.raises(ValueError, match='fresh_admitted'):
        environment.reset()


def test_initial_nondefault_not_globally_disabled():
    environment = environment_stub()
    environment._phase = 'initial'
    mask = environment.candidates('A')
    assert mask['actions'][0]['action'] == 'coordinate_strict'
    assert mask['actions'][0]['enabled']
    assert 'finite_MPC' in mask['supported_initial_methods']
    assert mask['initial_nondefault_R2_disabled'] is False
    assert mask['later_free_action_mask']['enabled'] is False
    assert foundation.CAPABILITIES['rl_ready'] is False


def test_activation_budget_is_unknown_not_finished():
    environment = environment_stub()
    environment._pending = []
    environment._activations = foundation.online.old.MAX_ACTIVATIONS
    assert environment.advance_to_next_decision()['status'] == 'unknown_activation_budget'


@pytest.mark.parametrize('leak', ['foreign_occupancy', 'foreign_tray', 'undelivered', 'wrong_target'])
def test_snapshot_rejects_foreign_dynamic_state_and_undelivered_message(leak):
    session = SessionStub()
    view, received = session.observe_protocol('A'), session.protocol_planning_snapshots('A')
    if leak == 'foreign_occupancy':
        view['node_contracts'].append({'node': 1, 'resource_owner': 'B', 'occupancy': 1})
    elif leak == 'foreign_tray':
        view['trays'][0]['node'] = 1
    elif leak == 'undelivered':
        received[0]['delivered_at'] = 1.
    else:
        received[0]['capture']['target_owner'] = 'B'
    with pytest.raises(ValueError):
        foundation.validate_owner_snapshot('A', view, received)
